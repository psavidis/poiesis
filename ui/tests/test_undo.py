import json

from undo import UNDO_HISTORY_LIMIT, restore_latest, save_checkpoint, wrap_with_checkpoint


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_save_checkpoint_is_a_noop_when_none_of_the_files_exist(tmp_path):
    processing = tmp_path / "processing"
    processing.mkdir()

    save_checkpoint(processing, [processing / "scene-plan.json"], "no files yet")

    assert not (processing / ".undo").exists()


def test_restore_latest_returns_none_with_no_history(tmp_path):
    processing = tmp_path / "processing"
    processing.mkdir()

    assert restore_latest(processing) is None


def test_save_checkpoint_then_restore_latest_round_trips_a_single_file(tmp_path):
    processing = tmp_path / "processing"
    scene_plan = processing / "scene-plan.json"
    _write(scene_plan, json.dumps({"version": 1}))

    save_checkpoint(processing, [scene_plan], "moment edit")

    scene_plan.write_text(json.dumps({"version": 2}))
    assert json.loads(scene_plan.read_text())["version"] == 2

    manifest = restore_latest(processing)

    assert manifest["label"] == "moment edit"
    assert json.loads(scene_plan.read_text())["version"] == 1


def test_save_checkpoint_restores_multiple_files_together(tmp_path):
    processing = tmp_path / "processing"
    scene_plan = processing / "scene-plan.json"
    moments = processing / "moments.json"

    _write(scene_plan, json.dumps({"scenes": ["original"]}))
    _write(moments, json.dumps({"moments": ["original"]}))

    save_checkpoint(processing, [scene_plan, moments], "moment edit")

    scene_plan.write_text(json.dumps({"scenes": ["edited"]}))
    moments.write_text(json.dumps({"moments": ["edited"]}))

    manifest = restore_latest(processing)

    assert {"scene-plan.json", "moments.json"} == {f["relative"] for f in manifest["files"]}
    assert json.loads(scene_plan.read_text())["scenes"] == ["original"]
    assert json.loads(moments.read_text())["moments"] == ["original"]


def test_save_checkpoint_only_snapshots_content_for_files_that_exist(tmp_path):
    # A file that didn't exist yet (e.g. edit_scene_plan only writes
    # title_scenes.json when the instruction actually removed a title —
    # see #33's bug class) is still tracked in the manifest (existed:
    # False, no snapshot) so undo can delete it if the write goes on to
    # create it, rather than being silently dropped from the manifest
    # entirely.
    processing = tmp_path / "processing"
    scene_plan = processing / "scene-plan.json"
    _write(scene_plan, json.dumps({"scenes": []}))

    never_existed = processing / "title_scenes.json"

    save_checkpoint(processing, [scene_plan, never_existed], "edit-plan: remove title")

    manifest = restore_latest(processing)

    by_relative = {f["relative"]: f for f in manifest["files"]}
    assert by_relative["scene-plan.json"]["existed"] is True
    assert by_relative["title_scenes.json"]["existed"] is False
    assert not never_existed.exists()


def test_restore_latest_deletes_a_file_the_write_created_where_none_existed_before(tmp_path):
    # The core fix this manifest-tracking exists for: moments.json didn't
    # exist before the write, the write created it, undo must delete it
    # again — not just restore scene-plan.json and leave a stray
    # moments.json behind (which would let a later moment save silently
    # resurrect the "undone" moment).
    processing = tmp_path / "processing"
    scene_plan = processing / "scene-plan.json"
    moments = processing / "moments.json"
    _write(scene_plan, json.dumps({"scenes": []}))

    def write_fn():
        scene_plan.write_text(json.dumps({"scenes": ["a moment"]}))
        _write(moments, json.dumps({"moments": ["a moment"]}))

    wrap_with_checkpoint(processing, [scene_plan, moments], "moment edit", write_fn)

    assert moments.exists()

    restore_latest(processing)

    assert json.loads(scene_plan.read_text())["scenes"] == []
    assert not moments.exists()


