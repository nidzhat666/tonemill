# Implementation Plan: Tonemill — Async Video Color-Grading Pipeline

**Branch**: `001-color-grading-pipeline` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-color-grading-pipeline/spec.md`

## Summary

Tonemill is an async video color-grading service: a client uploads a source clip via resumable multipart upload directly to S3-compatible storage, submits a grading job against a named profile (or `auto`), and polls a stage/percentage/status until a downloadable Rec.709 SDR result is ready. The technical approach: a FastAPI HTTP API for uploads/job submission/status, a Dramatiq-on-Redis worker pool that runs a pluggable grading-profile abstraction (each profile is a self-contained, SOLID-structured `ffmpeg` pipeline behind a common interface) with GPU (`hlg-gpu`) and CPU (`hlg-cpu`) implementations, Redis as the sole state store (TTL-bound job hashes, no database), and a SvelteKit frontend (its own backend-for-frontend) as the minimal status UI. All three services ship in one Docker Compose stack, with the GPU worker path degrading gracefully to CPU-only on hosts without an NVIDIA GPU.

## Technical Context

**Language/Version**: Python 3.12 (API + worker); TypeScript (SvelteKit, Svelte 5) for the frontend

**Primary Dependencies**: FastAPI + Uvicorn (API), Dramatiq with `dramatiq[redis]` (worker/queue), boto3 (S3-compatible client, presigned + multipart operations), Pydantic (schemas, ships with FastAPI), a pinned `ffmpeg` binary (BtbN `ffmpeg-n8.1-latest-linux64-gpl` — see research.md for the pin rationale, NOT a Python dependency), SvelteKit (frontend + BFF layer)

**Storage**: Redis only — TTL-bound job-state hashes (status/stage/progress/result/error) and Dramatiq's broker queues; no relational database. Source and result video files live in S3-compatible object storage (MinIO locally, unmodified against AWS S3) — never in Redis or on the API process's disk.

**Testing**: pytest for the Python backend/worker (unit tests with `fakeredis`/`moto` for fast logic checks; integration/contract tests against real Redis + MinIO containers for the full upload→job→result lifecycle); Vitest + Playwright for the SvelteKit frontend

**Target Platform**: Linux (Ubuntu 24.04) via Docker Compose. GPU worker requires an NVIDIA GPU with the NVIDIA Container Toolkit (validated target: RTX 3080 Ti, driver 580.x). The same Compose stack (worker on the CPU-only profile) MUST also run on a machine with no GPU at all, for local development.

**Project Type**: Web application — FastAPI backend (API + worker share one Python package), SvelteKit frontend, three independently deployed containers plus Redis and (locally) MinIO.

**Performance Goals**: GPU path (`hlg-gpu`) sustains ~1.08x realtime (~65 fps) on 4K60 HLG source on an RTX 3080 Ti — the validated production path. CPU fallback (`hlg-cpu`) is ~12 fps on the same source — acceptable only as a dev-machine/no-GPU fallback, not a throughput target. Upload throughput is maximized via parallel multipart part transfers, not a specific numeric target.

**Constraints**: `ffmpeg` build MUST stay pinned to the validated BtbN `ffmpeg-n8.1-latest-linux64-gpl` release (never `master`/`latest` — see research.md). GPU worker concurrency defaults to 1 job at a time (configurable up to 2) per GPU — additional throughput comes from adding GPU hosts, not raising per-host concurrency (FR-018). The container running the GPU profile must expose both CUDA/NVENC *and* Vulkan (for libplacebo) — validated on the bare host this session but **not yet inside a container**; treat as an open risk to verify, not an assumption (see research.md and quickstart.md). Job/progress state carries a bounded TTL, not indefinite retention.

**Scale/Scope**: Single-user, trusted-network, home-lab deployment (no auth in v1). One API instance, one or a small number of GPU-host workers (designed to add more GPU hosts later, not to raise per-host concurrency), plus CPU-fallback workers on dev machines. Job volume is human-driven (one user submitting/watching a handful of files at a time via the UI), not a high-QPS service.

## Tooling & Quality Gates

- **Environment/packages**: `uv` exclusively for the Python backend/worker (`uv sync`, `uv run ...`) — no pip/poetry/conda.
- **Lint & format**: `ruff` only, with import sorting enabled via ruff's own `I` rule set (no separate `isort`) alongside its standard lint/format rules — `ruff check` and `ruff format` are the sole linter/formatter for Python.
- **Type checking**: `ty` only — no mypy/pyright.
- **Enforcement via hooks**: a `pre-commit` config runs, on every commit touching `backend/`: `uv run ruff format --check`, `uv run ruff check` (import-sort + lint rules included), and `uv run ty check` — the same three commands required to be green before finishing any change. This blocks a commit locally rather than relying on CI (CI/CD is out of scope for v1). The `frontend/` SvelteKit app gets an equivalent hook scoped to its own files (lint/format/type-check via its native toolchain), so both halves of the repo are covered without cross-contaminating each other's rules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template (placeholder principle names/descriptions only) — no project constitution has been ratified for Tonemill yet. There are no codified principles to gate this plan against, so this check is **not applicable** rather than passing/failing, and Complexity Tracking below is empty (nothing to justify against non-existent gates). If the team wants principles (e.g., mandatory test-first, library-first structure, simplicity limits) enforced on this and future plans, run `/speckit-constitution` — this plan does not block on that.

## Project Structure

### Documentation (this feature)

```text
specs/001-color-grading-pipeline/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── api.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   └── tonemill/
│       ├── api/                # FastAPI app: upload, job submit/status, profile listing routes
│       │   ├── main.py
│       │   └── routes/
│       │       ├── uploads.py  # multipart create/part-url/complete/abort
│       │       └── jobs.py     # submit, get status, list profiles
│       ├── worker/             # Dramatiq actor(s): download → run profile → upload → report
│       │   └── actors.py
│       ├── profiles/           # Pluggable grading-profile abstraction (FR-023–FR-025)
│       │   ├── base.py         # GradingProfile interface (SOLID: open/closed per format)
│       │   ├── registry.py     # name → profile lookup, "auto" resolution (FR-012)
│       │   ├── hlg_gpu.py
│       │   ├── hlg_cpu.py
│       │   └── dlog_m.py       # registered stub only (FR-015) — no pipeline implementation
│       ├── jobs/                # Job model + Redis-backed state store (TTL) (FR-004–FR-007, FR-019)
│       │   └── store.py
│       ├── storage/             # S3-compatible client wrapper: presigned + multipart ops (FR-001, FR-030–032)
│       │   └── s3_client.py
│       ├── progress/             # ffmpeg `-progress pipe:1` parsing → stage/percentage (FR-005, FR-033)
│       │   └── ffmpeg_progress.py
│       ├── tools/                # Standalone, runnable tooling (not part of the API/worker runtime)
│       │   └── tune_profile.py   # Measurement-based grading-parameter tuning script (FR-017): extracts frames
│       │                         # from reference scenes, measures highlight/channel clipping % at candidate
│       │                         # contrast/saturation values, reports the highest value under the 0.3% threshold
│       └── config.py             # env-driven settings: Redis URL, S3 endpoint, ffmpeg path, concurrency, TTL
└── tests/
    ├── contract/                 # API request/response contract tests
    ├── integration/              # full upload→job→result flow against real Redis + MinIO
    └── unit/                     # profile registry, progress-percentage math, "auto" resolution

