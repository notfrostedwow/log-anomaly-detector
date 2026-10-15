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

## Not executed

No remote CI runs, AWS API calls, deployments, account connections, credential
discovery, Docker, LocalStack, remote Git creation, push or publication. The cloud
adapter and its offline template checks will have their own verification record.
