# Data Model: Tonemill

All state lives in Redis (job/upload records, TTL-bound) or is derived at runtime (the profile registry is code + config, not stored data). There is no relational database. Field names below are illustrative identifiers for `/speckit-tasks`, not a fixed serialization format.

## Job

One request to grade a single source video. Stored as a Redis hash at `tonemill:job:{job_id}`, `EXPIRE` refreshed on every write (default 24h, operator-configurable).

| Field | Type | Notes |
|---|---|---|
| `job_id` | string (UUID) | Primary identifier; also the Redis key suffix. |
| `source_key` | string | Object key of the uploaded source in storage. Must reference a **completed** Upload Session (see below) — enforced at submission time (FR-002, edge case: job referencing an incomplete/never-uploaded key). |
| `requested_profile` | string | One of the registered profile names, or `auto`. |
| `resolved_profile` | string \| null | Set once resolved (immediately for explicit names; at pickup time for `auto`, per FR-012). Null while still `queued` for an `auto` job. |
| `max_quality` | boolean | Per-job "maximum quality" flag (FR-027). Defaults `false`. |
| `status` | enum: `queued`, `running`, `done`, `failed` | FR-004. |
| `stage` | enum: `downloading`, `processing`, `uploading_result` \| null | Only meaningful while `status = running` (FR-033). Null otherwise. |
| `progress_pct` | number (0–100) | Meaningful only during the `processing` stage (FR-005); derived from `out_time_ms / probed_duration_ms`. |
| `result_key` | string \| null | Object key of the graded output. Set only once `status = done`. |
| `error` | string \| null | Human-readable failure reason. Set only once `status = failed` (FR-007). |
| `created_at` | timestamp | Job creation time. |
| `expires_at` | timestamp (derived) | Informational — actual expiry enforced by Redis `TTL` on the hash key, not a field consumers should trust as authoritative once close to expiry. |

**State transitions**: `queued → running → (done | failed)`. No transition leaves `done`/`failed` (terminal). `resolved_profile` is write-once. A request for a job outside its TTL window returns "not found / expired," not a stale record (FR-019).

**Validation rules** (from spec Functional Requirements):
- `requested_profile` MUST be a name known to the profile registry (including registered-but-stubbed names like `d-log-m`) or `auto`; unknown names are rejected at submission, before a Job record is created (FR-016).
- A job requesting `d-log-m` is rejected at submission with a "not implemented" response — no Job record is created for it (FR-015).
- `max_quality = true` combined with a `resolved_profile` that is not GPU-accelerated MUST transition the job to `failed` with a clear reason, never silently drop the flag (FR-029).
- An explicit (non-`auto`) GPU-profile request on a host without a working GPU path MUST fail, never silently substitute the CPU profile (FR-013).

## Upload Session

One client's in-progress or completed multipart upload of a single source file. Stored as a Redis hash at `tonemill:upload:{upload_id}` (or equivalent), independent of any Job.

| Field | Type | Notes |
|---|---|---|
| `upload_id` | string | Storage-assigned multipart upload identifier. |
| `target_key` | string | Object key the parts will assemble into. |
| `parts_received` | list of `{part_number, etag, size}` | Grows as parts complete; used to answer "what's left to resume" (FR-030), and is directly queryable by the client via `GET /uploads/{upload_id}/parts` rather than relying only on the client's own local record (FR-034). |
| `state` | enum: `in_progress`, `completed`, `aborted` | |
| `created_at` | timestamp | |

**Relationship**: A Job's `source_key` is only accepted at submission time if a matching Upload Session exists with `state = completed` (or, more simply, if the object exists in storage — completion is what makes the object exist at all, per S3 multipart semantics). Upload Sessions are not TTL-bound the same way Jobs are; an abandoned one is cleaned up via an explicit abort (client- or operator-triggered), not automatic background lifecycle management (which is out of scope for v1).

## Grading Profile (registry entry — configuration, not per-request data)

A named, pluggable color-grading pipeline definition. Not stored in Redis; defined in code (one module per profile behind the shared `GradingProfile` interface) plus its tunable parameters exposed as configuration (FR-024).

| Field | Type | Notes |
|---|---|---|
| `name` | string | Unique registry key (`hlg-gpu`, `hlg-cpu`, `d-log-m`, ...). |
| `source_format` | string | Color format this profile targets (e.g., `HLG/BT.2020`). |
| `execution_path` | enum: `gpu`, `cpu` | Determines `auto` resolution (FR-012) and the `max_quality` gate (FR-029). |
| `implemented` | boolean | `false` for stubs like `d-log-m` (FR-015). |
| `params` | structured config | Tone-mapping operator, contrast, saturation/vibrance, quality target (CQ/CRF), etc. — adjustable without touching the profile's pipeline code (FR-024); for `hlg-gpu`/`hlg-cpu` these are the exact validated values from FR-009–FR-011 and MUST NOT be re-derived. |
| `performance_reference` | structured note | Validated fps/realtime-factor on reference footage — informational, not a runtime guarantee. |

**Consistency rule**: every implemented profile, regardless of `execution_path`, MUST tag its output `bt709/bt709/bt709/tv` (FR-014) and MUST be reachable through the same registration/status-reporting behavior (FR-025) — this is enforced by the shared `GradingProfile` interface, not re-implemented per profile.
