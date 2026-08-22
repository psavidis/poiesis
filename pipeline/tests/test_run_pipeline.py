from unittest.mock import patch

import run_pipeline


def _fake_completed_process():
    class _Result:
        returncode = 0

    return _Result()


AI_SCRIPTS = {
    "analyze_episode.py",
    "generate_title_scenes.py",
    "generate_storyboard.py",
    "generate_moments.py",
    "generate_emphasis.py",
}

NON_AI_SCRIPTS = {
    "prepare_footage.py",
    "validate_transcripts.py",
    "normalize_transcripts.py",
    "merge_segments.py",
    "analyze_scenes.py",
    "index_assets.py",
    "index_code.py",
    "index_backgrounds.py",
    "generate_cut_candidates.py",
    "generate_captions.py",
    "generate_background_scenes.py",
    "generate_scene_plan_ts.py",
    "generate_episode_assets.py",
}


def _scripts_invoked(mock_run):
    invoked = set()

    for call in mock_run.call_args_list:
        command = call.args[0]
        for part in command:
            name = str(part)
            if name.endswith(".py"):
                invoked.add(name.rsplit("/", 1)[-1])

    return invoked


# #88: --no-ai must skip every stage that calls an LLM, while every
# deterministic/mechanical stage (scene cuts, indexing, captions,
# background merge, scene plan/asset generation) still runs — a --no-ai
# run must still produce a complete, renderable episode.
def test_no_ai_skips_every_ai_stage_but_runs_everything_else(tmp_path):
    episode = tmp_path / "episode"
    episode.mkdir()

    with patch("subprocess.run", return_value=_fake_completed_process()) as mock_run, \
         patch("sys.argv", ["run_pipeline.py", str(episode), "--no-ai"]):

        run_pipeline.main()

    invoked = _scripts_invoked(mock_run)

    assert invoked.isdisjoint(AI_SCRIPTS), f"AI stages were invoked under --no-ai: {invoked & AI_SCRIPTS}"
    assert NON_AI_SCRIPTS.issubset(invoked), f"missing non-AI stages: {NON_AI_SCRIPTS - invoked}"


def test_without_no_ai_every_stage_still_runs(tmp_path):
    episode = tmp_path / "episode"
    episode.mkdir()

    with patch("subprocess.run", return_value=_fake_completed_process()) as mock_run, \
         patch("sys.argv", ["run_pipeline.py", str(episode)]):

        run_pipeline.main()

    invoked = _scripts_invoked(mock_run)

    assert AI_SCRIPTS.issubset(invoked)
    assert NON_AI_SCRIPTS.issubset(invoked)


def test_no_ai_and_skip_captions_can_be_combined(tmp_path):
    episode = tmp_path / "episode"
    episode.mkdir()

    with patch("subprocess.run", return_value=_fake_completed_process()) as mock_run, \
         patch("sys.argv", ["run_pipeline.py", str(episode), "--no-ai", "--skip-captions"]):

        run_pipeline.main()

    invoked = _scripts_invoked(mock_run)

    assert invoked.isdisjoint(AI_SCRIPTS)
    assert "generate_captions.py" in invoked

    captions_call = next(
        call for call in mock_run.call_args_list
        if any(str(p).endswith("generate_captions.py") for p in call.args[0])
    )
    assert "--disable" in captions_call.args[0]
