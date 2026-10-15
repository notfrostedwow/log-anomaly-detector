from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from log_anomaly_detector.cli import main
from log_anomaly_detector.core import Config, Event, ValidationError, analyze, report_json
from log_anomaly_detector.io import load_config, read_events, regular_file


def row(second=0, user="mira", source="192.0.2.10", outcome="failure"):
    return {
        "timestamp": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=second)).isoformat(),
        "user": user,
        "source_ip": source,
        "outcome": outcome,
    }


def events(*rows):
    return [Event.parse(value) for value in rows]


def findings(rows, **kwargs):
    return analyze(events(*rows), Config(**kwargs))["findings"]


def read(data, kind="jsonl", **kwargs):
    return read_events(io.BytesIO(data), kind, Config(**kwargs))


def test_burst_positive_and_explanation():
    result = findings([row(second) for second in range(5)])
    assert len(result) == 1
    assert result[0]["rule"] == "failed_login_burst"
    assert result[0]["count"] == 5
    assert "threshold 5" in result[0]["explanation"]


@pytest.mark.parametrize(
    "rows",
    [
        [row(i) for i in range(4)],
        [row(i, outcome="success") for i in range(10)],
        [row(i * 301) for i in range(5)],
        [row(i, source=f"192.0.2.{i + 1}") for i in range(5)],
    ],
)
def test_negative(rows):
    assert findings(rows) == []


@pytest.mark.parametrize(("end", "expected"), [(300, 1), (300.000001, 0)])
def test_window_boundary(end, expected):
    assert len(findings([row(0), row(end)], burst_threshold=2)) == expected


def test_spray_counts_distinct_users_and_batches_same_timestamp():
    rows = [row(user=f"person{i}") for i in range(5)]
    result = findings(rows)
    assert len(result) == 1
    assert result[0]["rule"] == "password_spray"
    assert result[0]["count"] == 5
    assert result[0]["user"] is None


def test_spray_expires_users_and_repeated_user_is_not_spray():
    assert not findings([row(i) for i in range(4)], burst_threshold=100)
    assert not findings([row(0, "a"), row(301, "b")], spray_threshold=2)
    result = findings([row(0, "a"), row(1, "a"), row(300, "b")], spray_threshold=2)
    assert result[0]["count"] == 2


def test_overlapping_windows_are_explicit_findings():
    result = findings([row(i) for i in range(4)], burst_threshold=2)
    assert [item["count"] for item in result] == [2, 3, 4]


def test_burst_separates_users_and_sources():
    assert not findings([row(0, "a"), row(1, "b")], burst_threshold=2)
    assert not findings([row(0), row(1, source="192.0.2.11")], burst_threshold=2)


def test_unusual_source_baseline_semantics():
    baseline = {"mira": ["192.0.2.11"]}
    rows = [
        row(0, outcome="success"),
        row(1, outcome="success"),
        row(2, "unknown", outcome="success"),
        row(3, source="192.0.2.11", outcome="success"),
    ]
    result = findings(rows, baseline=baseline)
    assert len(result) == 1
    assert result[0]["rule"] == "unusual_source"
    assert result[0]["count"] == 1
    assert findings(rows) == []
    assert findings([row()], baseline=baseline) == []


def test_ipv6_baseline_normalization():
    assert not findings(
        [row(source="2001:db8::1", outcome="success")], baseline={"mira": ["2001:0db8:0:0:0:0:0:1"]}
    )


def test_out_of_order_dedup_timezone_and_determinism():
    rows = [row(i) for i in range(7)]
    duplicate = dict(rows[0], timestamp="2026-01-01T01:00:00+01:00")
    report = analyze(events(*rows, duplicate), Config())
    reversed_report = analyze(events(duplicate, *reversed(rows)), Config())
    assert report_json(report) == report_json(reversed_report)
    assert report["input"]["duplicates_removed"] == 1
    assert report["input"]["unique_events"] == 7
    assert report["schema_version"] == "1.0"
    assert "generated_at" not in report


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-01-01T00:00:00",
        "2026-01-01",
        "2026-02-30T00:00:00Z",
        "2026-01-01 00:00:00Z",
        "2026-01-01T00:00:60Z",
        "2026-01-01T00:00:00+00:60",
        "2026-01-01T00:00:00+24:00",
        "2026-01-01T00:00:00.1234567Z",
        "0001-01-01T00:00:00+01:00",
        "9999-12-31T23:59:59-01:00",
        None,
        1,
    ],
)
def test_bad_timestamps(stamp):
    with pytest.raises(ValidationError):
        Event.parse(dict(row(), timestamp=stamp))


def test_valid_timezone_and_microseconds():
    assert Event.parse(
        dict(row(), timestamp="2026-01-01T01:30:00.000001+01:30")
    ).timestamp == datetime(2026, 1, 1, microsecond=1, tzinfo=UTC)


def test_early_date_window_does_not_underflow():
    rows = [dict(row(i), timestamp=f"0001-01-01T00:00:0{i}Z") for i in range(2)]
    assert findings(rows, burst_threshold=2)[0]["window_start"] == "0001-01-01T00:00:00.000000Z"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("user", "\x1b[31m"),
        ("user", "a\nB"),
        ("user", "../secret"),
        ("user", "a" * 65),
        ("user", ""),
        ("user", "mïra"),
        ("user", None),
        ("source_ip", "example.invalid"),
        ("source_ip", "192.0.2.01"),
        ("source_ip", "fe80::1%eth0"),
        ("source_ip", "192.0.2.1\n"),
        ("outcome", "failed"),
        ("outcome", []),
        ("outcome", None),
    ],
)
def test_invalid_fields(key, value):
    with pytest.raises(ValidationError):
        Event.parse(dict(row(), **{key: value}))


