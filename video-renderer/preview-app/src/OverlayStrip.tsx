import { useEffect, useRef, useState } from "react";
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
    // The player's current frame (absolute), so the strip can draw a
    // playhead line in sync with what's actually on screen — the whole
    // point of showing this strip at all is to answer "where does this
    // overlay sit relative to the video," and a playhead is what makes
    // that legible at a glance instead of only while actively dragging.
    currentFrame: number;
}

// The strip always shows the FULL parent scene at once — no zoom window.
// An earlier version defaulted to a ~5s zoomed window with pan/scroll,
// which made a block impossible to place accurately (small movements were
// huge frame deltas once zoomed out) and gave no sense of where the
// overlay sat in the scene unless you happened to be scrolled to it.
// Showing the whole scene means the block is always sized proportionally
// to the real clip, and a click/drag anywhere on the track scrubs the
// player live, so the video is always visible feedback for wherever the
// cursor currently is — not just a frame-number readout.
export function OverlayStrip({ parentScene, overlays, onChange, onSeek, currentFrame }: Props) {
    const trackRef = useRef<HTMLDivElement>(null);
    const parentDuration = parentScene.durationInFrames;
    const parentStart = parentScene.timelineStartFrame;

    const framesPerPixel = (trackWidthPx: number) => parentDuration / trackWidthPx;

    const [dragging, setDragging] = useState<{
        overlay: EditableOverlay;
        mode: DragMode;
        startX: number;
        startOffset: number;
        startDuration: number;
        liveOffset: number;
        liveDuration: number;
    } | null>(null);

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
                // Capped by how much of the scene is left from this
                // moment's own start — generate_moments.py's propose_moments
                // now clamps maxDurationInParentFrames to the real rendered
                // duration before it's ever written to moments.json (see
                // momentDuration.ts), so this field is always the moment's
                // actual editable duration, not a separate "window ceiling"
                // needing its own tracking — a human can freely lengthen it
                // up to the end of the parent scene.
                const maxDuration = Math.max(1, parentDuration - dragging.startOffset);
                const newDuration = clamp(dragging.startDuration + deltaFrames, 1, maxDuration);

                setDragging((prev) => (prev ? { ...prev, liveDuration: newDuration } : prev));

                onChange({
                    ...dragging.overlay,
                    data: { ...dragging.overlay.data, maxDurationInParentFrames: newDuration },
                } as EditableOverlay);

                // Live-seek to the edge being dragged during a resize too —
                // previously only "move" scrubbed the player, so resizing
                // gave no visual feedback of where the new endpoint landed.
                onSeek(parentStart + dragging.startOffset + newDuration);
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
    }, [dragging]);

    // Clicking (not on a block/handle) anywhere on the track seeks the
    // player there directly — the fastest way to answer "what's at this
    // point in the clip" without needing an overlay to drag in the first
    // place.
    const onTrackClick = (e: React.MouseEvent) => {
        if (dragging || !trackRef.current) return;

        const rect = trackRef.current.getBoundingClientRect();
        const frameInScene = clamp(
            Math.round((e.clientX - rect.left) * framesPerPixel(rect.width)),
            0,
            parentDuration - 1
        );

        onSeek(parentStart + frameInScene);
    };

    const fps = 30; // presenter scenes are authored at the episode fps; frames-to-seconds is display-only here

    const tickCount = 8;
    const ticks = Array.from({ length: tickCount + 1 }, (_, i) => Math.round((parentDuration / tickCount) * i));

    const playheadFrameInScene = clamp(currentFrame - parentStart, 0, parentDuration);
    const playheadLeftPct = (playheadFrameInScene / parentDuration) * 100;

    return (
        <div style={styles.wrap}>
            <div style={styles.headerRow}>
                <div style={styles.label}>
                    {parentScene.id} — full clip, {formatFrames(parentDuration, fps)}
                </div>
            </div>

            <div style={styles.ruler}>
                {ticks.map((t) => (
                    <span key={t} style={styles.tick}>
                        {formatFrames(t, fps)}
                    </span>
                ))}
            </div>

            <div ref={trackRef} style={styles.track} onMouseDown={onTrackClick}>
                {overlays.map((overlay) => {
                    const isDragging = dragging?.overlay.data.windowId === overlay.data.windowId;
                    const offset = isDragging ? dragging!.liveOffset : overlay.data.offsetInParentFrames;
                    const duration = isDragging
                        ? dragging!.liveDuration
                        : overlay.data.maxDurationInParentFrames;

                    const leftPct = (offset / parentDuration) * 100;
                    // A block is given a visible minimum width so it's
                    // always a real drag target even for a short overlay in
                    // a long clip — previously (zoomed-window mode) this
                    // wasn't needed since zooming in already enlarged short
                    // overlays, but at full-scene width a 90-frame moment in
                    // a 3000-frame scene would otherwise be a 3%-wide sliver.
                    const widthPct = Math.max((duration / parentDuration) * 100, 6);

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

                <div style={{ ...styles.playhead, left: `${playheadLeftPct}%` }} />
            </div>

            <div style={styles.hint}>
                Drag a block to change when it appears, drag its right edge to change how long it
                shows, or click anywhere on the track to jump the player there — the vertical line
                always shows where the player currently is in {parentScene.id}. Values are frames
                relative to the start of the clip.
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
        height: 72,
        background: "#161d24",
        border: "1px solid #2a333d",
        borderRadius: 6,
        userSelect: "none",
        overflow: "hidden",
        cursor: "pointer",
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
        boxShadow: "0 0 0 1px rgba(0,0,0,0.3)",
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
        width: 12,
        cursor: "ew-resize",
        background: "rgba(255,255,255,0.3)",
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
        zIndex: 2,
    },
    playhead: {
        position: "absolute",
        top: 0,
        bottom: 0,
        width: 2,
        background: "#ff5a3c",
        pointerEvents: "none",
        zIndex: 1,
        boxShadow: "0 0 4px rgba(255,90,60,0.8)",
    },
    hint: {
        fontSize: 12,
        color: "#6b7683",
    },
};
