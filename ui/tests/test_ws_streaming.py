import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

import server
from server import app

client = TestClient(app)


def test_ws_stage_run_rejects_unknown_stage(tmp_path):
    episode = tmp_path / "episode"
    episode.mkdir()

    with client.websocket_connect("/ws/stage/run") as ws:
        ws.send_json({"path": str(episode), "stage": "not-a-real-stage"})
        msg = ws.receive_json()

    assert msg["type"] == "error"
    assert "not-a-real-stage" in msg["message"]


def test_ws_stage_run_rejects_missing_episode():
    with client.websocket_connect("/ws/stage/run") as ws:
        ws.send_json({"path": "/definitely/does/not/exist", "stage": "qa_check"})
        msg = ws.receive_json()

    assert msg["type"] == "error"


class _SlowStage:
    id = "slow_stage"

    def build_command(self, episode, force=False):
        return [sys.executable, "-c", "import time; time.sleep(30)"]


def test_ws_stage_run_cancel_stops_the_process(tmp_path, monkeypatch):
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr(server, "find_stage", lambda stage_id: _SlowStage())

    with client.websocket_connect("/ws/stage/run") as ws:
        ws.send_json({"path": str(episode), "stage": "slow_stage"})

        start_msg = ws.receive_json()
        assert start_msg["type"] == "start"

        ws.send_json({"type": "cancel"})

        msg = ws.receive_json()
        while msg["type"] == "log":
            msg = ws.receive_json()

        assert msg["type"] == "cancelled"


def test_ws_stage_run_rejects_second_run_for_same_episode_while_first_in_flight(tmp_path, monkeypatch):
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr(server, "find_stage", lambda stage_id: _SlowStage())

    with client.websocket_connect("/ws/stage/run") as first_ws:
        first_ws.send_json({"path": str(episode), "stage": "slow_stage"})
        start_msg = first_ws.receive_json()
        assert start_msg["type"] == "start"

        # first run is still in flight (holding the episode lock) — a
        # second run against the SAME episode must be rejected immediately
        # rather than queued or allowed to race the first
        with client.websocket_connect("/ws/stage/run") as second_ws:
            second_ws.send_json({"path": str(episode), "stage": "slow_stage"})
            second_msg = second_ws.receive_json()

        assert second_msg["type"] == "error"
        assert "already running" in second_msg["message"]

        # cleanup only — accept either outcome, see the comment in
        # test_ws_stage_run_allows_concurrent_runs_for_different_episodes
        first_ws.send_json({"type": "cancel"})
        msg = first_ws.receive_json()
        while msg["type"] == "log":
            msg = first_ws.receive_json()
        assert msg["type"] in ("cancelled", "done")


def test_ws_stage_run_allows_concurrent_runs_for_different_episodes(tmp_path, monkeypatch):
    episode_a = tmp_path / "episode-a"
    episode_a.mkdir()
    episode_b = tmp_path / "episode-b"
    episode_b.mkdir()

    monkeypatch.setattr(server, "find_stage", lambda stage_id: _SlowStage())

    with client.websocket_connect("/ws/stage/run") as first_ws:
        first_ws.send_json({"path": str(episode_a), "stage": "slow_stage"})
        start_msg = first_ws.receive_json()
        assert start_msg["type"] == "start"

        # a different episode must not be blocked by episode_a's in-flight
        # run — the actual thing under test is this second "start" arriving
        # at all rather than an "error" about the (unrelated) episode being
        # busy. Cancel both afterward just to clean up the slow subprocess;
        # accept either "cancelled" or "done" for that cleanup step since
        # the cancel racing the process's own 30s sleep under a loaded test
        # run is not what's being tested here.
        with client.websocket_connect("/ws/stage/run") as second_ws:
            second_ws.send_json({"path": str(episode_b), "stage": "slow_stage"})
            second_msg = second_ws.receive_json()
            assert second_msg["type"] == "start"

            second_ws.send_json({"type": "cancel"})
            msg = second_ws.receive_json()
            while msg["type"] == "log":
                msg = second_ws.receive_json()
            assert msg["type"] in ("cancelled", "done")

        first_ws.send_json({"type": "cancel"})
        msg = first_ws.receive_json()
        while msg["type"] == "log":
            msg = first_ws.receive_json()
        assert msg["type"] in ("cancelled", "done")


