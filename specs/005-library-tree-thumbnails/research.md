# Research: Library Tree View & Video Thumbnails

## 1. Thumbnail and preview-clip generation happen inline, in the same worker job

**Decision**: Right after a job's graded output is produced (still the same `_grade()` call, before the final `status=done` transition), the worker extracts a static thumbnail frame and the preview clips from the already-on-disk output file, uploads them alongside the result, and records their keys on the same `Video` document update that already sets `display_name`/`result_key`. No second job, no separate queue, no async "generation pending" state to track for newly-graded videos.

**Rationale**: The worker already has the finished output file on local disk at this point (spec 001's single-pass design) — extracting frames from it needs no extra download. Spec 005's own Assumptions already resolve the "not ready yet" state (FR-004) as being for *pre-existing* videos only ("Thumbnail and preview-clip generation for videos processed before this feature shipped is out of scope... a backfill mechanism, if wanted, is a separate concern") — so for every video graded going forward, "done" can simply mean "fully ready, including preview assets," with no separate completion signal to build or poll. This is the simplest design that satisfies every acceptance scenario without adding a new async orchestration layer.

**Alternatives considered**: A separate follow-up job (new Dramatiq actor) dispatched after grading succeeds — rejected: would require re-downloading the result (or keeping the temp directory alive across job boundaries), plus a genuine "pending" state on `Video` for brand-new videos that the spec doesn't actually need (its only pending-state scenario is the explicitly-out-of-scope backfill case).

## 2. Preview clips are re-encoded to H.264, not stream-copied from the HEVC master

**Decision**: Preview clips are generated with `libx264` (fast preset, modest quality, no audio track — `-an`), downscaled to a modest width (e.g. ~480px, independent of source resolution), not `-c copy` trims of the graded HEVC output.

**Rationale**: The graded output is intentionally tagged `hvc1`/HEVC for macOS Quick Look/Preview compatibility (research.md #2 in spec 004) — but that's an *OS-native* viewer, not a browser. HEVC playback support in `<video>` elements is inconsistent across browsers (notably unreliable in Chrome without specific hardware/OS support), and the hover preview *only* works if every user's browser can actually decode it. A stream-copy trim would have been free (no re-encode, just a container-level cut) and was the initial instinct, but it inherits the master's codec — wrong tool for a browser-playback use case. H.264 is universally supported in every major browser's `<video>` element, which is the actual requirement here (User Story 3 is entirely about in-browser hover playback). Downscaling keeps each clip small (fast to encode, cheap to store, fast for a browser to fetch on first hover) since a hover-preview thumbnail never needs source resolution.

**Alternatives considered**: Stream-copying the HEVC master (rejected above — browser compatibility). AV1/VP9 (rejected — smaller than H.264 in theory, but no efficiency win worth the added encode complexity for 1.5-second clips, and H.264 has the broadest guaranteed `<video>` support of the three). Keeping the source's native resolution (rejected — needlessly larger/slower for a small hover-preview image with no scenario that benefits from full resolution).

## 3. Clip count and spacing: a duration-driven formula, not a fixed 10

**Decision**: `clip_seconds = 1.5`. `N = max(1, min(10, floor(duration_seconds / clip_seconds)))`. Clip `i` (for `i` in `0..N-1`) starts at `i * (duration_seconds / N)` and runs `clip_seconds` long, except when `N == 1` and `duration_seconds < clip_seconds`, in which case the single clip covers the video's full duration instead of a fixed 1.5s.

**Rationale**: Directly implements FR-005/FR-006's "up to 10, evenly spaced, never overlapping, never past the end." Re-deriving spacing as `duration / N` (rather than always using the literal 10%-of-*original*-duration marks and just dropping some) means a reduced clip count still spreads evenly across the *entire* video rather than clustering in an arbitrary subset of the original 10 marks — matching User Story 3's "sampled across the video's full duration" framing even when `N < 10`.

**Alternatives considered**: Always sampling at literal 0/10/20/…% marks and simply omitting clips that would overlap (e.g., a 12s video keeps marks at 0%, 20%, 40%... dropping alternating ones) — rejected as needlessly more complex to reason about and no more correct than duration-driven even spacing at a reduced `N`.

## 4. Client never eagerly loads preview-clip bytes; the API can still return their URLs upfront

**Decision**: `GET /videos` includes `thumbnail_url` and an ordered `preview_clip_urls` array in every video's response — computing and returning presigned URLs is cheap (no bytes transferred). FR-010's "MUST NOT retrieve... MUST only be retrieved on first hover" is satisfied entirely at the DOM level: the frontend never sets a `<video>` element's `src` (the thing that actually triggers a browser fetch) until the user's pointer enters that row's thumbnail. Once set, the `src` is left in place rather than cleared on mouse-out, so hovering the same video again (FR-011) replays already-buffered content with no new network request.

**Rationale**: A dedicated "fetch this video's preview URLs" endpoint, called only on first hover, was considered and rejected — it would *increase* first-hover latency (an extra round trip before the browser can even start fetching the first clip) for a "lazy load" requirement that's really about not transferring megabytes of video for rows nobody hovers, not about hiding a few short presigned-URL strings already present in a JSON list response the library already has to fetch anyway.

**Alternatives considered**: A separate `GET /videos/{id}/preview` endpoint fetched on first hover — rejected (adds latency, adds an endpoint, solves a problem the DOM-level approach already solves for free).

## 5. Video deletion: hard delete, `S3StorageClient.delete_object` reintroduced

**Decision**: `POST /videos/delete` (body: `video_ids`) deletes each video's Mongo document (`VideoStore.delete`, a real `delete_one`) and every S3 object it owns — `result_key`, `thumbnail_key`, and every entry in `preview_clip_keys` — via a reintroduced `S3StorageClient.delete_object`. Unknown IDs are skipped (consistent with `POST /videos/move`'s existing behavior), and the response reports how many were actually deleted.

**Rationale**: Directly implements FR-018–FR-024 (spec.md Clarifications, Session 2026-08-21: "fully removed" was explicitly resolved to mean permanent, unrecoverable deletion of both the entry and the file). `delete_object` existed on `S3StorageClient` until the folder-move-latency fix (this spec's sibling change) removed it as dead code — it's not dead anymore; a real, new caller needs it. Deleting the Mongo document (rather than soft-marking it, e.g. a `deleted` status) is what makes FR-024 ("re-submitting the same file is treated as new, not a duplicate") correct for free: the fingerprint uniqueness index is scoped to `in_progress`/`done` documents, so a genuinely-removed document can never match it again — no extra "ignore deleted videos" clause needed anywhere else in the dedup logic.

**Alternatives considered**: A soft `deleted` status (keep the document, hide it from `GET /videos`) — explicitly rejected by the spec's own clarification (Option A over Option B); would also require carving out an extra exclusion in the fingerprint-uniqueness query that a hard delete makes unnecessary.

## 6. Folder collapse/expand is entirely client-local state; Unsorted defaults open

**Decision**: The library store keeps a client-only `expandedFolderIds` set (folders default to *not* being in it, i.e., collapsed) plus a separate `unsortedExpanded` boolean defaulting to `true`. Nothing is persisted server-side or in local storage; reopening the library resets to these defaults every time.

**Rationale**: Directly implements FR-013 and the spec's own Assumptions (per-session-only, resets on reload, explicitly *not* using the video library's existing shared/global data mechanisms). No backend change of any kind is needed for the entire Folder Tree Layout requirement group (FR-012–FR-017) — it's a pure rendering/state concern in the already-existing `library.svelte.ts` store and `+page.svelte`/`FolderCard.svelte` components.

## 7. Hover playback mechanics: one `<video>` element per row, `src` swapped on `ended`

**Decision**: Each video row's thumbnail area holds one `<video muted playsinline>` element. At rest it shows the static thumbnail image (a plain `<img>`, absolutely stacked above the `<video>`, hidden once playback starts). On `pointerenter`, the row's `<video>` gets `src` set to `preview_clip_urls[0]` and plays; its `ended` event advances to the next clip's URL (looping back to index 0 after the last), rather than a fixed `setTimeout` per clip — this stays correct even if a clip's actual playable duration differs slightly from the nominal 1.5s (e.g. the last, shorter fallback clip in a short video). On `pointerleave`, playback stops and the static `<img>` is shown again (FR-007/FR-008).

**Rationale**: A single reused `<video>` element (vs. 10 pre-mounted ones) keeps the DOM light across a library that may have many rows simultaneously rendered, and matches research.md #4's requirement that nothing fetches until hover. Driving advancement off the media element's own `ended` event (rather than a timer guessing at clip length) is simpler and more robust than keeping a duration constant in sync between backend generation and frontend playback.

**Alternatives considered**: Ten stacked, pre-mounted `<video>` elements with opacity-based crossfade — rejected as unnecessary DOM/complexity cost for a preview feature where a brief cut between clips (rather than a crossfade) is entirely acceptable, and it would fight research.md #4's lazy-fetch requirement (mounting 10 `<video src=...>` per row would fetch all 10 clips for every visible row immediately, not on hover).

## 8. New UI primitive needed: a confirmation dialog

**Decision**: Add a thin `alert-dialog` wrapper under `frontend/src/lib/components/ui/`, generated the same way the project's existing primitives were (shadcn-svelte's own component scaffolding over the already-installed `bits-ui` `AlertDialog`), matching the exact thin-wrapper pattern already used for `checkbox`/`button`/etc. No new dependency — `bits-ui` (already installed) exports `AlertDialog` directly; only the local wrapper file is missing.

**Rationale**: FR-019's mandatory confirm-before-delete step needs a real modal/dialog primitive; the project has none yet. Reusing the existing scaffolding convention keeps this consistent with every other UI primitive already in the codebase rather than hand-rolling a one-off confirm component.
