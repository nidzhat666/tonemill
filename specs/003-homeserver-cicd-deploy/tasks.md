---
description: "Task list for Homeserver CI/CD & GPU Deployment"
---

# Tasks: Homeserver CI/CD & GPU Deployment

**Input**: Design documents from `/specs/003-homeserver-cicd-deploy/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/deployment.md, quickstart.md

**Tests**: Not requested for the deployment/CI parts of this feature (infra configuration, not
application logic). One exception: the new shared-login check is real application logic with
real branching, so it gets a Given/When/Then unit test per plan.md's Testing section and the
project constitution's Test Clarity principle.

**Organization**: Tasks are grouped by user story (spec.md's US1–US4). This feature spans two
repositories — task descriptions state the repo explicitly whenever it's not `tonemill` (this
repo).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Every task includes its exact file path (or the concrete action, for repo-level/infra steps
  that have no source file)

---

## Phase 1: Setup

**Purpose**: The `tonemill` GitHub repository doesn't exist yet (confirmed via `git remote -v`
during planning) — nothing in this feature can run without it.

- [X] T001 Create a public GitHub repository `nidzhat666/tonemill`, add it as the `origin` remote of this local repo, and push `master`/`main` to it (research.md #7 — public, matching the project's own MIT/open-source goal)

**Checkpoint**: `gh repo view nidzhat666/tonemill` succeeds; the current code is visible on GitHub

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure every later story depends on, that isn't itself one of
spec.md's independently-testable user stories

**⚠️ CRITICAL**: US2 (deployment) and US4 (real grading) cannot be verified without this

- [X] T002 Create a dedicated `tonemill` bucket and a dedicated access key/secret pair in the existing homeserver MinIO instance (via `https://minio.nidzh.com` console or `mc` CLI against `minio-server`) — per research.md #4, no new MinIO instance

**Checkpoint**: The new bucket exists and the access key/secret can list/put/get objects in it

---

## Phase 3: User Story 1 - Publish a deployable image on every change (Priority: P1) 🎯 MVP

**Goal**: A push to `main` automatically builds and publishes all three component images to
GHCR, with no manual build/push and no partial publishing on failure.

**Independent Test**: Push a trivial commit to `main`; confirm all three images appear in GHCR
with `:latest` and `:sha-<short>` tags, with zero manual Docker commands.

### Implementation for User Story 1

- [X] T003 [US1] Create `.github/workflows/ghcr-build.yml`: a matrix job (api/worker/frontend) building `docker/api.Dockerfile`, `docker/worker.Dockerfile`, `docker/frontend.Dockerfile` (context `.`) and pushing to `ghcr.io/nidzhat666/tonemill-{api,worker,frontend}`, adapted from the real, proven template in `nidzhat666/reelsaz`'s `.github/workflows/ghcr-build.yml` (research.md #1) — `permissions: contents: read, packages: write`; `docker/login-action@v3` with `secrets.GITHUB_TOKEN` (research.md #3); `docker/metadata-action@v5` tagging `type=sha,prefix=sha-,format=short` + `type=raw,value=latest,enable={{is_default_branch}}`; `docker/build-push-action@v5` with `platforms: linux/amd64`; trigger `on: push: branches: [main, master]`
- [X] T004 [US1] Push a trivial test commit to `main`; confirm in the GitHub Actions tab and the repo's Packages page that all three images publish within 10 minutes with both tags (validates FR-001, FR-002, SC-001 — quickstart.md scenario 1)
- [X] T005 [US1] On a branch, temporarily break one Dockerfile (e.g. an invalid instruction), push, and confirm the workflow run fails and no new image/tag appears for any of the three components; then revert the breakage (validates FR-003 — quickstart.md scenario 2)

**Checkpoint**: User Story 1 is fully functional and independently testable — a push to `main`
reliably produces three published, correctly tagged images

---

## Phase 4: User Story 2 - Run the published images on the real GPU host (Priority: P2)

