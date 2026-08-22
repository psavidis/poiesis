import { useEffect, useRef, useState } from "react";
import type {
    BackgroundImageMotion,
    BackgroundImageMotionSpeed,
    BackgroundScene,
    EpisodeBackground,
    ScenePlan,
} from "video-renderer-src/episode/types";
import { getBackgroundInsertablePositions, getBackgroundScenes, saveBackgroundScenes, type ChapterBoundaryPosition } from "./api";
import { insertBackgroundAtFrame, nearestSegmentId } from "./backgroundInsert";
import { colors, radius, typography } from "./tokens";
import type { TimelineZoom } from "./useTimelineZoom";

// "does not distract" is a hard design constraint (see BackgroundImageMotion's
// own doc comment in types.ts) — fixed, non-tunable directions, no
// intensity slider (speed is its own separate fixed-preset choice, see
// IMAGE_MOTION_SPEED_OPTIONS below).
// Exported so AssetLibraryPanel's own Backgrounds tab can reuse the exact
// same option set/labels rather than a second, independently-maintained
// copy — both surfaces insert through the same shared
// backgroundInsert.ts helper and should offer identical choices.
export const IMAGE_MOTION_OPTIONS: { value: BackgroundImageMotion; label: string }[] = [
    { value: "none", label: "No motion" },
    { value: "zoom-in", label: "Zoom in" },
    { value: "zoom-out", label: "Zoom out" },
    { value: "palindrome", label: "Zoom in/out" },
];

// How much the drift scales — a second, independent choice from
// direction (see BackgroundImageMotionSpeed's own doc comment). Five
// numbered levels (#119, replacing the old subtle/normal/strong preset
// names — level "1" here is what used to be "strong", since even that
// read as barely-there motion). "3" is the default; shown in the middle
// rather than "1" being the implied default, since "3" is what a fresh
// pick lands on if the user doesn't touch this row at all.
export const IMAGE_MOTION_SPEED_OPTIONS: { value: BackgroundImageMotionSpeed; label: string }[] = [
    { value: "1", label: "1" },
    { value: "2", label: "2" },
    { value: "3", label: "3" },
    { value: "4", label: "4" },
    { value: "5", label: "5" },
];

// One distinct color per background in the library, assigned by the
// background's own position in the (stable, append-only — see
// index_backgrounds.py) library list rather than randomly, so a given
// background always renders the same color across reloads/re-renders.
// Cycles if there are ever more backgrounds than colors.
const BACKGROUND_SEGMENT_COLORS = [
    colors.timelineImage,
    colors.timelineText,
    colors.timelineBeat,
    colors.timelineMomentCode,
    colors.timelineVisual,
    colors.timelineTitle,
];
// The implicit "no override — presenter's own natural footage" gap
// between/before background spans — rendered so the bar always shows
// something across the WHOLE episode even with zero backgrounds
// inserted, matching "even if absent, there should be a bar." Unlike a
// real BackgroundScene segment, a gap is not independently selectable —
// clicking it just seeks, exactly like empty track space on BeatBar/
// MomentBar/ImageBar.
const EMPTY_COLOR = colors.borderStrong;

const MOD_KEY_LABEL = navigator.platform.toLowerCase().includes("mac") ? "Cmd" : "Ctrl";

interface Props {
    scenePlan: ScenePlan;
    totalFrames: number;
    onSeek: (absoluteFrame: number) => void;
    episodePath: string;
    onSaved: () => void;
    backgrounds: EpisodeBackground[];
    timelineZoom: TimelineZoom;
    // Live read of the player's actual current frame — used when opening/
    // committing an insert, since `frameupdate`-derived state only
    // updates on the next event and can lag the true playhead by a
    // couple of frames (see EpisodeWorkspace.tsx).
    getCurrentFrame: () => number;
    // See BeatBar's identical prop's own doc comment — mutual-exclusion
    // signal so this bar's selection (and its Cmd+E listener) clears
    // itself once a different bar becomes the active selection owner.
    activeSelectionBar: string | null;
    onActivateSelection: () => void;
}

