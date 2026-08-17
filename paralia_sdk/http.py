"""
Shared HTTP plumbing for every per-service client in this package. Every
Paralia app's network API (paradigm, parable, and future apps) already
speaks the same shape — FastAPI, an `X-Internal-Secret` header checked with
`secrets.compare_digest`, CORS restricted to known origins, JSON bodies —
because each was hand-copied from the last one. This class is that
convention made into one real implementation instead of a copy-paste
template, so a new app's client is a subclass, not a fresh file.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests


class ParaliaAPIError(Exception):
    """Raised for a non-2xx response. `status_code` is None for a transport-
    level failure (timeout, connection error) rather than an HTTP response."""

    def __init__(self, message: str, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class BaseClient:
    """One `requests.Session` per client instance, shared-secret auth header
    on every call, a single retry on transport-level failure (connection
    reset / timeout — not on 4xx/5xx, which are real answers, not glitches),
    and errors normalized to `ParaliaAPIError` so callers never need to
    branch on `requests` exception types directly.
    """

    def __init__(
        self,
        base_url: str,
        internal_secret: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 1,
    ):
        self.base_url = base_url.rstrip("/")
        self._secret = internal_secret if internal_secret is not None else os.environ.get(
            "API_INTERNAL_SECRET", ""
        )
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()

    def _headers(self, extra: Optional[dict] = None) -> dict:
        headers = {"X-Internal-Secret": self._secret}
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        data: Any = None,
        headers: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        attempt = 0
        last_exc: Optional[Exception] = None
        while attempt <= self.max_retries:
            try:
                resp = self._session.request(
                    method,
                    url,
                    json=json_body,
                    data=data,
                    headers=self._headers(headers),
                    timeout=timeout or self.timeout,
                )
                break
            except requests.RequestException as exc:
                last_exc = exc
                attempt += 1
                if attempt > self.max_retries:
                    raise ParaliaAPIError(f"{method} {url} failed: {exc}") from exc
        else:  # pragma: no cover - loop always breaks or raises
            raise ParaliaAPIError(f"{method} {url} failed: {last_exc}")

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            raise ParaliaAPIError(
                f"{method} {url} -> {resp.status_code}", status_code=resp.status_code, body=body
            )
        if not resp.content:
            return None
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return resp.json()
        return resp.content

    def get(self, path: str, **kw) -> Any:
        return self._request("GET", path, **kw)

    def post(self, path: str, **kw) -> Any:
        return self._request("POST", path, **kw)

    def delete(self, path: str, **kw) -> Any:
        return self._request("DELETE", path, **kw)
