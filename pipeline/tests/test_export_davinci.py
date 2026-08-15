from pathlib import Path
from unittest.mock import patch

from export_davinci import (
    build_otio_timeline,
    clip_label,
    export_davinci,
    render_scene_clips,
    scene_ranges,
    validate_export,
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
                "effects": {"captions": True, "transition": "none"},
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
        ],
    }


def test_scene_ranges_includes_only_track_scenes_in_timeline_order():
    ranges = scene_ranges(_scene_plan_two_clips_and_a_title())

    assert ranges == [
        ("scene-001", 0, 100),
        ("scene-title-002", 100, 160),
        ("scene-002", 160, 360),
    ]


def test_scene_ranges_excludes_overlay_scenes():
    scene_plan = _scene_plan_two_clips_and_a_title()

    ranges = scene_ranges(scene_plan)
    ids = {scene_id for scene_id, _, _ in ranges}

    assert "scene-moment-0" not in ids
    assert "scene-caption-0" not in ids


def test_scene_ranges_sorts_by_timeline_position_even_if_out_of_order_in_the_list():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-002",
                "type": "presenter",
                "timelineStartFrame": 100,
                "durationInFrames": 50,
            },
            {
                "id": "scene-001",
                "type": "presenter",
                "timelineStartFrame": 0,
                "durationInFrames": 100,
            },
        ],
    }

    ranges = scene_ranges(scene_plan)

    assert [scene_id for scene_id, _, _ in ranges] == ["scene-001", "scene-002"]


def test_clip_label_uses_title_text_for_title_scenes():
    scene = {"type": "title", "id": "scene-title-002", "text": "Chapter Two"}

    assert clip_label(scene) == "Chapter Two"


def test_clip_label_uses_presenter_prefix_for_presenter_scenes():
    scene = {"type": "presenter", "id": "scene-001"}

    assert clip_label(scene) == "presenter — scene-001"


def test_build_otio_timeline_has_one_clip_per_track_scene_in_order():
    scene_plan = _scene_plan_two_clips_and_a_title()
    ranges = scene_ranges(scene_plan)
    clips = [(scene_id, Path(f"/fake/{scene_id}.mov")) for scene_id, _, _ in ranges]

    timeline = build_otio_timeline(scene_plan, clips)

    track = timeline.tracks[0]
    assert [c.name for c in track] == ["presenter — scene-001", "Chapter Two", "presenter — scene-002"]


def test_build_otio_timeline_clip_durations_match_scene_durations():
    scene_plan = _scene_plan_two_clips_and_a_title()
    ranges = scene_ranges(scene_plan)
    clips = [(scene_id, Path(f"/fake/{scene_id}.mov")) for scene_id, _, _ in ranges]

    timeline = build_otio_timeline(scene_plan, clips)

    track = timeline.tracks[0]
    durations = [c.source_range.duration.value for c in track]

    assert durations == [100, 60, 200]


