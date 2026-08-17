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
            "effects": {"captions": True, "transition": "none"},
        }
        for i, vid in enumerate(video_ids)
    ]
    scene_plan = {"fps": 30, "scenes": scenes}
    (episode / "processing" / "scene-plan.json").write_text(json.dumps(scene_plan))
    return scene_plan


def _make_title_scene_fixtures(episode, video_ids=("001", "002")):
    """merge_title_scenes now resolves a title's segmentId via the whole-
    episode transcript + manifest, so any test exercising the title-scenes
    endpoint needs both on disk — mirrors how the real pipeline always has
    both available by the time title editing is possible (merge_segments
    runs before analyze_scenes, and generate_title_scenes itself requires
    both to have already produced its first title_scenes.json)."""
    manifest = {"videos": [{"id": vid, "filename": f"{vid}.mp4"} for vid in video_ids]}
    (episode / "processing" / "manifest.json").write_text(json.dumps(manifest))

    episode_transcript = {
        "segments": [
            {"source": f"{vid}.mp4", "start": 0.0, "end": 2.0, "text": f"segment for {vid}"}
            for vid in video_ids
        ]
    }
    (episode / "processing" / "episode_transcript.json").write_text(json.dumps(episode_transcript))


def test_update_title_scenes_returns_404_without_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)

    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"segmentId": "s0", "text": "Hello"}]},
    )

    assert response.status_code == 404


def test_update_title_scenes_writes_titles_file_and_merges_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    _make_title_scene_fixtures(episode)

    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"segmentId": "s0", "text": "Edited Title"}]},
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
    _make_title_scene_fixtures(episode)

    client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"segmentId": "s0", "text": "Keep me"}]},
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


def test_update_title_scenes_marks_changed_field_as_overridden(tmp_path):
    # #59 — mirrors #57/#58's provenance coverage, but matched by
    # segmentId (a title's real stable id) rather than array position.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    _make_title_scene_fixtures(episode)
    (episode / "processing" / "title_scenes.json").write_text(
        json.dumps({"titles": [{"segmentId": "s0", "text": "AI proposed this"}]})
    )

    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"segmentId": "s0", "text": "Human edited this"}]},
    )

    assert response.status_code == 200
    assert response.json()["titles"][0]["overriddenFields"] == ["text"]

    titles_on_disk = json.loads((episode / "processing" / "title_scenes.json").read_text())
    assert titles_on_disk["titles"][0]["overriddenFields"] == ["text"]


def test_update_title_scenes_unchanged_resave_does_not_add_spurious_overrides(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    _make_title_scene_fixtures(episode)
    (episode / "processing" / "title_scenes.json").write_text(
        json.dumps({"titles": [{"segmentId": "s0", "text": "AI proposed this"}]})
    )

    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"segmentId": "s0", "text": "AI proposed this"}]},
    )

    assert response.status_code == 200
    assert response.json()["titles"][0]["overriddenFields"] == []


def test_update_title_scenes_reset_to_automatic_clears_a_prior_override(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    _make_title_scene_fixtures(episode)
    (episode / "processing" / "title_scenes.json").write_text(
        json.dumps({"titles": [{"segmentId": "s0", "text": "edited", "overriddenFields": ["text"]}]})
    )

    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"segmentId": "s0", "text": "edited", "overriddenFields": []}]},
    )

    assert response.status_code == 200
    assert response.json()["titles"][0]["overriddenFields"] == []

    titles_on_disk = json.loads((episode / "processing" / "title_scenes.json").read_text())
    assert titles_on_disk["titles"][0]["overriddenFields"] == []


def test_update_title_scenes_matches_prior_state_by_segment_id_not_position(tmp_path):
    # Unlike moments/beats, a title's identity is segmentId, not array
    # position — reordering the payload must not lose or misattribute an
    # override.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    _make_title_scene_fixtures(episode)
    (episode / "processing" / "title_scenes.json").write_text(
        json.dumps(
            {
                "titles": [
                    {"segmentId": "s0", "text": "first, overridden", "overriddenFields": ["text"]},
                    {"segmentId": "s1", "text": "second, still automatic"},
                ]
            }
        )
    )

    # Payload arrives in the OPPOSITE order from what's on disk.
    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={
            "titles": [
                {"segmentId": "s1", "text": "second, still automatic"},
                {"segmentId": "s0", "text": "first, overridden", "overriddenFields": ["text"]},
            ]
        },
    )

    assert response.status_code == 200
    by_segment = {t["segmentId"]: t for t in response.json()["titles"]}
    assert by_segment["s0"]["overriddenFields"] == ["text"]
    assert by_segment["s1"]["overriddenFields"] == []


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


def _side_terms_payload(**overrides):
    payload = {
        "windowId": "w3",
        "sceneId": "scene-001",
        "videoId": "001",
        "offsetInParentFrames": 30,
        "maxDurationInParentFrames": 180,
        "treatment": "side-terms",
        "presenterSide": "left",
        "terms": [
            {"text": "Value Objects", "level": "muted"},
            {"text": "Aggregates", "level": "primary"},
        ],
        "reason": "names the related DDD building blocks together",
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


def test_update_moments_marks_changed_field_as_overridden(tmp_path):
    # #57 — a save that actually changes a field's value from what's on
    # disk records that field name in overriddenFields, so a later --force
    # regeneration knows not to clobber it.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    (episode / "processing" / "moments.json").write_text(
        json.dumps({"moments": [_bottom_callout_payload(text="AI proposed this")]})
    )

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_bottom_callout_payload(text="Human edited this")]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["moments"][0]["overriddenFields"] == ["text"]

    moments_on_disk = json.loads((episode / "processing" / "moments.json").read_text())
    assert moments_on_disk["moments"][0]["overriddenFields"] == ["text"]


