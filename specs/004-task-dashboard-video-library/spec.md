# Feature Specification: Task Dashboard & Video Library

**Feature Branch**: `004-task-dashboard-video-library`

**Created**: 2026-08-20

**Status**: Draft

**Input**: User description: "Turn the job list into a dashboard: failed jobs get a per-job Dismiss button, plus a Dismiss all that clears everything not currently in progress (disabled when nothing to dismiss). Add a new tab where already-processed videos can be organized into flat folders via drag-and-drop, including multi-select bulk move. Downloads should use a real filename instead of a UUID. Downloaded/processed videos currently fail to open in macOS's default Preview/Quick Look — fix that. Mirror the on-site folder structure inside the storage bucket, using the same readable names. Name result videos by the source video's recorded creation date plus the grading profile applied. If a user uploads a file that's a duplicate of one already processed (or in progress) through the same profile, reject it with a friendly, non-blocking error instead of creating another job."

## Clarifications

### Session 2026-08-20

- Q: Should the original (source) files a user uploads also get renamed and organized into the same folder structure as their processed results, or should this feature's naming/folder changes apply only to the processed result files? → A: Leave source files completely untouched — current UUID-based storage key, no renaming, no folder placement. Only result files get the new naming/folder treatment.

### Session 2026-08-21

- Q: Moving a video into a folder was measured taking ~2 seconds (a real S3 object copy+delete per move, visible in production network timing) — should folder organization keep re-keying the underlying stored object to mirror the folder, or should the object's storage location stay fixed and folder organization live in the database only? → A: Stop re-keying storage on move. A result video's stored object gets one permanent, opaque location at grading time (matching the original pre-this-feature pattern) and is never touched again; folder membership is a database-only property. The human-readable name FR-016 requires is delivered a different way — as the filename the browser saves the download under (via the download URL's response headers) — so users still never see or download anything by an opaque identifier; only the underlying storage path is now opaque.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Downloaded results are correctly named and actually playable (Priority: P1)

A user finishes grading a batch of clips and downloads the results to hand off for editing. Each file has a name that tells them, at a glance, which shoot it's from and which look was applied — and every file opens immediately in the operating system's built-in video previewer, the same way any other video file would.

**Why this priority**: This is the actual deliverable of the product. A result file that won't open in a standard previewer, or that's named an opaque identifier, undermines the core value of the tool even though grading itself succeeded.

**Independent Test**: Process a source clip through any profile, download the result, and confirm (a) the file name reflects the source's recording date and the profile used, and (b) the file opens correctly in the OS's default media viewer without conversion.

**Acceptance Scenarios**:

1. **Given** a completed grading job, **When** the user downloads the result, **Then** the downloaded file's name is built from the source video's recorded creation date and the grading profile that was applied, not an opaque identifier.
2. **Given** a downloaded result file, **When** the user opens it with the operating system's default media previewer, **Then** it opens and plays correctly, with no additional software or conversion required.
3. **Given** two source videos that would otherwise generate the identical result name (same recorded creation date-time and same profile), **When** both are processed, **Then** each downloadable result has a distinct name.

---

### User Story 2 - Dashboard stays focused on jobs that need attention (Priority: P2)

A user has been submitting clips all day. The job list keeps growing with finished and failed entries, burying the handful of jobs still uploading or grading. They want to clear out everything that's done, one at a time or all at once, without losing anything they've already downloaded or organized.

**Why this priority**: Directly affects daily usability once job volume grows; without it the list becomes unusable clutter. Independent of the library/folder work.

**Independent Test**: Submit several files so the list contains a mix of in-progress, completed, and failed jobs. Dismiss a single failed job, then use "Dismiss all" to clear the rest, and confirm only in-progress jobs remain visible.

**Acceptance Scenarios**:

1. **Given** a job that finished with an error, **When** the user views it on the dashboard, **Then** it has its own "Dismiss" control that removes just that job from the dashboard.
2. **Given** a dashboard containing a mix of in-progress, completed, and failed jobs, **When** the user clicks "Dismiss all", **Then** every completed and failed job is removed from the dashboard in one action, and every in-progress job remains.
3. **Given** a dashboard where every job is currently in progress (or the dashboard is empty), **When** the user looks at "Dismiss all", **Then** the control is disabled.
4. **Given** a job whose result was already dismissed from the dashboard, **When** the user opens the video library, **Then** the resulting video is still present and accessible there.

---

### User Story 3 - Organize processed videos into folders (Priority: P3)

A user has accumulated dozens of graded clips across several shoots. They open a new "Library" area, create a folder per shoot, and drag each clip (or a multi-selected batch) into the right folder so future downloads are easy to find on the site.

**Why this priority**: High value for long-term organization once volume grows, but the product is fully usable without it — files remain downloadable individually regardless.

**Independent Test**: With at least one completed job in the library, create a folder, drag a single video into it, then multi-select several unsorted videos and move them into that same folder in one action; confirm the folder's contents reflect the move, each move completes quickly regardless of file size (SC-006), and downloading a moved video still saves under its readable name.

**Acceptance Scenarios**:

1. **Given** the video library, **When** the user creates a new folder and gives it a name, **Then** the folder appears in the library, initially empty, alongside any existing folders (folders are flat — a folder cannot contain another folder).
2. **Given** an unsorted processed video, **When** the user drags it onto a folder, **Then** the video is moved into that folder and no longer appears in the unsorted area.
3. **Given** several videos selected together, **When** the user moves the selection into one folder, **Then** all selected videos are moved into that folder in a single action.
4. **Given** a video already inside a folder, **When** the user moves it into a different folder, **Then** it is removed from the first folder and appears only in the new one.
5. **Given** a video assigned to a folder, **When** the user downloads it, **Then** the file is delivered under its readable name (FR-027), regardless of the folder it's currently organized into or how the file happens to be stored underneath.

---

### User Story 4 - Re-uploading an already-processed file is rejected cleanly (Priority: P4)

A user accidentally selects a file they already graded with the same profile (or that is still being graded). Instead of silently starting a redundant job, the site tells them plainly that this exact file was already submitted through this profile, and skips it without disrupting any other files in the same batch.

**Why this priority**: Protects against wasted processing time and user confusion, but is a safeguard rather than core functionality — the product works without it, just less efficiently.

**Independent Test**: Submit a file through a given profile, let it finish (or while it's still in progress), then submit the exact same file through the same profile again and confirm it is rejected with a clear message rather than creating a second job.

**Acceptance Scenarios**:

1. **Given** a file already fully processed through a given profile, **When** the user submits the exact same file through that same profile again, **Then** the site rejects the submission with a clear, friendly message and no new job is created.
2. **Given** a file currently being processed through a given profile, **When** the user submits the exact same file through that same profile again before the first finishes, **Then** the second submission is also rejected as a duplicate.
3. **Given** a file already processed through one profile, **When** the user submits the exact same file through a *different* profile, **Then** it is accepted as a new, distinct job.
4. **Given** a file whose previous processing attempt through a profile failed, **When** the user resubmits the exact same file through that same profile, **Then** it is accepted and a new job is created (a failed attempt does not count as "already processed").
5. **Given** a batch of several files submitted together where one is a duplicate, **When** the batch is submitted, **Then** the duplicate is rejected while every other, non-duplicate file in the batch is still uploaded and processed normally.

---

### Edge Cases

- What happens when "Dismiss all" is clicked while some jobs are still uploading, queued, or grading? Only the non-in-progress (completed or failed) jobs are removed; in-progress jobs stay visible.
- What happens when a user drags a video onto the folder it's already in? Nothing changes.
- What happens when a folder that still has videos assigned to it is deleted? Its videos return to the unsorted area rather than being deleted.
- What happens when a source video's recorded creation date can't be read from its own metadata? The result file falls back to using the date the job was submitted.
- What happens when the same file is submitted twice, back to back, before the first submission has even registered as a job? The second is still caught and rejected as a duplicate.
- What happens when the same file is resubmitted through the same profile but with a different "maximum quality" setting than the earlier submission? It is accepted as a distinct request, not treated as a duplicate.

## Requirements *(mandatory)*

### Functional Requirements

**Dashboard**

- **FR-001**: The dashboard MUST list every submitted grading job along with its current status.
- **FR-002**: Every job that finished with an error MUST show its own "Dismiss" control that removes just that job from the dashboard view.
- **FR-003**: The dashboard MUST provide a single "Dismiss all" control that removes every job that is not currently in progress (i.e., every completed or failed job) in one action.
- **FR-004**: "Dismiss all" MUST be disabled whenever there is nothing eligible to dismiss (the dashboard is empty, or every job on it is still in progress).
- **FR-005**: Dismissing a job, individually or via "Dismiss all", MUST NOT delete the underlying processed video — a successfully completed job's result remains available in the video library after its dashboard entry is dismissed.
- **FR-006**: Dismissed state MUST be shared across sessions (a job dismissed by one user of the dashboard stays dismissed for everyone), consistent with the dashboard's existing shared, non-per-user job list.

**Video library & folders**

- **FR-007**: The system MUST provide a video library view listing every successfully completed processed video, independent of the dashboard's own list.
- **FR-008**: Users MUST be able to create a named folder within the video library.
- **FR-009**: Folders MUST be flat — a folder cannot contain another folder.
- **FR-010**: Users MUST be able to move a single processed video into a folder via drag-and-drop.
- **FR-011**: Users MUST be able to select multiple processed videos at once and move the entire selection into one folder in a single action.
- **FR-012**: A processed video MUST belong to at most one folder at a time; moving it into a folder removes it from any folder it was previously in.
- **FR-013**: A processed video not assigned to any folder MUST remain visible in an unsorted area of the library.
- **FR-014**: Users MUST be able to move a video out of a folder back to the unsorted area.
- **FR-015**: Deleting a folder MUST NOT delete the videos assigned to it; they return to the unsorted area.

**Result naming, storage layout, and playability**

- **FR-016**: Every downloadable result file MUST be named using the source video's recorded creation date and the grading profile applied to it, rather than an opaque identifier (e.g. a UUID).
- **FR-017**: When a source video's recorded creation date cannot be determined from its own metadata, the system MUST fall back to the date the job was submitted for processing.
- **FR-018**: When two result files would otherwise generate an identical name (same recorded creation date-time and same profile), the system MUST disambiguate them so neither is overwritten or made inaccessible.
- **FR-019**: Every result video's underlying stored location MUST be set once, when it is created, and MUST NOT change afterward, including when the video is organized into a folder or moved between folders — folder organization is a property tracked separately from where the file actually lives, so that reorganizing the video library is never a data-moving operation. This applies only to result videos — the original source file a user uploaded MUST be left exactly as stored today (its own opaque identifier, no folder placement), since source files are never shown or organized in the video library.
- **FR-027**: Whenever a result video is downloaded — from the dashboard or the video library, regardless of which folder (if any) it's organized into — the file MUST be delivered to the user under its readable name (FR-016), never under its underlying storage identifier (FR-019).
- **FR-020**: Every result video file MUST open and play correctly in the operating system's standard, built-in media viewer (e.g., macOS Quick Look/Preview), without requiring additional software or format conversion.

**Duplicate submission handling**

- **FR-021**: When a user submits a file for processing, the system MUST detect whether the same source file has already been processed, or is currently being processed, through the same grading profile.
- **FR-022**: On detecting such a duplicate, the system MUST reject that submission, present the user with a clear and friendly explanation, and MUST NOT create a new processing job for it.
- **FR-023**: A source file previously processed under one profile MUST still be accepted when submitted under a *different* profile — this is not treated as a duplicate.
- **FR-024**: A source file whose only prior processing attempt through a profile *failed* MUST still be accepted when resubmitted through that same profile — a failed attempt does not count as "already processed."
- **FR-025**: A source file previously submitted through a profile with a different "maximum quality" setting MUST still be accepted — that is treated as a distinct request, not a duplicate.
- **FR-026**: When a batch of multiple files is submitted together, one file being rejected as a duplicate MUST NOT block, delay, or otherwise affect the upload and processing of the other, non-duplicate files in that batch.

### Key Entities

- **Job (dashboard entry)**: A single submitted grading request as already tracked by the pipeline, extended with a dismissed flag scoped to dashboard visibility only; dismissing it never removes the video it produced.
- **Video** (formerly referred to as "Processed Video"): The durable record of a successfully completed job's result — source recording date, grading profile applied, generated display name, storage location, and current folder assignment (or "unsorted").
- **Folder**: A user-created, flat (non-nested) container with a name, used to group processed videos within the video library; a video belongs to at most one folder at a time.
- **Duplicate Fingerprint**: The identity used to recognize "the same source file submitted through the same profile" — tied to the file's own content and the profile (and quality setting) requested, independent of its filename.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of downloaded or stored result video files open successfully on the first attempt in the operating system's default media previewer.
- **SC-002**: 100% of result video file names communicate both the source recording date and the grading profile used, without needing to open the file.
- **SC-003**: A user can clear every completed and failed job from the dashboard in a single action, and doing so never removes a processed video from the library.
- **SC-004**: A user can move 20 already-processed videos into one folder via a single bulk action, rather than 20 separate one-by-one moves.
- **SC-005**: Attempting to resubmit an already-processed (or in-progress) file through the same profile is blocked before a new job is created, in 100% of cases, with an on-screen explanation the user can read without technical knowledge.
- **SC-006**: Moving a video (or a multi-selected batch) into a folder completes in under a second, regardless of the video's file size — reorganizing the library is never file-size-dependent. Every downloaded result, from any folder, is still saved under its readable name (FR-027) even though the storage location itself no longer reflects folder placement.

## Assumptions

- Duplicate detection is based on the submitted file's own content, not its filename — camera-generated filenames (e.g. sequential DJI clip numbers) are commonly reused across unrelated shoots and would otherwise cause false positives.
- The dashboard and video library are a single shared workspace, consistent with the existing pipeline's job list (already shown to every user with no per-user separation) — dismissed state and folder organization are shared/global, not private to one browser or session.
- "Video creation date" refers to the recording date embedded in the source video's own metadata; when that isn't present, the date the job was submitted for processing is used instead.
- Folder deletion is a supported but secondary action; it only ever clears a video's folder assignment, never the video itself.
- A dashboard entry for a failed job may be fully discarded once dismissed, since it produced no video; a dismissed *completed* job's entry is removed from the dashboard only — its video and folder assignment persist in the library.
- Name collisions arising from an identical recorded creation date-time and profile are resolved with an appended short disambiguator, keeping generated names both readable and unique.
- Only result (processed) videos are renamed and organized into folders; original source uploads keep their existing, non-human-readable storage location indefinitely, since the video library never lists or manages source files directly.
