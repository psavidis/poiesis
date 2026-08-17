#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_footage import generate_episode_props_ts


# Kept as a small, non-exhaustive allowlist — extend as needed rather than
# trying to cover every possible language up front (CLAUDE.md: build for
# the one user, not speculatively).
LANGUAGE_BY_EXTENSION = {
    ".java": "java",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".kt": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".rb": "ruby",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}

IGNORED_FILES = {
    ".DS_Store",
    "Thumbs.db",
}

# Same folder-as-authoring-hint convention as index_assets.py's
# FULL_SCREEN_HINT_FOLDERS (see docs/specs/content-types-and-presentation-
# editing.md's "Asset Folders as Authoring Metadata") — a code file placed
# directly under one of these subfolder names hints that its initial
# presentation should default to Full Screen, a suggestion generate_moments.py
# and the user can both override, never a permanent constraint.
FULL_SCREEN_HINT_FOLDERS = {"full-screen", "full"}


def default_display_hint(file: Path, code_dir: Path) -> str | None:
    """Mirrors index_assets.py's default_display_hint exactly — reads only
    the file's immediate parent folder name, relative to code/. Only one
    level deep is intentional: this reads as "this file lives in the
    full-screen bucket," not as walking an arbitrary folder hierarchy."""

    relative = file.relative_to(code_dir)

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


def description_from_filename(filename):

    stem = Path(filename).stem

    words = re.sub(r"[_\-]+", " ", stem)
    words = re.sub(r"[^a-zA-Z0-9 ]", " ", words)
    words = re.sub(r"\s+", " ", words).strip()

    return words


def list_code_files(code_dir: Path):
    """Recursive, unlike list_asset_files's flat graphics/ scan — real
    source files are often organized in subfolders mirroring a real
    project (e.g. code/com/example/Repository.java), so a flat scan would
    miss most of them."""

    if not code_dir.exists():
        return []

    files = sorted(
        f
        for f in code_dir.rglob("*")
        if f.is_file()
           and f.name not in IGNORED_FILES
           and f.suffix.lower() in LANGUAGE_BY_EXTENSION
    )

    return files


def index_code(episode: Path):

    code_dir = episode / "code"
    processing = episode / "processing"
    output_path = processing / "code_assets.json"

    existing_descriptions = {}

    if output_path.exists():

        existing = load_json(output_path)

        existing_descriptions = {
            asset["id"]: asset["description"]
            for asset in existing.get("codeAssets", [])
        }

    files = list_code_files(code_dir)

    code_assets = []

    for index, file in enumerate(files, start=1):

        asset_id = f"code-{index:03d}"

        description = existing_descriptions.get(
            asset_id,
            description_from_filename(file.name)
        )

        line_count = len(file.read_text(encoding="utf-8").splitlines())

        code_asset = {
            "id": asset_id,
            "filename": file.name,
            "path": str(file.relative_to(episode)),
            "renderPath": str(Path("episodes") / episode.name / "code" / file.relative_to(code_dir)),
            "language": LANGUAGE_BY_EXTENSION[file.suffix.lower()],
            "description": description,
            "lineCount": line_count,
        }

        hint = default_display_hint(file, code_dir)

        if hint:
            code_asset["defaultDisplay"] = hint

        code_assets.append(code_asset)

    write_json_atomic(output_path, {"codeAssets": code_assets})

    return code_assets


def main():

    parser = argparse.ArgumentParser(
        description="Index episode code/ folder into a code-asset manifest"
    )

    parser.add_argument("episode_folder")

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    code_assets = index_code(episode)

    print(f"Indexed {len(code_assets)} code asset(s).")

    for asset in code_assets:
        print(f"  [{asset['id']}] {asset['filename']} ({asset['language']}, {asset['lineCount']} lines): {asset['description']}")

    manifest_path = episode / "processing" / "manifest.json"
    assets_path = episode / "processing" / "assets.json"

    if manifest_path.exists():

        project_root = Path(__file__).resolve().parent.parent
        renderer_folder = project_root / "video-renderer"

        manifest = load_json(manifest_path)

        assets = load_json(assets_path)["assets"] if assets_path.exists() else []

        generate_episode_props_ts(manifest, renderer_folder, assets=assets, code_assets=code_assets)


if __name__ == "__main__":
    main()
