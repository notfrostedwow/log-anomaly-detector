# Log anomaly detector

A Python 3.11+ CLI for deterministic, offline authentication-log analysis. It flags
failed-login bursts, password sprays and successful logins outside an explicit
per-user source baseline. The rules are explainable; there is no machine learning.

This separate portfolio project belongs to notfrostedwow. All included data is
synthetic. Publication and the project license await parent review.

## Local setup

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e . -r requirements-dev.txt
.venv/Scripts/python -m pytest
.venv/Scripts/ruff check .
.venv/Scripts/python -m mypy src
```

The package itself has no third-party runtime dependencies. Development tools and
their licenses are recorded in [docs/dependencies.md](docs/dependencies.md).

More usage, schema and cloud-adapter documentation will accompany their verified
examples. No cloud resources have been deployed.
