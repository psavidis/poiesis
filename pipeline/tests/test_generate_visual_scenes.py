from generate_visual_scenes import (
    build_candidate_windows,
    is_grounded,
    merge_emphasis_scenes,
    merge_image_scenes,
    propose_visual_scenes,
)


def test_is_grounded_accepts_verbatim_text():
    assert is_grounded(
        "replace dependencies more easily",
        "we can replace our dependencies of our modules easier",
    )


def test_is_grounded_rejects_fabricated_text():
    assert not is_grounded(
        "the moon landing was faked",
        "we can replace our dependencies of our modules easier",
    )


def test_is_grounded_rejects_empty_text():
    assert not is_grounded("", "some source text")


def test_build_candidate_windows_produces_text_from_matching_segments():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "type": "presenter",
                "id": "scene-001",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,  # 30s, exceeds 18s threshold
                "sourceStartFrame": 0,
                "sourceEndFrame": 900,
            }
        ],
    }

    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 0.0, "end": 5.0, "text": "early talk"},
            {"source": "a.mp4", "start": 20.0, "end": 22.0, "text": "late important point"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    candidates = build_candidate_windows(scene_plan, transcript, manifest)

    assert len(candidates) == 1
    assert candidates[0]["videoId"] == "001"
    assert "late important point" in candidates[0]["text"]
    assert "early talk" not in candidates[0]["text"]


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response

    def complete_json(self, prompt, thinking=True):
        return self.response


def _scene_plan_with_one_long_scene():
    return {
        "fps": 30,
        "scenes": [
            {
                "type": "presenter",
                "id": "scene-001",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,
                "sourceStartFrame": 0,
                "sourceEndFrame": 900,
            }
        ],
    }


def _transcript_with_late_segment():
    return {
        "segments": [
            {"source": "a.mp4", "start": 20.0, "end": 22.0, "text": "the important key idea"},
        ]
    }


def _manifest_single_video():
    return {"videos": [{"id": "001", "filename": "a.mp4"}]}


def _no_assets():
    return []


def _one_asset():
    return [{"id": "img-001", "filename": "a.png", "caption": "a relevant diagram"}]


def test_propose_visual_scenes_accepts_grounded_emphasis_proposal():
    llm = _FakeLLMClient(
        {
            "emphases": [
                {
                    "windowId": "w0",
                    "text": "the important key idea",
                    "reason": "central point",
                }
            ],
            "images": [],
        }
    )

    emphases, images = propose_visual_scenes(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert len(emphases) == 1
    assert emphases[0]["text"] == "the important key idea"
    assert images == []


def test_propose_visual_scenes_rejects_ungrounded_emphasis_proposal():
    llm = _FakeLLMClient(
        {
            "emphases": [
                {
                    "windowId": "w0",
                    "text": "completely unrelated fabricated statement",
                    "reason": "made up",
                }
            ],
            "images": [],
        }
    )

    emphases, images = propose_visual_scenes(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert emphases == []
    assert images == []


def test_propose_visual_scenes_rejects_unknown_window_id():
    llm = _FakeLLMClient(
        {
            "emphases": [
                {
                    "windowId": "w999",
                    "text": "the important key idea",
                    "reason": "central point",
                }
            ],
            "images": [],
        }
    )

    emphases, images = propose_visual_scenes(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert emphases == []
    assert images == []


def test_propose_visual_scenes_accepts_valid_image_proposal():
    llm = _FakeLLMClient(
        {
            "emphases": [],
            "images": [
                {
                    "windowId": "w0",
                    "assetId": "img-001",
                    "reason": "illustrates the point",
                }
            ],
        }
    )

    emphases, images = propose_visual_scenes(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _one_asset(),
        llm,
        "{windows}{assets}",
    )

    assert emphases == []
    assert len(images) == 1
    assert images[0]["assetId"] == "img-001"
    assert images[0]["caption"] == "a relevant diagram"


def test_propose_visual_scenes_rejects_unknown_asset_id():
    llm = _FakeLLMClient(
        {
            "emphases": [],
            "images": [
                {
                    "windowId": "w0",
                    "assetId": "img-999",
                    "reason": "hallucinated",
                }
            ],
        }
    )

    emphases, images = propose_visual_scenes(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _one_asset(),
        llm,
        "{windows}{assets}",
    )

    assert images == []


def test_propose_visual_scenes_does_not_double_propose_same_window():
    llm = _FakeLLMClient(
        {
            "emphases": [
                {
                    "windowId": "w0",
                    "text": "the important key idea",
                    "reason": "central point",
                }
            ],
            "images": [
                {
                    "windowId": "w0",
                    "assetId": "img-001",
                    "reason": "also relevant",
                }
            ],
        }
    )

    emphases, images = propose_visual_scenes(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _one_asset(),
        llm,
        "{windows}{assets}",
    )

    # only the first-seen proposal (emphasis) should win for a claimed window
    assert len(emphases) == 1
    assert images == []


def test_merge_emphasis_scenes_inserts_overlay_after_presenter_scene_for_stacking():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,
            },
            {
                "id": "scene-002",
                "type": "presenter",
                "videoId": "002",
                "timelineStartFrame": 900,
                "durationInFrames": 300,
            },
        ],
    }

    proposals = [
        {
            "windowId": "w0",
            "sceneId": "scene-001",
            "videoId": "001",
            "offsetInParentFrames": 500,
            "maxDurationInParentFrames": 400,
            "text": "key phrase",
            "reason": "central",
        }
    ]

    result = merge_emphasis_scenes(scene_plan, proposals)
    scenes = result["scenes"]

    assert [s["id"] for s in scenes] == ["scene-001", "scene-emphasis-0", "scene-002"]

    emphasis_scene = scenes[1]
    assert emphasis_scene["type"] == "emphasis"
    assert emphasis_scene["parentSceneId"] == "scene-001"
    assert emphasis_scene["offsetInParentFrames"] == 500
    assert emphasis_scene["durationInFrames"] == 90


def test_merge_emphasis_scenes_clamps_duration_to_window_end():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,
            },
        ],
    }

    proposals = [
        {
            "windowId": "w0",
            "sceneId": "scene-001",
            "videoId": "001",
            "offsetInParentFrames": 850,
            "maxDurationInParentFrames": 50,  # less than default 90
            "text": "key phrase",
            "reason": "central",
        }
    ]

    result = merge_emphasis_scenes(scene_plan, proposals)
    emphasis_scene = next(s for s in result["scenes"] if s["type"] == "emphasis")

    assert emphasis_scene["durationInFrames"] == 50


