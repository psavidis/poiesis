from validate_transcripts import find_suspicious_segments, group_segments


def test_find_suspicious_segments_flags_low_avg_logprob():
    transcript = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "clear", "avg_logprob": -0.1},
            {"start": 1.0, "end": 2.0, "text": "garbled", "avg_logprob": -1.5},
        ]
    }

    suspicious = find_suspicious_segments(transcript)

    assert len(suspicious) == 1
    assert suspicious[0]["text"] == "garbled"
    assert suspicious[0]["reasons"] == ["low_avg_logprob"]


def test_find_suspicious_segments_flags_high_temperature():
    transcript = {
        "segments": [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "risky",
                "avg_logprob": -0.1,
                "temperature": 1.2,
            }
        ]
    }

    suspicious = find_suspicious_segments(transcript)

    assert suspicious[0]["reasons"] == ["high_temperature"]


def test_find_suspicious_segments_skips_missing_avg_logprob():
    transcript = {"segments": [{"start": 0.0, "end": 1.0, "text": "no score"}]}

    assert find_suspicious_segments(transcript) == []


def test_group_segments_merges_close_segments():
    segments = [
        {"start": 0.0, "end": 1.0},
        {"start": 1.5, "end": 2.5},
        {"start": 10.0, "end": 11.0},
    ]

    groups = group_segments(segments)

    assert len(groups) == 2
    assert groups[0]["start"] == 0.0
    assert groups[0]["end"] == 2.5
    assert len(groups[0]["segments"]) == 2
    assert groups[1]["start"] == 10.0
    assert groups[1]["end"] == 11.0


def test_group_segments_empty_input():
    assert group_segments([]) == []
