from edit_plan import (
    INSET_IMAGE_DURATION_FRAMES,
    PROMPT_FILE,
    apply_operations,
    describe_scene_transcripts,
    describe_selected_scene,
    edit_plan,
    load_prompt,
    reflow_timeline,
    resolve_beat_creation,
    resolve_bottom_callout_creation,
    resolve_full_screen_code_creation,
    resolve_full_screen_diagram_creation,
    resolve_full_screen_image_creation,
    resolve_full_screen_text_creation,
    resolve_image_creation,
    resolve_manual_moment_creation,
    validate_operations,
)
from generate_emphasis import build_candidate_words
from style import load_style


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.last_prompt = None

    def complete_json(self, prompt, thinking=True):
        self.last_prompt = prompt
        return self.response


def _presenter(scene_id, source_start, source_end, timeline_start):
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


def _title(scene_id, text, timeline_start, duration=60):
    return {
        "id": scene_id,
        "type": "title",
        "text": text,
        "timelineStartFrame": timeline_start,
        "durationInFrames": duration,
    }


def _moment(scene_id, parent_id, offset, duration, text):
    return {
        "id": scene_id,
        "type": "moment",
        "treatment": "bottom-callout",
        "text": text,
        "parentSceneId": parent_id,
        "offsetInParentFrames": offset,
        "durationInFrames": duration,
    }


def _beat(scene_id, parent_id, offset, duration, text, kind="word-pop"):
    return {
        "id": scene_id,
        "type": "beat",
        "kind": kind,
        "text": text,
        "parentSceneId": parent_id,
        "offsetInParentFrames": offset,
        "durationInFrames": duration,
    }


# Beat-creation fixtures (#52) — same shape as
# test_generate_emphasis.py's own _manifest_single_video/
# _transcript_with_words, since resolve_beat_creation/build_candidate_words
# are imported from that module, not reimplemented here.
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


def _scene_plan_with_words_scene():
    return {
        "fps": 30,
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
        ],
    }


# Moment-creation fixtures (#53) — segment-level transcript text (not
# word-level; resolve_bottom_callout_creation grounds against whole
# segments via generate_moments.py's own is_grounded, reusing
# group_transcript_by_clip/filter_segments_in_window, not word-level
# matching the way beats do).
def _transcript_with_segments():
    return {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "dependency injection matters a lot"},
            {"source": "a.mp4", "start": 3.0, "end": 6.0, "text": "it makes testing much easier"},
        ]
    }


def test_validate_operations_accepts_remove_for_existing_scene():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    ops = [{"op": "remove", "sceneId": "scene-title-0", "reason": "not needed"}]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == ops
    assert rejected == []


def test_validate_operations_rejects_unknown_scene_id():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    ops = [{"op": "remove", "sceneId": "scene-does-not-exist", "reason": "x"}]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == []
    assert len(rejected) == 1
    assert "no scene with id" in rejected[0]["reason"]


def test_validate_operations_accepts_update_with_allowed_field():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    ops = [
        {
            "op": "update",
            "sceneId": "scene-title-0",
            "fields": {"text": "Goodbye"},
            "reason": "changed wording",
        }
    ]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == ops
    assert rejected == []


def test_validate_operations_rejects_update_with_disallowed_field():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    ops = [
        {
            "op": "update",
            "sceneId": "scene-title-0",
            "fields": {"timelineStartFrame": 999},
            "reason": "trying to move it",
        }
    ]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == []
    assert len(rejected) == 1
    assert "timelineStartFrame" in rejected[0]["reason"]


# --- trim op (#65 — mid-take pause cuts) ---


def test_validate_operations_accepts_trim_within_source_range():
    scene_plan = {"scenes": [_presenter("scene-001", 0, 300, 0)]}

    ops = [{"op": "trim", "sceneId": "scene-001", "cutStartFrame": 100, "cutEndFrame": 150, "reason": "pause"}]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == ops
    assert rejected == []


def test_validate_operations_rejects_trim_on_non_presenter_scene():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    ops = [{"op": "trim", "sceneId": "scene-title-0", "cutStartFrame": 0, "cutEndFrame": 10, "reason": "pause"}]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == []
    assert "presenter" in rejected[0]["reason"]


def test_validate_operations_rejects_trim_outside_source_range():
    scene_plan = {"scenes": [_presenter("scene-001", 0, 300, 0)]}

    ops = [{"op": "trim", "sceneId": "scene-001", "cutStartFrame": 280, "cutEndFrame": 320, "reason": "pause"}]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == []
    assert "source range" in rejected[0]["reason"]


def test_validate_operations_rejects_trim_with_start_at_or_after_end():
    scene_plan = {"scenes": [_presenter("scene-001", 0, 300, 0)]}

    ops = [{"op": "trim", "sceneId": "scene-001", "cutStartFrame": 150, "cutEndFrame": 100, "reason": "pause"}]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == []
    assert "source range" in rejected[0]["reason"]


def test_apply_operations_trim_splits_an_interior_cut_into_two_scenes():
    scene_plan = {
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
            _presenter("scene-002", 0, 100, 300),
        ]
    }

    ops = [{"op": "trim", "sceneId": "scene-001", "cutStartFrame": 100, "cutEndFrame": 150, "reason": "pause"}]

    result = reflow_timeline(apply_operations(scene_plan, ops))
    scenes_by_id = {s["id"]: s for s in result["scenes"]}

    assert scenes_by_id["scene-001"]["sourceStartFrame"] == 0
    assert scenes_by_id["scene-001"]["sourceEndFrame"] == 100
    assert scenes_by_id["scene-001"]["durationInFrames"] == 100
    assert scenes_by_id["scene-001"]["timelineStartFrame"] == 0

    assert scenes_by_id["scene-001-b"]["sourceStartFrame"] == 150
    assert scenes_by_id["scene-001-b"]["sourceEndFrame"] == 300
    assert scenes_by_id["scene-001-b"]["durationInFrames"] == 150
    assert scenes_by_id["scene-001-b"]["timelineStartFrame"] == 100
    assert scenes_by_id["scene-001-b"]["videoId"] == "001"
    assert scenes_by_id["scene-001-b"]["effects"]["transition"] == "crossfade"

    # reflow_timeline rippled the later, untouched scene by the removed span.
    assert scenes_by_id["scene-002"]["timelineStartFrame"] == 250


def test_apply_operations_trim_flush_against_scene_start_keeps_original_id():
    scene_plan = {"scenes": [_presenter("scene-001", 0, 300, 0)]}

    ops = [{"op": "trim", "sceneId": "scene-001", "cutStartFrame": 0, "cutEndFrame": 50, "reason": "pause"}]

    result = reflow_timeline(apply_operations(scene_plan, ops))

    assert [s["id"] for s in result["scenes"]] == ["scene-001"]
    assert result["scenes"][0]["sourceStartFrame"] == 50
    assert result["scenes"][0]["sourceEndFrame"] == 300
    assert result["scenes"][0]["effects"]["transition"] == "none"


def test_apply_operations_trim_flush_against_scene_end_keeps_original_id():
    scene_plan = {"scenes": [_presenter("scene-001", 0, 300, 0)]}

    ops = [{"op": "trim", "sceneId": "scene-001", "cutStartFrame": 250, "cutEndFrame": 300, "reason": "pause"}]

    result = reflow_timeline(apply_operations(scene_plan, ops))

    assert [s["id"] for s in result["scenes"]] == ["scene-001"]
    assert result["scenes"][0]["sourceEndFrame"] == 250


def test_apply_operations_trim_reparents_overlays_before_and_after_the_cut():
    scene_plan = {
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
            _moment("m-before", "scene-001", 50, 10, "before the cut"),
            _moment("m-after", "scene-001", 200, 10, "after the cut"),
        ]
    }

    ops = [{"op": "trim", "sceneId": "scene-001", "cutStartFrame": 100, "cutEndFrame": 150, "reason": "pause"}]

    result = apply_operations(scene_plan, ops)
    scenes_by_id = {s["id"]: s for s in result["scenes"]}

    assert scenes_by_id["m-before"]["parentSceneId"] == "scene-001"
    assert scenes_by_id["m-before"]["offsetInParentFrames"] == 50

    # 200 (absolute) - 150 (second scene's new sourceStartFrame) == 50
    assert scenes_by_id["m-after"]["parentSceneId"] == "scene-001-b"
    assert scenes_by_id["m-after"]["offsetInParentFrames"] == 50


