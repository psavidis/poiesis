#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_title_scenes import merge_title_scenes
from generate_moments import merge_moment_scenes


LEAD_IN_SECONDS = 0.15
TAIL_SECONDS = 0.25

LOW_LOGPROB_THRESHOLD = -1.0


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


def trim_trailing_low_confidence_segments(segments):

    trimmed = list(segments)

    while trimmed:

        avg_logprob = trimmed[-1].get("avg_logprob")

        if avg_logprob is None or avg_logprob >= LOW_LOGPROB_THRESHOLD:
            break

        trimmed.pop()

    return trimmed


def analyze_speech_bounds(transcript, duration, fps):

    if not transcript:
        return 0, int(duration * fps)


    segments = transcript.get(
        "segments",
        []
    )

    segments = trim_trailing_low_confidence_segments(segments)

    if not segments:
        return 0, int(duration * fps)


    first_start = segments[0]["start"]

    last_end = min(
        segments[-1]["end"],
        duration
    )


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
                "captions": True,
                # Applied uniformly to every cut, like the brand palette —
                # not an AI decision per clip. See Episode.tsx's
                # CROSSFADE_TRANSITION_FRAMES for the actual duration.
                # A specific cut can still be set to "none" by hand-editing
                # scene-plan.json or via a natural-language edit instruction
                # if a particular hard cut is wanted.
                "transition": "crossfade"
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


def run_scene_analysis(episode):

    manifest = load_manifest(
        episode
    )


    scene_plan = create_scene_plan(
        episode,
        manifest
    )


    title_scenes_path = (
            episode
            /
            "processing"
            /
            "title_scenes.json"
    )

    if title_scenes_path.exists():

        with title_scenes_path.open(
                "r",
                encoding="utf-8"
        ) as f:
            titles = json.load(f)["titles"]

        episode_transcript_path = episode / "processing" / "episode_transcript.json"

        with episode_transcript_path.open("r", encoding="utf-8") as f:
            episode_transcript = json.load(f)

        scene_plan = merge_title_scenes(
            scene_plan,
            titles,
            episode_transcript,
            manifest
        )

        print(
            f"Re-merged {len(titles)} existing title scene(s)."
        )


    moments_path = (
            episode
            /
            "processing"
            /
            "moments.json"
    )

    if moments_path.exists():

        with moments_path.open(
                "r",
                encoding="utf-8"
        ) as f:
            moments = json.load(f).get("moments", [])

        scene_plan = merge_moment_scenes(
            scene_plan,
            moments
        )

        print(
            f"Re-merged {len(moments)} existing moment scene(s)."
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

    return scene_plan


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "episode_folder"
    )

    args = parser.parse_args()


    episode = Path(
        args.episode_folder
    ).resolve()


    run_scene_analysis(episode)


if __name__ == "__main__":
    main()