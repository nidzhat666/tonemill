# Feature Specification: Library Tree View & Video Thumbnails

**Feature Branch**: `005-library-tree-thumbnails`

**Created**: 2026-08-21

**Status**: Draft

**Input**: User description: "Redesign the video library to look like folders with files inside: files render as a compact list, indented under their folder so the grouping is visible at a glance. Folders gain a collapse/expand control and start collapsed by default. Each video shows a thumbnail — a frame captured at 5 seconds into the clip — and hovering over it plays a slideshow cycling through frames sampled every 10% of the video's duration, a couple of seconds apart. Size each list row so the thumbnail is clearly visible without the list feeling bulky."

## Clarifications

### Session 2026-08-21

- Q: How long should each mini-clip in the hover preview be? → A: 1.5 seconds per clip (10 clips = a 15-second full loop) — a clear-motion-vs-quick-loop balance.
- Q: Should the hover-preview mini-clips be loaded for every video when the library (or a folder) is opened, or only on demand? → A: Only on demand — a given video's mini-clips are retrieved the first time it's hovered, not up front; once retrieved during a session, hovering that same video again replays them without waiting again.
- Q: Does "fully removed" for video deletion mean the video's library entry and its underlying stored file are both permanently deleted with no recovery, or just hidden from the library view while the file is kept recoverable? → A: Permanent deletion — library entry and stored file are both gone forever; no recovery. The required confirmation step is the only safety net.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scan the library by thumbnail instead of by filename alone (Priority: P1)

A user opens the Library to find a specific clip among dozens of graded videos. Instead of a wall of identical-looking cards distinguished only by a date-stamped filename, each video shows a small preview image, so the user can recognize the shot by sight — the same way they'd browse a photo library or a file manager's icon view.

**Why this priority**: This is the core visual upgrade the rest of the feature builds on. Even without collapsing or hover-preview, a thumbnail-per-video list is immediately more useful than the current text-only rows.

**Independent Test**: Open the library with at least one completed video in it and confirm every video's list row shows a preview image alongside its name, sized so the image is clearly recognizable without any single row dominating the screen.

**Acceptance Scenarios**:

1. **Given** a completed video in the library, **When** the library is opened, **Then** its list row shows a thumbnail image representative of the video's content, not a placeholder or blank space.
2. **Given** a video whose thumbnail has not finished being prepared yet, **When** the library is opened, **Then** the video still appears in its list with a clear "preview not ready yet" state, rather than being hidden or blocking the rest of the list from displaying.
3. **Given** the library list showing several videos, **When** a user scans the rows, **Then** each row's thumbnail is large enough to recognize the shot but small enough that many rows are visible without excessive scrolling.

---

### User Story 2 - Collapse folders to cut through clutter (Priority: P2)

A user with many folders opens the Library and, by default, sees just the list of folder names with how many videos each holds — not every video inside every folder all at once. They expand only the folder they're currently working in, keeping the rest out of the way, and can tell at a glance which videos belong to which folder by how far they're indented.

**Why this priority**: Directly addresses the clutter the current always-expanded layout creates as folder count grows; independent of the thumbnail work in User Story 1.

**Independent Test**: With at least two folders that each contain a video, open the library and confirm both folders start collapsed (showing only name and count); expand one and confirm only its videos appear, indented under it, while the other stays collapsed.

**Acceptance Scenarios**:

1. **Given** the library is opened, **When** it finishes loading, **Then** every folder starts collapsed, showing only its name and video count — none of its videos are visible until the user expands it.
2. **Given** a collapsed folder, **When** the user activates its expand control, **Then** the videos inside it become visible, visually indented so their membership in that folder is unambiguous at a glance.
3. **Given** an expanded folder, **When** the user activates its collapse control again, **Then** its videos are hidden again and the folder returns to showing just its name and count.
4. **Given** two folders where one is expanded and one is collapsed, **When** the user looks at the library, **Then** each folder's own expand/collapse state is independent of the other's.

