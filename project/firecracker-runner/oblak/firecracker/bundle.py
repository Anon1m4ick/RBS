"""Bundle validation and function payload preparation."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


MAX_BUNDLE_BYTES = 25 * 1024 * 1024
MAX_BUNDLE_FILES = 512


class BundleValidationError(ValueError):
    pass


@dataclass(frozen=True)
class BundleFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class FunctionManifest:
    function_id: str
    request_id: str
    entrypoint: str
    created_at: str
    bundle_sha256: str
    files: list[BundleFile]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_entrypoint(entrypoint: str) -> tuple[str, str]:
    if ":" not in entrypoint:
        raise BundleValidationError("Entrypoint must use module.py:function format.")
    module_path, function_name = entrypoint.split(":", 1)
    if not module_path.endswith(".py"):
        raise BundleValidationError("Entrypoint module must be a .py file.")
    if module_path.startswith("/") or ".." in Path(module_path).parts:
        raise BundleValidationError("Entrypoint module must stay inside the bundle.")
    if not function_name.isidentifier():
        raise BundleValidationError("Entrypoint function must be a valid Python identifier.")
    return module_path, function_name


def validate_bundle(bundle_dir: str | Path, entrypoint: str) -> list[BundleFile]:
    root = Path(bundle_dir)
    if not root.is_dir():
        raise BundleValidationError(f"Bundle directory does not exist: {root}")

    module_path, _ = validate_entrypoint(entrypoint)
    root_resolved = root.resolve()
    files: list[BundleFile] = []
    total_size = 0

    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise BundleValidationError(f"Symlinks are not allowed in function bundles: {path}")
        if not path.is_file():
            continue

        resolved = path.resolve()
        try:
            rel = resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise BundleValidationError(f"Bundle file escapes root directory: {path}") from exc

        rel_posix = rel.as_posix()
        if rel_posix.startswith("/") or ".." in rel.parts or "\x00" in rel_posix:
            raise BundleValidationError(f"Unsafe bundle path: {rel_posix}")

        size = path.stat().st_size
        total_size += size
        if total_size > MAX_BUNDLE_BYTES:
            raise BundleValidationError(f"Bundle is larger than {MAX_BUNDLE_BYTES} bytes.")

        files.append(BundleFile(rel_posix, size, sha256_file(path)))
        if len(files) > MAX_BUNDLE_FILES:
            raise BundleValidationError(f"Bundle contains more than {MAX_BUNDLE_FILES} files.")

    if not any(file.path == module_path for file in files):
        raise BundleValidationError(f"Entrypoint module is missing from bundle: {module_path}")
    return files


def write_bundle_tar(bundle_dir: str | Path, tar_path: str | Path, entrypoint: str) -> list[BundleFile]:
    root = Path(bundle_dir).resolve()
    tar_path = Path(tar_path)
    files = validate_bundle(root, entrypoint)
    tar_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(tar_path, "w") as tar:
        for bundle_file in files:
            source = root / bundle_file.path
            data = source.read_bytes()
            info = tarfile.TarInfo(bundle_file.path)
            info.size = len(data)
            info.mode = 0o444
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            tar.addfile(info, io.BytesIO(data))
    return files


def prepare_function_payload(
    *,
    function_id: str,
    request_id: str,
    bundle_dir: str | Path,
    event: Any,
    entrypoint: str,
    staging_dir: str | Path,
) -> FunctionManifest:
    staging = Path(staging_dir)
    staging.mkdir(parents=True, exist_ok=False)
    os.chmod(staging, 0o700)

    code_tar = staging / "code.tar"
    files = write_bundle_tar(bundle_dir, code_tar, entrypoint)

    with (staging / "event.json").open("w", encoding="utf-8") as event_file:
        json.dump(event, event_file, ensure_ascii=False, sort_keys=True)

    manifest = FunctionManifest(
        function_id=function_id,
        request_id=request_id,
        entrypoint=entrypoint,
        created_at=dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        bundle_sha256=sha256_file(code_tar),
        files=files,
    )
    manifest_dict = asdict(manifest)
    with (staging / "manifest.json").open("w", encoding="utf-8") as manifest_file:
        json.dump(manifest_dict, manifest_file, indent=2, sort_keys=True)
    return manifest


def create_ext4_drive_from_dir(source_dir: str | Path, drive_path: str | Path, size_mib: int) -> None:
    mkfs_ext4 = shutil.which("mkfs.ext4")
    if not mkfs_ext4:
        raise RuntimeError("mkfs.ext4 is required to build the function drive image.")
    if size_mib < 8:
        raise RuntimeError("Function drive size must be at least 8 MiB.")

    drive = Path(drive_path)
    drive.parent.mkdir(parents=True, exist_ok=True)
    with drive.open("wb") as drive_file:
        drive_file.truncate(size_mib * 1024 * 1024)

    subprocess.run(
        [mkfs_ext4, "-q", "-F", "-d", str(source_dir), str(drive)],
        check=True,
        text=True,
        capture_output=True,
    )

