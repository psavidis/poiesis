from generate_emphasis import (
    build_candidate_words,
    join_words,
    merge_beat_scenes,
    overlaps_existing_overlay,
    propose_emphasis,
    resolve_phrase,
    strip_edge_punctuation,
    words_for_presenter_scene,
)


def _presenter_scene(overrides=None):
    scene = {
        "id": "scene-001",
        "type": "presenter",
        "videoId": "001",
        "timelineStartFrame": 0,
        "durationInFrames": 300,
        "sourceStartFrame": 0,
        "sourceEndFrame": 300,
    }
    scene.update(overrides or {})
    return scene


def _manifest_single_video():
    return {"videos": [{"id": "001", "filename": "a.mp4"}]}


def _transcript_with_words():
    return {
        "segments": [
            {
                "source": "a.mp4",
                "start": 0.0,
                "end": 3.0,
                "text": "dependency injection matters a lot",
                "words": [
                    {"word": "dependency", "start": 0.0, "end": 0.5},
                    {"word": "injection", "start": 0.5, "end": 1.0},
                    {"word": "matters", "start": 1.0, "end": 1.5},
                    {"word": "a", "start": 1.5, "end": 1.6},
                    {"word": "lot", "start": 1.6, "end": 2.0},
                ],
            }
        ]
    }


def test_words_for_presenter_scene_extracts_and_positions_words():
    scene = _presenter_scene()
    words = words_for_presenter_scene(
        scene,
        _transcript_with_words()["segments"],
        fps=30,
    )

    assert len(words) == 5
    assert words[0] == {"text": "dependency", "offsetInParentFrames": 0, "durationInFrames": 15}
    assert words[1]["text"] == "injection"
    assert words[1]["offsetInParentFrames"] == 15


