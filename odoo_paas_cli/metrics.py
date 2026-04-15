"""Metrics commands: snapshot, watch."""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

import typer
from rich.console import Console

from .client import APIClient
from .config import get_api_key, get_api_url, load_config
from .exceptions import (
    AuthError,
    CLIError,
    EXIT_AUTH,
    EXIT_ERROR,
    EXIT_NOT_FOUND,
    EXIT_SUCCESS,
    NotFoundError,
)
from .output import output_data, print_metrics_table

app = typer.Typer(
    help="View instance resource metrics.",
    no_args_is_help=True,
)

VALID_METRICS = {"all", "cpu", "memory", "disk"}


def _get_state() -> Any:
    from .main import state
    return state


def _make_client(state: Any) -> APIClient:
    config = load_config()
    api_key = get_api_key(config)
    api_url = get_api_url(config, state.api_url)
    return APIClient(api_url, api_key, verbose=state.verbose, no_color=state.no_color)


def _stderr(state: Any) -> Console:
    return Console(stderr=True, no_color=state.no_color)


def _resolve_instance_id(client: APIClient, name: str) -> tuple[str, dict[str, Any]]:
    try:
        data = client.get_instance_by_slug(name)
    except NotFoundError:
        raise NotFoundError(
            f'Instance "{name}" not found.\n\n'
            "Run `doo-cli instances list` to see available instances."
        )
    return str(data.get("id", data.get("slug", name))), data


def _parse_watch_interval(interval: str) -> int:
    """Parse an interval like 5s, 1m into seconds."""
    interval = interval.strip()
    units = {"s": 1, "m": 60, "h": 3600}
    if interval and interval[-1] in units:
        try:
            return int(interval[:-1]) * units[interval[-1]]
        except ValueError:
            pass
    try:
        return int(interval)
    except ValueError:
        raise typer.BadParameter(f"Cannot parse interval '{interval}'. Use e.g. 5s, 1m.")


def _normalize_metric(metric: str | None) -> str:
    value = (metric or "all").strip().lower()
    if value not in VALID_METRICS:
        raise typer.BadParameter("Metric must be one of: cpu, memory, disk, all.")
    return value


@app.command("snapshot")
def metrics_snapshot(
    instance: Annotated[str, typer.Option("--instance", help="Instance name/slug")],
    metric: Annotated[
        Optional[str],
        typer.Option("--metric", help="Metric to show: cpu, memory, disk, all"),
    ] = "all",
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output format: table, json, yaml"),
    ] = None,
) -> None:
    """Show current resource metrics for an instance."""
    state = _get_state()
    fmt = output or state.output
    stderr = _stderr(state)

    try:
        metric_name = _normalize_metric(metric)
        with _make_client(state) as client:
            instance_id, inst_data = _resolve_instance_id(client, instance)

            inst_status = inst_data.get("status", "")
            if inst_status and inst_status not in {"running", "starting"}:
                stderr.print(
                    f'[red]Error:[/red] Instance "{instance}" is not running (status: {inst_status}).\n'
                    "Metrics are only available for running instances."
                )
                raise typer.Exit(EXIT_ERROR)

            metrics = client.get_metrics_summary(instance_id, metric=metric_name)

    except AuthError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_AUTH)
    except NotFoundError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_NOT_FOUND)
    except CLIError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(e.exit_code)
    except KeyboardInterrupt:
        print()
        raise typer.Exit(EXIT_SUCCESS)

    output_data(
        metrics,
        fmt,
        table_fn=lambda: print_metrics_table(
            metrics, instance, metric_filter=metric_name, no_color=state.no_color
        ),
        no_color=state.no_color,
    )


@app.command("watch")
def metrics_watch(
    instance: Annotated[str, typer.Option("--instance", help="Instance name/slug")],
    interval: Annotated[
        str,
        typer.Option("--interval", help="Refresh interval (e.g. 5s, 1m)"),
    ] = "5s",
    metric: Annotated[
        Optional[str],
        typer.Option("--metric", help="Metric to show: cpu, memory, disk, all"),
    ] = "all",
) -> None:
    """Continuously refresh metrics for an instance (Ctrl+C to stop)."""
    state = _get_state()
    stderr = _stderr(state)

    try:
        interval_secs = _parse_watch_interval(interval)
        metric_name = _normalize_metric(metric)
    except typer.BadParameter as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)

    try:
        with _make_client(state) as client:
            instance_id, inst_data = _resolve_instance_id(client, instance)

            if not state.quiet:
                stderr.print(
                    f'Watching metrics for "[bold]{instance}[/bold]" every {interval}... (Ctrl+C to stop)'
                )

            while True:
                try:
                    now = datetime.now(tz=timezone.utc)
                    metrics = client.get_metrics_summary(instance_id, metric=metric_name)
                    # Clear screen (ANSI escape)
                    if sys.stdout.isatty() and not state.no_color:
                        print("\033[2J\033[H", end="")

                    print_metrics_table(
                        metrics,
                        instance,
                        metric_filter=metric_name,
                        no_color=state.no_color,
                    )
                    timestamp = now.strftime("%Y-%m-%d %H:%M:%S UTC")
                    print(f"\nLast updated: {timestamp}  (refreshing every {interval})\n")

                except CLIError as e:
                    stderr.print(f"[yellow]Warning:[/yellow] Failed to fetch metrics: {e}")

                time.sleep(interval_secs)

    except KeyboardInterrupt:
        print()
        raise typer.Exit(EXIT_SUCCESS)
    except AuthError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_AUTH)
    except NotFoundError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_NOT_FOUND)
    except CLIError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(e.exit_code)
