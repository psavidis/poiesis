#!/usr/bin/env python3

import json
import sys
from pathlib import Path

import ollama


MODEL = "qwen3.5:latest"


PROMPT = """
You are an expert technical YouTube video editor.

Analyze the transcript segments below.

Your task:
- Understand the technical argument.
- Identify the purpose of each section.
- Recommend what should be kept or removed.
- Identify possible editing improvements.

Return ONLY valid JSON.

The JSON format must be:

{
  "topic": "...",
  "summary": "...",
  "segments": [
    {
      "start": 0.0,
      "end": 0.0,
      "purpose": "...",
      "quality": "high|medium|low",
      "action": "keep|cut|review",
      "reason": "..."
    }
  ],
  "editing_notes": [
    {
      "type": "...",
      "reason": "..."
    }
  ]
}
"""


def analyze_segments(data):
    transcript = "\n".join(
        [
            f"[{segment['start']:.2f}s - {segment['end']:.2f}s] {segment['text']}"
            for segment in data["segments"]
        ]
    )

    prompt = PROMPT + "\n\nTranscript:\n" + transcript

    response = ollama.chat(
        model=MODEL,
        format="json",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
    )

    return json.loads(response["message"]["content"])


def main():

    if len(sys.argv) != 2:
        print("Usage: analyze_segments.py <project_folder>")
        sys.exit(1)

    project_dir = Path(sys.argv[1]).resolve()

    input_dir = project_dir / "processing" / "segments"
    output_dir = project_dir / "processing" / "analysis"

    if not input_dir.exists():
        print(f"Missing input folder: {input_dir}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    files = list(input_dir.glob("*.json"))

    if not files:
        print("No segment files found.")
        sys.exit(1)

    for file in files:

        print(f"Analyzing {file.name}")

        with file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        analysis = analyze_segments(data)

        output_file = output_dir / file.name

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "source": file.stem,
                    "analysis": analysis
                },
                f,
                indent=2,
                ensure_ascii=False
            )

    print("Analysis completed.")


if __name__ == "__main__":
    main()