import json
from unittest.mock import patch

from key_footage import key_footage, most_common_crop


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _manifest(videos):
    return {
        "width": 1280,
        "height": 720,
        "fps": 30,
        "videos": [
            {
                "renderPath": f"episodes/ep/{video['path']}",
                "duration": 5.0,
                "fps": 60.0,
                "width": 1920,
                "height": 1080,
                **video,
            }
            for video in videos
        ],
    }


def test_most_common_crop_picks_most_frequent_value():
    output = (
        "frame 1 cropdetect crop=2592:1458:0:108\n"
        "frame 2 cropdetect crop=2592:1458:0:108\n"
        "frame 3 cropdetect crop=2592:1400:0:137\n"
    )

    assert most_common_crop(output) == "2592:1458:0:108"


def test_most_common_crop_returns_none_when_no_matches():
    assert most_common_crop("no crop info here") is None


def test_key_footage_skips_missing_source(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"

    _write_json(
        processing / "manifest.json",
        _manifest(
            [
                {
                    "id": "001",
                    "filename": "a.mp4",
                    "path": "original_footage/a.mp4",
                }
            ]
        ),
    )

    try:
        key_footage(episode, force=False, renderer_folder=tmp_path / "renderer")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_key_footage_skips_existing_output_without_force(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"
    footage = episode / "original_footage"
    footage.mkdir(parents=True)
    (footage / "a.mp4").write_bytes(b"fake")

    _write_json(
        processing / "manifest.json",
        _manifest(
            [
                {
                    "id": "001",
                    "filename": "a.mp4",
                    "path": "original_footage/a.mp4",
                }
            ]
        ),
    )

    keyed_dir = processing / "keyed"
    keyed_dir.mkdir(parents=True)
    (keyed_dir / "001.webm").write_bytes(b"already keyed")
    (keyed_dir / "001.audio.webm").write_bytes(b"already remuxed")

    with patch("key_footage.key_clip") as mock_key_clip, \
         patch("key_footage.remux_audio") as mock_remux_audio:
        key_footage(episode, force=False, renderer_folder=tmp_path / "renderer")
        mock_key_clip.assert_not_called()
        mock_remux_audio.assert_not_called()

    manifest = json.loads((processing / "manifest.json").read_text())
    assert manifest["videos"][0]["keyedPath"] == "processing/keyed/001.webm"


def test_key_footage_processes_and_annotates_manifest(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"
    footage = episode / "original_footage"
    footage.mkdir(parents=True)
    (footage / "a.mp4").write_bytes(b"fake")

    _write_json(
        processing / "manifest.json",
        _manifest(
            [
                {
                    "id": "001",
                    "filename": "a.mp4",
                    "path": "original_footage/a.mp4",
                }
            ]
        ),
    )

    def fake_key_clip(source, output, crop):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"keyed output")

    def fake_remux_audio(source, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"remuxed audio")

    with patch("key_footage.detect_crop", return_value="2592:1458:0:108"), \
         patch("key_footage.key_clip", side_effect=fake_key_clip), \
         patch("key_footage.remux_audio", side_effect=fake_remux_audio):

        key_footage(episode, force=False, renderer_folder=tmp_path / "renderer")

    manifest = json.loads((processing / "manifest.json").read_text())
    video = manifest["videos"][0]

    assert video["keyedPath"] == "processing/keyed/001.webm"
    assert video["keyedRenderPath"] == (
        f"episodes/{episode.name}/processing/keyed/001.webm"
    )
    assert (processing / "keyed" / "001.webm").exists()

    # #128: a browser-safe audio-only remux is produced alongside the keyed
    # video and recorded in the manifest, since <Audio> can't reliably seek
    # into the raw original_footage file (moov atom trails the media data).
    assert video["keyedAudioPath"] == "processing/keyed/001.audio.webm"
    assert video["keyedAudioRenderPath"] == (
        f"episodes/{episode.name}/processing/keyed/001.audio.webm"
    )
    assert (processing / "keyed" / "001.audio.webm").exists()


# A clip keyed before #128 (or by a run interrupted between the two ffmpeg
# calls) has a video .webm but no .audio.webm yet — key_footage must still
# backfill the missing audio remux without re-doing the (expensive) keying.
def test_key_footage_backfills_missing_audio_remux_for_already_keyed_clip(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"
    footage = episode / "original_footage"
    footage.mkdir(parents=True)
    (footage / "a.mp4").write_bytes(b"fake")

    _write_json(
        processing / "manifest.json",
        _manifest(
            [
                {
                    "id": "001",
                    "filename": "a.mp4",
                    "path": "original_footage/a.mp4",
                }
            ]
        ),
    )

    keyed_dir = processing / "keyed"
    keyed_dir.mkdir(parents=True)
    (keyed_dir / "001.webm").write_bytes(b"already keyed")

    def fake_remux_audio(source, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"remuxed audio")

    with patch("key_footage.key_clip") as mock_key_clip, \
         patch("key_footage.remux_audio", side_effect=fake_remux_audio) as mock_remux_audio:

        key_footage(episode, force=False, renderer_folder=tmp_path / "renderer")

        mock_key_clip.assert_not_called()
        mock_remux_audio.assert_called_once()

    manifest = json.loads((processing / "manifest.json").read_text())
    assert manifest["videos"][0]["keyedAudioPath"] == "processing/keyed/001.audio.webm"
