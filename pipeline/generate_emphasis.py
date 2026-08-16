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
from generate_moments import group_transcript_by_clip  # noqa: E402
from generate_title_scenes import load_json, load_prompt, write_json_atomic  # noqa: E402
from overlay_placement import insert_overlay_scene  # noqa: E402
from style import load_style  # noqa: E402
from episode_context import NO_CONTEXT_TEXT, load_episode_narrative_text  # noqa: E402


PROMPT_FILE = PIPELINE_DIR / "prompts" / "emphasis.txt"

VALID_KINDS = {"word-pop", "underline", "icon-accent"}
VALID_ICONS = {"arrow", "check", "warning", "gear"}

# A beat is a quick accent, not a paraphrase of the sentence — the prompt
# asks for at most 3 words, this is the code-enforced backstop for when
# the model doesn't comply (confirmed necessary: a real run proposed a
# 6-word icon-accent phrase despite the prompt's "one or two words"
# instruction).
MAX_BEAT_WORDS = 3

# Whisper's word-level tokens carry attached sentence punctuation (e.g.
# "injection." or "well,") — correct for a transcript, but a beat is a
# punchy on-screen pop, not prose, so trailing/leading punctuation is
# stripped for display. Only strips from the OUTSIDE of a word/phrase
# (matched at start/end of the whole joined string, not mid-word), so
# internal punctuation that's actually part of a word survives — e.g.
# "self-contained" or "Bob's" keep their internal hyphen/apostrophe.
_EDGE_PUNCTUATION = re.compile(r'^[\s,.!?;:"\'’]+|[\s,.!?;:"\'’]+$')


def strip_edge_punctuation(text):
    return _EDGE_PUNCTUATION.sub("", text)


def join_words(words):
    """Whisper's word-level tokenizer sometimes attaches a hyphen to the
    FRONT of the next word instead of the end of the previous one — e.g.
    "domain-driven" comes back as two tokens, "domain" and "-driven", not
    "domain-" and "driven". A plain " ".join would render "domain -driven"
    with a stray space before the hyphen. Joining with no space whenever
    the next token starts with a hyphen produces the correct "domain-driven"
    instead, without needing to special-case punctuation generally — this
    is specifically about how Whisper splits hyphenated compounds."""

    joined = ""

    for index, word in enumerate(words):
        if index > 0 and not word.startswith("-"):
            joined += " "
        joined += word

    return joined


def words_for_presenter_scene(scene, clip_segments, fps):
    """Every word from this clip's word-level transcript data that falls
    within the scene's post-silence-trim [sourceStartFrame, sourceEndFrame)
    window, positioned relative to the scene's own start — same
    relative-positioning pattern generate_captions.py's
    captions_for_presenter_scene already uses for the same reason (stays
    correct if analyze_scenes.py's trim points shift on a re-run). Segments
    with no "words" key (not yet re-transcribed with word timestamps) are
    silently skipped — a beat needs real word timing, not a segment-level
    guess."""

    source_start = scene["sourceStartFrame"]
    source_end = scene["sourceEndFrame"]

    words = []

    for segment in clip_segments:

        for word in segment.get("words", []):

            word_start = round(word["start"] * fps)
            word_end = round(word["end"] * fps)

            clipped_start = max(word_start, source_start)
            clipped_end = min(word_end, source_end)

            if clipped_end <= clipped_start:
                continue

            text = word["word"].strip()

            if not text:
                continue

            words.append(
                {
                    "text": text,
                    "offsetInParentFrames": clipped_start - source_start,
                    "durationInFrames": clipped_end - clipped_start,
                }
            )

    return words


