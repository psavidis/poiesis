from pathlib import Path
import json

from .ollama_client import OllamaClient


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

        else:
            raise RuntimeError(
                f"Unsupported LLM provider: {provider}"
            )


    def complete(self, prompt: str, thinking: bool = True) -> str:
        print(f"LLM request: prompt={prompt} thinking={'on' if thinking else 'off'}")

        return self.client.complete(prompt, thinking)

    def complete_json(self, prompt: str, thinking: bool = True):
        print(f"LLM JSON request: prompt={prompt} thinking={'on' if thinking else 'off'}")

        response = self.client.complete_json(
            prompt,
            thinking
        )

        return json.loads(response)