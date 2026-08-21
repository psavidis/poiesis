#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm"
}

IGNORED_FILES = {
    ".DS_Store",
    "Thumbs.db"
}


def load_config(project_root: Path):
    config_path = project_root / "config.json"

    if not config_path.exists():
        raise RuntimeError(
            f"Missing config file: {config_path}"
        )

    with config_path.open(
            "r",
            encoding="utf-8"
    ) as f:
        return json.load(f)


# Matches a leading "chapter[.part]" numeric prefix, e.g. "6", "6.1",
# "3.The Symptom...". Free-text description after the prefix (if any) is
# ignored for ordering purposes.
CHAPTER_PREFIX_RE = re.compile(r"^(\d+)(?:\.(\d+))?")


def footage_sort_key(filename: str):
    """Chapter-numeric-aware sort key. A bare "N" (no ".part") is chapter
    N's unnumbered part and must sort before "N.1", "N.2", etc. — plain
    alphabetical sort puts it after them instead, because "." sorts before
    letters/digits, which silently reorders footage recorded across
    multiple part files (see #75). Filenames without a leading numeric
    prefix (e.g. reserved-keyword names) fall back to alphabetical order,
    unchanged from today's behavior, and always sort after numbered ones.
    """

    match = CHAPTER_PREFIX_RE.match(filename)

    if not match:
        return (1, 0, 0, filename)

    chapter = int(match.group(1))
    part = int(match.group(2)) if match.group(2) else 0

    return (0, chapter, part, filename)


def validate_original_footage(folder: Path):

    if not folder.exists():
        raise RuntimeError(
            f"Folder does not exist: {folder}"
        )

    files = list(folder.iterdir())

    if not files:
        raise RuntimeError(
            "original_footage is empty"
        )

    invalid = [
        f.name
        for f in files
        if f.name not in IGNORED_FILES
           and (
                   not f.is_file()
                   or f.suffix.lower() not in VIDEO_EXTENSIONS
           )
    ]

    if invalid:
        raise RuntimeError(
            "Invalid files:\n"
            + "\n".join(invalid)
        )

    return sorted(
        [
            f
            for f in files
            if f.name not in IGNORED_FILES
               and f.suffix.lower() in VIDEO_EXTENSIONS
        ],
        key=lambda x: footage_sort_key(x.name)
    )


# The pixel formats ffmpeg/Remotion actually treat as carrying real alpha
# — not an exhaustive list of every alpha-capable codec, just the ones
# this pipeline's own outputs (key_footage.py's yuva420p webm) and common
# alpha-exported graphics are likely to use.
ALPHA_PIXEL_FORMATS = {"yuva420p", "yuva444p", "rgba", "bgra", "argb", "abgr"}


def get_video_metadata(video: Path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)

    stream = next(
        s for s in data["streams"]
        if s["codec_type"] == "video"
    )

    fps_parts = stream["r_frame_rate"].split("/")

    fps = (
            int(fps_parts[0])
            /
            int(fps_parts[1])
    )

    return {
        "duration": float(
            data["format"]["duration"]
        ),
        "fps": fps,
        "width": stream["width"],
        "height": stream["height"],
        # True for pixel formats that carry a real alpha channel (e.g.
        # yuva420p, the format key_footage.py's own chroma-keyed output
        # uses) — informational only here; nothing in prepare_footage.py
        # itself branches on it. index_backgrounds.py reads this to flag a
        # background source that's already alpha-transparent, since
        # compositing an alpha video as a background fill (rather than
        # behind the presenter) would just show through to nothing.
        "hasAlpha": stream.get("pix_fmt", "") in ALPHA_PIXEL_FORMATS,
    }


def create_episode_symlink(
        episode_folder: Path,
        renderer_folder: Path
):

    episodes_folder = (
            renderer_folder
            /
            "public"
            /
            "episodes"
    )

    episodes_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    link = (
            episodes_folder
            /
            episode_folder.name
    )

    if link.exists() or link.is_symlink():

        if (
                link.is_symlink()
                and link.resolve()
                == episode_folder.resolve()
        ):
            print(
                f"Episode link already exists: {link}"
            )
            return

        raise RuntimeError(
            f"Conflicting path exists: {link}"
        )

    link.symlink_to(
        episode_folder,
        target_is_directory=True
    )

    print(
        f"Created episode symlink:\n"
        f"{link} -> {episode_folder}"
    )


