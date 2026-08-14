from pathlib import Path
import json

from .ollama_client import OllamaClient
from .anthropic_client import AnthropicClient
from .claude_code_client import ClaudeCodeClient
from .usage import Usage


def _add_usage(total: Usage, latest: Usage | None) -> Usage:
    """Accumulates whatever fields latest actually reports into total,
    leaving a field alone (not zeroing it) if latest didn't report it —
    mirrors Usage's own "None means unknown, never guessed as 0" rule."""

    if latest is None:
        return total

    def add(a, b):
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)

    return Usage(
        input_tokens=add(total.input_tokens, latest.input_tokens),
        output_tokens=add(total.output_tokens, latest.output_tokens),
        cost_usd=add(total.cost_usd, latest.cost_usd),
        duration_ms=add(total.duration_ms, latest.duration_ms),
    )


class LLMClient:

    def __init__(self, config_path: Path):

        with config_path.open(
                "r",
                encoding="utf-8"
        ) as f:
            config = json.load(f)


        provider = config["llm"]["provider"]
        model = config["llm"]["model"]


        if provider == "ollama":
            self.client = OllamaClient(model)

        elif provider == "anthropic":
            self.client = AnthropicClient(model)

        elif provider == "claude-code":
            self.client = ClaudeCodeClient(model)

        else:
            raise RuntimeError(
                f"Unsupported LLM provider: {provider}"
            )

        # Accumulated across every call made through this LLMClient
        # instance (typically the lifetime of one pipeline stage script's
        # process) — printed as a running total, not just per-call, since
        # a stage like edit_plan's interactive loop can make several calls
        # and a per-call number alone wouldn't show the total cost of the
        # stage's actual work.
        self.total_usage = Usage()

    @property
    def last_usage(self) -> Usage | None:
        return getattr(self.client, "last_usage", None)

    def _log_usage(self):
        usage = self.last_usage

        if usage is not None:
            self.total_usage = _add_usage(self.total_usage, usage)
            print(f"LLM usage: {usage.format()} (total this run: {self.total_usage.format()})")

    def complete(self, prompt: str, thinking: bool = True) -> str:
        print(f"LLM request: prompt={prompt} thinking={'on' if thinking else 'off'}")

        # finally, not just after a successful return: a provider that
        # raises after already parsing a response (e.g. Claude Code CLI
        # returning is_error=true) has still incurred real cost, and that's
        # exactly the kind of call worth seeing logged, not silently lost
        # because the exception unwound past a plain post-call log line.
        try:
            return self.client.complete(prompt, thinking)
        finally:
            self._log_usage()

    def complete_json(self, prompt: str, thinking: bool = True):
        print(f"LLM JSON request: prompt={prompt} thinking={'on' if thinking else 'off'}")

        try:
            response = self.client.complete_json(prompt, thinking)
        finally:
            self._log_usage()

        return json.loads(response)
