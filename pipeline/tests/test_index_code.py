import json
import subprocess
from unittest.mock import patch

from index_code import (
    code_asset_kind,
    default_display_hint,
    description_from_filename,
    index_code,
    list_code_files,
)


def test_description_from_filename_cleans_up_separators():
    assert description_from_filename("order_repository-impl.java") == "order repository impl"


def test_default_display_hint_reads_full_screen_folder(tmp_path):
    code = tmp_path / "code"
    (code / "full-screen").mkdir(parents=True)
    file = code / "full-screen" / "KafkaConsumer.java"
    file.write_text("class KafkaConsumer {}")

    assert default_display_hint(file, code) == "full"


def test_default_display_hint_accepts_the_shorter_full_folder_name(tmp_path):
    code = tmp_path / "code"
    (code / "full").mkdir(parents=True)
    file = code / "full" / "KafkaConsumer.java"
    file.write_text("class KafkaConsumer {}")

    assert default_display_hint(file, code) == "full"


def test_default_display_hint_is_none_for_flat_root_files(tmp_path):
    code = tmp_path / "code"
    code.mkdir(parents=True)
    file = code / "Repository.java"
    file.write_text("class Repository {}")

    assert default_display_hint(file, code) is None


def test_default_display_hint_is_none_for_an_unrecognized_subfolder_name(tmp_path):
    code = tmp_path / "code"
    (code / "com" / "example").mkdir(parents=True)
    file = code / "com" / "example" / "Repository.java"
    file.write_text("class Repository {}")

    assert default_display_hint(file, code) is None


def test_default_display_hint_only_reads_the_immediate_parent_folder(tmp_path):
    code = tmp_path / "code"
    (code / "full-screen" / "nested").mkdir(parents=True)
    file = code / "full-screen" / "nested" / "x.java"
    file.write_text("class X {}")

    assert default_display_hint(file, code) is None


def test_list_code_files_filters_by_extension_and_ignores_system_files(tmp_path):
    code = tmp_path / "code"
    code.mkdir()

    (code / "Repository.java").write_text("class Repository {}")
    (code / "notes.txt").write_text("not code")
    (code / ".DS_Store").write_bytes(b"fake")

    files = list_code_files(code)
    names = {f.name for f in files}

    assert names == {"Repository.java"}


def test_list_code_files_scans_recursively_unlike_list_asset_files(tmp_path):
    # real source files are often organized in subfolders mirroring a real
    # project — unlike graphics/, a flat scan would miss most of them
    code = tmp_path / "code"
    nested = code / "com" / "example"
    nested.mkdir(parents=True)

    (nested / "Repository.java").write_text("class Repository {}")

    files = list_code_files(code)

    assert len(files) == 1
    assert files[0].name == "Repository.java"


def test_list_code_files_returns_empty_when_no_code_dir(tmp_path):
    assert list_code_files(tmp_path / "code") == []


def test_index_code_generates_filename_description_and_language_on_first_run(tmp_path):
    episode = tmp_path / "episode"
    code = episode / "code"
    code.mkdir(parents=True)

    (code / "order_repository.java").write_text("class OrderRepository {}\n")

    code_assets = index_code(episode)

    assert len(code_assets) == 1
    asset = code_assets[0]
    assert asset["id"] == "code-001"
    assert asset["description"] == "order repository"
    assert asset["filename"] == "order_repository.java"
    assert asset["language"] == "java"
    assert asset["lineCount"] == 1


def test_index_code_line_count_matches_real_file_content(tmp_path):
    episode = tmp_path / "episode"
    code = episode / "code"
    code.mkdir(parents=True)

    (code / "a.py").write_text("line one\nline two\nline three\n")

    code_assets = index_code(episode)

    assert code_assets[0]["lineCount"] == 3


def test_index_code_preserves_manually_edited_description_on_rerun(tmp_path):
    episode = tmp_path / "episode"
    code = episode / "code"
    code.mkdir(parents=True)

    (code / "unclear_name_123.py").write_text("x = 1\n")

    index_code(episode)

    code_assets_path = episode / "processing" / "code_assets.json"
    data = json.loads(code_assets_path.read_text())
    data["codeAssets"][0]["description"] = "constructor injection example"
    code_assets_path.write_text(json.dumps(data))

    code_assets = index_code(episode)

    assert code_assets[0]["description"] == "constructor injection example"


def test_index_code_description_stays_attached_to_its_file_after_an_earlier_file_is_removed(tmp_path):
    """Regression test for #80/#94 (same class of bug as index_assets.py's
    caption cache): descriptions AND ids must be matched by filename, not
    position — removing "a.py" must not shift b.py's own id (code-002)
    down to code-001, since that id is a live foreign key any
    moments.json's codeAssetId may already hold onto (see #94's
    delete-asset feature, which would otherwise silently reattach an
    existing id, and therefore an already-placed moment's rendered code,
    to a different file on every delete of a non-last asset)."""

    episode = tmp_path / "episode"
    code = episode / "code"
    code.mkdir(parents=True)

    (code / "a.py").write_text("x = 1\n")
    (code / "b.py").write_text("y = 2\n")

    index_code(episode)

    code_assets_path = episode / "processing" / "code_assets.json"
    data = json.loads(code_assets_path.read_text())
    for asset in data["codeAssets"]:
        if asset["filename"] == "b.py":
            asset["description"] = "b's own real description"
    code_assets_path.write_text(json.dumps(data))

    (code / "a.py").unlink()

    code_assets = index_code(episode)

    assert len(code_assets) == 1
    assert code_assets[0]["filename"] == "b.py"
    assert code_assets[0]["id"] == "code-002"
    assert code_assets[0]["description"] == "b's own real description"


