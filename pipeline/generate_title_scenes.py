#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from llm.client import LLMClient
from style import load_style
from episode_context import NO_CONTEXT_TEXT, load_episode_narrative_text


PROMPT_FILE = PIPELINE_DIR / "prompts" / "title_scenes.txt"

# A split landing this close to a presenter scene's own start/end produces
# a presenter "piece" too short to read as real footage — just a handful
# of frames of the presenter mid-expression, visible for a fraction of a
# second before or after a title card. Snap a split that close to the
# scene boundary it's nearest to (see merge_title_scenes) so the cut reads
# as a clean "presenter ends, title, next presenter begins" instead of
# "presenter ends, a flash of the wrong frame, title, presenter begins
# again." One second is short enough to never eat a genuine early/late
# topic shift, long enough that no sliver piece is ever visible.
MIN_PIECE_FRAMES_SECONDS = 1.0


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


def indexed_segments(transcript, manifest):
    """Every transcript segment tagged with a stable segmentId (s0, s1, ...
    in transcript order) and its resolved videoId — the shared building
    block for both the whole-episode prompt (format_transcript_for_prompt)
    and resolving a proposed title's segmentId back to a real position
    (merge_title_scenes). Segments whose source clip isn't in the
    manifest are skipped but still consume an index, so a segmentId always
    means "the Nth segment in the transcript," stable regardless of which
    clips happen to be recognized."""

    filename_to_id = {
        video["filename"]: video["id"]
        for video in manifest["videos"]
    }

    indexed = []

    for i, segment in enumerate(transcript["segments"]):

        video_id = filename_to_id.get(segment["source"])

        if video_id is None:
            continue

        indexed.append(
            {
                "segmentId": f"s{i}",
                "videoId": video_id,
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"],
            }
        )

    return indexed


def format_transcript_for_prompt(transcript, manifest):
    """Whole-episode view, in transcript order — NOT grouped/collapsed per
    clip. Topic shifts are a property of the narrative, not of clip
    boundaries, so every segment boundary (a possible title-insertion
    point) needs to survive into the prompt, tagged with a stable id the
    LLM can point back at."""

    lines = []

    for segment in indexed_segments(transcript, manifest):
        lines.append(f"[{segment['segmentId']}] {segment['text']}")

    return "\n".join(lines)


def propose_title_scenes(transcript, manifest, llm: LLMClient, prompt_template: str, style=None, episode_context=None):

    if style is None:
        style = load_style()

    if episode_context is None:
        episode_context = NO_CONTEXT_TEXT

    segments = indexed_segments(transcript, manifest)

    if not segments:
        return []

    prompt = prompt_template.replace(
        "{segments}",
        format_transcript_for_prompt(transcript, manifest)
    ).replace(
        "{episode_context}",
        episode_context
    )

    # Unlike the old per-clip design (one small decision per clip),
    # this now requires reasoning about the whole episode's narrative
    # structure in a single call to find every genuine topic boundary —
    # thinking=False under-triggered badly in testing (found 2 of 9 real
    # chapters on Episode 9), so this needs the model's full reasoning.
    response = llm.complete_json(prompt, thinking=True)

    segments_by_id = {s["segmentId"]: s for s in segments}

    # The opening segment is always the presenter's performed intro, never
    # a topic that needs its own title card — enforced here, not just
    # asked for in the prompt, since this is a fixed rule with no
    # exceptions across any episode, not a judgment call worth leaving to
    # the LLM.
    opening_segment_id = segments[0]["segmentId"]

    titles = [
        title
        for title in response.get("titles", [])
        if title.get("segmentId") in segments_by_id
        and title.get("text")
        and title.get("segmentId") != opening_segment_id
    ]

    # Keep chronological order (segment index order — segmentIds are
    # assigned in transcript order, which spans clips in sequence) so the
    # min-spacing filter below compares each title only against the
    # nearest earlier one, not an arbitrary LLM response order.
    titles.sort(key=lambda t: int(t["segmentId"][1:]))

    kept = []
    last_kept_segment = None

    for title in titles:

        segment = segments_by_id[title["segmentId"]]

        # segment["start"] is clip-relative (resets to 0 at the start of
        # each source clip — see indexed_segments), so it's only
        # comparable to another segment's start within the SAME clip.
        # Two titles in different clips are never "too close" by this
        # check — the clip boundary itself is already a natural break, and
        # there's no shared timeline value here to compare against without
        # first resolving both to absolute frames (which needs the scene
        # plan, not available at proposal time).
        too_close = (
            last_kept_segment is not None
            and segment["videoId"] == last_kept_segment["videoId"]
            and segment["start"] - last_kept_segment["start"] < style["titles"]["minSpacingSeconds"]
        )

        if too_close:
            continue

        kept.append(title)
        last_kept_segment = segment

    return kept


