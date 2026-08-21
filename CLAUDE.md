# Poiesis — Claude Project Instructions

## Purpose

Poiesis is an AI-assisted video production system for turning raw talking-head footage into polished software-engineering YouTube videos.

The goal is **not** to build another general-purpose video editor.

The goal is to build a **personal AI video-production system** that understands my scripts, footage, visual style, reusable visual components, and editing preferences, and automates as much of the repetitive editing work as possible.

Poiesis should allow me to go from:

> "I recorded the episode."

to:

> "I have a polished video ready for final review."

with as little manual editing as possible.

The human remains the director.

AI performs the creative editing work.

Poiesis provides the editing environment, orchestration, assets, rendering, and feedback loop.

---

# Vision

I create software-engineering videos where I talk directly to the camera, usually for 10–15 minutes.

The videos typically contain:

* Talking-head footage
* Background removal
* Animated backgrounds
* Intro and outro sequences
* Animated titles
* Important phrases
* Code snippets
* Diagrams
* Images and screenshots
* B-roll
* Captions
* Transitions
* Subtle animations
* Music and sound effects

Producing this manually can take many hours even when the recorded footage is already good.

Poiesis should automate both the **mechanical** and **creative** editing decisions that can reasonably be automated by AI.

The objective is not to eliminate human creative control.

The objective is to eliminate repetitive manual editing.

---

# Core Product Principle

Poiesis is **not a traditional nonlinear video editor**.

It should not attempt to reproduce:

* Premiere Pro
* Final Cut Pro
* DaVinci Resolve
* CapCut

The primary interaction should not be:

> Drag clips around a timeline until the video looks right.

Instead, it should be:

> Understand the content, generate a semantic edit, expose the decisions as editable Moments, and let the creator correct the result through direct manipulation or natural language.

The central product concept is therefore not the traditional timeline.

It is the combination of:

**Content → Chapters → Moments → Assets → Visual Components → Render**

---

# The Semantic Model

The semantic model is the foundation of Poiesis.

The system should represent the video at a level that is meaningful to both humans and AI.

The core concepts are:

```text
Episode
   |
   +-- Source Footage
   |
   +-- Transcript
   |
   +-- Chapters
   |
   +-- Moments
   |
   +-- Assets
   |
   +-- Visual Components
   |
   +-- Edit / Composition
```

The exact domain model should evolve with the codebase.

Do not prematurely lock the model to a particular JSON schema.

The important principle is:

> **The semantic meaning of the video must exist independently of rendering implementation.**

---

# Chapters

Chapters represent the major narrative structure of an episode.

A chapter may correspond to:

* A major topic
* A conceptual section
* A transition in the argument
* A logical part of the script
* A major visual section

Chapters should be understandable and editable by the creator.

The AI should be able to:

* Detect chapters
* Name chapters
* Suggest chapter boundaries
* Move chapter boundaries
* Rename chapters
* Merge chapters
* Split chapters

Chapters are a narrative structure, not merely arbitrary time ranges.

---

# Moments

**Moments are a first-class concept in Poiesis.**

A Moment represents a meaningful visual or editorial intervention associated with a portion of the narration.

Examples:

* Important phrase
* Title
* Code
* Diagram
* Screenshot
* Image
* Comparison
* Callout
* Concept visualization
* Full-screen statement
* Presenter composition change
* B-roll
* Transition
* Other reusable visual treatment

A Moment should capture both **what should happen** and enough semantic information to understand why it exists.

Conceptually:

```json
{
  "type": "diagram",
  "start": 38,
  "end": 52,
  "purpose": "Explain event flow",
  "visualConcept": "Producer sends an event through Kafka to a consumer",
  "asset": "event-flow-diagram"
}
```

This is illustrative only.

The exact schema should evolve with the application.

The important principle is:

> **A Moment is a semantic editing decision, not merely a rendered clip.**

---

# Moments Bar

The Moments Bar is a fundamental part of the editing experience.

It should provide a persistent visual representation of the Moments associated with the episode.

### Critical behavior

The Moments Bar must **always be visible**.

If AI analysis produces zero Moments, the bar must still exist and represent the valid empty state.

Do not conditionally hide the Moments Bar because:

```text
moments.length === 0
```

An empty result is still meaningful state.

The UI should distinguish between:

* Moments are currently being calculated
* Moments have been calculated and there are none
* Moments exist and can be edited
* Analysis failed

The failure state must not accidentally look like an empty successful result.

The Moments Bar should therefore be treated as part of the persistent editor structure rather than a result that appears only when AI generated content.

---

# Editing Moments

Moments should be directly editable.

The creator should be able to change things such as:

* Start time
* End time
* Type
* Text
* Visual treatment
* Asset
* Position
* Duration
* Animation
* Configuration
* Relationship to the narration

The system should make simple edits extremely cheap.

For example:

> "Move this moment two seconds earlier."

> "Make this moment shorter."

> "Remove this."

> "Use a diagram instead."

> "Show the presenter here."

> "Use the same treatment as the previous moment."

These operations should modify structured semantic state rather than directly modifying rendered video.

---

# Command+E

Editing should support fast keyboard-driven workflows.

**Command+E is a core editing interaction.**

The exact command behavior should follow the current application implementation/specification, but keyboard-first editing should be preferred wherever it makes common editing operations faster.

The editor should not require the user to navigate complex menus for frequent operations.

---

# Natural-Language Editing

Natural-language editing is a first-class feature of Poiesis.

The user should be able to describe desired changes conversationally.

Examples:

> "Remove this pause."

> "Make this section faster."

