#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from generate_title_scenes import indexed_segments, resolvable_segment_positions  # noqa: E402


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def merge_background_scenes(scene_plan, entries, transcript, manifest):
    """Resolves each background_scenes.json entry's segmentId to a real
    timeline frame and produces one BackgroundScene per entry, each
    auto-closed by whichever entry starts next (or the end of the episode
    for the last one) — same "sorted list of start points, no independent
    end" model as chapters/titles, not free-standing start+end spans like
    moments/beats. Deliberately does NOT split presenter scenes the way
    merge_title_scenes does: a background is a pure overlay behind the
    presenter, not a cut in the footage, so there's no source-frame
    concept to resolve, only a timeline position.

    Unlike titles, there is no AI proposal step for backgrounds (the user
    is the only author — see the feature's own design decision), so this
    has no preserve_overridden_fields/compute_overridden_fields
    counterpart: background_scenes.json entries ARE the human's edits
    directly, nothing to diff against a fresh AI proposal.

    A background entry whose segmentId doesn't resolve (deleted transcript
    segment, footage no longer in this scene plan) is dropped rather than
    guessed — same "skip, don't guess" rule resolvable_segment_positions
    itself already follows."""

    # Only presenter/title scenes carry an absolute timelineStartFrame
    # directly — moments/images/captions/beats are positioned relative to
    # a parent scene (parentSceneId/offsetInParentFrames) and would raise
    # a KeyError here, not just be irrelevant to the episode's total length.
    total_frames = max(
        (
            s["timelineStartFrame"] + s["durationInFrames"]
            for s in scene_plan["scenes"]
            if s["type"] in ("presenter", "title")
        ),
        default=0,
    )

    positions_by_segment = {
        p["segmentId"]: p["timelineFrame"]
        for p in resolvable_segment_positions(scene_plan, transcript, manifest)
    }

    resolved = []

    for entry in entries:

        segment_id = entry.get("segmentId")
        timeline_frame = positions_by_segment.get(segment_id)

        if timeline_frame is None:
            continue

        resolved.append({
            "segmentId": segment_id,
            "backgroundId": entry.get("backgroundId"),
            "timelineStartFrame": timeline_frame,
            # Only meaningful for an image background — see
            # BackgroundImageMotion's own doc comment in types.ts.
            # Defaults to None (no motion), same as every background
            # scene before this field existed.
            "imageMotion": entry.get("imageMotion"),
            # Only meaningful when imageMotion is set — see
            # BackgroundImageMotionSpeed's own doc comment in types.ts.
            # Defaults to None (renderer treats that as "normal").
            "imageMotionSpeed": entry.get("imageMotionSpeed"),
        })

    resolved.sort(key=lambda r: r["timelineStartFrame"])

    background_scenes = []

    for i, entry in enumerate(resolved):

        next_start = resolved[i + 1]["timelineStartFrame"] if i + 1 < len(resolved) else total_frames
        duration = max(1, next_start - entry["timelineStartFrame"])

        background_scene = {
            "type": "background",
            "id": f"scene-background-{i}",
            "backgroundId": entry["backgroundId"],
            "timelineStartFrame": entry["timelineStartFrame"],
            "durationInFrames": duration,
        }

        if entry.get("imageMotion"):
            background_scene["imageMotion"] = entry["imageMotion"]

        if entry.get("imageMotionSpeed"):
            background_scene["imageMotionSpeed"] = entry["imageMotionSpeed"]

        background_scenes.append(background_scene)

    other_scenes = [s for s in scene_plan["scenes"] if s["type"] != "background"]

    merged_scene_plan = dict(scene_plan)
    merged_scene_plan["scenes"] = other_scenes + background_scenes

    return merged_scene_plan


def main():

    parser = argparse.ArgumentParser(
        description="Merge human-authored background_scenes.json into scene-plan.json"
    )

    parser.add_argument("episode_folder")

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()
    processing = episode / "processing"

    scene_plan_file = processing / "scene-plan.json"
    transcript_file = processing / "episode_transcript.json"
    manifest_file = processing / "manifest.json"
    background_scenes_file = processing / "background_scenes.json"

    if not scene_plan_file.exists():
        print(f"ERROR: Missing scene plan: {scene_plan_file}")
        sys.exit(1)

    if not transcript_file.exists():
        print(f"ERROR: Missing transcript: {transcript_file}")
        sys.exit(1)

    if not manifest_file.exists():
        print(f"ERROR: Missing manifest: {manifest_file}")
        sys.exit(1)

    scene_plan = load_json(scene_plan_file)
    transcript = load_json(transcript_file)
    manifest = load_json(manifest_file)

    entries = (
        load_json(background_scenes_file).get("scenes", [])
        if background_scenes_file.exists()
        else []
    )

    scene_plan = merge_background_scenes(scene_plan, entries, transcript, manifest)

    write_json_atomic(scene_plan_file, scene_plan)

    print(f"Merged {len(entries)} background scene entry(ies).")
    print(scene_plan_file)


if __name__ == "__main__":
    main()
