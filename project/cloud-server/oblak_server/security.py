from __future__ import annotations

import hashlib
import secrets


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, expected_hash: str) -> bool:
    return secrets.compare_digest(hash_token(token), expected_hash)
