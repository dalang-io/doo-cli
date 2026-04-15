from __future__ import annotations

import pytest

from odoo_paas_cli.config import get_api_url, peek_api_url
from odoo_paas_cli.exceptions import UsageError


def test_get_api_url_prefers_environment(monkeypatch):
    monkeypatch.setenv("ODOO_PAAS_API_URL", "https://env.example.com/api/")

    url = get_api_url({"profiles": {"default": {"api_url": "https://config.example.com/api"}}})

    assert url == "https://env.example.com/api"


def test_get_api_url_raises_when_missing():
    with pytest.raises(UsageError):
        get_api_url({"profiles": {"default": {}}})


def test_peek_api_url_returns_none_when_missing():
    assert peek_api_url({"profiles": {"default": {}}}) is None
