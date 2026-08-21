from generate_storyboard import propose_storyboard


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.last_prompt = None
        self.last_thinking = None

    def complete_json(self, prompt, thinking=True):
        self.last_prompt = prompt
        self.last_thinking = thinking
        return self.response


def _scene_plan_with_one_chapter():
    return {
        "fps": 30,
        "scenes": [
            {
                "type": "presenter",
                "id": "scene-001",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,
                "sourceStartFrame": 0,
                "sourceEndFrame": 900,
            },
            {"type": "title", "id": "t0", "text": "The Chapter", "timelineStartFrame": 0, "durationInFrames": 60},
        ],
    }


def _scene_plan_with_two_chapters():
    return {
        "fps": 30,
        "scenes": [
            {
                "type": "presenter",
                "id": "scene-001",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 1200,
                "sourceStartFrame": 0,
                "sourceEndFrame": 1200,
            },
            {"type": "title", "id": "t0", "text": "First Chapter", "timelineStartFrame": 0, "durationInFrames": 60},
            {"type": "title", "id": "t1", "text": "Second Chapter", "timelineStartFrame": 600, "durationInFrames": 60},
        ],
    }


def _transcript_with_late_segment():
    return {
        "segments": [
            {"source": "a.mp4", "start": 20.0, "end": 22.0, "text": "the important key idea"},
        ]
    }


def _transcript_spanning_two_chapters():
    return {
        "segments": [
            {"source": "a.mp4", "start": 20.0, "end": 22.0, "text": "the important key idea"},
            {"source": "a.mp4", "start": 25.0, "end": 27.0, "text": "the second point matters"},
        ]
    }


def _manifest_single_video():
    return {"videos": [{"id": "001", "filename": "a.mp4"}]}


def test_propose_storyboard_returns_one_entry_per_chapter():
    llm = _FakeLLMClient(
        {
            "chapters": [
                {"chapterId": "c0", "notes": "This chapter introduces the core idea."},
            ]
        }
    )

    chapters = propose_storyboard(
        _scene_plan_with_one_chapter(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        llm,
        "{windows}{episode_context}",
    )

    assert len(chapters) == 1
    assert chapters[0]["chapterId"] == "c0"
    assert chapters[0]["chapterText"] == "The Chapter"
    assert chapters[0]["notes"] == "This chapter introduces the core idea."


def test_propose_storyboard_prompt_shows_the_real_chapter_id_not_just_title():
    # Regression: format_windows_for_prompt used to render only the chapter
    # title text in the heading ('Chapter "The Chapter"'), never the actual
    # chapterId ("c0") the schema asks the LLM to key its response by. The
    # model then had nothing to reference but the title, returned the title
    # string as "chapterId", and every note silently failed to match in
    # propose_storyboard's notes_by_chapter_id lookup — confirmed against a
    # real episode before this was fixed (every chapter came back empty).
    llm = _FakeLLMClient({"chapters": [{"chapterId": "c0", "notes": "reasoning"}]})

    propose_storyboard(
        _scene_plan_with_one_chapter(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        llm,
        "{windows}{episode_context}",
    )

    assert "[c0]" in llm.last_prompt


def test_propose_storyboard_fills_missing_chapter_with_empty_notes():
    # LLM only returned notes for c0, not c1 — every real chapter should
    # still get an entry rather than silently disappearing.
    llm = _FakeLLMClient(
        {
            "chapters": [
                {"chapterId": "c0", "notes": "First chapter reasoning."},
            ]
        }
    )

    chapters = propose_storyboard(
        _scene_plan_with_two_chapters(),
        _transcript_spanning_two_chapters(),
        _manifest_single_video(),
        llm,
        "{windows}{episode_context}",
    )

    assert len(chapters) == 2
    assert chapters[0]["notes"] == "First chapter reasoning."
    assert chapters[1]["chapterId"] == "c1"
    assert chapters[1]["notes"] == ""


def test_propose_storyboard_returns_empty_list_when_no_chapters():
    llm = _FakeLLMClient({"chapters": []})

    scene_plan_no_titles = {
        "fps": 30,
        "scenes": [
            {
                "type": "presenter",
                "id": "scene-001",
                "videoId": "001",
                "timelineStartFrame": 0,
                "durationInFrames": 900,
                "sourceStartFrame": 0,
                "sourceEndFrame": 900,
            },
        ],
    }

    chapters = propose_storyboard(
        scene_plan_no_titles,
        _transcript_with_late_segment(),
        _manifest_single_video(),
        llm,
        "{windows}{episode_context}",
    )

    assert chapters == []
    assert llm.last_prompt is None  # no LLM call made — nothing to reason about


def test_propose_storyboard_requests_thinking():
    llm = _FakeLLMClient({"chapters": [{"chapterId": "c0", "notes": "reasoning"}]})

    propose_storyboard(
        _scene_plan_with_one_chapter(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        llm,
        "{windows}{episode_context}",
    )

    assert llm.last_thinking is True


def test_propose_storyboard_ignores_entry_with_unknown_chapter_id():
    llm = _FakeLLMClient(
        {
            "chapters": [
                {"chapterId": "c0", "notes": "real chapter"},
                {"chapterId": "c99", "notes": "fabricated chapter id"},
            ]
        }
    )

    chapters = propose_storyboard(
        _scene_plan_with_one_chapter(),
        _transcript_with_late_segment(),
        _manifest_single_video(),
        llm,
        "{windows}{episode_context}",
    )

    assert len(chapters) == 1
    assert chapters[0]["chapterId"] == "c0"
