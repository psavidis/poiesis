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


def test_browse_returns_404_for_missing_folder(tmp_path):
    response = client.get("/api/browse", params={"path": str(tmp_path / "nope")})
    assert response.status_code == 404


def test_browse_lists_subdirectories_and_flags_episodes(tmp_path):
    episode = _make_episode(tmp_path)
    (tmp_path / "not-an-episode").mkdir()
    (tmp_path / ".hidden").mkdir()

    response = client.get("/api/browse", params={"path": str(tmp_path)})

    assert response.status_code == 200
    body = response.json()
    names = {e["name"] for e in body["entries"]}
    assert names == {episode.name, "not-an-episode"}

    by_name = {e["name"]: e for e in body["entries"]}
    assert by_name[episode.name]["isEpisode"] is True
    assert by_name["not-an-episode"]["isEpisode"] is False


def test_browse_reports_parent_and_self_episode_flag(tmp_path):
    episode = _make_episode(tmp_path)

    response = client.get("/api/browse", params={"path": str(episode)})

    assert response.status_code == 200
    body = response.json()
    assert body["parent"] == str(tmp_path)
    assert body["isEpisode"] is True


def _make_scene_plan(episode, video_ids=("001", "002")):
    scenes = [
        {
            "id": f"scene-{vid}",
            "type": "presenter",
            "videoId": vid,
            "sourceStartFrame": 0,
            "sourceEndFrame": 100,
            "timelineStartFrame": i * 100,
            "durationInFrames": 100,
        }
        for i, vid in enumerate(video_ids)
    ]
    scene_plan = {"scenes": scenes}
    (episode / "processing" / "scene-plan.json").write_text(json.dumps(scene_plan))
    return scene_plan


def test_update_title_scenes_returns_404_without_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)

    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"videoId": "001", "text": "Hello"}]},
    )

    assert response.status_code == 404


def test_update_title_scenes_writes_titles_file_and_merges_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"videoId": "001", "text": "Edited Title"}]},
    )

    assert response.status_code == 200
    assert response.json()["titles"][0]["text"] == "Edited Title"

    titles_on_disk = json.loads((episode / "processing" / "title_scenes.json").read_text())
    assert titles_on_disk["titles"][0]["text"] == "Edited Title"

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    title_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "title"]
    assert len(title_scenes) == 1
    assert title_scenes[0]["text"] == "Edited Title"


def test_update_title_scenes_can_remove_a_title_by_omitting_it(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"videoId": "001", "text": "Keep me"}]},
    )

    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": []},
    )

    assert response.status_code == 200

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    title_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "title"]
    assert title_scenes == []
