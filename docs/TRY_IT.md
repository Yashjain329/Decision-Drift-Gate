# Try Decision Drift Gate

This guide is for a developer who did not build DDG. It has four parts:

1. Run the demo and see a regression fail.
2. Draft a check with your own Claude Code or Codex login (a live proposal).
3. Run DDG on a repository of your own.
4. Report what happened.

Part 1 takes about 10 minutes. Parts 2 and 3 take 15 to 45 minutes each. You can stop after any part. Each part gives the results to report.

DDG (Decision Drift Gate) compares two commits of a repository. The base commit holds approved checks, and each check is linked to a recorded engineering decision. The head commit holds the change under review. DDG runs each check on both commits and reports whether the change breaks the decision.

## Before you start

You need:

- Python 3.12 or later.
- Git.
- Docker Desktop or Podman, running. DDG runs the code under review in a container. Without a container runtime, the checks end as NOT_CHECKED.

Install DDG from a clone of the repository:

```bash
git clone https://github.com/Yashjain329/Decision-Drift-Gate.git
cd Decision-Drift-Gate
python -m pip install .
ddg --help
```

Do all the work in a folder outside the clone, for example `../ddg-try`. The demo commands create new Git repositories, and those repositories must not go into the DDG source tree.

The commands in this guide are single lines. They work the same in bash and in PowerShell.

## Part 1: Run the demo

The demo is a small generated repository. It has a job client, an old retry decision (DEC-001), a new decision that replaces it (DEC-002), and branches with good and bad versions of the code. DEC-002 says that a retry must not create a second job when the first request succeeded but its response was lost.

1. Create the demo repository:

   ```bash
   ddg demo-init --destination ../ddg-try/demo
   ```

2. Draft a check from the recorded model answer. This step makes no network call:

   ```bash
   ddg propose --repo ../ddg-try/demo --mode recorded --out ../ddg-try/draft.json
   ```

3. Calibrate the draft. DDG runs it against a known-bad commit, a known-good commit and an allowed exception. The output must show `"eligible": true`:

   ```bash
   ddg validate --repo ../ddg-try/demo --draft ../ddg-try/draft.json --out ../ddg-try/validation.json
   ```

4. Approve the check. Put your own name and a short reason:

   ```bash
   ddg approve --repo ../ddg-try/demo --draft ../ddg-try/draft.json --validation ../ddg-try/validation.json --reviewer "Your Name" --reason "Read the check and the calibration" --commit-demo
   ```

5. Run the approved check on a regression branch:

   ```bash
   ddg run --repo ../ddg-try/demo --base approved-base --head regression --out ../ddg-try/report.json
   ```

   The command prints `"aggregate": "FAILED"` and exits with code 1. The Markdown report `../ddg-try/report.md` explains the failure. On the base commit, one operation creates one job. On the head commit, it creates two.

6. Run it on the corrected branch. The result is `PASSED_CHECKS` and the exit code is 0:

   ```bash
   ddg run --repo ../ddg-try/demo --base approved-base --head corrected --out ../ddg-try/report-ok.json
   ```

7. Optional: open the browser viewer for the demo. Open the address that the command prints, then stop the server with Ctrl+C:

   ```bash
   ddg serve --repo ../ddg-try/demo --state-dir ../ddg-try/state
   ```

