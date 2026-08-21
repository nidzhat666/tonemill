# Data Model: Library Tree View & Video Thumbnails

Extends spec 004's data model (`specs/004-task-dashboard-video-library/data-model.md`). Two fields added to the existing `Video` document; no new collections, no changes to `Folder`. Field names below are illustrative identifiers for `/speckit-tasks`, not a fixed serialization format.

## Video (MongoDB `videos` collection — extends spec 004)

Two fields added to the existing document:

| Field | Type | Notes |
|---|---|---|
| `thumbnail_key` | string \| null | Object key of the static 5-second-mark JPEG frame (FR-001, FR-002; research.md #1). Set once, alongside `display_name`/`result_key`, when grading finishes successfully. `null` for any video graded before this feature shipped — the library renders the "not ready yet" placeholder (FR-004) for those. |
| `preview_clip_keys` | list of string | Ordered object keys of the video's short H.264 preview clips (research.md #2, #3) — length `N` per the FR-006 formula (1 to 10 entries), empty for a pre-existing video with no clips generated. Set once, at the same point as `thumbnail_key`. |

**Validation rules** (extends spec 004's):
- `thumbnail_key` and `preview_clip_keys` are only ever written once, in the same `status=done` update that sets `display_name`/`result_key` (research.md #1) — never recomputed or touched again afterward, including by a folder move (unaffected — orthogonal to spec 004's storage-permanence decision) or by anything in this feature.
- `preview_clip_keys` is only ever non-empty when `thumbnail_key` is also set — the two are always produced together, from the same successful grading pass, never independently.

**Deletion** (FR-018–FR-024, research.md #5): a `Video` document is now genuinely removable. Deleting one is: (1) delete the S3 objects at `result_key`, `thumbnail_key` (if set), and every entry in `preview_clip_keys`, then (2) `delete_one` the document itself. Because the fingerprint-uniqueness index (spec 004 data-model.md) is scoped to `in_progress`/`done` documents, a deleted document can never re-match it — FR-024 ("resubmitting the same file afterward is treated as new") falls out of the existing index design with no additional query changes needed anywhere.

## Folder (client-side display state only — no schema change)

Spec 004's `Folder` document (Mongo) is completely unchanged by this feature. What's new is purely client-local, held in the frontend's library store, never sent to or read from the backend:

| Field | Type | Notes |
|---|---|---|
| `expandedFolderIds` | set of folder id | Which folders are currently showing their videos (FR-011, FR-012). A folder not in this set is collapsed — the default (FR-013). Reset every time the library is (re)loaded (research.md #6). |
| `unsortedExpanded` | boolean | Same idea, for the Unsorted area specifically; defaults `true` (spec.md Assumptions), independent of `expandedFolderIds`. |

No relationship to persist: this state never needs to survive a reload, sync across sessions, or appear in any API response.
