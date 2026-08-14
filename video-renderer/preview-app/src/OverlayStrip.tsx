import { useEffect, useRef, useState } from "react";
import type { PresenterScene } from "video-renderer-src/episode/types";

export type EditableOverlay =
    | { kind: "emphasis"; data: any }
    | { kind: "image"; data: any };

type DragMode = "move" | "resize";

interface Props {
    parentScene: PresenterScene;
    overlays: EditableOverlay[];
    onChange: (updated: EditableOverlay) => void;
    onSeek: (offsetInParentFrames: number) => void;
}

// A single-row strip representing one presenter scene's duration, with a
// draggable/resizable block per emphasis/image overlay anchored to it.
// Deliberately not a multi-track timeline (CLAUDE.md's non-goal): this only
// ever shows one presenter scene at a time, and only overlay timing is
// interactive here — clip order/cuts aren't touched by this component.
export function OverlayStrip({ parentScene, overlays, onChange, onSeek }: Props) {
    const trackRef = useRef<HTMLDivElement>(null);
    const [dragging, setDragging] = useState<{
        overlay: EditableOverlay;
        mode: DragMode;
        startX: number;
        startOffset: number;
        startDuration: number;
    } | null>(null);

    const parentDuration = parentScene.durationInFrames;

    const framesPerPixel = (trackWidthPx: number) => parentDuration / trackWidthPx;

    const startDrag = (
        e: React.MouseEvent,
        overlay: EditableOverlay,
        mode: DragMode
    ) => {
        e.preventDefault();
        e.stopPropagation();
        setDragging({
            overlay,
            mode,
            startX: e.clientX,
            startOffset: overlay.data.offsetInParentFrames,
            startDuration: overlay.data.maxDurationInParentFrames,
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

            const trackWidth = trackRef.current.getBoundingClientRect().width;
            const fpp = framesPerPixel(trackWidth);
            const deltaFrames = Math.round((e.clientX - dragging.startX) * fpp);

            if (dragging.mode === "move") {
                const maxOffset = Math.max(0, parentDuration - dragging.startDuration);
                const newOffset = clamp(dragging.startOffset + deltaFrames, 0, maxOffset);

                onChange({
                    ...dragging.overlay,
                    data: { ...dragging.overlay.data, offsetInParentFrames: newOffset },
                } as EditableOverlay);

                onSeek(newOffset);
            } else {
                const maxDuration = Math.max(1, parentDuration - dragging.startOffset);
                const newDuration = clamp(dragging.startDuration + deltaFrames, 1, maxDuration);

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
    }, [dragging]);

    return (
        <div style={styles.wrap}>
            <div style={styles.label}>
                {parentScene.id} — {parentDuration} frames
            </div>
            <div ref={trackRef} style={styles.track}>
                {overlays.map((overlay) => {
                    const leftPct = (overlay.data.offsetInParentFrames / parentDuration) * 100;
                    const widthPct = (overlay.data.maxDurationInParentFrames / parentDuration) * 100;

                    return (
                        <div
                            key={overlay.data.windowId}
                            style={{
                                ...styles.block,
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                background: overlay.kind === "emphasis" ? "#3a7bd5" : "#c96f2a",
                            }}
                            onMouseDown={(e) => startDrag(e, overlay, "move")}
                            title={
                                overlay.kind === "emphasis"
                                    ? overlay.data.text
                                    : `${overlay.data.assetId} — ${overlay.data.caption}`
                            }
                        >
                            <span style={styles.blockLabel}>
                                {overlay.kind === "emphasis" ? overlay.data.text : overlay.data.assetId}
                            </span>
                            <div
                                style={styles.resizeHandle}
                                onMouseDown={(e) => startDrag(e, overlay, "resize")}
                            />
                        </div>
                    );
                })}
            </div>
            <div style={styles.hint}>
                Drag a block to change when it appears, drag its right edge to change how long it
                shows. Values are frames relative to the start of {parentScene.id}.
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
        fontSize: 12,
        color: "#9aa7b4",
    },
    track: {
        position: "relative",
        height: 48,
        background: "#161d24",
        border: "1px solid #2a333d",
        borderRadius: 6,
        userSelect: "none",
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
        overflow: "hidden",
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
    hint: {
        fontSize: 12,
        color: "#6b7683",
    },
};
