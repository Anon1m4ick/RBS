from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from oblak_server.config import Settings
from oblak_server.main import create_app


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "cloud.sqlite3",
        audit_log_path=tmp_path / "audit.jsonl",
        public_base_url="http://testserver",
        bootstrap_username="alice",
        bootstrap_token="secret-token",
    )
    app = create_app(settings)
    monkeypatch.setattr("oblak_server.main.run_code_verifier", lambda path: {"ok": True})
    monkeypatch.setattr("oblak_server.main.run_requirements_antivirus", lambda path: (True, ""))
    return TestClient(app)


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer secret-token"}


def test_auth_me_accepts_bootstrap_token(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/auth/me", headers=_auth())

    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_auth_me_rejects_invalid_token(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/auth/me", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401


def test_upload_stores_verified_function_and_requirements(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/functions",
            headers=_auth(),
            files={
                "file": ("handler.py", b"def handle(event):\n    return {'ok': True}\n", "text/x-python"),
                "requirements": ("requirements.txt", b"requests==2.32.3\n", "text/plain"),
            },
        )
        listed = client.get("/functions", headers=_auth())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "VERIFIED"
    assert body["invoke_url"].endswith(f"/run/{body['function_id']}")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == body["function_id"]

    conn = sqlite3.connect(tmp_path / "cloud.sqlite3")
    row = conn.execute(
        "SELECT code, requirements, status FROM functions WHERE id = ?",
        (body["function_id"],),
    ).fetchone()
    assert row[0].startswith(b"def handle")
    assert row[1] == b"requests==2.32.3\n"
    assert row[2] == "VERIFIED"


def test_upload_rejects_failed_verification_and_audits(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        database_path=tmp_path / "cloud.sqlite3",
        audit_log_path=tmp_path / "audit.jsonl",
        public_base_url="http://testserver",
        bootstrap_username="alice",
        bootstrap_token="secret-token",
    )
    app = create_app(settings)
    monkeypatch.setattr(
        "oblak_server.main.run_code_verifier",
        lambda path: {"ok": False, "failed_check": "bandit", "reason": "shell usage"},
    )

    with TestClient(app) as client:
        response = client.post(
            "/functions",
            headers=_auth(),
            files={"file": ("handler.py", b"import os\nos.system('id')\n", "text/x-python")},
        )

    assert response.status_code == 400
    assert "Verification failed (bandit)" in response.json()["detail"]

    conn = sqlite3.connect(tmp_path / "cloud.sqlite3")
    row = conn.execute("SELECT status, verification_result FROM functions").fetchone()
    assert row[0] == "REJECTED"
    assert json.loads(row[1])["failed_check"] == "bandit"

    audit_text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "function_verification_failed" in audit_text


def test_delete_soft_deletes_function(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/functions",
            headers=_auth(),
            files={"file": ("handler.py", b"def handle(event):\n    return event\n", "text/x-python")},
        ).json()
        delete_response = client.delete(f"/functions/{created['function_id']}", headers=_auth())
        listed = client.get("/functions", headers=_auth())

    assert delete_response.status_code == 204
    assert listed.json() == []


def test_invoke_url_is_placeholder_not_execution(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/functions",
            headers=_auth(),
            files={"file": ("handler.py", b"def handle(event):\n    return event\n", "text/x-python")},
        ).json()
        response = client.post(f"/run/{created['function_id']}", headers=_auth())

    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"]
