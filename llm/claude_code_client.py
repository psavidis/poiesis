import json
import subprocess


class ClaudeCodeClient:

    def __init__(self, model: str):
        self.model = model

    def _run(self, prompt: str) -> str:

        command = [
            "claude",
            "--print",
            "--output-format", "json",
            "--model", self.model,
            "--tools", "",
        ]

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

        if response.get("is_error"):
            raise RuntimeError(
                f"Claude Code returned an error: {response.get('result')}"
            )

        return response["result"]

    def complete(self, prompt: str, thinking: bool = True) -> str:
        return self._run(prompt)

    def complete_json(self, prompt: str, thinking: bool = True) -> str:

        json_prompt = (
            f"{prompt}\n\n"
            "Return ONLY the JSON object. Do not include any other text, "
            "explanation, or markdown code fences."
        )

        text = self._run(json_prompt)

        text = text.strip()

        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        return json.dumps(json.loads(text))
