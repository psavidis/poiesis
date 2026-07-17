#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path):

    with path.open(
            "r",
            encoding="utf-8"
    ) as f:
        return json.load(f)


def write_text(path: Path, content: str):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
            "w",
            encoding="utf-8"
    ) as f:
        f.write(content)


def format_timestamp(seconds):

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{millis:03d}"
    )


def generate_srt(transcript):

    lines = []

    for index, segment in enumerate(
            transcript["segments"],
            start=1
    ):

        start = format_timestamp(
            segment["start"]
        )

        end = format_timestamp(
            segment["end"]
        )

        text = segment["text"].strip()

        lines.append(
            f"{index}\n"
            f"{start} --> {end}\n"
            f"{text}\n"
        )

    return "\n".join(lines)


def generate_review_notes(analysis):

    lines = []

    lines.append(
        "# Episode Review Notes\n"
    )


    issues = analysis.get(
        "issues",
        []
    )


    if not issues:

        lines.append(
            "No issues detected.\n"
        )

        return "\n".join(lines)


    for issue in issues:

        lines.append(
            f"## {issue.get('severity', 'unknown').upper()} "
            f"{issue.get('start')}s - {issue.get('end')}s\n"
        )

        lines.append(
            issue.get(
                "assessment",
                ""
            )
        )

        lines.append(
            ""
        )


    return "\n".join(lines)


def main():

    parser = argparse.ArgumentParser(
        description="Generate episode assets"
    )

    parser.add_argument(
        "episode_folder"
    )

    parser.add_argument(
        "--force",
        action="store_true"
    )

    args = parser.parse_args()


    episode = Path(
        args.episode_folder
    ).resolve()


    processing = (
            episode
            / "processing"
    )


    transcript_file = (
            processing
            / "episode_transcript.json"
    )

    analysis_file = (
            processing
            / "episode_analysis.json"
    )


    if not transcript_file.exists():

        print(
            f"Missing transcript: {transcript_file}"
        )

        sys.exit(1)


    if not analysis_file.exists():

        print(
            f"Missing analysis: {analysis_file}"
        )

        sys.exit(1)


    print(
        "Generating episode assets..."
    )


    try:

        transcript = load_json(
            transcript_file
        )

        analysis = load_json(
            analysis_file
        )


        subtitles = generate_srt(
            transcript
        )

        write_text(
            processing / "subtitles.srt",
            subtitles
        )


        notes = generate_review_notes(
            analysis["analysis"]
        )

        write_text(
            processing / "review_notes.md",
            notes
        )


        write_text(processing / "chapters.txt","# Chapters\n\nTODO\n")


        print("Episode assets generated.")


    except Exception as e:

        print(
            f"FAILED: {e}"
        )

        sys.exit(1)


if __name__ == "__main__":

    main()