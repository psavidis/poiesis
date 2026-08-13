from unittest.mock import patch

from prepare_footage import create_manifest, find_background_video, generate_episode_props_ts


def _manifest(videos):
    return {
        "width": 1280,
        "height": 720,
        "fps": 30,
        "videos": videos,
    }


def test_generate_episode_props_ts_omits_keyed_path_when_absent(tmp_path):
    manifest = _manifest(
        [
            {
                "id": "001",
                "filename": "a.mov",
                "renderPath": "episodes/ep/original_footage/a.mov",
                "duration": 5.0,
                "fps": 60.0,
                "width": 1920,
                "height": 1080,
            }
        ]
    )

    generate_episode_props_ts(manifest, tmp_path)

    output = (tmp_path / "generated" / "episode" / "episode-props.ts").read_text()

    assert "keyedPath" not in output
    assert 'path: "episodes/ep/original_footage/a.mov"' in output


def test_generate_episode_props_ts_includes_keyed_path_when_present(tmp_path):
    manifest = _manifest(
        [
            {
                "id": "001",
                "filename": "a.mov",
                "renderPath": "episodes/ep/original_footage/a.mov",
                "keyedRenderPath": "episodes/ep/processing/keyed/001.webm",
                "duration": 5.0,
                "fps": 60.0,
                "width": 1920,
                "height": 1080,
            }
        ]
    )

    generate_episode_props_ts(manifest, tmp_path)

    output = (tmp_path / "generated" / "episode" / "episode-props.ts").read_text()

    assert 'keyedPath: "episodes/ep/processing/keyed/001.webm"' in output


def test_find_background_video_returns_none_when_no_folder(tmp_path):
    assert find_background_video(tmp_path) is None


def test_find_background_video_returns_none_when_folder_empty(tmp_path):
    (tmp_path / "background").mkdir()

    assert find_background_video(tmp_path) is None


def test_find_background_video_finds_video_file(tmp_path):
    background = tmp_path / "background"
    background.mkdir()
    (background / "loop.mp4").write_bytes(b"fake")

    result = find_background_video(tmp_path)

    assert result is not None
    assert result.name == "loop.mp4"


def test_find_background_video_ignores_non_video_files(tmp_path):
    background = tmp_path / "background"
    background.mkdir()
    (background / ".DS_Store").write_bytes(b"fake")
    (background / "notes.txt").write_bytes(b"fake")

    assert find_background_video(tmp_path) is None


def test_generate_episode_props_ts_omits_background_video_when_absent(tmp_path):
    manifest = _manifest([])

    generate_episode_props_ts(manifest, tmp_path)

    output = (tmp_path / "generated" / "episode" / "episode-props.ts").read_text()

    assert "backgroundVideo" not in output


def test_generate_episode_props_ts_includes_background_video_when_present(tmp_path):
    manifest = _manifest([])
    manifest["backgroundVideo"] = {
        "filename": "loop.mp4",
        "renderPath": "episodes/ep/background/loop.mp4",
        "duration": 29.029,
        "fps": 29.97,
    }

    generate_episode_props_ts(manifest, tmp_path)

    output = (tmp_path / "generated" / "episode" / "episode-props.ts").read_text()

    assert "backgroundVideo: {" in output
    assert 'path: "episodes/ep/background/loop.mp4"' in output
    assert 'filename: "loop.mp4"' in output
    assert "duration: 29.029," in output
    assert "fps: 29.97," in output


def _fake_metadata(video):
    return {"duration": 10.0, "fps": 30.0, "width": 1920, "height": 1080}


def test_create_manifest_preserves_keyed_path_from_previous_manifest(tmp_path):
    episode = tmp_path / "episode"
    footage = episode / "original_footage"
    footage.mkdir(parents=True)
    video_path = footage / "a.mov"
    video_path.write_bytes(b"fake")

    config = {"render": {"width": 1280, "height": 720, "fps": 30}}

    previous_manifest = {
        "videos": [
            {
                "id": "001",
                "keyedPath": "processing/keyed/001.webm",
                "keyedRenderPath": "episodes/episode/processing/keyed/001.webm",
            }
        ]
    }

    with patch("prepare_footage.get_video_metadata", side_effect=_fake_metadata):
        manifest = create_manifest(
            episode,
            [video_path],
            config,
            previous_manifest=previous_manifest,
        )

    assert manifest["videos"][0]["keyedPath"] == "processing/keyed/001.webm"
    assert (
        manifest["videos"][0]["keyedRenderPath"]
        == "episodes/episode/processing/keyed/001.webm"
    )


def test_create_manifest_no_previous_manifest_omits_keyed_path(tmp_path):
    episode = tmp_path / "episode"
    footage = episode / "original_footage"
    footage.mkdir(parents=True)
    video_path = footage / "a.mov"
    video_path.write_bytes(b"fake")

    config = {"render": {"width": 1280, "height": 720, "fps": 30}}

    with patch("prepare_footage.get_video_metadata", side_effect=_fake_metadata):
        manifest = create_manifest(episode, [video_path], config)

    assert "keyedPath" not in manifest["videos"][0]
