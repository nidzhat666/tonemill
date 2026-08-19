# Research: Tailwind CSS Visual Design

## 1. Tailwind CSS installation path for SvelteKit + Vite

**Decision**: Tailwind CSS v4 (confirmed current: `tailwindcss@4.3.3`, `@tailwindcss/vite@4.3.3`
on npm as of 2026-08-19) via the official `@tailwindcss/vite` plugin — no `tailwind.config.js`,
no `postcss.config.js`.

**Rationale**: This is the current officially documented installation path for Vite-based
frameworks, SvelteKit included (confirmed against tailwindcss.com's SvelteKit guide, fetched
live, not from training-data memory). It integrates as a single Vite plugin, needs one CSS file
(`@import "tailwindcss";`), and avoids a separate PostCSS pipeline entirely — the smallest
possible amount of new tooling for the project (Principle I: Simplicity, DRY & YAGNI).

**Alternatives considered**:
- Tailwind v3 + `postcss.config.js` + `autoprefixer` — legacy setup path; more config files for
  no benefit on a project starting its Tailwind integration fresh in 2026.
- A component library on top of Tailwind (daisyUI, shadcn-svelte, Skeleton) — rejected at the
  time: the spec scoped this to restyling 3 existing files with plain utility classes, and a
  component library was unrequested scope (YAGNI) for a page this small. **Superseded by #7**
  once the feature owner explicitly requested exactly this.

## 2. Utility-class formatting

**Decision**: Add `prettier-plugin-tailwindcss` (confirmed current: `0.8.1` on npm) to
`frontend/prettier.config.js`'s `plugins` array, after `prettier-plugin-svelte`.

**Rationale**: The project already runs Prettier (`npm run lint` = `prettier --check . && eslint
.`) as part of its quality gate. This plugin deterministically sorts utility classes into
Tailwind's canonical order, so class lists stay consistent across files without manual review —
directly supports FR-001 (one consistent visual style) at the tooling level. Per the plugin's own
documentation, Tailwind-class-sorting plugins must be loaded *last* in the `plugins` array to
compose correctly with other Prettier plugins (here, `prettier-plugin-svelte`).

**Alternatives considered**: No class-sorting plugin — rejected; without it, class order drifts
per author/edit and produces noisy diffs on unrelated changes.

## 3. Import placement in `+layout.svelte`

**Decision**: `import '../app.css';` is placed as the first statement in `+layout.svelte`'s
`<script>` block, before `let { children } = $props();`.

**Rationale**: Tailwind's own SvelteKit guide shows the CSS import *after* the `$props()` line
in its example snippet. That ordering conflicts with this project's constitution (Principle II:
Explicit Imports — "All imports MUST be placed at the top of the file"). The guide's ordering is
incidental to its example, not a requirement of the tool itself, so the project's own rule
governs here.

**Alternatives considered**: Following the doc's exact snippet ordering — rejected, violates
Principle II.

## 4. Centralizing per-status visual treatment

**Decision**: `JobCard.svelte` gets one small mapping (status/phase → Tailwind classes for
color/badge/icon) alongside its existing `stageLabel` mapping, instead of inline
conditional class strings scattered through the template.

**Rationale**: FR-003 and FR-006 require every job status to be visually distinguishable and
every failed job to stand out; doing this with repeated inline ternaries across the template
would duplicate the same status→color logic at multiple call sites, which Principle I (DRY)
rules out. A single mapping object is also where FR-003/FR-006's requirement lives in one
place, making it easy to verify against the design-tokens contract (`contracts/design-tokens.md`).

**Alternatives considered**: Inline `class:` conditionals per status directly on each element —
rejected as the number of call sites grows (status text, status badge, border/background),
duplicating the same condition each time.

## 5. Dark theme, no light-mode toggle

**Decision**: Apply the dark palette as the page's actual base colors (body background, default
text color) rather than using Tailwind's `dark:` variant driven by `prefers-color-scheme` or a
class toggle.

**Rationale**: The spec's Assumptions section fixes a single dark theme with no light-mode toggle
in scope for this pass. Using `dark:` variants would imply a light default plus a conditional
dark override — a second code path for a theme that doesn't exist in this feature (Principle I:
YAGNI). If a light theme or toggle is requested later, `dark:` variants can be introduced then
without restructuring the base markup.

