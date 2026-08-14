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


def check_scene_plan_asset_ids(scene_plan, assets):

    issues = []

    known_ids = {asset["id"] for asset in assets}

    for scene in scene_plan["scenes"]:

        if scene["type"] == "image":
            asset_id = scene["assetId"]
        elif scene["type"] == "moment" and scene["treatment"] == "side-image":
            asset_id = scene["assetId"]
        else:
            continue

        if asset_id not in known_ids:
            issues.append(
                {
                    "check": "unknown_asset_id",
                    "severity": "high",
                    "sceneId": scene["id"],
                    "detail": f"Scene references unknown assetId: {asset_id}",
                }
            )

    return issues


def is_overlay_scene(scene):

    # "emphasis" is the pre-moments overlay type (see the now-removed
    # generate_visual_scenes.py) — still recognized here so qa_check.py
    # doesn't break on an older episode's scene-plan.json that was never
    # re-run through generate_moments.py. No migration is required for
    # existing episodes; this is the compatibility path for them.
    if scene["type"] in ("moment", "emphasis"):
        return True

    if scene["type"] == "caption":
        return True

    if scene["type"] == "image":
        return scene.get("display") == "inset"

    return False


# Which treatments require a presenterSide — the presenter's on-screen
# position is derived per-frame from the active moment's own window at
# render time (Episode.tsx's layoutWindowsForScene), so this is a
# moment-internal consistency check (treatment vs. its own presenterSide),
# not a moment-vs-parent one — there's no parent "layout" field anymore.
MOMENT_REQUIRES_NO_SIDE = {"bottom-callout"}
MOMENT_REQUIRES_SIDE = {"side-text", "side-image"}

# Mirrors Episode.tsx's TRANSITION_FRAMES / generate_moments.py's
# TRANSITION_FRAMES — the presenter's actual on-screen shift window is a
# moment's own span padded by this many frames on both sides, so two
# moments on the same parent must not have overlapping padded windows or
# their slide animations would collide.
MOMENT_TRANSITION_FRAMES = 24


def check_moment_presenter_side_agreement(scene_plan):

    issues = []

    for scene in scene_plan["scenes"]:

        if scene["type"] != "moment":
            continue

        treatment = scene["treatment"]
        presenter_side = scene.get("presenterSide")

        if treatment in MOMENT_REQUIRES_NO_SIDE and presenter_side is not None:
            issues.append(
                {
                    "check": "moment_presenter_side_mismatch",
                    "severity": "medium",
                    "sceneId": scene["id"],
                    "detail": (
                        f"Moment treatment '{treatment}' should not set presenterSide, "
                        f"but found '{presenter_side}'"
                    ),
                }
            )

        elif treatment in MOMENT_REQUIRES_SIDE and presenter_side not in ("left", "right"):
            issues.append(
                {
                    "check": "moment_presenter_side_mismatch",
                    "severity": "medium",
                    "sceneId": scene["id"],
                    "detail": (
                        f"Moment treatment '{treatment}' requires presenterSide "
                        f"'left' or 'right', found '{presenter_side}'"
                    ),
                }
            )

    return issues


def check_moment_windows_do_not_overlap(scene_plan):

    issues = []

    moments_by_parent = {}

    for scene in scene_plan["scenes"]:

        if scene["type"] != "moment":
            continue

        moments_by_parent.setdefault(scene["parentSceneId"], []).append(scene)

    for parent_id, moments in moments_by_parent.items():

        moments = sorted(moments, key=lambda m: m["offsetInParentFrames"])

        kept_windows = []

        for moment in moments:

            start = moment["offsetInParentFrames"] - MOMENT_TRANSITION_FRAMES
            end = moment["offsetInParentFrames"] + moment["durationInFrames"] + MOMENT_TRANSITION_FRAMES

            overlaps = any(start < w_end and end > w_start for w_start, w_end in kept_windows)

            if overlaps:
                issues.append(
                    {
                        "check": "moment_windows_overlap",
                        "severity": "medium",
                        "sceneId": moment["id"],
                        "detail": (
                            f"Moment's on-screen window (including transition pad) overlaps "
                            f"another moment on the same parent scene {parent_id}"
                        ),
                    }
                )
                continue

            kept_windows.append((start, end))

    return issues


def check_timeline_continuity(scene_plan):

    issues = []

    track_scenes = sorted(
        (
            scene
            for scene in scene_plan["scenes"]
            if not is_overlay_scene(scene)
        ),
        key=lambda s: s["timelineStartFrame"]
    )

    expected_frame = 0

    for scene in track_scenes:

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


def check_overlay_scenes_within_bounds(scene_plan):

    issues = []

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}

    overlay_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if is_overlay_scene(scene)
    ]

    for overlay in overlay_scenes:

        parent = scenes_by_id.get(overlay.get("parentSceneId"))

        if not parent or is_overlay_scene(parent):

            issues.append(
                {
                    "check": "overlay_outside_bounds",
                    "severity": "medium",
                    "sceneId": overlay["id"],
                    "detail": (
                        f"Overlay scene references missing or invalid "
                        f"parentSceneId: {overlay.get('parentSceneId')}"
                    ),
                }
            )

            continue

        offset = overlay["offsetInParentFrames"]
        overlay_end = offset + overlay["durationInFrames"]

        if offset < 0 or overlay_end > parent["durationInFrames"]:

            issues.append(
                {
                    "check": "overlay_outside_bounds",
                    "severity": "medium",
                    "sceneId": overlay["id"],
                    "detail": (
                        f"Overlay scene [{offset}, {overlay_end}) is not "
                        f"fully contained within parent scene {parent['id']} "
                        f"(duration {parent['durationInFrames']})"
                    ),
                }
            )

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
            if not is_overlay_scene(scene)
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

    assets_path = processing / "assets.json"
    assets = load_json(assets_path)["assets"] if assets_path.exists() else []

    issues = []

    issues += check_missing_media(episode, manifest)
    issues += check_scene_plan_video_ids(scene_plan, manifest)
    issues += check_scene_plan_asset_ids(scene_plan, assets)
    issues += check_timeline_continuity(scene_plan)
    issues += check_overlay_scenes_within_bounds(scene_plan)
    issues += check_moment_presenter_side_agreement(scene_plan)
    issues += check_moment_windows_do_not_overlap(scene_plan)
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
