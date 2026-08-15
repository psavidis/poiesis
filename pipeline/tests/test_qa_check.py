from unittest.mock import patch

from qa_check import (
    check_audio_video_duration_parity,
    check_black_frames,
    check_missing_media,
    check_moment_presenter_side_agreement,
    check_moment_windows_do_not_overlap,
    check_overlay_scenes_within_bounds,
    check_rendered_duration,
    check_scene_plan_asset_ids,
    check_scene_plan_video_ids,
    check_silent_audio,
    check_timeline_continuity,
)


def test_check_missing_media_flags_nonexistent_file(tmp_path):
    manifest = {
        "videos": [
            {"id": "001", "path": "original_footage/missing.mp4"},
        ]
    }

    issues = check_missing_media(tmp_path, manifest)

    assert len(issues) == 1
    assert issues[0]["check"] == "missing_media"
    assert issues[0]["videoId"] == "001"


def test_check_missing_media_passes_when_file_exists(tmp_path):
    footage_dir = tmp_path / "original_footage"
    footage_dir.mkdir()
    (footage_dir / "a.mp4").write_bytes(b"fake")

    manifest = {
        "videos": [
            {"id": "001", "path": "original_footage/a.mp4"},
        ]
    }

    assert check_missing_media(tmp_path, manifest) == []


def test_check_scene_plan_video_ids_flags_unknown_id():
    scene_plan = {
        "scenes": [
            {"id": "scene-001", "type": "presenter", "videoId": "999"},
        ]
    }
    manifest = {"videos": [{"id": "001"}]}

    issues = check_scene_plan_video_ids(scene_plan, manifest)

    assert len(issues) == 1
    assert issues[0]["check"] == "unknown_video_id"


def test_check_scene_plan_video_ids_ignores_non_presenter_scenes():
    scene_plan = {
        "scenes": [
            {"id": "scene-title-001", "type": "title", "text": "Intro"},
        ]
    }
    manifest = {"videos": []}

    assert check_scene_plan_video_ids(scene_plan, manifest) == []


def test_check_scene_plan_asset_ids_flags_unknown_id():
    scene_plan = {
        "scenes": [
            {"id": "scene-image-0", "type": "image", "assetId": "img-999"},
        ]
    }
    assets = [{"id": "img-001"}]

    issues = check_scene_plan_asset_ids(scene_plan, assets)

    assert len(issues) == 1
    assert issues[0]["check"] == "unknown_asset_id"


def test_check_scene_plan_asset_ids_passes_for_known_id():
    scene_plan = {
        "scenes": [
            {"id": "scene-image-0", "type": "image", "assetId": "img-001"},
        ]
    }
    assets = [{"id": "img-001"}]

    assert check_scene_plan_asset_ids(scene_plan, assets) == []


def test_check_scene_plan_asset_ids_ignores_non_image_scenes():
    scene_plan = {
        "scenes": [
            {"id": "scene-title-001", "type": "title", "text": "Intro"},
        ]
    }

    assert check_scene_plan_asset_ids(scene_plan, []) == []


def test_check_scene_plan_asset_ids_flags_unknown_id_for_side_image_moment():
    scene_plan = {
        "scenes": [
            {"id": "scene-moment-0", "type": "moment", "treatment": "side-image", "assetId": "img-999"},
        ]
    }
    assets = [{"id": "img-001"}]

    issues = check_scene_plan_asset_ids(scene_plan, assets)

    assert len(issues) == 1
    assert issues[0]["check"] == "unknown_asset_id"


def test_check_scene_plan_asset_ids_ignores_non_side_image_moments():
    scene_plan = {
        "scenes": [
            {"id": "scene-moment-0", "type": "moment", "treatment": "bottom-callout", "text": "hi"},
        ]
    }

    assert check_scene_plan_asset_ids(scene_plan, []) == []