def test_merge_emphasis_scenes_no_proposals_leaves_plan_unchanged():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,
            },
        ],
    }

    result = merge_emphasis_scenes(scene_plan, [])

    assert result["scenes"] == scene_plan["scenes"]


def test_merge_image_scenes_inserts_inset_overlay():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,
            },
        ],
    }

    proposals = [
        {
            "windowId": "w0",
            "sceneId": "scene-001",
            "videoId": "001",
            "offsetInParentFrames": 500,
            "maxDurationInParentFrames": 400,
            "assetId": "img-001",
            "caption": "a relevant diagram",
            "reason": "illustrates the point",
        }
    ]

    result = merge_image_scenes(scene_plan, proposals)
    image_scene = next(s for s in result["scenes"] if s["type"] == "image")

    assert image_scene["assetId"] == "img-001"
    assert image_scene["caption"] == "a relevant diagram"
    assert image_scene["display"] == "inset"
    assert image_scene["parentSceneId"] == "scene-001"
    assert image_scene["offsetInParentFrames"] == 500
    assert image_scene["durationInFrames"] == 120


def test_merge_image_scenes_clamps_duration_to_window_end():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,
            },
        ],
    }

    proposals = [
        {
            "windowId": "w0",
            "sceneId": "scene-001",
            "videoId": "001",
            "offsetInParentFrames": 850,
            "maxDurationInParentFrames": 50,  # less than default 120
            "assetId": "img-001",
            "caption": "a relevant diagram",
            "reason": "illustrates the point",
        }
    ]

    result = merge_image_scenes(scene_plan, proposals)
    image_scene = next(s for s in result["scenes"] if s["type"] == "image")

    assert image_scene["durationInFrames"] == 50


def test_merge_emphasis_scenes_is_idempotent_on_rerun():
    # regression: re-merging against an already-merged plan should replace,
    # not stack, emphasis scenes
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,
            },
        ],
    }

    proposals = [
        {
            "windowId": "w0",
            "sceneId": "scene-001",
            "videoId": "001",
            "offsetInParentFrames": 500,
            "maxDurationInParentFrames": 400,
            "text": "key phrase",
            "reason": "central",
        }
    ]

    once = merge_emphasis_scenes(scene_plan, proposals)
    twice = merge_emphasis_scenes(once, proposals)

    emphasis_scenes = [s for s in twice["scenes"] if s["type"] == "emphasis"]
    assert len(emphasis_scenes) == 1


def test_merge_image_scenes_is_idempotent_on_rerun():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "id": "scene-001",
                "type": "presenter",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,
            },
        ],
    }

    proposals = [
        {
            "windowId": "w0",
            "sceneId": "scene-001",
            "videoId": "001",
            "offsetInParentFrames": 500,
            "maxDurationInParentFrames": 400,
            "assetId": "img-001",
            "caption": "a relevant diagram",
            "reason": "illustrates the point",
        }
    ]

    once = merge_image_scenes(scene_plan, proposals)
    twice = merge_image_scenes(once, proposals)

    image_scenes = [s for s in twice["scenes"] if s["type"] == "image"]
    assert len(image_scenes) == 1
