#!/usr/bin/env python3

import json
import sys
from pathlib import Path


PADDING_SECONDS = 0.5


def load_json(path: Path):
    with path.open(
            "r",
            encoding="utf-8"
    ) as f:
        return json.load(f)


def save_json(path: Path, data):
    temp = path.with_suffix(".tmp.json")

    with temp.open(
            "w",
            encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    temp.replace(path)


def get_last_speech_time(transcript):
    segments = transcript.get(
        "segments",
        []
    )

    if not segments:
        return None

    return max(
        segment["end"]
        for segment in segments
    )


def analyze_scene_plan(
        episode_folder: Path
):

    processing = (
            episode_folder
            / "processing"
    )

    scene_plan_path = (
            processing
            / "scene-plan.json"
    )

    transcripts_dir = (
            processing
            / "transcripts"
    )

    if not scene_plan_path.exists():
        raise RuntimeError(
            f"Missing scene plan: {scene_plan_path}"
        )

    scene_plan = load_json(
        scene_plan_path
    )

    fps = scene_plan["fps"]

    updated = 0

    for scene in scene_plan["scenes"]:

        video_id = scene["videoId"]

        transcript_file = (
                transcripts_dir
                / f"{video_id}.json"
        )

        if not transcript_file.exists():
            print(
                f"{video_id}: no transcript, skipped"
            )
            continue

        transcript = load_json(
            transcript_file
        )

        last_speech = get_last_speech_time(
            transcript
        )

        if last_speech is None:
            print(
                f"{video_id}: empty transcript, skipped"
            )
            continue

        new_duration = round(
            (
                    last_speech
                    + PADDING_SECONDS
            )
            * fps
        )

        old_duration = scene[
            "durationInFrames"
        ]

        if new_duration < old_duration:

            print(
                f"{video_id}: "
                f"{old_duration} -> {new_duration} frames"
            )

            scene[
                "sourceEndFrame"
            ] = new_duration

            scene[
                "durationInFrames"
            ] = new_duration

            updated += 1

        else:
            print(
                f"{video_id}: no trim needed"
            )

    save_json(
        scene_plan_path,
        scene_plan
    )

    print()
    print(
        f"Updated scenes: {updated}"
    )


def main():

    if len(sys.argv) != 2:
        print(
            "Usage: analyze_scenes.py <episode-folder>"
        )
        sys.exit(1)

    episode_folder = Path(
        sys.argv[1]
    ).resolve()

    analyze_scene_plan(
        episode_folder
    )


if __name__ == "__main__":
    main()