def test_update_moments_unchanged_resave_does_not_add_spurious_overrides(tmp_path):
    # A save that round-trips the SAME values (e.g. clicking Save without
    # editing anything) must not mark fields as overridden — only an
    # actual value change should.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    (episode / "processing" / "moments.json").write_text(
        json.dumps({"moments": [_bottom_callout_payload(text="AI proposed this")]})
    )

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_bottom_callout_payload(text="AI proposed this")]},
    )

    assert response.status_code == 200
    assert response.json()["moments"][0]["overriddenFields"] == []


def test_update_moments_preserves_prior_overrides_across_an_unrelated_save(tmp_path):
    # A field overridden in an earlier save stays overridden even when a
    # LATER save only changes some other field.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    (episode / "processing" / "moments.json").write_text(
        json.dumps({"moments": [_bottom_callout_payload(text="edited earlier", overriddenFields=["text"])]})
    )

    # A real client (MomentBar's drag commit, MomentEditorPanel's save)
    # always round-trips the full fetched moment — including whatever
    # overriddenFields it already had — before patching only the field(s)
    # it actually changed, same as this payload does.
    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={
            "moments": [
                _bottom_callout_payload(text="edited earlier", offsetInParentFrames=99, overriddenFields=["text"])
            ]
        },
    )

    assert response.status_code == 200
    assert set(response.json()["moments"][0]["overriddenFields"]) == {"text", "offsetInParentFrames"}


def test_update_moments_reset_to_automatic_clears_a_prior_override(tmp_path):
    # #57's "Reset to Automatic" affordance sends the SAME value back but
    # with the field removed from overriddenFields — this must actually
    # clear it (a value-unchanged diff must not silently re-add it from
    # the old on-disk state, which was this feature's first, broken
    # implementation — a reset that could never take effect).
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    (episode / "processing" / "moments.json").write_text(
        json.dumps(
            {"moments": [_bottom_callout_payload(offsetInParentFrames=99, overriddenFields=["offsetInParentFrames"])]}
        )
    )

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_bottom_callout_payload(offsetInParentFrames=99, overriddenFields=[])]},
    )

    assert response.status_code == 200
    assert response.json()["moments"][0]["overriddenFields"] == []

    moments_on_disk = json.loads((episode / "processing" / "moments.json").read_text())
    assert moments_on_disk["moments"][0]["overriddenFields"] == []


def test_update_moments_round_trips_edited_side_terms(tmp_path):
    # Regression for #22: MomentProposal used to be missing the `terms`
    # field entirely, so any save through this endpoint on a side-terms
    # moment (even an edit to some other field on the same payload) would
    # silently drop its terms array — pydantic parses only fields the model
    # declares, so an undeclared `terms` key on the request body never
    # reaches model_dump() at all.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    edited_terms = [
        {"text": "Value Objects", "level": "muted"},
        {"text": "Aggregates", "level": "accent"},  # changed from "primary"
        {"text": "Entities", "level": "primary"},  # newly added term
    ]

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_side_terms_payload(terms=edited_terms)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["moments"][0]["terms"] == edited_terms

    moments_on_disk = json.loads(
        (episode / "processing" / "moments.json").read_text()
    )
    assert moments_on_disk["moments"][0]["terms"] == edited_terms

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    moment_scene = next(s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment")
    assert moment_scene["terms"] == edited_terms
    assert "presenterSide" not in moment_scene or moment_scene["presenterSide"] == "left"


def test_update_moments_round_trips_edited_side_text_style(tmp_path):
    # Same gap as above, for sideTextStyle on a side-text moment.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    payload = {
        "windowId": "w4",
        "sceneId": "scene-001",
        "videoId": "001",
        "offsetInParentFrames": 40,
        "maxDurationInParentFrames": 150,
        "treatment": "side-text",
        "presenterSide": "right",
        "text": "Introducing the pattern",
        "sideTextStyle": "title",
        "reason": "announces a new concept",
    }

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [payload]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["moments"][0]["sideTextStyle"] == "title"

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    moment_scene = next(s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment")
    assert moment_scene["sideTextStyle"] == "title"


def test_update_moments_does_not_attach_unrelated_fields_to_bottom_callout(tmp_path):
    # Regression: MomentProposal.model_dump() always includes every
    # optional field (assetId, codeAssetId, diagram) with a None default,
    # regardless of the payload's actual treatment. merge_moment_scenes
    # must not mistake "key present with value None" for "field genuinely
    # set" — a bottom-callout saved through this endpoint should never end
    # up with assetId/codeAssetId/diagram keys on its moment scene at all.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_bottom_callout_payload()]},
    )

    assert response.status_code == 200

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    moment_scene = next(s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment")

    assert "assetId" not in moment_scene
    assert "codeAssetId" not in moment_scene
    assert "diagram" not in moment_scene


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


def test_update_moments_stores_entrance_for_bottom_callout(tmp_path):
    # entrance (docs/specs/ai-assisted-editing-and-conversational-control.md
    # section 7) must round-trip through a save, not be silently stripped
    # by MomentProposal's own field allowlist.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_bottom_callout_payload(entrance="slide")]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["moments"][0]["entrance"] == "slide"

    moments_on_disk = json.loads((episode / "processing" / "moments.json").read_text())
    assert moments_on_disk["moments"][0]["entrance"] == "slide"

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    moment_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment"]
    assert len(moment_scenes) == 1
    assert moment_scenes[0]["entrance"] == "slide"


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


def _side_code_payload(**overrides):
    payload = {
        "windowId": "w4",
        "sceneId": "scene-001",
        "videoId": "001",
        "offsetInParentFrames": 10,
        "maxDurationInParentFrames": 60,
        "treatment": "side-code",
        "presenterSide": "left",
        "codeAssetId": "kafka-consumer.java",
        "caption": "the consumer loop",
        "reason": "shows the implementation",
    }
    payload.update(overrides)
    return payload


def _side_image_moment_payload(**overrides):
    payload = {
        "windowId": "w5",
        "sceneId": "scene-001",
        "videoId": "001",
        "offsetInParentFrames": 10,
        "maxDurationInParentFrames": 60,
        "treatment": "side-image",
        "presenterSide": "left",
        "assetId": "diagram-1.png",
        "caption": "the architecture",
        "reason": "shows the architecture",
    }
    payload.update(overrides)
    return payload


# PUT /api/episode/moment-treatment — switching an existing moment among
# the treatments that present the same content at different prominence
# (see docs/specs/content-types-and-presentation-editing.md).
def test_update_moment_treatment_switches_side_code_to_full_visual(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_side_code_payload()]},
    )

    response = client.put(
        "/api/episode/moment-treatment",
        params={"path": str(episode)},
        json={"sceneId": "scene-moment-0", "newTreatment": "full-visual"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["moments"][0]["treatment"] == "full-visual"
    assert body["moments"][0]["fullVisualKind"] == "code"
    assert body["moments"][0]["presenterSide"] is None
    # content preserved
    assert body["moments"][0]["codeAssetId"] == "kafka-consumer.java"
    assert body["moments"][0]["caption"] == "the consumer loop"

    moments_on_disk = json.loads((episode / "processing" / "moments.json").read_text())
    assert moments_on_disk["moments"][0]["treatment"] == "full-visual"

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    moment_scene = next(s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment")
    assert moment_scene["treatment"] == "full-visual"


def test_update_moment_treatment_records_provenance_override(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_side_code_payload()]},
    )

    response = client.put(
        "/api/episode/moment-treatment",
        params={"path": str(episode)},
        json={"sceneId": "scene-moment-0", "newTreatment": "content-dominant-code"},
    )

    assert response.status_code == 200
    overridden = response.json()["moments"][0]["overriddenFields"]
    assert "treatment" in overridden
    assert "maxDurationInParentFrames" in overridden


def test_update_moment_treatment_switches_side_image_to_full_visual(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_side_image_moment_payload()]},
    )

    response = client.put(
        "/api/episode/moment-treatment",
        params={"path": str(episode)},
        json={"sceneId": "scene-moment-0", "newTreatment": "full-visual"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["moments"][0]["treatment"] == "full-visual"
    assert body["moments"][0]["fullVisualKind"] == "image"
    assert body["moments"][0]["presenterSide"] is None
    assert body["moments"][0]["assetId"] == "diagram-1.png"


def test_update_moment_treatment_switches_full_visual_image_back_to_side_image(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_side_image_moment_payload()]},
    )
    client.put(
        "/api/episode/moment-treatment",
        params={"path": str(episode)},
        json={"sceneId": "scene-moment-0", "newTreatment": "full-visual"},
    )

    response = client.put(
        "/api/episode/moment-treatment",
        params={"path": str(episode)},
        json={"sceneId": "scene-moment-0", "newTreatment": "side-image"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["moments"][0]["treatment"] == "side-image"
    assert body["moments"][0]["fullVisualKind"] is None
    assert body["moments"][0]["assetId"] == "diagram-1.png"


def test_update_moment_treatment_rejects_target_outside_switchable_treatments(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_side_code_payload()]},
    )

    response = client.put(
        "/api/episode/moment-treatment",
        params={"path": str(episode)},
        json={"sceneId": "scene-moment-0", "newTreatment": "bottom-callout"},
    )

    assert response.status_code == 422


