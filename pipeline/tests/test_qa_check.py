from unittest.mock import patch

from qa_check import (
    check_missing_media,
    check_rendered_duration,
    check_scene_plan_video_ids,
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


def test_check_timeline_continuity_passes_for_contiguous_scenes():
    scene_plan = {
        "scenes": [
            {"id": "a", "timelineStartFrame": 0, "durationInFrames": 100},
            {"id": "b", "timelineStartFrame": 100, "durationInFrames": 50},
        ]
    }

    assert check_timeline_continuity(scene_plan) == []


def test_check_timeline_continuity_flags_gap():
    scene_plan = {
        "scenes": [
            {"id": "a", "timelineStartFrame": 0, "durationInFrames": 100},
            {"id": "b", "timelineStartFrame": 150, "durationInFrames": 50},
        ]
    }

    issues = check_timeline_continuity(scene_plan)

    assert len(issues) == 1
    assert issues[0]["check"] == "timeline_gap_or_overlap"
    assert issues[0]["sceneId"] == "b"


def test_check_timeline_continuity_flags_overlap():
    scene_plan = {
        "scenes": [
            {"id": "a", "timelineStartFrame": 0, "durationInFrames": 100},
            {"id": "b", "timelineStartFrame": 80, "durationInFrames": 50},
        ]
    }

    issues = check_timeline_continuity(scene_plan)

    assert len(issues) == 1
    assert issues[0]["sceneId"] == "b"


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
            {"timelineStartFrame": 0, "durationInFrames": 300},
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
            {"timelineStartFrame": 0, "durationInFrames": 300},
        ],
    }

    with patch("qa_check.get_video_duration_seconds", return_value=10.2):
        issues = check_rendered_duration(episode, scene_plan)

    assert issues == []
