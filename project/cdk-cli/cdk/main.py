from __future__ import annotations

import sys

import click
from rich.console import Console

from cdk.auth import login as do_login
from cdk.deploy import deploy as do_deploy
from cdk.functions import delete_function, list_functions

console = Console()


@click.group()
def cli() -> None:
    """Oblak CDK — deploy and manage serverless functions."""


@cli.command("login")
def login() -> None:
    """Authenticate with the Oblak server."""
    do_login()


@cli.command("deploy")
@click.argument("file", type=click.Path(exists=True))
def deploy(file: str) -> None:
    """Deploy a Python function."""
    do_deploy(file)


@cli.command("list")
def list_cmd() -> None:
    """List deployed functions."""
    list_functions()


@cli.command("delete")
@click.argument("function_id")
def delete(function_id: str) -> None:
    """Delete a function by ID."""
    delete_function(function_id)


def main() -> None:
    try:
        cli()
    except click.ClickException as exc:
        console.print(f"[red]{exc.format_message()}[/red]")
        sys.exit(exc.exit_code)
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"[red]Unexpected error: {exc}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
