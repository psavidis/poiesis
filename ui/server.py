#!/usr/bin/env python3

import asyncio
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from pipeline_stages import SECONDARY_STAGES, find_stage, stage_status
from process_runner import stream_process

RESOLUTION_PATTERN = re.compile(r"^\d+x\d+$")

UI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = UI_DIR.parent

app = FastAPI(title="Poiesis Control Panel")


def resolve_episode(path: str) -> Path:
    episode = Path(path).expanduser().resolve()

    if not episode.exists() or not episode.is_dir():
        raise HTTPException(status_code=404, detail=f"Episode folder not found: {episode}")

    return episode


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
        "visual_scenes.json",
        "assets.json",
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


async def _run_websocket(websocket: WebSocket, build_command):
    """Accepts the connection, lets build_command(params) -> list[str]
    construct the command to run from the client's initial message, then
    streams it. Centralizes the accept/error/close handling shared by every
    streaming endpoint."""

    await websocket.accept()

    try:
        params = await websocket.receive_json()
        command = await build_command(params)

        if command is None:
            return

        await _stream_command(websocket, command)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


@app.websocket("/ws/pipeline/run")
async def ws_run_pipeline(websocket: WebSocket):

    async def build_command(params):
        episode = resolve_episode(params["path"])
        force = bool(params.get("force", False))

        command = [str(PROJECT_ROOT / "create_episode.sh"), str(episode)]

        if force:
            command.append("--force")

        return command

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

        return stage.build_command(episode, force=force)

    await _run_websocket(websocket, build_command)


@app.websocket("/ws/render/run")
async def ws_run_render(websocket: WebSocket):

    async def build_command(params):
        episode = resolve_episode(params["path"])
        resolution = params.get("resolution")

        command = [str(PROJECT_ROOT / "render_episode.sh"), str(episode)]

        if resolution:
            if not RESOLUTION_PATTERN.match(resolution):
                await websocket.send_json(
                    {"type": "error", "message": f"Invalid resolution: {resolution}"}
                )
                return None

            command.append(resolution)

        return command

    await _run_websocket(websocket, build_command)


async def _stream_command(websocket: WebSocket, command):
    """Runs the (blocking) process generator in a worker thread and relays
    each line to the websocket as it arrives, without blocking the event
    loop for the whole (potentially very long) process lifetime."""

    await websocket.send_json({"type": "start", "command": " ".join(command)})

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    error_holder = {}

    def produce():
        try:
            for line in stream_process(command):
                loop.call_soon_threadsafe(queue.put_nowait, line)
        except Exception as e:
            error_holder["error"] = str(e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, produce)

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

        await websocket.send_json({"type": "log", "line": line})


app.mount("/", StaticFiles(directory=str(UI_DIR / "static"), html=True), name="static")
