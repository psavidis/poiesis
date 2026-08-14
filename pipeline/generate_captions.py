#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from generate_title_scenes import write_json_atomic  # noqa: E402
from generate_visual_scenes import _insert_overlay_scene  # noqa: E402


# Whisper's segments are sentence/multi-sentence length (no word-level
# timing exists anywhere in this pipeline), so a single segment can run well
# past what's comfortably readable as one on-screen caption. Cap how long
# any single caption block stays up rather than pretending word-level
# splitting is possible without data that doesn't exist.
MAX_CAPTION_DURATION_FRAMES = 180  # 6s at 30fps


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_transcript(episode: Path, video_id: str):
    path = episode / "processing" / "transcripts" / f"{video_id}.json"

    if not path.exists():
        return None

    return load_json(path)


def captions_for_presenter_scene(scene, transcript, fps):
    """Clips this clip's transcript segments to the scene's post-silence-trim
    [sourceStartFrame, sourceEndFrame) window and returns them positioned
    relative to the scene's own start (offsetInParentFrames), the same
    relative-positioning pattern emphasis/image overlays use — so re-running
    analyze_scenes.py later (which can shift trim points) never leaves a
    caption pointing at the wrong moment; it's always correct relative to
    the clip's own kept range."""

    if not transcript:
        return []

    source_start = scene["sourceStartFrame"]
    source_end = scene["sourceEndFrame"]

    captions = []

    for segment in transcript.get("segments", []):

        segment_start = round(segment["start"] * fps)
        segment_end = round(segment["end"] * fps)

        clipped_start = max(segment_start, source_start)
        clipped_end = min(segment_end, source_end)

        if clipped_end <= clipped_start:
            continue

        duration = min(clipped_end - clipped_start, MAX_CAPTION_DURATION_FRAMES)

        text = segment["text"].strip()

        if not text:
            continue

        captions.append(
            {
                "parentSceneId": scene["id"],
                "offsetInParentFrames": clipped_start - source_start,
                "durationInFrames": duration,
                "text": text,
            }
        )

    return captions


def merge_caption_scenes(scene_plan, proposals):

    existing_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if scene["type"] != "caption"
    ]

    scenes_by_id = {scene["id"]: scene for scene in existing_scenes}

    merged_scenes = list(existing_scenes)

    for index, proposal in enumerate(proposals):

        parent = scenes_by_id.get(proposal["parentSceneId"])

        if not parent:
            continue

        caption_scene = {
            "id": f"scene-caption-{index}",
            "type": "caption",
            "text": proposal["text"],
            "parentSceneId": proposal["parentSceneId"],
            "offsetInParentFrames": proposal["offsetInParentFrames"],
            "durationInFrames": proposal["durationInFrames"],
        }

        _insert_overlay_scene(
            merged_scenes,
            scenes_by_id,
            caption_scene,
            parent["timelineStartFrame"] + proposal["offsetInParentFrames"]
        )

    scene_plan = dict(scene_plan)
    scene_plan["scenes"] = merged_scenes

    return scene_plan


def generate_captions(episode: Path, scene_plan):

    fps = scene_plan["fps"]

    all_captions = []

    for scene in scene_plan["scenes"]:

        if scene["type"] != "presenter":
            continue

        transcript = load_transcript(episode, scene["videoId"])

        all_captions.extend(
            captions_for_presenter_scene(scene, transcript, fps)
        )

    return all_captions


def main():

    parser = argparse.ArgumentParser(
        description="Generate caption overlay scenes from per-clip transcripts, "
                     "clipped to the post-silence-trim scene plan"
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate captions even if already applied"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    processing = episode / "processing"

    scene_plan_file = processing / "scene-plan.json"
    output_file = processing / "captions.json"

    if not scene_plan_file.exists():
        print(f"ERROR: Missing scene plan: {scene_plan_file}")
        sys.exit(1)

    if output_file.exists() and not args.force:
        print("Captions already generated. Skipping.")
        print(output_file)
        return

    scene_plan = load_json(scene_plan_file)

    print("Generating captions...")

    captions = generate_captions(episode, scene_plan)

    write_json_atomic(output_file, {"captions": captions})

    scene_plan = merge_caption_scenes(scene_plan, captions)

    write_json_atomic(scene_plan_file, scene_plan)

    print(f"Generated {len(captions)} caption scenes.")
    print(output_file)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
