import json

import pytest

from generate_episode_assets import (
    format_timestamp,
    generate_review_notes,
    generate_srt,
    main,
)


def test_format_timestamp_formats_hours_minutes_seconds_millis():
    assert format_timestamp(3661.5) == "01:01:01,500"


def test_generate_srt_formats_each_segment_in_order():
    transcript = {
        "segments": [
            {"start": 0.0, "end": 1.5, "text": " Hello "},
            {"start": 1.5, "end": 3.0, "text": "World"},
        ]
    }

    srt = generate_srt(transcript)

    assert "1\n00:00:00,000 --> 00:00:01,500\nHello\n" in srt
    assert "2\n00:00:01,500 --> 00:00:03,000\nWorld\n" in srt


def test_generate_review_notes_reports_no_issues_when_empty():
    assert generate_review_notes({}) == "# Episode Review Notes\n\nNo issues detected.\n"


def test_generate_review_notes_lists_each_issue():
    analysis = {
        "issues": [
            {"severity": "high", "start": 1, "end": 2, "assessment": "Something's off"},
        ]
    }

    notes = generate_review_notes(analysis)

    assert "## HIGH 1s - 2s" in notes
    assert "Something's off" in notes


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# #88: episode_analysis.json is AI-produced (analyze_episode.py) — a
# --no-ai pipeline run skips that stage entirely, so this stage must still
# succeed and produce subtitles/review notes/chapters without it, exactly
# like a normal run, just with an empty (not missing) review-notes report.
def test_main_succeeds_without_episode_analysis_json(tmp_path, monkeypatch):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(
        processing / "episode_transcript.json",
        {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}]},
    )

    monkeypatch.setattr("sys.argv", ["generate_episode_assets.py", str(episode)])

    main()

    assert (processing / "subtitles.srt").exists()
    assert (processing / "review_notes.md").read_text(encoding="utf-8") == (
        "# Episode Review Notes\n\nNo issues detected.\n"
    )
    assert (processing / "chapters.txt").exists()


def test_main_uses_real_analysis_when_present(tmp_path, monkeypatch):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(
        processing / "episode_transcript.json",
        {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}]},
    )
    _write_json(
        processing / "episode_analysis.json",
        {"analysis": {"issues": [{"severity": "low", "start": 0, "end": 1, "assessment": "Minor"}]}},
    )

    monkeypatch.setattr("sys.argv", ["generate_episode_assets.py", str(episode)])

    main()

    notes = (processing / "review_notes.md").read_text(encoding="utf-8")
    assert "LOW 0s - 1s" in notes
    assert "Minor" in notes


def test_main_exits_when_transcript_missing(tmp_path, monkeypatch):
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr("sys.argv", ["generate_episode_assets.py", str(episode)])

    with pytest.raises(SystemExit):
        main()
