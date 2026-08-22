import json
import subprocess
from unittest.mock import patch

from prepare_footage import (
    create_manifest,
    footage_sort_key,
    generate_episode_props_ts,
    get_video_metadata,
    load_backgrounds_for_codegen,
    validate_original_footage,
)


def _ffprobe_result(pix_fmt="yuv420p"):
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "r_frame_rate": "30/1",
                "width": 1920,
                "height": 1080,
                "pix_fmt": pix_fmt,
            }
        ],
        "format": {"duration": "12.5"},
    }
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload), stderr=""
    )


def test_get_video_metadata_reports_no_alpha_for_ordinary_pixel_format(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    with patch("prepare_footage.subprocess.run", return_value=_ffprobe_result("yuv420p")):
        metadata = get_video_metadata(video)

    assert metadata["hasAlpha"] is False
    assert metadata["fps"] == 30.0
    assert metadata["duration"] == 12.5


def test_get_video_metadata_reports_alpha_for_yuva_pixel_format(tmp_path):
    video = tmp_path / "keyed.webm"
    video.write_bytes(b"fake")

    with patch("prepare_footage.subprocess.run", return_value=_ffprobe_result("yuva420p")):
        metadata = get_video_metadata(video)

    assert metadata["hasAlpha"] is True


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


def test_generate_episode_props_ts_includes_keyed_audio_path_when_present(tmp_path):
    manifest = _manifest(
        [
            {
                "id": "001",
                "filename": "a.mov",
                "renderPath": "episodes/ep/original_footage/a.mov",
                "keyedAudioRenderPath": "episodes/ep/processing/keyed/001.audio.webm",
                "duration": 5.0,
                "fps": 60.0,
                "width": 1920,
                "height": 1080,
            }
        ]
    )

    generate_episode_props_ts(manifest, tmp_path)

    output = (tmp_path / "generated" / "episode" / "episode-props.ts").read_text()

    assert 'keyedAudioPath: "episodes/ep/processing/keyed/001.audio.webm"' in output


def test_generate_episode_props_ts_omits_keyed_audio_path_when_absent(tmp_path):
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

    assert "keyedAudioPath" not in output


def test_load_backgrounds_for_codegen_returns_empty_when_file_absent(tmp_path):
    assert load_backgrounds_for_codegen(tmp_path) == []


def test_load_backgrounds_for_codegen_reads_backgrounds_json(tmp_path):
    processing = tmp_path / "processing"
    processing.mkdir()
    (processing / "backgrounds.json").write_text(
        json.dumps({"backgrounds": [{"id": "bg-001", "filename": "loop.mp4"}]})
    )

    assert load_backgrounds_for_codegen(tmp_path) == [{"id": "bg-001", "filename": "loop.mp4"}]


def test_generate_episode_props_ts_omits_backgrounds_when_absent(tmp_path):
    manifest = _manifest([])

    generate_episode_props_ts(manifest, tmp_path)

    output = (tmp_path / "generated" / "episode" / "episode-props.ts").read_text()

    assert "backgrounds" not in output


def test_generate_episode_props_ts_includes_backgrounds_when_present(tmp_path):
    manifest = _manifest([])
    backgrounds = [
        {
            "id": "bg-001",
            "filename": "loop.mp4",
            "renderPath": "episodes/ep/background/loop.mp4",
            "caption": "loop",
            "mediaType": "video",
            "duration": 29.029,
            "fps": 29.97,
        }
    ]

    generate_episode_props_ts(manifest, tmp_path, backgrounds=backgrounds)

    output = (tmp_path / "generated" / "episode" / "episode-props.ts").read_text()

    assert "backgrounds: [" in output
    assert 'id: "bg-001",' in output
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
                "keyedAudioPath": "processing/keyed/001.audio.webm",
                "keyedAudioRenderPath": "episodes/episode/processing/keyed/001.audio.webm",
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
    assert manifest["videos"][0]["keyedAudioPath"] == "processing/keyed/001.audio.webm"
    assert (
        manifest["videos"][0]["keyedAudioRenderPath"]
        == "episodes/episode/processing/keyed/001.audio.webm"
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
    assert "keyedAudioPath" not in manifest["videos"][0]


def test_footage_sort_key_bare_chapter_sorts_before_its_numbered_parts():
    names = ["6.1.mov", "6.2.mov", "6.3.mov", "6.mov"]

    assert sorted(names, key=footage_sort_key) == ["6.mov", "6.1.mov", "6.2.mov", "6.3.mov"]


def test_footage_sort_key_orders_chapters_and_parts_numerically():
    names = ["10.mov", "2.mov", "1.10.mov", "1.2.mov", "1.mov"]

    assert sorted(names, key=footage_sort_key) == [
        "1.mov",
        "1.2.mov",
        "1.10.mov",
        "2.mov",
        "10.mov",
    ]


def test_footage_sort_key_keeps_non_numeric_names_after_numbered_and_alphabetical():
    names = ["9 outro.mov", "0. Welcome.mov", "1.mov"]

    assert sorted(names, key=footage_sort_key) == ["0. Welcome.mov", "1.mov", "9 outro.mov"]


def test_validate_original_footage_orders_bare_chapter_before_parts(tmp_path):
    footage = tmp_path / "original_footage"
    footage.mkdir()

    for name in ["6.1.mov", "6.2.mov", "6.3.mov", "6.mov", "8.1.mov", "8.mov"]:
        (footage / name).write_bytes(b"fake")

    result = [f.name for f in validate_original_footage(footage)]

    assert result == ["6.mov", "6.1.mov", "6.2.mov", "6.3.mov", "8.mov", "8.1.mov"]


# Regression coverage for #95: filenames carrying a "#" (e.g. "Question #1")
# alongside sibling "N.part" clips from the same chapter, exactly as reported
# against episode 10. footage_sort_key ignores everything after the numeric
# prefix, so the "#" character is irrelevant to ordering, but the issue's
# reporter saw these clips missing from the merged episode and this is the
# closest reproducible surface for that filename set — verifying nothing is
# dropped and the order matches Finder's alphanumerical ascending order.
def test_footage_sort_key_orders_hash_named_parts_within_a_chapter():
    names = [
        "1.7 Bridge to Plato.mov",
        "1.3 Question #3.mov",
        "1. Socrates - Intro.mov",
        "1.5 Socrates Part2.mov",
        "1.1 Question #1.mov",
        "1.6 Socrates Part3.mov",
        "1.2 Question #2.mov",
    ]

    assert sorted(names, key=footage_sort_key) == [
        "1. Socrates - Intro.mov",
        "1.1 Question #1.mov",
        "1.2 Question #2.mov",
        "1.3 Question #3.mov",
        "1.5 Socrates Part2.mov",
        "1.6 Socrates Part3.mov",
        "1.7 Bridge to Plato.mov",
    ]


def test_validate_original_footage_drops_no_clips_from_issue_95_footage_set(tmp_path):
    footage = tmp_path / "original_footage"
    footage.mkdir()

    names = [
        "0. Welcome.mov",
        "1. Socrates - Intro.mov",
        "1.1 Question #1.mov",
        "1.2 Question #2.mov",
        "1.3 Question #3.mov",
        "1.5 Socrates Part2.mov",
        "1.6 Socrates Part3.mov",
        "1.7 Bridge to Plato.mov",
        "2. Plato Intro.mov",
        "2.1 Plato and theory of ideas.mov",
        "3. Aristotle.mov",
    ]

    for name in names:
        (footage / name).write_bytes(b"fake")

    result = [f.name for f in validate_original_footage(footage)]

    # Every clip placed in original_footage must survive validation/ordering
    # — no omissions, matching macOS's alphanumerical ascending order.
    assert result == names
    assert len(result) == len(names)
