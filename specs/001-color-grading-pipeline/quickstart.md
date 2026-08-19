# Quickstart: Validating Tonemill End-to-End

This is a runnable validation guide, not an implementation spec — it proves the feature works, referencing [contracts/api.md](./contracts/api.md) and [data-model.md](./data-model.md) rather than duplicating them.

## Prerequisites

- Docker + Docker Compose on the host.
- A source HLG (BT.2020, ARIB STD-B67) 4K test clip (any duration; a short one is fine for a smoke test — use a real 4K60 clip to validate the SC-003 performance claim).
- **GPU path**: an NVIDIA GPU with the NVIDIA Container Toolkit installed and `docker run --gpus all ...` already confirmed working on the host, independent of this project.
- **CPU-only path**: no GPU required at all — this is the expected local-dev configuration.

## 1. Start the stack

```bash
# Production (the home GPU server): everything baked into one file, points at the existing MinIO/S3.
docker compose up -d --build

# Dev, no GPU on this machine (the common case): CPU-profile worker + bundled MinIO.
docker compose -f docker-compose.dev.yml up --build

# Dev, this machine also has a GPU and you want to exercise hlg-gpu before deploying:
docker compose -f docker-compose.dev.yml -f docker-compose.dev.gpu.yml up --build
```

Expected: `api`, `worker`, `redis`, `frontend` containers report healthy (plus `minio` in dev, since production points at the already-existing external MinIO instead). The worker logs which profile(s) it can run — `hlg-gpu` only appears as available if `hevc_nvenc` was detected (FR-012's `auto` resolution).

**GPU-in-container check (research.md item 4 — verify, don't assume)**: on first GPU-host run, confirm the worker container can actually complete a `libplacebo`/Vulkan pass, not just CUDA decode/NVENC encode. If it fails specifically at the tone-map/grade filter stage with a Vulkan/ICD error, adjust `NVIDIA_DRIVER_CAPABILITIES` in `docker-compose.yml` (production) or `docker-compose.dev.gpu.yml` (dev) — start from `all` — before assuming any other cause.

## 2. Upload a source file (via UI or curl)

**Via UI**: open the frontend, select one or more source files, submit.

**Via curl** (mirrors what the frontend does — see [contracts/api.md](./contracts/api.md#uploads-fr-001-fr-030fr-032)):
```bash
curl -X POST $API/uploads -d '{"filename":"clip.mp4","content_type":"video/mp4","size_bytes":<N>}'
# → upload_id, s3_key, part_size_bytes, part_count
# for each part: POST /uploads/{upload_id}/parts/{n} → PUT the chunk to the returned URL, keep the ETag
# POST /uploads/{upload_id}/complete with all {part_number, etag} pairs
```

**Resume check (FR-030, SC-011)**: mid-upload, kill the client (or drop the connection) after only some parts succeeded, then re-run the client. Expected: it re-requests part URLs only for parts not yet confirmed and completes without re-sending already-uploaded bytes.

## 3. Submit a job

```bash
curl -X POST $API/jobs -d '{"s3_key":"<from step 2>","profile":"auto","max_quality":false}'
# → {"job_id": "...", "status": "queued"}
```

## 4. Poll status until done

```bash
curl $API/jobs/<job_id>
```
Expected over time: `status: "queued"` → `status: "running"` with `stage` cycling `downloading` → `processing` (with `progress_pct` climbing, not jumping) → `uploading_result` → `status: "done"` with a populated `result_url` (SC-002, SC-012).

## 5. Download and verify the result

```bash
curl -o result.mp4 "<result_url>"
ffprobe -show_streams result.mp4   # confirm color_primaries=bt709, color_trc=bt709, colorspace=bt709, color_range=tv (FR-014)
```
Play `result.mp4` in standard playback software — expected: correctly exposed, saturated Rec.709 SDR video, not flat/dull, and not misinterpreted as HDR (SC-001, SC-005).

## 6. Validate the secondary flows

- **Multiple files (FR-026, SC-009)**: submit 2+ files together (one deliberately pointing at a bogus `s3_key`); confirm the valid ones complete independently while the bad one reports `failed` with a clear reason, without affecting the others.
- **Explicit GPU profile on a CPU-only host (FR-013)**: on a no-GPU deployment, submit `profile: "hlg-gpu"` explicitly; expect `status: "failed"` with a clear reason, not a silent CPU fallback.
- **`d-log-m` (FR-015)**: submit `profile: "d-log-m"`; expect a submission-time "not implemented" error, no job created.
- **Maximum quality (FR-027–FR-029, SC-010)**: on a GPU host, submit the same clip with `max_quality: true`; expect success with a visibly larger result file and no perceptible quality loss versus the source. On a CPU-only host, expect `status: "failed"` rather than a silent CPU run.
- **Expired job (FR-019)**: query a `job_id` known to have outlived the configured TTL (or lower the TTL for this test); expect `404`, not a stale or default response.

## Success criteria this proves

Covers SC-001, SC-002, SC-003 (re-run with a real 4K60 clip and time it), SC-004 (CPU-only run), SC-005, SC-006, SC-007 (UI-only pass), SC-009, SC-010, SC-011, SC-012.
