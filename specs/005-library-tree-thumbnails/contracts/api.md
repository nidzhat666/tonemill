# API Contract: Library Tree View & Video Thumbnails

Extends `specs/004-task-dashboard-video-library/contracts/api.md`. Only new and changed endpoints are documented here; `POST /videos/move`, `GET /folders`, `POST /folders`, `DELETE /folders/{id}` are unchanged.

## Videos (changed)

### `GET /videos` (changed — thumbnail and preview-clip URLs added)

Response `200` (new fields in **bold**):
```json
[
  {
    "video_id": "string",
    "display_name": "2026-07-22_16-35-09_hlg-gpu.mp4",
    "profile": "hlg-gpu",
    "recorded_created_at": "2026-07-22T16:35:09Z",
    "folder_id": "string|null",
    "result_url": "https://storage/...(presigned, time-limited)",
    "thumbnail_url": "https://storage/...(presigned)|null",
    "preview_clip_urls": ["https://storage/...(presigned)", "..."]
  }
]
```
`thumbnail_url` is `null` and `preview_clip_urls` is `[]` for a video graded before this feature shipped (research.md #1) — the client renders the "not ready yet" placeholder (FR-004) in that case. `preview_clip_urls` has between 1 and 10 entries, in playback order (research.md #3); returning the URLs here does not itself cause any video bytes to be fetched (research.md #4) — that only happens once the frontend sets a `<video>` element's `src` on hover.

### `POST /videos/delete` (new)

Permanently delete one or more videos — their library entries and their underlying stored files (result, thumbnail, preview clips). Irreversible (FR-018–FR-024; contracts note: the confirmation step itself is a client-side concern, not part of this request).

Request:
```json
{ "video_ids": ["string", "..."] }
```

Response `200`:
```json
{ "deleted": 3 }
```
An unknown `video_id` in the list is silently skipped rather than failing the whole batch (same pattern as `POST /videos/move`).

## Folders (unchanged)

`GET /folders`, `POST /folders`, `DELETE /folders/{id}` are unaffected by this feature — folder collapse/expand display state (FR-012–FR-017) is entirely client-side (research.md #6) and never reaches the API.

## Notes for `/speckit-tasks`

- `thumbnail_url`/`preview_clip_urls` are minted the same way `result_url` already is (`S3StorageClient.presign_get_object`) — no new presigning mechanism, just new keys being presigned.
- `POST /videos/delete` deleting `thumbnail_key`/each of `preview_clip_keys` alongside `result_key` should tolerate a key that's already missing (e.g. a partial prior failure) the same way the rest of this codebase treats storage operations as best-effort on cleanup paths — a missing object is not an error worth failing the whole delete over.
- No endpoint changes are needed for the folder-tree collapse/expand story (FR-012–FR-017) or the hover-preview playback mechanics (FR-007, FR-008) themselves — both are entirely frontend behavior over data `GET /videos` already returns.
