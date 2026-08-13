#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from llm.client import LLMClient


PROMPT_FILE = PIPELINE_DIR / "prompts" / "title_scenes.txt"

TITLE_DURATION_FRAMES = 60


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


def group_transcript_by_clip(transcript, manifest):

    filename_to_id = {
        video["filename"]: video["id"]
        for video in manifest["videos"]
    }

    clips = {}

    for segment in transcript["segments"]:

        video_id = filename_to_id.get(segment["source"])

        if video_id is None:
            continue

        clips.setdefault(video_id, []).append(segment["text"])

    return clips


def format_clips_for_prompt(clips):

    lines = []

    for video_id in sorted(clips):
        lines.append(f"[{video_id}]")
        lines.append(" ".join(clips[video_id]))
        lines.append("")

    return "\n".join(lines)


def propose_title_scenes(transcript, manifest, llm: LLMClient, prompt_template: str):

    clips = group_transcript_by_clip(transcript, manifest)

    prompt = prompt_template.replace(
        "{clips}",
        format_clips_for_prompt(clips)
    )

    response = llm.complete_json(prompt, thinking=False)

    valid_ids = set(clips.keys())

    titles = [
        title
        for title in response.get("titles", [])
        if title.get("videoId") in valid_ids and title.get("text")
    ]

    return titles


def merge_title_scenes(scene_plan, titles):

    titles_by_video_id = {
        title["videoId"]: title["text"]
        for title in titles
    }

    # Track scenes (presenter) define the contiguous timeline; overlay scenes
    # (emphasis, inset images) don't consume track space. Rebuilding track
    # positions from scratch — rather than incrementally shifting whatever
    # positions happen to already be on the scenes — makes this merge safe
    # to re-run on an already-merged plan (idempotent), since it never
    # compounds a previous run's title offset.
    track_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if scene["type"] == "presenter"
    ]

    overlay_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if scene["type"] not in ("presenter", "title")
    ]

    merged_scenes = []
    timeline_frame = 0

    for scene in track_scenes:

        title_text = titles_by_video_id.get(scene.get("videoId"))

        if title_text:

            merged_scenes.append(
                {
                    "id": f"scene-title-{scene['videoId']}",
                    "type": "title",
                    "text": title_text,
                    "timelineStartFrame": timeline_frame,
                    "durationInFrames": TITLE_DURATION_FRAMES,
                }
            )

            timeline_frame += TITLE_DURATION_FRAMES

        scene = dict(scene)
        scene["timelineStartFrame"] = timeline_frame

        merged_scenes.append(scene)

        timeline_frame += scene["durationInFrames"]

    merged_scenes.extend(overlay_scenes)

    scene_plan = dict(scene_plan)
    scene_plan["scenes"] = merged_scenes

    return scene_plan


def main():

    parser = argparse.ArgumentParser(
        description="Propose title scenes from the episode transcript using an LLM"
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate title scenes even if already applied"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    processing = episode / "processing"

    transcript_file = processing / "episode_transcript.json"
    manifest_file = processing / "manifest.json"
    scene_plan_file = processing / "scene-plan.json"
    output_file = processing / "title_scenes.json"

    if not transcript_file.exists():
        print(f"ERROR: Missing transcript: {transcript_file}")
        sys.exit(1)

    if not manifest_file.exists():
        print(f"ERROR: Missing manifest: {manifest_file}")
        sys.exit(1)

    if not scene_plan_file.exists():
        print(f"ERROR: Missing scene plan: {scene_plan_file}")
        sys.exit(1)

    if output_file.exists() and not args.force:
        print("Title scenes already proposed. Skipping.")
        print(output_file)
        return

    llm = LLMClient(PROJECT_ROOT / "config.json")
    prompt_template = load_prompt(PROMPT_FILE)

    transcript = load_json(transcript_file)
    manifest = load_json(manifest_file)
    scene_plan = load_json(scene_plan_file)

    print("Proposing title scenes...")
    print()

    try:
        titles = propose_title_scenes(
            transcript,
            manifest,
            llm,
            prompt_template
        )

        write_json_atomic(output_file, {"titles": titles})

        scene_plan = merge_title_scenes(scene_plan, titles)

        write_json_atomic(scene_plan_file, scene_plan)

        print(f"Proposed {len(titles)} title scene(s).")
        print(output_file)
        print(scene_plan_file)

    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
