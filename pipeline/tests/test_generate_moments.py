from episode_context import NO_CONTEXT_TEXT
from generate_moments import (
    build_candidate_windows,
    cap_full_visual_ratio,
    chapter_for_absolute_frame,
    chapters_from_scene_plan,
    dedupe_overlapping_windows,
    format_storyboard_for_prompt,
    format_windows_for_prompt,
    is_comparison_grounded,
    is_diagram_grounded,
    is_grounded,
    is_terms_grounded,
    merge_moment_scenes,
    propose_moments,
)
from style import load_style


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


def test_is_diagram_grounded_accepts_labels_matching_source_words():
    diagram = {
        "nodes": [{"id": "n1", "label": "dependencies"}, {"id": "n2", "label": "modules"}],
        "edges": [{"from": "n1", "to": "n2"}],
        "layout": "horizontal",
    }

    assert is_diagram_grounded(diagram, "we can replace our dependencies of our modules easier")


def test_is_diagram_grounded_rejects_fabricated_labels():
    diagram = {
        "nodes": [{"id": "n1", "label": "Kubernetes"}, {"id": "n2", "label": "Istio"}],
        "edges": [{"from": "n1", "to": "n2"}],
        "layout": "horizontal",
    }

    assert not is_diagram_grounded(diagram, "we can replace our dependencies of our modules easier")


def test_is_diagram_grounded_rejects_empty_nodes():
    diagram = {"nodes": [], "edges": [], "layout": "horizontal"}

    assert not is_diagram_grounded(diagram, "some source text")


def test_is_comparison_grounded_accepts_both_sides_matching_source_words():
    comparison = {"left": "monolith", "right": "microservices"}

    assert is_comparison_grounded(
        comparison, "we moved from a monolith to microservices last year"
    )


def test_is_comparison_grounded_rejects_fabricated_left_side():
    comparison = {"left": "Kubernetes", "right": "microservices"}

    assert not is_comparison_grounded(
        comparison, "we moved from a monolith to microservices last year"
    )


def test_is_comparison_grounded_rejects_fabricated_right_side():
    comparison = {"left": "monolith", "right": "Istio"}

    assert not is_comparison_grounded(
        comparison, "we moved from a monolith to microservices last year"
    )


def test_is_comparison_grounded_rejects_missing_side():
    assert not is_comparison_grounded(
        {"left": "monolith"}, "we moved from a monolith to microservices last year"
    )


def test_is_comparison_grounded_rejects_non_dict():
    assert not is_comparison_grounded(None, "some source text")


def test_is_diagram_grounded_rejects_more_than_max_nodes():
    diagram = {
        "nodes": [{"id": f"n{i}", "label": "dependencies"} for i in range(7)],
        "edges": [],
        "layout": "horizontal",
    }

    assert not is_diagram_grounded(diagram, "dependencies dependencies dependencies")


def test_is_diagram_grounded_rejects_more_than_max_edges():
    nodes = [{"id": f"n{i}", "label": "dependencies"} for i in range(2)]
    diagram = {
        "nodes": nodes,
        "edges": [{"from": "n0", "to": "n1"} for _ in range(9)],
        "layout": "horizontal",
    }

    assert not is_diagram_grounded(diagram, "dependencies dependencies")


def test_is_diagram_grounded_rejects_edge_referencing_unknown_node():
    diagram = {
        "nodes": [{"id": "n1", "label": "dependencies"}],
        "edges": [{"from": "n1", "to": "n99"}],
        "layout": "horizontal",
    }

    assert not is_diagram_grounded(diagram, "we can replace our dependencies")


def test_is_terms_grounded_accepts_terms_matching_source_words():
    terms = [
        {"text": "dependencies", "level": "muted"},
        {"text": "modules", "level": "primary"},
    ]

    assert is_terms_grounded(terms, "we can replace our dependencies of our modules easier")


def test_is_terms_grounded_rejects_fabricated_term():
    terms = [
        {"text": "dependencies", "level": "muted"},
        {"text": "Kubernetes", "level": "accent"},
    ]

    assert not is_terms_grounded(terms, "we can replace our dependencies of our modules easier")


