"""
paralia_sdk — the shared contract every Paralia app (paradigm, parable, and
future services) uses to talk to every other app, plus the generic geometry
utilities that don't belong to any one app's proprietary algorithm.

Two independent things live here, deliberately not entangled:
  - `paralia_sdk.geometry` — Mesh + mesh I/O + world-Z alignment. Pure numpy,
    no network, no auth. Safe for an open-source consumer (parable) to depend
    on directly.
  - `paralia_sdk.paradigm_client` / `paralia_sdk.parable_client` — typed HTTP
    clients wrapping each app's network API (shared-secret auth, timeouts,
    typed errors). This is what replaces in-process imports of a proprietary
    app's source: a consumer gets the app's *output*, never its source.

If you're adding a client for a new service, keep it a thin wrapper around
`paralia_sdk.http.BaseClient` — auth, request/response shaping, error
handling — with no side effects (file I/O, etc.) baked in; that belongs in
the calling application's own adapter code.
"""

from .geometry import Mesh, AlignmentResult, align_mesh_to_world_z
from .paradigm_client import ParadigmClient, ParadigmRunResult
from .parable_client import ParableClient

__all__ = [
    "Mesh", "AlignmentResult", "align_mesh_to_world_z",
    "ParadigmClient", "ParadigmRunResult",
    "ParableClient",
]
