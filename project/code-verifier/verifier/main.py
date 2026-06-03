from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from verifier.antivirus import run_clamav
from verifier.llm_analysis import run_llm
from verifier.models import VerificationResult
from verifier.static_analysis import run_bandit

AUDIT_LOG = "oblak-verifier.log"


def _write_audit_log(file_path: Path, result: VerificationResult) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file": file_path.name,
        "ok": result.ok,
        "failed_check": result.failed_check,
        "reason": result.reason,
    }
    with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def verify(file_path: Path) -> dict:
    """Run all verification checks sequentially; stop on first failure."""
    file_path = Path(file_path)

    bandit_result = run_bandit(file_path)
    if not bandit_result.ok:
        _write_audit_log(file_path, bandit_result)
        return bandit_result.to_dict()

    llm_result = run_llm(file_path)
    if not llm_result.ok:
        _write_audit_log(file_path, llm_result)
        return llm_result.to_dict()

    av_ok, av_reason = run_clamav(file_path)
    if not av_ok:
        av_result = VerificationResult(
            ok=False,
            failed_check="antivirus",
            reason=av_reason,
        )
        _write_audit_log(file_path, av_result)
        return av_result.to_dict()

    success = VerificationResult(ok=True)
    _write_audit_log(file_path, success)
    return success.to_dict()
