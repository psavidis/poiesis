from generate_moments import (
    build_candidate_windows,
    dedupe_overlapping_windows,
    is_grounded,
    merge_moment_scenes,
    propose_moments,
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


def test_propose_moments_accepts_grounded_bottom_callout():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "bottom-callout",
                    "text": "the important key idea",
                    "reason": "central point",
                }
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "bottom-callout"
    assert proposals[0]["text"] == "the important key idea"
    assert proposals[0]["presenterSide"] is None


def test_propose_moments_clamps_max_duration_to_the_real_rendered_duration():
    # regression: a proposal's maxDurationInParentFrames used to be left as
    # the raw eligible-window ceiling (here, 900 - 540 = 360 frames — the
    # scene's remaining room after the 18s monotony threshold), not the
    # real ~90-frame bottom-callout duration that actually renders. Human
    # edits via the preview app's drag-to-resize read/write this same
    # field, so leaving it un-clamped meant the UI showed a wildly
    # oversized block and any edit to it was silently discarded by
    # merge_moment_scenes' own re-clamp on save.
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "bottom-callout",
                    "text": "the important key idea",
                    "reason": "central point",
                }
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["maxDurationInParentFrames"] == 90


def test_propose_moments_max_duration_stays_below_a_narrow_window_ceiling():
    # when the eligible window's own ceiling is narrower than the
    # treatment's fixed length, the clamp must not WIDEN it back up —
    # min() of the two, not just "always use the fixed length."
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "type": "presenter",
                "id": "scene-001",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 560,  # only 20 frames of room past the 18s (540f) threshold
                "sourceStartFrame": 0,
                "sourceEndFrame": 560,
            }
        ],
    }
    transcript = {
        "segments": [
            # falls within the eligible window ([540, 560) frames = [18.0s, 18.67s))
            {"source": "a.mp4", "start": 18.1, "end": 18.4, "text": "the important key idea"},
        ]
    }

    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "bottom-callout",
                    "text": "the important key idea",
                    "reason": "central point",
                }
            ]
        }
    )

    proposals = propose_moments(
        scene_plan,
        transcript,
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["maxDurationInParentFrames"] == 20


def test_propose_moments_rejects_ungrounded_bottom_callout():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "bottom-callout",
                    "text": "completely unrelated fabricated statement",
                    "reason": "made up",
                }
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert proposals == []


def test_propose_moments_rejects_unknown_window_id():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w999",
                    "treatment": "bottom-callout",
                    "text": "the important key idea",
                    "reason": "central point",
                }
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert proposals == []


def test_propose_moments_accepts_grounded_side_text_with_valid_side():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-text",
                    "text": "the important key idea",
                    "presenterSide": "left",
                    "reason": "deserves weight",
                }
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "side-text"
    assert proposals[0]["presenterSide"] == "left"


def test_propose_moments_rejects_side_text_without_presenter_side():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-text",
                    "text": "the important key idea",
                    "reason": "deserves weight",
                }
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert proposals == []


def test_propose_moments_accepts_valid_side_image():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-image",
                    "assetId": "img-001",
                    "presenterSide": "right",
                    "reason": "illustrates the point",
                }
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _one_asset(),
        llm,
        "{windows}{assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "side-image"
    assert proposals[0]["assetId"] == "img-001"
    assert proposals[0]["caption"] == "a relevant diagram"
    assert proposals[0]["presenterSide"] == "right"


def test_propose_moments_rejects_unknown_asset_id():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-image",
                    "assetId": "img-999",
                    "presenterSide": "left",
                    "reason": "hallucinated",
                }
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _one_asset(),
        llm,
        "{windows}{assets}",
    )

    assert proposals == []


def test_propose_moments_rejects_side_image_without_presenter_side():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-image",
                    "assetId": "img-001",
                    "reason": "illustrates the point",
                }
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _one_asset(),
        llm,
        "{windows}{assets}",
    )

    assert proposals == []


def test_propose_moments_ignores_unrecognized_treatment():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "fullscreen-explosion",
                    "text": "the important key idea",
                    "reason": "made up treatment",
                }
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert proposals == []


def test_propose_moments_does_not_double_propose_same_window():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "bottom-callout",
                    "text": "the important key idea",
                    "reason": "central point",
                },
                {
                    "windowId": "w0",
                    "treatment": "side-image",
                    "assetId": "img-001",
                    "presenterSide": "left",
                    "reason": "also relevant",
                },
            ]
        }
    )

    proposals = propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _one_asset(),
        llm,
        "{windows}{assets}",
    )

    # only the first-seen proposal for a claimed window should win
    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "bottom-callout"


