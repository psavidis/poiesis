import { useEffect, useMemo, useRef, useState } from "react";
import type { PresenterScene } from "video-renderer-src/episode/types";

export type EditableOverlay =
    | { kind: "moment"; data: any }
    | { kind: "image"; data: any };

type DragMode = "move" | "resize";

interface Props {
    parentScene: PresenterScene;
    overlays: EditableOverlay[];
    onChange: (updated: EditableOverlay) => void;
    // Absolute composition frame (parentScene.timelineStartFrame + offset),
    // matching the frame numbers the Player itself uses — the strip and the
    // player share one coordinate space so "drag to X" and "player shows X"
    // are the same number instead of two independently-scaled percentages.
    onSeek: (absoluteFrame: number) => void;
}

const MIN_ZOOM_FRAMES = 30; // ~1s at 30fps — narrowest window
const MAX_ZOOM_FRAMES_FALLBACK = 900; // ~30s fallback ceiling when a scene is very long
const DEFAULT_ZOOM_FRAMES = 150; // ~5s at 30fps

// A single-row strip anchored to one presenter scene, showing a zoomed-in
// frame window (not the whole clip at fixed scale) so drag precision doesn't
// degrade on long clips and a short overlay doesn't collapse to a sliver.
// Deliberately not a multi-track timeline (CLAUDE.md's non-goal): this only
// ever shows one presenter scene at a time, and only overlay timing is
// interactive — clip order/cuts aren't touched here.
export function OverlayStrip({ parentScene, overlays, onChange, onSeek }: Props) {
    const trackRef = useRef<HTMLDivElement>(null);
    const parentDuration = parentScene.durationInFrames;
    const parentStart = parentScene.timelineStartFrame;

    const maxZoomFrames = Math.min(parentDuration, MAX_ZOOM_FRAMES_FALLBACK);

    const [zoomFrames, setZoomFrames] = useState(
        Math.min(DEFAULT_ZOOM_FRAMES, maxZoomFrames)
    );

    // Window is expressed as absolute composition frames, centered on the
    // first overlay initially, then only moved by explicit user action
    // (drag-near-edge auto-scroll, or the pan/zoom controls) — never
    // silently recentered on every render, which would fight the user's
    // own scrolling.
    const initialCenter =
        parentStart +
        (overlays[0] ? overlays[0].data.offsetInParentFrames : Math.floor(parentDuration / 2));

    const [windowStart, setWindowStart] = useState(
        clamp(
            initialCenter - Math.floor(zoomFrames / 2),
            parentStart,
            parentStart + Math.max(0, parentDuration - zoomFrames)
        )
    );

    const clampWindowStart = (start: number, zoom: number) =>
        clamp(start, parentStart, parentStart + Math.max(0, parentDuration - zoom));

    const setZoom = (nextZoomFrames: number) => {
        const clampedZoom = clamp(nextZoomFrames, MIN_ZOOM_FRAMES, maxZoomFrames);
        // Keep the current window's center fixed while zooming, rather than
        // jumping back to frame 0 of the scene.
        const center = windowStart + zoomFrames / 2;
        setZoomFrames(clampedZoom);
        setWindowStart(clampWindowStart(Math.round(center - clampedZoom / 2), clampedZoom));
    };

    const [dragging, setDragging] = useState<{
        overlay: EditableOverlay;
        mode: DragMode;
        startX: number;
        startOffset: number;
        startDuration: number;
        liveOffset: number;
        liveDuration: number;
    } | null>(null);

    const framesPerPixel = (trackWidthPx: number) => zoomFrames / trackWidthPx;

    const startDrag = (e: React.MouseEvent, overlay: EditableOverlay, mode: DragMode) => {
        e.preventDefault();
        e.stopPropagation();
        setDragging({
            overlay,
            mode,
            startX: e.clientX,
            startOffset: overlay.data.offsetInParentFrames,
            startDuration: overlay.data.maxDurationInParentFrames,
            liveOffset: overlay.data.offsetInParentFrames,
            liveDuration: overlay.data.maxDurationInParentFrames,
        });
    };

    // Listens on window (not the track element) so the drag keeps tracking
    // the cursor even if it moves outside the track's bounding box mid-drag
    // — a React onMouseMove scoped to the track stops firing the moment the
    // cursor leaves it, which freezes fast drags right at the edges.
    useEffect(() => {
        if (!dragging) return;

        const onMouseMove = (e: MouseEvent) => {
            if (!trackRef.current) return;

            const rect = trackRef.current.getBoundingClientRect();
            const fpp = framesPerPixel(rect.width);
            const deltaFrames = Math.round((e.clientX - dragging.startX) * fpp);

            // Auto-scroll the window when the cursor nears either edge of
            // the track, so a drag isn't capped at whatever the current
            // zoom window happens to show.
            const edgeMargin = rect.width * 0.1;
            if (e.clientX < rect.left + edgeMargin) {
                setWindowStart((prev) => clampWindowStart(prev - Math.round(zoomFrames * 0.05), zoomFrames));
            } else if (e.clientX > rect.right - edgeMargin) {
                setWindowStart((prev) => clampWindowStart(prev + Math.round(zoomFrames * 0.05), zoomFrames));
            }

            if (dragging.mode === "move") {
                const maxOffset = Math.max(0, parentDuration - dragging.startDuration);
                const newOffset = clamp(dragging.startOffset + deltaFrames, 0, maxOffset);

                setDragging((prev) => (prev ? { ...prev, liveOffset: newOffset } : prev));

                onChange({
                    ...dragging.overlay,
                    data: { ...dragging.overlay.data, offsetInParentFrames: newOffset },
                } as EditableOverlay);

                onSeek(parentStart + newOffset);
            } else {
                const maxDuration = Math.max(1, parentDuration - dragging.startOffset);
                const newDuration = clamp(dragging.startDuration + deltaFrames, 1, maxDuration);

                setDragging((prev) => (prev ? { ...prev, liveDuration: newDuration } : prev));

                onChange({
                    ...dragging.overlay,
                    data: { ...dragging.overlay.data, maxDurationInParentFrames: newDuration },
                } as EditableOverlay);
            }
        };

        const onMouseUp = () => setDragging(null);

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);

        return () => {
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dragging, zoomFrames]);

    const fps = 30; // presenter scenes are authored at the episode fps; frames-to-seconds is display-only here

    const ticks = useMemo(() => {
        const tickCount = 6;
        const step = zoomFrames / tickCount;
        return Array.from({ length: tickCount + 1 }, (_, i) => Math.round(i * step));
    }, [zoomFrames]);

    return (
        <div style={styles.wrap}>
            <div style={styles.headerRow}>
                <div style={styles.label}>
                    {parentScene.id} — showing {formatFrames(zoomFrames, fps)} window of{" "}
                    {formatFrames(parentDuration, fps)} total
                </div>
                <div style={styles.zoomControls}>
                    <button
                        style={styles.zoomBtn}
                        onClick={() => setZoom(zoomFrames * 1.6)}
                        disabled={zoomFrames >= maxZoomFrames}
                        title="Zoom out"
                    >
                        −
                    </button>
                    <button
                        style={styles.zoomBtn}
                        onClick={() => setZoom(zoomFrames / 1.6)}
                        disabled={zoomFrames <= MIN_ZOOM_FRAMES}
                        title="Zoom in"
                    >
                        +
                    </button>
                </div>
            </div>

            <div style={styles.ruler}>
                {ticks.map((t) => (
                    <span key={t} style={styles.tick}>
                        {formatFrames(windowStart - parentStart + t, fps)}
                    </span>
                ))}
            </div>

            <div ref={trackRef} style={styles.track}>
                {overlays.map((overlay) => {
                    const isDragging = dragging?.overlay.data.windowId === overlay.data.windowId;
                    const offset = isDragging ? dragging!.liveOffset : overlay.data.offsetInParentFrames;
                    const duration = isDragging
                        ? dragging!.liveDuration
                        : overlay.data.maxDurationInParentFrames;

                    const absoluteStart = parentStart + offset;
                    const leftPct = ((absoluteStart - windowStart) / zoomFrames) * 100;
                    const widthPct = (duration / zoomFrames) * 100;

                    // Skip rendering blocks fully outside the current window
                    // instead of drawing them off-canvas indefinitely.
                    if (leftPct + widthPct < 0 || leftPct > 100) return null;

                    const isMomentImage =
                        overlay.kind === "moment" && overlay.data.treatment === "side-image";
                    const showsText = overlay.kind === "moment" && !isMomentImage;

                    return (
                        <div
                            key={overlay.data.windowId}
                            style={{
                                ...styles.block,
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                background:
                                    overlay.kind === "moment"
                                        ? isMomentImage
                                            ? "#c96f2a"
                                            : "#3a7bd5"
                                        : "#c96f2a",
                            }}
                            onMouseDown={(e) => startDrag(e, overlay, "move")}
                            title={
                                showsText
                                    ? overlay.data.text
                                    : `${overlay.data.assetId} — ${overlay.data.caption}`
                            }
                        >
                            <span style={styles.blockLabel}>
                                {showsText ? overlay.data.text : overlay.data.assetId}
                            </span>
                            <div
                                style={styles.resizeHandle}
                                onMouseDown={(e) => startDrag(e, overlay, "resize")}
                            />

                            {isDragging && (
                                <div style={styles.readout}>
                                    offset {offset}f ({formatFrames(offset, fps)}) · duration {duration}f (
                                    {formatFrames(duration, fps)})
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            <div style={styles.hint}>
                Drag a block to change when it appears, drag its right edge to change how long it
                shows — the player above stays on the same frame you're pointing at. Use +/− to
                zoom the window; drag near either edge to scroll further. Values are frames
                relative to the start of {parentScene.id}.
            </div>
        </div>
    );
}

function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
}

function formatFrames(frames: number, fps: number) {
    const seconds = frames / fps;
    return `${seconds.toFixed(1)}s`;
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 6,
    },
    headerRow: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
    },
    label: {
        fontSize: 12,
        color: "#9aa7b4",
    },
    zoomControls: {
        display: "flex",
        gap: 4,
    },
    zoomBtn: {
        width: 24,
        height: 24,
        padding: 0,
        lineHeight: 1,
        fontSize: 15,
        fontWeight: 700,
        background: "#1c242d",
        border: "1px solid #2a333d",
        borderRadius: 4,
        color: "#e8edf2",
        cursor: "pointer",
    },
    ruler: {
        display: "flex",
        justifyContent: "space-between",
        fontSize: 10,
        color: "#5c6773",
        padding: "0 2px",
    },
    tick: {
        flexShrink: 0,
    },
    track: {
        position: "relative",
        height: 56,
        background: "#161d24",
        border: "1px solid #2a333d",
        borderRadius: 6,
        userSelect: "none",
        overflow: "hidden",
    },
    block: {
        position: "absolute",
        top: 6,
        bottom: 6,
        borderRadius: 4,
        cursor: "grab",
        display: "flex",
        alignItems: "center",
        paddingLeft: 8,
        color: "#fff",
        fontSize: 12,
        overflow: "visible",
        whiteSpace: "nowrap",
    },
    blockLabel: {
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
        background: "rgba(255,255,255,0.25)",
    },
    readout: {
        position: "absolute",
        bottom: "100%",
        left: 0,
        marginBottom: 4,
        padding: "3px 6px",
        background: "#0b0f14",
        border: "1px solid #2a333d",
        borderRadius: 4,
        fontSize: 11,
        color: "#e8edf2",
        whiteSpace: "nowrap",
        zIndex: 1,
    },
    hint: {
        fontSize: 12,
        color: "#6b7683",
    },
};
