#!/usr/bin/env python3

import argparse
import json
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
        key=lambda x: x.name
    )


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


def find_background_video(episode_folder: Path):

    background_dir = episode_folder / "background"

    if not background_dir.exists():
        return None

    candidates = sorted(
        f
        for f in background_dir.iterdir()
        if f.is_file()
           and f.name not in IGNORED_FILES
           and f.suffix.lower() in VIDEO_EXTENSIONS
    )

    if not candidates:
        return None

    return candidates[0]


def load_previous_manifest(episode_folder: Path):

    manifest_path = episode_folder / "processing" / "manifest.json"

    if not manifest_path.exists():
        return None

    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


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
        "backgroundVideo": None
    }

    background_video = find_background_video(episode_folder)

    if background_video:

        background_metadata = get_video_metadata(background_video)

        manifest["backgroundVideo"] = {
            "filename": background_video.name,
            "path": str(
                background_video.relative_to(episode_folder)
            ),
            "renderPath": str(
                Path("episodes")
                / episode_folder.name
                / background_video.relative_to(episode_folder)
            ),
            "duration": background_metadata["duration"],
            "fps": background_metadata["fps"],
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
        code_assets=None
):

    if assets is None:
        assets = []

    if code_assets is None:
        code_assets = []

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
                    f'      language: {json.dumps(code_asset["language"])},',
                    f'      description: {json.dumps(code_asset["description"])},',
                    f'      lineCount: {code_asset["lineCount"]},',
                    "    },",
                ]
            )

        lines.append("  ],")

    background_video = manifest.get("backgroundVideo")

    if background_video:
        lines.extend(
            [
                "  backgroundVideo: {",
                f'    filename: {json.dumps(background_video["filename"])},',
                f'    path: {json.dumps(background_video["renderPath"])},',
                f'    duration: {background_video["duration"]},',
                f'    fps: {background_video["fps"]},',
                "  },",
            ]
        )

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
        code_assets=code_assets
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