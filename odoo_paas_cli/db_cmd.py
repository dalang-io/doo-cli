"""Database insights commands."""

from __future__ import annotations

from typing import Annotated, Optional, Any

import typer

from .client import APIClient
from .config import get_api_key, get_api_url, load_config
from .exceptions import AuthError, CLIError, EXIT_AUTH, EXIT_NOT_FOUND, EXIT_SUCCESS, NotFoundError
from .instances import _resolve_instance_id
from .output import (
    output_data,
    print_db_size_summary,
    print_db_summary,
    print_slow_queries_table,
    print_table_health_table,
)

app = typer.Typer(help="Inspect PostgreSQL health for an instance.", no_args_is_help=True)


def _exit_with_error(message: str, code: int) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code)


def _get_state() -> Any:
    from .main import state

    return state


def _make_client(state: Any) -> APIClient:
    config = load_config()
    api_key = get_api_key(config, state.profile)
    api_url = get_api_url(config, state.profile, state.api_url)
    return APIClient(api_url, api_key, verbose=state.verbose, no_color=state.no_color)


@app.command("stats")
def db_stats(
    name: Annotated[str, typer.Argument(help="Instance slug")],
    output: Annotated[Optional[str], typer.Option("--output", "-o")] = None,
) -> None:
    state = _get_state()
    fmt = output or state.output
    try:
        with _make_client(state) as client:
            instance_id, instance = _resolve_instance_id(client, name)
            data = client.get_db_summary(instance_id)
    except AuthError as e:
        _exit_with_error(str(e), EXIT_AUTH)
    except NotFoundError as e:
        _exit_with_error(str(e), 1)
    except CLIError as e:
        _exit_with_error(str(e), e.exit_code)
    output_data(
        data,
        fmt,
        table_fn=lambda: print_db_summary(instance.get("name", name), data, no_color=state.no_color),
        no_color=state.no_color,
    )


@app.command("slow-queries")
def db_slow_queries(
    name: Annotated[str, typer.Argument(help="Instance slug")],
    sort: Annotated[str, typer.Option("--sort", help="avg or total")] = "avg",
    output: Annotated[Optional[str], typer.Option("--output", "-o")] = None,
) -> None:
    state = _get_state()
    fmt = output or state.output
    try:
        with _make_client(state) as client:
            instance_id, instance = _resolve_instance_id(client, name)
            data = client.get_db_slow_queries(instance_id, sort=sort)
    except AuthError as e:
        _exit_with_error(str(e), EXIT_AUTH)
    except NotFoundError as e:
        _exit_with_error(str(e), 1)
    except CLIError as e:
        _exit_with_error(str(e), e.exit_code)
    output_data(
        data,
        fmt,
        table_fn=lambda: print_slow_queries_table(instance.get("name", name), data, no_color=state.no_color),
        no_color=state.no_color,
    )


@app.command("tables")
def db_tables(
    name: Annotated[str, typer.Argument(help="Instance slug")],
    output: Annotated[Optional[str], typer.Option("--output", "-o")] = None,
) -> None:
    state = _get_state()
    fmt = output or state.output
    try:
        with _make_client(state) as client:
            instance_id, instance = _resolve_instance_id(client, name)
            data = client.get_db_table_health(instance_id)
    except AuthError as e:
        _exit_with_error(str(e), EXIT_AUTH)
    except NotFoundError as e:
        _exit_with_error(str(e), 1)
    except CLIError as e:
        _exit_with_error(str(e), e.exit_code)
    output_data(
        data,
        fmt,
        table_fn=lambda: print_table_health_table(instance.get("name", name), data, no_color=state.no_color),
        no_color=state.no_color,
    )


@app.command("size")
def db_size(
    name: Annotated[str, typer.Argument(help="Instance slug")],
    output: Annotated[Optional[str], typer.Option("--output", "-o")] = None,
) -> None:
    state = _get_state()
    fmt = output or state.output
    try:
        with _make_client(state) as client:
            instance_id, instance = _resolve_instance_id(client, name)
            data = client.get_db_size(instance_id)
    except AuthError as e:
        _exit_with_error(str(e), EXIT_AUTH)
    except NotFoundError as e:
        _exit_with_error(str(e), 1)
    except CLIError as e:
        _exit_with_error(str(e), e.exit_code)
    output_data(
        data,
        fmt,
        table_fn=lambda: print_db_size_summary(instance.get("name", name), data, no_color=state.no_color),
        no_color=state.no_color,
    )
