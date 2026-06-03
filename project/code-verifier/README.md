# Oblak Code Verifier

Security verification library for the Oblak serverless platform. Analyzes uploaded Python code for safety using static analysis (Bandit) and LLM review (Google Gemini).

## Installation

```bash
cd code-verifier
pip install -e ".[dev]"
```

This installs the `verifier` package and the `bandit` CLI on your PATH.

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
3. **Antivirus** — stub (always passes; ClamAV wiring left as TODO)

After each `verify()` call, an audit line is appended to `oblak-verifier.log` in the current working directory.

## Running Tests

```bash
cd code-verifier
pytest
```

Tests that require Bandit will be skipped automatically if the `bandit` binary is not on PATH.

## Assumptions

- **Python 3.11+** is the target runtime.
- **Bandit** is invoked as a subprocess (`bandit` on PATH); uploaded code is never executed.
- **LLM** calls `gemini-2.5-flash` via `requests` (no Gemini SDK); endpoint is `generativelanguage.googleapis.com/v1beta`.
- **Missing `GEMINI_API_KEY`** causes the LLM check to fail closed with an error result.
- **Antivirus** is a no-op stub; production wiring would call `clamscan`/`clamdscan` via subprocess.
- **Audit log** is written to `oblak-verifier.log` in the process working directory (not configurable).
- **Server integration**: the API server imports `verify` and returns HTTP 400 with `result["reason"]` on failure.
