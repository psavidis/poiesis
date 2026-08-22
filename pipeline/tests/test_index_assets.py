import json
import subprocess
from unittest.mock import patch

from index_assets import (
    caption_from_filename,
    default_display_hint,
    detect_key_color,
    index_assets,
    list_asset_files,
    _trim_letterbox_bounds,
)


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
    (graphics / "notes.txt").write_bytes(b"fake")
    (graphics / ".DS_Store").write_bytes(b"fake")

    files = list_asset_files(graphics)
    names = {f.name for f in files}

    assert names == {"logo.png", "photo.webp", "video.mov"}


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
    assert assets[0]["mediaType"] == "image"


def test_index_assets_tags_video_files_and_uses_separate_id_sequence(tmp_path):
    episode = tmp_path / "episode"
    graphics = episode / "graphics"
    graphics.mkdir(parents=True)

    (graphics / "logo.png").write_bytes(b"fake")
    (graphics / "gear.mov").write_bytes(b"fake")
    (graphics / "zzz_icon.webp").write_bytes(b"fake")

    assets = index_assets(episode)
    by_filename = {a["filename"]: a for a in assets}

    # Files sort alphabetically before ids are assigned, so image ids
    # follow that order regardless of where the video sorts among them.
    assert by_filename["logo.png"]["mediaType"] == "image"
    assert by_filename["logo.png"]["id"] == "img-001"
    assert by_filename["zzz_icon.webp"]["mediaType"] == "image"
    assert by_filename["zzz_icon.webp"]["id"] == "img-002"
    assert by_filename["gear.mov"]["mediaType"] == "video"
    assert by_filename["gear.mov"]["id"] == "vid-001"


def test_index_assets_video_id_stable_when_images_added_later(tmp_path):
    episode = tmp_path / "episode"
    graphics = episode / "graphics"
    graphics.mkdir(parents=True)

    (graphics / "gear.mov").write_bytes(b"fake")

    first_pass = index_assets(episode)
    assert first_pass[0]["id"] == "vid-001"

    (graphics / "logo.png").write_bytes(b"fake")

    second_pass = index_assets(episode)
    by_filename = {a["filename"]: a for a in second_pass}

    assert by_filename["gear.mov"]["id"] == "vid-001"
    assert by_filename["logo.png"]["id"] == "img-001"


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


def test_index_assets_caption_stays_attached_to_its_file_after_an_earlier_file_is_removed(tmp_path):
    """Regression test for #80/#93: captions AND ids must be matched by
    filename, not position — removing "a.png" must not shift b.png's own
    id (img-002) down to img-001, since that id is a live foreign key any
    moment.json's assetId may already hold onto (see #93's delete-asset
    feature, which would otherwise silently reattach an existing id, and
    therefore an already-placed moment's rendered image, to a different
    file on every delete of a non-last asset). A stale id-keyed caption
    lookup would similarly hand b.png the caption a.png had, rather than
    b.png's own."""

    episode = tmp_path / "episode"
    graphics = episode / "graphics"
    graphics.mkdir(parents=True)

    (graphics / "a.png").write_bytes(b"fake")
    (graphics / "b.png").write_bytes(b"fake")

    index_assets(episode)

    assets_path = episode / "processing" / "assets.json"
    data = json.loads(assets_path.read_text())
    for asset in data["assets"]:
        if asset["filename"] == "b.png":
            asset["caption"] = "b's own real caption"
    assets_path.write_text(json.dumps(data))

    (graphics / "a.png").unlink()

    assets = index_assets(episode)

    assert len(assets) == 1
    assert assets[0]["filename"] == "b.png"
    assert assets[0]["id"] == "img-002"
    assert assets[0]["caption"] == "b's own real caption"


