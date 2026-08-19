import { useEffect, useRef, useState } from "react";
import type { ImageScene, PresenterScene, ScenePlan, TitleScene } from "video-renderer-src/episode/types";
import { deleteScene, updateSceneFields } from "./api";
import { colors, radius, typography } from "./tokens";
import type { TimelineZoom } from "./useTimelineZoom";

// A fourth, distinct color from SceneBar/MomentBar/BeatBar — image scenes
// are their own scene type (not a moment treatment), and the spec (docs/
// specs/content-types-and-presentation-editing.md) calls Full Screen a
// first-class presentation deserving its own visible timeline surface, so
// this gets its own bar rather than folding into MomentBar (#46).
const IMAGE_COLOR = colors.timelineImage;

const MOD_KEY_LABEL = navigator.platform.toLowerCase().includes("mac") ? "Cmd" : "Ctrl";

interface Props {
    scenePlan: ScenePlan;
    totalFrames: number;
    currentFrame: number;
    onSeek: (absoluteFrame: number) => void;
    episodePath: string;
    onSaved: () => void;
    // Opens the structured ImageEditorPanel (asset/display/caption) for
    // whichever image scene is selected — image scenes have no single
    // text field, so there's no InlineTextEditor-style Cmd+E path the way
    // MomentBar has for text-eligible moments; click-to-select always
    // pairs with this same panel, reached via Cmd+E for consistency with
    // the rest of this timeline's select-then-edit lifecycle.
    onEditRequested: (sceneId: string) => void;
    // Set by EpisodeWorkspace right after a chat edit touches an image on
    // this bar (#54) — seeds selection and re-centers the view on it.
    highlightedId?: string | null;
    // Single zoom/pan window shared with Scenes/Moments/Beats (#86) —
    // owned by EpisodeWorkspace, not this component.
    timelineZoom: TimelineZoom;
    // See BeatBar's identical prop's own doc comment — mutual-exclusion
    // signal so this bar's selection (and its Cmd+E listener) clears
    // itself once a different bar becomes the active selection owner.
    activeSelectionBar: string | null;
    onActivateSelection: () => void;
}

type DragMode = "move" | "resize";

type DragState = {
    imageId: string;
    mode: DragMode;
    startX: number;
    startOffset: number;
    startDuration: number;
    liveOffset: number;
    liveDuration: number;
};

