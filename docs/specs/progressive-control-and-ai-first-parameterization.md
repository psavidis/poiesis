# Progressive Control and AI-First Parameterization

## Goal

Poiesis should automatically make as many visual and editing decisions as possible.

The user should not be required to understand or configure the underlying complexity of video production.

However, every important automatically generated decision should be customizable when the user wants to intervene.

The product should therefore follow this principle:

> AI decides by default. The user controls by exception.

Poiesis should provide the convenience of an AI-assisted editor while preserving the control expected from a professional editing tool.

---

# 1. AI-First, Human-Controllable

The default workflow should be:

    User provides footage + script + assets
                  ↓
            AI analyzes content
                  ↓
          AI makes visual decisions
                  ↓
            Poiesis creates video
                  ↓
            User reviews result
                  ↓
        User intervenes where desired

The user should not have to configure every element manually.

Poiesis should automatically determine, where practical:

- Where Moments, Beats, Full Screens, and other elements should appear.
- How long elements should remain visible.
- Which template should be used.
- Which animation should be used.
- How images, code, diagrams, and text should be presented.
- When Full Screen visuals should appear.
- How transitions should behave.
- How text should enter and exit.
- How elements should be positioned.
- Which visual treatment best communicates the concept.

The user can then override any of these decisions.

---

# 2. Complexity Should Be Hidden, Not Removed

Poiesis should hide complexity from the default workflow.

It should NOT remove the underlying flexibility.

Traditional editor:

    Complexity
    ████████████████████
    User must understand it

Poiesis:

    AI
     ↓
    Good default
     ↓
    Simple controls
     ↓
    Advanced controls when requested

The complexity still exists in the system, but the user only encounters it when they explicitly choose to control it.

---

# 3. Progressive Disclosure

The UI should reveal complexity progressively.

The default state should expose only the most important controls.

Example:

    Moment

    Template
    [ Emphasis ]

    Animation
    [ Fade In ]

    Duration
    [ 1.5s ]

             Customize

If the user chooses `Customize`, additional controls become available.

The user controls when complexity becomes visible.

---

# 4. AI Decisions Must Remain Overrideable

Any meaningful decision made by the AI should be overrideable whenever technically practical.

Examples:

    AI chooses:
    Template = Dramatic

    User changes:
    Template = Minimal

    AI chooses:
    Animation = Fade In

    User changes:
    Animation = Slide In

    AI chooses:
    Duration = 2.2s

    User changes:
    Duration = 4s

    AI chooses:
    Presentation = Split Screen

    User changes:
    Presentation = Full Screen

The AI should not fight the user's explicit decision.

---

# 5. Explicit User Decisions Have Priority

The system should distinguish between AI-generated values and user-defined values.

Conceptually:

    AI Default
        ↓
    User Override
        ↓
    Final Value

Once the user explicitly changes a parameter, Poiesis should respect that decision.

The AI should not silently overwrite the user's choice during subsequent automatic processing.

---

# 6. Automatic vs Customized State

The UI should make it possible to understand whether a value is:

- Automatically determined.
- Inherited from a template.
- Explicitly customized by the user.

The visual distinction should be subtle and should not clutter the interface.

---

# 7. "Automatic" Should Be a Valid Parameter Value

For many properties, the default should effectively be:

    Automatic

Examples:

    Animation: Automatic
    Duration: Automatic
    Position: Automatic
    Scale: Automatic
    Transition: Automatic
    Template: Automatic

This means:

> Let Poiesis decide.

The user can replace `Automatic` with an explicit value whenever desired.

---

# 8. Reverting to AI Control

If a user manually overrides a parameter, they should be able to return it to automatic control.

For example:

    Animation
    [ Slide In ]

    Reset to Automatic

After resetting:

    Animation
    [ Automatic ]

Poiesis can once again determine the appropriate animation.

Customization should therefore not permanently increase complexity.

---

# 9. AI Should Consider User Preferences

AI decisions should eventually take into account persistent user preferences.

Examples:

    Preferred text animation:
    Fade In

    Preferred code presentation:
    Split Screen

    Preferred chapter transition:
    Cross Fade

    Preferred Full Screen duration:
    3–5 seconds

These preferences can influence automatic decisions.

The user should not need to repeatedly correct the same behavior.

---

# 10. Templates Should Support Automatic Decisions

Templates should not necessarily mean that the user manually selects a template every time.

Poiesis should be able to select templates automatically.

For example:

    Moment
    Template = Automatic

The AI may determine:

    → Technical Emphasis

The user can override it:

    → Minimal

This allows templates to function both as AI choices and user choices.

---

# 11. Animation Should Also Support Automatic Decisions

The same principle applies to animation.

Default:

    Animation = Automatic

Poiesis determines:

    Fade In

The user can choose:

    Slide In
    Scale In
    None