def _fake_stream_process(command, cwd=None, on_start=None):
    """Replaces process_runner.stream_process for render-command tests —
    the real function unconditionally Popen()s whatever command it's
    given, which for /ws/render/run means a REAL Remotion render (a
    genuinely expensive, minutes-long subprocess tree) against a fake
    tmp_path episode with no real footage. These tests only care about
    what command ws_run_render CONSTRUCTS, not that a real render
    completes, so stub the actual process-spawning boundary instead of
    relying on a cancel message racing a real subprocess to death."""

    if on_start is not None:
        on_start(None)

    yield "__EXIT_CODE__0"


def test_ws_render_run_defaults_to_render_with_progress_js(tmp_path, monkeypatch):
    # render_episode.sh remains the documented standalone terminal tool
    # (see README.md) — the UI's own plain-video render instead calls
    # render-with-progress.js, which does the same render via Remotion's
    # Node API so it can report real __TOTAL__/__PROGRESS__ lines the way
    # export_davinci.py already does for the DaVinci path (see that
    # script's own header comment for why render_episode.sh's CLI output
    # can't be parsed reliably for this).
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr(server, "stream_process", _fake_stream_process)

    with client.websocket_connect("/ws/render/run") as ws:
        ws.send_json({"path": str(episode)})
        start_msg = ws.receive_json()

        assert start_msg["type"] == "start"
        assert "render-with-progress.js" in start_msg["command"]
        assert "render_episode.sh" not in start_msg["command"]
        assert "export_davinci.py" not in start_msg["command"]

        msg = ws.receive_json()
        while msg["type"] == "log":
            msg = ws.receive_json()
        assert msg["type"] == "done"


def test_ws_render_run_format_davinci_invokes_export_davinci(tmp_path, monkeypatch):
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr(server, "stream_process", _fake_stream_process)

    with client.websocket_connect("/ws/render/run") as ws:
        ws.send_json({"path": str(episode), "format": "davinci"})
        start_msg = ws.receive_json()

        assert start_msg["type"] == "start"
        assert "export_davinci.py" in start_msg["command"]
        assert "render_episode.sh" not in start_msg["command"]
        assert str(episode) in start_msg["command"]

        msg = ws.receive_json()
        while msg["type"] == "log":
            msg = ws.receive_json()
        assert msg["type"] == "done"


def test_ws_render_run_format_davinci_passes_resolution(tmp_path, monkeypatch):
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr(server, "stream_process", _fake_stream_process)

    with client.websocket_connect("/ws/render/run") as ws:
        ws.send_json({"path": str(episode), "format": "davinci", "resolution": "3840x2160"})
        start_msg = ws.receive_json()

        assert start_msg["type"] == "start"
        assert "3840x2160" in start_msg["command"]

        msg = ws.receive_json()
        while msg["type"] == "log":
            msg = ws.receive_json()
        assert msg["type"] == "done"


def _fake_slow_stream_process(command, cwd=None, on_start=None):
    """Blocks (via a real subprocess sleep, so it's genuinely still
    "running" from a second request's point of view) long enough for a
    test to make a second overlapping request against the same episode
    before this one finishes."""

    if on_start is not None:
        on_start(None)

    import subprocess

    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
    process.wait()

    yield "__EXIT_CODE__0"


