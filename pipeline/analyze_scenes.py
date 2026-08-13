#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


LEAD_IN_SECONDS = 0.15
TAIL_SECONDS = 0.40


def load_manifest(episode):
    path = episode / "processing" / "manifest.json"

    with path.open(
            "r",
            encoding="utf-8"
    ) as f:
        return json.load(f)


def load_transcript(episode, video_id):
    path = (
            episode
            / "processing"
            / "transcripts"
            / f"{video_id}.json"
    )

    if not path.exists():
        return None

    with path.open(
            "r",
            encoding="utf-8"
    ) as f:
        return json.load(f)


def analyze_speech_bounds(transcript, duration, fps):

    if not transcript:
        return 0, int(duration * fps)


    segments = transcript.get(
        "segments",
        []
    )

    if not segments:
        return 0, int(duration * fps)


    first_start = segments[0]["start"]

    last_end = segments[-1]["end"]


    start_seconds = max(
        0,
        first_start - LEAD_IN_SECONDS
    )

    end_seconds = min(
        duration,
        last_end + TAIL_SECONDS
    )


    return (
        int(start_seconds * fps),
        int(end_seconds * fps)
    )


def create_scene_plan(episode, manifest):

    fps = manifest["fps"]

    scenes = []

    timeline_frame = 0


    for video in manifest["videos"]:

        transcript = load_transcript(
            episode,
            video["id"]
        )


        source_start, source_end = (
            analyze_speech_bounds(
                transcript,
                video["duration"],
                fps
            )
        )


        duration = (
                source_end
                -
                source_start
        )


        scene = {
            "id": f"scene-{video['id']}",
            "type": "presenter",
            "videoId": video["id"],

            "sourceStartFrame": source_start,
            "sourceEndFrame": source_end,

            "timelineStartFrame": timeline_frame,

            "durationInFrames": duration,

            "effects": {
                "captions": False,
                "transition": "none"
            }
        }


        scenes.append(scene)


        timeline_frame += duration


        print(
            f"{video['id']}: "
            f"{source_start} -> "
            f"{source_end} frames"
        )


    return {
        "version": 1,
        "episode": manifest["episode"],
        "fps": fps,
        "scenes": scenes
    }


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "episode_folder"
    )

    args = parser.parse_args()


    episode = Path(
        args.episode_folder
    ).resolve()


    manifest = load_manifest(
        episode
    )


    scene_plan = create_scene_plan(
        episode,
        manifest
    )


    output = (
            episode
            /
            "processing"
            /
            "scene-plan.json"
    )


    with output.open(
            "w",
            encoding="utf-8"
    ) as f:
        json.dump(
            scene_plan,
            f,
            indent=2
        )


    print()
    print(
        f"Updated scenes: {len(scene_plan['scenes'])}"
    )


if __name__ == "__main__":
    main()