frontend/
├── src/
│   ├── routes/                   # SvelteKit pages: submit, job list/detail
│   ├── lib/
│   │   ├── api-client.ts         # typed client for the backend API (contracts/api.md)
│   │   ├── upload.ts             # chunked/resumable multipart upload logic (FR-030, FR-031)
│   │   └── components/           # per-file upload/progress card, "maximum quality" checkbox, etc.
│   └── hooks.server.ts           # BFF-layer request handling
└── tests/

docker/
├── worker.Dockerfile             # pins ffmpeg-n8.1-latest-linux64-gpl; pin documented inline (see research.md)
├── api.Dockerfile
└── frontend.Dockerfile

docker-compose.yml                # PRODUCTION, all-in-one: api, worker (GPU baked in), redis, frontend.
                                   # Points at the existing external MinIO/S3 via env vars — no bundled `minio`
                                   # service. `docker compose up -d` alone brings the whole stack up live.
docker-compose.dev.yml            # DEV base: api, worker (CPU profile), redis, frontend, + bundled `minio`
                                   # (no external S3 in dev). Run with `docker compose -f docker-compose.dev.yml up`.
docker-compose.dev.gpu.yml        # DEV override, for a dev machine that also has a GPU: adds the GPU reservation
                                   # + NVIDIA_DRIVER_CAPABILITIES=all to the worker service (see research.md #4).
                                   # `docker compose -f docker-compose.dev.yml -f docker-compose.dev.gpu.yml up`

.pre-commit-config.yaml           # ruff format --check, ruff check (incl. import sort), ty check on backend/;
                                   # frontend's own lint/format/type-check on frontend/
pyproject.toml                    # backend package + ruff config (select "I" for import sorting) + ty config
```

**Structure Decision**: Web application layout (frontend + backend). The API and worker share a single Python package (`backend/src/tonemill/`) because they share the job model, profile registry, storage client, and Redis access — splitting them into separate packages would duplicate that shared domain code for no benefit at this scale. `profiles/` is deliberately isolated behind a `GradingProfile` interface (`base.py`) so a new source-color-format profile (D-Log, D-Log M, etc.) is added as one new file conforming to that interface, per the clarified extensibility decision (FR-023–FR-025), without touching `api/`, `worker/`, `jobs/`, or `storage/`. The frontend is a separate SvelteKit app per the clarified backend-for-frontend decision, talking to the API only over its documented contract (`contracts/api.md`).

Compose files are deliberately asymmetric: production gets exactly one file (the Compose default name, so `docker compose up -d` needs no `-f` flags and no MinIO service, since production points at the already-existing self-hosted MinIO) so bringing the real deployment up is a single command. Development, which has more variability to support (no external S3, optionally a local GPU, hot-reload needs), stays as composable override files instead of cramming every mode into one file — see research.md #10 for the rationale.

## Complexity Tracking

> No constitution gates exist yet (see Constitution Check above), so there is nothing to justify here.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
