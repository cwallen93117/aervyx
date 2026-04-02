"""Aervyx REST API client for the audit import workflow."""
from __future__ import annotations

import time
from pathlib import Path

import requests


class ApiError(Exception):
    def __init__(self, status: int, detail: str, url: str = ""):
        self.status = status
        self.detail = detail
        self.url = url
        super().__init__(f"HTTP {status} {url}: {detail}")


class AervyxClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.token: str = ""

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/auth/login",
            json={"username": self.username, "password": self.password},
        )
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text, "/api/auth/login")
        data = resp.json()
        self.token = data["access_token"]
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        return data

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, retries: int = 2, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        for attempt in range(retries + 1):
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code >= 500 and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return resp
        return resp  # type: ignore[return-value]

    def _get(self, path: str, **kwargs) -> dict | list:
        resp = self._request("GET", path, **kwargs)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text, path)
        return resp.json()

    def _post(self, path: str, **kwargs) -> dict | list:
        resp = self._request("POST", path, **kwargs)
        if resp.status_code not in (200, 201):
            raise ApiError(resp.status_code, resp.text, path)
        return resp.json()

    def _put(self, path: str, **kwargs) -> dict | list:
        resp = self._request("PUT", path, **kwargs)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text, path)
        return resp.json()

    def _delete(self, path: str) -> None:
        resp = self._request("DELETE", path)
        if resp.status_code not in (200, 204):
            raise ApiError(resp.status_code, resp.text, path)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def list_events(self) -> list[dict]:
        return self._get("/api/events")

    def create_event(self, payload: dict) -> dict:
        return self._post("/api/events", json=payload)

    def get_event(self, event_id: int) -> dict:
        return self._get(f"/api/events/{event_id}")

    # ------------------------------------------------------------------
    # Pilots
    # ------------------------------------------------------------------

    def list_all_pilots(self) -> list[dict]:
        return self._get("/api/pilots")

    def list_event_pilots(self, event_id: int) -> list[dict]:
        return self._get(f"/api/events/{event_id}/pilots")

    def create_pilot(self, event_id: int, payload: dict) -> dict:
        return self._post(f"/api/events/{event_id}/pilots", json=payload)

    def assign_pilot(self, event_id: int, pilot_id: int) -> dict:
        return self._post(f"/api/events/{event_id}/pilots/{pilot_id}/assign")

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def list_tasks(self, event_id: int) -> list[dict]:
        return self._get(f"/api/events/{event_id}/tasks")

    def create_task(self, event_id: int, payload: dict) -> dict:
        return self._post(f"/api/events/{event_id}/tasks", json=payload)

    def publish_task(self, task_id: int) -> dict:
        return self._post(f"/api/tasks/{task_id}/publish")

    # ------------------------------------------------------------------
    # Uploads
    # ------------------------------------------------------------------

    def bulk_upload_igc(self, task_id: int, file_paths: list[Path]) -> list[dict]:
        files = []
        for fp in file_paths:
            files.append(("files", (fp.name, fp.read_bytes(), "application/octet-stream")))
        resp = self._request(
            "POST",
            f"/api/tasks/{task_id}/uploads/bulk",
            files=files,
            timeout=120,
        )
        if resp.status_code not in (200, 201):
            raise ApiError(resp.status_code, resp.text, f"/api/tasks/{task_id}/uploads/bulk")
        return resp.json()

    def upload_single_igc(self, task_id: int, file_path: Path, pilot_id: int) -> dict:
        """Upload a single IGC file for a specific pilot."""
        resp = self._request(
            "POST",
            f"/api/tasks/{task_id}/uploads",
            files=[("file", (file_path.name, file_path.read_bytes(), "application/octet-stream"))],
            data={"pilot_id": str(pilot_id)},
            timeout=60,
        )
        if resp.status_code not in (200, 201):
            raise ApiError(resp.status_code, resp.text, f"/api/tasks/{task_id}/uploads")
        return resp.json()

    def list_uploads(self, task_id: int) -> list[dict]:
        return self._get(f"/api/tasks/{task_id}/uploads")

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def get_scoring_operations(self, task_id: int) -> dict:
        return self._get(f"/api/tasks/{task_id}/scoring-operations")

    def update_scoring_operations(self, task_id: int, payload: dict) -> dict:
        return self._post(f"/api/tasks/{task_id}/scoring-operations", json=payload)

    def rescore_task(self, task_id: int) -> list[dict]:
        return self._post(f"/api/tasks/{task_id}/rescore")

    def get_task_results(self, task_id: int) -> list[dict]:
        return self._get(f"/api/tasks/{task_id}/results")
