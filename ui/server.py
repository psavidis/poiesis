#!/usr/bin/env python3

import asyncio
import json
import re
import threading
from pathlib import Path

import sys

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from episode_locks import EpisodeBusyError, episode_lock, is_episode_locked
from pipeline_stages import SECONDARY_STAGES, find_stage, stage_status
from process_runner import stream_process
from undo import restore_latest, wrap_with_checkpoint

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from generate_title_scenes import (  # noqa: E402
    compute_overridden_fields as compute_overridden_title_fields,
    merge_title_scenes,
    resolvable_segment_positions,
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
    resolve_manual_moment_creation,
)
from generate_cut_candidates import (  # noqa: E402
    compute_overridden_cut_fields,
)
from generate_background_scenes import (  # noqa: E402
    background_insertable_positions,
    merge_background_scenes,
)
from index_assets import index_assets  # noqa: E402
from index_backgrounds import index_backgrounds  # noqa: E402
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
    allow_methods=["GET", "PUT", "POST", "DELETE"],
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


@app.get("/api/episode/render-status")
def render_status(path: str):
    """Lets a client recover a render's live N-of-M progress AND what kind
    of render it is (format/resolution) after losing its websocket
    connection (e.g. a page refresh) instead of only ever seeing it
    through the one connection that started the run — see
    _render_progress's own comment. Polled once on the Advanced panel's
    mount (and continuously by RenderStatusBanner from every other tab);
    "running" reflects episode_locks.py's own lock state (a render could
    theoretically be mid-flight with no progress recorded yet, in the
    brief window before export_davinci.py's first __TOTAL__ line arrives —
    current/total are None in that case, "running" is still true, and the
    panel shows an indeterminate "Rendering..." state rather than a bar
    with no numbers to show). format/resolution are set once, up front
    (see ws_run_render's build_command), so they're available even in
    that same pre-__TOTAL__ window."""

    episode = resolve_episode(path)

    with _render_progress_guard:
        progress = _render_progress.get(str(episode))

    return {
        "running": is_episode_locked(episode),
        "current": progress.get("current") if progress else None,
        "total": progress.get("total") if progress else None,
        "format": progress.get("format") if progress else None,
        "resolution": progress.get("resolution") if progress else None,
    }


@app.post("/api/episode/render-cancel")
def render_cancel(path: str):
    """Cancels a render that's still running but whose original websocket
    connection is gone — e.g. the tab that clicked Render was refreshed,
    so AdvancedPanel's own runHandleRef (and therefore its normal Cancel
    button, which calls runHandleRef.current?.cancel() over that specific
    websocket) no longer exists for this run. Looks up the ProcessHandle
    _stream_command registered in _render_handles when the subprocess
    actually started (see _on_start in that function) and cancels it the
    same way ProcessHandle.cancel() always has — SIGTERM to the whole
    process group, since a render spawns its own child processes (npx,
    remotion) that a bare kill of just the top process would orphan.

    404 if nothing is currently running for this episode (nothing to
    cancel) rather than silently no-op-ing, so a client can tell the
    difference between "cancelled" and "there was nothing here" — a
    refresh raced against the render finishing on its own is the normal
    way this would happen, not a bug."""

    episode = resolve_episode(path)

    with _render_progress_guard:
        handle = _render_handles.get(str(episode))

    if handle is None:
        raise HTTPException(status_code=404, detail="No render is currently running for this episode")

    handle.cancel()

    return {"cancelled": True}