def test_apply_operations_trim_drops_an_overlay_strictly_inside_the_cut():
    scene_plan = {
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
            _moment("m-inside", "scene-001", 120, 10, "inside the cut"),
        ]
    }

    ops = [{"op": "trim", "sceneId": "scene-001", "cutStartFrame": 100, "cutEndFrame": 150, "reason": "pause"}]

    result = apply_operations(scene_plan, ops)

    assert "m-inside" not in {s["id"] for s in result["scenes"]}


def _image(scene_id, parent_id, offset, duration, asset_id, display="inset"):
    return {
        "id": scene_id,
        "type": "image",
        "assetId": asset_id,
        "caption": "",
        "display": display,
        "parentSceneId": parent_id,
        "offsetInParentFrames": offset,
        "durationInFrames": duration,
    }


def test_validate_operations_accepts_image_asset_and_display_updates():
    scene_plan = {"scenes": [_image("scene-image-0", "scene-001", 0, 60, "asset-1")]}

    ops = [
        {
            "op": "update",
            "sceneId": "scene-image-0",
            "fields": {"assetId": "asset-2", "display": "full"},
            "reason": "swap to a full-screen diagram",
        }
    ]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == ops
    assert rejected == []


def test_validate_operations_accepts_moment_entrance_update():
    # entrance (docs/specs/ai-assisted-editing-and-conversational-control.md
    # section 7's animation-configuration prerequisite) is a real editable
    # field on "moment" now, not just text/assetId/caption/timing.
    scene_plan = {"scenes": [_moment("scene-moment-0", "scene-001", 10, 60, "hello there")]}

    ops = [
        {
            "op": "update",
            "sceneId": "scene-moment-0",
            "fields": {"entrance": "slide"},
            "reason": "make it slide in",
        }
    ]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == ops
    assert rejected == []


def test_validate_operations_accepts_hold_from_previous_update():
    # holdFromPrevious lets a chat instruction ("keep me on the right for
    # the next image too") merge this moment's presenter-side window into
    # the immediately preceding one at render time — see MomentScene in
    # video-renderer's types.ts and Episode.tsx's layoutWindowsForScene.
    scene_plan = {"scenes": [_moment("scene-moment-1", "scene-001", 400, 100, "second image")]}

    ops = [
        {
            "op": "update",
            "sceneId": "scene-moment-1",
            "fields": {"holdFromPrevious": True},
            "reason": "keep the presenter on the same side as the previous moment",
        }
    ]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == ops
    assert rejected == []


def test_validate_operations_rejects_an_invalid_entrance_value():
    # Regression: field-NAME validation alone would let a hallucinated
    # entrance value (e.g. "bounce" — not one of the three real patterns
    # BottomCallout.tsx's computeTransform implements) through silently,
    # since "entrance" itself is a valid field name for "moment". Value
    # validation catches it explicitly instead.
    scene_plan = {"scenes": [_moment("scene-moment-0", "scene-001", 10, 60, "hello there")]}

    ops = [
        {
            "op": "update",
            "sceneId": "scene-moment-0",
            "fields": {"entrance": "bounce"},
            "reason": "x",
        }
    ]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == []
    assert len(rejected) == 1
    assert "entrance" in rejected[0]["reason"]


def test_validate_operations_accepts_each_valid_entrance_value():
    scene_plan = {"scenes": [_moment("scene-moment-0", "scene-001", 10, 60, "hello there")]}

    for value in ("fade", "scale", "slide"):
        ops = [{"op": "update", "sceneId": "scene-moment-0", "fields": {"entrance": value}, "reason": "x"}]
        valid, rejected = validate_operations(scene_plan, ops)
        assert valid == ops, f"entrance={value!r} should be valid"
        assert rejected == []


def test_validate_operations_rejects_id_and_type_and_linking_fields():
    scene_plan = {
        "scenes": [_moment("scene-moment-0", "scene-001", 10, 60, "hello there")]
    }

    ops = [
        {
            "op": "update",
            "sceneId": "scene-moment-0",
            "fields": {"parentSceneId": "scene-002"},
            "reason": "trying to reparent",
        }
    ]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == []
    assert "parentSceneId" in rejected[0]["reason"]


def test_validate_operations_rejects_unknown_op():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    ops = [{"op": "invent", "sceneId": "scene-title-0"}]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == []
    assert "unknown op" in rejected[0]["reason"]


def test_validate_operations_accepts_create_without_requiring_an_existing_scene_id():
    # A "create" op has no sceneId to look up yet — must not be rejected
    # via the same "no scene with id" path remove/update use.
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    ops = [{"op": "create", "type": "beat", "wordIds": ["scene-001-w0"], "kind": "word-pop", "reason": "x"}]

    valid, rejected = validate_operations(scene_plan, ops)

    assert valid == ops
    assert rejected == []


def test_apply_operations_leaves_create_ops_untouched():
    # apply_operations only mutates scene_plan["scenes"] for remove/update
    # — a "create" op is resolved into a beat proposal and routed to
    # emphasis.json separately (see edit_plan()), so it must pass through
    # apply_operations as a complete no-op rather than erroring on the
    # missing sceneId.
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    ops = [{"op": "create", "type": "beat", "wordIds": ["scene-001-w0"], "kind": "word-pop", "reason": "x"}]

    result = apply_operations(scene_plan, ops)

    assert result["scenes"] == scene_plan["scenes"]


def test_resolve_beat_creation_accepts_a_valid_single_word():
    scene_plan = _scene_plan_with_words_scene()
    candidates, scenes_by_id = build_candidate_words(
        scene_plan, _transcript_with_words(), _manifest_single_video()
    )

    op = {"op": "create", "type": "beat", "wordIds": ["scene-001-w1"], "kind": "word-pop", "reason": "the key term"}

    beat = resolve_beat_creation(op, scene_plan, candidates, scenes_by_id)

    assert beat["sceneId"] == "scene-001"
    assert beat["text"] == "injection"
    assert beat["kind"] == "word-pop"
    assert beat["offsetInParentFrames"] == 15
    assert beat["reason"] == "the key term"


def test_resolve_beat_creation_accepts_a_contiguous_phrase():
    scene_plan = _scene_plan_with_words_scene()
    candidates, scenes_by_id = build_candidate_words(
        scene_plan, _transcript_with_words(), _manifest_single_video()
    )

    op = {
        "op": "create", "type": "beat",
        "wordIds": ["scene-001-w0", "scene-001-w1"], "kind": "underline", "reason": "the whole term",
    }

    beat = resolve_beat_creation(op, scene_plan, candidates, scenes_by_id)

    assert beat["text"] == "dependency injection"


def test_resolve_beat_creation_rejects_non_contiguous_words():
    scene_plan = _scene_plan_with_words_scene()
    candidates, scenes_by_id = build_candidate_words(
        scene_plan, _transcript_with_words(), _manifest_single_video()
    )

    op = {
        "op": "create", "type": "beat",
        "wordIds": ["scene-001-w0", "scene-001-w2"], "kind": "word-pop", "reason": "x",
    }

    assert resolve_beat_creation(op, scene_plan, candidates, scenes_by_id) is None


def test_resolve_beat_creation_rejects_an_unknown_word_id():
    scene_plan = _scene_plan_with_words_scene()
    candidates, scenes_by_id = build_candidate_words(
        scene_plan, _transcript_with_words(), _manifest_single_video()
    )

    op = {"op": "create", "type": "beat", "wordIds": ["scene-001-w99"], "kind": "word-pop", "reason": "x"}

    assert resolve_beat_creation(op, scene_plan, candidates, scenes_by_id) is None


def test_resolve_beat_creation_rejects_an_invalid_kind():
    scene_plan = _scene_plan_with_words_scene()
    candidates, scenes_by_id = build_candidate_words(
        scene_plan, _transcript_with_words(), _manifest_single_video()
    )

    op = {"op": "create", "type": "beat", "wordIds": ["scene-001-w0"], "kind": "spin", "reason": "x"}

    assert resolve_beat_creation(op, scene_plan, candidates, scenes_by_id) is None