The user should never be forced to choose an animation.

---

# 12. Automatic Timing

Timing should be AI-driven wherever possible.

For example, Poiesis may determine:

    Moment duration = 1.8s

based on:

- Spoken sentence.
- Semantic importance.
- Reading speed.
- Visual complexity.
- Surrounding footage.
- Animation duration.

The user can override this:

    Duration = 3s

The same principle applies to:

- Beat duration.
- Full Screen duration.
- Image duration.
- Code duration.
- Transition duration.

---

# 13. Automatic Layout

Poiesis should automatically determine layouts whenever possible.

For example:

    Code
    → AI determines:
       talking head 30%
       code 70%

The user can override the layout or choose Full Screen.

The default experience should not require the user to understand layout mathematics.

---

# 14. Automatic Animation Composition

Poiesis should be able to compose multiple animation properties automatically.

For example:

    AI:

    Entrance:
    Fade In

    Emphasis:
    Subtle Scale

    Exit:
    Fade Out

The user should simply see:

    Animation
    [ Automatic ]

If desired, the user can open the customization interface and modify individual components.

---

# 15. Automatic Styling

The same principle applies to visual styling.

Poiesis should automatically determine:

- Font sizes.
- Font weights.
- Colors.
- Spacing.
- Positioning.
- Background treatment.
- Contrast.
- Visual hierarchy.

The user should not need to configure these for every element.

However, the user should be able to override them.

---

# 16. User Control Should Be Local

Customization should normally happen at the level where the user notices a problem.

For example:

    User notices:
    "This Moment is too small."

    Select Moment
        ↓
    Scale
        ↓
    120%

The user should not need to navigate through a global configuration system.

The UI should make local intervention easy.

---

# 17. Global Overrides

Power users should eventually be able to define global preferences.

Examples:

    Global Preferences

    Text animation:
    Fade In

    Code presentation:
    Split Screen

    Chapter transition:
    Cross Fade

    Default Full Screen duration:
    3s

These preferences influence AI decisions without requiring manual configuration of every element.

---

# 18. Three Levels of Control

The product should conceptually support three levels.

## Level 1 — Automatic

    AI decides everything.

This should be the default.

## Level 2 — Guided

    User chooses high-level options.

    Template
    Animation
    Presentation
    Duration

This should satisfy most users who want some control.

## Level 3 — Advanced

    User controls detailed parameters.

    Timing
    Easing
    Position
    Scale
    Opacity
    Animation composition
    etc.

This should be available to users who explicitly want it.

---

# 19. The UI Should Communicate the Levels Clearly

The interface should make it obvious that deeper controls exist without constantly displaying them.

For example:

    Animation
    [ Automatic ▼ ]

                 Customize

The important requirement is that advanced controls remain discoverable but do not dominate the default interface.

---

# 20. AI and Manual Editing Must Remain Symmetric

If the user changes something manually, the AI should understand the new state.

If the AI changes something, the user should be able to edit it manually.

There should be no distinction in the resulting video model.

Conceptually:

    Manual edit ─────┐
                     ├──> Semantic Video Model
    AI edit ─────────┘

This is critical to the product architecture.

---

# 21. Conversational Editing Must Support All Editing Operations

The AI conversation should not be limited to operations that are difficult to perform manually.

The user should be able to use natural language for both:

1. Operations that already exist in the UI.
2. Operations that require AI capabilities and do not yet have a direct UI equivalent.

Examples of normal editor operations:

    "Move this Moment two seconds later."

    "Make this text bigger."

    "Change this chapter title."

    "Extend this Full Screen by three seconds."

    "Change the image to full screen."

    "Make the code appear line by line."

Examples of AI-native operations:

    "Create a dramatic animation for this."

    "Make a visual that explains this concept."

    "Create a diagram showing the relationship between these services."

    "Make this section more visually engaging."

    "Create an animation that emphasizes the important part."

Both categories belong in the same conversational interface.

---

# 22. Conversational Customization of a User Selection

The user should be able to select a specific element, group, range, chapter, scene, or other meaningful selection in the editor and then describe what they want in free language.

The user should not be required to know the exact parameter or control that corresponds to their desired change.

For example:

    User selects:
    Moment #12

Then says:

    "Make this feel more dramatic."

The AI may determine that this means:

    Template → Dramatic
    Entrance → Scale + Fade
    Duration → slightly longer
    Emphasis → subtle scale

The user does not need to know which individual parameters are required.

Another example:

    User selects:
    Code element

User says:

    "Make the code the main focus but keep me visible."

The AI may determine:

    Presentation → Content Dominant
    Talking Head → Small
    Code → Large

Another:

    User selects:
    Chapter transition

User says:

    "Make this transition feel smoother and less abrupt."

The AI can determine an appropriate transition and parameters.

