import json
from unittest.mock import MagicMock, patch


def _mock_cli_result(payload: dict, returncode: int = 0):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = json.dumps(payload)
    result.stderr = ""
    return result


def test_complete_returns_result_text():
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result(
            {"is_error": False, "result": "hello"}
        )

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")
        result = client.complete("say hi")

        assert result == "hello"

        args, kwargs = mock_run.call_args
        command = args[0]
        assert command[0] == "claude"
        assert "--model" in command
        assert "sonnet" in command
        assert kwargs["input"] == "say hi"


def test_complete_passes_effort_high_when_thinking_is_true():
    # Regression: thinking was previously accepted by complete()/
    # complete_json() but never actually passed to the CLI at all — every
    # call ran at the CLI's own default effort regardless of the flag.
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result({"is_error": False, "result": "hello"})

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")
        client.complete("say hi", thinking=True)

        command = mock_run.call_args.args[0]
        assert "--effort" in command
        assert command[command.index("--effort") + 1] == "high"


def test_complete_omits_effort_flag_when_thinking_is_false():
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result({"is_error": False, "result": "hello"})

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")
        client.complete("say hi", thinking=False)

        command = mock_run.call_args.args[0]
        assert "--effort" not in command


def test_complete_json_passes_effort_high_when_thinking_is_true():
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result({"is_error": False, "result": '{"status": "ok"}'})

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")
        client.complete_json("analyze this", thinking=True)

        command = mock_run.call_args.args[0]
        assert "--effort" in command
        assert command[command.index("--effort") + 1] == "high"


def test_complete_json_parses_plain_json():
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result(
            {"is_error": False, "result": '{"status": "ok"}'}
        )

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")
        result = client.complete_json("analyze this")

        assert json.loads(result) == {"status": "ok"}


def test_complete_json_strips_markdown_code_fence():
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result(
            {"is_error": False, "result": '```json\n{"status": "ok"}\n```'}
        )

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")
        result = client.complete_json("analyze this")

        assert json.loads(result) == {"status": "ok"}


def test_complete_json_extracts_object_when_model_adds_prose():
    # Regression: the model sometimes reasons in prose before the JSON
    # object despite being told to return ONLY the object (e.g. explaining
    # why it picked a fallback operation) — this used to raise
    # JSONDecodeError and surface as a 502 to the caller.
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result(
            {
                "is_error": False,
                "result": 'Frame 9920 falls in scene-009.\n\n{"status": "ok"}',
            }
        )

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")
        result = client.complete_json("analyze this")

        assert json.loads(result) == {"status": "ok"}


def test_complete_json_still_raises_when_no_object_present():
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result(
            {"is_error": False, "result": "I cannot help with that."}
        )

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")

        try:
            client.complete_json("analyze this")
            assert False, "expected JSONDecodeError"
        except json.JSONDecodeError:
            pass


def test_raises_on_nonzero_exit():
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        result = MagicMock()
        result.returncode = 1
        result.stderr = "boom"
        mock_run.return_value = result

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")

        try:
            client.complete("say hi")
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "boom" in str(e)


def test_raises_when_response_is_error():
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result(
            {"is_error": True, "result": "something went wrong"}
        )

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")

        try:
            client.complete("say hi")
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "something went wrong" in str(e)


def test_complete_populates_last_usage():
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result(
            {
                "is_error": False,
                "result": "hello",
                "total_cost_usd": 0.0123,
                "duration_ms": 800,
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        )

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")
        assert client.last_usage is None

        client.complete("say hi")

        assert client.last_usage.input_tokens == 100
        assert client.last_usage.output_tokens == 50
        assert client.last_usage.cost_usd == 0.0123
        assert client.last_usage.duration_ms == 800


def test_last_usage_is_none_field_when_missing_from_response():
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result(
            {"is_error": False, "result": "hello"}
        )

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")
        client.complete("say hi")

        assert client.last_usage.input_tokens is None
        assert client.last_usage.cost_usd is None


def test_last_usage_is_populated_even_when_response_is_error():
    # a call that fails with is_error=true still incurred real cost —
    # that's worth surfacing, not silently discarded because an exception
    # was about to be raised
    with patch("llm.claude_code_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_cli_result(
            {
                "is_error": True,
                "result": "something went wrong",
                "total_cost_usd": 0.005,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )

        from llm.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient("sonnet")

        try:
            client.complete("say hi")
        except RuntimeError:
            pass

        assert client.last_usage.cost_usd == 0.005


def test_llm_client_dispatches_to_claude_code_provider(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"llm": {"provider": "claude-code", "model": "sonnet"}}),
        encoding="utf-8",
    )

    from llm.client import LLMClient
    from llm.claude_code_client import ClaudeCodeClient

    llm_client = LLMClient(config_path)

    assert isinstance(llm_client.client, ClaudeCodeClient)
    assert llm_client.client.model == "sonnet"
