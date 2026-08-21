from analyze_episode import analyze_episode


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.last_prompt = None

    def complete_json(self, prompt, thinking=True):
        self.last_prompt = prompt
        return self.response


def _transcript():
    return {
        "segments": [
            {"text": "Today we're talking about dependency injection."},
            {"text": "It lets you swap implementations without changing callers."},
        ]
    }


def test_analyze_episode_passes_through_narrative_section():
    llm = _FakeLLMClient(
        {
            "status": "ok",
            "issues": [],
            "narrative": {
                "topics": ["Dependency injection"],
                "keyConcepts": ["Dependency injection", "Inversion of control"],
                "hardToVisualize": ["How a container resolves a dependency at runtime"],
            },
        }
    )

    result = analyze_episode(_transcript(), {}, llm, "{transcript}{validation}")

    assert result["analysis"]["narrative"]["topics"] == ["Dependency injection"]
    assert result["analysis"]["narrative"]["keyConcepts"] == [
        "Dependency injection",
        "Inversion of control",
    ]


def test_analyze_episode_still_works_without_narrative_section():
    # Backward compatibility: an older/non-compliant LLM response without a
    # "narrative" key must not break analyze_episode.py's own output shape.
    llm = _FakeLLMClient({"status": "ok", "issues": []})

    result = analyze_episode(_transcript(), {}, llm, "{transcript}{validation}")

    assert result["analysis"]["status"] == "ok"
    assert "narrative" not in result["analysis"]
