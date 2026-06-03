from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from verifier.models import VerificationResult

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

SYSTEM_PROMPT = """\
You are a security code reviewer for a serverless Python platform.
Analyze the provided Python code and determine whether it is safe to execute
in a sandboxed environment.

Flag the code as UNSAFE if it attempts to:
- Delete or overwrite system files (e.g. rm -rf /, shutil.rmtree on /etc)
- Make external network connections (sockets, urllib, requests to external hosts)
- Fork-bomb or exhaust system resources (unbounded os.fork loops)
- Exfiltrate environment variables or secrets
- Bypass or escape the sandbox

Respond ONLY with valid JSON in one of these two forms:
{"safe": true}
{"safe": false, "reason": "brief explanation"}

Do not include any text outside the JSON object.\
"""


def run_llm(file_path: Path) -> VerificationResult:
    """Run LLM-based security analysis via the Google Gemini API."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return VerificationResult(
            ok=False,
            failed_check="llm",
            reason="GEMINI_API_KEY environment variable is not set",
        )

    code = file_path.read_text(encoding="utf-8")

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        "Review the following Python code for safety:\n\n"
        f"```python\n{code}\n```"
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(
            GEMINI_API_URL,
            params={"key": api_key},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError, TypeError) as exc:
        return VerificationResult(
            ok=False,
            failed_check="llm",
            reason=f"LLM API call failed: {exc}",
        )

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return VerificationResult(
            ok=False,
            failed_check="llm",
            reason="could not parse LLM response — treating as unsafe",
        )

    if not isinstance(parsed, dict) or "safe" not in parsed:
        return VerificationResult(
            ok=False,
            failed_check="llm",
            reason="could not parse LLM response — treating as unsafe",
        )

    if parsed["safe"] is True:
        return VerificationResult(ok=True)

    reason = parsed.get("reason", "code flagged as unsafe by LLM analysis")
    return VerificationResult(
        ok=False,
        failed_check="llm",
        reason=reason,
    )
