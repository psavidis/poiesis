alrigh# Poiesis Pipeline — Current State Guide

This is a snapshot of what the pipeline can do today, and how to drive it. For the
day-to-day command reference see the root `README.md` — this doc is the "how do all
the pieces fit together" explanation.

## The mental model

Everything funnels into one artifact: `processing/scene-plan.json`. It's a flat,
timeline-ordered list of scenes. Every pipeline stage either produces part of this file
or reads it. Nothing renders until you're happy with what's in it. That's the whole
architecture — AI stages propose scenes, deterministic code merges them, Remotion renders
whatever the file says.

```
original_footage/*.mov
      |
      v
 prepare_footage.py        -> processing/manifest.json
      |
      v
 transcribe_footage.sh     -> processing/transcripts/
      |
      v
 validate_transcripts.py   -> processing/transcript_validation.json
      |
      v
 normalize_transcripts.py  -> processing/segments/
      |
      v
 merge_segments.py         -> processing/episode_transcript.json
      |
      v
 analyze_scenes.py         -> processing/scene-plan.json   (base: presenter scenes, silence-trimmed)
      |
      v
 index_assets.py           -> processing/assets.json       (graphics/ folder indexed)
      |
      v
 generate_title_scenes.py  -> processing/title_scenes.json + merges "title" scenes into scene-plan.json
      |
      v
 generate_moments.py       -> processing/moments.json + merges "moment" scenes (and parent layout)
      |
      v
 generate_captions.py      -> processing/captions.json + merges "caption" scenes
      |
      v
 generate_scene_plan_ts.py -> video-renderer/generated/episode/scene-plan.ts  (Remotion reads this)
      |
      v
 [optional] key_footage.py -> processing/keyed/*.webm       (green-screen removal, opt-in, slow)
      |
      v
 render_episode.sh         -> rendered/<episode>.mp4
      |
      v
 qa_check.py               -> processing/qa-report.json
```

Run all the stages above `key_footage.py` in one shot with `./create_episode.sh <episode-folder>`.
`key_footage.py` and the final render/QA are separate, deliberate steps (see below for why).

## The five scene types that exist today

| Type | Who creates it | What it looks like | Position |
|---|---|---|---|
| `presenter` | `analyze_scenes.py` (deterministic) | your talking-head footage, silence-trimmed | absolute `timelineStartFrame` |
| `title` | `generate_title_scenes.py` (AI) | full-screen text card between clips | absolute `timelineStartFrame` |
| `moment` | `generate_moments.py` (AI) | `bottom-callout` (short phrase over the full-frame presenter), `side-text` (longer phrase filling one side), or `side-image` (an asset filling one side) | relative to a parent `presenter` scene |
| `image` | hand-authored / edit-plan only | inset picture-in-picture overlay from `graphics/` | relative to a parent `presenter` scene |
| `caption` | `generate_captions.py` (deterministic) | burned-in subtitle text, lower-third | relative to a parent `presenter` scene |

The AI never places these randomly. Titles get proposed once per clip, only for genuine
topic changes. Moment scenes only get *offered* to the AI for windows that have gone ≥18
seconds without a visual change (computed in code, not left to the LLM's judgment) — and even
then the AI is told to skip most of them and only act on the strongest candidates. Every
proposal is validated: `bottom-callout`/`side-text` text must actually appear in what was
said; `side-image` selections must reference a real, indexed asset. `side-text`/`side-image`
also assign the parent presenter scene's `layout` (`"left"`/`"right"`) so the presenter
animates to make room — two moments can't assign conflicting layouts to the same parent, and
a `bottom-callout`'s parent must stay `"center"`. Nothing is trusted blindly.

## How to process a new episode end to end

```bash
# 1. Drop footage into <episode>/original_footage/, then:
./create_episode.sh /path/to/episode

# 2. (Optional, and slow — see below) remove the green screen background:
python3 pipeline/key_footage.py /path/to/episode

# 3. Regenerate the Remotion codegen if you ran keying after step 1's codegen:
python3 pipeline/generate_scene_plan_ts.py /path/to/episode

# 4. Look at processing/scene-plan.json. Adjust anything you don't like (see below).

# 5. Render:
./render_episode.sh /path/to/episode              # default resolution from config.json
./render_episode.sh /path/to/episode 3840x2160     # or override resolution per-render

# 6. Check it:
python3 pipeline/qa_check.py /path/to/episode
```

## How to parameterize / control the output

**Resolution** — `config.json`'s `render.width`/`render.height` sets the default (currently
1920x1080). Override per-render without touching config: `./render_episode.sh <episode> 3840x2160`.