def build_candidate_words(scene_plan, transcript, manifest):
    """One flat, globally-id'd word list across every presenter scene, in
    timeline order — a whole-episode view (like generate_title_scenes.py's
    format_transcript_for_prompt), not one call per scene, so the model can
    reason about pacing across the whole episode in a single call rather
    than 15+ small ones with no memory of each other. wordId format is
    "<sceneId>-w<index>" so it always resolves back to an unambiguous scene
    + word, even though indices restart at 0 per scene."""

    fps = scene_plan["fps"]

    clips = group_transcript_by_clip(transcript, manifest)

    presenter_scenes = sorted(
        (s for s in scene_plan["scenes"] if s["type"] == "presenter"),
        key=lambda s: s["timelineStartFrame"]
    )

    candidates_by_word_id = {}
    scenes_by_id = {}

    for scene in presenter_scenes:

        clip_segments = clips.get(scene["videoId"], [])

        words = words_for_presenter_scene(scene, clip_segments, fps)

        if not words:
            continue

        scenes_by_id[scene["id"]] = scene

        for index, word in enumerate(words):
            word_id = f"{scene['id']}-w{index}"
            candidates_by_word_id[word_id] = {
                "sceneId": scene["id"],
                **word,
            }

    return candidates_by_word_id, scenes_by_id


def format_words_for_prompt(candidates_by_word_id):

    lines = []

    for word_id, word in candidates_by_word_id.items():
        lines.append(f"[{word_id}] {word['text']}")

    return " ".join(lines)


def normalize_for_grounding(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower())


def resolve_phrase(word_ids, candidates_by_word_id):
    """Resolves a list of wordIds to a single contiguous phrase: same
    sceneId, contiguous index order (w4, w5, w6 — not w4, w9), each id must
    actually exist. Returns None if any of that doesn't hold — a proposal
    referencing non-contiguous or unknown words is dropped, not guessed
    into shape, same discipline generate_moments.py applies to asset/code
    ids."""

    if not word_ids:
        return None

    words = []

    for word_id in word_ids:

        word = candidates_by_word_id.get(word_id)

        if word is None:
            return None

        words.append((word_id, word))

    scene_ids = {word["sceneId"] for _, word in words}

    if len(scene_ids) != 1:
        return None

    def word_index(word_id):
        # "<sceneId>-w<index>" — index is always the trailing "-wN" segment.
        return int(word_id.rsplit("-w", 1)[1])

    indices = sorted(word_index(word_id) for word_id, _ in words)

    if indices != list(range(indices[0], indices[0] + len(indices))):
        return None

    words_in_order = sorted(words, key=lambda item: word_index(item[0]))

    scene_id = scene_ids.pop()
    text = strip_edge_punctuation(join_words([word["text"] for _, word in words_in_order]))

    if not text:
        return None

    offset = words_in_order[0][1]["offsetInParentFrames"]
    end = words_in_order[-1][1]["offsetInParentFrames"] + words_in_order[-1][1]["durationInFrames"]

    return {
        "sceneId": scene_id,
        "text": text,
        "offsetInParentFrames": offset,
        "durationInFrames": max(1, end - offset),
    }


def overlaps_existing_overlay(scene_id, offset, duration, scene_plan):
    """A beat must not visually collide with an already-placed moment/image
    on the same parent presenter scene — those claim a side or the whole
    frame, and a beat popping mid-transition would look like a glitch, not
    an accent. Checked against the scene plan as it stands when this stage
    runs (after generate_moments.py in run_pipeline.py's order), not
    re-derived from any duration constant, so it reflects whatever is
    actually on the timeline right now, including any human hand-edit."""

    end = offset + duration

    for scene in scene_plan["scenes"]:

        if scene["type"] not in ("moment", "image"):
            continue

        if scene.get("parentSceneId") != scene_id:
            continue

        other_start = scene["offsetInParentFrames"]
        other_end = other_start + scene["durationInFrames"]

        if offset < other_end and end > other_start:
            return True

    return False


