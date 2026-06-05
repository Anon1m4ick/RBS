# Oblak Code Verifier

Security verification library for the Oblak serverless platform. Analyzes uploaded Python code for safety using static analysis (Bandit), LLM review (Google Gemini), and ClamAV antivirus scanning.

## Installation

```bash
cd code-verifier
pip install -e ".[dev]"
```

This installs the `verifier` package and the `bandit` CLI on your PATH.

**ClamAV** (`clamscan`) must be installed separately on the host and virus definitions
updated via `freshclam` (see [ClamAV docs](https://docs.clamav.net/)).

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes (for LLM check) | API key for Google Gemini. If unset, the LLM check fails closed (unsafe). |

## Usage

```python
from pathlib import Path
from verifier.main import verify

result = verify(Path("/tmp/uploads/abc123/function.py"))
if not result["ok"]:
    print(f"Failed {result['failed_check']}: {result['reason']}")
else:
    print("Code is safe to deploy")
```

### Checks (in order)

1. **Bandit** — static analysis; blocks MEDIUM and HIGH severity issues
2. **LLM** — Gemini 2.5 Flash reviews code for malicious patterns via the Google Generative Language API
3. **Antivirus** — ClamAV (`clamscan` subprocess); blocks files with known malware signatures

After each `verify()` call, an audit line is appended to `oblak-verifier.log` in the current working directory.

## Running Tests

```bash
cd code-verifier
pytest
```

Tests that require Bandit or ClamAV are skipped automatically when the corresponding binary is not on PATH.

## Assumptions

- **Python 3.11+** is the target runtime.
- **Bandit** is invoked as a subprocess (`bandit` on PATH); uploaded code is never executed.
- **LLM** calls `gemini-2.5-flash` via `requests` (no Gemini SDK); endpoint is `generativelanguage.googleapis.com/v1beta`.
- **Missing `GEMINI_API_KEY`** causes the LLM check to fail closed with an error result.
- **Antivirus** invokes `clamscan` as a subprocess; exit code 1 means infection found, 2 means scan error. If `clamscan` is missing, the check fails closed.
- **Audit log** is written to `oblak-verifier.log` in the process working directory (not configurable).
- **Server integration**: the API server imports `verify` and returns HTTP 400 with `result["reason"]` on failure.
