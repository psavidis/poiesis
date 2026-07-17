#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROMPT_TEMPLATE = """
You are analyzing a transcript segment from a video.

Analyze this segment and provide information useful for reviewing and editing the video.

Provide:

1. Main topic or purpose of this segment
2. Key ideas communicated
3. What should be kept
4. What could be improved
5. Suggested editing actions

Transcript:

{transcript}
"""


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: Path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp = path.with_suffix(".tmp.json")

    try:
        with temp.open("w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

        temp.replace(path)

    finally:
        if temp.exists():
            temp.unlink()


def ask_ollama(prompt: str):

    result = subprocess.run(
        [
            "ollama",
            "run",
            "qwen3.5:latest"
        ],
        input=prompt,
        text=True,
        capture_output=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr
        )

    return result.stdout.strip()


def analyze_segment(segment):

    transcript = segment["text"]

    prompt = PROMPT_TEMPLATE.format(
        transcript=transcript
    )

    analysis = ask_ollama(prompt)

    return {
        "source": segment["source"],
        "start": segment["start"],
        "end": segment["end"],
        "text": transcript,
        "analysis": analysis
    }


def main():

    parser = argparse.ArgumentParser(
        description="Analyze transcript segments using Ollama"
    )

    parser.add_argument(
        "episode_folder"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing analyses"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    transcript_file = (
            episode
            / "processing"
            / "episode_transcript.json"
    )

    analysis_dir = (
            episode
            / "processing"
            / "analysis"
    )


    if not transcript_file.exists():
        print(
            f"ERROR: Missing transcript: {transcript_file}"
        )
        sys.exit(1)


    transcript = load_json(
        transcript_file
    )


    processed = 0
    skipped = 0
    failed = 0


    print("Analyzing segments...")
    print()


    for index, segment in enumerate(
            transcript["segments"],
            start=1
    ):

        output = analysis_dir / f"{index:03d}.json"


        if output.exists() and not args.force:
            print(
                f"[{index:03d}] skipped (already exists)"
            )
            skipped += 1
            continue


        try:
            print(
                f"[{index:03d}] analyzing..."
            )

            result = analyze_segment(
                segment
            )

            write_json_atomic(
                output,
                result
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
    print("Analysis summary")
    print("==============================")
    print(f"Processed: {processed}")
    print(f"Skipped:   {skipped}")
    print(f"Failed:    {failed}")
    print("==============================")


    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()