import json
from pathlib import Path
from unittest.mock import patch

import opentimelineio as otio

from export_davinci import (
    OVERLAY_TRACK_TYPES,
    build_otio_timeline,
    build_srt,
    clip_label,
    export_davinci,
    load_asset_paths,
    overlay_scenes_of_type,
    presenter_scenes,
    render_clip,
    render_overlay_clips,
    render_presenter_clips,
    total_clips,
    validate_export,
    validate_native_assets,
)


def _scene_plan_two_clips_and_a_title():
    return {
        "fps": 30,
        "episode": "Test Episode",
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 100,
                "timelineStartFrame": 0,
                "durationInFrames": 100,
                "effects": {"captions": True, "transition": "none"},
            },
            {
                "id": "scene-title-002",
                "type": "title",
                "text": "Chapter Two",
                "timelineStartFrame": 100,
                "durationInFrames": 60,
            },
            {
                "id": "scene-002",
                "type": "presenter",
                "videoId": "002",
                "sourceStartFrame": 0,
                "sourceEndFrame": 200,
                "timelineStartFrame": 160,
                "durationInFrames": 200,
                "effects": {"captions": False, "transition": "none"},
            },
            {
                "id": "scene-moment-0",
                "type": "moment",
                "treatment": "bottom-callout",
                "text": "a key phrase",
                "parentSceneId": "scene-001",
                "offsetInParentFrames": 10,
                "durationInFrames": 90,
            },
            {
                "id": "scene-caption-0",
                "type": "caption",
                "text": "hello",
                "parentSceneId": "scene-001",
                "offsetInParentFrames": 0,
                "durationInFrames": 60,
            },
            {
                "id": "scene-caption-1",
                "type": "caption",
                "text": "captions off on this scene",
                "parentSceneId": "scene-002",
                "offsetInParentFrames": 0,
                "durationInFrames": 60,
            },
        ],
    }


def test_presenter_scenes_in_timeline_order():
    scenes = presenter_scenes(_scene_plan_two_clips_and_a_title())

    assert [s["id"] for s in scenes] == ["scene-001", "scene-002"]


def test_overlay_scenes_of_type_filters_and_sorts():
    scene_plan = _scene_plan_two_clips_and_a_title()

    titles = overlay_scenes_of_type(scene_plan, "title")
    moments = overlay_scenes_of_type(scene_plan, "moment")

    assert [s["id"] for s in titles] == ["scene-title-002"]
    assert [s["id"] for s in moments] == ["scene-moment-0"]


def test_overlay_scenes_of_type_captions_respects_parent_effects_flag():
    scene_plan = _scene_plan_two_clips_and_a_title()

    captions = overlay_scenes_of_type(scene_plan, "caption")

    # scene-caption-0's parent (scene-001) has captions enabled;
    # scene-caption-1's parent (scene-002) has them disabled.
    assert [s["id"] for s in captions] == ["scene-caption-0"]


def test_total_clips_counts_presenters_plus_rendered_overlays_only():
    scene_plan = _scene_plan_two_clips_and_a_title()

    # 2 presenter + 1 title + 1 moment = 4. Captions are excluded — they're
    # exported as a native SRT (build_srt), never rendered, so they don't
    # count toward render progress.
    assert total_clips(scene_plan) == 4


def test_render_clip_reports_progress_after_a_render(tmp_path, capsys):
    progress = {"done": 0, "total": 3}

    with patch("export_davinci.subprocess.run"):
        render_clip(tmp_path / "clip.mov", 0, 10, "presenter", None, resume=False, progress=progress)

    assert progress["done"] == 1
    assert "__PROGRESS__1/3" in capsys.readouterr().out


def test_render_clip_reports_progress_after_a_resume_skip(tmp_path, capsys):
    clip_path = tmp_path / "clip.mov"
    clip_path.write_bytes(b"existing content")

    progress = {"done": 1, "total": 3}

    render_clip(clip_path, 0, 10, "presenter", None, resume=True, progress=progress)

    assert progress["done"] == 2
    assert "__PROGRESS__2/3" in capsys.readouterr().out


def test_render_clip_without_progress_arg_prints_no_progress_line(tmp_path, capsys):
    with patch("export_davinci.subprocess.run"):
        render_clip(tmp_path / "clip.mov", 0, 10, "presenter", None, resume=False)

    assert "__PROGRESS__" not in capsys.readouterr().out


