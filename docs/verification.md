# Verification record

Local Windows / Python 3.11.9 verification on 2026-10-15. All development and test
data is synthetic. Commands below use the activated `.venv`; on Windows the
unactivated interpreter is `.venv/Scripts/python`.

Final result: **151 tests passed**, with no skipped tests. Ruff lint and format,
strict mypy (six source modules), `pip check` and network-disabled cfn-lint all
returned 0. The offline wheel build, MIT metadata/license inspection and clean
wheel-installed CLI smoke check passed separately. Generated JSONL/CSV report
bytes match. These are local results only.

## Executed

```text
python -m venv .venv
python -m pip install -e . -r requirements-dev.txt
python tools/create_samples.py
python tools/dependency_inventory.py
python tools/verify.py
python tools/capture_demo.py
python tools/package_check.py
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

## Final package and CLI review

`python tools/capture_demo.py` ran seven actual CLI subprocess commands, including
the installed console entry point, JSONL and CSV JSON output, a quiet input,
module execution, version and help. All exit codes matched documented semantics;
CSV/JSONL report bytes matched. Output and exact commands are saved in
[validation/cli-demo.txt](validation/cli-demo.txt), with generated reports under
`samples/report.json` and `samples/report.txt`. Module `--help` was also run.

After Zaheer's MIT approval, packaging was refreshed **without package-index
access**, using the setuptools 80.10.2 wheel already downloaded into this
workspace's pip cache during the initial build:

```text
python -m pip install --no-index --find-links .cache/wheels setuptools==80.10.2
python -m pip install --no-index --no-build-isolation -e .
python tools/dependency_inventory.py
python tools/package_check.py
```

`package_check.py` built a wheel offline, checked its bundled LICENSE against the
approved source and its `License-Expression: MIT` metadata, installed it into a
clean `.tmp/wheel-smoke` virtual environment without dependencies/index access,
and ran that wheel-installed CLI against the sample. Its JSON matched the
committed report. Exact subprocess commands/output are in
[validation/package.txt](validation/package.txt). The initial packaging assertion
incorrectly expected LF metadata on Windows; checking metadata lines corrected
the assertion, and the check then passed. This was a verification-script fix.

The actual terminal screenshot attempt failed because no dedicated console
window handle was exposed. See [validation/screenshot-attempt.txt](validation/screenshot-attempt.txt).
No screenshot or illustrated substitute is claimed. The genuine text transcript
is available for review.

Final cfn-lint invocation specifies `infra/cfnlintrc.json` explicitly so it does
not search for user-level lint settings. Package smoke checks disable pip config
and package-index access. Current exact check outputs supersede the earlier
checkpoint counts above.

## Not executed

No remote CI runs, AWS API calls, deployments, account connections, credential
discovery, Docker, LocalStack, remote Git creation, push or publication. Lambda
tests use offline fakes; they do not establish AWS integration behavior. The
GitHub Actions Python 3.11/3.12 matrix is configured but has not run remotely.
