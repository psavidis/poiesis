import json
import subprocess

from .usage import Usage


class ClaudeCodeClient:

    def __init__(self, model: str):
        self.model = model
        # Usage from the most recent complete()/complete_json() call — the
        # CLI's --output-format json response already includes cost/token/
        # duration fields per call; this just stops discarding them. None
        # until the first call completes.
        self.last_usage: Usage | None = None

    def _run(self, prompt: str, thinking: bool = True) -> str:

        # The CLI has no boolean --thinking flag — it takes --effort
        # (low/medium/high/xhigh/max). thinking was previously accepted by
        # this class's public methods but never actually passed to the CLI
        # at all, so every call ran at the CLI's own default effort
        # regardless of what a caller asked for. "high" is a reasonable,
        # deliberate choice for thinking=True (not the max/most expensive
        # tier) — callers that pass thinking=False get the CLI's default
        # (no --effort flag) rather than an artificially throttled "low",
        # since this project's few thinking=False call sites are simple
        # mechanical decisions, not ones that need to be actively degraded.
        command = [
            "claude",
            "--print",
            "--output-format", "json",
            "--model", self.model,
            "--tools", "",
        ]

        if thinking:
            command.extend(["--effort", "high"])

        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude Code failed: {result.stderr}"
            )

        response = json.loads(result.stdout)

        usage = response.get("usage") or {}

        self.last_usage = Usage(
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cost_usd=response.get("total_cost_usd"),
            duration_ms=response.get("duration_ms"),
        )

        if response.get("is_error"):
            raise RuntimeError(
                f"Claude Code returned an error: {response.get('result')}"
            )

        return response["result"]

    def complete(self, prompt: str, thinking: bool = True) -> str:
        return self._run(prompt, thinking)

    def complete_json(self, prompt: str, thinking: bool = True) -> str:

        json_prompt = (
            f"{prompt}\n\n"
            "Return ONLY the JSON object. Do not include any other text, "
            "explanation, or markdown code fences."
        )

        text = self._run(json_prompt, thinking)

        text = text.strip()

        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        return json.dumps(json.loads(text))
