import { useEffect, useRef, useState } from "react";
import { SIDE_CONTENT_WIDTH_PCT } from "video-renderer-src/episode/timing";
import type { MomentBox, MomentScene } from "video-renderer-src/episode/types";
import { getMoments, saveMoments } from "./api";
import { momentIndexFromSceneId, normalizeMoment } from "./momentDuration";
import { colors } from "./tokens";

// Mirrors each treatment component's own default-geometry literal (see
// timing.ts's resolveBoxStyle and each of MomentTreatments.tsx/
// EpisodeImage.tsx/CodeBlock.tsx/DiagramBlock.tsx/SideTerms.tsx's own
// default-box comments) — this is the box a drag/resize STARTS from when a
// moment has no box override yet. Kept in sync manually rather than
// imported, since the renderer's own defaults are spread across each
// component's local literal, not a single shared table; a mismatch here
// only affects where the handle starts, never the render itself (which
// always reads its OWN component's literal, this is only a UI seed value).
function defaultGeometryFor(scene: MomentScene): { xPct: number; yPct: number; widthPct: number; heightPct: number } {
    const presenterOnLeft = scene.presenterSide === "left";

    switch (scene.treatment) {
        case "content-dominant-code":
            return { xPct: 6, yPct: 8, widthPct: 62, heightPct: 60 };

        case "full-visual":
            return { xPct: 9, yPct: 9, widthPct: 82, heightPct: 82 };

        case "bottom-callout":
            return { xPct: 11, yPct: 70, widthPct: 78, heightPct: 18 };

        case "comparison":
            // Two independent flanking labels, not a single box — dragging
            // isn't offered for this treatment (see canEditBox below).
            return { xPct: 0, yPct: 0, widthPct: 100, heightPct: 100 };

        default: {
            // side-text / side-image / side-code / side-diagram / side-terms
            // all share sideContentStyle's own formula (MomentTreatments.tsx).
            const leftPct = presenterOnLeft ? 100 - SIDE_CONTENT_WIDTH_PCT : 0;
            return { xPct: leftPct, yPct: 0, widthPct: SIDE_CONTENT_WIDTH_PCT, heightPct: 100 };
        }
    }
}

// "comparison" has no single box (two independent flanking labels) — not
// offered for drag/resize. Every other treatment has exactly one visual
// region a box override can size/move.
function canEditBox(scene: MomentScene): boolean {
    return scene.treatment !== "comparison";
}

// Treatments where the presenter physically moves to make room for this
// box (see Episode.tsx's layoutWindowsForScene, which reads presenterSide
// for exactly these) — "full-visual"/"content-dominant-code" hide/shrink
// the presenter instead of sliding to a side, so there's no side for a
// drag to imply for them; "comparison" has no box at all (see canEditBox).
// Exported for MomentEditorPanel's own explicit Presenter side selector —
// same set, same reasoning, two different UI entry points to the same
// underlying field.
export const SIDE_MOVES_PRESENTER_TREATMENTS = new Set(["side-text", "side-image", "side-code", "side-diagram", "side-terms"]);

// Derives which side the presenter should move to from where the box was
// actually dragged, so "drag the image left/right" and "which way the
// presenter moves" stay spatially consistent by construction, instead of
// presenterSide being a fixed AI-decided value (almost always "left" per
// prompts/moments.txt) that a box drag had no effect on. Content sits on
// the OPPOSITE side from the presenter (see MomentTreatments.tsx's
// sideContentStyle: presenterOnLeft -> content on the right) — so a box
// dragged into the frame's right half implies the presenter should be on
// the left, and vice versa. Judged by the box's horizontal CENTER, not its
// left edge, so a wide box that merely starts left-of-center but is
// mostly on the right still reads as "on the right."
function presenterSideForBox(scene: MomentScene, box: MomentBox): "left" | "right" | undefined {
    if (!SIDE_MOVES_PRESENTER_TREATMENTS.has(scene.treatment)) return undefined;

    const centerXPct = box.xPct + box.widthPct / 2;
    return centerXPct >= 50 ? "left" : "right";
}

const HANDLE_SIZE = 12;
const MIN_BOX_PCT = 8; // a box this small or smaller isn't a usable drag target to shrink further

type DragMode = { kind: "move" } | { kind: "resize"; corner: "nw" | "ne" | "sw" | "se" };

