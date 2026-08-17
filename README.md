# paralia_sdk

A small, generic toolkit shared across the Paralia suite's apps: typed HTTP clients for calling each app's network API, and mesh geometry utilities with no proprietary logic. Built so an app like [parable](https://github.com/kotegc/parable) can talk to a proprietary service over its network API and process meshes locally, without ever needing that service's source code.

## What's here

- **`paralia_sdk.geometry`** — a `Mesh` dataclass, dependency-free readers/writers for OBJ/STL/PLY/3MF, and a PCA world-Z alignment routine. Pure numpy, no network, no auth. Generic geometry math — nothing algorithm-specific or proprietary lives here.
- **`paralia_sdk.http`** — `BaseClient`, the shared HTTP plumbing every per-service client below builds on: shared-secret auth header injection, timeouts, a single retry on transport failure, and errors normalized to `ParaliaAPIError`.
- **`paralia_sdk.paradigm_client`** — `ParadigmClient`, a typed client for a paradigm-shaped batch/evaluation pipeline API (`POST /pipeline/run`): hand it a `Mesh`, get back origin/axis recovery, metrics, and optionally a full heatmap grid.
- **`paralia_sdk.parable_client`** — `ParableClient`, a typed client for a parable-shaped async job-queue API (enqueue a run/sweep, poll status, fetch results).

## Install

```bash
pip install "paralia_sdk @ git+https://github.com/kotegc/paralia_sdk.git"
```

## Development

```bash
pip install -e .
pip install pytest
pytest tests/
```

## Design notes

This package exists specifically to let a consumer depend on *what a service outputs*, never *how it computes it*. If you're adding a client for a new service here, keep it a thin wrapper — auth, request/response shaping, error handling — with no side effects (file I/O, etc.) baked in; that belongs in the calling application's own adapter code.
