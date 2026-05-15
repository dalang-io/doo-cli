"""Instance commands: list, get, create, start, stop, delete."""

from __future__ import annotations

import sys
import time
from typing import Annotated, Optional, Any

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .client import APIClient
from .config import get_api_key, get_api_url, load_config
from .exceptions import (
    AuthError,
    CLIError,
    EXIT_AUTH,
    EXIT_ERROR,
    EXIT_NOT_FOUND,
    EXIT_SUCCESS,
    EXIT_TIMEOUT,
    EXIT_USAGE,
    NotFoundError,
)
from .output import (
    output_data,
    print_instance_detail,
    print_instances_table,
)

app = typer.Typer(
    help="Manage Odoo instances.",
    no_args_is_help=True,
)

DEFAULT_WAIT_TIMEOUT = 900  # 15 minutes
POLL_INTERVAL = 3  # seconds
SINGLE_SIZE_MAP = {
    "small": {"single_vcpus": 2, "single_ram_mb": 4096, "single_disk_gb": 40},
    "medium": {"single_vcpus": 4, "single_ram_mb": 8192, "single_disk_gb": 80},
    "large": {"single_vcpus": 8, "single_ram_mb": 16384, "single_disk_gb": 160},
}
APP_SIZE_MAP = {
    "small": {"app_vcpus": 2, "app_ram_mb": 4096, "app_disk_gb": 40},
    "medium": {"app_vcpus": 4, "app_ram_mb": 8192, "app_disk_gb": 80},
    "large": {"app_vcpus": 8, "app_ram_mb": 16384, "app_disk_gb": 160},
}
DB_SIZE_MAP = {
    "small": {"db_vcpus": 1, "db_ram_mb": 2048, "db_disk_gb": 20},
    "medium": {"db_vcpus": 2, "db_ram_mb": 4096, "db_disk_gb": 40},
    "large": {"db_vcpus": 4, "db_ram_mb": 8192, "db_disk_gb": 80},
}


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


def _require_size(mapping: dict[str, dict[str, int]], size_name: str | None, label: str) -> dict[str, int]:
    if not size_name:
        raise UsageError(f"{label} is required.")
    normalized = size_name.strip().lower()
    if normalized not in mapping:
        raise UsageError(f"Unsupported {label}: {size_name}. Use one of: {', '.join(mapping)}.")
    return mapping[normalized]


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


def _wait_for_state(
    client: APIClient,
    instance_id: str,
    terminal_states: set[str],
    error_states: set[str],
    deleted: bool = False,
    timeout: int = DEFAULT_WAIT_TIMEOUT,
    state: Any = None,
) -> dict[str, Any] | None:
    """Poll instance status until a terminal state is reached or timeout."""
    no_color = state.no_color if state else False
    quiet = state.quiet if state else False
    elapsed = 0
    last_status: str | None = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=Console(stderr=True, no_color=no_color),
        transient=not quiet,
    ) as progress:
        task = progress.add_task("Waiting...", total=None)

        while elapsed < timeout:
            try:
                data = client.get_instance(instance_id)
                status = data.get("status", "unknown")

                if status != last_status:
                    last_status = status
                    progress.update(task, description=f"Status: [bold]{status}[/bold]")

                if deleted and status == "deleted":
                    return data

                if status in terminal_states:
                    return data

                if status in error_states:
                    return data

            except NotFoundError:
                if deleted:
                    return None
                raise

            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

    raise CLIError(
        f"Timed out waiting for instance after {timeout}s. "
        "The operation may still be in progress — check the dashboard.",
        EXIT_TIMEOUT,
    )


@app.command("list")
def instances_list(
    status: Annotated[
        Optional[str],
        typer.Option("--status", help="Filter by status (running, stopped, etc.)"),
    ] = None,
    environment: Annotated[
        Optional[str],
        typer.Option("--environment", help="Filter by environment (development, staging, production)"),
    ] = None,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output format: table, json, yaml"),
    ] = None,
) -> None:
    """List all instances."""
    state = _get_state()
    fmt = output or state.output
    stderr = _stderr(state)

    try:
        with _make_client(state) as client:
            instances = client.list_instances(status=status, environment=environment)
    except AuthError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_AUTH)
    except CLIError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(e.exit_code)
    except KeyboardInterrupt:
        print()
        raise typer.Exit(EXIT_SUCCESS)

    output_data(
        instances,
        fmt,
        table_fn=lambda: print_instances_table(instances, no_color=state.no_color),
        no_color=state.no_color,
    )


