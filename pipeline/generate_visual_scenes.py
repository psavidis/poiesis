#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from llm.client import LLMClient
from visual_placement import find_monotony_eligible_windows, filter_segments_in_window


PROMPT_FILE = PIPELINE_DIR / "prompts" / "visual_scenes.txt"

EMPHASIS_DURATION_FRAMES = 90
IMAGE_DURATION_FRAMES = 120

MAX_VISUAL_SCENES_PER_1000_FRAMES = 1


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


def propose_visual_scenes(scene_plan, transcript, manifest, assets, llm: LLMClient, prompt_template: str):

    candidates = build_candidate_windows(scene_plan, transcript, manifest)

    if not candidates:
        return [], []

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

    emphasis_proposals = []

    for emphasis in response.get("emphases", []):

        window_id = emphasis.get("windowId")
        text = emphasis.get("text")

        candidate = candidates_by_id.get(window_id)

        if not candidate or not text or window_id in claimed_windows:
            continue

        if not is_grounded(text, candidate["text"]):
            continue

        claimed_windows.add(window_id)

        emphasis_proposals.append(
            {
                "windowId": window_id,
                "sceneId": candidate["sceneId"],
                "videoId": candidate["videoId"],
                "offsetInParentFrames": candidate["offsetInParentFrames"],
                "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                "text": text,
                "reason": emphasis.get("reason", ""),
            }
        )

    image_proposals = []

    for image in response.get("images", []):

        window_id = image.get("windowId")
        asset_id = image.get("assetId")

        candidate = candidates_by_id.get(window_id)
        asset = assets_by_id.get(asset_id)

        if not candidate or not asset or window_id in claimed_windows:
            continue

        claimed_windows.add(window_id)

        image_proposals.append(
            {
                "windowId": window_id,
                "sceneId": candidate["sceneId"],
                "videoId": candidate["videoId"],
                "offsetInParentFrames": candidate["offsetInParentFrames"],
                "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                "assetId": asset_id,
                "caption": asset["caption"],
                "reason": image.get("reason", ""),
            }
        )

    total_frames = max(
        (
            scene["timelineStartFrame"] + scene["durationInFrames"]
            for scene in scene_plan["scenes"]
        ),
        default=0,
    )

    max_scenes = max(
        1,
        int(total_frames / 1000 * MAX_VISUAL_SCENES_PER_1000_FRAMES)
    )

    combined = [("emphasis", p) for p in emphasis_proposals] + [("image", p) for p in image_proposals]
    combined = combined[:max_scenes]

    emphasis_proposals = [p for kind, p in combined if kind == "emphasis"]
    image_proposals = [p for kind, p in combined if kind == "image"]

    return emphasis_proposals, image_proposals


def _absolute_position(scene, scenes_by_id):
    """Resolve a scene's absolute timelineStartFrame. Track scenes carry
    this directly; overlay scenes resolve it via their parent."""

    if "timelineStartFrame" in scene:
        return scene["timelineStartFrame"]

    parent = scenes_by_id[scene["parentSceneId"]]

    return parent["timelineStartFrame"] + scene["offsetInParentFrames"]


def _insert_overlay_scene(merged_scenes, scenes_by_id, overlay_scene, absolute_position):

    insert_at = len(merged_scenes)

    for i, scene in enumerate(merged_scenes):
        if _absolute_position(scene, scenes_by_id) > absolute_position:
            insert_at = i
            break

    merged_scenes.insert(insert_at, overlay_scene)


def merge_emphasis_scenes(scene_plan, proposals):

    existing_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if scene["type"] != "emphasis"
    ]

    scenes_by_id = {scene["id"]: scene for scene in existing_scenes}

    merged_scenes = list(existing_scenes)

    for index, proposal in enumerate(proposals):

        parent = scenes_by_id.get(proposal["sceneId"])

        if not parent:
            continue

        offset = proposal["offsetInParentFrames"]

        duration = min(
            EMPHASIS_DURATION_FRAMES,
            proposal["maxDurationInParentFrames"]
        )

        if duration <= 0:
            continue

        emphasis_scene = {
            "id": f"scene-emphasis-{index}",
            "type": "emphasis",
            "text": proposal["text"],
            "parentSceneId": proposal["sceneId"],
            "offsetInParentFrames": offset,
            "durationInFrames": duration,
        }

        _insert_overlay_scene(
            merged_scenes,
            scenes_by_id,
            emphasis_scene,
            parent["timelineStartFrame"] + offset
        )

    scene_plan = dict(scene_plan)
    scene_plan["scenes"] = merged_scenes

    return scene_plan


def merge_image_scenes(scene_plan, proposals):

    existing_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if scene["type"] != "image"
    ]

    scenes_by_id = {scene["id"]: scene for scene in existing_scenes}

    merged_scenes = list(existing_scenes)

    for index, proposal in enumerate(proposals):

        parent = scenes_by_id.get(proposal["sceneId"])

        if not parent:
            continue

        offset = proposal["offsetInParentFrames"]

        duration = min(
            IMAGE_DURATION_FRAMES,
            proposal["maxDurationInParentFrames"]
        )

        if duration <= 0:
            continue

        image_scene = {
            "id": f"scene-image-{index}",
            "type": "image",
            "assetId": proposal["assetId"],
            "caption": proposal["caption"],
            "display": "inset",
            "parentSceneId": proposal["sceneId"],
            "offsetInParentFrames": offset,
            "durationInFrames": duration,
        }

        _insert_overlay_scene(
            merged_scenes,
            scenes_by_id,
            image_scene,
            parent["timelineStartFrame"] + offset
        )

    scene_plan = dict(scene_plan)
    scene_plan["scenes"] = merged_scenes

    return scene_plan


def main():

    parser = argparse.ArgumentParser(
        description="Propose emphasis overlay scenes from monotony-eligible transcript windows"
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate visual scenes even if already applied"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    processing = episode / "processing"

    transcript_file = processing / "episode_transcript.json"
    manifest_file = processing / "manifest.json"
    scene_plan_file = processing / "scene-plan.json"
    assets_file = processing / "assets.json"
    output_file = processing / "visual_scenes.json"

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
        print("Visual scenes already proposed. Skipping.")
        print(output_file)
        return

    llm = LLMClient(PROJECT_ROOT / "config.json")
    prompt_template = load_prompt(PROMPT_FILE)

    transcript = load_json(transcript_file)
    manifest = load_json(manifest_file)
    scene_plan = load_json(scene_plan_file)

    assets = load_json(assets_file)["assets"] if assets_file.exists() else []

    print("Proposing visual scenes...")
    print()

    try:
        emphasis_proposals, image_proposals = propose_visual_scenes(
            scene_plan,
            transcript,
            manifest,
            assets,
            llm,
            prompt_template
        )

        write_json_atomic(
            output_file,
            {"emphases": emphasis_proposals, "images": image_proposals}
        )

        scene_plan = merge_emphasis_scenes(scene_plan, emphasis_proposals)
        scene_plan = merge_image_scenes(scene_plan, image_proposals)

        write_json_atomic(scene_plan_file, scene_plan)

        print(
            f"Proposed {len(emphasis_proposals)} emphasis scene(s) "
            f"and {len(image_proposals)} image scene(s)."
        )
        print(output_file)
        print(scene_plan_file)

    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