// One "gap" (no background) or "span" (an inserted background, running
// until the next span/gap starts) segment for rendering — derived from
// BackgroundScene[] plus the implicit gaps between them, since
// scene-plan.json itself only ever stores the INSERTED spans, never the
// empty stretches (see BackgroundScene's own doc comment: absent means
// natural footage, not a synthetic "none" entry).
type Segment = {
    backgroundId: string | null;
    startFrame: number;
    endFrame: number;
    imageMotion?: BackgroundImageMotion;
    imageMotionSpeed?: BackgroundImageMotionSpeed;
};

function segmentsFromBackgroundScenes(scenes: BackgroundScene[], totalFrames: number): Segment[] {
    const sorted = [...scenes].sort((a, b) => a.timelineStartFrame - b.timelineStartFrame);

    const segments: Segment[] = [];
    let cursor = 0;

    for (const scene of sorted) {
        if (scene.timelineStartFrame > cursor) {
            segments.push({ backgroundId: null, startFrame: cursor, endFrame: scene.timelineStartFrame });
        }
        segments.push({
            backgroundId: scene.backgroundId,
            startFrame: scene.timelineStartFrame,
            endFrame: scene.timelineStartFrame + scene.durationInFrames,
            imageMotion: scene.imageMotion,
            imageMotionSpeed: scene.imageMotionSpeed,
        });
        cursor = scene.timelineStartFrame + scene.durationInFrames;
    }

    if (cursor < totalFrames) {
        segments.push({ backgroundId: null, startFrame: cursor, endFrame: totalFrames });
    }

    return segments;
}