> "Show the code when I mention the implementation."

> "Replace this text with a diagram."

> "Move the title earlier."

> "Make this less visually busy."

> "Use the same animation as the previous episode."

> "Show me full screen during this explanation."

> "Create a moment here explaining the relationship between these two components."

The AI should interpret the request and modify the semantic editing model.

It should **not** directly manipulate rendered pixels.

The preferred flow is:

```text
User request
     |
     v
AI understanding
     |
     v
Structured edit change
     |
     v
Updated semantic model
     |
     v
Preview / render
```

The system should make the resulting change inspectable.

---

# Conversational Editing

The conversational AI interface should eventually support a natural editing loop:

```text
Creator
   |
   | "Change this"
   v
AI
   |
   | understands context
   v
Edit Plan / Moments
   |
   v
Preview
   |
   v
Creator
   |
   +---- "Good"
   |
   +---- "Try something else"
```

The AI should understand the current editing context.

For example, when the user says:

> "Make this one smaller."

the system should understand which Moment "this one" refers to from the current UI context.

Natural language should complement direct manipulation, not replace it.

---

# Assets

Assets are first-class editing resources.

Poiesis should maintain a clear distinction between different asset categories.

Examples include:

* Full-screen images
* Images
* Diagrams
* Code
* Screenshots
* B-roll
* Backgrounds
* Audio
* Other reusable visual resources

Assets should have clear ownership and predictable organization.

The asset structure should reflect how the creator actually uses them rather than being a generic media bin copied from professional NLEs.

The AI should be able to:

* Identify when an existing asset is relevant
* Select an appropriate asset
* Suggest a new asset
* Associate an asset with a Moment
* Reuse assets across episodes

The system should avoid unnecessarily duplicating assets.

---

# Visual Components

Assets are not the same thing as visual components.

A visual component is a reusable piece of the Poiesis visual language.

Examples:

```text
Presenter
AnimatedTitle
ImportantPhrase
CodeBlock
ConceptDiagram
Comparison
Callout
Quote
Caption
Timeline
FlowDiagram
ArchitectureDiagram
ScreenshotFocus
FullScreenStatement
SectionTransition
ChapterTitle
```

A component defines **how something is presented**.

An asset defines **what content is presented**.

The AI should combine these concepts.

For example:

```text
Moment
   |
   +-- purpose: Explain architecture
   |
   +-- component: FlowDiagram
   |
   +-- asset/data: architecture definition
```

---

# AI Responsibilities

Claude should primarily be responsible for **creative and semantic decisions**.

## Understand the Content

The AI should be able to:

* Understand the script
* Understand the transcript
* Identify topics
* Identify chapters
* Identify concepts
* Identify important phrases
* Understand technical explanations
* Understand narrative structure
* Identify visual opportunities
* Understand the intended argument

## Decide the Edit

The AI should eventually be able to:

* Select good takes
* Remove obvious mistakes
* Identify unnecessary pauses
* Identify repeated or redundant sections
* Decide where visual changes are useful
* Decide when text should appear
* Decide when code should appear
* Decide when diagrams are useful
* Decide when screenshots or images would help
* Decide when the presenter should remain visible
* Decide when the visual composition should change
* Select appropriate reusable components
* Select appropriate assets
* Create and configure Moments

## Improve Engagement

The AI should look for sections where visual presentation becomes monotonous.

For example:

```text
20 seconds of talking head
        |
        v
Important concept
        |
        v
Diagram
        |
        v
Presenter
        |
        v
Code
```

But:

> **Do not add visual changes simply because the screen has been static.**

Visual changes should have a semantic reason.

Avoid "AI slop" where every sentence receives an animation.

---

# Do Not Animate Sentences

Do not treat the transcript as a sequence of sentences that need animation.

Treat the narration as a sequence of **ideas**.

For every meaningful section ask:

1. What is the speaker trying to communicate?
2. What does the audience need to understand?
3. What is abstract?
4. What is difficult to visualize?
5. What relationship is being described?
6. What should be emphasized?
7. What visual representation would make the idea easier to understand?

Only then select or create a Moment.

---

# Show, Don't Repeat

A visual should preferably add information rather than simply repeat narration.

Weak:

```text
"Checked in ≠ Actually there"
```

Strong:

```text
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

The visual should create a mental model.

That is the standard Poiesis should aim for.

---

# Visual Purpose

Every significant Moment should have an explicit purpose.

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

Avoid decorative animation that does not improve communication.

---

# Visual Decision Hierarchy

Prefer:

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

### 4. Decorative motion

Use only when it contributes to rhythm, polish, or transition.

---

# Professional Visual Rhythm

A professional video should have visual rhythm without becoming visually exhausting.

Possible sequence:

```text
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

The exact sequence depends on the content.

Avoid:

```text
TEXT
TEXT
TEXT
TEXT
```

or:

```text
ZOOM
ZOOM
ZOOM
ZOOM
```

or:

```text
POP-IN
POP-IN
POP-IN
POP-IN
```

Professionalism comes from variation combined with consistency.

---

# Visual Breathing Room

Not every moment requires a graphic.

Some strong moments may be:

* Presenter alone
* A simple statement
* A pause
* A clean composition
* A slow camera movement
* A minimal transition

Poiesis should intentionally create moments of visual silence.

A video that constantly demands attention becomes exhausting.

---

# Motion Must Communicate

Animation should have semantic meaning whenever possible.

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

# Build a Professional Motion Vocabulary

Poiesis should develop a reusable library of professional motion-design primitives.

Examples:

```text
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

The AI should normally **select and configure** these primitives rather than inventing completely new animation implementations.

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

Independently generated Moments should still feel like they belong to the same production.

Do not allow every Moment to develop its own visual language.

---

# Typography Rules

Prefer:

```text
ONE IMPORTANT IDEA
```

over:

```text
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

---

# Diagrams Are First-Class Visuals

For software-engineering content, diagrams should be one of the primary visual languages.

The AI should recognize when the speaker describes:

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

and consider creating a diagram Moment.

A diagram should usually be constructed progressively in sync with the explanation.

If the speaker introduces the API first, show the API.

When the speaker explains the service, reveal the service.

When the speaker explains the database, connect it.

The audience should build the mental model together with the speaker.

---

# Code Is a Visual Storytelling Tool

Code should not simply be displayed as a static screenshot.

When useful:

* Reveal relevant lines progressively.
* Highlight the important section.
* De-emphasize irrelevant code.
* Zoom into the relevant method.
* Show before/after.
* Connect code to architecture.
* Animate relationships between code and the concept.

The objective is:

> "Show the audience exactly what the speaker is talking about."

not:

> "Put the entire code listing on screen."

---

# Presenter Integration

The presenter remains an important visual anchor.

Possible compositions include:

```text
Presenter + supporting graphic

Presenter + diagram

Presenter + code

Presenter + highlighted phrase

Full-screen concept

Presenter → graphic → presenter
```

Do not obscure the presenter unnecessarily.

Do not cover their face with graphics.

Maintain visual hierarchy.

---

# Scene Composition

Every visual Moment should have deliberate composition.

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

Composition should depend on the content and intended visual relationship.

---

# Camera Language

Virtual camera movement can guide attention.

Examples:

* Slow push-in for emphasis
* Pull-back to reveal context
* Pan across a diagram
* Zoom into code
* Move between connected architecture components
* Follow data flow
* Reveal a larger system

Camera movement should have narrative purpose.

Avoid constant artificial zooming.

---

# Transitions

Transitions should reflect relationships between Moments.

Prefer:

* Morph
* Match movement
* Spatial continuation
* Shared elements
* Camera movement
* Shape transformation
* Progressive replacement
* Crossfade where appropriate

Avoid random transition effects merely to separate Moments.

---

# Semantic Moment Specification

A Moment should eventually distinguish between:

### WHAT

The idea being communicated.

### WHY

Why the visual exists.

### HOW

Which reusable component and assets communicate it.

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

The exact domain model should evolve.

The important principle is:

> **Creative intent must survive independently of rendering implementation.**

---

# AI Provider Architecture

The AI layer must be abstracted from the rest of the application.

Current important providers include:

* Claude
* Gemini
* Local models where appropriate

Conceptually:

```text
AI Provider
   |
   +-- Claude
   |
   +-- Gemini
   |
   +-- Local Model
   |
   +-- Other providers
```

Claude should remain the primary high-quality reasoning provider when sophisticated creative reasoning is required.

Gemini should be supported as a first-class provider rather than being treated as a special-case integration.

Local or cheaper models can be used for tasks where sophisticated reasoning is unnecessary.

The core domain must not depend directly on one specific LLM provider.

Provider-specific request/response formats belong at the AI infrastructure boundary.

The semantic video-production domain should remain provider-independent.

---

# AI Should Produce Decisions, Not Opaque Side Effects

Prefer:

```text
AI
 |
 v
Structured semantic decisions
 |
 v
Application orchestration
 |
 v
Deterministic execution
 |
 v
Render
```

over:

```text
AI
 |
 v
Random collection of video operations
```

The AI's decisions should be explicit, inspectable, testable, and reproducible where possible.

---

# Processing Pipeline

Poiesis should use clearly separated processing stages.

Conceptually:

```text
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
CHAPTER
   |
   v
MOMENT GENERATION
   |
   v
REVIEW / EDIT
   |
   v
RENDER
   |
   v
QA
   |
   v
EXPORT
```

Each stage should have a clear responsibility and preferably produce an inspectable artifact.

Potential artifacts include:

```text
transcript.json
segments.json
analysis.json
chapters.json
moments.json
edit-plan.json
render.mp4
qa-report.json
```

The exact artifacts may evolve.

The principle is:

> **The current state of an episode should be understandable without inspecting opaque internal application state.**

---

# Pipeline Orchestration

The processing pipeline should be treated as an explicit workflow rather than an accidental chain of function calls.

Stages may depend on outputs from earlier stages.

The system should therefore make:

* Dependencies
* State
* Failures
* Retries
* Intermediate results
* Re-running individual stages

explicit where practical.

Do not introduce a heavyweight orchestration system merely for architectural fashion.

The orchestration mechanism should be proportional to the actual complexity of the pipeline.

The important requirement is that the workflow is:

* Observable
* Restartable
* Deterministic where possible
* Failure-aware
* Incrementally executable

A failed AI stage should not require rebuilding the entire episode from scratch.

---

# Deterministic Video Processing

LLMs should not be responsible for operations that can be implemented deterministically.

Use conventional video-processing tools for:

* Cutting
* Concatenation
* Encoding
* Audio normalization
* Silence removal
* Resolution changes
* Format conversion
* Frame extraction
* Audio extraction
* Media inspection

FFmpeg should be used where appropriate.

Other specialized tools can be introduced when necessary.

The principle is:

> **Use AI for judgment. Use software for execution.**

---

# Remotion

Remotion is the primary rendering and composition engine.

Remotion should remain responsible for:

