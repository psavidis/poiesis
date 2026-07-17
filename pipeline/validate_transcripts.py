#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


LOW_LOGPROB_THRESHOLD = -1.0
HIGH_TEMPERATURE_THRESHOLD = 1.0


def load_json(path: Path):
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


def find_suspicious_segments(transcript):
    suspicious = []

    for segment in transcript.get("segments", []):

        avg_logprob = segment.get("avg_logprob")
        temperature = segment.get("temperature")

        if avg_logprob is None:
            continue

        reasons = []

        if avg_logprob < LOW_LOGPROB_THRESHOLD:
            reasons.append(
                "low_avg_logprob"
            )

        if temperature is not None and temperature >= HIGH_TEMPERATURE_THRESHOLD:
            reasons.append(
                "high_temperature"
            )

        if reasons:
            suspicious.append(
                {
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": segment["text"].strip(),
                    "reasons": reasons,
                    "avg_logprob": avg_logprob,
                    "temperature": temperature
                }
            )

    return suspicious


def group_segments(segments):
    if not segments:
        return []

    groups = []

    current = {
        "start": segments[0]["start"],
        "end": segments[0]["end"],
        "segments": [segments[0]]
    }

    for segment in segments[1:]:

        if segment["start"] - current["end"] < 2:
            current["end"] = segment["end"]
            current["segments"].append(segment)

        else:
            groups.append(current)

            current = {
                "start": segment["start"],
                "end": segment["end"],
                "segments": [segment]
            }

    groups.append(current)

    return groups


def main():

    parser = argparse.ArgumentParser(
        description="Validate Whisper transcripts"
    )

    parser.add_argument("episode_folder")

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    transcripts_dir = episode / "processing" / "transcripts"

    output = episode / "processing" / "transcript_validation.json"


    if not transcripts_dir.exists():
        print(f"ERROR: Missing transcripts folder: {transcripts_dir}")
        sys.exit(1)


    issues = []


    for transcript_file in sorted(transcripts_dir.glob("*.json")):

        transcript = load_json(transcript_file)

        suspicious = find_suspicious_segments(transcript)

        groups = group_segments(suspicious)


        for group in groups:

            issues.append(
                {
                    "transcript": transcript_file.name,
                    "start": group["start"],
                    "end": group["end"],
                    "segment_count": len(group["segments"]),
                    "segments": group["segments"]
                }
            )


    result = {
        "status": "warning" if issues else "ok",
        "issues_count": len(issues),
        "issues": issues
    }


    write_json_atomic(output, result)


    print("Transcript validation completed.")
    print(f"Issues found: {len(issues)}")
    print(output)


if __name__ == "__main__":
    main()