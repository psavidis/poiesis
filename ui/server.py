#!/usr/bin/env python3

import asyncio
import json
import re
from pathlib import Path

import sys

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from episode_locks import EpisodeBusyError, episode_lock
from pipeline_stages import SECONDARY_STAGES, find_stage, stage_status
from process_runner import stream_process
from undo import restore_latest, wrap_with_checkpoint

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from generate_title_scenes import (  # noqa: E402
    compute_overridden_fields as compute_overridden_title_fields,
    merge_title_scenes,
    write_json_atomic,
)
from generate_moments import (  # noqa: E402
    SWITCHABLE_TREATMENTS,
    compute_overridden_fields,
    merge_moment_scenes,
    switch_moment_treatment,
)
from generate_emphasis import (  # noqa: E402
    compute_overridden_fields as compute_overridden_beat_fields,
    merge_beat_scenes,
)
from generate_scene_plan_ts import generate_scene_plan_ts  # noqa: E402
from edit_plan import (  # noqa: E402
    edit_plan,
    load_prompt as load_edit_plan_prompt,
    PROMPT_FILE as EDIT_PLAN_PROMPT_FILE,
    validate_operations,
    apply_operations,
    reflow_timeline,
)
from llm.client import LLMClient  # noqa: E402
from overlay_placement import insert_overlay_scene  # noqa: E402

RENDERER_DIR = Path(__file__).resolve().parent.parent / "video-renderer"


def regenerate_codegen(episode: Path):
    """Re-runs generate_scene_plan_ts.py in-process right after any edit
    that changes scene-plan.json, so a render always reflects the latest
    edit without a separate manual "Generate Remotion codegen" click —
    that extra step was easy to forget between making an edit and
    re-rendering, and a stale codegen silently renders the OLD plan with
    no warning that anything's out of date. Errors are swallowed (logged,
    not raised) so a codegen hiccup never blocks the edit itself from
    being saved — the manual "Generate Remotion codegen" stage still
    exists as a fallback if this ever needs to be re-run by hand."""

    try:
        generate_scene_plan_ts(episode, RENDERER_DIR)
    except Exception as e:
        print(f"WARNING: codegen regeneration failed after edit: {e}")

RESOLUTION_PATTERN = re.compile(r"^\d+x\d+$")

UI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = UI_DIR.parent

DEFAULT_BROWSE_PATH = "/Users/petros/Youtube/Philosoftware/Videos"

app = FastAPI(title="Poiesis Control Panel")

# The embedded preview app (video-renderer/preview-app, Vite dev server on
# :5173) is a separate origin from this control panel and needs to read
# artifacts (scene-plan.json, manifest.json, assets.json) and write back
# visual-scene edits. Both are local-only dev servers, so scoping to
# localhost/127.0.0.1 rather than a wildcard is enough.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "PUT", "POST"],
    allow_headers=["*"],
)


def resolve_episode(path: str) -> Path:
    episode = Path(path).expanduser().resolve()

    if not episode.exists() or not episode.is_dir():
        raise HTTPException(status_code=404, detail=f"Episode folder not found: {episode}")

    return episode


@app.get("/api/browse")
def browse(path: str | None = None):
    target = Path(path).expanduser().resolve() if path else Path(DEFAULT_BROWSE_PATH).expanduser().resolve()

    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail=f"Folder not found: {target}")

    entries = sorted(
        (child for child in target.iterdir() if child.is_dir() and not child.name.startswith(".")),
        key=lambda child: child.name.lower(),
    )

    return {
        "path": str(target),
        "parent": str(target.parent) if target.parent != target else None,
        "isEpisode": (target / "processing").exists() or (target / "original_footage").exists(),
        "entries": [
            {
                "name": child.name,
                "path": str(child),
                "isEpisode": (child / "processing").exists() or (child / "original_footage").exists(),
            }
            for child in entries
        ],
    }


@app.get("/api/episode/status")
def episode_status(path: str):
    episode = resolve_episode(path)

    return {
        "episode": episode.name,
        "path": str(episode),
        "stages": stage_status(episode),
        "secondary": [
            {
                "id": stage.id,
                "label": stage.label,
                "complete": stage.is_complete(episode) if stage.artifact else None,
            }
            for stage in SECONDARY_STAGES
        ],
        "hasRender": (episode / "rendered" / f"{episode.name}.mp4").exists(),
    }


