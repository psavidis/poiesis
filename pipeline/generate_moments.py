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
from style import load_style  # noqa: E402


PROMPT_FILE = PIPELINE_DIR / "prompts" / "moments.txt"

MAX_DIAGRAM_NODES = 6
MAX_DIAGRAM_EDGES = 8

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


def format_code_assets_for_prompt(code_assets):

    if not code_assets:
        return "(none available)"

    lines = []

    for code_asset in code_assets:
        lines.append(f"[{code_asset['id']}] {code_asset['language']} — {code_asset['description']}")

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


def is_diagram_grounded(diagram, source_text):
    """Loosened grounding check for a proposed diagram: catches wholesale
    hallucination (e.g. a diagram about "Kubernetes" for a window that
    never mentions it) without strict-quoting each label the way
    is_grounded does for prose — diagram labels are often short single
    words/phrases ("Client", "Cache miss") where stem-matching against
    transcript text is noisier than for a full quoted sentence. A node's
    label passes if ANY of its words appear (or share a stem) in the
    source text, not is_grounded's stricter 70%-of-words threshold."""

    nodes = diagram.get("nodes", [])

    if not nodes or len(nodes) > MAX_DIAGRAM_NODES:
        return False

    edges = diagram.get("edges", [])

    if len(edges) > MAX_DIAGRAM_EDGES:
        return False

    node_ids = {node.get("id") for node in nodes}

    for edge in edges:
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            return False

    source_words = set(normalize_for_grounding(source_text).split())
    source_stems = {_stem(word) for word in source_words}

    for node in nodes:
        label = node.get("label")

        if not label:
            return False

        label_words = normalize_for_grounding(label).split()

        if not label_words:
            return False

        if not any(
            word in source_words or _stem(word) in source_stems
            for word in label_words
        ):
            return False

    return True


def duration_for_treatment(treatment, style=None):
    if style is None:
        style = load_style()

    duration_frames = style["moments"]["durationFrames"]

    return {
        "bottom-callout": duration_frames["bottomCallout"],
        "side-text": duration_frames["sideText"],
        "side-image": duration_frames["sideImage"],
        "side-code": duration_frames["sideCode"],
        "side-diagram": duration_frames["sideDiagram"],
        "full-visual": duration_frames["fullVisual"],
    }[treatment]


SIDE_TREATMENTS = {"side-text", "side-image", "side-code", "side-diagram"}


def cap_full_visual_ratio(proposals, style):
    """A full-visual moment hides the presenter entirely, so it should stay
    noticeably rarer than the side treatments — capped as a ratio of
    already-proposed side moments (style["moments"]["fullVisualMaxRatioToSideMoments"])
    rather than its own fixed density constant, so the cap scales with
    however visually busy this particular episode already is. Keeps
    proposals in their original (LLM response) order and drops full-visual
    proposals past the cap — the same "keep earliest, drop the rest"
    convention dedupe_overlapping_windows already uses."""

    side_count = sum(1 for p in proposals if p["treatment"] in SIDE_TREATMENTS)

    # At least 1: the ratio is meant to keep full-visual rarer once side
    # moments are already common, not to forbid it outright in an episode
    # that happens to have few/no side moments proposed.
    max_full_visual = max(
        1,
        int(side_count * style["moments"]["fullVisualMaxRatioToSideMoments"])
    )

    kept = []
    full_visual_count = 0

    for proposal in proposals:

        if proposal["treatment"] != "full-visual":
            kept.append(proposal)
            continue

        if full_visual_count >= max_full_visual:
            continue

        full_visual_count += 1
        kept.append(proposal)

    return kept