// Same select/insert/Delete lifecycle as MomentBar (#87, revised) — NOT a
// "select any span (including empty ones), then pick or clear" model.
// Clicking a real background segment selects it (Delete/Backspace
// removes it, inline-confirmed like every other bar); clicking empty
// track space just seeks, exactly like MomentBar's own empty stretches.
// Cmd+B at the playhead inserts a NEW background there — it runs from
// that point to wherever the next inserted background starts (or the
// episode's end), the same auto-closed-by-the-next-entry model
// generate_background_scenes.py already implements. There's no "kind"
// picker the way MomentBar's Cmd+I has (side-text vs side-image vs...) —
// the only decision is WHICH background, so Cmd+B opens that chooser
// directly. Cmd+B rather than Cmd+I specifically to avoid colliding with
// MomentBar's own Cmd+I, which fires at nearly every playhead position.
export function BackgroundBar({
    scenePlan,
    totalFrames,
    onSeek,
    episodePath,
    onSaved,
    backgrounds,
    timelineZoom,
    getCurrentFrame,
    activeSelectionBar,
    onActivateSelection,
}: Props) {
    const { windowFrames, windowStartFrame, frameToPct, playheadPct, playheadVisible, zoomToAtLeast4x } =
        timelineZoom;

    const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

    // See BeatBar's identical effect's own doc comment — clears this bar's
    // selection once a different bar takes over the shared selection.
    useEffect(() => {
        if (activeSelectionBar !== "background") setSelectedIndex(null);
    }, [activeSelectionBar]);
    const [pendingDeleteIndex, setPendingDeleteIndex] = useState<number | null>(null);
    const [insertPickerAnchor, setInsertPickerAnchor] = useState<{ x: number; y: number } | null>(null);
    // The frame the insert picker was opened at (Cmd+B keydown), captured
    // once via getCurrentFrame() rather than re-read later when the user
    // actually picks a background — see getCurrentFrame's own doc comment.
    const insertFrameRef = useRef(0);
    const [inserting, setInserting] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const trackRef = useRef<HTMLDivElement>(null);
    // Cmd+E on a selected IMAGE background segment opens this — the
    // motion editor (see MotionEditor below), same select-then-Cmd+E
    // lifecycle every other editable property in this app already uses.
    // Anchor captured at click time, same pattern as insertPickerAnchor.
    const [motionEditorAnchor, setMotionEditorAnchor] = useState<{ x: number; y: number } | null>(null);
    const [updatingMotion, setUpdatingMotion] = useState(false);
    const selectedAnchorRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

    // Every position a background can resolve to — transcript segment
    // starts plus each presenter piece's own clip-start frame (see
    // getBackgroundInsertablePositions) — needed here to resolve both a
    // NEW insert at the playhead and an EXISTING segment's derived
    // startFrame (segmentsFromBackgroundScenes) back to a real segmentId
    // (background_scenes.json entries are keyed by segmentId, not raw
    // frame, same as title_scenes.json). Must include the clip-start
    // entries, not just getChapterBoundaryPositions's transcript-only
    // ones — an existing background positioned via a "clip:..." id
    // (inserted at a clip's exact start) would otherwise never re-resolve
    // back to itself here.
    const [boundaryPositions, setBoundaryPositions] = useState<ChapterBoundaryPosition[]>([]);
    useEffect(() => {
        let cancelled = false;
        getBackgroundInsertablePositions(episodePath).then((positions) => {
            if (!cancelled) setBoundaryPositions(positions);
        });
        return () => {
            cancelled = true;
        };
    }, [episodePath]);

    const nearestSegmentIdForFrame = (frame: number): string | null => nearestSegmentId(boundaryPositions, frame);

    if (totalFrames <= 0) return null;

    const backgroundScenes = scenePlan.scenes.filter((s): s is BackgroundScene => s.type === "background");
    const segments = segmentsFromBackgroundScenes(backgroundScenes, totalFrames);
    const backgroundById = new Map(backgrounds.map((b) => [b.id, b]));
    const colorByBackgroundId = new Map(
        backgrounds.map((b, i) => [b.id, BACKGROUND_SEGMENT_COLORS[i % BACKGROUND_SEGMENT_COLORS.length]])
    );

    // Cmd+B (Mac) / Ctrl+B (elsewhere) opens the background chooser at
    // the playhead — works at ANY position, not just an empty gap. A
    // background already covering the playhead's own position is simply
    // split there: the new entry starts at the playhead and the existing
    // one's own span shortens to end there, the same auto-close-by-the-
    // next-entry model generate_background_scenes.py already implements
    // (no separate "split" logic needed — inserting a new entry with a
    // later timelineStartFrame than an existing one already does this).
    // Previously this required an empty gap under the playhead, which
    // meant Cmd+B silently did nothing anywhere past the FIRST inserted
    // background, since one background covering the rest of the episode
    // (the normal state right after any insert) leaves no gap left to
    // click into — confirmed live as the actual cause of "I can't insert
    // a second background."
    //
    // Doesn't require a selection first (inserting is independent of
    // selection, matching MomentBar's own Cmd+I rule). Deliberately NOT
    // Cmd+I: MomentBar's Cmd+I only checks for a presenter scene under
    // the playhead, which is true almost anywhere a background gap also
    // is, so sharing the shortcut opened BOTH bars' insert pickers at
    // once (confirmed live) — a distinct shortcut avoids that collision
    // entirely rather than trying to arbitrate whose Cmd+I "wins" at a
    // given playhead position.
    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "b" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
            if (!trackRef.current || backgrounds.length === 0) return;

            e.preventDefault();
            const rect = trackRef.current.getBoundingClientRect();
            const frame = getCurrentFrame();
            insertFrameRef.current = frame;
            setPendingDeleteIndex(null);
            setInsertPickerAnchor({ x: rect.left + frameToPct(frame) * (rect.width / 100), y: rect.bottom });
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [backgrounds.length, getCurrentFrame]);

    // Only an image background has a motion setting to edit — a video
    // background already has its own motion, so Cmd+E is a no-op there
    // (mirrors MomentBar's own "no valid target, no-op" rule for Cmd+E
    // when the selected moment has nothing text-eligible).
    const selectedSegment = selectedIndex !== null ? segments[selectedIndex] : undefined;
    const selectedIsImage =
        selectedSegment?.backgroundId != null &&
        backgroundById.get(selectedSegment.backgroundId)?.mediaType === "image";

    // Cmd+E on a selected image background segment opens the motion
    // editor — same select-then-Cmd+E convention as every other editable
    // property in this app.
    useEffect(() => {
        if (selectedIndex === null || !selectedIsImage) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "e" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            setMotionEditorAnchor(selectedAnchorRef.current);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedIndex, selectedIsImage]);

    // Delete/Backspace on a selected background segment shows the inline
    // confirm — same pattern as every other bar.
    useEffect(() => {
        if (selectedIndex === null) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key !== "Delete" && e.key !== "Backspace") return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            setPendingDeleteIndex(selectedIndex);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedIndex]);

    useEffect(() => {
        if (pendingDeleteIndex === null) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") setPendingDeleteIndex(null);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [pendingDeleteIndex]);

    // Inserts a new background_scenes.json entry starting at the given
    // frame's nearest resolvable segment — it runs until whichever entry
    // starts next (or episode end), same auto-close model as every other
    // insert here. Overwrites any entry already resolving to that exact
    // segmentId rather than duplicating it (shouldn't normally happen
    // since Cmd+I only opens over a gap, but stays correct if segment
    // resolution snaps two nearby frames to the same segmentId).
    // imageMotion/imageMotionSpeed are only meaningful for an image pick
    // — passed through regardless (harmless/ignored by the renderer for a
    // video pick), so the picker doesn't need to know the background's
    // own mediaType to decide whether to send them.
    const doInsert = async (
        backgroundId: string,
        imageMotion?: BackgroundImageMotion,
        imageMotionSpeed?: BackgroundImageMotionSpeed
    ) => {
        setInserting(true);
        setSaveError(null);

        const result = await insertBackgroundAtFrame(episodePath, insertFrameRef.current, backgroundId, imageMotion, imageMotionSpeed);

        if (result.ok) {
            onSaved();
            setInsertPickerAnchor(null);
        } else {
            setSaveError(result.error);
        }

        setInserting(false);
    };

    // Updates the imageMotion/imageMotionSpeed fields of the selected
    // segment's own entry — matched by its resolved start frame's nearest
    // segmentId, same identity approach doDelete already uses (a merged
    // BackgroundScene carries no segmentId of its own to match against
    // directly).
    const doUpdateMotion = async (imageMotion: BackgroundImageMotion, imageMotionSpeed: BackgroundImageMotionSpeed) => {
        if (selectedIndex === null) return;
        const segment = segments[selectedIndex];
        if (!segment?.backgroundId) return;

        setUpdatingMotion(true);
        setSaveError(null);

        try {
            const segmentId = nearestSegmentIdForFrame(segment.startFrame);
            const current = await getBackgroundScenes(episodePath);
            const index = current.findIndex((e) => e.segmentId === segmentId);
            if (index === -1) return;

            const next = current.map((e, i) => (i === index ? { ...e, imageMotion, imageMotionSpeed } : e));
            await saveBackgroundScenes(episodePath, next);
            onSaved();
            setMotionEditorAnchor(null);
        } catch (err) {
            setSaveError(String(err));
        } finally {
            setUpdatingMotion(false);
        }
    };

    // Removes the background_scenes.json entry resolving to the selected
    // segment's own start frame — same "fetch fresh, filter, save the
    // whole array" contract as every other bar's doDelete.
    const doDelete = async () => {
        if (pendingDeleteIndex === null) return;
        const segment = segments[pendingDeleteIndex];
        if (!segment) return;

        try {
            const current = await getBackgroundScenes(episodePath);
            const segmentId = nearestSegmentIdForFrame(segment.startFrame);
            const next = current.filter((e) => e.segmentId !== segmentId);
            await saveBackgroundScenes(episodePath, next);
            onSaved();
            setPendingDeleteIndex(null);
            setSelectedIndex(null);
        } catch (err) {
            setSaveError(String(err));
        }
    };

    const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
        setSelectedIndex(null);
        setPendingDeleteIndex(null);
        // Claims activeSelectionBar even though this click doesn't select a
        // particular background (#86 follow-up, matches every other bar's
        // own onTrackClick) — without this, a plain click into this track
        // to position the playhead left whatever bar was last selected
        // owning the shared shortcuts instead of this one.
        onActivateSelection();
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
        onSeek(Math.round(windowStartFrame + pct * windowFrames));
    };

    return (
        <div style={styles.wrap}>
            <div style={styles.label}>Background</div>

            <div ref={trackRef} style={styles.track} onMouseDown={onTrackClick}>
                {segments.map((segment, i) => {
                    const leftPct = frameToPct(segment.startFrame);
                    const rawWidthPct = ((segment.endFrame - segment.startFrame) / windowFrames) * 100;

                    if (leftPct + rawWidthPct < 0 || leftPct > 100) return null;

                    const widthPct = Math.max(rawWidthPct, 0.4);
                    const isReal = segment.backgroundId !== null;
                    const background = segment.backgroundId ? backgroundById.get(segment.backgroundId) : undefined;
                    const label = isReal ? background?.caption ?? segment.backgroundId! : "";
                    const isSelected = isReal && selectedIndex === i;

                    return (
                        <div
                            key={i}
                            style={{
                                ...styles.segment,
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                background: isReal
                                    ? colorByBackgroundId.get(segment.backgroundId!) ?? BACKGROUND_SEGMENT_COLORS[0]
                                    : EMPTY_COLOR,
                                cursor: isReal ? "pointer" : "default",
                                ...(isSelected ? styles.segmentSelected : {}),
                            }}
                            title={
                                isSelected
                                    ? background?.mediaType === "image"
                                        ? `${label} — press ${MOD_KEY_LABEL}+E to change its motion, Delete/Backspace to remove`
                                        : `${label} — press Delete/Backspace to remove`
                                    : isReal
                                    ? `Click to select: ${label}`
                                    : `No background — press ${MOD_KEY_LABEL}+B here to insert one`
                            }
                            onClick={
                                isReal
                                    ? (e) => {
                                          e.stopPropagation();
                                          selectedAnchorRef.current = { x: e.clientX, y: e.clientY };
                                          onActivateSelection();
                                          setSelectedIndex(i);
                                          setPendingDeleteIndex(null);
                                          // Seeks to the CLICKED position, not the
                                          // segment's own start — unlike every
                                          // other bar's segments (moments/beats/
                                          // images, all short), a background span
                                          // routinely covers most or all of the
                                          // episode, so "jump to this segment's
                                          // start" reads as "clicking anywhere
                                          // resets the playhead to the beginning"
                                          // and silently defeated Cmd+B's own
                                          // "insert at the playhead" contract
                                          // (confirmed live: a click meant to
                                          // position the playhead partway through
                                          // a long background actually snapped it
                                          // back to frame 0, so the very next
                                          // Cmd+B resolved to the SAME segmentId
                                          // as the existing entry and silently
                                          // overwrote it instead of splitting).
                                          const rect = trackRef.current?.getBoundingClientRect();
                                          const clickedFrame = rect
                                              ? Math.round(
                                                    windowStartFrame +
                                                        clamp((e.clientX - rect.left) / rect.width, 0, 1) * windowFrames
                                                )
                                              : segment.startFrame;
                                          onSeek(clickedFrame);
                                          zoomToAtLeast4x(clickedFrame);
                                      }
                                    : undefined
                            }
                        >
                            {isReal && widthPct > 3 && <span style={styles.segmentLabel}>{label}</span>}
                        </div>
                    );
                })}

                {playheadVisible && <div style={{ ...styles.playhead, left: `${playheadPct}%` }} />}
            </div>

            {insertPickerAnchor && (
                <BackgroundPicker
                    anchor={insertPickerAnchor}
                    backgrounds={backgrounds}
                    disabled={inserting}
                    onPick={doInsert}
                    onClose={() => setInsertPickerAnchor(null)}
                />
            )}

            {motionEditorAnchor && selectedSegment && (
                <MotionEditor
                    anchor={motionEditorAnchor}
                    currentMotion={selectedSegment.imageMotion ?? "none"}
                    currentSpeed={selectedSegment.imageMotionSpeed ?? "3"}
                    disabled={updatingMotion}
                    onPick={doUpdateMotion}
                    onClose={() => setMotionEditorAnchor(null)}
                />
            )}

            {saveError && <div style={styles.error}>{saveError}</div>}

            {pendingDeleteIndex !== null && (
                <div style={styles.deleteConfirm}>
                    <span>Remove this background?</span>
                    <button type="button" className="secondary small" onClick={doDelete} style={styles.deleteButton}>
                        Remove
                    </button>
                    <button type="button" className="secondary small" onClick={() => setPendingDeleteIndex(null)}>
                        Cancel
                    </button>
                </div>
            )}

            <div style={styles.hint}>
                {backgrounds.length === 0
                    ? "No files in this episode's background/ folder yet."
                    : selectedIndex !== null
                    ? selectedIsImage
                        ? `Selected — press ${MOD_KEY_LABEL}+E to change its motion, Delete/Backspace to remove it.`
                        : "Selected — press Delete/Backspace to remove it."
                    : `Press ${MOD_KEY_LABEL}+B at the playhead to insert a background — it runs until the next one or the episode's end.`}
            </div>
        </div>
    );
}

