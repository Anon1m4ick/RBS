"""Command-line entrypoint for the Firecracker stage."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .config import FirecrackerConfig
from .executor import ExecutionRequest, FirecrackerExecutor


def _load_event(args: argparse.Namespace) -> Any:
    if args.event_file:
        return json.loads(Path(args.event_file).read_text(encoding="utf-8"))
    return json.loads(args.event)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Oblak function invocation in Firecracker.")
    parser.add_argument("--bundle", required=True, type=Path, help="Directory with handler.py and optional files.")
    parser.add_argument("--function-id", default=None, help="Logical function id for audit logs.")
    parser.add_argument("--entrypoint", default="handler.py:handle", help="Entrypoint in module.py:function format.")
    parser.add_argument("--event", default="{}", help="JSON event payload.")
    parser.add_argument("--event-file", type=Path, help="Read JSON event payload from a file.")
    parser.add_argument("--dry-run", action="store_true", help="Prepare payload and audit logs without starting KVM.")
    parser.add_argument("--work-dir", type=Path, default=Path(".oblak/firecracker-runs"))
    parser.add_argument("--audit-log", type=Path, default=Path(".oblak/audit/firecracker.jsonl"))
    parser.add_argument(
        "--firecracker-bin",
        type=Path,
        default=Path(os.environ.get("OBLAK_FIRECRACKER_BIN", "firecracker")),
    )
    parser.add_argument(
        "--kernel",
        type=Path,
        default=Path(os.environ.get("OBLAK_FIRECRACKER_KERNEL", "/var/lib/oblak/firecracker/vmlinux")),
    )
    parser.add_argument(
        "--rootfs",
        type=Path,
        default=Path(os.environ.get("OBLAK_FIRECRACKER_ROOTFS", "/var/lib/oblak/firecracker/rootfs.ext4")),
    )
    parser.add_argument("--vcpu", type=int, default=1)
    parser.add_argument("--memory-mib", type=int, default=128)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--function-drive-size-mib", type=int, default=64)
    parser.add_argument("--enable-network", action="store_true", help="Attach a pre-created TAP device.")
    parser.add_argument("--tap-dev", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = FirecrackerConfig(
        firecracker_bin=args.firecracker_bin,
        kernel_image=args.kernel,
        rootfs_image=args.rootfs,
        work_dir=args.work_dir,
        audit_log=args.audit_log,
        vcpu_count=args.vcpu,
        mem_size_mib=args.memory_mib,
        timeout_seconds=args.timeout,
        function_drive_size_mib=args.function_drive_size_mib,
        enable_network=args.enable_network,
        tap_dev=args.tap_dev,
    )
    request = ExecutionRequest(
        function_id=args.function_id or args.bundle.name,
        bundle_dir=args.bundle,
        event=_load_event(args),
        entrypoint=args.entrypoint,
    )
    result = FirecrackerExecutor(config).run(request, dry_run=args.dry_run)
    print(json.dumps(result.to_json_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

