"""Config commands: show, set, unset."""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from .config import load_config, save_config, get_api_key
from .exceptions import EXIT_SUCCESS

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
    out.print(f"[bold]Default profile:[/bold] {config.get('default_profile', 'default')}\n")

    profiles = config.get("profiles", {})
    if not profiles:
        out.print("[dim]No profiles configured.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("PROFILE")
    table.add_column("API KEY")
    table.add_column("API URL")
    table.add_column("DEFAULT INSTANCE")
    table.add_column("DEFAULT OUTPUT")

    default_profile = config.get("default_profile", "default")

    for name, data in profiles.items():
        key = data.get("api_key", "")
        masked = _mask_key(key) if key else "[dim]not set[/dim]"
        is_default_marker = " [green](default)[/green]" if name == default_profile else ""
        table.add_row(
            f"{name}{is_default_marker}",
            masked,
            data.get("api_url", "[dim]not set[/dim]"),
            data.get("default_instance", "[dim]not set[/dim]"),
            data.get("default_output", "[dim]not set[/dim]"),
        )

    out.print(table)


def _safe_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return config with all API keys masked."""
    import copy
    safe = copy.deepcopy(config)
    for profile_data in safe.get("profiles", {}).values():
        key = profile_data.get("api_key", "")
        if key:
            profile_data["api_key"] = _mask_key(key)
    return safe


@app.command("set")
def config_set(
    key: str = typer.Argument(help="Config key (e.g. api-url, default-profile, default-instance)"),
    value: str = typer.Argument(help="Value to set"),
) -> None:
    """Set a configuration value."""
    state = _get_state()
    config = load_config()
    out = Console(no_color=state.no_color)

    normalized = key.replace("-", "_")

    # Handle profile-scoped keys
    profile_keys = {"api_url", "default_instance", "default_output", "api_key"}
    top_level_keys = {"default_profile", "version"}

    if normalized in top_level_keys:
        config[normalized] = value
    else:
        # Store in the active profile
        profile_name = state.profile or config.get("default_profile", "default")
        if "profiles" not in config:
            config["profiles"] = {}
        if profile_name not in config["profiles"]:
            config["profiles"][profile_name] = {}
        config["profiles"][profile_name][normalized] = value

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
    top_level_keys = {"default_profile", "version"}

    if normalized in top_level_keys:
        if normalized in config:
            config.pop(normalized)
            save_config(config)
            if not state.quiet:
                out.print(f"[green]Unset[/green] [bold]{key}[/bold]")
        else:
            stderr.print(f"[yellow]Key '{key}' is not set.[/yellow]")
    else:
        profile_name = state.profile or config.get("default_profile", "default")
        profile_data = config.get("profiles", {}).get(profile_name, {})
        if normalized in profile_data:
            del profile_data[normalized]
            save_config(config)
            if not state.quiet:
                out.print(f"[green]Unset[/green] [bold]{key}[/bold] from profile '[bold]{profile_name}[/bold]'")
        else:
            stderr.print(f"[yellow]Key '{key}' is not set in profile '{profile_name}'.[/yellow]")