def _reconstituted_track_scenes(scene_plan):
    """Undoes any splitting a previous merge_title_scenes call already
    performed, grouping presenter scenes back by videoId and re-joining
    them into their original single scene per clip (by source frame
    range) — the same "rebuild from scratch every call" discipline the
    rest of this pipeline already uses for moment/caption scenes, applied
    here to presenter-scene splits specifically so re-running against an
    already-split plan with a different (or the same) set of titles never
    compounds a previous run's split."""

    presenter_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if scene["type"] == "presenter"
    ]

    by_video_id = {}

    for scene in presenter_scenes:
        by_video_id.setdefault(scene["videoId"], []).append(scene)

    reconstituted = []

    for video_id, scenes in by_video_id.items():

        scenes = sorted(scenes, key=lambda s: s["sourceStartFrame"])

        reconstituted.append(
            {
                "id": f"scene-{video_id}",
                "type": "presenter",
                "videoId": video_id,
                "sourceStartFrame": scenes[0]["sourceStartFrame"],
                "sourceEndFrame": scenes[-1]["sourceEndFrame"],
                "durationInFrames": scenes[-1]["sourceEndFrame"] - scenes[0]["sourceStartFrame"],
                "effects": scenes[0]["effects"],
            }
        )

    return reconstituted


def _snapped_split_frame(source_frame, segment_start, segment_end, min_piece_frames):
    """Pulls a split point away from a scene boundary it's too close to,
    so neither the leading nor trailing presenter piece around the title
    is a near-zero-length sliver — a few frames of the presenter mid-
    expression flashing on screen for a fraction of a second isn't a
    real cut, it's a glitch (confirmed by watching real rendered output:
    a mid-clip split landing 5 frames after a clip's true start produced
    exactly this — presenter, instant flash, title, presenter again)."""

    if source_frame - segment_start < min_piece_frames:
        return segment_start

    if segment_end - source_frame < min_piece_frames:
        return segment_end

    return source_frame


def resolvable_segment_positions(scene_plan, transcript, manifest):
    """Every transcript segment's absolute timeline position, resolved
    against the CURRENT scene plan — the draggable-chapter-boundary
    equivalent of indexed_segments's clip-relative list. A segment whose
    clip isn't present as a presenter piece in this scene plan is skipped
    (can't be resolved to a timeline frame). Returned in timeline order so
    the frontend can snap a dragged pixel position to the nearest entry
    with a simple linear/binary search, with no further transcript access
    needed — segment TEXT is deliberately not included here, only
    segmentId + the resolved frame, since this is for snapping a drag, not
    for display."""

    presenter_pieces = sorted(
        (s for s in scene_plan["scenes"] if s["type"] == "presenter"),
        key=lambda s: s["timelineStartFrame"],
    )

    fps = scene_plan.get("fps", 30)

    positions = []

    for segment in indexed_segments(transcript, manifest):

        source_frame = round(segment["start"] * fps)

        # A segment's clip may appear as several pieces (already split by
        # earlier titles) — find whichever piece actually contains this
        # segment's source frame so the resolved timeline frame accounts
        # for title cards/splits already inserted before it.
        containing = next(
            (
                p for p in presenter_pieces
                if p["videoId"] == segment["videoId"]
                and p["sourceStartFrame"] <= source_frame < p["sourceEndFrame"]
            ),
            None,
        )

        if containing is None:
            continue

        timeline_frame = containing["timelineStartFrame"] + (source_frame - containing["sourceStartFrame"])

        positions.append({"segmentId": segment["segmentId"], "timelineFrame": timeline_frame})

    positions.sort(key=lambda p: p["timelineFrame"])

    return positions


