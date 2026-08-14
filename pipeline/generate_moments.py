#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from llm.client import LLMClient  # noqa: E402
from visual_placement import find_monotony_eligible_windows, filter_segments_in_window  # noqa: E402
from overlay_placement import insert_overlay_scene  # noqa: E402


PROMPT_FILE = PIPELINE_DIR / "prompts" / "moments.txt"

BOTTOM_CALLOUT_DURATION_FRAMES = 90
SIDE_TEXT_DURATION_FRAMES = 150
SIDE_IMAGE_DURATION_FRAMES = 150

MAX_MOMENTS_PER_1000_FRAMES = 1

# Presenter slides to the side for a moment's own window plus this many
# frames of transition pad on either side (Episode.tsx uses the same
# constant) — kept here so overlap-checking between two moments on the same
# parent scene accounts for the full space each one actually occupies, not
# just its bare on-screen duration.
TRANSITION_FRAMES = 24


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
            json.dump(data, f, indent=2, ensure_ascii=False)

        temp.replace(path)

    finally:
        if temp.exists():
            temp.unlink()


def group_transcript_by_clip(transcript, manifest):

    filename_to_id = {
        video["filename"]: video["id"]
        for video in manifest["videos"]
    }

    clips = {}

    for segment in transcript["segments"]:

        video_id = filename_to_id.get(segment["source"])

        if video_id is None:
            continue

        clips.setdefault(video_id, []).append(segment)

    return clips


def build_candidate_windows(scene_plan, transcript, manifest):

    fps = scene_plan["fps"]

    clips = group_transcript_by_clip(transcript, manifest)

    windows = find_monotony_eligible_windows(scene_plan)

    candidates = []

    for index, window in enumerate(windows):

        segments = clips.get(window["videoId"], [])

        matching = filter_segments_in_window(segments, window, fps)

        if not matching:
            continue

        candidates.append(
            {
                "windowId": f"w{index}",
                "sceneId": window["sceneId"],
                "videoId": window["videoId"],
                "offsetInParentFrames": window["offsetInParentFrames"],
                "maxDurationInParentFrames": window["maxDurationInParentFrames"],
                "text": " ".join(segment["text"] for segment in matching),
            }
        )

    return candidates


def format_windows_for_prompt(candidates):

    lines = []

    for candidate in candidates:
        lines.append(f"[{candidate['windowId']}]")
        lines.append(candidate["text"])
        lines.append("")

    return "\n".join(lines)


def format_assets_for_prompt(assets):

    if not assets:
        return "(none available)"

    lines = []

    for asset in assets:
        lines.append(f"[{asset['id']}] {asset['caption']}")

    return "\n".join(lines)


def normalize_for_grounding(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower())


WORD_STEM_PREFIX_LENGTH = 4


def _stem(word):
    return word[:WORD_STEM_PREFIX_LENGTH] if len(word) > WORD_STEM_PREFIX_LENGTH else word


def is_grounded(text, source_text):
    """Loose grounding check: most words in the proposed text must appear
    (or share a common stem with a word) in the source window's transcript
    text, to catch fabrication without rejecting light paraphrasing/
    inflection changes (e.g. "easier" vs "easily")."""

    proposed_words = normalize_for_grounding(text).split()

    if not proposed_words:
        return False

    source_words = set(normalize_for_grounding(source_text).split())
    source_stems = {_stem(word) for word in source_words}

    matches = sum(
        1
        for word in proposed_words
        if word in source_words or _stem(word) in source_stems
    )

    return matches / len(proposed_words) >= 0.7


def duration_for_treatment(treatment):
    return {
        "bottom-callout": BOTTOM_CALLOUT_DURATION_FRAMES,
        "side-text": SIDE_TEXT_DURATION_FRAMES,
        "side-image": SIDE_IMAGE_DURATION_FRAMES,
    }[treatment]


def propose_moments(scene_plan, transcript, manifest, assets, llm: LLMClient, prompt_template: str):

    candidates = build_candidate_windows(scene_plan, transcript, manifest)

    if not candidates:
        return []

    prompt = prompt_template.replace(
        "{windows}",
        format_windows_for_prompt(candidates)
    ).replace(
        "{assets}",
        format_assets_for_prompt(assets)
    )

    response = llm.complete_json(prompt, thinking=False)

    candidates_by_id = {c["windowId"]: c for c in candidates}
    assets_by_id = {a["id"]: a for a in assets}

    claimed_windows = set()
    proposals = []

    for moment in response.get("moments", []):

        window_id = moment.get("windowId")
        treatment = moment.get("treatment")

        candidate = candidates_by_id.get(window_id)

        if not candidate or window_id in claimed_windows:
            continue

        if treatment == "bottom-callout":

            text = moment.get("text")

            if not text or not is_grounded(text, candidate["text"]):
                continue

            claimed_windows.add(window_id)

            proposals.append(
                {
                    "windowId": window_id,
                    "sceneId": candidate["sceneId"],
                    "videoId": candidate["videoId"],
                    "offsetInParentFrames": candidate["offsetInParentFrames"],
                    "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                    "treatment": "bottom-callout",
                    "text": text,
                    "presenterSide": None,
                    "reason": moment.get("reason", ""),
                }
            )

        elif treatment == "side-text":

            text = moment.get("text")
            presenter_side = moment.get("presenterSide")

            if not text or not is_grounded(text, candidate["text"]):
                continue

            if presenter_side not in ("left", "right"):
                continue

            claimed_windows.add(window_id)

            proposals.append(
                {
                    "windowId": window_id,
                    "sceneId": candidate["sceneId"],
                    "videoId": candidate["videoId"],
                    "offsetInParentFrames": candidate["offsetInParentFrames"],
                    "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                    "treatment": "side-text",
                    "text": text,
                    "presenterSide": presenter_side,
                    "reason": moment.get("reason", ""),
                }
            )

        elif treatment == "side-image":

            asset_id = moment.get("assetId")
            presenter_side = moment.get("presenterSide")
            asset = assets_by_id.get(asset_id)

            if not asset or presenter_side not in ("left", "right"):
                continue

            claimed_windows.add(window_id)

            proposals.append(
                {
                    "windowId": window_id,
                    "sceneId": candidate["sceneId"],
                    "videoId": candidate["videoId"],
                    "offsetInParentFrames": candidate["offsetInParentFrames"],
                    "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                    "treatment": "side-image",
                    "assetId": asset_id,
                    "caption": asset["caption"],
                    "presenterSide": presenter_side,
                    "reason": moment.get("reason", ""),
                }
            )

        # else: unrecognized/omitted treatment — skip, don't guess.

    total_frames = max(
        (
            scene["timelineStartFrame"] + scene["durationInFrames"]
            for scene in scene_plan["scenes"]
            if "timelineStartFrame" in scene
        ),
        default=0,
    )

    max_moments = max(
        1,
        int(total_frames / 1000 * MAX_MOMENTS_PER_1000_FRAMES)
    )

    proposals = proposals[:max_moments]

    return dedupe_overlapping_windows(proposals)


