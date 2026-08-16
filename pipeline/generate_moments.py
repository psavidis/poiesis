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
from episode_context import NO_CONTEXT_TEXT, load_episode_narrative_text  # noqa: E402


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


def chapters_from_scene_plan(scene_plan):
    """The episode's chapter structure, derived from already-merged "title"
    scenes (generate_title_scenes.py runs before this stage — see
    run_pipeline.py) — each chapter starts at a title card's own
    timelineStartFrame and runs until the next title card (or the episode's
    end). No chapter-scoped state is stored anywhere; this is recomputed
    fresh from scene_plan every call, same "derive, don't persist redundant
    state" convention find_monotony_eligible_windows already follows.
    Returns chapters in timeline order, each with a stable "chapterId"
    (c0, c1, ...) an episode-relative index gives, plus its own start/end
    absolute frame bounds (end is None for the last chapter — open-ended)."""

    titles = sorted(
        (s for s in scene_plan["scenes"] if s["type"] == "title"),
        key=lambda s: s["timelineStartFrame"]
    )

    chapters = []

    for index, title in enumerate(titles):

        chapters.append(
            {
                "chapterId": f"c{index}",
                "text": title["text"],
                "start": title["timelineStartFrame"],
                "end": titles[index + 1]["timelineStartFrame"] if index + 1 < len(titles) else None,
            }
        )

    return chapters


def chapter_for_absolute_frame(chapters, absolute_frame):
    """Which chapter (if any) a given absolute timeline frame falls in —
    None for anything before the episode's first title card (the performed
    intro, which generate_title_scenes.py deliberately never titles)."""

    for chapter in chapters:

        if absolute_frame < chapter["start"]:
            continue

        if chapter["end"] is None or absolute_frame < chapter["end"]:
            return chapter["chapterId"]

    return None


def build_candidate_windows(scene_plan, transcript, manifest):

    fps = scene_plan["fps"]

    clips = group_transcript_by_clip(transcript, manifest)

    windows = find_monotony_eligible_windows(scene_plan)

    scenes_by_id = {scene["id"]: scene for scene in scene_plan["scenes"] if "timelineStartFrame" in scene}
    chapters = chapters_from_scene_plan(scene_plan)

    candidates = []

    for index, window in enumerate(windows):

        segments = clips.get(window["videoId"], [])

        matching = filter_segments_in_window(segments, window, fps)

        if not matching:
            continue

        parent = scenes_by_id.get(window["sceneId"])
        absolute_frame = (
            parent["timelineStartFrame"] + window["offsetInParentFrames"]
            if parent else None
        )

        candidates.append(
            {
                "windowId": f"w{index}",
                "sceneId": window["sceneId"],
                "videoId": window["videoId"],
                "offsetInParentFrames": window["offsetInParentFrames"],
                "maxDurationInParentFrames": window["maxDurationInParentFrames"],
                "text": " ".join(segment["text"] for segment in matching),
                "chapterId": (
                    chapter_for_absolute_frame(chapters, absolute_frame)
                    if absolute_frame is not None else None
                ),
            }
        )

    return candidates


def format_windows_for_prompt(candidates, chapters=None):
    """Groups candidate windows under their chapter heading (falling back to
    an "(intro)" heading for windows before the first title card, or
    "(unplaced)" for the rare case a window's parent scene can't be
    resolved) — a director reasoning about one chapter's visual story at a
    time needs its windows presented together, not as one flat list with no
    structure. chapters is optional so callers/tests that only care about
    the flat-list behavior can omit it.

    The heading includes the real chapterId (e.g. "[c0]") alongside the
    human-readable title text — generate_storyboard.py's prompt asks the
    LLM to key its per-chapter notes by chapterId, and without the id
    actually shown here the model has nothing to reference but the title
    text itself, which doesn't match storyboard.json's real chapterId
    values and silently breaks the lookup in propose_storyboard."""

    chapters_by_id = {c["chapterId"]: c for c in (chapters or [])}

    grouped = {}
    order = []

    for candidate in candidates:

        chapter_id = candidate.get("chapterId")

        if chapter_id not in grouped:
            grouped[chapter_id] = []
            order.append(chapter_id)

        grouped[chapter_id].append(candidate)

    lines = []

    for chapter_id in order:

        heading = "(intro, before the first chapter)"

        if chapter_id in chapters_by_id:
            heading = f'Chapter [{chapter_id}] "{chapters_by_id[chapter_id]["text"]}"'
        elif chapter_id is not None:
            heading = "(unplaced)"

        lines.append(f"=== {heading} ===")
        lines.append("")

        for candidate in grouped[chapter_id]:
            lines.append(f"[{candidate['windowId']}]")
            lines.append(candidate["text"])
            lines.append("")

    return "\n".join(lines)


