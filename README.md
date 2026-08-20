# Tonemill

Open-source async GPU video color-grading pipeline. Submit HDR (HLG) footage, pick a
grading profile (or let it auto-pick the best one available), watch live progress, download
a correctly tone-mapped Rec.709 SDR result. MIT licensed.

Also has a dashboard for managing submitted jobs and a video library for organizing
completed results into folders — see
[`specs/004-task-dashboard-video-library/`](specs/004-task-dashboard-video-library/).

Full spec, design decisions, and the end-to-end validation script live in
[`specs/001-color-grading-pipeline/`](specs/001-color-grading-pipeline/) — see
[`quickstart.md`](specs/001-color-grading-pipeline/quickstart.md) for the authoritative
walkthrough. This README is the short version.

## Running it

Both compose files now bundle a `mongo` service alongside Redis — no separate setup needed;
it's the durable store behind the video library, folder organization, and duplicate-upload
detection (Redis stays the ephemeral job/progress store it always was).

**Production** (the home GPU server — driver 580.x, NVIDIA Container Toolkit already
working, existing external MinIO/S3): everything in one file, no `-f` flags needed.

```bash
cp .env.example .env   # fill in TONEMILL_S3_* for your existing MinIO/S3
docker compose up -d --build
```

**Local dev, no GPU** (the common case — exercises `hlg-cpu`/`auto` fallback, bundles its
own MinIO since dev has no external S3):

```bash
docker compose -f docker-compose.dev.yml up --build
```

**Local dev with a GPU**, to exercise `hlg-gpu` before deploying:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.dev.gpu.yml up --build
```

Frontend at `http://localhost:3000`, API at `http://localhost:8000` (docs at `/docs`).

⚠️ Before a real production build: `docker/worker.Dockerfile`'s `FFMPEG_RELEASE_TAG`/
`FFMPEG_SHA256` build args are placeholders — pin them to a verified dated BtbN autobuild
release per the comment at the top of that file. Never track BtbN's rolling `latest` tag
(see `research.md` #3 for why).

## Project layout

- `backend/src/tonemill/` — FastAPI API + Dramatiq worker (one Python package; see
  `profiles/` for the pluggable grading-profile abstraction, FR-023–FR-025)
- `frontend/` — SvelteKit UI + backend-for-frontend proxy
- `docker/` + root `docker-compose*.yml` — container definitions

## Development workflow

Backend (`backend/`): `uv` for everything, `ruff` for lint+format (import sorting included
via its `I` rule set), `ty` for types.

```bash
cd backend
uv sync
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

Frontend (`frontend/`): `npm run lint`, `npm run check` (svelte-check), `npm run test:unit`.

A `pre-commit` config at the repo root runs the backend and frontend checks above,
scoped to each half of the repo, on every commit (`pre-commit install` to enable it).

## Tuning a grading profile

Cosmetic grade parameters (contrast, saturation, quality target) are never eyeballed —
they're validated by sweeping candidate values across multiple differently-lit reference
scenes and picking the highest value that keeps the worst scene under a highlight/channel
clipping threshold. `backend/src/tonemill/tools/tune_profile.py` implements this method
(FR-017); run it before changing any profile's tuned values.
