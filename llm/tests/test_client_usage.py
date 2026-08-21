import json
from unittest.mock import patch

from llm.client import LLMClient
from llm.usage import Usage


def _config(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"llm": {"provider": "claude-code", "model": "sonnet"}}),
        encoding="utf-8",
    )
    return config_path


def test_last_usage_passes_through_from_provider(tmp_path):
    llm = LLMClient(_config(tmp_path))
    llm.client.last_usage = Usage(input_tokens=10, output_tokens=5)

    assert llm.last_usage == Usage(input_tokens=10, output_tokens=5)


def test_last_usage_is_none_before_any_call(tmp_path):
    llm = LLMClient(_config(tmp_path))

    assert llm.last_usage is None


def test_complete_accumulates_total_usage_across_calls(tmp_path):
    llm = LLMClient(_config(tmp_path))

    def fake_complete(prompt, thinking):
        llm.client.last_usage = Usage(input_tokens=10, output_tokens=5, cost_usd=0.01)
        return "response"

    with patch.object(llm.client, "complete", side_effect=fake_complete):
        llm.complete("prompt one")
        llm.complete("prompt two")

    assert llm.total_usage.input_tokens == 20
    assert llm.total_usage.output_tokens == 10
    assert abs(llm.total_usage.cost_usd - 0.02) < 1e-9


def test_complete_json_accumulates_total_usage(tmp_path):
    llm = LLMClient(_config(tmp_path))

    def fake_complete_json(prompt, thinking):
        llm.client.last_usage = Usage(input_tokens=7, output_tokens=3)
        return '{"ok": true}'

    with patch.object(llm.client, "complete_json", side_effect=fake_complete_json):
        result = llm.complete_json("prompt")

    assert result == {"ok": True}
    assert llm.total_usage.input_tokens == 7
    assert llm.total_usage.output_tokens == 3


def test_total_usage_unaffected_when_provider_reports_no_usage(tmp_path):
    llm = LLMClient(_config(tmp_path))

    with patch.object(llm.client, "complete", return_value="response"):
        # provider's last_usage stays None (e.g. Ollama) — nothing to add
        llm.complete("prompt")

    assert llm.total_usage == Usage()


def test_usage_is_logged_even_when_call_raises(tmp_path, capsys):
    llm = LLMClient(_config(tmp_path))

    def fake_complete(prompt, thinking):
        llm.client.last_usage = Usage(cost_usd=0.005)
        raise RuntimeError("call failed")

    with patch.object(llm.client, "complete", side_effect=fake_complete):
        try:
            llm.complete("prompt")
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass

    assert llm.total_usage.cost_usd == 0.005
    assert "LLM usage" in capsys.readouterr().out
