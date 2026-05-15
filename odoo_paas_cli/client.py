"""httpx API client with auth and error handling for doo-cli."""

from __future__ import annotations

import sys
from typing import Any

import httpx

from .exceptions import (
    AuthError,
    CLIError,
    ConnectionError,
    NotFoundError,
    RateLimitError,
    UsageError,
)

CLI_VERSION = "1.0.0"
USER_AGENT = f"doo-cli/{CLI_VERSION}"
API_PREFIX = "/api"


class APIClient:
    """Synchronous httpx client wrapping the Odoo PaaS backend API."""

    def __init__(
        self,
        api_url: str,
        api_key: str | None,
        verbose: bool = False,
        no_color: bool = False,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.verbose = verbose
        self.no_color = no_color

        headers: dict[str, str] = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if api_key:
            headers["X-API-Key"] = api_key
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.Client(
            base_url=self.api_url,
            headers=headers,
            timeout=30.0,
        )

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[debug] {message}", file=sys.stderr)

    def _handle_response(self, response: httpx.Response) -> Any:
        """Raise appropriate CLI errors based on HTTP status."""
        self._log(f"<- {response.status_code} {response.url}")

        if response.status_code == 401:
            raise AuthError()

        if response.status_code == 404:
            try:
                detail = response.json().get("detail", "Resource not found")
            except Exception:
                detail = "Resource not found"
            raise NotFoundError(detail)

        if response.status_code == 422:
            try:
                body = response.json()
                detail = body.get("detail", body)
                if isinstance(detail, list):
                    msgs = [f"{'.'.join(str(l) for l in e.get('loc', []))}: {e.get('msg', '')}" for e in detail]
                    detail = "; ".join(msgs)
            except Exception:
                detail = response.text
            raise UsageError(f"Invalid request: {detail}")

        if response.status_code == 429:
            retry_after = None
            try:
                retry_after = int(response.headers.get("Retry-After", ""))
            except (ValueError, TypeError):
                pass
            raise RateLimitError(retry_after)

        if response.status_code >= 500:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise CLIError(f"API error: {response.status_code} {detail}")

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise CLIError(f"Request failed: {response.status_code} {detail}")

        return response

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = path if path.startswith("http") else path
        self._log(f"-> {method.upper()} {self.api_url}{url}")
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.ConnectError:
            raise ConnectionError(self.api_url)  # noqa: B904
        except httpx.TimeoutException:
            raise CLIError(f"Request timed out connecting to {self.api_url}")
        return self._handle_response(response)

    def get(self, path: str, **kwargs: Any) -> Any:
        resp = self._request("GET", path, **kwargs)
        try:
            return resp.json()
        except Exception:
            return resp.text

    def post(self, path: str, **kwargs: Any) -> Any:
        resp = self._request("POST", path, **kwargs)
        try:
            return resp.json()
        except Exception:
            return resp.text

    def delete(self, path: str, **kwargs: Any) -> Any:
        resp = self._request("DELETE", path, **kwargs)
        if resp.status_code == 204:
            return None
        try:
            return resp.json()
        except Exception:
            return resp.text

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "APIClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # --- Instance endpoints ---

    def list_instances(
        self,
        status: str | None = None,
        environment: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if environment:
            params["environment"] = environment
        result = self.get(f"{API_PREFIX}/instances/", params=params)
        if isinstance(result, dict):
            return result.get("instances", [])
        if isinstance(result, list):
            return result
        return []

    def get_instance(self, instance_id: str) -> dict[str, Any]:
        return self.get(f"{API_PREFIX}/instances/{instance_id}")

    def get_instance_by_slug(self, slug: str) -> dict[str, Any]:
        return self.get(f"{API_PREFIX}/instances/by-slug/{slug}")

    def create_instance(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post(f"{API_PREFIX}/instances/", json=payload)

    def start_instance(self, instance_id: str) -> dict[str, Any]:
        return self.post(f"{API_PREFIX}/instances/{instance_id}/start")

    def stop_instance(self, instance_id: str) -> dict[str, Any]:
        return self.post(f"{API_PREFIX}/instances/{instance_id}/stop")

    def delete_instance(self, instance_id: str) -> Any:
        return self.delete(f"{API_PREFIX}/instances/{instance_id}")

    # --- Backup endpoints ---

    def list_backups(self, instance_id: str) -> list[dict[str, Any]]:
        result = self.get(f"{API_PREFIX}/instances/{instance_id}/backups")
        return result if isinstance(result, list) else []

    def create_backup(self, instance_id: str, label: str | None = None) -> dict[str, Any]:
        payload = {"label": label} if label else {}
        result = self.post(f"{API_PREFIX}/instances/{instance_id}/backups", json=payload)
        return result if isinstance(result, dict) else {}

    def retry_backup(self, instance_id: str, backup_id: str) -> dict[str, Any]:
        result = self.post(f"{API_PREFIX}/instances/{instance_id}/backups/{backup_id}/retry")
        return result if isinstance(result, dict) else {}

    def delete_backup(self, instance_id: str, backup_id: str) -> Any:
        return self.delete(f"{API_PREFIX}/instances/{instance_id}/backups/{backup_id}")

    def restore_backup(self, instance_id: str, backup_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.post(f"{API_PREFIX}/instances/{instance_id}/backups/{backup_id}/restore", json=payload)
        return result if isinstance(result, dict) else {}

    def get_restore(self, instance_id: str, restore_id: str) -> dict[str, Any]:
        result = self.get(f"{API_PREFIX}/instances/{instance_id}/restores/{restore_id}")
        return result if isinstance(result, dict) else {}

    # --- Database insights endpoints ---

    def get_db_summary(self, instance_id: str) -> dict[str, Any]:
        result = self.get(f"{API_PREFIX}/instances/{instance_id}/database/summary")
        return result if isinstance(result, dict) else {}

    def get_db_slow_queries(self, instance_id: str, sort: str = "avg") -> dict[str, Any]:
        result = self.get(f"{API_PREFIX}/instances/{instance_id}/database/slow-queries", params={"sort": sort})
        return result if isinstance(result, dict) else {}

    def get_db_table_health(self, instance_id: str) -> dict[str, Any]:
        result = self.get(f"{API_PREFIX}/instances/{instance_id}/database/table-health")
        return result if isinstance(result, dict) else {}

    def get_db_size(self, instance_id: str) -> dict[str, Any]:
        result = self.get(f"{API_PREFIX}/instances/{instance_id}/database/size")
        return result if isinstance(result, dict) else {}

    # --- Log endpoints ---

    def query_logs(
        self,
        instance_id: str,
        *,
        query: str | None = None,
        level: str | None = None,
        vm: str | None = None,
        limit: int = 100,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if level:
            params["level"] = level
        if vm:
            params["vm"] = vm
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        result = self.get(f"{API_PREFIX}/instances/{instance_id}/logs", params=params)
        if not isinstance(result, dict):
            return []
        items = result.get("data", {}).get("result", [])
        entries: list[dict[str, Any]] = []
        for stream in items:
            labels = stream.get("stream", {})
            role = labels.get("role") or labels.get("service") or labels.get("job", "")
            for ts, message in stream.get("values", []):
                entries.append(
                    {
                        "timestamp": ts,
                        "level": labels.get("level", ""),
                        "vm": role,
                        "message": message,
                    }
                )
        entries.sort(key=lambda item: item.get("timestamp", ""))
        return entries

    # --- Metrics endpoints ---

    def get_metrics_summary(self, instance_id: str, metric: str = "all") -> dict[str, Any]:
        result = self.get(f"{API_PREFIX}/instances/{instance_id}/metrics/summary", params={"metric": metric})
        if isinstance(result, dict):
            return result
        return {}

    def whoami(self) -> dict[str, Any]:
        result = self.get(f"{API_PREFIX}/auth/whoami")
        if isinstance(result, dict):
            return result
        return {}
