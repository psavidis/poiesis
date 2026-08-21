from generate_captions import (
    CAPTION_MAX_LINE_CHARS,
    captions_for_presenter_scene,
    lines_for_segment_words,
    merge_caption_scenes,
    should_regenerate,
)


def _word(text, start, end):
    return {"word": text, "start": start, "end": end}


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


def test_captions_for_presenter_scene_does_not_cap_long_segments():
    # Regression guard: an earlier version capped durationInFrames at 6s
    # while keeping the full segment text, so the caption vanished before
    # the speaker finished — verified against real footage, where it hit
    # 79% of captions in a real episode. The caption must stay up for the
    # entire segment it transcribes, no matter how long.
    scene = _presenter_scene(source_start=0, source_end=10000)

    transcript = {
        "segments": [
            {"start": 0.0, "end": 30.0, "text": "a very long uninterrupted segment"},
        ]
    }

    captions = captions_for_presenter_scene(scene, transcript, fps=30)

    assert len(captions) == 1
    assert captions[0]["durationInFrames"] == 900  # 30s at 30fps, uncapped
    assert captions[0]["text"] == "a very long uninterrupted segment"


def test_captions_for_presenter_scene_drops_slivers_clipped_below_fade_envelope():
    # Regression guard: a segment straddling a trim boundary can clip down
    # to just a few frames. CaptionText's fade needs >=8 frames (4 in + 4
    # out); anything shorter crashed the renderer with a non-monotonic
    # interpolate() inputRange. See scene-caption-25/55 in a real episode.
    scene = _presenter_scene(source_start=60, source_end=300)

    transcript = {
        "segments": [
            # frames 30 -> 65, clipped to [60, 65) = 5 frames, below the floor
            {"start": 1.0, "end": 65 / 30, "text": "sliver"},
        ]
    }

    captions = captions_for_presenter_scene(scene, transcript, fps=30)

    assert captions == []


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


def test_lines_for_segment_words_splits_at_char_budget():
    words = [
        _word("a", 0.0, 0.5),
        _word("stretch", 0.5, 1.0),
        _word("of", 1.0, 1.5),
        _word("thoroughly", 1.5, 2.0),
        _word("unnecessarily", 2.0, 2.5),
        _word("long", 2.5, 3.0),
        _word("words", 3.0, 3.5),
    ]

    lines = lines_for_segment_words(words, max_line_chars=20)

    assert all(len(line["text"]) <= 20 for line in lines)
    # Every word must still show up, in order, across the lines.
    assert " ".join(line["text"] for line in lines) == \
        "a stretch of thoroughly unnecessarily long words"


def test_lines_for_segment_words_line_spans_first_to_last_word():
    words = [
        _word("hello", 1.0, 1.5),
        _word("there", 1.5, 2.2),
    ]

    lines = lines_for_segment_words(words, max_line_chars=CAPTION_MAX_LINE_CHARS)

    assert len(lines) == 1
    assert lines[0]["text"] == "hello there"
    assert lines[0]["start"] == 1.0
    assert lines[0]["end"] == 2.2


def test_lines_for_segment_words_always_keeps_at_least_one_word_per_line():
    # A single word longer than the budget must not produce an empty line —
    # it gets its own line rather than being dropped.
    words = [_word("supercalifragilisticexpialidocious", 0.0, 1.0)]

    lines = lines_for_segment_words(words, max_line_chars=10)

    assert len(lines) == 1
    assert lines[0]["text"] == "supercalifragilisticexpialidocious"


def test_captions_for_presenter_scene_splits_long_segment_into_line_captions():
    # Regression guard for the multi-line-caption readability bug: a long
    # segment with word timestamps must become several single-line captions
    # advancing over time, not one block that wraps to 2-3 lines on screen.
    scene = _presenter_scene(source_start=0, source_end=10000)

    words = [
        _word("instead", 0.0, 0.5),
        _word("of", 0.5, 0.8),
        _word("calculating", 0.8, 1.4),
        _word("the", 1.4, 1.6),
        _word("discount", 1.6, 2.2),
        _word("on", 2.2, 2.4),
        _word("the", 2.4, 2.5),
        _word("order", 2.5, 2.9),
        _word("using", 2.9, 3.3),
        _word("a", 3.3, 3.4),
        _word("service", 3.4, 4.0),
    ]

    transcript = {
        "segments": [
            {
                "start": 0.0,
                "end": 4.0,
                "text": " ".join(w["word"] for w in words),
                "words": words,
            }
        ]
    }

    captions = captions_for_presenter_scene(scene, transcript, fps=30)

    assert len(captions) > 1
    for caption in captions:
        assert len(caption["text"]) <= CAPTION_MAX_LINE_CHARS
    # Captions must be in speech order and non-overlapping.
    for a, b in zip(captions, captions[1:]):
        assert a["offsetInParentFrames"] + a["durationInFrames"] <= b["offsetInParentFrames"]


def test_captions_for_presenter_scene_falls_back_to_whole_segment_without_word_timestamps():
    # Segments not yet re-transcribed with word timing (no "words" key)
    # must keep today's single-block-per-segment behavior.
    scene = _presenter_scene(source_start=0, source_end=300)

    transcript = {
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "no word timing here"},
        ]
    }

    captions = captions_for_presenter_scene(scene, transcript, fps=30)

    assert len(captions) == 1
    assert captions[0]["text"] == "no word timing here"


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


def test_merge_caption_scenes_with_empty_proposals_strips_existing_captions():
    # This is exactly what --disable relies on: merge_caption_scenes(plan, [])
    # removes every existing caption scene and adds none back.
    scene_plan = {
        "fps": 30,
        "scenes": [
            _presenter_scene(source_start=0, source_end=300, timeline_start=0),
            {
                "id": "scene-caption-0",
                "type": "caption",
                "text": "hello there",
                "parentSceneId": "scene-001",
                "offsetInParentFrames": 10,
                "durationInFrames": 20,
            },
        ],
    }

    merged = merge_caption_scenes(scene_plan, [])

    assert [s for s in merged["scenes"] if s["type"] == "caption"] == []
    assert [s for s in merged["scenes"] if s["type"] == "presenter"] != []


def test_should_regenerate_when_no_previous_output():
    assert should_regenerate(None, force=False) is True


def test_should_regenerate_false_when_already_generated_and_not_forced():
    previous = {"captions": [{"text": "hello"}]}
    assert should_regenerate(previous, force=False) is False


def test_should_regenerate_true_when_forced():
    previous = {"captions": [{"text": "hello"}]}
    assert should_regenerate(previous, force=True) is True


def test_should_regenerate_true_when_previously_disabled_even_without_force():
    # Regression guard: re-enabling captions (running without --disable
    # again) must actually regenerate them, not stay silently disabled
    # because captions.json already exists from the --disable run.
    previous = {"captions": [], "disabled": True}
    assert should_regenerate(previous, force=False) is True
