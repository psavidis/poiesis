from generate_title_scenes import (
    format_transcript_for_prompt,
    indexed_segments,
    merge_title_scenes,
    propose_title_scenes,
    TITLE_DURATION_FRAMES,
)


def _manifest_two_videos():
    return {
        "videos": [
            {"id": "001", "filename": "a.mp4"},
            {"id": "002", "filename": "b.mp4"},
        ]
    }


def test_indexed_segments_assigns_stable_ids_in_transcript_order():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "hello"},
            {"source": "a.mp4", "start": 2.0, "end": 4.0, "text": "world"},
            {"source": "b.mp4", "start": 0.0, "end": 3.0, "text": "second clip"},
        ]
    }

    segments = indexed_segments(transcript, _manifest_two_videos())

    assert [s["segmentId"] for s in segments] == ["s0", "s1", "s2"]
    assert segments[0]["videoId"] == "001"
    assert segments[2]["videoId"] == "002"


def test_indexed_segments_skips_unknown_source_but_keeps_index_stable():
    # regression: a segmentId always means "the Nth segment in the
    # transcript" — skipping an unrecognized clip must not renumber
    # segments that come after it
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 1.0, "text": "known"},
            {"source": "unknown.mp4", "start": 1.0, "end": 2.0, "text": "orphaned"},
            {"source": "a.mp4", "start": 2.0, "end": 3.0, "text": "also known"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    segments = indexed_segments(transcript, manifest)

    assert [s["segmentId"] for s in segments] == ["s0", "s2"]


def test_format_transcript_for_prompt_includes_every_segment_with_its_id():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "hello there"},
            {"source": "a.mp4", "start": 2.0, "end": 4.0, "text": "world"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    formatted = format_transcript_for_prompt(transcript, manifest)

    assert "[s0] hello there" in formatted
    assert "[s1] world" in formatted


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response

    def complete_json(self, prompt, thinking=True):
        return self.response


def test_propose_title_scenes_filters_invalid_segment_ids():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "hello"},
            {"source": "b.mp4", "start": 0.0, "end": 2.0, "text": "world"},
        ]
    }

    llm = _FakeLLMClient(
        {
            "titles": [
                {"segmentId": "s0", "text": "Valid Title"},
                {"segmentId": "s99", "text": "Unknown Segment"},
                {"segmentId": "s1", "text": ""},
            ]
        }
    )

    titles = propose_title_scenes(transcript, _manifest_two_videos(), llm, "{segments}")

    assert titles == [{"segmentId": "s0", "text": "Valid Title"}]


def test_propose_title_scenes_drops_titles_closer_together_than_min_spacing():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 5.0, "text": "first"},
            {"source": "a.mp4", "start": 5.0, "end": 10.0, "text": "second, right after"},
            {"source": "a.mp4", "start": 60.0, "end": 65.0, "text": "third, much later"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    llm = _FakeLLMClient(
        {
            "titles": [
                {"segmentId": "s0", "text": "First Topic"},
                # s1 starts only 5s after s0 — well under MIN_TITLE_SPACING_SECONDS
                {"segmentId": "s1", "text": "Too Close"},
                {"segmentId": "s2", "text": "Third Topic"},
            ]
        }
    )

    titles = propose_title_scenes(transcript, manifest, llm, "{segments}")

    assert titles == [
        {"segmentId": "s0", "text": "First Topic"},
        {"segmentId": "s2", "text": "Third Topic"},
    ]


def test_propose_title_scenes_never_filters_titles_in_different_clips_by_spacing():
    # Regression: transcript segment "start" is clip-relative (resets to
    # 0 at the start of each source clip, confirmed against real episode
    # data) — comparing raw start values across DIFFERENT clips produced
    # nonsensical (often deeply negative) "gaps" and incorrectly dropped
    # almost every real title on a real episode (found 9 genuine chapters
    # in the raw LLM response, kept only 1 after this filter, before the
    # fix). Two titles in different clips must never be filtered by
    # spacing, regardless of their raw start values.
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 5.0, "text": "end of clip a"},
            # clip b's own timestamps reset to near 0 — nothing like a's
            # "60.0" that a real multi-minute clip would have
            {"source": "b.mp4", "start": 0.5, "end": 5.0, "text": "start of clip b"},
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
                {"segmentId": "s0", "text": "First Topic"},
                {"segmentId": "s1", "text": "Second Topic"},
            ]
        }
    )

    titles = propose_title_scenes(transcript, manifest, llm, "{segments}")

    assert titles == [
        {"segmentId": "s0", "text": "First Topic"},
        {"segmentId": "s1", "text": "Second Topic"},
    ]


