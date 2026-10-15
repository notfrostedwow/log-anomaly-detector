"""Run installed cfn-lint with sockets disabled and workspace-only AWS config."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Any, NoReturn


def deny_network(*args: Any, **kwargs: Any) -> NoReturn:
    raise RuntimeError("network access is disabled during offline IaC validation")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    temporary = root / ".tmp"
    temporary.mkdir(exist_ok=True)
    config = temporary / "empty-aws-config"
    config.write_text("[default]\nregion = us-east-1\n", encoding="utf-8")
    os.environ.update(
        {
            "AWS_CONFIG_FILE": str(config),
            "AWS_SHARED_CREDENTIALS_FILE": str(config),
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_ACCESS_KEY_ID": "offline-placeholder",
            "AWS_SECRET_ACCESS_KEY": "offline-placeholder",
            "AWS_SESSION_TOKEN": "offline-placeholder",
            "AWS_PROFILE": "default",
            "AWS_DEFAULT_PROFILE": "default",
        }
    )
    socket.socket.connect = deny_network  # type: ignore[method-assign]
    socket.socket.connect_ex = deny_network  # type: ignore[method-assign]
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    from cfnlint.runner import main as lint_main

    os.chdir(root)
    sys.argv = [
        "cfn-lint",
        "--config-file",
        "infra/cfnlintrc.json",
        "--template",
        "infra/template.yaml",
        "--regions",
        "us-east-1",
    ]
    print(" ".join(sys.argv) + " (network disabled)", flush=True)
    lint_main()


if __name__ == "__main__":
    main()
