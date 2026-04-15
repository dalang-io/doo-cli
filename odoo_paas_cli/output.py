"""Table/JSON/YAML output formatting for doo-cli."""

from __future__ import annotations

import json
import sys
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table
from rich import box

# Status badge colors
STATUS_COLORS: dict[str, str] = {
    "running": "green",
    "stopped": "yellow",
    "error": "red",
    "failed": "red",
    "creating": "cyan",
    "starting": "cyan",
    "stopping": "yellow",
    "deleting": "red",
    "pending": "blue",
    "provisioning": "cyan",
}


def get_console(no_color: bool = False) -> Console:
    """Return a Rich Console configured for color/no-color."""
    force_terminal = sys.stdout.isatty()
    return Console(
        highlight=False,
        no_color=no_color or not force_terminal,
        stderr=False,
    )


def get_stderr_console(no_color: bool = False) -> Console:
    """Return a Rich Console pointing to stderr."""
    return Console(
        highlight=False,
        no_color=no_color,
        stderr=True,
    )


def colorize_status(status: str, no_color: bool = False) -> str:
    """Return a Rich markup string for the status, or plain text."""
    if no_color or not sys.stdout.isatty():
        return status
    color = STATUS_COLORS.get(status.lower(), "white")
    return f"[{color}]{status}[/{color}]"


def print_json(data: Any) -> None:
    """Print data as indented JSON to stdout."""
    print(json.dumps(data, separators=(",", ":"), default=str))


def print_yaml(data: Any) -> None:
    """Print data as YAML to stdout."""
    print(yaml.dump(data, default_flow_style=False), end="")


def print_instances_table(instances: list[dict[str, Any]], no_color: bool = False) -> None:
    """Render a table of instances."""
    console = get_console(no_color)
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("NAME", style="bold")
    table.add_column("STATUS")
    table.add_column("ODOO VERSION")
    table.add_column("REGION")
    table.add_column("ENVIRONMENT")
    table.add_column("CREATED")

    for inst in instances:
        status = inst.get("status", "unknown")
        color = STATUS_COLORS.get(status.lower(), "white")
        status_markup = f"[{color}]{status}[/{color}]" if not no_color and sys.stdout.isatty() else status

        created = inst.get("created_at", inst.get("created", ""))
        if created and "T" in str(created):
            created = str(created).split("T")[0]

        table.add_row(
            inst.get("name", inst.get("slug", "")),
            status_markup,
            inst.get("odoo_version", ""),
            inst.get("region", ""),
            inst.get("environment_type", inst.get("environment", "")),
            str(created),
        )

    console.print(table)


def print_instance_detail(inst: dict[str, Any], no_color: bool = False) -> None:
    """Print instance detail as a key-value table."""
    console = get_console(no_color)
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    status = inst.get("status", "unknown")
    color = STATUS_COLORS.get(status.lower(), "white")
    status_markup = f"[{color}]{status}[/{color}]" if not no_color and sys.stdout.isatty() else status

    created = inst.get("created_at", inst.get("created", ""))
    updated = inst.get("updated_at", inst.get("updated", ""))

    fields: list[tuple[str, str]] = [
        ("Name", inst.get("name", inst.get("slug", ""))),
        ("Status", status_markup),
        ("Odoo Version", inst.get("odoo_version", "")),
        ("Edition", inst.get("odoo_edition", inst.get("edition", ""))),
        ("Postgres Version", inst.get("pg_version", inst.get("postgres_version", ""))),
        ("Region", inst.get("region", "")),
        ("Environment", inst.get("environment_type", inst.get("environment", ""))),
        ("Topology", inst.get("vm_topology", inst.get("topology", "single"))),
        ("URL", inst.get("odoo_url", inst.get("url", ""))),
        ("Created", str(created)),
        ("Updated", str(updated)),
    ]
    for field, value in fields:
        if value:
            table.add_row(field, value)

    console.print(table)


def print_backups_table(backups: list[dict[str, Any]], no_color: bool = False) -> None:
    console = get_console(no_color)
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("STATUS")
    table.add_column("TRIGGER")
    table.add_column("LABEL")
    table.add_column("CREATED")
    table.add_column("SIZE")

    for backup in backups:
        status = backup.get("status", "unknown")
        color = STATUS_COLORS.get(status.lower(), "white")
        status_markup = f"[{color}]{status}[/{color}]" if not no_color and sys.stdout.isatty() else status
        size_bytes = backup.get("size_bytes")
        size = "—"
        if size_bytes:
            try:
                size = f"{float(size_bytes) / 1048576:.1f} MB"
            except (TypeError, ValueError):
                size = str(size_bytes)
        table.add_row(
            str(backup.get("id", "")),
            status_markup,
            str(backup.get("trigger", "")),
            str(backup.get("label") or "—"),
            str((backup.get("completed_at") or backup.get("created_at") or "")),
            size,
        )

    console.print(table)


def print_logs_table(logs: list[dict[str, Any]], no_color: bool = False) -> None:
    """Render a table of log lines."""
    console = get_console(no_color)
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("TIMESTAMP")
    table.add_column("LEVEL")
    table.add_column("SERVICE")
    table.add_column("MESSAGE")

    for entry in logs:
        ts = entry.get("timestamp", entry.get("ts", ""))
        level = entry.get("level", "")
        service = entry.get("service", entry.get("vm", ""))
        message = entry.get("message", entry.get("msg", ""))
        table.add_row(str(ts), level, str(service), str(message))

    console.print(table)


