# Poiesis — Claude Project Instructions

## Purpose

Poiesis is an AI-assisted video production tool for turning raw talking-head footage into polished software-engineering YouTube videos.

The goal is **not** to build another general-purpose video editor.

The goal is to build a **personal AI video-production system** that understands my scripts, footage, visual style, and reusable video components, and automates as much of the repetitive editing work as possible.

Poiesis should allow me to go from:

> "I recorded the episode."

to:

> "I have a polished video ready for final review."

with as little manual editing as possible.

---

# Vision

I create software-engineering videos where I talk directly to the camera, usually for 10–15 minutes.

The videos typically contain:

- Talking-head footage with background removal
- Animated backgrounds
- Intro and outro sequences
- Animated titles
- Important phrases appearing on screen
- Code snippets
- Diagrams
- Images and screenshots
- B-roll
- Captions
- Transitions
- Subtle animations
- Music and sound effects

Today, producing this kind of video manually can take many hours even when the recorded footage is already good.

Poiesis should automate both the **mechanical** and **creative** editing decisions that can reasonably be automated by AI.

The human should remain the director.

The AI should be the editor.

---

# Core Product Principle

Poiesis is **not a traditional nonlinear video editor**.

It should not attempt to reproduce:

- Premiere Pro
- Final Cut Pro
- DaVinci Resolve
- CapCut

The primary interaction should not be:

> Drag clips around a timeline until the video looks right.

Instead, it should be:

> Give Poiesis the footage and script, let AI construct an edit plan, review the decisions, make corrections through natural language, and render the result.

The central artifact is therefore the **semantic edit plan**, not a traditional timeline.

---

# Target Workflow

The intended workflow is:

    RAW FOOTAGE
         |
         v
    INGESTION
         |
         v
    TRANSCRIPTION
         |
         v
    SEGMENT ANALYSIS
         |
         v
    AI EDITING PLAN
         |
         v
    HUMAN REVIEW
         |
         +----------------+
         |                |
      approve          ask AI to
                       modify
         |                |
         +-------+--------+
                 |
                 v
             REMOTION
                 |
                 v
              RENDER
                 |
                 v
                QA
                 |
                 v
            FINAL VIDEO

The ideal experience is:

1. Record the episode.

2. Drop the footage into Poiesis.

3. Poiesis transcribes and understands the footage.

4. Claude creates an initial edit plan.

5. Poiesis renders a preview.

6. I review the video.

7. I tell the AI things like:

    - "Remove this pause."
    - "Make this section more engaging."
    - "Show the code when I mention the implementation."
    - "Replace this text animation with a diagram."
    - "Move the title earlier."

8. Claude modifies the edit plan.

9. Poiesis renders again.

10. I approve the final video.

The objective is to make the final human review take **minutes rather than hours**.

---

# Existing Codebase

Poiesis already contains useful infrastructure for this workflow.

**Do not throw away the existing codebase simply because some parts of the UI or editor are difficult to maintain.**

The existing architecture should be treated as the foundation and evolved toward the vision described in this document.

Existing useful capabilities include:

- Video ingestion
- Footage preparation
- Transcription
- Segment extraction
- Segment normalization
- LLM integration
- Remotion-based rendering
- Video composition
- Processing pipelines

These components should be preserved and refactored where necessary.

The project should evolve incrementally rather than being rewritten from scratch.

Before replacing an existing component, determine:

1. What responsibility it currently has.
2. Whether that responsibility is still needed.
3. Whether the component can be simplified.
4. Whether it belongs in the new architecture.
5. Whether replacing it would actually improve the product.

Do not rewrite working infrastructure merely because a new architecture looks cleaner.

---

# The Semantic Edit Plan

The most important architectural concept in Poiesis is the **Edit Plan**.

The AI should not directly manipulate pixels or a traditional timeline.

Instead, it should produce a structured representation of what the video should contain.

Conceptually:

    {
      "scenes": [
        {
          "type": "presenter",
          "source": "03.mp4",
          "start": 0,
          "end": 18
        },
        {
          "type": "title",
          "text": "What Is Encapsulation?",
          "start": 18,
          "end": 23
        },
        {
          "type": "concept",
          "concept": "encapsulation",
          "start": 23,
          "end": 38
        },
        {
          "type": "code",
          "language": "java",
          "source": "examples/encapsulation.java",
          "start": 38,
          "end": 52
        }
      ]
    }

This is illustrative rather than a required schema.

The exact domain model should evolve with the project.

The important principle is:

> **AI decisions should be represented as structured, inspectable data.**

This makes the system:

- Deterministic where possible
- Testable
- Editable
- Debuggable
- Renderable
- Versionable
- Understandable by humans and AI agents

The Edit Plan should be the boundary between **AI reasoning** and **video rendering**.

---

# AI Responsibilities

Claude should be responsible primarily for **creative and semantic decisions**.

## Understand the Content

Claude should be able to:

- Understand the script
- Understand the transcript
- Identify topics
- Identify sections
- Identify important concepts
- Identify key phrases
- Understand technical explanations
- Understand the intended narrative

