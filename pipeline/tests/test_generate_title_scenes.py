from generate_title_scenes import (
    group_transcript_by_clip,
    merge_title_scenes,
    propose_title_scenes,
    TITLE_DURATION_FRAMES,
)


def test_group_transcript_by_clip_maps_source_filename_to_video_id():
    transcript = {
        "segments": [
            {"source": "a.mp4", "text": "hello"},
            {"source": "a.mp4", "text": "world"},
            {"source": "b.mp4", "text": "second clip"},
        ]
    }

    manifest = {
        "videos": [
            {"id": "001", "filename": "a.mp4"},
            {"id": "002", "filename": "b.mp4"},
        ]
    }

    clips = group_transcript_by_clip(transcript, manifest)

    assert clips == {
        "001": ["hello", "world"],
        "002": ["second clip"],
    }


def test_group_transcript_by_clip_skips_unknown_source():
    transcript = {"segments": [{"source": "unknown.mp4", "text": "orphaned"}]}
    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    assert group_transcript_by_clip(transcript, manifest) == {}


def test_merge_title_scenes_inserts_before_anchor_and_shifts_later_scenes():
    scene_plan = {
        "version": 1,
        "episode": "ep",
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 100,
            },
            {
                "id": "scene-002",
                "type": "presenter",
                "videoId": "002",
                "timelineStartFrame": 100,
                "durationInFrames": 200,
            },
        ],
    }

    titles = [{"videoId": "002", "text": "Second Topic"}]

    result = merge_title_scenes(scene_plan, titles)

    scenes = result["scenes"]
    assert len(scenes) == 3

    assert scenes[0]["id"] == "scene-001"
    assert scenes[0]["timelineStartFrame"] == 0

    assert scenes[1]["type"] == "title"
    assert scenes[1]["text"] == "Second Topic"
    assert scenes[1]["timelineStartFrame"] == 100
    assert scenes[1]["durationInFrames"] == TITLE_DURATION_FRAMES

    assert scenes[2]["id"] == "scene-002"
    assert scenes[2]["timelineStartFrame"] == 100 + TITLE_DURATION_FRAMES


def test_merge_title_scenes_no_titles_leaves_plan_unchanged():
    scene_plan = {
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 100,
            }
        ]
    }

    result = merge_title_scenes(scene_plan, [])

    assert result["scenes"] == scene_plan["scenes"]


def test_merge_title_scenes_tolerates_scenes_without_video_id():
    # regression: non-presenter scenes (title, emphasis) already merged into
    # the plan don't have a videoId and shouldn't crash a re-run
    scene_plan = {
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 100,
            },
            {
                "id": "scene-emphasis-0",
                "type": "emphasis",
                "text": "already there",
                "timelineStartFrame": 100,
                "durationInFrames": 90,
            },
        ]
    }

    result = merge_title_scenes(scene_plan, [])

    assert result["scenes"] == scene_plan["scenes"]


def test_merge_title_scenes_multiple_titles_shift_cumulatively():
    scene_plan = {
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 50,
            },
            {
                "id": "scene-002",
                "type": "presenter",
                "videoId": "002",
                "timelineStartFrame": 50,
                "durationInFrames": 50,
            },
            {
                "id": "scene-003",
                "type": "presenter",
                "videoId": "003",
                "timelineStartFrame": 100,
                "durationInFrames": 50,
            },
        ]
    }

    titles = [
        {"videoId": "001", "text": "First"},
        {"videoId": "003", "text": "Third"},
    ]

    result = merge_title_scenes(scene_plan, titles)
    scenes = result["scenes"]

    ids = [s["id"] for s in scenes]
    assert ids == [
        "scene-title-001",
        "scene-001",
        "scene-002",
        "scene-title-003",
        "scene-003",
    ]

    by_id = {s["id"]: s for s in scenes}
    assert by_id["scene-title-001"]["timelineStartFrame"] == 0
    assert by_id["scene-001"]["timelineStartFrame"] == TITLE_DURATION_FRAMES
    assert by_id["scene-002"]["timelineStartFrame"] == TITLE_DURATION_FRAMES + 50
    assert (
        by_id["scene-title-003"]["timelineStartFrame"]
        == TITLE_DURATION_FRAMES + 100
    )
    assert (
        by_id["scene-003"]["timelineStartFrame"]
        == 2 * TITLE_DURATION_FRAMES + 100
    )


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response

    def complete_json(self, prompt, thinking=True):
        return self.response


def test_propose_title_scenes_filters_invalid_video_ids():
    transcript = {
        "segments": [
            {"source": "a.mp4", "text": "hello"},
            {"source": "b.mp4", "text": "world"},
        ]
    }

    manifest = {
        "videos": [
            {"id": "001", "filename": "a.mp4"},
            {"id": "002", "filename": "b.mp4"},
        ]
    }

    llm = _FakeLLMClient(
        {
            "titles": [
                {"videoId": "001", "text": "Valid Title"},
                {"videoId": "999", "text": "Unknown Clip"},
                {"videoId": "002", "text": ""},
            ]
        }
    )

    titles = propose_title_scenes(transcript, manifest, llm, "{clips}")

    assert titles == [{"videoId": "001", "text": "Valid Title"}]


def test_merge_title_scenes_is_idempotent_on_rerun():
    # regression: re-merging against an already-merged plan should not
    # produce duplicate title scenes or duplicate scene ids
    scene_plan = {
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 100,
            },
        ],
    }

    titles = [{"videoId": "001", "text": "First Title"}]

    once = merge_title_scenes(scene_plan, titles)
    twice = merge_title_scenes(once, titles)

    title_scenes = [s for s in twice["scenes"] if s["type"] == "title"]
    assert len(title_scenes) == 1

    ids = [s["id"] for s in twice["scenes"]]
    assert len(ids) == len(set(ids))


def test_merge_title_scenes_keeps_overlay_scenes_aligned_when_parent_moves():
    # regression: emphasis/image overlays are anchored to a parent scene via
    # parentSceneId + offsetInParentFrames. When a title gets added and
    # shifts the parent presenter scene's timelineStartFrame, the overlay
    # must NOT need repositioning — its absolute position is derived from
    # wherever the parent currently is, not stored independently.
    scene_plan = {
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 100,
            },
            {
                "id": "scene-002",
                "type": "presenter",
                "videoId": "002",
                "timelineStartFrame": 100,
                "durationInFrames": 200,
            },
            {
                "id": "scene-emphasis-0",
                "type": "emphasis",
                "text": "key phrase",
                "parentSceneId": "scene-002",
                "offsetInParentFrames": 50,
                "durationInFrames": 90,
            },
        ],
    }

    # adding a title before scene-002 pushes scene-002 forward by TITLE_DURATION_FRAMES
    titles = [{"videoId": "002", "text": "New Section"}]

    result = merge_title_scenes(scene_plan, titles)

    scene_002 = next(s for s in result["scenes"] if s["id"] == "scene-002")
    emphasis_scene = next(s for s in result["scenes"] if s["id"] == "scene-emphasis-0")

    assert scene_002["timelineStartFrame"] == 100 + TITLE_DURATION_FRAMES

    # the overlay's own fields are untouched — it still resolves correctly
    # via parentSceneId + offsetInParentFrames against scene_002's new position
    assert emphasis_scene["parentSceneId"] == "scene-002"
    assert emphasis_scene["offsetInParentFrames"] == 50
