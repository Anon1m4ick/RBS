from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console

from cdk.api import api_post
from cdk.config import load_token

console = Console()


def deploy(file_path: str) -> None:
    """Deploy a Python function to the Oblak platform."""
    if not load_token():
        console.print("[red]Not logged in — run: cdk login[/red]")
        sys.exit(1)

    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        sys.exit(1)

    if path.suffix != ".py":
        console.print("[red]File must be a .py file[/red]")
        sys.exit(1)

    files: dict[str, tuple] = {
        "file": (path.name, path.read_bytes(), "text/x-python"),
    }

    requirements = path.parent / "requirements.txt"
    if requirements.exists():
        files["requirements"] = (
            "requirements.txt",
            requirements.read_bytes(),
            "text/plain",
        )

    result = api_post("/functions", files=files)
    if not result or "invoke_url" not in result:
        console.print("[red]Unexpected response from server[/red]")
        sys.exit(1)

    console.print(f"[green]Deployed successfully[/green]")
    console.print(f"Invoke URL: {result['invoke_url']}")
