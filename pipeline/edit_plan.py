#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from llm.client import LLMClient  # noqa: E402


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
    rejected is a list of {operation, reason} for transparency."""

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}

    valid_ops = []
    rejected = []

    for op in operations:

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
    """Applies already-validated operations to the scene plan. Removing a
    scene doesn't cascade to overlays anchored to it (parentSceneId pointing
    at a now-missing scene) — Episode.tsx already no-ops an overlay whose
    parent lookup fails, and qa_check.py's overlay-bounds check will flag the
    dangling reference so it's visible rather than silently cleaned up."""

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}

    remove_ids = {op["sceneId"] for op in operations if op["op"] == "remove"}

    updates_by_id = {
        op["sceneId"]: op["fields"] for op in operations if op["op"] == "update"
    }

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


def edit_plan(scene_plan, instruction, llm: LLMClient, prompt_template: str):

    # Substitute the two fixed, non-user-authored blocks first, then the
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
        "{instruction}", instruction
    )

    response = llm.complete_json(prompt, thinking=True)

    operations = response.get("operations", [])

    valid_ops, rejected = validate_operations(scene_plan, operations)

    updated_plan = apply_operations(scene_plan, valid_ops)
    updated_plan = reflow_timeline(updated_plan)

    return updated_plan, valid_ops, rejected


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

    updated_plan, valid_ops, rejected = edit_plan(
        scene_plan, args.instruction, llm, prompt_template
    )

    write_json_atomic(scene_plan_file, updated_plan)

    print(f"Applied {len(valid_ops)} operation(s):")
    for op in valid_ops:
        print(f"  {op['op']} {op['sceneId']}: {op.get('reason', '')}")

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
