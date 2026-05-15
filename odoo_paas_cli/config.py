"""Config file read/write for ~/.config/doo-cli/config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_URL = "https://app.odoo.dalang.io"
CONFIG_DIR = Path.home() / ".config" / "doo-cli"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def _default_config() -> dict[str, Any]:
    return {
        "version": 1,
        "api_url": DEFAULT_API_URL,
    }


def load_config() -> dict[str, Any]:
    """Load config from disk. Returns default config if file does not exist."""
    if not CONFIG_FILE.exists():
        return _default_config()

    # Warn if permissions are too broad
    mode = CONFIG_FILE.stat().st_mode & 0o777
    if mode & 0o077:
        import sys
        print(
            f"Warning: config file {CONFIG_FILE} has permissions {oct(mode)}. "
            "Consider running: chmod 600 ~/.config/doo-cli/config.yaml",
            file=sys.stderr,
        )

    with CONFIG_FILE.open("r") as f:
        data = yaml.safe_load(f) or {}

    # Backward compatibility: flatten the legacy single default profile layout.
    profiles = data.get("profiles")
    if isinstance(profiles, dict):
        default_profile_name = data.get("default_profile", "default")
        default_profile = profiles.get(default_profile_name) or profiles.get("default") or {}
        if "api_key" not in data and "api_key" in default_profile:
            data["api_key"] = default_profile["api_key"]
        if "api_url" not in data and "api_url" in default_profile:
            data["api_url"] = default_profile["api_url"]
        if "default_instance" not in data and "default_instance" in default_profile:
            data["default_instance"] = default_profile["default_instance"]
        if "default_output" not in data and "default_output" in default_profile:
            data["default_output"] = default_profile["default_output"]
        data.pop("profiles", None)
        data.pop("default_profile", None)

    if "version" not in data:
        data["version"] = 1
    if "api_url" not in data:
        data["api_url"] = DEFAULT_API_URL

    return data


def save_config(config: dict[str, Any]) -> None:
    """Persist config to disk with 0600 permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(yaml.dump(config, default_flow_style=False))
    CONFIG_FILE.chmod(0o600)


def get_api_key(config: dict[str, Any]) -> str | None:
    """Return the locally stored API key."""
    return config.get("api_key")


def get_api_url(config: dict[str, Any], override: str | None = None) -> str:
    """Return the API URL, with CLI flag taking priority."""
    if override:
        return override.rstrip("/")
    api_url = config.get("api_url")
    if api_url:
        return str(api_url).rstrip("/")
    return DEFAULT_API_URL


def peek_api_url(
    config: dict[str, Any],
    override: str | None = None,
) -> str | None:
    """Return the resolved API URL."""
    return get_api_url(config, override)


def set_config_key(key: str, value: Any) -> None:
    """Set a single config key and persist."""
    config = load_config()
    config[key] = value
    save_config(config)
