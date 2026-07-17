import subprocess
import json

import re


def repair_json(text: str) -> str:

    # Remove terminal escape sequences
    text = re.sub(
        r'\x1b\[[0-9;]*[a-zA-Z]',
        '',
        text
    )

    result = []
    inside_string = False
    escaped = False

    for char in text:

        if char == '"' and not escaped:
            inside_string = not inside_string

        if char == "\n" and inside_string:
            result.append("\\n")
        elif char == "\r" and inside_string:
            result.append("\\r")
        elif char == "\t" and inside_string:
            result.append("\\t")
        else:
            result.append(char)

        escaped = (
                char == "\\"
                and not escaped
        )

        if char != "\\":
            escaped = False

    return "".join(result)

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

    def complete_json(self, prompt: str, thinking: bool = True) -> str:

        command = [
            "ollama",
            "run",
            self.model,
            "--format",
            "json"
        ]

        if not thinking:
            command.append("--think=false")

        json_prompt = f"""
    {prompt}
    
    Return ONLY the JSON object.
    """

        result = subprocess.run(
            command,
            input=json_prompt,
            text=True,
            capture_output=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Ollama failed: {result.stderr}"
            )

        output = result.stdout.strip()

        print("RAW JSON RESPONSE:")
        print(output)

        output = repair_json(output)

        print("REPAIRED JSON RESPONSE:")
        print(output)

        return output