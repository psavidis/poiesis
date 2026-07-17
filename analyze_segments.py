#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

from llm.client import LLMClient


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return f.read()


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


def analyze_segment(segment, episode_context, llm, prompt_template):
    transcript = segment["text"]

    prompt = prompt_template.format(
        episode_analysis=json.dumps(episode_context, indent=2, ensure_ascii=False),
        transcript=transcript
    )

    analysis = llm.complete(prompt)

    return {
        "source": segment["source"],
        "start": segment["start"],
        "end": segment["end"],
        "text": transcript,
        "analysis": analysis
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze transcript segments using LLM")

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing analyses"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    project = Path(__file__).parent

    llm = LLMClient(project / "config.json")

    episode_transcript_file = episode / "processing" / "episode_transcript.json"
    episode_analysis_file = episode / "processing" / "episode_analysis.json"
    analysis_dir = episode / "processing" / "analysis"
    prompt_file = project / "prompts" / "segment_analysis.txt"


    if not episode_transcript_file.exists():
        print(f"ERROR: Missing transcript: {episode_transcript_file}")
        sys.exit(1)

    if not episode_analysis_file.exists():
        print(f"ERROR: Missing episode analysis: {episode_analysis_file}")
        sys.exit(1)

    if not prompt_file.exists():
        print(f"ERROR: Missing prompt template: {prompt_file}")
        sys.exit(1)


    transcript = load_json(episode_transcript_file)
    episode_analysis = load_json(episode_analysis_file)
    prompt_template = load_prompt(prompt_file)


    processed = 0
    skipped = 0
    failed = 0


    print("Analyzing segments...")
    print()


    for index, segment in enumerate(transcript["segments"], start=1):

        output = analysis_dir / f"{index:03d}.json"


        if output.exists() and not args.force:
            print(f"[{index:03d}] skipped (already exists)")
            skipped += 1
            continue


        try:
            print(f"[{index:03d}] analyzing...")

            result = analyze_segment(
                segment,
                episode_analysis,
                llm,
                prompt_template
            )

            write_json_atomic(output, result)

            processed += 1

            print("      completed")


        except Exception as e:
            print(f"      FAILED: {e}")
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