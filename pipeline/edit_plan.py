#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from llm.client import LLMClient  # noqa: E402
from generate_emphasis import (  # noqa: E402
    MAX_BEAT_WORDS,
    VALID_ICONS,
    VALID_KINDS,
    build_candidate_words,
    format_words_for_prompt,
    overlaps_existing_overlay,
    resolve_phrase,
)
from generate_moments import (  # noqa: E402
    TRANSITION_FRAMES,
    duration_for_treatment,
    format_assets_for_prompt,
    format_code_assets_for_prompt,
    group_transcript_by_clip,
    is_diagram_grounded,
    is_grounded,
)
from visual_placement import filter_segments_in_window  # noqa: E402
from style import load_style  # noqa: E402


PROMPT_FILE = PIPELINE_DIR / "prompts" / "edit_plan.txt"

# Must match MomentEntrance in video-renderer's types.ts exactly — the
# three entrance patterns BottomCallout.tsx's computeTransform actually
# implements (see #61-adjacent entrance-configuration work, docs/specs/
# ai-assisted-editing-and-conversational-control.md section 7). An
# "update" op's entrance value is checked against this in
# validate_operations indirectly via EDITABLE_FIELDS (which only checks
# the FIELD NAME is allowed, not the value) — resolve_bottom_callout_creation
# checks the VALUE directly, since a "create" op's fields aren't validated
# by validate_operations at all (see that function's own docstring).
VALID_ENTRANCES = {"scale", "slide", "fade"}

# Everything not listed here is read-only to natural-language edits: id/type
# never change what a scene fundamentally is, and videoId/parentSceneId/
# assetId repoint a scene at different footage/parent/asset rather than
# editing "this" scene — a structurally different (and much riskier)
# operation than the ones this endpoint is meant for. A moment's "treatment"
# is excluded for the same reason as "type": switching bottom-callout to
# side-text/side-image also changes what layout its parent presenter scene
# needs, which isn't something this endpoint reasons about — that's
# generate_moments.py's job, not a text edit. "layout" on presenter itself is
# likewise excluded — it's driven by whichever moment(s) target that scene,
# not edited independently.
EDITABLE_FIELDS = {
    "presenter": {"sourceStartFrame", "sourceEndFrame", "effects"},
    "title": {"text"},
    # "entrance" is only meaningful for treatment "bottom-callout" (see
    # MomentEntrance in video-renderer's types.ts) — included here rather
    # than validated per-treatment since EDITABLE_FIELDS is a per-type,
    # not per-treatment, allowlist (same coarseness "text" already has:
    # it's editable for every text-bearing treatment, not just one). A
    # field-level check for "does this treatment actually use this field"
    # isn't done anywhere else in this dict either.
    # "holdFromPrevious" (see MomentScene in video-renderer's types.ts)
    # merges this moment's presenter-side layout window into the
    # IMMEDIATELY PRECEDING moment's on the render side (Episode.tsx's
    # layoutWindowsForScene) — only takes effect when that preceding
    # moment already shares this one's own presenterSide, which stays
    # read-only here (unchanged from every other side-* field: layout
    # side is generate_moments.py's job, not a text edit).
    "moment": {"text", "assetId", "caption", "offsetInParentFrames", "durationInFrames", "entrance", "holdFromPrevious"},
    "caption": {"text", "offsetInParentFrames", "durationInFrames"},
    # "assetId"/"display" are included here (unlike moment's "assetId",
    # which stays read-only) because changing which image is shown or
    # whether it's full-screen vs. inset is a direct, low-risk field swap
    # for this scene type — there's no parent-layout side effect the way a
    # moment's treatment change has (see this dict's own module docstring).
    "image": {"caption", "assetId", "display", "offsetInParentFrames", "durationInFrames"},
    # "kind"/"icon" excluded for the same reason as moment's "treatment":
    # switching word-pop/underline/icon-accent is generate_emphasis.py's
    # job, not a text edit.
    "beat": {"text", "offsetInParentFrames", "durationInFrames"},
}

# Track scenes occupy the timeline sequentially (absolute timelineStartFrame,
# no gaps/overlaps — enforced by qa_check.py's check_timeline_continuity).
# Overlay scenes are positioned relative to a parent via offsetInParentFrames
# and never need their own timelineStartFrame touched.
TRACK_SCENE_TYPES = {"presenter", "title"}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing prompt file: {path}")

    return path.read_text(encoding="utf-8")


def write_json_atomic(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    temp = path.with_suffix(".tmp.json")

    try:
        with temp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        temp.replace(path)

    finally:
        if temp.exists():
            temp.unlink()


def validate_operations(scene_plan, operations):
    """Rejects any operation referencing a scene that doesn't exist or a
    field outside that scene type's editable allowlist — the LLM's output is
    never trusted blindly, same discipline generate_moments.py already
    applies to moment proposals. Returns (valid_ops, rejected) where
    rejected is a list of {operation, reason} for transparency.

    "create" is handled separately from remove/update below — it doesn't
    reference an EXISTING sceneId (there's nothing to look up yet), and its
    own grounding validation (real, contiguous transcript words; no overlay
    collision) is a different concern from EDITABLE_FIELDS's per-type field
    allowlist, so it's delegated to resolve_beat_creation (see below)
    rather than folded into this function's scene-lookup-first shape."""

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}

    valid_ops = []
    rejected = []

    for op in operations:

        if op.get("op") == "create":
            valid_ops.append(op)
            continue

        scene_id = op.get("sceneId")
        scene = scenes_by_id.get(scene_id)

        if not scene:
            rejected.append({"operation": op, "reason": f"no scene with id '{scene_id}'"})
            continue

        if op.get("op") == "remove":
            valid_ops.append(op)
            continue

        if op.get("op") == "trim":

            if scene["type"] != "presenter":
                rejected.append(
                    {"operation": op, "reason": f"trim only applies to presenter scenes, not '{scene['type']}'"}
                )
                continue

            cut_start = op.get("cutStartFrame")
            cut_end = op.get("cutEndFrame")

            if (
                not isinstance(cut_start, int)
                or not isinstance(cut_end, int)
                or not (scene["sourceStartFrame"] <= cut_start < cut_end <= scene["sourceEndFrame"])
            ):
                rejected.append(
                    {
                        "operation": op,
                        "reason": (
                            f"cut range [{cut_start}, {cut_end}) must fall strictly within the "
                            f"scene's own source range [{scene['sourceStartFrame']}, {scene['sourceEndFrame']}]"
                        ),
                    }
                )
                continue

            valid_ops.append(op)
            continue

        if op.get("op") == "update":

            fields = op.get("fields", {})
            allowed = EDITABLE_FIELDS.get(scene["type"], set())

            invalid_fields = set(fields.keys()) - allowed

            if invalid_fields:
                rejected.append(
                    {
                        "operation": op,
                        "reason": (
                            f"fields {sorted(invalid_fields)} are not editable on "
                            f"type '{scene['type']}' (allowed: {sorted(allowed)})"
                        ),
                    }
                )
                continue

            # Field-name validation above doesn't check VALUES — entrance
            # is the one editable field with a fixed enum of legal values
            # (must match BottomCallout.tsx's computeTransform exactly),
            # so an update proposing an invented 4th value (the model
            # hallucinating e.g. "bounce") is caught here rather than
            # silently written to scene-plan.json, where computeTransform
            # would fall through to its "scale" default with no feedback
            # to the user that their request wasn't honored.
            if "entrance" in fields and fields["entrance"] not in VALID_ENTRANCES:
                rejected.append(
                    {
                        "operation": op,
                        "reason": f"entrance {fields['entrance']!r} is not one of {sorted(VALID_ENTRANCES)}",
                    }
                )
                continue

            valid_ops.append(op)
            continue

        rejected.append({"operation": op, "reason": f"unknown op '{op.get('op')}'"})

    return valid_ops, rejected


