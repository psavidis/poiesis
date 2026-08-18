import { useEffect, useRef, useState } from "react";
import type { BackgroundImageMotion, BackgroundScene, EpisodeBackground, ScenePlan } from "video-renderer-src/episode/types";
import {
    getBackgroundScenes,
    getChapterBoundaryPositions,
    saveBackgroundScenes,
    type ChapterBoundaryPosition,
} from "./api";
import { colors, radius, typography } from "./tokens";
import type { TimelineZoom } from "./useTimelineZoom";

// "does not distract" is a hard design constraint (see BackgroundImageMotion's
// own doc comment in types.ts) — three fixed, non-tunable directions, no
// intensity slider.
const IMAGE_MOTION_OPTIONS: { value: BackgroundImageMotion; label: string }[] = [
    { value: "none", label: "No motion" },
    { value: "zoom-in", label: "Slow zoom in" },
    { value: "zoom-out", label: "Slow zoom out" },
    { value: "palindrome", label: "Slow zoom in/out" },
];

const BACKGROUND_COLOR = colors.timelineImage;
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
    currentFrame: number;
    onSeek: (absoluteFrame: number) => void;
    episodePath: string;
    onSaved: () => void;
    backgrounds: EpisodeBackground[];
    timelineZoom: TimelineZoom;
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
    currentFrame,
    onSeek,
    episodePath,
    onSaved,
    backgrounds,
    timelineZoom,
}: Props) {
    const { windowFrames, windowStartFrame, frameToPct, playheadPct, playheadVisible, zoomToAtLeast4x } =
        timelineZoom;

    const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
    const [pendingDeleteIndex, setPendingDeleteIndex] = useState<number | null>(null);
    const [insertPickerAnchor, setInsertPickerAnchor] = useState<{ x: number; y: number } | null>(null);
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

    // Every transcript segment's resolved timeline frame — the same
    // snapping data ChapterStrip's boundary drag uses, needed here to
    // resolve "insert a background starting at the playhead" to a real
    // segmentId (background_scenes.json entries are keyed by segmentId,
    // not raw frame, same as title_scenes.json).
    const [boundaryPositions, setBoundaryPositions] = useState<ChapterBoundaryPosition[]>([]);
    useEffect(() => {
        let cancelled = false;
        getChapterBoundaryPositions(episodePath).then((positions) => {
            if (!cancelled) setBoundaryPositions(positions);
        });
        return () => {
            cancelled = true;
        };
    }, [episodePath]);

    const nearestSegmentIdForFrame = (frame: number): string | null => {
        if (boundaryPositions.length === 0) return null;
        return boundaryPositions.reduce((nearest, p) =>
            Math.abs(p.timelineFrame - frame) < Math.abs(nearest.timelineFrame - frame) ? p : nearest
        ).segmentId;
    };

    if (totalFrames <= 0) return null;

    const backgroundScenes = scenePlan.scenes.filter((s): s is BackgroundScene => s.type === "background");
    const segments = segmentsFromBackgroundScenes(backgroundScenes, totalFrames);
    const backgroundById = new Map(backgrounds.map((b) => [b.id, b]));

    // The gap (if any) the playhead currently sits inside — Cmd+B only
    // does something meaningful there; a playhead already inside a real
    // background segment has nothing to insert (mirrors MomentBar's own
    // "requires a presenter scene under the playhead" gate).
    const gapAtPlayhead = segments.find(
        (s) => s.backgroundId === null && currentFrame >= s.startFrame && currentFrame < s.endFrame
    );

    // Cmd+B (Mac) / Ctrl+B (elsewhere) opens the background chooser at
    // the playhead — global, doesn't require a selection first (inserting
    // is independent of selection, matching MomentBar's own Cmd+I rule).
    // Deliberately NOT Cmd+I: MomentBar's Cmd+I only checks for a
    // presenter scene under the playhead, which is true almost anywhere a
    // background gap also is, so sharing the shortcut opened BOTH bars'
    // insert pickers at once (confirmed live) — a distinct shortcut avoids
    // that collision entirely rather than trying to arbitrate whose
    // Cmd+I "wins" at a given playhead position.
    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "b" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
            if (!gapAtPlayhead || !trackRef.current || backgrounds.length === 0) return;

            e.preventDefault();
            const rect = trackRef.current.getBoundingClientRect();
            setPendingDeleteIndex(null);
            setInsertPickerAnchor({ x: rect.left + frameToPct(currentFrame) * (rect.width / 100), y: rect.bottom });
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [gapAtPlayhead?.startFrame, currentFrame, backgrounds.length]);

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
    // imageMotion is only meaningful for an image pick — passed through
    // regardless (harmless/ignored by the renderer for a video pick), so
    // the picker doesn't need to know the background's own mediaType to
    // decide whether to send it.
    const doInsert = async (backgroundId: string, imageMotion?: BackgroundImageMotion) => {
        setInserting(true);
        setSaveError(null);

        try {
            const segmentId = nearestSegmentIdForFrame(currentFrame);
            if (!segmentId) {
                setSaveError("Couldn't resolve this position to a transcript segment yet — try again in a moment.");
                return;
            }

            const current = await getBackgroundScenes(episodePath);
            const next = [
                ...current.filter((e) => e.segmentId !== segmentId),
                { segmentId, backgroundId, ...(imageMotion ? { imageMotion } : {}) },
            ];
            await saveBackgroundScenes(episodePath, next);
            onSaved();
            setInsertPickerAnchor(null);
        } catch (err) {
            setSaveError(String(err));
        } finally {
            setInserting(false);
        }
    };

    // Updates ONLY the imageMotion field of the selected segment's own
    // entry — matched by its resolved start frame's nearest segmentId,
    // same identity approach doDelete already uses (a merged
    // BackgroundScene carries no segmentId of its own to match against
    // directly).
    const doUpdateMotion = async (imageMotion: BackgroundImageMotion) => {
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

            const next = current.map((e, i) => (i === index ? { ...e, imageMotion } : e));
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
                                background: isReal ? BACKGROUND_COLOR : EMPTY_COLOR,
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
                                          setSelectedIndex(i);
                                          setPendingDeleteIndex(null);
                                          onSeek(segment.startFrame);
                                          zoomToAtLeast4x(segment.startFrame + (segment.endFrame - segment.startFrame) / 2);
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
// only one "kind" here). An IMAGE entry expands into its own row of
// motion buttons (see IMAGE_MOTION_OPTIONS) so direction is chosen in
// the same step as picking the file, per the feature's own design —
// a video entry has no motion setting, so it's a single one-click insert.
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
    onPick: (backgroundId: string, imageMotion?: BackgroundImageMotion) => void;
    onClose: () => void;
}) {
    const boxRef = useRef<HTMLDivElement>(null);
    // Which image entry's motion row is expanded — at most one at a
    // time, collapsed again on outside click/Escape same as the picker
    // itself. A video entry has no expanded state (single click inserts
    // immediately).
    const [expandedImageId, setExpandedImageId] = useState<string | null>(null);

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
                            onClick={() => (isImage ? setExpandedImageId(isExpanded ? null : b.id) : onPick(b.id))}
                        >
                            {b.caption || b.filename} ({b.mediaType})
                        </button>
                        {isExpanded && (
                            <div style={styles.motionRow}>
                                {IMAGE_MOTION_OPTIONS.map((option) => (
                                    <button
                                        key={option.value}
                                        type="button"
                                        className="secondary small"
                                        style={styles.motionOption}
                                        disabled={disabled}
                                        onClick={() => onPick(b.id, option.value)}
                                    >
                                        {option.label}
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

// Cmd+E's editor for an already-inserted image background's own motion —
// same 4-option set as the insert picker's expanded image row, just
// without the file choice (that's fixed once inserted; changing the
// FILE means removing and re-inserting, same as every other bar's own
// "delete + re-add to change identity" convention).
function MotionEditor({
    anchor,
    currentMotion,
    disabled,
    onPick,
    onClose,
}: {
    anchor: { x: number; y: number };
    currentMotion: BackgroundImageMotion;
    disabled: boolean;
    onPick: (motion: BackgroundImageMotion) => void;
    onClose: () => void;
}) {
    const boxRef = useRef<HTMLDivElement>(null);

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
            {IMAGE_MOTION_OPTIONS.map((option) => (
                <button
                    key={option.value}
                    type="button"
                    className="secondary small"
                    style={{
                        ...styles.pickerOption,
                        ...(option.value === currentMotion ? styles.pickerOptionActive : {}),
                    }}
                    disabled={disabled}
                    onClick={() => onPick(option.value)}
                >
                    {option.label}
                </button>
            ))}
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
};
