from __future__ import annotations

import argparse

from oblak_server.config import load_settings
from oblak_server.database import connect, ensure_user, init_db


def create_user_main() -> None:
    parser = argparse.ArgumentParser(description="Create an Oblak Cloud API user")
    parser.add_argument("username")
    parser.add_argument("token")
    args = parser.parse_args()

    settings = load_settings()
    init_db(settings)
    with connect(settings) as conn:
        user = ensure_user(conn, args.username, args.token)
        conn.commit()
    print(f"created_or_existing_user_id={user['id']}")