def test_update_moment_treatment_rejects_source_outside_switchable_treatments(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_bottom_callout_payload()]},
    )

    response = client.put(
        "/api/episode/moment-treatment",
        params={"path": str(episode)},
        json={"sceneId": "scene-moment-0", "newTreatment": "full-visual"},
    )

    assert response.status_code == 422


def test_update_moment_treatment_rejects_cross_content_type_switch(tmp_path):
    # An image moment can become full-visual, but never side-code — see
    # switch_moment_treatment's own docstring in generate_moments.py.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_side_image_moment_payload()]},
    )

    response = client.put(
        "/api/episode/moment-treatment",
        params={"path": str(episode)},
        json={"sceneId": "scene-moment-0", "newTreatment": "side-code"},
    )

    assert response.status_code == 422


def test_update_moment_treatment_returns_404_for_unknown_moment_index(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    response = client.put(
        "/api/episode/moment-treatment",
        params={"path": str(episode)},
        json={"sceneId": "scene-moment-99", "newTreatment": "full-visual"},
    )

    assert response.status_code == 404


def test_update_moment_treatment_returns_422_for_non_moment_scene_id(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    response = client.put(
        "/api/episode/moment-treatment",
        params={"path": str(episode)},
        json={"sceneId": "scene-001", "newTreatment": "full-visual"},
    )

    assert response.status_code == 422


def _beat_payload(**overrides):
    payload = {
        "sceneId": "scene-001",
        "kind": "word-pop",
        "text": "dependency injection",
        "icon": None,
        "offsetInParentFrames": 10,
        "durationInFrames": 60,
        "reason": "key term",
    }
    payload.update(overrides)
    return payload


def test_update_beats_returns_404_without_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)

    response = client.put(
        "/api/episode/beats",
        params={"path": str(episode)},
        json={"beats": [_beat_payload()]},
    )

    assert response.status_code == 404


def test_update_beats_writes_file_and_merges_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    response = client.put(
        "/api/episode/beats",
        params={"path": str(episode)},
        json={"beats": [_beat_payload(durationInFrames=75)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["beats"][0]["durationInFrames"] == 75

    beats_on_disk = json.loads((episode / "processing" / "emphasis.json").read_text())
    assert beats_on_disk["beats"][0]["durationInFrames"] == 75

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    beat_scene = next(s for s in scene_plan_on_disk["scenes"] if s["type"] == "beat")
    assert beat_scene["durationInFrames"] == 75


def test_update_beats_clamps_duration_that_overflows_parent_scene(tmp_path):
    episode = _make_episode(tmp_path)
    scene_plan = _make_scene_plan(episode)  # scene-001 has durationInFrames=100

    response = client.put(
        "/api/episode/beats",
        params={"path": str(episode)},
        json={"beats": [_beat_payload(offsetInParentFrames=90, durationInFrames=60)]},
    )

    assert response.status_code == 200

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    beat_scene = next(s for s in scene_plan_on_disk["scenes"] if s["type"] == "beat")
    parent = next(s for s in scene_plan["scenes"] if s["id"] == "scene-001")
    assert beat_scene["durationInFrames"] == parent["durationInFrames"] - 90


def test_update_beats_can_remove_beats_by_omitting_them(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    client.put(
        "/api/episode/beats",
        params={"path": str(episode)},
        json={"beats": [_beat_payload()]},
    )

    response = client.put(
        "/api/episode/beats",
        params={"path": str(episode)},
        json={"beats": []},
    )

    assert response.status_code == 200

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    beat_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "beat"]
    assert beat_scenes == []


def test_update_beats_marks_changed_field_as_overridden(tmp_path):
    # #58 — mirrors #57's moments coverage: a save that actually changes a
    # field's value from what's on disk records that field name in
    # overriddenFields, so a later --force regeneration knows not to
    # clobber it.
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    (episode / "processing" / "emphasis.json").write_text(
        json.dumps({"beats": [_beat_payload(text="AI proposed this")]})
    )

    response = client.put(
        "/api/episode/beats",
        params={"path": str(episode)},
        json={"beats": [_beat_payload(text="Human edited this")]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["beats"][0]["overriddenFields"] == ["text"]

    beats_on_disk = json.loads((episode / "processing" / "emphasis.json").read_text())
    assert beats_on_disk["beats"][0]["overriddenFields"] == ["text"]


def test_update_beats_unchanged_resave_does_not_add_spurious_overrides(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    (episode / "processing" / "emphasis.json").write_text(
        json.dumps({"beats": [_beat_payload(text="AI proposed this")]})
    )

    response = client.put(
        "/api/episode/beats",
        params={"path": str(episode)},
        json={"beats": [_beat_payload(text="AI proposed this")]},
    )

    assert response.status_code == 200
    assert response.json()["beats"][0]["overriddenFields"] == []


def test_update_beats_preserves_prior_overrides_across_an_unrelated_save(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    (episode / "processing" / "emphasis.json").write_text(
        json.dumps({"beats": [_beat_payload(text="edited earlier", overriddenFields=["text"])]})
    )

    response = client.put(
        "/api/episode/beats",
        params={"path": str(episode)},
        json={
            "beats": [
                _beat_payload(text="edited earlier", durationInFrames=90, overriddenFields=["text"])
            ]
        },
    )

    assert response.status_code == 200
    assert set(response.json()["beats"][0]["overriddenFields"]) == {"text", "durationInFrames"}


def test_update_beats_reset_to_automatic_clears_a_prior_override(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    (episode / "processing" / "emphasis.json").write_text(
        json.dumps(
            {"beats": [_beat_payload(durationInFrames=90, overriddenFields=["durationInFrames"])]}
        )
    )

    response = client.put(
        "/api/episode/beats",
        params={"path": str(episode)},
        json={"beats": [_beat_payload(durationInFrames=90, overriddenFields=[])]},
    )

    assert response.status_code == 200
    assert response.json()["beats"][0]["overriddenFields"] == []

    beats_on_disk = json.loads((episode / "processing" / "emphasis.json").read_text())
    assert beats_on_disk["beats"][0]["overriddenFields"] == []


def _make_scene_plan_with_image(episode, video_ids=("001", "002")):
    """Same as _make_scene_plan but with an image scene overlaid on the
    first presenter scene — used by the new direct-field-update endpoint's
    tests (#46), which need a scene type that isn't a moment/beat/title
    since those already have their own dedicated endpoints."""

    scene_plan = _make_scene_plan(episode, video_ids)
    scene_plan["scenes"].append(
        {
            "id": "scene-image-0",
            "type": "image",
            "assetId": "asset-1",
            "caption": "A diagram",
            "display": "inset",
            "parentSceneId": scene_plan["scenes"][0]["id"],
            "offsetInParentFrames": 10,
            "durationInFrames": 40,
        }
    )
    (episode / "processing" / "scene-plan.json").write_text(json.dumps(scene_plan))
    return scene_plan


def test_update_scene_returns_404_without_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)

    response = client.put(
        "/api/episode/scene",
        params={"path": str(episode)},
        json={"sceneId": "scene-image-0", "fields": {"display": "full"}},
    )

    assert response.status_code == 404


def test_update_scene_rejects_unknown_scene_id(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan_with_image(episode)

    response = client.put(
        "/api/episode/scene",
        params={"path": str(episode)},
        json={"sceneId": "scene-does-not-exist", "fields": {"display": "full"}},
    )

    assert response.status_code == 422


def test_update_scene_rejects_disallowed_field(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan_with_image(episode)

    response = client.put(
        "/api/episode/scene",
        params={"path": str(episode)},
        json={"sceneId": "scene-image-0", "fields": {"parentSceneId": "scene-002"}},
    )

    assert response.status_code == 422


def test_update_scene_changes_image_display_mode(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan_with_image(episode)

    response = client.put(
        "/api/episode/scene",
        params={"path": str(episode)},
        json={"sceneId": "scene-image-0", "fields": {"display": "full"}},
    )

    assert response.status_code == 200

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    image_scene = next(s for s in scene_plan_on_disk["scenes"] if s["id"] == "scene-image-0")
    assert image_scene["display"] == "full"


def test_update_scene_moves_and_resizes_an_image_overlay(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan_with_image(episode)

    response = client.put(
        "/api/episode/scene",
        params={"path": str(episode)},
        json={
            "sceneId": "scene-image-0",
            "fields": {"offsetInParentFrames": 20, "durationInFrames": 60},
        },
    )

    assert response.status_code == 200

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    image_scene = next(s for s in scene_plan_on_disk["scenes"] if s["id"] == "scene-image-0")
    assert image_scene["offsetInParentFrames"] == 20
    assert image_scene["durationInFrames"] == 60


def test_update_scene_returns_409_when_episode_is_locked(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan_with_image(episode)

    with episode_lock(episode):
        response = client.put(
            "/api/episode/scene",
            params={"path": str(episode)},
            json={"sceneId": "scene-image-0", "fields": {"display": "full"}},
        )

    assert response.status_code == 409


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
        [],
        [],
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
    # #54 — createdSceneIds includes every applied op's own sceneId too,
    # not just created beats/moments, so a plain remove/update also
    # highlights on the relevant bar.
    assert body["createdSceneIds"] == ["scene-002"]


def test_edit_scene_plan_passes_selected_scene_id_through_to_edit_plan(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    fake_result = ({"scenes": []}, [], [], [], [], [])

    with patch("server.edit_plan", return_value=fake_result) as mock_edit_plan:
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "make this bigger", "selectedSceneId": "scene-002"},
        )

    assert response.status_code == 200
    mock_edit_plan.assert_called_once()
    assert mock_edit_plan.call_args.kwargs["selected_scene_id"] == "scene-002"


def test_edit_scene_plan_defaults_selected_scene_id_to_none(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    fake_result = ({"scenes": []}, [], [], [], [], [])

    with patch("server.edit_plan", return_value=fake_result) as mock_edit_plan:
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "remove the second clip"},
        )

    assert response.status_code == 200
    assert mock_edit_plan.call_args.kwargs["selected_scene_id"] is None


def test_edit_scene_plan_removes_moment_from_moments_json(tmp_path):
    # Regression for #33: edit_plan.py only ever writes scene-plan.json, so
    # a chat-removed moment used to stay in moments.json — a later
    # structured-editor save (which rewrites moments.json from scratch and
    # re-merges via merge_moment_scenes) would silently resurrect it. The
    # scene-plan.json fed to server.edit_plan (mocked here, same as
    # test_edit_scene_plan_applies_validated_operations) must itself
    # contain the moment scene being removed — that's where
    # _sync_removed_moments reads which moments.json index to drop from.
    episode = _make_episode(tmp_path)
    base_scene_plan = _make_scene_plan(episode)

    (episode / "processing" / "moments.json").write_text(
        json.dumps({"moments": [_bottom_callout_payload(), _side_image_payload()]})
    )

    moment_scenes = [
        {
            "id": "scene-moment-0",
            "type": "moment",
            "treatment": "bottom-callout",
            "parentSceneId": "scene-001",
            "offsetInParentFrames": 10,
            "durationInFrames": 90,
        },
        {
            "id": "scene-moment-1",
            "type": "moment",
            "treatment": "side-image",
            "parentSceneId": "scene-001",
            "offsetInParentFrames": 20,
            "durationInFrames": 120,
        },
    ]
    scene_plan_before = {
        **base_scene_plan,
        "scenes": base_scene_plan["scenes"] + moment_scenes,
    }
    (episode / "processing" / "scene-plan.json").write_text(json.dumps(scene_plan_before))

    fake_result = (
        {
            "fps": 30,
            "scenes": [s for s in scene_plan_before["scenes"] if s["id"] != "scene-moment-0"],
        },
        [{"op": "remove", "sceneId": "scene-moment-0", "reason": "instruction said to remove it"}],
        [],
        [],
        [],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result):
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "remove the bottom callout"},
        )

    assert response.status_code == 200

    moments_on_disk = json.loads((episode / "processing" / "moments.json").read_text())
    assert len(moments_on_disk["moments"]) == 1
    assert moments_on_disk["moments"][0]["treatment"] == "side-image"

    # The resurrection check: saving through update_moments now (as
    # MomentEditorPanel would on any "Save changes" click) must not bring
    # scene-moment-0 back, since moments.json no longer has it.
    save_response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": moments_on_disk["moments"]},
    )
    assert save_response.status_code == 200

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    moment_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment"]
    assert len(moment_scenes) == 1
    assert moment_scenes[0]["treatment"] == "side-image"


def _make_word_level_transcript_fixtures(episode, video_ids=("001",)):
    """Like _make_title_scene_fixtures, but with word-level timing data —
    needed for #52's beat-creation grounding (build_candidate_words reads
    each segment's "words" array)."""
    manifest = {"videos": [{"id": vid, "filename": f"{vid}.mp4"} for vid in video_ids]}
    (episode / "processing" / "manifest.json").write_text(json.dumps(manifest))

    episode_transcript = {
        "segments": [
            {
                "source": f"{vid}.mp4",
                "start": 0.0,
                "end": 2.0,
                "text": "dependency injection matters",
                "words": [
                    {"word": "dependency", "start": 0.0, "end": 0.5},
                    {"word": "injection", "start": 0.5, "end": 1.0},
                    {"word": "matters", "start": 1.0, "end": 1.5},
                ],
            }
            for vid in video_ids
        ]
    }
    (episode / "processing" / "episode_transcript.json").write_text(json.dumps(episode_transcript))


def test_edit_scene_plan_creates_a_beat_in_emphasis_json_and_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)
    scene_plan_before = _make_scene_plan(episode, video_ids=("001",))
    _make_word_level_transcript_fixtures(episode, video_ids=("001",))

    fake_result = (
        scene_plan_before,
        [],
        [],
        [
            {
                "sceneId": "scene-001",
                "kind": "word-pop",
                "text": "injection",
                "icon": None,
                "offsetInParentFrames": 15,
                "durationInFrames": 60,
                "reason": "the key term",
            }
        ],
        [],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result) as mock_edit_plan:
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "pop the word injection"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["created"]) == 1
    assert body["created"][0]["text"] == "injection"

    # edit_plan() was called WITH the transcript/manifest it needs to
    # ground a beat — confirms the endpoint actually loaded and passed
    # them through, not just that the mocked return value round-trips.
    assert mock_edit_plan.call_args.kwargs["transcript"] is not None
    assert mock_edit_plan.call_args.kwargs["manifest"] is not None

    beats_on_disk = json.loads((episode / "processing" / "emphasis.json").read_text())
    assert len(beats_on_disk["beats"]) == 1
    assert beats_on_disk["beats"][0]["text"] == "injection"

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    beat_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "beat"]
    assert len(beat_scenes) == 1
    assert beat_scenes[0]["text"] == "injection"

    # #54 — the response names the beat's own resolved id (scene-beat-0,
    # the first beat in an initially-empty emphasis.json), not the parent
    # scene-001 the fake_result's "sceneId" field actually means.
    assert body["createdSceneIds"] == [beat_scenes[0]["id"]]
    assert beat_scenes[0]["id"] == "scene-beat-0"


def test_edit_scene_plan_appends_created_beat_to_existing_beats(tmp_path):
    episode = _make_episode(tmp_path)
    scene_plan_before = _make_scene_plan(episode, video_ids=("001",))
    _make_word_level_transcript_fixtures(episode, video_ids=("001",))

    existing_beat = {
        "sceneId": "scene-001",
        "kind": "underline",
        "text": "dependency",
        "icon": None,
        "offsetInParentFrames": 0,
        "durationInFrames": 60,
        "reason": "already there",
    }
    (episode / "processing" / "emphasis.json").write_text(json.dumps({"beats": [existing_beat]}))

    fake_result = (
        scene_plan_before,
        [],
        [],
        [
            {
                "sceneId": "scene-001",
                "kind": "word-pop",
                "text": "matters",
                "icon": None,
                "offsetInParentFrames": 30,
                "durationInFrames": 60,
                "reason": "new one",
            }
        ],
        [],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result):
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "pop the word matters too"},
        )

    assert response.status_code == 200

    beats_on_disk = json.loads((episode / "processing" / "emphasis.json").read_text())
    texts = {b["text"] for b in beats_on_disk["beats"]}
    assert texts == {"dependency", "matters"}


def test_undo_after_edit_plan_chat_creates_beat_restores_emphasis_json(tmp_path):
    episode = _make_episode(tmp_path)
    scene_plan_before = _make_scene_plan(episode, video_ids=("001",))
    _make_word_level_transcript_fixtures(episode, video_ids=("001",))

    fake_result = (
        scene_plan_before,
        [],
        [],
        [
            {
                "sceneId": "scene-001",
                "kind": "word-pop",
                "text": "injection",
                "icon": None,
                "offsetInParentFrames": 15,
                "durationInFrames": 60,
                "reason": "the key term",
            }
        ],
        [],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result):
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "pop the word injection"},
        )
    assert response.status_code == 200
    assert (episode / "processing" / "emphasis.json").exists()

    undo_response = client.post("/api/episode/undo", params={"path": str(episode)})
    assert undo_response.status_code == 200
    assert undo_response.json()["restored"] is not None

    # emphasis.json didn't exist before the create — undo must delete it
    # again (see #50's own existed:False handling), not leave a stray file
    # a later beat save could silently build on top of.
    assert not (episode / "processing" / "emphasis.json").exists()

    scene_plan_restored = json.loads((episode / "processing" / "scene-plan.json").read_text())
    assert scene_plan_restored == scene_plan_before


def test_edit_scene_plan_creates_a_moment_in_moments_json_and_scene_plan(tmp_path):
    episode = _make_episode(tmp_path)
    scene_plan_before = _make_scene_plan(episode, video_ids=("001",))
    _make_word_level_transcript_fixtures(episode, video_ids=("001",))

    fake_result = (
        scene_plan_before,
        [],
        [],
        [],
        [
            {
                "sceneId": "scene-001",
                "videoId": "001",
                "treatment": "bottom-callout",
                "text": "dependency injection matters",
                "presenterSide": None,
                "offsetInParentFrames": 0,
                "maxDurationInParentFrames": 90,
                "reason": "the core idea",
            }
        ],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result) as mock_edit_plan:
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "add a callout saying dependency injection matters"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["createdMoments"]) == 1
    assert body["createdMoments"][0]["text"] == "dependency injection matters"

    assert mock_edit_plan.call_args.kwargs["transcript"] is not None
    assert mock_edit_plan.call_args.kwargs["manifest"] is not None

    moments_on_disk = json.loads((episode / "processing" / "moments.json").read_text())
    assert len(moments_on_disk["moments"]) == 1
    assert moments_on_disk["moments"][0]["treatment"] == "bottom-callout"

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    moment_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment"]
    assert len(moment_scenes) == 1
    assert moment_scenes[0]["text"] == "dependency injection matters"

    # #54 — resolved id (scene-moment-0), not the parent scene-001 the
    # fake_result's "sceneId" field actually means.
    assert body["createdSceneIds"] == [moment_scenes[0]["id"]]
    assert moment_scenes[0]["id"] == "scene-moment-0"


