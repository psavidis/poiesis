import subprocess


class OllamaClient:

    def __init__(self, model: str):
        self.model = model


    def complete(self, prompt: str) -> str:
        result = subprocess.run(
            [
                "ollama",
                "run",
                self.model
            ],
            input=prompt,
            text=True,
            capture_output=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Ollama failed: {result.stderr}"
            )

        return result.stdout