def propose_moments(scene_plan, transcript, manifest, assets, llm: LLMClient, prompt_template: str, code_assets=None):

    if code_assets is None:
        code_assets = []

    style = load_style()

    candidates = build_candidate_windows(scene_plan, transcript, manifest)

    if not candidates:
        return []

    prompt = prompt_template.replace(
        "{windows}",
        format_windows_for_prompt(candidates)
    ).replace(
        "{assets}",
        format_assets_for_prompt(assets)
    ).replace(
        "{code_assets}",
        format_code_assets_for_prompt(code_assets)
    )

    response = llm.complete_json(prompt, thinking=False)

    candidates_by_id = {c["windowId"]: c for c in candidates}
    assets_by_id = {a["id"]: a for a in assets}
    code_assets_by_id = {a["id"]: a for a in code_assets}

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

        elif treatment == "side-code":

            code_asset_id = moment.get("codeAssetId")
            presenter_side = moment.get("presenterSide")
            code_asset = code_assets_by_id.get(code_asset_id)

            if not code_asset or presenter_side not in ("left", "right"):
                continue

            claimed_windows.add(window_id)

            proposals.append(
                {
                    "windowId": window_id,
                    "sceneId": candidate["sceneId"],
                    "videoId": candidate["videoId"],
                    "offsetInParentFrames": candidate["offsetInParentFrames"],
                    "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                    "treatment": "side-code",
                    "codeAssetId": code_asset_id,
                    "caption": code_asset["description"],
                    "presenterSide": presenter_side,
                    "reason": moment.get("reason", ""),
                }
            )

        elif treatment == "side-diagram":

            diagram = moment.get("diagram")
            presenter_side = moment.get("presenterSide")

            if not isinstance(diagram, dict) or presenter_side not in ("left", "right"):
                continue

            if diagram.get("layout") not in ("horizontal", "vertical"):
                continue

            if not is_diagram_grounded(diagram, candidate["text"]):
                continue

            claimed_windows.add(window_id)

            proposals.append(
                {
                    "windowId": window_id,
                    "sceneId": candidate["sceneId"],
                    "videoId": candidate["videoId"],
                    "offsetInParentFrames": candidate["offsetInParentFrames"],
                    "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                    "treatment": "side-diagram",
                    "diagram": diagram,
                    "presenterSide": presenter_side,
                    "reason": moment.get("reason", ""),
                }
            )

        elif treatment == "full-visual":

            full_visual_kind = moment.get("fullVisualKind")

            if full_visual_kind == "image":

                asset_id = moment.get("assetId")
                asset = assets_by_id.get(asset_id)

                if not asset:
                    continue

                claimed_windows.add(window_id)

                proposals.append(
                    {
                        "windowId": window_id,
                        "sceneId": candidate["sceneId"],
                        "videoId": candidate["videoId"],
                        "offsetInParentFrames": candidate["offsetInParentFrames"],
                        "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                        "treatment": "full-visual",
                        "fullVisualKind": "image",
                        "assetId": asset_id,
                        "caption": asset["caption"],
                        "presenterSide": None,
                        "reason": moment.get("reason", ""),
                    }
                )

            elif full_visual_kind == "diagram":

                diagram = moment.get("diagram")

                if not isinstance(diagram, dict):
                    continue

                if diagram.get("layout") not in ("horizontal", "vertical"):
                    continue

                if not is_diagram_grounded(diagram, candidate["text"]):
                    continue

                claimed_windows.add(window_id)

                proposals.append(
                    {
                        "windowId": window_id,
                        "sceneId": candidate["sceneId"],
                        "videoId": candidate["videoId"],
                        "offsetInParentFrames": candidate["offsetInParentFrames"],
                        "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                        "treatment": "full-visual",
                        "fullVisualKind": "diagram",
                        "diagram": diagram,
                        "presenterSide": None,
                        "reason": moment.get("reason", ""),
                    }
                )

            elif full_visual_kind == "text":

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
                        "treatment": "full-visual",
                        "fullVisualKind": "text",
                        "text": text,
                        "presenterSide": None,
                        "reason": moment.get("reason", ""),
                    }
                )

            # else: missing/unrecognized fullVisualKind — skip, don't guess.

        # else: unrecognized/omitted treatment — skip, don't guess.

    proposals = cap_full_visual_ratio(proposals, style)

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
        int(total_frames / 1000 * style["moments"]["maxPer1000Frames"])
    )

    proposals = proposals[:max_moments]

    proposals = dedupe_overlapping_windows(proposals, style)

    # Clamp maxDurationInParentFrames down to the real rendered duration
    # (what merge_moment_scenes will actually use) right here, once, before
    # this ever reaches moments.json — not left for merge_moment_scenes to
    # re-derive on every call. merge_moment_scenes is also called on a
    # human-edited save (ui/server.py's update_moments) and on every
    # analyze_scenes.py re-run, both of which re-merge whatever duration is
    # already sitting in moments.json; if that field still held the raw
    # eligible-window ceiling instead of the real duration, either of those
    # re-merges would silently re-derive (and thus be unable to change) the
    # duration a human explicitly set via the preview app's drag-to-resize.
    # Clamping once here means maxDurationInParentFrames means exactly what
    # it will render as everywhere downstream, and a human edit to it always
    # sticks.
    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"]}

    for proposal in proposals:
        proposal["maxDurationInParentFrames"] = min(
            duration_for_treatment(proposal["treatment"], style),
            proposal["maxDurationInParentFrames"]
        )

        # Also reserve room for the presenter's own TRANSITION_FRAMES exit
        # pad (Episode.tsx's layoutWindowsForScene clamps its slide-back
        # window to the parent scene's own durationInFrames) — without
        # this, a moment placed close enough to the end of its parent scene
        # could have a duration that individually fits the parent, but
        # whose padded window (offset + duration + TRANSITION_FRAMES)
        # doesn't, leaving content on screen after the presenter has
        # already started sliding back to center.
        parent = scenes_by_id.get(proposal["sceneId"])

        if parent:
            room_for_content = (
                parent["durationInFrames"]
                - proposal["offsetInParentFrames"]
                - TRANSITION_FRAMES
            )
            proposal["maxDurationInParentFrames"] = max(
                0,
                min(proposal["maxDurationInParentFrames"], room_for_content)
            )

    proposals = [p for p in proposals if p["maxDurationInParentFrames"] > 0]

    return proposals


