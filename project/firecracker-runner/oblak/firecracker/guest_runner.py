"""Guest-side function runner intended to run inside the Firecracker rootfs."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pwd
import resource
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any


RESULT_BEGIN = "OBLAK_RESULT_BEGIN"
RESULT_END = "OBLAK_RESULT_END"
DEFAULT_FUNCTION_DEVICE = "/dev/vdb"
DEFAULT_MOUNT_DIR = "/mnt/oblak/function"


class GuestRunnerError(RuntimeError):
    pass


def emit_result(payload: dict[str, Any]) -> None:
    print(RESULT_BEGIN, flush=True)
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False), flush=True)
    print(RESULT_END, flush=True)


def mount_function_drive(device: str, mount_dir: str) -> Path:
    mount_path = Path(mount_dir)
    mount_path.mkdir(parents=True, exist_ok=True)
    if not any(line.split()[1] == str(mount_path) for line in Path("/proc/mounts").read_text().splitlines()):
        subprocess.run(["mount", "-o", "ro,nosuid,nodev,noexec", device, str(mount_path)], check=True)
    return mount_path


def safe_extract_tar(tar_path: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(tar_path, "r") as tar:
        for member in tar.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise GuestRunnerError(f"Unsafe tar member path: {member.name}")
            if member.issym() or member.islnk() or member.isdev():
                raise GuestRunnerError(f"Unsafe tar member type: {member.name}")
            target = (root / member.name).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise GuestRunnerError(f"Tar member escapes destination: {member.name}") from exc
        tar.extractall(root)


def make_code_tree_read_only(code_dir: Path) -> None:
    for path in code_dir.rglob("*"):
        if path.is_dir():
            os.chmod(path, 0o555)
        elif path.is_file():
            os.chmod(path, 0o444)
        else:
            raise GuestRunnerError(f"Unsupported extracted path type: {path}")
    os.chmod(code_dir, 0o555)


def parse_entrypoint(entrypoint: str) -> tuple[str, str]:
    if ":" not in entrypoint:
        raise GuestRunnerError("Entrypoint must use module.py:function format.")
    module_path, function_name = entrypoint.split(":", 1)
    if not module_path.endswith(".py") or Path(module_path).is_absolute() or ".." in Path(module_path).parts:
        raise GuestRunnerError("Entrypoint module path is unsafe.")
    if not function_name.isidentifier():
        raise GuestRunnerError("Entrypoint function is not a valid identifier.")
    return module_path, function_name


def apply_resource_limits(cpu_seconds: int, memory_mib: int) -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (memory_mib * 1024 * 1024, memory_mib * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    if hasattr(resource, "RLIMIT_NPROC"):
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))


def drop_to_nobody() -> None:
    if os.getuid() != 0:
        return
    try:
        user = pwd.getpwnam("nobody")
        uid = user.pw_uid
        gid = user.pw_gid
    except KeyError:
        uid = 65534
        gid = 65534
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)


def load_handler(code_dir: Path, entrypoint: str) -> Any:
    module_path, function_name = parse_entrypoint(entrypoint)
    module_file = code_dir / module_path
    if not module_file.is_file():
        raise GuestRunnerError(f"Entrypoint module does not exist: {module_path}")

    sys.path.insert(0, str(code_dir))
    spec = importlib.util.spec_from_file_location("oblak_user_handler", module_file)
    if spec is None or spec.loader is None:
        raise GuestRunnerError(f"Cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = getattr(module, function_name, None)
    if not callable(handler):
        raise GuestRunnerError(f"Entrypoint is not callable: {entrypoint}")
    return handler


def run_function(function_mount: Path, cpu_seconds: int, memory_mib: int) -> dict[str, Any]:
    manifest = json.loads((function_mount / "manifest.json").read_text(encoding="utf-8"))
    event = json.loads((function_mount / "event.json").read_text(encoding="utf-8"))

    work_dir = Path(tempfile.mkdtemp(prefix="oblak-function-"))
    code_dir = work_dir / "code"
    code_dir.mkdir(mode=0o700)
    try:
        safe_extract_tar(function_mount / "code.tar", code_dir)
        make_code_tree_read_only(code_dir)
        os.chdir(code_dir)
        apply_resource_limits(cpu_seconds, memory_mib)
        drop_to_nobody()

        started = time.monotonic()
        handler = load_handler(code_dir, manifest["entrypoint"])
        context = {
            "function_id": manifest["function_id"],
            "request_id": manifest["request_id"],
            "deadline_ms": int((started + cpu_seconds) * 1000),
        }
        value = handler(event, context)
        return {
            "status": "ok",
            "request_id": manifest["request_id"],
            "duration_ms": int((time.monotonic() - started) * 1000),
            "return": value,
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an Oblak function inside the Firecracker guest.")
    parser.add_argument("--device", default=DEFAULT_FUNCTION_DEVICE)
    parser.add_argument("--mount-dir", default=DEFAULT_MOUNT_DIR)
    parser.add_argument("--cpu-seconds", type=int, default=5)
    parser.add_argument("--memory-mib", type=int, default=96)
    parser.add_argument("--no-poweroff", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        function_mount = mount_function_drive(args.device, args.mount_dir)
        emit_result(run_function(function_mount, args.cpu_seconds, args.memory_mib))
        return_code = 0
    except Exception as exc:
        emit_result(
            {
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=5),
            }
        )
        return_code = 1
    finally:
        if not args.no_poweroff:
            subprocess.run(["poweroff", "-f"], check=False)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