def dedupe_overlapping_windows(proposals):
    """The presenter's on-screen window for a moment is its own span padded
    by TRANSITION_FRAMES on both sides for the slide animation (see
    Episode.tsx's layoutWindowsForScene) — two moments proposed for the same
    parent presenter scene must not have overlapping padded windows, or
    their slide animations would collide. Keeps the first proposal for each
    parent (proposals are already in the order the LLM returned them) and
    drops any later one for the same parent whose padded window overlaps an
    already-kept one, rather than letting them clobber each other visually."""

    kept_windows_by_parent = {}
    kept = []

    for proposal in proposals:

        duration = min(
            duration_for_treatment(proposal["treatment"]),
            proposal["maxDurationInParentFrames"]
        )

        start = proposal["offsetInParentFrames"] - TRANSITION_FRAMES
        end = proposal["offsetInParentFrames"] + duration + TRANSITION_FRAMES

        existing_windows = kept_windows_by_parent.setdefault(proposal["sceneId"], [])

        overlaps = any(start < w_end and end > w_start for w_start, w_end in existing_windows)

        if overlaps:
            continue

        existing_windows.append((start, end))
        kept.append(proposal)

    return kept


def merge_moment_scenes(scene_plan, proposals):
    """Merges moment overlay scenes into the plan. Each moment carries its
    own presenterSide (None for bottom-callout, "left"/"right" for the side
    treatments) — the parent presenter scene itself is never mutated, since
    the presenter's on-screen position is derived per-frame from the active
    moment's own window at render time (Episode.tsx's layoutWindowsForScene),
    not a static property of the whole scene."""

    existing_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if scene["type"] != "moment"
    ]

    scenes_by_id = {scene["id"]: scene for scene in existing_scenes}

    merged_scenes = list(existing_scenes)

    for index, proposal in enumerate(proposals):

        parent = scenes_by_id.get(proposal["sceneId"])

        if not parent:
            continue

        offset = proposal["offsetInParentFrames"]

        duration = min(
            duration_for_treatment(proposal["treatment"]),
            proposal["maxDurationInParentFrames"]
        )

        if duration <= 0:
            continue

        moment_scene = {
            "id": f"scene-moment-{index}",
            "type": "moment",
            "treatment": proposal["treatment"],
            "parentSceneId": proposal["sceneId"],
            "offsetInParentFrames": offset,
            "durationInFrames": duration,
        }

        if proposal.get("presenterSide"):
            moment_scene["presenterSide"] = proposal["presenterSide"]

        if "text" in proposal:
            moment_scene["text"] = proposal["text"]

        if "assetId" in proposal:
            moment_scene["assetId"] = proposal["assetId"]
            moment_scene["caption"] = proposal["caption"]

        insert_overlay_scene(
            merged_scenes,
            scenes_by_id,
            moment_scene,
            parent["timelineStartFrame"] + offset
        )

    scene_plan = dict(scene_plan)
    scene_plan["scenes"] = merged_scenes

    return scene_plan


def main():

    parser = argparse.ArgumentParser(
        description="Propose moment overlay scenes (bottom-callout/side-text/side-image) "
                     "from monotony-eligible transcript windows"
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate moments even if already proposed"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    processing = episode / "processing"

    transcript_file = processing / "episode_transcript.json"
    manifest_file = processing / "manifest.json"
    scene_plan_file = processing / "scene-plan.json"
    assets_file = processing / "assets.json"
    output_file = processing / "moments.json"

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
        print("Moments already proposed. Skipping.")
        print(output_file)
        return

    llm = LLMClient(PROJECT_ROOT / "config.json")
    prompt_template = load_prompt(PROMPT_FILE)

    transcript = load_json(transcript_file)
    manifest = load_json(manifest_file)
    scene_plan = load_json(scene_plan_file)

    assets = load_json(assets_file)["assets"] if assets_file.exists() else []

    print("Proposing moments...")
    print()

    try:
        proposals = propose_moments(
            scene_plan,
            transcript,
            manifest,
            assets,
            llm,
            prompt_template
        )

        write_json_atomic(output_file, {"moments": proposals})

        scene_plan = merge_moment_scenes(scene_plan, proposals)

        write_json_atomic(scene_plan_file, scene_plan)

        print(f"Proposed {len(proposals)} moment(s).")
        print(output_file)
        print(scene_plan_file)

    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
