#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


def generate_scene_plan_ts(
        episode_folder: Path,
        renderer_folder: Path
):
    scene_plan_path = (
            episode_folder
            / "processing"
            / "scene-plan.json"
    )

    if not scene_plan_path.exists():
        raise RuntimeError(
            f"Scene plan not found: {scene_plan_path}"
        )

    with scene_plan_path.open(
            "r",
            encoding="utf-8"
    ) as f:
        scene_plan = json.load(f)


    output = (
            renderer_folder
            / "generated"
            / "episode"
            / "scene-plan.ts"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    lines = [
        "export const scenePlan = ",
        json.dumps(
            scene_plan,
            indent=2,
            ensure_ascii=False
        ),
        ";",
        "",
    ]

    output.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print(
        f"Generated scene plan TS: {output}"
    )


def main():

    parser = argparse.ArgumentParser(
        description="Generate Remotion scene plan TS"
    )

    parser.add_argument(
        "episode_folder"
    )

    args = parser.parse_args()


    episode_folder = Path(
        args.episode_folder
    ).resolve()


    project_root = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    renderer_folder = (
            project_root
            / "video-renderer"
    )


    generate_scene_plan_ts(
        episode_folder,
        renderer_folder
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(
            f"ERROR: {e}"
        )
        sys.exit(1)