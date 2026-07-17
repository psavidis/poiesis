#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: Path, data):
    tmp_path = path.with_suffix(".tmp.json")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    tmp_path.replace(path)


def merge_segments(episode_folder: Path, force: bool):
    processing = episode_folder / "processing"

    manifest_path = processing / "manifest.json"
    segments_dir = processing / "segments"
    output_path = processing / "episode_transcript.json"

    if not manifest_path.exists():
        raise RuntimeError(
            f"Missing manifest: {manifest_path}"
        )

    if output_path.exists() and not force:
        print("Episode transcript already exists. Skipping.")
        print(output_path)
        return


    manifest = load_json(manifest_path)

    merged_segments = []
    failed = 0


    for video in manifest["videos"]:

        video_id = video["id"]
        segment_path = segments_dir / f"{video_id}.json"

        if not segment_path.exists():
            print(
                f"[{video_id}] missing segments - skipping"
            )
            failed += 1
            continue


        data = load_json(segment_path)

        for segment in data.get("segments", []):
            merged_segments.append(
                {
                    "source": data["source"],
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": segment["text"]
                }
            )


    episode_transcript = {
        "episode": episode_folder.name,
        "segments": merged_segments
    }


    write_json_atomic(
        output_path,
        episode_transcript
    )


    print()
    print("==============================")
    print("Episode transcript created")
    print("==============================")
    print(f"Segments: {len(merged_segments)}")
    print(f"Failed:   {failed}")
    print("==============================")


    if failed:
        sys.exit(1)


def main():

    parser = argparse.ArgumentParser(
        description="Merge normalized segments into episode transcript"
    )

    parser.add_argument(
        "episode_folder"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing episode transcript"
    )

    args = parser.parse_args()

    merge_segments(
        Path(args.episode_folder).resolve(),
        args.force
    )


if __name__ == "__main__":
    main()