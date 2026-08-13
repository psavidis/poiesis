import json

import pytest
from fastapi.testclient import TestClient

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