@app.command("get")
def instances_get(
    name: Annotated[str, typer.Option("--name", help="Instance name/slug")],
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output format: table, json, yaml"),
    ] = None,
) -> None:
    """Get details for a specific instance."""
    state = _get_state()
    fmt = output or state.output
    stderr = _stderr(state)

    try:
        with _make_client(state) as client:
            _, inst = _resolve_instance_id(client, name)
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
        inst,
        fmt,
        table_fn=lambda: print_instance_detail(inst, no_color=state.no_color),
        no_color=state.no_color,
    )


@app.command("create")
def instances_create(
    name: Annotated[str, typer.Option("--name", help="Instance name")],
    odoo_version: Annotated[str, typer.Option("--odoo-version", help="Odoo version (e.g. 17.0)")],
    edition: Annotated[str, typer.Option("--edition", help="community or enterprise")],
    postgres_version: Annotated[str, typer.Option("--postgres-version", help="PostgreSQL version (e.g. 17)")],
    environment: Annotated[str, typer.Option("--environment", help="staging or production")],
    install_type: Annotated[
        str,
        typer.Option("--install-type", help="Odoo install type: docker or system"),
    ] = "docker",
    github_repository: Annotated[
        Optional[str],
        typer.Option("--github-repository", help="Optional GitHub repository name or slug"),
    ] = None,
    github_repository_clone_url: Annotated[
        Optional[str],
        typer.Option("--github-repository-clone-url", help="Optional Git clone URL"),
    ] = None,
    size: Annotated[
        Optional[str],
        typer.Option("--size", help="Instance size: small, medium, large (for single topology)"),
    ] = None,
    topology: Annotated[
        Optional[str],
        typer.Option("--topology", help="VM topology: single or split"),
    ] = "single",
    app_size: Annotated[
        Optional[str],
        typer.Option("--app-size", help="App VM size (for split topology)"),
    ] = None,
    app_vm_count: Annotated[
        Optional[int],
        typer.Option("--app-vm-count", min=1, max=5, help="Number of app VMs for split topology"),
    ] = None,
    db_size: Annotated[
        Optional[str],
        typer.Option("--db-size", help="DB VM size (for split topology)"),
    ] = None,
    region: Annotated[
        Optional[str],
        typer.Option("--region", help="Region (e.g. eu-west)"),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option("--wait", help="Wait for instance to reach running state"),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Timeout in seconds when using --wait"),
    ] = DEFAULT_WAIT_TIMEOUT,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output format: table, json, yaml"),
    ] = None,
) -> None:
    """Create a new Odoo instance."""
    state = _get_state()
    fmt = output or state.output
    stderr = _stderr(state)
    out = Console(no_color=state.no_color)

    payload: dict[str, Any] = {
        "name": name,
        "odoo_version": odoo_version,
        "odoo_edition": edition,
        "odoo_install_type": install_type,
        "pg_version": postgres_version,
        "environment_type": environment,
        "vm_topology": topology or "single",
        "usage_profile": {
            "concurrent_users": 10,
            "modules": [],
            "expected_storage": "20-50gb",
        },
    }
    if github_repository:
        payload["github_repository"] = github_repository
    if github_repository_clone_url:
        payload["github_repository_clone_url"] = github_repository_clone_url
    if topology == "split":
        payload.update(_require_size(APP_SIZE_MAP, app_size, "--app-size"))
        payload.update(_require_size(DB_SIZE_MAP, db_size, "--db-size"))
        if app_vm_count is not None:
            payload["app_vm_count"] = app_vm_count
    else:
        payload.update(_require_size(SINGLE_SIZE_MAP, size, "--size"))

    try:
        with _make_client(state) as client:
            result = client.create_instance(payload)

            if not state.quiet:
                workflow_id = result.get("workflow_id", result.get("id", ""))
                out.print(
                    f'Creating instance "[bold]{name}[/bold]"...'
                    + (f" workflow ID: {workflow_id}" if workflow_id else "")
                )

            if wait:
                instance_id = str(result.get("id", result.get("slug", name)))
                final = _wait_for_state(
                    client,
                    instance_id,
                    terminal_states={"running"},
                    error_states={"error", "failed"},
                    timeout=timeout,
                    state=state,
                )
                if final:
                    status = final.get("status", "unknown")
                    if status in {"error", "failed"}:
                        stderr.print(f"[red]Error:[/red] Instance reached error state: {status}")
                        raise typer.Exit(EXIT_ERROR)
                    if not state.quiet:
                        url = final.get("url", "")
                        out.print(
                            f'[green]Instance "[bold]{name}[/bold]" is {status}.[/green]'
                            + (f" URL: {url}" if url else "")
                        )
                    output_data(
                        final,
                        fmt,
                        table_fn=lambda: print_instance_detail(final, no_color=state.no_color),
                        no_color=state.no_color,
                    )
                return
            else:
                output_data(
                    result,
                    fmt,
                    table_fn=lambda: print_instance_detail(result, no_color=state.no_color),
                    no_color=state.no_color,
                )

    except AuthError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_AUTH)
    except CLIError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(e.exit_code)
    except KeyboardInterrupt:
        print()
        raise typer.Exit(EXIT_SUCCESS)