def test_words_for_presenter_scene_skips_segments_without_words():
    scene = _presenter_scene()
    segments = [{"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "no word timing here"}]

    assert words_for_presenter_scene(scene, segments, fps=30) == []


def test_words_for_presenter_scene_respects_trim_bounds():
    scene = _presenter_scene({"sourceStartFrame": 20, "sourceEndFrame": 300})
    words = words_for_presenter_scene(
        scene,
        _transcript_with_words()["segments"],
        fps=30,
    )

    # "dependency" spans frames [0, 15) — entirely before the trim start (20)
    assert all(w["text"] != "dependency" for w in words)


def test_build_candidate_words_assigns_scene_scoped_ids():
    scene_plan = {"fps": 30, "scenes": [_presenter_scene()]}

    candidates, scenes_by_id = build_candidate_words(
        scene_plan,
        _transcript_with_words(),
        _manifest_single_video(),
    )

    assert set(candidates.keys()) == {f"scene-001-w{i}" for i in range(5)}
    assert candidates["scene-001-w0"]["text"] == "dependency"
    assert scenes_by_id["scene-001"]["id"] == "scene-001"


def test_build_candidate_words_empty_when_no_word_data():
    scene_plan = {"fps": 30, "scenes": [_presenter_scene()]}
    transcript = {"segments": [{"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "no words"}]}

    candidates, scenes_by_id = build_candidate_words(scene_plan, transcript, _manifest_single_video())

    assert candidates == {}
    assert scenes_by_id == {}


def test_resolve_phrase_joins_contiguous_words():
    candidates = {
        "scene-001-w0": {"sceneId": "scene-001", "text": "dependency", "offsetInParentFrames": 0, "durationInFrames": 15},
        "scene-001-w1": {"sceneId": "scene-001", "text": "injection", "offsetInParentFrames": 15, "durationInFrames": 15},
    }

    phrase = resolve_phrase(["scene-001-w0", "scene-001-w1"], candidates)

    assert phrase == {
        "sceneId": "scene-001",
        "text": "dependency injection",
        "offsetInParentFrames": 0,
        "durationInFrames": 30,
    }


def test_resolve_phrase_rejects_non_contiguous_words():
    candidates = {
        "scene-001-w0": {"sceneId": "scene-001", "text": "dependency", "offsetInParentFrames": 0, "durationInFrames": 15},
        "scene-001-w2": {"sceneId": "scene-001", "text": "matters", "offsetInParentFrames": 30, "durationInFrames": 15},
    }

    assert resolve_phrase(["scene-001-w0", "scene-001-w2"], candidates) is None


def test_resolve_phrase_rejects_unknown_word_id():
    candidates = {
        "scene-001-w0": {"sceneId": "scene-001", "text": "dependency", "offsetInParentFrames": 0, "durationInFrames": 15},
    }

    assert resolve_phrase(["scene-001-w0", "scene-001-w99"], candidates) is None


def test_resolve_phrase_rejects_words_from_different_scenes():
    candidates = {
        "scene-001-w0": {"sceneId": "scene-001", "text": "dependency", "offsetInParentFrames": 0, "durationInFrames": 15},
        "scene-002-w0": {"sceneId": "scene-002", "text": "injection", "offsetInParentFrames": 0, "durationInFrames": 15},
    }

    assert resolve_phrase(["scene-001-w0", "scene-002-w0"], candidates) is None


def test_resolve_phrase_rejects_empty_word_ids():
    assert resolve_phrase([], {}) is None
    assert resolve_phrase(None, {}) is None


def test_resolve_phrase_strips_trailing_sentence_punctuation():
    # regression: a real Whisper word token came back as "injection." with
    # the sentence's own trailing period attached — a beat is a punchy pop,
    # not a sentence fragment, so this shouldn't render with the period.
    candidates = {
        "scene-001-w0": {"sceneId": "scene-001", "text": "dependency", "offsetInParentFrames": 0, "durationInFrames": 15},
        "scene-001-w1": {"sceneId": "scene-001", "text": "injection.", "offsetInParentFrames": 15, "durationInFrames": 15},
    }

    phrase = resolve_phrase(["scene-001-w0", "scene-001-w1"], candidates)

    assert phrase["text"] == "dependency injection"


def test_resolve_phrase_joins_hyphen_prefixed_token_without_space():
    # regression: Whisper tokenizes "domain-driven" as two words, "domain"
    # and "-driven" (hyphen attached to the front of the SECOND token, not
    # the end of the first) — a plain " ".join produces "domain -driven"
    # with a stray space before the hyphen.
    candidates = {
        "scene-001-w0": {"sceneId": "scene-001", "text": "domain", "offsetInParentFrames": 0, "durationInFrames": 15},
        "scene-001-w1": {"sceneId": "scene-001", "text": "-driven", "offsetInParentFrames": 15, "durationInFrames": 15},
    }

    phrase = resolve_phrase(["scene-001-w0", "scene-001-w1"], candidates)

    assert phrase["text"] == "domain-driven"


def test_resolve_phrase_rejects_phrase_that_is_pure_punctuation():
    candidates = {
        "scene-001-w0": {"sceneId": "scene-001", "text": "...", "offsetInParentFrames": 0, "durationInFrames": 15},
    }

    assert resolve_phrase(["scene-001-w0"], candidates) is None


def test_strip_edge_punctuation_keeps_internal_punctuation():
    assert strip_edge_punctuation("injection.") == "injection"
    assert strip_edge_punctuation("well,") == "well"
    assert strip_edge_punctuation("self-contained") == "self-contained"
    assert strip_edge_punctuation("Bob's") == "Bob's"


def test_join_words_no_space_before_leading_hyphen():
    assert join_words(["domain", "-driven", "design"]) == "domain-driven design"


def test_join_words_normal_case_unaffected():
    assert join_words(["dependency", "injection"]) == "dependency injection"


def test_overlaps_existing_overlay_true_for_overlapping_moment():
    scene_plan = {
        "scenes": [
            {
                "id": "scene-moment-0",
                "type": "moment",
                "treatment": "bottom-callout",
                "parentSceneId": "scene-001",
                "offsetInParentFrames": 50,
                "durationInFrames": 90,
            }
        ]
    }

    assert overlaps_existing_overlay("scene-001", 60, 24, scene_plan)


def test_overlaps_existing_overlay_false_when_no_overlap():
    scene_plan = {
        "scenes": [
            {
                "id": "scene-moment-0",
                "type": "moment",
                "treatment": "bottom-callout",
                "parentSceneId": "scene-001",
                "offsetInParentFrames": 50,
                "durationInFrames": 90,
            }
        ]
    }

    assert not overlaps_existing_overlay("scene-001", 200, 24, scene_plan)


def test_overlaps_existing_overlay_false_for_different_parent():
    scene_plan = {
        "scenes": [
            {
                "id": "scene-moment-0",
                "type": "moment",
                "treatment": "bottom-callout",
                "parentSceneId": "scene-999",
                "offsetInParentFrames": 0,
                "durationInFrames": 90,
            }
        ]
    }

    assert not overlaps_existing_overlay("scene-001", 0, 24, scene_plan)


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response

    def complete_json(self, prompt, thinking=True):
        return self.response


def test_propose_emphasis_accepts_valid_word_pop():
    llm = _FakeLLMClient(
        {
            "beats": [
                {
                    "wordIds": ["scene-001-w0", "scene-001-w1"],
                    "kind": "word-pop",
                    "reason": "key term",
                }
            ]
        }
    )

    proposals = propose_emphasis(
        {"fps": 30, "scenes": [_presenter_scene()]},
        _transcript_with_words(),
        _manifest_single_video(),
        llm,
        "{words}",
    )

    assert len(proposals) == 1
    assert proposals[0]["kind"] == "word-pop"
    assert proposals[0]["text"] == "dependency injection"
    assert proposals[0]["icon"] is None


def test_propose_emphasis_accepts_valid_icon_accent():
    llm = _FakeLLMClient(
        {
            "beats": [
                {
                    "wordIds": ["scene-001-w2"],
                    "kind": "icon-accent",
                    "icon": "check",
                    "reason": "affirms correctness",
                }
            ]
        }
    )

    proposals = propose_emphasis(
        {"fps": 30, "scenes": [_presenter_scene()]},
        _transcript_with_words(),
        _manifest_single_video(),
        llm,
        "{words}",
    )

    assert len(proposals) == 1
    assert proposals[0]["kind"] == "icon-accent"
    assert proposals[0]["icon"] == "check"


def test_propose_emphasis_rejects_icon_accent_without_valid_icon():
    llm = _FakeLLMClient(
        {
            "beats": [
                {
                    "wordIds": ["scene-001-w2"],
                    "kind": "icon-accent",
                    "icon": "rocket",
                    "reason": "made up icon",
                }
            ]
        }
    )

    proposals = propose_emphasis(
        {"fps": 30, "scenes": [_presenter_scene()]},
        _transcript_with_words(),
        _manifest_single_video(),
        llm,
        "{words}",
    )

    assert proposals == []


def test_propose_emphasis_rejects_unrecognized_kind():
    llm = _FakeLLMClient(
        {
            "beats": [
                {"wordIds": ["scene-001-w0"], "kind": "explosion", "reason": "made up kind"},
            ]
        }
    )

    proposals = propose_emphasis(
        {"fps": 30, "scenes": [_presenter_scene()]},
        _transcript_with_words(),
        _manifest_single_video(),
        llm,
        "{words}",
    )

    assert proposals == []


def test_propose_emphasis_rejects_unknown_word_id():
    llm = _FakeLLMClient(
        {
            "beats": [
                {"wordIds": ["scene-001-w99"], "kind": "word-pop", "reason": "unknown word"},
            ]
        }
    )

    proposals = propose_emphasis(
        {"fps": 30, "scenes": [_presenter_scene()]},
        _transcript_with_words(),
        _manifest_single_video(),
        llm,
        "{words}",
    )

    assert proposals == []


def test_propose_emphasis_rejects_phrase_longer_than_max_beat_words():
    # regression: a real run proposed a 6-word icon-accent phrase despite
    # the prompt asking for at most a couple of words — this is the
    # code-enforced backstop.
    transcript = {
        "segments": [
            {
                "source": "a.mp4",
                "start": 0.0,
                "end": 3.0,
                "text": "one two three four five six",
                "words": [
                    {"word": w, "start": i * 0.5, "end": (i + 1) * 0.5}
                    for i, w in enumerate(["one", "two", "three", "four", "five", "six"])
                ],
            }
        ]
    }

    llm = _FakeLLMClient(
        {
            "beats": [
                {
                    "wordIds": [f"scene-001-w{i}" for i in range(6)],
                    "kind": "word-pop",
                    "reason": "too long",
                },
            ]
        }
    )

    proposals = propose_emphasis(
        {"fps": 30, "scenes": [_presenter_scene()]},
        transcript,
        _manifest_single_video(),
        llm,
        "{words}",
    )

    assert proposals == []


def test_propose_emphasis_enforces_minimum_gap_between_beats():
    # w0 (0-15) and w1 (15-30) are essentially back-to-back — well under
    # the default 4s (120 frame) minimum gap between beats on the same
    # scene, so only the first should survive.
    llm = _FakeLLMClient(
        {
            "beats": [
                {"wordIds": ["scene-001-w0"], "kind": "word-pop", "reason": "first"},
                {"wordIds": ["scene-001-w1"], "kind": "word-pop", "reason": "second, too close"},
            ]
        }
    )

    proposals = propose_emphasis(
        {"fps": 30, "scenes": [_presenter_scene()]},
        _transcript_with_words(),
        _manifest_single_video(),
        llm,
        "{words}",
    )

    assert len(proposals) == 1
    assert proposals[0]["text"] == "dependency"


def test_propose_emphasis_rejects_beat_colliding_with_existing_moment():
    scene_plan = {
        "fps": 30,
        "scenes": [
            _presenter_scene(),
            {
                "id": "scene-moment-0",
                "type": "moment",
                "treatment": "bottom-callout",
                "parentSceneId": "scene-001",
                "offsetInParentFrames": 0,
                "durationInFrames": 30,
            },
        ],
    }

    llm = _FakeLLMClient(
        {
            "beats": [
                {"wordIds": ["scene-001-w0"], "kind": "word-pop", "reason": "collides with moment"},
            ]
        }
    )

    proposals = propose_emphasis(
        scene_plan,
        _transcript_with_words(),
        _manifest_single_video(),
        llm,
        "{words}",
    )

    assert proposals == []


def test_propose_emphasis_returns_empty_when_no_word_data():
    llm = _FakeLLMClient({"beats": [{"wordIds": ["scene-001-w0"], "kind": "word-pop", "reason": "x"}]})

    transcript = {"segments": [{"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "no word timing"}]}

    proposals = propose_emphasis(
        {"fps": 30, "scenes": [_presenter_scene()]},
        transcript,
        _manifest_single_video(),
        llm,
        "{words}",
    )

    assert proposals == []


def test_merge_beat_scenes_inserts_overlay():
    scene_plan = {"fps": 30, "scenes": [_presenter_scene()]}

    proposals = [
        {
            "sceneId": "scene-001",
            "kind": "word-pop",
            "text": "dependency injection",
            "icon": None,
            "offsetInParentFrames": 0,
            "durationInFrames": 24,
            "reason": "key term",
        }
    ]

    result = merge_beat_scenes(scene_plan, proposals)
    beat_scene = next(s for s in result["scenes"] if s["type"] == "beat")

    assert beat_scene["kind"] == "word-pop"
    assert beat_scene["text"] == "dependency injection"
    assert beat_scene["parentSceneId"] == "scene-001"
    assert "icon" not in beat_scene


def test_merge_beat_scenes_stores_icon_when_present():
    scene_plan = {"fps": 30, "scenes": [_presenter_scene()]}

    proposals = [
        {
            "sceneId": "scene-001",
            "kind": "icon-accent",
            "text": "correct",
            "icon": "check",
            "offsetInParentFrames": 0,
            "durationInFrames": 24,
            "reason": "affirms correctness",
        }
    ]

    result = merge_beat_scenes(scene_plan, proposals)
    beat_scene = next(s for s in result["scenes"] if s["type"] == "beat")

    assert beat_scene["icon"] == "check"


def test_merge_beat_scenes_is_idempotent_on_rerun():
    scene_plan = {"fps": 30, "scenes": [_presenter_scene()]}

    proposals = [
        {
            "sceneId": "scene-001",
            "kind": "word-pop",
            "text": "dependency",
            "icon": None,
            "offsetInParentFrames": 0,
            "durationInFrames": 24,
            "reason": "x",
        }
    ]

    once = merge_beat_scenes(scene_plan, proposals)
    twice = merge_beat_scenes(once, proposals)

    beat_scenes = [s for s in twice["scenes"] if s["type"] == "beat"]
    assert len(beat_scenes) == 1