## Decide the Edit

Claude should eventually be able to:

- Select good takes
- Remove obvious mistakes
- Identify unnecessary pauses
- Identify repeated or redundant sections
- Decide where visual changes are useful
- Decide when text should appear
- Decide when code should appear
- Decide when diagrams are useful
- Decide when screenshots or images would help
- Decide when the presenter should remain on screen
- Decide when to change the visual composition
- Decide which reusable visual component should be used

## Improve Engagement

The AI should look for sections where the visual presentation becomes monotonous.

For example:

> 20 seconds of talking head with no visual change

might become:

    Presenter
        |
        v
    Important phrase
        |
        v
    Animated concept
        |
        v
    Presenter
        |
        v
    Code example

The objective is **not** to add animations everywhere.

The objective is to add meaningful visual changes where they improve comprehension or engagement.

Avoid "AI slop" where every sentence gets an animation.

Visual changes should have a reason.

---

# Deterministic Video Processing

LLMs should not be responsible for operations that can be implemented deterministically.

Use conventional video-processing tools for things such as:

- Cutting
- Concatenation
- Encoding
- Audio normalization
- Silence removal
- Resolution changes
- Format conversion
- Frame extraction
- Audio extraction
- Media inspection

FFmpeg should be used where appropriate.

Other specialized tools can be introduced when necessary.

The principle is:

> **Use AI for judgment. Use software for execution.**

Do not ask an LLM to perform deterministic media-processing work that can be handled reliably by normal software.

---

# Remotion

Remotion is the primary rendering and composition engine.

Remotion should remain responsible for:

- Video composition
- Presenter placement
- Backgrounds
- Text
- Captions
- Code blocks
- Diagrams
- Animations
- Transitions
- Images
- Screenshots
- Reusable visual components
- Intro
- Outro

The visual language of the channel should be implemented as a reusable **video component system**.

Conceptually, the system may contain components such as:

    <Presenter />

    <AnimatedTitle />

    <ImportantPhrase />

    <CodeBlock />

    <ConceptDiagram />

    <Comparison />

    <Callout />

    <Quote />

    <Caption />

The exact component architecture should be determined by the existing codebase and evolving requirements.

The AI should compose these components rather than inventing a completely new visual system for every episode.

---

# Channel Editing Style

Poiesis is initially designed for a specific software-engineering YouTube channel.

The editing style should therefore be treated as a **design system**.

The system should eventually encode rules such as:

- Presenter remains visually prominent.
- Do not obscure the presenter unnecessarily.
- Use visual changes to support the explanation.
- Do not animate every sentence.
- Important concepts deserve stronger visual treatment.
- Technical concepts should often use diagrams or code.
- Code should be readable.
- Text should be concise.
- Animations should feel intentional rather than distracting.
- Maintain a consistent visual identity between episodes.
- Reuse established animation patterns.
- Intro and outro should remain consistent.

These rules should live in project documentation/configuration that Claude can inspect.

The AI should learn the editing style from:

1. Explicit editing rules.
2. Existing Remotion components.
3. Existing visual assets.
4. Previous episodes where available.
5. Human corrections and feedback.

The goal is for Poiesis to become increasingly consistent with my personal editing style.

---

# Human-in-the-Loop

Poiesis should not attempt to remove the human from the creative process.

The intended relationship is:

    Human
      |
      | provides
      v
    Content + intent + style
      |
      v
    AI
      |
      | proposes
      v
    Edit Plan
      |
      v
    Human
      |
      | reviews / corrects
      v
    Final Edit Plan
      |
      v
    Remotion
      |
      v
    Video

The human should be able to override AI decisions easily.

Natural-language editing should eventually be a first-class interaction.

Examples:

> "Cut the first 2 seconds."

> "Use a diagram here."

> "Make this section faster."

> "Remove this animation."

> "Show me full screen during this explanation."

> "Use the same animation as the previous episode."

> "This section is too visually busy."

The AI should modify the structured edit plan rather than directly manipulating rendered video.

---

# Editor UI

A traditional timeline editor is **not the primary goal**.

A lightweight review interface is preferable.

The UI should allow the user to:

- Preview the rendered video
- Inspect scenes
- Inspect source footage
- See the edit plan
- Approve or reject AI decisions
- Make simple corrections
- Ask Claude for changes
- Re-render previews

A timeline may exist as a visualization or convenience, but it should not become the architectural center of the application.

## Important

Do not spend large amounts of development effort turning Poiesis into a full nonlinear editor.

If an editor feature does not directly help the user review or correct an AI-generated edit, question whether it is necessary.

The goal is not to compete with professional video-editing software.

The goal is to automate professional-looking video production.

---

# AI Provider Architecture

The AI layer should be abstracted from the rest of the application.

Claude should be the primary high-quality reasoning model.

Local models can be used for cheaper or mechanical tasks where appropriate.

Conceptually:

    LLM
    ├── Claude
    ├── Local model
    └── Other providers

The core domain should not depend directly on one specific LLM provider.