def test_resolve_beat_creation_requires_a_valid_icon_for_icon_accent():
    scene_plan = _scene_plan_with_words_scene()
    candidates, scenes_by_id = build_candidate_words(
        scene_plan, _transcript_with_words(), _manifest_single_video()
    )

    missing_icon = {"op": "create", "type": "beat", "wordIds": ["scene-001-w0"], "kind": "icon-accent", "reason": "x"}
    assert resolve_beat_creation(missing_icon, scene_plan, candidates, scenes_by_id) is None

    valid_icon = {
        "op": "create", "type": "beat",
        "wordIds": ["scene-001-w0"], "kind": "icon-accent", "icon": "arrow", "reason": "x",
    }
    beat = resolve_beat_creation(valid_icon, scene_plan, candidates, scenes_by_id)
    assert beat["icon"] == "arrow"


def test_resolve_beat_creation_rejects_a_phrase_over_the_word_cap():
    scene_plan = _scene_plan_with_words_scene()
    candidates, scenes_by_id = build_candidate_words(
        scene_plan, _transcript_with_words(), _manifest_single_video()
    )

    # All 5 words — well past MAX_BEAT_WORDS (3).
    op = {
        "op": "create", "type": "beat",
        "wordIds": ["scene-001-w0", "scene-001-w1", "scene-001-w2", "scene-001-w3", "scene-001-w4"],
        "kind": "word-pop", "reason": "x",
    }

    assert resolve_beat_creation(op, scene_plan, candidates, scenes_by_id) is None


def test_resolve_beat_creation_rejects_overlap_with_an_existing_moment():
    scene_plan = _scene_plan_with_words_scene()
    style = load_style()
    beat_duration = style["emphasis"]["defaultDurationFrames"]

    # "injection" starts at offset 15 (see fixture) — place a moment
    # covering that exact window so the new beat collides with it.
    scene_plan["scenes"].append(_moment("scene-moment-0", "scene-001", 0, beat_duration + 20, "existing moment"))

    candidates, scenes_by_id = build_candidate_words(
        scene_plan, _transcript_with_words(), _manifest_single_video()
    )

    op = {"op": "create", "type": "beat", "wordIds": ["scene-001-w1"], "kind": "word-pop", "reason": "x"}

    assert resolve_beat_creation(op, scene_plan, candidates, scenes_by_id, style) is None


def test_resolve_beat_creation_rejects_when_word_id_is_missing():
    scene_plan = _scene_plan_with_words_scene()
    candidates, scenes_by_id = build_candidate_words(
        scene_plan, _transcript_with_words(), _manifest_single_video()
    )

    op = {"op": "create", "type": "beat", "kind": "word-pop", "reason": "x"}

    assert resolve_beat_creation(op, scene_plan, candidates, scenes_by_id) is None


def test_edit_plan_creates_a_beat_grounded_against_real_transcript_words():
    scene_plan = _scene_plan_with_words_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "beat",
                    "wordIds": ["scene-001-w1"], "kind": "word-pop",
                    "reason": "the key term",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "add a beat popping the word injection", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_words(), manifest=_manifest_single_video(),
    )

    assert len(created_beats) == 1
    assert created_beats[0]["text"] == "injection"
    assert created_beats[0]["sceneId"] == "scene-001"
    assert rejected == []
    # remove/update ops list is separate from created_beats — a create op
    # doesn't show up there since it never touches scene_plan directly.
    assert valid_ops == []
    assert "scene-001-w1" in llm.last_prompt


def test_edit_plan_rejects_an_ungroundable_beat_creation():
    scene_plan = _scene_plan_with_words_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "beat",
                    "wordIds": ["scene-001-w0", "scene-001-w2"], "kind": "word-pop",
                    "reason": "non-contiguous, should be rejected",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "add a weird beat", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_words(), manifest=_manifest_single_video(),
    )

    assert created_beats == []
    assert len(rejected) == 1


def test_edit_plan_without_transcript_cannot_create_beats():
    scene_plan = _scene_plan_with_words_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "beat",
                    "wordIds": ["scene-001-w1"], "kind": "word-pop", "reason": "x",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "add a beat", llm, PROMPT_TEMPLATE,
    )

    assert created_beats == []
    assert len(rejected) == 1
    assert "no word-level transcript data available" in llm.last_prompt


def test_edit_plan_surfaces_explanation_when_model_returns_no_operations():
    # Regression (#67): a request the model correctly declines (e.g. custom
    # invented text for a beat, which must be an exact transcript phrase)
    # used to reach the creator as a bare empty result with no reason why —
    # the prompt now asks the model to explain itself whenever it returns
    # zero operations, and this value must survive edit_plan()'s return.
    scene_plan = _scene_plan_with_words_scene()

    llm = _FakeLLMClient(
        {
            "operations": [],
            "explanation": "\"Hello this is Petros\" isn't a phrase actually said in the transcript.",
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "add a beat saying Hello this is Petros", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_words(), manifest=_manifest_single_video(),
    )

    assert valid_ops == []
    assert created_beats == []
    assert explanation == "\"Hello this is Petros\" isn't a phrase actually said in the transcript."


def test_edit_plan_explanation_is_none_when_operations_are_returned():
    scene_plan = _scene_plan_with_words_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "beat",
                    "wordIds": ["scene-001-w1"], "kind": "word-pop",
                    "reason": "the key term",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "add a beat popping the word injection", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_words(), manifest=_manifest_single_video(),
    )

    assert len(created_beats) == 1
    assert explanation is None


def _scene_plan_with_segments_scene():
    return {
        "fps": 30,
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
        ],
    }


def test_resolve_bottom_callout_creation_accepts_grounded_text():
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "moment", "sceneId": "scene-001",
        "text": "dependency injection matters", "reason": "the core idea",
    }

    moment = resolve_bottom_callout_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video())

    assert moment["sceneId"] == "scene-001"
    assert moment["treatment"] == "bottom-callout"
    assert moment["text"] == "dependency injection matters"
    assert moment["presenterSide"] is None
    assert moment["reason"] == "the core idea"


def test_resolve_bottom_callout_creation_sets_entrance_when_provided_and_valid():
    # Regression: a "create" op's entrance was previously silently
    # discarded entirely — resolve_bottom_callout_creation's returned dict
    # never included it, so a single instruction combining creation with
    # an animation request ("show a callout... and make it slide in")
    # could never actually set the animation at creation time.
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "moment", "sceneId": "scene-001",
        "text": "dependency injection matters", "entrance": "slide", "reason": "x",
    }

    moment = resolve_bottom_callout_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video())

    assert moment["entrance"] == "slide"


def test_resolve_bottom_callout_creation_omits_entrance_when_absent():
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "moment", "sceneId": "scene-001",
        "text": "dependency injection matters", "reason": "x",
    }

    moment = resolve_bottom_callout_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video())

    assert "entrance" not in moment


def test_resolve_bottom_callout_creation_ignores_an_invalid_entrance_value():
    # An invented/hallucinated entrance value doesn't reject the whole
    # creation — the callout itself is still real and grounded, just
    # without a non-default entrance (falls back to the renderer's own
    # "scale" default).
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "moment", "sceneId": "scene-001",
        "text": "dependency injection matters", "entrance": "bounce", "reason": "x",
    }

    moment = resolve_bottom_callout_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video())

    assert moment is not None
    assert "entrance" not in moment


def test_resolve_bottom_callout_creation_places_the_moment_near_where_text_is_spoken():
    scene_plan = _scene_plan_with_segments_scene()

    # "makes testing much easier" is only in the SECOND segment (starts at
    # 3.0s = frame 90), not the first — placement must follow the actual
    # spoken position, not always default to the scene's start.
    op = {
        "op": "create", "type": "moment", "sceneId": "scene-001",
        "text": "makes testing much easier", "reason": "x",
    }

    moment = resolve_bottom_callout_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video())

    assert moment["offsetInParentFrames"] == 90


