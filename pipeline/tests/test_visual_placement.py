from visual_placement import (
    filter_segments_in_window,
    find_monotony_eligible_windows,
    source_frame_to_seconds,
)


def test_no_windows_when_scene_shorter_than_threshold():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 300,  # 10s, below 18s threshold
                "sourceStartFrame": 0,
                "sourceEndFrame": 300,
            }
        ],
    }

    assert find_monotony_eligible_windows(scene_plan) == []


def test_window_found_when_scene_exceeds_threshold():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,  # 30s, exceeds 18s threshold
                "sourceStartFrame": 0,
                "sourceEndFrame": 900,
            }
        ],
    }

    windows = find_monotony_eligible_windows(scene_plan)

    assert len(windows) == 1
    window = windows[0]
    assert window["sceneId"] == "scene-001"
    assert window["videoId"] == "001"
    # 18s * 30fps = 540 frames in, relative to the scene's own start
    assert window["offsetInParentFrames"] == 540
    assert window["maxDurationInParentFrames"] == 360
    assert window["sourceStartFrame"] == 540
    assert window["sourceEndFrame"] == 900


def test_title_scene_resets_monotony_counter():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 300,  # 10s
                "sourceStartFrame": 0,
                "sourceEndFrame": 300,
            },
            {
                "id": "scene-title-001",
                "type": "title",
                "timelineStartFrame": 300,
                "durationInFrames": 60,
            },
            {
                "id": "scene-002",
                "type": "presenter",
                "videoId": "002",
                "timelineStartFrame": 360,
                "durationInFrames": 300,  # another 10s, total would be 20s without reset
                "sourceStartFrame": 0,
                "sourceEndFrame": 300,
            },
        ],
    }

    # without reset, cumulative 10+10=20s would exceed 18s threshold on the second clip
    # with reset, second clip only accumulates its own 10s, below threshold
    assert find_monotony_eligible_windows(scene_plan) == []


def test_multiple_presenter_scenes_accumulate_across_boundary():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 300,  # 10s
                "sourceStartFrame": 0,
                "sourceEndFrame": 300,
            },
            {
                "id": "scene-002",
                "type": "presenter",
                "videoId": "002",
                "timelineStartFrame": 300,
                "durationInFrames": 300,  # another 10s, cumulative 20s > 18s threshold
                "sourceStartFrame": 0,
                "sourceEndFrame": 300,
            },
        ],
    }

    windows = find_monotony_eligible_windows(scene_plan)

    assert len(windows) == 1
    assert windows[0]["sceneId"] == "scene-002"
    assert windows[0]["videoId"] == "002"
    # threshold crossed 8s into the second scene (18s - 10s already accumulated)
    assert windows[0]["offsetInParentFrames"] == 240


def test_windows_never_have_end_before_start_across_many_long_scenes():
    # regression: a long scene that crosses the threshold should reset the
    # monotony counter, not keep compounding into later scenes and producing
    # a nonsensical window whose sourceStartFrame exceeds sourceEndFrame.
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 3000,  # 100s, well past threshold
                "sourceStartFrame": 0,
                "sourceEndFrame": 3000,
            },
            {
                "id": "scene-002",
                "type": "presenter",
                "videoId": "002",
                "timelineStartFrame": 3000,
                "durationInFrames": 500,
                "sourceStartFrame": 0,
                "sourceEndFrame": 500,
            },
            {
                "id": "scene-003",
                "type": "presenter",
                "videoId": "003",
                "timelineStartFrame": 3500,
                "durationInFrames": 500,
                "sourceStartFrame": 0,
                "sourceEndFrame": 500,
            },
        ],
    }

    windows = find_monotony_eligible_windows(scene_plan)

    for window in windows:
        assert window["sourceStartFrame"] <= window["sourceEndFrame"]
        assert window["offsetInParentFrames"] >= 0

    # only the first scene should have flagged (it alone exceeds threshold);
    # the counter resets after, and scenes 002/003 individually (10s+10s=20s
    # combined, but each below 18s alone) still combine and should flag once
    # more, not carry forward the huge original debt from scene 001
    assert len(windows) == 2
    assert windows[0]["sceneId"] == "scene-001"
    assert windows[1]["sceneId"] == "scene-003"


def test_source_frame_to_seconds():
    assert source_frame_to_seconds(150, 30) == 5.0


def test_filter_segments_in_window_selects_only_segments_in_range():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "before"},
        {"start": 20.0, "end": 22.0, "text": "inside"},
        {"start": 40.0, "end": 42.0, "text": "after"},
    ]

    window = {
        "sourceStartFrame": 540,  # 18s at 30fps
        "sourceEndFrame": 900,    # 30s at 30fps
    }

    result = filter_segments_in_window(segments, window, fps=30)

    assert result == [segments[1]]
