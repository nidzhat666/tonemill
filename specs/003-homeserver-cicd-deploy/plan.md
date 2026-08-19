# Implementation Plan: Homeserver CI/CD & GPU Deployment

**Branch**: `003-homeserver-cicd-deploy` | **Date**: 2026-08-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-homeserver-cicd-deploy/spec.md`

## Summary

Publish Tonemill's three components (API, worker, frontend) as versioned container images from
GitHub Actions to GHCR on every push to `main`, add a new `tonemill/` stack to the account's
`homeserver-stacks` GitOps repository that runs those images on `homeserver` (a real x86_64 host
confirmed to have an RTX 3080 Ti with the NVIDIA container runtime already installed), gate the
whole application behind a single shared username/password checked in SvelteKit's
`hooks.server.ts`, and expose it publicly at `tonemill.nidzh.com`. Applying a newly published
image to production stays a manual `docker compose pull && up -d` step, matching every other
service in that repository — no new cross-repo automation is introduced.

## Technical Context

**Language/Version**: YAML (GitHub Actions workflow, Docker Compose) plus one small TypeScript
addition to the existing SvelteKit `hooks.server.ts` — no backend (Python) code changes.

**Primary Dependencies**: GitHub Actions (`docker/setup-buildx-action@v3`,
`docker/login-action@v3`, `docker/metadata-action@v5`, `docker/build-push-action@v5` — the exact
actions and versions already proven working in this account's `nidzhat666/reelsaz` repo, fetched
live from its real workflow file rather than assumed); GHCR (`ghcr.io`) as the registry; the
account's existing self-hosted MinIO and nginx-proxy-manager stacks (already running on
`homeserver`). Secrets are a plain `.env` on the server for now, not Infisical (research.md #8).

**Storage**: No new storage service. Reuses the homeserver's existing self-hosted MinIO —
internal endpoint `http://minio-server:9000` (container DNS name, confirmed from
`homeserver-stacks/minio/docker-compose.yml`) for API/worker traffic, public endpoint
`https://s3.nidzh.com` (confirmed from that same file's `MINIO_SERVER_URL`) for browser-facing
presigned URLs — this is exactly the internal/public split `TONEMILL_S3_ENDPOINT_URL` /
`TONEMILL_S3_PUBLIC_ENDPOINT_URL` already built for in `config.py`. A new bucket and access key
are created within that existing MinIO instance; no new object storage is provisioned.

**Testing**: No new automated test suite — this is a deployment/infra feature. Verification is
real and end-to-end: a real push triggers a real GHCR publish (observable in the registry), and
`quickstart.md` walks through actually running a real HDR file through the deployed production
app on real GPU hardware (spec's own emphasis — this closes the project's long-standing
"GPU path never verified on real hardware" gap). If the `hooks.server.ts` auth check grows
non-trivial branching, it gets a small Vitest unit test following this repo's existing
Given/When/Then convention.

**Target Platform**: linux/amd64 on both ends — confirmed live via SSH
(`ssh homeserver 'uname -m'` → `x86_64`, Ubuntu 24.04.3 LTS, Docker 29.0.0,
`nvidia-smi` → RTX 3080 Ti / driver 580.173.02, `docker info` lists the `nvidia` container
runtime as already installed and available). GitHub Actions' `ubuntu-latest` runners are also
amd64, matching `worker.Dockerfile`'s existing `--platform=linux/amd64` pin exactly — no
cross-architecture build or emulation is needed anywhere in this pipeline.

**Project Type**: Deployment/infrastructure feature spanning two repositories: `tonemill` itself
(gains `.github/workflows/`, and the small `hooks.server.ts` auth addition) and
`/Users/nidzhat/Documents/homeserver-stacks` (gains a new `tonemill/` stack directory). No new
application functionality beyond the shared-login gate (spec's own Assumptions).

**Performance Goals**: Image builds complete well within SC-001's 10-minute budget — this
account's existing single-image repos (`eatmeter_garmin`, `kinozal-bot`, `wordpocket`, `reelsaz`)
observably build in 1–3 minutes each per `homeserver-stacks/docs/stacks.md`; three components
built in parallel (matrix job) comfortably clears the budget even accounting for Tonemill's
larger `worker` image (pinned ffmpeg binary download + extraction).

**Constraints**: `worker.Dockerfile` stays pinned to `linux/amd64` (unchanged, already required
for its ffmpeg binary). GHCR images are public (Tonemill is MIT-licensed/open-source per its own
original spec — matches this account's default for such images). Deploying a newly published
image to `homeserver` remains an explicit manual step (FR-004) — no GHCR-push webhook or
cross-repo auto-commit is introduced. The `api` service's port MUST NOT be published to the
host in the `homeserver-stacks` deployment (research.md #5) — otherwise the shared-login gate in
`hooks.server.ts` could be bypassed entirely by hitting the API directly on its host port.

**Scale/Scope**: 3 published images (api, worker, frontend), 1 new GitHub Actions workflow file,
1 new stack directory in `homeserver-stacks` (compose file + a plain, server-only `.env`), 1
small addition to `hooks.server.ts` — no database/schema changes, no new backend routes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Simplicity, DRY & YAGNI | PASS. The CI workflow reuses this account's own proven template (`reelsaz`'s `ghcr-build.yml`) rather than inventing a new pattern; the auth gate lives in exactly one place (`hooks.server.ts`), not duplicated into the FastAPI backend, because removing the API's public port mapping closes the only bypass path (research.md #5) — the simplest sufficient fix, not defense-in-depth for its own sake. Auto-deploy-on-publish was explicitly rejected (FR-004) as unrequested new cross-repo automation. |
| II. Explicit Imports | PASS. The only new application code (`hooks.server.ts`) follows this file's and the codebase's existing top-of-file import convention. |
| III. Docstrings Over Comments | PASS. The auth-check logic gets a short doc comment on an extracted, named function if it's non-trivial enough to need one — not an inline comment block. |
| IV. Test Clarity (Given/When/Then) | PASS (N/A for most of this feature). No new test suite is required for infra/CI configuration; if a unit test is added for the auth-check function, it follows Given/When/Then. |
| V. Readability & Maintainability | PASS. Small, flat addition to an already-designed extension point (`hooks.server.ts`'s existing "lands here as it's needed" comment). |

No violations — Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-homeserver-cicd-deploy/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command) — no new entities
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── deployment.md    # The stack's env-var/network/port contract with homeserver-stacks
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This feature spans two repositories.

```text
# tonemill (this repo)
.github/
└── workflows/
    └── ghcr-build.yml          # NEW: matrix build (api/worker/frontend) → GHCR, on push to main

frontend/
└── src/
    └── hooks.server.ts         # MODIFIED: shared-login check (TONEMILL_AUTH_USERNAME/PASSWORD),
                                #   gates every request before SvelteKit resolves it

docker-compose.yml               # UNCHANGED locally (still build:-based, for the existing
                                  #   documented "existing external MinIO/S3" production path);
                                  #   the homeserver deployment gets its own compose file below

# /Users/nidzhat/Documents/homeserver-stacks (separate repo)
tonemill/
├── docker-compose.yml           # NEW: references ghcr.io/nidzhat666/tonemill-{api,worker,frontend}
│                                 #   images (pull_policy: always), worker gets the same GPU
│                                 #   reservation as cinema-agent's jellyfin/plex, frontend joins
│                                 #   nginx-network for tonemill.nidzh.com, api's port is NOT
│                                 #   published to the host (research.md #5)
└── .env                         # NOT committed (repo .gitignore covers it): plain env file
                                  #   created directly on the server, not Infisical-managed
                                  #   (research.md #8) -- no .infisical marker for this stack
```

**Structure Decision**: No structural changes inside `tonemill/`'s existing `backend`/`frontend`
split — this feature only adds a CI workflow and one small frontend file. The
production-with-registry-images compose definition lives in `homeserver-stacks/tonemill/`, not
as a second file inside this repo, matching how every other custom-built service in this
account's fleet is deployed (the app repo builds and publishes; the deploy repo runs).
`homeserver-stacks/docs/stacks.md` and its summary table gain a `tonemill` row, following the
same documentation convention already used for every other stack.

## Complexity Tracking

> Constitution Check above reported no violations — nothing to justify here.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
