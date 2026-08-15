# Design: Engaging Visual Layer for Production-Ready Renders

**Status:** Proposed
**Date:** 2026-08-15

## Problem

The current pipeline produces videos with the right *structure* (correct
cuts, correct chapter titles, correct pacing of topics) but the wrong
*surface* — long stretches feel like a talking-head recording with
occasional decoration, not a produced video. Three concrete gaps, confirmed
by reading the actual pipeline/renderer code (not assumed):

1. **No full-screen visual takeover.** `EpisodeImage.tsx`'s `display:
   "full"` mode and the `image` scene type already exist and are already
   wired through the renderer, QA checks, and DaVinci export — but no
   pipeline stage ever produces one. The only AI-reachable visual
   treatments today either leave the presenter full-frame with a small
   overlay (`bottom-callout`) or shrink the presenter to 72% width for a
   28%-width side panel (`side-*`). There is no treatment where a visual
   — a diagram, a photo of cabling, a screenshot — gets to *be the video*
   for a few seconds while the presenter's voice carries on as narration.

2. **No emphasis layer independent of captions.** Captions exist and stay
   as-is (verbatim Whisper segments, full sentence on screen for however
   long it takes to say, toggleable per-render/per-DaVinci-export). What's
   missing is a *second*, sparser layer: words and short phrases animating
   in sync with speech to underline meaning — not a transcript, a visual
   accent. Today the closest thing (`side-text`/`bottom-callout`) is
   gated behind the same rare "18s of monotony" trigger as diagrams and
   images, so it can't function as a frequent, lightweight rhythm layer.

3. **No machine-inspectable style system.** Pacing thresholds, treatment
   preferences, and "how much is too much" judgment calls are hardcoded
   across `visual_placement.py`, `generate_moments.py`, and prose baked
   into `.txt` prompt files. CLAUDE.md calls for this to live in
   inspectable config the AI can read and humans can tune — it doesn't
   today.

A fourth prerequisite surfaced during design: tight word-synced animation
needs word-level timing, and today's transcripts only have segment-level
`start`/`end` (~9s chunks). The `openai-whisper` CLI already in use
supports `--word_timestamps True`; it's currently off.

## Goals

- AI can place a **full-screen visual moment** (image, diagram, or a new
  combined text+graphic composition) where the presenter fully disappears
  from frame, voice continuing as narration.
- AI can place **lightweight kinetic emphasis** (word/phrase pops, simple
  motion graphics tied to a specific word or short span) much more
  frequently and cheaply than today's sparse moments, without competing
  with captions or full moments for attention.
- Both of the above draw from a **growing library of reusable animation
  treatments**, not one bespoke effect — new treatments should be easy to
  add later without touching the AI prompt architecture each time.
- Pacing/density/style judgment calls move into a **style-config doc** the
  AI reads and a human can edit directly, closing the CLAUDE.md gap.
- DaVinci export continues to Just Work — new scene types get their own
  transparent overlay clips the same way `image`/`moment` do today.
- **No rewrite.** Every change below is additive to the existing
  scene-plan schema, track/overlay split, and three-stage AI pipeline —
  nothing described in the "Solidly built" list gets replaced.

## Non-goals

- Auto-generating music/SFX, intro/outro, or background video — stays
  manual in DaVinci per the existing, deliberate boundary.
- Full generative video/image synthesis — visuals are still composed from
  indexed assets (images, code, diagrams) plus typographic/motion
  treatments, not AI-generated pixels.
- Changing the caption track itself (content, chunking, styling )— out of
  scope per explicit direction; captions stay exactly as they are today
  and remain independently toggleable.
- Real-time/interactive preview of the new treatments beyond what the
  existing Remotion Studio / preview-app already provides.

---

## Part 1 — Word-level timestamps (prerequisite)

**Change:** `transcribe_footage.sh` adds `--word_timestamps True` to the
`whisper` CLI invocation. `normalize_transcripts.py` and
`merge_segments.py` currently whitelist fields when reshaping Whisper's
raw output (`start`/`end`/`text`/a fixed metadata block) — both need to
pass a `words: [{word, start, end}]` array through unchanged instead of
dropping it.

**Migration:** the pipeline has no dependency-invalidation — each stage
skips if its artifact file already exists, `--force` doesn't cascade. Full
re-run required per episode: `transcribe_footage.sh --force` →
`normalize_transcripts.py --force` → `merge_segments.py --force`. This is
a one-time cost per already-transcribed episode; new episodes get it for
free once the flag is on. No schema version bump needed since `words` is
additive and nothing currently reads it.

**New consumer:** `generate_captions.py` is untouched (captions stay
verbatim, segment-level). Word-level data is consumed only by the new
emphasis-generation stage (Part 3).

---

## Part 2 — Full-screen visual moments

### Schema change

Add one new `MomentTreatment` value: `"full-visual"`. Reuses the existing
`MomentScene` shape — no new scene type needed, since a full-visual moment
is still "a moment relative to a parent presenter scene," just one that
claims the whole frame instead of a side.

```ts
// video-renderer/src/episode/types.ts
export type MomentTreatment =
  | "bottom-callout" | "side-text" | "side-image" | "side-code" | "side-diagram"
  | "full-visual";

