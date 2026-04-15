"""Auth commands: login, logout, status, list-profiles, use-profile."""

from __future__ import annotations

import re
import sys
from typing import Annotated, Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich import box

from .client import APIClient, USER_AGENT
from .config import (
    get_api_key,
    peek_api_url,
    load_config,
    save_config,
    set_profile_key,
)
from .exceptions import EXIT_SUCCESS, EXIT_ERROR, UsageError

app = typer.Typer(
    help="Manage authentication credentials and profiles.",
    no_args_is_help=True,
)


def _mask_key(key: str) -> str:
    """Mask API key showing only the last 4 characters."""
    if len(key) <= 4:
        return "****"
    return f"****{key[-4:]}"


def _get_state() -> "GlobalState":  # type: ignore[name-defined]
    from .main import state
    return state


def _resolve_api_url_for_login(configured_url: str | None) -> str:
    if configured_url:
        return configured_url
    if not sys.stdin.isatty():
        raise UsageError(
            "API URL is not configured. Set `ODOO_PAAS_API_URL`, pass `--api-url`, "
            "or run `doo-cli config set api-url <url>`."
        )
    return typer.prompt("API URL", default="https://api.paas.example.com").rstrip("/")


def _extract_login_error(html: str) -> str | None:
    match = re.search(r'<div class="[^"]*text-red-700[^"]*">\s*(.*?)\s*</div>', html, re.DOTALL)
    if not match:
        return None
    message = re.sub(r"<[^>]+>", "", match.group(1))
    return " ".join(message.split())


def _mint_api_key_from_password_login(
    api_url: str,
    email: str,
    password: str,
    key_name: str,
    scope: str,
    expires_in_days: int | None,
) -> tuple[str, dict]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html",
    }
    with httpx.Client(base_url=api_url, headers=headers, timeout=30.0, follow_redirects=False) as client:
        login_page = client.get("/login")
        login_page.raise_for_status()

        csrf_token = client.cookies.get("csrf_token")
        if not csrf_token:
            raise UsageError("Login failed: missing CSRF token from the server.")

        login_response = client.post(
            "/login",
            headers={"X-CSRF-Token": csrf_token, "HX-Request": "true"},
            data={
                "email": email,
                "password": password,
                "next": "",
                "csrf_token": csrf_token,
            },
        )
        login_response.raise_for_status()

        if not client.cookies.get("session"):
            detail = _extract_login_error(login_response.text) or "Invalid email or password."
            raise UsageError(detail)

        payload: dict[str, object] = {"name": key_name, "scope": scope}
        if expires_in_days is not None:
            payload["expires_in_days"] = expires_in_days

        key_response = client.post("/api/auth/api-keys", json=payload)
        key_response.raise_for_status()
        body = key_response.json()
        api_key = body.get("api_key")
        if not isinstance(api_key, str) or not api_key:
            raise UsageError("Login succeeded, but the API did not return an API key.")

        whoami_response = client.get(
            "/api/auth/whoami",
            headers={"X-API-Key": api_key, "Authorization": f"Bearer {api_key}"},
        )
        whoami_response.raise_for_status()
        return api_key, whoami_response.json()


