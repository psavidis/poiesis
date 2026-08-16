# Poiesis Glossary

## Purpose

This glossary defines the canonical terminology used throughout Poiesis.

Poiesis is an AI-assisted video editor designed specifically for structured YouTube videos, particularly software-engineering and educational content.

The terminology in this document is part of the product model. Features, UI components, AI instructions, documentation, and implementation should use these terms consistently.

When a concept already exists in this glossary, do not introduce a competing synonym without a deliberate product decision.

---

# 1. Video

A **Video** is the complete audiovisual production being created in Poiesis.

A video contains the complete sequence of chapters, sections, beats, moments, media, captions, and other visual elements required to produce the final rendered video.

Example:

```text
Video
├── Chapter 1
├── Chapter 2
├── Chapter 3
└── Outro
```

---

# 2. Chapter

A **Chapter** is a major conceptual division of a video.

Chapters correspond to meaningful topics or stages in the narrative and are typically represented in the final YouTube video as chapters.

A chapter contains one or more sections or visual elements.

Example:

```text
Chapter 1 — What is Event Sourcing?
Chapter 2 — Why Event Sourcing?
Chapter 3 — Implementation
```

A chapter is primarily a **narrative structure**, not a visual effect.

---

# 3. Section

A **Section** is a smaller logical subdivision of a chapter.

Sections are useful when a chapter contains multiple related ideas that need to be visually or structurally separated.

Example:

```text
Chapter — Event Sourcing

Section — The Problem
Section — The Traditional Solution
Section — Event Sourcing
Section — Trade-offs
```

A section is optional. A chapter may contain sections or may directly contain visual elements.

---

# 4. Beat

A **Beat** is a discrete visual or audiovisual intervention that supports the spoken narrative.

A beat usually occurs at a specific point in the talking-head footage and temporarily adds something to the presentation.

Examples:

* A phrase appearing on screen
* A visual emphasis
* A small animation
* A short piece of supporting information
* An icon or graphic
* A short code fragment
* A visual callout

A beat is generally **small, contextual, and subordinate to the main presentation**.

Example:

```text
Talking Head
      ↓
Beat: "This is the important part"
      ↓
Talking Head
```

The defining characteristic of a beat is that it enhances the current moment without fundamentally replacing the main visual presentation.

---

# 5. Moment

A **Moment** is a visual communication element that appears during a specific point in the narrative to emphasize, explain, or reinforce an idea.

A moment is more general than a beat and may contain richer visual content or animation.

Examples:

* Animated text
* A highlighted concept
* A visual explanation
* An animated diagram
* A contextual graphic
* A visual comparison
* A large on-screen statement

A moment answers:

> "What should the viewer see right now to better understand what is being said?"

A moment may be visually larger or more elaborate than a typical beat.

---

# 6. Full Screen

A **Full Screen** is a visual element that temporarily replaces the primary talking-head presentation with a dedicated visual.

The full screen occupies the main visual canvas and is intended to make an idea more prominent, dramatic, or understandable.

Examples:

* Full-screen image
* Architecture diagram
* Screenshot
* Large code example
* Concept illustration
* Large textual statement
* B-roll footage

Example:

```text
Talking Head
      ↓
Full Screen: Architecture Diagram
      ↓
Talking Head
```

A full screen is different from a beat or moment because it is intended to become the **primary visual presentation** for its duration.

---

# 7. Talking Head

**Talking Head** refers to the primary video footage of the presenter speaking directly to the audience.

Talking-head footage is typically the default visual layer of a Poiesis video.

Other visual elements such as beats, moments, and full screens are introduced around or over the talking head.

---

# 8. Title

A **Title** is a textual visual element used to introduce or identify content.

Titles may appear at:

* The beginning of the video
* The beginning of a chapter
* The beginning of a section
* A specific point in the narrative

Examples:

```text
Event Sourcing Explained
```

```text
Chapter 2
Why Event Sourcing?
```

