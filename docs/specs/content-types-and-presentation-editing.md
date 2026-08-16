# Content Types and Presentation Editing

## Goal

Poiesis should provide a clear visual editing model for the different types of visual content that can appear during a video.

The current model treats Moments as a broad container for several fundamentally different types of content, including:

* Text
* Images
* Diagrams
* Code

This should evolve into a more explicit model where the editor distinguishes between:

1. **Content type** — what the asset represents.
2. **Presentation** — how that content is shown to the viewer.

This distinction is important because the same content can be presented in multiple ways.

For example, code may be:

* Displayed alongside the talking head.
* Displayed as the dominant visual while the talking head is minimized.
* Displayed full screen.
* Displayed as a smaller visual element.

The editor should make these choices visible and easy to modify.

---

# 1. Content Types

Poiesis should recognize different types of visual content.

The initial supported content types are:

* Text
* Image
* Diagram
* Code

Additional content types may be added later.

The content type describes the underlying content, not how it is displayed.

For example:

```text
Code
```

describes the content.

It does not determine whether the code is full screen, split screen, or shown alongside the talking head.

---

# 2. Presentation Types

The editor should support different ways of presenting content.

The initial presentation types should include:

* Inline
* Full Screen
* Split Screen
* Content Dominant
* Overlay

The exact visual implementation of these presentations should follow the existing Poiesis visual language.

The important principle is that presentation is configurable independently from content type.

Example:

```text
Code
    ├── Inline
    ├── Split Screen
    ├── Content Dominant
    └── Full Screen
```

Similarly:

```text
Image
    ├── Inline
    ├── Overlay
    └── Full Screen
```

Not every content type needs to support every presentation type.

The editor should only expose presentations that are meaningful for the selected content.

---

# 3. Full Screen as a First-Class Element

Full Screen should be a first-class presentation in Poiesis.

It should not be treated merely as another variation of a Moment.

A Full Screen presentation temporarily makes the selected content the primary visual content of the video.

Examples:

* A large architecture diagram.
* An important image.
* A complete code example.
* A conceptual illustration.
* A dramatic textual statement.

Conceptually:

```text
Talking Head
      ↓
Full Screen
      ↓
Talking Head
```

The Full Screen should have its own timeline representation and editable duration.

---

# 4. Asset Folders as Authoring Metadata

Users should be able to provide assets to Poiesis using categorized folders.

For example:

```text
assets/
├── images/
├── diagrams/
├── code/
└── full-screen/
```

The folder structure provides information to Poiesis about the user's intention.

For example:

```text
assets/full-screen/example.png
```

suggests:

> This asset is intended to be displayed as a Full Screen visual.

Likewise:

```text
assets/code/example.java
```

suggests:

> This asset is code and should be considered for a code-specific presentation.

The folder structure should therefore be treated as **authoring metadata / hints**, not as the final domain representation.

Poiesis should interpret these hints and create the appropriate semantic representation in the video model.

---

# 5. Asset Type vs Presentation

The system must not permanently couple asset folders to presentation types.

For example:

```text
code/example.java
```

does not mean that the code must always be displayed inline.

The user may later change it to:

```text
Code → Full Screen
```

Similarly:

```text
full-screen/example.png
```

provides an initial presentation hint, but the user should still be able to change the presentation in the editor.

This allows the AI and the user to make different presentation decisions without changing the underlying asset.

---

# 6. Visual Timeline Representation

Each content/presentation element should have a clear visual representation on the timeline.

The editor should make it possible to distinguish different types of content at a glance.

Conceptually:

```text
Timeline

Text       [───────]

Image            [──────────]

Diagram                    [──────]

Code                              [────────────]

Full Screen                                      [──────────]
```

The exact visual design is implementation-specific, but the user should be able to immediately understand:

* What the element is.
* When it appears.
* How long it remains visible.
* Which element is selected.
* How the element is presented.

The visual language should be consistent with the existing Beat timeline representation.

---

# 7. Selecting an Element

When the user selects a visual element, the editor should expose the properties relevant to that element.

For example, selecting Code could expose:

```text
CODE

Presentation
[ Content Dominant ▼ ]

Talking Head
[ Small Right ▼ ]

Duration
[ 8.0s ]

Position
[────────●────────]
```

Selecting an Image might expose:

```text
IMAGE

Presentation
[ Full Screen ▼ ]

Duration
[ 5.0s ]
```

The editor should not expose irrelevant configuration options.

The available controls should depend on the selected content type and presentation.

---

# 8. Presentation Editing

The user must be able to change how an element is presented without replacing the underlying content.

Example:

```text
Code
    ↓
Full Screen
```

can be changed to:

```text
Code
    ↓
Content Dominant
```

without replacing the code asset.

The change should immediately be reflected in the editor preview.

---

# 9. Code Presentation

Code requires specialized presentation options because code is frequently used in software-engineering videos.

The initial code presentation options should support at least:

### Full Screen

The code occupies the primary visual canvas.

```text
┌──────────────────────────────┐
│                              │
│          CODE                │
│                              │
│                              │
└──────────────────────────────┘
```

The talking head is hidden or temporarily replaced.

---

### Split Screen

The talking head and code are displayed simultaneously.

```text
┌──────────────┬───────────────┐
│              │               │
│    CODE      │  TALKING HEAD │
│              │               │
└──────────────┴───────────────┘
```

