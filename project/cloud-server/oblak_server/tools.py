from __future__ import annotations

import shutil
# subprocess is used only for the fixed ClamAV maintenance command.
import subprocess  # nosec B404


TOOLS = ("bandit", "clamscan", "freshclam")


def tool_status() -> dict[str, bool]:
    return {tool: shutil.which(tool) is not None for tool in TOOLS}


def run_freshclam(timeout_seconds: int) -> tuple[bool, str]:
    freshclam = shutil.which("freshclam")
    if freshclam is None:
        return False, "freshclam is not installed or not found on PATH"

    try:
        proc = subprocess.run(
            [freshclam],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )  # nosec B603
    except subprocess.TimeoutExpired:
        return False, f"freshclam timed out after {timeout_seconds} seconds"

    output = (proc.stdout.strip() or proc.stderr.strip()).strip()
    if proc.returncode == 0:
        return True, output
    return False, output or f"freshclam failed with exit code {proc.returncode}"
