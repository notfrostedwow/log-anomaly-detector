from __future__ import annotations

import copy
import io
import json
from types import SimpleNamespace

import pytest

from log_anomaly_detector import aws_lambda
from log_anomaly_detector.core import Config, ValidationError
from log_anomaly_detector.lambda_adapter import MAX_OBJECT_BYTES, process_s3_event

BUCKET = "synthetic-review-input"
ETAG = "a" * 32
RAW = (
    b'{"timestamp":"2026-01-01T00:00:00Z","user":"mira",'
    b'"source_ip":"192.0.2.10","outcome":"success"}\n'
)


def s3_event(raw=RAW, key="incoming/auth.jsonl"):
    return {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventVersion": "2.1",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": BUCKET},
                    "object": {"key": key, "size": len(raw), "eTag": ETAG},
                },
            }
        ]
    }


def run(event, raw=RAW, **kwargs):
    calls = []
    output = []

    def fetch(*args):
        calls.append(args)
        return raw

    summaries = process_s3_event(event, bucket=BUCKET, fetch=fetch, emit=output.append, **kwargs)
    return calls, output, summaries


def test_success_aggregate_only_and_bounded():
    calls, output, summaries = run(s3_event())
    assert calls == [(BUCKET, "incoming/auth.jsonl", ETAG, MAX_OBJECT_BYTES)]
    assert len(summaries) == 1
    assert summaries[0]["events"] == 1
    assert len(output[0].encode()) <= 2048
    for forbidden in (BUCKET, "incoming/", "mira", "192.0.2.10", "timestamp", "eTag"):
        assert forbidden not in output[0]
    assert json.loads(output[0]) == summaries[0]


def test_burst_summary_uses_real_analysis():
    raw = b"".join(
        RAW.replace(b"00:00:00", f"00:00:0{i}".encode()).replace(b"success", b"failure")
        for i in range(5)
    )
    _, _, summaries = run(s3_event(raw), raw)
    assert summaries[0]["rules"] == {"failed_login_burst": 1}


def test_csv_and_encoded_key():
    raw = b"timestamp,user,source_ip,outcome\n2026-01-01T00:00:00Z,mira,192.0.2.10,success\n"
    calls, _, summary = run(s3_event(raw, "incoming%2Fauth.csv"), raw)
    assert calls[0][1] == "incoming/auth.csv"
    assert summary[0]["unique_events"] == 1


def test_duplicate_delivery_is_local_only_and_identity_is_stable():
    event = s3_event()
    event["Records"].append(copy.deepcopy(event["Records"][0]))
    calls, first, _ = run(event)
    assert len(calls) == 1
    _, second, _ = run(event)
    assert first == second  # A later invocation emits again; no exactly-once claim.


@pytest.mark.parametrize(
    "event",
    [
        None,
        [],
        {},
        {"Records": []},
        {"Records": [None]},
        {"Records": [{}] * 11},
        {"Records": "bad"},
    ],
)
def test_bad_event_envelope_before_io(event):
    def forbidden(*args):
        pytest.fail("invalid event reached cloud I/O")

    with pytest.raises(ValidationError):
        process_s3_event(event, bucket=BUCKET, fetch=forbidden, emit=forbidden)


@pytest.mark.parametrize(
    "key",
    [
        "../auth.jsonl",
        "incoming/../auth.jsonl",
        "out/auth.jsonl",
        "incoming/dir/auth.jsonl",
        "incoming/a.jsonl\n",
        "incoming/a.exe",
        "incoming/%FF.jsonl",
        "incoming/a+space.jsonl",
        "incoming/a%00.jsonl",
        "incoming/a..jsonl",
        "incoming/" + "a" * 513,
        None,
    ],
)
def test_bad_keys_before_io(key):
    event = s3_event()
    event["Records"][0]["s3"]["object"]["key"] = key
    with pytest.raises(ValidationError):
        run(event)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("eTag", "bad"),
        ("eTag", None),
        ("size", MAX_OBJECT_BYTES + 1),
        ("size", -1),
        ("size", True),
        ("size", "1"),
    ],
)
def test_invalid_object_metadata(field, value):
    event = s3_event()
    event["Records"][0]["s3"]["object"][field] = value
    with pytest.raises(ValidationError):
        run(event)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("eventSource", "other"),
        ("eventName", "ObjectRemoved:Delete"),
        ("eventName", []),
        ("eventVersion", "3.0"),
    ],
)
def test_invalid_record_metadata(field, value):
    event = s3_event()
    event["Records"][0][field] = value
    with pytest.raises(ValidationError):
        run(event)


