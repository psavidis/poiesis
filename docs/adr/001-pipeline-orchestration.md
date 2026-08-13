# ADR 001: Sequential pipeline orchestration with shared data

**Status:** Accepted
**Date:** 2026-07-19

## Context

The poiesis project transforms raw episode footage into a finished video through a multi-stage process (prepare, transcribe, validate, normalize, merge, analyze scenes, generate Remotion plan, analyze episode, generate assets). These stages have strict ordering — each depends on the output of its predecessor. There is also a separate Render step that consumes the pipeline's output to produce the final video file.

The team needed a way to run all pipeline stages in order without requiring users to invoke each script individually, while still allowing per-stage debugging and selective force-regeneration.

## Decision

We use a **thin shell entry point** that delegates to a **Python orchestrator**, which runs stage scripts sequentially against a shared episode folder.

```
create_episode.sh  ──→  pipeline/run_pipeline.py  ──→  [stage1, stage2, …, stage9]
         │                      │
         ▼                      ▼
    forwards $@          shared episode folder
                        (all stages read/write the same data)
```

- **`create_episode.sh`** — one line: `python3 run_pipeline.py "$@"`. No logic of its own; it only gives the project a shell-native entry point so users can invoke `./create_episode.sh` from the terminal without remembering Python.

- **`pipeline/run_pipeline.py`** — sequential, imperative script that imports `subprocess`, runs each stage in order, and bails on first failure (`subprocess.run` raises `RuntimeError` on non-zero exit code). The `--force` flag is forwarded to individual stages that declare support for it.

- **Shared episode folder** — all stage scripts read from and write to the same directory (passed as the sole positional argument). There is no inter-process communication (pipes, queues, messages). Each step is a standalone process that treats the folder as its input/output medium.

## Consequences

### Positive
- **Simple to run.** One command: `./create_episode.sh <episode_folder>`.
- **Fail-fast.** Any stage returning non-zero aborts the entire pipeline immediately; no silent partial runs.
- **No new dependencies.** The orchestrator uses only Python stdlib (`subprocess`, `pathlib`, `argparse`). Each stage script can be written in whatever language/tool is appropriate for its job.
- **Selective force-regeneration.** Passing `--force` to the entry point propagates to every stage that understands it, without requiring users to hunt for per-stage flags.
- **Each stage is independently runnable and testable.** You can invoke `pipeline/analyze_scenes.py <folder>` directly for debugging without running the whole pipeline.

### Negative
- **No concurrency between stages.** The pipeline is strictly sequential — a future redesign would be needed if any stages could run in parallel.
- **No progress tracking or retry semantics.** If a stage fails, the user must fix the underlying issue and re-run from the beginning; there's no checkpoint/resume.
- **Shared folder coupling.** Stages are loosely coupled through file artifacts — there is no schema validation between steps (the `validate_transcripts.py` stage helps, but most boundaries are implicit). Corrupt output from one step silently propagates downstream until something breaks.
- **No parallelism in `create_episode.sh`.** The shell wrapper simply forwards `$@`; it doesn't add logging, timeout, or signal handling of its own (though these could be added later without changing the contract).
