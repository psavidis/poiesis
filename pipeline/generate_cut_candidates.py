#!/usr/bin/env python3

"""Proposes mid-take pause cuts from word-level transcript timing (#65).
Pure signal processing, no LLM — a pause is a measurable gap in Whisper's
own word timestamps, not a subjective judgment call (see CLAUDE.md's "use
AI for judgment, use software for execution").

This stage only ever WRITES cut_candidates.json — it never touches
scene-plan.json. A proposed cut is applied only when a human explicitly
accepts it via PUT /api/episode/cut-candidates (ui/server.py), which
invokes edit_plan.py's "trim" op.

KNOWN LIMITATION, not solved here: this stage runs early in run_pipeline.py
(right after analyze_scenes.py), but acceptance is a manual human action
that may happen much later — possibly after generate_title_scenes.py,
generate_moments.py, or generate_emphasis.py have already computed offsets
against the PRE-cut timeline. If a cut is accepted after that, those
stages' overlay offsets can go stale in scene-plan.json (their
parentSceneId/offsetInParentFrames were computed for a timeline that no
longer exists in that shape post-trim), the same staleness risk any manual
scene-plan.json edit already carries today, mitigated only by each
artifact's own overriddenFields/preserve_*-on-force provenance, not by
blocking the pipeline on cut review."""

import argparse
import json
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PIPELINE_DIR))


# Gaps shorter than this are natural speech rhythm (a breath, a beat before
# the next sentence), not dead air worth proposing a cut for. Distinct from
# analyze_scenes.py's LEAD_IN_SECONDS/TAIL_SECONDS (which trim silence at a
# SCENE's own edges) — this threshold is for INTERIOR pauses, mid-take, and
# is deliberately more conservative (a longer minimum) since an interior cut
# is a bigger edit than trimming dead air off either end of a clip.
MIN_PAUSE_SECONDS = 1.2

# Kept on each side of a proposed cut so the accepted edit doesn't land
# mid-breath — the pause itself is still removed, just not shaved down to
# the exact silent frame on either boundary.
PAD_SECONDS = 0.2

# The fields a human can meaningfully nudge on a still-pending cut before
# accepting it — unlike moments/beats, a cut candidate IS its span; there's
# no separate content field to override. Mirrors OVERRIDABLE_MOMENT_FIELDS/
# OVERRIDABLE_BEAT_FIELDS in shape (generate_moments.py, generate_emphasis.py).
OVERRIDABLE_CUT_FIELDS = {"cutStartFrame", "cutEndFrame"}


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


def find_pause_gaps(segments):
    """Scans word-level timing gaps within transcript segments belonging to
    ONE video's transcript (segments already filtered to a single `source`
    by the caller) and returns raw candidate gaps in clip-native seconds:
    [{"gapStartSeconds", "gapEndSeconds"}, ...] for every gap >=
    MIN_PAUSE_SECONDS.

    Pure signal processing over Whisper's own timestamps — no LLM, no
    judgment beyond a fixed duration threshold, consistent with CLAUDE.md's
    "use AI for judgment, use software for execution" (silence duration is
    measured, not judged; see #65).

    Checks gaps WITHIN a segment's own words, and the gap BETWEEN
    consecutive segments (silence at a segment boundary is exactly as real
    a pause as one inside a segment's own words — normalize_transcripts.py
    only splits into segments at Whisper's own segment boundaries, not at
    every natural pause). Falls back to segment-level start/end when a
    segment has no `words` (normalize_transcripts.py only includes `words`
    when Whisper provided them — see #65's research), degrading gracefully
    the same way analyze_scenes.py's analyze_speech_bounds already does
    without word-level timing."""

    gaps = []

    previous_end = None

    for segment in segments:

        words = segment.get("words")

        points = (
            [(w["start"], w["end"]) for w in words]
            if words
            else [(segment["start"], segment["end"])]
        )

        for start, end in points:

            if previous_end is not None and start - previous_end >= MIN_PAUSE_SECONDS:
                gaps.append({"gapStartSeconds": previous_end, "gapEndSeconds": start})

            previous_end = end

    return gaps


def resolve_candidates_for_scene(scene, segments_for_video, fps):
    """Converts raw pause gaps (clip-native seconds, from find_pause_gaps)
    into cut_candidates entries scoped to one presenter scene: converts to
    absolute source frames (same coordinate space as the scene's own
    sourceStartFrame/sourceEndFrame), pads by PAD_SECONDS on each side, and
    clips to the scene's own [sourceStartFrame, sourceEndFrame] bounds — a
    gap detected in footage the scene's own lead-in/tail silence trim
    already excludes (see analyze_scenes.py's analyze_speech_bounds) isn't
    re-proposed here. Drops any candidate that pads down to a zero/negative
    length after clamping."""

    candidates = []

    for gap in find_pause_gaps(segments_for_video):

        raw_start_frame = int((gap["gapStartSeconds"] + PAD_SECONDS) * fps)
        raw_end_frame = int((gap["gapEndSeconds"] - PAD_SECONDS) * fps)

        cut_start_frame = max(raw_start_frame, scene["sourceStartFrame"])
        cut_end_frame = min(raw_end_frame, scene["sourceEndFrame"])

        if cut_end_frame <= cut_start_frame:
            continue

        candidates.append(
            {
                "sceneId": scene["id"],
                "videoId": scene["videoId"],
                "cutStartFrame": cut_start_frame,
                "cutEndFrame": cut_end_frame,
                "durationSeconds": round((cut_end_frame - cut_start_frame) / fps, 2),
                "reason": f"{round(gap['gapEndSeconds'] - gap['gapStartSeconds'], 1)}s silence with no speech",
                "status": "pending",
                "overriddenFields": [],
            }
        )

    return candidates