Titles are primarily structural or introductory visual elements.

---

# 9. Caption

A **Caption** is synchronized text representing spoken dialogue or important speech-related information.

Captions are generally associated with the timeline of the spoken content and may span a significant portion of the video.

Captions are different from moments and beats.

A caption represents **what is being said**.

A moment or beat represents **what should be visually communicated around what is being said**.

---

# 10. Code

A **Code** element displays source code as a visual part of the video.

Code may be used as:

* A beat
* A moment
* A full-screen visual

The distinction is based on presentation rather than content.

For example, a small highlighted line of code may be a beat, while a complete code example occupying the screen may be a full screen.

---

# 11. Diagram

A **Diagram** is a visual representation of a concept, relationship, architecture, process, or system.

Examples:

* Software architecture
* Sequence diagrams
* Data flow
* Entity relationships
* System interactions
* Process flows

A diagram may be presented as a moment or as a full-screen visual.

---

# 12. Image

An **Image** is a static visual asset used within the video.

Examples:

* Photograph
* Illustration
* Screenshot
* Logo
* Generated image
* UI screenshot

An image describes the underlying media asset. Its presentation can be a beat, moment, or full screen.

---

# 13. Video Asset

A **Video Asset** is a video file or video segment used as supporting visual material.

Examples:

* B-roll
* Screen recordings
* Demonstrations
* External footage
* Animated sequences

A video asset can be presented as a moment or full screen.

---

# 14. B-Roll

**B-Roll** is supporting video footage used to visually reinforce the narrative while the primary talking-head footage is reduced, covered, or replaced.

Examples:

* Screen recordings
* Product demonstrations
* Environmental footage
* Software usage
* Relevant supporting footage

B-roll is a type of media/content, not necessarily a specific editor element.

---

# 15. Asset

An **Asset** is any external media resource used by the video.

Examples:

* Images
* Videos
* Audio files
* Screenshots
* Fonts
* Logos
* Diagrams

An asset is the underlying resource. A visual element determines how that asset is presented in the video.

---

# 16. Timeline

The **Timeline** represents the temporal structure of the video.

It determines when visual and audiovisual elements begin, end, overlap, and transition.

In Poiesis, the timeline should primarily be understood through the semantic elements of the video rather than through traditional NLE concepts such as tracks and arbitrary clips.

Example:

```text
00:00  Talking Head
01:14  Beat
01:19  Talking Head
02:03  Moment
02:11  Talking Head
03:20  Full Screen
04:02  Talking Head
```

---

# 17. Element

An **Element** is a discrete item placed within the video structure.

Examples include:

* Beat
* Moment
* Full Screen
* Title
* Caption
* Code
* Diagram
* Talking Head

"Element" is a generic term and should be used when the specific type is not relevant.

---

# 18. Visual Element

A **Visual Element** is an element whose primary purpose is to communicate information visually.

Examples:

* Beat
* Moment
* Full Screen
* Title
* Code
* Diagram
* Image

---

# 19. Presentation

A **Presentation** describes how an underlying piece of content is displayed to the viewer.

For example, the same image asset could be presented as:

```text
Beat
Moment
Full Screen
```

This distinction is important:

**Content is not necessarily the same thing as presentation.**

An image is content.

A full-screen image is a presentation of that content.

---

# 20. Transition

A **Transition** describes the visual change between two elements.

Examples:

* Fade
* Cut
* Slide
* Zoom
* Morph

Transitions should remain secondary to the semantic elements of the video.

Poiesis should prefer a small set of opinionated transitions rather than attempting to reproduce the extensive transition systems of traditional video editors.

---

# 21. Render

A **Render** is the process of converting the Poiesis video representation into a playable video output.

Conceptually:

```text
Poiesis Video Model
        ↓
      Render
        ↓
   Video File
```

The render is an output of the editor, not the source representation.

---

# 22. Template

