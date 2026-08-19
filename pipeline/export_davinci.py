#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import opentimelineio as otio

from generate_episode_assets import format_timestamp
from overlay_placement import absolute_position

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent
RENDERER_DIR = PROJECT_ROOT / "video-renderer"

# How many render_clip() calls (each its own "npx remotion render"
# subprocess) run at once. Each clip's OWN render already uses Remotion's
# default intra-render concurrency (parallel headless-browser frame
# rendering within that one clip — confirmed live at "Concurrency 6x" on
# this machine's 12 cores), so running clips fully sequentially left half
# the machine idle between clips: every clip pays Remotion's own bundle/
# browser-launch startup cost from a cold start, one at a time, for an
# episode that can have 50+ clips (one per presenter scene plus one per
# overlay scene). 2 is deliberately conservative rather than
# cpu_count()-driven — each clip's own intra-render work already
# saturates several cores, so running MORE than 2-3 at once would mostly
# contend with itself rather than add real throughput; 2 already lets one
# clip's browser-launch/bundle overhead overlap with another clip's actual
# frame rendering, which is where the sequential version's idle time came
# from. subprocess.run releases the GIL while waiting on the child
# process, so a plain ThreadPoolExecutor (not multiprocessing) is enough —
# the actual CPU-bound work happens in the child "npx remotion render"
# process, not in this Python thread.
RENDER_CONCURRENCY = min(2, os.cpu_count() or 1)

# One clip per element of each of these types, each on its own OTIO track —
# titles/moments/beats are never baked into their parent presenter's clip
# here (contrast render_episode.sh --transparent, which renders one
# flattened composite). "presenter" is handled separately since it also
# produces an audio track from the same source. "caption"/"image"/
# "background" are NOT in this list — they're exported as native Resolve
# data/source-media instead of rendered clips (see build_srt/
# add_native_asset_track), per docs/specs/resolve-native-export-
# architecture.md's Category A/B principle: don't render something that
# can be represented as editable Resolve data. What's left here
# (title/moment/beat) has no reliable native-Resolve representation
# available today — OTIO has no keyframe/text-object schema and driving
# Resolve's own scripting API for that is a separate, heavier undertaking
# (rejected for this pass: requires Resolve Studio running, and its
# transform/title APIs have documented silent-failure modes) — so they
# stay Remotion-rendered transparent clips, same as before this change.
OVERLAY_TRACK_TYPES = ["title", "moment", "beat"]

TRACK_NAMES = {
    "presenter": "Video — Presenter",
    "presenter-audio": "Audio — Presenter",
    "title": "Video — Titles",
    "moment": "Video — Moments",
    "image": "Video — Images",
    "background": "Video — Background",
    "beat": "Video — Beats",
}


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


def scenes_by_id(scene_plan):
    return {scene["id"]: scene for scene in scene_plan["scenes"]}


def presenter_scenes(scene_plan):
    """Presenter scenes in timeline order — each becomes one clip on the
    Presenter video track (and, from the same rendered file, one entry on
    the Presenter audio track)."""

    scenes = [s for s in scene_plan["scenes"] if s["type"] == "presenter"]

    return sorted(scenes, key=lambda s: s["timelineStartFrame"])


def overlay_scenes_of_type(scene_plan, scene_type):
    """Scenes of one type (title/moment/beat, or caption for build_srt), in
    timeline order. Captions respect their parent presenter scene's
    effects.captions flag — the same per-scene on/off state
    generate_captions.py --disable already writes to scene-plan.json, so
    the SRT export doesn't need its own separate caption toggle."""

    by_id = scenes_by_id(scene_plan)

    scenes = [s for s in scene_plan["scenes"] if s["type"] == scene_type]

    if scene_type == "caption":
        scenes = [
            s for s in scenes
            if by_id[s["parentSceneId"]]["effects"]["captions"]
        ]

    return sorted(scenes, key=lambda s: absolute_position(s, by_id))


