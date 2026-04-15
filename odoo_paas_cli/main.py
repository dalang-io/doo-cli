"""Typer app root, global flags, and subcommand registration."""

from __future__ import annotations

import sys
from typing import Annotated, Optional

import typer
from rich.console import Console

from . import __version__
from .exceptions import CLIError, EXIT_SUCCESS

# Import sub-apps
from .auth import app as auth_app
from .instances import app as instances_app
from .backup import app as backup_app
from .db_cmd import app as db_app
from .logs import app as logs_app
from .metrics import app as metrics_app
from .config_cmd import app as config_app

# ---------------------------------------------------------------------------
# Global state shared across subcommands via the context object
# ---------------------------------------------------------------------------


class GlobalState:
    output: str = "table"
    profile: str | None = None
    api_url: str | None = None
    quiet: bool = False
    verbose: bool = False
    no_color: bool = False


# Module-level state singleton accessed by subcommands
state = GlobalState()

# ---------------------------------------------------------------------------
# Root app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="doo-cli",
    help="CLI for the Odoo PaaS platform — manage instances, logs, and metrics.",
    no_args_is_help=True,
    invoke_without_command=True,
    add_completion=True,
    pretty_exceptions_enable=False,
)

app.add_typer(auth_app, name="auth")
app.add_typer(instances_app, name="instances")
app.add_typer(backup_app, name="backup")
app.add_typer(db_app, name="db")
app.add_typer(logs_app, name="logs")
app.add_typer(metrics_app, name="metrics")
app.add_typer(config_app, name="config")


@app.callback()
def main_callback(
    ctx: typer.Context,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output format: table, json, yaml"),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", help="Named credential profile to use"),
    ] = None,
    api_url: Annotated[
        Optional[str],
        typer.Option("--api-url", help="Override the API base URL"),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress non-essential output"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Emit debug info to stderr"),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable color output"),
    ] = False,
    version: Annotated[
        bool,
        typer.Option("--version", help="Print version and exit", is_eager=True),
    ] = False,
) -> None:
    """doo-cli — automate your Odoo instance management."""
    import os

    # Respect NO_COLOR env var (https://no-color.org/)
    if os.environ.get("NO_COLOR"):
        no_color = True

    # Populate global state
    state.output = output or "table"
    state.profile = profile
    state.api_url = api_url
    state.quiet = quiet
    state.verbose = verbose
    state.no_color = no_color

    if version:
        from .config import load_config, peek_api_url
        cfg = load_config()
        url = peek_api_url(cfg, profile, api_url)
        console = Console(no_color=no_color)
        console.print(f"doo-cli version {__version__}")
        console.print(f"API URL: {url or 'not configured'}")
        raise typer.Exit(EXIT_SUCCESS)

    # If no subcommand given, show help
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        raise typer.Exit(EXIT_SUCCESS)


def _handle_cli_error(err: CLIError) -> None:
    """Print the error message and exit with the correct code."""
    stderr = Console(stderr=True)
    stderr.print(f"[bold red]Error:[/bold red] {err}")
    raise typer.Exit(err.exit_code)


if __name__ == "__main__":
    app()


def run() -> None:
    app()
