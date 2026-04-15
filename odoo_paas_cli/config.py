"""Config file read/write for ~/.config/doo-cli/config.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .exceptions import UsageError

load_dotenv()

CONFIG_DIR = Path.home() / ".config" / "doo-cli"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def _default_config() -> dict[str, Any]:
    return {
        "version": 1,
        "default_profile": "default",
        "profiles": {
            "default": {}
        },
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

    # Merge with defaults so new keys are always present
    if "version" not in data:
        data["version"] = 1
    if "default_profile" not in data:
        data["default_profile"] = "default"
    if "profiles" not in data:
        data["profiles"] = {}

    return data


def save_config(config: dict[str, Any]) -> None:
    """Persist config to disk with 0600 permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(yaml.dump(config, default_flow_style=False))
    CONFIG_FILE.chmod(0o600)


def get_profile(config: dict[str, Any], profile_name: str | None = None) -> dict[str, Any]:
    """Return the named profile dict (or the default profile)."""
    # Env var takes top priority for profile selection
    if profile_name is None:
        profile_name = os.environ.get("ODOO_PAAS_PROFILE")
    if profile_name is None:
        profile_name = config.get("default_profile", "default")

    profiles = config.get("profiles", {})
    return profiles.get(profile_name) or {}


def get_api_key(config: dict[str, Any], profile_name: str | None = None) -> str | None:
    """Return the API key, respecting env var override."""
    env_key = os.environ.get("ODOO_PAAS_API_KEY")
    if env_key:
        return env_key
    profile = get_profile(config, profile_name)
    return profile.get("api_key")


def get_api_url(config: dict[str, Any], profile_name: str | None = None, override: str | None = None) -> str:
    """Return the API URL, with env var and CLI flag taking priority."""
    if override:
        return override.rstrip("/")
    env_url = os.environ.get("ODOO_PAAS_API_URL")
    if env_url:
        return env_url.rstrip("/")
    profile = get_profile(config, profile_name)
    profile_url = profile.get("api_url")
    if profile_url:
        return str(profile_url).rstrip("/")
    raise UsageError(
        "API URL is not configured. Set `ODOO_PAAS_API_URL`, pass `--api-url`, "
        "or run `doo-cli config set api-url <url>`."
    )


def peek_api_url(
    config: dict[str, Any],
    profile_name: str | None = None,
    override: str | None = None,
) -> str | None:
    """Return the resolved API URL, or None when no URL is configured."""
    try:
        return get_api_url(config, profile_name, override)
    except UsageError:
        return None


def set_profile_key(profile_name: str, key: str, value: Any) -> None:
    """Set a key in a named profile and persist."""
    config = load_config()
    if profile_name not in config["profiles"]:
        config["profiles"][profile_name] = {}
    config["profiles"][profile_name][key] = value
    save_config(config)


def remove_profile(profile_name: str) -> None:
    """Remove a profile and persist."""
    config = load_config()
    config.get("profiles", {}).pop(profile_name, None)
    save_config(config)


def set_config_value(key: str, value: str) -> None:
    """Set a top-level or profile config value (e.g. default-profile, api-url)."""
    config = load_config()
    # Normalize key
    normalized = key.replace("-", "_")
    config[normalized] = value
    save_config(config)


def unset_config_value(key: str) -> None:
    """Unset a top-level config key."""
    config = load_config()
    normalized = key.replace("-", "_")
    config.pop(normalized, None)
    save_config(config)
