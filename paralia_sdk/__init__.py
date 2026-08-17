"""
paralia_sdk — the internal contract every Paralia app (paradigm, parable, and
future tools like parapet/parasol) uses to talk to every other app, plus the
generic geometry utilities that don't belong to any one app's proprietary
algorithm. See ../../docs/internal-api-sdk.md for the pattern a new app
should follow to plug into this.

Two independent things live here, deliberately not entangled:
  - `paralia_sdk.geometry` — Mesh + mesh I/O + world-Z alignment. Pure numpy,
    no network, no auth. Safe for an open-source consumer (parable) to depend
    on directly.
  - `paralia_sdk.paradigm_client` / `paralia_sdk.parable_client` — typed HTTP
    clients wrapping each app's network API (shared-secret auth, timeouts,
    typed errors). This is what replaces in-process imports of a proprietary
    app's source: a consumer gets the app's *output*, never its source.
"""

from .geometry import Mesh, AlignmentResult, align_mesh_to_world_z
from .paradigm_client import ParadigmClient, ParadigmRunResult
from .parable_client import ParableClient

__all__ = [
    "Mesh", "AlignmentResult", "align_mesh_to_world_z",
    "ParadigmClient", "ParadigmRunResult",
    "ParableClient",
]