def test_check_scene_plan_asset_ids_flags_unknown_id_for_full_visual_image_moment():
    scene_plan = {
        "scenes": [
            {
                "id": "scene-moment-0",
                "type": "moment",
                "treatment": "full-visual",
                "fullVisualKind": "image",
                "assetId": "img-999",
            },
        ]
    }
    assets = [{"id": "img-001"}]

    issues = check_scene_plan_asset_ids(scene_plan, assets)

    assert len(issues) == 1
    assert issues[0]["check"] == "unknown_asset_id"


def test_check_scene_plan_asset_ids_ignores_full_visual_non_image_moments():
    scene_plan = {
        "scenes": [
            {"id": "scene-moment-0", "type": "moment", "treatment": "full-visual", "fullVisualKind": "text", "text": "hi"},
        ]
    }

    assert check_scene_plan_asset_ids(scene_plan, []) == []


def test_check_moment_presenter_side_agreement_passes_for_bottom_callout_without_side():
    scene_plan = {
        "scenes": [
            {"id": "m", "type": "moment", "treatment": "bottom-callout"},
        ]
    }

    assert check_moment_presenter_side_agreement(scene_plan) == []


def test_check_moment_presenter_side_agreement_flags_bottom_callout_with_side():
    scene_plan = {
        "scenes": [
            {"id": "m", "type": "moment", "treatment": "bottom-callout", "presenterSide": "left"},
        ]
    }

    issues = check_moment_presenter_side_agreement(scene_plan)

    assert len(issues) == 1
    assert issues[0]["check"] == "moment_presenter_side_mismatch"
    assert issues[0]["sceneId"] == "m"


def test_check_moment_presenter_side_agreement_passes_for_side_text_with_side():
    scene_plan = {
        "scenes": [
            {"id": "m", "type": "moment", "treatment": "side-text", "presenterSide": "left"},
        ]
    }

    assert check_moment_presenter_side_agreement(scene_plan) == []


def test_check_moment_presenter_side_agreement_flags_side_text_without_side():
    scene_plan = {
        "scenes": [
            {"id": "m", "type": "moment", "treatment": "side-text"},
        ]
    }

    issues = check_moment_presenter_side_agreement(scene_plan)

    assert len(issues) == 1
    assert issues[0]["sceneId"] == "m"


def test_check_moment_presenter_side_agreement_passes_for_full_visual_without_side():
    scene_plan = {
        "scenes": [
            {"id": "m", "type": "moment", "treatment": "full-visual", "fullVisualKind": "text"},
        ]
    }

    assert check_moment_presenter_side_agreement(scene_plan) == []


def test_check_moment_presenter_side_agreement_flags_full_visual_with_side():
    scene_plan = {
        "scenes": [
            {"id": "m", "type": "moment", "treatment": "full-visual", "fullVisualKind": "text", "presenterSide": "left"},
        ]
    }

    issues = check_moment_presenter_side_agreement(scene_plan)

    assert len(issues) == 1
    assert issues[0]["sceneId"] == "m"


def test_check_moment_presenter_side_agreement_flags_side_code_without_side():
    scene_plan = {
        "scenes": [
            {"id": "m", "type": "moment", "treatment": "side-code"},
        ]
    }

    issues = check_moment_presenter_side_agreement(scene_plan)

    assert len(issues) == 1
    assert issues[0]["sceneId"] == "m"


def test_check_moment_presenter_side_agreement_flags_side_diagram_without_side():
    scene_plan = {
        "scenes": [
            {"id": "m", "type": "moment", "treatment": "side-diagram"},
        ]
    }

    issues = check_moment_presenter_side_agreement(scene_plan)

    assert len(issues) == 1
    assert issues[0]["sceneId"] == "m"


def test_check_moment_windows_do_not_overlap_passes_for_well_spaced_moments():
    scene_plan = {
        "scenes": [
            {
                "id": "m1",
                "type": "moment",
                "parentSceneId": "a",
                "offsetInParentFrames": 0,
                "durationInFrames": 90,
            },
            {
                "id": "m2",
                "type": "moment",
                "parentSceneId": "a",
                "offsetInParentFrames": 500,
                "durationInFrames": 150,
            },
        ]
    }

    assert check_moment_windows_do_not_overlap(scene_plan) == []


