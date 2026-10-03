import copy
import unittest

from ddg.contracts import validate_decisions


DECISIONS = [
    {"schema_version": 1, "id": "DEC-001", "status": "superseded", "supersedes": None,
     "scope": "src/job_client.py", "rule": "Retry after 503.", "exceptions": []},
    {"schema_version": 1, "id": "DEC-002", "status": "active", "supersedes": "DEC-001",
     "scope": "src/job_client.py", "rule": "Prevent duplicates.", "exceptions": ["Retry after rejection."]},
]


class DecisionGovernanceTests(unittest.TestCase):
    def invalid(self, records):
        with self.assertRaises(ValueError):
            validate_decisions(records)

    def test_valid_records_are_indexed_by_id(self):
        result = validate_decisions(DECISIONS)
        self.assertEqual(set(result), {"DEC-001", "DEC-002"})
        self.assertEqual(result["DEC-002"]["status"], "active")
        result["DEC-002"]["rule"] = "mutated"
        self.assertEqual(DECISIONS[1]["rule"], "Prevent duplicates.")

    def test_duplicate_ids_missing_predecessor_and_schema_errors_reject(self):
        self.invalid([*DECISIONS, copy.deepcopy(DECISIONS[1])])
        missing = copy.deepcopy(DECISIONS)
        missing[1]["supersedes"] = "DEC-404"
        self.invalid(missing)
        invalid = copy.deepcopy(DECISIONS)
        invalid[0]["extra"] = "ignored?"
        self.invalid(invalid)

    def test_cycles_and_multiple_active_successors_reject(self):
        cycle = copy.deepcopy(DECISIONS)
        cycle[0]["supersedes"] = "DEC-002"
        self.invalid(cycle)
        competing = copy.deepcopy(DECISIONS)
        competing.append({"schema_version": 1, "id": "DEC-003", "status": "active", "supersedes": "DEC-001",
                          "scope": "src/job_client.py", "rule": "Other rule.", "exceptions": []})
        self.invalid(competing)

    def test_boolean_schema_version_is_rejected(self):
        invalid = copy.deepcopy(DECISIONS)
        invalid[0]["schema_version"] = True
        self.invalid(invalid)

    def test_active_predecessor_cannot_compete_with_active_successor(self):
        competing = copy.deepcopy(DECISIONS)
        competing[0]["status"] = "active"
        self.invalid(competing)


if __name__ == "__main__":
    unittest.main()