def resolve_trim(scene, cut_start_frame, cut_end_frame):
    """Excises an interior [cut_start_frame, cut_end_frame) sub-range from
    a presenter scene's own source range by splitting it into up to two
    presenter scenes — NOT by introducing a multi-range source schema.
    Verified against Episode.tsx: presenter rendering is already one
    <OffthreadVideo trimBefore trimAfter> per scene, and the existing
    crossfade-at-scene-boundary logic (crossfadeInFramesForScene) doesn't
    care whether two adjacent presenter scenes share a videoId — so two
    scenes from the SAME video, back to back, render exactly like a clean
    cut with zero renderer changes (see #65). The second scene's
    transition is set to "crossfade" (this repo's existing default, see
    create_scene_plan in analyze_scenes.py) — at CROSSFADE_TRANSITION_FRAMES
    (9 frames, Episode.tsx) this reads as a clean cut, not a visible fade.

    Returns (first_scene, second_scene) — either may be None if the cut is
    flush against that edge of the scene's source range, degenerating to a
    single adjusted scene rather than a spurious zero-length one. The
    caller (apply_operations) is responsible for calling reflow_timeline
    afterward, same as any other duration-changing op."""

    keeps_front = cut_start_frame > scene["sourceStartFrame"]
    keeps_back = cut_end_frame < scene["sourceEndFrame"]

    first_scene = None
    second_scene = None

    if keeps_front:
        first_scene = {
            **scene,
            "sourceEndFrame": cut_start_frame,
            "durationInFrames": cut_start_frame - scene["sourceStartFrame"],
        }

    if keeps_back:
        second_scene = {
            **scene,
            # Only renamed when BOTH halves survive — a cut flush against
            # either edge degenerates to a single adjusted scene that
            # keeps the ORIGINAL id, not a spurious "-b" rename of the
            # only remaining half (which would silently break anything
            # still addressing this scene by its original id, e.g. a
            # not-yet-applied overlay op referencing it in the same batch).
            "id": f"{scene['id']}-b" if keeps_front else scene["id"],
            "sourceStartFrame": cut_end_frame,
            "durationInFrames": scene["sourceEndFrame"] - cut_end_frame,
            "effects": {**scene.get("effects", {}), "transition": "crossfade"} if keeps_front else scene.get("effects", {}),
        }

    return first_scene, second_scene


def _reparent_overlays_for_trim(
    scenes, original_scene_id, original_source_start_frame, first_scene, second_scene, cut_start_frame, cut_end_frame
):
    """For every overlay scene anchored to original_scene_id via
    parentSceneId (moment/caption/image/beat all share this shape — see
    types.ts): an overlay entirely before the cut stays on first_scene, one
    at/after the cut is re-parented onto second_scene with its
    offsetInParentFrames reduced by the removed span (and rebased onto
    second_scene's own sourceStartFrame origin), and one strictly inside
    the cut span is dropped — it anchored to a moment now excised from the
    footage, so there's no valid position for it anymore. Dropped overlays
    are returned separately (not silently discarded) so callers can
    surface them, mirroring apply_operations' own "don't silently clean
    up a dangling parentSceneId" discipline for plain removal.

    original_source_start_frame is the PRE-trim scene's own
    sourceStartFrame — the stable reference point offsetInParentFrames was
    always relative to, regardless of which half (if either) keeps the
    original scene id after the split.

    Returns (kept_overlays, dropped_overlay_ids)."""

    kept = []
    dropped = []

    for scene in scenes:

        if scene.get("parentSceneId") != original_scene_id:
            kept.append(scene)
            continue

        absolute_offset = original_source_start_frame + scene["offsetInParentFrames"]

        if absolute_offset < cut_start_frame and first_scene is not None:
            kept.append({**scene, "parentSceneId": first_scene["id"]})
        elif absolute_offset >= cut_end_frame and second_scene is not None:
            kept.append(
                {
                    **scene,
                    "parentSceneId": second_scene["id"],
                    "offsetInParentFrames": absolute_offset - second_scene["sourceStartFrame"],
                }
            )
        else:
            dropped.append(scene["id"])

    return kept, dropped


