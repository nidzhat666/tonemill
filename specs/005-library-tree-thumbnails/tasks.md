# Tasks: Library Tree View & Video Thumbnails

**Input**: Design documents from `/specs/005-library-tree-thumbnails/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md (all present)

**Tests**: Not explicitly requested in spec.md, so no dedicated test-writing tasks are generated per user story, matching specs 001/004's precedent. Polish includes running quickstart.md's end-to-end validation, which is where the clip-count formula (research.md #3) and `POST /videos/delete` get exercised.

**Organization**: Tasks are grouped by user story (spec.md priorities P1–P4) to enable independent implementation and testing of each.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1–US4)
- File paths are exact, per plan.md's Project Structure

## Path Conventions

Web application layout per plan.md, extending specs 001/004's existing package: `backend/src/tonemill/` (Python, API + worker share one package), `frontend/src/` (SvelteKit).

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: The one piece of schema shared by two different stories (US1 writes one field, US3 writes the other, on the same document/model) — defining it once avoids two separate stories editing the same model definition.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 Add `thumbnail_key: str | None` and `preview_clip_keys: list[str]` (default `[]`) to the `Video` Pydantic model in `backend/src/tonemill/videos/store.py`, and in `_video_from_doc` read both via `doc.get("thumbnail_key")` / `doc.get("preview_clip_keys", [])` — **not** bracket access — matching the existing pattern already used there for `display_name`/`result_key`/`folder_id`. This is required, not stylistic: a video graded before this feature shipped has *neither* key present in its document at all, and bracket access would raise `KeyError` on every such document, crashing `GET /videos` for the whole library rather than showing that one video's "not ready yet" state (FR-004; data-model.md) — no index changes needed

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 2: User Story 1 - Scan the library by thumbnail instead of by filename alone (Priority: P1) 🎯 MVP

**Goal**: Every successfully graded video shows a static thumbnail (the frame at 5 seconds, or the nearest available frame for a shorter source) in its library row.

**Independent Test**: Open the library with at least one completed video and confirm its row shows a real thumbnail image (not a placeholder), sized so it's recognizable without dominating the row; for a video whose thumbnail isn't set (simulate by clearing `thumbnail_key` in Mongo), confirm a clear "not ready yet" state instead of a blank/hidden row.

### Implementation for User Story 1

- [X] T002 [P] [US1] Implement thumbnail extraction — one `ffmpeg -ss <t> -frames:v 1` call against the already-graded output, where `t = 5.0` when `duration_seconds >= 5.0`, else `t = duration_seconds / 2` (the video's midpoint, matching spec.md's Edge Cases example — not a near-the-end frame, which risks landing on a fade-out/black frame) (FR-001, FR-002) — as a function taking the output path and the source's probed `duration_seconds`, returning a local JPEG path, in `backend/src/tonemill/videos/preview.py` (NEW file; research.md #1)
- [X] T003 [US1] In the worker's grading-success path (`backend/src/tonemill/worker/pipeline.py`), after the existing result upload: generate the thumbnail (T002) using the already-probed duration, upload it to `results/{job_id}/thumbnail.jpg`, and include `thumbnail_key` in the same final `Video` document update that already sets `display_name`/`result_key` — depends on T001, T002
- [X] T004 [US1] Add `thumbnail_url` to `VideoResponse` and `_to_video_response` in `backend/src/tonemill/api/routes/videos.py` — presigned via `storage.presign_get_object(video.thumbnail_key)` when set, else `null` (FR-003, FR-004; contracts/api.md) — depends on T001
- [X] T005 [P] [US1] Add `thumbnail_url: string | null` to the `VideoResponse` interface in `frontend/src/lib/api-client.ts` — depends on T004
- [X] T006 [P] [US1] Implement `VideoThumbnail.svelte` (static-only for now — an `<img>` when `thumbnail_url` is set, a clearly-labeled "preview not ready yet" placeholder otherwise) in `frontend/src/lib/components/VideoThumbnail.svelte` (FR-003, FR-004; research.md #7) — depends on T005
- [X] T007 [US1] Wire `VideoThumbnail` into `frontend/src/lib/components/VideoCard.svelte`'s row, sized so the thumbnail is clearly visible without the row dominating the screen (FR-003) — depends on T006

**Checkpoint**: User Story 1 is fully functional and independently testable — every new video shows a real thumbnail (MVP).

---

## Phase 3: User Story 2 - Collapse folders to cut through clutter (Priority: P2)

**Goal**: Folders default to collapsed (name + count only); Unsorted defaults open; expanding a folder shows its videos indented beneath it.

**Independent Test**: With at least two folders each holding a video, open the library and confirm both start collapsed while Unsorted's videos are already visible; expand one folder and confirm only its videos appear, indented, while the other stays collapsed; reload and confirm every folder is back to collapsed.

### Implementation for User Story 2

- [X] T008 [P] [US2] Add `expandedFolderIds` (a `SvelteSet<string>`, empty by default = every folder collapsed) and `unsortedExpanded` (boolean, default `true`) plus `toggleFolderExpanded(folderId)`/`isFolderExpanded(folderId)` to `frontend/src/lib/stores/library.svelte.ts` (FR-012, FR-013, FR-015; research.md #6) — purely client-local, no API call, never persisted
- [X] T009 [P] [US2] Add an expand/collapse control to `frontend/src/lib/components/FolderCard.svelte`, wired to `libraryStore.toggleFolderExpanded`/`isFolderExpanded` (FR-014, FR-015) — depends on T008
- [X] T010 [US2] In `frontend/src/routes/library/+page.svelte`, only render a folder's video grid when `libraryStore.isFolderExpanded(folder.folder_id)` is true, and gate the Unsorted section's video grid on `libraryStore.unsortedExpanded`; apply left padding/indentation to video rows so their folder membership reads as visibly nested (FR-012, FR-016) — depends on T009
- [X] T011 [US2] Restyle `frontend/src/lib/components/VideoCard.svelte` from a full-width card into a compact list-row layout (thumbnail + name + actions in one row, not stacked), keeping the thumbnail clearly visible while the row stays compact enough that several rows fit without excessive scrolling (FR-017) — depends on T007 (US1's thumbnail integration), extends US1's VideoCard changes

**Checkpoint**: User Stories 1 and 2 both work independently; the library reads as a real folder tree.

---

## Phase 4: User Story 3 - Preview a video's content by hovering, before downloading it (Priority: P3)

**Goal**: Hovering a video's thumbnail plays a short, silent, browser-playable montage of clips sampled across the footage; moving away reverts to the static thumbnail; a second hover in the same session replays instantly.

**Independent Test**: Hover a video's thumbnail for a full preview loop and confirm real motion plays (not repeated stills) sampled across the video, not clustered at the start; move away and confirm it reverts to the static thumbnail; hover the same video again and confirm no loading delay. Separately, confirm a source under 10 seconds yields a reduced (not 10) clip count.

### Implementation for User Story 3

- [X] T012 [P] [US3] Implement the clip-count/spacing pure function — `N = max(1, min(10, floor(duration_seconds / 1.5)))`, clip `i` starts at `i * (duration_seconds / N)` and runs 1.5s (or the video's full duration when `N == 1` and `duration_seconds < 1.5`) — in `backend/src/tonemill/videos/preview.py` (FR-005, FR-006; research.md #3) — depends on T002 (same file)
- [X] T013 [US3] Implement preview-clip extraction — for each `(start, length)` from T012, one `ffmpeg -ss <start> -t <length> -c:v libx264 -preset veryfast -an -vf scale=480:-2` call against the already-graded output — returning a list of local clip paths, in `backend/src/tonemill/videos/preview.py` (FR-005, FR-006, FR-009; research.md #2, #3) — depends on T012
- [X] T014 [US3] In the worker's grading-success path (`backend/src/tonemill/worker/pipeline.py`), extend T003's thumbnail step to also generate the preview clips (T013), upload each to `results/{job_id}/preview-{n}.mp4`, and include `preview_clip_keys` (ordered) in the same final `Video` document update — depends on T001, T003, T013
- [X] T015 [US3] Add `preview_clip_urls: list[str]` (ordered, presigned) to `VideoResponse`/`_to_video_response` in `backend/src/tonemill/api/routes/videos.py` (FR-005; contracts/api.md) — depends on T004, T014
- [X] T016 [P] [US3] Add `preview_clip_urls: string[]` to the `VideoResponse` interface in `frontend/src/lib/api-client.ts` — depends on T015
- [X] T017 [US3] Extend `VideoThumbnail.svelte` with hover-driven playback — a single `<video muted playsinline>`, `src` set to `preview_clip_urls[0]` only on `pointerenter` (never eagerly, FR-010), advancing to the next URL on the video's own `ended` event and looping (FR-007), reverting to the static `<img>` on `pointerleave` (FR-008) and leaving `src` set afterward so a repeat hover replays instantly with no new fetch (FR-011; research.md #4, #7) — depends on T006, T016

**Checkpoint**: All three user stories work independently; hovering any ready video plays a real, in-browser preview.

---

## Phase 5: User Story 4 - Permanently delete videos that are no longer needed (Priority: P4)

**Goal**: Selecting one or more videos and confirming deletion permanently removes their library entries and every stored file they own; canceling changes nothing; re-uploading a deleted video's source file afterward is accepted as new, not blocked as a duplicate.

**Independent Test**: Select one or more videos (including one in a folder), trigger delete, confirm, and verify they're gone from the library and their folder still exists with a reduced count; separately, trigger delete and cancel, and verify nothing changed. Re-upload a deleted video's original source through the same profile and confirm it's accepted.

### Implementation for User Story 4

- [X] T018 [P] [US4] Reintroduce `delete_object(key: str)` on `S3StorageClient` in `backend/src/tonemill/storage/s3_client.py` (research.md #5)
- [X] T019 [P] [US4] Add `VideoStore.delete(video_id)` (a real `delete_one`, raising `VideoNotFoundError` if missing) to `backend/src/tonemill/videos/store.py` (FR-021; data-model.md) — depends on T001
- [X] T020 [US4] Implement `POST /videos/delete` in `backend/src/tonemill/api/routes/videos.py` — for each requested (existing) video, delete its `result_key`, `thumbnail_key` (if set), and every entry in `preview_clip_keys` from storage (tolerating an already-missing object), then `VideoStore.delete` it; unknown IDs are skipped, not errors; returns `{"deleted": N}` (FR-018, FR-021, FR-022; contracts/api.md) — depends on T018, T019
- [X] T021 [P] [US4] Add `deleteVideos(videoIds: string[])` to the typed API client in `frontend/src/lib/api-client.ts` (`POST /videos/delete`) — depends on T020
- [X] T022 [P] [US4] Add `deleteVideos(videoIds?: string[])` to `frontend/src/lib/stores/library.svelte.ts` — calls the API, removes the deleted videos from local `videos`, clears selection (mirrors `moveVideos`'s shape) — depends on T021
- [X] T023 [P] [US4] Scaffold a local `alert-dialog` wrapper under `frontend/src/lib/components/ui/alert-dialog/`, matching the project's existing thin-wrapper convention (`checkbox`, `button`, etc.) over `bits-ui`'s already-installed `AlertDialog` (research.md #8) — no new dependency
- [X] T024 [US4] Add a "Delete selected" control to `frontend/src/routes/library/+page.svelte` — disabled when `libraryStore.selectedVideoIds` is empty (FR-023), opens the T023 confirmation dialog naming the selected count, and on confirm calls `libraryStore.deleteVideos()`; canceling closes the dialog with no call made (FR-019, FR-020) — depends on T022, T023

**Checkpoint**: All four user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T025 [P] Add structured logging for the new operations (thumbnail/preview clips generated, video deleted) in `backend/src/tonemill/`, consistent with the existing logging setup
- [X] T026 Run quickstart.md's end-to-end validation — thumbnail/clip generation and codec (SC-001, SC-003), folder tree defaults (SC-002, SC-004, SC-005), hover playback and repeat-hover speed (SC-003), delete confirm/cancel and post-delete dedup behavior (SC-006, SC-007)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — BLOCKS all user stories.
- **User Story 1 (Phase 2)**: Depends on Foundational only. This is the MVP.
- **User Story 2 (Phase 3)**: Depends on Foundational + US1's `VideoCard`/`VideoThumbnail` already existing (T011 explicitly extends T007's integration) — not independent of US1 the way specs 001/004's stories usually are, since there's only one video row to restyle.
- **User Story 3 (Phase 4)**: Depends on Foundational + US1 (extends T002/T003's `preview.py`/`pipeline.py` work and T006's `VideoThumbnail` component); independent of US2 (touches different files: `worker/pipeline.py`, `videos/preview.py`, `VideoThumbnail.svelte` vs. US2's `library.svelte.ts`, `FolderCard.svelte`, `+page.svelte`, `VideoCard.svelte`).
- **User Story 4 (Phase 5)**: Depends on Foundational only — genuinely independent of US1/US2/US3 (different files throughout: `s3_client.py`, a new `POST /videos/delete` route, new `deleteVideos` store/API methods, a new UI primitive). Could be built first, in parallel with any of the others, without any rework.
- **Polish (Phase 6)**: Depends on whichever user stories are in scope for the release being finished.

### Within Each User Story

- Backend generation/storage before the API field that exposes it, before the frontend type, before the UI that renders it.
- US2 and US3 both extend files US1 created (`VideoCard.svelte`/`VideoThumbnail.svelte`, `videos/preview.py`) rather than duplicating them.

### Parallel Opportunities

- Foundational: single task, nothing to parallelize.
- US1: T002 can start immediately after Foundational; T003 depends on it. T004 depends only on Foundational (T001), so it can proceed alongside T002/T003. T005/T006 depend on T004/nothing respectively and can run together; T007 is the integration point.
- US2: T008 first; T009 depends on it; T010 depends on T009; T011 depends on US1's T007 (separate story, sequenced after).
- US3: T012 → T013 → T014 (same file/sequential); T015 depends on T014; T016 can run in parallel with T015 once T014 lands; T017 is the integration point, depends on T016 and US1's T006.
- US4: T018, T019 in parallel (different files); T020 depends on both; T021 depends on T020; T022 depends on T021; T023 is independent of the rest of US4 (new, self-contained UI primitive) and can be built any time; T024 is the integration point.
- **Staffing**: once Foundational + US1 are done, US2 and US3 can be worked by different people in parallel (disjoint files, per Phase Dependencies above); US4 can be worked by a third person in parallel with *both*, starting as soon as Foundational is done — it never touches a file either US1, US2, or US3 touches.

---

## Parallel Example: User Story 1

```bash
Task: "Implement thumbnail extraction in backend/src/tonemill/videos/preview.py"
Task: "Add thumbnail_url to VideoResponse in backend/src/tonemill/api/routes/videos.py"
# After both land:
Task: "Add thumbnail_url to the VideoResponse interface in frontend/src/lib/api-client.ts"
Task: "Implement VideoThumbnail.svelte (static-only)"
```

## Parallel Example: User Story 4

```bash
Task: "Reintroduce delete_object on S3StorageClient in backend/src/tonemill/storage/s3_client.py"
Task: "Add VideoStore.delete in backend/src/tonemill/videos/store.py"
Task: "Scaffold the alert-dialog UI primitive in frontend/src/lib/components/ui/alert-dialog/"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (one task)
2. Complete Phase 2: User Story 1
3. **STOP and VALIDATE**: run quickstart.md's thumbnail section against a fresh job
4. Deploy/demo if ready — every new video shows a real, recognizable thumbnail instead of a wall of filenames

