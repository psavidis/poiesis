#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from llm.client import LLMClient  # noqa: E402
from episode_context import NO_CONTEXT_TEXT, load_episode_narrative_text  # noqa: E402
from generate_moments import (  # noqa: E402
    build_candidate_windows,
    chapters_from_scene_plan,
    format_windows_for_prompt,
    load_json,
    load_prompt,
    write_json_atomic,
)


PROMPT_FILE = PIPELINE_DIR / "prompts" / "storyboard.txt"


def propose_storyboard(scene_plan, transcript, manifest, llm: LLMClient, prompt_template: str, episode_context=None):
    """Chapter-level visual-story reasoning, as its own LLM call — split out
    from generate_moments.py so this reasoning can be reviewed and edited
    independently of (and without re-running) the per-window treatment
    decisions that used to share one call with it. Reuses
    build_candidate_windows/chapters_from_scene_plan as-is (pure, already
    exercised by generate_moments.py's own tests) since the window/chapter
    grouping this reasoning is presented against is identical either way."""

    if episode_context is None:
        episode_context = NO_CONTEXT_TEXT

    candidates = build_candidate_windows(scene_plan, transcript, manifest)

    chapters = chapters_from_scene_plan(scene_plan)

    if not candidates or not chapters:
        return []

    prompt = prompt_template.replace(
        "{windows}",
        format_windows_for_prompt(candidates, chapters)
    ).replace(
        "{episode_context}",
        episode_context
    )

    response = llm.complete_json(prompt, thinking=True)

    notes_by_chapter_id = {}

    for entry in response.get("chapters", []):

        chapter_id = entry.get("chapterId")
        notes = entry.get("notes")

        if not chapter_id or not notes:
            continue

        notes_by_chapter_id[chapter_id] = notes

    # Always return one entry per real chapter, in timeline order, even if
    # the LLM skipped one — an empty "notes" string is a clearer signal to
    # a human reviewing storyboard.json than a chapter silently missing
    # from the list, and generate_moments.py can rely on every chapter
    # having an entry rather than needing its own fallback.
    return [
        {
            "chapterId": chapter["chapterId"],
            "chapterText": chapter["text"],
            "notes": notes_by_chapter_id.get(chapter["chapterId"], ""),
        }
        for chapter in chapters
    ]


def main():

    parser = argparse.ArgumentParser(
        description="Propose chapter-level visual storyboard reasoning, "
                     "as a standalone pass before per-window moment treatments"
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate the storyboard even if already proposed"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    processing = episode / "processing"

    transcript_file = processing / "episode_transcript.json"
    manifest_file = processing / "manifest.json"
    scene_plan_file = processing / "scene-plan.json"
    output_file = processing / "storyboard.json"

    if not transcript_file.exists():
        print(f"ERROR: Missing transcript: {transcript_file}")
        sys.exit(1)

    if not manifest_file.exists():
        print(f"ERROR: Missing manifest: {manifest_file}")
        sys.exit(1)

    if not scene_plan_file.exists():
        print(f"ERROR: Missing scene plan: {scene_plan_file}")
        sys.exit(1)

    if output_file.exists() and not args.force:
        print("Storyboard already proposed. Skipping.")
        print(output_file)
        return

    llm = LLMClient(PROJECT_ROOT / "config.json")
    prompt_template = load_prompt(PROMPT_FILE)

    transcript = load_json(transcript_file)
    manifest = load_json(manifest_file)
    scene_plan = load_json(scene_plan_file)

    print("Proposing storyboard...")
    print()

    try:
        chapters = propose_storyboard(
            scene_plan,
            transcript,
            manifest,
            llm,
            prompt_template,
            episode_context=load_episode_narrative_text(episode)
        )

        write_json_atomic(output_file, {"chapters": chapters})

        print(f"Proposed storyboard notes for {len(chapters)} chapter(s).")
        print(output_file)

    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
