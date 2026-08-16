from edit_plan import (
    apply_operations,
    describe_selected_scene,
    edit_plan,
    reflow_timeline,
    validate_operations,
)


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

    updated_plan, valid_ops, rejected = edit_plan(
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

    updated_plan, valid_ops, rejected = edit_plan(
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

    updated_plan, valid_ops, rejected = edit_plan(
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

    updated_plan, valid_ops, rejected = edit_plan(
        scene_plan, "make this bigger", llm, PROMPT_TEMPLATE, selected_scene_id="scene-does-not-exist"
    )

    assert "(nothing selected)" in llm.last_prompt
    assert valid_ops == []
    assert rejected == []
