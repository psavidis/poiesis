# Chapter Editing

## Goal

Allow users to edit chapter titles directly from the Poiesis editor using the same interaction model already established for editing Beats.

Chapter editing should feel like a natural extension of the existing Beat editing workflow rather than introducing a separate editing mechanism.

---

## User Story

As a video creator, I want to quickly edit a chapter title directly from the editor so that I can refine the structure and naming of my video without leaving the editor or opening a separate configuration panel.

---

## Interaction

When a Chapter is selected in the editor, pressing:

```text
Cmd + E
```

should enter edit mode for that Chapter.

The same keyboard shortcut and interaction pattern currently used for editing Beats should be reused.

The user should immediately be able to modify the chapter title.

No additional dialog or navigation should be required.

---

## Expected Behavior

Given a Chapter such as:

```text
Chapter 2
Why Event Sourcing?
```

the user selects the chapter and presses:

```text
Cmd + E
```

The chapter title becomes editable immediately.

The user can modify it, for example:

```text
Why You Should Use Event Sourcing
```

After confirming the edit, the new title should immediately be reflected throughout the editor.

The editor should not require a reload.

---

## Live Editor Reflection

Changes to a chapter title must be reflected immediately in every relevant place in the editor.

For example, if the chapter title is displayed:

* In the timeline
* In the chapter list
* In the video structure/navigation
* In the relevant preview UI

all affected representations should update to the new value.

There should be a single underlying chapter value rather than independent values maintained by different UI components.

---

## Editing Lifecycle

The expected interaction should follow the same lifecycle as Beat editing:

```text
Chapter selected
      ↓
Cmd + E
      ↓
Chapter enters edit mode
      ↓
User changes title
      ↓
User confirms
      ↓
Chapter model is updated
      ↓
Editor immediately reflects new title
```

If the existing Beat editing mechanism already defines behavior for:

* Confirming an edit
* Cancelling an edit
* Keyboard navigation
* Focus management
* Escape handling
* Validation

Chapter editing should reuse those behaviors rather than implementing chapter-specific alternatives.

---

## Consistency With Beats

The primary requirement is **interaction consistency**.

A user who already knows how to edit a Beat should not need to learn a different workflow for editing a Chapter.

For example:

```text
Beat selected
    → Cmd + E
    → Edit
    → Confirm

Chapter selected
    → Cmd + E
    → Edit
    → Confirm
```

The specific UI presentation may differ where necessary because a Chapter has different content, but the interaction model should remain consistent.

---

## Data Model

The chapter title should be part of the canonical Chapter model.

The UI must not maintain a separate title value solely for display purposes.

Conceptually:

```text
Chapter
├── id
├── title
└── ...
```

The editor should render the title from the Chapter model.

When the title changes, the Chapter model is updated and all dependent UI representations react to that change.

---

## Scope

This feature concerns editing the **Chapter title**.

It does not yet require editing:

* Chapter duration
* Chapter ordering
* Chapter boundaries
* Chapter visual styling
* Chapter thumbnails
* Chapter metadata
* YouTube chapter timestamps

Those can be separate features.

---

## Design Principle

Chapter editing should reinforce a broader Poiesis principle:

> **Anything that can be meaningfully edited directly in the editor should be editable through the editor without requiring the user to leave the current workflow.**

The editor should progressively become a direct manipulation interface for the semantic video model.

---

## Acceptance Criteria

* [ ] A Chapter can be selected in the editor.
* [ ] Pressing `Cmd + E` on a selected Chapter enters edit mode.
* [ ] The chapter title becomes immediately editable.
* [ ] The editing interaction follows the existing Beat editing behavior.
* [ ] The user can confirm the change.
* [ ] The user can cancel the change using the same mechanism as Beat editing.
* [ ] The underlying Chapter model is updated when the edit is confirmed.
* [ ] The updated title is immediately reflected in the editor.
* [ ] All editor views displaying the Chapter title use the updated value.
* [ ] No page reload is required.
* [ ] No separate chapter-editing dialog is introduced.
* [ ] Existing Beat editing behavior is not regressed.
* [ ] Tests cover the Chapter editing interaction and resulting model/UI update.