def apply_operations(scene_plan, operations):
    """Applies already-validated remove/update/trim operations to the
    scene plan. "create" operations are deliberately NOT applied here — a
    created beat is resolved (resolve_beat_creation) and written to
    emphasis.json + re-merged via merge_beat_scenes, the same two-step
    write PUT /api/episode/beats already performs, not a direct
    scene_plan["scenes"] mutation the way remove/update/trim are. Keeping
    that write path out of this function preserves apply_operations'
    existing scope (pure scene-plan transform, no other file's concerns) —
    see resolve_beat_creation's own docstring for where "create" actually
    gets handled.

    Removing a scene doesn't cascade to overlays anchored to it
    (parentSceneId pointing at a now-missing scene) — Episode.tsx already
    no-ops an overlay whose parent lookup fails, and qa_check.py's
    overlay-bounds check will flag the dangling reference so it's visible
    rather than silently cleaned up.

    Trimming a scene DOES cascade to its overlays (see
    _reparent_overlays_for_trim) — unlike remove, a trim doesn't destroy
    the parent scene's identity outright, so leaving stale offsets in
    place would silently misplace a moment/beat/caption/image rather than
    surface a clearly-dangling reference the way remove's no-op does.
    Callers must run reflow_timeline() afterward — trim changes
    durationInFrames on track scenes, same as any duration-changing edit."""

    remove_ids = {op["sceneId"] for op in operations if op["op"] == "remove"}

    updates_by_id = {
        op["sceneId"]: op["fields"] for op in operations if op["op"] == "update"
    }

    trims_by_id = {
        op["sceneId"]: op for op in operations if op["op"] == "trim"
    }

    # "create" ops pass through this function untouched (see docstring) —
    # explicitly excluded from remove_ids/updates_by_id/trims_by_id above
    # via the op-type filters already in place, nothing further needed here.

    new_scenes = []

    for scene in scene_plan["scenes"]:

        if scene["id"] in remove_ids:
            continue

        trim_op = trims_by_id.get(scene["id"])

        if trim_op:
            first_scene, second_scene = resolve_trim(scene, trim_op["cutStartFrame"], trim_op["cutEndFrame"])

            if first_scene is not None:
                new_scenes.append(first_scene)

            if second_scene is not None:
                new_scenes.append(second_scene)

            continue

        fields = updates_by_id.get(scene["id"])

        if fields:
            scene = {**scene, **fields}

        new_scenes.append(scene)

    # Overlay reparenting runs as a second pass over the ALREADY-trimmed
    # track scenes above, since it needs to know which of first_scene/
    # second_scene (if either) survived each trim.
    for trim_op in trims_by_id.values():

        original_id = trim_op["sceneId"]
        original_scene = next((s for s in scene_plan["scenes"] if s["id"] == original_id), None)

        if original_scene is None:
            continue

        first_scene = next((s for s in new_scenes if s["id"] == original_id), None)
        second_scene = next((s for s in new_scenes if s["id"] == f"{original_id}-b"), None)

        new_scenes, _dropped = _reparent_overlays_for_trim(
            new_scenes, original_id, original_scene["sourceStartFrame"], first_scene, second_scene,
            trim_op["cutStartFrame"], trim_op["cutEndFrame"],
        )

    scene_plan = dict(scene_plan)
    scene_plan["scenes"] = new_scenes

    return scene_plan


def reflow_timeline(scene_plan):
    """Recomputes timelineStartFrame for track scenes (presenter/title) in
    their existing order, sequentially from durationInFrames — needed after
    any edit that can change a track scene's duration (e.g. a presenter
    trim), since qa_check.py's check_timeline_continuity requires track
    scenes to be contiguous with no gaps/overlaps. Overlay scenes
    (moment/caption/image) are positioned relative to their parent via
    offsetInParentFrames and never need touching here — they resolve
    correctly at render time regardless of where their parent ends up."""

    scene_plan = dict(scene_plan)

    track_scenes = [s for s in scene_plan["scenes"] if s["type"] in TRACK_SCENE_TYPES]
    overlay_scenes = [s for s in scene_plan["scenes"] if s["type"] not in TRACK_SCENE_TYPES]

    track_scenes = sorted(track_scenes, key=lambda s: s["timelineStartFrame"])

    timeline_frame = 0
    reflowed_track_scenes = []

    for scene in track_scenes:
        scene = {**scene, "timelineStartFrame": timeline_frame}
        reflowed_track_scenes.append(scene)
        timeline_frame += scene["durationInFrames"]

    scene_plan["scenes"] = reflowed_track_scenes + overlay_scenes

    return scene_plan


# Fields worth surfacing per scene type when describing "the currently
# selected scene" to the LLM — a small, deliberate subset (not the whole
# scene object) that's actually useful for recognizing what "this"/"that"
# refers to: content the creator would recognize (text/caption), not
# internal bookkeeping (frame offsets, ids of other scenes). Mirrors
# EDITABLE_FIELDS's own per-type structure, but this is about
# *description*, not what can be edited.
SELECTED_SCENE_DESCRIPTION_FIELDS = {
    "presenter": ["videoId"],
    "title": ["text"],
    "moment": ["treatment", "text", "caption"],
    "caption": ["text"],
    "image": ["caption", "display"],
    "beat": ["kind", "text"],
}


def describe_selected_scene(scene_plan, selected_scene_id):
    """Renders the currently-selected scene as a short, human-readable
    block for the prompt's "Currently selected" section — or None if
    selected_scene_id is falsy or doesn't match any scene in the current
    plan (e.g. a stale selection left over after a prior edit removed that
    scene). A stale/unresolvable id is not an error: selection is a hint
    for resolving "this"/"that", not a requirement, so the instruction
    should still be attempted with no selection context rather than
    failing outright."""

    if not selected_scene_id:
        return None

    scene = next((s for s in scene_plan["scenes"] if s["id"] == selected_scene_id), None)

    if not scene:
        return None

    lines = [f"id: {scene['id']}", f"type: {scene['type']}"]

    for field in SELECTED_SCENE_DESCRIPTION_FIELDS.get(scene["type"], []):
        if scene.get(field) is not None:
            lines.append(f"{field}: {scene[field]}")

    return "\n".join(lines)


def describe_scene_transcripts(scene_plan, transcript, manifest):
    """Renders, per presenter scene, what is actually said in it — so a
    script-anchored reference ("after I mention CQRS", "the scene where I
    talk about the anemic domain model") can be resolved to the right
    sceneId even though a presenter scene itself carries no text field
    (see #55). Reuses generate_moments.py's group_transcript_by_clip +
    visual_placement.py's filter_segments_in_window — the same
    videoId-then-source-window narrowing resolve_bottom_callout_creation
    already does for grounding a created moment — rather than
    reimplementing transcript-window extraction here. Returns a fallback
    string (not None) when transcript/manifest are unavailable, matching
    candidate_words_text's own degrade-gracefully convention in edit_plan()."""

    if not transcript or not manifest:
        return "(no transcript available — script-anchored references like \"after I mention X\" cannot be resolved for this episode)"

    clips = group_transcript_by_clip(transcript, manifest)
    fps = scene_plan["fps"]

    lines = []

    for scene in scene_plan["scenes"]:

        if scene["type"] != "presenter":
            continue

        segments = clips.get(scene["videoId"], [])
        window = {"sourceStartFrame": scene["sourceStartFrame"], "sourceEndFrame": scene["sourceEndFrame"]}
        matching = filter_segments_in_window(segments, window, fps)

        if not matching:
            continue

        text = " ".join(segment["text"] for segment in matching)
        lines.append(f"{scene['id']}: {text}")

    return "\n".join(lines) if lines else "(no transcript segments matched any presenter scene)"


