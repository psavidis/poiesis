import json

from index_assets import caption_from_filename, default_display_hint, index_assets, list_asset_files


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


def test_list_asset_files_recurses_into_subfolders(tmp_path):
    graphics = tmp_path / "graphics"
    (graphics / "full-screen").mkdir(parents=True)

    (graphics / "logo.png").write_bytes(b"fake")
    (graphics / "full-screen" / "wiring.png").write_bytes(b"fake")

    files = list_asset_files(graphics)
    names = {f.name for f in files}

    assert names == {"logo.png", "wiring.png"}


def test_default_display_hint_reads_full_screen_folder(tmp_path):
    graphics = tmp_path / "graphics"
    (graphics / "full-screen").mkdir(parents=True)
    file = graphics / "full-screen" / "wiring.png"
    file.write_bytes(b"fake")

    assert default_display_hint(file, graphics) == "full"


def test_default_display_hint_accepts_the_shorter_full_folder_name(tmp_path):
    graphics = tmp_path / "graphics"
    (graphics / "full").mkdir(parents=True)
    file = graphics / "full" / "wiring.png"
    file.write_bytes(b"fake")

    assert default_display_hint(file, graphics) == "full"


def test_default_display_hint_is_none_for_flat_root_files(tmp_path):
    graphics = tmp_path / "graphics"
    graphics.mkdir(parents=True)
    file = graphics / "logo.png"
    file.write_bytes(b"fake")

    assert default_display_hint(file, graphics) is None


def test_default_display_hint_is_none_for_an_unrecognized_subfolder_name(tmp_path):
    graphics = tmp_path / "graphics"
    (graphics / "diagrams").mkdir(parents=True)
    file = graphics / "diagrams" / "arch.png"
    file.write_bytes(b"fake")

    assert default_display_hint(file, graphics) is None


def test_default_display_hint_only_reads_the_immediate_parent_folder(tmp_path):
    # graphics/full-screen/nested/x.png — the immediate parent is
    # "nested", not "full-screen", so no hint (see the function's own
    # docstring: this deliberately doesn't walk the whole ancestor chain).
    graphics = tmp_path / "graphics"
    (graphics / "full-screen" / "nested").mkdir(parents=True)
    file = graphics / "full-screen" / "nested" / "x.png"
    file.write_bytes(b"fake")

    assert default_display_hint(file, graphics) is None


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


def test_index_assets_stamps_default_display_for_full_screen_folder_assets(tmp_path):
    episode = tmp_path / "episode"
    graphics = episode / "graphics"
    (graphics / "full-screen").mkdir(parents=True)

    (graphics / "logo.png").write_bytes(b"fake")
    (graphics / "full-screen" / "wiring.png").write_bytes(b"fake")

    assets = index_assets(episode)
    by_filename = {a["filename"]: a for a in assets}

    assert "defaultDisplay" not in by_filename["logo.png"]
    assert by_filename["wiring.png"]["defaultDisplay"] == "full"


def test_index_assets_computes_render_path_relative_to_graphics_for_nested_files(tmp_path):
    episode = tmp_path / "My Episode"
    graphics = episode / "graphics"
    (graphics / "full-screen").mkdir(parents=True)

    (graphics / "full-screen" / "wiring.png").write_bytes(b"fake")

    assets = index_assets(episode)

    assert assets[0]["renderPath"] == "episodes/My Episode/graphics/full-screen/wiring.png"


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
