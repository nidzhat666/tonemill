# Phase 0 Research: Tonemill

All items below resolve the "NEEDS CLARIFICATION"-shaped technical unknowns implied by the spec's Technical Context. Two items (Vulkan-in-container, near-lossless quality value) are decisions made for v1 but explicitly flagged as needing on-hardware verification/tuning rather than settled research — that's the honest state, not a gap in this document.

## 1. Task-queue framework: Dramatiq vs. alternatives

**Decision**: Dramatiq (`dramatiq[redis]`) as the worker/queue framework, using Redis purely as its broker.

**Rationale**: The actual unit of work — spawning `ffmpeg`, blocking on its `-progress pipe:1` stream, waiting on subprocess exit — is inherently blocking, not I/O-bound in the asyncio sense, so a synchronous worker model is a better fit than forcing it through an event loop. Dramatiq's `--processes`/`--threads` CLI flags map directly and explicitly onto the spec's per-GPU concurrency requirement (default 1, configurable up to 2 — FR-018): one process-per-GPU-slot, no extra abstraction needed. It requires no separate result backend (job state is hand-rolled in Redis anyway, per the "Redis is the only state store" architecture decision), keeping the dependency footprint small.

**Alternatives considered**:
- **RQ (Redis Queue)** — simpler API, but weaker built-in concurrency/worker-pool control than Dramatiq's process/thread model; would need more custom scaffolding to enforce the per-GPU concurrency cap.
- **Celery** — the most feature-rich option, but its configuration surface (multiple broker/backend combinations, routing, Beat, etc.) is significant overkill for a single/few-worker home-lab deployment and works against the project's explicit "keep the foundation simple" stance.
- **arq** — asyncio-native, which is superficially attractive next to FastAPI's async style, but the task body itself gains nothing from asyncio (it's dominated by a blocking subprocess), and arq's ecosystem/maturity is thinner than Dramatiq's.

**Verdict**: No alternative surfaced a compelling reason to move off the original working assumption — Dramatiq stands.

## 2. S3-compatible client library

**Decision**: `boto3`, configured with a swappable `endpoint_url` (MinIO locally, unset/AWS-default in production), used by both the API (to mint presigned single- and multi-part URLs) and the worker (to download sources / upload results).

**Rationale**: `boto3` is the de facto standard S3 client and MinIO explicitly targets S3-API compatibility with it. It natively supports every multipart primitive the upload flow needs: `create_multipart_upload`, `generate_presigned_url("upload_part", ...)` per part, `complete_multipart_upload`, `abort_multipart_upload` — no custom signing logic required.

**Alternatives considered**:
- **aioboto3** — async wrapper; attractive next to FastAPI, but presigned-URL generation and multipart bookkeeping are fast, non-blocking-in-practice calls, so the added dependency/complexity isn't justified for v1.
- **`minio` (official MinIO SDK)** — MinIO-specific; would break the explicit requirement to work unmodified against real AWS S3.

## 3. Pinning the `ffmpeg` build

**Decision**: The worker Dockerfile pulls the exact BtbN `ffmpeg-n8.1-latest-linux64-gpl` release asset by its specific release URL/tag (not a "latest" alias that moves over time), with an inline comment directly above the download step recording *why*: the rolling `master` build requires NVENC API ≥13.1 (driver ≥610), while the validated target GPU host runs driver 580.x (API 13.0) and fails with "Function not implemented" against `master`.

**Rationale**: This is a validated, already-hit failure mode (not speculative) — the whole point of pinning is to stop a future image rebuild from silently sliding onto an incompatible build. Documenting the *reason* inline (not just the version) is what makes the pin durable across future edits.

**Alternatives considered**:
- **Build ffmpeg from source** — more control over exact flags, but a much heavier CI/build burden for no benefit here, and image-publishing pipelines are explicitly out of scope for v1.
- **Track BtbN's rolling `latest` tag** — rejected outright: this is the exact regression the operational constraints warn against.

## 4. GPU container exposure: CUDA + Vulkan together

