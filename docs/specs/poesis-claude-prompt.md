# Claude Prompt — Poesis: One-Click AI Video Editing with DaVinci-Ready Output

You are helping me architect and implement **Poesis**, an AI-powered tool whose goal is to reduce approximately 18 hours of manual YouTube video editing to roughly 30–60 minutes of human review and final polish.

## Product Goal

Poesis should be a **one-click video editing system**:

> Give Poesis the script, footage, voice-over, assets, and desired style → Poesis makes the editorial decisions → Poesis produces a nearly finished DaVinci Resolve project → the human performs only the final creative corrections and polish.

The important distinction is:

**Poesis should NOT simply render one final MP4.**

Instead, it should generate a **DaVinci-editable project with the appropriate level of granularity for each element**.

The user should not have to manually decide what needs to remain editable. **Poesis should make that decision automatically.**

---

## Core Architectural Principle

Think of Poesis as an **AI editorial engine**, not primarily a video renderer.

The desired architecture is:

```text
                    POESIS
                       │
               AI Editorial Engine
                       │
                       ▼
              Poesis Timeline Model
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      Timeline      Fusion       Rendered
      elements     templates     assets
          │            │            │
          └────────────┼────────────┘
                       ▼
                DaVinci Resolve
                       │
                       ▼
                  Final polish
                       │
                       ▼
                  YouTube master
```

The **Poesis Timeline Model** should be the canonical internal representation.

It should not be tightly coupled to a specific rendering technology.

---

## Semantic Granularity

The central design principle is:

> **Every meaningful editorial decision should remain editable, but not every implementation detail needs to be editable.**

Do NOT attempt to make every pixel, animation node, particle, easing curve, etc. independently editable.

Instead, use semantic editing primitives.

For example:

```text
Clip
Text
Graphic
Audio
Transition
Marker
FusionTemplate
RenderedAsset
```

Poesis should determine the appropriate representation for each element.

---

## Granularity Rules

Use approximately these rules:

| Element | Preferred Poesis output |
|---|---|
| Camera cuts | Native timeline elements |
| Video clips | Native timeline clips |
| B-roll | Separate timeline clips |
| Voice-over | Separate audio track |
| Music | Separate audio track |
| SFX | Separate audio clips |
| Subtitles | Editable text |
| Basic titles | Editable text / Fusion template |
| Lower thirds | Fusion template |
| Simple animations | Native/keyframed or Fusion template |
| Complex motion graphics | Fusion template or rendered asset |
| AI-generated B-roll | Independent video clip |
| Complex 3D animation | Rendered asset |
| Complex infographic | Rendered asset or Fusion template |
| Color grading | Leave for DaVinci |
| Final audio mastering | Leave for DaVinci |
| Final creative decisions | Leave for human |

The exact implementation can evolve, but this semantic distinction should remain.

---

## Example

Suppose Poesis decides that at 01:32 the video needs:

> "3 reasons why Java virtual threads matter"

Do NOT flatten this into the camera footage:

```text
camera + text + animation = one MP4
```

Instead, represent it approximately as:

```text
01:32 ─────────────── 01:39

VIDEO 1
[Camera footage]

VIDEO 2
[Graphic / animation]

TEXT / FUSION
[3 reasons why Java virtual threads matter]

AUDIO
[Voice-over]

SFX
[Whoosh]
```

The editor should be able to:

- change the text
- change timing
- move the graphic
- replace the graphic
- disable the graphic
- change its style
- change its duration

without rebuilding the entire video.

---

## Use DaVinci Resolve as the Final Editorial Environment

DaVinci Resolve should be treated as the professional final editing environment.

Poesis should generate a project/timeline that opens in Resolve and is already approximately finished.

The human should primarily do:

- correcting bad AI decisions
- replacing a bad shot
- adjusting B-roll
- changing graphic timing
- changing typography
- tweaking animations
- color grading
- audio mixing
- final creative decisions

The human should NOT spend hours doing:

- manually cutting every clip
- manually syncing captions
- manually adding every lower third
- manually searching and inserting every B-roll shot
- manually arranging music
- manually adding SFX
- manually building repetitive graphics
- manually constructing the basic timeline

That is Poesis's job.

---

## Remotion's Role

Do not necessarily eliminate Remotion.

Instead, treat Remotion as a **visual asset generation engine**, not as the replacement for DaVinci Resolve.

Use Remotion where it is particularly strong:

- complex animated charts
- data visualizations
- sophisticated motion graphics
- dynamic graphical sequences
- custom animations
- programmatically generated visuals

A useful conceptual architecture is:

```text
Poesis
  │
  ├── simple title ─────────────► Resolve/Fusion template
  │
  ├── lower third ──────────────► Resolve/Fusion template
  │
  ├── complex visualization ────► Remotion render
  │                                  │
  │                                  ▼
  │                            transparent asset
  │
  ├── AI B-roll ─────────────────► video asset
  │
  └── camera footage ────────────► original media
```