**Alternatives considered**: `dark:` variant + light default — rejected as unnecessary given the
single-theme scope; a class- or cookie-driven theme toggle — out of scope per spec.

## 6. No new visual-regression testing tooling

**Decision**: Do not introduce a visual-diffing/screenshot-regression tool (e.g., Percy,
Chromatic, Playwright's built-in screenshot assertions) for this feature.

**Rationale**: The spec's Success Criteria (SC-001–SC-004) are about at-a-glance
distinguishability and layout usability, which are validated through the existing Playwright
e2e suite (element presence, computed layout at defined viewport widths) plus manual review
against spec.md's acceptance scenarios, documented as runnable steps in quickstart.md. Standing
up a new visual-regression service is infrastructure not requested by the spec and not justified
by the scope of a single internal page (Principle I: YAGNI).

**Alternatives considered**: Percy/Chromatic integration — rejected for now; revisit if the
design surface grows beyond a single page or gets a dedicated design QA process.

## 7. Adding shadcn-svelte + lucide-svelte (post-implementation follow-up)

**Decision**: `shadcn-svelte@1.5.0` initialized with the **Vega** preset (Lucide icons, Inter
font — "the classic shadcn/ui look") and `baseColor: "zinc"`, adding the `select`, `checkbox`,
`progress`, `badge`, `button`, and `card` primitives (plus `separator`, a `select` dependency).
`@lucide/svelte` (Lucide icon set) added for per-status icons (upload/clock/loader-circle
spin/circle-check-big/circle-x/download).

**Rationale**: A direct follow-up request ("let's make the UI even more beautiful, plug in the
coolest new components") explicitly asked for exactly what decision #1 above had rejected as
out of scope. Presented with the tradeoff (a real component library vs. further hand-rolled
Tailwind polish vs. a lower-level headless kit), the feature owner chose shadcn-svelte. It fits
this project's existing values reasonably well despite being a new dependency: components are
generated *into* the repo (`src/lib/components/ui/`) rather than pulled in as an opaque
`node_modules` black box, so they remain fully readable/editable — e.g. `progress.svelte` was
given a small `indicatorClass` prop (not upstream) so each job status could color its own
progress bar, which the stock component didn't support.

The CLI's `init`/`add` commands are interactive (`@clack/prompts`-based TUI) with no fully
non-interactive named-preset flag; the `--preset` flag only accepts a base62-encoded preset
*code* (from shadcn-svelte.com/create), not a plain preset name. The Vega preset's code was
computed locally by replicating the CLI's own published bit-packing/base62 encoding (from the
CLI's real, fetched source — `packages/cli/src/preset/preset.ts` and `presets.ts` — not
guessed), with `baseColor` overridden to `"zinc"`. Confirmation prompts needed a literal `\r`
(carriage return) piped to stdin, not `\n` — piped `\n` was observed moving the prompt's
selection cursor instead of submitting it, and piping `yes ""` (infinite `\n`) caused the CLI to
spin at ~100% CPU without producing output, consistent with each line being read as a
navigation keystroke rather than a submit.

The generated dark-mode CSS variables (`.dark` block in `app.css`) default to a neutral
(zero-chroma) gray scale independent of the `baseColor` config value (that field is recorded in
`components.json` for future `add`-time registry resolution, but the `init`-time theme CSS is
driven by the preset's separate `theme` field, which Vega sets to `"neutral"`). Rather than
leave the shipped near-black neutral palette, the `.dark` block's tokens were repointed at
Tailwind v4's own default color CSS variables (`var(--color-slate-950)`,
`var(--color-sky-500)`, etc.) to match this feature's existing slate-based dark palette
(contracts/design-tokens.md) instead of hand-writing new OKLCH literals — Tailwind v4 exposes
every default-palette shade as a CSS variable already, so referencing it keeps one source of
truth rather than duplicating color values.

**Alternatives considered**:
- Keep the hand-rolled Tailwind-only design from the original pass — rejected once the feature
  owner explicitly asked for a component-library upgrade.
- A different preset (e.g. Luma, Rhea) or a from-scratch custom preset via
  shadcn-svelte.com/create — Vega was chosen as the most recognizable, "classic" shadcn look,
  matching a general "coolest/newest" ask without a more specific design direction from the
  feature owner.
- Headless-only (bits-ui/melt-ui without shadcn's pre-styled layer) — offered as an option;
  feature owner picked the pre-styled shadcn-svelte path instead for faster visual payoff.
