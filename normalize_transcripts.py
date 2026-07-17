#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


def load_manifest(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(".tmp.json")

    try:
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

        temp_path.replace(path)

    finally:
        if temp_path.exists():
            temp_path.unlink()


def normalize_transcript(
        source: str,
        transcript_path: Path,
        output_path: Path
):
    with transcript_path.open("r", encoding="utf-8") as f:
        transcript = json.load(f)

    normalized = {
        "source": source,
        "language": transcript.get("language"),
        "segments": [
            {
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"].strip(),
            }
            for segment in transcript.get("segments", [])
        ],
    }

    write_json_atomic(
        output_path,
        normalized
    )


def main():

    parser = argparse.ArgumentParser(
        description="Normalize Whisper transcripts into pipeline segments"
    )

    parser.add_argument(
        "episode_folder",
        help="Episode folder"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing segment files"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    processing = episode / "processing"

    manifest_path = processing / "manifest.json"
    transcripts_dir = processing / "transcripts"
    segments_dir = processing / "segments"


    if not manifest_path.exists():
        print(f"ERROR: Missing manifest: {manifest_path}")
        sys.exit(1)


    manifest = load_manifest(manifest_path)

    segments_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    processed = 0
    skipped = 0
    failed = 0


    print("Normalizing transcripts...")
    print()


    for video in manifest["videos"]:

        video_id = video["id"]
        source = video["filename"]

        transcript_path = transcripts_dir / f"{video_id}.json"
        output_path = segments_dir / f"{video_id}.json"


        if not transcript_path.exists():
            print(
                f"[{video_id}] missing transcript"
            )
            failed += 1
            continue


        if output_path.exists() and not args.force:
            print(
                f"[{video_id}] {source}"
            )
            print(
                "      skipped (already exists)"
            )

            skipped += 1
            continue


        try:
            print(
                f"[{video_id}] {source}"
            )
            print(
                "      normalizing..."
            )


            normalize_transcript(
                source,
                transcript_path,
                output_path
            )


            processed += 1

            print(
                "      completed"
            )


        except Exception as e:
            print(
                f"      FAILED: {e}"
            )
            failed += 1


        print()


    print("==============================")
    print("Normalization summary")
    print("==============================")
    print(f"Processed: {processed}")
    print(f"Skipped:   {skipped}")
    print(f"Failed:    {failed}")
    print("==============================")


    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()