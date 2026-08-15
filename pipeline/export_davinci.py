#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import opentimelineio as otio

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent
RENDERER_DIR = PROJECT_ROOT / "video-renderer"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def regenerate_scene_plan_ts(episode: Path):
    """Remotion renders from video-renderer/generated/episode/scene-plan.ts,
    a codegen'd copy of scene-plan.json (see generate_scene_plan_ts.py) —
    not the JSON file directly. run_pipeline.py always regenerates it right
    after any step that mutates scene-plan.json, so it must be refreshed
    here too, or a render can silently use a stale prior scene plan (e.g.
    captions.json fixed up and scene-plan.json rewritten, but Remotion
    still rendering the old caption durations from a stale .ts)."""

    subprocess.run(
        [
            sys.executable,
            str(PIPELINE_DIR / "generate_scene_plan_ts.py"),
            str(episode),
        ],
        check=True,
    )


def scene_ranges(scene_plan):
    """The track scenes (presenter/title — anything with an absolute
    timelineStartFrame, matching Composition.tsx's durationForScenePlan
    field-presence check rather than a hardcoded type list, since that's
    the one place in the codebase this distinction is already canonically
    made) as (scene_id, start_frame, end_frame) tuples in timeline order.
    Overlay scenes (moment/caption/image) are never their own DaVinci
    clip — they're already baked into whichever track scene's render they
    fall within, exactly as they are in a normal (non-per-scene) render."""

    track_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if "timelineStartFrame" in scene
    ]

    track_scenes = sorted(track_scenes, key=lambda s: s["timelineStartFrame"])

    return [
        (scene["id"], scene["timelineStartFrame"], scene["timelineStartFrame"] + scene["durationInFrames"])
        for scene in track_scenes
    ]


def render_scene_clips(episode: Path, scene_plan, output_dir: Path, resolution=None, resume=False):
    """Renders one transparent ProRes 4444 .mov per track scene, using the
    same flags render_episode.sh's --transparent mode already uses (see
    that script's own comments for why each flag is needed) — just scoped
    to one frame range per call via Remotion's --frames=start-end instead
    of rendering the whole episode in one file. Returns the list of
    (scene_id, clip_path) written, in timeline order.

    With resume=True, a scene whose clip file already exists (non-empty)
    is left in place rather than re-rendered — a per-scene Remotion render
    that dies partway through a long episode (e.g. the "Request closed"
    compositor error) shouldn't force re-rendering every scene that
    already succeeded."""

    output_dir.mkdir(parents=True, exist_ok=True)

    ranges = scene_ranges(scene_plan)

    clips = []

    for scene_id, start_frame, end_frame in ranges:

        clip_path = output_dir / f"{scene_id}.mov"

        if resume and clip_path.exists() and clip_path.stat().st_size > 0:
            print(f"Skipping {scene_id} (already rendered)...")
            clips.append((scene_id, clip_path))
            continue

        command = [
            "npx", "remotion", "render", "Episode", str(clip_path),
            f"--frames={start_frame}-{end_frame - 1}",
            "--codec=prores",
            "--prores-profile=4444",
            "--pixel-format=yuva444p10le",
            "--image-format=png",
            '--props={"backgroundVideo": null}',
        ]

        if resolution:
            width, height = resolution.split("x")
            command.extend([f"--width={width}", f"--height={height}"])

        print(f"Rendering {scene_id} (frames {start_frame}-{end_frame - 1})...")

        subprocess.run(command, cwd=RENDERER_DIR, check=True)

        clips.append((scene_id, clip_path))

    return clips


def clip_label(scene):
    """Human-legible name for a scene's clip on the Resolve timeline —
    a title's own text, or "presenter — <id>" for a presenter scene, so
    the user can tell clips apart in Resolve without cross-referencing
    scene-plan.json."""

    if scene["type"] == "title":
        return scene["text"]

    if scene["type"] == "presenter":
        return f"presenter — {scene['id']}"

    return scene["id"]


