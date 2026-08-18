#!/usr/bin/env python3

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from index_assets import (
    IGNORED_FILES,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    detect_key_color,
    load_json,
    write_json_atomic,
)
from prepare_footage import generate_episode_props_ts, get_video_metadata


MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def caption_from_filename(filename):
    stem = Path(filename).stem
    words = re.sub(r"[_\-]+", " ", stem)
    words = re.sub(r"[^a-zA-Z0-9 ]", " ", words)
    words = re.sub(r"\s+", " ", words).strip()
    return words


def list_background_files(background_dir: Path):
    """Every image/video directly under background/ — flat (not recursive
    like graphics/), since a background is a single selectable choice, not
    something worth organizing into authoring-hint subfolders the way
    FULL_SCREEN_HINT_FOLDERS does for graphics/."""

    if not background_dir.exists():
        return []

    return sorted(
        f
        for f in background_dir.iterdir()
        if f.is_file()
        and f.name not in IGNORED_FILES
        and f.suffix.lower() in MEDIA_EXTENSIONS
    )


def probe_has_alpha(video_path: Path) -> bool:
    """True if the video's own pixel format already encodes an alpha
    channel (e.g. yuva420p, the format key_footage.py's own keyed output
    uses) — a background sourced from an alpha-transparent video would be
    meaningless to composite as a full-frame opaque fill (see
    index_backgrounds' "opaque fill" design decision), so this is only
    used to warn/skip rather than to drive any keying decision the way
    detect_key_color does for graphics/code assets."""

    try:
        metadata = get_video_metadata(video_path)
    except Exception:
        return False

    return bool(metadata.get("hasAlpha"))


def index_backgrounds(episode: Path):
    """Indexes every background/ file into backgrounds.json — the
    selectable set a human picks from when assigning a BackgroundScene
    span (see generate_background_scenes.py), replacing
    prepare_footage.py's old find_background_video (which only ever
    auto-picked the first video file, with no user choice and no image
    support). Backgrounds always render as an opaque full-frame fill (per
    the user's own decision — a background REPLACES whatever's behind the
    presenter, it doesn't composite with anything under it), so unlike
    graphics/code assets no keyColor detection runs here: an alpha-video
    background would just show through to nothing behind it, so
    hasAlpha is recorded only as an informational flag, not used to alter
    rendering."""

    background_dir = episode / "background"
    processing = episode / "processing"
    output_path = processing / "backgrounds.json"

    existing_captions = {}

    if output_path.exists():
        existing = load_json(output_path)
        existing_captions = {
            bg["filename"]: bg["caption"]
            for bg in existing.get("backgrounds", [])
        }

    files = list_background_files(background_dir)

    backgrounds = []
    next_index = 1

    for file in files:

        is_video = file.suffix.lower() in VIDEO_EXTENSIONS
        media_type = "video" if is_video else "image"

        background_id = f"bg-{next_index:03d}"
        next_index += 1

        caption = existing_captions.get(file.name, caption_from_filename(file.name))

        background = {
            "id": background_id,
            "filename": file.name,
            "path": str(file.relative_to(episode)),
            "renderPath": str(Path("episodes") / episode.name / "background" / file.name),
            "caption": caption,
            "mediaType": media_type,
        }

        if is_video:
            try:
                metadata = get_video_metadata(file)
                background["duration"] = metadata["duration"]
                background["fps"] = metadata["fps"]
            except Exception:
                pass

        backgrounds.append(background)

    write_json_atomic(output_path, {"backgrounds": backgrounds})

    return backgrounds


def main():

    parser = argparse.ArgumentParser(
        description="Index episode background/ folder into a selectable background manifest"
    )

    parser.add_argument("episode_folder")

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    backgrounds = index_backgrounds(episode)

    print(f"Indexed {len(backgrounds)} background(s).")

    for background in backgrounds:
        print(f"  [{background['id']}] {background['filename']} ({background['mediaType']})")

    manifest_path = episode / "processing" / "manifest.json"

    if manifest_path.exists():

        project_root = Path(__file__).resolve().parent.parent
        renderer_folder = project_root / "video-renderer"

        manifest = load_json(manifest_path)

        assets_path = episode / "processing" / "assets.json"
        assets = load_json(assets_path)["assets"] if assets_path.exists() else []

        code_assets_path = episode / "processing" / "code_assets.json"
        code_assets = load_json(code_assets_path)["codeAssets"] if code_assets_path.exists() else []

        generate_episode_props_ts(
            manifest,
            renderer_folder,
            assets=assets,
            code_assets=code_assets,
            backgrounds=backgrounds
        )


if __name__ == "__main__":
    main()
