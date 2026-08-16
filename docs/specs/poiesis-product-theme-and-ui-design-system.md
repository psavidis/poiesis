# Poiesis Product Theme and UI Design System

## Goal

Transform the current Poiesis interface from a collection of individually styled UI elements into a cohesive, intentional product interface.

The existing video-oriented editor structure is valuable and should be preserved.

The goal is not to redesign the product from scratch.

The goal is to establish a consistent visual language and layout system across the entire application so that Poiesis feels like a real, polished product.

The interface should feel:

* Professional
* Minimal
* Modern
* Video-oriented
* Calm
* Focused
* Cohesive
* Purpose-built

---

# 1. Preserve the Existing Editor Concept

The current high-level editor structure is considered a good foundation.

In particular, the following concepts should remain central:

```text
Video
   ↓
Video Player
   ↓
Timeline / Visual Elements
   ↓
Editing / AI Interaction
```

The visual redesign must not unnecessarily replace this structure.

The existing video-first approach should remain the dominant mental model.

The redesign should improve:

* Layout
* Alignment
* Spacing
* Typography
* Colors
* Components
* Visual hierarchy
* Consistency
* Responsiveness

without destroying the existing editing workflow.

---

# 2. Center the Application

The current interface is visually biased toward the left side of the screen.

The primary editor should instead be centered within the available viewport.

Conceptually:

```text
Current:

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│ ┌──────────────────────────────┐                            │
│ │                              │                            │
│ │          VIDEO               │                            │
│ │                              │                            │
│ └──────────────────────────────┘                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Target:

```text
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│             ┌──────────────────────────────┐                │
│             │                              │                │
│             │            VIDEO             │                │
│             │                              │                │
│             └──────────────────────────────┘                │
│                                                             │
│             ┌──────────────────────────────┐                │
│             │          TIMELINE            │                │
│             └──────────────────────────────┘                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

The editor should use a deliberate maximum content width rather than allowing content to remain attached to the left edge.

The exact maximum width should be determined based on the actual video/editor proportions and responsive behavior.

---

# 3. Establish a Product Theme

Poiesis should have a recognizable visual identity.

Every major UI element should feel like it belongs to the same product.

This includes:

* Buttons
* Inputs
* Text fields
* Timeline elements
* Panels
* Cards
* Menus
* Dialogs
* Toolbars
* AI interface
* Video controls
* Chapter elements
* Beats
* Moments
* Full Screens
* Icons
* Empty states
* Notifications
* Loading states

The application should not look like independently styled HTML elements assembled together.

---

# 4. Primary Visual Direction

The default theme should be based on a **light / white interface**.

The visual language should work naturally with the Poiesis logo and branding.

The UI should generally feel:

```text id="z7tx5n"
Light
Clean
White
Soft
Minimal
Modern
Technical
```

White should be the dominant surface color.

Supporting neutral tones should provide hierarchy without making the interface visually heavy.

Avoid excessive use of:

* Strong borders
* Dark panels
* Heavy shadows
* Highly saturated colors
* Random accent colors
* Excessive gradients
* Visually noisy backgrounds

---

# 5. Brand Integration

The Poiesis logo should feel naturally integrated into the interface.

The application theme should derive its visual character from the logo rather than treating the logo as an unrelated image placed into the UI.

The brand should influence:

* Accent color
* Highlight color
* Button states
* Selection states
* Focus states
* Active timeline elements
* AI interaction states

The logo should inform the design system, but the interface should remain restrained.

The goal is:

> recognizable branding without turning every component into a branded graphic.

---

# 6. Design Tokens

The UI should establish centralized design tokens rather than allowing individual components to define arbitrary values.

At minimum, establish tokens for:

## Colors

* Background
* Surface
* Elevated surface
* Border
* Primary text
* Secondary text
* Muted text
* Accent
* Accent hover
* Accent active
* Selection
* Success
* Warning
* Error

## Typography

* Font family
* Heading sizes
* Body size
* Small text
* Caption text
* Font weights
* Line heights

## Spacing

A consistent spacing scale should be used throughout the application.

For example:

```text id="guk7xk"
4
8
12
16
24
32
48
64
```

The exact scale can be adjusted during implementation.