def test_check_moment_windows_do_not_overlap_flags_overlapping_moments_same_parent():
    scene_plan = {
        "scenes": [
            {
                "id": "m1",
                "type": "moment",
                "parentSceneId": "a",
                "offsetInParentFrames": 0,
                "durationInFrames": 90,
            },
            {
                "id": "m2",
                "type": "moment",
                "parentSceneId": "a",
                "offsetInParentFrames": 100,  # within m1's trailing transition pad
                "durationInFrames": 150,
            },
        ]
    }

    issues = check_moment_windows_do_not_overlap(scene_plan)

    assert len(issues) == 1
    assert issues[0]["check"] == "moment_windows_overlap"
    assert issues[0]["sceneId"] == "m2"


def test_check_moment_windows_do_not_overlap_ignores_different_parents():
    scene_plan = {
        "scenes": [
            {
                "id": "m1",
                "type": "moment",
                "parentSceneId": "a",
                "offsetInParentFrames": 0,
                "durationInFrames": 90,
            },
            {
                "id": "m2",
                "type": "moment",
                "parentSceneId": "b",
                "offsetInParentFrames": 0,
                "durationInFrames": 90,
            },
        ]
    }

    assert check_moment_windows_do_not_overlap(scene_plan) == []


def test_check_timeline_continuity_passes_for_contiguous_scenes():
    scene_plan = {
        "scenes": [
            {"id": "a", "type": "presenter", "timelineStartFrame": 0, "durationInFrames": 100},
            {"id": "b", "type": "presenter", "timelineStartFrame": 100, "durationInFrames": 50},
        ]
    }

    assert check_timeline_continuity(scene_plan) == []


def test_check_timeline_continuity_flags_gap():
    scene_plan = {
        "scenes": [
            {"id": "a", "type": "presenter", "timelineStartFrame": 0, "durationInFrames": 100},
            {"id": "b", "type": "presenter", "timelineStartFrame": 150, "durationInFrames": 50},
        ]
    }

    issues = check_timeline_continuity(scene_plan)

    assert len(issues) == 1
    assert issues[0]["check"] == "timeline_gap_or_overlap"
    assert issues[0]["sceneId"] == "b"


def test_check_timeline_continuity_flags_overlap():
    scene_plan = {
        "scenes": [
            {"id": "a", "type": "presenter", "timelineStartFrame": 0, "durationInFrames": 100},
            {"id": "b", "type": "presenter", "timelineStartFrame": 80, "durationInFrames": 50},
        ]
    }

    issues = check_timeline_continuity(scene_plan)

    assert len(issues) == 1
    assert issues[0]["sceneId"] == "b"


def test_check_timeline_continuity_ignores_overlay_scenes():
    scene_plan = {
        "scenes": [
            {"id": "a", "type": "presenter", "timelineStartFrame": 0, "durationInFrames": 100},
            {"id": "b", "type": "presenter", "timelineStartFrame": 100, "durationInFrames": 50},
            {"id": "e", "type": "moment", "timelineStartFrame": 40, "durationInFrames": 30},
        ]
    }

    assert check_timeline_continuity(scene_plan) == []


def test_check_timeline_continuity_ignores_legacy_emphasis_scenes():
    # backward compatibility: an episode processed before the moments
    # feature existed may still have "emphasis" scenes in its
    # scene-plan.json (no migration is required) — qa_check.py must not
    # treat them as track scenes.
    scene_plan = {
        "scenes": [
            {"id": "a", "type": "presenter", "timelineStartFrame": 0, "durationInFrames": 100},
            {"id": "b", "type": "presenter", "timelineStartFrame": 100, "durationInFrames": 50},
            {"id": "e", "type": "emphasis", "timelineStartFrame": 40, "durationInFrames": 30},
        ]
    }

    assert check_timeline_continuity(scene_plan) == []


def test_check_timeline_continuity_ignores_inset_image_scenes():
    scene_plan = {
        "scenes": [
            {"id": "a", "type": "presenter", "timelineStartFrame": 0, "durationInFrames": 100},
            {
                "id": "i",
                "type": "image",
                "display": "inset",
                "timelineStartFrame": 40,
                "durationInFrames": 30,
            },
        ]
    }

    assert check_timeline_continuity(scene_plan) == []


