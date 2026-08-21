# Poiesis — Resolve-Native Export Architecture

## Objective

Change Poiesis from a system that primarily renders a complete video through Remotion into a system that generates an editable DaVinci Resolve project/timeline.

The goal is:

1. Poiesis determines the complete video edit.
2. Poiesis preserves editability wherever possible.
3. Remotion is used only for visual elements that genuinely need pixel rendering.
4. DaVinci Resolve performs the final composition/render.
5. The resulting Resolve project should be editable by a human in DaVinci Resolve.

The core principle is:

> Do not render something in Remotion if the same result can be represented as editable Resolve timeline data, keyframes, media, masks, captions, or native Resolve properties.

---

# 1. Current Architecture

The current conceptual pipeline is:

Poiesis
    ↓
Video specification
    ↓
Remotion composition
    ↓
Render every frame
    ↓
Flattened MP4
    ↓
DaVinci Resolve
    ↓
Final edits

This causes unnecessary rendering.

For example, if the talking-head video moves horizontally, Remotion currently renders every frame with the new position even though the movement can be represented as Resolve transform keyframes.

The same principle applies to many other effects.

---

# 2. Target Architecture

The target architecture is:

Poiesis
    ↓
Canonical Video Timeline Model
    ↓
Resolve Exporter
    ├── source media
    ├── timeline clips
    ├── tracks
    ├── transform keyframes
    ├── opacity keyframes
    ├── audio
    ├── captions
    ├── masks/mattes where supported
    └── rendered visual assets only where necessary
    ↓
DaVinci Resolve
    ↓
Human editing / final adjustments
    ↓
Final render

Remotion becomes an asset renderer rather than the mandatory final compositor.

---

# 3. Core Architectural Principle

Every visual operation must be classified into one of three categories.

## Category A — Resolve-native

Do not render.

Represent the operation directly in the Resolve timeline/project.

Examples:

- clip placement
- clip trimming
- cuts
- position
- scale
- rotation
- opacity
- transform animation
- simple fades
- audio volume
- audio positioning
- timeline timing
- basic transitions
- simple text where practical
- captions/subtitles where practical

---

## Category B — Source + metadata/data

Do not render the final composited result.

Provide Resolve with the source media plus additional data required to reproduce the effect.

Examples:

- background-removal matte
- masks
- tracking data
- caption timing
- metadata
- animation/keyframe data
- externally generated masks

Where possible, Resolve should perform the final compositing.

---

## Category C — Rendered asset

Use Remotion only when the effect cannot reasonably be represented in Resolve.

Examples:

- complex animated diagrams
- complex SVG animations
- sophisticated code animations
- custom shader effects
- particle systems
- highly complex multi-element animations
- visual effects for which no practical Resolve representation exists

These should be rendered as independent assets, preferably with transparency where appropriate.

They must NOT be composited with unrelated video in Remotion unless necessary.

---

# 4. Canonical Timeline Model

Poiesis must have an internal timeline representation that is independent of Remotion and independent of DaVinci Resolve.

The timeline model is the source of truth.

Conceptually:

Project
    ├── Settings
    ├── Assets
    ├── Scenes
    └── Tracks

Scene
    ├── start
    ├── duration
    ├── clips
    ├── overlays
    ├── captions
    ├── audio
    └── effects

Clip
    ├── sourceAsset
    ├── timelineStart
    ├── timelineDuration
    ├── sourceStart
    ├── sourceDuration
    ├── transform
    ├── opacity
    └── effects

Transform
    ├── position
    ├── scale
    ├── rotation
    └── keyframes

---

# 5. Example Timeline

Example conceptual Poiesis timeline:

Scene 12

Start:
42.0 seconds

Duration:
8.0 seconds

Video:
    talking-head.mp4

Talking head:
    position:
        42.0s -> x=600
        44.0s -> x=0
        47.0s -> x=-300
        50.0s -> x=0

    scale:
        42.0s -> 1.0
        50.0s -> 1.0

Overlay:
    architecture-diagram

    start:
        47.0s

    duration:
        2.5s

Captions:
    start:
        42.0s

    end:
        50.0s

The timeline model should contain this information without knowing whether the final output is:

- Resolve
- Remotion
- MP4
- another editor

---

# 6. Talking-Head Movement

