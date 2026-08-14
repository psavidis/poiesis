import json

from analyze_scenes import (
    analyze_speech_bounds,
    run_scene_analysis,
    trim_trailing_low_confidence_segments,
    LEAD_IN_SECONDS,
    TAIL_SECONDS,
)


def test_no_transcript_returns_full_duration():
    start, end = analyze_speech_bounds(None, duration=10.0, fps=30)

    assert start == 0
    assert end == 300


def test_empty_segments_returns_full_duration():
    start, end = analyze_speech_bounds({"segments": []}, duration=10.0, fps=30)

    assert start == 0
    assert end == 300


def test_trims_lead_in_and_tail_around_speech():
    transcript = {
        "segments": [
            {"start": 2.0, "end": 3.0},
            {"start": 4.0, "end": 5.0},
        ]
    }

    start, end = analyze_speech_bounds(transcript, duration=10.0, fps=30)

    expected_start = int((2.0 - LEAD_IN_SECONDS) * 30)
    expected_end = int((5.0 + TAIL_SECONDS) * 30)

    assert start == expected_start
    assert end == expected_end


def test_lead_in_clamped_to_zero_when_speech_starts_near_beginning():
    transcript = {
        "segments": [
            {"start": 0.05, "end": 1.0},
        ]
    }

    start, _ = analyze_speech_bounds(transcript, duration=10.0, fps=30)

    assert start == 0


def test_tail_clamped_to_duration_when_speech_ends_near_end():
    transcript = {
        "segments": [
            {"start": 0.0, "end": 9.9},
        ]
    }

    duration = 10.0
    _, end = analyze_speech_bounds(transcript, duration=duration, fps=30)

    assert end == int(duration * 30)


def test_trim_trailing_low_confidence_segments_drops_hallucinated_tail():
    segments = [
        {"end": 10.0, "avg_logprob": -0.1},
        {"end": 20.0, "avg_logprob": -0.2},
        {"end": 20.5, "avg_logprob": -4.1},
    ]

    trimmed = trim_trailing_low_confidence_segments(segments)

    assert trimmed == segments[:2]


def test_trim_trailing_low_confidence_segments_stops_at_first_confident_segment():
    segments = [
        {"end": 10.0, "avg_logprob": -0.1},
        {"end": 15.0, "avg_logprob": -4.1},
        {"end": 20.0, "avg_logprob": -0.2},
        {"end": 20.5, "avg_logprob": -4.1},
    ]

    trimmed = trim_trailing_low_confidence_segments(segments)

    assert trimmed == segments[:3]


def test_trim_trailing_low_confidence_segments_keeps_missing_logprob():
    segments = [{"end": 10.0}]

    assert trim_trailing_low_confidence_segments(segments) == segments


def test_trim_trailing_low_confidence_segments_can_empty_all_segments():
    segments = [
        {"end": 5.0, "avg_logprob": -4.1},
        {"end": 6.0, "avg_logprob": -5.0},
    ]

    assert trim_trailing_low_confidence_segments(segments) == []


def test_analyze_speech_bounds_ignores_hallucinated_trailing_segment():
    transcript = {
        "segments": [
            {"start": 0.0, "end": 38.72, "avg_logprob": -0.19},
            {"start": 38.72, "end": 38.8, "avg_logprob": -4.1},
        ]
    }

    _, end = analyze_speech_bounds(transcript, duration=40.0, fps=30)

    expected_end = int((38.72 + TAIL_SECONDS) * 30)
    assert end == expected_end


def test_analyze_speech_bounds_clamps_last_end_to_duration():
    transcript = {
        "segments": [
            {"start": 0.0, "end": 108.56, "avg_logprob": -0.2},
        ]
    }

    duration = 102.48

    _, end = analyze_speech_bounds(transcript, duration=duration, fps=30)

    expected_end = int(min(duration, duration + TAIL_SECONDS) * 30)
    assert end == expected_end


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_run_scene_analysis_regenerates_presenter_scenes(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(
        processing / "manifest.json",
        {
            "episode": "episode",
            "fps": 30,
            "videos": [{"id": "001", "duration": 10.0}],
        },
    )

    scene_plan = run_scene_analysis(episode)

    assert len(scene_plan["scenes"]) == 1
    assert scene_plan["scenes"][0]["type"] == "presenter"


def test_run_scene_analysis_preserves_existing_title_scenes(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(
        processing / "manifest.json",
        {
            "episode": "episode",
            "fps": 30,
            "videos": [
                {"id": "001", "duration": 10.0},
                {"id": "002", "duration": 10.0},
            ],
        },
    )

    _write_json(
        processing / "title_scenes.json",
        {"titles": [{"videoId": "002", "text": "Second Topic"}]},
    )

    scene_plan = run_scene_analysis(episode)

    types = [scene["type"] for scene in scene_plan["scenes"]]
    assert types == ["presenter", "title", "presenter"]

    title_scene = scene_plan["scenes"][1]
    assert title_scene["text"] == "Second Topic"

    written = json.loads(
        (processing / "scene-plan.json").read_text(encoding="utf-8")
    )
    assert written == scene_plan


def test_run_scene_analysis_preserves_existing_moment_scenes(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(
        processing / "manifest.json",
        {
            "episode": "episode",
            "fps": 30,
            "videos": [{"id": "001", "duration": 30.0}],
        },
    )

    _write_json(
        processing / "moments.json",
        {
            "moments": [
                {
                    "windowId": "w0",
                    "sceneId": "scene-001",
                    "videoId": "001",
                    "offsetInParentFrames": 500,
                    "maxDurationInParentFrames": 400,
                    "treatment": "bottom-callout",
                    "requiredLayout": "center",
                    "text": "key phrase",
                    "reason": "central",
                }
            ]
        },
    )

    scene_plan = run_scene_analysis(episode)

    types = [scene["type"] for scene in scene_plan["scenes"]]
    assert "moment" in types

    moment_scene = next(s for s in scene_plan["scenes"] if s["type"] == "moment")
    assert moment_scene["text"] == "key phrase"