// Every image overlay's resolved window across the full episode — mirrors
// MomentBar (#41) and BeatBar (#38/#39): select-then-Cmd+E, zoom, drag to
// move, drag the right edge to resize. Image scenes live only in
// scene-plan.json (no separate images.json source file the way moments/
// beats have — see docs/pipeline-guide.md), so saves go through the
// direct scene-field-update endpoint (ui/server.py's PUT
// /api/episode/scene) rather than a moments.json/emphasis.json rewrite.
export function ImageBar({
    scenePlan,
    totalFrames,
    currentFrame,
    onSeek,
    episodePath,
    onSaved,
    onEditRequested,
    highlightedId,
    timelineZoom,
    activeSelectionBar,
    onActivateSelection,
}: Props) {
    const { zoom, windowFrames, windowStartFrame, frameToPct, playheadPct, playheadVisible, zoomToAtLeast4x } =
        timelineZoom;
    const [dragState, setDragState] = useState<{ imageId: string; mode: DragMode } | null>(null);
    const [liveOffset, setLiveOffset] = useState(0);
    const [liveDuration, setLiveDuration] = useState(0);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [selectedImageId, setSelectedImageId] = useState<string | null>(null);
    // Delete/Backspace on a selected image shows this inline confirm —
    // same pattern as MomentBar/ChapterStrip.
    const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
    const trackRef = useRef<HTMLDivElement>(null);
    const dragRef = useRef<DragState | null>(null);

    // See BeatBar's identical effect's own doc comment — clears this bar's
    // selection once a different bar takes over the shared selection.
    useEffect(() => {
        if (activeSelectionBar !== "image") setSelectedImageId(null);
    }, [activeSelectionBar]);

    // resolved/windowFrames etc. are computed unconditionally (not gated
    // behind the totalFrames/empty-state early returns below) — those
    // returns must come AFTER every hook in this component is declared.
    // They used to sit right here, before the useEffect calls further
    // down: harmless when the item count only ever went from N to N (drag/
    // resize never changed the array length), but the moment a delete path
    // existed and could take it from 1 to 0, this component would render
    // fewer hooks on that transition than on the previous render — React's
    // "Rendered fewer hooks than expected" crash, confirmed live when
    // deleting an episode's only image scene. Every one of MomentBar/
    // BeatBar/ImageBar had this same latent shape; fixed here first since
    // this is the one that actually crashed.
    const trackById = new Map<string, PresenterScene | TitleScene>();
    scenePlan.scenes.forEach((s) => {
        if (s.type === "presenter" || s.type === "title") trackById.set(s.id, s);
    });

    const resolved = scenePlan.scenes
        .filter((s): s is ImageScene => s.type === "image")
        .map((image) => {
            const parent = trackById.get(image.parentSceneId);
            if (!parent) return null;
            return {
                image,
                parent,
                startFrame: parent.timelineStartFrame + image.offsetInParentFrames,
            };
        })
        .filter((m): m is { image: ImageScene; parent: PresenterScene | TitleScene; startFrame: number } => m !== null)
        .sort((a, b) => a.startFrame - b.startFrame);

    const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
        if (dragState) return;
        setSelectedImageId(null);
        setPendingDeleteId(null);
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
        onSeek(Math.round(windowStartFrame + pct * windowFrames));
    };

    const startDrag = (e: React.MouseEvent, image: ImageScene, mode: DragMode) => {
        e.preventDefault();
        e.stopPropagation();
        setSaveError(null);
        dragRef.current = {
            imageId: image.id,
            mode,
            startX: e.clientX,
            startOffset: image.offsetInParentFrames,
            startDuration: image.durationInFrames,
            liveOffset: image.offsetInParentFrames,
            liveDuration: image.durationInFrames,
        };
        setDragState({ imageId: image.id, mode });
        setLiveOffset(image.offsetInParentFrames);
        setLiveDuration(image.durationInFrames);
    };

    useEffect(() => {
        if (!dragState) return;

        const onMouseMove = (e: MouseEvent) => {
            const drag = dragRef.current;
            if (!drag || !trackRef.current) return;
            const rect = trackRef.current.getBoundingClientRect();
            const framesPerPixel = windowFrames / rect.width;
            const deltaFrames = Math.round((e.clientX - drag.startX) * framesPerPixel);

            const parentEntry = resolved.find((r) => r.image.id === drag.imageId);
            const parentDuration = parentEntry?.parent.durationInFrames ?? Infinity;

            if (drag.mode === "move") {
                const maxOffset = Math.max(0, parentDuration - drag.startDuration);
                const newOffset = clamp(drag.startOffset + deltaFrames, 0, maxOffset);
                drag.liveOffset = newOffset;
                setLiveOffset(newOffset);
            } else {
                const maxDuration = Math.max(1, parentDuration - drag.startOffset);
                const newDuration = clamp(drag.startDuration + deltaFrames, 1, maxDuration);
                drag.liveDuration = newDuration;
                setLiveDuration(newDuration);
            }
        };

        const onMouseUp = () => {
            const drag = dragRef.current;
            dragRef.current = null;
            setDragState(null);
            if (drag) commitDrag(drag);
        };

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
        return () => {
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dragState, windowFrames]);

    useEffect(() => {
        if (!selectedImageId) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "e" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            onEditRequested(selectedImageId);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedImageId, onEditRequested]);

    // Delete/Backspace on a selected image shows the inline confirm —
    // mirrors MomentBar's own delete effect.
    useEffect(() => {
        if (!selectedImageId) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key !== "Delete" && e.key !== "Backspace") return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            setPendingDeleteId(selectedImageId);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedImageId]);

    // Escape dismisses the delete confirm without deleting (found missing
    // during a live keyboard-shortcut sweep — mirrors the fix in
    // MomentBar/ChapterStrip/BeatBar).
    useEffect(() => {
        if (!pendingDeleteId) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") setPendingDeleteId(null);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [pendingDeleteId]);

    const doDelete = async () => {
        if (!pendingDeleteId) return;

        try {
            await deleteScene(episodePath, pendingDeleteId);
            onSaved();
            setPendingDeleteId(null);
            setSelectedImageId(null);
        } catch (e) {
            setSaveError(String(e));
        }
    };

    // Seeds selection from an AI chat edit (#54) and re-centers the view on
    // it — mirrors MomentBar's own highlightedId effect.
    useEffect(() => {
        if (!highlightedId) return;
        const entry = resolved.find((r) => r.image.id === highlightedId);
        if (!entry) return;
        onActivateSelection();
        setSelectedImageId(highlightedId);
        onSeek(entry.startFrame);
        zoomToAtLeast4x(entry.startFrame);
        trackRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [highlightedId]);

    // Direct field update against scene-plan.json (no separate source-of-
    // truth file for image scenes, unlike moments/beats) — see api.ts's
    // updateSceneFields / ui/server.py's PUT /api/episode/scene.
    const commitDrag = async (drag: DragState) => {
        try {
            await updateSceneFields(episodePath, drag.imageId, {
                offsetInParentFrames: drag.liveOffset,
                durationInFrames: drag.liveDuration,
            });
            onSaved();
        } catch (e) {
            setSaveError(String(e));
        }
    };

    // Every hook above has now run unconditionally on every render — safe
    // to bail on rendering anything from here on.
    if (totalFrames <= 0 || resolved.length === 0) return null;

    return (
        <div style={styles.wrap}>
            <div style={styles.label}>Images ({resolved.length})</div>

            <div ref={trackRef} style={styles.track} onMouseDown={onTrackClick}>
                {resolved.map(({ image, startFrame }) => {
                    const isDragging = dragState?.imageId === image.id;
                    const offset = isDragging && dragState.mode === "move" ? liveOffset : image.offsetInParentFrames;
                    const duration = isDragging ? liveDuration : image.durationInFrames;
                    const effectiveStartFrame = startFrame - image.offsetInParentFrames + offset;

                    const leftPct = frameToPct(effectiveStartFrame);
                    const rawWidthPct = (duration / windowFrames) * 100;

                    if (leftPct + rawWidthPct < 0 || leftPct > 100) return null;

                    const widthPct = Math.max(rawWidthPct, 0.6);
                    const label = image.caption || image.assetId;
                    const isSelected = selectedImageId === image.id;

                    return (
                        <div
                            key={image.id}
                            style={{
                                ...styles.segment,
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                ...(isSelected ? styles.segmentSelected : {}),
                            }}
                            title={
                                isSelected
                                    ? `${image.id} — ${image.display}: ${label} — press ${MOD_KEY_LABEL}+E to edit`
                                    : `${image.id} — ${image.display}: ${label}`
                            }
                            onClick={(e) => {
                                if (isDragging) return;
                                e.stopPropagation();
                                onActivateSelection();
                                setSelectedImageId(image.id);
                                setPendingDeleteId(null);
                                onSeek(startFrame);
                            }}
                            onMouseDown={(e) => {
                                if (e.button !== 0) return;
                                startDrag(e, image, "move");
                            }}
                        >
                            {widthPct > 4 && <span style={styles.segmentLabel}>{label}</span>}
                            <div
                                style={styles.resizeHandle}
                                onMouseDown={(e) => startDrag(e, image, "resize")}
                                title="Drag to resize"
                            />
                            {isDragging && (
                                <div style={styles.readout}>
                                    {dragState.mode === "move"
                                        ? `offset ${(offset / 30).toFixed(1)}s`
                                        : `${(duration / 30).toFixed(1)}s`}
                                </div>
                            )}
                        </div>
                    );
                })}

                {playheadVisible && <div style={{ ...styles.playhead, left: `${playheadPct}%` }} />}
            </div>

            {saveError && <div style={styles.error}>{saveError}</div>}

            {pendingDeleteId && (
                <div style={styles.deleteConfirm}>
                    <span>Delete this image?</span>
                    <button type="button" className="secondary small" onClick={doDelete} style={styles.deleteButton}>
                        Delete
                    </button>
                    <button type="button" className="secondary small" onClick={() => setPendingDeleteId(null)}>
                        Cancel
                    </button>
                </div>
            )}

            <div style={styles.hint}>
                {selectedImageId
                    ? `Selected — press ${MOD_KEY_LABEL}+E to edit, Delete to remove it.`
                    : zoom > 1
                    ? "Click an image to select it, drag its body to move it or its right edge to resize, or click empty track to seek."
                    : "Zoom in for precise dragging — at full-episode width a short image overlay is too thin to grab reliably."}
            </div>
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
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        userSelect: "none",
        cursor: "pointer",
        overflow: "hidden",
    },
    segment: {
        position: "absolute",
        top: 2,
        bottom: 2,
        borderRadius: 3,
        background: IMAGE_COLOR,
        display: "flex",
        alignItems: "center",
        overflow: "visible",
        cursor: "grab",
        boxShadow: "0 0 0 0px transparent",
    },
    segmentSelected: {
        boxShadow: "0 0 0 2px #ffffff, 0 0 8px rgba(255,255,255,0.5)",
        zIndex: 1,
    },
    segmentLabel: {
        padding: "0 5px",
        fontSize: 10,
        fontWeight: typography.weight.semibold,
        // Dark text on the teal image-bar background specifically — a
        // computed contrast color for IMAGE_COLOR, not a reused UI color.
        color: "#04231a",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
    },
    resizeHandle: {
        position: "absolute",
        right: 0,
        top: 0,
        bottom: 0,
        width: 8,
        cursor: "ew-resize",
        background: "rgba(0,0,0,0.25)",
    },
    readout: {
        position: "absolute",
        bottom: "100%",
        right: 0,
        marginBottom: 4,
        padding: "2px 6px",
        background: colors.background,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.sm,
        fontSize: typography.size.xs,
        color: colors.textPrimary,
        whiteSpace: "nowrap",
        zIndex: 2,
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
    hint: {
        fontSize: typography.size.xs,
        color: colors.textMuted,
    },
};
