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
