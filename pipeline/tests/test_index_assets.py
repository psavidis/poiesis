import json

from index_assets import caption_from_filename, index_assets, list_asset_files


def test_caption_from_filename_cleans_up_separators():
    assert caption_from_filename("spring_boot-logo.png") == "spring boot logo"


def test_caption_from_filename_strips_non_alphanumeric():
    assert caption_from_filename("—Pngtree—vector injection icon_3876528.png") == (
        "Pngtree vector injection icon 3876528"
    )


def test_list_asset_files_filters_by_extension_and_ignores_system_files(tmp_path):
    graphics = tmp_path / "graphics"
    graphics.mkdir()

    (graphics / "logo.png").write_bytes(b"fake")
    (graphics / "photo.webp").write_bytes(b"fake")
    (graphics / "video.mov").write_bytes(b"fake")
    (graphics / ".DS_Store").write_bytes(b"fake")

    files = list_asset_files(graphics)
    names = {f.name for f in files}

    assert names == {"logo.png", "photo.webp"}


def test_list_asset_files_returns_empty_when_no_graphics_dir(tmp_path):
    assert list_asset_files(tmp_path / "graphics") == []


def test_index_assets_generates_filename_caption_on_first_run(tmp_path):
    episode = tmp_path / "episode"
    graphics = episode / "graphics"
    graphics.mkdir(parents=True)

    (graphics / "spring_boot_logo.png").write_bytes(b"fake")

    assets = index_assets(episode)

    assert len(assets) == 1
    assert assets[0]["id"] == "img-001"
    assert assets[0]["caption"] == "spring boot logo"
    assert assets[0]["filename"] == "spring_boot_logo.png"


def test_index_assets_preserves_manually_edited_caption_on_rerun(tmp_path):
    episode = tmp_path / "episode"
    graphics = episode / "graphics"
    graphics.mkdir(parents=True)

    (graphics / "unclear_name_123.png").write_bytes(b"fake")

    index_assets(episode)

    assets_path = episode / "processing" / "assets.json"
    data = json.loads(assets_path.read_text())
    data["assets"][0]["caption"] = "A hand-written accurate caption"
    assets_path.write_text(json.dumps(data))

    assets = index_assets(episode)

    assert assets[0]["caption"] == "A hand-written accurate caption"


def test_index_assets_adds_new_asset_without_disturbing_existing_caption(tmp_path):
    episode = tmp_path / "episode"
    graphics = episode / "graphics"
    graphics.mkdir(parents=True)

    (graphics / "a.png").write_bytes(b"fake")

    index_assets(episode)

    assets_path = episode / "processing" / "assets.json"
    data = json.loads(assets_path.read_text())
    data["assets"][0]["caption"] = "hand written"
    assets_path.write_text(json.dumps(data))

    (graphics / "b.png").write_bytes(b"fake")

    assets = index_assets(episode)

    assert len(assets) == 2
    by_filename = {a["filename"]: a for a in assets}
    assert by_filename["a.png"]["caption"] == "hand written"
    assert by_filename["b.png"]["caption"] == "b"