@app.command("start")
def instances_start(
    name: Annotated[str, typer.Option("--name", help="Instance name/slug")],
    wait: Annotated[
        bool,
        typer.Option("--wait", help="Wait for instance to reach running state"),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Timeout in seconds when using --wait"),
    ] = DEFAULT_WAIT_TIMEOUT,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output format: table, json, yaml"),
    ] = None,
) -> None:
    """Start a stopped instance."""
    state = _get_state()
    fmt = output or state.output
    stderr = _stderr(state)
    out = Console(no_color=state.no_color)

    try:
        with _make_client(state) as client:
            instance_id, inst_data = _resolve_instance_id(client, name)

            current_status = inst_data.get("status", "")
            if current_status == "running":
                stderr.print(f'[red]Error:[/red] Instance "{name}" is already running.')
                raise typer.Exit(EXIT_ERROR)

            result = client.start_instance(instance_id)

            if not state.quiet:
                out.print(f'Starting instance "[bold]{name}[/bold]"...')

            if wait:
                final = _wait_for_state(
                    client,
                    instance_id,
                    terminal_states={"running"},
                    error_states={"error", "failed"},
                    timeout=timeout,
                    state=state,
                )
                if final:
                    status = final.get("status", "unknown")
                    if status in {"error", "failed"}:
                        stderr.print(f"[red]Error:[/red] Instance reached error state: {status}")
                        raise typer.Exit(EXIT_ERROR)
                    if not state.quiet:
                        out.print(f'[green]Instance "[bold]{name}[/bold]" is {status}.[/green]')
                    output_data(
                        final,
                        fmt,
                        table_fn=lambda: print_instance_detail(final, no_color=state.no_color),
                        no_color=state.no_color,
                    )
            else:
                output_data(
                    result or inst_data,
                    fmt,
                    table_fn=lambda: print_instance_detail(result or inst_data, no_color=state.no_color),
                    no_color=state.no_color,
                )

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