def print_metrics_table(
    metrics: dict[str, Any],
    instance_name: str,
    metric_filter: str = "all",
    no_color: bool = False,
) -> None:
    """Render metrics as a table."""
    console = get_console(no_color)
    console.print(f"\nInstance: [bold]{instance_name}[/bold]\n")

    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("VM ROLE")
    if metric_filter in {"all", "cpu"}:
        table.add_column("CPU")
    if metric_filter in {"all", "memory"}:
        table.add_column("MEMORY")
    if metric_filter in {"all", "disk"}:
        table.add_column("DISK")

    # Support both flat and split-topology metrics
    if "roles" in metrics:
        for role, data in metrics["roles"].items():
            row = [role]
            if metric_filter in {"all", "cpu"}:
                row.append(_fmt_cpu(data.get("cpu")))
            if metric_filter in {"all", "memory"}:
                row.append(_fmt_memory(data.get("memory")))
            if metric_filter in {"all", "disk"}:
                row.append(_fmt_disk(data.get("disk")))
            table.add_row(*row)
    else:
        row = ["app"]
        if metric_filter in {"all", "cpu"}:
            row.append(_fmt_cpu(metrics.get("cpu")))
        if metric_filter in {"all", "memory"}:
            row.append(_fmt_memory(metrics.get("memory")))
        if metric_filter in {"all", "disk"}:
            row.append(_fmt_disk(metrics.get("disk")))
        table.add_row(*row)

    console.print(table)


def print_db_summary(instance_name: str, data: dict[str, Any], no_color: bool = False) -> None:
    console = get_console(no_color)
    console.print(f"\nInstance: [bold]{instance_name}[/bold]\n")
    connections = data.get("connections", {})
    cache = data.get("cache_health", {})
    slow = data.get("slow_queries", {})
    tables = data.get("table_health", {})

    summary = Table(box=box.SIMPLE, show_header=False)
    summary.add_column("Field", style="bold")
    summary.add_column("Value")
    summary.add_row("Active connections", str(connections.get("active_connections", "N/A")))
    summary.add_row("Idle connections", str(connections.get("idle_connections", "N/A")))
    summary.add_row("Idle in transaction", str(connections.get("idle_in_transaction_connections", "N/A")))
    summary.add_row("Max connections", str(connections.get("max_connections", "N/A")))
    summary.add_row("Buffer hit ratio", f"{cache.get('buffer_cache_hit_ratio', 'N/A')}%")
    summary.add_row("Index hit ratio", f"{cache.get('index_hit_ratio', 'N/A')}%")
    summary.add_row("Assessment", str(cache.get("assessment", "N/A")))
    console.print(summary)

    if slow.get("rows"):
        print_slow_queries_table(instance_name, slow, no_color=no_color)
    if tables.get("rows"):
        dead_rows = [row for row in tables["rows"] if float(row.get("dead_ratio_pct", 0)) > 20]
        if dead_rows:
            print_table_health_table(instance_name, {"rows": dead_rows}, no_color=no_color)


def print_slow_queries_table(instance_name: str, data: dict[str, Any], no_color: bool = False) -> None:
    console = get_console(no_color)
    rows = data.get("rows", [])
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("QUERY")
    table.add_column("CALLS")
    table.add_column("AVG MS")
    table.add_column("TOTAL S")
    for row in rows:
        table.add_row(
            str(row.get("query_text", ""))[:120],
            str(row.get("calls", "")),
            str(row.get("avg_duration_ms", "")),
            str(row.get("total_time_seconds", "")),
        )
    console.print(table)


def print_table_health_table(instance_name: str, data: dict[str, Any], no_color: bool = False) -> None:
    console = get_console(no_color)
    rows = data.get("rows", [])
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("TABLE")
    table.add_column("LIVE")
    table.add_column("DEAD")
    table.add_column("DEAD %")
    table.add_column("LAST VACUUM")
    for row in rows:
        table.add_row(
            str(row.get("table_name", "")),
            str(row.get("live_rows", "")),
            str(row.get("dead_rows", "")),
            f"{row.get('dead_ratio_pct', '')}%",
            str(row.get("last_autovacuum_display", row.get("last_autovacuum", ""))),
        )
    console.print(table)


def print_db_size_summary(instance_name: str, data: dict[str, Any], no_color: bool = False) -> None:
    console = get_console(no_color)
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Current size", str(data.get("current_size_display", "N/A")))
    history = data.get("history", [])[-7:]
    if history:
        trend = ", ".join(str(item.get("size_display", "")) for item in history)
        table.add_row("7-day trend", trend)
    console.print(table)


def _fmt_cpu(cpu: Any) -> str:
    if cpu is None:
        return "N/A"
    try:
        return f"{float(cpu):.1f}%"
    except (TypeError, ValueError):
        return str(cpu)


def _fmt_memory(mem: Any) -> str:
    if mem is None:
        return "N/A"
    if isinstance(mem, dict):
        used = mem.get("used_gb", mem.get("used", "?"))
        total = mem.get("total_gb", mem.get("total", "?"))
        pct = mem.get("percent", "")
        if pct:
            return f"{pct:.1f}%  {used} GB / {total} GB"
        return f"{used} GB / {total} GB"
    return str(mem)


def _fmt_disk(disk: Any) -> str:
    if disk is None:
        return "N/A"
    if isinstance(disk, dict):
        used = disk.get("used_gb", disk.get("used", "?"))
        total = disk.get("total_gb", disk.get("total", "?"))
        pct = disk.get("percent", "")
        if pct:
            return f"{pct:.1f}%  {used} GB / {total} GB"
        return f"{used} GB / {total} GB"
    return str(disk)


def output_data(
    data: Any,
    output_format: str,
    *,
    table_fn: Any = None,
    no_color: bool = False,
) -> None:
    """Route data to the correct output format."""
    fmt = output_format.lower()
    if fmt == "json":
        print_json(data)
    elif fmt == "yaml":
        print_yaml(data)
    else:
        if table_fn:
            table_fn()
        else:
            print_json(data)
