#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_footage import generate_episode_props_ts


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
}

IGNORED_FILES = {
    ".DS_Store",
    "Thumbs.db",
}

# Folder-as-authoring-hint (see docs/specs/content-types-and-presentation-
# editing.md's "Asset Folders as Authoring Metadata"): an image placed
# directly under one of these subfolder names hints that its initial
# presentation should default to Full Screen — a suggestion the AI
# (generate_moments.py) and the user can both override, never a permanent
# constraint. Kept as a small, explicit set (not a fuzzy match) rather than
# inferring intent from arbitrary folder names — an unrecognized subfolder
# name is just organizational to the user (no different from images nested
# for any other reason) and gets no hint, same as the flat-root case.
FULL_SCREEN_HINT_FOLDERS = {"full-screen", "full"}


def default_display_hint(file: Path, graphics_dir: Path) -> str | None:
    """The hint is read from the file's immediate parent folder name,
    relative to graphics/ — graphics/full-screen/x.png hints "full",
    graphics/full-screen/nested/x.png does NOT (nested is the immediate
    parent, not full-screen), and graphics/x.png (flat root, today's only
    existing convention) hints nothing. Only one level deep is
    intentional: this is meant to read as "this image lives in the
    full-screen bucket," not to walk an arbitrary folder hierarchy
    guessing intent from any ancestor."""

    relative = file.relative_to(graphics_dir)

    if len(relative.parts) < 2:
        return None

    immediate_parent = relative.parts[-2]

    if immediate_parent in FULL_SCREEN_HINT_FOLDERS:
        return "full"

    return None


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    temp = path.with_suffix(".tmp.json")

    try:
        with temp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        temp.replace(path)

    finally:
        if temp.exists():
            temp.unlink()


def caption_from_filename(filename):

    stem = Path(filename).stem

    words = re.sub(r"[_\-]+", " ", stem)
    words = re.sub(r"[^a-zA-Z0-9 ]", " ", words)
    words = re.sub(r"\s+", " ", words).strip()

    return words


def list_asset_files(graphics_dir: Path):
    """Recursive (rglob), matching index_code.py's list_code_files —
    subfolders under graphics/ are meaningful both for plain organization
    (a user grouping related images together) and, for FULL_SCREEN_HINT_FOLDERS
    specifically, as a presentation hint (see default_display_hint above).
    A flat graphics/ folder (no subfolders — every existing real episode's
    convention as of this change) indexes identically to the old
    non-recursive iterdir() scan, since rglob("*") includes the root's own
    direct children."""

    if not graphics_dir.exists():
        return []

    files = sorted(
        f
        for f in graphics_dir.rglob("*")
        if f.is_file()
           and f.name not in IGNORED_FILES
           and f.suffix.lower() in IMAGE_EXTENSIONS
    )

    return files


def index_assets(episode: Path):

    graphics_dir = episode / "graphics"
    processing = episode / "processing"
    output_path = processing / "assets.json"

    existing_captions = {}

    if output_path.exists():

        existing = load_json(output_path)

        existing_captions = {
            asset["id"]: asset["caption"]
            for asset in existing.get("assets", [])
        }

    files = list_asset_files(graphics_dir)

    assets = []

    for index, file in enumerate(files, start=1):

        asset_id = f"img-{index:03d}"

        caption = existing_captions.get(
            asset_id,
            caption_from_filename(file.name)
        )

        asset = {
            "id": asset_id,
            "filename": file.name,
            "path": str(file.relative_to(episode)),
            "renderPath": str(Path("episodes") / episode.name / "graphics" / file.relative_to(graphics_dir)),
            "caption": caption,
        }

        hint = default_display_hint(file, graphics_dir)

        if hint:
            asset["defaultDisplay"] = hint

        assets.append(asset)

    write_json_atomic(output_path, {"assets": assets})

    return assets


def main():

    parser = argparse.ArgumentParser(
        description="Index episode graphics/ folder into an asset manifest"
    )

    parser.add_argument("episode_folder")

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    assets = index_assets(episode)

    print(f"Indexed {len(assets)} asset(s).")

    for asset in assets:
        print(f"  [{asset['id']}] {asset['filename']}: {asset['caption']}")

    manifest_path = episode / "processing" / "manifest.json"

    if manifest_path.exists():

        project_root = Path(__file__).resolve().parent.parent
        renderer_folder = project_root / "video-renderer"

        manifest = load_json(manifest_path)

        code_assets_path = episode / "processing" / "code_assets.json"
        code_assets = load_json(code_assets_path)["codeAssets"] if code_assets_path.exists() else []

        generate_episode_props_ts(manifest, renderer_folder, assets=assets, code_assets=code_assets)


if __name__ == "__main__":
    main()
