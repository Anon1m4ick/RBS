from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path("oblak_cloud.sqlite3")
    audit_log_path: Path = Path("oblak-cloud-audit.log")
    public_base_url: str = "http://localhost:8000"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    bootstrap_username: str | None = None
    bootstrap_token: str | None = None
    max_code_bytes: int = 512 * 1024
    max_requirements_bytes: int = 128 * 1024
    run_freshclam_on_startup: bool = False
    freshclam_timeout_seconds: int = 120
    runtime_backend: str = "disabled"
    firecracker_dry_run: bool = False
    firecracker_bin: Path = Path("firecracker")
    firecracker_kernel_image: Path = Path("/var/lib/oblak/firecracker/vmlinux")
    firecracker_rootfs_image: Path = Path("/var/lib/oblak/firecracker/rootfs.ext4")
    firecracker_work_dir: Path = Path(".oblak/firecracker-runs")
    firecracker_audit_log_path: Path = Path(".oblak/audit/firecracker.jsonl")
    firecracker_vcpu_count: int = 1
    firecracker_memory_mib: int = 128
    firecracker_timeout_seconds: int = 10
    firecracker_function_drive_size_mib: int = 64


def load_settings() -> Settings:
    return Settings(
        database_path=Path(os.environ.get("OBLAK_DATABASE_PATH", "oblak_cloud.sqlite3")),
        audit_log_path=Path(os.environ.get("OBLAK_AUDIT_LOG_PATH", "oblak-cloud-audit.log")),
        public_base_url=os.environ.get("OBLAK_PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"),
        bind_host=os.environ.get("OBLAK_BIND_HOST", "127.0.0.1"),
        bind_port=int(os.environ.get("OBLAK_BIND_PORT", "8000")),
        bootstrap_username=os.environ.get("OBLAK_BOOTSTRAP_USERNAME"),
        bootstrap_token=os.environ.get("OBLAK_BOOTSTRAP_TOKEN"),
        max_code_bytes=int(os.environ.get("OBLAK_MAX_CODE_BYTES", str(512 * 1024))),
        max_requirements_bytes=int(os.environ.get("OBLAK_MAX_REQUIREMENTS_BYTES", str(128 * 1024))),
        run_freshclam_on_startup=_bool_env("OBLAK_RUN_FRESHCLAM_ON_STARTUP"),
        freshclam_timeout_seconds=int(os.environ.get("OBLAK_FRESHCLAM_TIMEOUT_SECONDS", "120")),
        runtime_backend=os.environ.get("OBLAK_RUNTIME_BACKEND", "disabled").strip().lower(),
        firecracker_dry_run=_bool_env("OBLAK_FIRECRACKER_DRY_RUN"),
        firecracker_bin=Path(os.environ.get("OBLAK_FIRECRACKER_BIN", "firecracker")),
        firecracker_kernel_image=Path(
            os.environ.get("OBLAK_FIRECRACKER_KERNEL", "/var/lib/oblak/firecracker/vmlinux")
        ),
        firecracker_rootfs_image=Path(
            os.environ.get("OBLAK_FIRECRACKER_ROOTFS", "/var/lib/oblak/firecracker/rootfs.ext4")
        ),
        firecracker_work_dir=Path(os.environ.get("OBLAK_FIRECRACKER_WORK_DIR", ".oblak/firecracker-runs")),
        firecracker_audit_log_path=Path(
            os.environ.get("OBLAK_FIRECRACKER_AUDIT_LOG_PATH", ".oblak/audit/firecracker.jsonl")
        ),
        firecracker_vcpu_count=int(os.environ.get("OBLAK_FIRECRACKER_VCPU_COUNT", "1")),
        firecracker_memory_mib=int(os.environ.get("OBLAK_FIRECRACKER_MEMORY_MIB", "128")),
        firecracker_timeout_seconds=int(os.environ.get("OBLAK_FIRECRACKER_TIMEOUT_SECONDS", "10")),
        firecracker_function_drive_size_mib=int(
            os.environ.get("OBLAK_FIRECRACKER_FUNCTION_DRIVE_SIZE_MIB", "64")
        ),
    )
