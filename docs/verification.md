# Verification record

Local Windows / Python 3.11.9 verification on 2026-10-15. All development and test
data is synthetic. Commands below use the activated `.venv`; on Windows the
unactivated interpreter is `.venv/Scripts/python`.

## Executed

```text
python -m venv .venv
python -m pip install -e . -r requirements-dev.txt
python tools/create_samples.py
python tools/dependency_inventory.py
python tools/verify.py
git diff --check
```

The install used the workspace-local pip cache and temporary directory. It
downloaded development packages from the package index; it made no cloud calls.
The exact verification subprocess commands, outputs and return codes are in
[validation/checks.txt](validation/checks.txt). Initial CLI checkpoint: 94 tests
passed, Ruff lint/format passed, strict mypy passed for four source files, and
`pip check` passed.

The first test run found a Windows test-fixture path-length issue: pytest used a
65,537-byte malformed-config parameter as a temporary directory label. Explicit
short test IDs fixed it. Initial lint findings were corrected before the passing
run. These failures were local development feedback, not skipped tests.

Cloud checkpoint: `python tools/verify.py` passed **147 tests**, Ruff lint/format,
strict mypy for six source files, `pip check`, and network-disabled cfn-lint.
The tests include fake S3 bodies/clients, an SDK-injected handler, sanitized
failures, object/event/key bounds, and assertions on the template's IAM scopes,
storage controls, invocation permission and workflow permissions. A socket guard
prevents network/DNS access during every test.

IaC development corrections: the first wrapper used the wrong installed cfn-lint
entry point; inspecting its local package metadata identified `cfnlint.runner`.
A subsequent missing-profile error was fixed by providing a `[default]` region
in the workspace-local placeholder config. Later validation passed without any
network access. Review of installed SAM translator source also showed its S3
event helper creates an account-scoped permission, so the final template uses an
explicit bucket/account-scoped invocation permission and native S3 notification.

## Not executed

No remote CI runs, AWS API calls, deployments, account connections, credential
discovery, Docker, LocalStack, remote Git creation, push or publication. Lambda
tests use offline fakes; they do not establish AWS integration behavior. The
GitHub Actions Python 3.11/3.12 matrix is configured but has not run remotely.