def propose_cuts(scene_plan, transcript, manifest):
    """Proposes pause-cut candidates for every presenter scene in the
    episode. Deterministic and LLM-free (see find_pause_gaps) — this
    function never calls out to an LLM, unlike generate_moments.py/
    generate_emphasis.py's propose_* functions."""

    fps = scene_plan["fps"]

    filename_to_video_id = {video["filename"]: video["id"] for video in manifest["videos"]}

    segments_by_video_id = {}
    for segment in transcript["segments"]:
        video_id = filename_to_video_id.get(segment.get("source"))
        if video_id is not None:
            segments_by_video_id.setdefault(video_id, []).append(segment)

    proposals = []

    for scene in scene_plan["scenes"]:

        if scene["type"] != "presenter":
            continue

        segments_for_video = segments_by_video_id.get(scene["videoId"], [])

        proposals.extend(resolve_candidates_for_scene(scene, segments_for_video, fps))

    return proposals


def compute_overridden_cut_fields(old_cut, new_cut):
    """Field names on new_cut whose value differs from old_cut (the same
    array-position entry currently on disk in cut_candidates.json) —
    mirrors compute_overridden_fields in generate_moments.py exactly, same
    positional-diff rationale (see #57)."""

    overridden = set(new_cut.get("overriddenFields", old_cut.get("overriddenFields", [])))

    for field in OVERRIDABLE_CUT_FIELDS:
        if new_cut.get(field) != old_cut.get(field):
            overridden.add(field)

    return sorted(overridden)


def preserve_status_and_overrides(old_cuts, new_proposals):
    """Before a --force regeneration overwrites cut_candidates.json, copy
    forward (a) any human-overridden boundary field and (b) the cut's
    status (pending/accepted/rejected) from an old cut onto whichever new
    proposal is its best match — mirrors preserve_overridden_fields in
    generate_moments.py, matched by sceneId + nearest cutStartFrame (no
    stable id exists across regenerations, same reasoning as #57).

    Preserving `status` is the one real divergence from the moments/beats
    pattern: status isn't a field a human edited, it's a workflow decision
    that must survive regeneration UNCONDITIONALLY once set — an accepted
    cut has already been applied to scene-plan.json; reverting it to
    "pending" on the next --force run would make the proposal artifact lie
    about what's actually been done to the footage. So unlike
    overriddenFields (only engaged for cuts a human has actually edited),
    every old cut with a non-"pending" status is carried forward here,
    whether or not it also has boundary overrides."""

    old_by_scene = {}
    for old_cut in old_cuts:
        if old_cut.get("status") != "pending" or old_cut.get("overriddenFields"):
            old_by_scene.setdefault(old_cut["sceneId"], []).append(old_cut)

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

        for old_cut in old_candidates:

            if not new_candidates:
                break

            best = min(
                new_candidates,
                key=lambda p: abs(p["cutStartFrame"] - old_cut["cutStartFrame"]),
            )

            for field in old_cut.get("overriddenFields", []):
                if field in old_cut:
                    best[field] = old_cut[field]

            best["overriddenFields"] = sorted(
                set(best.get("overriddenFields", [])) | set(old_cut.get("overriddenFields", []))
            )

            best["status"] = old_cut["status"]

            claimed_new_ids.add(id(best))
            new_candidates.remove(best)

    return new_proposals


def main():

    parser = argparse.ArgumentParser(
        description="Propose mid-take pause cuts from word-level transcript timing (#65) — "
                     "mechanical signal processing, no LLM involved."
    )

    parser.add_argument("episode_folder")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate cut candidates even if already proposed"
    )

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    processing = episode / "processing"

    transcript_file = processing / "episode_transcript.json"
    manifest_file = processing / "manifest.json"
    scene_plan_file = processing / "scene-plan.json"
    output_file = processing / "cut_candidates.json"

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
        print("Cut candidates already proposed. Skipping.")
        print(output_file)
        return

    # Loaded before the fresh proposal overwrites output_file, so a --force
    # regeneration can carry forward any accepted/rejected status or
    # human-overridden boundary from the cuts this run is about to replace.
    previous_cuts = load_json(output_file)["cuts"] if output_file.exists() else []

    transcript = load_json(transcript_file)
    manifest = load_json(manifest_file)
    scene_plan = load_json(scene_plan_file)

    print("Proposing pause cuts...")
    print()

    try:
        proposals = propose_cuts(scene_plan, transcript, manifest)

        proposals = preserve_status_and_overrides(previous_cuts, proposals)

        write_json_atomic(output_file, {"cuts": proposals})

        print(f"Proposed {len(proposals)} pause cut candidate(s).")
        print(output_file)

    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