**Which LLM does the AI stages** — `config.json`'s `llm.provider`. Currently `claude-code`,
which shells out to your Claude Code CLI login — no API key, no per-token billing, uses your
existing subscription. (`ollama` and `anthropic`-API-key providers also exist in the code if
you ever want to switch.)

**The edit plan itself** — `processing/scene-plan.json` is plain JSON, meant to be
hand-edited:
- Delete/edit any `title` scene's `text`, or a `moment` scene's `text` (bottom-callout/
  side-text) or `assetId`/`caption` (side-image).
- Delete/edit any `image` scene's `assetId` (must match an id in `processing/assets.json`)
  or `caption`.
- Adjust a `presenter` scene's `sourceStartFrame`/`sourceEndFrame` if the automatic
  silence-trim cut too much or too little.
- After hand-editing, re-run just the codegen step (`generate_scene_plan_ts.py`) — no need to
  re-run the whole pipeline.
- **In the app**: the preview app has a text box under the player for exactly this — "remove
  the second title card", "make the DI Promise clip end 20 frames earlier" — Claude proposes
  an edit (`pipeline/edit_plan.py`), validated against real scene ids and a per-type field
  allowlist before applying, shown with a reason. See the README's "Natural-language editing"
  section for the exact editable-field list.
- You can also just describe the change to me in a Claude Code session and I'll edit the JSON
  directly — same idea, no special tooling needed either way.

**Which images get selected** — `processing/assets.json`, generated by `index_assets.py` from
your `graphics/` folder. The AI only sees each image's `caption` field, never the pixels — so
caption quality directly determines selection quality. Filename-derived captions are usually
bad; write real ones.

**How sparse/frequent the AI visual additions are** — `pipeline/visual_placement.py`'s
`MONOTONY_THRESHOLD_SECONDS` (currently 18s) controls how long the presenter has to talk
uninterrupted before a window even becomes eligible for a moment overlay.
`generate_moments.py`'s `MAX_MOMENTS_PER_1000_FRAMES` caps total density.

## Fast iteration — don't full-render to check a small change

A full render re-encodes the whole episode; with keyed (background-removed) footage that's
15–20+ minutes for a ~12 minute episode. For checking a change:

```bash
cd video-renderer
npm run dev   # opens Remotion Studio — scrub the timeline live, no encoding
```

or a quick exported clip:

```bash
npx remotion render Episode --frames=5000-5300 --scale=0.5 /tmp/preview.mp4
```

`--frames` targets just the range you care about (read start/duration off `scene-plan.json`),
`--scale=0.5` halves resolution. Both cut render time drastically — good enough to judge
timing, titles, and keying quality.

## Background removal (green screen)

`pipeline/key_footage.py` is real, tested, and works — but it's a genuinely expensive
operation (chroma-key + alpha-channel video encoding), so it's **not** part of the default
`create_episode.sh` run. Run it explicitly when you want it:

```bash
python3 pipeline/key_footage.py /path/to/episode
```