// Cmd+B's chooser — a small fixed-position popup near wherever the
// shortcut was pressed, same pattern as MomentBar's own InsertTypePicker,
// just choosing WHICH background instead of which moment kind (there's
// only one "kind" here). An IMAGE entry expands into a direction row
// (see IMAGE_MOTION_OPTIONS); picking any direction other than "none"
// expands further into a speed row (see IMAGE_MOTION_SPEED_OPTIONS) —
// direction and speed are two independent choices, so this is a
// two-step nested reveal rather than one flat list of every direction×
// speed combination. A video entry has no motion setting at all, so
// it's a single one-click insert.
function BackgroundPicker({
    anchor,
    backgrounds,
    disabled,
    onPick,
    onClose,
}: {
    anchor: { x: number; y: number };
    backgrounds: EpisodeBackground[];
    disabled: boolean;
    onPick: (backgroundId: string, imageMotion?: BackgroundImageMotion, imageMotionSpeed?: BackgroundImageMotionSpeed) => void;
    onClose: () => void;
}) {
    const boxRef = useRef<HTMLDivElement>(null);
    // Which image entry's direction row is expanded — at most one at a
    // time, collapsed again on outside click/Escape same as the picker
    // itself. A video entry has no expanded state (single click inserts
    // immediately).
    const [expandedImageId, setExpandedImageId] = useState<string | null>(null);
    // Which direction (within the currently-expanded image) has its own
    // speed row expanded — "none" never expands further, there's nothing
    // to tune about no motion.
    const [expandedMotion, setExpandedMotion] = useState<BackgroundImageMotion | null>(null);

    useEffect(() => {
        const onOutsideClick = (e: MouseEvent) => {
            if (boxRef.current && !boxRef.current.contains(e.target as Node)) onClose();
        };
        document.addEventListener("mousedown", onOutsideClick);
        return () => document.removeEventListener("mousedown", onOutsideClick);
    }, [onClose]);

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [onClose]);

    // Clamp so the box stays on screen even when the anchor is near an
    // edge — same calibration as InlineTextEditor's own clamp.
    const left = Math.min(Math.max(anchor.x - 110, 8), window.innerWidth - 228);
    const top = Math.min(anchor.y + 8, window.innerHeight - 8);

    return (
        <div
            ref={boxRef}
            style={{ ...styles.picker, left, top }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
        >
            {backgrounds.map((b) => {
                const isImage = b.mediaType === "image";
                const isExpanded = expandedImageId === b.id;

                return (
                    <div key={b.id}>
                        <button
                            type="button"
                            className="secondary small"
                            style={styles.pickerOption}
                            disabled={disabled}
                            onClick={() => {
                                if (!isImage) {
                                    onPick(b.id);
                                    return;
                                }
                                setExpandedImageId(isExpanded ? null : b.id);
                                setExpandedMotion(null);
                            }}
                        >
                            {b.caption || b.filename} ({b.mediaType})
                        </button>
                        {isExpanded && (
                            <div style={styles.motionRow}>
                                {IMAGE_MOTION_OPTIONS.map((option) => {
                                    if (option.value === "none") {
                                        return (
                                            <button
                                                key={option.value}
                                                type="button"
                                                className="secondary small"
                                                style={styles.motionOption}
                                                disabled={disabled}
                                                onClick={() => onPick(b.id, "none")}
                                            >
                                                {option.label}
                                            </button>
                                        );
                                    }

                                    const isSpeedExpanded = expandedMotion === option.value;

                                    return (
                                        <div key={option.value}>
                                            <button
                                                type="button"
                                                className="secondary small"
                                                style={styles.motionOption}
                                                disabled={disabled}
                                                onClick={() => setExpandedMotion(isSpeedExpanded ? null : option.value)}
                                            >
                                                {option.label}
                                            </button>
                                            {isSpeedExpanded && (
                                                <div style={styles.speedRow}>
                                                    {IMAGE_MOTION_SPEED_OPTIONS.map((speedOption) => (
                                                        <button
                                                            key={speedOption.value}
                                                            type="button"
                                                            className="secondary small"
                                                            style={styles.speedOption}
                                                            disabled={disabled}
                                                            onClick={() => onPick(b.id, option.value, speedOption.value)}
                                                        >
                                                            {speedOption.label}
                                                        </button>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

// Cmd+E's editor for an already-inserted image background's own motion —
// same nested direction->speed reveal as the insert picker's expanded
// image row, just without the file choice (that's fixed once inserted;
// changing the FILE means removing and re-inserting, same as every other
// bar's own "delete + re-add to change identity" convention). Pre-opens
// the current direction's speed row so both current choices are visible
// at once, rather than requiring the user to re-click through the same
// nesting just to see what's already selected.
function MotionEditor({
    anchor,
    currentMotion,
    currentSpeed,
    disabled,
    onPick,
    onClose,
}: {
    anchor: { x: number; y: number };
    currentMotion: BackgroundImageMotion;
    currentSpeed: BackgroundImageMotionSpeed;
    disabled: boolean;
    onPick: (motion: BackgroundImageMotion, speed: BackgroundImageMotionSpeed) => void;
    onClose: () => void;
}) {
    const boxRef = useRef<HTMLDivElement>(null);
    const [expandedMotion, setExpandedMotion] = useState<BackgroundImageMotion | null>(
        currentMotion !== "none" ? currentMotion : null
    );

    useEffect(() => {
        const onOutsideClick = (e: MouseEvent) => {
            if (boxRef.current && !boxRef.current.contains(e.target as Node)) onClose();
        };
        document.addEventListener("mousedown", onOutsideClick);
        return () => document.removeEventListener("mousedown", onOutsideClick);
    }, [onClose]);

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [onClose]);

    const left = Math.min(Math.max(anchor.x - 110, 8), window.innerWidth - 228);
    const top = Math.min(anchor.y + 8, window.innerHeight - 8);

    return (
        <div
            ref={boxRef}
            style={{ ...styles.picker, left, top }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
        >
            {IMAGE_MOTION_OPTIONS.map((option) => {
                const isActiveDirection = option.value === currentMotion;

                if (option.value === "none") {
                    return (
                        <button
                            key={option.value}
                            type="button"
                            className="secondary small"
                            style={{ ...styles.pickerOption, ...(isActiveDirection ? styles.pickerOptionActive : {}) }}
                            disabled={disabled}
                            onClick={() => onPick("none", currentSpeed)}
                        >
                            {option.label}
                        </button>
                    );
                }

                const isSpeedExpanded = expandedMotion === option.value;

                return (
                    <div key={option.value}>
                        <button
                            type="button"
                            className="secondary small"
                            style={{ ...styles.pickerOption, ...(isActiveDirection ? styles.pickerOptionActive : {}) }}
                            disabled={disabled}
                            onClick={() => setExpandedMotion(isSpeedExpanded ? null : option.value)}
                        >
                            {option.label}
                        </button>
                        {isSpeedExpanded && (
                            <div style={styles.speedRow}>
                                {IMAGE_MOTION_SPEED_OPTIONS.map((speedOption) => (
                                    <button
                                        key={speedOption.value}
                                        type="button"
                                        className="secondary small"
                                        style={{
                                            ...styles.speedOption,
                                            ...(isActiveDirection && speedOption.value === currentSpeed
                                                ? styles.pickerOptionActive
                                                : {}),
                                        }}
                                        disabled={disabled}
                                        onClick={() => onPick(option.value, speedOption.value)}
                                    >
                                        {speedOption.label}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 6,
    },
    label: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
    },
    track: {
        position: "relative",
        height: 28,
        borderRadius: radius.md,
        overflow: "hidden",
        border: `1px solid ${colors.border}`,
        userSelect: "none",
        cursor: "pointer",
    },
    segment: {
        position: "absolute",
        top: 0,
        bottom: 0,
        display: "flex",
        alignItems: "center",
        borderRight: "1px solid rgba(0,0,0,0.35)",
        overflow: "visible",
    },
    segmentSelected: {
        boxShadow: "inset 0 0 0 2px #ffffff, 0 0 8px rgba(255,255,255,0.5)",
        zIndex: 1,
    },
    segmentLabel: {
        padding: "0 6px",
        fontSize: 10,
        fontWeight: typography.weight.semibold,
        color: "#fff",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        textShadow: "0 1px 2px rgba(0,0,0,0.5)",
    },
    playhead: {
        position: "absolute",
        top: 0,
        bottom: 0,
        width: 2,
        background: colors.playhead,
        pointerEvents: "none",
        boxShadow: "0 0 4px rgba(255,90,60,0.8)",
    },
    error: {
        fontSize: typography.size.sm,
        color: colors.error,
    },
    hint: {
        fontSize: typography.size.xs,
        color: colors.textMuted,
    },
    deleteConfirm: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px",
        background: colors.surfaceElevated,
        border: `1px solid ${colors.errorStrong}`,
        borderRadius: radius.md,
        fontSize: typography.size.sm,
        color: colors.textPrimary,
    },
    deleteButton: {
        color: colors.error,
        borderColor: colors.errorStrong,
    },
    picker: {
        position: "fixed",
        display: "flex",
        flexDirection: "column",
        gap: 4,
        padding: 8,
        background: colors.surfaceElevated,
        border: `1px solid ${colors.borderStrong}`,
        borderRadius: radius.md,
        boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
        zIndex: 50,
        minWidth: 220,
    },
    pickerOption: {
        textAlign: "left",
        fontSize: typography.size.sm,
        width: "100%",
    },
    pickerOptionActive: {
        borderColor: colors.accent,
    },
    motionRow: {
        display: "flex",
        flexDirection: "column",
        gap: 4,
        marginTop: 4,
        marginLeft: 12,
        paddingLeft: 8,
        borderLeft: `2px solid ${colors.border}`,
    },
    motionOption: {
        textAlign: "left",
        fontSize: typography.size.xs,
    },
    speedRow: {
        display: "flex",
        flexDirection: "row",
        gap: 4,
        marginTop: 4,
        marginLeft: 12,
        paddingLeft: 8,
        borderLeft: `2px solid ${colors.border}`,
    },
    speedOption: {
        textAlign: "center",
        fontSize: typography.size.xs,
        flex: 1,
    },
};