* Video composition
* Presenter placement
* Backgrounds
* Text
* Captions
* Code blocks
* Diagrams
* Animations
* Transitions
* Images
* Screenshots
* Reusable visual components
* Intro
* Outro

The semantic editor should **not become coupled to Remotion implementation details**.

The preferred architecture is:

```text
Semantic Model
     |
     v
Moment / Composition Specifications
     |
     v
Remotion Components
     |
     v
Rendered Video
```

Remotion executes the visual decisions.

It should not be the source of truth for those decisions.

---

# Editor UI

Poiesis does have an editor interface, but it is not intended to become a general-purpose nonlinear editor.

The UI should be optimized for **AI-assisted review and semantic editing**.

The editor should allow the user to:

* Preview the video
* Inspect chapters
* Inspect Moments
* Edit Moments
* Inspect source footage
* Manage assets
* See the semantic structure of the episode
* Approve or reject AI decisions
* Ask AI for changes
* Perform direct edits
* Re-render previews

The timeline may exist as a useful visualization and editing mechanism.

However:

> **The semantic model remains the architectural center, not the timeline.**

Do not spend large amounts of development effort reproducing professional NLE functionality that does not directly improve AI-assisted production.

---

# AI + Direct Manipulation

The editor should support two complementary editing modes:

### Direct editing

The creator can explicitly modify a Moment, chapter, asset, timing, or visual configuration.

### Natural-language editing

The creator can ask the AI to make the change.

These should ultimately operate on the same underlying semantic model.

For example:

```text
Direct UI edit
      |
      +------+
             |
Natural ----> Semantic Model
language     |
             v
           Render
```

There should not be two independent editing systems.

---

# Storyboard Before Implementation

For substantial sections, Claude should reason about the visual storyboard before implementing or modifying Remotion code.

Preferred process:

```text
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
Moments
   |
   v
Scene specifications
   |
   v
Remotion implementation
```

Do not immediately code the first visual idea.

Compare possible visual approaches and select the one that communicates best.

---

# Render → Inspect → Critique → Improve

A rendered video is not automatically successful because the code compiled.

The AI should inspect actual visual output whenever possible.

Desired loop:

```text
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

Inspect actual frames or short rendered sections rather than reasoning only from source code.

Source code cannot reliably tell you whether a composition looks professional.

---

# Quality Assurance

The system should eventually inspect its own output.

Potential checks include:

* Video duration
* Missing media
* Audio/video synchronization
* Black frames
* Broken assets
* Text outside viewport
* Overlapping elements
* Caption timing
* Presenter visibility
* Rendering errors
* Unexpected scene transitions

QA should distinguish between:

1. Technical failures
2. Structural problems
3. Visual-quality problems

A successful render is not necessarily a successful edit.

---

# Channel Editing Style

Poiesis is initially designed for a specific software-engineering YouTube channel.

The editing style should therefore be treated as a **design system**.

The system should encode rules such as:

* Presenter remains visually prominent.
* Do not obscure the presenter unnecessarily.
* Use visual changes to support explanation.
* Do not animate every sentence.
* Important concepts deserve stronger visual treatment.
* Technical concepts should often use diagrams or code.
* Code should be readable.
* Text should be concise.
* Animations should feel intentional.
* Maintain consistent visual identity.
* Reuse established animation patterns.
* Intro and outro remain consistent.

The AI should learn the style from:

1. Explicit editing rules.
2. Existing Remotion components.
3. Existing visual assets.
4. Previous episodes where available.
5. Human corrections and feedback.

The goal is for Poiesis to become increasingly consistent with my personal editing style.

---

# Human-in-the-Loop

Poiesis should not remove the human from the creative process.

The intended relationship is:

```text
Human
  |
  | content + intent + style
  v
AI
  |
  | proposes
  v
Chapters + Moments + Assets + Edit decisions
  |
  v
Human
  |
  | reviews / corrects
  v
Final semantic edit
  |
  v
Remotion
  |
  v
Video
```

The human should be able to override AI decisions easily.

The system should optimize for:

> **AI does the work; human makes the important decisions.**

---

# Avoid AI Slop

Poiesis must actively avoid visual patterns associated with low-quality AI-generated content.

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
* Visuals unrelated to narration

When in doubt:

> **Prefer simple, intentional, well-composed design over flashy animation.**

---

# Non-Goals

Poiesis should **not** become:

* A Premiere Pro clone
* A Final Cut clone
* A DaVinci Resolve clone
* A generic video editor
* A social-media video editor
* A fully autonomous AI filmmaker
* A complex multi-track NLE
* A collection of unrelated AI-generated effects

The goal is much narrower:

> **Automate the production of polished software-engineering YouTube videos using my footage, scripts, visual components, assets, and editing style.**

---

# Existing Codebase

Poiesis already contains useful infrastructure.

**Do not throw away the existing codebase simply because some parts of the UI or editor are difficult to maintain.**

Existing useful capabilities include:

* Video ingestion
* Footage preparation
* Transcription
* Segment extraction
* Segment normalization
* LLM integration
* AI analysis
* Remotion rendering
* Video composition
* Processing pipelines

These components should be preserved and refactored where necessary.

The project should evolve incrementally rather than being rewritten from scratch.

Before replacing an existing component, determine:

1. What responsibility it currently has.
2. Whether that responsibility is still needed.
3. Whether it can be simplified.
4. Whether it belongs in the new architecture.
5. Whether replacement actually improves the product.

Do not rewrite working infrastructure merely because a new architecture looks cleaner.

---

# Design Principles

## 1. Preserve the Existing Codebase

Prefer incremental evolution over rewriting.

Existing working functionality is valuable.

## 2. Keep the Domain Model Clean

UI concerns should not leak into the core video-production model.

The semantic model should remain independent of the UI.

The renderer should consume semantic specifications rather than UI state.

## 3. Moments Are Semantic Decisions

A Moment should represent meaningful editorial intent.

It should not merely be a rectangle on a timeline.

## 4. AI Produces Decisions, Software Executes Them

Prefer:

```text
AI
 |
 v