This is a core part of AI-assisted editing.

---

# 23. Free-Language Intent Over Parameter Knowledge

The user should not have to translate their creative intention into technical parameters.

Traditional workflow:

    "I want this to feel more dramatic."

    ↓
    Find animation controls

    ↓
    Choose entrance

    ↓
    Choose duration

    ↓
    Choose easing

    ↓
    Adjust scale

    ↓
    Adjust opacity

    ↓
    Preview

    ↓
    Repeat

Poiesis workflow:

    Select element

    ↓

    "I want this to feel more dramatic."

    ↓

    AI interprets intention

    ↓

    AI modifies the element

    ↓

    User reviews result

The AI should perform the translation between creative intent and technical parameters.

---

# 24. Conversational Refinement

The user should be able to iteratively refine a selection through conversation.

Example:

    User:
    Make this more dramatic.

    AI:
    Updated the Moment with a stronger visual treatment.

    User:
    That's too much.

    AI:
    Reduced the animation intensity.

    User:
    Keep the entrance but remove the exit animation.

    AI:
    Done.

The user should not need to restart the editing process.

The conversation should maintain context about the selected element and recent changes.

---

# 25. Selection Context

When the user has selected an element, the AI should automatically receive relevant context such as:

- Element type.
- Element content.
- Current template.
- Current animation.
- Current timing.
- Current presentation.
- Position.
- Duration.
- Nearby elements.
- Chapter.
- Script context.

This allows instructions such as:

    "Make this shorter."

    "Make this more dramatic."

    "Move it closer to the previous one."

    "Use the same style as the previous Moment."

    "Make this easier to read."

to be understood without requiring the user to explicitly identify the element.

---

# 26. Selection Can Represent More Than One Element

Conversational customization should support selection of:

- One element.
- Multiple elements.
- A timeline range.
- A chapter.
- A scene.
- Potentially an entire video section.

Examples:

    Select three Moments.

    "Make these use the same animation."

or:

    Select a chapter.

    "Make this chapter visually more dramatic."

or:

    Select a range.

    "Reduce the visual noise in this section."

The AI should apply changes consistently across the selection.

---

# 27. AI Should Translate Intent Into Existing Capabilities First

When the user's request can be fulfilled using existing Poiesis capabilities, the AI should use those capabilities.

For example:

    "Make this fade in."

should map to:

    Entrance = Fade In

rather than generating a new animation.

Similarly:

    "Make this full screen."

should use:

    Presentation = Full Screen

The AI should prefer existing semantic operations because they remain editable and predictable.

---

# 28. AI Should Generate New Capabilities When Necessary

If the requested result cannot be achieved using existing capabilities, the AI may create or compose a new visual treatment.

For example:

    "Create an animation where the architecture
    builds itself from left to right."

If no suitable preset exists, AI may generate a new animation.

The generated result should become part of the semantic editing model whenever practical.

---

# 29. AI Should Make the Technical Translation Invisible

The user should not have to know whether the AI performed:

    Template change
    +
    Animation change
    +
    Timing change
    +
    Layout change

The user only needs to express the desired result.

For example:

    "Make this look like an important key takeaway."

Poiesis can decide how to achieve that.

The AI is responsible for translating the creative instruction into concrete editing operations.

---

# 30. AI Should Show the Result, Not Just the Reasoning

After a conversational edit, the editor should immediately reflect the result.

The AI response should remain concise.

Example:

    User:
    Make this more dramatic.

    AI:
    Updated the Moment's visual treatment.

The primary feedback should be the changed editor state.

The conversation is secondary to the actual video result.

---

# 31. Undo and Conversational Edits

Conversational edits must integrate with the same undo system as manual edits.

For example:

    User:
    Make this more dramatic.

    AI:
    Updated the element.

    Undo

The user should be able to undo the entire AI operation.

If the AI changes multiple related properties, those changes should preferably be treated as one logical edit.

---

# 32. Automatic Values Should Remain Automatic Until Overridden

The AI should be free to optimize values that remain automatic.

For example:

    Animation = Automatic
    Duration = Automatic
    Position = Automatic

If the AI determines:

    Animation = Fade In

that does not necessarily mean the user has explicitly overridden the parameter.

The system should retain the distinction between:

    AI-selected value

and:

    User-selected value

This allows future AI optimization while preserving explicit user decisions.

---

# 33. User Overrides Should Be Stable

Once a user explicitly sets:

    Animation = Slide In

the system should treat that as an explicit preference.

Automatic AI operations should not replace it unless:

- The user asks AI to reconsider it.
- The user resets it to Automatic.
- A higher-level operation explicitly requires reconsideration.

---

# 34. "Let AI Decide" Should Be Explicitly Available

Every customizable parameter should ideally have a path back to automatic behavior.

