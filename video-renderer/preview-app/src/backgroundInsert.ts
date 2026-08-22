import {
    getBackgroundInsertablePositions,
    getBackgroundScenes,
    saveBackgroundScenes,
    type BackgroundSceneProposal,
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

// Inserts a background_scenes.json entry starting at the given frame — it
// runs until whichever entry starts next (or episode end), the same auto-
// close-by-the-next-entry model generate_background_scenes.py always
// applies. Works at ANY frame, not just an empty gap: inserting inside an
// already-covered span splits it there (the existing entry's own span
// simply shortens to end at the new one's start — no separate "split"
// logic needed, purely a consequence of how durations are derived).
//
// Drops every existing entry whose OWN resolved frame is >= this insert's
// frame, not just one exact-segmentId match — positions now come from
// getBackgroundInsertablePositions, which offers both transcript-segment
// AND clip-start snap points (see its own doc comment), so two different
// inserts aimed at "the same place" can legitimately resolve to two
// different, nearby segmentIds (e.g. a clip's frame-0 start vs. its first
// spoken word a few frames later). Only matching the exact segmentId would
// leave the earlier insert's now-superseded entry behind as a same-frame
// duplicate/sliver instead of replacing it.
export async function insertBackgroundAtFrame(
    episodePath: string,
    frame: number,
    backgroundId: string,
    imageMotion?: BackgroundImageMotion,
    imageMotionSpeed?: BackgroundImageMotionSpeed
): Promise<{ ok: true; segmentId: string } | { ok: false; error: string }> {
    const positions = await getBackgroundInsertablePositions(episodePath);
    const segmentId = nearestSegmentId(positions, frame);

    if (!segmentId) {
        return { ok: false, error: "Couldn't resolve this position to a transcript segment yet — try again in a moment." };
    }

    const insertFrame = positions.find((p) => p.segmentId === segmentId)!.timelineFrame;
    const frameById = new Map(positions.map((p) => [p.segmentId, p.timelineFrame]));

    try {
        const current = await getBackgroundScenes(episodePath);
        const next = [
            ...current.filter((e) => {
                const existingFrame = frameById.get(e.segmentId);
                return existingFrame === undefined || existingFrame < insertFrame;
            }),
            {
                segmentId,
                backgroundId,
                ...(imageMotion ? { imageMotion } : {}),
                ...(imageMotionSpeed ? { imageMotionSpeed } : {}),
            },
        ];
        await saveBackgroundScenes(episodePath, next);
        return { ok: true, segmentId };
    } catch (err) {
        return { ok: false, error: String(err) };
    }
}

// Removes a background_scenes.json entry by its own segmentId — shared by
// BackgroundBar's own Delete/Backspace and BackgroundEditorPanel's Remove
// button (#91 follow-up), so both delete paths stay correct together
// rather than the fix living in only one of them (confirmed live: fixing
// this in BackgroundBar's own doDelete alone left the bug fully
// reproducible via the editor panel's Remove button instead — a SEPARATE
// plain filter-and-save with no gap-closing logic of its own).
//
// merge_background_scenes auto-closes each entry's duration at whichever
// entry starts NEXT (or episode end) — a derived value, not stored data.
// That means removing any entry EXCEPT the earliest one self-heals for
// free: the previous entry's own duration just recomputes to reach the
// next surviving entry (or episode end) at merge time. But the earliest
// entry has no PREVIOUS entry to absorb the gap it leaves — its own
// timelineStartFrame simply vanishes from the array, and nothing before
// the next surviving entry's start resolves to a background any more
// (confirmed live: deleting the first of two backgrounds left the whole
// first half with no background at all). Fixed by moving the NEXT
// surviving entry's own segmentId back to the deleted entry's — same
// "background always covers what it did before, minus only the deleted
// entry's own contribution" rule the later-entry case already gets
// automatically.
export async function deleteBackgroundScene(
    episodePath: string,
    segmentId: string
): Promise<{ ok: true } | { ok: false; error: string }> {
    try {
        const [positions, current] = await Promise.all([
            getBackgroundInsertablePositions(episodePath),
            getBackgroundScenes(episodePath),
        ]);
        const frameById = new Map(positions.map((p) => [p.segmentId, p.timelineFrame]));

        const deletedFrame = frameById.get(segmentId);
        const remaining = current.filter((e) => e.segmentId !== segmentId);

        let next: BackgroundSceneProposal[] = remaining;

        if (deletedFrame !== undefined) {
            const remainingSorted = [...remaining].sort(
                (a, b) => (frameById.get(a.segmentId) ?? 0) - (frameById.get(b.segmentId) ?? 0)
            );
            const wasEarliest = remainingSorted.every((e) => (frameById.get(e.segmentId) ?? 0) > deletedFrame);

            if (wasEarliest && remainingSorted.length > 0) {
                const survivorSegmentId = remainingSorted[0].segmentId;
                next = remaining.map((e) => (e.segmentId === survivorSegmentId ? { ...e, segmentId } : e));
            }
        }

        await saveBackgroundScenes(episodePath, next);
        return { ok: true };
    } catch (err) {
        return { ok: false, error: String(err) };
    }
}
