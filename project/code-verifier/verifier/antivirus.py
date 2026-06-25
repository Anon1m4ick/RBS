from __future__ import annotations

import subprocess
from pathlib import Path


def run_clamav(file_path: Path) -> tuple[bool, str]:
    """Run ClamAV scan on a file via subprocess."""
    try:
        proc = subprocess.run(
            ["clamscan", "--no-summary", str(file_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, "clamscan is not installed or not found on PATH"

    if proc.returncode == 0:
        return True, ""

    if proc.returncode == 1:
        detail = proc.stdout.strip() or "malware detected"
        return False, f"virus found: {detail}"

    detail = proc.stderr.strip() or proc.stdout.strip() or "clamscan failed"
    return False, f"antivirus scan error: {detail}"