Use the most capable model for creative editing decisions and cheaper/local models for tasks where sophisticated reasoning is unnecessary.

The architecture should make it possible to change the model without changing the video-production domain.

---

# Processing Pipeline

The pipeline should evolve toward clearly separated stages:

    INGEST
       |
       v
    PREPARE
       |
       v
    TRANSCRIBE
       |
       v
    SEGMENT
       |
       v
    UNDERSTAND
       |
       v
    PLAN
       |
       v
    REVIEW
       |
       v
    RENDER
       |
       v
    QA
       |
       v
    EXPORT

Each stage should have a well-defined responsibility and preferably produce an inspectable artifact.

Potential artifacts include:

    transcript.json
    segments.json
    analysis.json
    edit-plan.json
    render.mp4
    qa-report.json

This allows both humans and AI agents to understand the current state of an episode.

Intermediate artifacts should be useful for debugging and should not be hidden inside opaque application state.

---

# Quality Assurance

The system should eventually be able to automatically inspect its own output.

Potential checks include:

- Video duration
- Missing media
- Audio/video synchronization
- Black frames
- Broken assets
- Text outside the viewport
- Overlapping elements
- Caption timing
- Presenter visibility
- Rendering errors
- Unexpected scene transitions

The pipeline should support an iterative process:

    render
       |
       v
    inspect
       |
       v
    detect problems
       |
       v
    modify edit plan
       |
       v
    render again

This creates an iterative AI editing loop rather than a one-shot generation process.

---

# Non-Goals

Poiesis should **not** become:

- A Premiere Pro clone
- A Final Cut clone
- A DaVinci Resolve clone
- A generic video editor
- A social-media video editor
- A fully autonomous AI filmmaker
- A complex multi-track timeline application

The goal is much narrower:

> **Automate the production of polished software-engineering YouTube videos using my existing footage, scripts, visual components, and editing style.**

---

# Design Principles

## 1. Preserve the Existing Codebase

Prefer incremental evolution over rewriting.

Existing working functionality is valuable.

Before replacing something, understand why it exists and whether it can be adapted.

## 2. Keep the Domain Model Clean

Do not allow UI concerns to leak into the core video-production model.

The Edit Plan should be independent of the UI.

The renderer should consume the Edit Plan rather than depending on UI state.

## 3. AI Should Produce Decisions, Not Opaque Side Effects

Prefer:

    AI
      |
      v
    Structured Plan
      |
      v
    Deterministic Execution

over:

    AI
      |
      v
    Random collection of video operations

The AI's decisions should be explicit and inspectable.

## 4. Everything Should Be Inspectable

An engineer should be able to understand:

> Why did Poiesis create this video?

by inspecting the intermediate artifacts and edit plan.

## 5. Prefer Reusable Components

If an animation is useful once, consider making it reusable.

The visual system should become more powerful with every episode.

The goal is to build a growing library of reusable video primitives.

## 6. Optimize for Iteration

A bad AI edit is not a failure.

The system should make it extremely cheap to say:

> "No, change this."

and produce another version.

## 7. Optimize for My Time

The ultimate metric is not:

> How sophisticated is the editor?

It is:

> **How much time do I spend between recording the footage and uploading the video?**

Every architectural and product decision should ultimately be evaluated against this metric.

---

# Long-Term Goal

The ideal Poiesis experience is:

    ME
     |
     | Record the episode
     v
    Drop footage in
     |
     v
    POIESIS
     |
     +------------------+
     |                  |
     v                  v
    Understand        Create
    footage           edit plan
     |                  |
     +--------+---------+
              |
              v
           PREVIEW
              |
              v
        "Looks good."
              |
              v
           EXPORT
              |
              v
         YOUTUBE VIDEO

The purpose of Poiesis is not to make video editing more sophisticated.

It is to make video editing **disappear as much as possible**.

The creator should spend their time thinking about:

> **What do I want to say?**

rather than:

> **How do I spend six hours turning what I said into a video?**

---

# Development Directive

When modifying Poiesis, always optimize for the vision described in this document.

If an existing component is difficult to fix, first ask:

> **Is this component necessary for the product we are trying to build?**

Do not automatically make a complex video-editor abstraction more sophisticated.

Prefer simplifying the product around:

    Content
       |
       v
    Understanding
       |
       v
    Edit Plan
       |
       v
    Review
       |
       v
    Remotion
       |
       v
    Video

The existing Poiesis codebase is the starting point.

The objective is to **evolve it into an AI-powered personal YouTube production system**, not to replace it with a new application.

When making architectural decisions, favor:

1. Reuse of existing working code.
2. Small, composable domain concepts.
3. Structured intermediate artifacts.
4. Clear boundaries between AI reasoning and deterministic execution.
5. Remotion as the rendering engine.
6. Natural-language AI interaction.
7. Human review instead of manual editing.
8. Automation of repetitive work.
9. A reusable visual design system.
10. Simplicity over building a general-purpose editor.

The ultimate goal is:

> **Record once, review briefly, publish.**