For example:

    Animation
    [ Slide In ]

    Reset to Automatic

or conversationally:

    "Let AI choose the best animation."

This keeps the system fluid between automation and manual control.

---

# 35. AI-Assisted Editing Definition

Poiesis should ultimately provide the following editing loop:

                         USER
                           │
                 ┌─────────┴─────────┐
                 │                   │
             Direct UI          Natural Language
                 │                   │
                 │                Text / Voice
                 │                   │
                 └─────────┬─────────┘
                           ↓
                     AI / Editor
                     Interpretation
                           ↓
                      Semantic Actions
                           ↓
                    Semantic Video Model
                           ↓
                        Preview
                           ↓
                         USER

The user can continuously move between:

- Manual editing.
- AI-assisted editing.
- Automatic AI decisions.
- Explicit customization.

All four modes operate on the same video model.

---

# 36. Product Philosophy

The fundamental philosophy is:

> Poiesis should automate decisions, not remove control.

The product should avoid both extremes.

## Too much automation

    AI decides everything.
    User has little control.

## Too much configuration

    User must manually configure everything.
    AI becomes irrelevant.

The desired position is:

                     POIESIS

           Automatic ←──────→ Manual

           AI-first      Human-controlled
           defaults      exceptions

The AI should do the work until the user decides that they want to take control.

---

# 37. Complexity Is an Escape Hatch

Advanced configuration should be treated as an escape hatch.

The normal workflow should be:

    AI
     ↓
    Good result
     ↓
    User accepts

Only when the user is dissatisfied:

    AI
     ↓
    Good result
     ↓
    User wants change
     ↓
    Simple control
     ↓
    Still not enough
     ↓
    Advanced control

This is fundamentally different from traditional editors where the user begins with the complexity.

---

# 38. Core Product Rule

Every feature should have a sensible automatic behavior before exposing manual configuration.

Before adding a new parameter to the UI, ask:

1. Can Poiesis calculate this automatically?
2. Can AI make a reasonable default decision?
3. Does the user actually need to see this parameter?
4. If the user does need it, can it be hidden behind progressive disclosure?
5. Can the user override it locally without entering a complex editor?
6. Can the user return it to Automatic?
7. Can the user describe the desired result using natural language instead of manipulating the parameter manually?

If the answer is yes, the feature belongs in Poiesis.

---

# Acceptance Criteria

- [ ] AI automatically determines sensible visual defaults.
- [ ] AI automatically determines sensible timing where possible.
- [ ] AI automatically determines sensible templates.
- [ ] AI automatically determines sensible animations.
- [ ] AI automatically determines sensible layouts.
- [ ] AI automatically determines sensible styling.
- [ ] Users can override AI decisions.
- [ ] Users can override individual parameters without replacing the entire template.
- [ ] Users can return individual parameters to Automatic.
- [ ] The system distinguishes AI-generated values from explicit user overrides.
- [ ] Explicit user overrides are preserved during subsequent AI processing.
- [ ] AI can reconsider an explicit decision when the user asks it to.
- [ ] Advanced controls are hidden by default.
- [ ] Advanced controls are discoverable through progressive disclosure.
- [ ] Users can customize individual elements locally.
- [ ] Users can customize multiple selected elements.
- [ ] Users can customize chapters or larger video sections where appropriate.
- [ ] Users can use natural language to modify existing editor operations.
- [ ] Users can use natural language to express creative intentions rather than technical parameters.
- [ ] Users can select an element and describe the desired result conversationally.
- [ ] AI can translate creative intent into multiple underlying editing operations.
- [ ] AI prefers existing semantic capabilities when they can satisfy the request.
- [ ] AI can generate new visual treatments when existing capabilities are insufficient.
- [ ] Voice input can use the same conversational editing pipeline as typed input.
- [ ] Conversational edits immediately update the editor.
- [ ] Conversational edits integrate with the normal undo system.
- [ ] The current selection is automatically available as AI context.
- [ ] The AI can understand contextual references such as "this", "that", "the previous one", and "make it more dramatic".
- [ ] The AI can use script, transcript, timeline, and semantic element context when interpreting requests.
- [ ] Manual editing and AI editing operate on the same semantic video model.
- [ ] AI-generated results remain manually editable whenever technically practical.
- [ ] The system does not require users to understand traditional NLE concepts such as keyframes or animation curves for normal editing.
- [ ] The product remains simple for users who never want advanced customization.
- [ ] The product remains flexible enough for users who want detailed control.

---

# Core Principle

> Poiesis should make the decisions for the user until the user decides they want to make them themselves.

The product should not force the user to choose between:

- An easy AI tool with little control, and
- A powerful editor with overwhelming complexity.

Poiesis should provide:

> AI-first automation with an accessible escape hatch to human control.

That is the core definition of AI-assisted editing in Poiesis.