def test_is_terms_grounded_rejects_empty_list():
    assert not is_terms_grounded([], "some source text")


def test_is_terms_grounded_rejects_more_than_max_terms():
    terms = [{"text": "dependencies", "level": "muted"} for _ in range(5)]

    assert not is_terms_grounded(terms, "dependencies dependencies dependencies dependencies dependencies")


def test_is_terms_grounded_rejects_term_missing_text():
    terms = [{"level": "muted"}]

    assert not is_terms_grounded(terms, "some source text")


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


def test_chapters_from_scene_plan_orders_by_timeline_start():
    scene_plan = {
        "fps": 30,
        "scenes": [
            {"type": "title", "id": "t1", "text": "Second Chapter", "timelineStartFrame": 500, "durationInFrames": 60},
            {"type": "title", "id": "t0", "text": "First Chapter", "timelineStartFrame": 100, "durationInFrames": 60},
        ],
    }

    chapters = chapters_from_scene_plan(scene_plan)

    assert [c["text"] for c in chapters] == ["First Chapter", "Second Chapter"]
    assert chapters[0]["chapterId"] == "c0"
    assert chapters[0]["start"] == 100
    assert chapters[0]["end"] == 500
    assert chapters[1]["end"] is None  # last chapter is open-ended


def test_chapters_from_scene_plan_returns_empty_when_no_titles():
    scene_plan = {"fps": 30, "scenes": [{"type": "presenter", "id": "p1", "timelineStartFrame": 0, "durationInFrames": 900}]}

    assert chapters_from_scene_plan(scene_plan) == []


def test_chapter_for_absolute_frame_finds_containing_chapter():
    chapters = [
        {"chapterId": "c0", "text": "First", "start": 100, "end": 500},
        {"chapterId": "c1", "text": "Second", "start": 500, "end": None},
    ]

    assert chapter_for_absolute_frame(chapters, 50) is None  # before first chapter (intro)
    assert chapter_for_absolute_frame(chapters, 100) == "c0"  # exactly at start
    assert chapter_for_absolute_frame(chapters, 499) == "c0"
    assert chapter_for_absolute_frame(chapters, 500) == "c1"  # boundary belongs to next chapter
    assert chapter_for_absolute_frame(chapters, 99999) == "c1"  # last chapter is open-ended


def test_build_candidate_windows_assigns_chapter_id():
    scene_plan = {
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
            },
            {"type": "title", "id": "t0", "text": "The Chapter", "timelineStartFrame": 0, "durationInFrames": 60},
        ],
    }

    transcript = {
        "segments": [
            {"source": "a.mp4", "start": 20.0, "end": 22.0, "text": "late important point"},
        ]
    }

    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}]}

    candidates = build_candidate_windows(scene_plan, transcript, manifest)

    assert len(candidates) == 1
    assert candidates[0]["chapterId"] == "c0"


def test_format_windows_for_prompt_groups_by_chapter_heading():
    chapters = [{"chapterId": "c0", "text": "Dependency Injection", "start": 0, "end": None}]
    candidates = [
        {"windowId": "w0", "text": "first window text", "chapterId": "c0"},
        {"windowId": "w1", "text": "second window text", "chapterId": None},
    ]

    formatted = format_windows_for_prompt(candidates, chapters)

    assert 'Chapter [c0] "Dependency Injection"' in formatted
    assert "(intro, before the first chapter)" in formatted
    assert "[w0]" in formatted
    assert "first window text" in formatted
    assert "[w1]" in formatted


def test_format_windows_for_prompt_works_without_chapters_argument():
    candidates = [{"windowId": "w0", "text": "some text", "chapterId": None}]

    formatted = format_windows_for_prompt(candidates)

    assert "[w0]" in formatted
    assert "some text" in formatted


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.last_prompt = None
        self.last_thinking = None

    def complete_json(self, prompt, thinking=True):
        self.last_prompt = prompt
        self.last_thinking = thinking
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


def _one_code_asset():
    return [{"id": "code-001", "filename": "Repository.java", "language": "java", "description": "a constructor injection example"}]


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


