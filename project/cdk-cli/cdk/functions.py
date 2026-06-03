from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.table import Table

from cdk.api import api_delete, api_get
from cdk.config import load_token

console = Console()


def list_functions() -> None:
    """List all deployed functions."""
    if not load_token():
        console.print("[red]Not logged in — run: cdk login[/red]")
        sys.exit(1)

    result = api_get("/functions")
    functions = result if isinstance(result, list) else []

    table = Table(title="Functions")
    table.add_column("id", style="cyan")
    table.add_column("name")
    table.add_column("status")
    table.add_column("invoke_url", style="green")

    for fn in functions:
        table.add_row(
            str(fn.get("id", fn.get("function_id", ""))),
            str(fn.get("name", "")),
            str(fn.get("status", "")),
            str(fn.get("invoke_url", "")),
        )

    console.print(table)


def delete_function(function_id: str) -> None:
    """Delete a deployed function by ID."""
    if not load_token():
        console.print("[red]Not logged in — run: cdk login[/red]")
        sys.exit(1)

    if not click.confirm("Are you sure?", default=False):
        console.print("Aborted.")
        return

    api_delete(f"/functions/{function_id}")
    console.print(f"[green]Deleted function {function_id}[/green]")
