"""Build and smoke-test a wheel in a clean venv with package-index access disabled."""

from __future__ import annotations

import os
import subprocess
import sys
import venv
import zipfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    temporary = root / ".tmp"
    temporary.mkdir(exist_ok=True)
    environment = dict(
        os.environ,
        PIP_NO_INDEX="1",
        PIP_CONFIG_FILE=os.devnull,
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PIP_CACHE_DIR=str(root / ".cache" / "pip"),
        TMP=str(temporary),
        TEMP=str(temporary),
        TMPDIR=str(temporary),
    )
    transcript = ["Offline wheel build and clean-install smoke check.\n"]

    def run(command: list[str], expected: int = 0) -> str:
        # Commands are constructed below from the local interpreter and fixed arguments.
        result = subprocess.run(  # noqa: S603
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        command_text = " ".join(
            str(Path(arg).relative_to(root)) if arg.startswith(str(root)) else arg
            for arg in command
        )
        transcript.append(
            f"\n$ {command_text}\n{result.stdout}{result.stderr}"
            f"exit_code={result.returncode} (expected {expected})\n"
        )
        if result.returncode != expected:
            raise RuntimeError("offline package command failed")
        return result.stdout

    destination = root / "docs" / "validation" / "package.txt"
    try:
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                "artifacts",
                ".",
            ]
        )
        wheel = root / "artifacts" / "log_anomaly_detector-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel) as archive:
            license_name = "log_anomaly_detector-0.1.0.dist-info/licenses/LICENSE"
            if archive.read(license_name) != (root / "LICENSE").read_bytes():
                raise RuntimeError("wheel license does not match approved LICENSE")
            metadata = archive.read("log_anomaly_detector-0.1.0.dist-info/METADATA").decode()
            if "License-Expression: MIT" not in metadata.splitlines():
                raise RuntimeError("wheel MIT license metadata is missing")
        transcript.append(
            "Wheel LICENSE matches approved source; License-Expression: MIT present.\n"
        )
        smoke = temporary / "wheel-smoke"
        venv.EnvBuilder(with_pip=True).create(smoke)
        scripts = smoke / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        cli = scripts / ("log-anomaly-detector.exe" if os.name == "nt" else "log-anomaly-detector")
        run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--force-reinstall",
                "--no-index",
                "--no-deps",
                str(wheel),
            ]
        )
        actual = run(
            [
                str(cli),
                "samples/auth.jsonl",
                "--format",
                "jsonl",
                "--config",
                "samples/config.json",
                "--json",
            ],
            expected=1,
        )
        if actual != (root / "samples" / "report.json").read_text(encoding="utf-8"):
            raise RuntimeError("installed wheel report differs from captured report")
        transcript.append("Clean wheel-installed console script matches committed sample report.\n")
    finally:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("".join(transcript), encoding="utf-8")
    print("Offline wheel build, MIT metadata/license and clean-install CLI smoke check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
