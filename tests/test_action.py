import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ddg.engine import compare
from tests.support import make_approved_demo

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pr_comment", ROOT / "scripts" / "pr_comment.py")
pr_comment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr_comment)


class ActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        demo = make_approved_demo(Path(cls.tmp.name) / "demo")
        refs = demo["refs"]
        cls.repo = Path(demo["repo"])
        cls.real = {name: compare(cls.repo, refs["approved_base"], refs[name]) for name in ("regression", "exception")}

    def test_real_reports_render_with_marker(self):
        self.assertTrue(self.real, "expected at least one real report")
        for report in self.real.values():
            text = pr_comment.render(report)
            self.assertIn("<!-- ddg-report -->", text)
            self.assertIn(report["head_sha"], text)
            self.assertIn(report["aggregate"], text)
            self.assertEqual(pr_comment.conclusion(report), pr_comment.CONCLUSIONS[report["aggregate"]])

    def _synthetic(self, aggregate, **extra):
        base = next(iter(self.real.values()))
        return {**base, "aggregate": aggregate, **extra}

    def test_each_aggregate(self):
        for aggregate, conclusion in (("FAILED", "failure"), ("PASSED_CHECKS", "success"), ("INCOMPLETE", "neutral")):
            report = self._synthetic(aggregate, sandbox="docker")
            text = pr_comment.render(report)
            self.assertIn(aggregate, text)
            self.assertEqual(pr_comment.conclusion(report), conclusion)
            self.assertNotIn("UNSAFE", text)

    def test_host_sandbox_banner(self):
        self.assertIn("UNSAFE", pr_comment.render(self._synthetic("PASSED_CHECKS", sandbox="host")))
        self.assertIn("UNSAFE", pr_comment.render(self._synthetic("PASSED_CHECKS", sandbox={"mode": "host"})))

    def test_malformed_report_is_neutral(self):
        for bad in (None, [], {}, {"aggregate": "PASSED"}):
            self.assertEqual(pr_comment.conclusion(bad), "neutral")
            self.assertIn("INCOMPLETE", pr_comment.render(bad))

    def test_size_cap(self):
        report = self._synthetic("FAILED")
        report["checks"] = [dict(report["checks"][0], check_id=f"c{i}", base={"x": "A" * 2900}, head={"x": "B" * 2900})
                            for i in range(60)]
        report["warnings"] = [{"code": "W", "message": "m" * 1000}] * 50
        text = pr_comment.render(report)
        self.assertLessEqual(len(text), 60000)
        self.assertIn("truncated", text)
        self.assertIn("<!-- ddg-report -->", text)

    def test_injection_is_escaped(self):
        evil = "<script>alert(1)</script> [x](http://evil) @admin `|` <!-- ddg-report -->"
        report = self._synthetic("INCOMPLETE", sandbox="docker")
        item = dict(report["checks"][0], check_id=evil, error=evil, decision={"id": evil, "rule": evil})
        item["base"] = {"status": evil}
        report["checks"] = [item]
        report["warnings"] = [{"code": "X", "message": evil}, evil]
        full = pr_comment.render(report)
        text = re.sub(r"```.*?```", "", full, flags=re.S)  # fenced blocks are inert
        text = re.sub(r"`[^`]*`", "", text)  # so are inline code spans
        self.assertNotIn("<script>", full)
        self.assertNotIn("](http://evil)", text)
        self.assertNotIn("@admin", text)
        self.assertEqual(full.count("<!-- ddg-report -->"), 1)
        for line in text.splitlines():
            if line.startswith("| "):
                self.assertEqual(len(line.replace("\\|", "").split("|")), 6)

    def test_cli_stdout_offline(self):
        path = Path(self.tmp.name) / "r.json"
        path.write_text(json.dumps(next(iter(self.real.values()))), encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pr_comment.py"), "--report", str(path)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0)
        self.assertTrue(done.stdout.startswith("<!-- ddg-report -->"))

    def test_yaml_sanity(self):
        action = (ROOT / "action.yml").read_text(encoding="utf-8")
        for needle in ("using: composite", "base-ref:", "head-ref:", "sandbox:", "default: docker", "python-version:",
                       "fail-on-incomplete:", "ddg run --repo .", "--sandbox", "upload-artifact", "ddg-report.json",
                       "pr_comment.py", "exit 1"):
            self.assertIn(needle, action)
        self.assertNotIn("${{ inputs", action.split("run: |")[1].split("- name: Render")[0])
        workflow = (ROOT / ".github" / "workflows" / "ddg.yml").read_text(encoding="utf-8")
        for needle in ("uses: ./", "contents: read", "pull-requests: write", "fetch-depth: 0", "container"):
            self.assertIn(needle, workflow)


if __name__ == "__main__":
    unittest.main()