def dedupe_overlapping_windows(proposals, style=None):
    """The presenter's on-screen window for a moment is its own span padded
    by TRANSITION_FRAMES on both sides for the slide animation (see
    Episode.tsx's layoutWindowsForScene) — two moments proposed for the same
    parent presenter scene must not have overlapping padded windows, or
    their slide animations would collide. Keeps the first proposal for each
    parent (proposals are already in the order the LLM returned them) and
    drops any later one for the same parent whose padded window overlaps an
    already-kept one, rather than letting them clobber each other visually."""

    if style is None:
        style = load_style()

    kept_windows_by_parent = {}
    kept = []

    for proposal in proposals:

        duration = min(
            duration_for_treatment(proposal["treatment"], style),
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

        # maxDurationInParentFrames is already the real, final duration by
        # the time it reaches this function — propose_moments() clamps it
        # to min(the treatment's fixed length, the eligible window's
        # ceiling) once, right after the AI proposes it, specifically so
        # this merge step (and the human-edit save path in
        # ui/server.py's update_moments, which calls merge_moment_scenes
        # directly on whatever's in moments.json) never needs to re-derive
        # it. Re-deriving here via duration_for_treatment(...) would
        # silently discard a human's drag-to-lengthen edit on every save,
        # since a human-lengthened duration is by definition ABOVE the
        # treatment's own fixed default.
        duration = proposal["maxDurationInParentFrames"]

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

        # Truthiness checks, not dict-membership ("key" in proposal) —
        # proposals reaching this function come from two different shapes:
        # propose_moments builds a plain dict with only the keys that
        # genuinely apply to that treatment (membership would work there),
        # but ui/server.py's update_moments passes proposal.model_dump()'d
        # pydantic objects, which always include every optional field with
        # a None default regardless of treatment. A membership check would
        # incorrectly fire for every field on every treatment (e.g.
        # attaching assetId=None to a bottom-callout moment saved through
        # the UI) — checking truthiness instead makes both call shapes
        # behave the same way.
        if proposal.get("presenterSide"):
            moment_scene["presenterSide"] = proposal["presenterSide"]

        if proposal.get("fullVisualKind"):
            moment_scene["fullVisualKind"] = proposal["fullVisualKind"]

        if proposal.get("text"):
            moment_scene["text"] = proposal["text"]

        if proposal.get("assetId"):
            moment_scene["assetId"] = proposal["assetId"]
            moment_scene["caption"] = proposal.get("caption")

        if proposal.get("codeAssetId"):
            moment_scene["codeAssetId"] = proposal["codeAssetId"]
            moment_scene["caption"] = proposal.get("caption")

        if proposal.get("diagram"):
            moment_scene["diagram"] = proposal["diagram"]

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
    code_assets_file = processing / "code_assets.json"
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
    code_assets = load_json(code_assets_file)["codeAssets"] if code_assets_file.exists() else []

    print("Proposing moments...")
    print()

    try:
        proposals = propose_moments(
            scene_plan,
            transcript,
            manifest,
            assets,
            llm,
            prompt_template,
            code_assets=code_assets
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
