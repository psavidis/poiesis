import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import server
from episode_locks import episode_lock
from server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_real_codegen_regeneration(request):
    """Every scene-plan write endpoint calls regenerate_codegen(episode),
    which would otherwise overwrite the real
    video-renderer/generated/episode/scene-plan.ts with test fixture data
    on every test run. Auto-applied to every test in this file so no
    individual test needs to remember to mock it — except the
    test_regenerate_codegen_* tests below, which are testing that function
    itself and patch generate_scene_plan_ts (one layer deeper) instead, so
    they opt out here to avoid double-patching the thing they're testing."""

    if request.node.name.startswith("test_regenerate_codegen_"):
        yield
        return

    with patch("server.regenerate_codegen"):
        yield


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


def _bottom_callout_payload(**overrides):
    payload = {
        "windowId": "w1",
        "sceneId": "scene-001",
        "videoId": "001",
        "offsetInParentFrames": 10,
        "maxDurationInParentFrames": 90,
        "treatment": "bottom-callout",
        "presenterSide": None,
        "text": "Hello",
        "reason": "topic shift",
    }
    payload.update(overrides)
    return payload


def _side_image_payload(**overrides):
    payload = {
        "windowId": "w2",
        "sceneId": "scene-001",
        "videoId": "001",
        "offsetInParentFrames": 20,
        "maxDurationInParentFrames": 120,
        "treatment": "side-image",
        "presenterSide": "left",
        "assetId": "asset-1",
        "caption": "a diagram",
        "reason": "visual aid",
    }
    payload.update(overrides)
    return payload


def test_update_moments_returns_404_without_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_bottom_callout_payload()]},
    )

    assert response.status_code == 404


def test_update_moments_writes_file_and_merges_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={
            "moments": [_bottom_callout_payload(text="Edited emphasis", offsetInParentFrames=15)],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["moments"][0]["text"] == "Edited emphasis"

    moments_on_disk = json.loads(
        (episode / "processing" / "moments.json").read_text()
    )
    assert moments_on_disk["moments"][0]["offsetInParentFrames"] == 15

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    moment_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment"]
    assert len(moment_scenes) == 1
    assert moment_scenes[0]["text"] == "Edited emphasis"
    assert moment_scenes[0]["offsetInParentFrames"] == 15


def test_update_moments_stores_presenter_side_for_side_image(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_side_image_payload(assetId="asset-2")]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["moments"][0]["assetId"] == "asset-2"

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    moment_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment"]
    assert len(moment_scenes) == 1
    assert moment_scenes[0]["assetId"] == "asset-2"
    assert moment_scenes[0]["presenterSide"] == "left"

    parent = next(s for s in scene_plan_on_disk["scenes"] if s["id"] == "scene-001")
    assert "layout" not in parent


def test_update_moments_can_remove_scenes_by_omitting_them(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_bottom_callout_payload(), _side_image_payload()]},
    )

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": []},
    )

    assert response.status_code == 200

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    overlay_scenes = [
        s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment"
    ]
    assert overlay_scenes == []


def test_edit_scene_plan_returns_404_without_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)

    response = client.post(
        "/api/episode/edit-plan",
        params={"path": str(episode)},
        json={"instruction": "remove the title card"},
    )

    assert response.status_code == 404


def test_edit_scene_plan_applies_validated_operations(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    fake_result = (
        {"scenes": [{"id": "scene-001", "type": "presenter", "videoId": "001", "text": "unused"}]},
        [{"op": "remove", "sceneId": "scene-002", "reason": "instruction said to remove it"}],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result) as mock_edit_plan:
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "remove the second clip"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"][0]["sceneId"] == "scene-002"
    assert body["rejected"] == []
    mock_edit_plan.assert_called_once()

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    assert scene_plan_on_disk["scenes"][0]["id"] == "scene-001"


def test_edit_scene_plan_returns_502_when_llm_call_fails(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    with patch("server.edit_plan", side_effect=RuntimeError("claude CLI not found")):
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "remove the title card"},
        )

    assert response.status_code == 502