@pytest.mark.parametrize("value", [[], None, {}, {**row(), "extra": "no"}])
def test_schema_exact(value):
    with pytest.raises(ValidationError):
        Event.parse(value)


@pytest.mark.parametrize(
    "data",
    [
        b"{",
        b"\n",
        b"null\n",
        b'{"user":"a","user":"b"}',
        b"NaN",
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"[" * 2000,
        b'{"x":Infinity}',
    ],
)
def test_invalid_jsonl(data):
    with pytest.raises(ValidationError):
        read(data)


def test_jsonl_and_csv_equivalence():
    rows = [row(i) for i in range(5)]
    jsonl = "\n".join(json.dumps(value) for value in rows).encode()
    csv = (
        "source_ip,timestamp,outcome,user\r\n"
        + "\r\n".join(f"{v['source_ip']},{v['timestamp']},{v['outcome']},{v['user']}" for v in rows)
    ).encode()
    assert read(jsonl) == read(csv, "csv")
    assert len(read(jsonl + b"\n")) == 5


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"user,user,outcome,timestamp",
        b"user,timestamp,outcome,source_ip,extra",
        b"user,timestamp,outcome,source_ip\na,b,c",
        b"user,timestamp,outcome,source_ip\n",
        b'user,timestamp,outcome,source_ip\n"a\nb",c,d,e',
        b'user,timestamp,outcome,source_ip\n"a,b,c,d',
    ],
)
def test_bad_csv(data):
    if data.endswith(b"source_ip\n"):
        assert read(data, "csv") == []  # A header alone is a valid empty CSV.
    else:
        with pytest.raises(ValidationError):
            read(data, "csv")


def test_empty_jsonl():
    report = analyze(read(b""), Config())
    assert report["input"]["start"] is None
    assert report["finding_count"] == 0


@pytest.mark.parametrize(
    ("data", "kwargs"),
    [
        (b"{}\n", {"max_line_bytes": 2}),
        (b"{}\n", {"max_file_bytes": 2}),
        ((json.dumps(row()) + "\n").encode() * 2, {"max_events": 1}),
    ],
)
def test_read_bounds(data, kwargs):
    with pytest.raises(ValidationError):
        read(data, **kwargs)


def test_exact_read_bounds():
    data = json.dumps(row()).encode()
    assert len(read(data, max_file_bytes=len(data), max_line_bytes=len(data), max_events=1)) == 1


def test_findings_cap_rejects_and_event_cap_includes_duplicates():
    with pytest.raises(ValidationError, match="finding limit"):
        findings([row(i) for i in range(4)], burst_threshold=2, max_findings=2)
    with pytest.raises(ValidationError, match="event limit"):
        analyze(events(row(), row()), Config(max_events=1))
    assert len(findings([row(i) for i in range(3)], burst_threshold=2, max_findings=2)) == 2


@pytest.mark.parametrize(
    "config",
    [
        [],
        {"unknown": 1},
        {"window_seconds": True},
        {"window_seconds": 0},
        {"burst_threshold": 1},
        {"spray_threshold": 1001},
        {"max_events": 20001},
        {"max_file_bytes": 8388609},
        {"max_line_bytes": 16385},
        {"max_findings": 2001},
        {"max_events": "5"},
        {"baseline": None},
        {"baseline": {"mira": []}},
        {"baseline": {"mira": "192.0.2.1"}},
        {"baseline": {"mira": ["bad"]}},
        {"baseline": {"../bad": ["192.0.2.1"]}},
    ],
)
def test_bad_config(config):
    with pytest.raises(ValidationError):
        Config.parse(config)


def test_valid_config_and_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"burst_threshold": 2}', encoding="utf-8")
    assert load_config(path).burst_threshold == 2
    assert len(findings([row(0), row(1)], burst_threshold=2)) == 1


@pytest.mark.parametrize(
    "data",
    [b"\xff", b"x" * 65537, b"{", b'{"max_events":1,"max_events":2}'],
    ids=["encoding", "oversize", "syntax", "duplicate-key"],
)
def test_bad_config_file(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_bytes(data)
    with pytest.raises(ValidationError):
        load_config(path)


def test_regular_file_checks(tmp_path):
    for path in (tmp_path, tmp_path / "missing"):
        with pytest.raises(ValidationError), regular_file(path):
            pytest.fail("should not open")


def test_cli_reports_and_exit_codes(tmp_path, capsys):
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(row(i)) for i in range(5)), encoding="utf-8")
    assert main([str(path), "--format", "jsonl", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["finding_count"] == 1
    assert main([str(path), "--format", "jsonl"]) == 1
    assert "failed_login_burst" in capsys.readouterr().out
    path.write_bytes(b"")
    assert main([str(path), "--format", "jsonl", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["finding_count"] == 0
    path.write_bytes(b"malformed\x1b[31m")
    assert main([str(path), "--format", "jsonl", "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "\x1b" not in captured.err
    assert "line 1" in captured.err


def test_cli_bad_arguments_are_not_echoed(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--bad\x1b[31m"])
    assert exc.value.code == 2
    assert "\x1b" not in capsys.readouterr().err


def test_cli_missing_path_is_not_echoed(capsys):
    assert main(["nonexistent\x1b[31m", "--format", "jsonl"]) == 2
    assert "\x1b" not in capsys.readouterr().err
