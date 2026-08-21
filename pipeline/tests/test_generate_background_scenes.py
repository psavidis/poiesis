from generate_background_scenes import merge_background_scenes


def _manifest_one_video():
    return {"videos": [{"id": "001", "filename": "a.mp4"}]}


def _transcript_two_segments():
    return {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "intro talk"},
            {"source": "a.mp4", "start": 5.0, "end": 8.0, "text": "new topic begins here"},
        ]
    }


def _scene_plan_one_clip(duration=300):
    return {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": duration,
                "durationInFrames": duration,
                "timelineStartFrame": 0,
                "effects": {"captions": True, "transition": "none"},
            },
        ],
    }


def test_merge_background_scenes_carries_image_motion_speed_through():
    scene_plan = _scene_plan_one_clip()
    entries = [{"segmentId": "s0", "backgroundId": "bg-001", "imageMotion": "zoom-in", "imageMotionSpeed": "strong"}]

    result = merge_background_scenes(scene_plan, entries, _transcript_two_segments(), _manifest_one_video())

    backgrounds = [s for s in result["scenes"] if s["type"] == "background"]

    assert backgrounds[0]["imageMotionSpeed"] == "strong"


def test_merge_background_scenes_omits_image_motion_speed_when_absent():
    scene_plan = _scene_plan_one_clip()
    entries = [{"segmentId": "s0", "backgroundId": "bg-001", "imageMotion": "zoom-in"}]

    result = merge_background_scenes(scene_plan, entries, _transcript_two_segments(), _manifest_one_video())

    backgrounds = [s for s in result["scenes"] if s["type"] == "background"]

    assert "imageMotionSpeed" not in backgrounds[0]


def test_merge_background_scenes_carries_image_motion_through():
    scene_plan = _scene_plan_one_clip()
    entries = [{"segmentId": "s0", "backgroundId": "bg-001", "imageMotion": "palindrome"}]

    result = merge_background_scenes(scene_plan, entries, _transcript_two_segments(), _manifest_one_video())

    backgrounds = [s for s in result["scenes"] if s["type"] == "background"]

    assert backgrounds[0]["imageMotion"] == "palindrome"


def test_merge_background_scenes_omits_image_motion_when_absent():
    scene_plan = _scene_plan_one_clip()
    entries = [{"segmentId": "s0", "backgroundId": "bg-001"}]

    result = merge_background_scenes(scene_plan, entries, _transcript_two_segments(), _manifest_one_video())

    backgrounds = [s for s in result["scenes"] if s["type"] == "background"]

    assert "imageMotion" not in backgrounds[0]


def test_merge_background_scenes_resolves_segment_to_timeline_frame_and_extends_to_episode_end():
    scene_plan = _scene_plan_one_clip()
    entries = [{"segmentId": "s0", "backgroundId": "bg-001"}]

    result = merge_background_scenes(scene_plan, entries, _transcript_two_segments(), _manifest_one_video())

    backgrounds = [s for s in result["scenes"] if s["type"] == "background"]

    assert len(backgrounds) == 1
    assert backgrounds[0]["backgroundId"] == "bg-001"
    assert backgrounds[0]["timelineStartFrame"] == 0
    assert backgrounds[0]["durationInFrames"] == 300


def test_merge_background_scenes_auto_closes_earlier_entry_at_the_next_ones_start():
    scene_plan = _scene_plan_one_clip()
    entries = [
        {"segmentId": "s0", "backgroundId": "bg-001"},
        {"segmentId": "s1", "backgroundId": "bg-002"},
    ]

    result = merge_background_scenes(scene_plan, entries, _transcript_two_segments(), _manifest_one_video())

    backgrounds = sorted(
        (s for s in result["scenes"] if s["type"] == "background"),
        key=lambda s: s["timelineStartFrame"],
    )

    assert len(backgrounds) == 2
    assert backgrounds[0]["backgroundId"] == "bg-001"
    assert backgrounds[0]["timelineStartFrame"] == 0
    assert backgrounds[0]["durationInFrames"] == 150  # closed exactly where s1 starts

    assert backgrounds[1]["backgroundId"] == "bg-002"
    assert backgrounds[1]["timelineStartFrame"] == 150
    assert backgrounds[1]["durationInFrames"] == 150  # extends to episode end


def test_merge_background_scenes_sorts_entries_regardless_of_input_order():
    scene_plan = _scene_plan_one_clip()
    # Deliberately out of timeline order.
    entries = [
        {"segmentId": "s1", "backgroundId": "bg-002"},
        {"segmentId": "s0", "backgroundId": "bg-001"},
    ]

    result = merge_background_scenes(scene_plan, entries, _transcript_two_segments(), _manifest_one_video())

    backgrounds = sorted(
        (s for s in result["scenes"] if s["type"] == "background"),
        key=lambda s: s["timelineStartFrame"],
    )

    assert [b["backgroundId"] for b in backgrounds] == ["bg-001", "bg-002"]


def test_merge_background_scenes_drops_entry_with_unresolvable_segment():
    scene_plan = _scene_plan_one_clip()
    entries = [{"segmentId": "s99", "backgroundId": "bg-001"}]

    result = merge_background_scenes(scene_plan, entries, _transcript_two_segments(), _manifest_one_video())

    backgrounds = [s for s in result["scenes"] if s["type"] == "background"]

    assert backgrounds == []


def test_merge_background_scenes_ignores_scenes_without_absolute_timeline_frame():
    # regression: moment/image/caption/beat scenes have no timelineStartFrame
    # of their own (only parentSceneId/offsetInParentFrames) — computing
    # total_frames must skip them rather than raising a KeyError.
    scene_plan = _scene_plan_one_clip()
    scene_plan["scenes"].append({
        "type": "moment",
        "id": "scene-moment-0",
        "treatment": "bottom-callout",
        "text": "hello",
        "parentSceneId": "scene-001",
        "offsetInParentFrames": 10,
        "durationInFrames": 60,
    })

    entries = [{"segmentId": "s0", "backgroundId": "bg-001"}]

    result = merge_background_scenes(scene_plan, entries, _transcript_two_segments(), _manifest_one_video())

    backgrounds = [s for s in result["scenes"] if s["type"] == "background"]

    assert len(backgrounds) == 1
    assert backgrounds[0]["durationInFrames"] == 300  # not affected by the moment scene


def test_merge_background_scenes_with_no_entries_produces_no_background_scenes():
    scene_plan = _scene_plan_one_clip()

    result = merge_background_scenes(scene_plan, [], _transcript_two_segments(), _manifest_one_video())

    assert [s for s in result["scenes"] if s["type"] == "background"] == []
    # Non-background scenes pass through unchanged.
    assert result["scenes"] == scene_plan["scenes"]


def test_merge_background_scenes_replaces_any_previously_merged_background_scenes():
    # Re-running the merge (e.g. after editing background_scenes.json) must
    # not accumulate stale background scenes from a prior merge pass.
    scene_plan = _scene_plan_one_clip()
    scene_plan["scenes"].append({
        "type": "background",
        "id": "scene-background-0",
        "backgroundId": "stale-bg",
        "timelineStartFrame": 0,
        "durationInFrames": 300,
    })

    entries = [{"segmentId": "s0", "backgroundId": "bg-001"}]

    result = merge_background_scenes(scene_plan, entries, _transcript_two_segments(), _manifest_one_video())

    backgrounds = [s for s in result["scenes"] if s["type"] == "background"]

    assert len(backgrounds) == 1
    assert backgrounds[0]["backgroundId"] == "bg-001"
