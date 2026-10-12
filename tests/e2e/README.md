# End-to-end suite

Drives the real CLI (`python -m ddg ...`) as subprocesses on fresh temp repos:
demo-init, recorded propose, validate, approve, then `run` for every scenario branch
(regression, unseen-regression, corrected, exception, unrelated, abort, crashing,
timing-out, missing-entrypoint, policy-edit, pre-existing/resolved), plus the
`python_function_v1` adapter on a new repo, unapproved-author approvals (INCOMPLETE,
`APPROVER_NOT_VERIFIED`), stale-report detection via `status`, and a `serve` smoke test
(free port via `--port 0`, session token scraped from `/`, propose/validate/approve/run over HTTP).

## Run

    python -m unittest discover -s tests/e2e          # host + docker classes
    python -m unittest tests.e2e.test_lifecycle.HostLifecycleE2E   # host only

Both sandbox modes run from one parametrized mixin (`HostLifecycleE2E`, `DockerLifecycleE2E`).
The docker class is skipped with a visible reason when `ddg.sandbox._usable('docker')` is false
(start Docker Desktop; check `docker info`). It also asserts no `ddg-*` container is left.

## Runtime

Host class about 1.5 min, docker class about 3.5 min (each scenario starts a container).
Total about 5 min; each test is independent except that the scenario tests of one class share
a single approved demo repo (`run` never mutates it). Everything lives under temp dirs.
After a run, `docker ps -a --filter name=ddg-` should print nothing.

Note: the function-adapter repository in these tests builds its artifacts through the Python API and runs only `python -m ddg run` as a subprocess. The real CLI lifecycle on a repository with no demo marker (`init`, `propose`, `validate --calibration-*`, `approve`, `run`) is covered by `tests/test_cli_real.py`.
