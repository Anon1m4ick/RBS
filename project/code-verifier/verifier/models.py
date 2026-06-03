from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VerificationResult:
    ok: bool
    failed_check: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict:
        result: dict = {"ok": self.ok}
        if not self.ok:
            result["failed_check"] = self.failed_check
            result["reason"] = self.reason
        return result
