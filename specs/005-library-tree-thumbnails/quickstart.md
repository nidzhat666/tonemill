# Quickstart: Validating the Library Tree View & Video Thumbnails

A runnable validation guide — proves the feature works, referencing [contracts/api.md](./contracts/api.md) and [data-model.md](./data-model.md) rather than duplicating them. Assumes spec 004's video library (folders, move, dismiss) already works; this guide only covers what's new.

## Prerequisites

- The full stack running with at least one freshly-graded (post-this-feature) video in the library, plus ideally one *pre-existing* video graded before this feature shipped (to exercise the "not ready yet" placeholder).
- A source clip at least 20 seconds long (to get a full 10-clip preview) and, separately, one under 10 seconds (to exercise the reduced-clip-count path).

## 1. Thumbnail and preview clips exist after grading (P1, P3)

```bash
curl -s $API/videos | python3 -m json.tool
```
Expected for a freshly-graded video: `thumbnail_url` is a real (non-null) presigned URL; `preview_clip_urls` has up to 10 entries. For the sub-10-second source clip, confirm the count is reduced per research.md #3's formula (`floor(duration / 1.5)`, minimum 1) rather than still showing 10.

```bash
curl -o thumb.jpg "<thumbnail_url>"
file thumb.jpg   # confirm it's a real JPEG, not empty/corrupt
curl -o clip0.mp4 "<preview_clip_urls[0]>"
ffprobe -v error -show_entries stream=codec_name,width -of default=nw=1 clip0.mp4
# confirm codec_name=h264 (not hevc) -- research.md #2's browser-compatibility decision
ffprobe -v error -show_entries format=duration -of default=nw=1 clip0.mp4
# confirm ~1.5s (or the whole source's duration, for a too-short source)
```

## 2. Hover preview plays in-browser, static at rest (P3)

In the UI: open the library, confirm every ready video's row shows the static thumbnail at rest. Hover over one and confirm it starts playing a short montage of distinct moments (not the same frame repeated); move the pointer away and confirm it reverts to the static thumbnail. Hover the same video again and confirm playback starts with no visible loading delay (FR-011) — open the browser's network panel first and confirm no request for that video's clips fires until the *first* hover (FR-010).

## 3. Folder tree starts collapsed, Unsorted starts open (P2)

Open the library with at least two named folders (each holding a video) plus at least one unsorted video. Confirm both named folders show only name+count, collapsed, while Unsorted's videos are already visible. Expand one folder — confirm its videos appear indented beneath it and the other folder stays collapsed. Reload the page and confirm every folder is back to collapsed (client-local state, research.md #6 — nothing persisted).

## 4. Deleting videos is permanent and confirmed (P4)

```bash
# Given at least one done video's id:
curl -s -X POST $API/videos/delete -d '{"video_ids":["<id>"]}'
# -> {"deleted": 1}
curl -s $API/videos | grep -c '<id>'   # -> 0, it's gone
```
In the UI: select one or more videos (including at least one assigned to a folder), trigger delete, and confirm a confirmation dialog appears before anything happens. Cancel it — confirm nothing changed. Trigger delete again and confirm this time — confirm the videos disappear from the library, the folder they were in still exists (with its count reduced, not deleted itself), and the "Delete" control is disabled again once the selection is empty.

**Storage is actually freed, and dedup forgets the deleted video (FR-021, FR-024)**: after confirming deletion, check the bucket — the result/thumbnail/preview-clip objects for that video are gone. Then re-upload the exact same original source file through the same profile and confirm it's accepted as a brand-new submission (not rejected as a duplicate).

## Success criteria this proves

SC-001, SC-002 (folder tree), SC-003 (hover playback + repeat-hover speed), SC-004, SC-005, SC-006, SC-007 (delete).
