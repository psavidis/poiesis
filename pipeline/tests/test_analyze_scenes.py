from analyze_scenes import analyze_speech_bounds, LEAD_IN_SECONDS, TAIL_SECONDS


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
