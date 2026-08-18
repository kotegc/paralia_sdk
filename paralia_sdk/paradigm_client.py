"""
Typed client for paradigm's batch/evaluation pipeline API: hand it a mesh,
get back origin/axis recovery, cap/dr metrics, and optionally the full
heatmap grid. Same never-raises contract as the service itself — a pipeline
failure comes back as `success=False` with a stage/reason, never an
exception from this client.

NOT a client for paradigm's *other*, viewer-facing API (mesh-name-keyed,
cached for one interactive specimen at a time) — that one is shaped for a
live UI, not for "run the full pipeline on this mesh and give me back
everything a batch caller needs." A future client for that API would be its
own method or class here, not an overload of this one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .geometry import Mesh, write_stl_bytes
from .http import BaseClient


@dataclass
class ParadigmRunResult:
    """The result of one pipeline run. Field shapes mirror the batch API's
    JSON response directly."""

    success: bool
    origin: Optional[tuple[float, float, float]] = None
    primary_axis: Optional[tuple[float, float, float]] = None
    failure_stage: Optional[str] = None
    failure_reason: Optional[str] = None
    runtime_seconds: float = 0.0
    metrics: dict = field(default_factory=dict)
    debug: str = ""  # a short diagnostic string the pipeline attaches to its result, if any
    heatmap: Optional[dict] = None  # present only when include_heatmap=True was requested


class ParadigmClient(BaseClient):
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
            "X-Include-Heatmap": "true" if include_heatmap else "false",
            "Content-Type": "application/octet-stream",
        }
        if case_id:
            headers["X-Case-Id"] = case_id
        if sdf_backend:
            headers["X-Sdf-Backend"] = sdf_backend
        resp = self.post("/pipeline/run", data=body, headers=headers, timeout=timeout)
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
