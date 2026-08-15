#!/usr/bin/env python3

import asyncio
import json
import re
from pathlib import Path

import sys

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from episode_locks import EpisodeBusyError, episode_lock
from pipeline_stages import SECONDARY_STAGES, find_stage, stage_status
from process_runner import stream_process

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from generate_title_scenes import merge_title_scenes, write_json_atomic  # noqa: E402
from generate_moments import merge_moment_scenes  # noqa: E402
from generate_scene_plan_ts import generate_scene_plan_ts  # noqa: E402
from edit_plan import edit_plan, load_prompt as load_edit_plan_prompt, PROMPT_FILE as EDIT_PLAN_PROMPT_FILE  # noqa: E402
from llm.client import LLMClient  # noqa: E402

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

    try:
        with episode_lock(episode, wait=False):
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
            write_json_atomic(storyboard_path, {"chapters": chapters})
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
    caption: str | None = None
    reason: str = ""


class MomentsUpdate(BaseModel):
    moments: list[MomentProposal]


@app.put("/api/episode/moments")
def update_moments(path: str, body: MomentsUpdate):
    """Human edits to AI-proposed moment overlays: treatment, text/assetId,
    timing (offsetInParentFrames), duration (maxDurationInParentFrames,
    capped by merge_moment_scenes at duration_for_treatment(...)), and
    presenterSide. Writes the edited proposals back to moments.json, then
    deterministically re-merges them into scene-plan.json the same way
    generate_moments.py does after the LLM call — no LLM involved here.
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

    try:
        with episode_lock(episode, wait=False):
            with scene_plan_path.open("r", encoding="utf-8") as f:
                scene_plan = json.load(f)

            scene_plan = merge_moment_scenes(scene_plan, moments)

            write_json_atomic(moments_path, {"moments": moments})
            write_json_atomic(scene_plan_path, scene_plan)
            regenerate_codegen(episode)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"moments": moments}


class EditPlanRequest(BaseModel):
    instruction: str


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
    loop, same as every other route in this file."""

    episode = resolve_episode(path)
    processing = episode / "processing"

    scene_plan_path = processing / "scene-plan.json"

    if not scene_plan_path.exists():
        raise HTTPException(status_code=404, detail="scene-plan.json not found — run the pipeline first")

    try:
        with episode_lock(episode, wait=False):
            with scene_plan_path.open("r", encoding="utf-8") as f:
                scene_plan = json.load(f)

            llm = LLMClient(PROJECT_ROOT / "config.json")
            prompt_template = load_edit_plan_prompt(EDIT_PLAN_PROMPT_FILE)

            try:
                updated_plan, valid_ops, rejected = edit_plan(
                    scene_plan, body.instruction, llm, prompt_template
                )
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Edit request failed: {e}")

            write_json_atomic(scene_plan_path, updated_plan)
            regenerate_codegen(episode)
    except EpisodeBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"applied": valid_ops, "rejected": rejected}


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


app.mount("/", StaticFiles(directory=str(UI_DIR / "static"), html=True), name="static")