The key is that even rendered assets should normally be **independent timeline objects**, not baked permanently into the entire video.

---

## One-Click UX

The desired user experience should be approximately:

```text
                 GENERATE VIDEO
                       │
                       ▼
               ┌──────────────┐
               │ Analyze input │
               └──────┬───────┘
                      ▼
               Analyze footage
                      ▼
               Transcribe speech
                      ▼
               Select best takes
                      ▼
               Build narrative
                      ▼
               Remove dead time
                      ▼
               Select B-roll
                      ▼
               Generate graphics
                      ▼
               Generate animations
                      ▼
               Add captions
                      ▼
               Arrange music
                      ▼
               Add SFX
                      ▼
               Build timeline
                      ▼
            Prepare DaVinci project
                      ▼
              OPEN IN DAVINCI
```

The user should not need to understand the internal distinction between native timeline elements, Fusion templates, and rendered assets.

**Poesis makes that decision.**

---

## Internal Timeline Model

Design a canonical internal model that represents editorial intent.

For example, conceptually:

```json
{
  "timeline": [
    {
      "start": 0,
      "duration": 4.2,
      "type": "video",
      "asset": "camera_001.mov"
    },
    {
      "start": 4.2,
      "duration": 3.0,
      "type": "broll",
      "asset": "broll_001.mp4"
    },
    {
      "start": 4.2,
      "duration": 3.0,
      "type": "title",
      "text": "Why Virtual Threads Matter"
    }
  ]
}
```

This is only illustrative.

Do not blindly adopt this exact JSON structure.

Design a proper domain model around semantic editorial concepts.

The model should eventually be able to express:

- source media
- timeline tracks
- clips
- in/out points
- transitions
- audio
- captions
- text
- graphics
- Fusion templates
- rendered assets
- keyframes
- markers
- metadata
- editorial rationale
- confidence
- asset provenance
- style/theme information

---

## Preserve Editorial Intent

A particularly important idea is that Poesis should preserve **why** it made a decision.

For example:

```json
{
  "type": "broll",
  "start": 32.0,
  "duration": 4.5,
  "asset": "stock_042",
  "reason": "Illustrate database concurrency",
  "confidence": 0.91
}
```

Or:

```json
{
  "type": "lower-third",
  "text": "Java 21",
  "reason": "Introduce the technical concept"
}
```

Or:

```json
{
  "type": "camera_zoom",
  "start": 77.0,
  "from": 1.0,
  "to": 1.08,
  "reason": "Maintain visual movement during continuous speech"
}
```

This metadata does not necessarily need to be exposed to the final editor immediately.

However, it should exist in the internal model because it enables future functionality such as:

> "Regenerate this section."

or:

> "Make this section more dynamic."

or:

> "Replace the B-roll that was chosen only for illustrative purposes."

The AI should understand its own editorial decisions.

---

## Important Product Constraint

Do NOT optimize for:

> "100% of the video is editable at the lowest possible level."

That is the wrong objective.

Optimize for:

> **"The video is automatically edited while preserving control over the decisions an editor is likely to want to change."**

This is what allows Poesis to eliminate the majority of the 18-hour mechanical editing process without making the final result rigid.

---

## Proposed Output

The ideal output is something conceptually like:

```text
Poesis Output/
│
├── project/
│   └── Poesis.drp
│
├── media/
│   ├── camera/
│   ├── broll/
│   └── generated/
│
├── audio/
│   ├── voiceover/
│   ├── music/
│   └── sfx/
│
├── graphics/
│   ├── fusion/
│   └── rendered/
│
└── metadata/
    └── timeline.json
```

The exact structure is up to you.

The key requirement is that the final DaVinci project contains the correct timeline structure and references the necessary assets.

---

# What I Want You to Do

Analyze the current Poesis architecture and propose how to evolve it toward this model.

I want a **practical implementation plan**, not a theoretical discussion.

Specifically:

## 1. Analyze the Existing Architecture

Inspect the current codebase and identify:

- how video generation currently works
- where rendering happens
- how the timeline is represented
- how assets are represented
- how Claude/LLM decisions are represented
- where Remotion fits
- where FFmpeg fits
- what parts are currently flattened
- what parts could already become reusable timeline primitives

Do not assume the current architecture from this prompt; inspect the actual code.

## 2. Define the Canonical Poesis Timeline Model

Design the domain model that should sit between AI editorial decisions and output/rendering.

Explain:

- entities
- value objects
- relationships
- lifecycle
- serialization
- extensibility
- how to represent semantic elements
- how to represent editable vs rendered elements

Prefer a clean domain-oriented architecture rather than coupling the model directly to DaVinci.

