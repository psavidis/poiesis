import {
    getBackgroundScenes,
    getChapterBoundaryPositions,
    saveBackgroundScenes,
    type ChapterBoundaryPosition,
} from "./api";
import type { BackgroundImageMotion, BackgroundImageMotionSpeed } from "video-renderer-src/episode/types";

// Resolves an absolute timeline frame to its nearest resolvable transcript
// segmentId — background_scenes.json entries are keyed by segmentId, not
// raw frame, same as title_scenes.json (see getChapterBoundaryPositions'
// own doc comment). Shared between BackgroundBar's own Cmd+B insert and
// AssetLibraryPanel's Backgrounds tab so "insert at the playhead" means
// exactly the same thing — same resolution, same save shape — regardless
// of which UI surface the user starts from.
export function nearestSegmentId(positions: ChapterBoundaryPosition[], frame: number): string | null {
    if (positions.length === 0) return null;
    return positions.reduce((nearest, p) =>
        Math.abs(p.timelineFrame - frame) < Math.abs(nearest.timelineFrame - frame) ? p : nearest
    ).segmentId;
}

// Inserts (or overwrites, if one already resolves to the same segmentId)
// a background_scenes.json entry starting at the given frame — it runs
// until whichever entry starts next (or episode end), the same auto-
// close-by-the-next-entry model generate_background_scenes.py always
// applies. Works at ANY frame, not just an empty gap: inserting inside an
// already-covered span splits it there (the existing entry's own span
// simply shortens to end at the new one's start — no separate "split"
// logic needed, purely a consequence of how durations are derived).
export async function insertBackgroundAtFrame(
    episodePath: string,
    frame: number,
    backgroundId: string,
    imageMotion?: BackgroundImageMotion,
    imageMotionSpeed?: BackgroundImageMotionSpeed
): Promise<{ ok: true } | { ok: false; error: string }> {
    const positions = await getChapterBoundaryPositions(episodePath);
    const segmentId = nearestSegmentId(positions, frame);

    if (!segmentId) {
        return { ok: false, error: "Couldn't resolve this position to a transcript segment yet — try again in a moment." };
    }

    try {
        const current = await getBackgroundScenes(episodePath);
        const next = [
            ...current.filter((e) => e.segmentId !== segmentId),
            {
                segmentId,
                backgroundId,
                ...(imageMotion ? { imageMotion } : {}),
                ...(imageMotionSpeed ? { imageMotionSpeed } : {}),
            },
        ];
        await saveBackgroundScenes(episodePath, next);
        return { ok: true };
    } catch (err) {
        return { ok: false, error: String(err) };
    }
}
