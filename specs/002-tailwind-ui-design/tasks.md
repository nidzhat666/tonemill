---
description: "Task list for Tailwind CSS Visual Design"
---

# Tasks: Tailwind CSS Visual Design

**Input**: Design documents from `/specs/002-tailwind-ui-design/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/design-tokens.md, quickstart.md

**Tests**: Not requested for this feature (purely presentational; spec has no test-first
requirement). Visual acceptance is validated manually via quickstart.md in the Polish phase.

**Organization**: Tasks are grouped by user story (spec.md's US1/US2/US3) to enable independent
implementation and testing of each.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task includes its exact file path

## Path Conventions

Web app, frontend-only feature: `frontend/src/...` (see plan.md's Project Structure). No
`backend/` changes.

---

## Phase 1: Setup

**Purpose**: Bring Tailwind CSS into the existing frontend toolchain

- [X] T001 Add `tailwindcss`, `@tailwindcss/vite`, and `prettier-plugin-tailwindcss` as devDependencies in `frontend/package.json` and run `npm install` (versions per research.md #1/#2: `tailwindcss@4.3.3`, `@tailwindcss/vite@4.3.3`, `prettier-plugin-tailwindcss@0.8.1`)
- [X] T002 [P] Add the `@tailwindcss/vite` plugin to the `plugins` array in `frontend/vite.config.ts`, alongside the existing `sveltekit()` plugin
- [X] T003 [P] Add `prettier-plugin-tailwindcss` to the `plugins` array in `frontend/prettier.config.js`, after `prettier-plugin-svelte` (must load last per research.md #2)
- [X] T004 [P] Create `frontend/src/app.css` containing `@import "tailwindcss";`

**Checkpoint**: `npm run dev` in `frontend/` starts with no Tailwind/Vite config errors

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Wire the stylesheet into the app and establish the base dark theme every user story
renders on top of

**⚠️ CRITICAL**: No user story work can begin until this phase is complete — no Tailwind utility
class takes effect anywhere in the app until `app.css` is loaded

- [X] T005 In `frontend/src/routes/+layout.svelte`, add `import '../app.css';` as the first statement in the `<script>` block (before `let { children } = $props();`, per constitution Principle II and research.md #3), and apply the base dark-theme classes (`bg-slate-950 text-slate-100 min-h-screen`, per contracts/design-tokens.md's Color roles) to the root markup

**Checkpoint**: Loading the app shows the dark background/text globally; foundation ready for
per-story styling

---

## Phase 3: User Story 1 - Recognizable, cohesive product feel (Priority: P1) 🎯 MVP

**Goal**: A single, consistent visual design (typography, spacing, color) across every control on
the page, including a properly designed empty state and visible hover/focus states.

**Independent Test**: Load the app with no jobs submitted. Every visible element (heading,
profile selector, max-quality checkbox, file picker) shares one visual language; the empty job
list shows a designed placeholder, not blank space.

### Implementation for User Story 1

- [X] T006 [US1] In `frontend/src/routes/+page.svelte`, restyle the page header (`<h1>`, intro `<p>`) using contracts/design-tokens.md's Typography scale and Spacing tokens (`max-w-3xl mx-auto`, `px-4 py-8 sm:px-6 md:px-8` page container)
- [X] T007 [US1] In `frontend/src/routes/+page.svelte`, restyle the profile `<label>`/`<select>` with consistent spacing/typography and `hover:`/`focus-visible:` states per contracts/design-tokens.md's Interactive states
- [X] T008 [US1] In `frontend/src/routes/+page.svelte`, restyle the max-quality checkbox `<label>`/`<input>` with consistent spacing/typography and a visible `focus-visible:` ring
- [X] T009 [US1] In `frontend/src/routes/+page.svelte`, restyle the file `<input type="file">` picker with consistent spacing/typography and `hover:`/`focus-visible:` states
- [X] T010 [US1] In `frontend/src/routes/+page.svelte`, remove the `<style>` block and replace `.jobs`'s spacing with Tailwind utility classes (`space-y-3 mt-6`) on the job list `<section>`; implement the empty state (FR-009) using contracts/design-tokens.md's Empty state treatment when `jobsStore.items` is empty
- [X] T011 [US1] In `frontend/src/lib/components/JobCard.svelte`, remove the `<style>` block and restyle the card container and filename text using contracts/design-tokens.md's Color roles/Typography/Spacing tokens (`bg-slate-900 border border-slate-800 rounded-lg p-4`; filename as `text-sm font-medium truncate`)
- [X] T012 [US1] In `frontend/src/lib/components/JobCard.svelte`, add `hover:`/`focus-visible:` states to the download link per contracts/design-tokens.md's Interactive states

**Checkpoint**: At this point, User Story 1 is fully functional and testable independently — run
quickstart.md scenarios 1–2

---

## Phase 4: User Story 2 - At-a-glance job status (Priority: P2)

**Goal**: Every job's status, progress, current stage, and errors are visually scannable, and a
completed job's download action is unmistakably prominent.

**Independent Test**: Submit several files so jobs land in different states (uploading, queued,
processing, done, failed) simultaneously. Each state is distinguishable by color/iconography
alone; progress renders as a bar; the current processing stage is visible; failures stand out.

### Implementation for User Story 2

- [X] T013 [US2] In `frontend/src/lib/components/JobCard.svelte`, add a status→Tailwind-classes mapping (alongside the existing `stageLabel` mapping) covering `uploading`/`queued`/`running`/`done`/`failed`, per contracts/design-tokens.md's Status → visual mapping table
- [X] T014 [US2] In `frontend/src/lib/components/JobCard.svelte`, render the status as a colored badge using the T013 mapping instead of plain text (FR-003)
- [X] T015 [US2] In `frontend/src/lib/components/JobCard.svelte`, implement a visual progress bar (`bg-slate-800` track, fill colored per current state) driven by `uploadPercent`/`progressPct` (FR-004)
- [X] T016 [US2] In `frontend/src/lib/components/JobCard.svelte`, show the current processing stage (downloading source / grading / uploading result) alongside the progress bar while `status === 'running'` (FR-005)
- [X] T017 [US2] In `frontend/src/lib/components/JobCard.svelte`, style the failed-job error message so it wraps and stays fully readable without breaking the card layout, using the Status mapping's red treatment (FR-006, FR-010)
- [X] T018 [US2] In `frontend/src/lib/components/JobCard.svelte`, make the completed job's download link a visually prominent button (accent color from contracts/design-tokens.md), clearly distinct from in-progress jobs' treatment (FR-007)

**Checkpoint**: At this point, User Stories 1 AND 2 both work independently — run quickstart.md
scenarios 3–5

---

## Phase 5: User Story 3 - Usable on any screen size (Priority: P3)

**Goal**: The full page remains usable and readable, with no horizontal scrolling or overlap,
from mobile (~375px) through desktop (~1440px+) widths.

**Independent Test**: Resize the browser from ~375px to desktop width with several jobs in
different states shown. All controls and job entries stay reachable/readable, and the layout
reflows without clipping or horizontal scrolling.

### Implementation for User Story 3

- [X] T019 [US3] In `frontend/src/routes/+page.svelte`, apply contracts/design-tokens.md's Breakpoints (`sm:`/`md:` padding, `max-w-3xl mx-auto` centering) so the page container adapts from mobile to desktop widths (FR-008)
- [X] T020 [US3] In `frontend/src/routes/+page.svelte`, verify the profile selector, checkbox, and file picker remain full-width and fully usable at a ~375px viewport, adjusting classes from T007–T009 if needed (FR-008)
- [X] T021 [US3] In `frontend/src/lib/components/JobCard.svelte`, verify filename truncation (T011) and error wrapping (T017) hold up correctly across ~375px–1440px+ widths, adjusting if needed (FR-010)

**Checkpoint**: All three user stories are independently functional — run quickstart.md scenario 6

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final verification across all stories

- [X] T022 [P] Run `npm run lint` and `npm run check` in `frontend/` to confirm ESLint, Prettier (with `prettier-plugin-tailwindcss` class sorting), and `svelte-check` all pass
- [X] T023 Run all 6 validation scenarios in `specs/002-tailwind-ui-design/quickstart.md` end-to-end against the running app and confirm spec.md's Success Criteria (SC-001–SC-004)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories (no Tailwind class renders without `app.css` loaded)
- **User Stories (Phase 3–5)**: All depend on Foundational; within this feature they build on each other in priority order (US2's status badges style JobCard's card shell from US1; US3 verifies/adjusts US1+US2's markup at other widths) — implement in order P1 → P2 → P3
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Within Each User Story

- Tasks touching `+page.svelte` (T006–T010, T019–T020) are independent of tasks touching
  `JobCard.svelte` (T011–T012, T013–T018, T021) and can run in parallel across those two files
- Within `JobCard.svelte`, T013 (the status mapping) MUST precede T014 (badge rendering, which
  consumes the mapping)

### Parallel Opportunities

- T002, T003, T004 (Setup) can run in parallel once T001 completes
- T006–T009 (`+page.svelte` controls) can run in parallel with each other
- T011–T012 (`JobCard.svelte` base styling) can run in parallel with T006–T010 (`+page.svelte`), since they're different files
- T022 (lint/check) has no file dependency on T023 (manual validation) and can run in parallel

---

## Parallel Example: Phase 1 Setup

```bash
# After T001 (npm install) completes, run together:
Task: "Add @tailwindcss/vite plugin in frontend/vite.config.ts"
Task: "Add prettier-plugin-tailwindcss in frontend/prettier.config.js"
Task: "Create frontend/src/app.css with @import \"tailwindcss\";"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (dark theme + stylesheet wired in)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run quickstart.md scenarios 1–2 against the running app
5. Demo if ready — the page already looks and feels like a designed product, even before status
   colors (US2) or responsive polish (US3) land

### Incremental Delivery

1. Setup + Foundational → dark theme active, Tailwind wired in
2. Add User Story 1 → validate (scenarios 1–2) → demo (MVP)
3. Add User Story 2 → validate (scenarios 3–5) → demo
4. Add User Story 3 → validate (scenario 6) → demo
5. Polish: lint/check + full quickstart pass

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- No automated tests are added for this feature (see Tests note above); validation is the
  quickstart.md walkthrough plus the existing `npm run lint`/`npm run check` gates
- Commit after each phase checkpoint
