# Implementation Plan: Tailwind CSS Visual Design

**Branch**: `002-tailwind-ui-design` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-tailwind-ui-design/spec.md`

## Summary

Give the existing, functionally-complete Tonemill frontend (profile selector, max-quality
toggle, multi-file upload with live per-job status) a single, consistent visual design built
with Tailwind CSS — replacing the current bare, per-component `<style>` blocks. No new routes,
API calls, or user-facing functionality are introduced; this is a presentational pass over
`+page.svelte`, `+layout.svelte`, and `JobCard.svelte` that makes job status, progress, and
errors scannable at a glance (per spec's User Stories 1–3) and keeps the layout usable from
mobile through desktop widths.

## Technical Context

**Language/Version**: TypeScript (SvelteKit 5, Svelte 5 runes) — unchanged, matches the existing
frontend.

**Primary Dependencies**: Tailwind CSS v4.3.3 via the official `@tailwindcss/vite` plugin (no
separate PostCSS config — confirmed as the current, recommended install path for Vite-based
SvelteKit projects); `prettier-plugin-tailwindcss` 0.8.1 for deterministic utility-class ordering
in the project's existing Prettier setup. Both versions confirmed live against the npm registry
(2026-08-19), not assumed.

**Storage**: N/A — no data model, API, or persistence changes; this feature is purely
presentational.

**Testing**: Existing Vitest (unit) and Playwright (e2e) suites, unchanged tooling. No new
automated visual-regression tooling (e.g., Percy/Chromatic) is introduced — see research.md #6
for why. Visual acceptance is validated against spec.md's acceptance scenarios via
quickstart.md.

**Target Platform**: Web browser, served via the existing SvelteKit `adapter-node` build inside
`docker/frontend.Dockerfile` — unchanged deployment target.

**Project Type**: Web application — this feature touches `frontend/` only; `backend/` is
untouched.

**Performance Goals**: No regression to page load weight or time-to-interactive versus the
current unstyled page. Tailwind v4's engine only emits CSS for utility classes actually used in
the source, so the shipped CSS stays small regardless of the full utility set's size.

**Constraints**: No new functionality, routes, or backend calls (per spec's Assumptions). Must
build inside the existing `docker/frontend.Dockerfile` multi-stage build without adding new
runtime services or build steps beyond the existing `npm run build`.

**Scale/Scope**: Three source files restyled (`+layout.svelte`, `+page.svelte`,
`JobCard.svelte`) plus one new global stylesheet (`app.css`) and the Tailwind/Prettier tooling
wiring — a small, bounded surface matching the app's existing single-page scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Simplicity, DRY & YAGNI | PASS. Utility classes applied directly in markup via the official Vite plugin — no component-library layer (e.g., daisyUI, shadcn-svelte) added on top, since none was requested and none is needed for a 3-file page (YAGNI). Per-status color logic is centralized in one mapping (research.md #4) instead of duplicated per template (DRY). |
| II. Explicit Imports | PASS, with one deliberate deviation from Tailwind's own doc example: `app.css` is imported at the very top of `+layout.svelte`'s `<script>` block, not after other statements as the official snippet shows (research.md #3). |
| III. Docstrings Over Comments | PASS. No non-obvious logic is introduced; the one small helper (a status→Tailwind-classes mapping) is self-evident from its names and needs no docstring beyond what a one-line description already covers. |
| IV. Test Clarity (Given/When/Then) | PASS. No new automated tests are required for this presentational pass (existing component logic/tests are unchanged); if any are added they follow the existing Given/When/Then convention. |
| V. Readability & Maintainability | PASS. Centralizing status-to-style mapping (rather than inline conditionals repeated across templates) keeps the templates readable despite Tailwind's verbose class lists. |

No violations — Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/002-tailwind-ui-design/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command) — no new entities
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── design-tokens.md # The visual "contract": color/status/spacing/breakpoint tokens
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
frontend/
├── vite.config.ts                  # MODIFIED: add the @tailwindcss/vite plugin
├── prettier.config.js              # MODIFIED: add prettier-plugin-tailwindcss (loaded last)
├── package.json                    # MODIFIED: new devDependencies (tailwindcss, @tailwindcss/vite,
│                                    #   prettier-plugin-tailwindcss)
└── src/
    ├── app.css                     # NEW: `@import "tailwindcss";` — the single global stylesheet
    └── routes/
        ├── +layout.svelte          # MODIFIED: import app.css (top of <script>), apply base
        │                           #   page/background/typography classes
        ├── +page.svelte            # MODIFIED: Tailwind utility classes replace the current
        │                           #   unstyled markup; layout, spacing, empty state (FR-009)
        └── lib/components/
            └── JobCard.svelte      # MODIFIED: Tailwind utility classes replace the component's
                                    #   `<style>` block; status→style mapping (FR-003, FR-006, FR-007)
```

**Structure Decision**: No structural changes to the app — same three Svelte files, same
routing, same component boundaries. The only additions are the Tailwind entry stylesheet and the
Vite/Prettier tooling wiring; `backend/` is untouched, matching the spec's Assumption that this
is a visual-only pass with no new functionality.

## Complexity Tracking

> Constitution Check above reported no violations — nothing to justify here.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