def test_format_storyboard_for_prompt_includes_chapter_headings_and_notes():
    chapters = [
        {"chapterId": "c0", "chapterText": "Intro", "notes": "Keep it simple."},
        {"chapterId": "c1", "chapterText": "The Fix", "notes": "A diagram fits best here."},
    ]

    formatted = format_storyboard_for_prompt(chapters)

    assert 'Chapter "Intro"' in formatted
    assert "Keep it simple." in formatted
    assert 'Chapter "The Fix"' in formatted
    assert "A diagram fits best here." in formatted


def test_format_storyboard_for_prompt_handles_empty_list():
    assert format_storyboard_for_prompt([]) == "(no storyboard reasoning available)"


def test_propose_moments_threads_storyboard_chapters_into_prompt():
    llm = _FakeLLMClient({"moments": []})

    propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}{storyboard}",
        storyboard_chapters=[
            {"chapterId": "c0", "chapterText": "Intro", "notes": "Favor restraint here."}
        ],
    )

    assert "Favor restraint here." in llm.last_prompt


def test_propose_moments_requests_thinking():
    # This call now reasons chapter-by-chapter before committing individual
    # window treatments — a harder task than judging one window in
    # isolation, so it needs the model's full reasoning the same way
    # generate_title_scenes.py's whole-episode call already does.
    llm = _FakeLLMClient({"moments": []})

    propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}",
    )

    assert llm.last_thinking is True


def test_propose_moments_substitutes_episode_context_into_prompt():
    llm = _FakeLLMClient({"moments": []})

    propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}{code_assets}{episode_context}",
        episode_context="Key concepts central to this episode: dependency injection",
    )

    assert "Key concepts central to this episode: dependency injection" in llm.last_prompt
    assert "{episode_context}" not in llm.last_prompt


