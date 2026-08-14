from unittest.mock import patch

from qa_check import (
    check_missing_media,
    check_moment_presenter_side_agreement,
    check_moment_windows_do_not_overlap,
    check_overlay_scenes_within_bounds,
    check_rendered_duration,
    check_scene_plan_asset_ids,
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
