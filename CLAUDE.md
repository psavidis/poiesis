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

# Visual Storytelling & Professional Motion Design Directive

This section defines the visual-quality standard for Poiesis.

It is intentionally more demanding than simply producing "animated" videos.

The objective is to produce videos that look **professionally designed and edited**, not merely AI-generated.

---

# The Core Creative Goal

Poiesis should not think of itself as an animation generator.

It should think of itself as a:

> **Professional visual storytelling and motion-design system for software-engineering videos.**

The job of the AI is to transform spoken reasoning into a visual experience that helps the audience understand, remember, and follow the argument.

The objective is NOT:

> "Make the video more animated."

The objective is:

> **"Make the ideas easier and more compelling to understand through visuals."**

This distinction is fundamental.

---

# The Creative Director Model

Claude should act as the **creative director and visual storyteller**.

Remotion should act as the **motion-design and rendering engine**.

Poiesis should act as the **orchestration and production system**.

The relationship is:

```
SCRIPT / AUDIO
      |
      v
SEMANTIC UNDERSTANDING
      |
      v
CREATIVE DIRECTION
      |
      v
VISUAL STORYBOARD
      |
      v
SCENE SPECIFICATION
      |
      v
REMOTION COMPONENTS
      |
      v
    RENDER
      |
      v
VISUAL QA / CRITIQUE
      |
      v
   ITERATION
      |
      v
  FINAL VIDEO
```

Claude should make the creative decisions.

Remotion should execute those decisions deterministically.

---

# Do Not Animate Sentences

One of the most important rules in Poiesis is:

> **Do not treat the transcript as a sequence of sentences that need animation.**

Instead, treat the narration as a sequence of **ideas**.

For every meaningful section of narration, determine:

1. What is the speaker trying to communicate?
2. What does the audience need to understand?
3. What is abstract?
4. What is difficult to visualize?
5. What relationship is being described?
6. What should be emphasized?
7. What visual representation would make the idea easier to understand?

Only after answering those questions should a visual be selected.

---

# Show, Don't Repeat

A visual should preferably add information rather than simply repeat the narration.

For example, if the speaker says:

> "A hotel knows that someone checked in, but it doesn't know where that person actually is."

A weak implementation would display:

```
"Checked in ≠ Actually there"
```

as animated text.

A stronger implementation could show:

```
PMS
 |
 | Check-in
 v
HOTEL
 |
 +---- Room
 +---- Restaurant
 +---- Pool
 +---- Gym
 |
 v
Unknown physical location
```

Then actual occupancy can progressively appear.

The visual creates a mental model.

That is the standard Poiesis should aim for.

---

# Visual Purpose

Every significant visual element should have an explicit purpose.

A visual should primarily serve one or more of:

* Explanation
* Emphasis
* Context
* Comparison
* Causality
* Process
* Spatial understanding
* Temporal understanding
* Data comprehension
* Demonstration
* Emotional impact
* Attention direction
* Narrative transition

Avoid decorative animation that does not improve the communication.

---

# Visual Decision Hierarchy

When deciding what should appear on screen, prefer this hierarchy:

### 1. Real evidence

Use:

* Product UI
* Screenshots
* Code
* Real diagrams
* Real data
* Actual footage

when they directly explain the idea.

### 2. Constructed explanatory graphics

Use:

* Diagrams
* Flow charts
* Timelines
* Comparisons
* Conceptual illustrations
* Animated architecture
* Spatial representations

when the idea needs explanation.

### 3. Typography

Use large text when the **statement itself** is important.

Typography should usually emphasize rather than explain a complicated concept.

### 4. Decorative motion

Use only when it contributes to visual rhythm, polish, or transition.

Decorative animation should never replace useful visual communication.

---

# Professional Visual Rhythm

A professional video should not remain visually static for long periods when the content benefits from visual support.

However, visual change should also not happen continuously.

Think in terms of **visual rhythm**.

For example:

```
PRESENTER
    |
    v
IMPORTANT STATEMENT
    |
    v
DIAGRAM
    |
    v
PRESENTER
    |
    v
CODE
    |
    v
CONCEPT VISUALIZATION
    |
    v
PRESENTER
```

The exact sequence should depend on the content.

Avoid repetitive patterns such as:

```
TEXT
TEXT
TEXT
TEXT
```

or:

```
ZOOM
ZOOM
ZOOM
ZOOM
```

or:

```
POP-IN
POP-IN
POP-IN
POP-IN
```

Professionalism comes from variation combined with consistency.

---

# Visual Breathing Room

Not every moment requires a graphic.

Some of the strongest moments may be:

* Presenter alone
* A simple sentence
* A pause
* A clean composition
* A slow camera movement
* A minimal visual transition