def test_resolve_bottom_callout_creation_rejects_ungrounded_text():
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "moment", "sceneId": "scene-001",
        "text": "this was never actually said in the video", "reason": "x",
    }

    assert resolve_bottom_callout_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_bottom_callout_creation_rejects_a_non_presenter_scene():
    scene_plan = {
        "fps": 30,
        "scenes": [_title("scene-title-0", "Hello", 0)],
    }

    op = {
        "op": "create", "type": "moment", "sceneId": "scene-title-0",
        "text": "dependency injection matters", "reason": "x",
    }

    assert resolve_bottom_callout_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_bottom_callout_creation_rejects_an_unknown_scene_id():
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "moment", "sceneId": "scene-does-not-exist",
        "text": "dependency injection matters", "reason": "x",
    }

    assert resolve_bottom_callout_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_bottom_callout_creation_requires_scene_id_and_text():
    scene_plan = _scene_plan_with_segments_scene()

    missing_scene_id = {"op": "create", "type": "moment", "text": "dependency injection matters", "reason": "x"}
    assert resolve_bottom_callout_creation(
        missing_scene_id, scene_plan, _transcript_with_segments(), _manifest_single_video()
    ) is None

    missing_text = {"op": "create", "type": "moment", "sceneId": "scene-001", "reason": "x"}
    assert resolve_bottom_callout_creation(
        missing_text, scene_plan, _transcript_with_segments(), _manifest_single_video()
    ) is None


def test_resolve_bottom_callout_creation_rejects_overlap_with_an_existing_moment():
    scene_plan = _scene_plan_with_segments_scene()

    # An existing moment already covers frame 0 through well past the
    # default bottom-callout duration — the new one (which would also
    # place at/near frame 0, matching the FIRST segment) must be rejected.
    scene_plan["scenes"].append(_moment("scene-moment-0", "scene-001", 0, 150, "already here"))

    op = {
        "op": "create", "type": "moment", "sceneId": "scene-001",
        "text": "dependency injection matters", "reason": "x",
    }

    assert resolve_bottom_callout_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_bottom_callout_creation_returns_none_without_transcript_or_manifest():
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "moment", "sceneId": "scene-001",
        "text": "dependency injection matters", "reason": "x",
    }

    assert resolve_bottom_callout_creation(op, scene_plan, None, _manifest_single_video()) is None
    assert resolve_bottom_callout_creation(op, scene_plan, _transcript_with_segments(), None) is None


# resolve_manual_moment_creation — human-initiated (Cmd+I), not AI-proposed,
# moment insertion. Unlike resolve_bottom_callout_creation and friends,
# there's no transcript/grounding involved — a human directly authors the
# content afterward through the existing editors, so these tests only cover
# placement/duration/overlap, not text fabrication.
def _presenter_only_scene_plan(duration=300):
    return {"fps": 30, "scenes": [_presenter("scene-001", 0, duration, 0)]}


def test_resolve_manual_moment_creation_creates_a_bottom_callout_for_text_kind():
    scene_plan = _presenter_only_scene_plan()

    moment = resolve_manual_moment_creation("scene-001", 60, "text", scene_plan)

    assert moment["sceneId"] == "scene-001"
    assert moment["treatment"] == "bottom-callout"
    assert moment["offsetInParentFrames"] == 60
    assert moment["text"] == ""
    assert moment["presenterSide"] is None


def test_resolve_manual_moment_creation_maps_each_kind_to_its_treatment():
    scene_plan = _presenter_only_scene_plan()

    assert resolve_manual_moment_creation("scene-001", 0, "image", scene_plan)["treatment"] == "side-image"
    assert resolve_manual_moment_creation("scene-001", 0, "code", scene_plan)["treatment"] == "side-code"
    assert resolve_manual_moment_creation("scene-001", 0, "diagram", scene_plan)["treatment"] == "side-diagram"


def test_resolve_manual_moment_creation_rejects_an_unknown_kind():
    scene_plan = _presenter_only_scene_plan()

    assert resolve_manual_moment_creation("scene-001", 0, "video", scene_plan) is None


def test_resolve_manual_moment_creation_rejects_a_non_presenter_scene():
    scene_plan = {"fps": 30, "scenes": [_title("scene-title-0", "Hello", 0)]}

    assert resolve_manual_moment_creation("scene-title-0", 0, "text", scene_plan) is None


def test_resolve_manual_moment_creation_rejects_an_unknown_scene_id():
    scene_plan = _presenter_only_scene_plan()

    assert resolve_manual_moment_creation("scene-does-not-exist", 0, "text", scene_plan) is None


def test_resolve_manual_moment_creation_clamps_duration_to_remaining_room():
    # A tiny presenter scene with almost no room left after the offset —
    # the default bottom-callout duration must be clamped, not overflow
    # past the parent scene's own end.
    scene_plan = _presenter_only_scene_plan(duration=70)

    moment = resolve_manual_moment_creation("scene-001", 60, "text", scene_plan)

    assert moment["maxDurationInParentFrames"] == 10


def test_resolve_manual_moment_creation_rejects_placement_with_no_room_left():
    scene_plan = _presenter_only_scene_plan(duration=60)

    assert resolve_manual_moment_creation("scene-001", 60, "text", scene_plan) is None


def test_resolve_manual_moment_creation_rejects_overlap_with_an_existing_moment():
    scene_plan = _presenter_only_scene_plan()
    scene_plan["scenes"].append(_moment("scene-moment-0", "scene-001", 0, 150, "already here"))

    assert resolve_manual_moment_creation("scene-001", 0, "text", scene_plan) is None


# resolve_image_creation — AI creation of inset image scenes via chat
# (previously ImageScene had no creation path at all: not the pipeline,
# not the editor UI, not chat — see docs/specs/content-types-and-presentation-editing.md).
def _assets():
    return [
        {"id": "asset-1", "caption": "the architecture diagram"},
        {"id": "asset-2", "caption": "a screenshot of the config file"},
    ]


def test_resolve_image_creation_accepts_a_real_asset_id():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "image", "sceneId": "scene-001", "assetId": "asset-1", "reason": "shows the design"}

    image = resolve_image_creation(op, scene_plan, _assets(), None, None)

    assert image["type"] == "image"
    assert image["assetId"] == "asset-1"
    assert image["caption"] == "the architecture diagram"
    assert image["display"] == "inset"
    assert image["parentSceneId"] == "scene-001"


def test_resolve_image_creation_rejects_an_unknown_asset_id():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "image", "sceneId": "scene-001", "assetId": "asset-does-not-exist", "reason": "x"}

    assert resolve_image_creation(op, scene_plan, _assets(), None, None) is None


def test_resolve_image_creation_rejects_a_non_presenter_scene():
    scene_plan = {"fps": 30, "scenes": [_title("scene-title-0", "Hello", 0)]}

    op = {"op": "create", "type": "image", "sceneId": "scene-title-0", "assetId": "asset-1", "reason": "x"}

    assert resolve_image_creation(op, scene_plan, _assets(), None, None) is None


def test_resolve_image_creation_requires_scene_id_and_asset_id():
    scene_plan = _scene_plan_with_segments_scene()

    missing_scene_id = {"op": "create", "type": "image", "assetId": "asset-1", "reason": "x"}
    assert resolve_image_creation(missing_scene_id, scene_plan, _assets(), None, None) is None

    missing_asset_id = {"op": "create", "type": "image", "sceneId": "scene-001", "reason": "x"}
    assert resolve_image_creation(missing_asset_id, scene_plan, _assets(), None, None) is None


def test_resolve_image_creation_defaults_to_scene_start_without_anchor_text():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "image", "sceneId": "scene-001", "assetId": "asset-1", "reason": "x"}

    image = resolve_image_creation(op, scene_plan, _assets(), _transcript_with_segments(), _manifest_single_video())

    assert image["offsetInParentFrames"] == 0


def test_resolve_image_creation_places_near_anchor_text_when_given():
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "image", "sceneId": "scene-001", "assetId": "asset-2",
        "anchorText": "makes testing much easier", "reason": "x",
    }

    image = resolve_image_creation(op, scene_plan, _assets(), _transcript_with_segments(), _manifest_single_video())

    # "makes testing much easier" is only in the SECOND segment (starts at
    # 3.0s = frame 90) — same placement discipline as
    # resolve_bottom_callout_creation's own anchor test above.
    assert image["offsetInParentFrames"] == 90


def test_resolve_image_creation_uses_default_duration():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "image", "sceneId": "scene-001", "assetId": "asset-1", "reason": "x"}

    image = resolve_image_creation(op, scene_plan, _assets(), None, None)

    assert image["durationInFrames"] == INSET_IMAGE_DURATION_FRAMES