def test_propose_moments_defaults_episode_context_when_omitted():
    llm = _FakeLLMClient({"moments": []})

    propose_moments(
        _scene_plan_with_one_long_scene(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        _no_assets(),
        llm,
        "{windows}{assets}{code_assets}{episode_context}",
    )

    assert "{episode_context}" not in llm.last_prompt
    assert NO_CONTEXT_TEXT in llm.last_prompt


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
    # min() of the two, not just "always use the fixed length." The scene
    # leaves 44 frames of room past the 18s (540f) threshold: 20 for the
    # narrow ceiling being tested, plus TRANSITION_FRAMES (24) reserved for
    # the presenter's own exit pad — enough that the ceiling itself, not
    # the transition-pad reservation, is what's under test here.
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "type": "presenter",
                "id": "scene-001",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 584,
                "sourceStartFrame": 0,
                "sourceEndFrame": 584,
            }
        ],
    }
    transcript = {
        "segments": [
            # falls within the eligible window ([540, 584) frames = [18.0s, 19.47s))
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


def test_propose_moments_clamps_duration_to_leave_room_for_transition_pad():
    # Regression test: a moment whose duration individually fits within
    # the parent scene must still be clamped further if offset + duration
    # + TRANSITION_FRAMES would overflow the parent — otherwise the
    # presenter's own slide-back-to-center animation (clamped to the
    # parent's durationInFrames in Episode.tsx's layoutWindowsForScene)
    # ends before the moment's content does, leaving content on screen
    # after the presenter has already returned to center.
    #
    # Scene is 570 frames. The eligible window starts at 540 (18s
    # threshold) leaving exactly 30 frames of raw remaining-scene room —
    # enough for the treatment's own fixed duration (90 for
    # bottom-callout would be clamped to 30 by the existing ceiling logic
    # regardless, so use a treatment whose fixed length is small enough
    # to fit the raw 30-frame room but not the padded room). No treatment
    # here is under 30 frames by default, so this exercises the case via
    # the eligible window's own ceiling landing at exactly 30 (room
    # without the pad) — the fix must reduce it further to leave 24
    # frames (TRANSITION_FRAMES) for the exit pad, i.e. to 6.
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "type": "presenter",
                "id": "scene-001",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 570,
                "sourceStartFrame": 0,
                "sourceEndFrame": 570,
            }
        ],
    }
    transcript = {
        "segments": [
            # falls within the eligible window ([540, 570) frames = [18.0s, 19.0s))
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
    proposal = proposals[0]
    offset = proposal["offsetInParentFrames"]
    duration = proposal["maxDurationInParentFrames"]

    # The padded window (what the presenter's slide-back animation needs)
    # must fit within the parent scene's own duration.
    assert offset + duration + 24 <= scene_plan["scenes"][0]["durationInFrames"]


def test_propose_moments_drops_proposal_with_no_room_for_transition_pad():
    # If even the minimum possible content can't fit alongside the
    # transition pad, the proposal must be dropped entirely rather than
    # kept with a zero or negative duration.
    scene_plan = {
        "fps": 30,
        "scenes": [
            {
                "type": "presenter",
                "id": "scene-001",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 560,  # only 20 frames of room past the 540f threshold
                "sourceStartFrame": 0,
                "sourceEndFrame": 560,
            }
        ],
    }
    transcript = {
        "segments": [
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

    assert proposals == []


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


def test_propose_moments_accepts_valid_side_code():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-code",
                    "codeAssetId": "code-001",
                    "presenterSide": "left",
                    "reason": "shows the constructor injection being discussed",
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
        "{windows}{assets}{code_assets}",
        code_assets=_one_code_asset(),
    )

    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "side-code"
    assert proposals[0]["codeAssetId"] == "code-001"
    assert proposals[0]["caption"] == "a constructor injection example"
    assert proposals[0]["presenterSide"] == "left"


def test_propose_moments_rejects_unknown_code_asset_id():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-code",
                    "codeAssetId": "code-999",
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
        _no_assets(),
        llm,
        "{windows}{assets}{code_assets}",
        code_assets=_one_code_asset(),
    )

    assert proposals == []


def test_propose_moments_rejects_side_code_without_presenter_side():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-code",
                    "codeAssetId": "code-001",
                    "reason": "shows the constructor injection being discussed",
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
        "{windows}{assets}{code_assets}",
        code_assets=_one_code_asset(),
    )

    assert proposals == []


def test_propose_moments_accepts_valid_side_diagram():
    # _transcript_with_late_segment's text is "the important key idea" —
    # labels below share words/stems with it ("important", "idea").
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-diagram",
                    "diagram": {
                        "nodes": [
                            {"id": "n1", "label": "important idea"},
                            {"id": "n2", "label": "key idea"},
                        ],
                        "edges": [{"from": "n1", "to": "n2", "label": "leads to"}],
                        "layout": "vertical",
                    },
                    "presenterSide": "left",
                    "reason": "shows how the idea builds",
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
        "{windows}{assets}{code_assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "side-diagram"
    assert proposals[0]["diagram"]["nodes"] == [
        {"id": "n1", "label": "important idea"},
        {"id": "n2", "label": "key idea"},
    ]
    assert proposals[0]["presenterSide"] == "left"


def test_propose_moments_rejects_side_diagram_with_dangling_edge():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-diagram",
                    "diagram": {
                        "nodes": [{"id": "n1", "label": "important idea"}],
                        # references a node id that doesn't exist
                        "edges": [{"from": "n1", "to": "n2"}],
                        "layout": "vertical",
                    },
                    "presenterSide": "left",
                    "reason": "shows the idea",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_rejects_side_diagram_exceeding_node_cap():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-diagram",
                    "diagram": {
                        "nodes": [{"id": f"n{i}", "label": "important idea"} for i in range(7)],
                        "edges": [],
                        "layout": "vertical",
                    },
                    "presenterSide": "left",
                    "reason": "too many boxes",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_rejects_side_diagram_with_fabricated_labels():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-diagram",
                    "diagram": {
                        # "Kubernetes"/"Istio" share no words or stems with
                        # the transcript text "the important key idea"
                        "nodes": [
                            {"id": "n1", "label": "Kubernetes"},
                            {"id": "n2", "label": "Istio"},
                        ],
                        "edges": [{"from": "n1", "to": "n2"}],
                        "layout": "horizontal",
                    },
                    "presenterSide": "left",
                    "reason": "hallucinated infrastructure diagram",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_accepts_side_text_with_title_style():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-text",
                    "text": "the important key idea",
                    "sideTextStyle": "title",
                    "presenterSide": "left",
                    "reason": "announces the chapter's own concept",
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
        "{windows}{assets}{code_assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["sideTextStyle"] == "title"


def test_propose_moments_side_text_defaults_style_to_quote_when_omitted():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-text",
                    "text": "the important key idea",
                    "presenterSide": "left",
                    "reason": "a claim",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals[0]["sideTextStyle"] == "quote"


def test_propose_moments_rejects_side_text_with_invalid_style():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-text",
                    "text": "the important key idea",
                    "sideTextStyle": "dramatic",
                    "presenterSide": "left",
                    "reason": "invalid style value",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_accepts_valid_side_terms():
    # _transcript_with_late_segment's text is "the important key idea" —
    # terms below share words/stems with it.
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-terms",
                    "terms": [
                        {"text": "important", "level": "muted"},
                        {"text": "key idea", "level": "primary"},
                    ],
                    "presenterSide": "right",
                    "reason": "names the related concepts together",
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
        "{windows}{assets}{code_assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "side-terms"
    assert proposals[0]["terms"] == [
        {"text": "important", "level": "muted"},
        {"text": "key idea", "level": "primary"},
    ]
    assert proposals[0]["presenterSide"] == "right"


def test_propose_moments_rejects_side_terms_missing_presenter_side():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-terms",
                    "terms": [{"text": "important", "level": "primary"}],
                    "reason": "missing presenterSide",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_rejects_side_terms_with_invalid_level():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-terms",
                    "terms": [{"text": "important", "level": "bold"}],
                    "presenterSide": "left",
                    "reason": "invalid level value",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_rejects_side_terms_exceeding_max_terms():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-terms",
                    "terms": [{"text": "important", "level": "muted"} for _ in range(5)],
                    "presenterSide": "left",
                    "reason": "too many terms",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_rejects_side_terms_with_fabricated_term():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "side-terms",
                    "terms": [
                        {"text": "important", "level": "muted"},
                        {"text": "Kubernetes", "level": "accent"},
                    ],
                    "presenterSide": "left",
                    "reason": "Kubernetes is never mentioned",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_accepts_valid_comparison():
    # _transcript_with_late_segment's text is "the important key idea" —
    # both sides below share a word/stem with it.
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "comparison",
                    "comparison": {"left": "important", "right": "key idea"},
                    "reason": "draws a direct two-way contrast",
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
        "{windows}{assets}{code_assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "comparison"
    assert proposals[0]["comparison"] == {"left": "important", "right": "key idea"}
    assert proposals[0]["presenterSide"] is None


def test_propose_moments_rejects_comparison_with_fabricated_side():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "comparison",
                    "comparison": {"left": "important", "right": "Kubernetes"},
                    "reason": "Kubernetes is never mentioned",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_rejects_comparison_missing_side():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "comparison",
                    "comparison": {"left": "important"},
                    "reason": "missing right side",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_accepts_valid_full_visual_image():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "full-visual",
                    "fullVisualKind": "image",
                    "assetId": "img-001",
                    "reason": "the wiring needs to fill the screen to be legible",
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
        "{windows}{assets}{code_assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "full-visual"
    assert proposals[0]["fullVisualKind"] == "image"
    assert proposals[0]["assetId"] == "img-001"
    assert proposals[0]["caption"] == "a relevant diagram"
    assert proposals[0]["presenterSide"] is None


def test_propose_moments_rejects_full_visual_image_with_unknown_asset_id():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "full-visual",
                    "fullVisualKind": "image",
                    "assetId": "img-999",
                    "reason": "unknown asset",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_accepts_valid_full_visual_diagram():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "full-visual",
                    "fullVisualKind": "diagram",
                    "diagram": {
                        "nodes": [
                            {"id": "n1", "label": "important idea"},
                            {"id": "n2", "label": "key idea"},
                        ],
                        "edges": [{"from": "n1", "to": "n2", "label": "leads to"}],
                        "layout": "vertical",
                    },
                    "reason": "the relationship needs the whole frame",
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
        "{windows}{assets}{code_assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "full-visual"
    assert proposals[0]["fullVisualKind"] == "diagram"
    assert proposals[0]["presenterSide"] is None


def test_propose_moments_rejects_full_visual_diagram_with_fabricated_labels():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "full-visual",
                    "fullVisualKind": "diagram",
                    "diagram": {
                        "nodes": [
                            {"id": "n1", "label": "Kubernetes"},
                            {"id": "n2", "label": "Istio"},
                        ],
                        "edges": [{"from": "n1", "to": "n2"}],
                        "layout": "horizontal",
                    },
                    "reason": "hallucinated infrastructure diagram",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_accepts_valid_full_visual_text():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "full-visual",
                    "fullVisualKind": "text",
                    "text": "the important key idea",
                    "reason": "the claim deserves the whole screen",
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
        "{windows}{assets}{code_assets}",
    )

    assert len(proposals) == 1
    assert proposals[0]["treatment"] == "full-visual"
    assert proposals[0]["fullVisualKind"] == "text"
    assert proposals[0]["text"] == "the important key idea"
    assert proposals[0]["presenterSide"] is None


