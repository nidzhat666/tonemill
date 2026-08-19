# Quickstart: Validating the Tailwind CSS Visual Design

## Prerequisites

- Node.js toolchain already used by `frontend/` (see `frontend/package.json`).
- The full stack running so real jobs can be submitted, per the existing dev flow:
  `docker compose -f docker-compose.dev.yml up -d --build`, or `npm run dev` inside `frontend/`
  against an already-running `backend/` (see `backend/README.md`).

## Setup

```bash
cd frontend
npm install        # picks up tailwindcss, @tailwindcss/vite, prettier-plugin-tailwindcss
npm run dev
```

Open the printed local URL (or `http://localhost:3000` when running via Docker Compose).

## Validation scenarios

Each scenario below maps directly to an acceptance scenario in `spec.md` — see that file for the
full Given/When/Then wording. Confirm each one visually.

1. **Cohesive look (User Story 1)** — Load the page with no jobs submitted. Confirm the heading,
   profile selector, max-quality checkbox, and file picker share one consistent visual style
   (see `contracts/design-tokens.md`), and that the empty state (FR-009) is shown instead of a
   blank area.

2. **Interactive states (User Story 1)** — Tab through the controls with the keyboard. Confirm
   each shows a visible focus ring (`contracts/design-tokens.md`'s Interactive states), and that
   hovering each control with a mouse visibly changes its appearance.

3. **At-a-glance status (User Story 2)** — Upload several files at once (or reuse the manual
   S3-seeding approach from `specs/001-color-grading-pipeline/quickstart.md` to create jobs in
   different states directly). With jobs in `uploading`, `queued`, `running`, `done`, and
   `failed` states simultaneously visible, confirm each is distinguishable by color alone
   (cover the status text with a hand/window and confirm the states still look different).

4. **Progress & stage (User Story 2)** — Watch a `running` job. Confirm progress renders as a
   visual bar (not just a number), and that the current stage (downloading source / grading /
   uploading result) is indicated as it changes.

5. **Failure readability (User Story 2)** — Submit a job that will fail (e.g., an invalid/corrupt
   source file, as used in the backend's own manual test flow). Confirm the error message is
   fully readable and does not break the job list layout, even if long.

6. **Responsive layout (User Story 3)** — Resize the browser window (or use dev-tools device
   emulation) from ~375px wide up to a desktop width (~1440px+). Confirm no horizontal
   scrolling, no clipped or overlapping content, at every width in between.

## Expected outcome

All six scenarios pass visually, matching `spec.md`'s Success Criteria (SC-001–SC-004), with no
functional behavior changes versus the pre-existing page (same requests, same polling, same
upload flow — see `data-model.md`).
