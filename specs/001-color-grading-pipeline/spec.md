# Feature Specification: Tonemill — Async Video Color-Grading Pipeline

**Feature Branch**: `001-color-grading-pipeline`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "Build Tonemill — an open-source async GPU video color-grading pipeline. MIT licensed.
Problem
Drone/camera footage shot in HDR (HLG, sometimes PQ/HDR10) looks flat, dull, and desaturated when interpreted naively — the source needs a proper tone-map from its real transfer function down to Rec.709 SDR before it's usable. Doing this by hand with one-off ffmpeg scripts works but doesn't scale: no queue, no progress visibility, no reuse across machines. Tonemill turns this into a real async service: submit a video, pick a grading profile, get back a correctly tone-mapped result, with live status.
Core flow
Client requests a presigned upload URL from the API and PUTs the raw source file directly to S3-compatible storage (never through the API process).
Client submits a job: {s3_key, profile} — profile is a named grading pipeline, or "auto" to let the worker pick the best one it can run.
The API dispatches the job to a queue; a worker picks it up, downloads the source, runs it through ffmpeg per the profile, uploads the result, and reports progress throughout (not just start/done — a live percentage).
Client polls job status: queued | running | done | failed, a progress percentage, and — once done — a presigned URL to download the result.
Grading profiles (the pluggable part)
A profile is a named ffmpeg pipeline (filter chain + encoder settings) for a specific source color format. Two profiles must exist from day one, with these exact validated parameters (do not re-derive/guess — these were benchmarked on real 4K60 HLG footage):
hlg-gpu — HLG (BT.2020, arib-std-b67) → Rec.709 SDR, entirely on an NVIDIA GPU: CUDA decode (-hwaccel cuda), tone-map + grade via libplacebo (Vulkan) in one pass (tonemapping=hable, contrast=1.12, saturation=1.10, dynamic peak detection built in), encode via hevc_nvenc (-rc vbr -cq 20 -b:v 0, not a fixed bitrate). contrast/saturation were not eyeballed — swept programmatically across 4 scenes with different lighting (overcast road, bright sky+sea, dusk with people, white rooftops) and picked as the highest value where the worst scene across all 4 stays under 0.3% highlight/channel clipping (measured via pixel-level analysis of extracted frames, not a visual guess). The bright sky+sea scene was the binding constraint — a single-scene tune had landed on 1.16, which blows out sky/water on other footage. Measured ~65 fps / ~1.08x realtime on 4K60 on an RTX 3080 Ti — i.e. this profile is the intended production path, not just "fast enough."
hlg-cpu — same color transform, CPU-only fallback: zscale (linear→bt709, npl=100) + tonemap=hable + eq(contrast 1.06)/vibrance(0.22)/unsharp grade, libx265 encode (preset medium, crf 20). ~12 fps on 4K60 — slow, this is the dev-machine/no-GPU-host fallback, not meant for production throughput.
profile: "auto" must resolve to hlg-gpu if the worker's ffmpeg build reports hevc_nvenc as an available encoder, else fall back to hlg-cpu — same worker image runs (slowly) on a laptop and (fast) on the GPU host with no config change.
Output color tagging matters: always explicitly tag the output stream as bt709/bt709/bt709/tv (primaries/transfer/colorspace/range) — otherwise players may still treat converted output as if it were still HDR/2020.
A d-log-m profile (LUT-based, for D-Log M source footage) is a known future need — stub it in the profile registry/spec as not-yet-implemented, don't build it now.
Operational constraints (validated this session, must be respected)
Pin the ffmpeg build. The worker must ship a specific tagged ffmpeg release (validated: BtbN's ffmpeg-n8.1-latest-linux64-gpl), never track master/latest. The rolling master build requires NVENC API 13.1 (driver ≥610); the actual target GPU host runs driver 580.x (API 13.0) and fails with Function not implemented against master. This must be documented inline wherever the ffmpeg build is pulled, so a future rebuild doesn't silently regress onto an incompatible build.
GPU concurrency doesn't scale the way you'd expect. Benchmarked: going from 1 to 6 concurrent ffmpeg GPU jobs on one RTX 3080 Ti raised aggregate throughput only ~8% (1.08x → 1.17x realtime) — a single GPU saturates almost immediately on this workload. Worker concurrency must default low (1, at most 2, per GPU) and be configurable — scaling is about adding more GPU hosts, not more threads on one.
libplacebo needs Vulkan exposed in the container, not just CUDA — plain --gpus all covers CUDA/NVENC but the Vulkan ICD needs NVIDIA_DRIVER_CAPABILITIES=all (or at least graphics) on the container. This was validated on the bare host this session but NOT yet inside a container — flag it as something to verify, not assume, when the worker is actually containerized.
Progress must come from ffmpeg -progress pipe:1 (machine-readable key=value stream), not scraped from the human-readable stderr status line — parse out_time_ms against the source's probed duration to get a percentage.
Cosmetic grade knobs (contrast/saturation/etc.) get tuned by measurement, not by eye. The multi-scene clipping-threshold sweep used for hlg-gpu worked well and should be the standard method for tuning any future profile's grade parameters — worth codifying as a repeatable script/tool in the project, not a one-off.
Non-functional / architecture decisions already made
No database. Redis is both the task queue broker and the only state store for job status/progress (with a TTL) — deliberately, to keep the foundation simple.
S3-compatible storage via a client configured with a swappable endpoint URL — target is an existing self-hosted MinIO instance, but must work unmodified against real AWS S3 too.
Stack: Python (uv for env/deps, ruff for lint/format, ty for type checking), FastAPI for the API, a Python task-queue framework backed by Redis for the worker (Dramatiq was the working assumption, open to reconsideration if the spec process surfaces a better fit).
Deployment target: a home Ubuntu 24.04 server running Docker Compose, with an NVIDIA RTX 3080 Ti already set up with the NVIDIA container toolkit (--gpus all confirmed working). The Compose setup must also run (worker falling back to hlg-cpu) on a machine with no GPU at all, for local development.
A minimal status UI (submit a job, watch progress, download the result) is in scope for v1 — it does not need to be fancy, just functional.
Explicitly out of scope for v1
Auth / multi-user, CI/CD image publishing, reverse-proxy/public-domain wiring, the d-log-m profile's actual implementation, S3 object lifecycle management, retry policies beyond whatever the task queue framework does by default."

## Clarifications

### Session 2026-08-19

- Q: When someone wants to add a brand-new grading profile (e.g., for D-Log or D-Log M source footage), should that be doable purely by editing a configuration entry with no code changes, or is it acceptable that adding support for a new source color format still requires writing a small amount of pipeline code, while the cosmetic knobs (contrast, saturation, quality target, etc.) are config-driven? → A: Hybrid (Option B) — adding a new source color format requires a small, self-contained code addition implemented behind a common, SOLID-aligned profile abstraction/interface; each profile's tunable parameters (grade knobs, quality target, encoder settings, etc.) are exposed as configuration that can be changed without touching that profile's pipeline code.
- Q: Does the minimal status UI need its own dedicated application with a server-side layer, or is a simple static page that calls the core job API directly from the browser sufficient? → A: Dedicated web application with its own lightweight backend-for-frontend layer, separate from the core job API (the specific frontend framework is a planning-phase/implementation decision, not a functional requirement).
- Q: Can a user submit more than one source file at a time, and if so how are the files tracked? → A: Yes — the UI supports selecting and submitting multiple files in one session; each file is uploaded and becomes its own independent job, tracked and reported separately, so one file's failure does not block or fail the others.
- Q: Is authentication or multi-user access control needed for v1? → A: No — reaffirms the existing assumption of a single-user, trusted-network v1 deployment with no auth; to be addressed later.
- Q: Should an optional "compress as much as possible with zero quality loss" job option mean true bit-exact lossless encoding, or a near-lossless high-quality encode, given those two goals conflict (true lossless produces larger files, not smaller)? → A: Near-lossless GPU encode — an optional per-job "maximum quality" flag switches the GPU-accelerated encoder to its lowest usable quality-value setting (far beyond the default CQ 20), giving effectively imperceptible quality loss while still compressing meaningfully; this is GPU-only in v1, does not change the profile's tone-mapping/grading parameters, and accepts a larger output file and longer encode time in exchange (explicitly acceptable per user: "time is not important").
- Q: For the "durable, reliable, and fast" upload requirement on large 4K60 source files, should the system support resumable, chunked (multipart) upload, or is a single simple presigned upload sufficient for v1? → A: Resumable multipart upload — the client initiates a multipart upload, uploads fixed-size parts directly to storage (optionally in parallel for speed) via per-part presigned URLs, can resume by re-sending only incomplete parts after an interruption, and completes the upload via a final assemble call; the upload API's role is limited to minting/relaying create/complete/abort calls, bytes still flow client→storage directly (no change to the no-proxy-through-API constraint).
- Q: Beyond status and progress percentage, should the backend also report which coarse processing stage a running job is in, or is percentage alone transparent enough? → A: Add a lightweight "stage" field alongside status/percentage, reflecting the worker's natural control-flow steps: `downloading` (source from storage) → `processing` (running the grading pipeline, where the existing percentage applies) → `uploading_result` (result to storage) → `done`/`failed`.
- Q: FR-030 requires resuming an interrupted upload by sending only the not-yet-received parts, but nothing lets a client discover which parts already succeeded if its own local upload-progress record is lost (e.g., browser closed, resumed on a different device) — should the system expose that? → A: Yes — the system MUST let a client query which parts of an in-progress upload have already been received, so resume never depends solely on client-side memory that can be lost. (Resolves readiness.md CHK002/CHK021.)
- Q: Is "a common configuration surface" (FR-024) precise enough to know whether changing a profile's tunable parameters requires restarting the worker, or must apply live without a restart? → A: Redeploy/restart-time — the profile registry and its configuration are read once at worker process startup; changing or adding a profile's configuration takes effect via restarting the worker process (a cheap operation on this Docker Compose deployment), not via a live/hot-reload mechanism. No requirement anywhere in scope needs live reload, and adding one would be unjustified complexity for a single/few-host home-lab deployment. (Resolves readiness.md CHK010/CHK034; this was the deferred question from the original clarification session.)
- Q: Does FR-017's "provide a repeatable, measurement-based method" require a shippable tool/script as a v1 deliverable, or only that the method be followed by hand whenever parameters are tuned? → A: Shippable tool — the original description already called this "worth codifying as a repeatable script/tool in the project, not a one-off," so FR-017 is amended to require it be shipped as a runnable tool, not just documented as a process. (Resolves readiness.md CHK009; also closes the zero-task-coverage gap `/speckit-analyze` found for FR-017.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit footage and retrieve a correctly graded result (Priority: P1)

A user has a raw HDR (HLG) clip that looks flat and desaturated when played naively. They upload it, submit a grading job against it, watch its progress advance from queued through running to done, and download a Rec.709 SDR result that plays correctly — with proper contrast and color — on standard playback software.

**Why this priority**: This is the entire reason Tonemill exists. Without this flow working end-to-end, there is no product. Every other capability supports or refines this one.

**Independent Test**: Can be fully tested by requesting an upload URL, uploading a source HLG clip, submitting a job with an explicit profile, polling until status is `done`, and downloading and verifying the result is Rec.709-tagged SDR video with visibly correct exposure/color (not washed out, not blown out, not still tagged as HDR).

**Acceptance Scenarios**:

1. **Given** a raw HLG source file has been uploaded to storage, **When** the user submits a job referencing that file and an explicit grading profile, **Then** the job is accepted and immediately reports status `queued`.
2. **Given** a queued job is picked up for processing, **When** processing is underway, **Then** polling the job repeatedly shows status `running`, a current stage (downloading source / processing / uploading result), and a progress percentage that increases over time (not a single jump from 0 to 100).
3. **Given** a job completes processing successfully, **When** the user polls its status, **Then** the response is `done` together with a URL the user can use to download the finished video.
4. **Given** a completed job's result is downloaded, **When** the file is inspected or played, **Then** it is standard Rec.709 SDR video (not still tagged or behaving as HDR/wide-gamut) with visibly corrected exposure and color rather than the flat, dull appearance of the naively-interpreted source.
5. **Given** a job fails during processing (e.g., corrupt or unreadable source), **When** the user polls its status, **Then** the response is `failed` with a reason the user can understand, rather than the job silently disappearing or hanging indefinitely.

---

### User Story 2 - Get a working result regardless of which machine is running the worker (Priority: P2)

A user (or operator) runs the same worker deployment on two different machines — one with a capable GPU, one without — without changing any configuration. On both machines, submitting a job with profile `auto` produces a correct result: fast on the GPU machine, slower but equally correct on the machine without one.

**Why this priority**: This is what makes Tonemill reusable across machines instead of a single hand-tuned script tied to one box — a core stated goal. It directly enables local development and low-cost fallback without operator intervention.

**Independent Test**: Can be tested by submitting a job with `profile: "auto"` on a GPU-capable deployment and confirming it resolves to and completes via the GPU-accelerated path, then repeating the same submission unmodified on a deployment with no usable GPU and confirming it resolves to and completes via the non-GPU path, with both producing a correctly graded result.

**Acceptance Scenarios**:

1. **Given** a worker deployment with a working GPU-accelerated encoding path available, **When** a job is submitted with `profile: "auto"`, **Then** the job is processed using the GPU-accelerated profile.
2. **Given** a worker deployment where GPU-accelerated encoding is not available, **When** a job is submitted with `profile: "auto"`, **Then** the job is processed using the non-GPU fallback profile and still completes successfully with a correctly graded result.
3. **Given** the same worker deployment artifact is used, **When** moved between a GPU-capable machine and a machine without a GPU, **Then** no configuration change is required for `auto` jobs to complete correctly on either.

---

### User Story 3 - Manage jobs without touching the API directly (Priority: P3)

A user who doesn't want to script HTTP calls opens a simple page, picks one or more files, submits them for grading, watches each one's upload and processing progress update live, and downloads each result as it becomes ready.

**Why this priority**: Rounds out v1 into something usable end-to-end by a person, not just a client script — explicitly called out as in-scope, but the underlying job flow (Story 1) delivers value on its own even without this UI.

**Independent Test**: Can be fully tested by using only the UI — no direct API calls — to go from "have one or more source files on disk" to "have downloaded each graded result," observing per-file upload and processing progress update while jobs run.

**Acceptance Scenarios**:

1. **Given** a user has a source video file, **When** they use the UI to submit it for grading, **Then** the file is uploaded and a job is created without the user needing to interact with the API directly.
2. **Given** a job is running, **When** the user is viewing it in the UI, **Then** the displayed progress updates over time without requiring a manual page reload.
3. **Given** a job has completed, **When** the user is viewing it in the UI, **Then** a download link/action for the result is presented.
4. **Given** a user selects multiple source files at once, **When** they submit them for grading, **Then** each file is uploaded and tracked as its own independent job, individually visible in the UI (own status, own progress, own download link).
5. **Given** multiple files were submitted together, **When** one file's upload or processing fails, **Then** the other files' jobs continue and complete independently, unaffected by that failure.

---

### User Story 4 - Opt into maximum-quality output when file size and time don't matter (Priority: P4)

A user grading a clip they care a lot about checks a "maximum quality" box before submitting. They're fine waiting longer and getting a bigger file in exchange for output that's effectively indistinguishable in quality from the source.

**Why this priority**: A genuine but secondary need — the default profiles already produce a good result; this serves the subset of jobs where quality (not turnaround time or file size) is the priority. The core flow (Story 1) is fully valuable without it.

**Independent Test**: Can be tested by submitting the same source file twice — once with the option unchecked, once checked — and confirming the checked run produces a visibly higher-quality (and larger) result, using the GPU path, with no change to job status/progress/download mechanics.

**Acceptance Scenarios**:

1. **Given** a user is submitting a job, **When** they check the "maximum quality" option, **Then** the job is processed via the GPU-accelerated profile using a near-lossless encoder quality setting instead of the profile's default quality target.
2. **Given** the "maximum quality" option was selected, **When** the result is compared to the same source graded without it, **Then** the result shows no perceptible quality loss from the source, at the cost of a larger file and longer processing time.
3. **Given** the "maximum quality" option is selected but only the CPU-only profile is available (no usable GPU), **When** the job is submitted, **Then** the job fails with a clear reason rather than silently running at default quality or silently ignoring the option.

---

### Edge Cases

- What happens when a job is submitted referencing an `s3_key` that was never actually uploaded, or the upload failed/was never completed (e.g., an abandoned multipart upload with some parts missing)? Job should fail with a clear reason rather than hanging in `queued`/`running` indefinitely.
- What happens when a client abandons an in-progress multipart upload (stops sending parts, never completes it)? The system should be able to abort and clean up the incomplete upload rather than leaving it dangling in storage indefinitely.
- What happens when a client resumes an upload with no local record of which parts already succeeded (e.g., a new browser session, or a different device)? It MUST be able to query the already-received parts from the system rather than only trusting its own possibly-lost state (FR-034).
- What happens when a job explicitly requests `profile: "hlg-gpu"` on a worker that has no usable GPU path? This should fail clearly and immediately rather than silently falling back — automatic fallback only applies to `profile: "auto"`.
- What happens when a job is submitted with `profile: "d-log-m"` (registered but not implemented)? The system should reject it with a clear "not yet implemented" response rather than accepting it and getting stuck.
- What happens when a job is submitted with an unrecognized profile name entirely? Rejected at submission time with a clear error, not accepted into the queue.
- What happens when the source file is not actually HLG/HDR (e.g., already SDR, or an unsupported codec/container)? The job should fail with a diagnosable reason rather than producing a silently wrong or corrupted result.
- What happens when a worker process crashes or is killed mid-job? The job should not remain stuck in `running` forever from the client's perspective (bounded by status retention).
- What happens when a client polls a job after its status/progress record has expired (retention window elapsed)? The client should receive an unambiguous "unknown/expired job" response rather than a misleading default.
- What happens when more jobs are submitted than the worker(s) can run concurrently? Excess jobs remain `queued` and are processed in turn rather than overwhelming the processing host.
- What happens when a client tries to download a result before the job reaches `done`? No valid download URL should be available yet.
- What happens when a user submits multiple files at once and one file's upload or job fails? That file's job reports `failed` with its own reason; the other files' jobs are unaffected and continue to completion independently.
- What happens when a job requests the "maximum quality" option but resolves (explicitly or via `auto`) to the CPU-only profile? The job fails with a clear reason — the option is GPU-only in v1 and MUST NOT be silently downgraded or ignored.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let a client initiate a resumable, multi-part upload for a source video — obtaining a time-limited upload URL per part — and upload the raw file directly to object storage in parts, without the file passing through the API process itself.
- **FR-030**: System MUST let a client resume an interrupted upload by uploading only the parts not yet successfully received, rather than restarting the whole file from the beginning.
- **FR-031**: System MUST let a client upload multiple parts of the same file concurrently, so upload speed is not limited to a single sequential transfer.
- **FR-032**: System MUST let a client finalize an upload once all parts are received, assembling them into the complete source object before it becomes eligible for job submission; and MUST let a client (or the system) abort an abandoned, never-completed upload so it does not linger indefinitely.
- **FR-034**: System MUST let a client query which parts of an in-progress upload have already been successfully received, so that resuming an interrupted upload (FR-030) never depends solely on client-side state that may itself have been lost (e.g., the browser was closed, or the upload is resumed from a different device/session).
- **FR-002**: System MUST let a client submit a grading job by referencing an already-uploaded source object and a named grading profile (or `auto`).
- **FR-003**: System MUST process submitted jobs asynchronously through a queue — job submission returns immediately and does not block on processing completion.
- **FR-004**: System MUST expose, for any submitted job, a current status of exactly one of: `queued`, `running`, `done`, or `failed`.
- **FR-005**: System MUST report a numeric progress percentage for a job while it is `running`, and that percentage MUST advance over the course of processing (derived from actual elapsed processing time against the source's known duration), not merely jump from 0% to 100%.
- **FR-033**: While a job is `running`, system MUST additionally report which coarse stage it is currently in — downloading its source from storage, actively processing (grading pipeline running, where FR-005's percentage applies), or uploading its result to storage — so a client can show what is actually happening, not just an overall percentage.
- **FR-006**: System MUST provide, once a job reaches `done`, a time-limited URL the client can use to download the graded result directly from object storage.
- **FR-007**: System MUST provide, when a job reaches `failed`, a human-readable reason describing why it failed.
- **FR-008**: System MUST support at least two named grading profiles at launch — a GPU-accelerated profile and a CPU-only fallback profile — both performing the same HLG (BT.2020, ARIB STD-B67) → Rec.709 SDR color transform, differing only in execution path and performance. These are the first two entries in a profile registry that is not limited to HLG sources (see FR-023–FR-025).
- **FR-009**: The GPU-accelerated profile MUST decode and tone-map/grade the source without leaving the GPU, apply the Hable tone-mapping operator with a contrast of 1.12 and saturation of 1.10 with dynamic highlight/peak detection, and encode using a quality-targeted (not fixed-bitrate) GPU hardware encoder at a quality setting equivalent to CQ 20.
- **FR-010**: The CPU-only fallback profile MUST perform the equivalent linear→Rec.709 color transform (100-nit reference) with the Hable tone-mapping operator, followed by a grade of contrast 1.06 and a vibrance boost of 0.22 with sharpening, encoded in software at a quality setting equivalent to CRF 20 (medium preset).
- **FR-011**: The contrast and saturation/vibrance values used by each profile MUST be exactly the validated values specified in FR-009/FR-010 and MUST NOT be re-derived, re-tuned by visual judgment, or altered without re-running the same measurement-based validation method (see FR-017).
- **FR-012**: When a job specifies `profile: "auto"`, the system MUST resolve it to the GPU-accelerated profile if the processing host reports a working GPU hardware encoding path, and to the CPU-only fallback profile otherwise — with no configuration change required between hosts.
- **FR-013**: When a job explicitly specifies the GPU-accelerated profile by name on a host where the GPU encoding path is not available, the system MUST fail the job with a clear reason rather than silently substituting the CPU fallback (automatic substitution applies only to `auto`).
- **FR-014**: System MUST explicitly tag the output video of every profile with standard-dynamic-range Rec.709 color metadata (matching primaries, transfer function, and matrix coefficients, standard "tv" signal range), regardless of which profile produced it, so downstream players do not misinterpret the result as still HDR or wide-gamut.
- **FR-015**: System MUST recognize a `d-log-m` profile name as a registered-but-not-yet-implemented profile: jobs submitted against it MUST be rejected with a clear "not implemented" response rather than accepted into the queue.
- **FR-016**: System MUST reject job submissions that reference an unrecognized profile name at submission time, rather than accepting them and failing later.
- **FR-017**: System MUST provide a repeatable, measurement-based method for validating or re-tuning any grading profile's cosmetic parameters (not visual/manual judgment), based on checking worst-case highlight/channel clipping across multiple differently-lit reference scenes against a defined threshold. This method MUST be shipped as a runnable tool/script in the project (not only documented as a process), so re-tuning an existing profile or validating a new one doesn't depend on re-deriving the measurement approach from scratch each time.
- **FR-018**: System MUST limit how many jobs a single GPU-capable processing host will run at the same time to a small, low default (no more than 2), reflecting that this workload does not meaningfully benefit from higher per-GPU concurrency; this limit MUST be configurable by an operator.
- **FR-019**: System MUST retain each job's status/progress/result information for a bounded period after creation rather than indefinitely, and MUST return an unambiguous "not found / expired" response when a client asks about a job outside that window.
- **FR-020**: System MUST provide a minimal interface allowing a user to submit a source file for grading, observe its progress while running, and download the result once done, without needing to issue direct API calls.
- **FR-026**: System MUST let a user submit multiple source files in one session; each submitted file MUST be uploaded and tracked as its own independent job, with its own status, progress, result, and failure reason, so that one file's failure does not block, fail, or delay any other file's job.
- **FR-027**: System MUST let a client optionally request a "maximum quality" encode for a job at submission time (e.g., via a checkbox), independent of which grading profile is used.
- **FR-028**: When "maximum quality" is requested, the system MUST use the GPU-accelerated encoder's near-lossless quality setting in place of the profile's default quality target (FR-009), within the same single job and the same single decode/tone-map/grade/encode pass already used for that profile — NOT as a separate follow-up job or a second encode pass over an already-graded/already-encoded output (which would compound quality loss instead of preserving it). The profile's tone-mapping and grading parameters (FR-009–FR-011) remain unchanged; only the encoder's quality setting differs.
- **FR-029**: The "maximum quality" option MUST require the GPU-accelerated execution path; a job that requests it but resolves (explicitly or via `auto`) to the CPU-only profile MUST fail with a clear reason rather than silently running at default quality or on the CPU path.
- **FR-021**: System MUST work against S3-compatible object storage regardless of provider (self-hosted or public cloud) without requiring different behavior or code paths per provider.
- **FR-022**: System MUST be usable, without modification, on a processing host that has no usable GPU at all — all `auto` and CPU-profile jobs MUST still complete correctly on such a host, only slower.
- **FR-023**: The set of grading profiles MUST be a registry, not a fixed pair — the system MUST be designed so that support for an additional source color format (e.g., D-Log, D-Log M) can be added as a new, self-contained profile entry without changing the job submission, queueing, status, or storage behavior described elsewhere in this spec.
- **FR-024**: Each grading profile's tunable parameters (e.g., grade knobs such as contrast/saturation, quality/encoder target) MUST be exposed through a common configuration surface shared by every profile, so that adjusting those values for an existing profile does not require changing that profile's underlying pipeline implementation.
- **FR-025**: Adding a new source color format's grading pipeline MAY require a dedicated, self-contained implementation for that format, but it MUST conform to the same common profile abstraction used by `hlg-gpu` and `hlg-cpu` (same registration, naming, status-reporting, and output color-tagging behavior from FR-014/FR-015/FR-016), so new profiles behave consistently with existing ones from the client's perspective.
- **FR-035**: The profile registry and each profile's configuration (FR-024) MUST be read once when the worker process starts; adding a profile or changing an existing profile's tunable configuration MUST take effect by restarting the worker process, not via a live/hot-reload mechanism at runtime. This is a deliberate v1 simplicity choice, not a technical ceiling — nothing in scope requires configuration changes to apply without a restart.

### Key Entities

- **Job**: A single request to grade one source video. Attributes: unique identifier, reference to the source object, requested profile name, resolved profile actually used (relevant when `auto` was requested), whether "maximum quality" was requested, current status (`queued`/`running`/`done`/`failed`), current stage while running (`downloading`/`processing`/`uploading_result`), progress percentage, reference to the result object (once done), failure reason (once failed), creation time, and the point at which its record expires.
- **Upload Session**: A single client's in-progress or completed multi-part upload of one source file to object storage. Attributes: target object key, upload identifier, the set of parts received so far (with per-part confirmation), and completion state (in-progress, completed, aborted). Exists prior to and independently of any Job — a Job can only be submitted once its source's upload session has completed.
- **Grading Profile**: A named, versioned color-grading pipeline definition for a specific source color format, and one entry in an extensible profile registry (not limited to HLG). Attributes: name, source color format it targets (e.g., HLG/BT.2020), execution path (GPU-accelerated vs. CPU-only), the specific validated grading parameters it applies (tone-mapping operator, contrast, saturation/vibrance) — exposed as adjustable configuration rather than hardcoded within the pipeline implementation, output color tagging (always Rec.709 SDR, "tv" range), implementation status (implemented vs. stubbed/not-yet-implemented — e.g., `d-log-m`), and known relative performance characteristics (validated realtime-factor/frame-rate on reference footage, used to set expectations rather than as a runtime guarantee).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from "have a raw HDR clip that looks flat/dull" to "have a downloaded, correctly-graded Rec.709 SDR result" using only upload, submit, poll/watch, and download actions — no manual color-grading commands or scripts required.
- **SC-002**: While a job is running, a user watching its status sees the progress indicator advance at least several times before completion (not a single jump from start to finish), giving a continuous sense of how much work remains.
- **SC-003**: On the GPU-accelerated path, a 4K60 source clip is processed at at or near real-time speed (within the validated ~1.08x-realtime benchmark), confirming the GPU path is production-viable rather than merely functional.
- **SC-004**: On a host with no usable GPU, the same job submission (via `auto`) still completes successfully and unattended, producing an equally correctly-graded result, just at markedly lower throughput than the GPU path.
- **SC-005**: 100% of results produced by any implemented profile play back as standard SDR video on common playback software — none are misinterpreted as HDR/wide-gamut content by the player.
- **SC-006**: 100% of jobs that fail (bad source, missing upload, unavailable requested profile, unimplemented profile) surface a clear, specific reason to the client rather than hanging or returning an ambiguous result.
- **SC-007**: A user can complete an entire submit-watch-download cycle for a job using only the minimal status interface, without ever needing to construct an API request by hand.
- **SC-008**: Running multiple jobs at once against a single GPU host does not degrade individual job correctness, and aggregate throughput behaves consistently with the validated finding that a single GPU saturates quickly (i.e., the system does not attempt unbounded concurrency per GPU by default).
- **SC-009**: A user submitting several files together can see each file's own upload/processing outcome and one file failing never prevents the others from completing successfully.
- **SC-010**: A user who opts into "maximum quality" gets a result with no perceptible quality loss compared to the source, and understands upfront that this trades off a larger file and longer processing time.
- **SC-011**: An upload of a large (multi-gigabyte) source file that is interrupted partway (e.g., a dropped connection) can be resumed and completed without re-transferring the portion already uploaded.
- **SC-012**: While a job is running, a user can tell at a glance whether it is currently fetching the source, actively grading it, or delivering the result — not just an unlabeled percentage.

## Assumptions

- v1 is single-user / trusted-network deployment: no authentication or per-user access control is required, consistent with the explicit out-of-scope note on auth/multi-user (reaffirmed and unchanged as of this session).
- The minimal UI (FR-020, FR-026) is built as its own dedicated web application with a lightweight server-side backend-for-frontend layer, rather than a static page calling the core job API directly from the browser; the specific frontend framework/toolkit is an implementation choice for the planning phase, not a functional requirement.
- Only HLG (BT.2020, ARIB STD-B67) source footage is handled by an implemented profile in v1. PQ/HDR10 is mentioned in the problem statement as part of the broader real-world problem but is not covered by a v1 profile; a job against PQ/HDR10 source without an appropriate profile is expected to be handled the same as any mismatched/unsupported source (fails with a clear reason).
- Job status/progress/result metadata retention uses a bounded, operator-configurable time window ("TTL") rather than indefinite storage; the exact default duration is an implementation decision left to planning, not a user-facing scope question.
- Clients are responsible for polling job status at their own interval; no push notifications or persistent live-update connection is required for v1 beyond what the minimal UI needs to appear "live" to a human watching it.
- Each job produces exactly one result file at one quality/resolution; producing multiple output variants per job is out of scope for v1.
- The "maximum quality" option (FR-027–FR-029) is GPU-only in v1: it swaps the GPU encoder's quality-value setting for a near-lossless one but does not introduce a CPU-path equivalent, does not change tone-mapping/grading math, and is not true bit-exact lossless (which would produce larger files than the default and would not serve the "compress as much as possible" goal). Processing-time success criteria (e.g., SC-003) do not apply when this option is used, since slower processing is an explicitly accepted tradeoff.
- The GPU-accelerated profile's specific numeric grading parameters (contrast 1.12, saturation 1.10, quality level equivalent to CQ 20) and the CPU profile's (contrast 1.06, vibrance 0.22, quality level equivalent to CRF 20) were already validated this session via multi-scene, clipping-threshold measurement and MUST be carried into implementation unchanged rather than re-derived.
- The specific processing runtime build used by the worker must be a pinned, known-compatible release rather than a rolling "latest" build, because a rolling build was confirmed incompatible with the actual target GPU host's driver during this session's validation; this compatibility constraint must be preserved and documented at whatever point the runtime build is selected/pulled during implementation.
- A single GPU host should default to running very few jobs concurrently (no more than 2, one by default) because concurrency was measured to yield negligible additional throughput on this workload; scaling out is expected to mean adding more GPU-equipped hosts, not raising per-host concurrency.
- Exposing the GPU's graphics/shader capability (not only its compute/decode-encode capability) to wherever the GPU-accelerated profile actually executes has only been confirmed on a bare host so far, not inside an isolated/containerized environment — this needs to be verified, not assumed, once the worker is packaged for deployment.
- Any future grading profile's cosmetic parameters (contrast, saturation, and similar) should be validated using the same repeatable, multi-scene, clipping-threshold measurement approach used for the GPU profile in this session, rather than tuned by visual judgment.
- The `d-log-m` profile is a known, named future need and must exist as a recognized-but-not-implemented entry so clients get a clear "not implemented" response, but its actual grading pipeline is explicitly out of scope for v1. The profile registry/abstraction itself (FR-023–FR-025) is in scope for v1 so that D-Log, D-Log M, and similar formats can be added later as self-contained profiles without reworking the job/queue/API layer.
- Out of scope for v1, per explicit direction: authentication/multi-user support, publishing/distributing build artifacts, exposing the service outside the local network, the `d-log-m` profile's real implementation, lifecycle management of stored objects, and any job-retry behavior beyond whatever the underlying queueing mechanism does automatically.
