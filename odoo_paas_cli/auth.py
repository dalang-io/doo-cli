"""Auth commands: login, logout, status."""

from __future__ import annotations

import re
import sys
from typing import Annotated, Optional

import httpx
import typer
from rich.console import Console
from .client import APIClient, USER_AGENT
from .config import (
    DEFAULT_API_URL,
    get_api_key,
    peek_api_url,
    load_config,
    save_config,
    set_config_key,
)
from .exceptions import EXIT_SUCCESS, EXIT_ERROR, UsageError

app = typer.Typer(
    help="Manage authentication credentials.",
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
    return DEFAULT_API_URL


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
    console = Console(no_color=state.no_color, stderr=True)
    out = Console(no_color=state.no_color)
    config = load_config()
    configured_api_url = peek_api_url(config, state.api_url)

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

    set_config_key("api_key", api_key)
    set_config_key("api_url", api_url)

    if not state.quiet:
        if generated_key:
            out.print(
                f"[green]Logged in.[/green] Generated and stored an API key ({_mask_key(api_key)})."
            )
        else:
            out.print(f"[green]Logged in.[/green] API key stored ({_mask_key(api_key)}).")
        tenant = whoami.get("tenant", {}).get("slug")
        if tenant:
            out.print(f"Tenant: {tenant}")


@app.command("logout")
def auth_logout(
) -> None:
    """Remove stored credentials."""
    state = _get_state()
    out = Console(no_color=state.no_color)

    config = load_config()
    config.pop("api_key", None)
    save_config(config)

    if not state.quiet:
        out.print("[green]Logged out.[/green]")


@app.command("status")
def auth_status() -> None:
    """Show the current authentication status."""
    state = _get_state()
    config = load_config()
    api_key = get_api_key(config)
    api_url = peek_api_url(config, state.api_url)

    out = Console(no_color=state.no_color)

    if not api_key:
        out.print(
            "[yellow]Not logged in.[/yellow] No API key stored locally.\n"
            "Run [bold]doo-cli auth login[/bold] to set up credentials."
        )
        raise typer.Exit(EXIT_ERROR)

    masked = _mask_key(api_key)
    out.print(f"API Key:  {masked}")
    out.print(f"API URL:  {api_url}")