**Decision for v1**: Set `NVIDIA_DRIVER_CAPABILITIES=all` (superset covering `compute`, `video`, and `graphics`) on the GPU worker's Compose service, rather than the toolkit's CUDA-only default — `libplacebo`'s Vulkan path needs the `graphics` capability, which plain `--gpus all` / a compute-only capability list does not guarantee.

**Status**: **Not fully resolved by research — flagged for on-hardware verification.** This was validated only on the bare GPU host this session, never inside a container. The plan carries this forward as an explicit first-run verification step (see quickstart.md), not as a proven fact. If `all` turns out to be broader than needed (or insufficient), the fallback is to enumerate the minimal capability set (`compute,video,graphics,utility`) and re-test.

**Alternatives considered**: Leaving capabilities at the NVIDIA Container Toolkit's CUDA-only default — rejected because it's already known that plain `--gpus all` covers CUDA/NVENC but not Vulkan ICD exposure, which `hlg-gpu` requires for its libplacebo pass.

## 5. Progress reporting from `ffmpeg`

**Decision**: The worker actor spawns `ffmpeg ... -progress pipe:1 -nostats`, reads the child's stdout line-by-line in a blocking loop (consistent with Dramatiq's synchronous actor model — decision #1), parses `out_time_ms=`, and divides by the source's duration (probed once via `ffprobe` at job start) to compute a percentage. Each parsed update writes `{status: running, stage: processing, progress: pct}` into the job's Redis hash, throttled to roughly once per 1–2 seconds to avoid hammering Redis on every line. The stream's own `progress=end` marker (or the process's exit code) drives the transition out of the `processing` stage.

**Rationale**: This is exactly what FR-005 mandates — machine-readable progress, not stderr-scraping — and matches the validated approach from the operational constraints.

## 6. Redis job-state schema and TTL behavior

**Decision**: One Redis hash per job at key `tonemill:job:{job_id}`, holding `status`, `stage`, `progress`, `requested_profile`, `resolved_profile`, `max_quality`, `source_key`, `result_key`, `error`, `created_at`. An `EXPIRE` (default 24h, operator-configurable via env var) is (re-)applied on every write to that hash, so a job's record naturally survives as long as it's actively being updated and then counts down from whatever its *last* update was (typically its terminal `done`/`failed` write) — no separate cleanup process needed.

**Rationale**: Satisfies the spec's "bounded, operator-configurable TTL" assumption with the simplest possible mechanism — Redis's native key expiry — instead of a custom sweeper.

## 7. Frontend: SvelteKit as the backend-for-frontend

**Decision**: SvelteKit (Svelte 5) app, per the clarified decision. Multipart upload orchestration (file slicing, parallel part `PUT`s, resume-by-tracking-completed-parts) is implemented client-side in `frontend/src/lib/upload.ts` against the browser's `File`/`fetch` APIs, with per-file upload/job state held in a Svelte store so multiple concurrently submitted files (FR-026) render independent progress/status without interfering with each other.

**Alternatives considered**: A static page calling the API directly from the browser — explicitly rejected during clarification in favor of a dedicated app with its own backend-for-frontend layer.

## 8. Initial quality value for the "maximum quality" (near-lossless) option

**Decision for v1**: Start the GPU near-lossless encode at `-rc vbr -cq 1 -b:v 0` (hevc_nvenc's lowest practical CQ value) as the initial default for FR-028, rather than leaving it unspecified.

**Status**: **Explicitly not benchmarked this session** — unlike the two default profiles' contrast/saturation/CQ-20/CRF-20 values (FR-011, which are locked and must not be re-derived), this value has no multi-scene clipping-threshold validation behind it yet. It should be run through the same measurement-based tuning method (FR-017) before being treated as final, using the profiling tool built for task coverage of FR-017. Until then, CQ 1 is a reasonable, conservative starting point (NVENC's documented range treats very low CQ values as visually lossless) that unblocks implementation without contradicting FR-011's "don't guess" rule for the *already-validated* profiles.

**Where this sits on the quality/size spectrum** (illustrative, order-of-magnitude figures for a 10-minute 4K60 clip — only the CQ 20 / CRF 20 row is an actual validated Tonemill number; the rest are standard HEVC ballparks shown for context, not project-benchmarked, since real size is always content-dependent):

