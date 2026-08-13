import json

from anthropic import Anthropic

MAX_TOKENS = 8192


class AnthropicClient:

    def __init__(self, model: str):
        self.model = model
        self.client = Anthropic()

    def complete(self, prompt: str, thinking: bool = True) -> str:

        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "user", "content": prompt}
            ],
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
