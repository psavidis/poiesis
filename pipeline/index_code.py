#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from index_assets import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, detect_key_color
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

# code/ isn't only real source text — a screenshot of an IDE or a screen
# recording of code being written both "demonstrate code" just as much as a
# .java file, and are common enough that a creator organizes them together
# by subject rather than by file format (see #79's design discussion). Each
# gets a "kind" tag (see CodeAssetKind in types.ts) so the renderer knows
# which treatment applies: "source" -> real Shiki-highlighted CodeBlock,
# "screenshot"/"recording" -> the same framed-image/keyed-video treatment
# graphics/ assets already get. Reuses index_assets.py's own extension
# sets/detection rather than duplicating them, so both folders recognize
# exactly the same file types.
IMAGE_CODE_EXTENSIONS = IMAGE_EXTENSIONS
VIDEO_CODE_EXTENSIONS = VIDEO_EXTENSIONS

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


CODE_FOLDER_EXTENSIONS = set(LANGUAGE_BY_EXTENSION) | IMAGE_CODE_EXTENSIONS | VIDEO_CODE_EXTENSIONS


def code_asset_kind(file: Path) -> str:
    suffix = file.suffix.lower()

    if suffix in VIDEO_CODE_EXTENSIONS:
        return "recording"

    if suffix in IMAGE_CODE_EXTENSIONS:
        return "screenshot"

    return "source"


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
           and f.suffix.lower() in CODE_FOLDER_EXTENSIONS
    )

    return files


def index_code(episode: Path):

    code_dir = episode / "code"
    processing = episode / "processing"
    output_path = processing / "code_assets.json"

    existing_descriptions = {}

    if output_path.exists():

        existing = load_json(output_path)

        # Keyed by filename, not id — see index_assets.py's own
        # existing_captions comment (#80) for why: an asset's id is purely
        # positional, so adding/removing any other file in the folder
        # shifts every later id and would silently reattach a stale
        # manually-edited description to the wrong file otherwise.
        existing_descriptions = {
            asset["filename"]: asset["description"]
            for asset in existing.get("codeAssets", [])
        }

    files = list_code_files(code_dir)

    code_assets = []

    for index, file in enumerate(files, start=1):

        asset_id = f"code-{index:03d}"

        description = existing_descriptions.get(
            file.name,
            description_from_filename(file.name)
        )

        kind = code_asset_kind(file)

        code_asset = {
            "id": asset_id,
            "filename": file.name,
            "path": str(file.relative_to(episode)),
            "renderPath": str(Path("episodes") / episode.name / "code" / file.relative_to(code_dir)),
            "description": description,
            "kind": kind,
        }

        if kind == "source":
            code_asset["language"] = LANGUAGE_BY_EXTENSION[file.suffix.lower()]
            code_asset["lineCount"] = len(file.read_text(encoding="utf-8").splitlines())
        elif kind == "recording":
            key_color = detect_key_color(file)
            if key_color:
                code_asset["keyColor"] = key_color

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
        if asset["kind"] == "source":
            detail = f"{asset['language']}, {asset['lineCount']} lines"
        else:
            detail = asset["kind"]
        print(f"  [{asset['id']}] {asset['filename']} ({detail}): {asset['description']}")

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