def load_previous_manifest(episode_folder: Path):

    manifest_path = episode_folder / "processing" / "manifest.json"

    if not manifest_path.exists():
        return None

    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_backgrounds_for_codegen(episode_folder: Path):
    """The selectable background library (see index_backgrounds.py),
    loaded the same defensive "exists? then read, else empty" way every
    OTHER generate_episode_props_ts call site already loads assets.json/
    code_assets.json — every stage that regenerates the codegen
    (index_assets.py, index_code.py, index_backgrounds.py, key_footage.py,
    prepare_footage.py itself) must pass this through, or whichever stage
    runs last "wins" and silently drops backgrounds from the generated
    episode-props.ts."""

    backgrounds_path = episode_folder / "processing" / "backgrounds.json"

    if not backgrounds_path.exists():
        return []

    with backgrounds_path.open("r", encoding="utf-8") as f:
        return json.load(f).get("backgrounds", [])


def create_manifest(
        episode_folder: Path,
        videos,
        config,
        previous_manifest=None
):

    render = config["render"]

    previous_keying_by_id = {}

    if previous_manifest:

        previous_keying_by_id = {
            video["id"]: {
                key: video[key]
                for key in ("keyedPath", "keyedRenderPath")
                if key in video
            }
            for video in previous_manifest.get("videos", [])
        }

    manifest = {
        "version": 1,
        "episode": episode_folder.name,
        "created_at": datetime.now().isoformat(),
        "width": render["width"],
        "height": render["height"],
        "fps": render["fps"],
        "videos": [],
        "scenes": [],
    }

    for index, video in enumerate(
            videos,
            start=1
    ):

        video_id = f"{index:03d}"

        metadata = get_video_metadata(
            video
        )

        manifest["videos"].append(
            {
                "id": video_id,
                "order": index,
                "filename": video.name,
                "stem": video.stem,
                "path": str(
                    video.relative_to(
                        episode_folder
                    )
                ),
                "renderPath": str(
                    Path("episodes")
                    / episode_folder.name
                    / video.relative_to(episode_folder)
                ),

                **metadata,
                **previous_keying_by_id.get(video_id, {}),
            }
        )

    return manifest


def write_manifest(
        path: Path,
        manifest
):

    with path.open(
            "w",
            encoding="utf-8"
    ) as f:

        json.dump(
            manifest,
            f,
            indent=2,
            ensure_ascii=False
        )


