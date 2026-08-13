import json

from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def _make_episode(tmp_path):
    episode = tmp_path / "My Episode"
    processing = episode / "processing"
    processing.mkdir(parents=True)
    (processing / "manifest.json").write_text("{}")
    return episode


def test_episode_status_returns_404_for_missing_folder(tmp_path):
    response = client.get(
        "/api/episode/status", params={"path": str(tmp_path / "does-not-exist")}
    )
    assert response.status_code == 404


def test_episode_status_returns_stage_info(tmp_path):
    episode = _make_episode(tmp_path)

    response = client.get("/api/episode/status", params={"path": str(episode)})

    assert response.status_code == 200
    body = response.json()
    assert body["episode"] == "My Episode"
    assert any(s["id"] == "prepare" and s["complete"] for s in body["stages"])


def test_episode_artifact_rejects_unknown_filename(tmp_path):
    episode = _make_episode(tmp_path)

    response = client.get(
        "/api/episode/artifact",
        params={"path": str(episode), "name": "../../etc/passwd"},
    )

    assert response.status_code == 400


def test_episode_artifact_returns_404_when_not_produced(tmp_path):
    episode = _make_episode(tmp_path)

    response = client.get(
        "/api/episode/artifact",
        params={"path": str(episode), "name": "title_scenes.json"},
    )

    assert response.status_code == 404


def test_episode_artifact_returns_parsed_json(tmp_path):
    episode = _make_episode(tmp_path)
    (episode / "processing" / "title_scenes.json").write_text(
        json.dumps({"titles": [{"videoId": "001", "text": "Hello"}]})
    )

    response = client.get(
        "/api/episode/artifact",
        params={"path": str(episode), "name": "title_scenes.json"},
    )

    assert response.status_code == 200
    assert response.json()["titles"][0]["text"] == "Hello"
