import json

from anthropic import Anthropic

from .usage import Usage

MAX_TOKENS = 8192


class AnthropicClient:

    def __init__(self, model: str):
        self.model = model
        self.client = Anthropic()
        # Usage from the most recent complete()/complete_json() call. The
        # Messages API reports token counts but not a dollar cost (unlike
        # the Claude Code CLI provider) — cost_usd stays None here rather
        # than guessing at a per-token price that would drift out of date.
        self.last_usage: Usage | None = None

    def complete(self, prompt: str, thinking: bool = True) -> str:

        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        self.last_usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        return "".join(
            block.text
            for block in response.content
            if block.type == "text"
        )

    def complete_json(self, prompt: str, thinking: bool = True) -> str:

        json_prompt = (
            f"{prompt}\n\n"
            "Return ONLY the JSON object. Do not include any other text."
        )

        text = self.complete(json_prompt, thinking)

        return json.dumps(json.loads(text))
