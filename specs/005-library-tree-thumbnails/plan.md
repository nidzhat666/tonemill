# Implementation Plan: Library Tree View & Video Thumbnails

**Branch**: `005-library-tree-thumbnails` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-library-tree-thumbnails/spec.md`

## Summary

Redesigns the video library into a real folder tree — collapsible folders (collapsed by default, Unsorted open), indented compact video rows — and gives every video a real preview: a static thumbnail (the frame at 5s) at rest, and a short silent montage of clips sampled across the footage on hover. Also adds permanent, confirmed deletion of selected videos. Technical approach: the worker generates the thumbnail (JPEG) and preview clips (small H.264 MP4s, for universal browser `<video>` support, re-encoded rather than copied from the HEVC-tagged master) inline in the same job that already produces the graded result, storing their keys on the existing `Video` document; the API exposes their presigned URLs as part of the existing `GET /videos` response (no new "fetch preview" round trip); the frontend only ever *fetches* the actual clip bytes on a row's first hover, by not setting a `<video>` element's `src` until then. Folder collapse/expand is pure client-side state, never touching the backend. Deletion is a new `POST /videos/delete` that hard-deletes both the Mongo document and every S3 object it owns, gated by a confirmation dialog on the frontend.

## Technical Context

**Language/Version**: Python 3.12 (API + worker, unchanged); TypeScript (SvelteKit, Svelte 5, unchanged)

**Primary Dependencies**: Existing stack unchanged (FastAPI, Dramatiq, aioboto3, pymongo, SvelteKit). No new backend dependency — `libx264` (H.264 encode, for preview clips) is already compiled into the pinned BtbN `ffmpeg` build (confirmed: `--enable-libx264` in the worker image's ffmpeg build config, already relied on by `hlg-cpu`). Frontend gains one new local UI primitive, `alert-dialog` (research.md #8) — scaffolded from `bits-ui`'s `AlertDialog`, already an installed dependency (no new package).

**Storage**: MongoDB — two new fields on the existing `Video` document (`thumbnail_key`, `preview_clip_keys`), no new collection (data-model.md). S3-compatible object storage — three new object kinds per graded video (thumbnail JPEG, up to 10 preview-clip MP4s), all under the video's existing `results/{job_id}/` prefix; `S3StorageClient.delete_object` (removed as dead code in spec 004's folder-move-latency fix) is reintroduced for video deletion (research.md #5).

**Testing**: pytest (backend/worker, unchanged toolchain) — new coverage for the clip-count/spacing formula (research.md #3) as a pure-function unit test, and an integration test for `POST /videos/delete` against real Mongo + MinIO; Vitest + Playwright (frontend, unchanged) — new coverage for folder collapse/expand defaults, hover-triggered `src` assignment timing, and the delete confirmation flow (confirm vs. cancel).

**Target Platform**: Unchanged (Docker Compose, Linux worker; browser frontend). Hover preview playback specifically targets whatever `<video>`/H.264 support already exists in the browsers this app is used from — no new platform requirement, since H.264 is the reason it was chosen (research.md #2) over reusing the existing HEVC output.

**Project Type**: Web application — unchanged structure, extends the existing `backend/src/tonemill/` package and `frontend/src/` app from specs 001/004.

**Performance Goals**: Each grading job gains a small, bounded amount of extra worker time — one frame-accurate JPEG extract plus up to 10 short, downscaled H.264 encodes (research.md #2) from an already-decoded-and-available local file; this is a fixed, small addition per job, not proportional to the source's own resolution/duration beyond determining clip count (research.md #3). No change to the GPU grading pass's own performance envelope (spec 001's ~1.08x-realtime path, spec 004's muxer-only `hvc1`/faststart flags — both untouched). `GET /videos` gains two more presigned-URL computations per video (cheap, no bytes transferred, research.md #4) but no new network round trip on first hover.

**Constraints**: Preview clips MUST play in a standard browser `<video>` element without any codec/plugin caveat — this is the entire point of research.md #2's H.264 decision, not a nice-to-have. Folder collapse/expand state MUST NOT be persisted anywhere (client-local only, research.md #6) — this is a deliberate simplicity choice already resolved by spec.md's Assumptions, not still open. Video deletion MUST be unconditional and irreversible once confirmed (spec.md Clarifications, Session 2026-08-21) — no soft-delete/trash scope creep.

**Scale/Scope**: Same single shared workspace as specs 001/004 (no auth, no per-user scoping). Per spec.md's own out-of-scope note, thumbnail/preview-clip backfill for already-graded videos is explicitly not part of this feature — those videos simply show the "not ready yet" placeholder (FR-004) until re-processed, if ever.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against `.specify/memory/constitution.md` v1.1.0:

- **I. Simplicity, DRY & YAGNI**: Generation happens inline in the existing job rather than a new async pipeline (research.md #1) — the simplest design that satisfies every acceptance scenario, not speculative infrastructure. Folder collapse/expand needed zero backend changes because it's genuinely a display-only concern (research.md #6) — not forced into the existing shared/global data model just for consistency's sake. Deletion reuses the existing fingerprint-uniqueness index to satisfy FR-024 for free (research.md #5) rather than adding a second "is this fingerprint still valid" check. **Pass.**
- **II. Explicit Imports**: No planned code needs deferred/local imports; new worker helpers (thumbnail/clip extraction) and the new `POST /videos/delete` route follow the exact same module/dependency patterns already used throughout `backend/src/tonemill/`.
- **III. Docstrings Over Comments**: New functions (clip-count formula, thumbnail/clip extraction, delete route) get one-line-or-explained-when-non-obvious docstrings, matching the codebase's existing convention — the clip-spacing formula in particular is exactly the kind of "non-obvious, needs explaining" case the constitution calls out, and gets a docstring rather than an inline comment block.
- **IV. Test Clarity (Given/When/Then)**: New tests follow spec 004's established pattern (real Redis + MinIO + MongoDB, no mocks for the stores under test).
- **V. Readability & Maintainability**: Hover-playback logic (research.md #7) is driven by the media element's own `ended` event rather than a hand-maintained timer kept in sync with a duration constant defined elsewhere — avoids exactly the kind of implicit cross-file coupling that erodes readability over time.

No violations requiring justification. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-library-tree-thumbnails/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
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
│       │   └── routes/
│       │       ├── videos.py      # GET /videos gains thumbnail_url/preview_clip_urls;
│       │       │                  #   + POST /videos/delete
│       │       └── folders.py     # unchanged
│       ├── worker/
│       │   └── pipeline.py        # + thumbnail extraction (ffmpeg -ss 5 -frames:v 1) and
│       │                          #   preview-clip generation (ffmpeg -c:v libx264, per-clip
│       │                          #   start/length from research.md #3's formula), both
│       │                          #   inline in the existing successful-grade path
│       ├── videos/
│       │   ├── store.py           # Video gains thumbnail_key/preview_clip_keys fields (+
│       │   │                      #   VideoStore.delete); index setup unchanged
│       │   ├── preview.py         # NEW: the clip-count/spacing formula (research.md #3) as
│       │   │                      #   a pure function, plus the ffmpeg invocations for
│       │   │                      #   thumbnail + clip extraction
│       │   └── relocate.py        # unchanged
│       └── storage/
│           └── s3_client.py       # + delete_object reintroduced (research.md #5)
└── tests/
    ├── integration/                # + POST /videos/delete against real Mongo + MinIO
    └── unit/                       # + preview.py's clip-count/spacing formula

frontend/
├── src/
│   ├── lib/
│   │   ├── api-client.ts          # VideoResponse gains thumbnail_url/preview_clip_urls;
│   │   │                          #   + deleteVideos()
│   │   ├── stores/
│   │   │   └── library.svelte.ts  # + expandedFolderIds/unsortedExpanded (client-only,
│   │   │                          #   research.md #6); + deleteVideos()
│   │   └── components/
│   │       ├── ui/
│   │       │   └── alert-dialog/  # NEW: scaffolded local wrapper (research.md #8)
│   │       ├── VideoCard.svelte   # restructured into a compact list row (indented under
│   │       │                      #   its folder); thumbnail area delegates to VideoThumbnail
│   │       ├── VideoThumbnail.svelte  # NEW: static image at rest, hover-driven clip
│   │       │                          #   playback (research.md #7)
│   │       └── FolderCard.svelte  # + expand/collapse control, wired to the library store
│   └── routes/
│       └── library/
│           └── +page.svelte       # video rows only rendered under an expanded folder (or
│                                   #   always under Unsorted); + "Delete selected" control +
│                                   #   confirmation dialog
```

**Structure Decision**: Same web-application layout as specs 001/004 — no new top-level project. A new `videos/preview.py` module (alongside the existing `videos/store.py`, `fingerprint.py`, `naming.py`, `relocate.py`) isolates the clip-count formula and the ffmpeg calls it drives, keeping `worker/pipeline.py` a thin orchestrator that calls into `videos/` helpers rather than growing ffmpeg-invocation logic of its own — consistent with how `pipeline.py` already delegates naming (`videos/naming.py`) and fingerprinting (`videos/fingerprint.py`) instead of inlining them.

## Complexity Tracking

> Constitution Check above found no violations to justify.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
