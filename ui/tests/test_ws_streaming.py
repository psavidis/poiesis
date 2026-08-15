import json
import sys

import pytest
from fastapi.testclient import TestClient

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


def test_ws_render_run_defaults_to_render_episode_sh(tmp_path, monkeypatch):
    episode = tmp_path / "episode"
    episode.mkdir()

    monkeypatch.setattr(server, "stream_process", _fake_stream_process)

    with client.websocket_connect("/ws/render/run") as ws:
        ws.send_json({"path": str(episode)})
        start_msg = ws.receive_json()

        assert start_msg["type"] == "start"
        assert "render_episode.sh" in start_msg["command"]
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


def test_ws_render_run_rejects_invalid_resolution_for_davinci_format(tmp_path):
    episode = tmp_path / "episode"
    episode.mkdir()

    with client.websocket_connect("/ws/render/run") as ws:
        ws.send_json({"path": str(episode), "format": "davinci", "resolution": "not-a-resolution"})
        msg = ws.receive_json()

    assert msg["type"] == "error"
    assert "not-a-resolution" in msg["message"]