| Setting | In Tonemill? | Encoder value | Quality loss | Size vs. default | Example: 10-min 4K60 |
|---|---|---|---|---|---|
| Raw / uncompressed | Not produced — reference only | — | None (not encoded) | ~150–250× larger | ~500–700 GB |
| True bit-exact lossless | Considered, explicitly rejected (FR-028) | CQ/CRF 0 / lossless flag | None (mathematically identical) | ~8–12× larger | ~30–60 GB |
| `max_quality: true` | Yes — GPU only | CQ ≈ 1 | Imperceptible, even under close inspection | ~3× larger | ~10–15 GB |
| `max_quality: false` (default) | **Yes — default for both profiles** | CQ 20 (`hlg-gpu`) / CRF 20 (`hlg-cpu`) — FR-009/FR-010, validated | Imperceptible in normal viewing; tiny loss only under pixel-level inspection | 1× (baseline) | ~3–5 GB |
| Typical streaming quality | Not implemented — comparison only | CRF ≈ 28 | Visible in detailed/complex scenes; occasional banding on skies/gradients | ~⅓ the size | ~1–1.5 GB |
| Heavy compression | Not implemented — comparison only | CRF ≈ 35+ | Clearly visible — blocking, banding, softened detail | ~⅛ the size | ~0.4–0.5 GB |

Tonemill's default already sits well up the quality end of this spectrum; `max_quality` only spends a large size increase on the narrow, largely-invisible gap between "imperceptible" and "mathematically perfect."

**This value is per-profile, not a global constant — it will NOT automatically transfer to future formats (e.g., D-Log M).** FR-024 scopes quality/encoder target as part of each profile's own tunable configuration, and FR-017 requires any new profile's parameters (grading *and* quality target) to go through the same measurement-based validation rather than being copied from an existing profile. HLG and D-Log source material have different gamma curves and dynamic-range distributions, so how compressible the graded footage ends up being — and therefore what CQ/CRF value is actually appropriate — is expected to differ and must be re-measured against real D-Log/D-Log M footage when that profile is eventually built, not assumed to be CQ 20/CRF 20 or CQ 1 by default. What *does* carry over unchanged is the mechanism: `max_quality` is gated only on "is this profile's execution path GPU" (FR-029), not on which color format the profile targets, so any future GPU profile gets the same near-lossless toggle for free — only its specific quality value would need its own validation pass.

## 9. Docker Compose topology: one prod file vs. split dev files

**Decision**: Production gets a single, unqualified `docker-compose.yml` at the repo root with everything baked in — API, worker with the GPU reservation already applied, Redis, frontend — and pointed at the existing external MinIO/S3 via environment variables (no bundled `minio` service). `docker compose up -d` alone is the entire production bring-up. Development instead stays split: `docker-compose.dev.yml` (CPU-profile worker + a bundled `minio`, since dev has no external S3) plus an optional `docker-compose.dev.gpu.yml` override for a developer who happens to have a local GPU and wants to exercise `hlg-gpu` before pushing to the real host.

**Rationale**: These two environments have opposite priorities. Production is fixed and known in advance (the home Ubuntu server, GPU always present, external MinIO always present) — every "override" that split-file Compose exists for (GPU vs. no-GPU, bundled vs. external storage) is a *constant*, not a variable, so collapsing it to one file removes indirection instead of adding it, and directly satisfies the explicit ask for a single `docker compose up`. Development is the opposite: it needs to flex across "no GPU at all" (the common case, testing `hlg-cpu`/`auto` fallback), "local GPU available" (occasionally, testing `hlg-gpu` before a real deploy), and "no external S3" (always, hence bundled MinIO) — keeping those as composable override files avoids maintaining permutations of one bloated file and matches Compose's own override mechanism.