Structured decisions
 |
 v
Application
 |
 v
Deterministic execution
```

## 5. Everything Should Be Inspectable

An engineer should be able to understand:

> Why did Poiesis create this video?

by inspecting the episode state, chapters, Moments, assets, and intermediate artifacts.

## 6. Prefer Reusable Components

If a visual treatment is useful once, consider making it reusable.

The visual system should become more powerful with every episode.

## 7. Optimize for Iteration

A bad AI edit is not necessarily a failure.

The system should make it extremely cheap to say:

> "No, change this."

and produce another version.

## 8. Optimize for My Time

The ultimate metric is not:

> How sophisticated is the editor?

It is:

> **How much time do I spend between recording the footage and uploading the video?**

## 9. Do Not Hide Empty States

An empty result is still a valid state.

For example:

> Zero generated Moments

must not cause the Moments Bar to disappear.

The UI should represent state explicitly rather than using absence of data as absence of interface.

## 10. Prefer Semantic Editing Over Pixel Editing

The creator should primarily manipulate:

* What is being communicated
* When it appears
* Which asset is used
* Which visual component presents it
* Why it exists

rather than manually manipulating rendered pixels.

---

# Development Directive

When modifying Poiesis, always optimize for the vision described in this document.

If an existing component is difficult to fix, first ask:

> **Is this component necessary for the product we are trying to build?**

Do not automatically make a complex video-editor abstraction more sophisticated.

Prefer simplifying the product around:

```text
Content
   |
   v
Understanding
   |
   v
Chapters
   |
   v
Moments
   |
   +---- Assets
   |
   +---- Visual Components
   |
   v
Review / Edit
   |
   +---- Direct manipulation
   |
   +---- Natural language
   |
   v
Semantic Model
   |
   v
Remotion
   |
   v
Video
```

The existing Poiesis codebase is the starting point.

The objective is to **evolve it into an AI-powered personal YouTube production system**, not replace it with a new application.

When making architectural decisions, favor:

1. Reuse of existing working code.
2. Small, composable domain concepts.
3. Chapters and Moments as semantic editing primitives.
4. Structured intermediate artifacts.
5. Clear boundaries between AI reasoning and deterministic execution.
6. Provider-independent AI architecture.
7. Claude and Gemini as supported AI providers.
8. Remotion as the rendering engine.
9. Natural-language AI interaction.
10. Direct semantic editing.
11. Persistent and explicit UI state.
12. Reusable visual components.
13. Automation of repetitive work.
14. Simplicity over building a general-purpose editor.

---

# Visual Storytelling & Professional Motion Design Directive

Poiesis should not think of itself as an animation generator.

It should think of itself as a:

> **Professional visual storytelling and motion-design system for software-engineering videos.**

The job of the AI is to transform spoken reasoning into a visual experience that helps the audience understand, remember, and follow the argument.

The objective is NOT:

> "Make the video more animated."

The objective is:

> **"Make the ideas easier and more compelling to understand through visuals."**

---

# Creative Director Model

Claude should act as the **creative director and visual storyteller**.

Remotion should act as the **motion-design and rendering engine**.

Poiesis should act as the **orchestration and production system**.

The relationship is:

```text
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
MOMENTS
      |
      v
SCENE SPECIFICATIONS
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

Claude should make creative decisions.

The application should translate those decisions into structured state.

Remotion should execute them deterministically.

---

# The Audience Comprehension Test

For every important Moment ask:

> What should the audience understand after seeing this?

Then ask:

> Is the visual actually helping them understand it?

If removing the visual would make the explanation equally clear, consider whether it is necessary.

If the visual merely repeats narration without adding useful information, consider replacing it.

---

# The Professionalism Test

Before accepting a generated Moment, evaluate:

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

Does it make the concept easier to understand?

### Originality

Does it look like a thoughtful production rather than a generic AI template?

---

# Development Priority

When improving Poiesis's visual-generation capabilities, prioritize:

1. Better semantic understanding of narration.
2. Better identification of visual opportunities.
3. Better chapter detection.
4. Better Moment generation.
5. Better storyboard generation.
6. Better reusable visual primitives.
7. Better asset selection and management.
8. Better scene composition.
9. Better timing synchronization.
10. Better transitions.
11. Better visual QA.
12. Better iterative refinement.
13. More visual variety.

Do NOT prioritize:

> "More animation types."

A small library of excellent components is more valuable than a huge library of mediocre ones.

---

# Definition of Success

Poiesis succeeds when:

> I can give it a 10–15 minute software-engineering talking-head video and its first generated version already looks sufficiently professional that I mainly spend my time correcting creative decisions rather than manually editing the video.

The goal is not perfection on the first render.

The goal is:

> **The AI makes a strong professional edit, and the human makes the final creative decisions.**

The human should be the director.

Claude should be the creative editor.

Gemini should be available as an alternative AI provider.

Remotion should be the motion-design and rendering engine.

Poiesis should orchestrate the entire process.

The ultimate goal is:

> **Record once, review briefly, publish.**

# Engineering Workflow for GitHub Issues

When working on a GitHub issue, follow a systematic implementation workflow.

## 1. Understand the Issue

Before changing code:

1. Read the issue carefully.
2. Identify the expected behavior and acceptance criteria.
3. Inspect the relevant existing code and architecture.
4. Identify existing tests covering the affected behavior.
5. Check whether the issue conflicts with the current product model or terminology.

Do not implement based only on the issue title.

## 2. Plan Before Implementing

Before making changes, establish:

- What needs to change.
- Which existing components are affected.
- Whether the change belongs in the domain, application, UI, pipeline, or infrastructure.
- What behavior must be tested.
- Whether existing abstractions should be reused rather than replaced.

For non-trivial issues, briefly state the implementation plan before coding.

Prefer the smallest change that correctly solves the issue.

## 3. Implement Against the Semantic Model

Changes should respect the Poiesis semantic model.

Prefer modifying:

- Chapters
- Scenes
- Moments
- Assets
- Visual Components
- Semantic editing state

rather than introducing low-level UI or rendering concepts into the domain.

Do not create new concepts when an existing canonical concept can represent the behavior.

## 4. Tests Are Part of the Implementation

Every behavioral change should include appropriate tests.

The implementation is not considered complete until the relevant tests pass.

Prefer tests that verify observable behavior rather than implementation details.

Use the testing style already established in the affected part of the codebase.

Where appropriate, prefer:

- Domain-level tests for domain behavior.
- Integration tests for interactions between components.
- End-to-end tests for important user workflows.
- Rendering or visual checks where the issue affects generated video output.

Avoid tests that merely verify private implementation details.

## 5. Regression Protection

For bug fixes:

1. Reproduce the problematic behavior.
2. Add a regression test that fails before the fix.
3. Implement the fix.
4. Verify that the regression test passes.
5. Run the relevant existing test suite.

A bug fix without regression coverage should be considered incomplete when the behavior can reasonably be tested.

## 6. Verify the Complete Change

Before considering an issue complete:

1. Run the tests relevant to the changed code.
2. Run broader tests when the change can affect other parts of the system.
3. Run linting, type checking, formatting, or build validation when applicable.
4. For UI changes, verify the actual UI behavior.
5. For rendering changes, inspect the rendered output when practical.

Do not assume that compilation or a successful render means the feature is correct.

## 7. Keep Changes Focused

Do not introduce unrelated refactoring while solving an issue.

If existing code is problematic but unrelated to the issue:

- Avoid changing it unless necessary.
- Mention the problem separately if it is important.
- Do not expand the scope without a reason.

Prefer small, reviewable commits and changes.

## 8. Update Documentation When Necessary

If an implementation changes:

- Product terminology
- Architecture
- User-facing behavior
- Domain concepts
- Development conventions

update the relevant documentation or glossary.

Documentation should describe the current system, not the implementation that existed before the issue.

## 9. Issue Completion Criteria

An issue is complete when:

- The requested behavior is implemented.
- The implementation fits the existing architecture.
- Appropriate tests have been added or updated.
- Relevant tests pass.
- Regression risks have been considered.
- The resulting behavior has been verified.
- Documentation has been updated when necessary.

Do not mark an issue complete merely because the code has been written.

## 10. Final Report

When finishing an issue, provide a concise summary containing:

- What changed.
- Which tests were added or modified.
- Which verification commands were run.
- Any limitations, remaining concerns, or follow-up work.

The final report should make it clear whether the issue is actually verified or only implemented.

## Engineering Principle

Use this workflow:

Understand
  |
  v
Inspect
  |
  v
Plan
  |
  v
Implement
  |
  v
Test
  |
  v
Verify
  |
  v
Review
  |
  v
Complete

The objective is not simply to produce working code.

The objective is to produce a small, well-tested, architecturally consistent change that can be confidently integrated into Poiesis.

# GitHub Issue Writing

GitHub issues are designed to be quickly understandable and actionable by a human.

When creating or updating GitHub issues, prefer the existing issue structure and categories already defined in the repository.

## Issue Structure

Use the appropriate issue type:

- Bug
- Feature
- Task
- Other repository-defined types when applicable

Do not create a custom structure when an existing issue type already represents the work.

Issues should fit naturally into the repository's existing issue templates and fields.

## Keep Issues Simple

Issue descriptions should be:

- Short
- Human-readable
- Specific
- Actionable
- Easy to scan

Do not write long essays explaining the entire reasoning behind an issue.

Avoid unnecessary technical detail unless it is required to implement or understand the issue.

Prefer concrete statements over abstract descriptions.

## Prefer Structured Information

Whenever possible, use:

- Bullet lists
- Numbered lists
- Checklists
- Short sections
- Explicit requirements
- Explicit acceptance criteria

For example:

Instead of:

"The system should provide a persistent representation of the generated moments while also making sure that the state of the component remains visible in cases where the analysis has not generated any moments."

Prefer:

"Keep the Moments Bar visible in all states.

Requirements:
- Visible while analysis is running.
- Visible when moments exist.
- Visible when zero moments were generated.
- Show a distinct failure state when analysis fails."

## Separate Intent from Implementation

Describe what needs to happen before explaining how it should be implemented.

Prefer:

"Keep the Moments Bar visible when zero moments are generated."

over:

"Change the React conditional rendering logic so that moments.length === 0 does not cause the component to return null."

Implementation details belong in the implementation discussion unless they are necessary requirements.

## Acceptance Criteria

For non-trivial issues, explicitly define acceptance criteria.

Keep them short and testable.

Example:

"Acceptance criteria:
- Moments Bar is always visible.
- Empty state is shown when there are zero moments.
- Failure state is distinguishable from empty state.
- Existing Moments Bar tests continue to pass."