### Incremental Delivery

1. Foundational → foundation ready
2. Add US1 → validate independently → MVP deployable (thumbnails)
3. Add US2 → validate folder defaults/indentation → deploy (the library reads as a real tree)
4. Add US3 → validate hover playback, codec, and lazy-fetch timing → deploy (full preview experience)
5. Add US4 → validate confirm/cancel and post-delete dedup behavior → deploy (cleanup capability)
6. Polish → logging, full quickstart.md validation

### Parallel Team Strategy

1. Foundational lands first (single task, fast).
2. US1 lands next (US2 and US3 both extend files it creates).
3. Once US1 is done: Developer A takes US2 (folder tree, frontend-only), Developer B takes US3 (preview clips, extends US1's worker/component work) — disjoint files, no coordination needed. Developer C can take US4 any time after Foundational, in parallel with either.

---

## Notes

- [P] tasks touch different files with no unmet dependency on an incomplete task.
- [Story] labels map every user-story-phase task to its spec.md priority for traceability.
- No dedicated per-story test tasks were generated (not requested in spec.md, matching specs 001/004's precedent); if added later, the clip-count/spacing formula (T012) is the highest-value candidate for a pure-function unit test (no I/O, easy to assert exact boundaries), and `POST /videos/delete` (T020) the highest-value integration test (real Mongo + MinIO, per specs 001/004's own testing philosophy).
- T011 (US2) and T017 (US3) both extend components US1 built (T007's `VideoCard` integration, T006's `VideoThumbnail`) rather than duplicating them — avoid two people editing `VideoThumbnail.svelte` at the same time across US1/US3.
- Avoid: touching `backend/src/tonemill/videos/preview.py` from US1 (T002) and US3 (T012/T013) concurrently without coordinating — US3 extends the same file US1 creates.
