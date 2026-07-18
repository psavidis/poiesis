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
        raise RuntimeError(f"Folder does not exist: {folder}")

    if not folder.is_dir():
        raise RuntimeError(f"Not a folder: {folder}")

    files = list(folder.iterdir())

    if not files:
        raise RuntimeError("original_footage is empty")

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
            "original_footage must contain only video files:\n"
            + "\n".join(f" - {name}" for name in invalid)
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

    video_stream = next(
        stream
        for stream in data["streams"]
        if stream["codec_type"] == "video"
    )

    fps_parts = video_stream["r_frame_rate"].split("/")

    fps = int(fps_parts[0]) / int(fps_parts[1])

    return {
        "duration": float(data["format"]["duration"]),
        "fps": fps,
        "width": video_stream["width"],
        "height": video_stream["height"],
    }


def create_episode_symlink(
        episode_folder: Path,
        renderer_folder: Path
):
    episodes_folder = (
            renderer_folder
            / "public"
            / "episodes"
    )

    episodes_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    link = episodes_folder / episode_folder.name

    if link.exists() or link.is_symlink():

        if (
                link.is_symlink()
                and link.resolve() == episode_folder.resolve()
        ):
            print(
                f"Episode link already exists: {link}"
            )
            return

        raise RuntimeError(
            f"Existing path conflicts with episode link: {link}"
        )

    link.symlink_to(
        episode_folder,
        target_is_directory=True
    )

    print(
        "Created episode symlink:\n"
        f"{link} -> {episode_folder}"
    )


def create_manifest(
        episode_folder: Path,
        videos,
        config
):
    render = config["render"]

    manifest = {
        "version": 1,
        "episode": episode_folder.name,
        "created_at": datetime.now().isoformat(),
        "width": render["width"],
        "height": render["height"],
        "fps": render["fps"],
        "videos": [],
        "scenes": []
    }

    for index, video in enumerate(videos, start=1):

        metadata = get_video_metadata(video)

        video_id = f"{index:03d}"

        manifest["videos"].append(
            {
                "id": video_id,
                "order": index,
                "filename": video.name,
                "stem": video.stem,
                "path": str(
                    Path("episodes")
                    / episode_folder.name
                    / video.relative_to(episode_folder)
                ),
                **metadata,
            }
        )

        manifest["scenes"].append(
            {
                "id": f"scene-{video_id}",
                "videoId": video_id,
                "startFrame": 0,
                "durationInFrames": round(
                    metadata["duration"] * render["fps"]
                )
            }
        )

    return manifest


def write_manifest(
        path: Path,
        manifest
):
    temp_path = path.with_suffix(".tmp.json")

    with temp_path.open(
            "w",
            encoding="utf-8"
    ) as f:
        json.dump(
            manifest,
            f,
            indent=2,
            ensure_ascii=False
        )

    temp_path.replace(path)


def generate_episode_props_ts(
        manifest,
        renderer_folder: Path
):
    output = (
            renderer_folder
            / "generated"
            / "episode"
            / "episode-props.ts"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    lines = [
        "import type { EpisodeProps } from '../../src/episode/types';",
        "",
        "export const episodeProps: EpisodeProps = {",
        f"  width: {manifest['width']},",
        f"  height: {manifest['height']},",
        f"  fps: {manifest['fps']},",
        "  videos: [",
    ]

    for video in manifest["videos"]:
        lines.extend(
            [
                "    {",
                f'      id: "{video["id"]}",',
                f'      filename: "{video["filename"]}",',
                f'      path: "{video["path"]}",',
                f'      duration: {video["duration"]},',
                f'      fps: {video["fps"]},',
                f'      width: {video["width"]},',
                f'      height: {video["height"]},',
                "    },",
            ]
        )

    lines.extend(
        [
            "  ],",
            "  scenes: [",
        ]
    )

    for scene in manifest["scenes"]:
        lines.extend(
            [
                "    {",
                f'      id: "{scene["id"]}",',
                f'      videoId: "{scene["videoId"]}",',
                f'      startFrame: {scene["startFrame"]},',
                f'      durationInFrames: {scene["durationInFrames"]},',
                "    },",
            ]
        )

    lines.extend(
        [
            "  ],",
            "};",
            "",
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

    parser = argparse.ArgumentParser(
        description="Prepare footage and create manifest"
    )

    parser.add_argument(
        "episode_folder",
        help="Episode folder"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate manifest"
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

    config = load_config(project_root)

    renderer_folder = (
            project_root
            / "video-renderer"
    )

    if not renderer_folder.exists():
        raise RuntimeError(
            f"Cannot find renderer project: {renderer_folder}"
        )

    original = episode_folder / "original_footage"

    processing = episode_folder / "processing"

    processing.mkdir(
        exist_ok=True
    )

    manifest_path = processing / "manifest.json"

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

    print("\nProcessing order:")

    for index, video in enumerate(
            videos,
            start=1
    ):
        print(
            f"{index:2}. {video.name}"
        )

    manifest = create_manifest(
        episode_folder,
        videos,
        config
    )

    write_manifest(
        manifest_path,
        manifest
    )

    generate_episode_props_ts(
        manifest,
        renderer_folder
    )

    print()
    print(
        f"Manifest created: {manifest_path}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(
            f"ERROR: {e}"
        )
        sys.exit(1)