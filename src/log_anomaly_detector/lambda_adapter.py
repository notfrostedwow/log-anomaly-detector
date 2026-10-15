"""Optional S3 adapter. Cloud I/O is injected; importing this module is offline."""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote_plus

from .core import Config, ValidationError, analyze
from .io import read_events

MAX_OBJECT_BYTES = 1024 * 1024
MAX_RECORDS = 10
MAX_SUMMARY_BYTES = 2048
KEY = re.compile(r"incoming/[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.(?:jsonl|csv)\Z", re.ASCII)
ETAG = re.compile(r"[0-9a-f]{32}(?:-[1-9][0-9]{0,5})?\Z", re.ASCII)
BUCKET = re.compile(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]\Z", re.ASCII)
CREATED = {
    "ObjectCreated:Put",
    "ObjectCreated:Post",
    "ObjectCreated:Copy",
    "ObjectCreated:CompleteMultipartUpload",
}


@dataclass(frozen=True)
class ObjectRef:
    bucket: str
    key: str
    etag: str
    size: int


def object_refs(event: object, bucket: str) -> list[ObjectRef]:
    if not BUCKET.fullmatch(bucket):
        raise ValidationError("adapter requires a configured bucket name")
    if not isinstance(event, dict) or not isinstance(event.get("Records"), list):
        raise ValidationError("expected an S3 Records event")
    records = event["Records"]
    if not 1 <= len(records) <= MAX_RECORDS:
        raise ValidationError("S3 event must contain 1-10 records")
    refs = []
    for record in records:
        try:
            if not isinstance(record, dict):
                raise ValidationError("invalid S3 record")
            if record["eventSource"] != "aws:s3" or record["eventName"] not in CREATED:
                raise ValidationError("expected S3 object-created record")
            version = record["eventVersion"]
            if not isinstance(version, str) or not re.fullmatch(r"2\.[0-9]{1,2}", version):
                raise ValidationError("unsupported S3 event version")
            data = record["s3"]
            actual_bucket = data["bucket"]["name"]
            obj = data["object"]
            key = obj["key"]
            etag = obj["eTag"]
            size = obj["size"]
            if actual_bucket != bucket:
                raise ValidationError("S3 bucket does not match configuration")
            if not isinstance(key, str) or len(key) > 512:
                raise ValidationError("invalid S3 key")
            key = unquote_plus(key, encoding="utf-8", errors="strict")
            if not KEY.fullmatch(key) or ".." in key:
                raise ValidationError("key must be a flat incoming JSONL or CSV filename")
            if not isinstance(etag, str) or not ETAG.fullmatch(etag):
                raise ValidationError("invalid S3 object ETag")
            if type(size) is not int or not 0 <= size <= MAX_OBJECT_BYTES:
                raise ValidationError("S3 object size limit exceeded or invalid")
            refs.append(ObjectRef(bucket, key, etag, size))
        except (KeyError, TypeError, UnicodeError) as exc:
            raise ValidationError("malformed S3 record") from exc
    return refs


def process_s3_event(
    event: object,
    *,
    bucket: str,
    fetch: Callable[[str, str, str, int], bytes],
    emit: Callable[[str], None],
    config: Config | None = None,
) -> list[dict[str, Any]]:
    """Return/emit bounded aggregate summaries, with no raw log identifiers.

    fetch must enforce its byte cap while reading, not after an unbounded read.
    Validate every record before any I/O. Duplicate object refs in one invocation
    are processed once; cross-invocation duplicates are deliberately not stored.
    """
    rules = config or Config(max_file_bytes=MAX_OBJECT_BYTES, max_events=5000, max_findings=500)
    if (
        rules.max_file_bytes > MAX_OBJECT_BYTES
        or rules.max_events > 5000
        or rules.max_findings > 500
    ):
        raise ValidationError("cloud configuration exceeds adapter limits")
    refs = object_refs(event, bucket)
    summaries: list[dict[str, Any]] = []
    seen: set[ObjectRef] = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        raw = fetch(ref.bucket, ref.key, ref.etag, rules.max_file_bytes)
        if not isinstance(raw, bytes) or len(raw) != ref.size or len(raw) > rules.max_file_bytes:
            raise ValidationError("fetched object size does not match bounded event metadata")
        report = analyze(read_events(io.BytesIO(raw), ref.key.rsplit(".", 1)[1], rules), rules)
        # A stable digest helps downstream deduplication; it contains no raw key.
        identity = json.dumps([ref.bucket, ref.key, ref.etag], separators=(",", ":"))
        summary = {
            "schema_version": "1.0",
            "kind": "authentication_rule_summary",
            "object_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            "events": report["input"]["events"],
            "unique_events": report["input"]["unique_events"],
            "duplicates_removed": report["input"]["duplicates_removed"],
            "finding_count": report["finding_count"],
            "rules": dict(sorted(Counter(f["rule"] for f in report["findings"]).items())),
        }
        encoded = json.dumps(summary, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_SUMMARY_BYTES:
            raise ValidationError("summary byte limit exceeded")
        emit(encoded)
        summaries.append(summary)
    return summaries
