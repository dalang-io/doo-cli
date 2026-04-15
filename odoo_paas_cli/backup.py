"""Backup commands: create, list, restore, delete."""

from __future__ import annotations

from typing import Annotated, Any, Optional

import typer
from rich.console import Console

from .client import APIClient
from .config import get_api_key, get_api_url, load_config
from .exceptions import AuthError, CLIError, EXIT_AUTH, EXIT_NOT_FOUND, EXIT_SUCCESS, NotFoundError
from .output import output_data, print_backups_table

app = typer.Typer(help="Manage instance snapshots and restores.", no_args_is_help=True)


def _get_state() -> Any:
    from .main import state
    return state


def _make_client(state: Any) -> APIClient:
    config = load_config()
    api_key = get_api_key(config, state.profile)
    api_url = get_api_url(config, state.profile, state.api_url)
    return APIClient(api_url, api_key, verbose=state.verbose, no_color=state.no_color)


def _stderr(state: Any) -> Console:
    return Console(stderr=True, no_color=state.no_color)


def _resolve_instance_id(client: APIClient, name: str) -> tuple[str, dict[str, Any]]:
    data = client.get_instance_by_slug(name)
    return str(data["id"]), data


@app.command("list")
def backup_list(
    name: Annotated[str, typer.Option("--name", help="Instance name/slug")],
    output: Annotated[Optional[str], typer.Option("--output", "-o")] = None,
) -> None:
    state = _get_state()
    fmt = output or state.output
    stderr = _stderr(state)
    try:
        with _make_client(state) as client:
            instance_id, _ = _resolve_instance_id(client, name)
            backups = client.list_backups(instance_id)
    except AuthError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(EXIT_AUTH)
    except NotFoundError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(EXIT_NOT_FOUND)
    except CLIError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(exc.exit_code)
    output_data(backups, fmt, table_fn=lambda: print_backups_table(backups, no_color=state.no_color), no_color=state.no_color)


@app.command("create")
def backup_create(
    name: Annotated[str, typer.Option("--name", help="Instance name/slug")],
    label: Annotated[Optional[str], typer.Option("--label", help="Optional snapshot label")] = None,
    output: Annotated[Optional[str], typer.Option("--output", "-o")] = None,
) -> None:
    state = _get_state()
    fmt = output or state.output
    stderr = _stderr(state)
    try:
        with _make_client(state) as client:
            instance_id, _ = _resolve_instance_id(client, name)
            backup = client.create_backup(instance_id, label=label)
    except AuthError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(EXIT_AUTH)
    except NotFoundError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(EXIT_NOT_FOUND)
    except CLIError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(exc.exit_code)
    output_data(backup, fmt, no_color=state.no_color)


@app.command("delete")
def backup_delete(
    name: Annotated[str, typer.Option("--name", help="Instance name/slug")],
    backup_id: Annotated[str, typer.Option("--backup-id", help="Backup UUID")],
) -> None:
    state = _get_state()
    stderr = _stderr(state)
    try:
        with _make_client(state) as client:
            instance_id, _ = _resolve_instance_id(client, name)
            client.delete_backup(instance_id, backup_id)
    except AuthError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(EXIT_AUTH)
    except NotFoundError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(EXIT_NOT_FOUND)
    except CLIError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(exc.exit_code)
    raise typer.Exit(EXIT_SUCCESS)


@app.command("restore")
def backup_restore(
    name: Annotated[str, typer.Option("--name", help="Source instance name/slug")],
    backup_id: Annotated[str, typer.Option("--backup-id", help="Backup UUID")],
    restore_name: Annotated[str, typer.Option("--restore-name", help="New restored instance name")],
    topology: Annotated[str, typer.Option("--topology", help="single or split")] = "single",
    output: Annotated[Optional[str], typer.Option("--output", "-o")] = None,
) -> None:
    state = _get_state()
    fmt = output or state.output
    stderr = _stderr(state)
    payload: dict[str, Any] = {"name": restore_name, "vm_topology": topology}
    if topology == "split":
        payload.update({
            "app_vcpus": 4,
            "app_ram_mb": 8192,
            "app_disk_gb": 80,
            "db_vcpus": 2,
            "db_ram_mb": 4096,
            "db_disk_gb": 40,
        })
    else:
        payload.update({
            "single_vcpus": 4,
            "single_ram_mb": 8192,
            "single_disk_gb": 80,
        })
    try:
        with _make_client(state) as client:
            instance_id, _ = _resolve_instance_id(client, name)
            restore = client.restore_backup(instance_id, backup_id, payload)
    except AuthError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(EXIT_AUTH)
    except NotFoundError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(EXIT_NOT_FOUND)
    except CLIError as exc:
        stderr.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(exc.exit_code)
    output_data(restore, fmt, no_color=state.no_color)