Talking-head movement MUST NOT be rendered by Remotion when the movement can be represented using Resolve transforms.

Example:

The desired behavior:

- talking head starts on the right
- moves to center
- moves left when a diagram appears
- returns to center

Instead of rendering:

talking-head + movement + background + overlays

Poiesis should export:

talking-head.mp4

plus Resolve transform keyframes.

Example:

Transform keyframes:

00:00:
    X = +600
    Y = 0
    Scale = 1.0

00:02:
    X = 0
    Y = 0
    Scale = 1.0

00:08:
    X = -300
    Y = 0
    Scale = 1.0

00:15:
    X = -300
    Y = 0
    Scale = 1.0

00:20:
    X = 0
    Y = 0
    Scale = 1.0

DaVinci Resolve performs the interpolation.

This makes the movement editable after export.

---

# 7. Background Removal

Background removal must be separated from compositing.

Do NOT automatically render:

talking-head + removed-background + background + animations

into a single video.

Investigate these strategies in this order.

## Strategy A — Resolve-native background removal

If the desired background-removal effect can be reproduced using DaVinci Resolve's native capabilities, prefer this.

Poiesis should configure Resolve to perform the effect.

Advantages:

- editable
- no additional rendered asset
- Resolve controls the final result
- user can modify it later

---

## Strategy B — External matte

If Poiesis uses a better background-removal algorithm than Resolve, generate a matte separately.

Conceptually:

talking-head.mp4
    +
person-matte
    ↓
DaVinci Resolve
    ↓
composite

The matte represents which pixels belong to the person.

The original talking-head video remains untouched.

The matte can be:

- a grayscale video
- an alpha-capable asset
- an image sequence
- another Resolve-compatible mask representation

The exact implementation must be selected based on what Resolve can reliably import and use.

---

## Strategy C — Transparent rendered video

If a matte-based workflow is impractical, render the talking head with transparency as an independent asset.

Use a codec/container that preserves alpha and is practical for Resolve.

The transparent talking-head asset can then be placed above the background in Resolve.

This is still preferable to rendering the entire scene because:

- movement remains potentially editable
- background remains editable
- other overlays remain editable
- the asset can be cached
- the talking head does not need to be re-rendered when unrelated elements change

---

# 8. Animation Strategy

Every animation must be classified.

## Simple animation

If an animation can be represented using Resolve properties, export keyframes.

Examples:

- position
- scale
- rotation
- opacity
- simple fades
- simple movement
- basic zoom
- simple entrance/exit

Do not render these through Remotion.

---

## Complex animation

If an animation consists of complex generated visuals that cannot reasonably be reconstructed in Resolve, render it using Remotion.

Example:

architecture-diagram.mov

Requirements:

- render only the animation
- do not include unrelated video
- use transparency when appropriate
- cache the result
- insert the resulting asset into its own Resolve track

---

# 9. Transparent Animation Assets

Complex animations that need to appear over existing video should preferably be rendered with transparency.

Example:

talking-head.mp4
    ↓
Resolve V2

architecture-animation.mov
    ↓
Resolve V3

captions
    ↓
Resolve V4

Resolve performs the final composite.

The animation should NOT be rendered together with the talking head.

---

# 10. Code Animations

Code animations are likely to be one of the main Remotion-rendered assets.

Example:

code-animation-001.mov

The animation should be:

- independently rendered
- cached
- transparent when appropriate
- placed on its own Resolve track
- positioned/timed using Resolve where possible

If the code animation itself contains internal movement that cannot be represented by Resolve, that internal movement may remain baked into the rendered asset.

However, its:

- timeline position
- scale
- overall position
- opacity

should remain editable in Resolve.

---

# 11. Captions

Captions should not normally be rendered into the video.

Poiesis should export caption information in a format that Resolve can import or create as timeline caption/subtitle objects.

The caption data should contain:

- text
- start time
- end time
- optionally speaker
- optionally style information

Example:

00:42.100
"This is an example"

00:43.800
"of the architecture"

The user should be able to modify the captions in Resolve.

If a particular visual caption animation cannot be represented natively, that specific animation may be rendered separately.

---

# 12. Titles

Titles should remain editable wherever practical.

Preferred:

Poiesis
    ↓
Resolve title/text object

Fallback:

Poiesis
    ↓
transparent rendered title asset

