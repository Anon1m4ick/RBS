"""Append-only JSONL audit log with a simple hash chain."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any


ZERO_HASH = "0" * 64


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _event_hash(event_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(event_without_hash)).hexdigest()


class AuditLog:
    """Writes audit events where each event commits to the previous event hash."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._read_last_hash()

    def record(self, event_type: str, **fields: Any) -> dict[str, Any]:
        event = {
            "ts": dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "event_type": event_type,
            "prev_hash": self._last_hash,
            **fields,
        }
        event["hash"] = _event_hash(event)
        with self.path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            audit_file.flush()
        self._last_hash = event["hash"]
        return event

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return ZERO_HASH
        last_hash = ZERO_HASH
        with self.path.open("r", encoding="utf-8") as audit_file:
            for line in audit_file:
                if line.strip():
                    last_hash = json.loads(line)["hash"]
        return last_hash


def load_events(path: str | Path) -> list[dict[str, Any]]:
    audit_path = Path(path)
    if not audit_path.exists():
        return []
    with audit_path.open("r", encoding="utf-8") as audit_file:
        return [json.loads(line) for line in audit_file if line.strip()]


def verify_hash_chain(path: str | Path) -> bool:
    previous = ZERO_HASH
    for event in load_events(path):
        if event.get("prev_hash") != previous:
            return False
        event_hash = event.get("hash")
        event_without_hash = dict(event)
        event_without_hash.pop("hash", None)
        if event_hash != _event_hash(event_without_hash):
            return False
        previous = event_hash
    return True

