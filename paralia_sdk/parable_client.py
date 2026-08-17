"""
Typed client for parable's hosted job-queue API (`parable/parable/io/api.py`)
— the async generate/perturb/run/evaluate job runner. Used by Website's
server-side proxy routes (`Website/src/pages/api/parable/*`) instead of each
route hand-rolling its own `fetch()` + `X-Internal-Secret` header, and
available to any future caller that needs to kick off a parable run
programmatically.
"""

from __future__ import annotations

from .http import BaseClient


class ParableClient(BaseClient):
    def health(self) -> bool:
        try:
            return bool(self.get("/health", timeout=5.0).get("ok"))
        except Exception:
            return False

    def list_runs(self) -> list[dict]:
        return self.get("/runs")

    def create_run(self, config: dict) -> str:
        return self.post("/runs", json_body=config)["run_id"]

    def create_sweep(self, config: dict) -> str:
        return self.post("/sweeps", json_body=config)["run_id"]

    def run_status(self, run_id: str) -> dict:
        return self.get(f"/runs/{run_id}/status")

    def cancel_run(self, run_id: str) -> None:
        self.post(f"/runs/{run_id}/cancel")

    def delete_run(self, run_id: str) -> None:
        self.delete(f"/runs/{run_id}")

    def run_data(self, run_id: str, path: str) -> bytes:
        return self.get(f"/runs/{run_id}/data/{path}")