def _scene_plan_with_n_presenter_scenes(n):
    return {
        "fps": 30,
        "episode": "Concurrency Test Episode",
        "scenes": [
            {
                "id": f"scene-{i:03d}",
                "type": "presenter",
                "videoId": f"{i:03d}",
                "sourceStartFrame": 0,
                "sourceEndFrame": 100,
                "timelineStartFrame": i * 100,
                "durationInFrames": 100,
                "effects": {"captions": True, "transition": "none"},
            }
            for i in range(n)
        ],
    }


def test_render_presenter_clips_progress_count_is_exact_under_concurrency(tmp_path):
    # Regression guard for the race this session's RENDER_CONCURRENCY change
    # introduced: progress["done"] += 1 is a read-modify-write, not atomic,
    # so without _report_progress's lock, several clips finishing at
    # genuinely the same moment could silently under-count (two threads
    # read the same "done", both write back the same incremented value).
    # A real sleep (not a mock that returns instantly) in the fake
    # subprocess.run is what actually forces real thread overlap here — an
    # instant mock can happen to never overlap even with max_workers=2.
    import time

    scene_plan = _scene_plan_with_n_presenter_scenes(12)
    progress = {"done": 0, "total": 12}

    def fake_run(*args, **kwargs):
        time.sleep(0.01)

    with patch("export_davinci.subprocess.run", side_effect=fake_run):
        clips = render_presenter_clips(scene_plan, tmp_path, progress=progress)

    assert len(clips) == 12
    assert [scene_id for scene_id, _ in clips] == [f"scene-{i:03d}" for i in range(12)]
    # The actual race guard: every one of the 12 clips must have been
    # counted exactly once, no matter how their completions overlapped.
    assert progress["done"] == 12


def test_clip_label_uses_title_text_for_title_scenes():
    scene = {"type": "title", "id": "scene-title-002", "text": "Chapter Two"}

    assert clip_label(scene) == "Chapter Two"


def test_clip_label_uses_caption_text_for_caption_scenes():
    scene = {"type": "caption", "id": "scene-caption-0", "text": "hello"}

    assert clip_label(scene) == "hello"


def test_clip_label_uses_presenter_prefix_for_presenter_scenes():
    scene = {"type": "presenter", "id": "scene-001"}

    assert clip_label(scene) == "presenter — scene-001"