Poiesis should intentionally create moments of visual silence.

A video that constantly demands attention becomes exhausting.

---

# Motion Must Communicate

Animation should have semantic meaning whenever possible.

Examples:

### Movement

Can communicate:

* Flow
* Direction
* Progression
* Migration
* Causality
* Connection

### Scale

Can communicate:

* Importance
* Growth
* Zooming into detail
* Hierarchy

### Opacity

Can communicate:

* Secondary information
* Context
* Disappearance
* Focus

### Position

Can communicate:

* Relationships
* Spatial organization
* Before/after
* Movement between states

### Morphing

Can communicate:

* Transformation
* Equivalence
* Evolution
* Refactoring

Prefer meaningful motion over generic effects.

---

# Build A Professional Motion Vocabulary

Poiesis should develop a reusable library of professional motion-design primitives.

Examples:

```
TitleReveal
KineticStatement
WordHighlight
NumberReveal
Counter
Comparison
BeforeAfter
Diagram
FlowDiagram
ProcessDiagram
Timeline
ArchitectureDiagram
DataChart
BarChart
LineChart
Map
Callout
Annotation
ScreenshotFocus
ImageReveal
ImagePan
UIShowcase
CodeReveal
CodeFocus
ConceptVisualization
Quote
FullScreenStatement
SectionTransition
ChapterTitle
```

These should be reusable and parameterized.

The AI should normally **select and configure** these primitives instead of inventing completely new animation implementations.

The library should grow over time.

---

# Motion Design System

The visual system should have explicit reusable rules for:

* Typography
* Font sizes
* Font weights
* Color
* Spacing
* Grid
* Alignment
* Corner radius
* Shadows
* Borders
* Backgrounds
* Stroke widths
* Animation durations
* Easing
* Entrance animations
* Exit animations
* Transitions

The purpose is to make independently generated scenes feel like they belong to the same professional production.

Do not allow every scene to develop its own visual language.

---

# Typography Rules

Typography should be treated as a design system.

Prefer:

```
ONE IMPORTANT IDEA
```

over:

```
A paragraph of text explaining everything.
```

Text should generally be:

* Short
* Hierarchical
* Readable
* Deliberately positioned
* Timed with narration

Use large text for emphasis.

Use smaller text for supporting information.

Do not turn the video into a presentation deck.

The viewer should be watching a video, not reading slides.

---

# Diagrams Are First-Class Visuals

For software-engineering content, diagrams should be one of the primary visual languages.

Claude should recognize when the speaker is describing:

* Architecture
* Data flow
* APIs
* Components
* Dependencies
* Processes
* State transitions
* Queues
* Events
* Databases
* Networks
* Algorithms
* Relationships

and consider generating a diagram.

For example:

```
Client
   |
   v
 API
   |
   v
Service
   |
+--+--+
|     |
v     v
```

DB    Kafka

A diagram should not simply appear.

It should usually be **constructed progressively in sync with the explanation**.

If the speaker introduces the API first, show the API.

When the speaker explains the service, reveal the service.

When the speaker explains the database, connect it.

This allows the audience to build the mental model together with the speaker.

---

# Code Is A Visual Storytelling Tool

Code should not simply be displayed as a static screenshot.

When useful:

* Reveal relevant lines progressively.
* Highlight the important section.
* De-emphasize irrelevant code.
* Zoom into the relevant method.
* Show a before/after.
* Animate relationships between code and architecture.
* Connect the code to the concept being explained.

The objective is:

> "Show the audience exactly what the speaker is talking about."

not:

> "Put the entire code listing on screen."

---

# Presenter Integration

The presenter should remain an important visual anchor.

Visuals should complement the presenter rather than constantly replacing them.

Possible compositions include:

```
Presenter + supporting graphic

Presenter + diagram

Presenter + code

Presenter + highlighted phrase

Full-screen concept

Presenter → graphic → presenter
```

Use the presenter strategically.

Do not obscure the presenter unnecessarily.

Do not cover their face with graphics.

Maintain visual hierarchy.

---

# Scene Composition

Every scene should have deliberate composition.

Consider:

* Subject position
* Negative space
* Visual balance
* Alignment
* Hierarchy
* Depth
* Scale
* Focus
* Contrast

Do not simply center everything.

Do not automatically put text in the middle of the screen.

Composition should depend on the content and the intended visual relationship.

---

# Camera Language

Virtual camera movement can be used to guide attention.

Examples:

* Slow push-in for emphasis
* Pull-back to reveal context
* Pan across a diagram
* Zoom into code
* Move between connected architecture components
* Follow a data flow
* Reveal a larger system

Camera movement should have narrative purpose.

Avoid constant artificial zooming.

---

# Transitions

