# Feature Specification: Homeserver CI/CD & GPU Deployment

**Feature Branch**: `[003-homeserver-cicd-deploy]`

**Created**: 2026-08-20

**Status**: Draft

**Input**: User description: "Давай теперь сделаем cicd через package через /Users/nidzhat/Documents/homeserver-stacks и на сервере ssh homeserver, где у меня видеокарта rtx 3080 ti как раз" (let's build CI/CD via packaging, through /Users/nidzhat/Documents/homeserver-stacks, deploying to the `ssh homeserver` server, which has an RTX 3080 Ti GPU)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Publish a deployable image on every change (Priority: P1)

A maintainer pushes a change to Tonemill's main branch. Without running any manual Docker build
command, a new, versioned, deployable image of every Tonemill component becomes available for
the production host to run.

**Why this priority**: Nothing else in this feature is possible without a reliable, automated
build/publish step — it's the foundation the deployment and GPU-validation stories both depend
on.

**Independent Test**: Push a trivial change to main. Confirm a new image build completes and a
new image becomes available in the registry, without any manual `docker build`/`docker push`.

**Acceptance Scenarios**:

1. **Given** a change is pushed to the main branch, **When** the automated build runs, **Then**
   a new image is published for each of Tonemill's deployable components (API, worker,
   frontend).
2. **Given** one component fails to build, **When** the automated build runs, **Then** no
   partial or broken image set is published — the failure is visible and nothing silently ships.
3. **Given** a previously published image exists, **When** a new one is published, **Then** the
   previous one remains identifiable and retrievable (not overwritten without a way back).

---

### User Story 2 - Run the published images on the real GPU host (Priority: P2)

An operator gets the currently published Tonemill images running on the home server that has
the RTX 3080 Ti, following the same repository-driven deployment pattern already used for this
account's other self-hosted services, instead of building from source on that machine.

**Why this priority**: Publishing images (US1) has no value until something actually runs them
in the real target environment; this is the second half of "ship a change and have it running."

**Independent Test**: With published images available, add/update the deployment definition for
Tonemill in the existing deployment repository and confirm all three components come up and the
worker has access to the host's GPU.

**Acceptance Scenarios**:

1. **Given** published images exist, **When** the production deployment definition references
   them, **Then** the API, worker, and frontend all start successfully on the target host.
2. **Given** the deployment is running, **When** the worker component starts, **Then** it has
   access to the host's NVIDIA GPU (matching how this account's other GPU-using services on the
   same host access it).
3. **Given** the deployment needs storage and credentials, **When** it starts, **Then** it uses
   this account's existing self-hosted object storage and existing secrets-management approach —
   no new storage service or plaintext secret is introduced.

---

### User Story 3 - Gate access behind a shared login (Priority: P2)

Anyone reaching the deployed application (once it's reachable at a public domain) is challenged
for a username and password before they can use any part of it, including uploading files or
submitting grading jobs. The credentials are a single shared pair configured via the
deployment's environment configuration, not a full user-account system.

**Why this priority**: The application currently has no authentication of any kind. Now that
it's going to be reachable at a public domain (`tonemill.nidzh.com`, via the account's existing
reverse proxy), an unauthenticated visitor could otherwise submit arbitrary uploads and consume
GPU time and storage. This must be in place before, or as part of, exposing it publicly.

**Independent Test**: With the deployment running, request any page or API endpoint without
credentials and confirm access is refused; request it again with the correct username/password
and confirm it succeeds. This can be verified without a real GPU job.

**Acceptance Scenarios**:

1. **Given** the application is deployed, **When** a request is made without credentials or with
   incorrect ones, **Then** access is refused and no application functionality (viewing,
   uploading, submitting, downloading) is reachable.
2. **Given** the correct shared username and password are provided, **When** a request is made,
   **Then** access is granted to the full application as before.
3. **Given** the deployment's environment configuration changes the username/password, **When**
   the application is restarted, **Then** the old credentials no longer work and the new ones
   do.

---

### User Story 4 - Confirm GPU-accelerated grading actually works on real hardware (Priority: P3)

Once deployed, an operator submits a real HDR video file to the running production application
and confirms it completes grading successfully using the GPU-accelerated profile — closing the
long-standing gap where this path had never been verified against real GPU hardware.

**Why this priority**: This is the payoff of the whole feature — the GPU grading path existed in
code but was only ever a documented, honest "unverified" risk without real hardware to test
against. It depends on US1 and US2 being done first.

**Independent Test**: Submit a real HDR clip to the deployed application, select (or let `auto`
resolve to) the GPU-accelerated profile, and confirm it completes successfully end-to-end.

**Acceptance Scenarios**:

1. **Given** the application is deployed and running on the GPU host, **When** a real HDR file
   is submitted with the GPU-accelerated profile selected, **Then** the job completes
   successfully and produces a downloadable, correctly graded result.
2. **Given** the GPU-accelerated path completes successfully once, **When** the outcome is
   recorded, **Then** the project's known "GPU path never verified on real hardware" gap is
   explicitly closed (documented, not just informally observed).

---

### Edge Cases

- What happens if an image build succeeds but the GPU-accelerated profile still fails at
  runtime on the real host (e.g., a dependency that only manifests inside a container)?
- What happens if the production host's GPU is temporarily unavailable when a job is
  submitted — does the job fail outright, or is there a fallback?
