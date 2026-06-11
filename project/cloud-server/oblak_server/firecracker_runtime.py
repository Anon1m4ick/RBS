from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from oblak_server.config import Settings


def run_firecracker_function(
    *,
    settings: Settings,
    function_id: str,
    request_id: str,
    filename: str,
    code: bytes,
    requirements: bytes | None,
    event: Any,
) -> dict[str, Any]:
    from oblak.firecracker.config import FirecrackerConfig
    from oblak.firecracker.executor import ExecutionRequest, FirecrackerExecutor

    with tempfile.TemporaryDirectory(prefix="oblak-firecracker-bundle-") as tmp:
        bundle_dir = Path(tmp)
        (bundle_dir / filename).write_bytes(code)
        if requirements is not None:
            (bundle_dir / "requirements.txt").write_bytes(requirements)

        config = FirecrackerConfig(
            firecracker_bin=settings.firecracker_bin,
            kernel_image=settings.firecracker_kernel_image,
            rootfs_image=settings.firecracker_rootfs_image,
            work_dir=settings.firecracker_work_dir,
            audit_log=settings.firecracker_audit_log_path,
            vcpu_count=settings.firecracker_vcpu_count,
            mem_size_mib=settings.firecracker_memory_mib,
            timeout_seconds=settings.firecracker_timeout_seconds,
            function_drive_size_mib=settings.firecracker_function_drive_size_mib,
        )
        request = ExecutionRequest(
            function_id=function_id,
            request_id=request_id,
            bundle_dir=bundle_dir,
            event=event,
            entrypoint=f"{filename}:handle",
        )
        result = FirecrackerExecutor(config).run(request, dry_run=settings.firecracker_dry_run)
        return result.to_json_dict()
