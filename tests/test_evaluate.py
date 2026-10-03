"""Acceptance-output tests for the deterministic case evaluator."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from ddg.approval import approve, validate_draft
from ddg.demo import build_demo
from ddg.proposal import load_context, propose
from scripts.evaluate import CASES, evaluate


ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ddg evaluation ")
        self.root = Path(self.temp.name)
        self.repo = self.root / "synthetic repo"
        demo = build_demo(self.repo)
        marker = json.loads((self.repo / ".ddg-demo.json").read_text(encoding="utf-8"))
        context = load_context(self.repo, revision=marker["refs"]["decision_change"])
        context["capture"] = json.loads((ROOT / "evidence" / "gemini-proposal.json").read_text(encoding="utf-8"))
        draft = propose(context, mode="recorded")
        validation = validate_draft(self.repo, draft, demo["refs"])
        approve(self.repo, draft, validation, "Evaluation test", "Create an approved synthetic fixture", commit_demo=True)
        self.out = self.root / "results"

    def tearDown(self):
        self.temp.cleanup()

    def test_subset_writes_expected_observed_evidence_and_empty_timing_template(self):
        before = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], check=True,
                                capture_output=True, text=True, encoding="utf-8").stdout.strip()
        selected = [case for case in CASES if case["id"] in {"regression", "corrected"}]
        result = evaluate(self.repo, self.out, cases=selected)
        after = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], check=True,
                               capture_output=True, text=True, encoding="utf-8").stdout.strip()
        self.assertEqual(before, after, "the evaluator must not mutate the input repository")
        self.assertEqual([item["case_id"] for item in result["cases"]], ["regression", "corrected"])
        regression, corrected = result["cases"]
        self.assertEqual(regression["expected_aggregate"], "FAILED")
        self.assertEqual(regression["observed_aggregate"], "FAILED")
        self.assertEqual(regression["observed_verdicts"]["CHK-001"], "VIOLATION_INTRODUCED")
        self.assertEqual(corrected["observed_aggregate"], "PASSED_CHECKS")
        for item in result["cases"]:
            self.assertRegex(item["base_sha"], re.compile(r"^[0-9a-f]{40}$"))
            self.assertRegex(item["head_sha"], re.compile(r"^[0-9a-f]{40}$"))
            self.assertTrue(item["check_results"])
            self.assertRegex(item["check_results"][0]["check_digest"], re.compile(r"^[0-9a-f]{64}$"))
            self.assertIn("unique_jobs", item["check_results"][0]["base_metrics"])
            self.assertIn("unique_jobs", item["check_results"][0]["head_metrics"])
            self.assertIsNone(item["error"])

        saved = json.loads((self.out / "case_results.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, result)
        with (self.out / "timing.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows, [["reviewer_id", "condition", "task_id", "order", "setup_seconds",
                                 "review_seconds", "correct_verdict", "correct_reason", "notes"]])

        # Test-only row, not participant evidence. A repeated evaluator run must
        # never erase rows that a human evaluator recorded between runs.
        timing_path = self.out / "timing.csv"
        mock_timing = timing_path.read_bytes() + b"TEST-ONLY,assisted,fixture,1,,,,,,not participant data\n"
        timing_path.write_bytes(mock_timing)
        evaluate(self.repo, self.out, cases=selected)
        self.assertEqual(timing_path.read_bytes(), mock_timing)

    def test_output_inside_input_repo_is_refused_without_creating_files(self):
        output = self.repo / ".ddg" / "unsafe-evaluation"
        with self.assertRaisesRegex(ValueError, "outside the input repository"):
            evaluate(self.repo, output, cases=CASES[:1])
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