export interface MomentScene {
  // ...unchanged fields...
  // presenterSide becomes irrelevant for "full-visual" — presenter is
  // fully hidden, not shifted. Existing validation in generate_moments.py
  // already treats presenterSide as treatment-specific; extend that
  // switch rather than the field itself.
  fullVisualKind?: "image" | "diagram" | "text"; // what fills the frame
}
```

`assetId` (image) / `diagram` (DiagramData) / `text` (headline-style
phrase) are reused as-is depending on `fullVisualKind` — this is
compositional, not a new data shape.

### Renderer change

New component `FullVisualMoment.tsx` in `video-renderer/src/episode/`,
sibling to `MomentTreatments.tsx`:

- Reuses `EpisodeImage`'s `display: "full"` rendering path for
  `fullVisualKind: "image"` (already built, already Ken-Burns animated —
  no new work there beyond routing).
- New: a full-frame `DiagramBlock` layout variant (existing `DiagramBlock`
  sized to fill center-frame instead of a side panel — same node/edge
  data, different container sizing + larger type scale).
- New: a full-frame typographic treatment for `fullVisualKind: "text"` —
  a short headline-scale phrase, brand-styled, for moments that deserve
  full visual weight without an image/diagram (e.g. a strong claim or a
  section's core idea stated plainly).
- Presenter handling: `Episode.tsx`'s `layoutWindowsForScene()` currently
  computes `center | left | right` from the active moment. Extend it to a
  fourth state, `hidden`, active only for the `full-visual` moment's own
  window (same padding-by-`TRANSITION_FRAMES` pattern already used for
  left/right) — presenter track continues playing audio, video is not
  rendered for that span. This is the same "derived per-frame, not a
  static scene property" pattern already documented at `types.ts:40-48`,
  extended by one case, not redesigned.

### AI planning change

Extend `generate_moments.py` + `pipeline/prompts/moments.txt` with
`full-visual` as a sixth (well, now via `fullVisualKind`, up to three new)
option alongside the existing five. Prompt additions:

- Explicit criterion: propose `full-visual` only when the visual is
  central enough to *replace* the presenter's screen time, not merely
  relevant to it — e.g. a wiring diagram someone needs to actually read,
  not a decorative photo. This mirrors the existing strict-relevance
  language already used for `side-image`/`side-code`, raised one notch.
- Keep it under the same grounding checks (`is_grounded`,
  `is_diagram_grounded`) already applied to text/diagram content — no new
  hallucination surface, same validation function, new call site.
- Duration: full-visual needs to be able to run *longer* than side
  treatments in some cases (a complex diagram may need 10-15s to read
  without a presenter competing for attention) — add a
  `FULL_VISUAL_DURATION_FRAMES` constant to the style config (Part 4)
  rather than hardcoding a fourth magic number in Python.
- Frequency: full-visual moments should be rarer than side treatments —
  express this as a style-config ratio (e.g. "at most 1 full-visual per N
  side moments") rather than a separate density constant duplicated in
  code.

### DaVinci export

No new work required beyond registering `"full-visual"` alongside existing
`moment` treatments — `export_davinci.py` already treats every `moment`
scene as one transparent-clip render regardless of treatment, and already
handles presenter-hidden spans correctly for any overlay-track scene
(it's just a `Gap` + separate clip, same as today).

---

## Part 3 — Kinetic emphasis layer

This is the "words/phrases pop in sync with speech, can combine with
graphics, more frequent and lighter than moments" layer.

### Why a new scene type, not a moment extension

Moments are deliberately rare (`MAX_MOMENTS_PER_1000_FRAMES = 1`,
monotony-gated) because they compete for the whole side of the frame.
Emphasis beats need the opposite cadence — potentially several per minute,
each on screen for under a second, timed to a specific word or short
phrase rather than a monotony window. Folding this into `generate_moments`
would either dilute the monotony gate's purpose or require two incompatible
cadences in one prompt. A new scene type keeps both simple.

### Schema

```ts
// New scene type, overlay-positioned like moment/caption/image.
export type EmphasisKind =
  | "word-pop"      // single word or short phrase, brand-styled, scales/fades in on the beat
  | "underline"     // a drawn accent line beneath a word as it's spoken
  | "icon-accent";  // a small glyph/icon appearing beside a word (e.g. an arrow, a check)

