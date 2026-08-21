import json

from normalize_transcripts import normalize_transcript


def test_normalize_transcript_extracts_fields_and_strips_text(tmp_path):
    transcript_path = tmp_path / "001.json"
    output_path = tmp_path / "out.json"

    transcript_path.write_text(
        json.dumps(
            {
                "language": "en",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.5,
                        "text": "  hello world  ",
                        "avg_logprob": -0.2,
                        "no_speech_prob": 0.01,
                        "compression_ratio": 1.1,
                        "extra_whisper_field": "ignored",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    normalize_transcript("001.mp4", transcript_path, output_path)

    result = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["source"] == "001.mp4"
    assert result["language"] == "en"
    assert len(result["segments"]) == 1

    segment = result["segments"][0]
    assert segment["start"] == 0.0
    assert segment["end"] == 1.5
    assert segment["text"] == "hello world"
    assert segment["metadata"] == {
        "avg_logprob": -0.2,
        "no_speech_prob": 0.01,
        "compression_ratio": 1.1,
    }
    assert "extra_whisper_field" not in segment


def test_normalize_transcript_passes_through_word_timestamps(tmp_path):
    transcript_path = tmp_path / "003.json"
    output_path = tmp_path / "out.json"

    transcript_path.write_text(
        json.dumps(
            {
                "language": "en",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.5,
                        "text": "hello world",
                        "words": [
                            {"word": " hello", "start": 0.0, "end": 0.6, "probability": 0.9},
                            {"word": " world", "start": 0.6, "end": 1.5, "probability": 0.95},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    normalize_transcript("003.mp4", transcript_path, output_path)

    result = json.loads(output_path.read_text(encoding="utf-8"))
    words = result["segments"][0]["words"]

    assert words == [
        {"word": "hello", "start": 0.0, "end": 0.6},
        {"word": "world", "start": 0.6, "end": 1.5},
    ]


def test_normalize_transcript_omits_words_when_absent(tmp_path):
    transcript_path = tmp_path / "004.json"
    output_path = tmp_path / "out.json"

    transcript_path.write_text(
        json.dumps(
            {
                "language": "en",
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "hi"}
                ],
            }
        ),
        encoding="utf-8",
    )

    normalize_transcript("004.mp4", transcript_path, output_path)

    result = json.loads(output_path.read_text(encoding="utf-8"))

    assert "words" not in result["segments"][0]


def test_normalize_transcript_handles_no_segments(tmp_path):
    transcript_path = tmp_path / "002.json"
    output_path = tmp_path / "out.json"

    transcript_path.write_text(
        json.dumps({"language": "en"}),
        encoding="utf-8",
    )

    normalize_transcript("002.mp4", transcript_path, output_path)

    result = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["segments"] == []
