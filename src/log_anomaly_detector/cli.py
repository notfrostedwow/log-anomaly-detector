"""CLI: stdout is either a complete report or summary; errors go to stderr."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

from . import __version__
from .core import Config, ValidationError, analyze, report_json
from .io import load_config, read_events, regular_file


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's default echoes untrusted argument text to terminals.
        self.print_usage(sys.stderr)
        self.exit(2, "error: invalid arguments; use --help\n")


def main(argv: list[str] | None = None) -> int:
    parser = Parser(prog="log-anomaly-detector", description="Offline authentication-log rules")
    parser.add_argument("input", type=Path, help="regular UTF-8 JSONL or CSV file")
    parser.add_argument("--format", choices=("jsonl", "csv"), required=True)
    parser.add_argument("--config", type=Path, help="strict JSON configuration")
    parser.add_argument("--json", action="store_true", help="emit stable schema-versioned JSON")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config) if args.config else Config()
        with regular_file(args.input) as stream:
            events = read_events(stream, args.format, config)
        report = analyze(events, config)
        if args.json:
            print(report_json(report), end="")
        else:
            print(f"Authentication analysis | schema {report['schema_version']} | offline rules")
            print(
                f"Events: {report['input']['events']} | unique: {report['input']['unique_events']} "
                f"| duplicates removed: {report['input']['duplicates_removed']}"
            )
            print(f"Findings: {report['finding_count']}")
            for finding in report["findings"]:
                print(f"[{finding['rule']}] {finding['window_end']} {finding['explanation']}")
        return 1 if report["finding_count"] else 0
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("error: local I/O failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
