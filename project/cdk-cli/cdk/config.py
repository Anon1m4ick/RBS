from __future__ import annotations

import json
import os
from pathlib import Path

SERVER_URL = os.environ.get("OBLAK_SERVER_URL", "http://localhost:8000")

CONFIG_DIR = Path.home() / ".cdk"
CONFIG_FILE = CONFIG_DIR / "config.json"


def save_token(token: str) -> None:
    """Persist the API token with restrictive file permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    CONFIG_FILE.write_text(json.dumps({"token": token}), encoding="utf-8")
    os.chmod(CONFIG_FILE, 0o600)


def load_token() -> str | None:
    """Load the stored API token, or None if not configured."""
    if not CONFIG_FILE.exists():
        return None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data.get("token")