A **Template** is a reusable visual definition for an element.

Examples:

* Chapter title template
* Beat template
* Code template
* Full-screen image template
* Callout template
* Outro template

Templates allow Poiesis to maintain a consistent visual language across videos.

---

# 23. Visual Language

The **Visual Language** is the collection of visual conventions that define how a Poiesis video looks and behaves.

It includes:

* Typography
* Animation
* Spacing
* Layout
* Colors
* Motion
* Transitions
* Element styles
* Timing conventions

The visual language should be reusable across videos rather than manually recreated for every production.

---

# 24. AI Edit

An **AI Edit** is a modification to the video structure proposed or performed by an AI system.

Examples:

```text
Add a Moment after this sentence.
```

```text
Replace this image with a full-screen diagram.
```

```text
Add a Beat emphasizing "event-driven architecture".
```

```text
Move this visual earlier by 500ms.
```

AI edits should operate on Poiesis's semantic model rather than requiring the AI to manipulate low-level rendering details.

---

# 25. Editor

The **Editor** is the user-facing Poiesis application used to inspect, modify, and arrange the semantic elements of a video.

The Poiesis editor is intentionally smaller and more opinionated than a traditional non-linear video editor.

Its purpose is not to reproduce the feature set of applications such as DaVinci Resolve.

Its purpose is to make the specific editing workflow of structured YouTube videos fast and understandable.

---

# 26. Poiesis

**Poiesis** is an AI-assisted editor for structured YouTube videos.

Its primary goal is to allow AI to perform most of the repetitive video-production work while giving the human creator a simple visual interface for reviewing and correcting the result.

Poiesis is intentionally opinionated.

It should optimize for:

```text
AI creates
    ↓
Human reviews
    ↓
Human adjusts
    ↓
Poiesis renders
    ↓
Final touches / advanced editing elsewhere
```

Poiesis is not intended to replace professional non-linear video editors in every use case.

Its purpose is to make the creator's recurring video-production workflow dramatically faster.

---

# Terminology Rules

## Prefer canonical terms

Use the terminology defined in this document when discussing product features.

For example:

* Prefer **Beat** over "toast" or "popup".
* Prefer **Moment** over "overlay" when referring to a semantic communication element.
* Prefer **Full Screen** over "scene replacement" when referring to a visual that replaces the talking head.
* Prefer **Element** when the specific element type is irrelevant.

## Do not introduce synonyms casually

Terms such as "toast", "piece", "card", "popup", "overlay", "scene", and "clip" may be useful during implementation discussions, but they should not replace the canonical product terminology unless explicitly adopted into this glossary.

## Semantic model over implementation model

Product terminology should describe what the creator is trying to communicate, not how the renderer happens to implement it.

For example:

```text
Correct:
"Add a Full Screen showing the architecture diagram."

Implementation detail:
"Create a Remotion composition covering the talking-head layer."
```

The first is the product-level concept.

The second is an implementation detail.

---

# Core Mental Model

The central Poiesis mental model is:

```text
VIDEO
│
├── CHAPTER
│   ├── SECTION
│   │   ├── TALKING HEAD
│   │   ├── BEAT
│   │   ├── MOMENT
│   │   ├── CODE
│   │   ├── DIAGRAM
│   │   └── FULL SCREEN
│   │
│   └── SECTION
│
├── CHAPTER
│   └── ...
│
└── OUTRO
```

The important distinction is:

```text
Narrative structure
    ├── Chapter
    └── Section

Presentation
    ├── Talking Head
    ├── Beat
    ├── Moment
    └── Full Screen

Content
    ├── Text
    ├── Image
    ├── Video
    ├── Code
    └── Diagram

Supporting infrastructure
    ├── Asset
    ├── Template
    ├── Timeline
    └── Render
```

This vocabulary should remain intentionally small.

New concepts should only be introduced when an existing concept cannot accurately represent the intended user-facing behavior.