## 3. Define the Output Strategy

Determine how Poesis should produce:

- DaVinci Resolve project/timeline
- Fusion templates
- rendered transparent assets
- video assets
- audio assets
- captions
- metadata

Identify what can realistically be generated automatically and what limitations exist in Resolve's APIs/import formats.

Do not invent capabilities.

If something requires experimentation, explicitly identify it as such.

## 4. Define the Rendering Boundary

Determine exactly when Poesis should:

- create a native timeline element
- create a Fusion template
- use Remotion
- use FFmpeg
- render a standalone asset
- leave something for DaVinci

Create clear decision rules that the implementation can eventually encode.

## 5. Design the One-Click Pipeline

Design the complete pipeline from:

```text
Input
→ analysis
→ editorial planning
→ asset selection/generation
→ timeline construction
→ graphics generation
→ audio arrangement
→ DaVinci project generation
→ validation
→ final project
```

Identify where AI is involved and where deterministic software should be used.

AI should make **editorial decisions**.

Deterministic code should execute those decisions reliably.

## 6. Define the Minimum Viable Version

Do NOT attempt to implement everything at once.

Identify the smallest architecture that can demonstrate:

> "Poesis can take a video and automatically produce a mostly finished, editable DaVinci timeline."

For example, determine whether V1 should support only:

- source video
- cuts
- B-roll
- voice-over
- music
- captions
- basic titles
- simple graphics

and defer complex Fusion/Remotion integration.

## 7. Define the Migration Path

Explain how to move from the current Poesis implementation to this architecture incrementally without rewriting the entire application.

Identify:

- files/modules likely to change
- new abstractions
- existing code that can be reused
- code that should eventually be removed
- intermediate milestones
- risks

## 8. Evaluate the "18 Hours → 30–60 Minutes" Objective

Be realistic.

Explain which portions of professional editing can plausibly be automated and which parts are likely to remain human-heavy.

The goal is not to claim magical 100% automation.

The goal is to maximize:

> **automatic mechanical/editorial work**

while preserving:

> **human creative control**

## 9. Recommend the Architecture

At the end, give me a concrete recommended architecture for Poesis.

Include:

- components/modules
- responsibilities
- data flow
- major interfaces
- timeline model
- rendering boundaries
- DaVinci integration strategy
- Remotion integration strategy
- testing strategy

Prefer a design that is simple enough to implement now but doesn't paint Poesis into a corner later.

---

# Engineering Principles

Follow these principles throughout the proposal:

1. **Domain model first.**
2. **AI decides; deterministic software executes.**
3. **DaVinci is the final professional editing environment.**
4. **Do not flatten the entire video.**
5. **Preserve semantic editorial decisions.**
6. **Use the appropriate granularity for each element.**
7. **Rendered assets are acceptable when they are independent and replaceable.**
8. **Do not expose unnecessary implementation complexity to the user.**
9. **One-click should remain the user experience even if the backend is sophisticated.**
10. **Prefer incremental migration over a complete rewrite.**
11. **Do not build an NLE inside Poesis.**
12. **Do not force every animation to be natively editable.**
13. **Make the final timeline inspectable and deterministic.**
14. **Design for reproducibility: the same editorial plan should produce the same timeline unless randomness is intentional.**
15. **Keep the canonical Poesis model independent from DaVinci, Remotion, and FFmpeg.**

---

# Final Deliverable

After inspecting the repository, provide:

1. **Current architecture assessment**
2. **Target architecture**
3. **Canonical timeline/domain model**
4. **Granularity decision system**
5. **DaVinci integration approach**
6. **Remotion/FFmpeg integration approach**
7. **One-click generation pipeline**
8. **MVP implementation plan**
9. **Incremental migration plan**
10. **Risks and technical unknowns**
11. **Concrete next coding steps**

Be opinionated.

If the current architecture is wrong, say so clearly.

If part of the proposed architecture is unnecessary, say so.

Do not over-engineer for hypothetical future requirements.

The ultimate success criterion is:

> **A user clicks "Export to DaVinci", waits, opens the result in DaVinci Resolve, and finds a professionally assembled video that is approximately 90–95% complete while retaining enough semantic editability that the remaining 5–10% can be polished quickly rather than rebuilt manually.**

# Output formats

Right now there is the option to click "Render" and produce a video output.
The final solution should modify the UI so that it gives the option to the user to select the output format, either a video with resolution options to choose from to export or to davinci forma
so that the user can just import the whole project to davinci.
The Solution should use the existing episode project folder for refencing all assets, animations, videos, images, music etc used and it should be 95% ready for the user
to give the final editing touches in da vinci. Not to edit everything but to polish the final result before choosing to export via davinci if they choose to do so.
IF they choose to render the video using poesis, then poesis will take over the rendering. But the user should have the option to select the output format.