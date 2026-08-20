# Research: Task Dashboard & Video Library

## 1. Where duplicate/library state lives — a new persistent store is genuinely required

**Decision**: Add MongoDB as a second, durable store alongside Redis. A new `videos` collection becomes the single source of truth for (a) the duplicate-submission fingerprint index and (b) the video library (folders, display names, storage locations) — completely decoupled from Redis's job hashes.

**Rationale**: `JobStore` (`backend/src/tonemill/jobs/store.py`) re-applies a TTL (`job_ttl_seconds`, default 86400s / 24h) on every write and is explicitly designed to expire — that's correct for live job/progress polling, but structurally incompatible with two things this feature requires to live forever: a video library that must still show a clip processed weeks ago, and a duplicate fingerprint that must still block a re-upload after the original job's Redis record has long since expired. Bolting indefinite retention onto `JobStore` (e.g. dropping its TTL) would break its existing, validated contract (spec 001 FR-019: "a request for a job outside its TTL window returns not-found/expired, not a stale record") for jobs that have nothing to do with this feature. A second store scoped to exactly the durable data this feature needs is simpler than overloading Redis's semantics.

**Alternatives considered**:
- *Drop the TTL on Redis job hashes*: rejected — breaks spec 001's validated TTL contract and turns Redis into unbounded long-term storage it wasn't designed to be queried as (no secondary indexes, e.g. "find by fingerprint" or "list by folder" would mean a full `SCAN`).
- *PostgreSQL*: rejected — no relational/multi-table needs here (folders/videos is a simple one-to-many, not joins-heavy); the user's own suggestion (MongoDB) and the document-shaped, mostly-independent records (one video doc, one folder doc) fit a document store with no schema-migration overhead, and the team has no existing relational database to extend.
- *Keep everything in Redis with no TTL for this feature's own keys only*: rejected — still leaves no real query capability for "list videos in folder X" or "does this fingerprint+profile already exist" beyond `SCAN`, which doesn't scale as the library grows; a document store with real indexes (including a unique index that closes the race condition in research item 3) is the right tool.

**Driver choice**: `pymongo` (>=4.9) using its native async API (`pymongo.AsyncMongoClient`), not Motor. MongoDB has deprecated Motor in favor of PyMongo's own async support (GA since 4.13, Motor's sunset already reached as of this feature's creation date). Using the deprecated driver in a brand-new integration would be adding technical debt on day one.

## 2. macOS Quick Look/Preview can't open downloaded results — root cause found

**Decision**: Every profile's `ffmpeg` output flags gain `-tag:v hvc1` and `-movflags +faststart`.

**Rationale**: Read `hlg_gpu.py` and `hlg_cpu.py` (both HEVC/`libx265`/`hevc_nvenc` outputs) — neither sets an explicit video tag. ffmpeg's own `mp4` muxer default-tags HEVC streams `hev1`, which QuickTime/AVFoundation-based viewers (Quick Look, Preview.app, the Finder thumbnailer) refuse to play; Apple's ecosystem requires the `hvc1` tag for HEVC-in-MP4 to be recognized as playable. This is confirmed by the reported symptom (files download fine, thumbnail/metadata read by Finder, but default double-click preview fails) and matches this well-documented ffmpeg/macOS interaction exactly. `+faststart` (moving the `moov` atom to the front) is added alongside it — same output flags block, negligible cost — since Quick Look's fast preview also depends on being able to read a file's index without a full download/seek-to-end, and there's no reason to leave it unset now that this code path is being touched anyway.

