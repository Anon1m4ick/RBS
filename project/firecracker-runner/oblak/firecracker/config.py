"""Configuration and host checks for the Firecracker stage."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BOOT_ARGS = (
    "console=ttyS0 reboot=k panic=1 pci=off random.trust_cpu=on "
    "quiet systemd.unit=oblak-function.service"
)


@dataclass(frozen=True)
class FirecrackerConfig:
    firecracker_bin: Path = Path("firecracker")
    kernel_image: Path = Path("/var/lib/oblak/firecracker/vmlinux")
    rootfs_image: Path = Path("/var/lib/oblak/firecracker/rootfs.ext4")
    work_dir: Path = Path(".oblak/firecracker-runs")
    audit_log: Path = Path(".oblak/audit/firecracker.jsonl")
    boot_args: str = DEFAULT_BOOT_ARGS
    vcpu_count: int = 1
    mem_size_mib: int = 128
    timeout_seconds: int = 10
    function_drive_size_mib: int = 64
    rootfs_read_only: bool = True
    enable_network: bool = False
    tap_dev: str | None = None
    guest_mac: str = "06:00:AC:10:00:02"

    def resolved_firecracker_bin(self) -> Path:
        candidate = str(self.firecracker_bin)
        found = shutil.which(candidate)
        return Path(found) if found else self.firecracker_bin

    def validate_for_real_run(self) -> None:
        errors: list[str] = []
        if platform.system() != "Linux":
            errors.append("Firecracker requires Linux with KVM; use --dry-run on this host.")

        kvm = Path("/dev/kvm")
        if not os.access(kvm, os.R_OK | os.W_OK):
            errors.append("Current user must have read/write access to /dev/kvm.")

        firecracker_bin = self.resolved_firecracker_bin()
        if not firecracker_bin.exists():
            errors.append(f"Firecracker binary not found: {self.firecracker_bin}")
        elif not os.access(firecracker_bin, os.X_OK):
            errors.append(f"Firecracker binary is not executable: {firecracker_bin}")

        if not self.kernel_image.is_file():
            errors.append(f"Kernel image not found: {self.kernel_image}")
        if not self.rootfs_image.is_file():
            errors.append(f"Rootfs image not found: {self.rootfs_image}")

        if self.vcpu_count < 1:
            errors.append("vcpu_count must be at least 1.")
        if self.mem_size_mib < 64:
            errors.append("mem_size_mib must be at least 64.")
        if self.timeout_seconds < 1:
            errors.append("timeout_seconds must be at least 1.")
        if self.enable_network and not self.tap_dev:
            errors.append("tap_dev is required when enable_network=True.")

        if errors:
            raise RuntimeError("Invalid Firecracker configuration:\n- " + "\n- ".join(errors))