def test_propose_moments_rejects_full_visual_text_ungrounded():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "full-visual",
                    "fullVisualKind": "text",
                    "text": "the moon landing was faked",
                    "reason": "fabricated claim",
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
        "{windows}{assets}{code_assets}",
    )

    assert proposals == []


def test_propose_moments_rejects_full_visual_missing_kind():
    llm = _FakeLLMClient(
        {
            "moments": [
                {
                    "windowId": "w0",
                    "treatment": "full-visual",
                    "text": "the important key idea",
                    "reason": "missing fullVisualKind",
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
        "{windows}{assets}{code_assets}",
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


def test_merge_moment_scenes_side_code_stores_code_asset_and_caption():
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
            "maxDurationInParentFrames": 240,
            "treatment": "side-code",
            "codeAssetId": "code-001",
            "caption": "a constructor injection example",
            "presenterSide": "left",
            "reason": "shows the constructor injection being discussed",
        }
    ]

    result = merge_moment_scenes(scene_plan, proposals)
    moment_scene = next(s for s in result["scenes"] if s["type"] == "moment")

    assert moment_scene["codeAssetId"] == "code-001"
    assert moment_scene["caption"] == "a constructor injection example"
    assert moment_scene["presenterSide"] == "left"


def test_merge_moment_scenes_side_diagram_stores_diagram_data():
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

    diagram = {
        "nodes": [{"id": "n1", "label": "Client"}, {"id": "n2", "label": "Server"}],
        "edges": [{"from": "n1", "to": "n2", "label": "request"}],
        "layout": "horizontal",
    }

    proposals = [
        {
            "windowId": "w0",
            "sceneId": "scene-001",
            "videoId": "001",
            "offsetInParentFrames": 500,
            "maxDurationInParentFrames": 180,
            "treatment": "side-diagram",
            "diagram": diagram,
            "presenterSide": "right",
            "reason": "shows client-server relationship",
        }
    ]

    result = merge_moment_scenes(scene_plan, proposals)
    moment_scene = next(s for s in result["scenes"] if s["type"] == "moment")

    assert moment_scene["diagram"] == diagram
    assert moment_scene["presenterSide"] == "right"


def test_merge_moment_scenes_side_terms_stores_terms():
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

    terms = [
        {"text": "Value Objects", "level": "muted"},
        {"text": "Aggregates", "level": "primary"},
        {"text": "Entities", "level": "accent"},
    ]

    proposals = [
        {
            "windowId": "w0",
            "sceneId": "scene-001",
            "videoId": "001",
            "offsetInParentFrames": 500,
            "maxDurationInParentFrames": 180,
            "treatment": "side-terms",
            "terms": terms,
            "presenterSide": "left",
            "reason": "names the related DDD building blocks together",
        }
    ]

    result = merge_moment_scenes(scene_plan, proposals)
    moment_scene = next(s for s in result["scenes"] if s["type"] == "moment")

    assert moment_scene["terms"] == terms
    assert moment_scene["presenterSide"] == "left"


def test_merge_moment_scenes_comparison_stores_comparison_and_no_side():
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
            "maxDurationInParentFrames": 150,
            "treatment": "comparison",
            "comparison": {"left": "Monolith", "right": "Microservices"},
            "presenterSide": None,
            "reason": "the episode's central contrast",
        }
    ]

    result = merge_moment_scenes(scene_plan, proposals)
    moment_scene = next(s for s in result["scenes"] if s["type"] == "moment")

    assert moment_scene["comparison"] == {"left": "Monolith", "right": "Microservices"}
    assert "presenterSide" not in moment_scene