def test_index_code_new_file_after_a_deletion_gets_a_fresh_unused_id(tmp_path):
    """A file added AFTER an earlier one was deleted must not reuse the
    deleted file's old id number — code-001 (a.py) stays retired once
    a.py is gone, rather than being handed to the next new file, which
    would otherwise collide with any stale moments.json codeAssetId still
    referencing "code-001" as a.py."""

    episode = tmp_path / "episode"
    code = episode / "code"
    code.mkdir(parents=True)

    (code / "a.py").write_text("x = 1\n")
    (code / "b.py").write_text("y = 2\n")

    first_pass = index_code(episode)
    by_filename = {a["filename"]: a for a in first_pass}
    assert by_filename["a.py"]["id"] == "code-001"
    assert by_filename["b.py"]["id"] == "code-002"

    (code / "a.py").unlink()
    (code / "c.py").write_text("z = 3\n")

    second_pass = index_code(episode)
    by_filename = {a["filename"]: a for a in second_pass}

    assert by_filename["b.py"]["id"] == "code-002"
    assert by_filename["c.py"]["id"] == "code-003"


def test_index_code_stamps_default_display_for_full_screen_folder_assets(tmp_path):
    episode = tmp_path / "episode"
    code = episode / "code"
    (code / "full-screen").mkdir(parents=True)

    (code / "Repository.java").write_text("class Repository {}")
    (code / "full-screen" / "KafkaConsumer.java").write_text("class KafkaConsumer {}")

    code_assets = index_code(episode)
    by_filename = {a["filename"]: a for a in code_assets}

    assert "defaultDisplay" not in by_filename["Repository.java"]
    assert by_filename["KafkaConsumer.java"]["defaultDisplay"] == "full"


def test_index_code_adds_new_asset_without_disturbing_existing_description(tmp_path):
    episode = tmp_path / "episode"
    code = episode / "code"
    code.mkdir(parents=True)

    (code / "a.py").write_text("x = 1\n")

    index_code(episode)

    code_assets_path = episode / "processing" / "code_assets.json"
    data = json.loads(code_assets_path.read_text())
    data["codeAssets"][0]["description"] = "hand written"
    code_assets_path.write_text(json.dumps(data))

    (code / "b.py").write_text("y = 2\n")

    code_assets = index_code(episode)

    assert len(code_assets) == 2
    by_filename = {a["filename"]: a for a in code_assets}
    assert by_filename["a.py"]["description"] == "hand written"
    assert by_filename["b.py"]["description"] == "b"


def test_code_asset_kind_classifies_by_extension(tmp_path):
    assert code_asset_kind(tmp_path / "Repository.java") == "source"
    assert code_asset_kind(tmp_path / "screenshot.png") == "screenshot"
    assert code_asset_kind(tmp_path / "recording.mov") == "recording"


def test_list_code_files_also_includes_screenshots_and_recordings(tmp_path):
    code = tmp_path / "code"
    code.mkdir()

    (code / "Repository.java").write_text("class Repository {}")
    (code / "screenshot.png").write_bytes(b"fake")
    (code / "recording.mov").write_bytes(b"fake")
    (code / "notes.txt").write_text("not code")

    files = list_code_files(code)
    names = {f.name for f in files}

    assert names == {"Repository.java", "screenshot.png", "recording.mov"}


def _fake_video_metadata(video):
    return {"duration": 5.0, "fps": 30.0, "width": 200, "height": 200}


def _corner_sample_result(rgb):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=bytes(rgb), stderr=b"")


def test_index_code_screenshot_has_no_language_or_line_count(tmp_path):
    episode = tmp_path / "episode"
    code = episode / "code"
    code.mkdir(parents=True)

    (code / "2.1 Class Without DI.png").write_bytes(b"fake")

    code_assets = index_code(episode)

    asset = code_assets[0]
    assert asset["kind"] == "screenshot"
    assert "language" not in asset
    assert "lineCount" not in asset
    assert asset["description"] == "2 1 Class Without DI"


def test_index_code_recording_detects_key_color(tmp_path):
    episode = tmp_path / "episode"
    code = episode / "code"
    code.mkdir(parents=True)

    (code / "0715.mov").write_bytes(b"fake")

    with patch("index_code.detect_key_color", return_value="black"):
        code_assets = index_code(episode)

    asset = code_assets[0]
    assert asset["kind"] == "recording"
    assert asset["keyColor"] == "black"
    assert "language" not in asset


def test_index_code_recording_omits_key_color_when_not_detected(tmp_path):
    episode = tmp_path / "episode"
    code = episode / "code"
    code.mkdir(parents=True)

    (code / "0715.mov").write_bytes(b"fake")

    with patch("index_code.detect_key_color", return_value=None):
        code_assets = index_code(episode)

    assert "keyColor" not in code_assets[0]


def test_index_code_source_files_still_get_language_and_line_count_alongside_media(tmp_path):
    episode = tmp_path / "episode"
    code = episode / "code"
    code.mkdir(parents=True)

    (code / "Repository.java").write_text("class Repository {}\n")
    (code / "screenshot.png").write_bytes(b"fake")

    code_assets = index_code(episode)
    by_filename = {a["filename"]: a for a in code_assets}

    assert by_filename["Repository.java"]["kind"] == "source"
    assert by_filename["Repository.java"]["language"] == "java"
    assert by_filename["Repository.java"]["lineCount"] == 1
    assert by_filename["screenshot.png"]["kind"] == "screenshot"
