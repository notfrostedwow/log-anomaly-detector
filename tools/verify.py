"""Run local checks and save exact commands, outputs, and return codes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    checks = [
        [sys.executable, "-m", "pytest", "-q", "--basetemp=.tmp/pytest"],
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "mypy", "src", "--cache-dir=.cache/mypy"],
        [sys.executable, "-m", "pip", "check"],
        [sys.executable, "tools/validate_iac.py"],
    ]
    output = ["Local verification; no remote workflow run implied.\n"]
    failed = False
    for command in checks:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)  # noqa: S603
        label = "python " + " ".join(command[1:])
        section = f"\n$ {label}\n{result.stdout}{result.stderr}exit_code={result.returncode}\n"
        output.append(section)
        print(section, end="")
        failed |= result.returncode != 0
    destination = root / "docs" / "validation"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "checks.txt").write_text("".join(output), encoding="utf-8")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
