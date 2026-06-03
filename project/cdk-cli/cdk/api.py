from __future__ import annotations

import sys

import requests
from rich.console import Console

from cdk.config import SERVER_URL, load_token

console = Console()


def _auth_headers() -> dict[str, str]:
    token = load_token()
    if not token:
        console.print("[red]Not logged in — run: cdk login[/red]")
        sys.exit(1)
    return {"Authorization": f"Bearer {token}"}


def _handle_response(response: requests.Response) -> dict | list | None:
    if response.status_code == 401:
        console.print("[red]Not authorized — run: cdk login[/red]")
        sys.exit(1)

    if 400 <= response.status_code < 500:
        try:
            body = response.json()
            message = body.get("detail") or body.get("message") or body.get("error")
            if isinstance(message, list):
                message = "; ".join(str(m) for m in message)
            if not message:
                message = response.text or f"Request failed with status {response.status_code}"
        except (ValueError, AttributeError):
            message = response.text or f"Request failed with status {response.status_code}"
        console.print(f"[red]{message}[/red]")
        sys.exit(1)

    if response.status_code >= 500:
        console.print("[red]Server error — please try again later[/red]")
        sys.exit(1)

    if response.status_code == 204 or not response.content:
        return None

    return response.json()


def api_get(path: str, *, require_auth: bool = True) -> dict | list | None:
    headers = _auth_headers() if require_auth else {}
    try:
        response = requests.get(f"{SERVER_URL}{path}", headers=headers, timeout=30)
    except requests.RequestException as exc:
        console.print(f"[red]Network error: {exc}[/red]")
        sys.exit(1)
    return _handle_response(response)


def api_post(
    path: str,
    *,
    files: dict | None = None,
    data: dict | None = None,
) -> dict | list | None:
    headers = _auth_headers()
    try:
        response = requests.post(
            f"{SERVER_URL}{path}",
            headers=headers,
            files=files,
            data=data,
            timeout=60,
        )
    except requests.RequestException as exc:
        console.print(f"[red]Network error: {exc}[/red]")
        sys.exit(1)
    return _handle_response(response)


def api_delete(path: str) -> dict | list | None:
    headers = _auth_headers()
    try:
        response = requests.delete(f"{SERVER_URL}{path}", headers=headers, timeout=30)
    except requests.RequestException as exc:
        console.print(f"[red]Network error: {exc}[/red]")
        sys.exit(1)
    return _handle_response(response)