def resolve_beat_creation(op, scene_plan, candidates_by_word_id, scenes_by_id, style=None):
    """Resolves a single "create"/"beat" operation into a beat proposal
    ready to append to emphasis.json — or None if it fails any of the same
    grounding checks generate_emphasis.py's own automated pipeline stage
    already applies to AI-proposed beats (imported and reused here, not
    reimplemented, so a chat-created beat is held to the identical
    standard: real/contiguous transcript words, a recognized kind/icon, a
    short phrase, no collision with an existing moment/image, and enough
    room in the parent scene). A chat instruction creating a beat is a
    single request, not a batch of proposals, so this only does Pass 1's
    per-candidate checks from propose_emphasis — the minimum-spacing-
    between-beats Pass 2 there is about multiple simultaneous NEW proposals
    competing with each other, which doesn't apply to inserting one beat
    among already-committed ones."""

    if style is None:
        style = load_style()

    kind = op.get("kind")

    if kind not in VALID_KINDS:
        return None

    icon = op.get("icon")

    if kind == "icon-accent":
        if icon not in VALID_ICONS:
            return None
    else:
        icon = None

    phrase = resolve_phrase(op.get("wordIds"), candidates_by_word_id)

    if phrase is None:
        return None

    if len(phrase["text"].split()) > MAX_BEAT_WORDS:
        return None

    scene_id = phrase["sceneId"]
    offset = phrase["offsetInParentFrames"]
    duration = style["emphasis"]["defaultDurationFrames"]

    if overlaps_existing_overlay(scene_id, offset, duration, scene_plan):
        return None

    parent = scenes_by_id.get(scene_id)

    if not parent or offset + duration > parent["durationInFrames"]:
        return None

    return {
        "sceneId": scene_id,
        "kind": kind,
        "text": phrase["text"],
        "icon": icon,
        "offsetInParentFrames": offset,
        "durationInFrames": duration,
        "reason": op.get("reason", ""),
    }


# The moment "kind" a human picks from the Cmd+I insert prompt, mapped to
# the simplest single-content treatment for that kind — side-* rather than
# full-visual, so a freshly inserted moment keeps the presenter visible by
# default (CLAUDE.md: "do not obscure the presenter unnecessarily") instead
# of defaulting to the most visually aggressive option. The user can still
# switch to full-visual afterward via the existing treatment-switch UI.
MANUAL_CREATION_TREATMENTS = {
    "text": "bottom-callout",
    "image": "side-image",
    "code": "side-code",
    "diagram": "side-diagram",
}


def resolve_manual_moment_creation(scene_id, offset_in_parent_frames, kind, scene_plan, style=None):
    """Resolves a human-initiated (Cmd+I), not AI-proposed, moment
    insertion into a minimal valid proposal ready to append to
    moments.json — or None if the scene/kind/placement is invalid. Unlike
    resolve_bottom_callout_creation and friends, there is no grounding
    check here: the human is directly authoring this moment (its actual
    content gets filled in afterward through the existing inline text
    editor or structured MomentEditorPanel/AssetLibraryPanel), not an AI
    inventing text/assets that need to be checked against the transcript.
    Content fields (text/assetId/codeAssetId/diagram) are deliberately left
    at their empty defaults — the moment renders as a visible-but-empty
    placeholder until the user fills it in through those existing editors,
    exactly as if the AI had proposed an empty one."""

    if style is None:
        style = load_style()

    treatment = MANUAL_CREATION_TREATMENTS.get(kind)

    if treatment is None:
        return None

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}
    parent = scenes_by_id.get(scene_id)

    if not parent or parent["type"] != "presenter":
        return None

    offset = max(0, min(offset_in_parent_frames, parent["durationInFrames"]))

    duration = min(
        duration_for_treatment(treatment, style),
        max(0, parent["durationInFrames"] - offset),
    )

    if duration <= 0:
        return None

    if _bottom_callout_overlaps_existing_moment(scene_plan, scene_id, offset, duration):
        return None

    proposal = {
        "sceneId": scene_id,
        "videoId": parent["videoId"],
        "treatment": treatment,
        "presenterSide": None if treatment in ("bottom-callout",) else "right",
        "offsetInParentFrames": offset,
        "maxDurationInParentFrames": duration,
        "reason": "",
    }

    if treatment == "bottom-callout":
        proposal["text"] = ""

    return proposal


def resolve_manual_beat_creation(scene_id, offset_in_parent_frames, scene_plan, style=None):
    """Resolves a human-initiated (Cmd+I), not AI-proposed, beat insertion
    into a minimal valid proposal ready to append to emphasis.json — or
    None if the scene/placement is invalid. Mirrors
    resolve_manual_moment_creation exactly: no transcript grounding here
    (resolve_beat_creation's job, for the chat-editing path, which needs
    real wordIds) since the human is directly authoring this beat — text/
    kind/icon get filled in afterward through the existing BeatEditorPanel.
    Defaults to "word-pop", the simplest kind (no icon to pick), same
    reasoning as moments defaulting to the least visually aggressive
    treatment (bottom-callout) rather than forcing a choice up front; the
    user can switch kind/icon via the editor immediately after insertion."""

    if style is None:
        style = load_style()

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}
    parent = scenes_by_id.get(scene_id)

    if not parent or parent["type"] != "presenter":
        return None

    offset = max(0, min(offset_in_parent_frames, parent["durationInFrames"]))
    duration = min(style["emphasis"]["defaultDurationFrames"], max(0, parent["durationInFrames"] - offset))

    if duration <= 0:
        return None

    if overlaps_existing_overlay(scene_id, offset, duration, scene_plan):
        return None

    return {
        "sceneId": scene_id,
        "kind": "word-pop",
        "text": "",
        "icon": None,
        "offsetInParentFrames": offset,
        "durationInFrames": duration,
        "reason": "",
    }


def _bottom_callout_overlaps_existing_moment(scene_plan, scene_id, offset, duration):
    """Mirrors generate_moments.py's dedupe_overlapping_windows — a moment's
    on-screen window is its own span padded by TRANSITION_FRAMES on both
    sides for the slide/fade animation, and two moments on the same parent
    scene must not have overlapping padded windows. dedupe_overlapping_windows
    itself is shaped for a batch of NEW proposals checked against each
    other; this checks a single new window against scene_plan's
    ALREADY-MERGED moment scenes instead, since that's what a chat-created
    moment needs to avoid colliding with."""

    start = offset - TRANSITION_FRAMES
    end = offset + duration + TRANSITION_FRAMES

    for scene in scene_plan["scenes"]:

        if scene["type"] != "moment" or scene.get("parentSceneId") != scene_id:
            continue

        other_start = scene["offsetInParentFrames"] - TRANSITION_FRAMES
        other_end = scene["offsetInParentFrames"] + scene["durationInFrames"] + TRANSITION_FRAMES

        if start < other_end and end > other_start:
            return True

    return False