def build_srt(scene_plan) -> str:
    """SRT built directly from scene-plan.json's own "caption" scenes — the
    exact same reviewed/edited/split captions already shown in the Poiesis
    preview (post-silence-trim, one line per cue after generate_captions.py's
    line-chunking) — rather than re-deriving timing from the raw episode
    transcript (generate_episode_assets.py's own generate_srt does that, for
    a different purpose: a rough whole-episode subtitle file, not
    scene-plan-accurate cue timing). Imported into Resolve as a native,
    editable subtitle track (File -> Import -> Subtitle) instead of
    rendering captions as transparent clips — captions are plain timed text,
    Category A in the resolve-native-export-architecture.md spec."""

    captions = overlay_scenes_of_type(scene_plan, "caption")
    by_id = scenes_by_id(scene_plan)
    fps = scene_plan["fps"]

    lines = []

    for index, scene in enumerate(captions, start=1):
        start_frame = absolute_position(scene, by_id)
        end_frame = start_frame + scene["durationInFrames"]

        lines.append(
            f"{index}\n"
            f"{format_timestamp(start_frame / fps)} --> {format_timestamp(end_frame / fps)}\n"
            f"{scene['text']}\n"
        )

    return "\n".join(lines)


def load_asset_paths(episode: Path, artifact_name: str, list_key: str) -> dict:
    """id -> absolute source-file path, from an index_assets.py/
    index_backgrounds.py-produced artifact (assets.json/backgrounds.json).
    Empty dict (not an error) if the artifact doesn't exist yet — an episode
    with no images/backgrounds never ran that indexing stage, same
    "absence means none" convention scene-plan.json's own optional fields
    already use."""

    path = episode / "processing" / artifact_name

    if not path.exists():
        return {}

    data = load_json(path)

    return {item["id"]: (episode / item["path"]).resolve() for item in data.get(list_key, [])}


