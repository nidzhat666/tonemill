# Contract: Design Tokens

This is the visual "interface contract" for the feature: the fixed set of colors, spacing,
typography, and breakpoints every screen/component MUST draw from. Any future addition to the
frontend restyles against this table rather than introducing new one-off values, keeping FR-001
("single, consistent visual design") and SC-003 (100% consistent styling) enforceable over time.

All tokens are Tailwind's own default theme (no custom `tailwind.config.js` palette) — see
research.md #1 for why no config file is introduced.

## Color roles

| Role | Tailwind classes | Used for |
|---|---|---|
| Page background | `bg-slate-950` | `<body>` / root layout background (dark theme, research.md #5) |
| Surface (card) | `bg-slate-900` | Job card backgrounds |
| Border | `border-slate-800` | Card and input borders |
| Primary text | `text-slate-100` | Headings, primary content |
| Secondary text | `text-slate-400` | Labels, helper/status text |
| Interactive accent | `text-sky-400` / `bg-sky-500` | Links, primary buttons, focus rings |

## Status → visual mapping (FR-003, FR-006)

| Job state | Color role | Tailwind classes (badge/indicator) |
|---|---|---|
| Uploading | Amber | `bg-amber-500/10 text-amber-400 border-amber-500/30` |
| Queued | Slate (neutral) | `bg-slate-500/10 text-slate-300 border-slate-500/30` |
| Running | Sky (blue) | `bg-sky-500/10 text-sky-400 border-sky-500/30` |
| Done | Emerald (green) | `bg-emerald-500/10 text-emerald-400 border-emerald-500/30` |
| Failed | Red | `bg-red-500/10 text-red-400 border-red-500/30` |

Progress bars (upload and processing) use the same role color as the row's current state
(amber while uploading, sky while running) against a `bg-slate-800` track.

## Typography scale

| Use | Tailwind classes |
|---|---|
| Page title | `text-2xl font-semibold` |
| Section/body copy | `text-sm` / `text-base` |
| Filename (job card title) | `text-sm font-medium truncate` (FR-010: truncates long filenames) |
| Status/meta text | `text-xs text-slate-400` |

## Spacing & layout

| Use | Tailwind classes |
|---|---|
| Page padding | `px-4 py-8` (mobile) → `sm:px-6 md:px-8` (wider viewports) |
| Max content width | `max-w-3xl mx-auto` |
| Job card padding | `p-4` |
| Vertical rhythm between job cards | `space-y-3` |

## Breakpoints (FR-008, mobile ≈375px → desktop ≈1440px+)

Mobile-first: unprefixed utility classes target the narrowest supported width (≈375px). Wider
layouts adjust via Tailwind's default breakpoints:

| Breakpoint | Min width | Applied to |
|---|---|---|
| (base) | 0 | Single-column layout, full-width controls |
| `sm:` | 640px | Increased horizontal padding |
| `md:` | 768px | Content width caps at `max-w-3xl`, centered |

No `lg:`/`xl:` overrides are needed — the page's content (a form plus a job list) doesn't
benefit from a wider-than-`max-w-3xl` reading measure even on large desktop viewports.

## Interactive states (FR-002)

| State | Treatment |
|---|---|
| Hover | Slightly lighter background/border than resting state (e.g., `hover:bg-slate-800`) |
| Focus | Visible ring: `focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:outline-none` |
| Disabled | `disabled:opacity-50 disabled:cursor-not-allowed` |

## Empty state (FR-009)

A centered, muted message (`text-slate-400 text-sm`) inside a dashed-border placeholder
(`border border-dashed border-slate-800 rounded-lg`) replaces the job list area when no jobs
have been submitted yet.