def propose_emphasis(scene_plan, transcript, manifest, llm: LLMClient, prompt_template: str, style=None, episode_context=None):

    if style is None:
        style = load_style()

    if episode_context is None:
        episode_context = NO_CONTEXT_TEXT

    candidates_by_word_id, scenes_by_id = build_candidate_words(scene_plan, transcript, manifest)

    if not candidates_by_word_id:
        return []

    prompt = prompt_template.replace(
        "{words}",
        format_words_for_prompt(candidates_by_word_id)
    ).replace(
        "{episode_context}",
        episode_context
    )

    response = llm.complete_json(prompt, thinking=False)

    default_duration = style["emphasis"]["defaultDurationFrames"]
    min_gap_frames = round(style["emphasis"]["minSecondsBetweenBeats"] * scene_plan["fps"])

    # Pass 1: resolve each proposal against real word data and reject
    # anything structurally invalid (unknown kind/icon, non-contiguous or
    # unknown wordIds, out-of-bounds, colliding with an already-placed
    # moment/image) — order-independent checks, so response order doesn't
    # matter yet.
    candidates = []

    for beat in response.get("beats", []):

        kind = beat.get("kind")

        if kind not in VALID_KINDS:
            continue

        icon = beat.get("icon")

        if kind == "icon-accent":
            if icon not in VALID_ICONS:
                continue
        else:
            icon = None

        phrase = resolve_phrase(beat.get("wordIds"), candidates_by_word_id)

        if phrase is None:
            continue

        if len(phrase["text"].split()) > MAX_BEAT_WORDS:
            continue

        scene_id = phrase["sceneId"]
        offset = phrase["offsetInParentFrames"]

        # A beat's own duration is a fixed style default (a quick pop), not
        # the spoken word's own duration — it's an accent timed to START
        # when the word is said, not a subtitle that tracks how long the
        # word takes to say.
        duration = default_duration

        if overlaps_existing_overlay(scene_id, offset, duration, scene_plan):
            continue

        parent = scenes_by_id.get(scene_id)

        if not parent or offset + duration > parent["durationInFrames"]:
            continue

        candidates.append(
            {
                "sceneId": scene_id,
                "kind": kind,
                "text": phrase["text"],
                "icon": icon,
                "offsetInParentFrames": offset,
                "durationInFrames": duration,
                "reason": beat.get("reason", ""),
            }
        )

    # Pass 2: enforce minimum spacing per scene. Response order isn't
    # guaranteed to be chronological, so sort first — this check assumes
    # proposals are visited in increasing offset order per scene.
    candidates.sort(key=lambda p: (p["sceneId"], p["offsetInParentFrames"]))

    proposals = []
    last_end_by_scene = {}

    for candidate in candidates:

        scene_id = candidate["sceneId"]
        offset = candidate["offsetInParentFrames"]

        last_end = last_end_by_scene.get(scene_id)

        if last_end is not None and offset - last_end < min_gap_frames:
            continue

        last_end_by_scene[scene_id] = offset + candidate["durationInFrames"]
        proposals.append(candidate)

    return proposals


# Fields a human can actually change through the editor (InlineTextEditor's
# Cmd+E text box, BeatBar's drag-to-resize) — see #58, second slice of #44
# after generate_moments.py's OVERRIDABLE_MOMENT_FIELDS. "kind"/"icon"/
# "offsetInParentFrames"/"sceneId"/"reason" have no editing UI today, so
# they're excluded — a re-save always round-trips them verbatim and
# including them would risk a spurious override from float/ordering noise,
# not an actual human edit.
OVERRIDABLE_BEAT_FIELDS = {"text", "durationInFrames"}


def compute_overridden_fields(old_beat, new_beat):
    """Same positional-diff approach as generate_moments.py's function of
    the same name (see #57) — a beat has no persistent id of its own
    either, so a same-array positional comparison against what's currently
    on disk in emphasis.json is the reliable signal for "did the human
    actually change this field." Starts from new_beat's own
    overriddenFields (so a client-side Reset-to-Automatic can actually take
    effect) and adds anything with a real value change on top."""

    overridden = set(new_beat.get("overriddenFields", old_beat.get("overriddenFields", [])))

    for field in OVERRIDABLE_BEAT_FIELDS:
        if new_beat.get(field) != old_beat.get(field):
            overridden.add(field)

    return sorted(overridden)


def preserve_overridden_fields(old_beats, new_proposals):
    """Before a --force regeneration overwrites emphasis.json, copy forward
    any human-overridden field value from an old beat onto its
    closest-matching new proposal — mirrors generate_moments.py's function
    of the same name (see #57/#58). Match key: sceneId (which parent
    presenter scene), then nearest offsetInParentFrames among same-scene
    candidates, since a fresh proposal batch has no positional
    correspondence to the old one. Only engages for beats that actually
    have overrides to protect."""

    old_by_scene = {}
    for old_beat in old_beats:
        if old_beat.get("overriddenFields"):
            old_by_scene.setdefault(old_beat["sceneId"], []).append(old_beat)

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

        for old_beat in old_candidates:

            best = min(
                new_candidates,
                key=lambda p: abs(p["offsetInParentFrames"] - old_beat["offsetInParentFrames"]),
            )

            for field in old_beat["overriddenFields"]:
                if field in old_beat:
                    best[field] = old_beat[field]

            best["overriddenFields"] = sorted(
                set(best.get("overriddenFields", [])) | set(old_beat["overriddenFields"])
            )

            claimed_new_ids.add(id(best))
            new_candidates.remove(best)

    return new_proposals


