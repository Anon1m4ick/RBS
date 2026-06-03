from __future__ import annotations

from pathlib import Path


def run_clamav(file_path: Path) -> tuple[bool, str]:
    """Run ClamAV scan on a file.

    TODO: Wire in ClamAV by calling a subprocess such as:
        subprocess.run(
            ["clamscan", "--no-summary", str(file_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    Return (False, "virus found: <name>") when the exit code indicates infection,
    otherwise (True, "").
    """
    return True, ""
