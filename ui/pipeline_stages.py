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
    def __init__(self, id, label, command, artifact, supports_force=True):
        self.id = id
        self.label = label
        self.command = command
        self.artifact = artifact
        # Whether the underlying script accepts --force at all (#81). Most
        # scripts skip regenerating their output when it already exists
        # UNLESS --force is passed (e.g. generate_title_scenes.py's own
        # `if output_file.exists() and not args.force: skip`) — for those,
        # --force is exactly what makes the UI's "Re-run" button actually
        # rerun the stage instead of silently no-op'ing (exit code 0, "X
        # already proposed. Skipping."). A handful of scripts
        # (index_assets.py, index_backgrounds.py, index_code.py,
        # analyze_scenes.py, generate_scene_plan_ts.py, qa_check.py,
        # validate_transcripts.py) have no such skip check at all — they
        # always regenerate their output unconditionally — and never
        # defined a --force argparse flag in the first place, so passing
        # --force to them would fail with argparse's "unrecognized
        # arguments" rather than doing anything useful. Defaults to True
        # (the common case) — set False only for stages confirmed to have
        # no --force flag.
        self.supports_force = supports_force

    def artifact_path(self, episode: Path) -> Path:
        return episode / "processing" / self.artifact

    def is_complete(self, episode: Path) -> bool:
        return self.artifact_path(episode).exists()

    def build_command(self, episode: Path, force: bool = False):
        command = [str(part) for part in self.command(episode)]
        if force and self.supports_force and "--force" not in command:
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
        supports_force=False,
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
        supports_force=False,
    ),
    Stage(
        "index_assets",
        "Index graphics assets",
        lambda ep: [PYTHON, PIPELINE_DIR / "index_assets.py", ep],
        "assets.json",
        supports_force=False,
    ),
    Stage(
        "index_code",
        "Index code assets",
        lambda ep: [PYTHON, PIPELINE_DIR / "index_code.py", ep],
        "code_assets.json",
        supports_force=False,
    ),
    Stage(
        "index_backgrounds",
        "Index backgrounds",
        lambda ep: [PYTHON, PIPELINE_DIR / "index_backgrounds.py", ep],
        "backgrounds.json",
        supports_force=False,
    ),
    Stage(
        "generate_cut_candidates",
        "Propose pause cuts (mechanical, no AI)",
        lambda ep: [PYTHON, PIPELINE_DIR / "generate_cut_candidates.py", ep],
        "cut_candidates.json",
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
        supports_force=False,
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
        supports_force=False,
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
