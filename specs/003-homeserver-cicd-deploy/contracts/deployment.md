# Contract: tonemill ↔ homeserver-stacks

The interface between the two repositories this feature touches: what `tonemill`'s CI publishes,
and what `homeserver-stacks/tonemill/` is entitled to assume exists when it runs.

## What `tonemill` CI publishes

| Image | Tags | Platform |
|---|---|---|
| `ghcr.io/nidzhat666/tonemill-api` | `:latest`, `:sha-<short>` | `linux/amd64` |
| `ghcr.io/nidzhat666/tonemill-worker` | `:latest`, `:sha-<short>` | `linux/amd64` |
| `ghcr.io/nidzhat666/tonemill-frontend` | `:latest`, `:sha-<short>` | `linux/amd64` |

`:latest` is only (re-)published from the default branch (`main`). Every push additionally gets
a `:sha-<short>` tag, which never moves once published — the rollback mechanism (research.md #6)
depends on this.

## What `homeserver-stacks/tonemill/docker-compose.yml` MUST provide

- **Network**: all three services join the existing external `nginx-network` (required for
  `frontend` to be reachable via nginx-proxy-manager at `tonemill.nidzh.com`, and for `api`/
  `worker` to reach `minio-server:9000` by container name).
- **Ports**: Neither `api` nor `frontend` publishes a host port. `frontend` gets a stable
  `container_name` (`tonemill-frontend`) so nginx-proxy-manager can target it by name over
  `nginx-network` — the same pattern the `honcho` stack already uses (no `ports:` entry, joins
  `nginx-network` with an alias). `api`'s port staying unpublished is a hard contract, not a
  suggestion (research.md #5 — the shared-login gate depends on it); `frontend` follows the same
  no-published-port convention for consistency with every other NPM-proxied stack in this repo,
  even though its own exposure risk is lower.
- **GPU**: `worker` gets the same GPU reservation shape already used by `cinema-agent`'s
  `jellyfin`/`plex` services on this host (`runtime: nvidia` + `deploy.resources.reservations
  .devices` with `driver: nvidia`, `capabilities: [gpu]`), plus
  `NVIDIA_DRIVER_CAPABILITIES=all` (unchanged from the existing local production compose file —
  libplacebo's Vulkan pass needs `graphics`, not just `compute`/`video`).
- **Environment**: the six variables in data-model.md's table, sourced from a plain `.env` file
  placed directly in `homeserver-stacks/tonemill/` on the server (research.md #8) — not
  committed to git (covered by that repo's `.gitignore`), and not Infisical-managed for now.
- **Redis**: a dedicated `redis` service in the same stack (matching the local production
  compose file) — not shared with any other stack's Redis.

## What this feature does NOT change

- Redis job-state shape, S3 key layout, grading-profile behavior, or any API request/response
  shape (`contracts/api.md` from specs/001 is unchanged).
- The local development compose files (`docker-compose.dev.yml`, `docker-compose.dev.gpu.yml`)
  and the existing build-from-source `docker-compose.yml` at the repo root — those remain the
  local-dev path; the registry-image-based compose file is new and lives only in
  `homeserver-stacks/tonemill/`.