@app.command("login")
def auth_login(
    api_key: Annotated[
        Optional[str],
        typer.Option("--api-key", help="Store an existing API key instead of logging in with email/password"),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", help="Profile name to store the key under"),
    ] = None,
    email: Annotated[
        Optional[str],
        typer.Option("--email", help="Account email for user login"),
    ] = None,
    password: Annotated[
        Optional[str],
        typer.Option("--password", help="Account password for non-interactive login"),
    ] = None,
    name: Annotated[
        str,
        typer.Option("--name", help="Name for the generated API key"),
    ] = "doo-cli",
    scope: Annotated[
        str,
        typer.Option("--scope", help="Generated API key scope: read_write or read_only"),
    ] = "read_write",
    expires_in_days: Annotated[
        Optional[int],
        typer.Option("--expires-in-days", help="Optional expiry for the generated API key"),
    ] = None,
) -> None:
    """Log in with email/password, generate an API key, and store it locally."""
    state = _get_state()
    profile_name = profile or state.profile or "default"
    console = Console(no_color=state.no_color, stderr=True)
    out = Console(no_color=state.no_color)
    config = load_config()
    configured_api_url = peek_api_url(config, profile_name, state.api_url)

    if scope not in {"read_write", "read_only"}:
        console.print("[red]Error:[/red] --scope must be either `read_write` or `read_only`.")
        raise typer.Exit(2)

    try:
        api_url = _resolve_api_url_for_login(configured_api_url)
    except UsageError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2)

    whoami: dict
    generated_key = False

    if api_key is None:
        if email is None:
            if not sys.stdin.isatty():
                console.print("[red]Error:[/red] `--email` is required in non-interactive mode.")
                raise typer.Exit(2)
            email = typer.prompt("Email")
        if password is None:
            if not sys.stdin.isatty():
                console.print("[red]Error:[/red] `--password` is required in non-interactive mode.")
                raise typer.Exit(2)
            password = typer.prompt("Password", hide_input=True)
        if not email or not password:
            console.print("[red]Error:[/red] Email and password are required.")
            raise typer.Exit(EXIT_ERROR)
        try:
            api_key, whoami = _mint_api_key_from_password_login(
                api_url=api_url,
                email=email,
                password=password,
                key_name=name,
                scope=scope,
                expires_in_days=expires_in_days,
            )
            generated_key = True
        except httpx.HTTPStatusError as exc:
            console.print(
                f"[red]Error:[/red] Authentication failed: {exc.response.status_code} {exc.response.reason_phrase}"
            )
            raise typer.Exit(EXIT_ERROR)
        except (httpx.HTTPError, UsageError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(EXIT_ERROR)
    else:
        if not api_key:
            console.print("[red]Error:[/red] API key cannot be empty.")
            raise typer.Exit(EXIT_ERROR)
        try:
            with APIClient(api_url, api_key, verbose=state.verbose, no_color=state.no_color) as client:
                whoami = client.whoami()
        except Exception as exc:
            console.print(f"[red]Error:[/red] API key validation failed: {exc}")
            raise typer.Exit(EXIT_ERROR)

    set_profile_key(profile_name, "api_key", api_key)
    set_profile_key(profile_name, "api_url", api_url)

    if not state.quiet:
        if generated_key:
            out.print(
                f"[green]Logged in.[/green] Generated and stored an API key for profile "
                f"'[bold]{profile_name}[/bold]' ({_mask_key(api_key)})."
            )
        else:
            out.print(
                f"[green]Logged in.[/green] API key stored in profile '[bold]{profile_name}[/bold]' "
                f"({_mask_key(api_key)})."
            )
        tenant = whoami.get("tenant", {}).get("slug")
        if tenant:
            out.print(f"Tenant: {tenant}")


@app.command("logout")
def auth_logout(
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", help="Profile to log out of"),
    ] = None,
) -> None:
    """Remove stored credentials for a profile."""
    state = _get_state()
    profile_name = profile or state.profile or "default"
    console = Console(no_color=state.no_color, stderr=True)
    out = Console(no_color=state.no_color)

    config = load_config()
    profiles = config.get("profiles", {})

    if profile_name not in profiles:
        console.print(f"[yellow]No profile named '{profile_name}' found.[/yellow]")
        raise typer.Exit(EXIT_SUCCESS)

    # Remove just the api_key, keep other profile settings
    profiles[profile_name].pop("api_key", None)
    save_config(config)

    if not state.quiet:
        out.print(f"[green]Logged out[/green] of profile '[bold]{profile_name}[/bold]'.")


@app.command("status")
def auth_status() -> None:
    """Show the currently active API key and profile."""
    state = _get_state()
    config = load_config()
    profile_name = state.profile or config.get("default_profile", "default")
    api_key = get_api_key(config, profile_name)
    api_url = peek_api_url(config, profile_name, state.api_url)

    out = Console(no_color=state.no_color)

    if not api_key:
        out.print(
            f"[yellow]Not logged in.[/yellow] No API key found for profile '[bold]{profile_name}[/bold]'.\n"
            "Run [bold]doo-cli auth login[/bold] to set up credentials."
        )
        raise typer.Exit(EXIT_ERROR)

    masked = _mask_key(api_key)
    out.print(f"Profile:  [bold]{profile_name}[/bold]")
    out.print(f"API Key:  {masked}")
    out.print(f"API URL:  {api_url or 'not configured'}")


@app.command("list-profiles")
def auth_list_profiles() -> None:
    """List all named credential profiles."""
    state = _get_state()
    config = load_config()
    profiles = config.get("profiles", {})
    default_profile = config.get("default_profile", "default")

    out = Console(no_color=state.no_color)

    if not profiles:
        out.print("No profiles configured.")
        return

    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("PROFILE")
    table.add_column("DEFAULT")
    table.add_column("API KEY")
    table.add_column("API URL")

    for name, data in profiles.items():
        key = data.get("api_key", "")
        url = data.get("api_url", "")
        is_default = "[green]yes[/green]" if name == default_profile else ""
        masked = _mask_key(key) if key else "[dim]not set[/dim]"
        table.add_row(name, is_default, masked, url)

    out.print(table)


@app.command("use-profile")
def auth_use_profile(
    name: Annotated[str, typer.Argument(help="Profile name to make default")],
) -> None:
    """Set the default profile."""
    state = _get_state()
    config = load_config()
    out = Console(no_color=state.no_color)

    if name not in config.get("profiles", {}):
        Console(stderr=True, no_color=state.no_color).print(
            f"[red]Error:[/red] Profile '[bold]{name}[/bold]' does not exist.\n"
            "Run [bold]doo-cli auth list-profiles[/bold] to see available profiles."
        )
        raise typer.Exit(EXIT_ERROR)

    config["default_profile"] = name
    save_config(config)

    if not state.quiet:
        out.print(f"[green]Default profile set to '[bold]{name}[/bold]'.[/green]")