def test_check_timeline_continuity_treats_full_display_image_as_track_scene():
    scene_plan = {
        "scenes": [
            {"id": "a", "type": "presenter", "timelineStartFrame": 0, "durationInFrames": 100},
            {
                "id": "i",
                "type": "image",
                "display": "full",
                "timelineStartFrame": 200,  # gap: full-display images occupy the track
                "durationInFrames": 30,
            },
        ]
    }

    issues = check_timeline_continuity(scene_plan)

    assert len(issues) == 1
    assert issues[0]["sceneId"] == "i"


def test_check_overlay_scenes_within_bounds_passes_when_contained():
    scene_plan = {
        "scenes": [
            {"id": "a", "type": "presenter", "timelineStartFrame": 0, "durationInFrames": 100},
            {
                "id": "e",
                "type": "moment",
                "parentSceneId": "a",
                "offsetInParentFrames": 40,
                "durationInFrames": 30,
            },
        ]
    }

    assert check_overlay_scenes_within_bounds(scene_plan) == []


def test_check_overlay_scenes_within_bounds_flags_scene_outside_any_base_scene():
    scene_plan = {
        "scenes": [
            {"id": "a", "type": "presenter", "timelineStartFrame": 0, "durationInFrames": 100},
            {
                "id": "e",
                "type": "moment",
                "parentSceneId": "a",
                "offsetInParentFrames": 90,
                "durationInFrames": 30,
            },
        ]
    }

    issues = check_overlay_scenes_within_bounds(scene_plan)

    assert len(issues) == 1
    assert issues[0]["check"] == "overlay_outside_bounds"
    assert issues[0]["sceneId"] == "e"


def test_check_overlay_scenes_within_bounds_flags_missing_parent():
    scene_plan = {
        "scenes": [
            {
                "id": "e",
                "type": "moment",
                "parentSceneId": "does-not-exist",
                "offsetInParentFrames": 0,
                "durationInFrames": 30,
            },
        ]
    }

    issues = check_overlay_scenes_within_bounds(scene_plan)

    assert len(issues) == 1
    assert issues[0]["sceneId"] == "e"


def test_check_rendered_duration_skips_when_no_render_exists(tmp_path):
    scene_plan = {"fps": 30, "scenes": []}

    assert check_rendered_duration(tmp_path, scene_plan) == []


def test_check_rendered_duration_flags_mismatch(tmp_path):
    episode = tmp_path / "My Episode"
    rendered_dir = episode / "rendered"
    rendered_dir.mkdir(parents=True)
    (rendered_dir / "My Episode.mp4").write_bytes(b"fake")

    scene_plan = {
        "fps": 30,
        "scenes": [
            {"type": "presenter", "timelineStartFrame": 0, "durationInFrames": 300},
        ],
    }

    with patch("qa_check.get_video_duration_seconds", return_value=5.0):
        issues = check_rendered_duration(episode, scene_plan)

    assert len(issues) == 1
    assert issues[0]["check"] == "duration_mismatch"


def test_check_rendered_duration_passes_within_tolerance(tmp_path):
    episode = tmp_path / "My Episode"
    rendered_dir = episode / "rendered"
    rendered_dir.mkdir(parents=True)
    (rendered_dir / "My Episode.mp4").write_bytes(b"fake")

    scene_plan = {
        "fps": 30,
        "scenes": [
            {"type": "presenter", "timelineStartFrame": 0, "durationInFrames": 300},
        ],
    }

    with patch("qa_check.get_video_duration_seconds", return_value=10.2):
        issues = check_rendered_duration(episode, scene_plan)

    assert issues == []


def test_check_audio_video_duration_parity_skips_when_no_render_exists(tmp_path):
    assert check_audio_video_duration_parity(tmp_path) == []


