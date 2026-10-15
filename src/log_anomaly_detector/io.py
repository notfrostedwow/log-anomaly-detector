"""Bounded UTF-8 file and record handling; never include source text in errors."""

from __future__ import annotations

import csv
import io
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from .core import FIELDS, Config, Event, ValidationError, strict_json


@contextmanager
def regular_file(path: Path) -> Iterator[BinaryIO]:
    # Reject symlinks/junctions, including parents. No devices, pipes, or directories.
    absolute = path.absolute()
    if str(path).startswith("\\\\") or absolute.drive.startswith("\\\\"):
        raise ValidationError("network and device paths are not supported")
    if os.name == "nt" and any(
        ":" in part or Path(part).is_reserved() for part in absolute.parts[1:]
    ):
        raise ValidationError("device names and alternate data streams are not supported")
    try:
        for part in (absolute, *absolute.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValidationError("input paths must not contain links or reparse points")
        before = absolute.stat()
        if not stat.S_ISREG(before.st_mode):
            raise ValidationError("input must be a regular file")
        descriptor = os.open(
            absolute,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise ValidationError("input changed while opening")
            yield stream
    except OSError as exc:
        raise ValidationError("cannot read regular input file") from exc


def lines(stream: BinaryIO, config: Config) -> Iterator[tuple[int, str]]:
    total = 0
    number = 0
    while raw := stream.readline(config.max_line_bytes + 1):
        number += 1
        total += len(raw)
        if total > config.max_file_bytes:
            raise ValidationError("file byte limit exceeded")
        if len(raw) > config.max_line_bytes:
            raise ValidationError(f"line {number}: line byte limit exceeded")
        try:
            value = raw.decode("utf-8")
        except UnicodeError as exc:
            raise ValidationError(f"line {number}: invalid UTF-8") from exc
        # csv.reader must never interpret a physical record as multiple records.
        yield number, value.removesuffix("\n").removesuffix("\r")


def read_events(stream: BinaryIO, kind: str, config: Config) -> list[Event]:
    if kind not in ("jsonl", "csv"):
        raise ValidationError("format must be jsonl or csv")
    events: list[Event] = []
    header: list[str] | None = None
    for number, line in lines(stream, config):
        try:
            if kind == "jsonl":
                record = strict_json(line)
            else:
                row = next(csv.reader(io.StringIO(line), strict=True))
                if header is None:
                    if len(row) != 4 or set(row) != FIELDS:
                        raise ValidationError("CSV header must name the four schema fields once")
                    header = row
                    continue
                if len(row) != len(header):
                    raise ValidationError("CSV row must have exactly four fields")
                record = dict(zip(header, row, strict=True))
            if len(events) >= config.max_events:
                raise ValidationError("event limit exceeded")
            events.append(Event.parse(record))
        except (ValidationError, csv.Error, StopIteration) as exc:
            reason = str(exc) if isinstance(exc, ValidationError) else "invalid single-line CSV"
            raise ValidationError(f"line {number}: {reason}") from exc
    if kind == "csv" and header is None:
        raise ValidationError("CSV requires a header")
    return events


def load_config(path: Path) -> Config:
    with regular_file(path) as stream:
        raw = stream.read(65_537)
    if len(raw) > 65_536:
        raise ValidationError("config byte limit exceeded (65536)")
    try:
        return Config.parse(strict_json(raw.decode("utf-8")))
    except UnicodeError as exc:
        raise ValidationError("config must be UTF-8") from exc