def test_edit_scene_plan_creates_an_image_scene_directly_in_scene_plan(tmp_path):
    # Image scenes have no separate source file (see #60) — unlike beats/
    # moments, this asserts the created image lands straight in
    # scene-plan.json, not a merge from some images.json that doesn't
    # exist.
    episode = _make_episode(tmp_path)
    scene_plan_before = _make_scene_plan(episode, video_ids=("001",))
    (episode / "processing" / "assets.json").write_text(
        json.dumps({"assets": [{"id": "asset-1", "caption": "the architecture diagram"}]})
    )

    fake_result = (
        scene_plan_before,
        [],
        [],
        [],
        [],
        [
            {
                "type": "image",
                "assetId": "asset-1",
                "caption": "the architecture diagram",
                "display": "inset",
                "parentSceneId": "scene-001",
                "offsetInParentFrames": 0,
                "durationInFrames": 150,
            }
        ],
    )

    with patch("server.edit_plan", return_value=fake_result) as mock_edit_plan:
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "show the architecture diagram in the corner"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["createdImages"]) == 1
    assert body["createdImages"][0]["assetId"] == "asset-1"

    assert mock_edit_plan.call_args.kwargs["assets"] == [{"id": "asset-1", "caption": "the architecture diagram"}]

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    image_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "image"]
    assert len(image_scenes) == 1
    assert image_scenes[0]["assetId"] == "asset-1"
    assert image_scenes[0]["display"] == "inset"
    assert image_scenes[0]["id"] == "scene-image-0"

    assert body["createdSceneIds"] == ["scene-image-0"]


