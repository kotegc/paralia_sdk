"""
Typed client for parable's hosted job-queue API: the async generate/perturb
/run/evaluate job runner. Enqueue a run or sweep, poll its status, fetch its
output — every server-side proxy that needs to kick off a parable run
programmatically should go through this instead of hand-rolling its own
`fetch()`/`requests` call plus the shared-secret header.
"""

from __future__ import annotations

from typing import Optional

from .http import BaseClient


class ParableClient(BaseClient):
    def list_runs(self, timeout: Optional[float] = None) -> list[dict]:
        return self.get("/runs", timeout=timeout)

    def create_run(self, config: dict, timeout: Optional[float] = None) -> str:
        """`config` is a RunConfig-shaped dict (see parable's own `config.py`
        for the schema — not re-typed here to avoid a second source of truth
        for a shape this SDK doesn't own). Returns the new run's ID."""
        return self.post("/runs", json_body=config, timeout=timeout)["run_id"]

    def create_sweep(self, config: dict, timeout: Optional[float] = None) -> str:
        """`config` is a SweepConfig-shaped dict (see parable's own
        `sweep_config.py`). Returns the new sweep's run ID — sweeps and plain
        runs share the same ID scheme server-side."""
        return self.post("/sweeps", json_body=config, timeout=timeout)["run_id"]

    def run_status(self, run_id: str, timeout: Optional[float] = None) -> dict:
        return self.get(f"/runs/{run_id}/status", timeout=timeout)

    def cancel_run(self, run_id: str, timeout: Optional[float] = None) -> None:
        self.post(f"/runs/{run_id}/cancel", timeout=timeout)

    def delete_run(self, run_id: str, timeout: Optional[float] = None) -> None:
        self.delete(f"/runs/{run_id}", timeout=timeout)

    def run_data(self, run_id: str, data_path: str, timeout: Optional[float] = None):
        """Fetch one file from a run's output (.csv/.json/.stl only — the
        server rejects anything else). Returns raw bytes for .csv/.stl, but
        a parsed dict for .json (the shared HTTP layer parses any
        application/json response body automatically) — check the type if
        `data_path`'s extension isn't known ahead of time."""
        return self.get(f"/runs/{run_id}/data/{data_path}", timeout=timeout)
