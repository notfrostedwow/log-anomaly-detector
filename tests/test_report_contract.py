import io
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from log_anomaly_detector.core import Config, analyze, report_json
from log_anomaly_detector.io import load_config, read_events


def test_committed_report_is_actual_current_output_and_valid_schema():
    config = load_config(Path("samples/config.json"))
    events = read_events(io.BytesIO(Path("samples/auth.jsonl").read_bytes()), "jsonl", config)
    report = analyze(events, config)
    assert report_json(report) == Path("samples/report.json").read_text(encoding="utf-8")
    schema = json.loads(Path("docs/report-schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(report)
    validator.validate(analyze([], Config()))
    assert report["finding_count"] == len(report["findings"]) == 3
