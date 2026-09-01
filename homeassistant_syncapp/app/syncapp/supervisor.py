from __future__ import annotations

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class SupervisorError(RuntimeError):
    pass


class SupervisorClient:
    def __init__(self, token: str | None = None, base_url: str = "http://supervisor"):
        self.token = token or os.environ.get("SUPERVISOR_TOKEN")
        self.base_url = base_url.rstrip("/")
        if not self.token:
            raise SupervisorError("SUPERVISOR_TOKEN is not available")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        timeout: int = 120,
    ) -> dict:
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
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            suffix = f": {detail}" if detail else ""
            raise SupervisorError(
                f"Supervisor request {path} failed with HTTP {exc.code}{suffix}"
            ) from exc
        except URLError as exc:
            raise SupervisorError(f"Supervisor request {path} failed: {exc}") from exc
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise SupervisorError(f"Supervisor request {path} returned invalid JSON") from exc

    @staticmethod
    def _unwrap(response: dict, operation: str) -> dict:
        if "result" not in response:
            return response
        if response.get("result") != "ok":
            raise SupervisorError(
                f"Supervisor {operation} failed: {response.get('message', response)!r}"
            )
        data = response.get("data", {})
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise SupervisorError(f"Supervisor {operation} returned unexpected data")
        return data

    @staticmethod
    def _safe_backup_slug(slug: str) -> str:
        if not slug or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in slug
        ):
            raise SupervisorError("refusing invalid backup slug")
        return quote(slug, safe="")

    def check_core_configuration(self) -> dict:
        return self._unwrap(
            self._request("POST", "/core/check", {}),
            "Core configuration check",
        )

    def create_homeassistant_backup(self, name: str) -> str:
        data = self._unwrap(
            self._request(
                "POST",
                "/backups/new/partial",
                {
                    "name": name,
                    "homeassistant": True,
                    "homeassistant_exclude_database": True,
                    "background": False,
                },
                timeout=900,
            ),
            "Home Assistant backup",
        )
        slug = data.get("slug")
        if not isinstance(slug, str) or not slug:
            raise SupervisorError("Supervisor backup response did not include a slug")
        return slug

    def list_backups(self) -> list[dict]:
        data = self._unwrap(self._request("GET", "/backups"), "backup inventory")
        backups = data.get("backups", [])
        if not isinstance(backups, list) or not all(
            isinstance(item, dict) for item in backups
        ):
            raise SupervisorError("Supervisor backup inventory returned unexpected data")
        return list(backups)

    def backup_info(self, slug: str) -> dict:
        encoded = self._safe_backup_slug(slug)
        return self._unwrap(
            self._request("GET", f"/backups/{encoded}/info"),
            f"backup information {slug}",
        )

    def verify_homeassistant_backup(
        self,
        slug: str,
        expected_name: str,
    ) -> dict[str, object]:
        """Fail closed unless Supervisor proves the requested HA backup exists."""
        matches = [item for item in self.list_backups() if item.get("slug") == slug]
        if len(matches) != 1:
            raise SupervisorError(
                "Supervisor backup inventory did not contain exactly one entry for "
                f"newly created backup slug {slug!r}"
            )

        backup = matches[0]
        if backup.get("name") != expected_name:
            raise SupervisorError(
                "Supervisor backup inventory entry name did not match the backup request"
            )
        if backup.get("type") != "partial":
            raise SupervisorError(
                "Supervisor backup inventory entry was not the requested partial backup"
            )
        content = backup.get("content")
        if not isinstance(content, dict) or content.get("homeassistant") is not True:
            raise SupervisorError(
                "Supervisor backup inventory does not prove the backup contains Home Assistant data"
            )

        details = self.backup_info(slug)
        if details.get("slug") != slug:
            raise SupervisorError("Supervisor backup detail slug did not match the created backup")
        if details.get("name") != expected_name:
            raise SupervisorError("Supervisor backup detail name did not match the backup request")
        if details.get("type") != "partial":
            raise SupervisorError("Supervisor backup details did not report a partial backup")
        homeassistant_version = details.get("homeassistant")
        if not isinstance(homeassistant_version, str) or not homeassistant_version.strip():
            raise SupervisorError(
                "Supervisor backup details did not prove Home Assistant content is present"
            )
        if details.get("homeassistant_exclude_database") is not True:
            raise SupervisorError(
                "Supervisor backup details did not confirm Home Assistant database exclusion"
            )

        evidence: dict[str, object] = {
            "slug": slug,
            "name_matches_request": True,
            "type": "partial",
            "inventory_verified": True,
            "homeassistant_content_verified": True,
            "homeassistant_version": homeassistant_version,
            "homeassistant_database_excluded": True,
            "detail_verified": True,
        }
        for field in ("date", "protected"):
            if field in backup:
                evidence[field] = backup[field]
        return evidence

    def delete_backup(self, slug: str) -> None:
        encoded = self._safe_backup_slug(slug)
        self._unwrap(
            self._request("DELETE", f"/backups/{encoded}"),
            f"backup deletion {slug}",
        )

    def restart_core(self) -> None:
        self._unwrap(self._request("POST", "/core/restart", {}), "Core restart")

    def core_info(self) -> dict:
        return self._unwrap(self._request("GET", "/core/info"), "Core info")

    def supervisor_info(self) -> dict:
        return self._unwrap(
            self._request("GET", "/supervisor/info"),
            "Supervisor info",
        )

    def host_info(self) -> dict:
        return self._unwrap(self._request("GET", "/host/info"), "host info")

    def core_api_health(self, *, timeout: int = 10) -> dict:
        response = self._request("GET", "/core/api/", timeout=timeout)
        data = self._unwrap(response, "Core API health check")
        if data.get("message") != "API running.":
            raise SupervisorError(
                f"Home Assistant Core API returned an unexpected health response: {data!r}"
            )
        return data

    def wait_for_core_api(
        self,
        timeout_seconds: int,
        poll_seconds: float = 2.0,
    ) -> dict:
        deadline = time.monotonic() + timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return self.core_api_health(timeout=max(1, min(10, timeout_seconds)))
            except SupervisorError as exc:
                last_error = exc
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(poll_seconds, remaining))
        raise SupervisorError(
            f"Home Assistant Core API did not become healthy within {timeout_seconds}s"
            + (f": {last_error}" if last_error else "")
        )