## Avoid Over-Specification

Do not create unnecessarily complex issues.

An issue should describe the smallest meaningful unit of work.

If the work is genuinely large, split it into smaller issues rather than hiding multiple independent requirements inside one large description.

If several issues are required, establish the relationship between them clearly.

## Issue Quality Test

Before creating or updating an issue, ask:

1. Can I understand the problem in less than a minute?
2. Is it clear what needs to change?
3. Are the requirements easy to identify?
4. Are the acceptance criteria testable?
5. Is unnecessary implementation detail removed?
6. Does the issue fit the repository's existing issue type and structure?

If not, simplify the issue.

## Principle

GitHub issues are working documents, not design documents.

Prefer:

"Small, clear, actionable, testable"

over:

"Complete, exhaustive, and complicated."

The issue should give the developer enough information to implement the change without making the developer decode a large amount of prose.

## Final Report

When finishing an issue, keep the report concise and human-readable.

Prefer:

- What changed.
- Tests added or updated.
- Verification performed.
- Any remaining concern.

Use bullet points whenever possible.

Do not provide a long narrative unless the change is unusually complex.

--------------------

# Autonomous GitHub Development Workflow

## Purpose

When working autonomously on Poiesis tickets, behave as a software engineer working normally on the repository.

Each ticket must be treated as an independent unit of work with its own Git branch and GitHub Pull Request.

The `main` branch must always remain the integration branch.

Never implement ticket changes directly on `main`.

---

## Core Workflow

For every ticket, follow this lifecycle:

1. Start from the latest `main`.
2. Create a dedicated branch for the ticket.
3. Implement the ticket completely.
4. Run the appropriate tests and validation.
5. Review the complete Git diff.
6. Commit the work.
7. Push the branch to GitHub.
8. Create a Pull Request for the ticket.
9. Associate the Pull Request with the GitHub Issue.
10. Review the implementation again using the PR diff.
11. Make additional commits if problems are found.
12. When the ticket is complete, squash-merge the Pull Request into `main`.
13. Verify that `main` contains the expected result.
14. Close the GitHub Issue if it was not automatically closed by the merge.
15. Delete the remote feature branch.
16. Return to `main`.
17. Pull the latest `main`.
18. Continue with the next ticket.

Do not stop after completing one ticket. Continue through the assigned ticket queue.

---

# Branch Rules

## Never work directly on `main`

Before modifying files:

```bash
git status
git branch --show-current
```

The working branch must be the ticket branch.

If currently on `main`, update it first:

```bash
git checkout main
git pull --ff-only origin main
```

Then create the ticket branch.

---

## Branch Naming

Use:

```text
<type>/<issue-number>-<short-description>
```

Examples:

```text
feature/123-title-screen-duration
feature/124-moments-bar-always-visible
fix/125-invalid-chapter-count
refactor/126-animation-timing
```

Prefer these types:

* `feature/` — new functionality
* `fix/` — bug fix
* `refactor/` — refactoring
* `test/` — test-only changes
* `docs/` — documentation-only changes
* `chore/` — maintenance

The issue number must be included whenever possible.

---

# Starting a Ticket

Before implementing a ticket:

1. Read the complete GitHub Issue.
2. Inspect related code.
3. Inspect related tests.
4. Inspect recent Git history when useful.
5. Check whether other tickets have already changed the relevant area.
6. Understand the current implementation rather than relying only on the ticket description.

Do not blindly implement the ticket from its title.

If the ticket references other issues, inspect those relationships before starting.

---

# Creating the Branch

Always branch from the latest `main`.

Example:

```bash
git checkout main
git pull --ff-only origin main
git checkout -b feature/123-short-description
```

Do not branch from an old feature branch.

---

# Implementation

Implement the ticket according to the existing Poiesis architecture and conventions.

Prefer:

* existing abstractions
* existing utilities
* existing patterns
* minimal changes
* consistent naming
* tests that verify behavior rather than implementation details

Do not introduce unrelated refactoring.

Do not modify unrelated files unless the implementation genuinely requires it.

---

# Testing

Before creating the Pull Request:

1. Run the most specific tests relevant to the change.
2. Run broader tests when practical.
3. Run type checking/linting/build validation when applicable.
4. Fix failures before opening the PR.

Do not consider a ticket complete merely because the code compiles.

The implementation must satisfy the ticket's acceptance criteria.

---

# Commit Rules

Commits should represent meaningful development steps.

During implementation, normal commits are allowed.

Do not obsess over producing one commit during development.

The Pull Request will ultimately be squash-merged into `main`.

Use clear commit messages.

Examples:

```text
Add title screen duration calculation
Fix title screen frame conversion
Add tests for title screen timing
```

Avoid meaningless messages such as:

```text
changes
fix
stuff
wip
update
```

---

# Pull Request

When implementation and validation are complete, push the branch:

```bash
git push -u origin <branch>
```

Create a Pull Request targeting:

```text
main
```

The PR title should clearly describe the ticket.

Example:

```text
Add automatic title screen duration
```

The PR description should contain:

* what changed
* why it changed
* how it was implemented
* tests/validation performed
* the associated issue

Use GitHub's issue-closing syntax where appropriate:

```text
Closes #123
```

This associates the PR with the issue and allows GitHub to close the issue when the PR is merged.

---

# Pull Request Self-Review

Before merging, review the PR as if another engineer submitted it.

Inspect:

```bash
git diff main...HEAD
```

Look specifically for:

* accidental changes
* debugging code
* dead code
* unnecessary complexity
* incorrect assumptions
* missing tests
* regressions
* inconsistent naming
* unrelated modifications