# A chat-created inset image's fixed duration — images have no
# style["images"] section of their own (only moments do, in
# style.py's DEFAULTS), and this is the only place that would ever need
# one, so a plain constant is simpler than adding a whole new style
# subsection for a single number. Matches style.py's own
# moments.durationFrames.sideImage (150 frames) — a comparable "glance at
# an image" read time, just presented as a corner inset instead of a
# side panel.
INSET_IMAGE_DURATION_FRAMES = 150


def _image_overlaps_existing_overlay(scene_plan, scene_id, offset, duration):
    """Mirrors _bottom_callout_overlaps_existing_moment's padded-window
    collision check, but for a chat-created inset image against BOTH
    existing moment and image scenes on the same parent — an inset image
    popping in at the same time as a side-* moment's presenter shift (or
    another image) would read as visual clutter, not a deliberate
    composition, the same discipline every other overlay-creation path in
    this file already applies."""

    start = offset - TRANSITION_FRAMES
    end = offset + duration + TRANSITION_FRAMES

    for scene in scene_plan["scenes"]:

        if scene["type"] not in ("moment", "image") or scene.get("parentSceneId") != scene_id:
            continue

        other_start = scene["offsetInParentFrames"] - TRANSITION_FRAMES
        other_end = other_start + scene["durationInFrames"] + 2 * TRANSITION_FRAMES

        if start < other_end and end > other_start:
            return True

    return False


def resolve_image_creation(op, scene_plan, assets, transcript, manifest):
    """Resolves a single "create"/"image" operation into an image scene
    ready to append to scene-plan.json directly — image scenes have no
    separate source-of-truth file the way moments/beats do (see #60:
    "image scenes are hand-authored / edit-plan only... scene-plan.json
    already IS their only representation"), so unlike
    resolve_beat_creation/resolve_bottom_callout_creation, the caller
    doesn't merge this through a generate_*.py merge function — it's
    inserted directly via overlay_placement.insert_overlay_scene, same as
    those functions do internally.

    Grounding here means picking a REAL assetId from the assets index
    (assets is index_assets.py's output — see format_assets_for_prompt in
    generate_moments.py, the prompt-formatting this reuses) rather than
    inventing one — the same "never fabricate, only reference what
    actually exists" discipline resolve_beat_creation applies to word ids
    and resolve_bottom_callout_creation applies to spoken text. There is
    deliberately no text-grounding step: an inset image has no spoken-text
    requirement the way a bottom-callout does, since its content is the
    image itself, not a paraphrase of narration."""

    scene_id = op.get("sceneId")
    asset_id = op.get("assetId")

    if not scene_id or not asset_id:
        return None

    asset = next((a for a in (assets or []) if a["id"] == asset_id), None)

    if asset is None:
        return None

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}
    parent = scenes_by_id.get(scene_id)

    if not parent or parent["type"] != "presenter":
        return None

    # Placement: right after wherever the instruction's own context
    # anchors it, resolved the same way resolve_bottom_callout_creation
    # anchors a callout — the segment whose text best matches whatever the
    # instruction referenced, defaulting to the start of the scene when no
    # more specific anchor is available (a plain "show a screenshot of X"
    # with no spoken-phrase reference to match against).
    offset = 0

    anchor_text = op.get("anchorText")

    if anchor_text and transcript and manifest:
        clips = group_transcript_by_clip(transcript, manifest)
        segments = clips.get(parent["videoId"], [])
        window = {"sourceStartFrame": parent["sourceStartFrame"], "sourceEndFrame": parent["sourceEndFrame"]}
        matching_segments = filter_segments_in_window(segments, window, scene_plan["fps"])

        best_segment = next(
            (segment for segment in matching_segments if is_grounded(anchor_text, segment["text"])),
            None,
        )

        if best_segment:
            offset = max(0, round(best_segment["start"] * scene_plan["fps"] - parent["sourceStartFrame"]))

    duration = min(INSET_IMAGE_DURATION_FRAMES, max(0, parent["durationInFrames"] - offset))

    if duration <= 0:
        return None

    if _image_overlaps_existing_overlay(scene_plan, scene_id, offset, duration):
        return None

    return {
        "type": "image",
        "assetId": asset_id,
        "caption": asset.get("caption"),
        "display": "inset",
        "parentSceneId": scene_id,
        "offsetInParentFrames": offset,
        "durationInFrames": duration,
    }


def resolve_bottom_callout_creation(op, scene_plan, transcript, manifest, style=None):
    """Resolves a single "create"/"moment" (bottom-callout only, see #53)
    operation into a moment proposal ready to append to moments.json — or
    None if it fails any grounding/placement check. Reuses
    generate_moments.py's own is_grounded/duration_for_treatment
    (identical discipline an AI-pipeline-proposed bottom-callout is held
    to) rather than reimplementing text-fabrication checking or duration
    math here."""

    if style is None:
        style = load_style()

    scene_id = op.get("sceneId")
    text = op.get("text")

    if not scene_id or not text:
        return None

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}
    parent = scenes_by_id.get(scene_id)

    if not parent or parent["type"] != "presenter":
        return None

    if not transcript or not manifest:
        return None

    clips = group_transcript_by_clip(transcript, manifest)
    segments = clips.get(parent["videoId"], [])

    window = {"sourceStartFrame": parent["sourceStartFrame"], "sourceEndFrame": parent["sourceEndFrame"]}
    matching_segments = filter_segments_in_window(segments, window, scene_plan["fps"])

    if not matching_segments:
        return None

    full_window_text = " ".join(segment["text"] for segment in matching_segments)

    if not is_grounded(text, full_window_text):
        return None

    # Placement: the segment whose own text best matches the grounded
    # phrase, so the callout appears near where it's actually said rather
    # than always defaulting to the scene's start — falls back to the
    # first segment if no individual one matches (e.g. the phrase spans a
    # segment boundary), same "don't guess, use the closest real anchor"
    # reasoning as resolve_phrase's own word-position math for beats.
    best_segment = next(
        (segment for segment in matching_segments if is_grounded(text, segment["text"])),
        matching_segments[0],
    )

    offset = max(0, round(best_segment["start"] * scene_plan["fps"] - parent["sourceStartFrame"]))

    duration = min(
        duration_for_treatment("bottom-callout", style),
        max(0, parent["durationInFrames"] - offset),
    )

    if duration <= 0:
        return None

    if _bottom_callout_overlaps_existing_moment(scene_plan, scene_id, offset, duration):
        return None

    proposal = {
        "sceneId": scene_id,
        "videoId": parent["videoId"],
        "treatment": "bottom-callout",
        "text": text,
        "presenterSide": None,
        "offsetInParentFrames": offset,
        "maxDurationInParentFrames": duration,
        "reason": op.get("reason", ""),
    }

    # entrance is optional on a create op (an instruction that only asks
    # to show a callout, with no animation request, has nothing to set
    # here — the renderer's own "scale" default applies) — validated the
    # same way validate_operations checks an update's entrance value,
    # since a "create" op's fields never pass through that function (see
    # its own docstring). An invalid/hallucinated value is silently
    # dropped rather than rejecting the whole creation over one bad field
    # — the callout itself is still real and grounded, just without a
    # non-default entrance.
    entrance = op.get("entrance")

    if entrance in VALID_ENTRANCES:
        proposal["entrance"] = entrance

    return proposal