@app.get("/api/episode/artifact")
def episode_artifact(path: str, name: str):
    episode = resolve_episode(path)

    allowed = {
        "title_scenes.json",
        "storyboard.json",
        "moments.json",
        "emphasis.json",
        "captions.json",
        "assets.json",
        "code_assets.json",
        "scene-plan.json",
        "qa-report.json",
        "episode_analysis.json",
        "manifest.json",
    }

    if name not in allowed:
        raise HTTPException(status_code=400, detail=f"Artifact not readable: {name}")

    artifact_path = episode / "processing" / name

    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact not yet produced: {name}")

    with artifact_path.open("r", encoding="utf-8") as f:
        return json.load(f)


class TitleScene(BaseModel):
    segmentId: str
    text: str
    # Field names a human has explicitly changed since the AI last proposed
    # this title (see #59) — recomputed on every save in
    # update_title_scenes below, matched by segmentId rather than array
    # position (a title has a stable id, unlike moments/beats).
    overriddenFields: list[str] = []


class TitleScenesUpdate(BaseModel):
    titles: list[TitleScene]


@app.put("/api/episode/title-scenes")
def update_title_scenes(path: str, body: TitleScenesUpdate):
    """Human edits to AI-proposed title text. Writes the edited titles back
    to title_scenes.json, then deterministically re-merges them into
    scene-plan.json the same way generate_title_scenes.py does after the LLM
    call — no LLM involved here, this only replays the merge with edited
    text. merge_title_scenes rebuilds timelineStartFrame from scratch each
    call, so re-running it against the current scene plan is safe even if
    titles were already merged before."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"
    title_scenes_path = processing / "title_scenes.json"
    episode_transcript_path = processing / "episode_transcript.json"
    manifest_path = processing / "manifest.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    if not episode_transcript_path.exists() or not manifest_path.exists():
        raise HTTPException(status_code=404, detail="episode_transcript.json/manifest.json not found — run the pipeline first")

    titles = [title.model_dump() for title in body.titles]

    # overriddenFields (#59) is recomputed here, not trusted from the
    # request body — matched by segmentId (a title's real stable id),
    # unlike update_moments/update_beats which must diff by array position
    # since moments/beats have no persistent id of their own.
    old_titles_by_segment = {}
    if title_scenes_path.exists():
        with title_scenes_path.open("r", encoding="utf-8") as f:
            old_titles_by_segment = {
                t["segmentId"]: t for t in json.load(f).get("titles", [])
            }

    for title in titles:
        old_title = old_titles_by_segment.get(title["segmentId"], {})
        title["overriddenFields"] = compute_overridden_title_fields(old_title, title)

    def do_write():
        with scene_plan_path.open("r", encoding="utf-8") as f:
            scene_plan = json.load(f)

        with episode_transcript_path.open("r", encoding="utf-8") as f:
            episode_transcript = json.load(f)

        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        scene_plan = merge_title_scenes(scene_plan, titles, episode_transcript, manifest)

        write_json_atomic(title_scenes_path, {"titles": titles})
        write_json_atomic(scene_plan_path, scene_plan)
        regenerate_codegen(episode)

    try:
        with episode_lock(episode, wait=False):
            wrap_with_checkpoint(processing, [scene_plan_path, title_scenes_path], "title edit", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"titles": titles}


class StoryboardChapter(BaseModel):
    chapterId: str
    chapterText: str
    notes: str


class StoryboardUpdate(BaseModel):
    chapters: list[StoryboardChapter]


@app.put("/api/episode/storyboard")
def update_storyboard(path: str, body: StoryboardUpdate):
    """Human edits to the AI's chapter-level storyboard reasoning. Unlike
    title-scenes/moments, this has no scene-plan.json merge step — the
    storyboard doesn't itself produce any scenes, it's read-as-context by
    the next generate_moments.py run (see propose_moments's
    storyboard_chapters param). Saving here just persists the edit; the
    payoff is that re-running "Propose moment scenes" afterward reads the
    edited reasoning without needing to regenerate it first."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    storyboard_path = processing / "storyboard.json"

    chapters = [chapter.model_dump() for chapter in body.chapters]

    try:
        with episode_lock(episode, wait=False):
            wrap_with_checkpoint(
                processing, [storyboard_path], "storyboard edit",
                lambda: write_json_atomic(storyboard_path, {"chapters": chapters})
            )
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"chapters": chapters}


class MomentProposal(BaseModel):
    windowId: str
    sceneId: str
    videoId: str
    offsetInParentFrames: int
    maxDurationInParentFrames: int
    treatment: str
    presenterSide: str | None = None
    fullVisualKind: str | None = None
    text: str | None = None
    assetId: str | None = None
    codeAssetId: str | None = None
    diagram: dict | None = None
    comparison: dict | None = None
    terms: list[dict] | None = None
    sideTextStyle: str | None = None
    caption: str | None = None
    # Only meaningful for treatment "bottom-callout" — see MomentEntrance
    # in video-renderer's types.ts. Included here so a save round-trips it
    # (Pydantic silently strips any field not declared on the model), same
    # as every other treatment-specific field in this class.
    entrance: str | None = None
    reason: str = ""
    # Field names a human has explicitly changed since the AI last proposed
    # this moment (see #57) — a save's own diff against what's currently on
    # disk RECOMPUTES this in update_moments below, so a client never needs
    # to compute or send it correctly itself; it only needs to round-trip
    # whatever getMoments() returned (same as every other field here).
    overriddenFields: list[str] = []


