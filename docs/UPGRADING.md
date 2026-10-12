# Upgrading existing approved bundles

This note is for repositories that approved checks before approver identity existed (the 4 October 2026 prototype and earlier). It describes the code at commit `bbb0e33` or later.

## What changed

Before: DDG trusted the reviewer name typed into the approval record. A bundle was valid if its digests matched.

Now: DDG also checks Git history (`ddg/identity.py`). For each approved check, every commit that ever touched `.ddg/checks/<id>.json`, `.ddg/validations/<id>.json` or `.ddg/approvals/<id>.json` must:

1. be authored by an email listed in `.ddg/approvers.json` **at the base commit**;
2. change only files under `.ddg/checks/`, `.ddg/validations/` or `.ddg/approvals/`;
3. carry a good signature, if `require_signed` is `true`.

If any rule fails, that check is not trusted. The report shows an `APPROVER_NOT_VERIFIED` warning and the aggregate is INCOMPLETE. The check does not run.

## Demo repositories

Demos created before this change have no `.ddg/approvers.json`. Their runs now end INCOMPLETE.

The simplest fix is to create a new demo. The destination must be absent or empty, and `demo-init` now writes the policy file:

```powershell
python -m ddg demo-init --destination .ddg-demo-new
```

The generated policy lists `ddg-demo@example.invalid`, the email used by the generated commits, with `require_signed` set to `false`.

To keep an old demo, add the policy to the base history yourself in a separate commit before approval, with the same JSON shape (see below). Because an approval commit that also adds the policy file would mix paths, the policy file must be committed on its own. Creating a new demo is less error-prone.

`DDG_ALLOW_UNVERIFIED_APPROVERS=1` lets a repository without a policy file run. Reports mark the approver as unverified. Use it only for local checks, never in CI.

## Real repositories

1. Create `.ddg/approvers.json` and merge it to the base branch:

   ```json
   {"schema_version": 1, "require_signed": true, "approvers": ["alice@example.com"]}
   ```

   The file must have exactly these three keys. Emails are compared in lower case. Protect this file with branch protection or CODEOWNERS.
2. Configure signature checking on every machine that runs DDG: `git config gpg.format ssh` and `git config gpg.ssh.allowedSignersFile <file>`, or a GPG keyring. DDG reads the status Git reports (`%G?`); it does not manage keys.
3. Fetch full history in CI. A shallow clone fails with "No commit history".

## Bundles whose approval was authored by a non-approver

These become INCOMPLETE. Git history cannot be edited without changing the base, so the old check id stays tainted. To re-approve:

1. An allowed approver proposes, validates and approves the check again under a **new check id**. (`approve` refuses to overwrite an existing artifact, so the old id cannot be reused in place.)
2. The approver commits the three new files in one commit that touches nothing else. Sign it if `require_signed` is `true`.
3. Merge that commit to base.
4. Remove the old check's three files in a reviewed change, so the INCOMPLETE warning goes away.

Steps 1 and 2 use the commands in the [README](../README.md). The validation step currently needs the generated-demo marker; see the README section "Planned for real repositories". I did not test re-approval on a non-demo repository; verify it after the CLI changes merge.

## Reports

Reports now include an `approver` entry per check and a top-level `sandbox` field. The Markdown report writer prints `Isolation: not recorded` when a report has no `sandbox` field. Runs before this change used a host subprocess, not a container. Re-run them to get current results.

## Isolation

Runs now need Docker or Podman. If neither works, checks end NOT_CHECKED. To keep the old unsafe behaviour for a trusted local repository, set `DDG_SANDBOX=host`. Reports then say the code ran on the host.
