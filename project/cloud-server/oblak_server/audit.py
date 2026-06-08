from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from oblak_server.config import Settings
from oblak_server.database import utc_now

ZERO_HASH = "0" * 64


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _event_hash(event_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(event_without_hash)).hexdigest()


def _last_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT event_hash FROM audit_events ORDER BY ts DESC, id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return ZERO_HASH
    return str(row["event_hash"])


def record_audit(
    conn: sqlite3.Connection,
    settings: Settings,
    event_type: str,
    *,
    outcome: str,
    actor_user_id: str | None = None,
    function_id: str | None = None,
    request_id: str | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_id = str(uuid.uuid4())
    event = {
        "id": event_id,
        "ts": utc_now(),
        "event_type": event_type,
        "actor_user_id": actor_user_id,
        "function_id": function_id,
        "request_id": request_id,
        "ip": ip,
        "outcome": outcome,
        "details": details or {},
        "prev_hash": _last_hash(conn),
    }
    event["hash"] = _event_hash(event)
    conn.execute(
        """
        INSERT INTO audit_events (
            id, ts, event_type, actor_user_id, function_id, request_id, ip,
            outcome, details_json, prev_hash, event_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["id"],
            event["ts"],
            event["event_type"],
            event["actor_user_id"],
            event["function_id"],
            event["request_id"],
            event["ip"],
            event["outcome"],
            json.dumps(event["details"], sort_keys=True),
            event["prev_hash"],
            event["hash"],
        ),
    )
    settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.audit_log_path.open("a", encoding="utf-8") as audit_log:
        audit_log.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
    return event