export function MomentBoxOverlay({
    playerContainerRef,
    scene,
    episodePath,
    onLiveChange,
    onSaved,
}: {
    playerContainerRef: React.RefObject<HTMLDivElement | null>;
    scene: MomentScene;
    episodePath: string;
    // Called on every pointermove during a drag/resize, BEFORE the save
    // completes — patches the actual Remotion composition's box locally
    // (EpisodeWorkspace.tsx's applyLiveMomentBox, same live-patch-before-
    // real-save pattern applyLiveBeatText already uses) so the video
    // visibly grows/shrinks/moves in step with the drag instead of only
    // jumping to the new box after the PUT round-trip resolves.
    onLiveChange: (box: MomentBox) => void;
    onSaved: () => void;
}) {
    const [box, setBox] = useState<MomentBox>(() => {
        const existing = scene.box;
        const fallback = defaultGeometryFor(scene);
        return existing ?? { xPct: fallback.xPct, yPct: fallback.yPct, widthPct: fallback.widthPct, heightPct: fallback.heightPct };
    });

    const isDraggingRef = useRef(false);

    // Resyncs local state when a different moment becomes selected, or the
    // same moment's box changes from elsewhere (e.g. MomentEditorPanel) —
    // deliberately keyed on scene.id + scene.box's own values, not just
    // scene.id, so an external change is picked up too. Skipped while a
    // drag is actively in progress: onLiveChange's own patch to
    // episodeProps.scenePlan flows straight back into this component's
    // OWN scene.box prop every pointermove, and resyncing from that
    // echoed value here would fight the drag rather than just reflect it
    // (liveBox is already the authoritative visual mid-drag, so this
    // effect has nothing useful to do until the drag ends anyway).
    useEffect(() => {
        if (isDraggingRef.current) return;
        const existing = scene.box;
        const fallback = defaultGeometryFor(scene);
        setBox(existing ?? { xPct: fallback.xPct, yPct: fallback.yPct, widthPct: fallback.widthPct, heightPct: fallback.heightPct });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [scene.id, scene.box?.xPct, scene.box?.yPct, scene.box?.widthPct, scene.box?.heightPct]);

    const dragRef = useRef<{
        mode: DragMode;
        startClientX: number;
        startClientY: number;
        startBox: MomentBox;
        containerWidth: number;
        containerHeight: number;
    } | null>(null);

    const [liveBox, setLiveBox] = useState<MomentBox | null>(null);
    const [saveError, setSaveError] = useState<string | null>(null);

    const persist = async (nextBox: MomentBox) => {
        setSaveError(null);

        const index = momentIndexFromSceneId(scene.id);
        if (index === null) return;

        try {
            const data = await getMoments(episodePath);
            const moments = (data.moments ?? []).map(normalizeMoment);
            if (!moments[index]) return;

            // Dragging updates presenterSide too (see presenterSideForBox)
            // so the presenter's own movement stays spatially consistent
            // with where the box actually ended up, not left pointing at
            // whatever side the AI originally guessed.
            const nextPresenterSide = presenterSideForBox(scene, nextBox);

            moments[index] = {
                ...moments[index],
                box: nextBox,
                ...(nextPresenterSide ? { presenterSide: nextPresenterSide } : {}),
            };

            await saveMoments(episodePath, moments);
            onSaved();
        } catch (e) {
            setSaveError(String(e));
        }
    };

    const clampPct = (value: number) => Math.min(100, Math.max(0, value));

    // The authoritative in-progress box during a drag, read by onPointerUp
    // — NOT liveBox's own state value, which onPointerUp's closure (fixed
    // at the addEventListener call in startDrag) would only ever see as
    // whatever it was AT DRAG START, never a later setLiveBox update. A
    // ref sidesteps the stale-closure problem entirely since reading
    // liveBoxRef.current always gets the latest value regardless of when
    // the closure was created.
    const liveBoxRef = useRef<MomentBox | null>(null);

    const onPointerMove = (e: PointerEvent) => {
        const drag = dragRef.current;
        if (!drag) return;

        const deltaXPct = ((e.clientX - drag.startClientX) / drag.containerWidth) * 100;
        const deltaYPct = ((e.clientY - drag.startClientY) / drag.containerHeight) * 100;

        let next: MomentBox = drag.startBox;

        if (drag.mode.kind === "move") {
            next = {
                ...drag.startBox,
                xPct: clampPct(drag.startBox.xPct + deltaXPct),
                yPct: clampPct(drag.startBox.yPct + deltaYPct),
            };
        } else {
            const { corner } = drag.mode;
            let { xPct, yPct, widthPct, heightPct } = drag.startBox;

            if (corner === "se" || corner === "ne") {
                widthPct = Math.max(MIN_BOX_PCT, drag.startBox.widthPct + deltaXPct);
            } else {
                const newWidth = Math.max(MIN_BOX_PCT, drag.startBox.widthPct - deltaXPct);
                xPct = drag.startBox.xPct + (drag.startBox.widthPct - newWidth);
                widthPct = newWidth;
            }

            if (corner === "se" || corner === "sw") {
                heightPct = Math.max(MIN_BOX_PCT, drag.startBox.heightPct + deltaYPct);
            } else {
                const newHeight = Math.max(MIN_BOX_PCT, drag.startBox.heightPct - deltaYPct);
                yPct = drag.startBox.yPct + (drag.startBox.heightPct - newHeight);
                heightPct = newHeight;
            }

            next = { xPct: clampPct(xPct), yPct: clampPct(yPct), widthPct, heightPct };
        }

        liveBoxRef.current = next;
        setLiveBox(next);
        onLiveChange(next);
    };

    const onPointerUp = () => {
        const finalBox = liveBoxRef.current;
        dragRef.current = null;
        isDraggingRef.current = false;
        window.removeEventListener("pointermove", onPointerMove);
        window.removeEventListener("pointerup", onPointerUp);

        if (finalBox) {
            setBox(finalBox);
            setLiveBox(null);
            liveBoxRef.current = null;
            persist(finalBox);
        }
    };

    const startDrag = (e: React.PointerEvent, mode: DragMode) => {
        if (!playerContainerRef.current) return;
        e.preventDefault();
        e.stopPropagation();

        isDraggingRef.current = true;

        const rect = playerContainerRef.current.getBoundingClientRect();

        dragRef.current = {
            mode,
            startClientX: e.clientX,
            startClientY: e.clientY,
            startBox: box,
            containerWidth: rect.width,
            containerHeight: rect.height,
        };

        window.addEventListener("pointermove", onPointerMove);
        window.addEventListener("pointerup", onPointerUp);
    };

    useEffect(() => {
        return () => {
            window.removeEventListener("pointermove", onPointerMove);
            window.removeEventListener("pointerup", onPointerUp);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    if (!canEditBox(scene)) return null;

    const displayBox = liveBox ?? box;

    return (
        <div
            style={{
                position: "absolute",
                left: `${displayBox.xPct}%`,
                top: `${displayBox.yPct}%`,
                width: `${displayBox.widthPct}%`,
                height: `${displayBox.heightPct}%`,
                border: `2px dashed ${colors.accent}`,
                boxSizing: "border-box",
                cursor: "move",
                pointerEvents: "auto",
            }}
            onPointerDown={(e) => startDrag(e, { kind: "move" })}
        >
            {(["nw", "ne", "sw", "se"] as const).map((corner) => (
                <div
                    key={corner}
                    onPointerDown={(e) => startDrag(e, { kind: "resize", corner })}
                    style={{
                        position: "absolute",
                        width: HANDLE_SIZE,
                        height: HANDLE_SIZE,
                        background: colors.accent,
                        borderRadius: "50%",
                        cursor: `${corner}-resize`,
                        top: corner[0] === "n" ? -HANDLE_SIZE / 2 : undefined,
                        bottom: corner[0] === "s" ? -HANDLE_SIZE / 2 : undefined,
                        left: corner[1] === "w" ? -HANDLE_SIZE / 2 : undefined,
                        right: corner[1] === "e" ? -HANDLE_SIZE / 2 : undefined,
                    }}
                />
            ))}
            {saveError && (
                <div
                    style={{
                        position: "absolute",
                        bottom: -24,
                        left: 0,
                        fontSize: 11,
                        color: colors.error,
                        whiteSpace: "nowrap",
                    }}
                >
                    {saveError}
                </div>
            )}
        </div>
    );
}
