#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from pathlib import Path


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


def check_missing_media(episode, manifest):

    issues = []

    for video in manifest["videos"]:

        path = episode / video["path"]

        if not path.exists():
            issues.append(
                {
                    "check": "missing_media",
                    "severity": "high",
                    "videoId": video["id"],
                    "detail": f"Referenced file does not exist: {path}",
                }
            )

    return issues


def check_scene_plan_video_ids(scene_plan, manifest):

    issues = []

    known_ids = {video["id"] for video in manifest["videos"]}

    for scene in scene_plan["scenes"]:

        if scene["type"] != "presenter":
            continue

        if scene["videoId"] not in known_ids:
            issues.append(
                {
                    "check": "unknown_video_id",
                    "severity": "high",
                    "sceneId": scene["id"],
                    "detail": f"Scene references unknown videoId: {scene['videoId']}",
                }
            )

    return issues


def check_timeline_continuity(scene_plan):

    issues = []

    scenes = sorted(
        scene_plan["scenes"],
        key=lambda s: s["timelineStartFrame"]
    )

    expected_frame = 0

    for scene in scenes:

        start = scene["timelineStartFrame"]

        if start != expected_frame:

            issues.append(
                {
                    "check": "timeline_gap_or_overlap",
                    "severity": "medium",
                    "sceneId": scene["id"],
                    "detail": (
                        f"Expected scene to start at frame {expected_frame}, "
                        f"found {start}"
                    ),
                }
            )

        expected_frame = start + scene["durationInFrames"]

    return issues


def get_video_duration_seconds(path: Path):

    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)

    return float(data["format"]["duration"])


def check_rendered_duration(episode, scene_plan):

    issues = []

    rendered = episode / "rendered" / f"{episode.name}.mp4"

    if not rendered.exists():
        return issues

    total_frames = max(
        (
            scene["timelineStartFrame"] + scene["durationInFrames"]
            for scene in scene_plan["scenes"]
        ),
        default=0,
    )

    expected_seconds = total_frames / scene_plan["fps"]

    actual_seconds = get_video_duration_seconds(rendered)

    tolerance_seconds = 0.5

    if abs(actual_seconds - expected_seconds) > tolerance_seconds:

        issues.append(
            {
                "check": "duration_mismatch",
                "severity": "high",
                "detail": (
                    f"Expected rendered duration ~{expected_seconds:.2f}s "
                    f"(from scene plan), found {actual_seconds:.2f}s"
                ),
            }
        )

    return issues


def run_qa(episode: Path):

    processing = episode / "processing"

    manifest_path = processing / "manifest.json"
    scene_plan_path = processing / "scene-plan.json"

    if not manifest_path.exists():
        raise RuntimeError(f"Missing manifest: {manifest_path}")

    if not scene_plan_path.exists():
        raise RuntimeError(f"Missing scene plan: {scene_plan_path}")

    manifest = load_json(manifest_path)
    scene_plan = load_json(scene_plan_path)

    issues = []

    issues += check_missing_media(episode, manifest)
    issues += check_scene_plan_video_ids(scene_plan, manifest)
    issues += check_timeline_continuity(scene_plan)
    issues += check_rendered_duration(episode, scene_plan)

    return {
        "status": "warning" if issues else "ok",
        "issues_count": len(issues),
        "issues": issues,
    }


def main():

    parser = argparse.ArgumentParser(
        description="Run QA checks against an episode's scene plan and rendered output"
    )

    parser.add_argument("episode_folder")

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    output = episode / "processing" / "qa-report.json"

    try:
        report = run_qa(episode)

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    write_json_atomic(output, report)

    print("QA check completed.")
    print(f"Status: {report['status']}")
    print(f"Issues: {report['issues_count']}")
    print(output)

    if report["status"] != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
