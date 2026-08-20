# Tasks: Task Dashboard & Video Library

**Input**: Design documents from `/specs/004-task-dashboard-video-library/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md (all present)

**Tests**: Not explicitly requested in spec.md, so no dedicated test-writing tasks are generated per user story, matching spec 001's own precedent. Test *tooling* needs no new setup beyond what spec 001 already established (pytest/fakeredis/moto, Vitest/Playwright) except a real MongoDB for integration tests, provisioned by the same `mongo` service Setup adds. Polish includes running quickstart.md's end-to-end validation.

**Organization**: Tasks are grouped by user story (spec.md priorities P1–P4) to enable independent implementation and testing of each.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1–US4)
- File paths are exact, per plan.md's Project Structure

## Path Conventions

Web application layout per plan.md, extending spec 001's existing package: `backend/src/tonemill/` (Python, API + worker share one package), `frontend/src/` (SvelteKit), root-level `docker-compose*.yml`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the one new piece of infrastructure this feature needs (MongoDB) to the stack — nothing story-specific yet.

- [X] T001 Add `pymongo>=4.9` (native async API, not Motor — research.md #1) to `backend/pyproject.toml` via `uv`
- [X] T002 [P] Add a `mongo` service (single-node, healthcheck, named volume) to `docker-compose.dev.yml`, and wire `api`/`worker`'s `depends_on` to it, mirroring the existing `redis`/`minio` pattern
- [X] T003 [P] Add the same `mongo` service + `depends_on` wiring to `docker-compose.yml` (production)

**Checkpoint**: MongoDB is reachable from both compose stacks. No application code yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The durable storage layer every user story builds on — Mongo client, `Video`/`Folder` models and stores, and the S3-client/fingerprint primitives that both naming (US1) and duplicate detection (US4) share.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add `mongo_url`/`mongo_db` settings to `backend/src/tonemill/config.py` (research.md #1)
- [X] T005 [P] Define the `Video` and `Folder` Pydantic models and index setup — unique partial `(fingerprint, profile, max_quality)` scoped to `status in {in_progress, done}`, unique partial `display_name`, unique case-insensitive `folders.name`, non-unique `videos.folder_id` — in `backend/src/tonemill/videos/store.py` (data-model.md)
- [X] T006 Implement `VideoStore` (create, get, update, list_all with a `status` filter, `find_by_fingerprint`) in `backend/src/tonemill/videos/store.py` (data-model.md) — depends on T005
- [X] T007 [P] Implement `FolderStore` (create, get, list with video counts, delete) in `backend/src/tonemill/videos/store.py` (data-model.md) — depends on T005
- [X] T008 [P] Add `get_mongo_client`/`get_video_store`/`get_folder_store` factories (`lru_cache`, mirroring the existing `get_job_store`) in `backend/src/tonemill/dependencies.py` — depends on T006, T007
- [X] T009 [P] Extend `S3StorageClient` with `read_range` (ranged `GET`, for fingerprinting), `copy_object`, and `delete_object` (for folder-move re-keying) in `backend/src/tonemill/storage/s3_client.py` (research.md #3, #5)
- [X] T010 [P] Implement the content-fingerprint helper (`sha256(size_bytes || first 1MiB || last 1MiB)` via `read_range`) in `backend/src/tonemill/videos/fingerprint.py` (research.md #3) — depends on T009

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Downloaded results are correctly named and actually playable (Priority: P1) 🎯 MVP

**Goal**: Every result file is named `<recorded creation date>_<profile>.mp4` (disambiguated on collision) instead of a UUID, and opens correctly in the operating system's default media viewer (macOS Quick Look/Preview).

**Independent Test**: Process a source clip through any profile, download the result, and confirm (a) the file name reflects the source's recording date and the profile used, and (b) the file opens correctly in the OS's default media viewer without conversion.

### Implementation for User Story 1

- [X] T011 [P] [US1] Add a `mp4_playback_compatibility_args()` helper (`-tag:v hvc1`, `-movflags +faststart`) alongside `output_color_tagging_args()` in `backend/src/tonemill/profiles/base.py` (FR-020, research.md #2)
- [X] T012 [US1] Apply `mp4_playback_compatibility_args()` in `hlg_gpu.py`'s `build_command` output flags (FR-020) — depends on T011
- [X] T013 [US1] Apply `mp4_playback_compatibility_args()` in `hlg_cpu.py`'s `build_command` output flags (FR-020) — depends on T011
- [X] T014 [P] [US1] Implement display-name formatting (`"{recorded_created_at:%Y-%m-%d_%H-%M-%S}_{profile}.mp4"`, callable with a disambiguating suffix) as a pure function in `backend/src/tonemill/videos/naming.py` (FR-016, FR-018, research.md #4)
- [X] T015 [US1] Extend the worker's existing duration probe into one combined `ffprobe` call that also reads the source's `format_tags.creation_time`, falling back to the job's `created_at` when the tag is absent, in `backend/src/tonemill/progress/ffmpeg_progress.py` (FR-017, research.md #4)
- [X] T016 [US1] In `POST /jobs` (`backend/src/tonemill/api/routes/jobs.py`), compute the source's content fingerprint (T010) and create a `Video` document (`status=in_progress`, `fingerprint`, `source_key`, `profile`, `max_quality`) via `VideoStore` alongside the existing `Job` creation (data-model.md) — depends on T006, T010
- [X] T017 [US1] In the worker's grading pass (`backend/src/tonemill/worker/pipeline.py`), on success: generate `display_name` (T014) from T015's recorded creation date and the resolved profile, retrying with a disambiguating suffix on a `VideoStore` uniqueness conflict; upload the result under `results/unsorted/{display_name}` instead of the current UUID key; update the `Video` document (`status=done`, `display_name`, `result_key`, **and `profile` set to the resolved profile name** — `Video.profile` is written as the *requested* profile at T016 and, for an `auto` submission, is never otherwise corrected, so `GET /videos` would otherwise keep showing `"auto"` instead of the actual profile used) alongside the existing `Job` update. On failure, update the `Video` document to `status=failed` (FR-016–FR-019; data-model.md) — depends on T006, T012, T013, T014, T015, T016

**Checkpoint**: User Story 1 is fully functional and independently testable — every new result is correctly named and Quick-Look-playable (MVP).

---

## Phase 4: User Story 2 - Dashboard stays focused on jobs that need attention (Priority: P2)

**Goal**: Failed jobs get a per-job "Dismiss"; a "Dismiss all" clears every completed/failed job in one action and is disabled when there's nothing to dismiss; dismissing never touches the underlying video.

**Independent Test**: Submit several files so the list contains a mix of in-progress, completed, and failed jobs. Dismiss a single failed job, then use "Dismiss all" to clear the rest, and confirm only in-progress jobs remain visible.

### Implementation for User Story 2

- [X] T018 [US2] Add a `dismissed: bool = False` field to `Job` (`_to_hash`/`_from_hash`), plus `dismiss(job_id)` and `dismiss_all()` methods on `JobStore` that only ever affect `done`/`failed` jobs, and make `list_all()` exclude `dismissed=true` records by default, in `backend/src/tonemill/jobs/store.py` (FR-001–FR-006, research.md #6)
- [X] T019 [US2] Add `POST /jobs/{id}/dismiss` (404 unknown job, 409 if still `queued`/`running`) and `POST /jobs/dismiss-all` (returns `{"dismissed": N}`) endpoints in `backend/src/tonemill/api/routes/jobs.py` (FR-002–FR-004; contracts/api.md §Jobs) — depends on T018
- [X] T020 [P] [US2] Add `dismiss`/`dismissAll` methods to the typed API client in `frontend/src/lib/api-client.ts` — depends on T019
- [X] T021 [US2] Add a `remove(id)` method to `JobsStore` and a "Dismiss" button to failed job cards that calls it on a successful dismiss, in `frontend/src/lib/stores/jobs.svelte.ts` and `frontend/src/lib/components/JobCard.svelte` (FR-002) — depends on T020
- [X] T022 [US2] Add a bulk-clear method to `JobsStore` (drop every non-in-progress item) and a "Dismiss all" control to the dashboard — disabled whenever nothing is dismissable, computed from `jobsStore.items`' current statuses — calling `POST /jobs/dismiss-all` and then the new bulk-clear method, in `frontend/src/lib/stores/jobs.svelte.ts` and `frontend/src/routes/+page.svelte` (FR-003, FR-004) — depends on T020

**Checkpoint**: User Stories 1 and 2 both work independently; the dashboard stays readable as job volume grows.

---

## Phase 5: User Story 3 - Organize processed videos into folders (Priority: P3)

**Goal**: A new "Library" tab where completed videos can be created into flat folders and organized via drag-and-drop (single or multi-selected), with storage in S3 mirroring the same folders and readable names.

**Independent Test**: With at least one completed job in the library, create a folder, drag a single video into it, then multi-select several unsorted videos and move them into that same folder in one action; confirm the folder's contents and each video's storage location reflect the move.

### Implementation for User Story 3

- [X] T023 [P] [US3] Implement `GET /videos` (list `status=done` videos, newest first, with a presigned `result_url`) in `backend/src/tonemill/api/routes/videos.py` (FR-007; contracts/api.md §Videos) — depends on T006
- [X] T024 [P] [US3] Implement `GET /folders` (with per-folder video counts), `POST /folders` (409 on a case-insensitive name conflict), `DELETE /folders/{id}` in `backend/src/tonemill/api/routes/folders.py` (FR-008, FR-009; contracts/api.md §Folders) — depends on T007
- [X] T025 [US3] Implement a shared video-relocation helper — `copy_object`+`delete_object` re-key to `results/{folder-slug|"unsorted"}/{display_name}`, then update the `Video` document's `folder_id`/`result_key` only once the copy succeeds — in `backend/src/tonemill/videos/relocate.py` (kept out of `store.py` since it needs both `S3StorageClient` and `VideoStore`, matching the existing storage/domain separation) — and wire `POST /videos/move` in `backend/src/tonemill/api/routes/videos.py` to call it per selected video: validate a non-null `folder_id` exists via `FolderStore` (404 if not), skip unknown `video_id`s, and treat a video already in the target folder as a no-op that still counts toward the response's `moved` total (FR-010–FR-014, FR-019; contracts/api.md §Videos) — depends on T006, T007, T009, T023
- [X] T026 [US3] Wire `DELETE /folders/{id}` (`backend/src/tonemill/api/routes/folders.py`) to call the same relocation helper (T025) for every video assigned to that folder, moving each to `folder_id=null`/`results/unsorted/...`, before removing the folder document (FR-015, FR-019) — depends on T024, T025
- [X] T027 [P] [US3] Add `listVideos`, `listFolders`, `createFolder`, `deleteFolder`, `moveVideos` to the typed API client in `frontend/src/lib/api-client.ts` — depends on T023, T024, T025
- [X] T028 [P] [US3] Implement the library store (videos, folders, current multi-selection state) in `frontend/src/lib/stores/library.svelte.ts` — depends on T027
- [X] T029 [US3] Add tab navigation between Dashboard and Library in `frontend/src/routes/+layout.svelte`
- [X] T030 [P] [US3] Implement `FolderCard.svelte` (native HTML5 drop target, name, video count, delete action) in `frontend/src/lib/components/FolderCard.svelte` (research.md #7) — depends on T028
- [X] T031 [P] [US3] Implement `VideoCard.svelte` (draggable, multi-select toggle) in `frontend/src/lib/components/VideoCard.svelte` (research.md #7) — depends on T028
- [X] T032 [US3] Implement the library page — folder list, unsorted/foldered video grid, create-folder action, drag-and-drop of one or a multi-selected batch onto a folder, bulk-move action — in `frontend/src/routes/library/+page.svelte`. The unsorted section is itself a valid drop target (`folder_id: null`), not just the named `FolderCard`s, so a video can be dragged back out of a folder to unsorted (FR-007–FR-014) — depends on T029, T030, T031

**Checkpoint**: All three user stories work independently; videos can be organized into folders both on-site and in storage.

---

## Phase 6: User Story 4 - Re-uploading an already-processed file is rejected cleanly (Priority: P4)

**Goal**: Submitting a file already processed (or in progress) through the same profile and quality setting is rejected with a friendly error instead of creating a duplicate job.

**Independent Test**: Submit a file through a given profile, let it finish (or while it's still in progress), then submit the exact same file through the same profile again and confirm it is rejected with a clear message rather than creating a second job.

### Implementation for User Story 4

- [X] T033 [US4] In `POST /jobs` (`backend/src/tonemill/api/routes/jobs.py`), after computing the fingerprint (T016) and before creating the `Job`/`Video` documents, query `VideoStore.find_by_fingerprint(fingerprint, profile, max_quality)` scoped to `status in {in_progress, done}` and return `409` with a friendly, profile-naming message when a match exists (FR-021–FR-025; contracts/api.md §Jobs) — depends on T006, T016
- [X] T034 [US4] Catch a losing concurrent insert against the Foundational unique index (T005) — i.e. `DuplicateKeyError` on `Video` creation — and translate it into the same `409` response as T033, closing the race between two near-simultaneous submissions of the same file; also explicitly fail the just-created `Job` record in this path rather than leaving it stuck `queued` forever (no `grade_video.send()` runs for a rejected submission) (FR-021, Edge Cases; data-model.md) — depends on T033
- [X] T035 [P] [US4] Surface the `409` duplicate response as a friendly, per-file error on the dashboard — already covered by `+page.svelte`'s existing failed-submission catch block (no job card with a `jobId` is ever created for a rejected submission); the one real gap found was `api-client.ts`'s generic error formatting leaking a raw HTTP status-code prefix into every displayed message, fixed there so the duplicate (and every other) rejection reads as plain text (FR-022, FR-026) — depends on T033

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T036 [P] Add structured logging for the new store operations (video created, dismissed, moved, duplicate-rejected) in `backend/src/tonemill/`, consistent with the existing logging setup
- [X] T037 [P] Update the root `README.md`'s local-dev instructions to mention the new `mongo` service/dependency
- [X] T038 Ran quickstart.md's validation against the real dev stack (`docker compose -f docker-compose.dev.yml up --build`, all 6 services healthy including the new `mongo`): backend test suite extended with a real session-scoped MongoDB container (`tests/conftest.py`, fixing a genuine cross-event-loop regression the new lifespan-time Mongo connection introduced in `tests/integration/test_smoke.py`) — 25/25 passing. Live-verified against the running stack: `-tag:v hvc1`/`+faststart` confirmed via `ffprobe`/byte-offset inspection on a direct encode (SC-001's actual mechanism); `Video` document lifecycle (`in_progress`→`failed`, `original_filename`/`fingerprint` capture) via MongoDB inspection; dismiss/dismiss-all including the in-progress-is-never-dismissable and nothing-to-dismiss cases (SC-003); duplicate rejection — in-progress blocks (409), failed does not (FR-024), different profile does not (FR-023) — via direct API calls (SC-005); folder create/move/delete with real `copy_object`/`delete_object` re-keying confirmed via MinIO bucket listing before/after (SC-004, SC-006). **Not validated**: a full real HLG-source grading pass end-to-end — every synthetic test clip generated for this session hit a pre-existing `zscale`/libzimg "no path between colorspaces" limitation with lavfi-generated frames (reproduced identically with and without this feature's changes, confirming it's unrelated — spec 001's chain was validated against real DJI footage, not synthetic ones). SC-002 (naming format itself) validated via the `Video` document/`GET /videos` response, not via a fresh worker-generated file.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational only. This is the MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational only (touches `jobs/store.py`/`api/routes/jobs.py`, disjoint from US1's naming/probe changes in the same files — see Parallel Opportunities caveat below); independent of US1, US3, US4.
- **User Story 3 (Phase 5)**: Depends on Foundational; independent of US1, US2, US4 (its `Video`/`Folder` reads don't require US1's naming logic to have run — an empty library is a valid state to build/test the folder UI against).
- **User Story 4 (Phase 6)**: Depends on Foundational + US1's T016 (fingerprint computed and `Video` document created at submission) — *extends* `POST /jobs` with the actual rejection check rather than duplicating the fingerprint step.
- **Polish (Phase 7)**: Depends on whichever user stories are in scope for the release being finished.

### Within Each User Story

- Foundational stores/clients (`VideoStore`, `FolderStore`, `S3StorageClient` extensions, fingerprint helper) before any story-specific route/worker logic.
- Backend endpoints before the frontend API-client methods that call them, before the UI that uses them.
- Story complete and independently testable before moving to the next priority.

### Parallel Opportunities

- Setup: T002, T003 in parallel.
- Foundational: T005 first; then T006, T007 in parallel; then T008, T009 in parallel; T010 after T009.
- US1: T011 and T014 in parallel (independent files); T012/T013 sequential after T011 (each its own profile file); T015 independent of T011–T014; T016 depends on Foundational only; T017 is the integration point, depends on everything else in US1.
- US2: T018 → T019 → T020, then T021/T022 both depend on T020 but touch different files (`JobCard.svelte` vs `+page.svelte`) so can proceed together once T020 lands.
- US3: T023 and T024 in parallel (different route files); T025 depends on T023 (same file, `videos.py`) and T024/T007 (validates `folder_id` via `FolderStore`); T027 after T023–T025; T028 after T027; T030/T031 in parallel after T028; T032 is the integration point.
- US4: T033 → T034 sequential (same file, same endpoint); T035 (frontend) can proceed in parallel with T034 once T033 lands.
- **Caveat**: US1 (T015–T017) and US2 (T018) both touch files under `backend/src/tonemill/jobs/` and `api/routes/jobs.py` in the same window — these two stories should not be worked by different people concurrently without coordinating on `jobs.py`'s diff, even though they're logically independent.
- Different user stories can otherwise be staffed in parallel once Foundational is complete.

---

## Parallel Example: Foundational Phase

```bash
# After T004 (config.py) and T005 (models/indexes) are done, launch together:
Task: "Implement VideoStore in backend/src/tonemill/videos/store.py"
Task: "Implement FolderStore in backend/src/tonemill/videos/store.py"
# Then, after both land:
Task: "Add Mongo dependency factories in backend/src/tonemill/dependencies.py"
Task: "Extend S3StorageClient with read_range/copy_object/delete_object in backend/src/tonemill/storage/s3_client.py"
```

## Parallel Example: User Story 3

```bash
Task: "Implement GET /videos in backend/src/tonemill/api/routes/videos.py"
Task: "Implement GET/POST /folders, DELETE /folders/{id} in backend/src/tonemill/api/routes/folders.py"
# After both land:
Task: "Implement FolderCard.svelte"
Task: "Implement VideoCard.svelte"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks everything)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md's naming/playability section against a fresh job
5. Deploy/demo if ready — every new result is correctly named and actually playable, the core defect this feature exists to fix

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. Add US1 → validate independently → MVP deployable
3. Add US2 → validate dismiss/dismiss-all → deploy (dashboard stays usable at volume)
4. Add US3 → validate folder drag-and-drop + storage mirroring → deploy (library becomes usable)
5. Add US4 → validate duplicate rejection → deploy
6. Polish → logging, docs, full quickstart.md validation