def build_otio_timeline(scene_plan, clips):
    """clips: [(scene_id, clip_path), ...] as returned by
    render_scene_clips, in timeline order. Builds a single-video-track
    OTIO timeline with one Clip per rendered scene file, each covering its
    own full duration (already correctly trimmed by the frame-range
    render — no further in/out trimming needed here)."""

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}
    fps = scene_plan["fps"]

    timeline = otio.schema.Timeline(name=scene_plan.get("episode", "Episode"))
    track = otio.schema.Track(name="Video 1")
    timeline.tracks.append(track)

    for scene_id, clip_path in clips:

        scene = scenes_by_id[scene_id]
        duration_frames = scene["durationInFrames"]

        media_reference = otio.schema.ExternalReference(
            target_url=str(clip_path),
            available_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, fps),
                duration=otio.opentime.RationalTime(duration_frames, fps),
            ),
        )

        clip = otio.schema.Clip(
            name=clip_label(scene),
            media_reference=media_reference,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, fps),
                duration=otio.opentime.RationalTime(duration_frames, fps),
            ),
        )

        track.append(clip)

    return timeline


def validate_export(scene_plan, clips_dir: Path, timeline_path: Path):
    """Deterministic check, not an LLM judgment call — mirrors
    qa_check.py's check_missing_media pattern: every track scene must have
    produced a clip file that actually exists on disk, and the OTIO
    timeline itself must have been written. Catches a partial/failed
    per-scene render before the user opens a broken project in Resolve."""

    issues = []

    if not timeline_path.exists():
        issues.append(f"Missing timeline file: {timeline_path}")
        return issues

    for scene_id, start_frame, end_frame in scene_ranges(scene_plan):

        clip_path = clips_dir / f"{scene_id}.mov"

        if not clip_path.exists():
            issues.append(f"Missing rendered clip for {scene_id}: {clip_path}")

    return issues


def export_davinci(episode: Path, scene_plan, resolution=None, resume=False):

    export_dir = episode / "processing" / "davinci-export"
    clips_dir = export_dir / "clips"
    timeline_path = export_dir / "timeline.otio"

    regenerate_scene_plan_ts(episode)

    clips = render_scene_clips(episode, scene_plan, clips_dir, resolution, resume=resume)

    timeline = build_otio_timeline(scene_plan, clips)

    otio.adapters.write_to_file(timeline, str(timeline_path))

    issues = validate_export(scene_plan, clips_dir, timeline_path)

    return timeline_path, issues


def main():

    parser = argparse.ArgumentParser(
        description="Export an episode as a DaVinci Resolve-importable OTIO "
                     "timeline: one transparent ProRes clip per track scene "
                     "(presenter/title, with moments/captions/images already "
                     "baked in), positioned on a timeline.otio the user "
                     "imports via Resolve's File -> Import Timeline -> "
                     "OpenTimelineIO. Background/intro/outro/music stay a "
                     "manual step, same as render_episode.sh --transparent."
    )

    parser.add_argument("episode_folder")
    parser.add_argument(
        "resolution",
        nargs="?",
        default=None,
        help="Optional WIDTHxHEIGHT override, e.g. 3840x2160"
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip scenes whose clip file was already rendered by a prior "
             "run — for resuming after a render failure partway through"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    scene_plan_file = episode / "processing" / "scene-plan.json"

    if not scene_plan_file.exists():
        print(f"ERROR: Missing scene plan: {scene_plan_file}")
        sys.exit(1)

    if args.resolution and not re.match(r"^\d+x\d+$", args.resolution):
        print("ERROR: resolution must be WIDTHxHEIGHT, e.g. 3840x2160")
        sys.exit(1)

    scene_plan = load_json(scene_plan_file)

    timeline_path, issues = export_davinci(episode, scene_plan, args.resolution, resume=args.resume)

    print()
    print("================================")
    if issues:
        print("DaVinci export completed WITH ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("DaVinci export completed")
    print("Timeline:")
    print(timeline_path)
    print("Import via Resolve: File -> Import Timeline -> OpenTimelineIO")
    print("================================")

    if issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
