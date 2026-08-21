# AI-Assisted Editing and Conversational Control

## Goal

Poiesis should provide an AI-native editing experience in which natural language and voice can be used to control the same semantic video model that is edited directly through the UI.

The existing AI input below the video editor should evolve from a simple command input into an integrated **AI Editing Interface**.

The AI should not exist as a separate feature disconnected from the editor.

Instead:

```text
                 ┌─────────────────────┐
                 │   Poiesis Video     │
                 │   Semantic Model    │
                 └──────────┬──────────┘
                            │
             ┌──────────────┴──────────────┐
             │                             │
       Direct Editing                AI Editing
       Mouse / Keyboard             Text / Voice
             │                             │
             └──────────────┬──────────────┘
                            │
                    Same Editing Model
```

The result of an AI instruction should be equivalent to performing the corresponding operation manually whenever that operation already exists in the editor.

---

# 1. AI Editing Is a First-Class Editing Interface

The AI interface should not be treated as a generic chatbot attached to the application.

It is an **editing interface**.

The user should be able to express editing intentions naturally:

```text
"Move this moment two seconds earlier."

"Change the title to 'Why Kafka Works'."

"Make this image full screen."

"Make the code smaller and keep me visible on the right."

"Extend this beat by two seconds."

"Change this animation from slide-in to fade-in."
```

The AI should interpret these requests as operations against the Poiesis video model.

---

# 2. Existing UI Operations Must Be Available Through AI

Any operation that the user can perform manually should, where practical, also be executable through natural language.

Examples:

```text
Manual:
Drag a Moment to the right.

AI:
"Move this Moment three seconds later."
```

```text
Manual:
Resize the right edge of a Beat.

AI:
"Make this Beat last two seconds longer."
```

```text
Manual:
Edit a Chapter title.

AI:
"Rename this chapter to 'Why Event Sourcing Matters'."
```

```text
Manual:
Change Code from Full Screen to Split Screen.

AI:
"Show the code alongside me instead of full screen."
```

The AI should therefore operate on the same underlying concepts as the UI.

---

# 3. Semantic Action Model

AI instructions should be translated into explicit semantic editing actions.

Conceptually:

```text
Natural Language
      ↓
AI Interpretation
      ↓
Editing Action
      ↓
Poiesis Video Model
      ↓
Editor Update
```

For example:

```text
User:
"Move the Kafka diagram closer to where I say
'event streaming'."

AI:
MoveElement(
    element = kafka-diagram,
    target = semantic-reference("event streaming")
)
```

The exact internal representation is implementation-specific.

The important principle is:

> The AI should modify the semantic video model, not directly manipulate arbitrary UI state.

---

# 4. Existing Operations and AI-Only Operations

AI editing should support two categories of operations.

## Category A — Existing Editor Operations

These are operations the user can already perform manually.

Examples:

* Edit text.
* Rename chapters.
* Move elements.
* Resize elements.
* Change duration.
* Change presentation mode.
* Change an image.
* Change code presentation.
* Change timing.
* Reorder elements.
* Change supported animation settings.

The AI should provide a natural-language alternative to these operations.

---

## Category B — AI-Only Operations

The AI should also be able to perform operations that are not currently exposed through direct UI controls.

Examples:

* Create a new graphic.
* Generate a new animation.
* Create an illustration explaining a concept.
* Generate a diagram from the script.
* Create a custom visual emphasis.
* Design a new animation for a Moment.
* Generate a visual transition.
* Create a new Beat based on spoken content.
* Create a new Full Screen visual.
* Combine multiple existing assets into a new presentation.
* Modify a visual style in ways not currently exposed through the UI.

This is where the AI becomes more than a natural-language wrapper around existing editor controls.

---

# 5. AI Should Be Able to Create Elements

The AI should be able to create new semantic elements when requested.

For example:

```text
"Add a Beat here saying:
'This is the key idea'."
```

or:

```text
"Create a Full Screen diagram explaining
how the producer communicates with Kafka."
```

or:

```text
"Create a visual showing the difference between
synchronous and asynchronous communication."
```

The AI should create the appropriate semantic element and insert it into the video model.

The new element should immediately become visible in the editor.

---

# 6. AI-Generated Graphics

AI should eventually be able to generate graphics that do not already exist as assets.

For example:

```text
"Create a simple animated graphic showing
three services communicating through Kafka."
```

The AI may generate:

```text
Graphic
    ↓
Animation
    ↓
Moment / Full Screen
```

The result should become an editable Poiesis element rather than an opaque piece of video whenever practical.

This is important because the user should retain control over the generated visual.

---

# 7. AI-Generated Animations

The AI should be able to create or modify animations.

Examples:

```text
"Make this text fade in."

"Make the diagram slide in from the right."

"Animate the arrows one after another."

"Make the code appear line by line."

"Give this Moment a more dramatic entrance."
```