def resolve_full_screen_diagram_creation(op, scene_plan, transcript, manifest, style=None):
    """Resolves a single "create"/"diagram" operation into a full-visual
    moment proposal (treatment "full-visual", fullVisualKind "diagram") —
    the spec's own worked example (docs/specs/ai-assisted-editing-and-
    conversational-control.md, section 5: "Create a Full Screen diagram
    explaining how the producer communicates with Kafka"). Unlike
    resolve_image_creation (which references a real, pre-existing asset),
    a diagram has no asset to ground against — its nodes/edges are
    AI-authored structured data the model invents from the instruction,
    which is a fundamentally different (harder) fabrication risk: nothing
    stops the model from inventing an architecture that was never
    described. Reuses generate_moments.py's own is_diagram_grounded — the
    SAME check an AI-pipeline-proposed side-diagram/full-visual diagram is
    held to (loose per-node-label stem matching against the source
    window's transcript text, plus MAX_DIAGRAM_NODES/MAX_DIAGRAM_EDGES
    caps) — rather than inventing a second, looser standard for the
    chat-creation path specifically."""

    if style is None:
        style = load_style()

    scene_id = op.get("sceneId")
    diagram = op.get("diagram")

    if not scene_id or not isinstance(diagram, dict):
        return None

    if diagram.get("layout") not in ("horizontal", "vertical"):
        return None

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}
    parent = scenes_by_id.get(scene_id)

    if not parent or parent["type"] != "presenter":
        return None

    if not transcript or not manifest:
        return None

    clips = group_transcript_by_clip(transcript, manifest)
    segments = clips.get(parent["videoId"], [])

    window = {"sourceStartFrame": parent["sourceStartFrame"], "sourceEndFrame": parent["sourceEndFrame"]}
    matching_segments = filter_segments_in_window(segments, window, scene_plan["fps"])

    if not matching_segments:
        return None

    full_window_text = " ".join(segment["text"] for segment in matching_segments)

    if not is_diagram_grounded(diagram, full_window_text):
        return None

    # A full-visual moment (unlike a bottom-callout) isn't anchored to
    # where a specific phrase is spoken — it takes over the whole frame
    # for its own window, same as an AI-pipeline-proposed full-visual
    # moment starts at the candidate window's own offset rather than a
    # matched segment's position. Placed at the start of the scene, same
    # "no more specific anchor available" default resolve_image_creation
    # uses for an image with no anchorText.
    offset = 0

    duration = min(
        duration_for_treatment("full-visual", style),
        max(0, parent["durationInFrames"] - offset),
    )

    if duration <= 0:
        return None

    if _bottom_callout_overlaps_existing_moment(scene_plan, scene_id, offset, duration):
        return None

    return {
        "sceneId": scene_id,
        "videoId": parent["videoId"],
        "treatment": "full-visual",
        "fullVisualKind": "diagram",
        "diagram": diagram,
        "presenterSide": None,
        "offsetInParentFrames": offset,
        "maxDurationInParentFrames": duration,
        "reason": op.get("reason", ""),
    }


def _full_screen_creation_preamble(op, scene_plan, style):
    """Shared setup for resolve_full_screen_image_creation/
    resolve_full_screen_code_creation/resolve_full_screen_text_creation
    (see #64) — the same "resolve sceneId to a real presenter scene, then
    compute a start-of-scene offset/duration" preamble
    resolve_full_screen_diagram_creation already establishes, factored out
    now that four full-visual creation kinds exist side by side rather
    than duplicating it a third/fourth time. Returns (parent, offset,
    duration) or None if sceneId is missing/not a real presenter scene, or
    there's no room left in the parent scene — same rejection behavior
    resolve_full_screen_diagram_creation already has, just shared."""

    scene_id = op.get("sceneId")

    if not scene_id:
        return None

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}
    parent = scenes_by_id.get(scene_id)

    if not parent or parent["type"] != "presenter":
        return None

    # Same "no more specific anchor available" default every other
    # full-visual creation path uses — a full-visual moment takes over the
    # whole frame for its own window, it isn't anchored to a specific
    # spoken phrase's position the way a bottom-callout is.
    offset = 0

    duration = min(
        duration_for_treatment("full-visual", style),
        max(0, parent["durationInFrames"] - offset),
    )

    if duration <= 0:
        return None

    if _bottom_callout_overlaps_existing_moment(scene_plan, scene_id, offset, duration):
        return None

    return parent, offset, duration


def resolve_full_screen_image_creation(op, scene_plan, assets, style=None):
    """Resolves a single "create"/"full-screen" operation with
    fullVisualKind "image" into a full-visual moment proposal — the Full
    Screen counterpart to resolve_image_creation's inset image (#64).
    Grounding here means picking a REAL assetId from the assets index
    (same discipline resolve_image_creation already applies to inset
    images) — there is deliberately no separate text-grounding step, the
    image itself is the content, not a paraphrase of narration."""

    if style is None:
        style = load_style()

    asset_id = op.get("assetId")

    if not asset_id:
        return None

    asset = next((a for a in (assets or []) if a["id"] == asset_id), None)

    if asset is None:
        return None

    preamble = _full_screen_creation_preamble(op, scene_plan, style)

    if preamble is None:
        return None

    parent, offset, duration = preamble

    return {
        "sceneId": op["sceneId"],
        "videoId": parent["videoId"],
        "treatment": "full-visual",
        "fullVisualKind": "image",
        "assetId": asset_id,
        "caption": asset.get("caption"),
        "presenterSide": None,
        "offsetInParentFrames": offset,
        "maxDurationInParentFrames": duration,
        "reason": op.get("reason", ""),
    }