def merge_title_scenes(scene_plan, titles, transcript, manifest, style=None):
    """Resolves each title's segmentId to a real source-frame position
    (via the transcript/manifest) and splits the presenter scene it falls
    within there, inserting the title card between the two resulting
    pieces. transcript/manifest are required — a title's segmentId is its
    only source of position, there is no positionless title anymore
    (unlike the old videoId-anchored design, where a title always sat at
    its clip's own start with nothing further to resolve)."""

    if style is None:
        style = load_style()

    title_duration_frames = style["titles"]["durationFrames"]

    fps = scene_plan.get("fps", 30)

    segments_by_id = {s["segmentId"]: s for s in indexed_segments(transcript, manifest)}

    # Undo any previous split first — see _reconstituted_track_scenes.
    track_scenes = _reconstituted_track_scenes(scene_plan)
    track_scenes_by_video_id = {s["videoId"]: s for s in track_scenes}

    overlay_scenes = [
        scene
        for scene in scene_plan["scenes"]
        if scene["type"] not in ("presenter", "title")
    ]

    # Group valid titles by which presenter scene (videoId) they split,
    # each with the resolved source frame to split at. A title whose
    # segmentId doesn't resolve to a known segment, or whose resolved clip
    # isn't in this scene plan, is skipped rather than guessed.
    splits_by_video_id = {}

    for title in titles:

        segment = segments_by_id.get(title.get("segmentId"))

        if not segment or segment["videoId"] not in track_scenes_by_video_id:
            continue

        splits_by_video_id.setdefault(segment["videoId"], []).append(
            {
                "text": title["text"],
                "sourceFrame": round(segment["start"] * fps),
                # Human-set override for THIS title's own on-screen display
                # duration (#83) — falls back to the shared config default
                # when absent, same as every episode before this field
                # existed. Growing/shrinking one title shifts every LATER
                # scene's timelineStartFrame by the same amount (the running
                # `timeline_frame` cursor below already does this for the
                # existing global-duration case; a per-title override just
                # changes which number that cursor advances by).
                "durationFrames": title.get("durationFrames") or title_duration_frames,
            }
        )

    merged_scenes = []
    timeline_frame = 0

    for scene in track_scenes:

        splits = sorted(
            splits_by_video_id.get(scene["videoId"], []),
            key=lambda s: s["sourceFrame"]
        )

        # Snap each split point into the scene's own bounds. A split that
        # lands exactly at the scene's own start still gets its title
        # inserted (right before the whole scene, same as the old
        # clip-boundary-only behavior) — it just produces no preceding
        # presenter piece, since there's nothing before it to carve off.
        segment_start = scene["sourceStartFrame"]
        segment_end = scene["sourceEndFrame"]

        min_piece_frames = round(MIN_PIECE_FRAMES_SECONDS * fps)

        clamped_splits = [
            {
                "text": split["text"],
                "sourceFrame": _snapped_split_frame(
                    max(segment_start, min(split["sourceFrame"], segment_end)),
                    segment_start,
                    segment_end,
                    min_piece_frames,
                ),
                "durationFrames": split["durationFrames"],
            }
            for split in splits
        ]

        piece_count = 0
        cursor = segment_start

        for i, split in enumerate(clamped_splits):

            piece_end = split["sourceFrame"]

            if piece_end > cursor:

                piece = dict(scene)
                piece["id"] = scene["id"] if piece_count == 0 else f"{scene['id']}-{piece_count}"
                piece["sourceStartFrame"] = cursor
                piece["sourceEndFrame"] = piece_end
                piece["durationInFrames"] = piece_end - cursor
                piece["timelineStartFrame"] = timeline_frame

                merged_scenes.append(piece)
                timeline_frame += piece["durationInFrames"]
                piece_count += 1

            merged_scenes.append(
                {
                    "id": f"scene-title-{scene['videoId']}-{i}" if len(clamped_splits) > 1 else f"scene-title-{scene['videoId']}",
                    "type": "title",
                    "text": split["text"],
                    "timelineStartFrame": timeline_frame,
                    "durationInFrames": split["durationFrames"],
                }
            )
            timeline_frame += split["durationFrames"]

            cursor = piece_end

        if segment_end > cursor:

            final_piece = dict(scene)
            final_piece["id"] = scene["id"] if piece_count == 0 else f"{scene['id']}-{piece_count}"
            final_piece["sourceStartFrame"] = cursor
            final_piece["sourceEndFrame"] = segment_end
            final_piece["durationInFrames"] = segment_end - cursor
            final_piece["timelineStartFrame"] = timeline_frame

            merged_scenes.append(final_piece)
            timeline_frame += final_piece["durationInFrames"]

    merged_scenes.extend(overlay_scenes)

    scene_plan = dict(scene_plan)
    scene_plan["scenes"] = merged_scenes

    return scene_plan