def test_update_title_scenes_regenerates_codegen(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    with patch("server.regenerate_codegen") as mock_regen:
        response = client.put(
            "/api/episode/title-scenes",
            params={"path": str(episode)},
            json={"titles": [{"videoId": "001", "text": "Hello"}]},
        )

    assert response.status_code == 200
    mock_regen.assert_called_once_with(episode)


def test_update_moments_regenerates_codegen(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    with patch("server.regenerate_codegen") as mock_regen:
        response = client.put(
            "/api/episode/moments",
            params={"path": str(episode)},
            json={"moments": [_bottom_callout_payload()]},
        )

    assert response.status_code == 200
    mock_regen.assert_called_once_with(episode)


def test_edit_scene_plan_regenerates_codegen(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    fake_result = (
        {"scenes": [{"id": "scene-001", "type": "presenter", "videoId": "001", "text": "unused"}]},
        [],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result), patch(
        "server.regenerate_codegen"
    ) as mock_regen:
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "remove the second clip"},
        )

    assert response.status_code == 200
    mock_regen.assert_called_once_with(episode)


def test_edit_scene_plan_does_not_regenerate_codegen_when_llm_call_fails(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    with patch("server.edit_plan", side_effect=RuntimeError("claude CLI not found")), patch(
        "server.regenerate_codegen"
    ) as mock_regen:
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "remove the title card"},
        )

    assert response.status_code == 502
    mock_regen.assert_not_called()


def test_regenerate_codegen_calls_generate_scene_plan_ts(tmp_path):
    episode = tmp_path / "My Episode"

    with patch("server.generate_scene_plan_ts") as mock_generate:
        server.regenerate_codegen(episode)

    mock_generate.assert_called_once_with(episode, server.RENDERER_DIR)


def test_regenerate_codegen_swallows_errors(tmp_path):
    episode = tmp_path / "My Episode"

    with patch("server.generate_scene_plan_ts", side_effect=RuntimeError("scene plan missing")):
        # must not raise — a codegen hiccup should never block the edit
        # itself from being saved, which already succeeded by this point
        server.regenerate_codegen(episode)


def test_update_title_scenes_returns_409_when_episode_is_locked(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    # Simulate a pipeline/render already in flight for this episode by
    # holding its lock for the duration of the request, same as
    # _run_websocket does around a real subprocess run.
    with episode_lock(episode):
        response = client.put(
            "/api/episode/title-scenes",
            params={"path": str(episode)},
            json={"titles": [{"videoId": "001", "text": "Hello"}]},
        )

    assert response.status_code == 409

    # scene-plan.json must be untouched — the busy episode was never
    # allowed to be written to
    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    title_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "title"]
    assert title_scenes == []


def test_update_title_scenes_succeeds_once_lock_is_released(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    with episode_lock(episode):
        blocked = client.put(
            "/api/episode/title-scenes",
            params={"path": str(episode)},
            json={"titles": [{"videoId": "001", "text": "Hello"}]},
        )
    assert blocked.status_code == 409

    # lock released after the `with` block — the same request now succeeds
    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"videoId": "001", "text": "Hello"}]},
    )
    assert response.status_code == 200


def test_update_moments_returns_409_when_episode_is_locked(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    with episode_lock(episode):
        response = client.put(
            "/api/episode/moments",
            params={"path": str(episode)},
            json={"moments": [_bottom_callout_payload()]},
        )

    assert response.status_code == 409


def test_edit_scene_plan_returns_409_when_episode_is_locked(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    with episode_lock(episode):
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "remove the title card"},
        )

    assert response.status_code == 409


def test_different_episodes_do_not_block_each_other(tmp_path):
    episode_a = _make_episode(tmp_path)
    _make_scene_plan(episode_a)

    episode_b = tmp_path / "Another Episode"
    (episode_b / "processing").mkdir(parents=True)
    (episode_b / "processing" / "manifest.json").write_text("{}")
    _make_scene_plan(episode_b)

    with episode_lock(episode_a):
        response = client.put(
            "/api/episode/title-scenes",
            params={"path": str(episode_b)},
            json={"titles": [{"videoId": "001", "text": "Hello"}]},
        )

    assert response.status_code == 200