If the requested animation corresponds to an existing supported animation, the AI should configure that animation.

If it does not correspond to an existing animation, the AI may create or generate a new animation.

---

# 8. Animation as a Configurable Property

Animations should be treated as properties of visual elements rather than hard-coded behavior.

Conceptually:

```text
Moment
├── content
├── presentation
├── timing
└── animation
      ├── entrance
      ├── emphasis
      └── exit
```

This allows both direct UI controls and AI instructions to modify animations.

For example:

```text
Animation:
    entrance = fade
```

can be changed by:

```text
"Use a slide-in instead."
```

---

# 9. AI Editing Should Be Reflected Visually

AI operations must not disappear into the conversation.

When the AI changes the video, the corresponding editor state should update immediately.

For example:

```text
User:
"Make the diagram full screen."

AI:
Done.

Editor:
[Diagram] ─────────────
Presentation: Full Screen
```

The user should be able to see exactly what changed.

AI and direct editing should therefore operate on the same live editor state.

---

# 10. Conversational Editing Loop

The AI interface should support an iterative conversational workflow.

Example:

```text
User:
"Show the architecture diagram after I explain
the database."

AI:
Adds the diagram after the relevant sentence.

User:
"It's too short."

AI:
Extends its duration.

User:
"Also make me smaller in the bottom right."

AI:
Changes the presentation.

User:
"Actually, make the diagram full screen for the first
three seconds, then bring me back on the right."

AI:
Creates the requested presentation sequence.
```

The conversation should retain enough context to understand references such as:

* "this"
* "that"
* "the previous one"
* "make it bigger"
* "move it earlier"
* "the diagram"
* "the code"
* "the last Beat"

---

# 11. Selection Provides Context

The currently selected editor element should be available as context to the AI.

For example:

```text
Selected:
Moment #17
Type: Text
Content: "Event sourcing is..."
Time: 04:32–04:36
```

The user can then simply say:

```text
"Make this bigger."
```

The AI should understand that "this" refers to the selected Moment.

Selection should therefore become an important bridge between direct manipulation and conversational editing.

---

# 12. Natural-Language References

The AI should be able to resolve references using multiple sources of context.

Potential references include:

* Current selection.
* Current playhead position.
* Visible timeline region.
* Element type.
* Element content.
* Chapter.
* Section.
* Nearby elements.
* Script text.
* Spoken dialogue.
* Asset names.
* Asset metadata.

For example:

```text
"Move the diagram after I mention CQRS."
```

should be resolvable using the script/transcript.

---

# 13. Voice Input

The AI Editing Interface should support voice input.

The user should be able to speak an instruction rather than type it.

The flow should be:

```text
User speaks
    ↓
Speech-to-text
    ↓
Natural-language editing instruction
    ↓
AI interpretation
    ↓
Editing action
    ↓
Editor update
```

The transcribed text should be visible to the user before or while it is submitted, depending on the interaction design.

The voice interface should feel like a natural extension of the conversational editor rather than a separate application feature.

---

# 14. Voice Editing Example

The user selects a Moment and speaks:

> "Make this appear half a second earlier and fade in."

Poiesis should:

```text
Speech
    ↓
Transcript
    ↓
Interpretation
    ↓
Move Moment
    ↓
Set entrance animation = fade
    ↓
Update editor
```

The user should not need to manually enter the same instruction.

---

# 15. Integrated AI Interface

The existing large input below the video player should be reconsidered as a product component.

It should not feel like:

```text
Video Editor
────────────────────

[ Timeline ]

[                    ]
[ Type something...  ]
[              Apply ]
```

The AI interface should feel integrated with the editing environment.

The exact UI is open for design, but it should provide:

* Natural-language input.
* Voice input.
* Conversation history.
* AI responses.
* Visibility into changes made.
* Relationship to the selected element.
* Ability to continue refining the previous operation.

The AI interaction should feel like part of the editor itself.

---

# 16. Conversation History

The user should be able to see the recent AI interaction.

Example:

```text
USER
Make the diagram full screen.

AI
Changed "Kafka Architecture" to Full Screen.

USER
Make it last five seconds.

AI
Changed duration to 5 seconds.

USER
Fade it in.

AI
Changed entrance animation to Fade.
```

The history does not need to become a full-featured chat application.

Its purpose is to support iterative editing.

---

# 17. AI Responses Should Describe Actions

AI responses should be concise and action-oriented.

Prefer:

```text
Changed the diagram to Full Screen.
Duration: 5 seconds.
```

over long explanations.

When useful, the response should identify the affected element.

For example:

```text
Updated:
Kafka Architecture

Presentation:
Full Screen

Duration:
5s
```

---

# 18. AI Actions Should Be Observable

The editor should make AI modifications visually apparent.

Potential mechanisms include:

