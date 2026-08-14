from dataclasses import dataclass


@dataclass
class Usage:
    """What a provider reported about the cost of a single completion.
    Every field is optional because providers differ in what they can
    report at all — Ollama (a local model) has no dollar cost and this
    codebase doesn't ask it for token counts either, while the Claude Code
    CLI reports cost, tokens, AND wall-clock duration. None means
    "unknown", not "zero" — never printed/summed as if it were 0."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None

    def format(self) -> str:
        parts = []

        if self.input_tokens is not None or self.output_tokens is not None:
            parts.append(f"{self.input_tokens or 0}in/{self.output_tokens or 0}out tokens")

        if self.cost_usd is not None:
            parts.append(f"${self.cost_usd:.4f}")

        if self.duration_ms is not None:
            parts.append(f"{self.duration_ms}ms")

        return ", ".join(parts) if parts else "usage unavailable"
