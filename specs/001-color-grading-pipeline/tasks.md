# Tasks: Tonemill — Async Video Color-Grading Pipeline

**Input**: Design documents from `/specs/001-color-grading-pipeline/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md (all present)

**Tests**: Not explicitly requested in spec.md, so no dedicated test-writing tasks are generated per user story. Test *tooling* (pytest/fakeredis/moto, Vitest/Playwright) is still set up in Phase 1 as shared infrastructure, and Polish includes running quickstart.md's end-to-end validation.

**Organization**: Tasks are grouped by user story (spec.md priorities P1–P4) to enable independent implementation and testing of each.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1–US4)
- File paths are exact, per plan.md's Project Structure

## Path Conventions

Web application layout per plan.md: `backend/src/tonemill/` (Python, API + worker share one package), `frontend/src/` (SvelteKit), `docker/` + root-level `docker-compose*.yml`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repo scaffolding, tooling, and container definitions — nothing story-specific yet.

- [X] T001 Create backend project skeleton: `backend/src/tonemill/{api,worker,profiles,jobs,storage,progress}/` packages (with `__init__.py`) and `backend/tests/{contract,integration,unit}/` directories, per plan.md Project Structure
- [X] T002 [P] Initialize `backend/pyproject.toml` via `uv`: runtime deps (FastAPI, Uvicorn, `dramatiq[redis]`, boto3, Pydantic), dev deps (pytest, fakeredis, moto), and ruff (lint + format, import sorting via ruff's `I` rule set) / `ty` configuration
- [X] T003 [P] Create SvelteKit frontend project skeleton: `frontend/src/routes/`, `frontend/src/lib/{components,stores}/`, `frontend/src/hooks.server.ts` placeholder, and `frontend/package.json` with SvelteKit, eslint, prettier, svelte-check, Vitest, Playwright deps
- [X] T004 Create root `.pre-commit-config.yaml` with hooks for backend (`uv run ruff format --check`, `uv run ruff check`, `uv run ty check`, scoped to `backend/`) and frontend (its own lint/format/type-check, scoped to `frontend/`) — per plan.md Tooling & Quality Gates
- [X] T005 [P] Write `docker/api.Dockerfile` (uv-installed FastAPI backend image)
- [X] T006 [P] Write `docker/worker.Dockerfile` — pin the exact BtbN `ffmpeg-n8.1-latest-linux64-gpl` release asset by URL/tag (never `master`/`latest`), with an inline comment directly above the download step documenting *why*: rolling `master` needs NVENC API ≥13.1 (driver ≥610), the target host runs driver 580.x (API 13.0) and fails with "Function not implemented" against `master` (research.md #3)
- [X] T007 [P] Write `docker/frontend.Dockerfile` (SvelteKit build + serve)
- [X] T008 Write root `docker-compose.yml` — production, all-in-one: `api`, `worker` (GPU reservation + `NVIDIA_DRIVER_CAPABILITIES=all` baked in), `redis`, `frontend`; points at the existing external MinIO/S3 via env vars, no bundled `minio` service — `docker compose up -d` alone must bring it live (research.md #9)
- [X] T009 [P] Write `docker-compose.dev.yml` — dev base: `api`, `worker` (CPU profile, no GPU flags), `redis`, `frontend`, plus a bundled `minio` service (dev has no external S3)
- [X] T010 [P] Write `docker-compose.dev.gpu.yml` — dev override adding the GPU reservation + `NVIDIA_DRIVER_CAPABILITIES=all` to the worker service, for a dev machine that also has a GPU (research.md #4, #9)

**Checkpoint**: Repo scaffolding, tooling, and container definitions exist. No application logic yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared domain code every user story builds on — profile abstraction, job state, storage client, progress parsing, API/worker skeletons.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T011 Implement env-driven settings module in `backend/src/tonemill/config.py` — Redis URL, S3 endpoint/credentials, `ffmpeg` binary path, GPU worker concurrency (default 1, max 2 — FR-018), job TTL default (FR-019)
- [X] T012 Implement the `GradingProfile` abstract interface in `backend/src/tonemill/profiles/base.py` — the SOLID, open/closed abstraction a new source-color-format profile must conform to (FR-023, FR-025)
- [X] T013 Implement the profile registry (registration, name → profile lookup, unknown-name rejection), loaded once at worker startup with changes requiring a restart, not hot-reload (FR-035), in `backend/src/tonemill/profiles/registry.py` (FR-016, FR-023, FR-024, FR-035) — depends on T012
- [X] T014 [P] Register `d-log-m` as an `implemented=false` stub entry (no pipeline) in `backend/src/tonemill/profiles/dlog_m.py` (FR-015) — depends on T013
- [X] T015 [P] Implement the Job model + Redis-backed job store (create/get/update; `EXPIRE` re-applied on every write) in `backend/src/tonemill/jobs/store.py` (FR-004, FR-005, FR-007, FR-019, FR-033) — depends on T011
- [X] T016 [P] Implement the S3-compatible storage client wrapper (presigned single-part URL + multipart create/part-url/complete/abort) in `backend/src/tonemill/storage/s3_client.py` (FR-001, FR-030–FR-032) — depends on T011
- [X] T017 [P] Implement the ffmpeg progress utility (`ffprobe` duration probe + `-progress pipe:1` line parsing → stage/percentage) in `backend/src/tonemill/progress/ffmpeg_progress.py` (FR-005, FR-033)
- [X] T018 [P] Set up the FastAPI app skeleton (app factory, shared error-handling conventions, router registration) in `backend/src/tonemill/api/main.py` — depends on T011
- [X] T019 [P] Set up the Dramatiq broker + actor skeleton wired to Redis, with worker concurrency read from config in `backend/src/tonemill/worker/actors.py` (FR-018) — depends on T011

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Submit footage and retrieve a correctly graded result (Priority: P1) 🎯 MVP

**Goal**: A client can upload a source HLG clip, submit a job against an explicit profile, poll status/stage/progress, and download a correctly Rec.709-tagged SDR result.

**Independent Test**: Per spec.md — request an upload URL, upload a source HLG clip, submit a job with an explicit profile, poll until `done`, download and verify Rec.709-tagged SDR output. Fully exercisable via `curl` per quickstart.md steps 2–5, no UI required.

### Implementation for User Story 1

- [X] T020 [P] [US1] Implement uploads API routes — `POST /uploads`, `POST /uploads/{id}/parts/{n}`, `GET /uploads/{id}/parts` (list already-received parts, so a client with no/lost local state can discover what's left to resume), `POST /uploads/{id}/complete`, `POST /uploads/{id}/abort` — in `backend/src/tonemill/api/routes/uploads.py` (FR-001, FR-030–FR-032, FR-034; contracts/api.md §Uploads)
- [X] T021 [P] [US1] Implement jobs API routes — `POST /jobs` (validate `s3_key` references a completed upload, validate profile name via the registry, reject `d-log-m`/unknown names), `GET /jobs/{id}`, and `GET /profiles` (list registered profiles from the registry, for UI display and client-side validation) — in `backend/src/tonemill/api/routes/jobs.py` (FR-002, FR-004–FR-007, FR-015, FR-016, FR-019; contracts/api.md §Jobs, §Profiles) — depends on T013
- [X] T022 [P] [US1] Implement the `hlg-gpu` profile pipeline: CUDA decode, libplacebo tone-map/grade (`tonemapping=hable`, `contrast=1.12`, `saturation=1.10`, dynamic peak detection), `hevc_nvenc` encode (`-rc vbr -cq 20 -b:v 0`), explicit `bt709/bt709/bt709/tv` output tagging in `backend/src/tonemill/profiles/hlg_gpu.py` (FR-009, FR-011, FR-014)
- [X] T023 [P] [US1] Implement the `hlg-cpu` profile pipeline: `zscale` linear→bt709 (`npl=100`), `tonemap=hable`, `eq(contrast=1.06)`/`vibrance(0.22)`/unsharp grade, `libx265` encode (`preset medium`, `crf 20`), explicit `bt709/bt709/bt709/tv` output tagging in `backend/src/tonemill/profiles/hlg_cpu.py` (FR-010, FR-011, FR-014)
- [X] T024 [US1] Implement the worker job-processing actor: download source from storage, probe duration, run the resolved profile's `ffmpeg` command with progress parsing, upload the result, update the job store through `downloading` → `processing` → `uploading_result` → `done`/`failed` in `backend/src/tonemill/worker/actors.py` (FR-003, FR-005–FR-007, FR-033) — depends on T015, T016, T017, T019, T022, T023
- [X] T025 [US1] Implement the explicit-profile-unavailable failure path — e.g., `hlg-gpu` requested on a host with no GPU encoding path fails the job with a clear reason, no silent substitution — in `backend/src/tonemill/worker/actors.py` (FR-013) — depends on T024

**Checkpoint**: User Story 1 is fully functional and independently testable (MVP).

---

## Phase 4: User Story 2 - Get a working result regardless of which machine is running the worker (Priority: P2)

**Goal**: `profile: "auto"` resolves to `hlg-gpu` when the worker's `ffmpeg` build reports `hevc_nvenc`, else falls back to `hlg-cpu` — same worker image, no config change.

**Independent Test**: Submit `profile: "auto"` on a GPU-capable deployment and confirm it resolves to and completes via `hlg-gpu`; repeat unmodified on a deployment with no usable GPU and confirm it resolves to and completes via `hlg-cpu`.

### Implementation for User Story 2

- [X] T026 [US2] Implement GPU/`hevc_nvenc` capability detection (query the worker's `ffmpeg` build's available encoders at startup) in `backend/src/tonemill/profiles/registry.py` (FR-012) — extends T013
- [X] T027 [US2] Wire `profile: "auto"` resolution — resolved at worker pickup time to `hlg-gpu` if GPU capability was detected, else `hlg-cpu`; `resolved_profile` recorded on the job — into `backend/src/tonemill/api/routes/jobs.py` and `backend/src/tonemill/worker/actors.py` (FR-012) — depends on T026

**Checkpoint**: User Stories 1 and 2 both work independently; the same worker image behaves correctly on GPU and non-GPU hosts.

---

## Phase 5: User Story 3 - Manage jobs without touching the API directly (Priority: P3)

**Goal**: A minimal SvelteKit UI to select one or more files, submit them, watch live per-file progress/stage, and download each result — no direct API calls by the user.

**Independent Test**: Using only the UI, go from "one or more source files on disk" to "downloaded graded result(s)," observing per-file upload/processing progress update live, including one file failing without affecting the others (FR-026).

### Implementation for User Story 3

- [X] T028 [P] [US3] Implement the typed API client (uploads/profiles/jobs) in `frontend/src/lib/api-client.ts`, per contracts/api.md
- [X] T029 [US3] Implement resumable multipart upload logic — file chunking, parallel part `PUT`s, resume by tracking already-completed parts locally, falling back to `GET /uploads/{id}/parts` to discover completed parts when local state is unavailable (e.g., a fresh session) — in `frontend/src/lib/upload.ts` (FR-030, FR-031, FR-034) — depends on T028
- [X] T030 [P] [US3] Implement a per-file upload/job progress store, so multiple concurrently submitted files render independent state, in `frontend/src/lib/stores/jobs.ts` (FR-026, FR-033)
- [X] T031 [US3] Implement the submit page — multi-file picker, profile dropdown (via `GET /profiles`), submit action — in `frontend/src/routes/+page.svelte` (FR-020, FR-026) — depends on T028, T029, T030
- [X] T032 [P] [US3] Implement the job progress card component (status, stage, percentage, download link) in `frontend/src/lib/components/JobCard.svelte` (FR-020, FR-033)
- [X] T033 [US3] Implement live status polling (updates without a full page reload), wired into the submit page and job cards, in `frontend/src/lib/polling.ts` (FR-020) — depends on T030, T031, T032
- [X] T034 [P] [US3] Implement SvelteKit backend-for-frontend server hooks in `frontend/src/hooks.server.ts` (per the clarified BFF decision)

**Checkpoint**: All three user stories work independently; the UI provides a full submit-watch-download loop without direct API calls.

---

## Phase 6: User Story 4 - Opt into maximum-quality output when file size and time don't matter (Priority: P4)

**Goal**: An optional `max_quality` flag switches `hlg-gpu` to a near-lossless encode setting in the same single pass, GPU-only.

**Independent Test**: Submit the same source twice — `max_quality` unchecked vs. checked — and confirm the checked run produces a visibly larger, higher-quality result via the GPU path; confirm it fails clearly (not silently downgraded) when only the CPU profile is available.

### Implementation for User Story 4

- [X] T035 [US4] Add `max_quality` field handling to `POST /jobs`, with GPU-only validation (fails clearly if the resolved profile isn't GPU-accelerated) in `backend/src/tonemill/api/routes/jobs.py` (FR-027, FR-029) — extends T021
- [X] T036 [US4] Implement the near-lossless quality override within `hlg-gpu`'s existing single decode/tone-map/grade/encode pass — swap the encoder's quality setting for the initial near-lossless value (research.md #8) when `max_quality=true`; tone-mapping/grading parameters unchanged — in `backend/src/tonemill/profiles/hlg_gpu.py` (FR-028) — extends T022
- [X] T037 [P] [US4] Add the "maximum quality" checkbox to the frontend submit form, wired into the job-submission payload, in `frontend/src/routes/+page.svelte` (FR-027) — extends T031

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T038 [P] Add the MIT `LICENSE` file at the repository root (per spec.md: "open-source ... MIT licensed")
- [X] T039 [P] Add structured logging across API and worker for operator diagnosability in `backend/src/tonemill/`
- [X] T040 [P] Write the top-level `README.md`: `uv`/`ruff`/`ty` workflow, and `docker compose` usage (production single-command vs. dev split files)
- [X] T041 Security/consistency pass: confirm every presigned URL is time-limited and that source/result bytes never pass through the API process (FR-001, FR-006)
- [ ] T042 Run quickstart.md's end-to-end validation on both a GPU host and a CPU-only host, covering SC-001–SC-012 — **CPU-only path done**: a full clean `docker compose -f docker-compose.dev.yml up -d --build` (fresh volumes) through a real upload -> job -> `hlg-cpu` grading -> download cycle, verified `bt709`-tagged output (research.md #16). **GPU path still open** — no NVIDIA GPU available in any environment this has been validated in; needs the real production host.
- [X] T043 [P] Build the measurement-based profile-tuning tool: extract frames from the 4 reference scenes (overcast road, bright sky+sea, dusk with people, white rooftops), sweep candidate contrast/saturation values through a profile's grading step, measure per-scene highlight/channel clipping %, and report the highest value where the worst scene stays under 0.3% — in `backend/src/tonemill/tools/tune_profile.py` (FR-017)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational only. This is the MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational; *extends* US1's `registry.py`/`jobs.py`/`actors.py` (adds `auto` resolution on top of explicit-profile submission) rather than duplicating them — implement after US1.
- **User Story 3 (Phase 5)**: Depends on Foundational + US1's API endpoints being live (the UI calls them); independent of US2 and US4.
- **User Story 4 (Phase 6)**: Depends on Foundational + US1's `hlg-gpu` profile and `jobs.py` route (extends both); independent of US2 and US3, though its UI checkbox (T037) is naturally added after US3's submit page (T031) exists.
- **Polish (Phase 7)**: Depends on whichever user stories are in scope for the release being finished.

### Within Each User Story

- Foundational abstractions (profile interface, job store, storage client, progress parser) before any story-specific route/actor logic.
- Route/profile implementation files before the worker actor that wires them together.
- Story complete and independently testable before moving to the next priority.

### Parallel Opportunities

- Setup: T002, T003 in parallel; T005, T006, T007 in parallel; T009, T010 in parallel.
- Foundational: T014–T019 in parallel once T011–T013 (config → interface → registry) are done.
- US1: T020, T021, T022, T023 in parallel (four independent files); T024 and T025 are sequential (same file, and T024 depends on the profiles).
- US3: T028, T030 in parallel; T032, T034 in parallel with the rest of US3.
- Different user stories can be staffed in parallel by different developers once Foundational is complete, respecting the extends-relationships noted above (US2/US4 both touch files US1 created, so those two should not be worked by different people at the same time as US1 itself).

---

## Parallel Example: Foundational Phase

```bash
# After T011 (config.py), T012 (base.py), T013 (registry.py) are done, launch together:
Task: "Register d-log-m stub in backend/src/tonemill/profiles/dlog_m.py"
Task: "Implement Job model + Redis job store in backend/src/tonemill/jobs/store.py"
Task: "Implement S3-compatible storage client wrapper in backend/src/tonemill/storage/s3_client.py"
Task: "Implement ffmpeg progress utility in backend/src/tonemill/progress/ffmpeg_progress.py"
Task: "Set up FastAPI app skeleton in backend/src/tonemill/api/main.py"
Task: "Set up Dramatiq broker/actor skeleton in backend/src/tonemill/worker/actors.py"
```

## Parallel Example: User Story 1

```bash
Task: "Implement uploads API routes in backend/src/tonemill/api/routes/uploads.py"
Task: "Implement jobs API routes in backend/src/tonemill/api/routes/jobs.py"
Task: "Implement hlg-gpu profile pipeline in backend/src/tonemill/profiles/hlg_gpu.py"
Task: "Implement hlg-cpu profile pipeline in backend/src/tonemill/profiles/hlg_cpu.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks everything)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md steps 2–5 against User Story 1 alone (explicit profiles only, no `auto`, no UI, no `max_quality`)
5. Deploy/demo if ready — this is a complete, useful product on its own (submit via `curl`/script, get a correctly graded result back)

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. Add US1 → validate independently → MVP deployable
3. Add US2 → validate `auto` on both a GPU and a non-GPU host → deploy
4. Add US3 → validate the UI end-to-end → deploy (this is when a non-technical user can use Tonemill directly)
5. Add US4 → validate the near-lossless option → deploy
6. Polish → license, logging, docs, full quickstart.md validation

