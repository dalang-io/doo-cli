"""Log commands: tail, query."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
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

app = typer.Typer(
    help="Query and tail instance logs.",
    no_args_is_help=True,
)

LOG_TAIL_WINDOW_SECS = 10
LOG_POLL_INTERVAL = 2
MAX_LOG_CAP = 10000


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
    """Get instance by slug/name and return (id, data)."""
    try:
        data = client.get_instance_by_slug(name)
    except NotFoundError:
        raise NotFoundError(
            f'Instance "{name}" not found.\n\n'
            "Run `doo-cli instances list` to see available instances."
        )
    return str(data.get("id", data.get("slug", name))), data


def _parse_duration(since: str) -> datetime:
    """Parse a duration like 1h, 30m, 7d into a past UTC datetime."""
    since = since.strip()
    now = datetime.now(tz=timezone.utc)

    # Try ISO 8601
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(since, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    # Duration shorthand
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if since and since[-1] in units:
        try:
            value = int(since[:-1])
            delta = timedelta(seconds=value * units[since[-1]])
            return now - delta
        except ValueError:
            pass

    raise typer.BadParameter(
        f"Cannot parse '{since}'. Use a duration like 1h, 30m, 7d, or an ISO 8601 timestamp."
    )


def _format_log_line(entry: dict[str, Any], output_format: str) -> str:
    """Format a single log entry as text or JSON."""
    if output_format == "json":
        return json.dumps(entry, default=str)

    ts = entry.get("timestamp", entry.get("ts", ""))
    level = entry.get("level", "").upper().ljust(5)
    service = entry.get("service", entry.get("vm", ""))
    message = entry.get("message", entry.get("msg", ""))
    parts = [str(ts), level]
    if service:
        parts.append(str(service))
    parts.append(str(message))
    return "  ".join(parts)


def _print_log_entry(entry: dict[str, Any], output_format: str, no_color: bool = False) -> None:
    """Print a log entry to stdout, with optional color."""
    line = _format_log_line(entry, output_format)
    if output_format == "json" or no_color or not sys.stdout.isatty():
        print(line)
        return

    level = entry.get("level", "").lower()
    color_map = {
        "error": "\033[31m",   # red
        "warn": "\033[33m",    # yellow
        "warning": "\033[33m",
        "debug": "\033[36m",   # cyan
        "info": "",
    }
    color = color_map.get(level, "")
    reset = "\033[0m" if color else ""
    print(f"{color}{line}{reset}")


@app.command("tail")
def logs_tail(
    instance: Annotated[str, typer.Option("--instance", help="Instance name/slug")],
    service: Annotated[
        Optional[str],
        typer.Option("--service", help="Filter by service: odoo or postgres"),
    ] = None,
    level: Annotated[
        Optional[str],
        typer.Option("--level", help="Filter by log level: debug, info, warn, error"),
    ] = None,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output format: text (default) or json"),
    ] = None,
) -> None:
    """Tail live logs from an instance (polling every 2s)."""
    state = _get_state()
    fmt = output or ("json" if state.output == "json" else "text")
    stderr = _stderr(state)

    try:
        with _make_client(state) as client:
            instance_id, inst_data = _resolve_instance_id(client, instance)

            inst_status = inst_data.get("status", "")
            if inst_status and inst_status not in {"running", "starting", "stopping"}:
                stderr.print(
                    f'[red]Error:[/red] Instance "{instance}" is not running (status: {inst_status}).\n'
                    "Start it with: doo-cli instances start --name " + instance
                )
                raise typer.Exit(EXIT_ERROR)

            if not state.quiet:
                stderr.print(
                    f'Tailing logs for "[bold]{instance}[/bold]"... (Ctrl+C to stop)'
                )

            last_timestamp: str | None = None
            reconnect_attempts = 0
            max_reconnects = 3

            while True:
                try:
                    now = datetime.now(tz=timezone.utc)
                    window_start = now - timedelta(seconds=LOG_TAIL_WINDOW_SECS)
                    start_str = window_start.strftime("%Y-%m-%dT%H:%M:%SZ")

                    entries = client.query_logs(
                        instance_id,
                        level=level,
                        vm=service,
                        start=start_str,
                        limit=200,
                    )

                    reconnect_attempts = 0
                    new_entries = []

                    for entry in entries:
                        ts = str(entry.get("timestamp", entry.get("ts", "")))
                        if last_timestamp is None or ts > last_timestamp:
                            new_entries.append(entry)

                    for entry in new_entries:
                        _print_log_entry(entry, fmt, no_color=state.no_color)

                    if new_entries:
                        last_ts = str(new_entries[-1].get("timestamp", new_entries[-1].get("ts", "")))
                        if last_ts:
                            last_timestamp = last_ts

                    time.sleep(LOG_POLL_INTERVAL)

                except CLIError:
                    reconnect_attempts += 1
                    stderr.print(
                        f"[yellow]Log stream interrupted (attempt {reconnect_attempts}/{max_reconnects}). Reconnecting...[/yellow]"
                    )
                    if reconnect_attempts >= max_reconnects:
                        stderr.print("[red]Error:[/red] Could not reconnect to log stream.")
                        raise typer.Exit(EXIT_ERROR)
                    time.sleep(LOG_POLL_INTERVAL * 2)

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


@app.command("query")
def logs_query(
    instance: Annotated[str, typer.Option("--instance", help="Instance name/slug")],
    since: Annotated[str, typer.Option("--since", help="Start time: duration (1h, 30m) or ISO 8601")],
    until: Annotated[
        Optional[str],
        typer.Option("--until", help="End time: ISO 8601 (defaults to now)"),
    ] = None,
    level: Annotated[
        Optional[str],
        typer.Option("--level", help="Filter by log level: debug, info, warn, error"),
    ] = None,
    grep: Annotated[
        Optional[str],
        typer.Option("--grep", help="Substring filter on the message field"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Maximum number of log lines to return"),
    ] = MAX_LOG_CAP,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output format: table, json, yaml"),
    ] = None,
) -> None:
    """Query historical logs for an instance."""
    state = _get_state()
    fmt = output or state.output
    stderr = _stderr(state)

    try:
        start_dt = _parse_duration(since)
        start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        until_str: str | None = None
        if until:
            until_str = until
        else:
            until_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with _make_client(state) as client:
            instance_id, _ = _resolve_instance_id(client, instance)

            entries = client.query_logs(
                instance_id,
                query=grep,
                level=level,
                limit=min(limit, MAX_LOG_CAP),
                start=start_str,
                end=until_str,
            )

            # Client-side grep fallback
            if grep:
                entries = [
                    e for e in entries
                    if grep.lower() in str(e.get("message", e.get("msg", ""))).lower()
                ]

            if len(entries) >= MAX_LOG_CAP:
                stderr.print(
                    f"[yellow]Warning:[/yellow] Result capped at {MAX_LOG_CAP} lines. "
                    "Use --limit to adjust or narrow your time range."
                )

    except typer.BadParameter as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)
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

    if fmt == "json":
        for entry in entries:
            print(json.dumps(entry, default=str))
    elif fmt == "yaml":
        import yaml
        print(yaml.dump([dict(e) for e in entries], default_flow_style=False), end="")
    else:
        from .output import print_logs_table
        print_logs_table(entries, no_color=state.no_color)
