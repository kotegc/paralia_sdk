<p align="center">
  <img src="assets/paralia-logo.svg" alt="Paralia" height="56">
</p>

<h1 align="center">paralia_sdk</h1>

<p align="center">
  <a href="https://github.com/Paralia-Labs/paralia_sdk/actions/workflows/test.yml"><img src="https://github.com/Paralia-Labs/paralia_sdk/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-BSD--2--Clause-183EFC.svg" alt="License: BSD-2-Clause"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-183EFC.svg" alt="Python 3.10+">
</p>

A small, generic toolkit shared across the Paralia suite's apps: typed HTTP clients for calling each app's network API, and mesh geometry utilities with no proprietary logic. Built so an app like [parable](https://github.com/Paralia-Labs/parable) can talk to a proprietary service over its network API and process meshes locally, without ever needing that service's source code.

Part of the [Paralia Labs](https://github.com/Paralia-Labs) suite — see [paralia.io/docs](https://www.paralia.io/docs) for how this fits alongside `parable` and the rest of the platform.

## What's here

- **`paralia_sdk.geometry`** — a `Mesh` dataclass, dependency-free readers/writers for OBJ/STL/PLY/3MF, and a PCA world-Z alignment routine. Pure numpy, no network, no auth. Generic geometry math — nothing algorithm-specific or proprietary lives here.
- **`paralia_sdk.http`** — `BaseClient`, the shared HTTP plumbing every per-service client below builds on: shared-secret auth header injection, timeouts, a single retry on transport failure, and errors normalized to `ParaliaAPIError`.
- **`paralia_sdk.paradigm_client`** — `ParadigmClient`, a typed client for a paradigm-shaped batch/evaluation pipeline API (`POST /pipeline/run`): hand it a `Mesh`, get back origin/axis recovery, metrics, and optionally a full heatmap grid.
- **`paralia_sdk.parable_client`** — `ParableClient`, a typed client for a parable-shaped async job-queue API (enqueue a run/sweep, poll status, fetch results).

## Install

```bash
pip install "paralia_sdk @ git+https://github.com/Paralia-Labs/paralia_sdk.git"
```

## Quickstart

Every client needs a base URL for the service it talks to, and a shared secret for the `X-Internal-Secret` auth header — either passed explicitly or read from the `API_INTERNAL_SECRET` environment variable if omitted.

```python
import os
from paralia_sdk import ParadigmClient
from paralia_sdk.geometry import read_mesh

client = ParadigmClient(
    base_url="http://localhost:8091",         # or a deployed service's URL
    internal_secret=os.environ["API_INTERNAL_SECRET"],
)

mesh = read_mesh("scan.stl")
result = client.run_pipeline(mesh, case_id="case_001")

if result.success:
    print(result.origin, result.primary_axis)
else:
    print(f"failed at {result.failure_stage}: {result.failure_reason}")
```

`ParableClient` follows the same construction pattern (`base_url`, `internal_secret`) for parable's job-queue API.

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```

See `CONTRIBUTING.md` for more, and `TESTING.md` for what's not covered yet.

## Design notes

This package exists specifically to let a consumer depend on *what a service outputs*, never *how it computes it*. If you're adding a client for a new service here, keep it a thin wrapper — auth, request/response shaping, error handling — with no side effects (file I/O, etc.) baked in; that belongs in the calling application's own adapter code.
