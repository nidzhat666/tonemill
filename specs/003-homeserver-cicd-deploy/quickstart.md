# Quickstart: Validating Homeserver CI/CD & GPU Deployment

## Prerequisites

- `gh` authenticated as `nidzhat666` (already confirmed working during planning).
- SSH access to `homeserver` (already confirmed working during planning: `ssh homeserver`).
- A GitHub repository for `tonemill` exists and this local repo's `main`/`master` is pushed to it
  (none exists yet as of this plan — see tasks.md).
- `homeserver-stacks/tonemill/.env` created directly on the server with the six env vars from
  data-model.md (research.md #8 — plain `.env`, not Infisical, for now).
- A dedicated bucket + access key created in the existing homeserver MinIO for Tonemill.

## Validation scenarios

Each maps to an acceptance scenario in `spec.md`.

1. **Build & publish (US1)** — Push a trivial commit to `main`. In the GitHub repo's Actions tab,
   confirm the matrix build runs and all three images
   (`ghcr.io/nidzhat666/tonemill-{api,worker,frontend}`) appear in the repo's Packages with both
   a `:latest` and a `:sha-<short>` tag, within 10 minutes (SC-001). Confirm no manual
   `docker build`/`docker push` was run.

2. **Build failure doesn't publish (US1)** — Temporarily break one Dockerfile (e.g. a typo) on a
   branch, open a PR or push to main, confirm the workflow fails and no new image is published
   for any of the three components (FR-003).

3. **Deploy to the GPU host (US2)** — With `homeserver-stacks/tonemill/docker-compose.yml`
   committed and pushed, either wait for the ~1-minute GitOps timer or run
   `ssh homeserver 'cd ~/stacks/tonemill && docker compose pull && docker compose up -d'`
   (matching FR-004's manual-trigger decision). Confirm all three containers report healthy/
   running, and `docker exec <worker-container> nvidia-smi` succeeds (worker has real GPU
   access).

4. **Storage & secrets (US2)** — Confirm the running `api`/`worker` containers can create/read
   objects in the new MinIO bucket via the internal endpoint, and that presigned URLs returned
   to a browser resolve via `https://s3.nidzh.com`. Confirm `homeserver-stacks/tonemill/.env` is
   not committed to git (`git status`/`git log` show it untracked, matching the repo's
   `.gitignore`).

5. **Shared-login gate (US3)** — With no credentials, request `https://tonemill.nidzh.com/` and
   any `/api/*` path and confirm both are refused (401 + `WWW-Authenticate: Basic`). Repeat with
   the correct username/password and confirm full access. Attempt
   `curl http://<homeserver-ip>:8000/jobs` directly and confirm it is refused at the connection
   level (port not published) rather than reachable and merely unauthenticated (SC-006).

6. **Real GPU grading (US4)** — Through `https://tonemill.nidzh.com` (authenticated), upload a
   real HDR clip, select the GPU-accelerated profile (or `auto`), and confirm the job completes
   successfully end-to-end and produces a downloadable, correctly graded result (SC-003) — the
   first real-hardware confirmation of this path.

   **Status as of this feature's implementation: blocked, not passing.** Attempted with a real
   synthetic HLG/BT.2020 clip; two real bugs found and fixed along the way (GPU-detection probe
   frame size, missing `libvulkan1`/`libx11-6`/`libxext6` in `worker.Dockerfile`), but
   `hlg-gpu` still fails — libplacebo's Vulkan device creation fails with
   `VK_ERROR_INCOMPATIBLE_DRIVER`, root-caused to the host's legacy (non-CDI) NVIDIA Container
   Toolkit mode. CUDA decode + `hevc_nvenc` encode are separately confirmed genuinely working.
   `hlg-cpu` confirmed working end-to-end on this same real deployment as the current
   production path. Full diagnosis: research.md #9.

7. **Rollback (SC-002)** — Note the `:sha-<short>` tag currently running. Edit
   `homeserver-stacks/tonemill/docker-compose.yml` to pin a different, previously published
   `:sha-<short>`, commit, and push. Confirm the GitOps timer picks it up and the pinned version
   comes up — without rebuilding anything from source.

## Expected outcome

All seven scenarios pass, matching `spec.md`'s Success Criteria (SC-001–SC-006), with the
GPU-accelerated grading path confirmed working on real hardware for the first time in this
project's history.
