# Data Model: Tailwind CSS Visual Design

No new entities, fields, or state transitions are introduced by this feature — it is a
presentational pass over the existing frontend, and `backend/` is untouched.

## Existing view model this design renders

The visual design must correctly represent every value already produced by the existing
`FileJob` type (`frontend/src/lib/stores/jobs.svelte.ts`), which combines local upload state
with the backend's `JobStatusResponse` (`frontend/src/lib/api-client.ts`):

| Field | Values | Visual requirement this drives |
|---|---|---|
| `phase` | `uploading` \| `submitted` \| `failed` | Distinguishes "still uploading to storage" from "submitted, tracking backend status" from "failed before a job even existed" (FR-003, FR-006) |
| `status` (once submitted) | `queued` \| `running` \| `done` \| `failed` | Primary status-to-color/iconography mapping (FR-003) |
| `stage` (while `running`) | `downloading` \| `processing` \| `uploading_result` \| `null` | Current-stage indicator alongside progress (FR-005) |
| `uploadPercent` / `progressPct` | `0`–`100` | Visual progress indicator (FR-004) |
| `error` | `string \| null \| undefined` | Rendered readably without breaking layout when present (FR-006, FR-010) |
| `filename` | arbitrary string | Truncated/wrapped gracefully when long (FR-010) |
| `resultUrl` | `string \| null` | Presence drives the prominent download action (FR-007) |

No changes to this type or to any backend response shape are required; the design consumes it
as-is.
