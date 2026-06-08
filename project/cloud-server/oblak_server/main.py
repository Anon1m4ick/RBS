from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path, PurePath
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response

from oblak_server.audit import record_audit
from oblak_server.config import Settings, load_settings
from oblak_server.database import connect, find_user_by_token_hash, init_db, utc_now
from oblak_server.security import hash_token
from oblak_server.tools import run_freshclam, tool_status


def run_code_verifier(file_path: Path) -> dict[str, Any]:
    from verifier.main import verify

    return verify(file_path)


def run_requirements_antivirus(file_path: Path) -> tuple[bool, str]:
    from verifier.antivirus import run_clamav

    return run_clamav(file_path)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _request_id(request: Request) -> str:
    request_id = request.headers.get("X-Request-ID")
    if request_id:
        return request_id
    return str(uuid.uuid4())


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
    return token.strip()


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = _settings(request)
    request_id = _request_id(request)
    try:
        token = _extract_bearer(authorization)
    except HTTPException as exc:
        with connect(settings) as conn:
            record_audit(
                conn,
                settings,
                "auth_failed",
                outcome="failure",
                request_id=request_id,
                ip=_client_ip(request),
                details={"reason": exc.detail},
            )
            conn.commit()
        raise

    with connect(settings) as conn:
        user = find_user_by_token_hash(conn, hash_token(token))
        if not user:
            record_audit(
                conn,
                settings,
                "auth_failed",
                outcome="failure",
                request_id=request_id,
                ip=_client_ip(request),
                details={"reason": "unknown token"},
            )
            conn.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")
        return dict(user)


async def _read_limited(upload: UploadFile, max_bytes: int, label: str) -> bytes:
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{label} exceeds maximum size of {max_bytes} bytes",
        )
    return content


def _safe_filename(filename: str | None, *, expected_suffix: str) -> str:
    name = PurePath(filename or "").name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Missing upload filename")
    if name != filename and filename:
        raise HTTPException(status_code=400, detail="Upload filename must not include path components")
    if not name.endswith(expected_suffix):
        raise HTTPException(status_code=400, detail=f"Upload filename must end with {expected_suffix}")
    return name