def format_assets_for_prompt(assets):

    if not assets:
        return "(none available)"

    lines = []

    for asset in assets:
        # The suggestion annotation comes from the user's own folder
        # organization (see index_assets.py's default_display_hint) — a
        # nudge for the prompt to weigh, not a rule; the surrounding
        # prompt text (moments.txt) is explicit that the AI should still
        # judge relevance/centrality per its existing full-visual criteria
        # rather than treating a hinted asset as a guaranteed full-visual.
        suggestion = " (suggested: full screen)" if asset.get("defaultDisplay") == "full" else ""
        lines.append(f"[{asset['id']}] {asset['caption']}{suggestion}")

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


def _phrase_grounded(text, source_words, source_stems):
    """Shared any-word-matches check used by is_terms_grounded and
    is_comparison_grounded: a short phrase counts as grounded if at least
    one of its words (or stems) actually appears in the window's transcript
    text — looser than is_grounded's 70%-of-words threshold, which is tuned
    for full sentences, not short labels/terms."""

    if not text:
        return False

    words = normalize_for_grounding(text).split()

    if not words:
        return False

    return any(
        word in source_words or _stem(word) in source_stems
        for word in words
    )


def is_terms_grounded(terms, source_text):
    """Grounding check for a proposed "side-terms" moment: same
    any-word-matches discipline as is_diagram_grounded (terms are short
    words/phrases, not full sentences, so is_grounded's stricter
    70%-of-words threshold is noisier here) — every term must have at
    least one word (or stem) actually present in the window's transcript
    text, catching a fabricated term the presenter never said."""

    if not terms or len(terms) > MAX_SIDE_TERMS:
        return False

    source_words = set(normalize_for_grounding(source_text).split())
    source_stems = {_stem(word) for word in source_words}

    return all(
        _phrase_grounded(term.get("text"), source_words, source_stems)
        for term in terms
    )


def is_comparison_grounded(comparison, source_text):
    """Grounding check for a proposed "comparison" moment: both the "left"
    and "right" labels must each have at least one word/stem actually
    present in the window's transcript text — same discipline as
    is_terms_grounded, applied to exactly two fixed labels instead of a
    variable-length term list."""

    if not isinstance(comparison, dict):
        return False

    left = comparison.get("left")
    right = comparison.get("right")

    source_words = set(normalize_for_grounding(source_text).split())
    source_stems = {_stem(word) for word in source_words}

    return _phrase_grounded(left, source_words, source_stems) and _phrase_grounded(
        right, source_words, source_stems
    )


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
        "side-terms": duration_frames["sideTerms"],
        "comparison": duration_frames["comparison"],
        "full-visual": duration_frames["fullVisual"],
        "content-dominant-code": duration_frames["contentDominantCode"],
    }[treatment]


SIDE_TREATMENTS = {"side-text", "side-image", "side-code", "side-diagram", "side-terms"}

VALID_SIDE_TEXT_STYLES = {"quote", "title"}
VALID_TERM_LEVELS = {"muted", "primary", "accent"}
MAX_SIDE_TERMS = 4


def cap_full_visual_ratio(proposals, style):
    """A full-visual moment hides the presenter entirely, and a
    content-dominant-code moment shrinks the presenter to a small corner
    PiP (#48) — both give up significantly more presenter presence than a
    side treatment, so both stay noticeably rarer than the side
    treatments, capped as a ratio of already-proposed side moments
    (style["moments"]["fullVisualMaxRatioToSideMoments"]) rather than
    their own fixed density constant, so the cap scales with however
    visually busy this particular episode already is. Shares one cap
    (rather than a second near-duplicate config knob) since both
    represent the same underlying judgment call: "is this visual central
    enough to justify significantly reducing the presenter's presence."
    Keeps proposals in their original (LLM response) order and drops
    proposals past the cap — the same "keep earliest, drop the rest"
    convention dedupe_overlapping_windows already uses."""

    RARE_TREATMENTS = {"full-visual", "content-dominant-code"}

    side_count = sum(1 for p in proposals if p["treatment"] in SIDE_TREATMENTS)

    # At least 1: the ratio is meant to keep these rarer once side moments
    # are already common, not to forbid them outright in an episode that
    # happens to have few/no side moments proposed.
    max_rare = max(
        1,
        int(side_count * style["moments"]["fullVisualMaxRatioToSideMoments"])
    )

    kept = []
    rare_count = 0

    for proposal in proposals:

        if proposal["treatment"] not in RARE_TREATMENTS:
            kept.append(proposal)
            continue

        if rare_count >= max_rare:
            continue

        rare_count += 1
        kept.append(proposal)

    return kept


