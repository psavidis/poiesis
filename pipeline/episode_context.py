import json
from pathlib import Path

# What every prompt shows when no episode-level analysis exists yet (an
# episode processed before this stage was reordered ahead of title/moment/
# emphasis generation, or one where analyze_episode.py hasn't run) — a
# generator script should never fail just because this context is missing,
# only lose the added context.
NO_CONTEXT_TEXT = "(no episode-level analysis available)"


def _formatted(narrative):
    lines = []

    topics = narrative.get("topics") or []
    if topics:
        lines.append("Topics covered, in order: " + "; ".join(topics))

    key_concepts = narrative.get("keyConcepts") or []
    if key_concepts:
        lines.append("Key concepts central to this episode: " + "; ".join(key_concepts))

    hard_to_visualize = narrative.get("hardToVisualize") or []
    if hard_to_visualize:
        lines.append(
            "Ideas likely to benefit from a diagram or constructed visual: "
            + "; ".join(hard_to_visualize)
        )

    if not lines:
        return NO_CONTEXT_TEXT

    return "\n".join(lines)


def load_episode_narrative_text(episode_folder: Path) -> str:
    """Loads processing/episode_analysis.json's "narrative" section (topics/
    keyConcepts/hardToVisualize — see analyze_episode.py and
    prompts/episode_analysis.txt) and formats it as prompt-ready text, for
    stages that decide what appears on screen (title/moment/emphasis
    proposals) to ground their local, per-window decisions in the episode's
    overall shape. Falls back to NO_CONTEXT_TEXT rather than raising if the
    file, or the "narrative" key within it, doesn't exist — this context is
    additive, never a hard requirement for any of those stages to run."""

    analysis_file = Path(episode_folder) / "processing" / "episode_analysis.json"

    if not analysis_file.exists():
        return NO_CONTEXT_TEXT

    with analysis_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    narrative = data.get("analysis", {}).get("narrative")

    if not isinstance(narrative, dict):
        return NO_CONTEXT_TEXT

    return _formatted(narrative)
