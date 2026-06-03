from __future__ import annotations

import sys

import click
import requests
from rich.console import Console

from cdk.api import api_get
from cdk.config import SERVER_URL, save_token

console = Console()


def login() -> None:
    """Prompt for an API token and validate it against the server."""
    token = click.prompt("API token", hide_input=True)

    try:
        response = requests.get(
            f"{SERVER_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        console.print(f"[red]Network error: {exc}[/red]")
        sys.exit(1)

    if response.status_code == 401:
        console.print("[red]Invalid API token[/red]")
        sys.exit(1)

    if response.status_code >= 400:
        try:
            body = response.json()
            message = body.get("detail") or body.get("message") or "Authentication failed"
        except (ValueError, AttributeError):
            message = "Authentication failed"
        console.print(f"[red]{message}[/red]")
        sys.exit(1)

    save_token(token)
    console.print("[green]Logged in successfully[/green]")