---

### User Story 3 - Preview a video's content by hovering, before downloading it (Priority: P3)

A user is scanning the library trying to remember which clip is which. Instead of downloading each candidate to check, they hold their pointer over a thumbnail and watch a short, silent montage play — a handful of brief moving clips sampled across the footage, back to back — getting a much better sense of the shot than a single static frame gives.

**Why this priority**: A meaningful enhancement on top of the static thumbnail from User Story 1, but the library is fully useful without it — this is polish, not a blocker.

**Independent Test**: Hover over a video's thumbnail for the length of a full preview loop and confirm actual motion plays (not just a slideshow of stills), sampled across the video rather than clustered at its start, then confirm moving the pointer away returns the thumbnail to its static resting frame. Hover the same video a second time and confirm it starts playing immediately, without waiting again.

**Acceptance Scenarios**:

1. **Given** a video's thumbnail, **When** the user hovers over it and keeps the pointer there, **Then** a sequence of short (1.5-second) moving clips plays back to back, each sampled from a different point spread across the video's full duration, not just its beginning.
2. **Given** a hover-triggered preview is playing, **When** the user moves the pointer away from the thumbnail, **Then** playback stops and the row returns to showing its static resting frame (the 5-second frame from User Story 1).
3. **Given** a video too short to yield 10 non-overlapping 1.5-second clips, **When** the user hovers over its thumbnail, **Then** the preview still plays using however many non-overlapping clips actually fit, without erroring or showing a blank state.
4. **Given** a video whose hover preview has never been requested this session, **When** the user hovers over its thumbnail for the first time, **Then** the preview begins playing once ready, without needing every other video's preview to have been loaded first.
5. **Given** a video whose hover preview was already played once during this session, **When** the user hovers over its thumbnail again, **Then** playback starts immediately, with no repeat loading delay.

---

### User Story 4 - Permanently delete videos that are no longer needed (Priority: P4)

A user has graded clips they don't need anymore — a bad take, a duplicate shoot, leftover test footage — and wants them gone entirely, not just tidied out of sight. They select one or more videos in the library, choose to delete them, confirm the action, and the videos and their files are permanently gone.

**Why this priority**: A real, explicitly requested capability, but it's destructive and the library is fully useful for browsing and organizing without it — placed last so the safer, non-destructive interactions (browse, organize, preview) are already established first.

**Independent Test**: Select one or more videos, trigger deletion, confirm in the dialog, and verify they no longer appear anywhere in the library; separately, trigger deletion and cancel the confirmation, and verify nothing changed.

**Acceptance Scenarios**:

1. **Given** one or more videos selected in the library, **When** the user triggers the delete action, **Then** the system asks the user to confirm before anything is deleted.
2. **Given** the delete confirmation is showing, **When** the user confirms, **Then** every selected video's library entry and its stored file are permanently removed, with no way to recover them.
3. **Given** the delete confirmation is showing, **When** the user cancels instead, **Then** nothing is deleted and every selected video remains exactly as it was.
4. **Given** no videos are currently selected, **When** the user looks at the delete control, **Then** it is disabled, consistent with other selection-dependent actions in the library.
5. **Given** a deleted video was assigned to a folder, **When** the deletion completes, **Then** that folder's video count reflects the removal and the folder itself still exists (folders can be empty).
6. **Given** a video has been permanently deleted, **When** its original source file is uploaded again through the same grading profile, **Then** it is accepted as a new submission rather than being blocked as a duplicate of the now-deleted video.

---

### Edge Cases