def test_resolve_image_creation_rejects_overlap_with_an_existing_moment():
    scene_plan = _scene_plan_with_segments_scene()
    scene_plan["scenes"].append(_moment("scene-moment-0", "scene-001", 0, 150, "already here"))

    op = {"op": "create", "type": "image", "sceneId": "scene-001", "assetId": "asset-1", "reason": "x"}

    assert resolve_image_creation(op, scene_plan, _assets(), None, None) is None


def test_resolve_image_creation_rejects_overlap_with_an_existing_image():
    scene_plan = _scene_plan_with_segments_scene()
    scene_plan["scenes"].append(_image("scene-image-0", "scene-001", 0, 150, "asset-2"))

    op = {"op": "create", "type": "image", "sceneId": "scene-001", "assetId": "asset-1", "reason": "x"}

    assert resolve_image_creation(op, scene_plan, _assets(), None, None) is None


def test_resolve_image_creation_returns_none_without_any_assets():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "image", "sceneId": "scene-001", "assetId": "asset-1", "reason": "x"}

    assert resolve_image_creation(op, scene_plan, [], None, None) is None
    assert resolve_image_creation(op, scene_plan, None, None, None) is None


def test_edit_plan_creates_an_inset_image_grounded_against_a_real_asset():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "image", "sceneId": "scene-001",
                    "assetId": "asset-1", "reason": "the creator asked to show the diagram",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "show the architecture diagram in the corner", llm, PROMPT_TEMPLATE, assets=_assets()
    )

    assert len(created_images) == 1
    assert created_images[0]["assetId"] == "asset-1"
    assert created_images[0]["display"] == "inset"
    assert rejected == []


def test_edit_plan_rejects_an_ungroundable_image_creation():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "image", "sceneId": "scene-001",
                    "assetId": "asset-does-not-exist", "reason": "x",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "show some image", llm, PROMPT_TEMPLATE, assets=_assets()
    )

    assert created_images == []
    assert len(rejected) == 1


def test_edit_plan_without_assets_cannot_create_images():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "image", "sceneId": "scene-001",
                    "assetId": "asset-1", "reason": "x",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "show the diagram", llm, PROMPT_TEMPLATE
    )

    assert created_images == []
    assert len(rejected) == 1


# resolve_full_screen_diagram_creation — AI creation of Full Screen diagram
# moments via chat (docs/specs/ai-assisted-editing-and-conversational-
# control.md section 5's own worked example: "Create a Full Screen diagram
# explaining how the producer communicates with Kafka").
def _grounded_diagram():
    # Labels drawn from _transcript_with_segments()'s actual words
    # ("dependency injection", "testing") so is_diagram_grounded accepts it.
    return {
        "nodes": [
            {"id": "a", "label": "dependency injection"},
            {"id": "b", "label": "testing"},
        ],
        "edges": [{"from": "a", "to": "b", "label": "enables"}],
        "layout": "horizontal",
    }


def test_resolve_full_screen_diagram_creation_accepts_a_grounded_diagram():
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "diagram", "sceneId": "scene-001",
        "diagram": _grounded_diagram(), "reason": "explains the relationship",
    }

    moment = resolve_full_screen_diagram_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video())

    assert moment["sceneId"] == "scene-001"
    assert moment["treatment"] == "full-visual"
    assert moment["fullVisualKind"] == "diagram"
    assert moment["diagram"] == _grounded_diagram()
    assert moment["presenterSide"] is None
    assert "text" not in moment


def test_resolve_full_screen_diagram_creation_rejects_a_hallucinated_diagram():
    scene_plan = _scene_plan_with_segments_scene()

    diagram = {
        "nodes": [{"id": "a", "label": "kubernetes cluster"}, {"id": "b", "label": "service mesh"}],
        "edges": [{"from": "a", "to": "b"}],
        "layout": "horizontal",
    }
    op = {"op": "create", "type": "diagram", "sceneId": "scene-001", "diagram": diagram, "reason": "x"}

    assert resolve_full_screen_diagram_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_full_screen_diagram_creation_rejects_too_many_nodes():
    scene_plan = _scene_plan_with_segments_scene()

    diagram = {
        "nodes": [{"id": str(i), "label": "dependency injection"} for i in range(7)],
        "edges": [],
        "layout": "horizontal",
    }
    op = {"op": "create", "type": "diagram", "sceneId": "scene-001", "diagram": diagram, "reason": "x"}

    assert resolve_full_screen_diagram_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_full_screen_diagram_creation_rejects_an_edge_referencing_an_unknown_node():
    scene_plan = _scene_plan_with_segments_scene()

    diagram = {
        "nodes": [{"id": "a", "label": "dependency injection"}],
        "edges": [{"from": "a", "to": "does-not-exist"}],
        "layout": "horizontal",
    }
    op = {"op": "create", "type": "diagram", "sceneId": "scene-001", "diagram": diagram, "reason": "x"}

    assert resolve_full_screen_diagram_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_full_screen_diagram_creation_rejects_invalid_layout():
    scene_plan = _scene_plan_with_segments_scene()

    diagram = {**_grounded_diagram(), "layout": "diagonal"}
    op = {"op": "create", "type": "diagram", "sceneId": "scene-001", "diagram": diagram, "reason": "x"}

    assert resolve_full_screen_diagram_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_full_screen_diagram_creation_rejects_a_non_presenter_scene():
    scene_plan = {"fps": 30, "scenes": [_title("scene-title-0", "Hello", 0)]}

    op = {"op": "create", "type": "diagram", "sceneId": "scene-title-0", "diagram": _grounded_diagram(), "reason": "x"}

    assert resolve_full_screen_diagram_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_full_screen_diagram_creation_requires_scene_id_and_diagram():
    scene_plan = _scene_plan_with_segments_scene()

    missing_scene_id = {"op": "create", "type": "diagram", "diagram": _grounded_diagram(), "reason": "x"}
    assert resolve_full_screen_diagram_creation(
        missing_scene_id, scene_plan, _transcript_with_segments(), _manifest_single_video()
    ) is None

    missing_diagram = {"op": "create", "type": "diagram", "sceneId": "scene-001", "reason": "x"}
    assert resolve_full_screen_diagram_creation(
        missing_diagram, scene_plan, _transcript_with_segments(), _manifest_single_video()
    ) is None


def test_resolve_full_screen_diagram_creation_returns_none_without_transcript_or_manifest():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "diagram", "sceneId": "scene-001", "diagram": _grounded_diagram(), "reason": "x"}

    assert resolve_full_screen_diagram_creation(op, scene_plan, None, _manifest_single_video()) is None
    assert resolve_full_screen_diagram_creation(op, scene_plan, _transcript_with_segments(), None) is None


# resolve_full_screen_image_creation — Full Screen counterpart to
# resolve_image_creation's inset image (#64).
def test_resolve_full_screen_image_creation_accepts_a_real_asset_id():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "image", "assetId": "asset-1", "reason": "x"}

    moment = resolve_full_screen_image_creation(op, scene_plan, _assets())

    assert moment["sceneId"] == "scene-001"
    assert moment["treatment"] == "full-visual"
    assert moment["fullVisualKind"] == "image"
    assert moment["assetId"] == "asset-1"
    assert moment["caption"] == "the architecture diagram"
    assert moment["presenterSide"] is None


def test_resolve_full_screen_image_creation_rejects_an_unknown_asset_id():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "image", "assetId": "does-not-exist", "reason": "x"}

    assert resolve_full_screen_image_creation(op, scene_plan, _assets()) is None


def test_resolve_full_screen_image_creation_rejects_a_non_presenter_scene():
    scene_plan = {"fps": 30, "scenes": [_title("scene-title-0", "Hello", 0)]}

    op = {"op": "create", "type": "full-screen", "sceneId": "scene-title-0", "fullVisualKind": "image", "assetId": "asset-1", "reason": "x"}

    assert resolve_full_screen_image_creation(op, scene_plan, _assets()) is None


