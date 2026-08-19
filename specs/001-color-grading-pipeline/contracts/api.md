# API Contract: Tonemill

JSON over HTTP, served by the FastAPI backend. No authentication in v1 (spec Assumptions). All endpoints are relative to the API's base URL. This is the contract the SvelteKit frontend's BFF layer (and any script) integrates against — bytes for uploads/downloads always go client↔storage directly via presigned URLs, never through these endpoints' bodies.

## Uploads (FR-001, FR-030–FR-032, FR-034)

### `POST /uploads`
Initiate a resumable multipart upload for one source file.

Request:
```json
{ "filename": "clip.mp4", "content_type": "video/mp4", "size_bytes": 5321432100 }
```

Response `201`:
```json
{
  "upload_id": "string",
  "s3_key": "string",
  "part_size_bytes": 16777216,
  "part_count": 318
}
```

### `POST /uploads/{upload_id}/parts/{part_number}`
Mint a presigned URL for one part. Called on demand (including for parts being retried after an interruption — FR-030).

Response `200`:
```json
{ "part_number": 7, "upload_url": "https://storage/...", "expires_at": "2026-08-19T12:34:56Z" }
```
Client `PUT`s the part bytes directly to `upload_url` and keeps the returned `ETag` response header.

### `GET /uploads/{upload_id}/parts`
List parts already received for this upload, so a client with no (or lost) local record — a new browser session, a different device — can discover what's left to resume (FR-034), instead of resume depending solely on client-side memory.

Response `200`:
```json
{ "parts": [{ "part_number": 1, "etag": "\"abc\"", "size_bytes": 16777216 }, { "part_number": 2, "etag": "\"def\"", "size_bytes": 16777216 }] }
```
Client diffs this against `part_count` (from `POST /uploads`) to compute which part numbers still need `PUT`ting.

Errors: `404` if `upload_id` is unknown or already completed/aborted.

### `POST /uploads/{upload_id}/complete`
Finalize the upload once all parts are received (FR-032).

Request:
```json
{ "parts": [{ "part_number": 1, "etag": "\"abc\"" }, { "part_number": 2, "etag": "\"def\"" }] }
```

Response `200`: `{ "s3_key": "string", "status": "completed" }`

Errors: `409` if a listed part is missing/unrecognized; `404` if `upload_id` is unknown or already completed/aborted.

### `POST /uploads/{upload_id}/abort`
Abandon an in-progress upload (FR-032, edge case: abandoned multipart upload cleanup).

Response `204`.

## Profiles (supports FR-002's profile selection; read-only registry listing)

### `GET /profiles`
List registered grading profiles for UI display (submit-form options) and client-side validation before submission.

Response `200`:
```json
[
  { "name": "hlg-gpu", "source_format": "HLG/BT.2020", "execution_path": "gpu", "implemented": true },
  { "name": "hlg-cpu", "source_format": "HLG/BT.2020", "execution_path": "cpu", "implemented": true },
  { "name": "d-log-m", "source_format": "D-Log M", "execution_path": null, "implemented": false }
]
```

## Jobs (FR-002–FR-007, FR-012–FR-013, FR-019, FR-027–FR-029, FR-033)

### `POST /jobs`
Submit a grading job for an already-uploaded source.

Request:
```json
{ "s3_key": "string", "profile": "auto", "max_quality": false }
```

Response `201`:
```json
{ "job_id": "string", "status": "queued" }
```

Errors:
- `400` — `s3_key` does not reference a completed upload (edge case: never-uploaded/partial source).
- `400` — `profile` is not a recognized registry name (FR-016).
- `400` — `max_quality: true` combined with an explicitly-named CPU-only profile (FR-029). This is a synchronous rejection because it's structurally knowable from the profile's registry metadata (`execution_path`) alone — no runtime GPU/ffmpeg check is needed to know a CPU-only profile can never honor it.
- `409` — `profile = "d-log-m"` (or any registered-but-not-implemented profile) is rejected at submission (FR-015), returning a clear "not implemented" error body.

**FR-013's explicit-GPU-profile-unavailable failure is always an async `failed` job outcome, never a synchronous rejection.** The API process has no `ffmpeg` binary and cannot itself determine whether a GPU encoder is actually available on any worker — only the worker knows this when it picks up the job. `profile: "hlg-gpu"` (or any GPU profile) is always accepted at submission time; if no worker can actually run it, the job transitions to `failed` with a clear reason instead.

### `GET /jobs/{job_id}`
Poll current job state.

Response `200` (running example):
```json
{
  "job_id": "string",
  "status": "running",
  "stage": "processing",
  "progress_pct": 42.5,
  "requested_profile": "auto",
  "resolved_profile": "hlg-gpu",
  "max_quality": false,
  "result_url": null,
  "error": null
}
```

Response `200` (done example):
```json
{
  "job_id": "string",
  "status": "done",
  "stage": null,
  "progress_pct": 100,
  "requested_profile": "hlg-gpu",
  "resolved_profile": "hlg-gpu",
  "max_quality": true,
  "result_url": "https://storage/...(presigned, time-limited)",
  "error": null
}
```

Response `404`: job unknown or its TTL has expired (FR-019) — client must treat this as "unknown/expired," not silently retry forever.

## Notes for `/speckit-tasks`

- All presigned URLs (part upload, result download) are time-limited; exact expiry duration is an implementation default, not a contract requirement.
- The `stage` field is only populated while `status = "running"`; it is `null` at all other times (FR-033, data-model.md).
- `result_url` is only populated once `status = "done"`; requesting it earlier (e.g., via a would-be `GET /jobs/{id}/download` before completion) is invalid per the spec's edge cases and should not be exposed as a separate premature-download endpoint.
