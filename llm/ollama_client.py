import subprocess


class OllamaClient:

    def __init__(self, model: str):
        self.model = model


    def complete(self, prompt: str, thinking: bool = True) -> str:

        command = [
            "ollama",
            "run",
            self.model
        ]

        if not thinking:
            command.append("--think=false")

        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Ollama failed: {result.stderr}"
            )

        return result.stdout