# text (#59, third slice of #44 after moments #57 and beats #58) and
# durationFrames (#83 — a title's own on-screen display duration,
# previously a single shared config value with no per-title override) are
# the fields a human can actually change through the title-editing UIs
# (TitleEditorPanel.tsx, InlineTextEditor.tsx's "title" branch,
# SceneBar.tsx's drag-to-resize).
OVERRIDABLE_TITLE_FIELDS = {"text", "durationFrames"}


def compute_overridden_fields(old_title, new_title):
    """Unlike moments/beats (compute_overridden_fields in
    generate_moments.py/generate_emphasis.py), which have no persistent id
    and must diff by array position, a title has a real stable identity —
    segmentId, assigned from transcript segment order and unaffected by
    save-time reordering. old_title here is therefore looked up by
    segmentId, not position (see update_title_scenes in ui/server.py,
    which builds the old-titles-by-segmentId map before calling this).
    Same "start from new_title's own overriddenFields, then add real value
    changes on top" logic as #57/#58, so Reset to Automatic can actually
    take effect."""

    overridden = set(new_title.get("overriddenFields", old_title.get("overriddenFields", [])))

    for field in OVERRIDABLE_TITLE_FIELDS:
        if new_title.get(field) != old_title.get(field):
            overridden.add(field)

    return sorted(overridden)


def preserve_overridden_fields(old_titles, new_proposals):
    """Before a --force regeneration overwrites title_scenes.json, copy
    forward any human-overridden text onto the matching new proposal —
    matched by segmentId (exact match, not a nearest-offset heuristic like
    moments/beats use), since segmentId is stable across regenerations as
    long as the underlying transcript segment still exists. An old title
    whose segmentId doesn't appear in the fresh proposal batch (e.g. the AI
    no longer proposes a title for that segment) has nothing to copy onto —
    its override is silently dropped along with the proposal itself,
    mirroring how an old moment/beat with no matching new candidate is
    simply left unmatched."""

    old_by_segment = {
        title["segmentId"]: title for title in old_titles if title.get("overriddenFields")
    }

    if not old_by_segment:
        return new_proposals

    for proposal in new_proposals:

        old_title = old_by_segment.get(proposal["segmentId"])

        if old_title is None:
            continue

        for field in old_title["overriddenFields"]:
            if field in old_title:
                proposal[field] = old_title[field]

        proposal["overriddenFields"] = sorted(
            set(proposal.get("overriddenFields", [])) | set(old_title["overriddenFields"])
        )

    return new_proposals


def main():

    parser = argparse.ArgumentParser(
        description="Propose title scenes from the whole episode transcript using an LLM"
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate title scenes even if already applied"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    processing = episode / "processing"

    transcript_file = processing / "episode_transcript.json"
    manifest_file = processing / "manifest.json"
    scene_plan_file = processing / "scene-plan.json"
    output_file = processing / "title_scenes.json"

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
        print("Title scenes already proposed. Skipping.")
        print(output_file)
        return

    # Loaded before the fresh proposal overwrites output_file, so a
    # --force regeneration can carry forward any human-overridden text
    # from the titles this run is about to replace (see #59).
    previous_titles = load_json(output_file)["titles"] if output_file.exists() else []

    llm = LLMClient(PROJECT_ROOT / "config.json")
    prompt_template = load_prompt(PROMPT_FILE)

    transcript = load_json(transcript_file)
    manifest = load_json(manifest_file)
    scene_plan = load_json(scene_plan_file)

    print("Proposing title scenes...")
    print()

    try:
        titles = propose_title_scenes(
            transcript,
            manifest,
            llm,
            prompt_template,
            episode_context=load_episode_narrative_text(episode)
        )

        titles = preserve_overridden_fields(previous_titles, titles)

        write_json_atomic(output_file, {"titles": titles})

        scene_plan = merge_title_scenes(scene_plan, titles, transcript, manifest)

        write_json_atomic(scene_plan_file, scene_plan)

        print(f"Proposed {len(titles)} title scene(s).")
        print(output_file)
        print(scene_plan_file)

    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