def test_restore_latest_pops_only_the_most_recent_checkpoint(tmp_path):
    processing = tmp_path / "processing"
    scene_plan = processing / "scene-plan.json"

    _write(scene_plan, json.dumps({"version": 1}))
    save_checkpoint(processing, [scene_plan], "first edit")

    scene_plan.write_text(json.dumps({"version": 2}))
    save_checkpoint(processing, [scene_plan], "second edit")

    scene_plan.write_text(json.dumps({"version": 3}))

    first_undo = restore_latest(processing)
    assert first_undo["label"] == "second edit"
    assert json.loads(scene_plan.read_text())["version"] == 2

    second_undo = restore_latest(processing)
    assert second_undo["label"] == "first edit"
    assert json.loads(scene_plan.read_text())["version"] == 1

    assert restore_latest(processing) is None


def test_wrap_with_checkpoint_snapshots_before_calling_write_fn(tmp_path):
    processing = tmp_path / "processing"
    scene_plan = processing / "scene-plan.json"
    _write(scene_plan, json.dumps({"version": 1}))

    def write_fn():
        scene_plan.write_text(json.dumps({"version": 2}))
        return "write result"

    result = wrap_with_checkpoint(processing, [scene_plan], "moment edit", write_fn)

    assert result == "write result"
    assert json.loads(scene_plan.read_text())["version"] == 2

    manifest = restore_latest(processing)
    assert json.loads(scene_plan.read_text())["version"] == 1
    assert manifest["label"] == "moment edit"


def test_wrap_with_checkpoint_still_snapshots_even_if_write_fn_raises(tmp_path):
    # The checkpoint reflects the true pre-write state — if the write
    # itself fails partway, there must still be something correct to
    # restore to, not a checkpoint silently skipped because the write
    # never "succeeded."
    processing = tmp_path / "processing"
    scene_plan = processing / "scene-plan.json"
    _write(scene_plan, json.dumps({"version": 1}))

    def failing_write_fn():
        scene_plan.write_text(json.dumps({"version": "corrupted-mid-write"}))
        raise RuntimeError("simulated failure")

    try:
        wrap_with_checkpoint(processing, [scene_plan], "moment edit", failing_write_fn)
    except RuntimeError:
        pass

    manifest = restore_latest(processing)
    assert json.loads(scene_plan.read_text())["version"] == 1
    assert manifest is not None


def test_save_checkpoint_sanitizes_arbitrary_user_text_labels(tmp_path):
    # Labels can be arbitrary chat instruction text (a user could type
    # anything, including path-traversal-shaped text like "../../etc") —
    # must never be embedded directly into a filesystem directory name.
    # The full, unsanitized text should still survive in the manifest.
    processing = tmp_path / "processing"
    scene_plan = processing / "scene-plan.json"
    _write(scene_plan, json.dumps({"version": 1}))

    dangerous_label = "chat: ../../../etc/passwd; rm -rf /"
    save_checkpoint(processing, [scene_plan], dangerous_label)

    checkpoints = list((processing / ".undo").iterdir())
    assert len(checkpoints) == 1
    # The checkpoint directory landed INSIDE .undo/, not escaped via "..".
    assert checkpoints[0].parent == processing / ".undo"
    assert "/" not in checkpoints[0].name

    manifest = restore_latest(processing)
    assert manifest["label"] == dangerous_label


def test_save_checkpoint_prunes_history_past_the_limit(tmp_path):
    processing = tmp_path / "processing"
    scene_plan = processing / "scene-plan.json"
    _write(scene_plan, json.dumps({"version": 0}))

    for i in range(UNDO_HISTORY_LIMIT + 5):
        save_checkpoint(processing, [scene_plan], f"edit {i}")
        scene_plan.write_text(json.dumps({"version": i}))

    checkpoints = list((processing / ".undo").iterdir())
    assert len(checkpoints) == UNDO_HISTORY_LIMIT
