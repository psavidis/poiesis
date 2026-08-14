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

    if not graphics_dir.exists():
        return []

    files = sorted(
        f
        for f in graphics_dir.iterdir()
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

        assets.append(
            {
                "id": asset_id,
                "filename": file.name,
                "path": str(file.relative_to(episode)),
                "renderPath": str(Path("episodes") / episode.name / "graphics" / file.name),
                "caption": caption,
            }
        )

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