---

### Content Dominant

The content occupies most of the screen while the talking head remains visible in a smaller region.

```text
┌──────────────────────────────┐
│                              │
│            CODE          ┌───┤
│                          │TH │
│                          └───┤
└──────────────────────────────┘
```

The user should be able to select the appropriate presentation easily.

---

# 10. Presentation Parameters

Presentation types may expose parameters that the user can modify.

Examples include:

* Duration
* Talking-head visibility
* Talking-head size
* Talking-head position
* Content size
* Content position
* Layout
* Padding
* Zoom
* Alignment

Not every presentation needs every parameter.

The editor should expose only the parameters relevant to the selected presentation.

---

# 11. Timeline Duration Editing

All time-based visual elements must support direct timeline manipulation.

The user should be able to:

* Drag an element to change its start time.
* Resize the beginning of an element.
* Resize the end of an element.
* Change its duration.
* Zoom the timeline for precision.

This should use the same interaction model already established for Beats and Moments.

For example:

```text
       ← resize → 
       [──── CODE ─────]
                       ← resize →
```

Dragging the body moves the element.

Dragging either boundary changes its duration.

---

# 12. AI as the Initial Decision Maker

The AI should be able to make an initial presentation decision based on:

* The script.
* The semantic meaning of the content.
* The asset type.
* The asset folder.
* User-provided hints.
* Existing visual conventions.

For example:

```text
User provides:

assets/code/kafka-consumer.java
```

The AI may decide:

```text
Content: Code
Presentation: Content Dominant
Duration: 8 seconds
Talking Head: Small Right
```

The user can then inspect and modify this decision in the editor.

---

# 13. Human Override

AI decisions must always be editable.

The AI is responsible for creating a useful first draft.

The user is responsible for the final presentation.

The intended workflow is:

```text
Asset + Script
      ↓
AI interpretation
      ↓
Initial presentation
      ↓
Visual editor
      ↓
Human correction
      ↓
Final presentation
```

The editor should make these corrections extremely fast.

---

# 14. Relationship to Beats and Moments

Beats and Moments should not become overloaded containers for every possible visual concept.

The editor should distinguish between:

* Narrative/visual interventions.
* Underlying content.
* Presentation mode.

For example:

```text
Content
    Code
       ↓
Presentation
    Full Screen
       ↓
Timeline Element
    [──────────────]
```

A Beat or Moment may still be used where appropriate, but the underlying content and presentation should remain explicit.

This prevents the domain model from becoming a collection of special cases such as:

```text
Moment
├── text
├── image
├── diagram
├── code
├── fullScreen
└── ...
```

Instead, the model should conceptually move toward:

```text
Content
├── Text
├── Image
├── Diagram
└── Code

Presentation
├── Inline
├── Full Screen
├── Split Screen
├── Content Dominant
└── Overlay
```

with compatibility between content types and presentation types.

---

# 15. Editor Goal

The editor should visually communicate this model without requiring the user to understand its internal implementation.

The user should be able to look at the timeline and understand:

> "This is an image, it appears here, it lasts five seconds, and it is currently full screen."

or:

> "This is code, it appears here, it lasts eight seconds, and the talking head is minimized on the right."

The user should not need to manipulate raw video tracks, compositions, layers, or renderer configuration.

---

# 16. Product Principle

Poiesis should progressively become an editor of **semantic visual decisions** rather than an editor of low-level video mechanics.

The user should primarily manipulate concepts such as:

```text
What?
    Code

How?
    Content Dominant

When?
    03:42–03:50

Supporting presentation?
    Talking Head → Small Right
```

rather than:

```text
Track 4
Clip 17
Transform X=...
Transform Y=...
Scale=...
Opacity=...
```

The latter belongs to traditional NLE software.

The former is the intended Poiesis experience.

---

# Acceptance Criteria

* [ ] The editor distinguishes content type from presentation.
* [ ] Text, Image, Diagram, and Code are represented as distinct content types.
* [ ] Full Screen is supported as a first-class presentation.
* [ ] Assets can provide initial categorization through folders or equivalent metadata.
* [ ] Asset folder categorization is treated as authoring metadata rather than a permanent presentation constraint.
* [ ] A user can change an element's presentation without replacing its content.
* [ ] Visual elements have a clear timeline representation.
* [ ] Users can move visual elements on the timeline.
* [ ] Users can resize visual elements on the timeline.
* [ ] Timeline zoom works for these elements using the existing interaction model.
* [ ] Selecting an element exposes relevant presentation parameters.
* [ ] Irrelevant parameters are not exposed.
* [ ] Images can be presented as Full Screen.
* [ ] Diagrams can be presented as Full Screen.
* [ ] Code supports Full Screen presentation.
* [ ] Code supports Split Screen presentation.
* [ ] Code supports a Content Dominant presentation with a minimized talking head.
* [ ] Code presentation parameters can be edited by the user.
* [ ] Full Screen duration can be edited directly on the timeline.
* [ ] AI can make initial presentation decisions.
* [ ] AI-generated presentation decisions can be overridden by the user.
* [ ] Changes are immediately reflected in the editor preview.
* [ ] The underlying semantic model remains the source of truth.
* [ ] The implementation does not introduce separate ad-hoc models for each combination of content and presentation.
* [ ] Existing Beat and Moment editing behavior continues to work.
