import json

from index_code import description_from_filename, index_code, list_code_files


def test_description_from_filename_cleans_up_separators():
    assert description_from_filename("order_repository-impl.java") == "order repository impl"


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