def merge_beat_scenes(scene_plan, proposals):
    """Rebuilds every beat scene from proposals — safe to call repeatedly,
    same as merge_moment_scenes/merge_title_scenes. Unlike those, this is
    also now a target for direct human edits (ui/server.py's PUT
    /api/episode/beats, backing #38's drag-to-resize on BeatBar) with no
    LLM-proposal-time validation upstream of it — propose_emphasis's own
    bounds check (offset + duration <= parent's own durationInFrames)
    only runs when the LLM proposes a beat, so a duration lengthened by a
    human drag needs the same guarantee enforced here instead, or a
    beat could end up positioned past its own parent scene's end."""

    existing_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if scene["type"] != "beat"
    ]

    scenes_by_id = {scene["id"]: scene for scene in existing_scenes}

    merged_scenes = list(existing_scenes)

    for index, proposal in enumerate(proposals):

        parent = scenes_by_id.get(proposal["sceneId"])

        if not parent:
            continue

        offset = proposal["offsetInParentFrames"]

        # Clamped, not rejected — same choice merge_moment_scenes already
        # made for a duration that no longer fits (see its own
        # maxDurationInParentFrames clamp): a save with one beat dragged
        # slightly past its scene's end still succeeds, just shortened to
        # whatever room is actually left, rather than losing every other
        # edit in the same save because of one out-of-bounds beat.
        duration = max(0, min(proposal["durationInFrames"], parent["durationInFrames"] - offset))

        if duration <= 0:
            continue

        beat_scene = {
            "id": f"scene-beat-{index}",
            "type": "beat",
            "kind": proposal["kind"],
            "text": proposal["text"],
            "parentSceneId": proposal["sceneId"],
            "offsetInParentFrames": offset,
            "durationInFrames": duration,
        }

        if proposal.get("icon"):
            beat_scene["icon"] = proposal["icon"]

        insert_overlay_scene(
            merged_scenes,
            scenes_by_id,
            beat_scene,
            parent["timelineStartFrame"] + offset
        )

    scene_plan = dict(scene_plan)
    scene_plan["scenes"] = merged_scenes

    return scene_plan


def main():

    parser = argparse.ArgumentParser(
        description="Propose kinetic emphasis (\"beat\") overlay scenes from word-level "
                     "transcript timing"
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate beats even if already proposed"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    processing = episode / "processing"

    transcript_file = processing / "episode_transcript.json"
    manifest_file = processing / "manifest.json"
    scene_plan_file = processing / "scene-plan.json"
    output_file = processing / "emphasis.json"

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
        print("Emphasis beats already proposed. Skipping.")
        print(output_file)
        return

    # Loaded before the fresh proposal overwrites output_file, so a
    # --force regeneration can carry forward any human-overridden field
    # from the beats this run is about to replace (see #58).
    previous_beats = load_json(output_file)["beats"] if output_file.exists() else []

    llm = LLMClient(PROJECT_ROOT / "config.json")
    prompt_template = load_prompt(PROMPT_FILE)

    transcript = load_json(transcript_file)
    manifest = load_json(manifest_file)
    scene_plan = load_json(scene_plan_file)

    print("Proposing emphasis beats...")
    print()

    try:
        proposals = propose_emphasis(
            scene_plan,
            transcript,
            manifest,
            llm,
            prompt_template,
            episode_context=load_episode_narrative_text(episode)
        )

        proposals = preserve_overridden_fields(previous_beats, proposals)

        write_json_atomic(output_file, {"beats": proposals})

        scene_plan = merge_beat_scenes(scene_plan, proposals)

        write_json_atomic(scene_plan_file, scene_plan)

        print(f"Proposed {len(proposals)} emphasis beat(s).")
        print(output_file)
        print(scene_plan_file)

    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