- What happens when a video is shorter than 5 seconds (so the nominal thumbnail moment doesn't exist)? The thumbnail falls back to the nearest frame the video actually has (e.g., its midpoint) rather than failing to produce one.
- What happens when a folder containing zero videos is expanded? It expands to an empty, clearly-labeled area rather than looking broken or identical to a collapsed state.
- What happens when a user drags a video onto a folder that's currently collapsed? The drop still succeeds — a folder's collapsed/expanded state affects visibility only, not whether it can receive a move.
- What happens when a video is too short to produce even one full 1.5-second clip? The hover preview falls back to the single longest clip that fits (down to the video's whole duration if needed) rather than attempting to play a clip longer than the source.
- What happens when a user rapidly moves the pointer on and off a thumbnail? The preview restarts cleanly from the static frame each time, without stacking up multiple in-flight preview sequences.
- What happens when a user hovers a video whose preview hasn't finished being retrieved yet? The row shows a brief loading indication (or simply keeps showing the static thumbnail) rather than an error, and begins playing as soon as it's ready — even if the pointer is still hovering.
- What happens when the user selects videos spread across several folders (and/or unsorted) and deletes them together? All selected videos are deleted in the one confirmed action, regardless of which folder each belonged to.

## Requirements *(mandatory)*

### Functional Requirements

**Thumbnails**

- **FR-001**: The system MUST provide a representative thumbnail image for every successfully processed video, captured from the moment 5 seconds into the video.
- **FR-002**: When a video is shorter than 5 seconds, the system MUST fall back to the nearest frame available from that video rather than failing to produce a thumbnail.
- **FR-003**: The video library MUST show each video's thumbnail as part of its list row.
- **FR-004**: A video whose thumbnail is not yet ready MUST still appear in the library, in a clearly distinguishable "not ready yet" state, rather than being omitted from the list.

**Hover preview**

- **FR-005**: The system MUST provide a set of short (1.5-second) preview clips for every successfully processed video, one starting at each 10% increment across the video's full duration (up to 10 clips total).
- **FR-006**: When a video's duration is too short for 10 non-overlapping 1.5-second clips, the system MUST reduce the number of preview clips so that none overlap and none extend past the video's own end, down to a single clip covering as much of the video as fits.
- **FR-007**: When a user hovers over a video's thumbnail, the library MUST play that video's preview clips back to back, in order, looping for as long as the pointer remains over the thumbnail.
- **FR-008**: When the user's pointer leaves a thumbnail, the library MUST stop playback and return to showing the static 5-second thumbnail (FR-001).
- **FR-009**: For a video too short to have multiple distinct preview clips, the hover preview MUST still play without error, using whatever clip(s) are actually available (FR-006).
- **FR-010**: The system MUST NOT retrieve every video's preview clips when the library (or a folder) is opened. A given video's preview clips MUST only be retrieved the first time a user hovers over that video's thumbnail.
- **FR-011**: Once a video's preview clips have been retrieved during a session, hovering over that same video again MUST play them without repeating the retrieval delay.

**Folder tree layout**

- **FR-012**: The video library MUST present folders and their videos as a nested list: each folder is a collapsible group, and videos inside an expanded folder are visually indented beneath it.
- **FR-013**: Every folder MUST start collapsed (showing only its name and video count) when the library is opened.
- **FR-014**: Users MUST be able to expand a collapsed folder to reveal the videos inside it, and collapse an expanded folder to hide them again.
- **FR-015**: Each folder's expanded/collapsed state MUST be independent of every other folder's state.
- **FR-016**: Collapsing a folder MUST only affect the visibility of its contents — it MUST NOT prevent that folder from receiving a video moved into it (via drag-and-drop or bulk move).
- **FR-017**: Each video's list row MUST remain sized so its thumbnail is clearly recognizable while keeping the row compact enough that a typical library shows several rows without excessive scrolling.

**Deleting videos**

- **FR-018**: Users MUST be able to select one or more videos in the library and choose to delete them.
- **FR-019**: Before any video is deleted, the system MUST require the user to explicitly confirm the action.
- **FR-020**: Canceling the confirmation MUST leave every selected video — its library entry, its stored file, and its folder assignment — completely unchanged.
- **FR-021**: Confirming the deletion MUST permanently remove each selected video's library entry and its underlying stored file; this action MUST be irreversible, with no recovery mechanism.
- **FR-022**: Deleting a video MUST NOT delete the folder it was assigned to, even if it was the folder's only video.
- **FR-023**: The delete action MUST be disabled whenever no videos are currently selected.
- **FR-024**: Once a video has been permanently deleted, submitting its original source file through the same grading profile again MUST be treated as a new submission, not rejected as a duplicate of the deleted video.

### Key Entities

- **Video Thumbnail**: A single still image representing a processed video, captured at (or near, per FR-002) the 5-second mark — what a video's list row shows by default.
- **Video Preview Clips**: An ordered set of short (1.5-second) video clips sampled across a processed video's duration (every 10%, reduced per FR-006 for short videos), retrieved on demand (FR-010) and played back to back to drive the hover-triggered preview.
- **Folder (extended)**: Gains a per-user-session expanded/collapsed display state (see Assumptions) on top of its existing name and video membership from the video library feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can visually identify a specific video among 20+ library entries by its thumbnail alone, without reading every filename.
- **SC-002**: Opening the library with several folders shows, without any scrolling beyond what the folder names themselves require, only folder names and counts — no video is visible until its folder is expanded.
- **SC-003**: Hovering over any video's thumbnail for a full preview loop plays back actual motion (not a slideshow of stills) sampled from at least 2 visually distinct moments in that video's footage. Hovering the same video a second time in the same session starts playback with no perceptible delay.
- **SC-004**: A user can tell which folder a visible video belongs to purely from its indentation, without needing to scroll up to re-read a folder header.
- **SC-005**: With all folders collapsed, a library containing 10 folders shows at least twice as many folder rows on one screen as the number of individual video cards the current layout fits in the same space.
- **SC-006**: A user can select videos spread across multiple folders and permanently delete all of them in a single confirmed action.
- **SC-007**: Canceling a delete confirmation results in zero videos being removed, 100% of the time.

## Assumptions

- "Unsorted" (the catch-all area for videos not in any named folder) behaves like the always-visible top level of the tree and starts expanded by default, since it is the first place a user needs to check after grading finishes — the default-collapsed behavior (FR-013) applies to named folders.
- A folder's expanded/collapsed state is a per-browser-session display preference, not shared across devices or other users and not persisted long-term — reopening the library later resets every folder to collapsed. This is consistent with the video library's existing shared/global data (folder membership, dismissed state) being kept separate from purely local UI state.
- The hover preview always plays the same sampled clips in the same order for a given video (not randomized or re-sampled per hover) — the underlying preview clips are generated once per video, not regenerated on demand. "Retrieved" (FR-010) refers to a client fetching an already-generated clip, not generating one live on hover.
- Preview-clip retrieval (FR-010) happening only on first hover, rather than for the whole library up front, is treated purely as an availability/timing behavior in this spec — it does not change what the user is shown once retrieved, only when the retrieval happens.
- Thumbnail and preview-clip generation for videos processed before this feature shipped is out of scope for this spec — existing videos may show the "not ready yet" state (FR-004) until backfilled or re-processed; a backfill mechanism, if wanted, is a separate concern.
- Selecting a video (existing checkbox/multi-select behavior) and dragging it (existing drag-and-drop behavior) continue to work unchanged in the new compact row layout — this feature changes how a video row looks and how folders show/hide their contents, not the existing interactions on top of them.
- Deletion applies only to videos already showing in the library (i.e., successfully completed). It does not introduce any new way to remove an in-progress or failed job — those are already covered by the dashboard's existing dismiss behavior, which never deletes a video.
- Deleting a video's stored file happens unconditionally and immediately once confirmed — there is no soft-delete, trash, or retention grace period in this iteration; the confirmation step (FR-019) is the only safeguard.
- The delete action operates on the current selection as a single bulk action (reusing the library's existing multi-select), not a separate always-visible per-row delete control — selecting just one video and deleting it is simply the one-item case of the same action.