Transitions should reflect relationships between scenes.

Prefer:

* Morph
* Match movement
* Spatial continuation
* Shared elements
* Camera movement
* Shape transformation
* Progressive replacement
* Crossfade where appropriate

Avoid using random transition effects merely to separate scenes.

The transition itself should ideally communicate continuity.

---

# Semantic Scene Specification

The edit plan should eventually distinguish between:

### WHAT

The idea being communicated.

### WHY

Why the visual exists.

### HOW

Which reusable visual component should communicate it.

Conceptually:

```json
{
  "purpose": "Explain event flow",
  "visualConcept": "An event moves from producer to consumer through Kafka",
  "component": "FlowDiagram",
  "elements": [
    "Producer",
    "Kafka",
    "Consumer"
  ],
  "animation": "progressive-flow",
  "emphasis": ["Kafka"]
}
```

The exact domain model should evolve with the application.

The important principle is that **creative intent must survive independently of rendering implementation**.

---

# Storyboard Before Implementation

For substantial sections, Claude should first reason about the visual storyboard before writing or modifying Remotion code.

The preferred process is:

```
Narration
   |
   v
Semantic analysis
   |
   v
Visual opportunities
   |
   v
Storyboard
   |
   v
Scene specifications
   |
   v
Remotion implementation
```

Do not immediately code the first visual idea that comes to mind.

Compare possible visual approaches and choose the one that communicates best.

---

# The Audience Comprehension Test

For every important scene ask:

> What should the audience understand after seeing this?

Then ask:

> Is the visual actually helping them understand it?

If removing the visual would make the explanation equally clear, consider whether the visual is necessary.

If the visual merely repeats the narration without adding useful information, consider replacing it.

---

# The Professionalism Test

Before accepting a generated scene, evaluate:

### Composition

Does this look deliberately designed?

### Typography

Does it look like professional motion graphics rather than an HTML page?

### Motion

Does movement have purpose?

### Hierarchy

Is it immediately obvious where the viewer should look?

### Timing

Do important events happen at the right moment?

### Restraint

Is anything unnecessary?

### Consistency

Does it belong to the Poiesis visual language?

### Comprehension

Does the visual make the concept easier to understand?

### Originality

Does it look like a thoughtful production rather than a generic AI template?

---

# Render → Inspect → Critique → Improve

A rendered video is not automatically successful because the code compiled.

The AI should inspect its actual visual output.

The desired loop is:

```
IMPLEMENT
   |
   v
RENDER
   |
   v
INSPECT
   |
   v
CRITIQUE
   |
   v
IMPROVE
   |
   v
RENDER AGAIN
```

When possible, inspect actual frames or short rendered sections rather than reasoning only from source code.

Source code cannot reliably tell you whether a composition looks professional.

---

# Avoid AI Slop

Poiesis must actively avoid visual patterns commonly associated with low-quality AI-generated content.

Avoid:

* Excessive bouncing
* Excessive zooming
* Random particles
* Random gradients
* Generic glowing UI
* Excessive glassmorphism
* Emoji-heavy visuals
* Random icons
* Constant kinetic typography
* Every-word animation
* Unmotivated camera movement
* Excessive transitions
* Overly dense screens
* Generic stock-looking illustrations
* Visuals unrelated to the narration

When in doubt:

> **Prefer simple, intentional, well-composed design over flashy animation.**

---

# The Ultimate Standard

The final video should not feel like:

> "AI generated a video."

It should feel like:

> **"A professional editor and motion designer produced this video."**

AI should be invisible in the final result.

The audience should notice:

* Clear explanations
* Strong visual storytelling
* Excellent pacing
* Consistent design
* Professional motion
* Useful diagrams
* Well-timed emphasis
* Good composition

They should not notice the automation behind it.

---

# Development Priority

When improving Poiesis's visual generation capabilities, prioritize in this order:

1. Better semantic understanding of narration.
2. Better identification of visual opportunities.
3. Better storyboard generation.
4. Better reusable visual primitives.
5. Better scene composition.
6. Better timing synchronization.
7. Better transitions.
8. Better visual QA.
9. Better iterative refinement.
10. More visual variety.

Do NOT prioritize:

> "More animation types."

A small library of excellent components is more valuable than a huge library of mediocre ones.

---

# Definition Of Success

Poiesis succeeds when:

> I can give it a 10–15 minute software-engineering talking-head video and its first generated version already looks sufficiently professional that I mainly spend my time correcting creative decisions rather than manually editing the video.

The goal is not perfection on the first render.

The goal is:

> **The AI makes a strong professional edit, and the human makes the final creative decisions.**

The human should be the director.

Claude should be the creative editor.

Remotion should be the motion-design engine.

Poiesis should orchestrate the entire process.