It auto-detects letterboxing/crop, samples the actual green color from your footage, keys
+despills, and writes alpha-matted WebM files. On this machine, tuned settings get it to
roughly real-time-per-clip (not the multiple-times-slower-than-realtime it was before tuning).
`CHROMA_BLEND`/`DESPILL_MIX` (0.20/1.0) were widened from their original, tighter values
(0.06/0.5) after the original settings produced a visibly hard, scalloped hair silhouette —
verified against real footage that the wider values give a noticeably softer edge with no
green fringe. Known limits: `chromakey` is still a single-threshold keyer, not true
edge-aware alpha estimation (a dedicated matte-refinement tool like CapCut/Resolve does
better on fine flyaway strands), and green spill under strong lighting isn't always fully
eliminated by despill — usually fine for talking-head framing, more visible in extreme
close-ups.

**Audio**: `key_footage.py` strips audio from the keyed WebM (`-an` — it's a pure
visual-keying pass). `Episode.tsx` doesn't rely on it for sound either way: every presenter
scene plays audio from the *original* (unkeyed) source file via a separate `<Audio>`
element, trimmed to the same `sourceStartFrame`/`sourceEndFrame` as the video, regardless of
whether that scene uses keyed or raw footage. So audio is present and in sync whether or not
you've run background removal.

## Looping video background (behind the presenter)

If an episode has a `background/<video-file>` folder, `prepare_footage.py` picks it up
automatically (first video file found — no naming convention required) and records it in
`manifest.json`/`episode-props.ts`. `Episode.tsx` plays it as a continuously looping base
layer, using Remotion's native `<Loop>` component (no manual seam-matching needed — it
re-mounts the clip each cycle automatically). It's only visible where something is
transparent on top of it — in practice that means **keyed presenter footage**; title cards
and full-screen images paint their own opaque brand background over it, so it doesn't bleed
through everywhere.

Works with any looping clip you drop in a `background/` folder for future episodes — nothing
is hardcoded to Episode 9's specific file. If the clip isn't a perfectly seamless loop, a
soft/organic clip (particles, gradients, blur) tends to hide the seam well since there's no
hard geometry to jump; a clip with sharp shapes or text would show the cut more.

## Visual design (titles, moment overlays, image overlays)

`video-renderer/src/episode/brand.ts` holds the shared palette (`background`, `accent`,
text colors, corner radii) — change it there and `AnimatedTitle.tsx`, `MomentTreatments.tsx`
(`BottomCallout`/`SideText`/`SideImage`), and `EpisodeImage.tsx` all update consistently,
since they all import from it rather than hardcoding their own colors.

The current look (dark navy background, orange accent border/underline, subtle background
grid) was chosen after reviewing a specific reference channel's visual style — it's an
approximation using typography/color/layout, not custom illustration (that reference channel
uses bespoke character artwork, which is out of scope for what this can generate). If you
want to move closer to a different visual reference, point me at it and I'll re-derive the
palette/motion from it, same process as this round.

## What's deliberately NOT built (and why)

- **Code snippet scenes** — Episode 9's `code/` folder turned out to contain screen
  recordings and screenshots, not actual source text. Auto-generating a code snippet from
  the transcript would mean the AI fabricating code it never verified — exactly the kind of
  ungrounded decision this project avoids. Revisit once there's a real source-of-truth for
  code content.
- **Diagram scenes** — plausible next step, but needs a design decision first (hand-authored
  Mermaid templates the AI only fills in with labels, vs. fully generative diagrams — the
  former is safer and matches how titles/moments/images already work: AI selects/fills
  structured fields, never invents free-form content).
- **A DaVinci Resolve export path** — considered and explicitly rejected. Exporting to an
  editable Resolve timeline would break the core architecture: `scene-plan.json` stops being
  the single source of truth the moment a human starts hand-editing a copy of it inside
  Resolve's own timeline format. The real fix for "editing feels slow" was faster iteration
  tooling (Remotion Studio, fast preview renders), not a second editable representation.

## Everything is tested

180 automated tests currently cover: transcript normalization, silence trimming (including two
real bugs found and fixed — Whisper hallucinating trailing garbage text, and unclamped frame
math exceeding clip duration), scene-plan merging (including idempotency — re-running a stage
twice no longer duplicates scenes), QA checks, the natural-language edit-plan endpoint, and the
LLM client providers. Run them with:

```bash
.venv/bin/pytest
```