export interface EmphasisScene {
  type: "emphasis";
  id: string;
  kind: EmphasisKind;
  text: string;              // the word/phrase this beat emphasizes
  parentSceneId: string;
  offsetInParentFrames: number;
  durationInFrames: number;  // short — typically under 30 frames
}
```

Added to the `Scene` union. Positioned exactly like `caption`/`moment` via
`overlay_placement.py` — no new positioning logic needed, same
`absolute_position()` resolution.

`icon-accent` needs a small bundled icon set — start with a handful
(arrow, check, warning, gear — whatever recurs across the channel's
existing content) rather than an open-ended icon system; this can grow
per-episode without a schema change since it's just a string key into a
small static map in the component, same pattern as brand tokens today.

### Renderer

New component `EmphasisBeat.tsx`. Three small, cheap treatments (each is a
CSS transform/opacity animation over a handful of frames, no new
animation infrastructure needed — reuses spring/interpolate patterns
already used throughout `MomentTreatments.tsx`/`AnimatedTitle.tsx`).
Rendered as an overlay layer above the presenter, positioned using a
simple deterministic placement (e.g. lower-third, offset from the caption
region so it never collides with captions when both are on).

This is the seed of the "growing library of reusable animation
treatments" the product vision calls for — the type is intentionally an
enum (`EmphasisKind`) so adding a fourth/fifth treatment later (e.g. a
number counting up, a strikethrough) is additive: one new case in the enum,
one new small component branch, no pipeline/schema restructuring.

### AI planning change — new stage

New script `generate_emphasis.py` + `pipeline/prompts/emphasis.txt`,
inserted after `generate_captions.py` in `run_pipeline.py`. Unlike
moments, this stage is **word-timing driven, not monotony-driven**:

1. For each presenter scene, pass the transcript's word-level timing
   (Part 1) plus the segment text to the LLM.
2. The LLM picks a small set of words/short phrases per scene worth
   emphasizing — the ones carrying the key meaning (a named concept, a
   contrast, a number, a strong claim) — and a treatment (`word-pop` /
   `underline` / `icon-accent`) for each.
3. Because word-level start/end times are now available, the emphasis
   scene's `offsetInParentFrames`/`durationInFrames` are computed
   **deterministically in Python** from the matched word's actual
   timestamp, not chosen by the LLM — the LLM picks *which words*, code
   computes *exactly when*. This mirrors the existing division of labor
   (LLM judgment, code execution) used everywhere else in the pipeline,
   and it's what makes "pops exactly as the word is spoken" reliably
   accurate rather than an LLM guess at timing.
4. Density cap expressed in style config (Part 4), e.g. "at most 1
   emphasis beat per N seconds of presenter speech" — almost certainly a
   much higher frequency than the moments cap, since these are meant to be
   a constant light rhythm, not a rare event.
5. Same grounding discipline as existing stages: the emphasized text must
   be an exact word/phrase match against the transcript (trivially
   enforceable now, since it's selecting from real words with real
   timestamps rather than generating novel text).

### DaVinci export

`emphasis` joins `OVERLAY_TRACK_TYPES` alongside `title`/`caption`/
`moment`/`image` — same per-scene transparent clip + OTIO track pattern,
no new export logic, just registering the fifth overlay type.

### Collision handling

Emphasis beats must not visually collide with an active moment's side
panel or a full-visual takeover. Simplest correct rule: suppress emphasis
generation for any window that overlaps an existing `moment`/`image` scene
(check against the already-placed scene plan, since emphasis generation
runs after moments in the pipeline order) — no runtime collision detection
needed in the renderer, it's a placement-time filter in Python.

---

## Part 4 — Style config

New file: `config/style.json` (or `docs/style-guide.md` for the prose
parts + a small JSON for numeric knobs — see decision below), read by the
relevant pipeline stages instead of hardcoded Python constants, and
referenced by the prompt `.txt` files instead of prose duplicated in each
one.

**Recommendation: split, don't merge, prose and numbers.**

- `config/style.json` — every currently-hardcoded numeric/enum knob,
  consolidated:
  ```json
  {
    "monotonyThresholdSeconds": 18.0,
    "moments": {
      "maxPer1000Frames": 1,
      "durationFrames": {
        "bottomCallout": 90, "sideText": 150, "sideImage": 150,
        "sideCode": 240, "sideDiagram": 180, "fullVisual": 300
      },
      "fullVisualMaxRatioToSideMoments": 0.25
    },
    "emphasis": {
      "minSecondsBetweenBeats": 4.0,
      "defaultDurationFrames": 24
    },
    "titles": {
      "minSpacingSeconds": 20,
      "durationFrames": 60
    }
  }
  ```
  Loaded once by each stage script in place of its current
  module-level constant. This directly closes the "tunable without code
  edits" gap — a human can retune pacing per-channel-taste by editing one
  file, no Python changes.

- Prose editing *rules* (the "prefer left unless alternating", "use
  sparingly", anti-AI-slop guidance already in `moments.txt`) stay as
  prompt prose — they're instructions to the LLM, not values code branches
  on, so JSON adds indirection without benefit there. But **numbers
  referenced in that prose get templated in from `style.json`** at prompt-
  build time (e.g. "at most 1 full-visual per 4 side moments" — the `4`
  comes from `style.json`, not retyped by hand in the `.txt` file) so the
  two never drift out of sync.

**Learned preferences (CLAUDE.md's "human corrections accumulate into
future style guidance"):** out of scope for this change — flagged as a
clear follow-up once `style.json` exists, since it gives future
preference-learning something concrete to write to. Not designed further
here to avoid scope creep on an already-large change.

---

## Rollout plan (phased, each phase independently shippable/testable)

1. **Word-level timestamps** (Part 1) — transcription flag +
   normalize/merge pass-through. Test: re-transcribe one existing episode,
   confirm `words[]` survives to `episode_transcript.json`. No visible
   product change yet.
2. **Style config** (Part 4) — extract existing constants into
   `config/style.json`, update the 3-4 call sites to read from it, update
   prompt templating. Test: existing episodes render byte-identical scene
   plans (pure refactor, no behavior change) — good regression gate before
   adding new treatments on top.
3. **Full-screen visual moments** (Part 2) — schema, `FullVisualMoment.tsx`,
   `Episode.tsx` `hidden` layout state, `generate_moments.py` prompt
   extension, DaVinci registration. Test on Episode 9 (already has the
   "cables" asset use case in mind): confirm at least one full-visual
   moment gets proposed and renders correctly, presenter audio continues
   under it, DaVinci export produces a correct transparent clip.
4. **Kinetic emphasis layer** (Part 3) — schema, `EmphasisBeat.tsx`, new
   `generate_emphasis.py` stage + prompt, collision filtering, DaVinci
   registration. Test: run on a full episode, visually review density/
   placement, tune `style.json`'s `minSecondsBetweenBeats` from real
   output rather than guessing a value up front.

Each phase has its own QA-check additions (`qa_check.py` already has the
pattern for validating new scene types — extend, don't rearchitect) and
its own DaVinci export smoke test, so a problem in phase 4 can't regress
phases 1-3.

## Open questions for review

- `full-visual` and `emphasis` both introduce new prompt-facing judgment
  calls ("central enough to replace the presenter," "which words carry
  the key meaning") — expect the first real episode run to need 1-2 rounds
  of prompt tuning, same as `moments.txt` clearly went through
  historically (density caps, grounding checks, spacing minimums all read
  like lessons learned from real output).
- `icon-accent`'s bundled icon set needs an actual initial list — propose
  starting with 4-6 icons pulled from what's already used in existing
  thumbnails/graphics assets rather than designing icons from scratch.
