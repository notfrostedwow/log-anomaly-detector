"""Capture actual CLI subprocess output; no constructed or illustrated output."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    executable = Path(sys.executable).parent / (
        "log-anomaly-detector.exe" if os.name == "nt" else "log-anomaly-detector"
    )
    common = ["samples/auth.jsonl", "--format", "jsonl", "--config", "samples/config.json"]
    checks = [
        ([str(executable), *common], 1),
        ([str(executable), *common, "--json"], 1),
        (
            [
                str(executable),
                "samples/auth.csv",
                "--format",
                "csv",
                "--config",
                "samples/config.json",
                "--json",
            ],
            1,
        ),
        ([str(executable), "samples/quiet.jsonl", "--format", "jsonl"], 0),
        ([sys.executable, "-m", "log_anomaly_detector.cli", *common], 1),
        ([str(executable), "--version"], 0),
        ([str(executable), "--help"], 0),
    ]
    captured = ["Actual local CLI subprocess output (synthetic data).\n"]
    json_report = ""
    for index, (command, expected) in enumerate(checks):
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)  # noqa: S603
        label = Path(command[0]).name + " " + " ".join(command[1:])
        captured.append(
            f"\n$ {label}\n{result.stdout}{result.stderr}exit_code={result.returncode} "
            f"(expected {expected})\n"
        )
        if result.returncode != expected or result.stderr:
            raise RuntimeError("CLI demo command did not match documented behavior")
        if index == 0:
            (root / "samples" / "report.txt").write_text(result.stdout, encoding="utf-8")
        elif index == 1:
            json_report = result.stdout
            (root / "samples" / "report.json").write_text(json_report, encoding="utf-8")
        elif index == 2 and result.stdout != json_report:
            raise RuntimeError("CSV and JSONL reports differ")
    destination = root / "docs" / "validation"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "cli-demo.txt").write_text("".join(captured), encoding="utf-8")
    print("7 actual CLI commands matched expected exit codes; JSONL and CSV reports are identical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