**Alternatives considered**: One file for everything, gated entirely by environment variables/profiles (Compose `profiles:` key) — rejected as needlessly indirect for production, where nothing actually varies; a Compose `profile` flag the operator must remember to pass at every `up` contradicts "just `docker compose up` and it's live." Fully separate files per environment with no shared base (`docker-compose.prod.yml`, `docker-compose.dev-cpu.yml`, `docker-compose.dev-gpu.yml`, all standalone) — rejected for dev specifically, since it would duplicate the non-GPU service definitions across two dev files instead of layering one small override on a shared dev base.

## 10. Testing strategy

**Decision**: Two layers. Fast unit tests (`fakeredis`, `moto` for S3) cover pure logic — profile "auto" resolution, progress-percentage math, job-state transitions — without real infrastructure. Integration/contract tests run against real Redis + MinIO containers (via Docker Compose in CI/dev, or `testcontainers-python`) to validate the actual multipart-upload and job lifecycle end-to-end, since mocking the queue/storage would risk masking real integration bugs (e.g., presigned-URL signature mismatches between MinIO and AWS-shaped requests).

## 11. Local quality-gate enforcement: pre-commit hooks

**Decision**: A `pre-commit` config enforces, on every commit touching `backend/`: `uv run ruff format --check`, `uv run ruff check` (with ruff's `I` rule set enabled so import sorting is covered by the same tool, no separate `isort`), and `uv run ty check` — exactly the three commands already required to be green before any change is considered finished. `frontend/` gets its own equivalent hook (lint/format/type-check via SvelteKit's native toolchain, e.g. `eslint`/`prettier`/`svelte-check`) scoped only to frontend files, so neither side's tooling runs against the other's files.

**Rationale**: `uv`/`ruff`/`ty` are already the fixed, non-negotiable toolchain (project-wide convention, not a per-feature choice) — the only open question was whether they run manually or are enforced automatically, and a local pre-commit hook is the cheapest way to make "ruff check + ruff format + ty check must be green" actually hold, without needing CI (out of scope for v1).

**Alternatives considered**: Enforcing only in CI — rejected since CI/CD is explicitly out of scope for v1, which would leave the rule as an honor system; a custom `uv run` Makefile/script target with no git-hook trigger — rejected because it still relies on a developer remembering to run it, which `pre-commit` removes as a failure mode.

## 12. Profile registry reload timing: restart vs. hot-reload

**Decision**: The profile registry (`backend/src/tonemill/profiles/registry.py`) and each profile's configuration are loaded once when the worker process starts. Adding a new profile or changing an existing one's tunable parameters (contrast, saturation, quality target, etc.) takes effect by restarting the worker process — a `docker compose restart worker` (or a full `up` after an image rebuild) — not via any file-watching or live-reload mechanism. This resolves FR-035 and closes the question originally raised, but left unanswered, during the clarification session (spec.md Clarifications log).

**Rationale**: Nothing in the spec requires a profile change to apply without a restart, and a Docker Compose restart is cheap on this deployment target (a single home server, single/few worker containers) — there's no multi-minute redeploy cost that would make restart-on-change a real burden. Reading configuration once at startup is also simply less code: no file watcher, no cache-invalidation logic, no risk of a worker mid-job picking up a half-written config change. This is the same "keep the foundation simple" reasoning behind the no-database, Redis-only state store decision.

**Alternatives considered**: Live/hot-reload (e.g., watch a config file or poll Redis for profile definition changes) — rejected as unjustified complexity for a use case that never asks for it; the only real cost of the restart-based approach is a few seconds of worker downtime during a profile change, which is acceptable for a single-operator home-lab tool.

## 13. Output color tagging (FR-014): top-level ffmpeg flags are not reliable — validated during implementation

**Finding**: `-color_primaries`/`-color_trc`/`-colorspace`/`-color_range` as top-level ffmpeg *output* options do NOT reliably reach an encoder's actual VUI/bitstream signaling. Validated end-to-end this session against `hlg-cpu`'s real filter chain (libx265, real HLG-tagged source, both a local ffmpeg build and a full-featured `linuxserver/ffmpeg` build): with only the top-level output flags (with or without a matching `-x265-params colorprim=...:transfer=...:colormatrix=...`), `color_space` and `color_range` came through correctly, but `color_primaries` and `color_transfer` silently stayed at the *source's* HLG/BT.2020 values in the encoded output — exactly the FR-014 failure mode the spec warns about ("players may still treat converted output as if it were still HDR/2020").

