"""Defines the pipeline stages the UI displays and can trigger.

Mirrors pipeline/run_pipeline.py's stage order exactly. This module is the
single source of truth the UI uses to build the stage diagram and figure out
which stages have already produced output — it does not reimplement any
pipeline logic, only points at the existing scripts and artifact files.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"

# Invoke Python stage scripts via this interpreter (the venv running the UI
# server) rather than relying on the script's shebang + executable bit,
# which isn't guaranteed to be set.
PYTHON = sys.executable


class Stage:
    def __init__(self, id, label, command, artifact):
        self.id = id
        self.label = label
        self.command = command
        self.artifact = artifact

    def artifact_path(self, episode: Path) -> Path:
        return episode / "processing" / self.artifact

    def is_complete(self, episode: Path) -> bool:
        return self.artifact_path(episode).exists()

    def build_command(self, episode: Path, force: bool = False):
        command = [str(part) for part in self.command(episode)]
        if force and "--force" not in command:
            command.append("--force")
        return command


PIPELINE_STAGES = [
    Stage(
        "prepare",
        "Prepare footage",
        lambda ep: [PYTHON, PIPELINE_DIR / "prepare_footage.py", ep],
        "manifest.json",
    ),
    Stage(
        "transcribe",
        "Transcribe",
        lambda ep: [PROJECT_ROOT / "transcribe_footage.sh", ep],
        "transcripts",
    ),
    Stage(
        "validate_transcripts",
        "Validate transcripts",
        lambda ep: [PYTHON, PIPELINE_DIR / "validate_transcripts.py", ep],
        "transcript_validation.json",
    ),
    Stage(
        "normalize_transcripts",
        "Normalize transcripts",
        lambda ep: [PYTHON, PIPELINE_DIR / "normalize_transcripts.py", ep],
        "segments",
    ),
    Stage(
        "merge_segments",
        "Merge segments",
        lambda ep: [PYTHON, PIPELINE_DIR / "merge_segments.py", ep],
        "episode_transcript.json",
    ),
    Stage(
        "analyze_episode",
        "Analyze episode (AI narrative summary + transcript QA)",
        lambda ep: [PYTHON, PIPELINE_DIR / "analyze_episode.py", ep],
        "episode_analysis.json",
    ),
    Stage(
        "analyze_scenes",
        "Analyze scenes (silence trim)",
        lambda ep: [PYTHON, PIPELINE_DIR / "analyze_scenes.py", ep],
        "scene-plan.json",
    ),
    Stage(
        "index_assets",
        "Index graphics assets",
        lambda ep: [PYTHON, PIPELINE_DIR / "index_assets.py", ep],
        "assets.json",
    ),
    Stage(
        "generate_title_scenes",
        "Propose title scenes (AI)",
        lambda ep: [PYTHON, PIPELINE_DIR / "generate_title_scenes.py", ep],
        "title_scenes.json",
    ),
    Stage(
        "generate_storyboard",
        "Propose chapter storyboard (AI)",
        lambda ep: [PYTHON, PIPELINE_DIR / "generate_storyboard.py", ep],
        "storyboard.json",
    ),
    Stage(
        "generate_moments",
        "Propose moment scenes (AI)",
        lambda ep: [PYTHON, PIPELINE_DIR / "generate_moments.py", ep],
        "moments.json",
    ),
    Stage(
        "generate_captions",
        "Generate captions",
        lambda ep: [PYTHON, PIPELINE_DIR / "generate_captions.py", ep],
        "captions.json",
    ),
    Stage(
        "generate_emphasis",
        "Propose emphasis beats (AI)",
        lambda ep: [PYTHON, PIPELINE_DIR / "generate_emphasis.py", ep],
        "emphasis.json",
    ),
    Stage(
        "generate_scene_plan_ts",
        "Generate Remotion codegen",
        lambda ep: [PYTHON, PIPELINE_DIR / "generate_scene_plan_ts.py", ep],
        None,
    ),
    Stage(
        "generate_episode_assets",
        "Generate episode assets",
        lambda ep: [PYTHON, PIPELINE_DIR / "generate_episode_assets.py", ep],
        "subtitles.srt",
    ),
]

# Deliberately separate, opt-in steps — not part of the chained run.
SECONDARY_STAGES = [
    Stage(
        "key_footage",
        "Remove background (green screen)",
        lambda ep: [PYTHON, PIPELINE_DIR / "key_footage.py", ep],
        "keyed",
    ),
    Stage(
        "qa_check",
        "QA check",
        lambda ep: [PYTHON, PIPELINE_DIR / "qa_check.py", ep],
        "qa-report.json",
    ),
]


def stage_status(episode: Path):
    return [
        {
            "id": stage.id,
            "label": stage.label,
            "complete": stage.is_complete(episode) if stage.artifact else None,
        }
        for stage in PIPELINE_STAGES
    ]


def find_stage(stage_id: str):
    for stage in PIPELINE_STAGES + SECONDARY_STAGES:
        if stage.id == stage_id:
            return stage
    return None
