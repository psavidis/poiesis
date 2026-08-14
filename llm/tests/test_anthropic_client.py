import json
from unittest.mock import MagicMock, patch


def _mock_text_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.content = [block]
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens

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


def test_complete_populates_last_usage_with_tokens_but_no_cost():
    with patch("llm.anthropic_client.Anthropic") as MockAnthropic:
        instance = MockAnthropic.return_value
        instance.messages.create.return_value = _mock_text_response(
            "hello", input_tokens=123, output_tokens=45
        )

        from llm.anthropic_client import AnthropicClient

        client = AnthropicClient("claude-sonnet-5")
        assert client.last_usage is None

        client.complete("say hi")

        assert client.last_usage.input_tokens == 123
        assert client.last_usage.output_tokens == 45
        # the Messages API doesn't report a dollar cost — must stay None,
        # never guessed at from a per-token price that could go stale
        assert client.last_usage.cost_usd is None


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
