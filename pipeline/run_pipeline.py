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

    result = subprocess.run(
        command,
        cwd=cwd
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}"
        )


def main():

    parser = argparse.ArgumentParser(
        description="Run video processing pipeline"
    )

    parser.add_argument(
        "episode_folder"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration where supported"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    pipeline = Path(__file__).parent


    # 1. Prepare footage
    prepare_command = [
        str(pipeline / "prepare_footage.py"),
        str(episode)
    ]

    if args.force:
        prepare_command.append("--force")

    run(prepare_command)


    project = pipeline.parent

    # 2. Transcription
    transcription_command = [
        str(project / "transcribe_footage.sh"),
        str(episode)
    ]

    if args.force:
        transcription_command.append("--force")

    run(transcription_command)


    # 3. Validate transcripts
    validation_command = [
        str(pipeline / "validate_transcripts.py"),
        str(episode)
    ]

    run(validation_command)


    # 4. Normalize transcripts
    normalize_command = [
        str(pipeline / "normalize_transcripts.py"),
        str(episode)
    ]

    if args.force:
        normalize_command.append("--force")

    run(normalize_command)


    # 5. Merge segments
    merge_command = [
        str(pipeline / "merge_segments.py"),
        str(episode)
    ]

    if args.force:
        merge_command.append("--force")

    run(merge_command)


    # 6. Analyze episode
    analysis_command = [
        str(pipeline / "analyze_episode.py"),
        str(episode)
    ]

    if args.force:
        analysis_command.append("--force")

    run(analysis_command)

    # 7. Generate episode assets
    assets_command = [
        str(pipeline / "generate_episode_assets.py"),
        str(episode)
    ]

    if args.force:
        assets_command.append("--force")

    run(assets_command)

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