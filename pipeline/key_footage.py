#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_footage import generate_episode_props_ts


CHROMA_COLOR = "0x17FF1F"
CHROMA_SIMILARITY = 0.10
CHROMA_BLEND = 0.06

CROPDETECT_SAMPLE_FRAMES = 200


def load_manifest(episode):
    path = episode / "processing" / "manifest.json"

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


def most_common_crop(cropdetect_output: str):

    matches = re.findall(r"crop=(\d+:\d+:\d+:\d+)", cropdetect_output)

    if not matches:
        return None

    counts = {}

    for match in matches:
        counts[match] = counts.get(match, 0) + 1

    return max(counts, key=counts.get)


def detect_crop(source: Path):

    result = subprocess.run(
        [
            "ffmpeg",
            "-i", str(source),
            "-vframes", str(CROPDETECT_SAMPLE_FRAMES),
            "-vf", "cropdetect=24:2:0",
            "-f", "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )

    return most_common_crop(result.stderr)


def key_clip(source: Path, output: Path, crop: str | None):

    filters = []

    if crop:
        filters.append(f"crop={crop}")

    filters.append(
        f"chromakey={CHROMA_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}"
    )
    filters.append("despill=type=green:mix=0.5:expand=0")

    filter_chain = ",".join(filters)

    output.parent.mkdir(parents=True, exist_ok=True)

    temp_output = output.with_suffix(".tmp.webm")

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(source),
            "-vf", filter_chain,
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-cpu-used", "8",
            "-row-mt", "1",
            "-tile-columns", "4",
            "-deadline", "realtime",
            "-an",
            str(temp_output),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        if temp_output.exists():
            temp_output.unlink()

        raise RuntimeError(
            f"ffmpeg keying failed for {source}: {result.stderr[-2000:]}"
        )

    temp_output.replace(output)


def key_footage(episode: Path, force: bool, renderer_folder: Path | None = None):

    if renderer_folder is None:
        renderer_folder = Path(__file__).resolve().parent.parent / "video-renderer"

    manifest = load_manifest(episode)

    keyed_dir = episode / "processing" / "keyed"

    processed = 0
    skipped = 0
    failed = 0

    for video in manifest["videos"]:

        video_id = video["id"]
        source = episode / video["path"]
        output = keyed_dir / f"{video_id}.webm"

        if not source.exists():
            print(f"[{video_id}] missing source: {source}")
            failed += 1
            continue

        if output.exists() and not force:
            print(f"[{video_id}] {video['filename']}")
            print("      skipped (already exists)")
            skipped += 1
            continue

        print(f"[{video_id}] {video['filename']}")
        print("      detecting crop...")

        crop = detect_crop(source)

        if crop:
            print(f"      crop: {crop}")

        print("      keying...")

        try:
            key_clip(source, output, crop)
            processed += 1
            print("      completed")

        except Exception as e:
            print(f"      FAILED: {e}")
            failed += 1

        print()

    for video in manifest["videos"]:

        output = keyed_dir / f"{video['id']}.webm"

        if output.exists():

            video["keyedPath"] = str(
                Path("processing") / "keyed" / f"{video['id']}.webm"
            )

            video["keyedRenderPath"] = str(
                Path("episodes")
                / episode.name
                / "processing"
                / "keyed"
                / f"{video['id']}.webm"
            )

    write_json_atomic(episode / "processing" / "manifest.json", manifest)

    assets_path = episode / "processing" / "assets.json"
    assets = []

    if assets_path.exists():
        with assets_path.open("r", encoding="utf-8") as f:
            assets = json.load(f)["assets"]

    generate_episode_props_ts(manifest, renderer_folder, assets=assets)

    print("==============================")
    print("Keying summary")
    print("==============================")
    print(f"Processed: {processed}")
    print(f"Skipped:   {skipped}")
    print(f"Failed:    {failed}")
    print("==============================")

    if failed > 0:
        sys.exit(1)


def main():

    parser = argparse.ArgumentParser(
        description="Chroma-key green screen footage into alpha-matted WebM clips"
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing keyed clips"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    key_footage(episode, args.force)


if __name__ == "__main__":
    main()
