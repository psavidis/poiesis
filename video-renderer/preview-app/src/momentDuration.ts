// pipeline/generate_moments.py's propose_moments() now clamps
// maxDurationInParentFrames down to the real rendered duration
// (min(the treatment's fixed length, the eligible window's ceiling)) once,
// right before writing moments.json — so for any moment written by the
// current pipeline, maxDurationInParentFrames already IS the real,
// human-editable duration, no client-side re-derivation needed.
//
// This file exists only as a defensive normalizer for moments.json files
// written by an older version of the pipeline (before that clamp existed),
// where maxDurationInParentFrames could still be the much larger raw
// window ceiling. Applied once, right after fetch (see App.tsx) — a
// moment that's already clamped is left untouched (min() is a no-op).
const TREATMENT_DURATION_FRAMES: Record<string, number> = {
    "bottom-callout": 90,
    "side-text": 150,
    "side-image": 150,
};

export function normalizeMoment<
    T extends { treatment: string; maxDurationInParentFrames: number; overriddenFields?: string[] }
>(raw: T): T {
    // A human-lengthened duration (drag-to-resize past the treatment's
    // fixed default — see merge_moment_scenes' own docstring on this being
    // a legitimate, supported edit) is by definition ABOVE `fixed`. Without
    // this check, this stale-data clamp would silently discard that exact
    // edit on every fetch/save round-trip — which is precisely what
    // overriddenFields exists to prevent (#57).
    if (raw.overriddenFields?.includes("maxDurationInParentFrames")) {
        return raw;
    }

    const fixed = TREATMENT_DURATION_FRAMES[raw.treatment] ?? raw.maxDurationInParentFrames;

    return {
        ...raw,
        maxDurationInParentFrames: Math.min(fixed, raw.maxDurationInParentFrames),
    };
}

// merge_moment_scenes (pipeline/generate_moments.py) generates
// "scene-moment-{N}" as exactly the array index of moments.json's
// proposals list — an exact, non-heuristic correlation back to a moment's
// position in that array. Shared by MomentEditorPanel and InlineTextEditor
// (see #34) so both use the identical regex rather than risking silent
// divergence between two copies of "the" correlation logic.
export function momentIndexFromSceneId(sceneId: string): number | null {
    const match = /^scene-moment-(\d+)$/.exec(sceneId);
    return match ? Number(match[1]) : null;
}
