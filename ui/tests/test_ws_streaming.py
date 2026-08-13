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
