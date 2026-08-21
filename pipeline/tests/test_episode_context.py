import json

from episode_context import NO_CONTEXT_TEXT, load_episode_narrative_text


def _write_analysis(episode_dir, analysis):
    processing = episode_dir / "processing"
    processing.mkdir(parents=True, exist_ok=True)

    with (processing / "episode_analysis.json").open("w", encoding="utf-8") as f:
        json.dump({"segments": 1, "analysis": analysis}, f)


def test_missing_file_returns_fallback_text(tmp_path):
    assert load_episode_narrative_text(tmp_path) == NO_CONTEXT_TEXT


def test_missing_narrative_key_returns_fallback_text(tmp_path):
    _write_analysis(tmp_path, {"status": "ok", "issues": []})

    assert load_episode_narrative_text(tmp_path) == NO_CONTEXT_TEXT


def test_empty_narrative_lists_return_fallback_text(tmp_path):
    _write_analysis(
        tmp_path,
        {
            "status": "ok",
            "issues": [],
            "narrative": {"topics": [], "keyConcepts": [], "hardToVisualize": []},
        },
    )

    assert load_episode_narrative_text(tmp_path) == NO_CONTEXT_TEXT


def test_formats_all_three_narrative_fields(tmp_path):
    _write_analysis(
        tmp_path,
        {
            "status": "ok",
            "issues": [],
            "narrative": {
                "topics": ["Intro", "Dependency injection"],
                "keyConcepts": ["Dependency injection", "Inversion of control"],
                "hardToVisualize": ["The relationship between a container and a consumer"],
            },
        },
    )

    text = load_episode_narrative_text(tmp_path)

    assert "Intro; Dependency injection" in text
    assert "Dependency injection; Inversion of control" in text
    assert "The relationship between a container and a consumer" in text


def test_formats_only_present_fields(tmp_path):
    _write_analysis(
        tmp_path,
        {
            "status": "ok",
            "issues": [],
            "narrative": {"topics": ["Intro"]},
        },
    )

    text = load_episode_narrative_text(tmp_path)

    assert "Intro" in text
    assert "Key concepts" not in text
    assert "diagram or constructed visual" not in text
