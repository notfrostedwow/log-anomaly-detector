# Verification record

## CI temp-parent repair

Parent reported [run 38797910959](https://github.com/notfrostedwow/log-anomaly-detector/actions/runs/38797910959)
failed on Python 3.11 and 3.12 at published commit
`4d893b520badd7b8316886cbf78ed829505d7979`: 144 tests passed and seven fixtures
errored. This repair used no GitHub/authentication or cloud calls. A later remote
run of the repair has **not** been verified. Only **Windows / Python 3.11.9** was
tested locally; Python 3.12 was not tested locally.

Root cause: pytest creates the requested `.tmp/pytest` base directory without
creating its missing `.tmp` parent. The initial local verification had an ignored
`.tmp` directory left by setup, so it did not reproduce a fresh checkout.
`tests/conftest.py` now creates explicit basetemp parents during
`pytest_sessionstart`, before fixtures run. Pytest still manages the base itself;
default temp behavior, all existing tests and assertions are unchanged. This
also covers the direct command in CONTRIBUTING, not just `tools/verify.py`.

Two new regression cases launch real child pytest sessions with a `tmp_path`
fixture and an initially missing parent, using relative and absolute basetemp
paths. Both cases fail against the original conftest and pass with the repair.

Fresh detached worktrees were created **inside this workspace**, using only the
published local commit and existing local dependencies:

```text
git -c core.hooksPath=NUL worktree add --detach .cache/ci-repair/before 4d893b520badd7b8316886cbf78ed829505d7979
git -c core.hooksPath=NUL worktree add --detach .cache/ci-repair/after 4d893b520badd7b8316886cbf78ed829505d7979
```

The `before` checkout ran the original 151 tests with no `.tmp` parent and
reproduced **144 passed, 7 errors**. The `after` checkout received only the repaired
conftest and new regression test; both `.tmp` and `.cache` were asserted absent
before verification. `PYTHONPATH` selected that checkout's `src`, and its imported
package path was checked. The existing workspace's ignored directories were not
copied. The pre-existing timing-only change to `checks.txt` was preserved under
`.cache/ci-repair/preexisting-checks.txt` before replacing verification evidence.

Commands below were run with the workspace `.venv/Scripts/python.exe`, each from
the indicated checkout, with `PYTHONPATH` set to that checkout's `src`:

| Checkout | Exact interpreter arguments | Result |
| --- | --- | --- |
| `before` | `-m pytest -q --basetemp=.tmp/pytest` | 144 passed, 7 errors; exit 1 |
| `before`, new regression file only | `-m pytest tests/test_temp_bootstrap.py -q --basetemp=.regression-temp --tb=short` | 2 failed as expected against original conftest; exit 1 |
| `after` | `tools/verify.py` | 153 passed (151 originals + 2 regressions), no skips; all checks exit 0 |

Ruff lint/format, strict mypy for six source modules, `pip check` and
network-disabled SAM/cfn-lint validation all passed in `after`. Exact commands,
stdout/stderr and return codes are saved in:

- [ci-repair-before.txt](validation/ci-repair-before.txt): original clean-checkout failure.
- [ci-repair-regression-before.txt](validation/ci-repair-regression-before.txt): regression tests detect the missing fix.
- [ci-repair-clean.txt](validation/ci-repair-clean.txt): fresh-directory assertions, interpreter/source provenance and full repaired verification.
- [checks.txt](validation/checks.txt): verifier subprocess results copied from the fresh repaired checkout.

Trailing spaces in the captured failing regression diagnostics were trimmed for
Git's whitespace check; the untouched capture remains at
`.cache/ci-repair/ci-repair-regression-before.raw.txt` for local review.

No dependencies, detection rules, cloud resources, workflow permissions or matrix
versions changed. No push, publication, deployment or live AWS call was executed.

## Initial build record

Local Windows / Python 3.11.9 verification on 2026-10-15. All development and test
data is synthetic. Commands below use the activated `.venv`; on Windows the
unactivated interpreter is `.venv/Scripts/python`.

Initial local result: **151 tests passed**, with no skipped tests. Ruff lint and format,
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

## Initial build: not executed by this agent

No remote CI runs, AWS API calls, deployments, account connections, credential
discovery, Docker, LocalStack, remote Git creation, push or publication. Lambda
tests use offline fakes; they do not establish AWS integration behavior. The
GitHub Actions Python 3.11/3.12 matrix had not run remotely at that checkpoint.
Parent subsequently reported the failure recorded in the repair section above.
