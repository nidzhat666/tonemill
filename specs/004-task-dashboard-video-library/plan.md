# Implementation Plan: Task Dashboard & Video Library

**Branch**: `004-task-dashboard-video-library` | **Date**: 2026-08-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-task-dashboard-video-library/spec.md`

## Summary

Turns the existing job list into two views: a **dashboard** (today's list, minus the clutter — failed jobs get a per-job "Dismiss", plus a "Dismiss all" for everything not currently in progress) and a new **video library** tab where completed videos can be dragged into flat, user-created folders, individually or as a multi-selected batch. Alongside that, three correctness fixes to the actual deliverable: result files are named `<recording-date>_<profile>.mp4` instead of a UUID, they gain the `hvc1` tag (+`faststart`) that macOS Quick Look/Preview requires to open an HEVC MP4 at all, and re-submitting a file already processed (or in progress) through the same profile is rejected with a friendly error instead of creating a duplicate job. The technical approach: the ephemeral Redis `Job` store gains one field (`dismissed`) and stays exactly as TTL-bound as it already is; a new MongoDB `videos`/`folders` pair of collections becomes the durable store the library, folder organization, and duplicate-fingerprint index all live in, since none of those can correctly live behind a 24h TTL. No new frontend dependency — folder drag-and-drop uses the native HTML5 DnD API.

## Technical Context

**Language/Version**: Python 3.12 (API + worker, unchanged); TypeScript (SvelteKit, Svelte 5, unchanged)

**Primary Dependencies**: Existing stack unchanged (FastAPI, Dramatiq, aioboto3, Pydantic, SvelteKit) plus **`pymongo>=4.9`** (new — native async API, not Motor; research.md #1) for the API's and worker's MongoDB access.

**Storage**: Redis — unchanged role (live job/progress state, upload sessions), plus one new field (`Job.dismissed`, still TTL-bound). **MongoDB (new)** — durable `videos` and `folders` collections; source of truth for the video library, folder assignment, and duplicate-submission detection (research.md #1). S3-compatible object storage — unchanged: results keep the same opaque, permanent `results/{job_id}/{uuid}.mp4` key shape spec 001 already used; folder organization is a Mongo-only property and never touches S3 (research.md #5, revised 2026-08-21 after a real ~2s-per-move latency regression). The readable name still reaches every download via a presigned-URL `Content-Disposition` override (`S3StorageClient.presign_get_object`'s new `filename` param), not via the object's key.

**Testing**: pytest (backend/worker, unchanged toolchain) — new fixtures for a real MongoDB in integration tests (mirroring the existing real-Redis/real-MinIO pattern in spec 001, not `mongomock`, to catch real index/constraint behavior per spec 001's own testing philosophy); Vitest + Playwright (frontend, unchanged) — new coverage for dismiss/dismiss-all, folder creation, and drag-and-drop/multi-select move.

**Target Platform**: Unchanged (Docker Compose, Linux). One new service, `mongo`, added to `docker-compose.yml` and `docker-compose.dev.yml` (a single-node MongoDB is sufficient at this scale — no replica set needed for this feature's access patterns).

**Project Type**: Web application — unchanged structure (FastAPI backend + SvelteKit frontend, three containers plus now Redis *and* MongoDB, plus MinIO in dev).

**Performance Goals**: No change to the grading pipeline's own performance envelope (spec 001's ~1.08x-realtime GPU path is untouched — the two new output flags, `-tag:v hvc1`/`-movflags +faststart`, are muxer-level and add no measurable encode-time cost). New work is small, synchronous, request-scoped operations: the duplicate-fingerprint check is two small ranged `GET`s against the source object (bounded cost regardless of source file size, research.md #3), and folder moves are a single Mongo `folder_id` write per video with zero S3 calls (research.md #5, revised 2026-08-21) — a move's latency is now independent of the video's file size, closing a real regression where it depended on an S3 copy+delete (~2s observed in production).

**Constraints**: The duplicate fingerprint is a UX safeguard, not a security boundary (research.md #3) — it must stay cheap (bounded I/O per check) rather than hashing entire multi-gigabyte sources, even at the cost of not being a cryptographic identity guarantee. Folder rename and nested folders are explicitly out of scope for this iteration (spec.md Assumptions) — the schema and API surface should not pay complexity for either now.

**Scale/Scope**: Same single shared workspace as spec 001 (no auth, no per-user scoping) — dismissed state and folder organization are global, not per-browser (FR-006). Library expected to hold on the order of hundreds to low thousands of videos and a handful to a few dozen folders; no pagination is being added to `GET /videos`/`GET /folders` in this iteration (reasonable at this scale; revisit if the library grows well past that).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against `.specify/memory/constitution.md` v1.1.0:

- **I. Simplicity, DRY & YAGNI**: The one new piece of real infrastructure (MongoDB) is justified by a genuine, demonstrated conflict — Redis's existing, validated TTL contract (spec 001 FR-019) is structurally incompatible with "the library must outlive 24 hours" (research.md #1) — not spec-shopped for its own sake. `POST /videos/move` is one endpoint for both single- and bulk-move rather than two near-duplicate ones (DRY). Folder nesting and rename are deliberately *not* built (YAGNI — not asked for, spec.md marks them out of scope). **Pass.**
- **II. Explicit Imports**: No planned code requires deferred/local imports (Mongo client access follows the exact same `dependencies.py`/`api/dependencies.py` pattern already used for Redis and the S3 client). **Pass** (to be enforced at implementation/review time as usual).
- **III. Docstrings Over Comments**: Applies at implementation time; no plan-level violation anticipated — the new modules (`videos/store.py`, a fingerprint helper, folder-move logic) follow the same docstring-first convention already used throughout `backend/src/tonemill/`.
- **IV. Test Clarity (Given/When/Then)**: New integration tests follow spec 001's existing pattern (real Redis + MinIO, extended with real MongoDB) rather than introducing mocks for the new store.
- **V. Readability & Maintainability**: The worker (`pipeline.py`) stays unaware of folders entirely (research.md #5) — folder logic lives only in the API layer where the `videos` collection is already owned, keeping the grading pipeline's existing responsibility boundary intact rather than smearing a UI-only concept across it.

No violations requiring justification. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/004-task-dashboard-video-library/
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
│       ├── api/
│       │   ├── main.py
│       │   └── routes/
│       │       ├── uploads.py    # unchanged
│       │       ├── jobs.py       # + dismiss / dismiss-all endpoints, + duplicate-check call in submit_job
│       │       ├── videos.py     # NEW: GET /videos, POST /videos/move
│       │       └── folders.py    # NEW: GET/POST /folders, DELETE /folders/{id}
│       ├── worker/
│       │   ├── actors.py         # unchanged
│       │   └── pipeline.py       # + writes/updates the Video document alongside the existing Job update;
│       │                         #   + recorded_created_at probe; + display_name/result_key generation
│       ├── profiles/
│       │   ├── hlg_gpu.py        # + "-tag:v", "hvc1", "-movflags", "+faststart" in output flags
│       │   ├── hlg_cpu.py        # same
│       │   └── base.py           # output_color_tagging_args (or a sibling helper) gains the new flags,
│       │                         #   shared rather than duplicated per profile (DRY, research.md #2)
│       ├── videos/               # NEW: mirrors jobs/ and storage/'s existing module shape
│       │   ├── store.py          # MongoDB-backed VideoStore + FolderStore (data-model.md)
│       │   ├── fingerprint.py    # sha256(size || first 1MiB || last 1MiB) via ranged S3 GETs (research.md #3)
│       │   ├── naming.py         # display_name formatting + disambiguation (FR-016, FR-018, research.md #4)
│       │   └── relocate.py       # folder move/delete = a Video.folder_id write, no S3 calls (research.md #5)
│       ├── jobs/
│       │   └── store.py          # + `dismissed` field, + dismiss/dismiss-all store methods,
│       │                         #   GET-all excludes dismissed
│       ├── storage/
│       │   └── s3_client.py      # + presign_get_object(filename=...) -> Content-Disposition override,
│       │                         #   so a download's saved name never depends on the object's own key
│       ├── dependencies.py       # + get_mongo_client / get_video_store / get_folder_store (lru_cache,
│       │                         #   same pattern as get_job_store)
│       └── config.py             # + mongo_url / mongo_db setting
└── tests/
    ├── contract/                  # + videos/folders/dismiss endpoint contract tests
    ├── integration/               # + real-MongoDB fixture; duplicate-detection race, folder-move re-keying
    └── unit/                      # + fingerprint helper, display_name disambiguation, dismiss-eligibility logic

frontend/
├── src/
│   ├── routes/
│   │   ├── +layout.svelte        # + tab navigation between Dashboard and Library
│   │   ├── +page.svelte          # Dashboard (existing) — + Dismiss / Dismiss all wiring
│   │   └── library/
│   │       └── +page.svelte      # NEW: folder list + unsorted/foldered video grid
│   ├── lib/
│   │   ├── api-client.ts         # + dismiss, dismissAll, listVideos, moveVideos, listFolders,
│   │   │                         #   createFolder, deleteFolder
│   │   ├── stores/
│   │   │   ├── jobs.svelte.ts    # unchanged shape, dismiss just drops the item from `items`
│   │   │   └── library.svelte.ts # NEW: videos + folders + current multi-selection state
│   │   └── components/
│   │       ├── JobCard.svelte    # + Dismiss button (failed jobs)
│   │       ├── FolderCard.svelte # NEW: drop target, shows name + count
│   │       └── VideoCard.svelte  # NEW: draggable, selectable
│   └── tests/                    # + dismiss/dismiss-all, folder create, move (unit); drag-and-drop (e2e)

docker-compose.yml                 # + mongo service (production)
docker-compose.dev.yml             # + mongo service (dev)
```

**Structure Decision**: Same web-application layout as spec 001 — no new top-level project, this feature extends the existing `backend/src/tonemill/` package and `frontend/src/` app. A new `videos/` module (mirroring the existing `jobs/` and `storage/` module shape) isolates all MongoDB access behind `VideoStore`/`FolderStore`, so `worker/pipeline.py` and `api/routes/*.py` depend on that interface rather than talking to `pymongo` directly — consistent with spec 001's own precedent of isolating storage concerns (`storage/s3_client.py`) behind a thin wrapper rather than scattering raw client calls through route handlers.

## Complexity Tracking

> Constitution Check above found no violations to justify.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