Avoid baking titles into the talking-head video.

---

# 13. B-Roll

B-roll should remain source media.

Poiesis should create timeline clips referencing the original B-roll assets.

It should specify:

- source asset
- source in-point
- source out-point
- timeline position
- timeline duration
- transform
- opacity
- transitions

Do not render B-roll into the final video.

---

# 14. Audio

Audio should remain separate.

Examples:

- voice
- music
- sound effects
- ambience

Poiesis should place these on separate Resolve audio tracks.

Audio should not be unnecessarily re-rendered through Remotion.

The Resolve timeline should preserve:

- clip timing
- trims
- volume
- fades
- track assignment

---

# 15. Asset Cache

Poiesis must implement deterministic caching for rendered assets.

Every generated asset should have an identity based on its meaningful inputs.

Example:

Asset:

architecture-diagram

Inputs:

- diagram data
- animation parameters
- resolution
- frame rate
- renderer version

Generate:

assetHash = SHA256(inputs)

Cache:

.cache/
    architecture/
        abc123.mov

If the exact same asset is needed again:

Do not render it.

Reuse the cached asset.

---

# 16. Cache Invalidation

A rendered asset must only be invalidated when an input that affects the visual result changes.

For example:

Changing:

- talking-head position

must NOT invalidate:

- diagram animation

Changing:

- caption text

must NOT invalidate:

- talking-head render

Changing:

- diagram contents

should invalidate:

- diagram render

This is critical.

The system should avoid unnecessary Remotion renders.

---

# 17. Resolve Exporter

Implement a dedicated Resolve exporter.

The exporter takes:

Canonical Video Timeline Model

and produces:

DaVinci Resolve project/timeline

The exporter must be independent of Remotion.

Conceptually:

TimelineModel
    ↓
ResolveExporter
    ↓
Resolve Project

Do not construct the Resolve project from the final MP4.

The Resolve project should be constructed directly from the canonical timeline model.

---

# 18. Resolve Track Structure

The exporter should create meaningful tracks.

Example:

Video:

V1:
    background

V2:
    talking head

V3:
    B-roll

V4:
    diagrams

V5:
    code animations

V6:
    titles

V7:
    captions

Audio:

A1:
    voice

A2:
    music

A3:
    sound effects

The exact track ordering should be configurable.

---

# 19. Timeline Positioning

All timeline operations must use a consistent time representation internally.

Prefer frame-based precision internally for deterministic video editing.

The canonical timeline should know:

- FPS
- resolution
- timeline start
- frame numbers
- duration in frames

Avoid accumulating floating-point timing errors.

Example:

timeline FPS = 30

00:10.000 = frame 300

00:20.000 = frame 600

---

# 20. Remotion's New Role

Remotion should NOT be removed.

Instead, redefine its responsibility.

Remotion becomes:

"Render complex visual assets that cannot reasonably be represented natively in Resolve."

It should not automatically receive the entire video composition.

Avoid:

Poiesis
    ↓
one huge Remotion composition
    ↓
entire video render

Prefer:

Poiesis
    ↓
timeline model
    ↓
asset dependency analysis
    ↓
render only required assets
    ↓
Resolve timeline

---

# 21. Preview Rendering

The new architecture should also improve previews.

Poiesis should be able to preview the timeline without rendering the entire final composition through Remotion.

For example:

- Resolve can be used as the final compositor.
- Individual Remotion assets can be previewed independently.
- Cached assets should be reused.
- Only changed assets should be rendered.

The goal is to make an edit change such as:

"Move the talking head 200px left"

require:

NO Remotion render.

Only the Resolve timeline/keyframes need to change.

---

# 22. Example End-to-End Scenario

User records a 10-minute talking-head video.

Poiesis analyzes the video and determines:

1. Talking head occupies center.
2. At 01:20, talking head moves left.
3. Architecture diagram appears on the right.
4. At 01:28, talking head returns to center.
5. At 02:10, a code animation appears.
6. Captions run throughout.
7. Background is removed.
8. Music plays underneath.

The old architecture would do:

talking head
    +
background removal
    +
movement
    +
diagram
    +
code animation
    +
captions
    +
music
    ↓
Remotion
    ↓
10-minute rendered video

The new architecture should do:

talking-head.mp4
    ↓
Resolve V2
    ↓
