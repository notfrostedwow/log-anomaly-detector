# Contributing locally

Keep work within this independent project. Use synthetic inputs and documentation
IP ranges. Do not copy private logs, connect accounts, add credentials, run live
cloud commands or publish without separate authorization.

Python 3.11+ is required. From the workspace in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e . -r requirements-dev.txt
.venv/Scripts/python tools/verify.py
.venv/Scripts/python tools/capture_demo.py
git diff --check
```

`verify.py` records pytest, Ruff lint/format, strict mypy, `pip check` and offline
cfn-lint results in `docs/validation/checks.txt`. For a focused check/format:

```powershell
.venv/Scripts/python -m pytest tests/test_cli_core.py -q --basetemp=.tmp/pytest
.venv/Scripts/python -m ruff format .
```

The tests' startup hook creates the configured `--basetemp` parent before
`tmp_path` fixtures run. Both the verifier and the focused command above work
when a fresh checkout has no `.tmp` directory; no manual temp setup is required.

Tests block sockets/DNS. Inject fake cloud clients rather than bypassing that
guard. No LocalStack or Docker daemon is needed. Keep runtime dependencies at
zero unless a reviewed requirement justifies otherwise. Recheck dependency
versions, licenses and notices when upgrading development tools.

Add behavioral tests when changing detection, parsing or bounds. Update schema
docs and fixtures for contract changes. `tools/create_samples.py` regenerates the
synthetic scenario; `tools/capture_demo.py` captures actual executable output.
Record results and limitations. Do not claim remote CI success from local runs or
add a badge without verifying a real workflow run.

Before each small local commit, run checks and verify
`git config --local --get user.name` and `git config --local --get user.email`.
Expected author: `notfrostedwow <105129603+notfrostedwow@users.noreply.github.com>`.
Do not change global Git configuration. Parent review controls later remote
creation/push/publication. Original project code is MIT licensed; third-party
code keeps its own license and notices.
