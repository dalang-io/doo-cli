from __future__ import annotations

import json

from odoo_paas_cli.client import APIClient
from odoo_paas_cli.output import print_json


def test_cli_list_instances_unwraps_response(monkeypatch):
    client = APIClient("http://example.test", "test-key")
    monkeypatch.setattr(
        client,
        "get",
        lambda path, **kwargs: {
            "instances": [
                {"id": "inst-1", "name": "alpha"},
                {"id": "inst-2", "name": "beta"},
            ],
            "total": 2,
        },
    )

    assert client.list_instances() == [
        {"id": "inst-1", "name": "alpha"},
        {"id": "inst-2", "name": "beta"},
    ]


def test_cli_query_logs_flattens_loki_response(monkeypatch):
    client = APIClient("http://example.test", "test-key")
    monkeypatch.setattr(
        client,
        "get",
        lambda path, **kwargs: {
            "data": {
                "result": [
                    {
                        "stream": {"role": "app", "level": "info"},
                        "values": [["1710000000000000000", "started"], ["1710000001000000000", "ready"]],
                    }
                ]
            }
        },
    )

    assert client.query_logs("instance-1") == [
        {
            "timestamp": "1710000000000000000",
            "level": "info",
            "vm": "app",
            "message": "started",
        },
        {
            "timestamp": "1710000001000000000",
            "level": "info",
            "vm": "app",
            "message": "ready",
        },
    ]


def test_cli_print_json_is_minified(capsys):
    print_json({"name": "alpha", "count": 2})
    output = capsys.readouterr().out.strip()
    assert output == json.dumps({"name": "alpha", "count": 2}, separators=(",", ":"))


def test_cli_get_metrics_summary_passes_metric_param(monkeypatch):
    client = APIClient("http://example.test", "test-key")
    captured: dict[str, object] = {}

    def fake_get(path: str, **kwargs):
        captured["path"] = path
        captured["params"] = kwargs.get("params")
        return {"instance_id": "inst-1", "metric": "cpu", "roles": {"app": {"cpu": 42.0}}}

    monkeypatch.setattr(client, "get", fake_get)

    result = client.get_metrics_summary("inst-1", metric="cpu")

    assert captured["path"] == "/instances/inst-1/metrics/summary"
    assert captured["params"] == {"metric": "cpu"}
    assert result["metric"] == "cpu"


def test_cli_list_backups_uses_instance_backup_endpoint(monkeypatch):
    client = APIClient("http://example.test", "test-key")
    captured: dict[str, object] = {}

    def fake_get(path: str, **kwargs):
        captured["path"] = path
        return [{"id": "backup-1", "status": "completed"}]

    monkeypatch.setattr(client, "get", fake_get)
    result = client.list_backups("inst-1")

    assert captured["path"] == "/instances/inst-1/backups"
    assert result[0]["id"] == "backup-1"


def test_cli_restore_backup_posts_expected_payload(monkeypatch):
    client = APIClient("http://example.test", "test-key")
    captured: dict[str, object] = {}

    def fake_post(path: str, **kwargs):
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return {"id": "restore-1", "status": "pending"}

    monkeypatch.setattr(client, "post", fake_post)
    result = client.restore_backup(
        "inst-1",
        "backup-1",
        {"name": "restore-alpha", "vm_topology": "single", "single_vcpus": 2, "single_ram_mb": 4096, "single_disk_gb": 40},
    )

    assert captured["path"] == "/instances/inst-1/backups/backup-1/restore"
    assert captured["json"]["name"] == "restore-alpha"
    assert result["status"] == "pending"