**Goal**: The published images run on `homeserver`, with the worker having real GPU access and
storage pointed at the existing MinIO, deployed through the same GitOps pattern as every other
stack in `homeserver-stacks`.

**Independent Test**: With published images available, add the deployment definition and confirm
all three components start and the worker can see the GPU.

### Implementation for User Story 2

- [X] T006 [US2] Create `/Users/nidzhat/Documents/homeserver-stacks/tonemill/docker-compose.yml` per contracts/deployment.md: `redis` service (no host port); `api` referencing `ghcr.io/nidzhat666/tonemill-api:latest` with `pull_policy: always`, **no** `ports:` entry (research.md #5 — hard constraint, not optional); `worker` referencing `ghcr.io/nidzhat666/tonemill-worker:latest`, `pull_policy: always`, GPU reservation matching `homeserver-stacks/cinema-agent/docker-compose.yml`'s `jellyfin`/`plex` shape (`runtime: nvidia`, `deploy.resources.reservations.devices` with `driver: nvidia`/`capabilities: [gpu]`), plus `NVIDIA_DRIVER_CAPABILITIES=all`/`NVIDIA_VISIBLE_DEVICES=all`; `frontend` referencing `ghcr.io/nidzhat666/tonemill-frontend:latest`, `pull_policy: always`, joined to the external `nginx-network`; all services read env vars from `./.env`. **Post-deployment correction**: the `api` service was renamed to `tonemill-api` after going live — it collided in DNS with `honcho`'s own `api` service on the shared `nginx-network`, causing intermittent misrouted requests (research.md #10). `TONEMILL_API_BASE_URL` updated to match.
- [X] T007 [US2] Create `/Users/nidzhat/Documents/homeserver-stacks/tonemill/.env` directly on the server (over SSH — not committed, research.md #8) with `TONEMILL_S3_ENDPOINT_URL=http://minio-server:9000`, `TONEMILL_S3_PUBLIC_ENDPOINT_URL=https://s3.nidzh.com`, the T002 bucket's access key/secret, `TONEMILL_S3_BUCKET`, `TONEMILL_API_BASE_URL=http://api:8000`, and a chosen `TONEMILL_AUTH_USERNAME`/`TONEMILL_AUTH_PASSWORD` (consumed by US3's code, but the values themselves belong in this same env file)
- [X] T008 [US2] Commit and push `homeserver-stacks/tonemill/docker-compose.yml` (not `.env`) to `homeserver-stacks`; either wait for the ~1-minute GitOps timer or run `ssh homeserver 'cd ~/stacks/tonemill && docker compose pull && docker compose up -d'` (FR-004's confirmed manual-trigger decision)
- [X] T009 [US2] Verify all three containers are running (`docker compose ps`) and the worker has real GPU access: `ssh homeserver 'docker exec <worker-container> nvidia-smi'` succeeds (quickstart.md scenario 3)
- [X] T010 [US2] Verify the running `api`/`worker` can create/read objects in the new MinIO bucket via the internal endpoint, and that a presigned URL returned to a browser resolves via `https://s3.nidzh.com` (quickstart.md scenario 4)
- [X] T011 [P] [US2] Add a `tonemill` row to `/Users/nidzhat/Documents/homeserver-stacks/docs/stacks.md`'s summary table and its "GHCR-образы" table, matching the documentation convention every other stack follows (FR-010)

**Checkpoint**: User Stories 1 AND 2 both work — the application runs on real GPU hardware,
reachable within the home network (US3's public-domain gate isn't wired yet)

---

## Phase 5: User Story 3 - Gate access behind a shared login (Priority: P2)

**Goal**: No application functionality (frontend or API, via the BFF proxy) is reachable without
the correct shared username/password.

**Independent Test**: Request any page or `/api/*` path without credentials → refused; with the
correct credentials → succeeds. Verifiable without a real GPU job.

### Implementation for User Story 3

- [X] T012 [US3] Create `frontend/src/lib/auth.ts` with a small, docstring-documented function (e.g. `checkBasicAuth(authorizationHeader: string | null, username: string, password: string): boolean`) that parses an HTTP `Authorization: Basic` header and compares decoded credentials (FR-011, FR-013)
- [X] T013 [P] [US3] Add `frontend/src/lib/auth.test.ts`: Given/When/Then Vitest tests for `checkBasicAuth` covering a missing header, a malformed header, wrong credentials, and correct credentials
- [X] T014 [P] [US3] Wire `checkBasicAuth` into `frontend/src/hooks.server.ts`'s existing `handle` (currently a pass-through, per its own comment): read `TONEMILL_AUTH_USERNAME`/`TONEMILL_AUTH_PASSWORD` via `$env/dynamic/private` (matching `+server.ts`'s existing pattern), and return a `401` with a `WWW-Authenticate: Basic` header when the check fails, before `resolve(event)` runs (FR-011, FR-012; research.md #5)
- [X] T015 [US3] Add `TONEMILL_AUTH_USERNAME`/`TONEMILL_AUTH_PASSWORD` to `frontend/.env.example` with a one-line description, matching this file's existing documentation convention
- [X] T016 [US3] Verify quickstart.md scenario 5 against the deployed app: unauthenticated requests to `https://tonemill.nidzh.com/` and any `/api/*` path are refused (401); correct credentials succeed; `curl http://<homeserver-ip>:8000/jobs` is refused at the connection level, confirming T006's unpublished `api` port (SC-006)

**Checkpoint**: All three P1/P2 stories work together — the app is safely exposable at
`tonemill.nidzh.com` behind the shared login

---

## Phase 6: User Story 4 - Confirm GPU-accelerated grading actually works on real hardware (Priority: P3)

**Goal**: A real HDR file, submitted through the live production app, completes GPU-accelerated
grading successfully — closing the project's long-standing unverified-real-hardware gap.

**Independent Test**: Submit a real HDR clip through the deployed, authenticated app with the
GPU-accelerated profile selected (or `auto`); confirm it completes and produces a correct,
downloadable result.

### Implementation for User Story 4

- [x] T017 [US4] **BLOCKED, not resolved by this feature** — attempted through the deployed app (internal path, domain not yet live) with a real synthetic HLG/BT.2020 clip. Root-caused precisely, two real bugs found and fixed along the way (registry.py probe-frame size; worker.Dockerfile missing libvulkan1/libx11-6/libxext6), but `hlg-gpu` still fails: libplacebo's Vulkan device creation fails with `VK_ERROR_INCOMPATIBLE_DRIVER`. Confirmed via `vulkaninfo` and a direct ctypes call that NVIDIA's own `vk_icdGetInstanceProcAddr` returns NULL for `vkCreateInstance` on this host, independent of ffmpeg -- not a Tonemill bug. Confirmed CUDA decode + hevc_nvenc encode both work perfectly (13.8x realtime) in isolation; only libplacebo's Vulkan tone-mapping step is affected. Root cause: `homeserver` runs the legacy `runtime: nvidia` NVIDIA Container Toolkit mode (`nvidia-ctk cdi list` → 0 CDI devices, no `/etc/cdi/` at all) which doesn't fully wire up a working Vulkan ICD inside containers; the documented fix is migrating the host to CDI mode, which is out of this feature's scope (affects every GPU stack on the host, e.g. cinema-agent's jellyfin/plex, not just tonemill). See research.md #9.
- [x] T018 [US4] Updated `specs/001-color-grading-pipeline/tasks.md` and `research.md` to honestly reflect the above: NVENC/CUDA hardware access is now verified on real hardware (closing that part of the original gap); the Vulkan/libplacebo tone-mapping step remains blocked by host-level NVIDIA Container Toolkit configuration, documented as a distinct, precisely-diagnosed follow-up rather than left as a vague "unverified" note

**Checkpoint**: All four user stories are independently functional — the feature's full value is
delivered and the project's oldest open risk is closed

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final verification across all stories

- [X] T019 [P] Verify rollback (quickstart.md scenario 7): note the currently running `:sha-<short>`, pin a different previously published `:sha-<short>` in `homeserver-stacks/tonemill/docker-compose.yml`, push, and confirm the GitOps timer deploys it without rebuilding from source (SC-002, SC-005)
- [X] T020 Ran all 7 quickstart.md scenarios (interleaved with T004/T005/T009/T010/T016/T019 as each was implemented, then reconfirmed here). Final status: **SC-001 through SC-002, SC-004 through SC-006 all hold** (verified live: build+publish, no-partial-publish-on-failure, GPU-visible-in-container, internal+public S3 endpoints, login gate 401/401/401/200 plus port-8000 connection-refused, rollback via a real GitOps-timer-driven redeploy). **SC-003 (GPU-accelerated grading) does not yet hold** — scenario 6 blocked, root-caused and documented in research.md #9/#18, not a silent gap.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — the repo must exist before any CI can run
- **Foundational (Phase 2)**: Independent of Setup; can run in parallel with it. BLOCKS US2 (needs storage credentials) and transitively US4 (needs a working deployment)
- **User Story 1 (Phase 3)**: Depends on Setup (needs the GitHub repo). Independent of Foundational.
- **User Story 2 (Phase 4)**: Depends on US1 (needs published images to reference) and Foundational (needs MinIO credentials)
- **User Story 3 (Phase 5)**: Independent of US2's runtime state — the auth-check code (T012–T015) can be written and unit-tested any time after Setup; only the live verification (T016) needs US2 deployed. T007 (env vars) is shared with US2 for convenience but the credential *values* don't block writing T012–T015.
- **User Story 4 (Phase 6)**: Depends on US1 + US2 (needs a real running deployment) and benefits from US3 being live (tests the real public URL, per T017's wording) but could technically run against the internal-network address alone if US3 weren't done yet
- **Polish (Phase 7)**: Depends on all four user stories being complete

### Parallel Opportunities

- Setup (T001) and Foundational (T002) touch unrelated systems (GitHub vs. MinIO) and can run in parallel
- T012–T015 (US3's auth code) can be developed and unit-tested (T013) in parallel with all of US2's deployment work (T006–T011), since they touch entirely different files/systems — they only need to land before T016's live verification
- T013 and T014 can run in parallel once T012 exists (different files, both only depend on T012)
- T011 (docs update) can run in parallel with T009/T010 (live verification) — different files
- T019 (rollback check) has no file dependency on T020 (final quickstart pass) and could run in parallel, though running T020 last as a true final sign-off is simpler

---

## Parallel Example: User Story 3

```bash
# After T012 (frontend/src/lib/auth.ts) exists, run together:
Task: "Add Given/When/Then Vitest tests in frontend/src/lib/auth.test.ts"
Task: "Wire checkBasicAuth into frontend/src/hooks.server.ts's handle"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (create the GitHub repo)
2. Complete Phase 3: User Story 1
3. **STOP and VALIDATE**: Push a commit, confirm three images land in GHCR — the CI half of this
   feature is already delivering value (a working build/publish pipeline) even before anything
   is deployed

### Incremental Delivery

1. Setup → repo exists
2. Foundational → MinIO bucket/credentials ready (can happen anytime before US2)
3. Add User Story 1 → validate → images publish automatically (MVP)
4. Add User Story 2 → validate → the app is actually running on the RTX 3080 Ti
5. Add User Story 3 → validate → safely exposable at `tonemill.nidzh.com`
6. Add User Story 4 → validate → the GPU path is finally confirmed on real hardware
7. Polish → rollback verified, full quickstart pass

## Notes

- [P] tasks = different files/systems, no dependencies
- [Story] label maps task to specific user story for traceability
- This feature spans `tonemill` (this repo) and `/Users/nidzhat/Documents/homeserver-stacks` —
  task descriptions name the repo explicitly whenever it isn't `tonemill`
- No automated tests beyond T013 (the one piece of new application logic); everything else is
  verified by real, live checks (pushes, SSH, curl) per quickstart.md — matching this project's
  established practice of verifying infrastructure claims for real rather than assuming them
- Commit after each phase checkpoint