def test_ws_render_run_records_format_and_resolution_in_render_progress(tmp_path, monkeypatch):
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr(server, "stream_process", _fake_stream_process)

    with client.websocket_connect("/ws/render/run") as ws:
        ws.send_json({"path": str(episode), "format": "davinci", "resolution": "1920x1080"})

        msg = ws.receive_json()
        while msg["type"] not in ("done", "error"):
            msg = ws.receive_json()

    # By the time "done" arrives the run has already finished and
    # _clear_render_progress removed the entry — so this test asserts on
    # the metadata WHILE the run is still in flight isn't practical with
    # the simple (non-blocking) fake; see the concurrent-rejection test
    # below for the case that actually needs a still-running run.
    assert msg["type"] == "done"


def test_ws_render_run_second_rejected_request_does_not_corrupt_the_first_runs_metadata(tmp_path, monkeypatch):
    # Regression: _set_render_metadata used to be called from inside
    # build_command BEFORE the lock was acquired — so a second request
    # for the same episode that ultimately got rejected with
    # EpisodeBusyError had still already overwritten the FIRST, still-
    # running request's format/resolution with its own, since
    # EpisodeBusyError's handler never calls _clear_render_progress to
    # undo that. Metadata must only be recorded AFTER the lock is
    # actually held by the request that's keeping it.
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr(server, "stream_process", _fake_slow_stream_process)

    with client.websocket_connect("/ws/render/run") as first_ws:
        first_ws.send_json({"path": str(episode), "format": "davinci", "resolution": "1920x1080"})

        start_msg = first_ws.receive_json()
        assert start_msg["type"] == "start"

        # first run is now holding the lock and has recorded its metadata —
        # a second, different request for the SAME episode must be
        # rejected without touching that metadata at all.
        with client.websocket_connect("/ws/render/run") as second_ws:
            second_ws.send_json({"path": str(episode), "format": "video", "resolution": "3840x2160"})
            second_msg = second_ws.receive_json()

        assert second_msg["type"] == "error"
        assert "already running" in second_msg["message"]

        with server._render_progress_guard:
            recorded = server._render_progress.get(str(episode.resolve()))

        assert recorded is not None
        assert recorded["format"] == "davinci"
        assert recorded["resolution"] == "1920x1080"

        # drain the first run to completion so the test doesn't leak a
        # background subprocess/thread past its own scope.
        msg = first_ws.receive_json()
        while msg["type"] not in ("done", "cancelled", "error"):
            msg = first_ws.receive_json()


def _fake_stream_process_with_progress(command, cwd=None, on_start=None):
    """Like _fake_stream_process, but emits export_davinci.py's __TOTAL__/
    __PROGRESS__ sentinel lines (#65's sibling render-console request) so
    _stream_command's translation of them into structured total/progress
    websocket messages can be tested without a real render."""

    if on_start is not None:
        on_start(None)

    yield "__TOTAL__2"
    yield "Rendering presenter-scene-001.mov (frames 0-99)..."
    yield "__PROGRESS__1/2"
    yield "Rendering title-scene-title-002.mov (frames 100-159)..."
    yield "__PROGRESS__2/2"
    yield "__EXIT_CODE__0"


def test_ws_render_run_translates_total_and_progress_sentinel_lines(tmp_path, monkeypatch):
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr(server, "stream_process", _fake_stream_process_with_progress)

    with client.websocket_connect("/ws/render/run") as ws:
        ws.send_json({"path": str(episode), "format": "davinci"})

        start_msg = ws.receive_json()
        assert start_msg["type"] == "start"

        total_msg = ws.receive_json()
        assert total_msg == {"type": "total", "count": 2}

        log_msg = ws.receive_json()
        assert log_msg["type"] == "log"
        assert "Rendering presenter-scene-001.mov" in log_msg["line"]

        progress_msg = ws.receive_json()
        assert progress_msg == {"type": "progress", "current": 1, "total": 2}

        log_msg_2 = ws.receive_json()
        assert log_msg_2["type"] == "log"

        progress_msg_2 = ws.receive_json()
        assert progress_msg_2 == {"type": "progress", "current": 2, "total": 2}

        done_msg = ws.receive_json()
        assert done_msg["type"] == "done"