def _scene_plan_two_clips():
    return {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 300,
                "durationInFrames": 300,
                "effects": {"captions": True, "transition": "none"},
            },
            {
                "id": "scene-002",
                "type": "presenter",
                "videoId": "002",
                "sourceStartFrame": 0,
                "sourceEndFrame": 600,
                "durationInFrames": 600,
                "effects": {"captions": True, "transition": "none"},
            },
        ],
    }


def test_merge_title_scenes_inserts_before_clip_start():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "first clip"},
            {"source": "b.mp4", "start": 0.0, "end": 2.0, "text": "second clip"},
        ]
    }

    titles = [{"segmentId": "s1", "text": "Second Topic"}]

    result = merge_title_scenes(_scene_plan_two_clips(), titles, transcript, _manifest_two_videos())
    scenes = result["scenes"]

    assert [s["id"] for s in scenes] == ["scene-001", "scene-title-002", "scene-002"]

    title_scene = scenes[1]
    assert title_scene["text"] == "Second Topic"
    assert title_scene["timelineStartFrame"] == 300
    assert title_scene["durationInFrames"] == TITLE_DURATION_FRAMES

    assert scenes[2]["timelineStartFrame"] == 300 + TITLE_DURATION_FRAMES


def test_merge_title_scenes_splits_presenter_scene_mid_clip():
    # the real bug this fixes: a title whose segment starts partway
    # through a clip (not at the clip's own start) must split the
    # presenter scene there, not silently fail to place it
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "intro talk"},
            # starts at 5.0s = frame 150 (fps 30), partway through
            # scene-001's 0..300 frame range
            {"source": "a.mp4", "start": 5.0, "end": 8.0, "text": "new topic begins here"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 300,
                "durationInFrames": 300,
                "effects": {"captions": True, "transition": "none"},
            },
        ],
    }

    titles = [{"segmentId": "s1", "text": "New Topic"}]

    result = merge_title_scenes(scene_plan, titles, transcript, manifest)
    scenes = result["scenes"]

    presenter_scenes = [s for s in scenes if s["type"] == "presenter"]
    title_scenes = [s for s in scenes if s["type"] == "title"]

    assert len(presenter_scenes) == 2
    assert len(title_scenes) == 1

    first, second = presenter_scenes
    assert first["sourceStartFrame"] == 0
    assert first["sourceEndFrame"] == 150
    assert first["durationInFrames"] == 150
    assert first["timelineStartFrame"] == 0

    assert title_scenes[0]["text"] == "New Topic"
    assert title_scenes[0]["timelineStartFrame"] == 150

    assert second["sourceStartFrame"] == 150
    assert second["sourceEndFrame"] == 300
    assert second["durationInFrames"] == 150
    assert second["timelineStartFrame"] == 150 + TITLE_DURATION_FRAMES

    # both pieces still play the same source clip
    assert first["videoId"] == "001"
    assert second["videoId"] == "001"


def test_merge_title_scenes_no_titles_leaves_plan_unchanged():
    transcript = {"segments": [{"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "hello"}]}
    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 100,
                "durationInFrames": 100,
                "effects": {"captions": True, "transition": "none"},
            }
        ],
    }

    result = merge_title_scenes(scene_plan, [], transcript, manifest)

    assert [s["id"] for s in result["scenes"]] == ["scene-001"]
    assert result["scenes"][0]["timelineStartFrame"] == 0


def test_merge_title_scenes_tolerates_scenes_without_video_id():
    # regression: non-presenter scenes (moment, caption) already merged
    # into the plan don't have a videoId and shouldn't crash a re-run
    transcript = {"segments": [{"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "hello"}]}
    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 100,
                "durationInFrames": 100,
                "effects": {"captions": True, "transition": "none"},
            },
            {
                "id": "scene-moment-0",
                "type": "moment",
                "treatment": "bottom-callout",
                "text": "already there",
                "parentSceneId": "scene-001",
                "offsetInParentFrames": 10,
                "durationInFrames": 90,
            },
        ],
    }

    result = merge_title_scenes(scene_plan, [], transcript, manifest)

    moment_scenes = [s for s in result["scenes"] if s["type"] == "moment"]
    assert len(moment_scenes) == 1
    assert moment_scenes[0]["id"] == "scene-moment-0"