**Alternatives considered**: Re-muxing the output after the fact (`ffmpeg -c copy -tag:v hvc1 ...` as a second pass) — rejected, strictly worse than setting the tag once during the existing single encode pass (spec 001's whole design principle is one pass, no second re-encode/re-mux step).

## 3. Duplicate-submission fingerprint: computed server-side, from the already-uploaded object

**Decision**: At `POST /jobs` (after the existing `storage.object_exists(s3_key)` check, before creating any job), the API computes a lightweight content fingerprint — `sha256(size_bytes || first 1 MiB || last 1 MiB)` — via two small ranged `GET`s against the uploaded object in S3/MinIO, then checks it against the `videos` collection scoped to `(fingerprint, profile, max_quality)`.

**Rationale**: The alternative — hashing the whole file client-side before upload, to reject a duplicate before spending upload bandwidth — was considered and rejected: it means loading up to several GB into browser memory (risky, especially on Safari) or adding a streaming-hash dependency to the frontend, for a benefit (saving bandwidth on the rare accidental duplicate) that isn't what the spec actually asks for (spec 004 FR-021/FR-022 only requires the *job* never gets created, not that the upload itself is skipped). Computing a fast, size-plus-boundary-bytes fingerprint server-side, after the object already exists in storage, needs zero new frontend code, can't be bypassed by a different client, and reuses the exact point (`POST /jobs`) where the existing code already validates the upload and profile. It is not a cryptographic proof of exact-byte-identity (two different files could theoretically share size + first/last MiB), but this is a UX safeguard against accidental re-submission, not a security boundary — full-file hashing would be over-engineering for that goal (constitution Principle I, YAGNI).
A partial-unique index on `(fingerprint, profile, max_quality)` — filtered to `status: {$in: ["in_progress", "done"]}` — closes the race where two near-simultaneous submissions of the same file both pass the pre-check: the loser's insert simply fails the unique constraint and is converted to the same friendly 409.

**Alternatives considered**: filename+size only (rejected in spec.md's own Assumptions — this project's actual source files are camera-generated with reused, generic sequential names across unrelated shoots, e.g. `DJI_..._0001_D.MP4`, so filename-based matching would produce real false positives); full-file server-side hash (rejected — reading a multi-GB object end-to-end on every submission is needless I/O for a non-adversarial duplicate check).

## 4. Result naming & disambiguation

**Decision**: `display_name = "{recorded_created_at:%Y-%m-%d_%H-%M-%S}_{resolved_profile}.mp4"`. `recorded_created_at` is read from the source file's own container metadata (`ffprobe … format_tags.creation_time`) during the worker's existing probe step (it already calls `probe_duration_ms` on the same source file); if that tag is absent, it falls back to the job's `created_at`. A unique index on `display_name` in the `videos` collection means a second video that would generate an identical name gets a short numeric suffix appended (`..._hlg-gpu-2.mp4`) by retrying the insert with an incrementing suffix.

**Rationale**: Directly implements spec FR-016/FR-017/FR-018. Reusing the worker's existing `ffprobe` invocation point (rather than adding a second probe) keeps the pipeline at one source read, consistent with spec 001's single-pass design.

## 5. Storage layout mirrors the on-site folder browser

**Decision**: Every result object's S3 key is `results/{folder-slug|"unsorted"}/{display_name}`, where `folder-slug` is the folder's name, lowercased and with anything outside `[a-z0-9-]` collapsed to `-`. A freshly-graded job always lands under `results/unsorted/...` (the worker has no folder concept — folder assignment is a video-library action, not a grading-pipeline one). Moving a video into, out of, or between folders via the UI performs a storage-level `copy_object` to the new key followed by `delete_object` on the old one (S3/MinIO has no rename primitive), with the `videos` document's `result_key`/`folder_id` updated only after the copy succeeds.

**Rationale**: Directly implements FR-019. Keeping the worker unaware of folders preserves spec 001's pipeline boundary (`worker/pipeline.py` shouldn't need to know about a UI-only concept), and keeps this feature's storage-reorganization logic entirely in the API layer where the `videos` collection already lives.

**Alternatives considered**: Renaming folders in place (leaving already-stored objects at their old key) — rejected as inconsistent with FR-019's "kept in sync" requirement; not supporting folder rename at all in this iteration (see spec.md Assumptions) sidesteps needing bulk re-keying on rename, so this doesn't need to be solved now.

## 6. Dashboard dismiss stays entirely in Redis

**Decision**: `Job` (`jobs/store.py`) gains one new field, `dismissed: bool = False`. `GET /jobs` excludes `dismissed=true` records from its response. Two new endpoints flip the flag: `POST /jobs/{job_id}/dismiss` (one job) and `POST /jobs/dismiss-all` (every job whose `status` is `done` or `failed`).

**Rationale**: The dashboard's dismissed-ness is exactly as long-lived as the job list itself already is (spec 004 Assumptions: a dismissed failed job's record may be fully discarded — Redis's existing TTL already does that for free). Routing this through Mongo would add a second write path for data that Redis's existing lifecycle already models correctly, violating YAGNI. FR-005 ("dismissing must not delete the underlying video") is satisfied for free by construction — the `videos` collection in Mongo is never touched by a dismiss call; it's an entirely separate document from the Redis job hash.

## 7. Frontend: native drag-and-drop, no new dependency

**Decision**: Implement folder drag-and-drop with the browser's native HTML5 Drag and Drop API (`draggable`, `dragstart`/`dragover`/`drop` handlers) plus a plain array of selected-video IDs for multi-select — no new npm dependency.

**Rationale**: The existing frontend has zero drag-and-drop dependencies and the interaction needed (drag one or more video cards onto a folder card) doesn't need sorting, nested containers, or touch-emulation polish that would justify a library. Matches constitution Principle I (simplicity/YAGNI) and the existing frontend's pattern of minimal, purpose-built components (`JobCard.svelte`) over general-purpose UI kits beyond the already-adopted `bits-ui`/shadcn-svelte primitives.