- What happens if a new image is published while a grading job is actively running on the
  production host — is the in-progress job affected?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A change pushed to Tonemill's main branch MUST trigger an automated process that
  builds an image for each deployable component (API, worker, frontend).
- **FR-002**: Successfully built images MUST be published to a registry reachable by the
  production host, identifiable both by a stable "current" reference and by a reference tied to
  the specific source change, so a specific prior version can be identified.
- **FR-003**: The build process MUST fail visibly and publish nothing if any component fails to
  build — partial publishing MUST NOT occur.
- **FR-004**: Applying a newly published image to the production host is an explicit, separate
  step (not automatically triggered by publishing) — matching this account's existing pattern
  where every other self-hosted service is updated via a manual `docker compose pull && up -d`
  (or the `.scripts/stack update` wizard) after its image is published. No new cross-repository
  automation is introduced by this feature.
- **FR-005**: The production deployment MUST run the worker component with access to the
  production host's NVIDIA GPU, matching the GPU-reservation approach already used by this
  account's other GPU-using services on the same host.
- **FR-006**: The production deployment's object storage configuration MUST point at this
  account's existing self-hosted storage service rather than provisioning a new one.
- **FR-007**: Secrets required by the production deployment (storage credentials and any
  others) MUST NOT be committed to any repository in plaintext. For this feature, they are kept
  in a plain, uncommitted environment file on the production host rather than this account's
  centralized secrets manager — see Assumptions.
- **FR-008**: The deployed application MUST be reachable from outside the home network via a
  public domain (`tonemill.nidzh.com`), through this account's existing reverse proxy, gated by
  the shared-login requirement in FR-011–FR-013.
- **FR-009**: It MUST be possible, after deployment, to submit a real video file through the
  running production application and confirm it completes grading successfully using the
  GPU-accelerated profile.
- **FR-010**: Both the image-build definition and the production deployment definition MUST be
  tracked in version control, consistent with how this account manages its other self-hosted
  services.
- **FR-011**: The application MUST require a single shared username and password before
  granting access to any functionality (uploading, submitting jobs, viewing status,
  downloading results) — no request reaches application functionality without valid
  credentials.
- **FR-012**: The username and password MUST be configured via the deployment's environment
  configuration, not hard-coded in source, and MUST follow the same not-committed-in-plaintext
  handling as other deployment secrets (FR-007).
- **FR-013**: This is a single shared credential pair, not a multi-user account system — no
  per-user accounts, registration, or password-reset flow is in scope.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A change pushed to the main branch results in a new, published, deployable image
  for every component within 10 minutes, with zero manual build commands run.
- **SC-002**: An operator can get a specific, previously published version of the application
  running again without rebuilding it from source.
- **SC-003**: A real HDR video file submitted to the deployed production application completes
  GPU-accelerated grading successfully at least once, closing the previously-unverified
  real-hardware gap.
- **SC-004**: Zero storage or infrastructure secrets appear in plaintext in the version history
  of either the application repository or the deployment repository.
- **SC-005**: An operator can determine, without guessing, exactly which published version of
  Tonemill is currently running in production.
- **SC-006**: 100% of requests to the deployed application without valid credentials are
  refused — zero application functionality is reachable by an unauthenticated visitor.

## Assumptions

- The automated build/publish process (FR-001–FR-003) is added to Tonemill's own repository
  (e.g. under its existing CI configuration directory), matching this account's established
  convention where every other self-hosted, custom-built service builds and publishes its own
  image from its own source repository — the deployment repository
  (`/Users/nidzhat/Documents/homeserver-stacks`) hosts only the deployment definition, not build
  logic, consistent with every other custom-built service already deployed through it.
- Three images are published — one per existing deployable component (API, worker, frontend) —
  extending the account's existing container-registry usage rather than restructuring it.
- A new deployment definition for Tonemill is added to the deployment repository, replacing the
  project's current build-from-source production configuration with an equivalent one that
  references the published images instead.
- The production deployment reuses this account's already-running self-hosted object storage
  service (a new bucket/credentials within it), rather than standing up a separate storage
  instance.
- Following an explicit follow-up request to skip the account's centralized secrets manager for
  now, secrets are kept in a plain, uncommitted environment file directly on the production
  host instead — a deliberate, temporary deviation from how most other secret-bearing
  self-hosted services in the deployment repository are handled today. Nothing about this
  choice is a dead end: adopting the centralized approach later is a non-breaking follow-up, not
  a redo.
- GPU access for the worker component reuses the NVIDIA container GPU-passthrough configuration
  already validated and running for this account's other GPU-using services on the same host.
- The public domain is `tonemill.nidzh.com`, proxied through this account's existing
  nginx-proxy-manager instance (set up separately by the feature owner, outside this feature's
  scope — this feature only needs the application to be correctly reachable once proxied).
- The shared-login requirement (FR-011–FR-013) reverses the "no auth in v1" assumption from the
  original Tonemill specification (specs/001-color-grading-pipeline/spec.md) — that assumption
  held only as long as the application was never reachable outside the trusted home network.
  It remains true that no multi-user account system is in scope; this is the minimum gate needed
  to safely expose the application publicly, not a general authentication feature.
- This feature does not otherwise change Tonemill's application functionality — beyond the
  shared-login gate, it is about how an already-built application gets published and run in the
  real production environment.