**Decision**: Tag color *within the filter graph*, not via top-level output flags alone. `zscale`'s own `transfer=`/`primaries=`/`matrix=` parameters (already used by `hlg-cpu` for the tone-map conversion itself) stamp these values onto the frames directly, which *does* reliably propagate to the encoder — confirmed by adding an explicit `setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv` filter stage at the end of `hlg-cpu`'s chain and re-verifying with `ffprobe`: all four fields (`color_primaries`, `color_transfer`, `color_space`, `color_range`) came through as `bt709`/`bt709`/`bt709`/`tv`. `hlg-gpu`'s `libplacebo` filter already tags frames the same way (it's a colorspace-conversion filter, not a bolt-on flag), so it's expected to work by the same mechanism — but this is *unverified on real hardware* (no GPU in the dev/implementation environment) and should be double-checked the same way (encode a real clip, `ffprobe` the four fields) the first time `hlg-gpu` runs against real hardware. Top-level output flags are kept in both profiles' commands as harmless extra insurance, not as the relied-upon mechanism.

**Alternatives considered**: Relying on `-x265-params` alone for libx265 — tested, did not work either (silently ignored in this environment, no error). Relying on top-level flags alone — the original design; disproven by direct testing, which is exactly why this got caught before shipping rather than assumed correct.

## 14. ffmpeg build pin: verified for real (research.md #3 was a placeholder, now resolved)

**Finding**: research.md #3 correctly identified the *risk* (never track BtbN's rolling `latest` tag) but `worker.Dockerfile`'s `FFMPEG_RELEASE_TAG`/`FFMPEG_SHA256` were left as literal `REPLACE_WITH_VERIFIED_*` placeholders, since verifying a real dated release wasn't possible without network access at the time. A user hit this directly: `docker compose build` failed with a `404` on the placeholder URL.

**Decision**: Pinned to a real, verified release: tag `autobuild-2026-08-18-15-03`, asset `ffmpeg-n8.1.2-44-g7c533d0f86-linux64-gpl-8.1.tar.xz`, `sha256=03ccc8a1cb534b97c2bc43f322ddb1b7c23bd325abb7e4c31aa37f4b4c0e648f`. Verified, not assumed: the checksum was taken from that release's own `checksums.sha256` *and* independently re-derived by downloading the asset and hashing it myself (both matched); the binary was run (via a `linux/amd64` container, since this was pinned from an arm64 host) to confirm `ffmpeg -version` reports the n8.1.x branch, `-encoders` lists `hevc_nvenc` and `libx265`, `-filters` lists `libplacebo` and `zscale`, and the build config includes `--enable-vulkan --enable-libshaderc --enable-ffnvcodec --enable-cuda-llvm --enable-libzimg`. Still NOT verified: `hevc_nvenc` actually encoding against real NVIDIA hardware (no GPU in any environment this was validated in) — that remains the same open item research.md #4 already flags for libplacebo/Vulkan.

**Follow-up needed**: this pin will go stale — BtbN's dated releases roll forward, and old ones aren't deleted but the specific commit (`g7c533d0f86`) will eventually fall behind the n8.1 branch's own patch releases. Re-verify (same method: download, hash, run `-version`/`-encoders`/`-filters`, update the Dockerfile's header comment with the new verification date) periodically, not on a fixed schedule tied to this document.

## 15. `uv run` at container runtime silently re-installs the dev dependency group