def test_index_assets_new_file_after_a_deletion_gets_a_fresh_unused_id(tmp_path):
    """A file added AFTER an earlier one was deleted must not reuse the
    deleted file's old id number — img-001 (a.png) stays retired once
    a.png is gone, rather than being handed to the next new file, which
    would otherwise collide with any stale moments.json assetId still
    referencing "img-001" as a.png."""

    episode = tmp_path / "episode"
    graphics = episode / "graphics"
    graphics.mkdir(parents=True)

    (graphics / "a.png").write_bytes(b"fake")
    (graphics / "b.png").write_bytes(b"fake")

    first_pass = index_assets(episode)
    by_filename = {a["filename"]: a for a in first_pass}
    assert by_filename["a.png"]["id"] == "img-001"
    assert by_filename["b.png"]["id"] == "img-002"

    (graphics / "a.png").unlink()
    (graphics / "c.png").write_bytes(b"fake")

    second_pass = index_assets(episode)
    by_filename = {a["filename"]: a for a in second_pass}

    assert by_filename["b.png"]["id"] == "img-002"
    assert by_filename["c.png"]["id"] == "img-003"


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


def _fake_video_metadata(video):
    return {"duration": 5.0, "fps": 30.0, "width": 200, "height": 200}


def _corner_sample_result(rgb):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=bytes(rgb), stderr=b"")


def _column_sample_result(rgb, samples=64):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=bytes(rgb) * samples, stderr=b"")


def test_detect_key_color_returns_black_when_all_corners_are_near_black(tmp_path):
    video = tmp_path / "gear.mov"
    video.write_bytes(b"fake")

    with patch("index_assets.get_video_metadata", side_effect=_fake_video_metadata), patch(
        "index_assets.subprocess.run", return_value=_corner_sample_result((2, 1, 3))
    ):
        assert detect_key_color(video) == "black"


def test_detect_key_color_returns_green_when_all_corners_match_key_green(tmp_path):
    video = tmp_path / "logo.mov"
    video.write_bytes(b"fake")

    with patch("index_assets.get_video_metadata", side_effect=_fake_video_metadata), patch(
        "index_assets.subprocess.run", return_value=_corner_sample_result((5, 180, 60))
    ):
        assert detect_key_color(video) == "green"


def test_detect_key_color_returns_none_for_a_mixed_colorful_background(tmp_path):
    video = tmp_path / "photo.mov"
    video.write_bytes(b"fake")

    with patch("index_assets.get_video_metadata", side_effect=_fake_video_metadata), patch(
        "index_assets.subprocess.run", return_value=_corner_sample_result((128, 90, 200))
    ):
        assert detect_key_color(video) is None


def test_detect_key_color_requires_all_four_corners_to_agree(tmp_path):
    video = tmp_path / "mixed.mov"
    video.write_bytes(b"fake")

    no_letterbox = _column_sample_result((200, 100, 50))
    black = _corner_sample_result((0, 0, 0))
    colorful = _corner_sample_result((200, 100, 50))

    with patch("index_assets.get_video_metadata", side_effect=_fake_video_metadata), patch(
        "index_assets.subprocess.run", side_effect=[no_letterbox, black, black, black, colorful]
    ):
        assert detect_key_color(video) is None


def test_detect_key_color_returns_none_when_ffmpeg_sampling_fails(tmp_path):
    video = tmp_path / "broken.mov"
    video.write_bytes(b"fake")

    failed = subprocess.CompletedProcess(args=[], returncode=1, stdout=b"", stderr=b"error")

    with patch("index_assets.get_video_metadata", side_effect=_fake_video_metadata), patch(
        "index_assets.subprocess.run", return_value=failed
    ):
        assert detect_key_color(video) is None


def test_detect_key_color_returns_none_when_metadata_lookup_fails(tmp_path):
    video = tmp_path / "corrupt.mov"
    video.write_bytes(b"fake")

    with patch(
        "index_assets.get_video_metadata",
        side_effect=subprocess.CalledProcessError(1, ["ffprobe"]),
    ):
        assert detect_key_color(video) is None