class _DisconnectingWebSocket:
    """Stands in for a real WebSocket whose connection has died partway
    through a run — a page refresh, in production, raises WebSocketDisconnect
    (or another Exception; _stream_command's _send helper is deliberately
    broad) from send_json once the underlying socket is actually gone.
    starlette.testclient.TestClient's in-memory transport does NOT
    reproduce this: its send() never raises on a "closed" test connection
    (there's no real socket for an OSError to come from — see
    starlette.websockets.WebSocket.send, which only converts OSError into
    WebSocketDisconnect), so this bug can only be regression-tested by
    calling _stream_command directly with a fake that DOES raise, bypassing
    the ASGI transport entirely rather than going through
    client.websocket_connect()."""

    def __init__(self, fail_after: int):
        self.fail_after = fail_after
        self.sent: list[dict] = []

    async def send_json(self, payload: dict):
        self.sent.append(payload)
        if len(self.sent) > self.fail_after:
            raise WebSocketDisconnect(code=1006)

    async def receive_json(self):
        # _watch_for_cancel's own receive loop — never sends a cancel in
        # this test, just needs to not resolve before the run finishes.
        await asyncio.sleep(3600)


def _fake_stream_process_two_progress_lines(command, cwd=None, on_start=None):
    if on_start is not None:
        on_start(None)
    yield "__TOTAL__2"
    yield "__PROGRESS__1/2"
    yield "__PROGRESS__2/2"
    yield "__EXIT_CODE__0"


def test_stream_command_keeps_updating_render_progress_after_a_send_failure(tmp_path, monkeypatch):
    # Regression: a page refresh kills the websocket long before the actual
    # subprocess (export_davinci.py -> npx remotion render) exits. Before
    # this fix, letting a failed send_json propagate out of
    # _stream_command's loop unwound past the `with episode_lock(...)`
    # block in _run_websocket, releasing the lock — and abandoning
    # _render_progress updates — while the real subprocess (unaffected by
    # any of this; it isn't killed) was still running. That let a second
    # render start concurrently against the same episode, and made GET
    # /api/episode/render-status lie that nothing was running (confirmed
    # live against a real DaVinci export). _send must swallow the failure
    # and let the loop keep consuming the queue (and therefore keep
    # updating _render_progress) until the process itself actually
    # finishes, not until the socket dies.
    #
    # No pytest-asyncio in this project — _stream_command is driven
    # directly via asyncio.run() rather than an `async def test_`, which
    # plain pytest would otherwise silently skip without ever actually
    # awaiting it (a false-positive pass, not a real regression guard).
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr(server, "stream_process", _fake_stream_process_two_progress_lines)

    # fail_after=2: "start" and "total" succeed, then every send starting
    # with the first "progress" message raises — simulating the socket
    # dying right after the client has seen the total but before any
    # per-clip progress arrives, same shape as the live bug.
    ws = _DisconnectingWebSocket(fail_after=2)

    try:
        asyncio.run(server._stream_command(ws, ["fake-command"], episode))

        # The loop must have run to completion despite every send after the
        # 2nd one failing — _render_progress reflects the LAST line the fake
        # subprocess produced (2/2), not wherever it was when sends started
        # failing (1/2), proving the loop kept consuming the queue throughout.
        assert server._render_progress.get(str(episode)) == {"current": 2, "total": 2}
    finally:
        server._clear_render_progress(episode)


def test_ws_render_run_rejects_invalid_resolution_for_davinci_format(tmp_path):
    episode = tmp_path / "episode"
    episode.mkdir()

    with client.websocket_connect("/ws/render/run") as ws:
        ws.send_json({"path": str(episode), "format": "davinci", "resolution": "not-a-resolution"})
        msg = ws.receive_json()

    assert msg["type"] == "error"
    assert "not-a-resolution" in msg["message"]
