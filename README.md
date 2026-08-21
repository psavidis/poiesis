# Poiesis

Poiesis (ποίησις) is an AI-powered content creation pipeline that transforms raw footage into polished, publish-ready videos.

Built as an autonomous, agent-driven system, Poiesis orchestrates the entire production workflow—from ingesting recordings and generating transcripts to scripting, editing, rendering, and preparing content for publication. Its goal is to eliminate repetitive manual work while keeping creators in control of the creative process.

# Vision

Creating high-quality videos should be a creative task, not an editing marathon. Poiesis automates the production pipeline so creators can focus on ideas instead of repetitive workflows.

For a guided walkthrough of the current pipeline state — what each stage does, how to
parameterize resolution/LLM provider/AI sparsity, and what's deliberately not built yet —
see [`docs/pipeline-guide.md`](docs/pipeline-guide.md).

# The Poiesis App

A local, video-centric web app for driving the pipeline without the terminal. Instead of a
list of pipeline stages, the player sits at the center of the experience: pick an episode,
the preview lands automatically as soon as there's a scene plan to show (even before every AI
stage has finished — see below), and every AI-proposed scene (titles, moment overlays,
storyboard reasoning) is editable by clicking directly on the player or through a chat box
that turns a plain-English instruction into a validated edit. It runs the exact same scripts
as the CLI, using your Claude Code CLI login (`config.json`'s `llm.provider: "claude-code"`)
— no separate API key required.

```bash
./start_ui.sh
```

This starts the backend (`ui/server.py`, on :8000) and the app itself (on :5173), opening
:5173 in your browser automatically. Pick an episode folder from the list, or paste a path.
Pass a different backend port with `./start_ui.sh 8080` if 8000 is taken — the app itself
always runs on :5173. (For backend development with auto-reload on code changes, run
`cd ui && ../.venv/bin/uvicorn server:app --reload` in a separate terminal instead of
`start_ui.sh`, then run `cd video-renderer/preview-app && npm run dev` for the app.)

The first time, install the app's dependencies: `cd video-renderer/preview-app && npm install`.

## Running the pipeline and reviewing AI decisions

The default view is a collapsed progress indicator (Ingest / Understand / Draft edit /
Finalize) with a "Start" button — click it to run the full pipeline. The preview lands as
soon as `analyze_scenes` produces a scene plan (well before every AI stage has finished) and
fills in automatically as titles, moments, captions, and other proposals complete, with no
manual reload. Click any title or moment directly in the player (via the scene chips under
it) to open its editor — edit the text, remove it, or (for moments) expand "Adjust timing" to
drag its window against the real footage right there, no separate tab. Chapter-level
storyboard reasoning and the full AI episode-analysis pass are available as collapsible
panels above the player. Individual stage run/re-run, QA check, and render (including the
DaVinci Resolve export format) are one level down, behind the "Advanced" toggle, alongside a
live log of whatever's currently running.

## Natural-language editing

Under the player there's a text box. Type an instruction and Claude proposes a structured
edit to `scene-plan.json`, applied only after server-side validation — every scene id must be
real, every field must be on that scene type's editable allowlist, or the operation is
rejected and shown as such rather than silently ignored. Whatever was applied (or rejected,
and why) shows immediately, and the player reloads with the change. Clicking a scene chip
under the player both opens its structured editor and prefills this box with that scene's id,
so you don't have to already know it.

Deliberately scoped to editing/removing scenes that already exist — it won't invent a new
scene from a description, since that requires the AI to make up valid offsets/durations from
scratch rather than picking among real, already-validated options. Editable fields per type:

| Type | Editable fields |
|---|---|
| `presenter` | `sourceStartFrame`, `sourceEndFrame`, `effects` |
| `title` | `text` |
| `moment` | `text`, `assetId`, `caption`, `offsetInParentFrames`, `durationInFrames` |
| `caption` | `text`, `offsetInParentFrames`, `durationInFrames` |
| `image` | `caption`, `offsetInParentFrames`, `durationInFrames` |

Any scene type can be removed outright. `id`, `type`, and any scene-linking field (`videoId`,
`parentSceneId`, `assetId`) are never editable this way — those change what a scene
fundamentally *is* rather than how it behaves, a different (and much riskier) operation than
what this is for. A moment's `treatment` (and `presenterSide`) is likewise excluded — switching
treatments is `generate_moments.py`'s job, not a text edit.

Editing a presenter scene's trim points changes its duration, which shifts every later
track scene's (`presenter`/`title`) position to keep the timeline contiguous — this happens
automatically after every edit. Overlay scenes (`moment`/`caption`/`image`) never need
touching for this, since they're positioned relative to their own parent scene, not an
absolute timeline frame.

Like "Adjust timing", each instruction is applied straight to `processing/scene-plan.json`, and
the app automatically regenerates `video-renderer/generated/episode/scene-plan.ts` right after
— the next render already reflects the change, no separate manual codegen step. (Hand-editing
`scene-plan.json` directly, outside the app, still needs a manual `generate_scene_plan_ts.py`
run — see "Review" below.)

# Python Library Dependencies

- pip install json-repair
- pip install opentimelineio (only needed for `pipeline/export_davinci.py` —
  DaVinci Resolve export)



# Pipeline Order

Run the whole thing with:

```bash
./create_episode.sh /path/to/episode
```

which runs, in order:

1. `prepare_footage.py` — validates `original_footage/`, produces `processing/manifest.json`, symlinks the episode into the renderer's public folder.
2. `transcribe_footage.sh` — Whisper transcription, produces `processing/transcripts/`.
3. `validate_transcripts.py` — flags low-confidence transcript segments, produces `processing/transcript_validation.json`.
4. `normalize_transcripts.py` — cleans transcripts into a consistent shape, produces `processing/segments/`.
5. `merge_segments.py` — combines per-clip segments into `processing/episode_transcript.json`.
6. `analyze_scenes.py` — trims silence/dead air at each clip's start and tail, produces `processing/scene-plan.json`. Re-runs are safe: if `title_scenes.json`/`moments.json` already exist, it re-merges them into the freshly regenerated presenter scenes rather than losing them.
7. `index_assets.py` — lists the episode's `graphics/` folder into `processing/assets.json` (id, filename, caption). Captions default to a filename-derived guess but are preserved across re-runs once you (or the AI) write a real one — see "Writing good asset captions" below.
8. `generate_title_scenes.py` — proposes title-card scenes via the configured LLM provider, merges them into `scene-plan.json`, writes `processing/title_scenes.json` (the AI decision as an inspectable artifact).
9. `generate_moments.py` — proposes sparse `moment` overlay scenes for stretches of presenter footage that have gone too long without a visual change, choosing one of three treatments: `bottom-callout` (a short phrase overlaid on the still full-frame presenter), `side-text` (a longer phrase filling one side of the frame), or `side-image` (an asset from `assets.json` filling one side). `side-text`/`side-image` also set the parent presenter scene's `layout` to `"left"`/`"right"`, so the presenter animates to the opposite side to make room — Episode.tsx renders this as a slide, not a cut. Uses a deterministic pre-filter (`pipeline/visual_placement.py`, default: 18s since the last title/moment) to decide which windows are even eligible before asking the LLM, and validates every proposal — text must be grounded in what was actually said (rejects fabricated/unrelated text), image selections must reference a real `assetId` (rejects hallucinated ids). Never proposes more than one treatment for the same window, and never lets two moments assign conflicting layouts to the same parent scene. Writes `processing/moments.json`, merges into `scene-plan.json`.
10. `generate_captions.py` — deterministic, no LLM: for each presenter scene, clips that clip's per-segment transcript (`processing/transcripts/<videoId>.json`) to the scene's post-silence-trim `sourceStartFrame`/`sourceEndFrame` window and emits `caption` overlay scenes positioned the same relative way moment/image scenes are. Writes `processing/captions.json`, merges into `scene-plan.json`. Rendering respects each presenter scene's `effects.captions` flag (defaults to `true`) — set it to `false` on a specific scene to hide captions there.
11. `generate_scene_plan_ts.py` — generates `video-renderer/generated/episode/scene-plan.ts` for Remotion.
12. `analyze_episode.py` — LLM pass flagging transcript sections that may need a closer look, produces `processing/episode_analysis.json`.
13. `generate_episode_assets.py` — subtitles, review notes, chapters.

### Overlay scenes are positioned relative to their parent

`moment` scenes and inset `image` scenes don't store an absolute `timelineStartFrame`.
Instead they carry `parentSceneId` (a presenter scene's `id`) and `offsetInParentFrames`
(frames from that scene's own start). Remotion resolves the absolute position at render time
by looking up the parent's *current* position. This means re-running `analyze_scenes.py` or
`generate_title_scenes.py` — which can shift presenter scenes forward when titles are
added/removed — never leaves an overlay pointing at the wrong moment; it's always correct
relative to whichever clip it's anchored to, even if that clip's position in the timeline
changes. Full-screen (`display: "full"`) images are the exception — they occupy the track
like presenter/title scenes and use an absolute `timelineStartFrame`, since they replace the
whole frame rather than sitting on top of something.

### Writing good asset captions

`index_assets.py` seeds each image's caption from its filename, which is usually poor
(`Gemini_Generated_Image_by9kjgby9kjgby9k.png` tells the AI nothing). The image-selection
prompt only sees each asset's `caption` — not the image itself — so a vague caption means bad
or missing selections. After the first `index_assets.py` run, open
`processing/assets.json` and rewrite each `caption` to actually describe what the image shows
and what concept it represents (e.g. "a dense tangle of wires, representing an
overcomplicated, unmanageable system"). Captions you write are preserved on every future
re-index — only genuinely new files get a filename-derived placeholder.

## Review (before rendering)

The pipeline stops short of rendering on purpose. `processing/scene-plan.json` is the edit
plan — plain, human-readable JSON — and it's meant to be reviewed and adjusted before you render:

- **Title cards**: edit `text` on any `type: "title"` scene, delete ones you don't want,
  or add new ones by hand (same shape as the ones `generate_title_scenes.py` writes).
- **Moment overlays and inset images**: same idea for `type: "moment"` and `type: "image"`
  (`display: "inset"`) scenes — edit/remove/add. These render as an overlay on top of the
  presenter, positioned via `parentSceneId` (a presenter scene's `id`) and
  `offsetInParentFrames` (frames from that scene's start) — not an absolute timeline frame.
  `offsetInParentFrames + durationInFrames` must not exceed the parent scene's own
  `durationInFrames` (`qa_check.py` will flag it if not). A `moment`'s `treatment`
  (`bottom-callout`/`side-text`/`side-image`) must agree with its parent presenter scene's
  `layout` (`center` for bottom-callout, `left`/`right` for the side treatments) —
  `qa_check.py` flags a mismatch there too.
- **Clip trimming**: adjust `sourceStartFrame`/`sourceEndFrame` on any `type: "presenter"`
  scene if the automatic silence trim over- or under-cuts.
- **In the app**: click a title/moment chip under the player to edit it directly (see
  "Running the pipeline and reviewing AI decisions" above), or use the chat box under the
  player — "remove the third title card", "trim 10 more frames off the end of scene-009" —
  that asks Claude to propose the edit, shows what it did (or rejected, and why) before
  applying, then reloads the player with the change. Scoped to editing/removing existing
  scenes only (title/moment/caption/image text and timing, presenter trim points) — it won't
  invent a new scene from a description. See "Natural-language editing" above for exactly
  which fields are editable this way.
- Or ask Claude directly (in a coding session, e.g. this repo's Claude Code setup) to make the
  same kind of edits — since the plan is just JSON, this requires no special tooling either.

After editing `scene-plan.json` by hand, re-run just the codegen step to pick up the change
without re-running the whole pipeline:

```bash
python3 pipeline/generate_scene_plan_ts.py /path/to/episode
```

### Fast iteration (don't full-render every change)

A full `render_episode.sh` pass re-encodes the entire episode — with keyed (alpha) footage
this can take 15-20+ minutes for a ~12 minute episode. Don't use it to check a small edit.

- **Live scrubbing while editing the plan**: run `npm run dev` inside `video-renderer/` (wraps
  `remotion studio`). It opens an interactive preview that reads the same generated
  `scene-plan.ts`/`episode-props.ts` — scrub the timeline, jump to any scene, and it only
  computes the frames you're actually looking at instead of encoding the whole thing.
  Re-run `generate_scene_plan_ts.py` after editing `scene-plan.json` and the studio picks up
  the change on refresh.
- **A real exported preview file, fast**: render a small frame range and/or at reduced scale
  instead of the whole thing:

  ```bash
  cd video-renderer
  npx remotion render Episode --frames=0-300 --scale=0.5 /path/to/preview.mp4
  ```

  `--frames` limits which scenes get rendered (use `scene-plan.json`'s `timelineStartFrame`/
  `durationInFrames` to target the scene you're checking), `--scale=0.5` renders at half
  resolution — both cut render time substantially and are enough to judge timing, titles, and
  keying quality without waiting on the full-quality pass.

Once you're happy with the plan, render the full episode:

```bash
./render_episode.sh /path/to/episode
```

Default resolution comes from `config.json`'s `render.width`/`render.height` (1920x1080).
Override it per-render without touching config:

```bash
./render_episode.sh /path/to/episode 3840x2160
```

Higher resolution means more pixels to decode/composite per frame — this directly increases
render time, on top of whatever cost keyed (alpha) footage already adds.

### Finishing in DaVinci Resolve (background, intro/outro, music)

Poiesis renders presenter footage + AI-placed overlays (titles, moments, captions, images).
It doesn't render the looping background, intro/outro, or music — those are channel-wide
branding assets, mixed by hand on a DaVinci Resolve timeline, not per-episode AI decisions.
`--transparent` renders a **transparent master** instead of the normal opaque MP4: presenter
+ overlays only, as an alpha-preserving ProRes 4444 `.mov`, meant to be dropped into a Resolve
project that already has the background/intro/outro/music on the timeline:

```bash
./render_episode.sh /path/to/episode --transparent
```

This only produces real transparency where the presenter footage is actually keyed
(`key_footage.py` must have run first — unkeyed footage has no alpha to preserve) and
overrides any `backgroundVideo` configured on the episode to `null` at render time (so an
episode's own looping background never gets baked in and blocks the transparency). Combine
with a resolution override the same way: `./render_episode.sh /path/to/episode --transparent 3840x2160`.

And check the result:

```bash
python3 pipeline/qa_check.py /path/to/episode
```

`qa_check.py` catches gaps/overlaps in the timeline, missing media, and rendered-duration
mismatches on the scene plan — run it after any manual edit. Once a render exists, it also
decodes the actual rendered file: sustained black frames (tuned against this channel's dark
brand background so title cards don't false-positive), an audio track that's silent or missing
entirely, and audio/video streams whose lengths have drifted apart (not frame-accurate
lip-sync, but enough to catch a truncated or dropped audio track). Run it again after
rendering to catch render-time failures the scene-plan checks can't see.

### DaVinci Resolve export (automated per-scene alternative to `--transparent`)

`--transparent` above produces one long transparent video the user has to manually cut and
position in Resolve. `pipeline/export_davinci.py` automates that mechanical step: it renders
one short transparent ProRes 4444 clip per scene element (same flags as `--transparent`, just
scoped to each scene's own frame range via Remotion's `--frames=`), and writes an
[OpenTimelineIO](https://opentimelineio.readthedocs.io/) `timeline.otio` with each element
type — presenter (video + its own audio track), titles, captions, moments, images — on its own
OTIO track, independently trimmable/retimeable in Resolve rather than one flattened video.

```bash
python3 pipeline/export_davinci.py /path/to/episode
python3 pipeline/export_davinci.py /path/to/episode 3840x2160   # optional resolution override
python3 pipeline/export_davinci.py /path/to/episode --resume    # skip clips already rendered by a prior run
```

Requires `pip install opentimelineio` (see Python Library Dependencies above). Writes to
`<episode>/davinci-export/timeline.otio` and `<episode>/davinci-export/clips/` (sibling to
`processing/`/`rendered/`, not nested inside either). Open it in Resolve via **File → Import
Timeline → OpenTimelineIO**. Same as `--transparent`: background/intro/outro/music are not
part of this export — they stay a manual step on a project you build in Resolve. This is also
available from the app's Advanced panel's "Render" button via the **Output format** selector,
alongside the existing MP4 render.

Note: no interchange format (OTIO, AAF, EDL, FCPXML) reliably carries titles/text as
real, editable Resolve title objects on import — that's why titles are baked into each
clip's pixels via Remotion rather than left as Resolve-native text. Only clip placement
(in/out points, order, timeline position) survives the OTIO round-trip, which is exactly
what this export needs it for.

#### Organizing the media pool into bins

Resolve's OTIO importer can't be driven to create bins/folders from the `.otio` file itself —
it doesn't even preserve OTIO track names on import — so every imported clip lands in one flat
bin regardless of which track it came from. `pipeline/organize_davinci_bins.py` is a companion
script that sorts them afterward, using Resolve's own Python Scripting API (**DaVinci Resolve
Studio only** — the scripting API isn't available in the free edition). Run it from inside
Resolve, after importing `timeline.otio` into the project you want organized:

1. Open the project in Resolve, with `timeline.otio` already imported.
2. **Workspace → Console**, switch to the **Py3** tab.
3. `exec(open("/path/to/poiesis/pipeline/organize_davinci_bins.py").read())`

This groups clips already in the media pool's root bin into `Presenter`/`Titles`/`Captions`/
`Moments`/`Images`/`Beats` subfolders (only creating one for element types actually present),
keyed off the clip filename convention `export_davinci.py` already writes
(`{scene_type}-{scene_id}.mov`) — it doesn't read the OTIO timeline at all, and never touches
`scene-plan.json`, same one-directional (Poiesis → Resolve) data flow as the export itself.
Safe to re-run after importing more clips into the same project — already-sorted clips are
left where they are.

## Background removal (optional, not part of the default pipeline)

If your footage is shot on a physical green screen, `key_footage.py` chroma-keys each clip
into an alpha-matted WebM and points the renderer at the keyed version instead of the raw
footage. It's **not** wired into `run_pipeline.py` — even with tuned encoder settings it takes
roughly as long as the episode itself to key every clip, so it's a deliberate opt-in step
rather than something that slows down every pipeline run:

```bash
python3 pipeline/key_footage.py /path/to/episode
```

This writes `processing/keyed/<id>.webm` per clip, records `keyedPath`/`keyedRenderPath` on
each video in `manifest.json`, and regenerates `episode-props.ts` so Remotion picks up the
keyed clips automatically. Like other stages, it skips clips that are already keyed unless
you pass `--force` — episodes keyed before `CHROMA_BLEND`/`DESPILL_MIX` were widened need
`--force` to pick up the softer edges. Known limitations: `chromakey`'s single-threshold model
can't fully match a dedicated matte-refinement keyer (e.g. CapCut/Resolve) — flyaway hair
strands are softer than before but still not a true edge-aware alpha matte, and green spill on
hair/skin under strong lighting isn't always fully eliminated by the despill pass.

## Transcribing footage

`transcribe_footage.sh` can also be run standalone against an episode folder that already has
a `processing/manifest.json` (i.e. after `prepare_footage.py` has run):

```bash
./transcribe_footage.sh /path/to/project
```