def test_resolve_full_screen_image_creation_requires_scene_id_and_asset_id():
    scene_plan = _scene_plan_with_segments_scene()

    missing_scene_id = {"op": "create", "type": "full-screen", "fullVisualKind": "image", "assetId": "asset-1", "reason": "x"}
    assert resolve_full_screen_image_creation(missing_scene_id, scene_plan, _assets()) is None

    missing_asset_id = {"op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "image", "reason": "x"}
    assert resolve_full_screen_image_creation(missing_asset_id, scene_plan, _assets()) is None


def test_resolve_full_screen_image_creation_returns_none_without_any_assets():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "image", "assetId": "asset-1", "reason": "x"}

    assert resolve_full_screen_image_creation(op, scene_plan, None) is None
    assert resolve_full_screen_image_creation(op, scene_plan, []) is None


# resolve_full_screen_code_creation — same shape, grounded against a real
# codeAssetId instead of assetId (#64).
def _code_assets():
    return [
        {"id": "code-1", "language": "java", "description": "the kafka consumer"},
        {"id": "code-2", "language": "python", "description": "the order repository"},
    ]


def test_resolve_full_screen_code_creation_accepts_a_real_code_asset_id():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "code", "codeAssetId": "code-1", "reason": "x"}

    moment = resolve_full_screen_code_creation(op, scene_plan, _code_assets())

    assert moment["sceneId"] == "scene-001"
    assert moment["treatment"] == "full-visual"
    assert moment["fullVisualKind"] == "code"
    assert moment["codeAssetId"] == "code-1"
    assert moment["caption"] == "the kafka consumer"
    assert moment["presenterSide"] is None


def test_resolve_full_screen_code_creation_rejects_an_unknown_code_asset_id():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "code", "codeAssetId": "does-not-exist", "reason": "x"}

    assert resolve_full_screen_code_creation(op, scene_plan, _code_assets()) is None


def test_resolve_full_screen_code_creation_rejects_a_non_presenter_scene():
    scene_plan = {"fps": 30, "scenes": [_title("scene-title-0", "Hello", 0)]}

    op = {"op": "create", "type": "full-screen", "sceneId": "scene-title-0", "fullVisualKind": "code", "codeAssetId": "code-1", "reason": "x"}

    assert resolve_full_screen_code_creation(op, scene_plan, _code_assets()) is None


def test_resolve_full_screen_code_creation_requires_scene_id_and_code_asset_id():
    scene_plan = _scene_plan_with_segments_scene()

    missing_scene_id = {"op": "create", "type": "full-screen", "fullVisualKind": "code", "codeAssetId": "code-1", "reason": "x"}
    assert resolve_full_screen_code_creation(missing_scene_id, scene_plan, _code_assets()) is None

    missing_code_asset_id = {"op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "code", "reason": "x"}
    assert resolve_full_screen_code_creation(missing_code_asset_id, scene_plan, _code_assets()) is None


def test_resolve_full_screen_code_creation_returns_none_without_any_code_assets():
    scene_plan = _scene_plan_with_segments_scene()

    op = {"op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "code", "codeAssetId": "code-1", "reason": "x"}

    assert resolve_full_screen_code_creation(op, scene_plan, None) is None
    assert resolve_full_screen_code_creation(op, scene_plan, []) is None


# resolve_full_screen_text_creation — grounding-only, same discipline as
# resolve_bottom_callout_creation's own text field (#64).
def test_resolve_full_screen_text_creation_accepts_grounded_text():
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "text",
        "text": "dependency injection matters", "reason": "the core idea",
    }

    moment = resolve_full_screen_text_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video())

    assert moment["sceneId"] == "scene-001"
    assert moment["treatment"] == "full-visual"
    assert moment["fullVisualKind"] == "text"
    assert moment["text"] == "dependency injection matters"
    assert moment["presenterSide"] is None


def test_resolve_full_screen_text_creation_rejects_ungrounded_text():
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "text",
        "text": "this was never actually said in the video", "reason": "x",
    }

    assert resolve_full_screen_text_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_full_screen_text_creation_rejects_a_non_presenter_scene():
    scene_plan = {"fps": 30, "scenes": [_title("scene-title-0", "Hello", 0)]}

    op = {
        "op": "create", "type": "full-screen", "sceneId": "scene-title-0", "fullVisualKind": "text",
        "text": "dependency injection matters", "reason": "x",
    }

    assert resolve_full_screen_text_creation(op, scene_plan, _transcript_with_segments(), _manifest_single_video()) is None


def test_resolve_full_screen_text_creation_requires_scene_id_and_text():
    scene_plan = _scene_plan_with_segments_scene()

    missing_scene_id = {"op": "create", "type": "full-screen", "fullVisualKind": "text", "text": "dependency injection matters", "reason": "x"}
    assert resolve_full_screen_text_creation(
        missing_scene_id, scene_plan, _transcript_with_segments(), _manifest_single_video()
    ) is None

    missing_text = {"op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "text", "reason": "x"}
    assert resolve_full_screen_text_creation(
        missing_text, scene_plan, _transcript_with_segments(), _manifest_single_video()
    ) is None


def test_resolve_full_screen_text_creation_returns_none_without_transcript_or_manifest():
    scene_plan = _scene_plan_with_segments_scene()

    op = {
        "op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "text",
        "text": "dependency injection matters", "reason": "x",
    }

    assert resolve_full_screen_text_creation(op, scene_plan, None, _manifest_single_video()) is None
    assert resolve_full_screen_text_creation(op, scene_plan, _transcript_with_segments(), None) is None


def test_edit_plan_creates_a_full_screen_diagram_grounded_against_scene_transcript():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "diagram", "sceneId": "scene-001",
                    "diagram": _grounded_diagram(), "reason": "explains the relationship",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "create a full screen diagram of how DI relates to testing", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_segments(), manifest=_manifest_single_video(),
    )

    assert len(created_moments) == 1
    assert created_moments[0]["treatment"] == "full-visual"
    assert created_moments[0]["fullVisualKind"] == "diagram"
    assert rejected == []


def test_edit_plan_creates_a_full_screen_image_grounded_against_a_real_asset():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "image",
                    "assetId": "asset-1", "reason": "shows the architecture full screen",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "show the architecture diagram full screen", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_segments(), manifest=_manifest_single_video(), assets=_assets(),
    )

    assert len(created_moments) == 1
    assert created_moments[0]["treatment"] == "full-visual"
    assert created_moments[0]["fullVisualKind"] == "image"
    assert created_moments[0]["assetId"] == "asset-1"
    assert rejected == []


def test_edit_plan_creates_a_full_screen_code_grounded_against_a_real_code_asset():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "code",
                    "codeAssetId": "code-1", "reason": "shows the kafka consumer full screen",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "show the kafka consumer code full screen", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_segments(), manifest=_manifest_single_video(), code_assets=_code_assets(),
    )

    assert len(created_moments) == 1
    assert created_moments[0]["treatment"] == "full-visual"
    assert created_moments[0]["fullVisualKind"] == "code"
    assert created_moments[0]["codeAssetId"] == "code-1"
    assert rejected == []


def test_edit_plan_creates_a_full_screen_text_grounded_against_the_transcript():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "text",
                    "text": "dependency injection matters", "reason": "the core statement, full screen",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "make this statement full screen", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_segments(), manifest=_manifest_single_video(),
    )

    assert len(created_moments) == 1
    assert created_moments[0]["treatment"] == "full-visual"
    assert created_moments[0]["fullVisualKind"] == "text"
    assert created_moments[0]["text"] == "dependency injection matters"
    assert rejected == []


def test_edit_plan_rejects_a_full_screen_creation_with_an_unrecognized_full_visual_kind():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "full-screen", "sceneId": "scene-001", "fullVisualKind": "video",
                    "reason": "x",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "show a full screen video", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_segments(), manifest=_manifest_single_video(),
    )

    assert created_moments == []
    assert len(rejected) == 1


def test_edit_plan_rejects_an_ungroundable_diagram_creation():
    scene_plan = _scene_plan_with_segments_scene()

    diagram = {
        "nodes": [{"id": "a", "label": "kubernetes"}, {"id": "b", "label": "service mesh"}],
        "edges": [{"from": "a", "to": "b"}],
        "layout": "horizontal",
    }
    llm = _FakeLLMClient(
        {"operations": [{"op": "create", "type": "diagram", "sceneId": "scene-001", "diagram": diagram, "reason": "x"}]}
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "create a full screen diagram about kubernetes", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_segments(), manifest=_manifest_single_video(),
    )

    assert created_moments == []
    assert len(rejected) == 1