@app.get("/api/episode/artifact")
def episode_artifact(path: str, name: str):
    episode = resolve_episode(path)

    allowed = {
        "title_scenes.json",
        "storyboard.json",
        "moments.json",
        "emphasis.json",
        "cut_candidates.json",
        "captions.json",
        "assets.json",
        "code_assets.json",
        "backgrounds.json",
        "background_scenes.json",
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
    # Human-set override for this title's own on-screen display duration
    # (#83) — set by dragging the title's segment edge in SceneBar. Absent
    # means "use the read-time-based default" (#89, see
    # default_title_duration_frames), same as every title before this field
    # existed — see merge_title_scenes's own doc comment for the reflow
    # this produces.
    durationFrames: int | None = None
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


class BackgroundSceneEntry(BaseModel):
    segmentId: str
    backgroundId: str
    # Slow zoom drift for a static-image background — only meaningful
    # when the referenced background's mediaType is "image" (see
    # BackgroundImageMotion in types.ts). Absent/None means no motion,
    # same as every background entry before this field existed.
    imageMotion: str | None = None
    # How much the drift scales, only meaningful when imageMotion is set
    # (see BackgroundImageMotionSpeed in types.ts). Absent/None means
    # "normal" — the renderer's own default.
    imageMotionSpeed: str | None = None


class BackgroundScenesUpdate(BaseModel):
    scenes: list[BackgroundSceneEntry]


@app.put("/api/episode/background-scenes")
def update_background_scenes(path: str, body: BackgroundScenesUpdate):
    """Human-authored background selections (#87) — unlike titles/moments/
    beats, backgrounds are never AI-proposed, so there is no
    overriddenFields to recompute here, only a direct write-and-remerge.
    Writes the edited entries back to background_scenes.json, then
    deterministically re-merges them into scene-plan.json the same way
    merge_background_scenes always does — safe to re-run even if
    backgrounds were already merged before, since it rebuilds every
    BackgroundScene from scratch each call."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"
    background_scenes_path = processing / "background_scenes.json"
    episode_transcript_path = processing / "episode_transcript.json"
    manifest_path = processing / "manifest.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    if not episode_transcript_path.exists() or not manifest_path.exists():
        raise HTTPException(status_code=404, detail="episode_transcript.json/manifest.json not found — run the pipeline first")

    entries = [entry.model_dump() for entry in body.scenes]

    def do_write():
        with scene_plan_path.open("r", encoding="utf-8") as f:
            scene_plan = json.load(f)

        with episode_transcript_path.open("r", encoding="utf-8") as f:
            episode_transcript = json.load(f)

        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        scene_plan = merge_background_scenes(scene_plan, entries, episode_transcript, manifest)

        write_json_atomic(background_scenes_path, {"scenes": entries})
        write_json_atomic(scene_plan_path, scene_plan)
        regenerate_codegen(episode)

    try:
        with episode_lock(episode, wait=False):
            wrap_with_checkpoint(processing, [scene_plan_path, background_scenes_path], "background edit", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"scenes": entries}


@app.get("/api/episode/chapter-boundary-positions")
def chapter_boundary_positions(path: str):
    """Every transcript segment's resolved timeline frame, for the
    chapter-boundary drag UI (ChapterStrip.tsx) to snap a dragged pixel
    position to the nearest one client-side, with no per-pixel server
    round trip. Segment text is deliberately excluded — see
    resolvable_segment_positions."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"
    episode_transcript_path = processing / "episode_transcript.json"
    manifest_path = processing / "manifest.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    if not episode_transcript_path.exists() or not manifest_path.exists():
        raise HTTPException(status_code=404, detail="episode_transcript.json/manifest.json not found — run the pipeline first")

    with scene_plan_path.open("r", encoding="utf-8") as f:
        scene_plan = json.load(f)

    with episode_transcript_path.open("r", encoding="utf-8") as f:
        episode_transcript = json.load(f)

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    return {"positions": resolvable_segment_positions(scene_plan, episode_transcript, manifest)}


@app.get("/api/episode/background-insertable-positions")
def background_insertable_positions_route(path: str):
    """Every position a background can snap to when inserted at the
    playhead (BackgroundBar's Cmd+B, AssetLibraryPanel's Backgrounds tab)
    — every transcript segment's resolved frame (see
    chapter_boundary_positions above) PLUS each presenter piece's own
    timelineStartFrame. The clip-start entries matter because a clip's
    first transcript segment routinely starts a few frames after the
    clip's own start (silence trimmed before the first spoken word) —
    without them, inserting a background exactly at a clip's start (e.g.
    the episode's own frame 0) snaps to the nearest transcript segment
    instead and lands a few frames late. Deliberately a separate endpoint
    from chapter-boundary-positions rather than adding these entries
    there: ChapterStrip's title-boundary drag writes its own snapped
    segmentId straight into title_scenes.json, which only ever resolves
    real "sN" transcript ids (see merge_title_scenes) — mixing in
    "clip:..." ids there would make a title snapped onto one silently
    fail to resolve. See background_insertable_positions's own doc
    comment."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"
    episode_transcript_path = processing / "episode_transcript.json"
    manifest_path = processing / "manifest.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    if not episode_transcript_path.exists() or not manifest_path.exists():
        raise HTTPException(status_code=404, detail="episode_transcript.json/manifest.json not found — run the pipeline first")

    with scene_plan_path.open("r", encoding="utf-8") as f:
        scene_plan = json.load(f)

    with episode_transcript_path.open("r", encoding="utf-8") as f:
        episode_transcript = json.load(f)

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    return {"positions": background_insertable_positions(scene_plan, episode_transcript, manifest)}


@app.post("/api/episode/backgrounds/reindex")
def reindex_backgrounds(path: str):
    """Re-scans the episode's background/ folder and rewrites
    backgrounds.json — the same work the "Index backgrounds" Advanced
    stage does (see index_backgrounds.py), called in-process here instead
    of shelling out so AssetLibraryPanel can call this itself whenever its
    Backgrounds tab becomes active (#92's "autodiscovery": a file dropped
    into background/ shows up without the user having to remember to run
    the Advanced stage by hand). Always safe to re-run — index_backgrounds
    keys existing entries by filename, so already-indexed backgrounds keep
    their id/caption rather than being renumbered (see its own docstring)."""

    episode = resolve_episode(path)

    backgrounds = index_backgrounds(episode)

    return {"backgrounds": backgrounds}


@app.delete("/api/episode/backgrounds/{background_id}")
def delete_background(background_id: str, path: str):
    """Deletes one background/ file from disk and re-indexes — the
    deterministic counterpart to reindex_backgrounds above, for #92's
    delete requirement. Only removes the source file; it deliberately does
    NOT touch background_scenes.json/scene-plan.json (a background already
    placed on the timeline keeps its own backgroundId reference, same as
    deleting an image/code asset file never retroactively un-applies it
    from a moment) — a scene referencing a since-deleted background is
    caught by qa_check.py, not silently rewritten here."""

    episode = resolve_episode(path)
    processing = episode / "processing"
    backgrounds_path = processing / "backgrounds.json"

    if not backgrounds_path.exists():
        raise HTTPException(status_code=404, detail="backgrounds.json not found — run the pipeline first")

    with backgrounds_path.open("r", encoding="utf-8") as f:
        existing = json.load(f)

    match = next((bg for bg in existing.get("backgrounds", []) if bg["id"] == background_id), None)

    if match is None:
        raise HTTPException(status_code=404, detail=f"Background not found: {background_id}")

    file_path = episode / match["path"]

    try:
        with episode_lock(episode, wait=False):

            def do_write():
                if file_path.exists():
                    file_path.unlink()
                return index_backgrounds(episode)

            backgrounds = wrap_with_checkpoint(processing, [backgrounds_path], "background deletion", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"deleted": background_id, "backgrounds": backgrounds}


@app.post("/api/episode/assets/reindex")
def reindex_assets(path: str):
    """Re-scans the episode's graphics/ folder and rewrites assets.json —
    the same work the "Index graphics assets" Advanced stage does (see
    index_assets.py), called in-process here so AssetLibraryPanel can call
    this itself whenever its Images tab becomes active (#93's
    "autodiscovery", mirroring #92's reindex_backgrounds). Always safe to
    re-run — index_assets keys existing entries by filename, so
    already-indexed assets keep their id/caption rather than being
    renumbered (see its own docstring)."""

    episode = resolve_episode(path)

    assets = index_assets(episode)

    return {"assets": assets}


@app.delete("/api/episode/assets/{asset_id}")
def delete_asset(asset_id: str, path: str):
    """Deletes one graphics/ file from disk and re-indexes — the
    deterministic counterpart to reindex_assets above, for #93's delete
    requirement (mirrors #92's delete_background). Only removes the
    source file; it deliberately does NOT touch moments.json (a moment
    already using this assetId keeps its own reference, same as deleting
    a background file never retroactively un-applies it from a scene) —
    a moment referencing a since-deleted asset is caught by qa_check.py,
    not silently rewritten here."""

    episode = resolve_episode(path)
    processing = episode / "processing"
    assets_path = processing / "assets.json"

    if not assets_path.exists():
        raise HTTPException(status_code=404, detail="assets.json not found — run the pipeline first")

    with assets_path.open("r", encoding="utf-8") as f:
        existing = json.load(f)

    match = next((a for a in existing.get("assets", []) if a["id"] == asset_id), None)

    if match is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")

    file_path = episode / match["path"]

    try:
        with episode_lock(episode, wait=False):

            def do_write():
                if file_path.exists():
                    file_path.unlink()
                return index_assets(episode)

            assets = wrap_with_checkpoint(processing, [assets_path], "asset deletion", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"deleted": asset_id, "assets": assets}


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
    # Human-set size/position override (#77) — {xPct, yPct, widthPct,
    # heightPct}, percentage-of-canvas, set by dragging/resizing this
    # moment on the preview-app's player. Absent means "use the
    # treatment's own default geometry" — see timing.ts's resolveBoxStyle.
    box: dict | None = None
    # Where `caption` renders relative to the asset/video ("overlay" /
    # "below" / "off") — never AI-proposed, always a human choice (#82).
    # Absent means "overlay", same as every episode from before this field
    # existed.
    captionPlacement: str | None = None
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


class MomentInsert(BaseModel):
    sceneId: str
    offsetInParentFrames: int
    kind: str


@app.post("/api/episode/moments/insert")
def insert_moment(path: str, body: MomentInsert):
    """Cmd+I: a human-initiated moment insertion at the playhead — appends
    a minimal, content-empty proposal (resolve_manual_moment_creation) to
    moments.json and re-merges, the same write path update_moments already
    uses, just with one new proposal appended instead of the client's own
    edited array round-tripped. Returns the new moment's sceneId
    (scene-moment-{index}, same convention every moment endpoint in this
    file uses) so the frontend can select it and open its editor
    immediately — the moment has no real content yet until that happens."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"
    moments_path = processing / "moments.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    with scene_plan_path.open("r", encoding="utf-8") as f:
        scene_plan = json.load(f)

    proposal = resolve_manual_moment_creation(body.sceneId, body.offsetInParentFrames, body.kind, scene_plan)

    if proposal is None:
        raise HTTPException(
            status_code=400,
            detail="Couldn't insert a moment here — check the scene id, kind, and that there's room at this position.",
        )

    old_moments = []
    if moments_path.exists():
        with moments_path.open("r", encoding="utf-8") as f:
            old_moments = json.load(f).get("moments", [])

    # windowId is a generate_moments.py-only concept (a candidate window's
    # position within its own parent scene) that resolve_manual_moment_
    # creation never sets — meaningless for a moment that didn't come from
    # that windowing process. The MomentProposal Pydantic model requires it
    # though, so a moment with none breaks every LATER save of the full
    # array (any drag/click-commit elsewhere re-sends this moment verbatim
    # and 422s) — the exact bug already fixed once for chat-created moments
    # in update_edit_plan below. manual-w{N}, not chat-w{N}/w{N}, so it can
    # never collide with either.
    proposal["windowId"] = f"manual-w{len(old_moments)}"

    moments = old_moments + [proposal]
    new_scene_id = f"scene-moment-{len(moments) - 1}"

    def do_write():
        with scene_plan_path.open("r", encoding="utf-8") as f:
            fresh_scene_plan = json.load(f)

        merged = merge_moment_scenes(fresh_scene_plan, moments)

        write_json_atomic(moments_path, {"moments": moments})
        write_json_atomic(scene_plan_path, merged)
        regenerate_codegen(episode)

    try:
        with episode_lock(episode, wait=False):
            wrap_with_checkpoint(processing, [scene_plan_path, moments_path], "moment insert", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"moments": moments, "sceneId": new_scene_id}


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


class CutCandidate(BaseModel):
    sceneId: str
    videoId: str
    cutStartFrame: int
    cutEndFrame: int
    durationSeconds: float
    reason: str = ""
    status: str = "pending"
    # Same recompute-on-save contract as moments'/beats' overriddenFields —
    # a client only needs to round-trip whatever getCutCandidates()
    # returned; this endpoint recomputes it below (see
    # compute_overridden_cut_fields in generate_cut_candidates.py).
    overriddenFields: list[str] = []


class CutCandidatesUpdate(BaseModel):
    cuts: list[CutCandidate]


@app.put("/api/episode/cut-candidates")
def update_cut_candidates(path: str, body: CutCandidatesUpdate):
    """Human accept/reject/boundary-edit of AI-proposed pause cuts (#65).
    Unlike update_moments/update_beats, this does NOT rebuild scene-plan.json's
    overlay scenes wholesale on every save — cut_candidates.json's entries are
    inert proposals until a human acts on them. Only a cut whose status
    transitions from "pending" to "accepted" in THIS save (compared against
    what's already on disk, so re-saving an already-accepted cut is a no-op
    against scene-plan.json — idempotent, no double-cut) triggers a
    validate_operations/apply_operations/reflow_timeline "trim" op, the same
    scene-plan mutation path update_scene_fields/delete_scene already use for
    direct, non-LLM edits. Rejecting a cut (or nudging its boundary before
    accepting) is a pure metadata write to cut_candidates.json, no
    scene-plan.json touch at all.

    There is deliberately no "un-accept" here: once a cut's trim has
    reflowed the downstream timeline and re-parented (or dropped) whatever
    overlays fell after/inside the cut, flipping status back to "pending"
    can't undo any of that from this endpoint — reverting a mistaken accept
    is the existing global undo/checkpoint system's job (Cmd+Z /
    POST /api/episode/undo), same as any other mistaken edit, not a
    bespoke revert path on this endpoint."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"
    cut_candidates_path = processing / "cut_candidates.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    cuts = [c.model_dump() for c in body.cuts]

    old_cuts = []
    if cut_candidates_path.exists():
        with cut_candidates_path.open("r", encoding="utf-8") as f:
            old_cuts = json.load(f).get("cuts", [])

    for i, cut in enumerate(cuts):
        old_cut = old_cuts[i] if i < len(old_cuts) else {}
        cut["overriddenFields"] = compute_overridden_cut_fields(old_cut, cut)

    # Only cuts transitioning INTO "accepted" this save get trimmed — a cut
    # already "accepted" on disk has already had its trim applied; treating
    # it as newly-accepted again here would double-cut the footage.
    newly_accepted = [
        cut
        for i, cut in enumerate(cuts)
        if cut["status"] == "accepted" and (i >= len(old_cuts) or old_cuts[i].get("status") != "accepted")
    ]

    trim_ops = [
        {"op": "trim", "sceneId": cut["sceneId"], "cutStartFrame": cut["cutStartFrame"], "cutEndFrame": cut["cutEndFrame"]}
        for cut in newly_accepted
    ]

    with scene_plan_path.open("r", encoding="utf-8") as f:
        scene_plan = json.load(f)

    valid_ops, rejected = validate_operations(scene_plan, trim_ops)

    if rejected:
        raise HTTPException(status_code=422, detail=rejected[0]["reason"])

    def do_write():
        updated_plan = scene_plan

        if valid_ops:
            updated_plan = apply_operations(updated_plan, valid_ops)
            updated_plan = reflow_timeline(updated_plan)

        write_json_atomic(cut_candidates_path, {"cuts": cuts})
        write_json_atomic(scene_plan_path, updated_plan)
        regenerate_codegen(episode)

    try:
        with episode_lock(episode, wait=False):
            wrap_with_checkpoint(processing, [scene_plan_path, cut_candidates_path], "cut accept/reject", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"cuts": cuts}


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


@app.delete("/api/episode/scene")
def delete_scene(path: str, sceneId: str):
    """Removes a single scene from scene-plan.json by id — the deterministic
    counterpart to update_scene_fields above, for scene types with no
    separate source-of-truth file to also update (image scenes are the
    first user: ImageEditorPanel's own "Remove" button was previously a
    stub telling the user to go use the edit-plan chat instead). Reuses the
    exact same validate_operations/apply_operations path a chat-driven
    "remove this image" instruction already goes through — {"op": "remove"}
    needs no field allowlist check (see validate_operations), so this works
    for any scene type by id, not just images. Removing a scene doesn't
    cascade to overlays anchored to it (see apply_operations' own
    docstring) — a dangling parentSceneId is caught by qa_check.py, not
    silently cleaned up here."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    op = {"op": "remove", "sceneId": sceneId}

    try:
        with episode_lock(episode, wait=False):
            with scene_plan_path.open("r", encoding="utf-8") as f:
                scene_plan = json.load(f)

            valid_ops, rejected = validate_operations(scene_plan, [op])

            if rejected:
                raise HTTPException(status_code=422, detail=rejected[0]["reason"])

            def do_write():
                updated_plan = apply_operations(scene_plan, valid_ops)
                updated_plan = reflow_timeline(updated_plan)

                write_json_atomic(scene_plan_path, updated_plan)
                regenerate_codegen(episode)

            wrap_with_checkpoint(processing, [scene_plan_path], "scene removal", do_write)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"removed": sceneId}


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


def _sync_removed_cut_candidates(processing: Path, removed_ids: set[str]):
    """A presenter scene removed via chat-driven edit or DELETE
    /api/episode/scene may still have pending pause-cut candidates
    referencing it as their sceneId (#65) — unlike moments/titles, a cut
    candidate's sceneId points DIRECTLY at the presenter scene (no derived
    id pattern), so this is a simpler filter than
    _sync_removed_moments/_sync_removed_titles: any cut whose sceneId is in
    removed_ids no longer has a scene to apply a trim against. Marks it
    "rejected" (with a reason) rather than deleting the entry outright, so
    the artifact keeps a record of why it's no longer actionable instead of
    silently vanishing — consistent with cut_candidates.json never having
    entries silently removed elsewhere in this file. No-ops if nothing
    removed had pending cuts, or cut_candidates.json doesn't exist yet."""

    cut_candidates_path = processing / "cut_candidates.json"
    if not cut_candidates_path.exists():
        return None

    with cut_candidates_path.open("r", encoding="utf-8") as f:
        cuts = json.load(f).get("cuts", [])

    changed = False
    next_cuts = []

    for cut in cuts:
        if cut["sceneId"] in removed_ids and cut["status"] == "pending":
            cut = {**cut, "status": "rejected", "reason": cut["reason"] + " (scene removed)"}
            changed = True
        next_cuts.append(cut)

    if not changed:
        return None

    write_json_atomic(cut_candidates_path, {"cuts": next_cuts})
    return next_cuts


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
    code_assets_path = processing / "code_assets.json"

    # Beat/moment creation (#52/#53) needs real word-level transcript
    # timing to ground itself — both optional here (unlike
    # update_title_scenes, which 404s without them): an episode with no
    # word-level transcript data can still use every other chat
    # operation, it just can't create beats/moments (see edit_plan()'s
    # own docstring — this mirrors generate_emphasis.py's own graceful
    # no-op for the same case). Image creation is likewise optional on
    # assets.json existing (an episode with no indexed graphics/ folder
    # can't ground an inset image either). Full Screen code creation (#64)
    # is likewise optional on code_assets.json existing.
    episode_transcript = None
    manifest = None
    assets = None
    code_assets = None

    if episode_transcript_path.exists() and manifest_path.exists():
        with episode_transcript_path.open("r", encoding="utf-8") as f:
            episode_transcript = json.load(f)
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

    if assets_path.exists():
        with assets_path.open("r", encoding="utf-8") as f:
            assets = json.load(f).get("assets", [])

    if code_assets_path.exists():
        with code_assets_path.open("r", encoding="utf-8") as f:
            code_assets = json.load(f).get("codeAssets", [])

    try:
        with episode_lock(episode, wait=False):
            with scene_plan_path.open("r", encoding="utf-8") as f:
                scene_plan = json.load(f)

            llm = LLMClient(PROJECT_ROOT / "config.json")
            prompt_template = load_edit_plan_prompt(EDIT_PLAN_PROMPT_FILE)

            try:
                updated_plan, valid_ops, rejected, created_beats, created_moments, created_images, explanation = edit_plan(
                    scene_plan, body.instruction, llm, prompt_template,
                    selected_scene_id=body.selectedSceneId,
                    transcript=episode_transcript, manifest=manifest, assets=assets,
                    code_assets=code_assets,
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
                    _sync_removed_cut_candidates(processing, removed_ids)

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

                    # resolve_bottom_callout_creation (and the other
                    # create/moment resolvers) never set windowId — it's a
                    # generate_moments.py-only concept (a candidate window's
                    # position within its own parent scene), meaningless for
                    # a moment that didn't come from that windowing process.
                    # But the MomentProposal Pydantic model requires it, so
                    # a chat-created moment with no windowId broke every
                    # LATER save of the full array (any drag/click-commit
                    # elsewhere re-sends this same moment verbatim). Assign
                    # one here, at append time, where the final index is
                    # already known — chat-w{N}, not w{N}, so it can never
                    # collide with a real candidate-window id from the same
                    # parent scene.
                    for i, moment in enumerate(created_moments):
                        if not moment.get("windowId"):
                            moment["windowId"] = f"chat-w{len(existing_moments) + i}"

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
        "explanation": explanation,
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


# In-memory, per-episode "last known render progress" — lets a client that
# opens (or re-opens, e.g. after a page refresh) the Advanced panel while a
# render is already in flight recover a real N-of-M progress bar instead of
# starting blank, via GET /api/episode/render-status below. Keyed by
# resolved episode path (same key episode_locks.py uses), so this is
# naturally scoped per-episode without any extra bookkeeping. Same
# same-process, in-memory-only scope/limitation as episode_locks.py itself
# (restarting the server loses it — acceptable, since the render process
# it was tracking dies with the server anyway in that case).
_render_progress: dict[str, dict] = {}
_render_progress_guard = threading.Lock()

# Companion registry to _render_progress: the actual ProcessHandle for
# whichever subprocess a render run is currently running, keyed the same
# way. Exists so a run can be cancelled from a request that ISN'T the
# websocket connection that started it — e.g. after a page refresh, where
# AdvancedPanel's own runHandleRef is gone (a fresh page load has no
# RunHandle for a run this tab didn't start), but the actual subprocess is
# still running and still cancellable via POST /api/episode/render-cancel.
# Same in-memory, same-process scope/lifetime as _render_progress and
# episode_locks.py itself.
_render_handles: dict[str, object] = {}


def _set_render_progress(episode: Path, current: int | None, total: int | None):
    with _render_progress_guard:
        # Preserves format/resolution (set once, up front, by
        # _run_websocket — see its own docstring) across every subsequent
        # current/total update from _stream_command's __TOTAL__/__PROGRESS__
        # handling, since this function only ever knows about clip counts,
        # not what kind of render is running.
        existing = _render_progress.get(str(episode), {})
        _render_progress[str(episode)] = {**existing, "current": current, "total": total}


def _set_render_metadata(episode: Path, output_format: str, resolution: str | None):
    with _render_progress_guard:
        existing = _render_progress.get(str(episode), {})
        _render_progress[str(episode)] = {
            **existing,
            "format": output_format,
            "resolution": resolution,
            "current": existing.get("current"),
            "total": existing.get("total"),
        }


def _clear_render_progress(episode: Path):
    with _render_progress_guard:
        _render_progress.pop(str(episode), None)
    with _render_progress_guard:
        _render_handles.pop(str(episode), None)


def _set_render_handle(episode: Path, handle):
    with _render_progress_guard:
        _render_handles[str(episode)] = handle


async def _run_websocket(websocket: WebSocket, build_command):
    """Accepts the connection, lets build_command(params) -> (episode,
    command) or (episode, command, metadata) construct the episode and
    command to run from the client's initial message, then streams it.
    Centralizes the accept/error/close handling shared by every streaming
    endpoint. Acquires this episode's lock (fail-fast, not queued — see
    episode_locks.py) around the whole subprocess run, so a second tab
    starting a pipeline/stage/render run against the SAME episode while
    one is already in flight gets told immediately rather than silently
    racing it or queueing behind a potentially multi-minute run with no
    explanation.

    metadata (render runs only — ws_run_render's build_command returns a
    3-tuple; ws_run_pipeline/ws_run_stage's 2-tuples get an implicit None)
    is recorded into _render_progress only AFTER the lock is actually
    acquired — recording it any earlier (e.g. inside build_command itself,
    before episode_lock is even attempted) would let a SECOND request that
    loses the lock race to overwrite the FIRST, still-running request's
    displayed format/resolution with its own (rejected) values, since
    EpisodeBusyError never runs _clear_render_progress to undo that."""

    await websocket.accept()

    try:
        params = await websocket.receive_json()
        result = await build_command(params)

        if result is None:
            return

        episode, command, *rest = result
        metadata = rest[0] if rest else None

        try:
            with episode_lock(episode, wait=False):
                if metadata is not None:
                    _set_render_metadata(episode, metadata["format"], metadata["resolution"])
                try:
                    await _stream_command(websocket, command, episode)
                finally:
                    _clear_render_progress(episode)
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

        metadata = {"format": output_format, "resolution": resolution}

        if output_format == "davinci":
            # Presenter/title/moment/beat render as transparent clips (same
            # per-scene approach render_episode.sh --transparent uses,
            # just cut into one clip per scene); captions export as a
            # native captions.srt subtitle file, and background/image
            # scenes place their real source media directly — none of
            # those three are ever rendered by Remotion. See
            # pipeline/export_davinci.py's own docstring. Intro/outro/
            # music stay a manual Resolve step either way.
            command = [
                sys.executable,
                str(PROJECT_ROOT / "pipeline" / "export_davinci.py"),
                str(episode),
            ]

            if resolution:
                command.append(resolution)

            return episode, command, metadata

        # UI-only path — render_episode.sh itself is untouched and remains
        # the documented standalone terminal tool (see README.md). This
        # script does the same render (same "Episode" composition, same
        # width/height override) via Remotion's programmatic Node API
        # instead of shelling out to `npx remotion render`, so it gets a
        # real structured onProgress callback instead of the CLI's ANSI
        # progress bar (no stable text format to parse — see
        # render-with-progress.js's own header comment). Prints the same
        # __TOTAL__/__PROGRESS__ sentinel-line convention
        # pipeline/export_davinci.py already established for the DaVinci
        # path, so _stream_command's existing parsing (and the frontend's
        # existing progress bar) work unchanged for this format too.
        regenerate_codegen(episode)

        command = [
            "node",
            str(RENDERER_DIR / "render-with-progress.js"),
            str(episode),
        ]

        if resolution:
            command.append(resolution)

        return episode, command, metadata

    await _run_websocket(websocket, build_command)


async def _stream_command(websocket: WebSocket, command, episode: Path | None = None):
    """Runs the (blocking) process generator in a worker thread and relays
    each line to the websocket as it arrives, without blocking the event
    loop for the whole (potentially very long) process lifetime. Concurrently
    watches for a client "cancel" message so a long render/pipeline run can
    be stopped mid-flight.

    episode, when given (render runs only — stage/QA runs pass None), is
    used to mirror every total/progress message into _render_progress so a
    DIFFERENT client (e.g. this same tab after a refresh, or a second tab)
    can recover the current N-of-M via GET /api/episode/render-status
    instead of only ever seeing progress live over this one websocket
    connection — see that dict's own comment.

    Critically, this function's own loop — and therefore the episode_lock
    this is called from inside (see _run_websocket) — stays alive for the
    SUBPROCESS's real lifetime, not the websocket's. A page refresh closes
    the websocket (send_json starts raising) long before the subprocess
    actually exits; if that exception were allowed to propagate out of
    this function, it would unwind past episode_lock's `with` block and
    release the lock while export_davinci.py/npx remotion render keep
    running and writing files completely untracked — is_episode_locked()
    would then report the episode as free while a render is still
    genuinely in flight (confirmed live: this exact bug shipped in an
    earlier version of this function). _send, below, swallows a
    send-to-a-dead-socket failure (marking the socket dead so further
    sends are skipped rather than retried) without stopping the loop
    itself — the loop keeps draining the queue and updating
    _render_progress/holding the lock until the subprocess's own
    __EXIT_CODE__/__CANCELLED__/produce()-finished signal says it's
    actually done."""

    socket_dead = False

    async def _send(payload):
        nonlocal socket_dead
        if socket_dead:
            return
        try:
            await websocket.send_json(payload)
        except Exception:
            socket_dead = True

    await _send({"type": "start", "command": " ".join(command)})

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    error_holder = {}
    handle_holder = {}

    def _on_start(handle):
        handle_holder.setdefault("handle", handle)
        # Registered so a request OTHER than this websocket (e.g.
        # POST /api/episode/render-cancel after a page refresh, when
        # AdvancedPanel's own runHandleRef for this run no longer exists)
        # can still cancel the actual subprocess — see _render_handles'
        # own comment. Only meaningful for render runs (episode is None
        # for stage/QA runs, which already have a working cancel path via
        # their own still-live websocket).
        if episode is not None:
            _set_render_handle(episode, handle)

    def produce():
        try:
            for line in stream_process(command, on_start=_on_start):
                loop.call_soon_threadsafe(queue.put_nowait, line)
        except Exception as e:
            error_holder["error"] = str(e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, produce)

    # _watch_for_cancel reads from the websocket itself — once the socket
    # is dead there's nothing more it can usefully wait on, but it already
    # degrades safely on WebSocketDisconnect (see its own try/except), so
    # no special handling is needed here beyond the existing cleanup below.
    cancel_task = asyncio.ensure_future(_watch_for_cancel(websocket, handle_holder))

    try:
        while True:
            line = await queue.get()

            if line is None:
                if "error" in error_holder:
                    await _send({"type": "error", "message": error_holder["error"]})
                return

            if line.startswith("__EXIT_CODE__"):
                exit_code = int(line.removeprefix("__EXIT_CODE__"))
                await _send({"type": "done", "exitCode": exit_code})
                continue

            if line.startswith("__CANCELLED__"):
                await _send({"type": "cancelled"})
                continue

            # export_davinci.py (#65's sibling render-console request)
            # prints one __TOTAL__N line upfront and one __PROGRESS__i/N
            # line per clip rendered or skipped — translated into
            # structured messages here, same sentinel-line convention as
            # __EXIT_CODE__/__CANCELLED__ above, so AdvancedPanel can show
            # a real progress bar instead of parsing raw log text for it.
            # Other scripts never print these prefixes, so this is a no-op
            # for every other websocket-driven run (stage/QA). This is
            # deliberately updated even once socket_dead is true (_send
            # itself no-ops the actual websocket call, but the
            # _set_render_progress call above/outside _send always runs) —
            # a refreshed tab's later GET /api/episode/render-status poll
            # needs this to keep advancing after the original connection
            # is gone, which is the entire point of this recovery path.
            if line.startswith("__TOTAL__"):
                total = int(line.removeprefix("__TOTAL__"))
                if episode is not None:
                    _set_render_progress(episode, 0, total)
                await _send({"type": "total", "count": total})
                continue

            if line.startswith("__PROGRESS__"):
                current, total = line.removeprefix("__PROGRESS__").split("/")
                current, total = int(current), int(total)
                if episode is not None:
                    _set_render_progress(episode, current, total)
                await _send({"type": "progress", "current": current, "total": total})
                continue

            await _send({"type": "log", "line": line})
    finally:
        cancel_task.cancel()
        try:
            await cancel_task
        except asyncio.CancelledError:
            pass