## Radius

Components should use a consistent border-radius system.

## Shadows

Use a small number of consistent elevation levels.

---

# 7. Typography

Typography should establish a clear hierarchy.

The UI should distinguish clearly between:

* Application/navigation text
* Video/chapter titles
* Element names
* Secondary information
* Timeline labels
* AI conversation
* Controls
* Metadata

Typography should feel deliberate rather than relying on browser defaults.

Avoid excessive font-size variation.

---

# 8. Buttons

Buttons should share a consistent visual language.

The product should define clear variants such as:

```text id="9syjbu"
Primary
Secondary
Tertiary / Ghost
Destructive
Icon
```

Buttons should have consistent:

* Height
* Padding
* Border radius
* Typography
* Icon alignment
* Hover behavior
* Active behavior
* Disabled behavior
* Focus behavior

A button should look like a Poiesis button regardless of which feature uses it.

---

# 9. Inputs

Text inputs, text areas, and editing fields should share the same visual system.

Inputs should have consistent:

* Background
* Border
* Radius
* Typography
* Focus state
* Placeholder style
* Disabled state

Inline editing should feel like part of the same system as larger form inputs.

This is particularly important for:

* Chapter editing
* Beat editing
* Moment editing
* AI input
* Configuration controls

---

# 10. Cards and Panels

Panels should be used intentionally to establish hierarchy.

Avoid turning every section into a separate card.

The editor should feel like a coherent workspace rather than a dashboard composed of dozens of floating boxes.

Use:

* Spacing
* Background changes
* Typography
* Subtle borders

to establish grouping before relying on heavy shadows or card containers.

---

# 11. Timeline Design

The timeline is one of the most important parts of Poiesis.

It should receive special attention in the design system.

The current concept of visual bars representing Beats, Moments, and other elements should remain.

However, these bars should become visually consistent with the overall product theme.

The timeline should clearly communicate:

* Element type
* Selection
* Duration
* Start/end boundaries
* Current playhead
* Chapter boundaries
* Hover state
* Editing state

Different semantic element types may have distinct visual treatments, but those treatments must belong to the same design system.

---

# 12. Video Player

The video player should remain the primary visual focus of the application.

It should have strong visual hierarchy without overwhelming the surrounding editor.

The relationship should be:

```text id="y1j5cs"
             VIDEO
               ↓
            TIMELINE
               ↓
        EDITING CONTROLS
               ↓
          AI INTERACTION
```

The user should immediately understand that the video is the central artifact being edited.

---

# 13. AI Interface

The AI Editing Interface should be visually integrated into the product theme.

It should not look like a generic chatbot pasted underneath the editor.

The AI interface should feel like an integral editing tool.

Its visual design should communicate:

> "This is another way of controlling the video."

rather than:

> "This is an external AI service."

The AI interface should share:

* Typography
* Buttons
* Inputs
* Accent color
* Spacing
* Border radius
* Icons
* Interaction states

with the rest of the application.

---

# 14. Selection and Focus

Selection should be visually clear throughout the editor.

When an element is selected, the user should immediately understand:

* Which element is selected.
* What type of element it is.
* Where it exists on the timeline.
* Which properties can be edited.

Selection styling should be consistent across:

* Beats
* Moments
* Chapters
* Images
* Diagrams
* Code
* Full Screens

---

# 15. Visual Hierarchy

The application should establish a clear hierarchy.

The user should naturally perceive:

```text id="i1s0p7"
1. Video
2. Timeline
3. Selected / editable element
4. Editing controls
5. AI interaction
6. Secondary information
```

Not every element should compete for attention.

The interface should deliberately emphasize the current task.

---

# 16. Whitespace

Whitespace should be used deliberately.

The current left-aligned layout should not simply be moved to the center while retaining the same spacing.

The redesign should establish:

* Comfortable margins
* Consistent vertical rhythm
* Appropriate separation between major sections
* Clear grouping
* Enough space around the video
* Enough space around timeline elements

The interface should feel spacious without becoming wasteful.

---

# 17. Responsive Behavior

The editor should adapt gracefully to different viewport sizes.

The centered workspace should not become unusable on smaller screens.

At minimum, define behavior for:

* Large desktop
* Standard desktop
* Smaller desktop/laptop

The video and timeline should retain priority.

Secondary UI may compress or collapse when necessary.

---

# 18. Consistency Rules

Components should not introduce one-off styling unless there is a clear reason.

For example, avoid situations where:

```text id="o0a1gy"
Button A → 6px radius
Button B → 10px radius
Button C → no radius

Input A → dark border
Input B → light border
Input C → shadow

Panel A → 12px padding
Panel B → 18px padding
Panel C → 24px padding
```

Instead, components should derive their appearance from shared design tokens.

---

# 19. Component Library

The project should establish reusable UI components for recurring patterns.

Examples:

```text id="3f1drj"
Button
IconButton
Input
TextArea
Select
Dropdown
Panel
Toolbar
Badge
Tooltip
Dialog
ContextMenu
TimelineElement
TimelineTrack
PropertyEditor
AIInput
AIMessage
```

The exact component list should evolve with the application.

The important requirement is that repeated visual patterns should have reusable implementations.

---

# 20. Avoid Generic Dashboard Aesthetics

Poiesis should not become a generic SaaS dashboard.

Avoid unnecessary:

* Sidebars
* Dashboard cards
* KPI widgets
* Large navigation structures
* Excessive panels
* Dense enterprise-style controls

The product is fundamentally a creative editing workspace.

The interface should feel closer to a **focused creative tool** than to an administration dashboard.

---

# 21. Product Personality

The final interface should communicate:

> **A small, sophisticated tool built specifically for modern AI-assisted video creation.**

It should feel intentional.

The user should be able to open Poiesis and immediately perceive:

* This is a video editor.
* This editor is purpose-built.
* It has its own visual identity.
* The interface is cohesive.
* The product is mature enough to trust with real video projects.

---

# 22. Design Principle

The most important principle is:

> **Poiesis should look like one product, not a collection of UI components.**

Every component should answer the same visual language.

The redesign should therefore prioritize system-level consistency over isolated visual improvements.

A beautiful button is not the goal.

A beautiful button that belongs to the same visual system as the timeline, video player, AI interface, chapter editor, Moments, Beats, and property controls is the goal.

---

# 23. Implementation Approach

Before modifying individual components, establish the global design system.

Recommended order:

1. Define color tokens.
2. Define typography.
3. Define spacing scale.
4. Define border radius.
5. Define elevation/shadows.
6. Define button variants.
7. Define input styles.
8. Define panel/surface styles.
9. Establish global page/workspace width.
10. Center the main editor.
11. Restyle the video player.
12. Restyle the timeline.
13. Restyle element bars.
14. Restyle editing controls.
15. Integrate the AI interface.
16. Audit remaining components for consistency.

Avoid fixing components independently before establishing the global system.

---

# Acceptance Criteria

* [ ] The primary editor workspace is centered.
* [ ] The existing video-oriented editor structure is preserved.
* [ ] The video remains the primary visual focus.
* [ ] The timeline remains directly below/associated with the video.
* [ ] A coherent light/white product theme is established.
* [ ] The theme visually complements the Poiesis logo.
* [ ] Shared design tokens exist for colors.
* [ ] Shared design tokens exist for typography.
* [ ] Shared design tokens exist for spacing.
* [ ] Shared design tokens exist for border radius.
* [ ] Shared design tokens exist for elevation/shadows.
* [ ] Buttons use a consistent design system.
* [ ] Inputs use a consistent design system.
* [ ] Panels use a consistent design system.
* [ ] Timeline elements use a consistent design system.
* [ ] Selection states are visually consistent.
* [ ] Hover/focus/active/disabled states are consistent.
* [ ] The AI interface uses the same product theme.
* [ ] Chapter, Beat, Moment, Code, Diagram, Image, and Full Screen UI elements belong to the same visual system.
* [ ] The UI does not rely on arbitrary one-off styling where reusable design tokens/components are appropriate.
* [ ] The application does not look like a generic SaaS dashboard.
* [ ] The interface feels like a focused creative/video-production tool.
* [ ] The design remains usable across common desktop viewport sizes.
* [ ] Existing editor functionality is not broken by the visual redesign.