def test_edit_plan_without_transcript_cannot_create_diagrams():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {"op": "create", "type": "diagram", "sceneId": "scene-001", "diagram": _grounded_diagram(), "reason": "x"}
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "create a diagram", llm, PROMPT_TEMPLATE
    )

    assert created_moments == []
    assert len(rejected) == 1


def test_edit_plan_creates_a_bottom_callout_grounded_against_scene_transcript():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "moment", "sceneId": "scene-001",
                    "text": "dependency injection matters", "reason": "the core idea",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "add a callout saying dependency injection matters", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_segments(), manifest=_manifest_single_video(),
    )

    assert len(created_moments) == 1
    assert created_moments[0]["text"] == "dependency injection matters"
    assert created_moments[0]["treatment"] == "bottom-callout"
    assert rejected == []
    assert valid_ops == []
    assert created_beats == []


def test_edit_plan_rejects_an_ungroundable_moment_creation():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "create", "type": "moment", "sceneId": "scene-001",
                    "text": "this phrase was never said", "reason": "fabricated",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "add a weird callout", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_segments(), manifest=_manifest_single_video(),
    )

    assert created_moments == []
    assert len(rejected) == 1


def test_apply_operations_removes_scene():
    scene_plan = {
        "scenes": [
            _title("scene-title-0", "Hello", 0),
            _title("scene-title-1", "World", 60),
        ]
    }

    ops = [{"op": "remove", "sceneId": "scene-title-0", "reason": "x"}]

    result = apply_operations(scene_plan, ops)

    ids = [s["id"] for s in result["scenes"]]
    assert ids == ["scene-title-1"]


def test_apply_operations_updates_fields_without_touching_others():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0, duration=60)]}

    ops = [
        {
            "op": "update",
            "sceneId": "scene-title-0",
            "fields": {"text": "Goodbye"},
            "reason": "x",
        }
    ]

    result = apply_operations(scene_plan, ops)

    scene = result["scenes"][0]
    assert scene["text"] == "Goodbye"
    assert scene["durationInFrames"] == 60
    assert scene["timelineStartFrame"] == 0


def test_reflow_timeline_shifts_subsequent_track_scenes_after_shrinking_a_presenter_scene():
    scene_plan = {
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
            _title("scene-title-0", "Hello", 300),
            _presenter("scene-002", 0, 200, 360),
        ]
    }

    # Simulate a trim edit shrinking the first presenter scene
    scene_plan["scenes"][0]["sourceEndFrame"] = 200
    scene_plan["scenes"][0]["durationInFrames"] = 200

    result = reflow_timeline(scene_plan)

    by_id = {s["id"]: s for s in result["scenes"]}

    assert by_id["scene-001"]["timelineStartFrame"] == 0
    assert by_id["scene-title-0"]["timelineStartFrame"] == 200
    assert by_id["scene-002"]["timelineStartFrame"] == 260


def test_reflow_timeline_leaves_overlay_scenes_untouched():
    scene_plan = {
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
            _moment("scene-moment-0", "scene-001", 50, 90, "hello there"),
        ]
    }

    result = reflow_timeline(scene_plan)

    overlay = [s for s in result["scenes"] if s["type"] == "moment"][0]
    assert overlay["offsetInParentFrames"] == 50
    assert overlay["durationInFrames"] == 90
    assert "timelineStartFrame" not in overlay


def test_reflow_timeline_preserves_track_scene_relative_order():
    scene_plan = {
        "scenes": [
            _title("scene-title-1", "Second", 100),
            _presenter("scene-001", 0, 100, 0),
        ]
    }

    result = reflow_timeline(scene_plan)

    ids_in_order = [s["id"] for s in result["scenes"] if s["type"] in ("presenter", "title")]
    assert ids_in_order == ["scene-001", "scene-title-1"]


PROMPT_TEMPLATE = (
    "instruction: {instruction}\n"
    "plan: {scene_plan}\n"
    "fields: {editable_fields}\n"
    "selected: {selected_scene}\n"
    "words: {candidate_words}\n"
    "transcripts: {scene_transcripts}\n"
)


def test_edit_plan_end_to_end_applies_valid_operation_and_reflows():
    scene_plan = {
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
            _title("scene-title-0", "Old title", 300),
        ]
    }

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "update",
                    "sceneId": "scene-title-0",
                    "fields": {"text": "New title"},
                    "reason": "matches the instruction",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "change the title to New title", llm, PROMPT_TEMPLATE
    )

    assert len(valid_ops) == 1
    assert rejected == []

    by_id = {s["id"]: s for s in updated_plan["scenes"]}
    assert by_id["scene-title-0"]["text"] == "New title"
    # unaffected by the update, but reflow still runs unconditionally
    assert by_id["scene-title-0"]["timelineStartFrame"] == 300


def test_edit_plan_end_to_end_filters_out_invalid_operations():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "update",
                    "sceneId": "scene-does-not-exist",
                    "fields": {"text": "x"},
                    "reason": "hallucinated id",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "some instruction", llm, PROMPT_TEMPLATE
    )

    assert valid_ops == []
    assert len(rejected) == 1
    assert updated_plan["scenes"][0]["text"] == "Hello"


def test_edit_plan_handles_instruction_containing_template_like_braces():
    # Regression guard: the instruction is substituted last specifically so
    # a user-authored instruction containing literal "{scene_plan}"-shaped
    # text can't corrupt the earlier substitutions.
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    llm = _FakeLLMClient({"operations": []})

    tricky_instruction = 'remove the scene that says "{scene_plan}" in it'

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, tricky_instruction, llm, PROMPT_TEMPLATE
    )

    assert valid_ops == []
    assert rejected == []
    assert updated_plan["scenes"][0]["text"] == "Hello"


def test_describe_selected_scene_returns_none_when_no_id_given():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    assert describe_selected_scene(scene_plan, None) is None
    assert describe_selected_scene(scene_plan, "") is None


def test_describe_selected_scene_returns_none_for_a_stale_or_unknown_id():
    # A selection left over from before a prior edit removed that scene —
    # must degrade gracefully, not raise, since selection is a hint for
    # resolving "this"/"that", not a requirement.
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    assert describe_selected_scene(scene_plan, "scene-does-not-exist") is None


def test_describe_selected_scene_summarizes_a_title_scene():
    scene_plan = {"scenes": [_title("scene-title-0", "Why Event Sourcing", 0)]}

    description = describe_selected_scene(scene_plan, "scene-title-0")

    assert "id: scene-title-0" in description
    assert "type: title" in description
    assert "text: Why Event Sourcing" in description


def test_describe_selected_scene_summarizes_a_moment_scene():
    scene_plan = {"scenes": [_moment("scene-moment-0", "scene-001", 10, 60, "the key idea")]}

    description = describe_selected_scene(scene_plan, "scene-moment-0")

    assert "id: scene-moment-0" in description
    assert "type: moment" in description
    assert "text: the key idea" in description


def test_edit_plan_injects_selected_scene_description_into_the_prompt():
    scene_plan = {
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
            _moment("scene-moment-0", "scene-001", 10, 60, "the key idea"),
        ]
    }

    llm = _FakeLLMClient({"operations": []})

    edit_plan(scene_plan, "make this bigger", llm, PROMPT_TEMPLATE, selected_scene_id="scene-moment-0")

    assert "id: scene-moment-0" in llm.last_prompt
    assert "type: moment" in llm.last_prompt
    assert "text: the key idea" in llm.last_prompt


def test_edit_plan_injects_nothing_selected_when_no_selection_given():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    llm = _FakeLLMClient({"operations": []})

    edit_plan(scene_plan, "change the title", llm, PROMPT_TEMPLATE)

    assert "(nothing selected)" in llm.last_prompt


def test_edit_plan_degrades_to_nothing_selected_for_a_stale_selection():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    llm = _FakeLLMClient({"operations": []})

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "make this bigger", llm, PROMPT_TEMPLATE, selected_scene_id="scene-does-not-exist"
    )

    assert "(nothing selected)" in llm.last_prompt
    assert valid_ops == []
    assert rejected == []