def resolve_full_screen_code_creation(op, scene_plan, code_assets, style=None):
    """Resolves a single "create"/"full-screen" operation with
    fullVisualKind "code" into a full-visual moment proposal (#64).
    Grounding here means picking a REAL codeAssetId from the indexed code
    assets — same discipline generate_moments.py's side-code/
    content-dominant-code handling already applies, never inventing a
    codeAssetId."""

    if style is None:
        style = load_style()

    code_asset_id = op.get("codeAssetId")

    if not code_asset_id:
        return None

    code_asset = next((a for a in (code_assets or []) if a["id"] == code_asset_id), None)

    if code_asset is None:
        return None

    preamble = _full_screen_creation_preamble(op, scene_plan, style)

    if preamble is None:
        return None

    parent, offset, duration = preamble

    return {
        "sceneId": op["sceneId"],
        "videoId": parent["videoId"],
        "treatment": "full-visual",
        "fullVisualKind": "code",
        "codeAssetId": code_asset_id,
        "caption": code_asset.get("description"),
        "presenterSide": None,
        "offsetInParentFrames": offset,
        "maxDurationInParentFrames": duration,
        "reason": op.get("reason", ""),
    }


def resolve_full_screen_text_creation(op, scene_plan, transcript, manifest, style=None):
    """Resolves a single "create"/"full-screen" operation with
    fullVisualKind "text" into a full-visual moment proposal (#64).
    Grounding here means the same discipline resolve_bottom_callout_creation
    already applies to its own "text" field — a short phrase taken
    directly from what is actually said in the target scene, quoted
    closely, never paraphrased or invented — rather than a new, looser
    standard for full-screen text specifically. Unlike image/code, there's
    no asset to select: the text itself is grounded against the scene's
    own transcript, the same way a bottom-callout is."""

    if style is None:
        style = load_style()

    scene_id = op.get("sceneId")
    text = op.get("text")

    if not scene_id or not text:
        return None

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}
    parent = scenes_by_id.get(scene_id)

    if not parent or parent["type"] != "presenter":
        return None

    if not transcript or not manifest:
        return None

    clips = group_transcript_by_clip(transcript, manifest)
    segments = clips.get(parent["videoId"], [])

    window = {"sourceStartFrame": parent["sourceStartFrame"], "sourceEndFrame": parent["sourceEndFrame"]}
    matching_segments = filter_segments_in_window(segments, window, scene_plan["fps"])

    if not matching_segments:
        return None

    full_window_text = " ".join(segment["text"] for segment in matching_segments)

    if not is_grounded(text, full_window_text):
        return None

    preamble = _full_screen_creation_preamble(op, scene_plan, style)

    if preamble is None:
        return None

    parent, offset, duration = preamble

    return {
        "sceneId": scene_id,
        "videoId": parent["videoId"],
        "treatment": "full-visual",
        "fullVisualKind": "text",
        "text": text,
        "presenterSide": None,
        "offsetInParentFrames": offset,
        "maxDurationInParentFrames": duration,
        "reason": op.get("reason", ""),
    }


