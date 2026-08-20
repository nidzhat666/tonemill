# Data Model: Homeserver CI/CD & GPU Deployment

No new entities, database schema, or state are introduced — this feature is deployment
infrastructure plus one shared-login gate. Redis job state (`Job`/`JobStatus`/`JobStage`) and
the S3 object model are unchanged from specs/001; this feature only changes *where* the existing
application runs and *how* its images get there.

## New configuration values

The closest thing to a "model" here is the new environment configuration the production
deployment introduces, all consumed as plain env vars (no new config file format):

| Variable | Consumed by | Purpose |
|---|---|---|
| `TONEMILL_AUTH_USERNAME` | frontend (`hooks.server.ts`) | Shared-login username (FR-011–FR-013) |
| `TONEMILL_AUTH_PASSWORD` | frontend (`hooks.server.ts`) | Shared-login password |
| `TONEMILL_S3_ENDPOINT_URL` | api, worker | `http://minio-server:9000` — internal MinIO endpoint (research.md #4) |
| `TONEMILL_S3_PUBLIC_ENDPOINT_URL` | api | `https://s3.nidzh.com` — browser-facing endpoint for presigned URLs |
| `TONEMILL_S3_ACCESS_KEY_ID` / `TONEMILL_S3_SECRET_ACCESS_KEY` | api, worker | Dedicated credentials for the new `tonemill` bucket within the existing MinIO |
| `TONEMILL_API_BASE_URL` | frontend | `http://tonemill-api:8000` — internal-only; the service is named `tonemill-api`, not `api` (research.md #10 — a bare `api` collides with another stack's own `api` service on the shared network); its port is never published to the host (research.md #5) |

All of the above are supplied via a plain `.env` file placed directly in
`homeserver-stacks/tonemill/` on the server (research.md #8) — not Infisical-managed, unlike
most other secret-bearing stacks in that repository, but still covered by that repository's
`.gitignore` — none are committed to either repository in plaintext.