def test_dedupe_overlapping_windows_drops_moment_overlapping_earlier_one():
    proposals = [
        {
            "sceneId": "scene-001", "windowId": "w0", "treatment": "bottom-callout",
            "offsetInParentFrames": 0, "maxDurationInParentFrames": 90,
        },
        {
            # starts within w0's trailing transition pad (90 + 24 = 114)
            "sceneId": "scene-001", "windowId": "w1", "treatment": "bottom-callout",
            "offsetInParentFrames": 100, "maxDurationInParentFrames": 90,
        },
    ]

    kept = dedupe_overlapping_windows(proposals)

    assert [p["windowId"] for p in kept] == ["w0"]


def test_dedupe_overlapping_windows_keeps_well_spaced_moments_same_parent():
    proposals = [
        {
            "sceneId": "scene-001", "windowId": "w0", "treatment": "bottom-callout",
            "offsetInParentFrames": 0, "maxDurationInParentFrames": 90,
        },
        {
            "sceneId": "scene-001", "windowId": "w1", "treatment": "bottom-callout",
            "offsetInParentFrames": 500, "maxDurationInParentFrames": 90,
        },
    ]

    kept = dedupe_overlapping_windows(proposals)

    assert [p["windowId"] for p in kept] == ["w0", "w1"]


def test_dedupe_overlapping_windows_ignores_different_parents():
    proposals = [
        {
            "sceneId": "scene-001", "windowId": "w0", "treatment": "bottom-callout",
            "offsetInParentFrames": 0, "maxDurationInParentFrames": 90,
        },
        {
            "sceneId": "scene-002", "windowId": "w1", "treatment": "bottom-callout",
            "offsetInParentFrames": 0, "maxDurationInParentFrames": 90,
        },
    ]

    kept = dedupe_overlapping_windows(proposals)

    assert [p["windowId"] for p in kept] == ["w0", "w1"]


def test_merge_moment_scenes_inserts_overlay_with_presenter_side():
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
            "treatment": "side-text",
            "text": "key phrase",
            "presenterSide": "left",
            "reason": "central",
        }
    ]

    result = merge_moment_scenes(scene_plan, proposals)
    scenes = result["scenes"]

    assert [s["id"] for s in scenes] == ["scene-001", "scene-moment-0", "scene-002"]

    parent = scenes[0]
    assert "layout" not in parent

    moment_scene = scenes[1]
    assert moment_scene["type"] == "moment"
    assert moment_scene["treatment"] == "side-text"
    assert moment_scene["presenterSide"] == "left"
    assert moment_scene["parentSceneId"] == "scene-001"
    assert moment_scene["offsetInParentFrames"] == 500
    # merge_moment_scenes trusts maxDurationInParentFrames directly (it no
    # longer re-derives via duration_for_treatment) — propose_moments is
    # what clamps it to the treatment's real length, once, before this ever
    # runs. This proposal's 400 is what a human-edited moments.json would
    # look like after dragging a moment longer than its default.
    assert moment_scene["durationInFrames"] == 400


def test_merge_moment_scenes_clamps_duration_to_window_end():
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
            # merge_moment_scenes trusts this directly now (no re-derivation
            # via duration_for_treatment) — this value stands in for what
            # propose_moments would have already clamped a narrow window
            # down to, below bottom-callout's own default of 90.
            "maxDurationInParentFrames": 50,
            "treatment": "bottom-callout",
            "text": "key phrase",
            "presenterSide": None,
            "reason": "central",
        }
    ]

    result = merge_moment_scenes(scene_plan, proposals)
    moment_scene = next(s for s in result["scenes"] if s["type"] == "moment")

    assert moment_scene["durationInFrames"] == 50


def test_merge_moment_scenes_no_proposals_leaves_plan_unchanged():
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

    result = merge_moment_scenes(scene_plan, [])

    assert result["scenes"] == scene_plan["scenes"]


def test_merge_moment_scenes_side_image_stores_asset_and_caption():
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
            "treatment": "side-image",
            "assetId": "img-001",
            "caption": "a relevant diagram",
            "presenterSide": "right",
            "reason": "illustrates the point",
        }
    ]

    result = merge_moment_scenes(scene_plan, proposals)
    moment_scene = next(s for s in result["scenes"] if s["type"] == "moment")

    assert moment_scene["assetId"] == "img-001"
    assert moment_scene["caption"] == "a relevant diagram"
    assert moment_scene["presenterSide"] == "right"


def test_merge_moment_scenes_is_idempotent_on_rerun():
    # regression: re-merging against an already-merged plan should replace,
    # not stack, moment scenes
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
            "treatment": "side-text",
            "text": "key phrase",
            "presenterSide": "left",
            "reason": "central",
        }
    ]

    once = merge_moment_scenes(scene_plan, proposals)
    twice = merge_moment_scenes(once, proposals)

    moment_scenes = [s for s in twice["scenes"] if s["type"] == "moment"]
    assert len(moment_scenes) == 1
    assert moment_scenes[0]["presenterSide"] == "left"