def test_render_presenter_clips_invokes_remotion_per_presenter_scene(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()

    with patch("export_davinci.subprocess.run") as mock_run:
        clips = render_presenter_clips(scene_plan, tmp_path)

    assert mock_run.call_count == 2
    # The RETURNED clips list stays in timeline order regardless of which
    # clip's subprocess call actually happened first (render_presenter_clips
    # renders up to RENDER_CONCURRENCY clips concurrently — see that
    # constant's own comment — so raw mock call order is no longer
    # guaranteed to match scene order the way it was under the old
    # sequential loop; ThreadPoolExecutor.map's OUTPUT order is what's
    # actually guaranteed, which is what downstream code — build_otio_timeline
    # — depends on).
    assert [scene_id for scene_id, _ in clips] == ["scene-001", "scene-002"]

    all_commands = [call.args[0] for call in mock_run.call_args_list]
    assert any("npx" in command for command in all_commands)
    assert any("--frames=0-99" in command for command in all_commands)
    assert all('"onlyTypes": ["presenter"]' in command[-1] for command in all_commands)


def test_render_presenter_clips_passes_resolution_when_given(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()

    with patch("export_davinci.subprocess.run") as mock_run:
        render_presenter_clips(scene_plan, tmp_path, resolution="3840x2160")

    all_commands = [call.args[0] for call in mock_run.call_args_list]
    assert all("--width=3840" in command for command in all_commands)
    assert all("--height=2160" in command for command in all_commands)


def test_render_overlay_clips_uses_absolute_position_for_frame_range(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()

    with patch("export_davinci.subprocess.run") as mock_run:
        clips = render_overlay_clips(scene_plan, "moment", tmp_path)

    assert [scene_id for scene_id, _ in clips] == ["scene-moment-0"]

    command = mock_run.call_args_list[0].args[0]
    # scene-moment-0: parent scene-001 starts at 0, offset 10, duration 90
    assert "--frames=10-99" in command
    assert '"onlyTypes": ["moment"]' in command[-1]


def test_render_overlay_clips_empty_when_no_scenes_of_type(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()

    with patch("export_davinci.subprocess.run") as mock_run:
        clips = render_overlay_clips(scene_plan, "image", tmp_path)

    assert clips == []
    assert mock_run.call_count == 0


def test_render_clips_resume_skips_existing_clips(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    tmp_path.mkdir(exist_ok=True)

    (tmp_path / "presenter-scene-001.mov").write_bytes(b"fake")

    with patch("export_davinci.subprocess.run") as mock_run:
        clips = render_presenter_clips(scene_plan, tmp_path, resume=True)

    assert mock_run.call_count == 1
    assert [scene_id for scene_id, _ in clips] == ["scene-001", "scene-002"]


def test_render_clips_resume_rerenders_empty_clip(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    tmp_path.mkdir(exist_ok=True)

    (tmp_path / "presenter-scene-001.mov").write_bytes(b"")

    with patch("export_davinci.subprocess.run") as mock_run:
        render_presenter_clips(scene_plan, tmp_path, resume=True)

    assert mock_run.call_count == 2


def test_render_clips_without_resume_rerenders_everything(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    tmp_path.mkdir(exist_ok=True)

    (tmp_path / "presenter-scene-001.mov").write_bytes(b"fake")

    with patch("export_davinci.subprocess.run") as mock_run:
        render_presenter_clips(scene_plan, tmp_path)

    assert mock_run.call_count == 2


def test_build_otio_timeline_creates_one_track_per_populated_type(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()

    presenter_clips = [("scene-001", Path("/fake/presenter-scene-001.mov")),
                        ("scene-002", Path("/fake/presenter-scene-002.mov"))]
    overlay_clips_by_type = {
        "title": [("scene-title-002", Path("/fake/title-scene-title-002.mov"))],
        "moment": [("scene-moment-0", Path("/fake/moment-scene-moment-0.mov"))],
        "beat": [],
    }

    timeline = build_otio_timeline(scene_plan, presenter_clips, overlay_clips_by_type, tmp_path)

    track_names = [t.name for t in timeline.tracks]

    assert "Video — Presenter" in track_names
    assert "Audio — Presenter" in track_names
    assert "Video — Titles" in track_names
    assert "Video — Moments" in track_names
    # No captions/images/backgrounds in this plan (or no assets.json/
    # backgrounds.json in tmp_path) -> no empty native tracks created.
    assert "Video — Images" not in track_names
    assert "Video — Background" not in track_names
    # Captions are never an OTIO track at all — see build_srt.
    assert "Video — Captions" not in track_names


def test_build_otio_timeline_presenter_audio_track_references_same_media_as_video(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()

    presenter_clips = [("scene-001", Path("/fake/presenter-scene-001.mov"))]

    timeline = build_otio_timeline(scene_plan, presenter_clips, {t: [] for t in OVERLAY_TRACK_TYPES}, tmp_path)

    video_track = next(t for t in timeline.tracks if t.name == "Video — Presenter")
    audio_track = next(t for t in timeline.tracks if t.name == "Audio — Presenter")

    assert video_track[0].media_reference.target_url == audio_track[0].media_reference.target_url
    assert audio_track.kind == "Audio"
    assert video_track.kind == "Video"


def test_build_otio_timeline_clip_durations_match_scene_durations(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()

    overlay_clips_by_type = {
        "title": [("scene-title-002", Path("/fake/title-scene-title-002.mov"))],
        "moment": [],
        "beat": [],
    }

    timeline = build_otio_timeline(scene_plan, [], overlay_clips_by_type, tmp_path)

    title_track = next(t for t in timeline.tracks if t.name == "Video — Titles")

    # scene-title-002 starts at frame 100, so a leading Gap fills [0, 100)
    # before the clip itself.
    assert title_track[0].source_range.duration.value == 100
    assert title_track[1].source_range.duration.value == 60


def test_build_otio_timeline_inserts_gaps_so_sparse_clips_land_at_absolute_position(tmp_path):
    # Regression guard: a real export had moments/titles packed back-to-back
    # instead of at their real timeline positions, because Track.append()
    # places clips immediately after each other with no gap by default.
    scene_plan = _scene_plan_two_clips_and_a_title()

    overlay_clips_by_type = {
        "title": [],
        "moment": [("scene-moment-0", Path("/fake/moment-scene-moment-0.mov"))],
        "beat": [],
    }

    timeline = build_otio_timeline(scene_plan, [], overlay_clips_by_type, tmp_path)

    moment_track = next(t for t in timeline.tracks if t.name == "Video — Moments")

    # scene-moment-0: parent scene-001 (timelineStartFrame 0) + offset 10.
    assert isinstance(moment_track[0], otio.schema.Gap)
    assert moment_track[0].source_range.duration.value == 10
    assert moment_track[1].name == "scene-moment-0"


def test_build_otio_timeline_no_gap_when_clips_are_contiguous(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()

    presenter_clips = [("scene-001", Path("/fake/presenter-scene-001.mov")),
                        ("scene-002", Path("/fake/presenter-scene-002.mov"))]

    timeline = build_otio_timeline(scene_plan, presenter_clips, {t: [] for t in OVERLAY_TRACK_TYPES}, tmp_path)

    video_track = next(t for t in timeline.tracks if t.name == "Video — Presenter")

    # scene-001 ends at 100, scene-002 starts at 160 -> a 60-frame gap
    # between them, but no gap before scene-001 itself (starts at 0).
    assert video_track[0].name == "presenter — scene-001"
    assert isinstance(video_track[1], otio.schema.Gap)
    assert video_track[1].source_range.duration.value == 60
    assert video_track[2].name == "presenter — scene-002"


def test_build_otio_timeline_places_native_image_and_background_tracks(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    scene_plan["scenes"].append({
        "id": "scene-image-0",
        "type": "image",
        "assetId": "asset-1",
        "display": "full",
        "parentSceneId": "scene-001",
        "offsetInParentFrames": 5,
        "durationInFrames": 30,
    })
    scene_plan["scenes"].append({
        "id": "scene-bg-0",
        "type": "background",
        "backgroundId": "bg-1",
        "timelineStartFrame": 0,
        "durationInFrames": 400,
    })

    (tmp_path / "processing").mkdir()
    (tmp_path / "processing" / "assets.json").write_text(
        json.dumps({"assets": [{"id": "asset-1", "path": "graphics/shot.png"}]})
    )
    (tmp_path / "processing" / "backgrounds.json").write_text(
        json.dumps({"backgrounds": [{"id": "bg-1", "path": "background/bg.png"}]})
    )

    timeline = build_otio_timeline(scene_plan, [], {t: [] for t in OVERLAY_TRACK_TYPES}, tmp_path)

    image_track = next(t for t in timeline.tracks if t.name == "Video — Images")
    background_track = next(t for t in timeline.tracks if t.name == "Video — Background")

    # scene-image-0 starts at absolute frame 5 (parent scene-001 + offset
    # 5) -> a leading Gap fills [0, 5) before the clip itself.
    assert isinstance(image_track[0], otio.schema.Gap)
    assert image_track[1].media_reference.target_url == str((tmp_path / "graphics/shot.png").resolve())
    # scene-bg-0 starts at absolute frame 0 -> no leading gap.
    assert background_track[0].media_reference.target_url == str((tmp_path / "background/bg.png").resolve())


def test_export_davinci_writes_under_episode_root_not_processing(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()

    with patch("export_davinci.subprocess.run"):
        timeline_path, _ = export_davinci(tmp_path, scene_plan)

    assert timeline_path == tmp_path / "davinci-export" / "timeline.otio"
    assert "processing" not in timeline_path.parts


def test_export_davinci_regenerates_scene_plan_ts_before_rendering(tmp_path):
    # Remotion renders from generated/episode/scene-plan.ts, a codegen'd
    # copy of scene-plan.json — not the JSON file. If export_davinci
    # doesn't refresh it first, a scene-plan.json fix silently doesn't
    # take effect and Remotion keeps rendering the stale plan.
    scene_plan = _scene_plan_two_clips_and_a_title()

    with patch("export_davinci.subprocess.run") as mock_run:
        export_davinci(tmp_path, scene_plan)

    commands = [call.args[0] for call in mock_run.call_args_list]
    regen_calls = [c for c in commands if "generate_scene_plan_ts.py" in c[1]]

    assert len(regen_calls) == 1
    regen_index = commands.index(regen_calls[0])
    render_indices = [i for i, c in enumerate(commands) if "remotion" in c]
    assert all(regen_index < i for i in render_indices)


def test_validate_export_reports_missing_clip(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    timeline_path = tmp_path / "timeline.otio"
    timeline_path.write_text("{}")
    srt_path = tmp_path / "captions.srt"
    srt_path.write_text("")

    presenter_clips = [("scene-001", tmp_path / "presenter-scene-001.mov"),
                        ("scene-002", tmp_path / "presenter-scene-002.mov")]
    (tmp_path / "presenter-scene-001.mov").write_bytes(b"fake")
    # scene-002's clip is never written.

    issues = validate_export(scene_plan, presenter_clips, {t: [] for t in OVERLAY_TRACK_TYPES}, timeline_path, srt_path)

    assert len(issues) == 1
    assert "scene-002" in issues[0]


def test_validate_export_reports_missing_timeline_file(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    timeline_path = tmp_path / "timeline.otio"
    srt_path = tmp_path / "captions.srt"

    issues = validate_export(scene_plan, [], {t: [] for t in OVERLAY_TRACK_TYPES}, timeline_path, srt_path)

    assert len(issues) == 1
    assert "timeline" in issues[0].lower()


def test_validate_export_reports_missing_srt_when_episode_has_captions(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    timeline_path = tmp_path / "timeline.otio"
    timeline_path.write_text("{}")
    srt_path = tmp_path / "captions.srt"
    # srt_path never written — scene_plan has a caption with captions
    # enabled on its parent (scene-caption-0), so this must be flagged.

    issues = validate_export(scene_plan, [], {t: [] for t in OVERLAY_TRACK_TYPES}, timeline_path, srt_path)

    assert any("captions" in issue.lower() for issue in issues)


def test_validate_export_no_issues_when_everything_present(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    timeline_path = tmp_path / "timeline.otio"
    timeline_path.write_text("{}")
    srt_path = tmp_path / "captions.srt"
    srt_path.write_text("")

    presenter_clips = [("scene-001", tmp_path / "presenter-scene-001.mov"),
                        ("scene-002", tmp_path / "presenter-scene-002.mov")]
    for _, path in presenter_clips:
        path.write_bytes(b"fake")

    issues = validate_export(scene_plan, presenter_clips, {t: [] for t in OVERLAY_TRACK_TYPES}, timeline_path, srt_path)

    assert issues == []


def test_build_srt_uses_scene_plan_caption_scenes_respecting_captions_flag():
    scene_plan = _scene_plan_two_clips_and_a_title()

    srt = build_srt(scene_plan)

    # scene-caption-0 (parent scene-001, captions enabled): offset 0,
    # duration 60 at fps 30 -> 0.0s to 2.0s.
    assert "1\n00:00:00,000 --> 00:00:02,000\nhello" in srt
    # scene-caption-1's parent (scene-002) has captions disabled, same
    # filter overlay_scenes_of_type applies elsewhere in this module.
    assert "captions off on this scene" not in srt


def test_load_asset_paths_returns_empty_dict_when_artifact_missing(tmp_path):
    assert load_asset_paths(tmp_path, "assets.json", "assets") == {}


def test_load_asset_paths_resolves_ids_to_absolute_paths(tmp_path):
    (tmp_path / "processing").mkdir()
    (tmp_path / "processing" / "assets.json").write_text(
        json.dumps({"assets": [{"id": "asset-1", "path": "graphics/shot.png"}]})
    )

    paths = load_asset_paths(tmp_path, "assets.json", "assets")

    assert paths == {"asset-1": (tmp_path / "graphics/shot.png").resolve()}


def test_validate_native_assets_reports_unresolved_asset_ids(tmp_path):
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 100,
                "timelineStartFrame": 0,
                "durationInFrames": 100,
                "effects": {"captions": True, "transition": "none"},
            },
            {
                "id": "scene-image-0",
                "type": "image",
                "assetId": "missing-asset",
                "display": "full",
                "parentSceneId": "scene-001",
                "offsetInParentFrames": 0,
                "durationInFrames": 30,
            },
        ],
    }

    issues = validate_native_assets(scene_plan, tmp_path)

    assert len(issues) == 1
    assert "missing-asset" in issues[0]