def test_render_scene_clips_invokes_remotion_per_scene(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    output_dir = tmp_path / "clips"

    with patch("export_davinci.subprocess.run") as mock_run:
        clips = render_scene_clips(tmp_path, scene_plan, output_dir)

    assert mock_run.call_count == 3
    assert [scene_id for scene_id, _ in clips] == ["scene-001", "scene-title-002", "scene-002"]

    first_call_command = mock_run.call_args_list[0].args[0]
    assert "npx" in first_call_command
    assert "--frames=0-99" in first_call_command
    assert "--codec=prores" in first_call_command


def test_render_scene_clips_passes_resolution_when_given(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    output_dir = tmp_path / "clips"

    with patch("export_davinci.subprocess.run") as mock_run:
        render_scene_clips(tmp_path, scene_plan, output_dir, resolution="3840x2160")

    first_call_command = mock_run.call_args_list[0].args[0]
    assert "--width=3840" in first_call_command
    assert "--height=2160" in first_call_command


def test_render_scene_clips_resume_skips_existing_clips(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    output_dir = tmp_path / "clips"
    output_dir.mkdir()

    # Simulate scene-001 already rendered by a prior run that crashed
    # partway through.
    (output_dir / "scene-001.mov").write_bytes(b"fake")

    with patch("export_davinci.subprocess.run") as mock_run:
        clips = render_scene_clips(tmp_path, scene_plan, output_dir, resume=True)

    assert mock_run.call_count == 2
    rendered_ids = [call.args[0][3] for call in mock_run.call_args_list]
    assert all("scene-001" not in path for path in rendered_ids)
    assert [scene_id for scene_id, _ in clips] == ["scene-001", "scene-title-002", "scene-002"]


def test_render_scene_clips_resume_rerenders_empty_clip(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    output_dir = tmp_path / "clips"
    output_dir.mkdir()

    # A zero-byte file (e.g. left by a crashed ffmpeg/remotion process)
    # must not be treated as a successfully rendered clip.
    (output_dir / "scene-001.mov").write_bytes(b"")

    with patch("export_davinci.subprocess.run") as mock_run:
        render_scene_clips(tmp_path, scene_plan, output_dir, resume=True)

    assert mock_run.call_count == 3


def test_render_scene_clips_without_resume_rerenders_everything(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    output_dir = tmp_path / "clips"
    output_dir.mkdir()

    (output_dir / "scene-001.mov").write_bytes(b"fake")

    with patch("export_davinci.subprocess.run") as mock_run:
        render_scene_clips(tmp_path, scene_plan, output_dir)

    assert mock_run.call_count == 3


def test_export_davinci_regenerates_scene_plan_ts_before_rendering(tmp_path):
    # Remotion renders from generated/episode/scene-plan.ts, a codegen'd
    # copy of scene-plan.json — not the JSON file. If export_davinci
    # doesn't refresh it first, a scene-plan.json fix (e.g. dropping
    # slivers from generate_captions.py) silently doesn't take effect and
    # Remotion keeps rendering the stale plan.
    scene_plan = _scene_plan_two_clips_and_a_title()

    with patch("export_davinci.subprocess.run") as mock_run:
        export_davinci(tmp_path, scene_plan)

    commands = [call.args[0] for call in mock_run.call_args_list]
    regen_calls = [c for c in commands if "generate_scene_plan_ts.py" in c[1]]

    assert len(regen_calls) == 1
    # Must happen before any Remotion render call.
    regen_index = commands.index(regen_calls[0])
    render_indices = [i for i, c in enumerate(commands) if "remotion" in c]
    assert all(regen_index < i for i in render_indices)


def test_validate_export_reports_missing_clip(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    timeline_path = tmp_path / "timeline.otio"
    timeline_path.write_text("{}")

    # only create 2 of the 3 expected clips
    (clips_dir / "scene-001.mov").write_bytes(b"fake")
    (clips_dir / "scene-title-002.mov").write_bytes(b"fake")

    issues = validate_export(scene_plan, clips_dir, timeline_path)

    assert len(issues) == 1
    assert "scene-002" in issues[0]


def test_validate_export_reports_missing_timeline_file(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    clips_dir = tmp_path / "clips"
    timeline_path = tmp_path / "timeline.otio"

    issues = validate_export(scene_plan, clips_dir, timeline_path)

    assert len(issues) == 1
    assert "timeline" in issues[0].lower()


def test_validate_export_no_issues_when_everything_present(tmp_path):
    scene_plan = _scene_plan_two_clips_and_a_title()
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    timeline_path = tmp_path / "timeline.otio"
    timeline_path.write_text("{}")

    for scene_id in ("scene-001", "scene-title-002", "scene-002"):
        (clips_dir / f"{scene_id}.mov").write_bytes(b"fake")

    issues = validate_export(scene_plan, clips_dir, timeline_path)

    assert issues == []