def test_merge_moment_scenes_side_text_stores_style_when_present():
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
            "maxDurationInParentFrames": 150,
            "treatment": "side-text",
            "text": "Domain-Driven Design",
            "sideTextStyle": "title",
            "presenterSide": "left",
            "reason": "announces the chapter's concept",
        }
    ]

    result = merge_moment_scenes(scene_plan, proposals)
    moment_scene = next(s for s in result["scenes"] if s["type"] == "moment")

    assert moment_scene["sideTextStyle"] == "title"


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


def test_merge_moment_scenes_full_visual_stores_kind_and_text():
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
            "maxDurationInParentFrames": 300,
            "treatment": "full-visual",
            "fullVisualKind": "text",
            "text": "a strong claim",
            "presenterSide": None,
            "reason": "deserves the whole screen",
        }
    ]

    result = merge_moment_scenes(scene_plan, proposals)
    moment_scene = next(s for s in result["scenes"] if s["type"] == "moment")

    assert moment_scene["fullVisualKind"] == "text"
    assert moment_scene["text"] == "a strong claim"
    assert "presenterSide" not in moment_scene


def _side_text_proposal(window_id, scene_id="scene-001", offset=0):
    return {
        "windowId": window_id,
        "sceneId": scene_id,
        "videoId": "001",
        "offsetInParentFrames": offset,
        "maxDurationInParentFrames": 150,
        "treatment": "side-text",
        "text": "a phrase",
        "presenterSide": "left",
        "reason": "central point",
    }