def test_edit_scene_plan_creates_a_full_screen_diagram_moment(tmp_path):
    # A diagram-created moment (resolve_full_screen_diagram_creation) feeds
    # into the SAME created_moments list/write path as a bottom-callout —
    # this exercises that shape end to end rather than assuming it, since
    # the field shape differs (diagram/fullVisualKind instead of text).
    episode = _make_episode(tmp_path)
    scene_plan_before = _make_scene_plan(episode, video_ids=("001",))
    _make_word_level_transcript_fixtures(episode, video_ids=("001",))

    fake_result = (
        scene_plan_before,
        [],
        [],
        [],
        [
            {
                "sceneId": "scene-001",
                "videoId": "001",
                "treatment": "full-visual",
                "fullVisualKind": "diagram",
                "diagram": {
                    "nodes": [{"id": "a", "label": "Producer"}, {"id": "b", "label": "Kafka"}],
                    "edges": [{"from": "a", "to": "b"}],
                    "layout": "horizontal",
                },
                "presenterSide": None,
                "offsetInParentFrames": 0,
                "maxDurationInParentFrames": 300,
                "reason": "explains the flow",
            }
        ],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result):
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "create a full screen diagram of the producer talking to kafka"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["createdMoments"]) == 1
    assert body["createdMoments"][0]["treatment"] == "full-visual"
    assert body["createdMoments"][0]["fullVisualKind"] == "diagram"

    moments_on_disk = json.loads((episode / "processing" / "moments.json").read_text())
    assert moments_on_disk["moments"][0]["treatment"] == "full-visual"
    assert moments_on_disk["moments"][0]["diagram"]["nodes"][0]["label"] == "Producer"

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    moment_scenes = [s for s in scene_plan_on_disk["scenes"] if s["type"] == "moment"]
    assert len(moment_scenes) == 1
    assert moment_scenes[0]["treatment"] == "full-visual"
    assert moment_scenes[0]["fullVisualKind"] == "diagram"