def add_native_asset_track(timeline, scene_plan, scenes, asset_paths, id_field, track_kind, track_name):
    """Places each scene's real source file (image or background media,
    resolved via asset_paths[scene[id_field]]) directly on its own OTIO
    track at its own absolute timeline position — no Remotion render
    involved. Same Gap-filling/ordering logic as add_clip_track, but the
    media_reference points at the ORIGINAL asset file rather than a clip
    rendered under clips_dir, and there's no rendered-clip existence check
    (validate_export only validates what render_clip actually produced).
    No-op if scenes is empty, same convention as add_clip_track."""

    if not scenes:
        return

    by_id = scenes_by_id(scene_plan)
    fps = scene_plan["fps"]

    track = otio.schema.Track(name=track_name, kind=track_kind)
    timeline.tracks.append(track)

    cursor = 0

    for scene in scenes:

        asset_path = asset_paths.get(scene[id_field])

        if asset_path is None:
            print(f"WARNING: {scene['id']} references unknown asset {scene[id_field]!r} — skipped.")
            continue

        start_frame = absolute_position(scene, by_id)
        duration_frames = scene["durationInFrames"]

        gap_frames = start_frame - cursor

        if gap_frames > 0:
            track.append(
                otio.schema.Gap(
                    source_range=otio.opentime.TimeRange(
                        start_time=otio.opentime.RationalTime(0, fps),
                        duration=otio.opentime.RationalTime(gap_frames, fps),
                    )
                )
            )
        elif gap_frames < 0:
            print(
                f"WARNING: {scene['id']} starts at frame {start_frame}, before "
                f"the previous clip on {track_name} ends at {cursor} — "
                f"clip may be misplaced in the exported timeline."
            )

        media_reference = otio.schema.ExternalReference(
            target_url=str(asset_path),
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

        cursor = start_frame + duration_frames


def total_clips(scene_plan):
    """Total number of clips export_davinci() will render or skip — one per
    presenter scene plus one per overlay scene of each OVERLAY_TRACK_TYPES
    type (title/moment/beat). Captions/images/backgrounds are excluded —
    they're placed as native data/source-media, not rendered, so they
    never touch this render-progress count. Used to print an upfront
    __TOTAL__ line so a caller streaming this script's stdout (see
    ui/server.py's _stream_command) can show a real N-of-M progress bar
    instead of an open-ended scrolling log — see #65's
    sibling request for the render console UI."""

    return len(presenter_scenes(scene_plan)) + sum(
        len(overlay_scenes_of_type(scene_plan, scene_type)) for scene_type in OVERLAY_TRACK_TYPES
    )


def _report_progress(progress, progress_lock):
    """Increments progress["done"] and prints the __PROGRESS__ sentinel
    line as one atomic unit under progress_lock — required now that
    render_clip can run on several threads at once (see RENDER_CONCURRENCY):
    "done += 1" is a read-modify-write, not a single atomic op, so two
    threads finishing at the same moment could otherwise race and silently
    under-count (both read the same "done", both write back the same
    incremented value, one increment lost). flush=True — see the call
    sites' own history: stdout is a pipe here (not a TTY), so Python fully-
    buffers by default rather than line-buffering; without an explicit
    flush a line can sit in the buffer until process exit instead of
    arriving incrementally as each clip finishes.

    progress_lock=None (e.g. a caller using render_clip directly, outside
    render_presenter_clips/render_overlay_clips' own executor) falls back
    to an ad-hoc lock — safe but pointless for a genuinely single-threaded
    caller, just avoids requiring every render_clip call site to construct
    and pass one for a race that can't happen there."""

    lock = progress_lock or threading.Lock()

    with lock:
        progress["done"] += 1
        print(f"__PROGRESS__{progress['done']}/{progress['total']}", flush=True)


def render_clip(clip_path: Path, start_frame, end_frame, only_type, resolution, resume, progress=None, progress_lock=None):
    """Renders one transparent ProRes 4444 .mov covering [start_frame,
    end_frame) of the full episode timeline, with Episode.tsx's onlyTypes
    prop restricting output to a single scene type — e.g. onlyTypes=
    ["caption"] renders just that caption's text over transparency, with
    the presenter/titles/other overlays in that same frame range omitted
    (they're still resolved for parent lookups, per onlyTypes' contract —
    only their own pixels are skipped). Same flags render_episode.sh
    --transparent already uses, scoped to one frame range and one element
    type per call via Remotion's --frames=start-end.

    May run concurrently with other render_clip calls for different clips
    (see RENDER_CONCURRENCY) — this function itself has no shared mutable
    state of its own (each call renders its own clip_path), only the
    progress dict needs the lock, via _report_progress.

    With resume=True, a clip that already exists (non-empty) is left in
    place rather than re-rendered — a render that dies partway through a
    long episode shouldn't force re-rendering every clip that already
    succeeded.

    progress, when given, is a {"done": int, "total": int} dict this
    function mutates (through _report_progress, using progress_lock) and
    reports via a __PROGRESS__done/total line after EVERY clip (rendered
    or skipped) — a single shared dict rather than a return value, since
    the caller loops (render_presenter_clips/render_overlay_clips) have no
    other running-total bookkeeping to thread a return value through."""

    if resume and clip_path.exists() and clip_path.stat().st_size > 0:
        print(f"Skipping {clip_path.name} (already rendered)...")
        if progress is not None:
            _report_progress(progress, progress_lock)
        return

    command = [
        "npx", "remotion", "render", "Episode", str(clip_path),
        f"--frames={start_frame}-{end_frame - 1}",
        "--codec=prores",
        "--prores-profile=4444",
        "--pixel-format=yuva444p10le",
        "--image-format=png",
        f'--props={{"onlyTypes": ["{only_type}"]}}',
    ]

    if resolution:
        width, height = resolution.split("x")
        command.extend([f"--width={width}", f"--height={height}"])

    print(f"Rendering {clip_path.name} (frames {start_frame}-{end_frame - 1})...")

    subprocess.run(command, cwd=RENDERER_DIR, check=True)

    if progress is not None:
        _report_progress(progress, progress_lock)


def render_presenter_clips(scene_plan, clips_dir: Path, resolution=None, resume=False, progress=None, progress_lock=None):
    """One clip per presenter scene — video (with keyed alpha, if the
    source video has one) and its own embedded audio track together, since
    they come from the same underlying footage. Returns [(scene_id,
    clip_path), ...] in TIMELINE order (unchanged from the previous
    sequential version) — rendering itself now happens across up to
    RENDER_CONCURRENCY clips at once (see that constant's own comment),
    but ThreadPoolExecutor.map preserves input order in its output
    regardless of which worker finishes first, so build_otio_timeline
    downstream still sees clips in the same order it always has."""

    scenes = presenter_scenes(scene_plan)

    def render_one(scene):
        clip_path = clips_dir / f"presenter-{scene['id']}.mov"
        render_clip(
            clip_path,
            scene["timelineStartFrame"],
            scene["timelineStartFrame"] + scene["durationInFrames"],
            "presenter",
            resolution,
            resume,
            progress,
            progress_lock,
        )
        return scene["id"], clip_path

    with ThreadPoolExecutor(max_workers=RENDER_CONCURRENCY) as executor:
        return list(executor.map(render_one, scenes))


def render_overlay_clips(scene_plan, scene_type, clips_dir: Path, resolution=None, resume=False, progress=None, progress_lock=None):
    """One small transparent clip per overlay scene of the given type
    (title/moment/beat — see OVERLAY_TRACK_TYPES), each covering just that
    scene's own absolute frame range. Returns [(scene_id, clip_path), ...]
    in timeline order (see render_presenter_clips' own comment on why
    concurrent rendering doesn't disturb this). Empty list if there are no
    scenes of this type — the caller skips creating a track in that case."""

    by_id = scenes_by_id(scene_plan)
    scenes = overlay_scenes_of_type(scene_plan, scene_type)

    def render_one(scene):
        clip_path = clips_dir / f"{scene_type}-{scene['id']}.mov"
        start_frame = absolute_position(scene, by_id)
        end_frame = start_frame + scene["durationInFrames"]
        render_clip(clip_path, start_frame, end_frame, scene_type, resolution, resume, progress, progress_lock)
        return scene["id"], clip_path

    with ThreadPoolExecutor(max_workers=RENDER_CONCURRENCY) as executor:
        return list(executor.map(render_one, scenes))


def clip_label(scene):
    """Human-legible name for a scene's clip on the Resolve timeline —
    a title's own text, or "presenter — <id>" for a presenter scene, so
    the user can tell clips apart in Resolve without cross-referencing
    scene-plan.json."""

    if scene["type"] == "title":
        return scene["text"]

    if scene["type"] == "caption":
        return scene["text"]

    if scene["type"] == "beat":
        return scene["text"]

    if scene["type"] == "presenter":
        return f"presenter — {scene['id']}"

    if scene["type"] == "image":
        return scene.get("caption") or scene["assetId"]

    if scene["type"] == "background":
        return scene["backgroundId"]

    return scene["id"]


def add_clip_track(timeline, scene_plan, clips, track_kind, track_name):
    """clips: [(scene_id, clip_path), ...] in timeline order, as returned
    by render_presenter_clips/render_overlay_clips. Adds one OTIO Track
    with one Clip per rendered file, each covering its own full duration
    (already correctly trimmed by the frame-range render — no further
    in/out trimming needed here). No-op if clips is empty, so element
    types absent from this episode (e.g. no images) don't produce an
    empty track in the Resolve project.

    OTIO Track.append() places clips back-to-back with no gaps — correct
    for the Presenter track, where consecutive scenes really are adjacent
    on the timeline, but wrong for every sparse overlay track (titles,
    captions, moments, images), whose clips are scattered across the
    episode with silence in between. A Gap is inserted before any clip
    that doesn't start immediately after the previous one ended, so each
    clip lands at its own absolute timelineStartFrame instead of being
    packed against its neighbors."""

    if not clips:
        return

    by_id = scenes_by_id(scene_plan)
    fps = scene_plan["fps"]

    track = otio.schema.Track(name=track_name, kind=track_kind)
    timeline.tracks.append(track)

    cursor = 0

    for scene_id, clip_path in clips:

        scene = by_id[scene_id]
        start_frame = absolute_position(scene, by_id)
        duration_frames = scene["durationInFrames"]

        gap_frames = start_frame - cursor

        if gap_frames > 0:
            track.append(
                otio.schema.Gap(
                    source_range=otio.opentime.TimeRange(
                        start_time=otio.opentime.RationalTime(0, fps),
                        duration=otio.opentime.RationalTime(gap_frames, fps),
                    )
                )
            )
        elif gap_frames < 0:
            # Two same-type overlay scenes overlap in absolute position —
            # shouldn't happen for a well-formed scene-plan.json (verified
            # against real episode data), but OTIO tracks can't represent
            # overlapping clips on one track, so surface it instead of
            # silently mis-placing this clip against its neighbor.
            print(
                f"WARNING: {scene_id} starts at frame {start_frame}, before "
                f"the previous clip on {track_name} ends at {cursor} — "
                f"clip may be misplaced in the exported timeline."
            )

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

        cursor = start_frame + duration_frames


def build_otio_timeline(scene_plan, presenter_clips, overlay_clips_by_type, episode: Path):
    """presenter_clips: [(scene_id, clip_path), ...] from
    render_presenter_clips. overlay_clips_by_type: {scene_type: [(scene_id,
    clip_path), ...]} from render_overlay_clips, one entry per type in
    OVERLAY_TRACK_TYPES. Builds one OTIO track per element type (skipping
    types with no clips) — Background (native source media, bottom of the
    stack so it sits behind the presenter, same compositing order the
    renderer itself uses), Presenter video, Presenter audio (same source
    files as the video track, referenced as an audio Track so Resolve's
    OTIO import actually pulls in the embedded PCM audio instead of
    silently dropping it), then Titles/Moments/Beats (rendered), then
    Images (native source media) on top. Captions are NOT an OTIO track —
    see build_srt, imported into Resolve as a separate native subtitle
    file instead."""

    timeline = otio.schema.Timeline(name=scene_plan.get("episode", "Episode"))

    background_paths = load_asset_paths(episode, "backgrounds.json", "backgrounds")
    add_native_asset_track(
        timeline,
        scene_plan,
        overlay_scenes_of_type(scene_plan, "background"),
        background_paths,
        "backgroundId",
        otio.schema.TrackKind.Video,
        TRACK_NAMES["background"],
    )

    add_clip_track(timeline, scene_plan, presenter_clips, otio.schema.TrackKind.Video, TRACK_NAMES["presenter"])
    add_clip_track(timeline, scene_plan, presenter_clips, otio.schema.TrackKind.Audio, TRACK_NAMES["presenter-audio"])

    for scene_type in OVERLAY_TRACK_TYPES:
        add_clip_track(
            timeline,
            scene_plan,
            overlay_clips_by_type.get(scene_type, []),
            otio.schema.TrackKind.Video,
            TRACK_NAMES[scene_type],
        )

    image_paths = load_asset_paths(episode, "assets.json", "assets")
    add_native_asset_track(
        timeline,
        scene_plan,
        overlay_scenes_of_type(scene_plan, "image"),
        image_paths,
        "assetId",
        otio.schema.TrackKind.Video,
        TRACK_NAMES["image"],
    )

    return timeline


def validate_export(scene_plan, presenter_clips, overlay_clips_by_type, timeline_path: Path, srt_path: Path):
    """Deterministic check, not an LLM judgment call — mirrors
    qa_check.py's check_missing_media pattern: every scene that should have
    produced a clip actually has one on disk, the OTIO timeline itself was
    written, and the captions.srt file exists whenever the episode
    actually has captions to export. See validate_native_assets for the
    image/background asset-resolution counterpart. Catches a partial/
    failed export before the user opens a broken project in Resolve."""

    issues = []

    if not timeline_path.exists():
        issues.append(f"Missing timeline file: {timeline_path}")
        return issues

    expected = list(presenter_clips)
    for clips in overlay_clips_by_type.values():
        expected.extend(clips)

    for scene_id, clip_path in expected:
        if not clip_path.exists():
            issues.append(f"Missing rendered clip for {scene_id}: {clip_path}")

    has_captions = bool(overlay_scenes_of_type(scene_plan, "caption"))
    if has_captions and not srt_path.exists():
        issues.append(f"Missing captions file: {srt_path}")

    return issues


def validate_native_assets(scene_plan, episode: Path):
    """Every image/background scene's assetId/backgroundId must resolve to
    a real file in assets.json/backgrounds.json — add_native_asset_track
    already prints a WARNING and skips a scene it can't resolve rather than
    failing the whole export, so this re-checks the same condition to
    surface it as a proper export issue too, not just a console line easy
    to miss in a streamed log (see ui/server.py's _stream_command)."""

    issues = []

    image_paths = load_asset_paths(episode, "assets.json", "assets")
    for scene in overlay_scenes_of_type(scene_plan, "image"):
        if scene["assetId"] not in image_paths:
            issues.append(f"Missing asset for {scene['id']}: assetId {scene['assetId']!r} not found in assets.json")

    background_paths = load_asset_paths(episode, "backgrounds.json", "backgrounds")
    for scene in overlay_scenes_of_type(scene_plan, "background"):
        if scene["backgroundId"] not in background_paths:
            issues.append(
                f"Missing asset for {scene['id']}: backgroundId {scene['backgroundId']!r} not found in backgrounds.json"
            )

    return issues


def export_davinci(episode: Path, scene_plan, resolution=None, resume=False):

    export_dir = episode / "davinci-export"
    clips_dir = export_dir / "clips"
    timeline_path = export_dir / "timeline.otio"

    clips_dir.mkdir(parents=True, exist_ok=True)

    regenerate_scene_plan_ts(episode)

    # Printed once, upfront, so a caller streaming this script's stdout
    # (ui/server.py's _stream_command) can show a real N-of-M progress bar
    # instead of an open-ended scrolling log — see total_clips' own
    # docstring. progress is a single dict shared by every render_clip call
    # below (both loops, and every clip within each — see
    # RENDER_CONCURRENCY), incremented once per clip whether rendered or
    # skipped (resume mode). progress_lock guards that shared dict now that
    # multiple clips can finish at genuinely the same moment.
    total = total_clips(scene_plan)
    # flush=True — see render_clip's __PROGRESS__ print for why this is
    # required when stdout is a pipe, not a TTY (confirmed live: without
    # this, the frontend's progress bar never appeared at all, stuck
    # showing raw npx remotion render output for the entire multi-minute
    # export, because this line sat unflushed in Python's stdout buffer).
    print(f"__TOTAL__{total}", flush=True)
    progress = {"done": 0, "total": total}
    progress_lock = threading.Lock()

    presenter_clips = render_presenter_clips(
        scene_plan, clips_dir, resolution, resume=resume, progress=progress, progress_lock=progress_lock
    )

    overlay_clips_by_type = {
        scene_type: render_overlay_clips(
            scene_plan, scene_type, clips_dir, resolution, resume=resume, progress=progress, progress_lock=progress_lock
        )
        for scene_type in OVERLAY_TRACK_TYPES
    }

    timeline = build_otio_timeline(scene_plan, presenter_clips, overlay_clips_by_type, episode)

    otio.adapters.write_to_file(timeline, str(timeline_path))

    srt_path = export_dir / "captions.srt"
    srt_path.write_text(build_srt(scene_plan), encoding="utf-8")

    issues = validate_export(scene_plan, presenter_clips, overlay_clips_by_type, timeline_path, srt_path)
    issues.extend(validate_native_assets(scene_plan, episode))

    return timeline_path, issues


def main():

    parser = argparse.ArgumentParser(
        description="Export an episode as a DaVinci Resolve-importable "
                     "project: timeline.otio (presenter/title/moment/beat "
                     "as rendered transparent ProRes clips, one per "
                     "scene-plan element, each on its own track — plus "
                     "background/image scenes placed as their REAL source "
                     "media, never rendered) and captions.srt (a native, "
                     "editable Resolve subtitle track, also never "
                     "rendered) — per docs/specs/resolve-native-export-"
                     "architecture.md's Category A/B principle: render "
                     "only what can't be represented as editable Resolve "
                     "data. Import via Resolve's File -> Import Timeline "
                     "-> OpenTimelineIO, then File -> Import -> Subtitle "
                     "for captions.srt. Data flow is one-directional "
                     "(Poiesis -> Resolve) — edits made in Resolve are "
                     "never read back into scene-plan.json; fix the edit "
                     "plan and re-export instead."
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
        help="Skip clips that were already rendered by a prior run — for "
             "resuming after a render failure partway through"
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
    print("Captions:")
    print(timeline_path.parent / "captions.srt")
    print("Import via Resolve: File -> Import Timeline -> OpenTimelineIO")
    print("Then: File -> Import -> Subtitle, for captions.srt")
    print("================================")

    if issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
