"""Host-side Firecracker executor for one Oblak function invocation."""

from __future__ import annotations

import datetime as dt
import json
import os
import signal
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .api import FirecrackerAPI
from .audit import AuditLog
from .bundle import create_ext4_drive_from_dir, prepare_function_payload
from .config import FirecrackerConfig


RESULT_BEGIN = "OBLAK_RESULT_BEGIN"
RESULT_END = "OBLAK_RESULT_END"


@dataclass(frozen=True)
class ExecutionRequest:
    function_id: str
    bundle_dir: Path
    event: Any
    entrypoint: str = "handler.py:handle"
    request_id: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    request_id: str
    run_dir: Path
    duration_ms: int
    exit_code: int | None
    timed_out: bool
    result: Any | None
    console_tail: str

    def to_json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["run_dir"] = str(self.run_dir)
        return data


APIClientFactory = Callable[[Path], FirecrackerAPI]


class FirecrackerExecutor:
    def __init__(self, config: FirecrackerConfig, api_factory: APIClientFactory = FirecrackerAPI):
        self.config = config
        self.api_factory = api_factory

    def run(self, request: ExecutionRequest, *, dry_run: bool = False) -> ExecutionResult:
        request_id = request.request_id or str(uuid.uuid4())
        run_dir = self._new_run_dir(request.function_id, request_id)
        audit = AuditLog(self.config.audit_log)
        start = time.monotonic()
        audit.record(
            "firecracker.prepare.start",
            function_id=request.function_id,
            request_id=request_id,
            run_dir=str(run_dir),
            dry_run=dry_run,
        )

        staging_dir = run_dir / "function-staging"
        manifest = prepare_function_payload(
            function_id=request.function_id,
            request_id=request_id,
            bundle_dir=request.bundle_dir,
            event=request.event,
            entrypoint=request.entrypoint,
            staging_dir=staging_dir,
        )
        audit.record(
            "firecracker.prepare.complete",
            function_id=request.function_id,
            request_id=request_id,
            bundle_sha256=manifest.bundle_sha256,
            file_count=len(manifest.files),
        )

        if dry_run:
            duration_ms = self._elapsed_ms(start)
            audit.record(
                "firecracker.dry_run.complete",
                function_id=request.function_id,
                request_id=request_id,
                duration_ms=duration_ms,
            )
            return ExecutionResult(
                status="DRY_RUN",
                request_id=request_id,
                run_dir=run_dir,
                duration_ms=duration_ms,
                exit_code=None,
                timed_out=False,
                result={"manifest": asdict(manifest), "staging_dir": str(staging_dir)},
                console_tail="",
            )

        self.config.validate_for_real_run()

        function_drive = run_dir / "function.ext4"
        create_ext4_drive_from_dir(staging_dir, function_drive, self.config.function_drive_size_mib)
        audit.record(
            "firecracker.drive.created",
            function_id=request.function_id,
            request_id=request_id,
            drive_path=str(function_drive),
            size_mib=self.config.function_drive_size_mib,
        )

        socket_path = run_dir / "firecracker.socket"
        console_path = run_dir / "console.log"
        vmm_log_path = run_dir / "firecracker.log"
        metrics_path = run_dir / "metrics.ndjson"

        with console_path.open("wb") as console_file:
            process = subprocess.Popen(
                [str(self.config.resolved_firecracker_bin()), "--api-sock", str(socket_path)],
                cwd=run_dir,
                stdin=subprocess.DEVNULL,
                stdout=console_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

        try:
            self._wait_for_socket(socket_path, process)
            api = self.api_factory(socket_path)
            audit.record("firecracker.api.ready", function_id=request.function_id, request_id=request_id)

            api.configure_logger(vmm_log_path)
            api.configure_metrics(metrics_path)
            api.set_machine_config(
                vcpu_count=self.config.vcpu_count,
                mem_size_mib=self.config.mem_size_mib,
                smt=False,
            )
            api.set_boot_source(self.config.kernel_image, self.config.boot_args)
            api.attach_drive(
                "rootfs",
                self.config.rootfs_image,
                is_root_device=True,
                is_read_only=self.config.rootfs_read_only,
            )
            api.attach_drive(
                "function",
                function_drive,
                is_root_device=False,
                is_read_only=True,
            )
            if self.config.enable_network:
                api.attach_network(
                    iface_id="net1",
                    guest_mac=self.config.guest_mac,
                    host_dev_name=self.config.tap_dev or "",
                )
            api.start_instance()
            audit.record("firecracker.vm.started", function_id=request.function_id, request_id=request_id)

            timed_out = False
            try:
                exit_code = process.wait(timeout=self.config.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_code = self._terminate_vm(process)
                audit.record(
                    "firecracker.vm.timeout",
                    function_id=request.function_id,
                    request_id=request_id,
                    timeout_seconds=self.config.timeout_seconds,
                )

            console = self._read_text_tail(console_path)
            parsed_result = parse_guest_result(console)
            duration_ms = self._elapsed_ms(start)
            if timed_out:
                status = "TIMEOUT"
            elif parsed_result and parsed_result.get("status") == "ok":
                status = "SUCCESS"
            elif parsed_result and parsed_result.get("status") == "error":
                status = "FUNCTION_ERROR"
            else:
                status = "FAILED"

            audit.record(
                "firecracker.vm.complete",
                function_id=request.function_id,
                request_id=request_id,
                status=status,
                exit_code=exit_code,
                timed_out=timed_out,
                duration_ms=duration_ms,
            )
            return ExecutionResult(
                status=status,
                request_id=request_id,
                run_dir=run_dir,
                duration_ms=duration_ms,
                exit_code=exit_code,
                timed_out=timed_out,
                result=parsed_result,
                console_tail=console,
            )
        except Exception as exc:
            audit.record(
                "firecracker.vm.failed",
                function_id=request.function_id,
                request_id=request_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            if process.poll() is None:
                self._terminate_vm(process)
            raise

    def _new_run_dir(self, function_id: str, request_id: str) -> Path:
        safe_function_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in function_id)[:80]
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S")
        run_dir = self.config.work_dir / f"{timestamp}-{safe_function_id}-{request_id[:8]}"
        run_dir.mkdir(parents=True, exist_ok=False)
        os.chmod(run_dir, 0o700)
        return run_dir

    @staticmethod
    def _wait_for_socket(socket_path: Path, process: subprocess.Popen[bytes], timeout_seconds: float = 5.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Firecracker exited before API socket was ready: {process.returncode}")
            if socket_path.exists():
                return
            time.sleep(0.05)
        raise TimeoutError(f"Firecracker API socket was not created within {timeout_seconds} seconds.")

    @staticmethod
    def _terminate_vm(process: subprocess.Popen[bytes]) -> int | None:
        if process.poll() is not None:
            return process.returncode
        try:
            os.killpg(process.pid, signal.SIGTERM)
            return process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            return process.wait(timeout=3)

    @staticmethod
    def _read_text_tail(path: Path, max_bytes: int = 64 * 1024) -> str:
        if not path.exists():
            return ""
        size = path.stat().st_size
        with path.open("rb") as file_obj:
            if size > max_bytes:
                file_obj.seek(size - max_bytes)
            return file_obj.read().decode("utf-8", errors="replace")

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int((time.monotonic() - start) * 1000)


def parse_guest_result(console_text: str) -> dict[str, Any] | None:
    begin = console_text.rfind(RESULT_BEGIN)
    end = console_text.rfind(RESULT_END)
    if begin == -1 or end == -1 or end <= begin:
        return None
    payload = console_text[begin + len(RESULT_BEGIN) : end].strip()
    if not payload:
        return None
    return json.loads(payload)
