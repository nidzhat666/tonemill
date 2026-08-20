# API Contract: Task Dashboard & Video Library

Extends `specs/001-color-grading-pipeline/contracts/api.md`. Only new and changed endpoints are documented here; `POST /uploads` and its sub-resources, and `GET /jobs/{job_id}`, are unchanged.

## Jobs (changed)

### `POST /jobs` (changed — duplicate rejection added)

Request/response shape is unchanged from spec 001. New behavior only:

Errors (added):
- `409` — the uploaded source is a duplicate (research.md #3: same content fingerprint) of a file already `done` or currently `in_progress` under the *same* `profile` and `max_quality` combination (FR-021, FR-022). Response body carries a message meant to be shown to the user as-is:
  ```json
  { "detail": "This file was already processed with the \"hlg-gpu\" profile." }
  ```
  Not returned for the same file under a different profile or a different `max_quality` (FR-023, FR-025), nor when the only prior match `failed` (FR-024).

### `GET /jobs` (changed — dismissed jobs excluded)

Unchanged response shape. Now never includes a job whose `dismissed = true` (FR-002–FR-005) — dismissal is applied server-side, not left to the client to filter.

### `POST /jobs/{job_id}/dismiss` (new)

Dismiss one finished job from the dashboard (FR-002). No effect on its video, if any (FR-005).

Response `204`.

Errors: `404` — unknown job. `409` — job is still `queued` or `running` (FR-004's "in progress" jobs can't be dismissed, individually or otherwise).

### `POST /jobs/dismiss-all` (new)

Dismiss every job that is not currently `queued` or `running` (FR-003). A no-op call (nothing eligible) still returns `200` with `dismissed: 0` — the *client's* "Dismiss all" control is expected to disable itself when it already knows there's nothing to dismiss (FR-004), this endpoint doesn't need to error for that case.

Response `200`:
```json
{ "dismissed": 4 }
```

## Videos (new)

### `GET /videos`

List every successfully completed processed video (FR-007), newest first.

Response `200`:
```json
[
  {
    "video_id": "string",
    "display_name": "2026-07-22_16-35-09_hlg-gpu.mp4",
    "profile": "hlg-gpu",
    "recorded_created_at": "2026-07-22T16:35:09Z",
    "folder_id": "string|null",
    "result_url": "https://storage/...(presigned, time-limited)"
  }
]
```

### `POST /videos/move`

Move one or more videos into a folder, or back to unsorted — covers both the single drag-and-drop case and the multi-select bulk case (FR-010, FR-011, FR-014) with one endpoint. A move is a `Video.folder_id` write only; the underlying object's storage location never changes (FR-019, research.md #5), so this endpoint's cost doesn't depend on file size or count.

Request:
```json
{ "video_ids": ["string", "..."], "folder_id": "string|null" }
```
`folder_id: null` moves every listed video to unsorted.

Response `200`:
```json
{ "moved": 3 }
```
A `video_id` already in the target folder is counted as moved but skips even the `folder_id` write (Edge Cases: dragging a video onto the folder it's already in is a no-op for that video).

Errors: `404` — `folder_id` doesn't reference an existing folder (when non-null); any unknown `video_id` in the list is silently skipped rather than failing the whole batch, so one stale ID (e.g. a video deleted by another session) never blocks moving the rest.

## Folders (new)

### `GET /folders`

List every folder (FR-008), each with its current video count.

Response `200`:
```json
[{ "folder_id": "string", "name": "Kavos shoot", "video_count": 12 }]
```

### `POST /folders`

Create a folder (FR-008, FR-009 — flat only, no parent field accepted).

Request: `{ "name": "Kavos shoot" }`

Response `201`: `{ "folder_id": "string", "name": "Kavos shoot" }`

Errors: `409` — a folder with that name (case-insensitive) already exists.

### `DELETE /folders/{folder_id}`

Delete a folder. Every video assigned to it returns to unsorted; no video is deleted (FR-015).

Response `204`.

Errors: `404` — unknown folder.

## Notes for `/speckit-tasks`

- The duplicate-fingerprint computation (research.md #3) happens inside `POST /jobs`, after the existing `s3_key`-exists check and before the `Job`/`Video` documents are created — it is not a separate endpoint.
- `result_url` on `GET /videos` entries is minted the same way `GET /jobs/{id}`'s `result_url` already is (presigned, time-limited), and both now set a `Content-Disposition` response-header override so the browser saves the download under `display_name` regardless of the object's own (opaque, permanent) storage key (FR-027, research.md #5, revised 2026-08-21).
- `POST /jobs/dismiss-all`'s `dismissed` count and `POST /videos/move`'s `moved` count are both provided so the dashboard/library UI can show "cleared 4" / "moved 3" feedback without a follow-up list re-fetch being required to know it worked (a re-fetch to refresh the view is still expected, just not to learn the outcome).