def edit_plan(
    scene_plan, instruction, llm: LLMClient, prompt_template: str,
    selected_scene_id=None, transcript=None, manifest=None, assets=None, code_assets=None,
):
    """transcript/manifest are optional — only pass them when both are
    available (an episode with no word-level transcript data can't ground
    a beat/moment/diagram creation, same as generate_emphasis.py's own
    pipeline stage). When present, they enable "create" operations:
    "beat" (#52, resolve_beat_creation, reuses generate_emphasis.py's own
    word-matching), "moment"/bottom-callout (#53,
    resolve_bottom_callout_creation, reuses generate_moments.py's own
    text-grounding), and "full-screen" with fullVisualKind "diagram"/"text"
    (resolve_full_screen_diagram_creation/resolve_full_screen_text_creation
    — a Full Screen moment, reuses generate_moments.py's own
    is_diagram_grounded/is_grounded; see docs/specs/ai-assisted-editing-and-
    conversational-control.md section 5's own worked example). assets is
    likewise optional (an episode with no indexed graphics can't ground an
    inset image creation) and enables "create"/"image" (resolve_image_creation
    — the AI-creation path for ImageScene, previously unreachable by any
    real workflow; see docs/specs/content-types-and-presentation-editing.md)
    as well as "create"/"full-screen" with fullVisualKind "image"
    (resolve_full_screen_image_creation, #64). code_assets is likewise
    optional (an episode with no indexed code/ folder can't ground a Full
    Screen code creation) and enables "create"/"full-screen" with
    fullVisualKind "code" (resolve_full_screen_code_creation, #64). None of
    these are reimplemented here.

    Returns (updated_plan, valid_ops, rejected, created_beats,
    created_moments, created_images) — the three created_* lists are kept
    separate from updated_plan/valid_ops for different reasons:
    created_beats/created_moments are each written to their own source
    file (emphasis.json / moments.json) + re-merged, a different write
    path than remove/update's direct scene_plan mutation, while
    created_images has no separate source file at all (image scenes are
    "hand-authored / edit-plan only" — see #60) and is instead appended
    straight into scene_plan's own scenes list by the caller, mirroring
    how resolve_image_creation's own docstring describes
    insert_overlay_scene being used elsewhere. See each resolve_*
    function's own docstring for the full reasoning."""

    selected_scene_text = describe_selected_scene(scene_plan, selected_scene_id) or "(nothing selected)"

    candidates_by_word_id, scenes_by_id = (
        build_candidate_words(scene_plan, transcript, manifest)
        if transcript and manifest
        else ({}, {})
    )

    candidate_words_text = (
        format_words_for_prompt(candidates_by_word_id)
        if candidates_by_word_id
        else "(no word-level transcript data available — beat creation is not possible for this episode)"
    )

    scene_transcripts_text = describe_scene_transcripts(scene_plan, transcript, manifest)

    available_assets_text = format_assets_for_prompt(assets) if assets else "(none available)"

    available_code_assets_text = (
        format_code_assets_for_prompt(code_assets) if code_assets else "(none available)"
    )

    # Substitute the fixed, non-user-authored blocks first, then the
    # free-text instruction last — it's the one value that could plausibly
    # contain a literal "{scene_plan}"/"{editable_fields}" substring (e.g.
    # quoting scene-plan syntax back at the model), which would otherwise
    # get double-substituted if instruction were replaced earlier.
    prompt = prompt_template.replace(
        "{scene_plan}", json.dumps(scene_plan, indent=2)
    ).replace(
        "{editable_fields}", json.dumps(
            {k: sorted(v) for k, v in EDITABLE_FIELDS.items()}, indent=2
        )
    ).replace(
        "{selected_scene}", selected_scene_text
    ).replace(
        "{candidate_words}", candidate_words_text
    ).replace(
        "{scene_transcripts}", scene_transcripts_text
    ).replace(
        "{available_assets}", available_assets_text
    ).replace(
        "{available_code_assets}", available_code_assets_text
    ).replace(
        "{instruction}", instruction
    )

    response = llm.complete_json(prompt, thinking=True)

    operations = response.get("operations", [])
    # Only meaningful when operations ends up empty — the prompt asks for
    # this specifically so a genuine "nothing could be done" (e.g. custom
    # beat/callout text that isn't an actual transcript phrase) reaches the
    # creator as a real reason instead of a bare empty result (see #67).
    explanation = response.get("explanation")

    valid_ops, rejected = validate_operations(scene_plan, operations)

    remove_update_ops = [op for op in valid_ops if op["op"] != "create"]
    create_beat_ops = [op for op in valid_ops if op["op"] == "create" and op.get("type") == "beat"]
    create_moment_ops = [op for op in valid_ops if op["op"] == "create" and op.get("type") == "moment"]
    create_image_ops = [op for op in valid_ops if op["op"] == "create" and op.get("type") == "image"]
    create_diagram_ops = [op for op in valid_ops if op["op"] == "create" and op.get("type") == "diagram"]
    # "full-screen" (#64) covers the three fullVisualKind values diagram
    # creation didn't (image/code/text) — kept as a separate "type" from
    # "diagram" above rather than folding diagram into it, so the existing
    # diagram-creation prompt/tests/callers keep working unchanged.
    create_full_screen_ops = [op for op in valid_ops if op["op"] == "create" and op.get("type") == "full-screen"]

    created_beats = []

    for op in create_beat_ops:
        beat = resolve_beat_creation(op, scene_plan, candidates_by_word_id, scenes_by_id)

        if beat is None:
            rejected.append({"operation": op, "reason": "could not ground this beat against real transcript words"})
            continue

        created_beats.append(beat)

    created_moments = []

    for op in create_moment_ops:
        moment = resolve_bottom_callout_creation(op, scene_plan, transcript, manifest)

        if moment is None:
            rejected.append({"operation": op, "reason": "could not ground this moment against the target scene's transcript"})
            continue

        created_moments.append(moment)

    # A "diagram" create is also a moment proposal (treatment full-visual,
    # fullVisualKind diagram) — same created_moments list, same
    # moments.json write path (see do_write below) as a bottom-callout,
    # just resolved by a different function since the grounding discipline
    # is different (is_diagram_grounded, not is_grounded).
    for op in create_diagram_ops:
        diagram_moment = resolve_full_screen_diagram_creation(op, scene_plan, transcript, manifest)

        if diagram_moment is None:
            rejected.append({"operation": op, "reason": "could not ground this diagram against the target scene's transcript, or it exceeds node/edge limits"})
            continue

        created_moments.append(diagram_moment)

    # A "full-screen" create is also a moment proposal (treatment
    # full-visual) — same created_moments list, same moments.json write
    # path as a bottom-callout/diagram, just dispatched by fullVisualKind
    # to whichever of the three resolvers (#64) matches its grounding
    # discipline (asset-grounded for image/code, transcript-grounded for
    # text).
    for op in create_full_screen_ops:
        kind = op.get("fullVisualKind")

        if kind == "image":
            full_screen_moment = resolve_full_screen_image_creation(op, scene_plan, assets)
            reason = "could not ground this image against a real asset id"
        elif kind == "code":
            full_screen_moment = resolve_full_screen_code_creation(op, scene_plan, code_assets)
            reason = "could not ground this code snippet against a real code asset id"
        elif kind == "text":
            full_screen_moment = resolve_full_screen_text_creation(op, scene_plan, transcript, manifest)
            reason = "could not ground this text against the target scene's transcript"
        else:
            full_screen_moment = None
            reason = f"fullVisualKind must be 'image', 'code', or 'text' for a full-screen create, got {kind!r}"

        if full_screen_moment is None:
            rejected.append({"operation": op, "reason": reason})
            continue

        created_moments.append(full_screen_moment)

    created_images = []

    for op in create_image_ops:
        image = resolve_image_creation(op, scene_plan, assets, transcript, manifest)

        if image is None:
            rejected.append({"operation": op, "reason": "could not ground this image against a real asset id, or it collides with an existing overlay"})
            continue

        created_images.append(image)

    updated_plan = apply_operations(scene_plan, remove_update_ops)
    updated_plan = reflow_timeline(updated_plan)

    return updated_plan, remove_update_ops, rejected, created_beats, created_moments, created_images, explanation


def main():

    parser = argparse.ArgumentParser(
        description="Apply a natural-language edit instruction to scene-plan.json"
    )

    parser.add_argument("episode_folder")
    parser.add_argument("instruction")

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    scene_plan_file = episode / "processing" / "scene-plan.json"

    if not scene_plan_file.exists():
        print(f"ERROR: Missing scene plan: {scene_plan_file}")
        sys.exit(1)

    scene_plan = load_json(scene_plan_file)

    llm = LLMClient(PROJECT_ROOT / "config.json")
    prompt_template = load_prompt(PROMPT_FILE)

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, args.instruction, llm, prompt_template
    )

    write_json_atomic(scene_plan_file, updated_plan)

    print(f"Applied {len(valid_ops)} operation(s):")
    for op in valid_ops:
        print(f"  {op['op']} {op['sceneId']}: {op.get('reason', '')}")

    # created_beats/created_moments/created_images are always empty from
    # this CLI entry point — no transcript/manifest/assets is loaded/passed
    # here, so creation can't be grounded (see edit_plan's own docstring).
    # ui/server.py's edit_scene_plan is the only caller that currently
    # passes all three.
    if created_beats:
        print(f"\nCreated {len(created_beats)} beat(s):")
        for beat in created_beats:
            print(f"  {beat['kind']} on {beat['sceneId']}: \"{beat['text']}\"")

    if created_moments:
        print(f"\nCreated {len(created_moments)} moment(s):")
        for moment in created_moments:
            # A diagram-created moment (treatment "full-visual", see
            # resolve_full_screen_diagram_creation) has no "text" field —
            # summarize its node labels instead.
            summary = (
                moment["text"]
                if "text" in moment
                else ", ".join(n["label"] for n in moment["diagram"]["nodes"])
            )
            print(f"  {moment['treatment']} on {moment['sceneId']}: \"{summary}\"")

    if created_images:
        print(f"\nCreated {len(created_images)} image(s):")
        for image in created_images:
            print(f"  inset image on {image['parentSceneId']}: {image['assetId']}")

    if rejected:
        print(f"\nRejected {len(rejected)} operation(s):")
        for r in rejected:
            print(f"  {r['operation']}: {r['reason']}")

    if explanation:
        print(f"\n{explanation}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