def _full_visual_proposal(window_id, scene_id="scene-001", offset=0):
    return {
        "windowId": window_id,
        "sceneId": scene_id,
        "videoId": "001",
        "offsetInParentFrames": offset,
        "maxDurationInParentFrames": 300,
        "treatment": "full-visual",
        "fullVisualKind": "text",
        "text": "a strong claim",
        "presenterSide": None,
        "reason": "deserves the whole screen",
    }


def test_cap_full_visual_ratio_keeps_at_least_one_with_no_side_moments():
    style = load_style()
    proposals = [_full_visual_proposal("w0")]

    kept = cap_full_visual_ratio(proposals, style)

    assert len(kept) == 1


def test_cap_full_visual_ratio_drops_full_visual_past_the_ratio_cap():
    style = dict(load_style())
    style["moments"] = dict(style["moments"])
    style["moments"]["fullVisualMaxRatioToSideMoments"] = 0.25

    # 4 side moments -> cap is 1 full-visual; a 2nd one should be dropped
    proposals = [
        _side_text_proposal("w0", offset=0),
        _side_text_proposal("w1", offset=200),
        _side_text_proposal("w2", offset=400),
        _side_text_proposal("w3", offset=600),
        _full_visual_proposal("w4", offset=800),
        _full_visual_proposal("w5", offset=1000),
    ]

    kept = cap_full_visual_ratio(proposals, style)

    full_visual_kept = [p for p in kept if p["treatment"] == "full-visual"]
    assert len(full_visual_kept) == 1
    assert full_visual_kept[0]["windowId"] == "w4"
    # side moments are untouched by this cap
    assert sum(1 for p in kept if p["treatment"] == "side-text") == 4


def test_cap_full_visual_ratio_leaves_non_full_visual_proposals_untouched():
    style = load_style()
    proposals = [_side_text_proposal("w0")]

    kept = cap_full_visual_ratio(proposals, style)

    assert kept == proposals