**Finding**: `uv sync --frozen --no-dev` at Docker build time only affects that one build-time sync. `uv run <cmd>` (used in both Dockerfiles' `CMD`) performs its own sync check by default on every invocation, and without `--no-dev` it reconciles the venv against the *full* lockfile — silently installing the entire dev group (`moto`, `ruff`, `ty`, `numpy`, `cryptography`, `cfn-lint`, ~60MB) into the running container, every single container start. Caught by actually starting the built images and watching `uv run dramatiq ...`/`uv run uvicorn ...` download packages on every `docker run`, not by reading the Dockerfile.

**Decision**: `ENV UV_NO_SYNC=1` in both `api.Dockerfile` and `worker.Dockerfile`, after the build-time `uv sync` steps. This pins runtime `uv run` invocations to the already-built venv as-is — no network calls, no dev-group leakage, and (unlike the pre-fix behavior) actually works in a network-restricted production environment instead of silently depending on internet access at every container start.

**Alternatives considered**: Passing `--no-dev` on every runtime `uv run` invocation instead of the env var — works the same but has to be remembered at every call site (the `CMD` and any future `docker exec ... uv run ...` debugging session); the env var makes the whole image's `uv run` behavior consistent by default instead of relying on every caller getting the flag right.

## 16. Local MinIO needs its bucket created — nothing does that automatically

**Finding**: `docker-compose.dev.yml` bundles a fresh MinIO with no persisted data, and `TONEMILL_S3_BUCKET=tonemill-dev` is just a config value the app assumes exists. Nothing — not MinIO itself, not the app on startup — creates that bucket. A clean `docker compose up` failed the first real request with `botocore.errorfactory.NoSuchBucket`, only surfacing once far enough to actually call the API (later than the ffmpeg pin failure, so it wasn't hit until that was fixed).

**Decision**: Added a `minio-init` one-shot service (image `minio/mc`) to `docker-compose.dev.yml` that runs `mc mb --ignore-existing local/tonemill-dev` and exits; `api`/`worker` depend on it via `condition: service_completed_successfully`. `minio-init` itself depends on `minio` via `condition: service_healthy` (a `healthcheck: mc ready local` was added to the `minio` service) rather than plain `depends_on: minio`, which only waits for the container to *start*, not for MinIO to actually be accepting connections — the first version of this fix raced and failed with `connection refused` before this was added. Verified end-to-end: `docker compose down -v` (wipes the volume) then `docker compose up -d --build` then a real upload -> job -> download cycle through the actual containers, twice (once to catch the race, once to confirm the fix).

**Scope**: dev-only. Production points at an existing, already-provisioned external MinIO instance; bucket creation there is the operator's responsibility (consistent with "S3 object lifecycle management" being explicitly out of scope for v1).

## 17. `auto` resolution wrongly picked hlg-gpu on a host with no real GPU

**Finding**: `detect_gpu_encoder_available` checked whether `hevc_nvenc` appears in `ffmpeg -encoders` output. That only reports what was *compiled in* -- the pinned BtbN GPL build always includes `hevc_nvenc` (research.md #14's build config: `--enable-ffnvcodec --enable-cuda-llvm`), regardless of whether the host it's running on has an actual NVIDIA GPU/driver. Caught live: a real job with `profile: "auto"` resolved to `hlg-gpu` on a host with no real GPU, then failed with a real runtime error ("ffmpeg exited with code 187") once `hevc_nvenc` actually tried to initialize. This directly undermines FR-012's whole point -- the same worker image is supposed to fall back to `hlg-cpu` automatically on a non-GPU host, "no config change."

**Decision**: `detect_gpu_encoder_available` now attempts a trivial one-frame real encode (`-f lavfi -i color=... -frames:v 1 -c:v hevc_nvenc -f null -`) and checks the exit code, instead of grepping `-encoders`. Only a genuine, working hardware initialization reports "available." Verified: against the actual pinned worker image (which does have `hevc_nvenc` compiled in) on a host with no real GPU, the fixed check now correctly returns `False` where the old one returned `True`.

**Alternatives considered**: Checking for `/dev/nvidia*` device nodes or an `nvidia-smi` call instead of exercising ffmpeg directly -- rejected because the actual failure mode is specifically "ffmpeg can't use the encoder," and the most direct test of that claim is asking ffmpeg to use it, not inferring it from adjacent signals that could themselves be wrong (e.g., devices present but driver/container capability misconfigured -- exactly research.md #4's still-open Vulkan/libplacebo risk, which this same reasoning would apply to if it ever needs its own capability check).
