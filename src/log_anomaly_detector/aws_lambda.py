"""Undeployed AWS entry point. No SDK import or cloud activity at module import."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from typing import Any

from .core import Config, ValidationError, strict_json
from .lambda_adapter import process_s3_event


def s3_fetcher(client: Any) -> Callable[[str, str, str, int], bytes]:
    def fetch(bucket: str, key: str, etag: str, limit: int) -> bytes:
        response = client.get_object(Bucket=bucket, Key=key, IfMatch=f'"{etag}"')
        body = response["Body"]
        try:
            size = response["ContentLength"]
            if type(size) is not int or not 0 <= size <= limit:
                raise ValidationError("S3 response size limit exceeded or invalid")
            raw = body.read(limit + 1)
            if not isinstance(raw, bytes) or len(raw) > limit or len(raw) != size:
                raise ValidationError("S3 response body size mismatch")
            return raw
        finally:
            body.close()

    return fetch


def handle(
    event: object,
    *,
    client: Any,
    bucket: str,
    emit: Callable[[str], None],
    config: Config | None = None,
) -> dict[str, int]:
    try:
        summaries = process_s3_event(
            event, bucket=bucket, fetch=s3_fetcher(client), emit=emit, config=config
        )
        return {"processed_objects": len(summaries)}
    except Exception:
        # Never let Lambda log an SDK exception containing a key or raw data.
        raise RuntimeError(
            "object analysis failed; inspect aggregate operational metrics"
        ) from None


def lambda_handler(event: object, context: object) -> dict[str, int]:
    del context
    try:
        # Lambda provides boto3; the offline package does not depend on it.
        boto3 = importlib.import_module("boto3")
        config_text = os.environ.get("RULE_CONFIG_JSON", "{}")
        if len(config_text.encode("utf-8")) > 4096:
            raise ValidationError("cloud config exceeds 4096 bytes")
        settings = {"max_file_bytes": 1024 * 1024, "max_events": 5000, "max_findings": 500}
        supplied = strict_json(config_text)
        if not isinstance(supplied, dict):
            raise ValidationError("cloud config must be a JSON object")
        config = Config.parse({**settings, **supplied})
        return handle(
            event,
            client=boto3.client("s3"),
            bucket=os.environ["SOURCE_BUCKET"],
            emit=print,
            config=config,
        )
    except Exception:
        raise RuntimeError(
            "object analysis failed; inspect aggregate operational metrics"
        ) from None
