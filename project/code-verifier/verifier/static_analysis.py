from __future__ import annotations

import json
import subprocess
from pathlib import Path

from verifier.models import VerificationResult

BLOCKING_SEVERITIES = {"MEDIUM", "HIGH"}


def run_bandit(file_path: Path) -> VerificationResult:
    """Run bandit static analysis on a Python file via subprocess."""
    try:
        proc = subprocess.run(
            ["bandit", "-r", str(file_path), "-f", "json", "--quiet"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return VerificationResult(
            ok=False,
            failed_check="bandit",
            reason="bandit is not installed or not found on PATH",
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return VerificationResult(
            ok=False,
            failed_check="bandit",
            reason="bandit returned unparseable output",
        )

    blocking = [
        issue
        for issue in data.get("results", [])
        if issue.get("issue_severity") in BLOCKING_SEVERITIES
    ]

    if not blocking:
        return VerificationResult(ok=True)

    parts = []
    for issue in blocking:
        parts.append(
            f"[{issue.get('test_id', 'unknown')}] "
            f"{issue.get('issue_severity', 'UNKNOWN')} "
            f"line {issue.get('line_number', '?')}: "
            f"{issue.get('issue_text', 'no description')}"
        )

    return VerificationResult(
        ok=False,
        failed_check="bandit",
        reason="; ".join(parts),
    )