### Parallel Team Strategy

1. Team completes Setup + Foundational together.
2. Once Foundational is done, US1 must land first (US2 and US4 both extend files it creates).
3. After US1: Developer A takes US2 (auto-resolution), Developer B takes US3 (frontend, only needs US1's API), Developer C takes US4 (extends US1's `hlg-gpu`/`jobs.py`) — these three can proceed in parallel since none of them depend on each other, only on US1.

---

## Notes

- [P] tasks touch different files with no unmet dependency on an incomplete task.
- [Story] labels map every user-story-phase task to its spec.md priority for traceability.
- No dedicated per-story test tasks were generated (not requested in spec.md); test tooling is set up in Setup (T002 backend, T003 frontend) so tests can be added alongside implementation without additional infrastructure work.
- T038 (LICENSE) closes a gap: spec.md states the project is MIT-licensed, but no task before Polish actually creates that file.
- T021 now also covers `GET /profiles` (added after `/speckit-analyze` finding C1: this endpoint was fully specified in contracts/api.md and plan.md's file tree but had no implementing task). T043 (profile-tuning tool) was added after finding C2: FR-017 had zero task coverage.
- Avoid: touching `jobs.py`/`hlg_gpu.py`/`actors.py` from US2 and US4 concurrently with US1 itself — those tasks explicitly extend files US1 creates.
