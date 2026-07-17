#!/usr/bin/env python3

import argparse
import subprocess
import sys
from pathlib import Path


def run(command, cwd=None):
    print()
    print("=" * 60)
    print("Running:")
    print(" ".join(command))
    print("=" * 60)

    result = subprocess.run(command, cwd=cwd)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}"
        )


def main():

    parser = argparse.ArgumentParser(
        description="Run video processing pipeline"
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration where supported"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    project = Path(__file__).parent


    # 1. Prepare footage
    prepare_command = [
        str(project / "prepare_footage.py"),
        str(episode)
    ]

    if args.force:
        prepare_command.append("--force")

    run(prepare_command)


    # 2. Transcription
    transcription_command = [
        str(project / "transcribe_footage.sh"),
        str(episode)
    ]

    if args.force:
        transcription_command.append("--force")

    run(transcription_command)


    # 3. Normalize transcripts
    normalize_command = [
        str(project / "normalize_transcripts.py"),
        str(episode)
    ]

    if args.force:
        normalize_command.append("--force")

    run(normalize_command)


    # 4. Merge segments
    merge_command = [
        str(project / "merge_segments.py"),
        str(episode)
    ]

    if args.force:
        merge_command.append("--force")

    run(merge_command)


    # 5. Analyze episode
    analyze_episode_command = [
        str(project / "analyze_episode.py"),
        str(episode)
    ]

    if args.force:
        analyze_episode_command.append("--force")

    run(analyze_episode_command)


    # 6. Analyze segments
    analyze_segments_command = [
        str(project / "analyze_segments.py"),
        str(episode)
    ]

    if args.force:
        analyze_segments_command.append("--force")

    run(analyze_segments_command)

    print()
    print("=" * 60)
    print("Pipeline completed successfully")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print()
        print(f"ERROR: {e}")
        sys.exit(1)