import json
from unittest.mock import patch

from index_backgrounds import (
    caption_from_filename,
    index_backgrounds,
    list_background_files,
    probe_has_alpha,
)


def test_caption_from_filename_cleans_up_separators():
    assert caption_from_filename("office_background-loop.mp4") == "office background loop"


def test_list_background_files_filters_by_extension_and_ignores_system_files(tmp_path):
    background = tmp_path / "background"
    background.mkdir()

    (background / "office.mp4").write_bytes(b"fake")
    (background / "gradient.png").write_bytes(b"fake")
    (background / "notes.txt").write_bytes(b"fake")
    (background / ".DS_Store").write_bytes(b"fake")

    files = list_background_files(background)
    names = {f.name for f in files}

    assert names == {"office.mp4", "gradient.png"}


def test_list_background_files_does_not_recurse(tmp_path):
    background = tmp_path / "background"
    (background / "nested").mkdir(parents=True)

    (background / "top.mp4").write_bytes(b"fake")
    (background / "nested" / "buried.mp4").write_bytes(b"fake")

    files = list_background_files(background)
    names = {f.name for f in files}

    assert names == {"top.mp4"}


def test_list_background_files_returns_empty_when_no_background_dir(tmp_path):
    assert list_background_files(tmp_path / "background") == []


def _fake_video_metadata(video):
    return {"duration": 8.0, "fps": 30.0, "width": 1920, "height": 1080, "hasAlpha": False}


def test_index_backgrounds_assigns_sequential_ids_and_media_type(tmp_path):
    episode = tmp_path / "episode"
    background = episode / "background"
    background.mkdir(parents=True)
    (episode / "processing").mkdir()

    (background / "office.mp4").write_bytes(b"fake")
    (background / "gradient.png").write_bytes(b"fake")

    with patch("index_backgrounds.get_video_metadata", side_effect=_fake_video_metadata):
        backgrounds = index_backgrounds(episode)

    by_filename = {b["filename"]: b for b in backgrounds}

    assert by_filename["office.mp4"]["mediaType"] == "video"
    assert by_filename["office.mp4"]["duration"] == 8.0
    assert by_filename["gradient.png"]["mediaType"] == "image"
    assert "duration" not in by_filename["gradient.png"]

    ids = {b["id"] for b in backgrounds}
    assert len(ids) == 2  # every id is unique


def test_index_backgrounds_preserves_manually_edited_caption_by_filename(tmp_path):
    episode = tmp_path / "episode"
    background = episode / "background"
    background.mkdir(parents=True)
    processing = episode / "processing"
    processing.mkdir()

    (background / "office.mp4").write_bytes(b"fake")

    (processing / "backgrounds.json").write_text(
        json.dumps({"backgrounds": [{"filename": "office.mp4", "caption": "Hand-edited caption"}]})
    )

    with patch("index_backgrounds.get_video_metadata", side_effect=_fake_video_metadata):
        backgrounds = index_backgrounds(episode)

    assert backgrounds[0]["caption"] == "Hand-edited caption"


def test_index_backgrounds_removing_a_file_does_not_reattach_caption_to_wrong_file(tmp_path):
    # Same regression class as index_assets/index_code (#80): keyed by
    # filename, not positional id, so removing one file can't silently
    # reattach a stale caption to a differently-positioned survivor.
    episode = tmp_path / "episode"
    background = episode / "background"
    background.mkdir(parents=True)
    processing = episode / "processing"
    processing.mkdir()

    (processing / "backgrounds.json").write_text(
        json.dumps({
            "backgrounds": [
                {"filename": "a.mp4", "caption": "Caption A"},
                {"filename": "b.mp4", "caption": "Caption B"},
            ]
        })
    )

    # Only b.mp4 survives on disk now.
    (background / "b.mp4").write_bytes(b"fake")

    with patch("index_backgrounds.get_video_metadata", side_effect=_fake_video_metadata):
        backgrounds = index_backgrounds(episode)

    assert len(backgrounds) == 1
    assert backgrounds[0]["filename"] == "b.mp4"
    assert backgrounds[0]["caption"] == "Caption B"


def test_probe_has_alpha_reads_metadata_flag(tmp_path):
    video = tmp_path / "keyed.webm"
    video.write_bytes(b"fake")

    with patch("index_backgrounds.get_video_metadata", return_value={"hasAlpha": True}):
        assert probe_has_alpha(video) is True

    with patch("index_backgrounds.get_video_metadata", return_value={"hasAlpha": False}):
        assert probe_has_alpha(video) is False


def test_probe_has_alpha_returns_false_when_metadata_lookup_fails(tmp_path):
    video = tmp_path / "corrupt.webm"
    video.write_bytes(b"fake")

    with patch("index_backgrounds.get_video_metadata", side_effect=RuntimeError("boom")):
        assert probe_has_alpha(video) is False