* Highlighting modified elements.
* Showing temporary change indicators.
* Updating the selected element.
* Showing the changed property.
* Allowing the user to inspect the resulting state.

The user should never wonder:

> "What exactly did Claude change?"

---

# 19. Undo and Recovery

AI editing must integrate with the editor's undo model.

An AI operation should be treated as an editor operation.

Therefore, after:

```text
"Make the code full screen."
```

the user should be able to undo the resulting change using the same undo mechanism as a manual edit.

For complex AI operations involving multiple changes, the system should preferably treat the request as a coherent transaction.

Example:

```text
"Create a full-screen architecture diagram,
show it for five seconds, then return to the talking head."

```

should ideally be undoable as one logical operation.

---

# 20. AI Must Not Bypass the Semantic Model

AI-generated changes should ultimately produce valid Poiesis semantic elements and properties.

The AI should not directly modify:

* Renderer internals.
* Arbitrary DOM state.
* UI-only state.
* Generated video files as the primary editing representation.

The canonical video model remains the source of truth.

---

# 21. AI Capability Should Grow With the Product

As new direct editing capabilities are added to Poiesis, they should automatically become candidates for AI control.

For example, if Poiesis later adds:

```text
Animation:
    fade
    slide
    scale
    blur
```

the AI should be able to use those capabilities.

If a new element type is added:

```text
Callout
```

the AI should be able to create and modify Callouts.

The AI interface should therefore be designed as a layer over the evolving semantic editing system rather than as a collection of hard-coded commands.

---

# 22. AI as an Orchestration Layer

The long-term architecture should treat AI as an orchestration layer over Poiesis capabilities.

Conceptually:

```text
                 User
              /       \
          Mouse       Voice/Text
             \          /
              \        /
             AI / Direct
             Editing Layer
                    │
             Semantic Actions
                    │
             Video Model
                    │
                  Editor
                    │
                 Render
```

The AI should be able to compose multiple primitive operations into a higher-level result.

For example:

```text
"Make this section more visually engaging."
```

could potentially result in:

```text
Add Beat
Add Moment
Create Diagram
Change Code presentation
Add animation
Adjust timing
```

provided the AI can explain or expose the resulting changes.

---

# 23. Human Control Remains Primary

AI should accelerate editing, not make the editor opaque.

The user must always be able to:

* Inspect changes.
* Correct changes.
* Undo changes.
* Continue editing manually.
* Continue the conversation.
* Override AI decisions.

The ideal workflow is:

```text
AI proposes / executes
        ↓
User sees result
        ↓
User accepts or corrects
        ↓
AI or manual editing continues
```

---

# 24. Product Principle

Poiesis should converge toward the following principle:

> **Anything the user can reasonably describe, Poiesis should eventually be able to understand as an editing intention.**

There are two complementary paths:

### Direct manipulation

```text
"I know exactly what I want."

→ Select
→ Drag
→ Resize
→ Edit
→ Configure
```

### Conversational manipulation

```text
"I know what I want, but I don't want to manually construct it."

→ Describe it
→ AI interprets it
→ Poiesis performs it
→ User reviews it
```

Neither should replace the other.

They should operate on the same underlying editing model.

---

# Acceptance Criteria

* [ ] The existing AI input is integrated into the main editing experience.
* [ ] Natural-language instructions can modify existing editor elements.
* [ ] Existing manual editing operations can be expressed through natural language.
* [ ] AI operations modify the canonical semantic video model.
* [ ] AI changes are immediately reflected in the editor.
* [ ] The current selection is available as AI context.
* [ ] The AI can understand contextual references such as "this", "that", and "the previous one".
* [ ] The AI can use timeline and script context when resolving references.
* [ ] AI-generated changes can be undone using the normal editor undo mechanism.
* [ ] Multiple related AI operations can be treated as a coherent edit.
* [ ] The AI can create new Beats.
* [ ] The AI can create new Moments.
* [ ] The AI can create Full Screen elements.
* [ ] The AI can create or modify graphics.
* [ ] The AI can create or modify diagrams.
* [ ] The AI can modify animations.
* [ ] The AI can select existing animation types.
* [ ] The AI can create new visual treatments when existing editor capabilities are insufficient.
* [ ] Voice input is supported through speech-to-text.
* [ ] Voice instructions enter the same natural-language editing pipeline as typed instructions.
* [ ] The user can iteratively refine an AI edit conversationally.
* [ ] AI responses clearly communicate what was changed.
* [ ] AI modifications are visually identifiable in the editor.
* [ ] The AI interface does not become a separate editing system from the direct editor.
* [ ] New semantic editing capabilities can be exposed to AI without redesigning the entire AI interface.
* [ ] The system architecture treats AI as an orchestration layer over semantic editing actions rather than as a direct manipulator of renderer/UI internals.