def test_edit_scene_plan_appends_created_moment_to_existing_moments(tmp_path):
    episode = _make_episode(tmp_path)
    scene_plan_before = _make_scene_plan(episode, video_ids=("001",))
    _make_word_level_transcript_fixtures(episode, video_ids=("001",))

    existing_moment = {
        "sceneId": "scene-001",
        "videoId": "001",
        "treatment": "bottom-callout",
        "text": "already here",
        "presenterSide": None,
        "offsetInParentFrames": 0,
        "maxDurationInParentFrames": 90,
        "reason": "existing",
    }
    (episode / "processing" / "moments.json").write_text(json.dumps({"moments": [existing_moment]}))

    fake_result = (
        scene_plan_before,
        [],
        [],
        [],
        [
            {
                "sceneId": "scene-001",
                "videoId": "001",
                "treatment": "bottom-callout",
                "text": "a new one",
                "presenterSide": None,
                "offsetInParentFrames": 150,
                "maxDurationInParentFrames": 90,
                "reason": "new",
            }
        ],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result):
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "add another callout"},
        )

    assert response.status_code == 200

    moments_on_disk = json.loads((episode / "processing" / "moments.json").read_text())
    texts = {m["text"] for m in moments_on_disk["moments"]}
    assert texts == {"already here", "a new one"}


