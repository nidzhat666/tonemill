# Data Model: Task Dashboard & Video Library

Extends spec 001's data model (`specs/001-color-grading-pipeline/data-model.md`). Two stores now exist side by side:

- **Redis** — unchanged in shape except one new field on `Job`; still TTL-bound, still the live job/progress store.
- **MongoDB** (new) — durable, not TTL-bound; the `videos` and `folders` collections. Source of truth for the library, folder assignment, and duplicate detection. Field names below are illustrative identifiers for `/speckit-tasks`, not a fixed serialization format.

## Job (Redis — extends spec 001's Job)

One field added to the existing Redis-hash `Job` (`tonemill:job:{job_id}`, unchanged TTL behavior):

| Field | Type | Notes |
|---|---|---|
| `dismissed` | boolean | Default `false` (FR-002–FR-005). Dashboard-visibility only — flipping it never touches the `videos` collection. `GET /jobs` excludes `dismissed = true` records. |

**State transitions**: unchanged from spec 001 (`queued → running → (done \| failed)`), plus `dismissed: false → true` (one-way; nothing un-dismisses a job — it either stays hidden until Redis's TTL discards the whole record, or is superseded by a fresh submission).

**Validation rules**:
- `dismissed` MUST only be settable via `POST /jobs/{id}/dismiss` or `POST /jobs/dismiss-all` (FR-002, FR-003), and MUST NOT be settable on a job whose `status` is `queued` or `running` — both endpoints filter these out server-side (FR-004's "in progress" jobs are never eligible), not just hide the button client-side.

## Video (MongoDB — new)

One document per **submitted** job (not just completed ones) — created at the same moment the Redis `Job` is created (`POST /jobs`), so it can serve as both the duplicate-fingerprint record for in-progress jobs and, once `status` reaches `done`, the permanent video-library entry. Collection: `videos`.

| Field | Type | Notes |
|---|---|---|
| `_id` | string | Same value as the Redis `job_id` — one-to-one with the Job that created it, no separate ID scheme needed. |
| `fingerprint` | string | `sha256(size_bytes \|\| first_1mib \|\| last_1mib)` of the uploaded source object (research.md #3). Used only for duplicate detection — never shown to the user. |
| `source_key` | string | The uploaded source's object key (copied from the Job at creation). |
| `original_filename` | string | Recovered from `source_key`'s trailing path segment — kept for reference/debugging, not used in `display_name`. |
| `profile` | string | The *resolved* profile name (mirrors `Job.resolved_profile` once known; `Job.requested_profile` until then). |
| `max_quality` | boolean | Mirrors `Job.max_quality`. Part of the duplicate-detection key (FR-025). |
| `status` | enum: `in_progress`, `done`, `failed` | Mirrors the owning Job's lifecycle; updated by the same worker code path that updates the Redis `Job` (FR-021, FR-024 — a `failed` record never counts as a duplicate match). |
| `recorded_created_at` | timestamp | The source video's own recording date, from `ffprobe`'s `format_tags.creation_time`, falling back to the Job's `created_at` if absent (FR-017, research.md #4). Set once, at grading time. |
| `display_name` | string \| null | `"{recorded_created_at}_{profile}.mp4"`, disambiguated on collision (FR-016, FR-018, research.md #4). Null until `status = done` (nothing to name yet). |
| `result_key` | string \| null | The graded result's object key, `results/{job_id}/{uuid}.mp4` — opaque, and permanent once set (FR-019, research.md #5): never rewritten by a folder move or folder deletion. Null until `status = done`. |
| `folder_id` | string \| null | References `Folder._id`. Null means "unsorted" (FR-013). |
| `created_at` | timestamp | Document creation time (= job submission time). |
| `updated_at` | timestamp | Bumped on every status/folder/name change. |

**Indexes**:
- Unique, partial: `(fingerprint, profile, max_quality)` where `status` is `in_progress` or `done` — the authoritative duplicate check (FR-021–FR-025); a conflicting insert is what actually closes the race described in the Edge Cases (two near-simultaneous submissions of the same file).
- Unique, partial: `display_name` where not null — enforces FR-018's disambiguation at the storage layer, not just as an application-level convention.
- Non-unique: `folder_id` — backs "list videos in folder X" for the library view.

**State transitions**: `in_progress → (done | failed)`, matching the owning Job. `folder_id` changes freely and independently of `status` once `status = done` (FR-010–FR-014); it is meaningless (and left `null`) before then, since there's no result to organize yet.

**Validation rules** (from spec Functional Requirements):
- A document is only ever inserted once its Job passes the existing `s3_key`/profile checks in `POST /jobs` (spec 001 FR-002, FR-016) — never for a submission that was itself rejected.
- `display_name` and `result_key` are both set exactly once, when the worker's grading pass finishes successfully, and never recomputed afterward for any reason — including a `folder_id` change (research.md #5). Only `display_name` needs a collision-retry at that point; `result_key` (opaque) never collides.
- A `failed` video's document is retained (needed so a later duplicate check against a differently-fingerprinted resubmission still has history), but is excluded from every library-facing query — the library (FR-007) only ever lists `status = done` documents.

## Folder (MongoDB — new)

A user-created, flat container. Collection: `folders`.

| Field | Type | Notes |
|---|---|---|
| `_id` | string (generated) | Primary identifier. |
| `name` | string | User-supplied, unique (case-insensitive) — reusing a name is rejected rather than creating a second folder with the same label. |
| `created_at` | timestamp | |

**Relationship**: `Video.folder_id` references `Folder._id`; there is no reverse containment field on `Folder` (membership is queried via `Video.folder_id`, not stored redundantly on both sides — DRY). Folders never nest (FR-009 — enforced simply by the schema having no parent-folder field at all).

**State transitions**: none beyond create/delete. Deleting a folder (FR-015) is a two-step operation: every `Video` document with that `folder_id` is updated to `folder_id = null` (a Mongo-only write — `result_key` is untouched, research.md #5), then the `Folder` document itself is removed.
