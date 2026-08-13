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