def test_index_assets_stamps_key_color_for_video_assets(tmp_path):
    episode = tmp_path / "episode"
    graphics = episode / "graphics"
    graphics.mkdir(parents=True)

    (graphics / "gear.mov").write_bytes(b"fake")

    with patch("index_assets.get_video_metadata", side_effect=_fake_video_metadata), patch(
        "index_assets.subprocess.run", return_value=_corner_sample_result((0, 0, 0))
    ):
        assets = index_assets(episode)

    assert assets[0]["keyColor"] == "black"


def test_index_assets_omits_key_color_when_no_match_detected(tmp_path):
    episode = tmp_path / "episode"
    graphics = episode / "graphics"
    graphics.mkdir(parents=True)

    (graphics / "photo.mov").write_bytes(b"fake")

    with patch("index_assets.get_video_metadata", side_effect=_fake_video_metadata), patch(
        "index_assets.subprocess.run", return_value=_corner_sample_result((128, 90, 200))
    ):
        assets = index_assets(episode)

    assert "keyColor" not in assets[0]


def _column_with_letterbox(content_rgb, bar_fraction=0.1, samples=64):
    """A synthetic center-column sample: bar_fraction of black rows at the
    top, the same at the bottom, content_rgb in between — mimicking a
    letterboxed frame's vertical profile (see #80's real-world bug: a
    white-background presenter shot with black letterbox bars, wrongly
    corner-sampled from the bars and misclassified as black)."""

    bar_rows = int(samples * bar_fraction)
    content_rows = samples - 2 * bar_rows

    pixels = [(0, 0, 0)] * bar_rows + [content_rgb] * content_rows + [(0, 0, 0)] * bar_rows
    stdout = b"".join(bytes(p) for p in pixels)

    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=b"")


def test_trim_letterbox_bounds_detects_top_and_bottom_bars(tmp_path):
    video = tmp_path / "letterboxed.mov"
    video.write_bytes(b"fake")

    column = _column_with_letterbox((255, 255, 255), bar_fraction=0.1, samples=64)

    with patch("index_assets.subprocess.run", return_value=column):
        top, bottom = _trim_letterbox_bounds(video, width=200, height=200)

    expected_bar = int(64 * 0.1) / 64
    assert top == expected_bar
    assert bottom == 1 - expected_bar


def test_trim_letterbox_bounds_returns_full_frame_when_no_bars(tmp_path):
    video = tmp_path / "no_bars.mov"
    video.write_bytes(b"fake")

    column = _column_sample_result((100, 150, 200))

    with patch("index_assets.subprocess.run", return_value=column):
        top, bottom = _trim_letterbox_bounds(video, width=200, height=200)

    assert (top, bottom) == (0.0, 1.0)


def test_trim_letterbox_bounds_leaves_genuine_flat_black_video_untrimmed(tmp_path):
    video = tmp_path / "flat_black.mov"
    video.write_bytes(b"fake")

    # Entirely black top-to-bottom, no lighter content band in the
    # middle — a real solid-black-background graphic, not letterboxing.
    column = _column_sample_result((0, 0, 0))

    with patch("index_assets.subprocess.run", return_value=column):
        top, bottom = _trim_letterbox_bounds(video, width=200, height=200)

    assert (top, bottom) == (0.0, 1.0)


def test_detect_key_color_does_not_misclassify_letterboxed_white_background(tmp_path):
    """Regression test for #80: a letterboxed presenter shot (white
    content, black padding bars) must NOT classify as black just because
    its corners happen to land in the padding."""

    video = tmp_path / "letterboxed_presenter.mov"
    video.write_bytes(b"fake")

    column = _column_with_letterbox((255, 255, 255), bar_fraction=0.1, samples=64)
    white_corner = _corner_sample_result((255, 255, 255))

    with patch("index_assets.get_video_metadata", side_effect=_fake_video_metadata), patch(
        "index_assets.subprocess.run", side_effect=[column, white_corner, white_corner, white_corner, white_corner]
    ):
        assert detect_key_color(video) is None
