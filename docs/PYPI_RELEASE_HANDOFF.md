# Handoff: publish Decision Drift Gate to PyPI

For: Yash (repository owner). Written 19 October 2026. Release `v0.1.0` is tagged and on the [GitHub release page](https://github.com/Yashjain329/Decision-Drift-Gate/releases/tag/v0.1.0), but it is not on PyPI.

After these steps, `python -m pip install decision-drift-gate` works for everyone. Plan about one hour. Most of it is account setup.

## What I checked before writing this

- The name `decision-drift-gate` is free on PyPI and on TestPyPI. Both returned 404 on 19 October 2026. Register it soon, because names are first come, first served.
- The `v0.1.0` tag cannot go to PyPI as it is. `twine check --strict` fails on its sdist because the package has no long description (`readme`). The PyPI page would also have no license, no links and an empty description. You publish a new version, `0.1.1`, with the metadata below. A tag must not move, so `v0.1.0` stays as it is.
- The metadata below passes `python -m build` and `twine check --strict` for the wheel and the sdist. I tested it on a copy of `master`, with MIT as a stand-in license.
- The repository has no license file. Without a license, other people have no right to use the code, even from PyPI. You must choose one. See decision 1.
- An abandoned 2012 PyPI package, `ddg` (a DuckDuckGo client), also installs a command named `ddg`. If a user installs both, one `ddg` command replaces the other. The Python import name `ddg` does not clash, because that package installs `duckduckgo`. No action is needed. Mention it if a user reports a strange `ddg` command.

## Decisions you make first

1. The license. Common choices are MIT (short and permissive) and Apache-2.0 (permissive, with an explicit patent grant). Use the SPDX name in step 2, for example `MIT` or `Apache-2.0`. Copy the license text from <https://choosealicense.com>, and put your name and the year in it.
2. The author line, for example `{ name = "Yash Jain" }`. Add an email only if you want it public on PyPI.
3. Who approves a PyPI publish. The workflow below uses a GitHub environment named `pypi`. If you add yourself as a required reviewer of that environment, nothing goes to PyPI until you click Approve.

## Step 1: Create the accounts

1. Create an account on <https://pypi.org> and on <https://test.pypi.org>. They are separate accounts.
2. Turn on two-factor authentication on both. PyPI requires it for uploads.

## Step 2: Prepare version 0.1.1 in a pull request

Work on a branch, for example `release/0.1.1`, from an up-to-date `master`.

1. Add the license file `LICENSE` at the repository root, with the text from decision 1.

2. Edit `pyproject.toml`. Change the build requirement, because SPDX license names need setuptools 77 or later:

   ```toml
   [build-system]
   requires = ["setuptools>=77"]
   ```

   Add these lines in `[project]`, after `requires-python`. Use your license and author from decisions 1 and 2:

   ```toml
   readme = "README.md"
   license = "MIT"
   license-files = ["LICENSE"]
   authors = [{ name = "Yash Jain" }]
   keywords = ["code-review", "governance", "regression", "decision-records", "github-action"]
   classifiers = [
     "Development Status :: 3 - Alpha",
     "Environment :: Console",
     "Intended Audience :: Developers",
     "Operating System :: OS Independent",
     "Programming Language :: Python :: 3",
     "Programming Language :: Python :: 3.12",
     "Topic :: Software Development :: Quality Assurance",
   ]
   ```

   Add this table before `[project.scripts]`:

   ```toml
   [project.urls]
   Homepage = "https://github.com/Yashjain329/Decision-Drift-Gate"
   Changelog = "https://github.com/Yashjain329/Decision-Drift-Gate/blob/master/CHANGELOG.md"
   Issues = "https://github.com/Yashjain329/Decision-Drift-Gate/issues"
   ```

3. Make the README links absolute. PyPI shows `README.md` as the project page, but it cannot follow relative links. About 30 links and one image would break. Run this once from the repository root, then read the diff:

   ```bash
   python - <<'PY'
   import pathlib, re
   p = pathlib.Path("README.md")
   b = "https://github.com/Yashjain329/Decision-Drift-Gate/"
   t = p.read_text(encoding="utf-8")
   t = re.sub(r"!\[([^]]*)\]\((?!https?://)([^)]+)\)", lambda m: f"![{m[1]}]({b}raw/master/{m[2]})", t)
   t = re.sub(r"(?<!!)\[([^]]*)\]\((?!https?://|#|mailto:)([^)]+)\)", lambda m: f"[{m[1]}]({b}blob/master/{m[2]})", t)
   p.write_text(t, encoding="utf-8")
   PY
   git diff README.md
   ```

4. Set the version to `0.1.1` in `ddg/__init__.py` (`__version__ = "0.1.1"`).

5. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [0.1.1] - <date>`, add a new empty `## [Unreleased]` above it, and write what changed:

   ```markdown
   ### Added

   - Published to PyPI as `decision-drift-gate`. Package metadata: license, readme, project links and classifiers.
   ```

   At the bottom, change the `[Unreleased]` link to compare from `v0.1.1`, and add `[0.1.1]: https://github.com/Yashjain329/Decision-Drift-Gate/releases/tag/v0.1.1`.

6. Add the publish workflow `.github/workflows/release.yml` (next section).

7. Make sure that the build is clean on your machine:

   ```bash
   python -m pip install build twine
   python -m build
   python -m twine check --strict dist/*
   python -m unittest tests.test_packaging
   ```

   Then delete the local `dist/` and `build/` folders. Do not commit them.

8. Open the pull request. The DDG check on the pull request must pass. Merge it.

## Step 3: The publish workflow

This workflow uses Trusted Publishing: PyPI accepts the upload because it comes from this exact repository, workflow and environment. No PyPI password or token is stored in GitHub. Save it as `.github/workflows/release.yml`:

```yaml
name: publish
on:
  release:
    types: [published]        # a published GitHub release uploads to PyPI
  workflow_dispatch:          # a manual run uploads to TestPyPI or PyPI
    inputs:
      target:
        description: Where to upload
        required: true
        default: testpypi
        type: choice
        options: [testpypi, pypi]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install build twine
      - name: Release tag must match the package version
        if: github.event_name == 'release'
        env:
          TAG: ${{ github.event.release.tag_name }}
        run: |
          VERSION=$(python -c "import ddg; print(ddg.__version__)")
          test "$TAG" = "v$VERSION" || { echo "::error::tag $TAG does not match version $VERSION"; exit 1; }
      - run: python -m build
      - run: python -m twine check --strict dist/*
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  testpypi:
    if: github.event_name == 'workflow_dispatch' && inputs.target == 'testpypi'
    needs: build
    runs-on: ubuntu-latest
    environment: testpypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/

  pypi:
    if: github.event_name == 'release' || inputs.target == 'pypi'
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
```

## Step 4: Connect PyPI to the workflow

1. On GitHub, open Settings > Environments, and create two environments: `testpypi` and `pypi`. On `pypi`, add yourself under Required reviewers (decision 3).
2. On <https://test.pypi.org>, open Your account > Publishing > Add a new pending publisher, and enter:
   - PyPI project name: `decision-drift-gate`
   - Owner: `Yashjain329`
   - Repository name: `Decision-Drift-Gate`
   - Workflow name: `release.yml`
   - Environment name: `testpypi`
3. On <https://pypi.org>, do the same, with environment name `pypi`.

A pending publisher reserves nothing. The project name is registered by the first successful upload.

## Step 5: Test on TestPyPI

1. On GitHub, open Actions > publish > Run workflow. Select branch `master` and target `testpypi`, then run it.
2. When it is green, install from TestPyPI in a new virtual environment and run the command:

   ```bash
   python -m venv try-ddg
   try-ddg/bin/python -m pip install -i https://test.pypi.org/simple/ decision-drift-gate==0.1.1
   try-ddg/bin/ddg --help
   ```

   On Windows, use `try-ddg\Scripts\python` and `try-ddg\Scripts\ddg`. DDG has no required dependencies, so TestPyPI is enough for this install.

3. Open <https://test.pypi.org/project/decision-drift-gate/> and make sure that the description, license and links look correct. If something is wrong, fix it in a new pull request. TestPyPI does not accept the same version twice. For a second test, use a pre-release version such as `0.1.1rc1`, and never publish that version to PyPI.

## Step 6: Publish to PyPI

1. Tag the merge commit and create the GitHub release. Attach the files that `python -m build` made from that commit:

   ```bash
   git checkout master && git pull
   git tag -a v0.1.1 -m "Decision Drift Gate 0.1.1"
   git push origin v0.1.1
   python -m build
   gh release create v0.1.1 --verify-tag --title "Decision Drift Gate 0.1.1" --notes "Published to PyPI: pip install decision-drift-gate. See CHANGELOG.md." dist/*
   ```

2. Publishing the release starts the workflow. Approve the `pypi` environment when GitHub asks. The workflow refuses a tag that does not match `__version__`.
3. Make sure that it worked:

   ```bash
   python -m pip install decision-drift-gate==0.1.1
   ddg --help
   ```

   Also open <https://pypi.org/project/decision-drift-gate/>.

4. In a final small pull request, add `python -m pip install decision-drift-gate` to the Install section of the README, and remove "It is not published to PyPI" from the top of `CHANGELOG.md` and from `docs/PRODUCTIZATION_PLAN.md` (P7).

## If something goes wrong

- PyPI never accepts the same version twice, even after you delete it. To fix a bad release, publish `0.1.2`.
- To stop new installs of a bad version without breaking pinned users, yank it on PyPI: Manage > Releases > Options > Yank.
- `invalid-publisher` in the workflow log means that a Step 4 value does not match. Owner, repository, workflow file name and environment must match exactly.
- If you cannot use Trusted Publishing, create an API token for the project on PyPI and upload by hand: `python -m twine upload dist/*` with username `__token__` and the token as the password. Do not store the token in the repository.

## Not part of this handoff

- A default sandbox image pinned by digest. Reports still mark the default `python:3.12-slim` tag as not pinned.
- Human evaluation. See `docs/TRY_IT.md` and `docs/HUMAN_EVALUATION.md`.
