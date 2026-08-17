from generate_cut_candidates import (
    MIN_PAUSE_SECONDS,
    PAD_SECONDS,
    compute_overridden_cut_fields,
    find_pause_gaps,
    preserve_status_and_overrides,
    propose_cuts,
    resolve_candidates_for_scene,
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


def _words(*pairs):
    return [{"word": w, "start": s, "end": e} for w, s, e in pairs]


# --- find_pause_gaps ---


def test_find_pause_gaps_detects_a_gap_above_the_threshold():
    segments = [
        {
            "source": "a.mp4",
            "start": 0.0,
            "end": 5.0,
            "words": _words(("hello", 0.0, 0.5), ("world", 2.5, 3.0)),
        }
    ]

    gaps = find_pause_gaps(segments)

    assert gaps == [{"gapStartSeconds": 0.5, "gapEndSeconds": 2.5}]


def test_find_pause_gaps_ignores_a_gap_below_the_threshold():
    segments = [
        {
            "source": "a.mp4",
            "start": 0.0,
            "end": 5.0,
            "words": _words(("hello", 0.0, 0.5), ("world", 0.5 + MIN_PAUSE_SECONDS - 0.1, 1.0)),
        }
    ]

    gaps = find_pause_gaps(segments)

    assert gaps == []


def test_find_pause_gaps_falls_back_to_segment_bounds_without_word_timing():
    segments = [
        {"source": "a.mp4", "start": 0.0, "end": 1.0, "text": "hello"},
        {"source": "a.mp4", "start": 3.0, "end": 4.0, "text": "world"},
    ]

    gaps = find_pause_gaps(segments)

    assert gaps == [{"gapStartSeconds": 1.0, "gapEndSeconds": 3.0}]


def test_find_pause_gaps_detects_a_gap_spanning_a_segment_boundary():
    segments = [
        {"source": "a.mp4", "start": 0.0, "end": 1.0, "words": _words(("hi", 0.0, 1.0))},
        {"source": "a.mp4", "start": 3.5, "end": 4.5, "words": _words(("there", 3.5, 4.5))},
    ]

    gaps = find_pause_gaps(segments)

    assert gaps == [{"gapStartSeconds": 1.0, "gapEndSeconds": 3.5}]


# --- resolve_candidates_for_scene ---


def test_resolve_candidates_for_scene_converts_and_pads_a_gap():
    scene = _presenter_scene()
    segments = [
        {
            "source": "a.mp4",
            "start": 0.0,
            "end": 10.0,
            "words": _words(("hello", 0.0, 1.0), ("world", 3.0, 3.5)),
        }
    ]

    candidates = resolve_candidates_for_scene(scene, segments, fps=30)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["sceneId"] == "scene-001"
    assert candidate["videoId"] == "001"
    # gap is [1.0, 3.0]s, padded by PAD_SECONDS on each side -> [1.2, 2.8]s @ 30fps
    assert candidate["cutStartFrame"] == int((1.0 + PAD_SECONDS) * 30)
    assert candidate["cutEndFrame"] == int((3.0 - PAD_SECONDS) * 30)
    assert candidate["status"] == "pending"
    assert candidate["overriddenFields"] == []


def test_resolve_candidates_for_scene_clips_to_the_scenes_own_source_bounds():
    # Scene only covers source frames [60, 300) (60 = 2s @ 30fps) — a pause
    # detected before that (already excluded by analyze_speech_bounds's own
    # lead-in trim) must not be double-proposed here.
    scene = _presenter_scene({"sourceStartFrame": 60, "sourceEndFrame": 300})
    segments = [
        {
            "source": "a.mp4",
            "start": 0.0,
            "end": 10.0,
            "words": _words(("hello", 0.0, 0.5), ("world", 5.0, 5.5)),
        }
    ]

    candidates = resolve_candidates_for_scene(scene, segments, fps=30)

    assert len(candidates) == 1
    assert candidates[0]["cutStartFrame"] >= 60


def test_resolve_candidates_for_scene_drops_a_gap_entirely_before_scene_start():
    scene = _presenter_scene({"sourceStartFrame": 200, "sourceEndFrame": 300})
    segments = [
        {
            "source": "a.mp4",
            "start": 0.0,
            "end": 10.0,
            "words": _words(("hello", 0.0, 0.5), ("world", 3.0, 3.5)),
        }
    ]

    candidates = resolve_candidates_for_scene(scene, segments, fps=30)

    assert candidates == []


# --- propose_cuts ---


def test_propose_cuts_only_scopes_presenter_scenes():
    scene_plan = {
        "fps": 30,
        "scenes": [
            _presenter_scene(),
            {"id": "title-1", "type": "title", "text": "x", "timelineStartFrame": 0, "durationInFrames": 60},
        ],
    }
    transcript = {
        "segments": [
            {
                "source": "a.mp4",
                "start": 0.0,
                "end": 10.0,
                "words": _words(("hello", 0.0, 0.5), ("world", 3.0, 3.5)),
            }
        ]
    }
    manifest = _manifest_single_video()

    proposals = propose_cuts(scene_plan, transcript, manifest)

    assert len(proposals) == 1
    assert proposals[0]["sceneId"] == "scene-001"


def test_propose_cuts_scopes_segments_to_the_right_video_by_filename():
    scene_plan = {
        "fps": 30,
        "scenes": [
            _presenter_scene({"id": "scene-001", "videoId": "001"}),
            _presenter_scene({"id": "scene-002", "videoId": "002", "timelineStartFrame": 300}),
        ],
    }
    transcript = {
        "segments": [
            {
                "source": "a.mp4",
                "start": 0.0,
                "end": 10.0,
                "words": _words(("hello", 0.0, 0.5), ("world", 3.0, 3.5)),
            },
            {
                "source": "b.mp4",
                "start": 0.0,
                "end": 10.0,
                "words": _words(("foo", 0.0, 0.5), ("bar", 0.7, 1.0)),
            },
        ]
    }
    manifest = {"videos": [{"id": "001", "filename": "a.mp4"}, {"id": "002", "filename": "b.mp4"}]}

    proposals = propose_cuts(scene_plan, transcript, manifest)

    assert len(proposals) == 1
    assert proposals[0]["sceneId"] == "scene-001"
    assert proposals[0]["videoId"] == "001"


# --- provenance: compute_overridden_cut_fields / preserve_status_and_overrides ---


def _cut(scene_id="scene-001", cut_start=100, cut_end=150, status="pending", overridden=None):
    return {
        "sceneId": scene_id,
        "videoId": "001",
        "cutStartFrame": cut_start,
        "cutEndFrame": cut_end,
        "durationSeconds": (cut_end - cut_start) / 30,
        "reason": "x",
        "status": status,
        "overriddenFields": overridden or [],
    }


def test_compute_overridden_cut_fields_detects_a_changed_boundary():
    old = _cut(cut_start=100, cut_end=150)
    new = _cut(cut_start=105, cut_end=150)

    assert compute_overridden_cut_fields(old, new) == ["cutStartFrame"]


def test_compute_overridden_cut_fields_no_changes_no_overrides():
    old = _cut()
    new = _cut()

    assert compute_overridden_cut_fields(old, new) == []


def test_preserve_status_and_overrides_carries_accepted_status_across_regeneration():
    old_cuts = [_cut(scene_id="scene-001", cut_start=100, cut_end=150, status="accepted")]
    # Fresh proposal batch: slightly different frames, same scene, starts pending.
    new_proposals = [_cut(scene_id="scene-001", cut_start=102, cut_end=148, status="pending")]

    result = preserve_status_and_overrides(old_cuts, new_proposals)

    assert result[0]["status"] == "accepted"


def test_preserve_status_and_overrides_carries_rejected_status_across_regeneration():
    old_cuts = [_cut(scene_id="scene-001", status="rejected")]
    new_proposals = [_cut(scene_id="scene-001", status="pending")]

    result = preserve_status_and_overrides(old_cuts, new_proposals)

    assert result[0]["status"] == "rejected"


def test_preserve_status_and_overrides_preserves_a_manually_nudged_boundary():
    old_cuts = [_cut(scene_id="scene-001", cut_start=999, cut_end=150, overridden=["cutStartFrame"])]
    new_proposals = [_cut(scene_id="scene-001", cut_start=100, cut_end=150, status="pending")]

    result = preserve_status_and_overrides(old_cuts, new_proposals)

    assert result[0]["cutStartFrame"] == 999
    assert "cutStartFrame" in result[0]["overriddenFields"]


def test_preserve_status_and_overrides_leaves_untouched_pending_cuts_free_to_change():
    # An old cut with no overrides and still-pending status has nothing to
    # protect — the AI is free to drop/reshape it on a fresh regen, same as
    # a fully-automatic moment/beat.
    old_cuts = [_cut(scene_id="scene-001", status="pending")]
    new_proposals = [_cut(scene_id="scene-001", cut_start=999, cut_end=1050, status="pending")]

    result = preserve_status_and_overrides(old_cuts, new_proposals)

    assert result[0]["cutStartFrame"] == 999
    assert result[0]["status"] == "pending"


def test_preserve_status_and_overrides_is_a_noop_with_no_old_cuts():
    new_proposals = [_cut()]

    result = preserve_status_and_overrides([], new_proposals)

    assert result == new_proposals