### Parallel Team Strategy

1. Team completes Setup + Foundational together.
2. Once Foundational is done: Developer A takes US1 (MVP, should land first since US4 extends it), Developer B takes US3 (only needs Foundational's `VideoStore`/`FolderStore`, not US1's naming logic), Developer C takes US2 (coordinate with US1 on `api/routes/jobs.py` — see Parallel Opportunities caveat).
3. US4 starts once US1's T016 (fingerprint-at-submission) has landed.

---

## Notes

- [P] tasks touch different files with no unmet dependency on an incomplete task.
- [Story] labels map every user-story-phase task to its spec.md priority for traceability.
- No dedicated per-story test tasks were generated (not requested in spec.md, matching spec 001's precedent); integration tests for the new Mongo-backed stores should follow spec 001's existing pattern (real Redis + MinIO containers) extended with a real MongoDB container, not `mongomock` (research.md #1's testing philosophy).
- T016 (US1) intentionally does the fingerprint *computation* and `Video` document creation — US4 (T033) only *adds the rejection check* against that same data. This ordering exists so the `display_name`/`fingerprint` unique indexes are never violated by a document missing a fingerprint, regardless of which stories have shipped.
- Avoid: touching `api/routes/jobs.py` from US1, US2, and US4 concurrently without coordinating — all three extend it (US1 adds Video-doc creation + fingerprinting, US2 adds dismiss endpoints, US4 adds the duplicate-rejection check).
