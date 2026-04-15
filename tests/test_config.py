from __future__ import annotations

from odoo_paas_cli.config import get_api_url, peek_api_url
from odoo_paas_cli.config import DEFAULT_API_URL


def test_get_api_url_prefers_environment(monkeypatch):
    url = get_api_url({"api_url": "https://config.example.com/api"}, override="https://override.example.com/api/")

    assert url == "https://override.example.com/api"


def test_get_api_url_uses_default_when_missing():
    assert get_api_url({}) == DEFAULT_API_URL


def test_peek_api_url_returns_default_when_missing():
    assert peek_api_url({}) == DEFAULT_API_URL
