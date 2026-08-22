from episode_context import NO_CONTEXT_TEXT
from generate_title_scenes import (
    compute_overridden_fields,
    default_title_duration_frames,
    format_transcript_for_prompt,
    indexed_segments,
    merge_title_scenes,
    preserve_overridden_fields,
    propose_title_scenes,
    resolvable_segment_positions,
)

# "Second Topic" / "New Topic" / "First" / "Second" / "Intro" are the title
# texts every merge_title_scenes test below uses — all <= 3 words, so they
# share the same read-time-based default duration (#89). Computed once here
# rather than hardcoded so these tests don't silently drift from
# default_title_duration_frames's actual behavior.
TITLE_DURATION_FRAMES = default_title_duration_frames("Second Topic", fps=30)


def test_default_title_duration_frames_scales_with_word_count():
    # Mirrors the bucket boundaries from #89's algorithm (wordCount <= 3 ->
    # 2.5s, <= 6 -> 3.0s, <= 9 -> 3.5s, <= 12 -> 4.0s, else 5.0s).
    assert default_title_duration_frames("Introduction", fps=30) == 75  # 2.5s, 1 word
    assert default_title_duration_frames("Software Architecture", fps=30) == 75  # 2.5s, 2 words
    assert default_title_duration_frames(
        "Designing Software Through Greek Philosophy", fps=30
    ) == 90  # 3.0s, 5 words
    assert default_title_duration_frames(
        "Why Event Driven Architecture Changes Everything", fps=30
    ) == 90  # 3.0s, 6 words (<= 6 bucket)


def test_default_title_duration_frames_falls_back_for_very_long_titles():
    long_title = " ".join(["word"] * 13)

    assert default_title_duration_frames(long_title, fps=30) == 150  # 5.0s fallback


def test_default_title_duration_frames_scales_with_fps():
    assert default_title_duration_frames("Introduction", fps=60) == 150  # 2.5s at 60fps


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


def test_propose_title_scenes_substitutes_episode_context_into_prompt():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "welcome to the show"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    llm = _FakeLLMClient({"titles": []})

    propose_title_scenes(
        transcript,
        manifest,
        llm,
        "{segments}{episode_context}",
        episode_context="Topics covered, in order: Intro; Dependency injection",
    )

    assert "Topics covered, in order: Intro; Dependency injection" in llm.last_prompt
    assert "{episode_context}" not in llm.last_prompt


def test_propose_title_scenes_defaults_episode_context_when_omitted():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "welcome to the show"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    llm = _FakeLLMClient({"titles": []})

    propose_title_scenes(transcript, manifest, llm, "{segments}{episode_context}")

    assert "{episode_context}" not in llm.last_prompt
    assert NO_CONTEXT_TEXT in llm.last_prompt


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.last_prompt = None

    def complete_json(self, prompt, thinking=True):
        self.last_prompt = prompt
        return self.response


def test_propose_title_scenes_filters_invalid_segment_ids():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "hello"},
            {"source": "b.mp4", "start": 0.0, "end": 2.0, "text": "world"},
            {"source": "b.mp4", "start": 3.0, "end": 5.0, "text": "second real segment"},
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
                {"segmentId": "s1", "text": "Valid Title"},
                {"segmentId": "s99", "text": "Unknown Segment"},
                {"segmentId": "s2", "text": ""},
            ]
        }
    )

    titles = propose_title_scenes(transcript, manifest, llm, "{segments}")

    assert titles == [{"segmentId": "s1", "text": "Valid Title"}]