Other demo branches to try as `--head`: `unseen-regression`, `exception`, `unrelated`, `approved-abort`, `policy-edit`. The [README](../README.md#reading-a-report) explains each verdict.

Results to report: whether each step worked, the result of each `ddg run`, and anything in the report that you did not understand.

## Part 2: Test a live proposal with Claude Code or Codex

In Part 1 the check came from a recorded model answer. In this part, a model drafts a new check through your own subscription login. You do not need an API key.

Each attempt uses your subscription. One `claude_cli` call sends about 500 input tokens. DDG makes at most two calls per draft: one request and one repair attempt.

The CLI agent runs in an empty temporary folder with its tools off. It cannot read your repository or your files. It gets only the decision text and the code that DDG puts in the prompt.

1. Make sure that the agent is installed and logged in:

   - For Claude Code, run `claude --version`, then run `claude` once and use `/login` if it asks.
   - For Codex, run `codex --version`, then run `codex login` if needed.

2. Create a fresh demo. A demo that already has an approved check refuses a new draft:

   ```bash
   ddg demo-init --destination ../ddg-try/live
   ```

3. Draft the check with your provider. Use `claude_cli` or `codex_cli`:

   ```bash
   ddg propose --repo ../ddg-try/live --mode live --provider claude_cli --out ../ddg-try/live-draft.json
   ```

   Codex starts slowly. Allow about one minute. The time limit for CLI agents is 180 seconds. To change it, set `DDG_PROVIDER_TIMEOUT` (1 to 600 seconds). To choose a model, add `--model <name>`.

4. Calibrate the draft:

   ```bash
   ddg validate --repo ../ddg-try/live --draft ../ddg-try/live-draft.json --out ../ddg-try/live-validation.json
   ```

   Both results are valid test results. Exit code 0 with `"eligible": true` means that the model wrote a check that separates the bad code from the good code. Exit code 1 means that it did not. Then `live-validation.json` shows which calibration case did not match.

5. If the draft is eligible, approve it and run it as in Part 1, steps 4 to 6. Use `../ddg-try/live` and the `live-` file names.

Read the provenance that DDG recorded in the draft. It names the provider, the model and the CLI version. It does not contain the prompt or any credential:

```bash
python -c "import json; d = json.load(open('../ddg-try/live-draft.json')); print(d['proposal_mode'], d.get('model'), d.get('sdk_version'), d['request_metadata'])"
```

If the draft fails, DDG prints one of these codes instead of a check:

| Code | Meaning | What to do |
|---|---|---|
| `provider_auth_failed` | The CLI is not logged in. | Log in (step 1) and try again. |
| `provider_timeout` | No answer within the time limit. | Increase `DDG_PROVIDER_TIMEOUT` and try again. |
| `provider_unavailable` | The CLI is not on `PATH`, or it exited with an error. | Run the CLI by hand to see its error. |
| `provider_rate_limited` | The subscription limit was reached. | Wait, then try again. |
| `provider_response_invalid` | The answer was not a valid check, also after the repair attempt. | Report it. This is a useful result. |

Results to report: the provider and model, how long the draft took, whether calibration was eligible, the result of each `ddg run`, and any error code. The [providers guide](PROVIDERS.md) lists the other providers (API keys, local servers, any command).

## Part 3: Run DDG on your own repository

In this part you protect one rule of your own code with a check. Model proposals do not support this adapter, so you write the check by hand.

### Choose the rule and the function

DDG can check one Python function. The check calls the function with JSON arguments and compares the return value or the exception type, for up to 50 cases. This is the `python_function_v1` adapter.

The function must be in a module that DDG can load by itself. These conditions apply:

- The module imports only modules from the Python standard library.
- It does not import `os`, `sys`, `subprocess`, `pathlib`, `io`, `tempfile`, `socket`, `urllib`, `http`, `pickle` or other process, file or network modules.
- It does not call `open`, `eval`, `exec` or `__import__`.
- It does not import other modules of your project.

Most application modules do not meet these conditions. Look for a module with pure logic, such as validation, pricing, parsing or a state machine. If the rule lives inside a large module, you can move its logic into a small pure module first.

Good candidates are rules that people already broke once, or that a reviewer can easily miss. Examples: "a negative amount raises ValueError", "an unknown status maps to 'pending', never to 'paid'", "a cycle in the graph is rejected".

### Prepare three calibration commits

DDG approves a check only when it behaves correctly on three commits of your history:

- A bad commit, where the rule is broken. The check must fail on it.
- A good commit, where the rule holds. The check must pass on it.
- An exception commit, with a change that the decision allows. The check must pass on it.

If your history has no bad commit, make one on a side branch. For example, delete the guard that the rule needs. If it has no exception commit, make a change that the decision explicitly allows, for example a reworded error message when only the exception type is part of the rule.

### Steps

Work in a clone of your repository on a new branch. Do not push anything until step 7.

1. Create the `.ddg` folder and the approver list. Use the Git email of the person who will approve checks:

   ```bash
   ddg init --repo . --approver you@example.com
   ```

2. Write two decision records in `.ddg/decisions/`. DDG needs the old decision (`superseded`) and the new decision (`active`) that replaces it. The new decision names the old one in `supersedes`:

   ```json
   {"schema_version": 1, "id": "DEC-001", "status": "superseded", "supersedes": null,
    "scope": "src/pricing.py", "rule": "Any price is accepted.", "exceptions": []}
   ```

   ```json
   {"schema_version": 1, "id": "DEC-002", "status": "active", "supersedes": "DEC-001",
    "scope": "src/pricing.py", "rule": "discount must reject negative prices with ValueError.",
    "exceptions": ["A zero price is valid and costs nothing."]}
   ```

   Save them as `.ddg/decisions/DEC-001.json` and `.ddg/decisions/DEC-002.json`, then commit the `.ddg` folder.

3. Write the check in a file outside the repository, for example `../ddg-try/check.json`. Each assertion gives the arguments and the expected result. The `quote` in `citations` must be an exact part of the decision rule:

   ```json
   {
     "schema_version": 1, "id": "CHK-001", "decision_id": "DEC-002", "supersedes": "DEC-001",
     "adapter": "python_function_v1",
     "scenario": {"path": "src/pricing.py", "function": "discount"},
     "assertions": [
       {"args": [100, "GOLD"], "expect": {"returns": 80.0}},
       {"args": [-1, "GOLD"], "expect": {"raises": "ValueError"}},
       {"args": [0, "GOLD"], "expect": {"returns": 0.0}}
     ],
     "rationale": "Negative prices must raise ValueError. Zero stays valid.",
     "citations": [{"decision_id": "DEC-002", "quote": "must reject negative prices with ValueError"}]
   }
   ```

4. Make the draft from the commit where the decision records exist:

   ```bash
   ddg propose --repo . --adapter python_function_v1 --mode manual --check ../ddg-try/check.json --out ../ddg-try/my-draft.json
   ```

5. Calibrate it. Give the three commits from the previous section:

   ```bash
   ddg validate --repo . --draft ../ddg-try/my-draft.json --out ../ddg-try/my-validation.json --calibration-bad <bad-commit> --calibration-good <good-commit> --calibration-exception <exception-commit>
   ```

   If the exit code is 1, open `my-validation.json`. Each case shows the status and the error. The error `Unsupported import: <name>` means that the module does not meet the conditions above.

6. Approve the check. DDG writes three files and prints their paths. The approver from step 1 commits exactly these three files and nothing else. The author email of that commit (`git config user.email`) must be the approver email, or the run ends INCOMPLETE with `APPROVER_NOT_VERIFIED`:

   ```bash
   ddg approve --repo . --draft ../ddg-try/my-draft.json --validation ../ddg-try/my-validation.json --reviewer "Your Name" --reason "What you checked"
   git add .ddg/checks .ddg/validations .ddg/approvals
   git commit -m "Approve CHK-001"
   ```

7. Run DDG on a change. Compare the approval commit with any later commit of your branch:

   ```bash
   ddg run --repo . --base <approval-commit> --head <change-commit> --out ../ddg-try/my-report.json
   ```

   Exit code 0 means PASSED_CHECKS, 1 means FAILED and 2 means INCOMPLETE. The Markdown report beside the JSON report gives the reason.

8. Optional: open the report in the browser viewer. The view is read-only. Stop it with Ctrl+C:

   ```bash
   ddg serve --repo . --state-dir ../ddg-try/my-state --report ../ddg-try/my-report.json
   ```

9. Optional: add the GitHub Action. The [README](../README.md#use-it-in-github-actions) has the workflow. When the approved `.ddg` folder is on your default branch, every pull request runs the check in a container and gets one comment with the result.

Results to report: which rule you chose and why, how long each step took, whether calibration passed the first time, what you had to change to meet the module conditions, and whether the check found a real problem.

## Part 4: Report what happened

Open an issue in [the repository](https://github.com/Yashjain329/Decision-Drift-Gate/issues) with the title `Try-out: <your name or team>`. Copy this template and fill in only what you actually observed:

```text
Parts done: 1 / 2 / 3
Operating system, Python version, Docker or Podman version:

Part 1 (demo): worked yes/no. Steps that failed and their messages:
Part 2 (live proposal): provider and model, draft time in seconds, eligible yes/no, error code if any:
Part 3 (own repository): rule chosen, module path, calibration passed on the first try yes/no,
  time for each step, changes needed to meet the module conditions:

What was clear:
What was confusing:
Would you keep this check in your project? Why or why not:
```

Do not include API keys, tokens or private source code in the issue. The reports, drafts and validations contain commit IDs, decision text and check arguments. Read them before you attach them.

## For the person who runs a session

A session is one developer working through this guide while you watch. Run sessions with at least three developers who did not build DDG.

- Give each developer this guide and nothing else. Do not help unless a step blocks them for more than five minutes. Write down each time you help.
- Time each step from the moment the developer reads it until the command result is on the screen.
- After the session, ask the questions from the Part 4 template.
- Put each observation into [the observation file](../evidence/reviewer-observations.csv) as one row. Use only real observations. Do not estimate missing times.

For a timed comparison of reviews with and without DDG, use [the human evaluation plan](HUMAN_EVALUATION.md). That plan measures review time. This guide measures setup and usability.
