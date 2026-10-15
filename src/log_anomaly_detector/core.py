"""Strict data contracts and deterministic, bounded sliding-window rules."""

from __future__ import annotations

import ipaddress
import json
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import groupby
from typing import Any

HARD_FILE_BYTES = 8 * 1024 * 1024
HARD_LINE_BYTES = 16 * 1024
HARD_EVENTS = 20_000
HARD_FINDINGS = 2_000
FIELDS = {"timestamp", "user", "source_ip", "outcome"}
USER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z", re.ASCII)
STAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z",
    re.ASCII,
)


class ValidationError(ValueError):
    """A safe, fixed-text diagnostic that never echoes untrusted values."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise ValidationError("non-finite JSON number")


def strict_json(data: str) -> Any:
    try:
        return json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        raise ValidationError("invalid JSON") from exc


def canonical_ip(value: object) -> str:
    if not isinstance(value, str) or len(value) > 45 or "%" in value:
        raise ValidationError("source_ip must be an IPv4 or IPv6 address without a zone")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise ValidationError("source_ip must be an IPv4 or IPv6 address without a zone") from exc


def username(value: object) -> str:
    if not isinstance(value, str) or not USER.fullmatch(value):
        raise ValidationError(
            "user must be 1-64 ASCII letters, digits, dots, underscores or hyphens; "
            "start with a letter"
        )
    return value


def timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not STAMP.fullmatch(value):
        raise ValidationError("timestamp must be an ISO 8601 date-time with explicit UTC offset")
    try:
        if value[-1] != "Z" and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
            raise ValueError("invalid offset")
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise ValidationError(
            "invalid timestamp or UTC conversion outside supported dates"
        ) from exc


def iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, order=True)
class Event:
    timestamp: datetime
    user: str
    source_ip: str
    outcome: str

    @classmethod
    def parse(cls, value: object) -> Event:
        if not isinstance(value, dict) or set(value) != FIELDS:
            raise ValidationError("event must have exactly timestamp, user, source_ip, outcome")
        if value["outcome"] not in ("failure", "success"):
            raise ValidationError("outcome must be failure or success")
        return cls(
            timestamp(value["timestamp"]),
            username(value["user"]),
            canonical_ip(value["source_ip"]),
            value["outcome"],
        )


@dataclass(frozen=True)
class Config:
    window_seconds: int = 300
    burst_threshold: int = 5
    spray_threshold: int = 5
    max_file_bytes: int = HARD_FILE_BYTES
    max_line_bytes: int = HARD_LINE_BYTES
    max_events: int = HARD_EVENTS
    max_findings: int = HARD_FINDINGS
    baseline: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        limits = {
            "window_seconds": (1, 86_400),
            "burst_threshold": (2, 1_000),
            "spray_threshold": (2, 1_000),
            "max_file_bytes": (1, HARD_FILE_BYTES),
            "max_line_bytes": (1, HARD_LINE_BYTES),
            "max_events": (1, HARD_EVENTS),
            "max_findings": (1, HARD_FINDINGS),
        }
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValidationError(f"{name} must be an integer between {low} and {high}")
        if not isinstance(self.baseline, dict) or len(self.baseline) > 1_000:
            raise ValidationError("baseline must be a mapping with at most 1000 users")
        normalized: dict[str, tuple[str, ...]] = {}
        for user, sources in self.baseline.items():
            username(user)
            if not isinstance(sources, list | tuple) or not 1 <= len(sources) <= 32:
                raise ValidationError("baseline users need 1-32 explicit allowed source IPs")
            normalized[user] = tuple(sorted({canonical_ip(source) for source in sources}))
        object.__setattr__(self, "baseline", normalized)

    @classmethod
    def parse(cls, value: object) -> Config:
        allowed = set(cls.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) - allowed:
            raise ValidationError("config must be an object containing only documented settings")
        return cls(**value)

    def public(self) -> dict[str, Any]:
        return {
            name: getattr(self, name) for name in self.__dataclass_fields__ if name != "baseline"
        }


def analyze(events: list[Event], config: Config) -> dict[str, Any]:
    """Sort/deduplicate, then emit one finding per qualifying right endpoint/group.

    Every input row counts toward the input cap, including duplicates. A window is
    [endpoint - window_seconds, endpoint], inclusive. Findings exceeding the cap
    reject the analysis, so a successful report is never silently truncated.
    """
    if len(events) > config.max_events:
        raise ValidationError("event limit exceeded")
    ordered = sorted(set(events))
    findings: list[dict[str, Any]] = []
    bursts: dict[tuple[str, str], list[Event]] = defaultdict(list)
    sprays: dict[str, list[Event]] = defaultdict(list)
    unusual: set[tuple[str, str]] = set()
    delta = timedelta(seconds=config.window_seconds)

    def emit(
        rule: str,
        event: Event,
        start: datetime,
        count: int,
        explanation: str,
        user: str | None = None,
    ) -> None:
        if len(findings) >= config.max_findings:
            raise ValidationError("finding limit exceeded; narrow input or raise configured cap")
        findings.append(
            {
                "rule": rule,
                "source_ip": event.source_ip,
                "user": user,
                "window_start": iso(start),
                "window_end": iso(event.timestamp),
                "count": count,
                "explanation": explanation,
            }
        )

    for event in ordered:
        if event.outcome == "success":
            allowed = config.baseline.get(event.user)
            pair = (event.user, event.source_ip)
            if allowed is not None and event.source_ip not in allowed and pair not in unusual:
                unusual.add(pair)
                emit(
                    "unusual_source",
                    event,
                    event.timestamp,
                    1,
                    f"Successful login for {event.user} from {event.source_ip}; source is absent "
                    "from this user's explicit baseline. First occurrence per user/source.",
                    event.user,
                )
            continue
        bursts[(event.source_ip, event.user)].append(event)
        sprays[event.source_ip].append(event)

    for rule, groups, threshold in (
        ("failed_login_burst", bursts.values(), config.burst_threshold),
        ("password_spray", sprays.values(), config.spray_threshold),
    ):
        for group in groups:
            window: deque[Event] = deque()
            counts: Counter[str] = Counter()
            # Batch equal timestamps: a window includes every event at its endpoint.
            for endpoint, batch in groupby(group, key=lambda event: event.timestamp):
                try:
                    cutoff = endpoint - delta
                except OverflowError:
                    cutoff = datetime.min.replace(tzinfo=UTC)
                for event in batch:
                    window.append(event)
                    counts[event.user] += 1
                while window[0].timestamp < cutoff:
                    old = window.popleft()
                    counts[old.user] -= 1
                    if counts[old.user] == 0:
                        del counts[old.user]
                event = window[-1]
                count = len(window) if rule == "failed_login_burst" else len(counts)
                if count >= threshold:
                    detail = (
                        f"{count} failed logins for {event.user}"
                        if rule == "failed_login_burst"
                        else f"Failed logins for {count} distinct users"
                    )
                    emit(
                        rule,
                        event,
                        cutoff,
                        count,
                        f"{detail} from {event.source_ip} in the inclusive "
                        f"{config.window_seconds}s window; threshold {threshold}.",
                        event.user if rule == "failed_login_burst" else None,
                    )

    findings.sort(key=lambda f: (f["window_end"], f["rule"], f["source_ip"], f["user"] or ""))
    return {
        "schema_version": "1.0",
        "tool_version": "0.1.0",
        "settings": config.public(),
        "baseline": {"mode": "explicit_per_user_success_only", "users": len(config.baseline)},
        "input": {
            "events": len(events),
            "unique_events": len(ordered),
            "duplicates_removed": len(events) - len(ordered),
            "start": iso(ordered[0].timestamp) if ordered else None,
            "end": iso(ordered[-1].timestamp) if ordered else None,
        },
        "finding_count": len(findings),
        "findings": findings,
    }


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
