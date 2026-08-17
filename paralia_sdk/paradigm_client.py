"""
Typed client for paradigm's batch/evaluation network API
(`paradigm/paradigm/io/batch_api.py`). This is what replaced parable's
in-process `from paradigm.api import ParadigmInput, run_scan_pipeline,
PipelineParams` call — same never-raises contract (a pipeline failure comes
back as `success=False` with a stage/reason, never an exception from this
client), just over HTTP instead of an in-process function call, since
parable no longer has paradigm's source available to import.

NOT a client for paradigm's *other* API (`io/api.py`, the interactive
viewer's `/run`/`/ducky`/`/upload`) — that one is keyed by mesh name against
a small cache built for one interactive specimen, not shaped for "run the
full pipeline on this specific mesh and give me back everything a batch
harness needs." If a future app needs the viewer's endpoints, it gets its
own client method here rather than overloading this one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .geometry import Mesh, write_stl_bytes
from .http import BaseClient


@dataclass
class ParadigmRunResult:
    """Mirrors paradigm.api.ParadigmOutput field-for-field, so a caller that
    used to build a ParadigmResult from a ParadigmOutput (parable's
    `runners/paradigm_adapter.py`) barely needs to change."""

    success: bool
    origin: Optional[tuple] = None
    primary_axis: Optional[tuple] = None
    failure_stage: Optional[str] = None
    failure_reason: Optional[str] = None
    runtime_seconds: float = 0.0
    metrics: dict = field(default_factory=dict)
    debug: str = ""
    heatmap: Optional[dict] = None  # present only when include_heatmap=True was requested


class ParadigmClient(BaseClient):
    def health(self) -> bool:
        try:
            return bool(self.get("/health", timeout=5.0).get("ok"))
        except Exception:
            return False

    def run_pipeline(
        self,
        mesh: Mesh,
        case_id: str = "",
        sdf_backend: Optional[str] = None,
        include_heatmap: bool = False,
        timeout: Optional[float] = None,
    ) -> ParadigmRunResult:
        """Run the full paradigm pipeline on `mesh` and get back everything a
        batch/evaluation caller needs (origin, axis, cap/dr metrics, and
        optionally the full heatmap grid for field-consistency comparisons).
        """
        body = write_stl_bytes(mesh)
        headers = {
            "X-Filename": f"{case_id or 'mesh'}.stl",
            "X-Case-Id": case_id,
            "X-Include-Heatmap": "true" if include_heatmap else "false",
        }
        if sdf_backend:
            headers["X-Sdf-Backend"] = sdf_backend
        resp = self.post(
            "/pipeline/run",
            data=body,
            headers={**headers, "Content-Type": "application/octet-stream"},
            timeout=timeout,
        )
        return ParadigmRunResult(
            success=resp.get("success", False),
            origin=tuple(resp["origin"]) if resp.get("origin") is not None else None,
            primary_axis=tuple(resp["primary_axis"]) if resp.get("primary_axis") is not None else None,
            failure_stage=resp.get("failure_stage"),
            failure_reason=resp.get("failure_reason"),
            runtime_seconds=resp.get("runtime_seconds", 0.0),
            metrics=resp.get("metrics", {}),
            debug=resp.get("debug", ""),
            heatmap=resp.get("heatmap"),
        )
