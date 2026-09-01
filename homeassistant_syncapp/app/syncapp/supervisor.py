from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SupervisorError(RuntimeError):
    pass


class SupervisorClient:
    def __init__(self, token: str | None = None, base_url: str = "http://supervisor"):
        self.token = token or os.environ.get("SUPERVISOR_TOKEN")
        self.base_url = base_url.rstrip("/")
        if not self.token:
            raise SupervisorError("SUPERVISOR_TOKEN is not available")

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
        except (HTTPError, URLError) as exc:
            raise SupervisorError(f"Supervisor request {path} failed: {exc}") from exc
        return json.loads(raw) if raw else {}

    def check_core_configuration(self) -> dict:
        return self._request("POST", "/core/check", {})

    def create_homeassistant_backup(self, name: str) -> dict:
        return self._request(
            "POST",
            "/backups/new/partial",
            {
                "name": name,
                "homeassistant": True,
                "homeassistant_exclude_database": True,
                "background": False,
            },
        )

    def restart_core(self) -> dict:
        return self._request("POST", "/core/restart", {})

    def core_info(self) -> dict:
        return self._request("GET", "/core/info")
