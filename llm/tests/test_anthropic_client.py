import json
from unittest.mock import MagicMock, patch


def _mock_text_response(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.content = [block]

    return response


def test_complete_joins_text_blocks():
    with patch("llm.anthropic_client.Anthropic") as MockAnthropic:
        instance = MockAnthropic.return_value
        instance.messages.create.return_value = _mock_text_response("hello")

        from llm.anthropic_client import AnthropicClient

        client = AnthropicClient("claude-sonnet-5")
        result = client.complete("say hi")

        assert result == "hello"
        instance.messages.create.assert_called_once()
        _, kwargs = instance.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-5"
        assert kwargs["messages"] == [{"role": "user", "content": "say hi"}]


def test_complete_json_returns_valid_json_string():
    with patch("llm.anthropic_client.Anthropic") as MockAnthropic:
        instance = MockAnthropic.return_value
        instance.messages.create.return_value = _mock_text_response(
            '{"status": "ok"}'
        )

        from llm.anthropic_client import AnthropicClient

        client = AnthropicClient("claude-sonnet-5")
        result = client.complete_json("analyze this")

        assert json.loads(result) == {"status": "ok"}


def test_llm_client_dispatches_to_anthropic_provider(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"llm": {"provider": "anthropic", "model": "claude-sonnet-5"}}),
        encoding="utf-8",
    )

    with patch("llm.anthropic_client.Anthropic"):
        from llm.client import LLMClient
        from llm.anthropic_client import AnthropicClient

        llm_client = LLMClient(config_path)

        assert isinstance(llm_client.client, AnthropicClient)
        assert llm_client.client.model == "claude-sonnet-5"
