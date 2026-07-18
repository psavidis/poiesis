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


def create_manifest(episode_folder: Path, videos):
    manifest = {
        "version": 1,
        "episode": episode_folder.name,
        "created_at": datetime.now().isoformat(),
        "videos": []
    }

    for index, video in enumerate(videos, start=1):
        metadata = get_video_metadata(video)

        manifest["videos"].append(
            {
                "id": f"{index:03d}",
                "order": index,
                "filename": video.name,
                "stem": video.stem,
                "path": str(video.relative_to(episode_folder)),
                **metadata,
            }
        )

    return manifest


def write_manifest(path: Path, manifest):
    temp_path = path.with_suffix(".tmp.json")

    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(
            manifest,
            f,
            indent=2,
            ensure_ascii=False
        )

    temp_path.replace(path)


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
        help="Regenerate manifest even if it exists"
    )

    args = parser.parse_args()

    episode_folder = Path(args.episode_folder).resolve()

    original = episode_folder / "original_footage"

    processing = episode_folder / "processing"
    processing.mkdir(exist_ok=True)

    manifest_path = processing / "manifest.json"

    if manifest_path.exists() and not args.force:
        print("Manifest already exists. Skipping.")
        print(manifest_path)
        return

    print(f"Validating: {original}")

    videos = validate_original_footage(original)

    print(f"Found {len(videos)} videos")

    print("\nProcessing order:")
    for index, video in enumerate(videos, start=1):
        print(f"{index:2}. {video.name}")

    manifest = create_manifest(
        episode_folder,
        videos
    )

    write_manifest(
        manifest_path,
        manifest
    )

    print()
    print(f"Manifest created: {manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)