# describe_scene_transcripts (#55) — resolves script-anchored references
# ("after I mention CQRS") by surfacing what's actually said in each
# presenter scene, since a presenter scene itself has no text field.
def test_describe_scene_transcripts_lists_what_each_presenter_scene_says():
    scene_plan = _scene_plan_with_segments_scene()

    text = describe_scene_transcripts(scene_plan, _transcript_with_segments(), _manifest_single_video())

    assert "scene-001:" in text
    assert "dependency injection matters a lot" in text
    assert "it makes testing much easier" in text


def test_describe_scene_transcripts_only_includes_segments_within_the_scenes_source_window():
    scene_plan = {
        "fps": 30,
        "scenes": [
            # sourceEndFrame=90 at 30fps is 3.0s — only the first segment
            # (0.0-3.0s) falls inside this scene's own source window, the
            # second (3.0-6.0s) belongs to whatever scene comes after it.
            _presenter("scene-001", 0, 90, 0),
        ],
    }

    text = describe_scene_transcripts(scene_plan, _transcript_with_segments(), _manifest_single_video())

    assert "dependency injection matters a lot" in text
    assert "it makes testing much easier" not in text


def test_describe_scene_transcripts_covers_every_presenter_scene_not_just_the_first():
    scene_plan = {
        "fps": 30,
        "scenes": [
            _presenter("scene-001", 0, 90, 0),
            _presenter("scene-002", 90, 180, 90),
        ],
    }
    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 3.0, "text": "first scene content"},
            {"source": "a.mp4", "start": 3.0, "end": 6.0, "text": "second scene content"},
        ]
    }

    text = describe_scene_transcripts(scene_plan, transcript, _manifest_single_video())

    assert "scene-001: first scene content" in text
    assert "scene-002: second scene content" in text


def test_describe_scene_transcripts_degrades_gracefully_without_transcript_or_manifest():
    scene_plan = _scene_plan_with_segments_scene()

    text = describe_scene_transcripts(scene_plan, None, None)

    assert "no transcript available" in text


def test_edit_plan_injects_scene_transcripts_into_the_prompt():
    scene_plan = _scene_plan_with_segments_scene()

    llm = _FakeLLMClient({"operations": []})

    edit_plan(
        scene_plan, "make the scene about testing bigger", llm, PROMPT_TEMPLATE,
        transcript=_transcript_with_segments(), manifest=_manifest_single_video(),
    )

    assert "scene-001: dependency injection matters a lot it makes testing much easier" in llm.last_prompt


def test_edit_plan_degrades_scene_transcripts_without_transcript_or_manifest():
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    llm = _FakeLLMClient({"operations": []})

    edit_plan(scene_plan, "change the title", llm, PROMPT_TEMPLATE)

    assert "no transcript available" in llm.last_prompt


# Vague/free-language selection-scoped instruction translation (#61, part
# of #44) — the actual "what field should change" reasoning happens
# entirely inside the real LLM prompt (pipeline/prompts/edit_plan.txt),
# which these tests don't exercise (they use a fake, scripted LLM
# response, same as every other edit_plan() test in this file). What's
# tested here is the plumbing: a vague instruction's resulting operation
# — however the model decided to answer it — validates and applies
# through the same path a concrete instruction's operation would, and the
# real prompt template actually contains the new guidance.
def test_edit_plan_applies_a_vague_instructions_field_change_on_a_moment():
    scene_plan = {
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
            _moment("scene-moment-0", "scene-001", 10, 60, "some text"),
        ]
    }

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "update",
                    "sceneId": "scene-moment-0",
                    "fields": {"durationInFrames": 120},
                    "reason": "lengthened so it lingers longer, reading as more dramatic",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "make this more dramatic", llm, PROMPT_TEMPLATE, selected_scene_id="scene-moment-0"
    )

    assert len(valid_ops) == 1
    assert rejected == []

    by_id = {s["id"]: s for s in updated_plan["scenes"]}
    assert by_id["scene-moment-0"]["durationInFrames"] == 120


def test_edit_plan_applies_a_concrete_entrance_animation_request():
    # A CONCRETE animation request ("make this fade in") — distinct from
    # the vague-feeling tests above, this is docs/specs/ai-assisted-
    # editing-and-conversational-control.md section 7's "if the requested
    # animation corresponds to an existing supported animation, configure
    # it" — entrance is that configurable field.
    scene_plan = {
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
            _moment("scene-moment-0", "scene-001", 10, 60, "some text"),
        ]
    }

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "update",
                    "sceneId": "scene-moment-0",
                    "fields": {"entrance": "fade"},
                    "reason": "a plain fade in, as requested",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "make this fade in instead", llm, PROMPT_TEMPLATE, selected_scene_id="scene-moment-0"
    )

    assert len(valid_ops) == 1
    assert rejected == []

    by_id = {s["id"]: s for s in updated_plan["scenes"]}
    assert by_id["scene-moment-0"]["entrance"] == "fade"


def test_edit_plan_applies_a_vague_instructions_field_change_on_a_beat():
    scene_plan = {
        "scenes": [
            _presenter("scene-001", 0, 300, 0),
            _beat("scene-beat-0", "scene-001", 10, 30, "async"),
        ]
    }

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "update",
                    "sceneId": "scene-beat-0",
                    "fields": {"durationInFrames": 45},
                    "reason": "held slightly longer to pop harder",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "make this pop more", llm, PROMPT_TEMPLATE, selected_scene_id="scene-beat-0"
    )

    assert len(valid_ops) == 1
    by_id = {s["id"]: s for s in updated_plan["scenes"]}
    assert by_id["scene-beat-0"]["durationInFrames"] == 45


def test_edit_plan_applies_a_vague_instructions_field_change_on_a_title():
    scene_plan = {"scenes": [_title("scene-title-0", "Encapsulation", 0)]}

    llm = _FakeLLMClient(
        {
            "operations": [
                {
                    "op": "update",
                    "sceneId": "scene-title-0",
                    "fields": {"text": "Why Encapsulation Matters"},
                    "reason": "a punchier phrasing of the same topic, grounded in the original title",
                }
            ]
        }
    )

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "make this more dramatic", llm, PROMPT_TEMPLATE, selected_scene_id="scene-title-0"
    )

    assert len(valid_ops) == 1
    by_id = {s["id"]: s for s in updated_plan["scenes"]}
    assert by_id["scene-title-0"]["text"] == "Why Encapsulation Matters"


def test_edit_plan_vague_instruction_with_no_plausible_field_returns_no_operations():
    # A genuinely ungroundable vague instruction still degrades to an
    # empty operations list, same as an unresolvable concrete instruction
    # — the model (scripted here) chose not to guess.
    scene_plan = {"scenes": [_title("scene-title-0", "Hello", 0)]}

    llm = _FakeLLMClient({"operations": []})

    updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
        scene_plan, "make this more dramatic", llm, PROMPT_TEMPLATE
    )

    assert valid_ops == []
    assert updated_plan["scenes"][0]["text"] == "Hello"


def test_edit_plan_prompt_includes_vague_instruction_guidance():
    # Loads the REAL prompt template (not the test's minimal PROMPT_TEMPLATE
    # stand-in) to confirm the actual guidance added for #61 is present —
    # a regression check that the file on disk still contains it.
    real_template = load_prompt(PROMPT_FILE)

    assert "dramatic" in real_template
    assert "editable fields" in real_template.lower()


def test_edit_plan_prompt_includes_entrance_animation_guidance():
    # Regression check that the entrance-configuration guidance (docs/specs/
    # ai-assisted-editing-and-conversational-control.md section 7) is
    # present in the real prompt file on disk.
    real_template = load_prompt(PROMPT_FILE)

    assert "entrance" in real_template.lower()
    assert '"fade"' in real_template
    assert '"scale"' in real_template
    assert '"slide"' in real_template


def test_edit_plan_prompt_includes_full_screen_creation_guidance():
    # Regression check that Full Screen image/code/text creation (#64) is
    # documented in the real prompt file on disk, not just implemented in
    # code the LLM is never told about.
    real_template = load_prompt(PROMPT_FILE)

    assert '"type": "full-screen"' in real_template
    assert "fullVisualKind" in real_template
    assert "{available_code_assets}" in real_template