def test_undo_after_edit_plan_chat_creates_moment_restores_moments_json(tmp_path):
    episode = _make_episode(tmp_path)
    scene_plan_before = _make_scene_plan(episode, video_ids=("001",))
    _make_word_level_transcript_fixtures(episode, video_ids=("001",))

    fake_result = (
        scene_plan_before,
        [],
        [],
        [],
        [
            {
                "sceneId": "scene-001",
                "videoId": "001",
                "treatment": "bottom-callout",
                "text": "dependency injection matters",
                "presenterSide": None,
                "offsetInParentFrames": 0,
                "maxDurationInParentFrames": 90,
                "reason": "the core idea",
            }
        ],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result):
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "add a callout saying dependency injection matters"},
        )
    assert response.status_code == 200
    assert (episode / "processing" / "moments.json").exists()

    undo_response = client.post("/api/episode/undo", params={"path": str(episode)})
    assert undo_response.status_code == 200
    assert undo_response.json()["restored"] is not None

    # moments.json didn't exist before the create — undo must delete it
    # again, same existed:False handling verified for emphasis.json above.
    assert not (episode / "processing" / "moments.json").exists()

    scene_plan_restored = json.loads((episode / "processing" / "scene-plan.json").read_text())
    assert scene_plan_restored == scene_plan_before