def test_propose_title_scenes_never_proposes_a_title_for_the_opening_segment():
    # Regression: the very start of the episode is always the presenter's
    # performed intro — no video should ever get an on-screen title card
    # at 00:00, regardless of what the LLM proposes for it.
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "welcome to the show"},
            {"source": "a.mp4", "start": 30.0, "end": 33.0, "text": "a real topic begins"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    llm = _FakeLLMClient(
        {
            "titles": [
                {"segmentId": "s0", "text": "Dependency Injection"},
                {"segmentId": "s1", "text": "A Real Topic"},
            ]
        }
    )

    titles = propose_title_scenes(transcript, manifest, llm, "{segments}")

    assert titles == [{"segmentId": "s1", "text": "A Real Topic"}]


def test_propose_title_scenes_drops_titles_closer_together_than_min_spacing():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 5.0, "text": "opening intro, never a title"},
            {"source": "a.mp4", "start": 5.0, "end": 10.0, "text": "first real topic"},
            {"source": "a.mp4", "start": 15.0, "end": 20.0, "text": "second, right after"},
            {"source": "a.mp4", "start": 70.0, "end": 75.0, "text": "third, much later"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    llm = _FakeLLMClient(
        {
            "titles": [
                {"segmentId": "s1", "text": "First Topic"},
                # s2 starts only 5s after s1 — well under MIN_TITLE_SPACING_SECONDS
                {"segmentId": "s2", "text": "Too Close"},
                {"segmentId": "s3", "text": "Third Topic"},
            ]
        }
    )

    titles = propose_title_scenes(transcript, manifest, llm, "{segments}")

    assert titles == [
        {"segmentId": "s1", "text": "First Topic"},
        {"segmentId": "s3", "text": "Third Topic"},
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
            {"source": "a.mp4", "start": 0.0, "end": 5.0, "text": "opening intro, never a title"},
            {"source": "a.mp4", "start": 30.0, "end": 35.0, "text": "end of clip a"},
            # clip b's own timestamps reset to near 0 — nothing like a's
            # "30.0" that a real multi-minute clip would have
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
                {"segmentId": "s1", "text": "First Topic"},
                {"segmentId": "s2", "text": "Second Topic"},
            ]
        }
    )

    titles = propose_title_scenes(transcript, manifest, llm, "{segments}")

    assert titles == [
        {"segmentId": "s1", "text": "First Topic"},
        {"segmentId": "s2", "text": "Second Topic"},
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


def test_merge_title_scenes_uses_per_title_duration_override_when_present():
    # #83 — a human-set duration override on ONE title shifts every LATER
    # scene's timelineStartFrame by the difference, same reflow the global
    # default already produces (see the previous test's assertion at the
    # global TITLE_DURATION_FRAMES value).
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "first clip"},
            {"source": "b.mp4", "start": 0.0, "end": 2.0, "text": "second clip"},
        ]
    }

    custom_duration = TITLE_DURATION_FRAMES + 45

    titles = [{"segmentId": "s1", "text": "Second Topic", "durationFrames": custom_duration}]

    result = merge_title_scenes(_scene_plan_two_clips(), titles, transcript, _manifest_two_videos())
    scenes = result["scenes"]

    title_scene = scenes[1]
    assert title_scene["durationInFrames"] == custom_duration
    assert scenes[2]["timelineStartFrame"] == 300 + custom_duration


def test_merge_title_scenes_falls_back_to_read_time_duration_when_override_absent():
    # A title with no per-title override (every title before #83's field
    # existed, or one that never had it set) uses the read-time-based
    # default (#89) instead of a fixed value.
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "first clip"},
            {"source": "b.mp4", "start": 0.0, "end": 2.0, "text": "second clip"},
        ]
    }

    titles = [{"segmentId": "s1", "text": "Second Topic"}]

    result = merge_title_scenes(_scene_plan_two_clips(), titles, transcript, _manifest_two_videos())
    scenes = result["scenes"]

    assert scenes[1]["durationInFrames"] == TITLE_DURATION_FRAMES


