# Feature Specification: Tailwind CSS Visual Design

**Feature Branch**: `[002-tailwind-ui-design]`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "давай сделаем дизайн веб приложению используя tailwindcss" (let's design the web application using Tailwind CSS)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recognizable, cohesive product feel (Priority: P1)

A user opens Tonemill to upload and grade footage and sees a single, coherent visual
design across the whole page — consistent typography, color palette, and spacing — instead
of bare, unstyled form controls and default browser styling.

**Why this priority**: This is the foundation every other visual improvement builds on. Without
a consistent design system in place, styling individual states (progress, status, errors) would
just add more inconsistency.

**Independent Test**: Load the application with no jobs submitted yet. Every visible element
(heading, profile selector, max-quality toggle, file picker) shares one visual language and looks
like a deliberately designed product page, not an unstyled HTML form.

**Acceptance Scenarios**:

1. **Given** a user opens the application for the first time, **When** the page loads, **Then**
   all controls (profile selector, max-quality checkbox, file picker) share consistent
   typography, spacing, and color treatment.
2. **Given** a user interacts with any control (selector, checkbox, file picker, download link),
   **When** they hover, focus, or activate it, **Then** the control visibly responds (e.g., color
   or elevation change) so it's clear it's interactive.

---

### User Story 2 - At-a-glance job status (Priority: P2)

A user who has submitted one or more files can tell each job's status — uploading, queued,
processing (and which stage), done, or failed — by glancing at the page, without reading every
line of text.

**Why this priority**: Job status is the primary information the page exists to communicate
(per the existing progress-transparency requirement); making it visually scannable is the
highest-value design improvement beyond the base look-and-feel from User Story 1.

**Independent Test**: Submit several files so jobs land in different states (one still
uploading, one queued, one processing, one done, one failed). Each job's state is
distinguishable from the others by appearance alone (color/iconography), and a numeric or
stage-based progress indicator is rendered as a visual bar, not just a percentage in text.

**Acceptance Scenarios**:

1. **Given** a job is uploading, **When** its progress updates, **Then** a visual progress
   indicator reflects the current percentage.
2. **Given** a job is processing, **When** its stage changes (downloading source, grading,
   uploading result), **Then** the current stage is visually indicated alongside its progress.
3. **Given** a job has failed, **When** it's shown in the job list, **Then** it is visually
   distinguished (e.g., color) from queued, processing, and done jobs, and its error message is
   readable without breaking the layout.
4. **Given** a job has completed successfully, **When** it's shown in the job list, **Then** the
   download action is visually prominent and clearly distinct from other jobs' in-progress state.

---

### User Story 3 - Usable on any screen size (Priority: P3)

A user visits the application on a narrow (e.g., mobile/tablet) browser window as well as a wide
desktop window, and every control and job entry remains fully usable and readable without
horizontal scrolling or overlapping elements.

**Why this priority**: Broadens who can reliably use the tool, but the core desktop experience
(P1, P2) delivers the primary value first; responsiveness refines reach rather than core function.

**Independent Test**: Resize the browser window (or use a mobile-width viewport) with several
jobs in different states shown. All controls remain reachable and readable, and the job list
reflows without clipping content or requiring horizontal scrolling.

**Acceptance Scenarios**:

1. **Given** the application is viewed on a narrow viewport, **When** the page renders, **Then**
   all controls and job entries remain fully visible and usable without horizontal scrolling.
2. **Given** the application is viewed on a wide viewport, **When** many jobs are listed,
   **Then** the layout makes effective use of the available width rather than staying
   narrow-column-only.

---

### Edge Cases

- What does the page look like when no jobs have been submitted yet (empty state)?
- How is a very long filename displayed without breaking the job list layout?
- How is a long ffmpeg/validation error message displayed without breaking the job list layout?
- How does the job list look with a large number of jobs (e.g., after loading full job history
  from the backend)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The application MUST present a single, consistent visual design (typography, color
  palette, spacing, and component styling) across every element on the page.
- **FR-002**: Every interactive control (profile selector, max-quality toggle, file picker,
  download link) MUST have a visually distinct default, hover/focus, and disabled state.
- **FR-003**: Each job MUST be visually distinguishable by its current status (uploading, queued,
  processing, done, failed) through color and/or iconography, not text alone.
- **FR-004**: Upload and processing progress MUST be shown via a visual progress indicator in
  addition to (or instead of) a plain numeric percentage.
- **FR-005**: The currently active processing stage (downloading source, grading, uploading
  result) MUST be visually represented for a job that is processing.
- **FR-006**: A failed job MUST be visually distinguished from non-failed jobs, and its error
  message MUST remain fully readable without breaking or overflowing the job list layout.
- **FR-007**: A completed job's download action MUST be visually prominent and unambiguous.
- **FR-008**: The layout MUST remain fully usable (no horizontal scrolling, no overlapping or
  clipped content) on viewport widths from mobile (≈375px) through desktop (≈1440px+).
- **FR-009**: The page MUST present a distinct, intentional empty state when no jobs have been
  submitted yet, rather than an empty blank area.
- **FR-010**: Long filenames and long error messages MUST be handled gracefully (e.g., truncation
  with full text available, or wrapping) without breaking the surrounding layout.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time viewer can correctly identify the status (uploading, queued,
  processing, done, failed) of every job shown on the page within 3 seconds, without reading
  detailed status text.
- **SC-002**: Every interactive control on the page is fully visible, reachable, and usable
  without horizontal scrolling on both a 375px-wide and a 1440px-wide viewport.
- **SC-003**: 100% of visible elements on the page use the same consistent visual style — no
  unstyled, default-browser-styled, or visually inconsistent elements remain.
- **SC-004**: In a list containing both failed and non-failed jobs, a viewer can pick out every
  failed job correctly without reading any status text, in a single glance.

## Assumptions

- The scope of this feature is a visual/design pass over the existing functional page (profile
  selection, max-quality toggle, multi-file upload, job list with live status) — no new
  functionality, routes, or user flows are introduced.
- Visual styling will be implemented using Tailwind CSS, a utility-first CSS framework, as
  explicitly requested by the feature owner.
- Following an explicit follow-up request to raise the visual polish further, shadcn-svelte
  (copy-in-repo component primitives over Tailwind, not a black-box runtime dependency) and
  lucide-svelte (icon set) were added on top of the original Tailwind-only scope — see
  research.md #7. This supersedes the original plan's "no component library" research decision
  (#1), which was correct for the original request but not for this expanded one.
- A single dark visual theme is used by default, consistent with conventions in color-grading and
  video-editing tools (reduces eye strain and avoids interfering with color perception of graded
  footage previews); a light-theme toggle is out of scope for this pass.
- No custom logo or illustrated branding is introduced; the existing "Tonemill" text wordmark is
  kept, restyled to fit the new visual design.
- Accessibility baseline: sufficient color contrast for text and status indicators, and visible
  keyboard focus states on all interactive controls, consistent with standard web accessibility
  practice — no additional accessibility features (e.g., screen-reader-specific flows) are
  in scope beyond this baseline.
