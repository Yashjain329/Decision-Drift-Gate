"""Build a real (non-demo) repository for the UI suite: an approved python_function_v1 check, a regressing
head commit, and the `ddg run` report comparing them. Prints {"repo", "report", "base", "head"} as JSON."""

import json
import sys
from pathlib import Path

from ddg.engine import compare
from tests.test_adapters import BAD, FunctionAdapterBase
from tests.test_identity import commit, git

work = Path(sys.argv[1])
repo, base, _ = FunctionAdapterBase.build(work)
git(repo, "checkout", "--quiet", "-B", "regression", base)
head = commit(repo, {"src/pricing.py": BAD}, "drop the negative-price guard")
git(repo, "checkout", "--quiet", "--detach", base)
report = work / "report.json"
report.write_text(json.dumps(compare(repo, base, head)), encoding="utf-8")
print(json.dumps({"repo": str(repo), "report": str(report), "base": base, "head": head}))