def _make_rendered_file(tmp_path, name="My Episode"):
    episode = tmp_path / name
    rendered_dir = episode / "rendered"
    rendered_dir.mkdir(parents=True)
    (rendered_dir / f"{name}.mp4").write_bytes(b"fake")
    return episode


def test_check_audio_video_duration_parity_passes_when_streams_agree(tmp_path):
    episode = _make_rendered_file(tmp_path)

    with patch(
        "qa_check.get_stream_durations_seconds",
        return_value={"video": 100.0, "audio": 100.2},
    ):
        issues = check_audio_video_duration_parity(episode)

    assert issues == []


def test_check_audio_video_duration_parity_flags_drift(tmp_path):
    episode = _make_rendered_file(tmp_path)

    with patch(
        "qa_check.get_stream_durations_seconds",
        return_value={"video": 100.0, "audio": 40.0},
    ):
        issues = check_audio_video_duration_parity(episode)

    assert len(issues) == 1
    assert issues[0]["check"] == "audio_video_duration_mismatch"


def test_check_audio_video_duration_parity_flags_missing_audio_stream(tmp_path):
    episode = _make_rendered_file(tmp_path)

    with patch(
        "qa_check.get_stream_durations_seconds",
        return_value={"video": 100.0},
    ):
        issues = check_audio_video_duration_parity(episode)

    assert len(issues) == 1
    assert issues[0]["check"] == "missing_audio_stream"


def test_check_audio_video_duration_parity_skips_when_video_stream_unreadable(tmp_path):
    episode = _make_rendered_file(tmp_path)

    with patch("qa_check.get_stream_durations_seconds", return_value={}):
        issues = check_audio_video_duration_parity(episode)

    assert issues == []


def test_check_black_frames_skips_when_no_render_exists(tmp_path):
    assert check_black_frames(tmp_path) == []


def test_check_black_frames_flags_detected_segment(tmp_path):
    episode = _make_rendered_file(tmp_path)

    fake_result = type(
        "FakeResult",
        (),
        {"stderr": "black_start:10.5 black_end:13.2 black_duration:2.7"},
    )()

    with patch("qa_check.subprocess.run", return_value=fake_result):
        issues = check_black_frames(episode)

    assert len(issues) == 1
    assert issues[0]["check"] == "black_frames"
    assert "10.50s" in issues[0]["detail"]


def test_check_black_frames_passes_when_none_detected(tmp_path):
    episode = _make_rendered_file(tmp_path)

    fake_result = type("FakeResult", (), {"stderr": ""})()

    with patch("qa_check.subprocess.run", return_value=fake_result):
        issues = check_black_frames(episode)

    assert issues == []


def test_check_black_frames_flags_multiple_segments(tmp_path):
    episode = _make_rendered_file(tmp_path)

    fake_result = type(
        "FakeResult",
        (),
        {
            "stderr": (
                "black_start:1.0 black_end:2.0 black_duration:1.0\n"
                "black_start:50.0 black_end:52.0 black_duration:2.0"
            )
        },
    )()

    with patch("qa_check.subprocess.run", return_value=fake_result):
        issues = check_black_frames(episode)

    assert len(issues) == 2


def test_check_silent_audio_skips_when_no_render_exists(tmp_path):
    assert check_silent_audio(tmp_path) == []


def test_check_silent_audio_flags_effectively_silent_track(tmp_path):
    episode = _make_rendered_file(tmp_path)

    fake_result = type(
        "FakeResult",
        (),
        {"stderr": "[Parsed_volumedetect_0] mean_volume: -91.0 dB"},
    )()

    with patch("qa_check.subprocess.run", return_value=fake_result):
        issues = check_silent_audio(episode)

    assert len(issues) == 1
    assert issues[0]["check"] == "silent_audio"


def test_check_silent_audio_passes_for_normal_speech_levels(tmp_path):
    episode = _make_rendered_file(tmp_path)

    fake_result = type(
        "FakeResult",
        (),
        {"stderr": "[Parsed_volumedetect_0] mean_volume: -35.0 dB"},
    )()

    with patch("qa_check.subprocess.run", return_value=fake_result):
        issues = check_silent_audio(episode)

    assert issues == []
