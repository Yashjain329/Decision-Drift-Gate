import copy
import json
import unittest
from pathlib import Path

from ddg.contracts import ADAPTER_VERSION, canonical_bytes, digest, validate_check


VALID = {
    "schema_version": 1,
    "id": "CHK-001",
    "decision_id": "DEC-002",
    "supersedes": "DEC-001",
    "adapter": "python_job_client_v1",
    "scenario": "commit_then_503",
    "assertions": [
        {"metric": "unique_jobs", "equals": 1},
        {"metric": "returned_job_exists", "equals": True},
    ],
    "rationale": "A failed acknowledgement must not duplicate an accepted operation.",
    "citations": [
        {"decision_id": "DEC-002", "quote": "must not create duplicate jobs"}
    ],
}


class ContractTests(unittest.TestCase):
    def test_valid_check_is_normalized_deep_copy(self):
        source = copy.deepcopy(VALID)
        checked = validate_check(source)
        self.assertEqual(checked, source)
        self.assertIsNot(checked, source)
        self.assertIsNot(checked["assertions"], source["assertions"])
        checked["assertions"].clear()
        self.assertEqual(len(source["assertions"]), 2)
        self.assertEqual(ADAPTER_VERSION, "python_job_client_v1")

    def test_example_is_the_disclosed_valid_check(self):
        example = json.loads(Path("examples/manual_check.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_check(example), VALID)

    def test_canonical_bytes_are_stable_compact_unicode_and_sorted(self):
        self.assertEqual(canonical_bytes({"é": 1, "a": [True]}), '{"a":[true],"é":1}'.encode())
        self.assertEqual(digest({"b": 2, "a": 1}), digest({"a": 1, "b": 2}))
        self.assertEqual(len(digest(VALID)), 64)

    def assert_invalid(self, candidate):
        with self.assertRaises(ValueError):
            validate_check(candidate)

    def test_rejects_unknown_or_missing_top_level_fields(self):
        unknown = copy.deepcopy(VALID)
        unknown["command"] = "echo unsafe"
        self.assert_invalid(unknown)
        missing = copy.deepcopy(VALID)
        del missing["rationale"]
        self.assert_invalid(missing)

    def test_schema_version_must_be_integer_one_not_boolean(self):
        for version in (True, 1.0, 2, "1"):
            candidate = copy.deepcopy(VALID)
            candidate["schema_version"] = version
            self.assert_invalid(candidate)

    def test_ids_must_follow_record_prefix_and_not_be_blank(self):
        for field, bad in (("id", "DEC-002"), ("id", "CHK-"), ("decision_id", " "), ("supersedes", "CHK-001")):
            candidate = copy.deepcopy(VALID)
            candidate[field] = bad
            self.assert_invalid(candidate)

    def test_scenario_adapter_and_all_unknown_nested_fields_are_rejected(self):
        for field, bad in (("scenario", "exec_python"), ("adapter", "other")):
            candidate = copy.deepcopy(VALID)
            candidate[field] = bad
            self.assert_invalid(candidate)
        candidate = copy.deepcopy(VALID)
        candidate["assertions"][0]["expression"] = "__import__('os')"
        self.assert_invalid(candidate)
        candidate = copy.deepcopy(VALID)
        candidate["citations"][0]["path"] = "../../file"
        self.assert_invalid(candidate)

    def test_assertions_require_exactly_one_of_each_metric(self):
        for assertions in ([], VALID["assertions"][:1], [*VALID["assertions"], VALID["assertions"][0]],
                           [VALID["assertions"][0], copy.deepcopy(VALID["assertions"][0])]):
            candidate = copy.deepcopy(VALID)
            candidate["assertions"] = assertions
            self.assert_invalid(candidate)

    def test_metric_values_have_strict_types_and_range(self):
        for value in (True, -1, 3, 1.0, "1"):
            candidate = copy.deepcopy(VALID)
            candidate["assertions"][0]["equals"] = value
            self.assert_invalid(candidate)
        for value in (0, 1, 2):
            candidate = copy.deepcopy(VALID)
            candidate["assertions"][0]["equals"] = value
            self.assertEqual(validate_check(candidate)["assertions"][0]["equals"], value)
        for value in (0, 1, "true"):
            candidate = copy.deepcopy(VALID)
            candidate["assertions"][1]["equals"] = value
            self.assert_invalid(candidate)

    def test_citations_are_nonempty_and_have_only_exact_fields(self):
        for citations in ([], [{"decision_id": "DEC-002", "quote": " "}],
                          [{"decision_id": "DEC-002", "quote": "x", "extra": 1}],
                          [{"decision_id": "CHK-9", "quote": "x"}]):
            candidate = copy.deepcopy(VALID)
            candidate["citations"] = citations
            self.assert_invalid(candidate)

    def test_rejects_non_json_values_and_nonfinite_numbers(self):
        for value in (float("nan"), float("inf"), object(), {"x": (1, 2)}):
            with self.assertRaises(ValueError):
                canonical_bytes({"value": value})
        with self.assertRaises(ValueError):
            digest({"value": float("nan")})


if __name__ == "__main__":
    unittest.main()