def test_merge_title_scenes_multiple_titles_across_different_clips():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "first"},
            {"source": "b.mp4", "start": 0.0, "end": 2.0, "text": "second"},
        ]
    }

    titles = [
        {"segmentId": "s0", "text": "First"},
        {"segmentId": "s1", "text": "Second"},
    ]

    result = merge_title_scenes(_scene_plan_two_clips(), titles, transcript, _manifest_two_videos())
    ids = [s["id"] for s in result["scenes"]]

    assert ids == ["scene-title-001", "scene-001", "scene-title-002", "scene-002"]

    by_id = {s["id"]: s for s in result["scenes"]}
    assert by_id["scene-title-001"]["timelineStartFrame"] == 0
    assert by_id["scene-001"]["timelineStartFrame"] == TITLE_DURATION_FRAMES
    assert by_id["scene-title-002"]["timelineStartFrame"] == TITLE_DURATION_FRAMES + 300
    assert by_id["scene-002"]["timelineStartFrame"] == 2 * TITLE_DURATION_FRAMES + 300


def test_merge_title_scenes_is_idempotent_on_rerun():
    # regression: re-merging against an already-split plan should not
    # produce duplicate title scenes, duplicate presenter scene ids, or
    # compound a previous run's split
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "intro"},
            {"source": "a.mp4", "start": 5.0, "end": 7.0, "text": "new topic"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 300,
                "durationInFrames": 300,
                "effects": {"captions": True, "transition": "none"},
            },
        ],
    }

    titles = [{"segmentId": "s1", "text": "New Topic"}]

    once = merge_title_scenes(scene_plan, titles, transcript, manifest)
    twice = merge_title_scenes(once, titles, transcript, manifest)

    title_scenes = [s for s in twice["scenes"] if s["type"] == "title"]
    presenter_scenes = [s for s in twice["scenes"] if s["type"] == "presenter"]

    assert len(title_scenes) == 1
    assert len(presenter_scenes) == 2

    ids = [s["id"] for s in twice["scenes"]]
    assert len(ids) == len(set(ids))

    # positions match the first run exactly — no compounding
    assert twice["scenes"] == once["scenes"]


def test_merge_title_scenes_snaps_segment_landing_at_clip_start_to_no_split():
    # a title whose segment happens to start at frame 0 of its clip is
    # equivalent to the old "title before the whole clip" behavior — no
    # split needed, just insert before.
    transcript = {"segments": [{"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "intro"}]}
    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 100,
                "durationInFrames": 100,
                "effects": {"captions": True, "transition": "none"},
            },
        ],
    }

    titles = [{"segmentId": "s0", "text": "Intro"}]

    result = merge_title_scenes(scene_plan, titles, transcript, manifest)
    scenes = result["scenes"]

    presenter_scenes = [s for s in scenes if s["type"] == "presenter"]
    assert len(presenter_scenes) == 1
    assert presenter_scenes[0]["sourceStartFrame"] == 0
    assert presenter_scenes[0]["sourceEndFrame"] == 100


def test_merge_title_scenes_keeps_overlay_scenes_aligned_when_parent_splits():
    # regression: moment/caption overlays are anchored to a parent scene
    # via parentSceneId + offsetInParentFrames. When a mid-clip split
    # changes which presenter scene id spans a given moment's offset, the
    # overlay's own fields must stay untouched — it's still positioned
    # relative to whichever presenter scene id it names, and this test
    # only exercises a split that happens AFTER the moment's own offset,
    # so the moment's original parent id remains valid.
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "intro"},
            {"source": "a.mp4", "start": 8.0, "end": 9.0, "text": "new topic"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 300,  # 10s
                "durationInFrames": 300,
                "effects": {"captions": True, "transition": "none"},
            },
            {
                "id": "scene-moment-0",
                "type": "moment",
                "treatment": "bottom-callout",
                "text": "key phrase",
                "parentSceneId": "scene-001",
                "offsetInParentFrames": 10,
                "durationInFrames": 90,
            },
        ],
    }

    titles = [{"segmentId": "s1", "text": "New Topic"}]  # frame 240, after the moment's own offset

    result = merge_title_scenes(scene_plan, titles, transcript, manifest)

    moment_scene = next(s for s in result["scenes"] if s["type"] == "moment")

    assert moment_scene["parentSceneId"] == "scene-001"
    assert moment_scene["offsetInParentFrames"] == 10
