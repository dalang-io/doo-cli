from __future__ import annotations

import pytest

from odoo_paas_cli.auth import _extract_login_error, _resolve_api_url_for_login
from odoo_paas_cli.exceptions import UsageError


def test_extract_login_error_returns_message():
    html = '<div class="rounded-md text-red-700">Invalid email or password.</div>'

    assert _extract_login_error(html) == "Invalid email or password."


def test_resolve_api_url_uses_configured_value():
    assert _resolve_api_url_for_login("https://api.example.com/") == "https://api.example.com/"


def test_resolve_api_url_requires_interactive_prompt(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    with pytest.raises(UsageError):
        _resolve_api_url_for_login(None)
