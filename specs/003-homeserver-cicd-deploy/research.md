# Research: Homeserver CI/CD & GPU Deployment

## 1. GitHub Actions → GHCR build pattern

**Decision**: Adapt this account's own proven `ghcr-build.yml` template (fetched live from
`nidzhat666/reelsaz`, a real working repo — not written from memory/assumption) into a **matrix
build**, one job per Dockerfile (`docker/api.Dockerfile`, `docker/worker.Dockerfile`,
`docker/frontend.Dockerfile`), publishing three images:
`ghcr.io/nidzhat666/tonemill-api`, `ghcr.io/nidzhat666/tonemill-worker`,
`ghcr.io/nidzhat666/tonemill-frontend`. Each tagged `:latest` (default branch only) and
`:sha-<short>`, via `docker/metadata-action@v5` — same tagging scheme already used for every
other GHCR image in this account.

**Rationale**: Every other custom-built service in this account's fleet (`eatmeter_garmin`,
`kinozal-bot`, `wordpocket`, `reelsaz`, the `honcho` fork) publishes exactly one image per repo
using this identical workflow shape. Tonemill is the first repo in the fleet with three
deployable components from one repo, so the template needs a matrix instead of the single-image
`IMAGE_NAME: ${{ github.repository }}` line — everything else (buildx, GHCR login via
`GITHUB_TOKEN`, metadata-driven tagging, `linux/amd64`) carries over unchanged.

**Alternatives considered**:
- Three separate GitHub repos (api/worker/frontend split) — rejected: Tonemill is deliberately
  one repo/one package today (`backend/src/tonemill/`); splitting repos for CI convenience would
  be a much larger, unrequested restructuring (Principle I: YAGNI).
- One combined image running all three processes — rejected: breaks the existing, intentional
  three-container architecture (API/worker/frontend already scale and restart independently)
  for no benefit.

## 2. Real target-host verification

**Decision**: Confirmed live via `ssh homeserver` (read-only checks, no changes made):
`x86_64`, Ubuntu 24.04.3 LTS, Docker 29.0.0, GPU = NVIDIA GeForce RTX 3080 Ti, driver
`580.173.02`, and `docker info` lists `nvidia` as an available container runtime alongside
`runc`/`containerd`.

**Rationale**: This project's own history (specs/001) explicitly flagged the GPU-in-container
path as "validated on the bare host, never inside a container" and treated it as an open risk
rather than an assumption. Given real SSH access exists, verifying the actual target host's
architecture, Docker version, GPU, driver, and container-runtime availability before planning
further is the same discipline already applied throughout this project (e.g. the ffmpeg pin,
the GPU-detection bug) — confirm, don't assume. The driver version (580.x) matches what the
existing local `docker-compose.yml` comment already named as the validated driver, which is a
good sign this host is the same one that comment was written against.

**Alternatives considered**: Proceeding on the assumption that "a home server with an RTX 3080
Ti" implies x86_64/Linux/NVIDIA-toolkit-installed — rejected; cheap to verify for real, and this
project has been burned before by unverified GPU-path assumptions (the `auto`-resolution bug).

## 3. GHCR authentication in Actions

**Decision**: Use the workflow-scoped `GITHUB_TOKEN` (via `docker/login-action@v3`), not a
personal access token — matching the proven `reelsaz` template. Requires
`permissions: packages: write` on the job.

**Rationale**: `GITHUB_TOKEN` is automatically issued per-workflow-run with no secret to manage,
and this exact mechanism is already working for five other repos in this account. No new
credential is introduced.

**Alternatives considered**: A dedicated PAT stored as a repo secret — rejected, unnecessary
since `GITHUB_TOKEN` already has sufficient scope for pushing to the repo's own GHCR namespace.

## 4. Object storage: reuse the existing homeserver MinIO

**Decision**: Point the production deployment at the homeserver's already-running MinIO stack —
internal endpoint `http://minio-server:9000` (its container name, confirmed from
`homeserver-stacks/minio/docker-compose.yml`) for `TONEMILL_S3_ENDPOINT_URL`, and
`https://s3.nidzh.com` (confirmed from that same file's `MINIO_SERVER_URL`) for
`TONEMILL_S3_PUBLIC_ENDPOINT_URL`. A new bucket (e.g. `tonemill`) and a dedicated access
key/secret are created within that existing instance — not a new MinIO deployment.

**Rationale**: FR-006 requires reusing existing storage rather than provisioning new
infrastructure. This is also exactly the internal-vs-public endpoint split
`config.py`'s `s3_endpoint_url`/`s3_public_endpoint_url` fields were already built for (see
their docstrings) — this real-world deployment is precisely the case that justified that design,
not a coincidence. For Tonemill's `api`/`worker` containers to reach `minio-server:9000` by
container name, the `tonemill` stack's services must join the same `nginx-network` Docker
network that the `minio` stack publishes itself on (confirmed `networks: - nginx-network` in
its compose file).

