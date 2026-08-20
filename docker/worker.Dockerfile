# Tonemill worker — runs ffmpeg per grading profile, on GPU (hlg-gpu) or CPU (hlg-cpu).
#
# ==========================================================================================
# FFMPEG BUILD PIN — DO NOT TRACK "latest" / master. Read this before touching FFMPEG_*.
#
# The worker MUST ship the validated BtbN build: ffmpeg-n8.1-latest-linux64-gpl (gpl build,
# n8.1 branch). BtbN's rolling "latest" release tag is continuously overwritten with new
# builds from ffmpeg master, and current master requires NVENC API >=13.1 (driver >=610).
# The validated production GPU host runs driver 580.x (NVENC API 13.0) and fails against a
# master-tracking build with "Function not implemented" at the hevc_nvenc encode step.
#
# FFMPEG_RELEASE_TAG below MUST point at a specific, dated BtbN autobuild release (never the
# "latest" alias, which silently drifts) whose FFMPEG_ASSET is still an n8.1-branch GPL
# linux64 build. Verify against https://github.com/BtbN/FFmpeg-Builds/releases before changing
# these values: download the asset, confirm `ffmpeg -version` reports the n8.1.x branch and
# `-encoders`/`-filters` list hevc_nvenc and libplacebo, and re-validate hevc_nvenc against the
# actual GPU host's driver after any change (this pin was verified for build presence/checksum
# only -- see below -- not by running hevc_nvenc against real NVIDIA hardware). FFMPEG_SHA256
# pins the asset's checksum, taken from that release's own checksums.sha256 and independently
# re-verified by downloading the asset and hashing it, so a corrupted/substituted download
# fails the build instead of shipping silently.
#
# Pinned 2026-08-19: tag autobuild-2026-08-18-15-03, asset
# ffmpeg-n8.1.2-44-g7c533d0f86-linux64-gpl-8.1.tar.xz. Confirmed (via a linux/amd64 container,
# since this was pinned from a non-Linux host): `ffmpeg -version` reports
# "n8.1.2-44-g7c533d0f86-20260818"; `-encoders` lists hevc_nvenc and libx265; `-filters` lists
# libplacebo and zscale; build config includes --enable-vulkan --enable-libshaderc
# --enable-ffnvcodec --enable-cuda-llvm --enable-libzimg.
# ==========================================================================================
ARG FFMPEG_RELEASE_TAG=autobuild-2026-08-18-15-03
ARG FFMPEG_ASSET=ffmpeg-n8.1.2-44-g7c533d0f86-linux64-gpl-8.1.tar.xz
ARG FFMPEG_SHA256=03ccc8a1cb534b97c2bc43f322ddb1b7c23bd325abb7e4c31aa37f4b4c0e648f

# --platform=linux/amd64 is pinned, not host-default: BtbN's ffmpeg-n8.1 GPL asset is a
# linux64 (x86-64) binary only. The real production target (an x86-64 Ubuntu GPU host) needs
# this anyway; on an arm64 dev machine (e.g. Apple Silicon) it makes the image build/run
# under QEMU emulation instead of failing outright with "Dynamic loader not found" -- slower,
# but the CPU fallback path is already documented as slow-by-design, not a throughput target.
FROM --platform=linux/amd64 python:3.12-slim AS base

ARG FFMPEG_RELEASE_TAG
ARG FFMPEG_ASSET
ARG FFMPEG_SHA256

# libvulkan1: the generic Vulkan loader ffmpeg/libplacebo dynamically link against at
# runtime. libx11-6/libxext6: the NVIDIA driver's GLX-backed Vulkan ICD (libGLX_nvidia.so.0)
# links against X11 client libraries even for this headless, no-display encode path. The
# GLX ICD itself still fails to initialize in this container regardless (research.md #11) --
# fixed by switching to the EGL-backed ICD at container start (worker-entrypoint.sh,
# research.md #12), not by these packages -- but libvulkan1 (the loader itself) is still
# required either way, and libx11-6/libxext6 are cheap enough to keep rather than conditionally
# omit.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl xz-utils ca-certificates libvulkan1 libx11-6 libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Pinned ffmpeg — see the header comment above before ever changing FFMPEG_RELEASE_TAG.
RUN curl -fL -o /tmp/ffmpeg.tar.xz \
      "https://github.com/BtbN/FFmpeg-Builds/releases/download/${FFMPEG_RELEASE_TAG}/${FFMPEG_ASSET}" \
    && echo "${FFMPEG_SHA256}  /tmp/ffmpeg.tar.xz" | sha256sum -c - \
    && mkdir -p /opt/ffmpeg \
    && tar -xJf /tmp/ffmpeg.tar.xz -C /opt/ffmpeg --strip-components=1 \
    && rm /tmp/ffmpeg.tar.xz
ENV PATH="/opt/ffmpeg/bin:${PATH}"

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/src ./src
RUN uv sync --frozen --no-dev

# uv run re-syncs the venv against the full lockfile (dev group included) by default on
# every invocation, undoing the --no-dev build above and re-downloading it at every
# container start. UV_NO_SYNC pins runtime `uv run` to the already-built venv as-is.
ENV UV_NO_SYNC=1

COPY docker/worker-entrypoint.sh /usr/local/bin/worker-entrypoint.sh
RUN chmod +x /usr/local/bin/worker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/worker-entrypoint.sh"]

# GPU concurrency default (1, max 2 per GPU per FR-018) is set via TONEMILL_GPU_CONCURRENCY
# at runtime and passed straight to Dramatiq's own process pool (see config.py) -- not
# implemented as manual threading in application code.
CMD ["sh", "-c", "uv run dramatiq tonemill.worker.actors --processes ${TONEMILL_GPU_CONCURRENCY:-1} --threads 1"]