def _invoke_url(settings: Settings, function_id: str) -> str:
    return f"{settings.public_base_url}/run/{function_id}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    init_db(settings)
    if settings.run_freshclam_on_startup:
        ok, message = run_freshclam(settings.freshclam_timeout_seconds)
        with connect(settings) as conn:
            record_audit(
                conn,
                settings,
                "freshclam_startup",
                outcome="success" if ok else "failure",
                details={"message": message},
            )
            conn.commit()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Oblak Cloud Server", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or load_settings()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "tools": tool_status()}

    @app.get("/auth/me")
    def auth_me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
        return {"id": user["id"], "username": user["username"]}

    @app.post("/auth/login")
    def auth_login(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
        return {"id": user["id"], "username": user["username"]}

    @app.post("/admin/antivirus/refresh")
    def refresh_antivirus(
        request: Request,
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        settings = _settings(request)
        request_id = _request_id(request)
        ok, message = run_freshclam(settings.freshclam_timeout_seconds)
        with connect(settings) as conn:
            record_audit(
                conn,
                settings,
                "freshclam_manual",
                outcome="success" if ok else "failure",
                actor_user_id=user["id"],
                request_id=request_id,
                ip=_client_ip(request),
                details={"message": message},
            )
            conn.commit()
        if not ok:
            raise HTTPException(status_code=500, detail=message)
        return {"ok": True, "message": message}

    @app.post("/functions", status_code=201)
    async def upload_function(
        request: Request,
        file: UploadFile = File(...),
        requirements: UploadFile | None = File(default=None),
        user: dict[str, Any] = Depends(get_current_user),
    ) -> Response:
        settings = _settings(request)
        request_id = _request_id(request)
        filename = _safe_filename(file.filename, expected_suffix=".py")
        code = await _read_limited(file, settings.max_code_bytes, "Python file")

        requirements_content: bytes | None = None
        if requirements is not None:
            requirements_name = _safe_filename(requirements.filename, expected_suffix=".txt")
            if requirements_name != "requirements.txt":
                raise HTTPException(status_code=400, detail="Requirements upload must be named requirements.txt")
            requirements_content = await _read_limited(
                requirements,
                settings.max_requirements_bytes,
                "requirements.txt",
            )

        function_id = str(uuid.uuid4())
        now = utc_now()
        code_sha256 = hashlib.sha256(code).hexdigest()
        requirements_sha256 = (
            hashlib.sha256(requirements_content).hexdigest() if requirements_content is not None else None
        )

        with connect(settings) as conn:
            conn.execute(
                """
                INSERT INTO functions (
                    id, user_id, name, code, requirements, code_sha256,
                    requirements_sha256, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'UPLOADED', ?, ?)
                """,
                (
                    function_id,
                    user["id"],
                    filename,
                    code,
                    requirements_content,
                    code_sha256,
                    requirements_sha256,
                    now,
                    now,
                ),
            )
            record_audit(
                conn,
                settings,
                "function_upload_received",
                outcome="success",
                actor_user_id=user["id"],
                function_id=function_id,
                request_id=request_id,
                ip=_client_ip(request),
                details={
                    "name": filename,
                    "code_sha256": code_sha256,
                    "requirements_sha256": requirements_sha256,
                },
            )
            conn.commit()

        with tempfile.TemporaryDirectory(prefix="oblak-upload-") as tmp:
            tmp_path = Path(tmp)
            code_path = tmp_path / filename
            code_path.write_bytes(code)
            verification = run_code_verifier(code_path)

            if verification.get("ok") and requirements_content is not None:
                requirements_path = tmp_path / "requirements.txt"
                requirements_path.write_bytes(requirements_content)
                av_ok, av_reason = run_requirements_antivirus(requirements_path)
                if not av_ok:
                    verification = {
                        "ok": False,
                        "failed_check": "requirements_antivirus",
                        "reason": av_reason,
                    }

        if not verification.get("ok"):
            with connect(settings) as conn:
                conn.execute(
                    """
                    UPDATE functions
                    SET status = 'REJECTED', verification_result = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (json.dumps(verification, sort_keys=True), utc_now(), function_id),
                )
                record_audit(
                    conn,
                    settings,
                    "function_verification_failed",
                    outcome="failure",
                    actor_user_id=user["id"],
                    function_id=function_id,
                    request_id=request_id,
                    ip=_client_ip(request),
                    details=verification,
                )
                conn.commit()
            reason = verification.get("reason", "verification failed")
            failed_check = verification.get("failed_check", "unknown")
            raise HTTPException(status_code=400, detail=f"Verification failed ({failed_check}): {reason}")

        invoke_url = _invoke_url(settings, function_id)
        with connect(settings) as conn:
            conn.execute(
                """
                UPDATE functions
                SET status = 'VERIFIED', verification_result = ?, invoke_url = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(verification, sort_keys=True), invoke_url, utc_now(), function_id),
            )
            record_audit(
                conn,
                settings,
                "function_deployed",
                outcome="success",
                actor_user_id=user["id"],
                function_id=function_id,
                request_id=request_id,
                ip=_client_ip(request),
                details={"invoke_url": invoke_url, "code_sha256": code_sha256},
            )
            conn.commit()

        return JSONResponse(
            status_code=201,
            content={
                "function_id": function_id,
                "id": function_id,
                "name": filename,
                "status": "VERIFIED",
                "invoke_url": invoke_url,
            },
        )

    @app.get("/functions")
    def list_functions(user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
        settings = app.state.settings
        with connect(settings) as conn:
            rows = conn.execute(
                """
                SELECT id, name, status, invoke_url, code_sha256, requirements_sha256, created_at, updated_at
                FROM functions
                WHERE user_id = ? AND deleted_at IS NULL
                ORDER BY created_at DESC
                """,
                (user["id"],),
            ).fetchall()
        return [dict(row) for row in rows]

    @app.delete("/functions/{function_id}", status_code=204)
    def delete_function(
        function_id: str,
        request: Request,
        user: dict[str, Any] = Depends(get_current_user),
    ) -> JSONResponse:
        settings = _settings(request)
        request_id = _request_id(request)
        with connect(settings) as conn:
            row = conn.execute(
                """
                SELECT id FROM functions
                WHERE id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                (function_id, user["id"]),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Function not found")
            now = utc_now()
            conn.execute(
                """
                UPDATE functions
                SET status = 'DELETED', deleted_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, function_id),
            )
            record_audit(
                conn,
                settings,
                "function_deleted",
                outcome="success",
                actor_user_id=user["id"],
                function_id=function_id,
                request_id=request_id,
                ip=_client_ip(request),
            )
            conn.commit()
        return Response(status_code=204)

    @app.post("/run/{function_id}")
    def invoke_placeholder(
        function_id: str,
        request: Request,
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, str]:
        settings = _settings(request)
        request_id = _request_id(request)
        with connect(settings) as conn:
            row = conn.execute(
                """
                SELECT id, status FROM functions
                WHERE id = ? AND deleted_at IS NULL
                """,
                (function_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Function not found")
            record_audit(
                conn,
                settings,
                "function_invoke_requested",
                outcome="not_implemented",
                actor_user_id=user["id"],
                function_id=function_id,
                request_id=request_id,
                ip=_client_ip(request),
                details={"status": row["status"]},
            )
            conn.commit()
        raise HTTPException(
            status_code=501,
            detail="Function execution is handled by the Firecracker runner stage and is not implemented here",
        )

    return app


app = create_app()


def run() -> None:
    settings = load_settings()
    uvicorn.run("oblak_server.main:app", host=settings.bind_host, port=settings.bind_port, reload=False)