def generate_episode_props_ts(
        manifest,
        renderer_folder: Path,
        assets=None,
        code_assets=None,
        backgrounds=None
):

    if assets is None:
        assets = []

    if code_assets is None:
        code_assets = []

    if backgrounds is None:
        backgrounds = []

    output = (
            renderer_folder
            /
            "generated"
            /
            "episode"
            /
            "episode-props.ts"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    lines = [
        "import type { EpisodeBaseProps } from '../../src/episode/types';",
        "",
        "export const episodeProps: EpisodeBaseProps = {",
        f"  width: {manifest['width']},",
        f"  height: {manifest['height']},",
        f"  fps: {manifest['fps']},",
        "  videos: [",
    ]


    for video in manifest["videos"]:

        video_lines = [
            "    {",
            f'      id: "{video["id"]}",',
            f'      filename: "{video["filename"]}",',
            f'      path: "{video["renderPath"]}",',
        ]

        if video.get("keyedRenderPath"):
            video_lines.append(
                f'      keyedPath: "{video["keyedRenderPath"]}",'
            )

        video_lines.extend(
            [
                f'      duration: {video["duration"]},',
                f'      fps: {video["fps"]},',
                f'      width: {video["width"]},',
                f'      height: {video["height"]},',
                "    },",
            ]
        )

        lines.extend(video_lines)


    lines.extend(
        [
            "  ],",
            "  assets: [",
        ]
    )

    for asset in assets:

        lines.extend(
            [
                "    {",
                f'      id: {json.dumps(asset["id"])},',
                f'      filename: {json.dumps(asset["filename"])},',
                f'      path: {json.dumps(asset["renderPath"])},',
                f'      caption: {json.dumps(asset["caption"])},',
                f'      mediaType: {json.dumps(asset.get("mediaType", "image"))},',
                *([f'      keyColor: {json.dumps(asset["keyColor"])},'] if asset.get("keyColor") else []),
                "    },",
            ]
        )

    lines.append("  ],")

    if code_assets:

        lines.append("  codeAssets: [")

        for code_asset in code_assets:

            lines.extend(
                [
                    "    {",
                    f'      id: {json.dumps(code_asset["id"])},',
                    f'      filename: {json.dumps(code_asset["filename"])},',
                    f'      path: {json.dumps(code_asset["renderPath"])},',
                    f'      description: {json.dumps(code_asset["description"])},',
                    f'      kind: {json.dumps(code_asset.get("kind", "source"))},',
                    *([f'      language: {json.dumps(code_asset["language"])},'] if "language" in code_asset else []),
                    *([f'      lineCount: {code_asset["lineCount"]},'] if "lineCount" in code_asset else []),
                    *([f'      keyColor: {json.dumps(code_asset["keyColor"])},'] if code_asset.get("keyColor") else []),
                    "    },",
                ]
            )

        lines.append("  ],")

    if backgrounds:
        lines.append("  backgrounds: [")

        for background in backgrounds:
            lines.extend(
                [
                    "    {",
                    f'      id: {json.dumps(background["id"])},',
                    f'      filename: {json.dumps(background["filename"])},',
                    f'      path: {json.dumps(background["renderPath"])},',
                    f'      caption: {json.dumps(background["caption"])},',
                    f'      mediaType: {json.dumps(background["mediaType"])},',
                    *([f'      duration: {background["duration"]},'] if "duration" in background else []),
                    *([f'      fps: {background["fps"]},'] if "fps" in background else []),
                    "    },",
                ]
            )

        lines.append("  ],")

    lines.extend(
        [
            "};",
            ""
        ]
    )


    output.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print(
        f"Generated episode props: {output}"
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "episode_folder"
    )

    parser.add_argument(
        "--force",
        action="store_true"
    )

    args = parser.parse_args()


    episode_folder = Path(
        args.episode_folder
    ).resolve()


    project_root = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )


    renderer_folder = (
            project_root
            /
            "video-renderer"
    )


    config = load_config(
        project_root
    )


    original = (
            episode_folder
            /
            "original_footage"
    )


    print(
        f"Validating: {original}"
    )


    videos = validate_original_footage(
        original
    )


    print(
        f"Found {len(videos)} videos"
    )


    create_episode_symlink(
        episode_folder,
        renderer_folder
    )


    processing = (
            episode_folder
            /
            "processing"
    )

    processing.mkdir(
        exist_ok=True
    )


    previous_manifest = load_previous_manifest(episode_folder)

    manifest = create_manifest(
        episode_folder,
        videos,
        config,
        previous_manifest=previous_manifest
    )


    manifest_path = (
            processing
            /
            "manifest.json"
    )


    write_manifest(
        manifest_path,
        manifest
    )


    assets_path = processing / "assets.json"
    assets = []

    if assets_path.exists():
        with assets_path.open("r", encoding="utf-8") as f:
            assets = json.load(f)["assets"]

    code_assets_path = processing / "code_assets.json"
    code_assets = []

    if code_assets_path.exists():
        with code_assets_path.open("r", encoding="utf-8") as f:
            code_assets = json.load(f)["codeAssets"]

    generate_episode_props_ts(
        manifest,
        renderer_folder,
        assets=assets,
        code_assets=code_assets,
        backgrounds=load_backgrounds_for_codegen(episode_folder)
    )


    print()
    print(
        f"Manifest created: {manifest_path}"
    )

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(
            f"ERROR: {e}"
        )
        sys.exit(1)