import json

import pytest

from merge_segments import merge_segments


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_merge_segments_combines_all_videos_in_order(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(
        processing / "manifest.json",
        {
            "videos": [
                {"id": "001", "filename": "a.mp4"},
                {"id": "002", "filename": "b.mp4"},
            ]
        },
    )

    _write_json(
        processing / "segments" / "001.json",
        {
            "source": "a.mp4",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}],
        },
    )

    _write_json(
        processing / "segments" / "002.json",
        {
            "source": "b.mp4",
            "segments": [{"start": 0.0, "end": 2.0, "text": "world"}],
        },
    )

    merge_segments(episode, force=False)

    output = json.loads(
        (processing / "episode_transcript.json").read_text(encoding="utf-8")
    )

    assert output["episode"] == "episode"
    assert len(output["segments"]) == 2
    assert output["segments"][0]["source"] == "a.mp4"
    assert output["segments"][0]["text"] == "hello"
    assert output["segments"][1]["source"] == "b.mp4"
    assert output["segments"][1]["text"] == "world"


def test_merge_segments_passes_through_word_timestamps(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(
        processing / "manifest.json",
        {"videos": [{"id": "001", "filename": "a.mp4"}]},
    )

    _write_json(
        processing / "segments" / "001.json",
        {
            "source": "a.mp4",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "hello",
                    "words": [{"word": "hello", "start": 0.0, "end": 1.0}],
                }
            ],
        },
    )

    merge_segments(episode, force=False)

    output = json.loads(
        (processing / "episode_transcript.json").read_text(encoding="utf-8")
    )

    assert output["segments"][0]["words"] == [
        {"word": "hello", "start": 0.0, "end": 1.0}
    ]


def test_merge_segments_omits_words_when_absent(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(
        processing / "manifest.json",
        {"videos": [{"id": "001", "filename": "a.mp4"}]},
    )

    _write_json(
        processing / "segments" / "001.json",
        {
            "source": "a.mp4",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}],
        },
    )

    merge_segments(episode, force=False)

    output = json.loads(
        (processing / "episode_transcript.json").read_text(encoding="utf-8")
    )

    assert "words" not in output["segments"][0]


def test_merge_segments_skips_when_output_exists_and_not_forced(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(processing / "manifest.json", {"videos": []})
    _write_json(processing / "episode_transcript.json", {"already": "there"})

    merge_segments(episode, force=False)

    output = json.loads(
        (processing / "episode_transcript.json").read_text(encoding="utf-8")
    )

    assert output == {"already": "there"}


def test_merge_segments_exits_when_missing_segment_file(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(
        processing / "manifest.json",
        {"videos": [{"id": "001", "filename": "a.mp4"}]},
    )

    with pytest.raises(SystemExit):
        merge_segments(episode, force=False)