**Alternatives considered**: Routing all internal traffic through the public
`https://s3.nidzh.com` endpoint too — rejected: adds an unnecessary external hop and TLS
overhead for container-to-container calls, and the split-endpoint capability already exists in
code with no extra work required to use it correctly.

## 5. Shared-login gate: where it lives, and the port that must stay closed

**Decision**: Implement the shared-login check (FR-011–FR-013) entirely in the frontend's
`hooks.server.ts` — a plain HTTP Basic Auth challenge validated against
`TONEMILL_AUTH_USERNAME`/`TONEMILL_AUTH_PASSWORD` (server-only env vars, `$env/dynamic/private`,
matching this file's existing pattern in `+server.ts`). No changes to the FastAPI backend. In
the `homeserver-stacks/tonemill/docker-compose.yml`, the `api` service's port MUST NOT be
published to the host (no `ports:` entry) — only `frontend`'s port is reachable (and only via
the `nginx-network`/nginx-proxy-manager path to `tonemill.nidzh.com`).

**Rationale**: `hooks.server.ts` already wraps every request SvelteKit serves — including the
`/api/*` BFF proxy route (`+server.ts`) that is the browser's *only* path to the backend
(`TONEMILL_API_BASE_URL` is a server-only env var the browser can never resolve directly, per
that file's own comment). Gating in exactly one place, rather than duplicating the same check
into FastAPI, is the simplest sufficient fix (Principle I) — but it is only sufficient if the
API's host port stays unpublished; otherwise a request straight to `http://<host>:8000/jobs`
would bypass `hooks.server.ts` entirely, since that check never runs for a request that doesn't
go through SvelteKit at all. This is why "don't publish the API port" is called out as a hard
constraint in plan.md, not a minor detail.

Uploads themselves go browser → MinIO directly via presigned URLs (not proxied through
SvelteKit), which does **not** create a bypass: minting a presigned URL requires calling
`POST /api/uploads`, which — like every other request — passes through the
Basic-Auth-checking `hooks.server.ts` first. An unauthenticated visitor never obtains a
presigned URL to use in the first place.

**Alternatives considered**:
- Auth check duplicated in both FastAPI and `hooks.server.ts` — rejected: the API becoming
  unreachable from outside the Docker network already closes the only bypass, so a second,
  redundant check would just be more code with no additional security benefit (Principle I).
- Auth at the nginx-proxy-manager layer (its built-in Access Lists) — rejected: FR-012
  explicitly requires the credentials live in the deployment's environment configuration
  (`.env`), not in NPM's own UI-managed, non-version-controlled access-list database.

## 6. Rollback mechanism (SC-002)

**Decision**: Every image is tagged with both `:latest` and `:sha-<short>` (research.md #1).
Rolling back means editing `homeserver-stacks/tonemill/docker-compose.yml` to pin a specific
`:sha-<short>` tag instead of `:latest`, committing, and pushing — which the existing GitOps
timer picks up as a real diff to that stack directory (unlike a routine `:latest` update, a
tag-pin change in the compose file itself *is* a tracked change, so the existing reconcile loop
handles it with no new mechanism needed).

**Rationale**: This reuses the deployment repo's existing, working reconciliation loop exactly
as designed, rather than building separate rollback tooling — the loop already does the right
thing for any compose-file change, rollback included.

**Alternatives considered**: A dedicated rollback script — rejected as unrequested tooling for a
one-line compose-file edit that the existing GitOps flow already handles correctly.

## 7. Registry/repository visibility

**Decision**: The `tonemill` GitHub repository (not yet created — confirmed no remote is
currently configured) is created as **public**, and its GHCR images inherit public visibility.

**Rationale**: Tonemill's own original specification describes it as "an open-source,
MIT-licensed" project — a public repo and public images are the only consistent choice for
that stated goal, and match this account's own convention of public GHCR images for its other
public-facing tools.

**Alternatives considered**: Private repo/images — rejected as contradicting the project's own
stated open-source goal; would also require a registry pull secret on `homeserver` that no
other stack in the fleet needs today.

## 8. Secrets: a plain `.env` for now, not Infisical

**Decision**: The `tonemill` stack's secrets (the six variables in data-model.md) live in a
plain `.env` file placed directly in `homeserver-stacks/tonemill/` on the server, created
manually (e.g. over SSH) rather than generated by the Infisical integration every other
secret-bearing stack uses. No `.infisical` marker file is added for this stack.

**Rationale**: An explicit follow-up request to skip Infisical for now, in favor of the
simplest thing that works. This is a supported path, not a workaround:
`deploy-stacks.sh`'s `refresh_env_from_infisical` function only runs when a `.infisical` marker
is present in the stack directory (`[ -f .infisical ] || return 0`) — without it, the reconcile
loop just runs `docker compose up -d` against whatever `.env` is already sitting in that
directory, unmanaged. `.env` is already covered by `homeserver-stacks/.gitignore`
("Secrets — NEVER commit": `.env`, `.env.*`, `*.env`), so this still satisfies FR-007/FR-012
(not committed in plaintext) — it just isn't centrally rotated/audited via Infisical the way
every other secret-bearing stack's is.

**Alternatives considered**: Infisical from the start, matching every other secret-bearing
stack — the originally-planned default, and still the natural next step later: adding a
`.infisical` marker and populating the `/tonemill/` path in the existing Infisical project is a
non-breaking follow-up, not a redo, whenever that trade-off is revisited.

## 9. hlg-gpu on real hardware: NVENC/CUDA work, libplacebo's Vulkan step doesn't (yet)

**Finding**: The first real-hardware run of `hlg-gpu` (RTX 3080 Ti, T017) surfaced three
distinct issues, found and precisely isolated in order:

1. **Fixed** — `detect_gpu_encoder_available()`'s probe frame (`64x64`, later confirmed
   `128x128` too) is below `hevc_nvenc`'s real minimum encode size ("Frame dimensions are less
   than the minimum supported value"). `256x256` clears it. This wrongly reported `hevc_nvenc`
   unavailable even on hardware that genuinely supports it — see `registry.py`.
2. **Fixed** — the worker image had no Vulkan loader (`libvulkan1`) at all, so libplacebo fell
   back to a sentinel "Instance API version 1.0.0" rather than a real negotiated version.
   Adding `libvulkan1` surfaced a second, cascading issue: `ldd` on the NVIDIA-mounted
   `libGLX_nvidia.so.0` showed `libX11.so.6`/`libXext.so.6` as unresolved — NVIDIA's Vulkan
   implementation links against X11 client libraries even for this fully headless, no-display
   encode path. Adding `libx11-6`/`libxext6` resolved that.
3. **Not fixed by this feature — host-level, out of scope** — with all runtime library
   dependencies resolved (`ldd` clean), Vulkan instance creation still fails with
   `VK_ERROR_INCOMPATIBLE_DRIVER`. Isolated with `VK_LOADER_DEBUG=all`: the loader finds and
   `dlopen()`s the NVIDIA ICD manifest (`/etc/vulkan/icd.d/nvidia_icd.json` →
   `libGLX_nvidia.so.0`) successfully, but `vk_icdGetInstanceProcAddr(NULL, "vkCreateInstance")`
   returns `NULL` — confirmed independently three ways: `vulkaninfo --summary` (installed
   ad hoc for diagnosis), and a direct Python `ctypes.CDLL(...).vk_icdGetInstanceProcAddr(...)`
   call, both reproducing the same `NULL` result outside of ffmpeg entirely. CUDA decode
   (`-hwaccel cuda`) and `hevc_nvenc` encode were separately confirmed fully working in
   isolation (13.8x realtime) — this is specifically a Vulkan ICD initialization failure, not a
   general "no GPU access" problem.

**Root cause**: `homeserver` runs the NVIDIA Container Toolkit's legacy `runtime: nvidia` mode
(matching `cinema-agent`'s existing jellyfin/plex configuration, which this feature deliberately
reused per research.md #5's original rationale). `nvidia-ctk cdi list` reports 0 CDI devices and
`/etc/cdi/` doesn't exist on the host — this host has never had CDI (Container Device Interface)
mode set up. Legacy mode reliably wires up CUDA/NVENC device access (confirmed working) but does
not reliably produce a functional Vulkan ICD inside containers; NVIDIA's own documentation
recommends CDI mode for anything beyond pure compute/video workloads.

**Why this is out of scope for this feature, not just deferred out of laziness**: fixing this
means migrating the *host's* NVIDIA Container Toolkit configuration (`nvidia-ctk cdi generate`
+ switching every GPU-using compose file's device-reservation syntax from `runtime: nvidia` to
CDI device references) — a change with blast radius across every GPU stack already running on
`homeserver` (`cinema-agent`'s jellyfin/plex, `dispatcharr`'s transcoding), not something owned
by or scoped to the `tonemill` stack this feature adds. Making that change unilaterally as part
of a `tonemill`-focused feature would risk regressing already-working, unrelated production
services.

**Current state**: `hlg-cpu` verified working end-to-end on this real deployment (confirmed:
job completes, correct Rec.709-tagged HEVC output, downloadable via presigned URL) — the
application is fully functional in production today via the CPU path. `hlg-gpu` remains
unavailable until the host's Vulkan/CDI setup is addressed, tracked as a distinct, precisely
diagnosed follow-up rather than the vague "never verified" status it had before this feature.

**Alternatives considered**: Migrating the host to CDI as part of this feature — rejected for
its cross-stack blast radius (see above); worth doing as its own deliberate, explicitly-scoped
piece of work. Dropping the Vulkan/libplacebo tone-mapping step from `hlg-gpu` in favor of a
CUDA-only or `zscale`-based (CPU-filter, GPU-encode-only) hybrid — rejected: changes the
profile's actual color-science implementation to work around an infrastructure gap, which is a
worse trade than fixing the infrastructure once, properly, host-wide.

## 10. Post-deployment: intermittent 404s from the shared-hostname "api" collision with honcho

**Finding**: After going live, the frontend's grading-profile dropdown intermittently showed
only "auto" and the job list intermittently showed as empty even when jobs existed — traced to
`GET /api/profiles` (and other `/api/*` calls) returning a genuine-looking
`{"detail":"Not Found"}` roughly 1 in 3 times. This looked exactly like a backend routing bug
and led down two unproductive detours before the real cause was found:

1. **Wrong theory #1**: Uvicorn's default keep-alive timeout (5s) shorter than the BFF's
   outbound connection-pool idle timeout, causing a reused-stale-socket race. Raised
   `--timeout-keep-alive` to 75s — did not fix it (still ~30% failures after idle gaps).
2. **Wrong theory #2**: a bug in Node's shared undici connection pool for the BFF's outbound
   `fetch()`. Introduced a fresh, single-use `undici.Agent` dispatcher per proxied request.
   This first broke everything (`TypeError: fetch failed`, 10/10) because it mixed an
   `Agent` from the standalone `undici` npm package with Node's *global* `fetch`, which is
   powered by its own separate internal undici instance — incompatible pairing. Fixed by using
   `undici`'s own exported `fetch` consistently — but even then, still ~30% failures remained.
   Both attempts were reverted once the real cause was found (see `git log` on
   `frontend/src/routes/api/[...path]/+server.ts` and `docker/api.Dockerfile` for the full,
   honest back-and-forth).

**Real root cause**: `getent hosts api` from a container on `nginx-network` returned **two
different IPs**, alternating. `homeserver-stacks/honcho/docker-compose.yml` has a service
literally named `api`, also joined to `nginx-network` — Compose auto-registers every service's
own name as a DNS alias on every network it joins (not just explicit `aliases:` entries), so
with both `tonemill` and `honcho` naming a service `api` on the same shared network, Docker's
embedded DNS round-robinned the hostname `api` between `tonemill-api-1` and `honcho-api-1`.
Honcho is also a FastAPI app, so hitting it for a path it doesn't have (`/profiles`) returned a
genuinely well-formed `{"detail":"Not Found"}` — indistinguishable from a real Tonemill bug
without checking *which container* actually answered.

**Decision**: Renamed the service from `api` to `tonemill-api` in
`homeserver-stacks/tonemill/docker-compose.yml` (explicit `container_name` + `aliases` entry),
and updated `TONEMILL_API_BASE_URL` in the server's `.env` to match. Confirmed via
`getent hosts tonemill-api` (5/5 identical IP) and a real 8-second-gap reproduction loop against
the live public domain (0/8 failures, versus consistent ~30% failures before). Checked every
other stack in `homeserver-stacks` for the same collision risk against `tonemill`'s other
service names (`worker`, `frontend`, `redis`) — no other collision exists today.

**Lesson for future services on this shared network**: a generic Compose service name (`api`,
`worker`, `app`, `web`, ...) is only safe on a *private* per-project network; anything joining
the shared `nginx-network` needs a project-prefixed name, since Compose's automatic
service-name aliasing has no per-project namespacing on a network shared across many unrelated
stacks.

**Alternatives considered**: Keeping the name `api` and instead using `container_name`/explicit
network aliases only — rejected: Compose still registers the *service name* itself as an alias
regardless of `container_name`, so this would not have removed the collision. Not joining
`tonemill-api` to `nginx-network` at all — rejected: it genuinely needs to reach `minio-server`
on that network for presigned-URL generation and object checks (research.md #4).
