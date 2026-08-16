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
from style import load_style  # noqa: E402


PROMPT_FILE = PIPELINE_DIR / "prompts" / "edit_plan.txt"

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
    "moment": {"text", "assetId", "caption", "offsetInParentFrames", "durationInFrames"},
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

            valid_ops.append(op)
            continue

        rejected.append({"operation": op, "reason": f"unknown op '{op.get('op')}'"})

    return valid_ops, rejected


def apply_operations(scene_plan, operations):
    """Applies already-validated remove/update operations to the scene
    plan. "create" operations are deliberately NOT applied here — a
    created beat is resolved (resolve_beat_creation) and written to
    emphasis.json + re-merged via merge_beat_scenes, the same two-step
    write PUT /api/episode/beats already performs, not a direct
    scene_plan["scenes"] mutation the way remove/update are. Keeping that
    write path out of this function preserves apply_operations' existing
    scope (pure scene-plan transform, no other file's concerns) — see
    resolve_beat_creation's own docstring for where "create" actually gets
    handled.

    Removing a scene doesn't cascade to overlays anchored to it
    (parentSceneId pointing at a now-missing scene) — Episode.tsx already
    no-ops an overlay whose parent lookup fails, and qa_check.py's
    overlay-bounds check will flag the dangling reference so it's visible
    rather than silently cleaned up."""

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}

    remove_ids = {op["sceneId"] for op in operations if op["op"] == "remove"}

    updates_by_id = {
        op["sceneId"]: op["fields"] for op in operations if op["op"] == "update"
    }

    # "create" ops pass through this function untouched (see docstring) —
    # explicitly excluded from remove_ids/updates_by_id above via the
    # op-type filters already in place, nothing further needed here.

    new_scenes = []

    for scene in scene_plan["scenes"]:

        if scene["id"] in remove_ids:
            continue

        fields = updates_by_id.get(scene["id"])

        if fields:
            scene = {**scene, **fields}

        new_scenes.append(scene)

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


def edit_plan(
    scene_plan, instruction, llm: LLMClient, prompt_template: str,
    selected_scene_id=None, transcript=None, manifest=None,
):
    """transcript/manifest are optional — only pass them when both are
    available (an episode with no word-level transcript data can't ground
    a beat creation, same as generate_emphasis.py's own pipeline stage).
    When present, they enable the "create"/"beat" operation (#52): the LLM
    can propose a new beat grounded against a real spoken word's exact
    timestamp, resolved via resolve_beat_creation (imports/reuses
    generate_emphasis.py's own word-matching, not a reimplementation).
    Returns (updated_plan, valid_ops, rejected, created_beats) —
    created_beats is a separate list (not part of updated_plan/valid_ops)
    since a beat is written to emphasis.json + re-merged via
    merge_beat_scenes, a different write path than remove/update's direct
    scene_plan mutation; see resolve_beat_creation's own docstring."""

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
        "{instruction}", instruction
    )

    response = llm.complete_json(prompt, thinking=True)

    operations = response.get("operations", [])

    valid_ops, rejected = validate_operations(scene_plan, operations)

    remove_update_ops = [op for op in valid_ops if op["op"] != "create"]
    create_ops = [op for op in valid_ops if op["op"] == "create" and op.get("type") == "beat"]

    created_beats = []

    for op in create_ops:
        beat = resolve_beat_creation(op, scene_plan, candidates_by_word_id, scenes_by_id)

        if beat is None:
            rejected.append({"operation": op, "reason": "could not ground this beat against real transcript words"})
            continue

        created_beats.append(beat)

    updated_plan = apply_operations(scene_plan, remove_update_ops)
    updated_plan = reflow_timeline(updated_plan)

    return updated_plan, remove_update_ops, rejected, created_beats


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

    updated_plan, valid_ops, rejected, created_beats = edit_plan(
        scene_plan, args.instruction, llm, prompt_template
    )

    write_json_atomic(scene_plan_file, updated_plan)

    print(f"Applied {len(valid_ops)} operation(s):")
    for op in valid_ops:
        print(f"  {op['op']} {op['sceneId']}: {op.get('reason', '')}")

    # created_beats is always empty from this CLI entry point — no
    # transcript/manifest is loaded/passed here, so beat creation can't be
    # grounded (see edit_plan's own docstring). ui/server.py's
    # edit_scene_plan is the only caller that currently passes both.
    if created_beats:
        print(f"\nCreated {len(created_beats)} beat(s):")
        for beat in created_beats:
            print(f"  {beat['kind']} on {beat['sceneId']}: \"{beat['text']}\"")

    if rejected:
        print(f"\nRejected {len(rejected)} operation(s):")
        for r in rejected:
            print(f"  {r['operation']}: {r['reason']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