def test_merge_title_scenes_gives_longer_titles_more_duration_when_override_absent():
    # Regression for #89: a fixed durationFrames left long titles with no
    # more read time than short ones. A longer title (word count in a
    # higher bucket) must resolve to a longer default duration.
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "clip"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    long_title_text = "Why Event Driven Architecture Changes Everything"
    titles = [{"segmentId": "s0", "text": long_title_text}]

    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 60,
                "durationInFrames": 60,
                "effects": {"captions": True, "transition": "none"},
            },
        ],
    }

    result = merge_title_scenes(scene_plan, titles, transcript, manifest)
    title_scene = next(s for s in result["scenes"] if s["type"] == "title")

    assert title_scene["durationInFrames"] == default_title_duration_frames(long_title_text, fps=30)
    assert title_scene["durationInFrames"] > TITLE_DURATION_FRAMES


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


def test_merge_title_scenes_snaps_split_too_close_to_clip_start_to_no_leading_piece():
    # Regression: a real bug observed in rendered output — a split landing
    # a handful of frames (well under 1s) after a clip's true start
    # produced a near-zero-length presenter "piece" before the title.
    # Visually this looked like: presenter mid-expression flashes for a
    # fraction of a second, title appears, then the presenter's real
    # opening frame plays again — an inaccurate, jarring cut, not a clean
    # "presenter ends, title, next presenter begins." The fix snaps a
    # split that close to the boundary it's nearest to, so no sliver piece
    # is ever created.
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 0.5, "text": "barely anything"},
            # starts at frame 5 (30fps) — 5 frames after the clip's own
            # start, far under the 1s (30-frame) minimum piece length
            {"source": "a.mp4", "start": 0.1667, "end": 3.0, "text": "new topic begins almost immediately"},
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

    # no sliver leading piece — the title sits right before the whole clip
    assert len(presenter_scenes) == 1
    assert len(title_scenes) == 1
    assert scenes[0]["type"] == "title"
    assert scenes[0]["timelineStartFrame"] == 0
    assert presenter_scenes[0]["sourceStartFrame"] == 0
    assert presenter_scenes[0]["sourceEndFrame"] == 300


def test_merge_title_scenes_snaps_split_too_close_to_clip_end_to_no_trailing_piece():
    # Symmetric case: a split landing a handful of frames before a clip's
    # true end must not leave a sliver piece playing AFTER the title
    # before the clip ends.
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 9.0, "text": "most of the clip"},
            # starts at frame 295 (30fps) — 5 frames before the clip's own
            # end (frame 300), far under the 1s (30-frame) minimum
            {"source": "a.mp4", "start": 9.8333, "end": 10.0, "text": "barely anything at the very end"},
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

    # no sliver trailing piece — the title sits right after the whole clip
    assert len(presenter_scenes) == 1
    assert len(title_scenes) == 1
    assert scenes[-1]["type"] == "title"
    assert presenter_scenes[0]["sourceStartFrame"] == 0
    assert presenter_scenes[0]["sourceEndFrame"] == 300


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


# compute_overridden_fields / preserve_overridden_fields (#59) — AI-vs-
# human provenance tracking, third slice of #44 (mirrors #57/#58, but
# matched by segmentId — a title's real stable id — rather than array
# position or nearest-offset heuristics).
def test_resolvable_segment_positions_resolves_to_absolute_timeline_frames():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "intro talk"},
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
                "timelineStartFrame": 0,
                "effects": {"captions": True, "transition": "none"},
            },
        ],
    }

    positions = resolvable_segment_positions(scene_plan, transcript, manifest)

    assert positions == [
        {"segmentId": "s0", "timelineFrame": 0},
        {"segmentId": "s1", "timelineFrame": 150},
    ]


