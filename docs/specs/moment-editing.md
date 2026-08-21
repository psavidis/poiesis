# Moment Editing

## Goal

Allow users to edit Moments that were created or populated by the AI.

A Moment may contain text generated or inferred by the AI, but that content is not necessarily correct or exactly what the creator wants to communicate.

The user must therefore be able to directly edit both:

1. The content of the Moment.
2. The temporal position and duration of the Moment.

Moment editing should reuse the existing interaction patterns established for Beat editing wherever possible.

---

## User Story

As a video creator, I want to correct or refine AI-generated Moments directly in the editor so that I can quickly fix inaccurate text and adjust when the Moment appears and disappears without leaving the editing workflow.

---

# 1. Editing Moment Content

## Interaction

When a Moment is selected, the user should be able to enter edit mode using the same mechanism used for editing Beats.

Pressing:

```text id="q8p0ym"
Cmd + E
```

should allow the user to edit the textual content of the Moment.

The editing experience should be immediate and local to the Moment.

No separate configuration screen should be required.

---

## Example

The AI creates:

```text id="n9z6ub"
"Kafka guarantees exactly once delivery"
```

The creator notices that this is inaccurate and changes it to:

```text id="3d2h5f"
"Kafka can support exactly-once processing"
```

The updated content should immediately be reflected in the editor.

---

## Live Reflection

When the Moment content is changed, every relevant representation of that Moment in the editor should update immediately.

The UI must use the canonical Moment model as the source of truth.

There should not be separate independently maintained text values for:

* Timeline representation
* Preview representation
* Moment editor
* Other Moment-related UI

---

# 2. Editing Moment Timing

Moments should support the same timeline manipulation capabilities that already exist for Beats.

The user must be able to visually adjust:

* Start time
* End time
* Duration

by manipulating the Moment's visual bar on the timeline.

---

## Timeline Zoom

Moment editing must work correctly at different timeline zoom levels.

The user should be able to:

* Zoom in to make the timeline more precise.
* Zoom out to see a larger portion of the video.
* Drag the Moment when zoomed in or out.
* Adjust its boundaries with the same interaction model used for Beats.

The purpose of zooming is to allow the user to move between:

**High-level editing**

```text id="my7b4b"
Large section of video
↓
Quickly understand where Moments occur
```

and:

**Precise editing**

```text id="2b0sj7"
Small section of video
↓
Precisely position Moment start/end
```

---

# 3. Moment Timeline Representation

A Moment should have a visible representation on the timeline similar to the existing Beat representation.

Conceptually:

```text id="l0gk9s"
Timeline

00:00        01:00        02:00        03:00
|------------|------------|------------|------------|

                  [      MOMENT      ]
                  ↑                  ↑
                start               end
```

The visual representation should communicate:

* Where the Moment starts.
* Where the Moment ends.
* How long it lasts.
* Which Moment is currently selected.

---

# 4. Moving a Moment

The user should be able to drag the Moment's timeline representation to change its position.

Dragging the body of the Moment should move the entire Moment while preserving its duration.

Example:

```text id="a6l3yk"
Before:

        [------ MOMENT ------]

After dragging:

              [------ MOMENT ------]
```

The underlying Moment start and end times must be updated accordingly.

---

# 5. Resizing a Moment

The user should be able to adjust the start and end boundaries independently.

Conceptually:

```text id="qj7qf6"
        ← resize → 
        [------ MOMENT ------]
                         ← resize →
```

Changing the left boundary changes the Moment's start time.

Changing the right boundary changes the Moment's end time.

The duration should update automatically.

---

# 6. Relationship Between Content and Timing

Content editing and timeline editing are independent operations.

Changing the text of a Moment must not unintentionally change:

* Start time
* End time
* Duration

Likewise, moving or resizing a Moment must not change its textual content.

---

# 7. Interaction Consistency With Beats

The existing Beat editing behavior should be treated as the reference implementation for Moment timeline interaction.

Where the Beat editor already supports:

* Timeline zoom
* Dragging
* Resizing
* Selection
* Keyboard interaction
* Visual feedback
* Snapping
* Precision positioning

Moments should use the same behavior unless there is a clear semantic reason not to.

The goal is for the user to learn one timeline editing model rather than a separate model for every element type.

For example:

```text id="5l3w6m"
Beat:
    Select → zoom → drag/resize → confirm

Moment:
    Select → zoom → drag/resize → confirm
```

---

# 8. AI-Generated Content Is Editable

AI-generated content must never be treated as immutable.

The AI is responsible for proposing content.

The user remains the final authority over the content of the video.

Therefore:

```text id="d0h1ft"
AI-generated Moment
        ↓
Human reviews
        ↓
Human edits if necessary
        ↓
Final Moment
```

The editor should make this correction workflow fast and obvious.

---

# 9. Data Model

The Moment should contain both its semantic content and temporal information in the canonical video model.

Conceptually:

```text id="4ksy2c"
Moment
├── id
├── content
├── start
├── end
└── ...
```

The exact implementation structure should follow the existing Poiesis architecture.

The important requirement is that the editor manipulates the canonical Moment representation rather than maintaining temporary UI-only state as the source of truth.

---

# 10. Scope

This feature covers:

* Editing Moment text/content.
* Selecting Moments.
* Entering Moment edit mode.
* Moving Moments on the timeline.
* Resizing Moments.
* Timeline zoom for precise Moment manipulation.
* Immediate reflection of changes in the editor.

This feature does not require:

* Creating new Moments manually.
* AI generation of new Moments.
* Advanced Moment styling.
* Changing Moment animation.
* Changing Moment templates.
* Changing Moment visual design.

Those should be handled by separate specifications.

---

# Acceptance Criteria

* [ ] A user can select an existing Moment.
* [ ] Pressing `Cmd + E` enters Moment content-editing mode.
* [ ] The user can modify the textual content of an AI-generated Moment.
* [ ] The edited content is immediately reflected in the editor.
* [ ] The canonical Moment model is updated when the edit is confirmed.
* [ ] Editing content does not modify Moment timing.
* [ ] A Moment has a visible timeline representation.
* [ ] The user can move a Moment by dragging its timeline representation.
* [ ] Moving a Moment preserves its duration.
* [ ] The user can resize the beginning of a Moment.
* [ ] The user can resize the end of a Moment.
* [ ] Resizing updates the Moment's timing.
* [ ] The user can zoom the timeline in and out while editing Moments.
* [ ] Moment manipulation remains usable at different zoom levels.
* [ ] The Moment timeline interaction follows the existing Beat interaction model.
* [ ] The editor immediately reflects timing changes.
* [ ] The preview reflects the updated Moment content and timing.
* [ ] AI-generated Moment content is fully editable by the user.
* [ ] Existing Beat editing behavior is not regressed.
* [ ] Tests cover content editing.
* [ ] Tests cover moving a Moment.
* [ ] Tests cover resizing a Moment.
* [ ] Tests cover timeline zoom and Moment manipulation at different zoom levels.
