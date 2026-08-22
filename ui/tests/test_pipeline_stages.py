from pipeline_stages import PIPELINE_STAGES, SECONDARY_STAGES, find_stage, stage_status


def test_pipeline_stages_have_unique_ids():
    ids = [stage.id for stage in PIPELINE_STAGES]
    assert len(ids) == len(set(ids))


def test_stage_status_reports_incomplete_when_artifact_missing(tmp_path):
    episode = tmp_path / "episode"
    (episode / "processing").mkdir(parents=True)

    status = stage_status(episode)

    assert all(s["complete"] in (False, None) for s in status)


def test_stage_status_reports_complete_when_artifact_exists(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"
    processing.mkdir(parents=True)
    (processing / "manifest.json").write_text("{}")

    status = stage_status(episode)

    prepare = next(s for s in status if s["id"] == "prepare")
    assert prepare["complete"] is True


def test_stage_status_treats_directory_artifacts_correctly(tmp_path):
    episode = tmp_path / "episode"
    processing = episode / "processing"
    (processing / "transcripts").mkdir(parents=True)

    status = stage_status(episode)

    transcribe = next(s for s in status if s["id"] == "transcribe")
    assert transcribe["complete"] is True


def test_find_stage_returns_none_for_unknown_id():
    assert find_stage("does-not-exist") is None


def test_find_stage_finds_primary_and_secondary_stages():
    assert find_stage("prepare") is not None
    assert find_stage("key_footage") in SECONDARY_STAGES


def test_index_code_is_a_chained_stage_before_generate_moments():
    # index_code.py existed as a standalone script with no automatic
    # trigger — generate_moments.py already reads code_assets to propose
    # codeAssetId-grounded moments, so index_code must be chained in and
    # must run before generate_moments, or code assets are silently never
    # available to it on a fresh pipeline run.
    ids = [stage.id for stage in PIPELINE_STAGES]
    assert "index_code" in ids
    assert ids.index("index_code") < ids.index("generate_moments")


def test_build_command_appends_force_for_a_force_supporting_stage(tmp_path):
    # Regression test for #81: clicking "Re-run" on a stage whose script
    # only regenerates output when --force is passed (e.g.
    # generate_title_scenes.py's own "already proposed. Skipping.") must
    # actually append --force, not silently no-op.
    stage = find_stage("generate_title_scenes")
    command = stage.build_command(tmp_path, force=True)
    assert "--force" in command


def test_build_command_omits_force_for_a_stage_without_a_force_flag(tmp_path):
    # index_assets.py (like several other stages — see Stage.__init__'s
    # own docstring) has no --force argparse flag at all; appending it
    # anyway would make the subprocess fail with argparse's "unrecognized
    # arguments" instead of the intended re-run.
    stage = find_stage("index_assets")
    command = stage.build_command(tmp_path, force=True)
    assert "--force" not in command


def test_build_command_without_force_never_appends_it():
    stage = find_stage("generate_title_scenes")
    command = stage.build_command("/tmp/episode", force=False)
    assert "--force" not in command


def test_only_confirmed_force_incapable_stages_default_to_false():
    # Locks the exact set of stages this fix marked supports_force=False —
    # anyone adding a NEW pipeline_stages.py entry gets Stage's default
    # (supports_force=True), so a script that genuinely has no --force flag
    # must opt out explicitly, and this test catches it if that opt-out is
    # missing (the stage's "Re-run" button would otherwise pass --force
    # into an argparse error).
    no_force_ids = {
        stage.id
        for stage in PIPELINE_STAGES + SECONDARY_STAGES
        if not stage.supports_force
    }
    assert no_force_ids == {
        "validate_transcripts",
        "analyze_scenes",
        "index_assets",
        "index_code",
        "index_backgrounds",
        "generate_scene_plan_ts",
        "qa_check",
    }