def test_wrong_bucket_and_prevalidate_entire_batch():
    event = s3_event()
    event["Records"].append(copy.deepcopy(event["Records"][0]))
    event["Records"][1]["s3"]["bucket"]["name"] = "another-bucket"
    calls = []
    with pytest.raises(ValidationError):
        process_s3_event(event, bucket=BUCKET, fetch=lambda *a: calls.append(a), emit=print)
    assert not calls


@pytest.mark.parametrize(
    "raw",
    [b"{", RAW + b" ", b"x" * (MAX_OBJECT_BYTES + 1)],
    ids=["malformed", "size-mismatch", "oversized"],
)
def test_bad_object_content(raw):
    with pytest.raises(ValidationError):
        run(s3_event(), raw)


def test_cloud_config_can_supply_explicit_baseline_and_cannot_raise_caps():
    config = Config(
        max_file_bytes=1024, max_events=100, max_findings=10, baseline={"mira": ["192.0.2.11"]}
    )
    assert run(s3_event(), config=config)[2][0]["rules"] == {"unusual_source": 1}
    with pytest.raises(ValidationError, match="cloud configuration"):
        run(s3_event(), config=Config())


class FakeBody(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.requested = []

    def read(self, size=-1):
        self.requested.append(size)
        assert size >= 0, "unbounded reads are forbidden"
        return super().read(size)


class FakeClient:
    def __init__(self, data=RAW, size=None):
        self.body = FakeBody(data)
        self.size = len(data) if size is None else size
        self.calls = []

    def get_object(self, **kwargs):
        self.calls.append(kwargs)
        return {"Body": self.body, "ContentLength": self.size}


def test_sdk_wrapper_bounded_conditional_read_and_close():
    client = FakeClient()
    output = []
    assert aws_lambda.handle(s3_event(), client=client, bucket=BUCKET, emit=output.append) == {
        "processed_objects": 1
    }
    assert client.calls == [
        {"Bucket": BUCKET, "Key": "incoming/auth.jsonl", "IfMatch": f'"{ETAG}"'}
    ]
    assert client.body.requested == [MAX_OBJECT_BYTES + 1]
    assert client.body.closed


@pytest.mark.parametrize("size", [MAX_OBJECT_BYTES + 1, -1, True, "1"])
def test_sdk_wrapper_rejects_bad_size_and_closes(size):
    client = FakeClient(size=size)
    with pytest.raises(ValidationError):
        aws_lambda.s3_fetcher(client)(BUCKET, "incoming/auth.jsonl", ETAG, MAX_OBJECT_BYTES)
    assert client.body.closed
    assert client.body.requested == []


def test_sdk_wrapper_body_mismatch_and_sanitized_failure():
    client = FakeClient(size=len(RAW) + 1)
    with pytest.raises(RuntimeError, match="object analysis failed") as exc:
        aws_lambda.handle(s3_event(), client=client, bucket=BUCKET, emit=print)
    assert "incoming" not in str(exc.value)
    assert exc.value.__suppress_context__
    assert client.body.closed


def test_sdk_exception_never_reaches_runtime_logs():
    class FailingClient:
        def get_object(self, **kwargs):
            raise ValueError("sensitive-object-name\x1b[31m")

    with pytest.raises(RuntimeError) as exc:
        aws_lambda.handle(s3_event(), client=FailingClient(), bucket=BUCKET, emit=print)
    assert "sensitive" not in str(exc.value)


def test_lambda_entrypoint_uses_injected_fake_sdk(monkeypatch, capsys):
    client = FakeClient()
    monkeypatch.setattr(
        aws_lambda.importlib,
        "import_module",
        lambda name: SimpleNamespace(client=lambda service: client),
    )
    monkeypatch.setenv("SOURCE_BUCKET", BUCKET)
    monkeypatch.setenv("RULE_CONFIG_JSON", "{}")
    assert aws_lambda.lambda_handler(s3_event(), None) == {"processed_objects": 1}
    assert json.loads(capsys.readouterr().out)["events"] == 1


@pytest.mark.parametrize("setting", ["[]", '{"max_events":20000}', "x" * 4097])
def test_lambda_bad_config_is_sanitized(monkeypatch, setting):
    monkeypatch.setattr(
        aws_lambda.importlib,
        "import_module",
        lambda name: SimpleNamespace(client=lambda service: FakeClient()),
    )
    monkeypatch.setenv("SOURCE_BUCKET", BUCKET)
    monkeypatch.setenv("RULE_CONFIG_JSON", setting)
    with pytest.raises(RuntimeError, match="object analysis failed"):
        aws_lambda.lambda_handler(s3_event(), None)