If problems are found, fix them and push the changes.

Do not merge code that has not passed this self-review.

---

# Merge Policy

A completed ticket should ultimately produce **one commit on `main`**.

When the PR is ready:

1. Ensure all changes are pushed.
2. Ensure validation passes.
3. Squash-merge the PR into `main`.

Prefer GitHub's squash merge functionality.

The resulting `main` history should contain one logical commit for the ticket.

The final commit message should describe the completed ticket.

Example:

```text
Add automatic title screen duration (#123)
```

Do not preserve a large collection of intermediate development commits on `main`.

---

# After Merge

After the PR is merged:

```bash
git checkout main
git pull --ff-only origin main
```

Verify that the expected changes are present.

If GitHub has not automatically closed the issue, close it.

Delete the feature branch after successful merge.

Remote branch:

```bash
git push origin --delete <branch>
```

Local branch:

```bash
git branch -d <branch>
```

Do not delete the branch before confirming that the PR was successfully merged.

---

# Ticket Completion

A ticket is complete only when all of the following are true:

* [ ] Implementation is complete.
* [ ] Acceptance criteria are satisfied.
* [ ] Relevant tests pass.
* [ ] No unintended changes remain.
* [ ] Feature branch was pushed.
* [ ] Pull Request was created.
* [ ] Pull Request is associated with the ticket.
* [ ] PR was self-reviewed.
* [ ] PR was squash-merged into `main`.
* [ ] `main` contains the completed change.
* [ ] Ticket is closed.
* [ ] Feature branch was deleted.
* [ ] Working tree is clean.

Only then should the ticket be considered finished.

---

# Working Tree Safety

Before starting a ticket:

```bash
git status
```

The working tree should be clean.

If uncommitted changes exist that were not created by the current ticket, do not overwrite or discard them.

Determine whether they belong to previous work before proceeding.

Never use destructive commands such as:

```bash
git reset --hard
git clean -fd
```

to remove unknown user changes.

Protect existing work.

---

# Handling Failures

If tests fail:

1. Investigate the failure.
2. Determine whether it is caused by the current change.
3. Fix the implementation when appropriate.
4. Rerun the tests.
5. Continue.

If a build or command fails because of the environment, determine whether it can be resolved autonomously.

Do not stop merely because the first attempt failed.

---

# Handling Ambiguity

Do not ask the user for confirmation for ordinary engineering decisions.

When requirements are ambiguous:

1. Inspect the existing implementation.
2. Inspect related tickets.
3. Inspect existing tests.
4. Follow established project conventions.
5. Choose the smallest reasonable implementation.
6. Document important assumptions in the PR description.

Only stop and request user input when the decision genuinely cannot be made safely from the repository, issue, and existing conventions.

---

# Handling Blocked Tickets

If a ticket cannot be completed because it depends on another unfinished ticket:

1. Determine whether the dependency can reasonably be completed first.
2. If yes, follow the appropriate ticket order.
3. Otherwise leave the ticket untouched and continue with independent tickets.

Never merge knowingly incomplete work merely to mark a ticket complete.

---

# Autonomous Operation

When given a list of tickets, process them sequentially.

For each ticket:

```text
READ
 ↓
UNDERSTAND
 ↓
BRANCH
 ↓
IMPLEMENT
 ↓
TEST
 ↓
REVIEW
 ↓
COMMIT
 ↓
PUSH
 ↓
OPEN PR
 ↓
SELF-REVIEW
 ↓
SQUASH MERGE
 ↓
VERIFY MAIN
 ↓
CLOSE ISSUE
 ↓
DELETE BRANCH
 ↓
NEXT TICKET
```

Do not wait for user confirmation between these stages.

After completing one ticket, immediately begin the next ticket.

---

# Important Principle

Work as if you are the developer responsible for the ticket.

The expected result is not merely modified code.

The expected result is:

```text
Issue
  → feature branch
  → implementation
  → tests
  → commits
  → Pull Request
  → self-review
  → squash merge
  → single commit on main
  → closed issue
  → deleted branch
```

The repository should look as though a human developer independently completed each ticket using the normal GitHub development workflow.

# Development Modes

Poiesis uses two development modes.

## Normal Development Mode

Unless explicitly instructed to work on a GitHub ticket, work normally.

Normal development work does NOT require:

- creating a GitHub issue
- creating a ticket branch
- opening a Pull Request
- associating a PR with an issue
- squash merging
- closing an issue

For small changes, experiments, debugging, refactoring, design work,
or changes explicitly requested by the user without reference to a ticket,
simply work in the current development branch following the normal Git workflow.

Do not create unnecessary GitHub tickets or Pull Requests.

## Ticket Development Mode

When the user explicitly asks you to work on a GitHub ticket, issue,
or ticket number, enter Ticket Development Mode.

In Ticket Development Mode, follow the complete autonomous GitHub workflow
defined below.

This includes:

1. Start from the latest `main`.
2. Create a dedicated ticket branch.
3. Implement the ticket.
4. Test and validate it.
5. Commit the work.
6. Push the branch.
7. Open a Pull Request.
8. Associate the PR with the ticket.
9. Self-review the PR.
10. Fix any issues found.
11. Squash-merge the PR into `main`.
12. Verify `main`.
13. Close the ticket.
14. Delete the ticket branch.
15. Continue with the next ticket if more tickets were assigned.

Do NOT enter Ticket Development Mode merely because a GitHub issue exists.

Only enter Ticket Development Mode when the user explicitly requests
ticket-based work.