position keyframes

background removal
    ↓
Resolve-native effect OR external matte

architecture-diagram
    ↓
Remotion
    ↓
architecture.mov
    ↓
Resolve V4

code-animation
    ↓
Remotion
    ↓
code.mov
    ↓
Resolve V5

captions
    ↓
Resolve caption track

music
    ↓
Resolve A2

voice
    ↓
Resolve A1

Everything is assembled in Resolve.

---

# 23. Expected Performance Improvement

The goal is not necessarily to make Remotion itself render faster.

The goal is to dramatically reduce the amount of work that Remotion has to perform.

For example:

Before:

10-minute video
    ↓
18,000 frames at 30 FPS
    ↓
Remotion renders every frame

After:

10-minute video
    ↓
Resolve timeline
    │
    ├── original talking-head media
    ├── original B-roll
    ├── audio
    ├── captions
    ├── transform keyframes
    ├── masks
    └── only complex animations rendered by Remotion

Remotion might only render:

- 20-second diagram
- 15-second code animation
- 5-second custom animation

instead of the entire 10-minute video.

This is the intended optimization.

---

# 24. Priority Order

Implement in this order.

## Phase 1 — Canonical timeline model

Create a renderer-independent timeline representation.

Do not make Remotion the source of truth.

---

## Phase 2 — Resolve timeline export

Implement creation of:

- project
- timeline
- media pool/assets
- video tracks
- audio tracks
- clips
- timing
- trims

---

## Phase 3 — Transform keyframes

Export:

- position
- scale
- rotation
- opacity

This immediately eliminates many unnecessary Remotion renders.

---

## Phase 4 — Separate visual assets

Modify Remotion rendering so it can render:

- diagram
- code animation
- title animation
- other complex overlays

as independent assets.

---

## Phase 5 — Transparency

Add alpha-capable rendering for visual overlays.

---

## Phase 6 — Background removal

Evaluate:

1. Resolve-native background removal
2. external matte
3. transparent rendered asset

Select the best implementation based on quality, performance, and Resolve compatibility.

---

## Phase 7 — Captions

Export captions as editable Resolve timeline data rather than baked pixels.

---

## Phase 8 — Asset caching

Implement deterministic hashes and cache rendered assets.

---

## Phase 9 — Incremental regeneration

When the AI modifies the project:

1. calculate which timeline elements changed
2. invalidate only affected assets
3. rerender only invalidated Remotion assets
4. regenerate/update the Resolve timeline
5. preserve unchanged assets

---

# 25. Non-Goals

Do NOT optimize the project primarily by:

- simply increasing Remotion concurrency
- rendering the entire video faster
- increasing CPU usage
- producing a better flattened MP4

Those may still be useful optimizations, but they are secondary.

The primary optimization is:

> Reduce the number of frames that Remotion needs to render at all.

---

# 26. Architectural Rule

Whenever implementing a new Poiesis visual feature, ask:

1. Can Resolve represent this natively?
2. Can it be represented as timeline data?
3. Can it be represented as keyframes?
4. Can it be represented as source media + mask/matte?
5. If not, can only the visual element be rendered independently?
6. Only as a last resort: should the entire composition be rendered?

The default answer should be:

> Preserve editability and defer composition to DaVinci Resolve.

---

# 27. Success Criteria

The implementation is successful when the following workflow is possible:

1. User provides talking-head footage.
2. Poiesis generates the edit.
3. Poiesis identifies required visual assets.
4. Poiesis renders only complex assets through Remotion.
5. Poiesis caches those assets.
6. Poiesis generates a DaVinci Resolve project/timeline.
7. Resolve opens with:
   - talking head on its own track
   - B-roll on its own tracks
   - animations on their own tracks
   - captions editable
   - audio separated
   - talking-head movement represented by keyframes
   - backgrounds editable
   - complex animations already rendered as independent assets
8. User can continue editing everything in Resolve.
9. Changing a transform does not trigger a Remotion render.
10. Changing an unrelated scene does not trigger rendering of unchanged assets.
11. Re-running Poiesis reuses cached rendered assets whenever their inputs have not changed.

The final product should feel like:

"Poiesis automatically edited my video and handed me a fully structured DaVinci Resolve project."

Not:

"Poiesis rendered a video and imported it into DaVinci."