class MomentsUpdate(BaseModel):
    moments: list[MomentProposal]


@app.put("/api/episode/moments")
def update_moments(path: str, body: MomentsUpdate):
    """Human edits to AI-proposed moment overlays: text/assetId, timing
    (offsetInParentFrames), duration (maxDurationInParentFrames — trusted
    verbatim by merge_moment_scenes, NOT re-derived from treatment; see
    that function's own docstring), and presenterSide. This endpoint does
    NOT compute a correct new duration for a treatment change — a payload
    that changes "treatment" round-trips whatever maxDurationInParentFrames
    the client already sent, same as any other field, with no
    treatment-aware recompute. The one supported way to actually SWITCH a
    moment's treatment with correct duration/field recomputation is PUT
    /api/episode/moment-treatment, scoped to treatments that share the
    same underlying content (code/image/diagram, each side-* paired with
    full-visual; code additionally has content-dominant-code). Writes the
    edited proposals back to moments.json, then deterministically
    re-merges them into scene-plan.json the same
    way generate_moments.py does after the LLM call — no LLM involved
    here.
    merge_moment_scenes rebuilds all moment scenes from scratch each call
    (never touching their parent presenter scenes — the presenter's
    on-screen position is derived per-frame from each moment's own window
    at render time, not a static field), so this is safe to call repeatedly
    even if scenes were already merged before."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"
    moments_path = processing / "moments.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    moments = [m.model_dump() for m in body.moments]

    # overriddenFields (#57) is recomputed here, not trusted from the
    # request body — a positional diff against what's currently on disk
    # in moments.json is the only reliable "did the human actually change
    # this field" signal (see compute_overridden_fields' own docstring for
    # why sceneId+treatment can't identify a single moment). Positions
    # beyond the old array's length (a newly-created moment via this same
    # save, e.g. from the panel's own add-flow if one exists) have no old
    # entry to diff against, so they start with an empty override set —
    # correct, since there's nothing "AI-proposed-then-changed" yet.
    old_moments = []
    if moments_path.exists():
        with moments_path.open("r", encoding="utf-8") as f:
            old_moments = json.load(f).get("moments", [])

    for i, moment in enumerate(moments):
        old_moment = old_moments[i] if i < len(old_moments) else {}
        moment["overriddenFields"] = compute_overridden_fields(old_moment, moment)

    def do_write():
        with scene_plan_path.open("r", encoding="utf-8") as f:
            scene_plan = json.load(f)

        scene_plan = merge_moment_scenes(scene_plan, moments)

        write_json_atomic(moments_path, {"moments": moments})
        write_json_atomic(scene_plan_path, scene_plan)
        regenerate_codegen(episode)

    try:
        with episode_lock(episode, wait=False):
            wrap_with_checkpoint(processing, [scene_plan_path, moments_path], "moment edit", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"moments": moments}


class MomentTreatmentSwitch(BaseModel):
    sceneId: str
    newTreatment: str


@app.put("/api/episode/moment-treatment")
def update_moment_treatment(path: str, body: MomentTreatmentSwitch):
    """Switches an existing moment among the treatments that present the
    SAME content at different prominence — code (side-code /
    content-dominant-code / full-visual), image (side-image / full-visual),
    or diagram (side-diagram / full-visual) — without replacing its
    content. See docs/specs/content-types-and-presentation-editing.md
    (the content-type-vs-presentation model this implements one slice of).
    Deliberately a separate endpoint from PUT /api/episode/moments rather
    than folding this into that endpoint's generic field round-trip: a
    treatment switch needs real server-side computation (new duration via
    switch_moment_treatment, which merge_moment_scenes will NOT re-derive
    on its own — see that function's own docstring), not just a value the
    client already knows to send, the way every other field on that
    endpoint works today.

    sceneId resolves to a moments.json array index the same way
    MOMENT_SCENE_ID_PATTERN already does elsewhere in this file (moments
    have no persistent id of their own — see #57's own docstrings for
    why every moment endpoint in this file uses this same convention)."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"
    moments_path = processing / "moments.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    if body.newTreatment not in SWITCHABLE_TREATMENTS:
        raise HTTPException(
            status_code=422,
            detail=f"newTreatment must be one of {sorted(SWITCHABLE_TREATMENTS)} — arbitrary treatment "
                   "switching is not supported yet",
        )

    match = MOMENT_SCENE_ID_PATTERN.match(body.sceneId)

    if not match:
        raise HTTPException(status_code=422, detail=f"Not a moment scene id: {body.sceneId}")

    index = int(match.group(1))

    if not moments_path.exists():
        raise HTTPException(status_code=404, detail="moments.json not found — run the pipeline first")

    with moments_path.open("r", encoding="utf-8") as f:
        moments = json.load(f).get("moments", [])

    if index >= len(moments):
        raise HTTPException(status_code=404, detail=f"No moment at index {index}")

    old_moment = moments[index]

    with scene_plan_path.open("r", encoding="utf-8") as f:
        scene_plan_for_switch = json.load(f)

    switched = switch_moment_treatment(old_moment, body.newTreatment, scene_plan_for_switch)

    if switched is None:
        raise HTTPException(
            status_code=422,
            detail=f"Moment's current treatment ({old_moment.get('treatment')!r}) and newTreatment "
                   f"({body.newTreatment!r}) don't present the same content — this endpoint only "
                   "switches among treatments that share content (e.g. side-code <-> full-visual, "
                   "not side-code <-> side-image)",
        )

    # A deliberate human override, same as any other field edit (#57) — so
    # a subsequent --force regeneration doesn't silently revert the user's
    # chosen presentation. Both treatment and the recomputed duration
    # count, since the duration change is a direct consequence of the
    # switch, not independently AI-owned anymore.
    switched["overriddenFields"] = sorted(
        set(old_moment.get("overriddenFields", [])) | {"treatment", "maxDurationInParentFrames"}
    )

    moments[index] = switched

    def do_write():
        with scene_plan_path.open("r", encoding="utf-8") as f:
            scene_plan = json.load(f)

        scene_plan = merge_moment_scenes(scene_plan, moments)

        write_json_atomic(moments_path, {"moments": moments})
        write_json_atomic(scene_plan_path, scene_plan)
        regenerate_codegen(episode)

    try:
        with episode_lock(episode, wait=False):
            wrap_with_checkpoint(processing, [scene_plan_path, moments_path], "moment treatment switch", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"moments": moments}


class BeatProposal(BaseModel):
    sceneId: str
    kind: str
    text: str
    icon: str | None = None
    offsetInParentFrames: int
    durationInFrames: int
    reason: str = ""
    # Field names a human has explicitly changed since the AI last proposed
    # this beat (see #58) — recomputed on every save in update_beats below,
    # same as moments' overriddenFields (#57); a client only needs to
    # round-trip whatever getBeats() returned.
    overriddenFields: list[str] = []


class BeatsUpdate(BaseModel):
    beats: list[BeatProposal]


@app.put("/api/episode/beats")
def update_beats(path: str, body: BeatsUpdate):
    """Human edits to AI-proposed beat overlays — today, only duration
    (BeatBar's drag-to-resize, see #38). Writes the edited proposals back
    to emphasis.json, then deterministically re-merges them into
    scene-plan.json the same way generate_emphasis.py does after the LLM
    call — no LLM involved here. merge_beat_scenes clamps (not rejects)
    any beat whose duration would now push it past its own parent
    scene's end, so a slightly-too-far drag still saves successfully,
    just shortened to whatever room is actually left — see its own
    docstring for why that check has to live there rather than only at
    LLM-proposal time."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"
    beats_path = processing / "emphasis.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    beats = [b.model_dump() for b in body.beats]

    # overriddenFields (#58) is recomputed here, not trusted from the
    # request body — same positional diff against what's currently on disk
    # that update_moments already applies (see compute_overridden_fields'
    # docstring in generate_emphasis.py). Positions beyond the old array's
    # length have no old entry to diff against, so they start with an
    # empty override set.
    old_beats = []
    if beats_path.exists():
        with beats_path.open("r", encoding="utf-8") as f:
            old_beats = json.load(f).get("beats", [])

    for i, beat in enumerate(beats):
        old_beat = old_beats[i] if i < len(old_beats) else {}
        beat["overriddenFields"] = compute_overridden_beat_fields(old_beat, beat)

    def do_write():
        with scene_plan_path.open("r", encoding="utf-8") as f:
            scene_plan = json.load(f)

        scene_plan = merge_beat_scenes(scene_plan, beats)

        write_json_atomic(beats_path, {"beats": beats})
        write_json_atomic(scene_plan_path, scene_plan)
        regenerate_codegen(episode)

    try:
        with episode_lock(episode, wait=False):
            wrap_with_checkpoint(processing, [scene_plan_path, beats_path], "beat edit", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"beats": beats}


class SceneFieldUpdate(BaseModel):
    sceneId: str
    fields: dict


@app.put("/api/episode/scene")
def update_scene_fields(path: str, body: SceneFieldUpdate):
    """Direct, non-LLM field updates against a single scene in
    scene-plan.json — the deterministic counterpart to /api/episode/edit-plan
    for UI-driven edits (e.g. ImageBar's drag-to-move/resize, or a display
    full/inset toggle) that already know exactly which scene and field they
    want to change, so there's no reason to round-trip through the LLM the
    chat box uses for free-text instructions. Reuses edit_plan.py's own
    validate_operations/apply_operations — same allowlist per scene type
    (EDITABLE_FIELDS), same rejection behavior for an unknown scene id or a
    disallowed field, so this endpoint can never do anything the chat
    endpoint couldn't already do; it's just a faster, structured path to it.
    Unlike moments/beats, image scenes have no separate source-of-truth
    file to also update — scene-plan.json already IS their only
    representation (see docs/pipeline-guide.md: image scenes are
    "hand-authored / edit-plan only")."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    op = {"op": "update", "sceneId": body.sceneId, "fields": body.fields}

    try:
        with episode_lock(episode, wait=False):
            with scene_plan_path.open("r", encoding="utf-8") as f:
                scene_plan = json.load(f)

            valid_ops, rejected = validate_operations(scene_plan, [op])

            if rejected:
                raise HTTPException(status_code=422, detail=rejected[0]["reason"])

            # Checkpoint only after validation passes — a rejected
            # instruction never reaches a write at all, so it shouldn't
            # burn an undo-history slot for nothing.
            def do_write():
                updated_plan = apply_operations(scene_plan, valid_ops)
                updated_plan = reflow_timeline(updated_plan)

                write_json_atomic(scene_plan_path, updated_plan)
                regenerate_codegen(episode)

            wrap_with_checkpoint(processing, [scene_plan_path], "scene field edit", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"applied": valid_ops}


class EditPlanRequest(BaseModel):
    instruction: str
    # The scene id currently selected in the editor when the user
    # submitted the instruction (see #51) — lets edit_plan.py resolve
    # "this"/"that"/"it" without the user typing a scene id. Optional and
    # best-effort: a stale id (e.g. that scene was already removed by a
    # prior edit) degrades gracefully rather than erroring — see
    # edit_plan.describe_selected_scene.
    selectedSceneId: str | None = None


MOMENT_SCENE_ID_PATTERN = re.compile(r"^scene-moment-(\d+)$")


def _sync_removed_moments(processing: Path, scene_plan_before, removed_ids: set[str]):
    """A chat-removed moment (edit_plan.py only ever writes scene-plan.json)
    would otherwise be silently resurrected the next time anything calls
    update_moments/merge_moment_scenes — that function unconditionally
    rebuilds every moment scene in scene-plan.json from moments.json, and
    the chat removal never touched moments.json in the first place (see
    #33). Strips the same indices out of moments.json here so both
    artifacts agree on which moments exist, keeping moments.json the
    single source of truth for moment scenes rather than letting
    scene-plan.json and moments.json silently diverge. No-ops (returns
    None) if nothing removed was a moment, or moments.json doesn't exist —
    an episode with no moments proposed yet has nothing to sync."""

    moment_indices = set()
    for scene in scene_plan_before["scenes"]:
        if scene["id"] not in removed_ids:
            continue
        match = MOMENT_SCENE_ID_PATTERN.match(scene["id"])
        if match:
            moment_indices.add(int(match.group(1)))

    if not moment_indices:
        return None

    moments_path = processing / "moments.json"
    if not moments_path.exists():
        return None

    with moments_path.open("r", encoding="utf-8") as f:
        moments = json.load(f).get("moments", [])

    next_moments = [m for i, m in enumerate(moments) if i not in moment_indices]

    write_json_atomic(moments_path, {"moments": next_moments})
    return next_moments


def _sync_removed_titles(processing: Path, scene_plan_before, removed_ids: set[str]):
    """Same resurrection risk as moments (see _sync_removed_moments), but
    title_scenes.json entries have no id shared with the merged
    scene-plan.json TitleScene — only text (see #32's known, accepted
    text-match correlation, same one TitleEditorPanel already relies on).
    Removes any title_scenes.json entry whose text matches a removed
    title scene's text. Fine in practice since title text is expected to
    be unique per episode; if that assumption breaks, the match is
    ambiguous, same known limitation as everywhere else this correlation
    is used."""

    removed_texts = {
        scene["text"]
        for scene in scene_plan_before["scenes"]
        if scene["id"] in removed_ids and scene["type"] == "title"
    }

    if not removed_texts:
        return None

    title_scenes_path = processing / "title_scenes.json"
    if not title_scenes_path.exists():
        return None

    with title_scenes_path.open("r", encoding="utf-8") as f:
        titles = json.load(f).get("titles", [])

    next_titles = [t for t in titles if t["text"] not in removed_texts]

    write_json_atomic(title_scenes_path, {"titles": next_titles})
    return next_titles


@app.post("/api/episode/edit-plan")
def edit_scene_plan(path: str, body: EditPlanRequest):
    """Applies a natural-language instruction to scene-plan.json — the
    in-app edit loop the preview app's chat box calls. Loads the current
    plan, asks the LLM (same claude-code-CLI-backed LLMClient every other AI
    stage uses, no separate API key) to propose remove/update operations
    against real scene ids and an allowlisted set of fields per scene type,
    rejects anything that fails validation (edit_plan.validate_operations —
    unknown scene id, or a field outside that type's allowlist), applies
    only what's valid, then reflows track-scene timelineStartFrame so the
    timeline stays contiguous if a presenter trim changed a scene's
    duration. A plain (not async) def — FastAPI runs sync routes in a
    thread pool, so the LLM subprocess call here doesn't block the event
    loop, same as every other route in this file.

    Any removed moment/title scene is also stripped from moments.json/
    title_scenes.json (see #33) — otherwise a later structured-editor save
    (which rewrites its target file from scratch and re-merges) would
    silently resurrect it, since those source files never learn about a
    chat-only removal on their own."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    episode_transcript_path = processing / "episode_transcript.json"
    manifest_path = processing / "manifest.json"
    beats_path = processing / "emphasis.json"
    moments_path = processing / "moments.json"
    assets_path = processing / "assets.json"

    # Beat/moment creation (#52/#53) needs real word-level transcript
    # timing to ground itself — both optional here (unlike
    # update_title_scenes, which 404s without them): an episode with no
    # word-level transcript data can still use every other chat
    # operation, it just can't create beats/moments (see edit_plan()'s
    # own docstring — this mirrors generate_emphasis.py's own graceful
    # no-op for the same case). Image creation is likewise optional on
    # assets.json existing (an episode with no indexed graphics/ folder
    # can't ground an inset image either).
    episode_transcript = None
    manifest = None
    assets = None

    if episode_transcript_path.exists() and manifest_path.exists():
        with episode_transcript_path.open("r", encoding="utf-8") as f:
            episode_transcript = json.load(f)
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

    if assets_path.exists():
        with assets_path.open("r", encoding="utf-8") as f:
            assets = json.load(f).get("assets", [])

    try:
        with episode_lock(episode, wait=False):
            with scene_plan_path.open("r", encoding="utf-8") as f:
                scene_plan = json.load(f)

            llm = LLMClient(PROJECT_ROOT / "config.json")
            prompt_template = load_edit_plan_prompt(EDIT_PLAN_PROMPT_FILE)

            try:
                updated_plan, valid_ops, rejected, created_beats, created_moments, created_images = edit_plan(
                    scene_plan, body.instruction, llm, prompt_template,
                    selected_scene_id=body.selectedSceneId,
                    transcript=episode_transcript, manifest=manifest, assets=assets,
                )
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Edit request failed: {e}")

            # Checkpoint only after the LLM call succeeds — a failed LLM
            # call never reaches a write, so it shouldn't burn an
            # undo-history slot. moments.json/title_scenes.json/
            # emphasis.json are snapshotted unconditionally alongside
            # scene-plan.json (not only when removed_ids/created_beats/
            # created_moments are non-empty below) since save_checkpoint
            # already only snapshots files that actually exist — simpler
            # than predicting exactly which of the four this particular
            # instruction will end up touching.
            # Resolved child scene ids (#54) — filled in by do_write below,
            # once existing_beats'/existing_moments' lengths are known.
            # Kept OUT of the created_beats/created_moments dicts themselves:
            # each entry's own "sceneId" field means the PARENT scene it
            # attaches to (consumed by merge_beat_scenes/merge_moment_scenes
            # to place it — see generate_emphasis.py/generate_moments.py),
            # so overwriting it here would silently break placement.
            resolved_beat_ids: list[str] = []
            resolved_moment_ids: list[str] = []
            resolved_image_ids: list[str] = []

            def do_write():
                removed_ids = {op["sceneId"] for op in valid_ops if op["op"] == "remove"}
                if removed_ids:
                    _sync_removed_moments(processing, scene_plan, removed_ids)
                    _sync_removed_titles(processing, scene_plan, removed_ids)

                plan_to_write = updated_plan

                if created_beats:
                    existing_beats = []
                    if beats_path.exists():
                        with beats_path.open("r", encoding="utf-8") as f:
                            existing_beats = json.load(f).get("beats", [])

                    # scene-beat-{N} is exactly the array index (see
                    # merge_beat_scenes) — resolvable here, before the new
                    # entries are actually written, since existing_beats'
                    # current length is where they'll land.
                    resolved_beat_ids.extend(
                        f"scene-beat-{len(existing_beats) + i}" for i in range(len(created_beats))
                    )

                    all_beats = existing_beats + created_beats
                    plan_to_write = merge_beat_scenes(plan_to_write, all_beats)
                    write_json_atomic(beats_path, {"beats": all_beats})

                if created_moments:
                    existing_moments = []
                    if moments_path.exists():
                        with moments_path.open("r", encoding="utf-8") as f:
                            existing_moments = json.load(f).get("moments", [])

                    # scene-moment-{N} — same array-index convention as
                    # beats above (see merge_moment_scenes).
                    resolved_moment_ids.extend(
                        f"scene-moment-{len(existing_moments) + i}" for i in range(len(created_moments))
                    )

                    all_moments = existing_moments + created_moments
                    plan_to_write = merge_moment_scenes(plan_to_write, all_moments)
                    write_json_atomic(moments_path, {"moments": all_moments})

                if created_images:
                    # Image scenes have no separate source-of-truth file
                    # (see #60 — scene-plan.json already IS their only
                    # representation), so unlike beats/moments there's no
                    # merge_*_scenes to call: each created image is
                    # inserted directly via insert_overlay_scene, the same
                    # helper generate_moments.py/generate_emphasis.py use
                    # internally. scene-image-{N} numbers only the NEW
                    # ones sequentially — existing image scenes (however
                    # rare) may already occupy lower numbers, so this
                    # counts from however many "scene-image-*" ids are
                    # already on the plan, not from 0.
                    existing_image_count = sum(
                        1 for s in plan_to_write["scenes"]
                        if s["type"] == "image" and s["id"].startswith("scene-image-")
                    )

                    scenes_by_id = {s["id"]: s for s in plan_to_write["scenes"]}
                    merged_scenes = list(plan_to_write["scenes"])

                    for i, image in enumerate(created_images):
                        image_id = f"scene-image-{existing_image_count + i}"
                        resolved_image_ids.append(image_id)

                        parent = scenes_by_id[image["parentSceneId"]]
                        image_scene = {"id": image_id, **image}

                        insert_overlay_scene(
                            merged_scenes,
                            scenes_by_id,
                            image_scene,
                            parent["timelineStartFrame"] + image["offsetInParentFrames"],
                        )

                    plan_to_write = dict(plan_to_write)
                    plan_to_write["scenes"] = merged_scenes

                write_json_atomic(scene_plan_path, plan_to_write)
                regenerate_codegen(episode)

            wrap_with_checkpoint(
                processing,
                [scene_plan_path, moments_path, processing / "title_scenes.json", beats_path],
                f"chat: {body.instruction}",
                do_write,
            )
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # createdSceneIds (#54) — the resolved scene-beat-{N}/scene-moment-{N}/
    # scene-image-{N} ids for created_beats/created_moments/created_images,
    # in the same order, plus every remove/update op's own sceneId —
    # everything the frontend needs to highlight what this instruction
    # actually touched.
    created_scene_ids = (
        [op["sceneId"] for op in valid_ops] + resolved_beat_ids + resolved_moment_ids + resolved_image_ids
    )

    return {
        "applied": valid_ops,
        "rejected": rejected,
        "created": created_beats,
        "createdMoments": created_moments,
        "createdImages": created_images,
        "createdSceneIds": created_scene_ids,
    }


@app.post("/api/episode/undo")
def undo_last_edit(path: str):
    """Restores the most recent checkpoint saved by any of the write
    endpoints above (moments/beats/titles/storyboard/scene-field/edit-plan
    — see undo.py's module docstring for why every write endpoint
    snapshots every file it's about to touch, not just scene-plan.json).
    Returns {"restored": None} rather than a 404/error when there's no
    checkpoint to undo — an empty undo history is a normal state (a fresh
    episode, or one already fully undone), not a failure."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    try:
        with episode_lock(episode, wait=False):
            manifest = restore_latest(processing)

            if manifest is not None:
                regenerate_codegen(episode)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"restored": manifest}


async def _run_websocket(websocket: WebSocket, build_command):
    """Accepts the connection, lets build_command(params) -> (episode,
    command) construct the episode and command to run from the client's
    initial message, then streams it. Centralizes the accept/error/close
    handling shared by every streaming endpoint. Acquires this episode's
    lock (fail-fast, not queued — see episode_locks.py) around the whole
    subprocess run, so a second tab starting a pipeline/stage/render run
    against the SAME episode while one is already in flight gets told
    immediately rather than silently racing it or queueing behind a
    potentially multi-minute run with no explanation."""

    await websocket.accept()

    try:
        params = await websocket.receive_json()
        result = await build_command(params)

        if result is None:
            return

        episode, command = result

        try:
            with episode_lock(episode, wait=False):
                await _stream_command(websocket, command)
        except EpisodeBusyError as e:
            await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


async def _watch_for_cancel(websocket: WebSocket, handle_holder: dict):
    """Waits for a {"type": "cancel"} client message and signals the running
    process's handle once it's available. Runs concurrently with log
    streaming for the same connection's lifetime; cancelled/disconnected
    without ceremony once the run finishes on its own."""

    try:
        while True:
            message = await websocket.receive_json()

            if message.get("type") == "cancel":
                handle = handle_holder.get("handle")
                if handle is not None:
                    handle.cancel()
                return
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass


@app.websocket("/ws/pipeline/run")
async def ws_run_pipeline(websocket: WebSocket):

    async def build_command(params):
        episode = resolve_episode(params["path"])
        force = bool(params.get("force", False))
        skip_captions = bool(params.get("skipCaptions", False))

        command = [str(PROJECT_ROOT / "create_episode.sh"), str(episode)]

        if force:
            command.append("--force")

        if skip_captions:
            command.append("--skip-captions")

        return episode, command

    await _run_websocket(websocket, build_command)


@app.websocket("/ws/stage/run")
async def ws_run_stage(websocket: WebSocket):

    async def build_command(params):
        episode = resolve_episode(params["path"])
        stage_id = params["stage"]
        force = bool(params.get("force", False))

        stage = find_stage(stage_id)

        if stage is None:
            await websocket.send_json({"type": "error", "message": f"Unknown stage: {stage_id}"})
            return None

        return episode, stage.build_command(episode, force=force)

    await _run_websocket(websocket, build_command)


@app.websocket("/ws/render/run")
async def ws_run_render(websocket: WebSocket):

    async def build_command(params):
        episode = resolve_episode(params["path"])
        resolution = params.get("resolution")
        output_format = params.get("format", "video")

        if resolution and not RESOLUTION_PATTERN.match(resolution):
            await websocket.send_json(
                {"type": "error", "message": f"Invalid resolution: {resolution}"}
            )
            return None

        if output_format == "davinci":
            # Same underlying scene-plan-driven, per-scene transparent
            # render as render_episode.sh --transparent, just cut into one
            # clip per track scene and assembled into an OTIO timeline the
            # user imports into a fresh DaVinci Resolve project — see
            # pipeline/export_davinci.py's own docstring. Background/intro/
            # outro/music stay a manual Resolve step either way.
            command = [
                sys.executable,
                str(PROJECT_ROOT / "pipeline" / "export_davinci.py"),
                str(episode),
            ]

            if resolution:
                command.append(resolution)

            return episode, command

        command = [str(PROJECT_ROOT / "render_episode.sh"), str(episode)]

        if resolution:
            command.append(resolution)

        return episode, command

    await _run_websocket(websocket, build_command)


async def _stream_command(websocket: WebSocket, command):
    """Runs the (blocking) process generator in a worker thread and relays
    each line to the websocket as it arrives, without blocking the event
    loop for the whole (potentially very long) process lifetime. Concurrently
    watches for a client "cancel" message so a long render/pipeline run can
    be stopped mid-flight."""

    await websocket.send_json({"type": "start", "command": " ".join(command)})

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    error_holder = {}
    handle_holder = {}

    def produce():
        try:
            for line in stream_process(command, on_start=lambda h: handle_holder.setdefault("handle", h)):
                loop.call_soon_threadsafe(queue.put_nowait, line)
        except Exception as e:
            error_holder["error"] = str(e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, produce)

    cancel_task = asyncio.ensure_future(_watch_for_cancel(websocket, handle_holder))

    try:
        while True:
            line = await queue.get()

            if line is None:
                if "error" in error_holder:
                    await websocket.send_json({"type": "error", "message": error_holder["error"]})
                return

            if line.startswith("__EXIT_CODE__"):
                exit_code = int(line.removeprefix("__EXIT_CODE__"))
                await websocket.send_json({"type": "done", "exitCode": exit_code})
                continue

            if line.startswith("__CANCELLED__"):
                await websocket.send_json({"type": "cancelled"})
                continue

            await websocket.send_json({"type": "log", "line": line})
    finally:
        cancel_task.cancel()
        try:
            await cancel_task
        except asyncio.CancelledError:
            pass
