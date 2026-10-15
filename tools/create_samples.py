"""Regenerate small synthetic fixtures, never read an external data source."""

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    rows = []
    for second in range(5):
        rows.append(
            {
                "timestamp": (
                    datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=second)
                ).isoformat(),
                "user": "mira",
                "source_ip": "192.0.2.44",
                "outcome": "failure",
            }
        )
    for user in ("tavi", "lumo", "nori", "sela", "orin"):
        rows.append(
            {
                "timestamp": "2026-01-01T00:10:00Z",
                "user": user,
                "source_ip": "198.51.100.20",
                "outcome": "failure",
            }
        )
    rows.append(
        {
            "timestamp": "2026-01-01T00:20:00Z",
            "user": "mira",
            "source_ip": "203.0.113.9",
            "outcome": "success",
        }
    )
    rows.append(
        {
            "timestamp": "2026-01-01T00:21:00Z",
            "user": "tavi",
            "source_ip": "2001:db8::10",
            "outcome": "success",
        }
    )
    # An offset-equivalent duplicate and reversed ordering exercise the contract.
    rows.append(dict(rows[0], timestamp="2026-01-01T01:00:00+01:00"))
    rows.reverse()
    sample = root / "samples"
    (sample / "auth.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    with (sample / "auth.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ["timestamp", "user", "source_ip", "outcome"])
        writer.writeheader()
        writer.writerows(rows)
    (sample / "quiet.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "user": "mira",
                "source_ip": "192.0.2.10",
                "outcome": "success",
            }
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