def format_storyboard_for_prompt(storyboard_chapters):
    """Renders storyboard.json's per-chapter notes as prompt text — mirrors
    format_windows_for_prompt's "=== heading ===" grouping style so the
    two sections of the prompt (storyboard reasoning, then the windows it
    applies to) read as one consistent document."""

    if not storyboard_chapters:
        return "(no storyboard reasoning available)"

    lines = []

    for chapter in storyboard_chapters:
        lines.append(f'=== Chapter "{chapter.get("chapterText", "")}" ===')
        lines.append(chapter.get("notes") or "(no notes for this chapter)")
        lines.append("")

    return "\n".join(lines)


def propose_moments(scene_plan, transcript, manifest, assets, llm: LLMClient, prompt_template: str, code_assets=None, episode_context=None, storyboard_chapters=None):

    if code_assets is None:
        code_assets = []

    if episode_context is None:
        episode_context = NO_CONTEXT_TEXT

    if storyboard_chapters is None:
        storyboard_chapters = []

    style = load_style()

    candidates = build_candidate_windows(scene_plan, transcript, manifest)

    if not candidates:
        return []

    chapters = chapters_from_scene_plan(scene_plan)

    prompt = prompt_template.replace(
        "{windows}",
        format_windows_for_prompt(candidates, chapters)
    ).replace(
        "{assets}",
        format_assets_for_prompt(assets)
    ).replace(
        "{code_assets}",
        format_code_assets_for_prompt(code_assets)
    ).replace(
        "{episode_context}",
        episode_context
    ).replace(
        "{storyboard}",
        format_storyboard_for_prompt(storyboard_chapters)
    )

    # thinking=True: committing each window's treatment against the
    # storyboard's chapter-level reasoning (rather than judging the window
    # in isolation) is a genuinely harder task than a flat per-window
    # judgment, in the same way generate_title_scenes.py already needed
    # thinking=True to reliably find real chapter boundaries across a whole
    # episode instead of a handful. The chapter-level reasoning itself now
    # happens earlier, in generate_storyboard.py's own thinking=True call.
    response = llm.complete_json(prompt, thinking=True)

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
            side_text_style = moment.get("sideTextStyle", "quote")

            if not text or not is_grounded(text, candidate["text"]):
                continue

            if presenter_side not in ("left", "right"):
                continue

            if side_text_style not in VALID_SIDE_TEXT_STYLES:
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
                    "sideTextStyle": side_text_style,
                    "presenterSide": presenter_side,
                    "reason": moment.get("reason", ""),
                }
            )

        elif treatment == "side-terms":

            terms = moment.get("terms")
            presenter_side = moment.get("presenterSide")

            if not isinstance(terms, list) or presenter_side not in ("left", "right"):
                continue

            if not all(
                isinstance(term, dict) and term.get("level") in VALID_TERM_LEVELS
                for term in terms
            ):
                continue

            if not is_terms_grounded(terms, candidate["text"]):
                continue

            claimed_windows.add(window_id)

            proposals.append(
                {
                    "windowId": window_id,
                    "sceneId": candidate["sceneId"],
                    "videoId": candidate["videoId"],
                    "offsetInParentFrames": candidate["offsetInParentFrames"],
                    "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                    "treatment": "side-terms",
                    "terms": terms,
                    "presenterSide": presenter_side,
                    "reason": moment.get("reason", ""),
                }
            )

        elif treatment == "comparison":

            comparison = moment.get("comparison")

            if not is_comparison_grounded(comparison, candidate["text"]):
                continue

            claimed_windows.add(window_id)

            proposals.append(
                {
                    "windowId": window_id,
                    "sceneId": candidate["sceneId"],
                    "videoId": candidate["videoId"],
                    "offsetInParentFrames": candidate["offsetInParentFrames"],
                    "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                    "treatment": "comparison",
                    "comparison": {"left": comparison["left"], "right": comparison["right"]},
                    "presenterSide": None,
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

        elif treatment == "content-dominant-code":

            # No presenterSide — the presenter shrinks to a fixed corner
            # PiP (Episode.tsx's LAYOUT_GEOMETRY.corner) rather than a
            # chosen side, so there's no left/right decision here, same
            # reasoning as full-visual/comparison already not requiring one.
            code_asset_id = moment.get("codeAssetId")
            code_asset = code_assets_by_id.get(code_asset_id)

            if not code_asset:
                continue

            claimed_windows.add(window_id)

            proposals.append(
                {
                    "windowId": window_id,
                    "sceneId": candidate["sceneId"],
                    "videoId": candidate["videoId"],
                    "offsetInParentFrames": candidate["offsetInParentFrames"],
                    "maxDurationInParentFrames": candidate["maxDurationInParentFrames"],
                    "treatment": "content-dominant-code",
                    "codeAssetId": code_asset_id,
                    "caption": code_asset["description"],
                    "presenterSide": None,
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

            elif full_visual_kind == "code":

                code_asset_id = moment.get("codeAssetId")
                code_asset = code_assets_by_id.get(code_asset_id)

                if not code_asset:
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
                        "fullVisualKind": "code",
                        "codeAssetId": code_asset_id,
                        "caption": code_asset["description"],
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


# Fields a human can actually change through the editor (MomentEditorPanel/
# MomentBar), and therefore worth tracking provenance for (see #57).
# "windowId"/"reason" are bookkeeping the AI attaches to its own proposal,
# never user-facing content — they're excluded so re-saving an untouched
# moment (which still round-trips these fields verbatim) never produces a
# spurious override. "sceneId"/"videoId" identify what the moment
# fundamentally is, the same reasoning edit_plan.py's EDITABLE_FIELDS
# already applies to other scene types — not something a "field edit"
# changes. "treatment" WAS excluded for the same reason until #62 made one
# narrow slice of it editable (switching among the three code
# presentations, same codeAssetId) — see switch_code_treatment below; it's
# included here so that switch is itself tracked as a human override,
# same as any other field edit.
OVERRIDABLE_MOMENT_FIELDS = {
    "offsetInParentFrames", "maxDurationInParentFrames", "presenterSide",
    "fullVisualKind", "text", "assetId", "codeAssetId", "diagram",
    "comparison", "terms", "sideTextStyle", "caption", "treatment",
}

# Which MomentTreatment values all present the SAME underlying content at
# different prominence, grouped by content type — see #62 (code, first
# slice of #42, the content-type-vs-presentation epic) and its extension
# to image/diagram. Confirmed structurally compatible by reading
# Episode.tsx's layoutWindowsForScene, which already resolves every
# "side-*" treatment to presenterSide left/right, "content-dominant-code"
# to a corner PiP, and "full-visual" to hidden — all compatible presenter-
# layout states regardless of which content type is involved. Code has
# three siblings (it alone also has a Content Dominant treatment); image
# and diagram each have exactly two (their own side-* treatment plus
# full-visual). fullVisualKind is what full-visual uses to say WHICH
# content type it's currently showing — not a separate axis to switch
# independently here.
TREATMENT_GROUPS = {
    "code": {"side-code", "content-dominant-code", "full-visual"},
    "image": {"side-image", "full-visual"},
    "diagram": {"side-diagram", "full-visual"},
}

# Any treatment outside its own group is out of scope for
# switch_moment_treatment — #42's broader "arbitrary content/presentation"
# model (switching CONTENT TYPE, e.g. image to diagram, or reaching
# treatments like bottom-callout/side-text/side-terms/comparison that
# carry fundamentally different data) is a separate, larger future change,
# not this one. Kept as a flat set (not the dict above) since checking
# "is this treatment switchable AT ALL" doesn't need to know which group
# it belongs to — switch_moment_treatment derives group membership itself,
# from the MOMENT's own current content, not from the caller.
SWITCHABLE_TREATMENTS = set().union(*TREATMENT_GROUPS.values())


def _moment_treatment_group(moment):
    """Which TREATMENT_GROUPS key describes this MOMENT's current content
    — not just its treatment string. "full-visual" alone is ambiguous
    (every group contains it, since it's the shared "make it full-screen"
    treatment for any of the three content types); the actual content type
    a full-visual moment is showing is recorded in its OWN fullVisualKind
    field, so that's what's checked for it specifically. Every other
    treatment unambiguously belongs to exactly one group by string alone.
    Returns None for a treatment that isn't in any group, or a full-visual
    moment whose fullVisualKind isn't one of the three switchable groups
    (e.g. "text", which has no side-* sibling to switch to/from)."""

    treatment = moment.get("treatment")

    if treatment == "full-visual":
        kind = moment.get("fullVisualKind")
        return kind if kind in TREATMENT_GROUPS else None

    for group, treatments in TREATMENT_GROUPS.items():
        if treatment in treatments:
            return group

    return None


def switch_moment_treatment(moment, new_treatment, scene_plan, style=None):
    """Switches an existing moment among the treatments that present the
    SAME content at different prominence (TREATMENT_GROUPS), keeping that
    content field (codeAssetId/assetId/diagram, plus caption) untouched
    while recomputing everything that's actually presentation-specific:
    duration (merge_moment_scenes trusts maxDurationInParentFrames
    verbatim, it does NOT re-derive it from treatment — see that
    function's own docstring — so a switch that didn't recompute this
    would keep rendering at the OLD treatment's duration) and the
    treatment-specific fields (presenterSide only applies to side-*
    treatments; fullVisualKind only applies to full-visual). Returns None
    (reject, don't guess) if the moment's CURRENT content type doesn't
    have new_treatment as one of its own group's treatments — e.g. an
    image moment can become full-visual, but not side-code, since that
    would silently need to invent code content that was never there; a
    full-visual TEXT moment can't become side-code either, despite
    "full-visual" itself being a valid code-group treatment, since its
    actual content isn't code (see _moment_treatment_group). This function
    deliberately does not attempt cross-content-type switching, only
    same-content presentation switching.

    style is accepted (not just loaded internally) so a caller that
    already has one loaded (e.g. a request handler serving many switches)
    doesn't reload style.json per call — same pattern duration_for_treatment
    itself already uses."""

    current_group = _moment_treatment_group(moment)

    if current_group is None or new_treatment not in TREATMENT_GROUPS[current_group]:
        return None

    if style is None:
        style = load_style()

    switched = dict(moment)
    switched["treatment"] = new_treatment

    # Clear treatment-specific fields from the OLD treatment before
    # setting the NEW treatment's own — the group's own content field
    # (and caption) are deliberately left untouched below.
    switched["presenterSide"] = None
    switched["fullVisualKind"] = None

    if new_treatment.startswith("side-"):
        # No side preference implied by a fresh switch — same default
        # (None, meaning "let the layout choose") propose_moments itself
        # uses when nothing more specific is known; the user can still
        # change side afterward via whatever presenterSide editing already
        # exists.
        switched["presenterSide"] = moment.get("presenterSide")
    elif new_treatment == "full-visual":
        switched["fullVisualKind"] = current_group

    # Same clamp propose_moments applies once at proposal time (see its
    # own comment above): the new treatment's own fixed default, further
    # capped by whatever room is actually left in the parent scene so a
    # switch near a scene's end can't produce a duration that overflows
    # it. Deliberately NOT clamped against the OLD duration — a switch to
    # a treatment with a smaller default should actually shrink, not
    # preserve an oversized leftover from the old treatment.
    new_duration = duration_for_treatment(new_treatment, style)

    parent = next((s for s in scene_plan["scenes"] if s["id"] == moment.get("sceneId")), None)

    if parent:
        room_for_content = (
            parent["durationInFrames"]
            - moment["offsetInParentFrames"]
            - TRANSITION_FRAMES
        )
        new_duration = max(0, min(new_duration, room_for_content))

    switched["maxDurationInParentFrames"] = new_duration

    return switched


def compute_overridden_fields(old_moment, new_moment):
    """Field names on new_moment whose value differs from old_moment (the
    same array-position entry currently on disk in moments.json) — the
    human-edit save paths in ui/server.py's update_moments always send the
    ENTIRE moments array back, in the same order it was fetched, so a
    positional comparison against what's currently on disk is the only
    reliable way to tell "the user actually changed this field" apart from
    "this field just round-tripped unchanged" (see #57 — sceneId+treatment
    alone can't identify a single moment, since two non-overlapping
    moments can share both on a long presenter scene).

    Starts from new_moment's OWN overriddenFields, not old_moment's — the
    client (MomentEditorPanel's "Reset to Automatic") is the one place a
    field is meant to be REMOVED from this set, by omitting it from the
    array it sends back; starting from old_moment's set instead would
    silently re-add it every time and make Reset a permanent no-op. A
    field the client didn't think to touch but that was overridden before
    still survives, though: anything in old_moment's set that new_moment's
    own set doesn't explicitly drop is carried forward below, same as
    before. Then anything ACTUALLY changed in value gets added on top,
    regardless of what either side's overriddenFields said, since a value
    change is itself definitive proof of an override."""

    overridden = set(new_moment.get("overriddenFields", old_moment.get("overriddenFields", [])))

    for field in OVERRIDABLE_MOMENT_FIELDS:
        if new_moment.get(field) != old_moment.get(field):
            overridden.add(field)

    return sorted(overridden)


def preserve_overridden_fields(old_moments, new_proposals):
    """Before a --force regeneration overwrites moments.json, copy forward
    any human-overridden field value from an old moment onto whichever new
    proposal is its best match — otherwise re-running the AI stage would
    silently discard a manually dragged duration or edited callout text
    (see #57). Unlike compute_overridden_fields (a same-array positional
    diff against a just-fetched copy), a fresh proposal batch has no
    positional correspondence to the old one at all: different windows get
    discovered, in a different order, possibly a different count. The best
    available signal is sceneId (which parent presenter scene) plus,
    when more than one old/new moment shares a sceneId, the closest
    offsetInParentFrames — approximate, but better than losing the edit
    outright, and only engaged for moments that actually have overrides to
    protect (an old moment with no overriddenFields is left alone; the AI
    is free to drop or reshape it same as any fully-automatic moment)."""

    old_by_scene = {}
    for old_moment in old_moments:
        if old_moment.get("overriddenFields"):
            old_by_scene.setdefault(old_moment["sceneId"], []).append(old_moment)

    if not old_by_scene:
        return new_proposals

    new_by_scene = {}
    for proposal in new_proposals:
        new_by_scene.setdefault(proposal["sceneId"], []).append(proposal)

    claimed_new_ids = set()

    for scene_id, old_candidates in old_by_scene.items():

        new_candidates = [p for p in new_by_scene.get(scene_id, []) if id(p) not in claimed_new_ids]

        if not new_candidates:
            continue

        for old_moment in old_candidates:

            best = min(
                new_candidates,
                key=lambda p: abs(p["offsetInParentFrames"] - old_moment["offsetInParentFrames"]),
            )

            for field in old_moment["overriddenFields"]:
                if field in old_moment:
                    best[field] = old_moment[field]

            best["overriddenFields"] = sorted(
                set(best.get("overriddenFields", [])) | set(old_moment["overriddenFields"])
            )

            claimed_new_ids.add(id(best))
            new_candidates.remove(best)

    return new_proposals


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

        if proposal.get("sideTextStyle"):
            moment_scene["sideTextStyle"] = proposal["sideTextStyle"]

        if proposal.get("terms"):
            moment_scene["terms"] = proposal["terms"]

        if proposal.get("comparison"):
            moment_scene["comparison"] = proposal["comparison"]

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
    storyboard_file = processing / "storyboard.json"
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

    if not storyboard_file.exists():
        print(f"ERROR: Missing storyboard: {storyboard_file}")
        print("Run generate_storyboard.py first — moment treatments are now decided against its chapter-level reasoning.")
        sys.exit(1)

    if output_file.exists() and not args.force:
        print("Moments already proposed. Skipping.")
        print(output_file)
        return

    # Loaded before the fresh proposal overwrites output_file, so a
    # --force regeneration can carry forward any human-overridden field
    # from the moments this run is about to replace (see #57).
    previous_moments = load_json(output_file)["moments"] if output_file.exists() else []

    llm = LLMClient(PROJECT_ROOT / "config.json")
    prompt_template = load_prompt(PROMPT_FILE)

    transcript = load_json(transcript_file)
    manifest = load_json(manifest_file)
    scene_plan = load_json(scene_plan_file)
    storyboard_chapters = load_json(storyboard_file).get("chapters", [])

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
            code_assets=code_assets,
            episode_context=load_episode_narrative_text(episode),
            storyboard_chapters=storyboard_chapters
        )

        proposals = preserve_overridden_fields(previous_moments, proposals)

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