@app.command("stop")
def instances_stop(
    name: Annotated[str, typer.Option("--name", help="Instance name/slug")],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Skip confirmation prompt (required in non-TTY)"),
    ] = False,
    wait: Annotated[
        bool,
        typer.Option("--wait", help="Wait for instance to reach stopped state"),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Timeout in seconds when using --wait"),
    ] = DEFAULT_WAIT_TIMEOUT,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output format: table, json, yaml"),
    ] = None,
) -> None:
    """Stop a running instance."""
    state = _get_state()
    fmt = output or state.output
    stderr = _stderr(state)
    out = Console(no_color=state.no_color)

    # Non-interactive confirmation check
    if not confirm:
        if not sys.stdin.isatty():
            stderr.print(
                f'[red]Error:[/red] --confirm is required to stop an instance in non-interactive mode.\n'
                f'Add --confirm to proceed: doo-cli instances stop --name {name} --confirm'
            )
            raise typer.Exit(EXIT_USAGE)
        # TTY: prompt
        confirmed = typer.confirm(f'Stop instance "{name}"?', default=False)
        if not confirmed:
            out.print("Cancelled.")
            raise typer.Exit(EXIT_SUCCESS)

    try:
        with _make_client(state) as client:
            instance_id, inst_data = _resolve_instance_id(client, name)

            current_status = inst_data.get("status", "")
            if current_status == "stopped":
                stderr.print(f'[red]Error:[/red] Instance "{name}" is already stopped.')
                raise typer.Exit(EXIT_ERROR)

            result = client.stop_instance(instance_id)

            if not state.quiet:
                out.print(f'Stopping instance "[bold]{name}[/bold]"...')

            if wait:
                final = _wait_for_state(
                    client,
                    instance_id,
                    terminal_states={"stopped"},
                    error_states={"error", "failed"},
                    timeout=timeout,
                    state=state,
                )
                if final:
                    status = final.get("status", "unknown")
                    if status in {"error", "failed"}:
                        stderr.print(f"[red]Error:[/red] Instance reached error state: {status}")
                        raise typer.Exit(EXIT_ERROR)
                    if not state.quiet:
                        out.print(f'[yellow]Instance "[bold]{name}[/bold]" is {status}.[/yellow]')
                    output_data(
                        final,
                        fmt,
                        table_fn=lambda: print_instance_detail(final, no_color=state.no_color),
                        no_color=state.no_color,
                    )
            else:
                output_data(
                    result or inst_data,
                    fmt,
                    table_fn=lambda: print_instance_detail(result or inst_data, no_color=state.no_color),
                    no_color=state.no_color,
                )

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


@app.command("delete")
def instances_delete(
    name: Annotated[str, typer.Option("--name", help="Instance name/slug")],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Skip confirmation prompts (required in non-TTY)"),
    ] = False,
    wait: Annotated[
        bool,
        typer.Option("--wait", help="Wait for instance to be fully deleted"),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Timeout in seconds when using --wait"),
    ] = DEFAULT_WAIT_TIMEOUT,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output format: table, json, yaml"),
    ] = None,
) -> None:
    """Permanently delete an instance. This cannot be undone."""
    state = _get_state()
    stderr = _stderr(state)
    out = Console(no_color=state.no_color)

    # Non-interactive confirmation check
    if not confirm:
        if not sys.stdin.isatty():
            stderr.print(
                f'[red]Error:[/red] --confirm is required to delete an instance in non-interactive mode.\n'
                f'Add --confirm to proceed: doo-cli instances delete --name {name} --confirm'
            )
            raise typer.Exit(EXIT_USAGE)

        # TTY: double confirmation
        entered_name = typer.prompt(f'Type the instance name to confirm deletion')
        if entered_name != name:
            stderr.print("[red]Error:[/red] Instance name does not match. Deletion cancelled.")
            raise typer.Exit(EXIT_ERROR)

        confirmed = typer.confirm("This cannot be undone. Proceed?", default=False)
        if not confirmed:
            out.print("Cancelled.")
            raise typer.Exit(EXIT_SUCCESS)

    try:
        with _make_client(state) as client:
            instance_id, _ = _resolve_instance_id(client, name)
            client.delete_instance(instance_id)

            if not state.quiet:
                out.print(f'Deleting instance "[bold]{name}[/bold]"...')

            if wait:
                try:
                    _wait_for_state(
                        client,
                        instance_id,
                        terminal_states=set(),
                        error_states={"error", "failed"},
                        deleted=True,
                        timeout=timeout,
                        state=state,
                    )
                except NotFoundError:
                    pass  # Instance is gone — success

                if not state.quiet:
                    out.print(f'[green]Instance "[bold]{name}[/bold]" has been deleted.[/green]')
            else:
                if not state.quiet:
                    out.print(
                        f'Deletion of "[bold]{name}[/bold]" initiated. '
                        "Use --wait to poll until complete."
                    )

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