def test_resolvable_segment_positions_accounts_for_a_title_already_splitting_the_clip():
    # segment s1 (starting at source frame 150) now sits AFTER a title
    # card that was already inserted at that split — its absolute timeline
    # frame must include the title's own duration, not just the raw source
    # offset from the clip's original start.
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "intro talk"},
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
                "sourceEndFrame": 150,
                "durationInFrames": 150,
                "timelineStartFrame": 0,
                "effects": {"captions": True, "transition": "none"},
            },
            {
                "id": "scene-title-001",
                "type": "title",
                "text": "New Topic",
                "timelineStartFrame": 150,
                "durationInFrames": TITLE_DURATION_FRAMES,
            },
            {
                "id": "scene-001-1",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 150,
                "sourceEndFrame": 300,
                "durationInFrames": 150,
                "timelineStartFrame": 150 + TITLE_DURATION_FRAMES,
                "effects": {"captions": True, "transition": "none"},
            },
        ],
    }

    positions = resolvable_segment_positions(scene_plan, transcript, manifest)

    assert positions == [
        {"segmentId": "s0", "timelineFrame": 0},
        {"segmentId": "s1", "timelineFrame": 150 + TITLE_DURATION_FRAMES},
    ]


def test_resolvable_segment_positions_skips_segments_whose_clip_is_absent():
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 2.0, "text": "known clip"},
            {"source": "missing.mp4", "start": 0.0, "end": 2.0, "text": "unresolvable clip"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}, {"id": "002", "filename": "missing.mp4"}]}

    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "sourceStartFrame": 0,
                "sourceEndFrame": 60,
                "durationInFrames": 60,
                "timelineStartFrame": 0,
                "effects": {"captions": True, "transition": "none"},
            },
        ],
    }

    positions = resolvable_segment_positions(scene_plan, transcript, manifest)

    assert positions == [{"segmentId": "s0", "timelineFrame": 0}]


def test_compute_overridden_fields_detects_a_changed_field():
    old = {"segmentId": "s1", "text": "before"}
    new = {"segmentId": "s1", "text": "after"}

    assert compute_overridden_fields(old, new) == ["text"]


def test_compute_overridden_fields_ignores_unchanged_fields():
    old = {"segmentId": "s1", "text": "same"}
    new = {"segmentId": "s1", "text": "same"}

    assert compute_overridden_fields(old, new) == []


def test_compute_overridden_fields_reset_actually_clears_the_marker():
    old = {"segmentId": "s1", "text": "same", "overriddenFields": ["text"]}
    new = {"segmentId": "s1", "text": "same", "overriddenFields": []}

    assert compute_overridden_fields(old, new) == []


def test_compute_overridden_fields_against_empty_old_title():
    new = {"segmentId": "s1", "text": "brand new"}

    assert compute_overridden_fields({}, new) == ["text"]


def test_preserve_overridden_fields_copies_forward_a_manually_edited_text_matched_by_segment_id():
    old_titles = [
        {"segmentId": "s1", "text": "human edited title", "overriddenFields": ["text"]},
    ]
    fresh_proposals = [
        {"segmentId": "s1", "text": "freshly regenerated title"},
        {"segmentId": "s5", "text": "a different, unrelated title"},
    ]

    result = preserve_overridden_fields(old_titles, fresh_proposals)

    by_segment = {p["segmentId"]: p for p in result}
    assert by_segment["s1"]["text"] == "human edited title"
    assert by_segment["s1"]["overriddenFields"] == ["text"]
    # A segment with no prior override is left exactly as freshly proposed.
    assert by_segment["s5"]["text"] == "a different, unrelated title"


def test_preserve_overridden_fields_drops_override_when_segment_no_longer_proposed():
    # The AI no longer proposes a title for this segment at all — nothing
    # to copy the override onto, so it's silently dropped along with the
    # proposal itself (matches moments/beats' unmatched-candidate behavior).
    old_titles = [
        {"segmentId": "s1", "text": "human edited title", "overriddenFields": ["text"]},
    ]
    fresh_proposals = [
        {"segmentId": "s9", "text": "a completely different title"},
    ]

    result = preserve_overridden_fields(old_titles, fresh_proposals)

    assert result == fresh_proposals


def test_preserve_overridden_fields_with_no_prior_overrides_returns_proposals_unchanged():
    fresh_proposals = [{"segmentId": "s1", "text": "new"}]

    result = preserve_overridden_fields([], fresh_proposals)

    assert result is fresh_proposals