def test_edit_scene_plan_removes_title_from_title_scenes_json(tmp_path):
    # Same resurrection risk as moments, for titles — text-matched since
    # title_scenes.json entries have no id shared with the merged
    # TitleScene (see #32's known, accepted correlation limitation).
    episode = _make_episode(tmp_path)
    base_scene_plan = _make_scene_plan(episode)
    _make_title_scene_fixtures(episode)

    (episode / "processing" / "title_scenes.json").write_text(
        json.dumps({"titles": [{"segmentId": "s0", "text": "Keep me"}, {"segmentId": "s1", "text": "Remove me"}]})
    )

    title_scenes = [
        {"id": "scene-title-000", "type": "title", "text": "Keep me", "timelineStartFrame": 0, "durationInFrames": 60},
        {"id": "scene-title-001", "type": "title", "text": "Remove me", "timelineStartFrame": 60, "durationInFrames": 60},
    ]
    scene_plan_before = {
        **base_scene_plan,
        "scenes": base_scene_plan["scenes"] + title_scenes,
    }
    (episode / "processing" / "scene-plan.json").write_text(json.dumps(scene_plan_before))

    fake_result = (
        {
            "fps": 30,
            "scenes": [s for s in scene_plan_before["scenes"] if s["id"] != "scene-title-001"],
        },
        [{"op": "remove", "sceneId": "scene-title-001", "reason": "instruction said to remove it"}],
        [],
        [],
        [],
        [],
    )

    with patch("server.edit_plan", return_value=fake_result):
        response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "remove the second title card"},
        )

    assert response.status_code == 200

    titles_on_disk = json.loads((episode / "processing" / "title_scenes.json").read_text())
    assert [t["text"] for t in titles_on_disk["titles"]] == ["Keep me"]

    # The resurrection check: saving through update_title_scenes now (as
    # TitleEditorPanel would on any "Save changes" click) must not bring
    # "Remove me" back.
    save_response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": titles_on_disk["titles"]},
    )
    assert save_response.status_code == 200

    scene_plan_on_disk = json.loads((episode / "processing" / "scene-plan.json").read_text())
    title_texts = [s["text"] for s in scene_plan_on_disk["scenes"] if s["type"] == "title"]
    assert title_texts == ["Keep me"]


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
    _make_title_scene_fixtures(episode)

    with patch("server.regenerate_codegen") as mock_regen:
        response = client.put(
            "/api/episode/title-scenes",
            params={"path": str(episode)},
            json={"titles": [{"segmentId": "s0", "text": "Hello"}]},
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
        [],
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
    _make_title_scene_fixtures(episode)

    # Simulate a pipeline/render already in flight for this episode by
    # holding its lock for the duration of the request, same as
    # _run_websocket does around a real subprocess run.
    with episode_lock(episode):
        response = client.put(
            "/api/episode/title-scenes",
            params={"path": str(episode)},
            json={"titles": [{"segmentId": "s0", "text": "Hello"}]},
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
    _make_title_scene_fixtures(episode)

    with episode_lock(episode):
        blocked = client.put(
            "/api/episode/title-scenes",
            params={"path": str(episode)},
            json={"titles": [{"segmentId": "s0", "text": "Hello"}]},
        )
    assert blocked.status_code == 409

    # lock released after the `with` block — the same request now succeeds
    response = client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"segmentId": "s0", "text": "Hello"}]},
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
    _make_scene_plan(episode_b)
    _make_title_scene_fixtures(episode_b)

    with episode_lock(episode_a):
        response = client.put(
            "/api/episode/title-scenes",
            params={"path": str(episode_b)},
            json={"titles": [{"segmentId": "s0", "text": "Hello"}]},
        )

    assert response.status_code == 200


def test_undo_with_no_history_returns_none_restored(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    response = client.post("/api/episode/undo", params={"path": str(episode)})

    assert response.status_code == 200
    assert response.json() == {"restored": None}


def test_undo_restores_scene_plan_and_moments_after_a_moment_edit(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    scene_plan_before = json.loads((episode / "processing" / "scene-plan.json").read_text())
    assert not (episode / "processing" / "moments.json").exists()

    save_response = client.put(
        "/api/episode/moments",
        params={"path": str(episode)},
        json={"moments": [_bottom_callout_payload()]},
    )
    assert save_response.status_code == 200
    assert (episode / "processing" / "moments.json").exists()

    scene_plan_after = json.loads((episode / "processing" / "scene-plan.json").read_text())
    assert scene_plan_after != scene_plan_before
    assert any(s["type"] == "moment" for s in scene_plan_after["scenes"])

    undo_response = client.post("/api/episode/undo", params={"path": str(episode)})

    assert undo_response.status_code == 200
    assert undo_response.json()["restored"]["label"] == "moment edit"

    # scene-plan.json is back to its pre-edit state...
    scene_plan_restored = json.loads((episode / "processing" / "scene-plan.json").read_text())
    assert scene_plan_restored == scene_plan_before

    # ...and moments.json (which didn't exist before the edit) is gone
    # again too — restoring only scene-plan.json while leaving a stray
    # moments.json behind would let a later moment save silently
    # resurrect the undone moment (the #33 bug class this guards against).
    assert not (episode / "processing" / "moments.json").exists()


def test_undo_after_edit_plan_chat_restores_removed_title_scene(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)
    _make_title_scene_fixtures(episode)

    client.put(
        "/api/episode/title-scenes",
        params={"path": str(episode)},
        json={"titles": [{"segmentId": "s0", "text": "Original Title"}]},
    )

    title_scenes_before = json.loads((episode / "processing" / "title_scenes.json").read_text())
    scene_plan_before = json.loads((episode / "processing" / "scene-plan.json").read_text())
    assert any(s["type"] == "title" for s in scene_plan_before["scenes"])

    title_scene_id = next(s["id"] for s in scene_plan_before["scenes"] if s["type"] == "title")

    with patch("server.edit_plan") as mock_edit_plan:
        removed_plan = {
            **scene_plan_before,
            "scenes": [s for s in scene_plan_before["scenes"] if s["id"] != title_scene_id],
        }
        mock_edit_plan.return_value = (
            removed_plan,
            [{"op": "remove", "sceneId": title_scene_id, "reason": "not needed"}],
            [],
            [],
            [],
            [],
        )

        chat_response = client.post(
            "/api/episode/edit-plan",
            params={"path": str(episode)},
            json={"instruction": "remove the title card"},
        )

    assert chat_response.status_code == 200

    scene_plan_after = json.loads((episode / "processing" / "scene-plan.json").read_text())
    assert not any(s["type"] == "title" for s in scene_plan_after["scenes"])

    undo_response = client.post("/api/episode/undo", params={"path": str(episode)})

    assert undo_response.status_code == 200
    assert undo_response.json()["restored"]["label"] == "chat: remove the title card"

    scene_plan_restored = json.loads((episode / "processing" / "scene-plan.json").read_text())
    title_scenes_restored = json.loads((episode / "processing" / "title_scenes.json").read_text())

    assert scene_plan_restored == scene_plan_before
    assert title_scenes_restored == title_scenes_before


def test_undo_returns_409_when_episode_is_locked(tmp_path):
    episode = _make_episode(tmp_path)
    _make_scene_plan(episode)

    with episode_lock(episode):
        response = client.post("/api/episode/undo", params={"path": str(episode)})

    assert response.status_code == 409
