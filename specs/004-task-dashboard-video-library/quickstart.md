# Quickstart: Validating the Task Dashboard & Video Library

A runnable validation guide — proves the feature works, referencing [contracts/api.md](./contracts/api.md) and [data-model.md](./data-model.md) rather than duplicating them. Assumes spec 001's stack is already up and end-to-end grading already works (see `specs/001-color-grading-pipeline/quickstart.md`); this guide only covers what's new.

## Prerequisites

- The full stack running (`docker compose -f docker-compose.dev.yml up --build`, plus a new `mongo` service — see research.md #1), including at least one previously-completed grading job so the dashboard/library aren't empty.
- A second copy of the exact same source file used for one already-completed job (byte-identical — e.g. just `cp` it), to exercise duplicate rejection.

## 1. Result files: naming and playability (P1)

```bash
curl -o result.mp4 "<result_url from GET /jobs/{id} or GET /videos>"
```
Expected:
- The filename itself (not just the URL) reads as `<recording-date>_<profile>.mp4` — e.g. `2026-07-22_16-35-09_hlg-gpu.mp4` — not a UUID (FR-016).
- Double-click `result.mp4` in Finder (macOS): it opens directly in Preview/Quick Look and plays, with no "cannot be opened" error and no separate conversion step (FR-020).
- `ffprobe -show_streams result.mp4` confirms `codec_tag_string=hvc1` (research.md #2) alongside the existing bt709 tagging already validated in spec 001.

## 2. Dashboard: dismiss & dismiss-all (P2)

```bash
# Submit a few files, let some finish/fail, keep at least one in progress.
curl -X POST $API/jobs/<a finished job id>/dismiss   # -> 204
curl $API/jobs                                         # confirm that job is now absent
curl -X POST $API/jobs/<a still-running job id>/dismiss  # -> 409, not dismissed
curl -X POST $API/jobs/dismiss-all                     # -> {"dismissed": N}
curl $API/jobs                                         # only the still-in-progress job(s) remain
```
In the UI: with everything either dismissed or in progress, confirm the "Dismiss all" button is disabled (FR-004). Confirm the video from the job you dismissed first is still present under `GET /videos` (FR-005).

## 3. Video library: folders and drag-and-drop (P3)

```bash
curl -X POST $API/folders -d '{"name":"Kavos shoot"}'          # -> {"folder_id": "...", "name": "..."}
curl -X POST $API/folders -d '{"name":"Kavos shoot"}'          # -> 409, name already exists
curl -X POST $API/videos/move -d '{"video_ids":["<id>"],"folder_id":"<folder_id>"}'
curl $API/videos                                                 # confirm folder_id and result_url reflect the move
```
In the UI:
- Create a folder; drag one unsorted video onto it — it disappears from unsorted and appears in the folder.
- Select several unsorted videos at once (multi-select) and move them into one folder in a single action (FR-011).
- Delete that folder; confirm its videos reappear in unsorted, not deleted (FR-015).

**Storage mirrors the UI (FR-019, SC-006)**: after moving a video into "Kavos shoot", list bucket contents (`mc ls` / AWS CLI) and confirm the object now lives at `results/kavos-shoot/<display_name>` — not at its original `results/unsorted/...` key.

## 4. Duplicate submission is rejected cleanly (P4)

```bash
# Re-upload the byte-identical copy from Prerequisites, then:
curl -X POST $API/jobs -d '{"s3_key":"<new upload of the same bytes>","profile":"<same profile as the original>","max_quality":false}'
# -> 409, { "detail": "This file was already processed with the \"<profile>\" profile." }
```
Expected:
- No new job appears in `GET /jobs` for that submission.
- The same file submitted with a *different* `profile` succeeds normally (FR-023).
- If the *original* job's only prior attempt through that profile is `failed` (not `done`), the resubmission is accepted, not rejected (FR-024).
- Submitting a batch of 3 files where the 2nd is the duplicate: the 1st and 3rd still upload and process normally (FR-026).

## Success criteria this proves

SC-001, SC-002 (step 1), SC-003 (step 2), SC-004, SC-006 (step 3), SC-005 (step 4).
