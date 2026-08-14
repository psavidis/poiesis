from generate_captions import (
    MAX_CAPTION_DURATION_FRAMES,
    captions_for_presenter_scene,
    merge_caption_scenes,
)


def _presenter_scene(source_start, source_end, timeline_start=0, scene_id="scene-001"):
    return {
        "id": scene_id,
        "type": "presenter",
        "videoId": "001",
        "sourceStartFrame": source_start,
        "sourceEndFrame": source_end,
        "timelineStartFrame": timeline_start,
        "durationInFrames": source_end - source_start,
        "effects": {"captions": True, "transition": "none"},
    }


def test_captions_for_presenter_scene_positions_relative_to_scene_start():
    scene = _presenter_scene(source_start=30, source_end=300)

    transcript = {
        "segments": [
            {"start": 1.0, "end": 3.0, "text": "hello there"},
        ]
    }

    captions = captions_for_presenter_scene(scene, transcript, fps=30)

    assert len(captions) == 1
    # segment frames: 30 -> 90. scene starts at source frame 30, so offset is 0.
    assert captions[0]["offsetInParentFrames"] == 0
    assert captions[0]["durationInFrames"] == 60
    assert captions[0]["text"] == "hello there"
    assert captions[0]["parentSceneId"] == "scene-001"


def test_captions_for_presenter_scene_drops_segments_fully_trimmed_away():
    scene = _presenter_scene(source_start=100, source_end=300)

    transcript = {
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "trimmed silence at the start"},
        ]
    }

    captions = captions_for_presenter_scene(scene, transcript, fps=30)

    assert captions == []


def test_captions_for_presenter_scene_clips_segment_straddling_trim_boundary():
    scene = _presenter_scene(source_start=60, source_end=300)  # trim starts at frame 60 (2s)

    transcript = {
        "segments": [
            # frames 30 -> 120, straddles the source_start=60 boundary
            {"start": 1.0, "end": 4.0, "text": "straddles the cut"},
        ]
    }

    captions = captions_for_presenter_scene(scene, transcript, fps=30)

    assert len(captions) == 1
    # clipped_start = max(30, 60) = 60 -> offset 0
    assert captions[0]["offsetInParentFrames"] == 0
    # clipped_end = min(120, 300) = 120 -> duration 60
    assert captions[0]["durationInFrames"] == 60


def test_captions_for_presenter_scene_caps_unusually_long_segments():
    scene = _presenter_scene(source_start=0, source_end=10000)

    transcript = {
        "segments": [
            {"start": 0.0, "end": 30.0, "text": "a very long uninterrupted segment"},
        ]
    }

    captions = captions_for_presenter_scene(scene, transcript, fps=30)

    assert len(captions) == 1
    assert captions[0]["durationInFrames"] == MAX_CAPTION_DURATION_FRAMES


def test_captions_for_presenter_scene_skips_blank_text():
    scene = _presenter_scene(source_start=0, source_end=300)

    transcript = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "   "},
        ]
    }

    captions = captions_for_presenter_scene(scene, transcript, fps=30)

    assert captions == []


def test_captions_for_presenter_scene_handles_missing_transcript():
    scene = _presenter_scene(source_start=0, source_end=300)

    assert captions_for_presenter_scene(scene, None, fps=30) == []


def test_merge_caption_scenes_inserts_positioned_relative_to_parent_timeline():
    scene_plan = {
        "fps": 30,
        "scenes": [
            _presenter_scene(source_start=0, source_end=300, timeline_start=0),
        ],
    }

    proposals = [
        {
            "parentSceneId": "scene-001",
            "offsetInParentFrames": 30,
            "durationInFrames": 60,
            "text": "hello there",
        }
    ]

    merged = merge_caption_scenes(scene_plan, proposals)

    caption_scenes = [s for s in merged["scenes"] if s["type"] == "caption"]

    assert len(caption_scenes) == 1
    assert caption_scenes[0]["parentSceneId"] == "scene-001"
    assert caption_scenes[0]["offsetInParentFrames"] == 30
    assert caption_scenes[0]["durationInFrames"] == 60
    assert caption_scenes[0]["text"] == "hello there"


def test_merge_caption_scenes_is_idempotent_on_rerun():
    scene_plan = {
        "fps": 30,
        "scenes": [
            _presenter_scene(source_start=0, source_end=300, timeline_start=0),
        ],
    }

    proposals = [
        {
            "parentSceneId": "scene-001",
            "offsetInParentFrames": 10,
            "durationInFrames": 20,
            "text": "one",
        }
    ]

    once = merge_caption_scenes(scene_plan, proposals)
    twice = merge_caption_scenes(once, proposals)

    caption_scenes = [s for s in twice["scenes"] if s["type"] == "caption"]
    assert len(caption_scenes) == 1


def test_merge_caption_scenes_skips_proposal_with_missing_parent():
    scene_plan = {
        "fps": 30,
        "scenes": [
            _presenter_scene(source_start=0, source_end=300, timeline_start=0),
        ],
    }

    proposals = [
        {
            "parentSceneId": "scene-does-not-exist",
            "offsetInParentFrames": 0,
            "durationInFrames": 10,
            "text": "orphaned",
        }
    ]

    merged = merge_caption_scenes(scene_plan, proposals)

    assert [s for s in merged["scenes"] if s["type"] == "caption"] == []
