#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(
    0,
    str(PROJECT_ROOT)
)

from llm.client import LLMClient


PROMPT_FILE = PIPELINE_DIR / "prompts" / "episode_analysis.txt"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing prompt file: {path}")

    return path.read_text(encoding="utf-8")


def write_json_atomic(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    temp = path.with_suffix(".tmp.json")

    try:
        with temp.open("w", encoding="utf-8") as f:
            json.dump(data,f,indent=2,ensure_ascii=False)

        temp.replace(path)

    finally:
        if temp.exists():
            temp.unlink()


def clean_strings(value):

    if isinstance(value, dict):
        return {
            key: clean_strings(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            clean_strings(item)
            for item in value
        ]

    if isinstance(value, str):
        return " ".join(
            value.split()
        )

    return value


def analyze_episode(transcript, validation, llm: LLMClient, prompt_template: str):

    text = "\n".join(
        segment["text"]
        for segment in transcript["segments"]
    )

    validation_text = json.dumps(
        validation,
        indent=2,
        ensure_ascii=False
    )

    prompt = prompt_template.replace(
        "{transcript}",
        text
    ).replace(
        "{validation}",
        validation_text
    )

    analysis = llm.complete_json(
        prompt,
        thinking=False
    )

    analysis = clean_strings(
        analysis
    )

    return {
        "segments": len(transcript["segments"]),
        "analysis": analysis
    }


def main():

    parser = argparse.ArgumentParser(
        description="Analyze episode transcript using LLM"
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing episode analysis"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    llm = LLMClient(PROJECT_ROOT / "config.json")

    prompt_template = load_prompt(PROMPT_FILE)


    transcript_file = (
            episode
            / "processing"
            / "episode_transcript.json"
    )

    validation_file = (
            episode
            / "processing"
            / "transcript_validation.json"
    )

    output_file = (
            episode
            / "processing"
            / "episode_analysis.json"
    )


    if not transcript_file.exists():
        print(f"ERROR: Missing transcript: {transcript_file}")
        sys.exit(1)


    if output_file.exists() and not args.force:
        print("Episode analysis already exists. Skipping.")
        print(output_file)
        return


    print("Analyzing episode...")
    print()


    try:

        transcript = load_json(transcript_file)

        validation = {}

        if validation_file.exists():
            validation = load_json(validation_file)


        result = analyze_episode(
            transcript,
            validation,
            llm,
            prompt_template
        )

        write_json_atomic(
            output_file,
            result
        )

        print("Episode analysis completed.")
        print(output_file)


    except Exception as e:

        print(f"FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()