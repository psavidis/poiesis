# ADR 002: Use WhisperKit CLI for Transcription

* **Status:** Accepted
* **Date:** 2026-08-21

## Context

Poiesis initially used Whisper for local transcription.

On Apple Silicon, Whisper was unexpectedly slow and emitted warnings indicating that parts of the selected compute path were falling back to CPU execution due to an unsupported/incompatible integer/compute configuration.

This meant the Apple Silicon GPU acceleration was not being effectively utilized.

For a video-production pipeline, this made transcription a significant bottleneck.

## Decision

Use **WhisperKit CLI** as the default local transcription engine on Apple Silicon.

WhisperKit provides an Apple-optimized execution path that makes effective use of Apple Silicon hardware instead of the CPU fallback experienced with the previous Whisper setup.

## Result

The switch improved transcription performance by **more than 12×** in the tested Poiesis workload.

The pipeline went from:

```text
Whisper
  → CPU fallback
  → slow transcription
```

to:

```text
WhisperKit CLI
  → Apple Silicon acceleration
  → 12×+ faster transcription
```

This significantly reduces the time required to process an episode.

## Consequences

**Positive**

* 12×+ faster transcription in the tested workload.
* Better utilization of Apple Silicon hardware.
* Faster overall Poiesis processing.
* Local transcription remains possible without a cloud service.

**Negative**

* Adds a dependency on WhisperKit.
* The implementation is currently optimized primarily for Apple Silicon.

## Architectural Note

WhisperKit should remain behind a Poiesis transcription abstraction so that the underlying transcription engine can be replaced in the future without affecting the rest of the pipeline.

> **Use the transcription implementation that actually utilizes the available hardware rather than one that silently falls back to CPU execution.**
