"""Config commands: show, set, unset."""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from .config import load_config, save_config

app = typer.Typer(
    help="Manage CLI configuration.",
    no_args_is_help=True,
)


def _get_state() -> Any:
    from .main import state
    return state


def _mask_key(key: str) -> str:
    if len(key) <= 4:
        return "****"
    return f"****{key[-4:]}"


@app.command("show")
def config_show() -> None:
    """Show the current CLI configuration."""
    state = _get_state()
    config = load_config()
    out = Console(no_color=state.no_color)

    if state.output == "json":
        import json

        # Mask API keys before printing
        safe_config = _safe_config(config)
        print(json.dumps(safe_config, indent=2))
        return

    if state.output == "yaml":
        import yaml
        safe_config = _safe_config(config)
        print(yaml.dump(safe_config, default_flow_style=False), end="")
        return

    out.print(f"[bold]Config file:[/bold] ~/.config/doo-cli/config.yaml\n")
    out.print(f"[bold]Version:[/bold] {config.get('version', 1)}")
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("API KEY")
    table.add_column("API URL")
    table.add_column("DEFAULT INSTANCE")
    table.add_column("DEFAULT OUTPUT")
    key = config.get("api_key", "")
    masked = _mask_key(key) if key else "[dim]not set[/dim]"
    table.add_row(
        masked,
        config.get("api_url", "[dim]not set[/dim]"),
        config.get("default_instance", "[dim]not set[/dim]"),
        config.get("default_output", "[dim]not set[/dim]"),
    )

    out.print(table)


def _safe_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return config with all API keys masked."""
    import copy
    safe = copy.deepcopy(config)
    key = safe.get("api_key", "")
    if key:
        safe["api_key"] = _mask_key(key)
    return safe


@app.command("set")
def config_set(
    key: str = typer.Argument(help="Config key (e.g. api-url, default-instance, default-output)"),
    value: str = typer.Argument(help="Value to set"),
) -> None:
    """Set a configuration value."""
    state = _get_state()
    config = load_config()
    out = Console(no_color=state.no_color)

    normalized = key.replace("-", "_")

    config[normalized] = value

    save_config(config)

    if not state.quiet:
        display_value = _mask_key(value) if normalized == "api_key" else value
        out.print(f"[green]Set[/green] [bold]{key}[/bold] = {display_value}")


@app.command("unset")
def config_unset(
    key: str = typer.Argument(help="Config key to remove"),
) -> None:
    """Unset a configuration value."""
    state = _get_state()
    config = load_config()
    out = Console(no_color=state.no_color)
    stderr = Console(stderr=True, no_color=state.no_color)

    normalized = key.replace("-", "_")
    if normalized in config:
        config.pop(normalized)
        save_config(config)
        if not state.quiet:
            out.print(f"[green]Unset[/green] [bold]{key}[/bold]")
    else:
        stderr.print(f"[yellow]Key '{key}' is not set.[/yellow]")
