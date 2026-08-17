import { useEffect, useRef, useState } from "react";
import type { MomentScene, PresenterScene, ScenePlan, TitleScene } from "video-renderer-src/episode/types";
import { getMoments, insertMoment, saveMoments, type MomentInsertKind } from "./api";
import { isTextEligible } from "./InlineTextEditor";
import { contentTypeAndPresentationFor } from "./MomentEditorPanel";
import { momentIndexFromSceneId } from "./momentDuration";
import { colors, radius, shadow, typography } from "./tokens";

// Per-content-type color scheme — previously a single purple bucket for
// every non-text moment (#35's original "where does text appear" answer),
// which made image/code/diagram moments indistinguishable from each other
// at a glance. Reuses contentTypeAndPresentationFor (MomentEditorPanel.tsx)
// rather than a second parallel treatment->category table, so this strip's
// notion of "what kind of content is this" never drifts from the Asset
// library panel's. contentTypeAndPresentationFor returns null for every
// treatment this strip calls "text" (bottom-callout/side-text/side-terms/
// comparison, and full-visual with fullVisualKind "text") — that's not a
// coincidence, both were designed around the same content/no-content split.
const TEXT_COLOR = colors.timelineText;
const CONTENT_TYPE_COLOR: Record<string, string> = {
    image: colors.timelineMomentImage,
    code: colors.timelineMomentCode,
    diagram: colors.timelineMomentDiagram,
};

function momentColor(moment: MomentScene): string {
    const [contentType] = contentTypeAndPresentationFor(moment);
    return contentType ? CONTENT_TYPE_COLOR[contentType] : TEXT_COLOR;
}

// Best-effort label for what a moment actually shows, for the inline
// label on wide-enough segments and the hover tooltip on narrow ones —
// mirrors MomentEditorPanel's summarizeMomentContent for the treatments
// that don't carry a single m.text field.
function momentLabel(moment: MomentScene): string {
    if (moment.text) return moment.text;
    if (moment.treatment === "side-terms" && moment.terms?.length) {
        return moment.terms.map((t) => t.text).join(", ");
    }
    if (moment.treatment === "comparison" && moment.comparison) {
        return `${moment.comparison.left} vs ${moment.comparison.right}`;
    }
    if (moment.treatment === "side-diagram" && moment.diagram) {
        return moment.diagram.nodes.map((n) => n.label).join(" → ");
    }
    if (moment.treatment === "side-code" || moment.treatment === "content-dominant-code") {
        return moment.codeAssetId ?? moment.treatment;
    }
    if (moment.treatment === "side-image") return moment.caption || moment.assetId || moment.treatment;
    return moment.treatment;
}

// Same geometric zoom stepping as BeatBar (#38) — kept as a literal copy
// rather than a shared constant module, matching this codebase's existing
// preference for small, self-contained bar components over a shared
// timeline-bar abstraction (see BeatBar's own comments).
const ZOOM_STEP = 1.6;
const MAX_ZOOM = 20;
const MIN_ZOOM = 1;

// Display-only label for the edit shortcut's hint text — mirrors BeatBar's
// own MOD_KEY_LABEL constant.
const MOD_KEY_LABEL = navigator.platform.toLowerCase().includes("mac") ? "Cmd" : "Ctrl";

interface Props {
    scenePlan: ScenePlan;
    totalFrames: number;
    currentFrame: number;
    onSeek: (absoluteFrame: number) => void;
    episodePath: string;
    onSaved: () => void;
    // Fired only when the user presses the edit shortcut (Cmd+E / Ctrl+E)
    // while a text-eligible moment is selected — NOT on click. Selecting
    // (clicking) a moment highlights it and seeks the player there;
    // editing is a deliberate second step, matching BeatBar's #39 pattern
    // rather than MomentBar's old click-opens-immediately behavior (#41).
    // The third (treatment) arg is passed only by Cmd+I's insert flow,
    // which already knows the treatment it just created and can't rely on
    // EpisodeWorkspace's scenePlan closure being fresh yet at that exact
    // moment (see openInlineMomentEditor's own comment) — the click path
    // omits it and keeps looking the treatment up as before.
    onEditRequested: (sceneId: string, anchor: { x: number; y: number }, treatment?: string) => void;
    // Non-text-eligible treatments (side-image/side-terms/side-diagram/
    // side-code/comparison) have no single text field to inline-edit —
    // clicking one still opens the full structured MomentEditorPanel
    // directly, same as before #41, so this fires instead of selecting.
    onOpenStructuredEditor: (sceneId: string) => void;
    // Set by EpisodeWorkspace right after a chat edit touches a moment on
    // this bar (#54) — seeds selection and re-centers the view on it, the
    // same way clicking the segment yourself would, so the AI's change is
    // immediately visible instead of requiring the user to hunt for it.
    highlightedId?: string | null;
    // Fired on every moment click, text-eligible or not — separate from
    // onEditRequested (Cmd+E only) and onOpenStructuredEditor (non-text-
    // eligible treatments only). AssetLibraryPanel needs to know which
    // moment is focused regardless of treatment (a full-visual/side-text/
    // bottom-callout moment never opens a structured editor, so relying on
    // EpisodeWorkspace's selectedEditor alone left those permanently
    // unselectable there — see #69).
    onSelect?: (sceneId: string) => void;
}

type DragMode = "move" | "resize";

type DragState = {
    momentId: string;
    mode: DragMode;
    startX: number;
    startOffset: number;
    startDuration: number;
    liveOffset: number;
    liveDuration: number;
};

// Every moment overlay's resolved window across the full episode, so
// sparse, easy-to-miss moments (a few seconds each, scattered across a
// 12-minute episode) are visible and jumpable at a glance instead of only
// discoverable by scrubbing into one. Moments don't carry an absolute
// timelineStartFrame (see types.ts) — position is resolved the same way
// EpisodeWorkspace's activeScenes memo already does, against whichever
// track scene is currently at parentSceneId.
//
// Selection/zoom/drag/resize mirror BeatBar (#38, #39) — the moment-editing
// spec explicitly calls Beat editing "the reference implementation" for
// Moment timeline interaction (see docs/specs/moment-editing.md).
export function MomentBar({
    scenePlan,
    totalFrames,
    currentFrame,
    onSeek,
    episodePath,
    onSaved,
    onEditRequested,
    onOpenStructuredEditor,
    highlightedId,
    onSelect,
}: Props) {
    const [zoom, setZoom] = useState(1);
    const [panStartPct, setPanStartPct] = useState(0);
    const [dragState, setDragState] = useState<{ momentId: string; mode: DragMode } | null>(null);
    const [liveOffset, setLiveOffset] = useState(0);
    const [liveDuration, setLiveDuration] = useState(0);
    const [saveError, setSaveError] = useState<string | null>(null);
    // The clicked-but-not-editing moment — highlighted, and the target of
    // Cmd+E/Ctrl+E for text-eligible treatments.
    const [selectedMomentId, setSelectedMomentId] = useState<string | null>(null);
    // Cmd+I's type picker — open only while the user is choosing what kind
    // of moment to insert at the playhead. anchor positions the popup near
    // wherever the shortcut was pressed, same pattern as the inline text
    // editor's own anchor.
    const [insertPickerAnchor, setInsertPickerAnchor] = useState<{ x: number; y: number } | null>(null);
    const [inserting, setInserting] = useState(false);
    // Delete/Backspace on a selected moment shows this inline confirm
    // rather than deleting immediately — set to the moment id awaiting
    // confirmation, cleared on confirm/cancel/deselect.
    const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
    const selectedAnchorRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
    const trackRef = useRef<HTMLDivElement>(null);
    const dragRef = useRef<DragState | null>(null);

    if (totalFrames <= 0) return null;

    const trackById = new Map<string, PresenterScene | TitleScene>();
    scenePlan.scenes.forEach((s) => {
        if (s.type === "presenter" || s.type === "title") trackById.set(s.id, s);
    });

    // The presenter scene under the playhead right now, if any — Cmd+I
    // inserts there, at the playhead's own offset into it. A moment can
    // only be parented to a presenter scene (resolve_manual_moment_
    // creation rejects a title parent, same as every other moment-creation
    // path), so Cmd+I is simply unavailable while the playhead sits over a
    // title card — there's no ambiguity to resolve, just nothing to insert
    // into.
    const presenterAtPlayhead = scenePlan.scenes.find(
        (s): s is PresenterScene =>
            s.type === "presenter" &&
            currentFrame >= s.timelineStartFrame &&
            currentFrame < s.timelineStartFrame + s.durationInFrames
    );

    const resolved = scenePlan.scenes
        .filter((s): s is MomentScene => s.type === "moment")
        .map((moment) => {
            const parent = trackById.get(moment.parentSceneId);
            if (!parent) return null;
            return {
                moment,
                parent,
                startFrame: parent.timelineStartFrame + moment.offsetInParentFrames,
            };
        })
        .filter((m): m is { moment: MomentScene; parent: PresenterScene | TitleScene; startFrame: number } => m !== null)
        .sort((a, b) => a.startFrame - b.startFrame);

    if (resolved.length === 0) return null;

    const windowFrames = totalFrames / zoom;
    const maxPanStartPct = 1 - windowFrames / totalFrames;
    const clampedPanStartPct = clamp(panStartPct, 0, Math.max(0, maxPanStartPct));
    const windowStartFrame = clampedPanStartPct * totalFrames;

    const frameToPct = (frame: number) => ((frame - windowStartFrame) / windowFrames) * 100;

    const applyZoom = (nextZoom: number) => {
        const clampedZoom = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
        const nextWindowFrames = totalFrames / clampedZoom;
        setZoom(clampedZoom);
        setPanStartPct(currentFrame / totalFrames - nextWindowFrames / totalFrames / 2);
    };

    const zoomIn = () => applyZoom(zoom * ZOOM_STEP);
    const zoomOut = () => applyZoom(zoom / ZOOM_STEP);
    const resetZoom = () => {
        setZoom(1);
        setPanStartPct(0);
    };

    const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
        if (dragState) return;
        setSelectedMomentId(null);
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
        onSeek(Math.round(windowStartFrame + pct * windowFrames));
    };

    const startDrag = (
        e: React.MouseEvent,
        moment: MomentScene,
        mode: DragMode
    ) => {
        e.preventDefault();
        e.stopPropagation();
        setSaveError(null);
        dragRef.current = {
            momentId: moment.id,
            mode,
            startX: e.clientX,
            startOffset: moment.offsetInParentFrames,
            startDuration: moment.durationInFrames,
            liveOffset: moment.offsetInParentFrames,
            liveDuration: moment.durationInFrames,
        };
        setDragState({ momentId: moment.id, mode });
        setLiveOffset(moment.offsetInParentFrames);
        setLiveDuration(moment.durationInFrames);
    };

    // Mirrors BeatBar's drag effect (see its own comment for why the
    // mutable state lives in a ref, subscribed once per drag rather than
    // once per pixel of movement) — extended here to cover both move
    // (changes offset, preserves duration) and resize (changes duration,
    // preserves offset) in one effect, matching OverlayStrip's own
    // move/resize split.
    useEffect(() => {
        if (!dragState) return;

        const onMouseMove = (e: MouseEvent) => {
            const drag = dragRef.current;
            if (!drag || !trackRef.current) return;
            const rect = trackRef.current.getBoundingClientRect();
            const framesPerPixel = windowFrames / rect.width;
            const deltaFrames = Math.round((e.clientX - drag.startX) * framesPerPixel);

            const parentEntry = resolved.find((r) => r.moment.id === drag.momentId);
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

    // Seeds selection from an AI chat edit (#54) and re-centers the view on
    // it — reuses onSeek/applyZoom exactly as a real click would, so a
    // moment created or changed off-screen (at 1x zoom that's most of an
    // episode) becomes visible without the user hunting for it.
    useEffect(() => {
        if (!highlightedId) return;
        const entry = resolved.find((r) => r.moment.id === highlightedId);
        if (!entry) return;
        setSelectedMomentId(highlightedId);
        onSeek(entry.startFrame);
        // Center on entry.startFrame directly, not applyZoom's usual
        // currentFrame — onSeek's effect on currentFrame hasn't landed yet
        // this tick, so reading it here would center on the stale position.
        const nextZoom = clamp(zoom > 1 ? zoom : 4, MIN_ZOOM, MAX_ZOOM);
        const nextWindowFrames = totalFrames / nextZoom;
        setZoom(nextZoom);
        setPanStartPct(entry.startFrame / totalFrames - nextWindowFrames / totalFrames / 2);
        // The bar itself may be off-screen (long page, many bars) even once
        // the segment inside it is in view — bring the whole bar on screen.
        trackRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [highlightedId]);

    // Cmd+E (Mac) / Ctrl+E (elsewhere) opens the inline text editor for
    // whichever text-eligible moment is currently selected — never on the
    // click that selects it (see BeatBar's #39 for the same rule). Global,
    // not scoped to the track element, matching BeatBar.
    useEffect(() => {
        if (!selectedMomentId) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "e" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            const entry = resolved.find((r) => r.moment.id === selectedMomentId);
            if (!entry || !isTextEligible({ kind: "moment", sceneId: entry.moment.id, treatment: entry.moment.treatment })) {
                return;
            }

            e.preventDefault();
            onEditRequested(selectedMomentId, selectedAnchorRef.current);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedMomentId, onEditRequested]);

    // Cmd+I (Mac) / Ctrl+I (elsewhere) opens the insert type picker at the
    // playhead — global like Cmd+E, but doesn't require a moment to be
    // selected first (inserting is independent of selection; only editing/
    // deleting act on a selection). Requires a presenter scene under the
    // playhead (see presenterAtPlayhead above) — silently does nothing
    // otherwise rather than erroring, the same "no valid target, no-op"
    // behavior Cmd+E already has when nothing text-eligible is selected.
    // Anchored to the playhead's own DOM position (not selectedAnchorRef,
    // which only ever gets set by clicking a moment segment and would
    // still be its unset {0,0} default if the user presses Cmd+I before
    // ever clicking one) — always correct regardless of click history.
    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "i" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
            if (!presenterAtPlayhead || !trackRef.current) return;

            e.preventDefault();
            const rect = trackRef.current.getBoundingClientRect();
            setPendingDeleteId(null);
            setInsertPickerAnchor({ x: rect.left + frameToPct(currentFrame) * (rect.width / 100), y: rect.bottom });
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [presenterAtPlayhead?.id, currentFrame, zoom, panStartPct]);

    // Delete/Backspace on a selected moment shows the inline confirm
    // (pendingDeleteId) rather than deleting immediately — a destructive,
    // one-keystroke action needs a second deliberate step, unlike Cmd+E's
    // edit (fully reversible, nothing lost by opening it).
    useEffect(() => {
        if (!selectedMomentId) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key !== "Delete" && e.key !== "Backspace") return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            setPendingDeleteId(selectedMomentId);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedMomentId]);

    // Appends a new content-empty moment at the playhead (see
    // resolve_manual_moment_creation for what "empty" means per kind), then
    // immediately opens its editor — a text moment gets the inline text
    // editor (matches clicking a text-eligible moment), everything else
    // opens the structured panel (matches clicking a non-text-eligible one)
    // since there's no single field to inline-edit for those.
    const doInsert = async (kind: MomentInsertKind) => {
        if (!presenterAtPlayhead) return;

        // The picker's own anchor is exactly where the inline text editor
        // should open too (both are "a floating box near where the user
        // was just looking") — captured before it's cleared below.
        const anchor = insertPickerAnchor ?? selectedAnchorRef.current;

        setInserting(true);
        setSaveError(null);

        try {
            const offsetInParentFrames = currentFrame - presenterAtPlayhead.timelineStartFrame;
            const result = await insertMoment(episodePath, presenterAtPlayhead.id, offsetInParentFrames, kind);
            onSaved();
            setInsertPickerAnchor(null);
            onSelect?.(result.sceneId);

            if (kind === "text") {
                setSelectedMomentId(result.sceneId);
                // "bottom-callout" is exactly what MANUAL_CREATION_TREATMENTS
                // maps "text" to server-side (see resolve_manual_moment_
                // creation) — passed explicitly so onEditRequested doesn't
                // need to look the treatment up from a scenePlan that may
                // not have this brand-new moment in it yet (see
                // openInlineMomentEditor's own comment on why that lookup
                // can't be trusted right after onSaved()).
                onEditRequested(result.sceneId, anchor, "bottom-callout");
            } else {
                onOpenStructuredEditor(result.sceneId);
            }
        } catch (e) {
            setSaveError(String(e));
        } finally {
            setInserting(false);
        }
    };

    // Removes the moment at pendingDeleteId from the full array and saves —
    // same "fetch fresh, patch by index, save the whole array" contract as
    // commitDrag, just filtering the index out instead of patching it.
    const doDelete = async () => {
        if (!pendingDeleteId) return;
        const index = momentIndexFromSceneId(pendingDeleteId);
        if (index === null) return;

        try {
            const data = await getMoments(episodePath);
            const moments = data.moments ?? [];
            const next = moments.filter((_: unknown, i: number) => i !== index);

            await saveMoments(episodePath, next);
            onSaved();
            setPendingDeleteId(null);
            setSelectedMomentId(null);
        } catch (e) {
            setSaveError(String(e));
        }
    };

    // Writes the FULL moments array back (matching BeatBar's commitResize/
    // saveMoments contract) — fetches moments.json fresh rather than
    // reconstructing it from scenePlan's already-merged moment scenes,
    // since a raw moment carries offsetInParentFrames/
    // maxDurationInParentFrames under those exact names (see
    // generate_moments.py's merge_moment_scenes: offset maps 1:1,
    // maxDurationInParentFrames -> durationInFrames). Server-side merge
    // clamps to whatever room is left in the parent scene, so a drag that
    // overshoots still saves successfully.
    const commitDrag = async (drag: DragState) => {
        const index = momentIndexFromSceneId(drag.momentId);
        if (index === null) return;

        try {
            const data = await getMoments(episodePath);
            const moments = data.moments ?? [];
            if (!moments[index]) return;

            const next = moments.map((m: any, i: number) =>
                i === index
                    ? {
                          ...m,
                          offsetInParentFrames: drag.liveOffset,
                          maxDurationInParentFrames: drag.liveDuration,
                      }
                    : m
            );

            await saveMoments(episodePath, next);
            onSaved();
        } catch (e) {
            setSaveError(String(e));
        }
    };

    const playheadPct = clamp(frameToPct(currentFrame), 0, 100);
    const playheadVisible = currentFrame >= windowStartFrame && currentFrame <= windowStartFrame + windowFrames;

    // Whether the CURRENTLY SELECTED moment specifically is text-eligible —
    // selectedMomentId is now set on every click regardless (so Delete
    // works for every treatment), but Cmd+E only actually does anything
    // for text-eligible ones, so the hint below must reflect the selected
    // moment's own treatment, not just "something is selected."
    const selectedEntry = selectedMomentId ? resolved.find((r) => r.moment.id === selectedMomentId) : undefined;
    const selectedIsTextEligible =
        !!selectedEntry &&
        isTextEligible({ kind: "moment", sceneId: selectedEntry.moment.id, treatment: selectedEntry.moment.treatment });

    return (
        <div style={styles.wrap}>
            <div style={styles.labelRow}>
                <span style={styles.label}>Moments ({resolved.length})</span>
                <span style={styles.legend}>
                    <span style={styles.legendItem}>
                        <span style={{ ...styles.legendDot, background: TEXT_COLOR }} /> text
                    </span>
                    <span style={styles.legendItem}>
                        <span style={{ ...styles.legendDot, background: CONTENT_TYPE_COLOR.image }} /> image
                    </span>
                    <span style={styles.legendItem}>
                        <span style={{ ...styles.legendDot, background: CONTENT_TYPE_COLOR.code }} /> code
                    </span>
                    <span style={styles.legendItem}>
                        <span style={{ ...styles.legendDot, background: CONTENT_TYPE_COLOR.diagram }} /> diagram
                    </span>
                </span>
                <div style={styles.zoomControls}>
                    <button className="secondary small" onClick={zoomIn} disabled={zoom >= MAX_ZOOM}>
                        Zoom in
                    </button>
                    <button className="secondary small" onClick={zoomOut} disabled={zoom <= MIN_ZOOM}>
                        Zoom out
                    </button>
                    <button className="secondary small" onClick={resetZoom} disabled={zoom === 1}>
                        Reset
                    </button>
                </div>
            </div>

            <div ref={trackRef} style={styles.track} onMouseDown={onTrackClick}>
                {resolved.map(({ moment, startFrame }) => {
                    const isDragging = dragState?.momentId === moment.id;
                    const offset = isDragging && dragState.mode === "move" ? liveOffset : moment.offsetInParentFrames;
                    const duration = isDragging ? liveDuration : moment.durationInFrames;
                    const effectiveStartFrame = startFrame - moment.offsetInParentFrames + offset;

                    const leftPct = frameToPct(effectiveStartFrame);
                    const rawWidthPct = (duration / windowFrames) * 100;

                    if (leftPct + rawWidthPct < 0 || leftPct > 100) return null;

                    const widthPct = Math.max(rawWidthPct, 0.6);
                    const label = momentLabel(moment);
                    const color = momentColor(moment);
                    const textEligible = isTextEligible({ kind: "moment", sceneId: moment.id, treatment: moment.treatment });
                    const isSelected = selectedMomentId === moment.id;

                    return (
                        <div
                            key={moment.id}
                            style={{
                                ...styles.segment,
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                background: color,
                                ...(isSelected ? styles.segmentSelected : {}),
                            }}
                            title={
                                isSelected && textEligible
                                    ? `${moment.id} — ${moment.treatment}: ${label} — press ${MOD_KEY_LABEL}+E to edit`
                                    : `${moment.id} — ${moment.treatment}: ${label}`
                            }
                            onClick={(e) => {
                                if (isDragging) return;
                                e.stopPropagation();
                                onSelect?.(moment.id);
                                // selectedMomentId is set on EVERY click,
                                // text-eligible or not — it's what makes
                                // Delete/Backspace work (see the delete
                                // effect above), and a non-text-eligible
                                // moment is just as deletable as a text
                                // one. The Cmd+E effect already re-checks
                                // isTextEligible itself before opening the
                                // inline editor, so this doesn't change
                                // when Cmd+E fires — only when Delete does.
                                selectedAnchorRef.current = { x: e.clientX, y: e.clientY };
                                setSelectedMomentId(moment.id);
                                onSeek(startFrame);
                                if (!textEligible) {
                                    // No single text field to inline-edit — keep
                                    // opening the full structured panel directly,
                                    // same as before #41.
                                    onOpenStructuredEditor(moment.id);
                                }
                            }}
                            onMouseDown={(e) => {
                                // Body-drag = move. Only text-ineligible clicks
                                // fire onClick's structured-editor path above;
                                // a mousedown-then-release-without-moving on a
                                // text-eligible segment still selects via onClick.
                                if (e.button !== 0) return;
                                startDrag(e, moment, "move");
                            }}
                        >
                            {widthPct > 4 && <span style={styles.segmentLabel}>{label}</span>}
                            <div
                                style={styles.resizeHandle}
                                onMouseDown={(e) => startDrag(e, moment, "resize")}
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
                    <span>Delete this moment?</span>
                    <button type="button" className="secondary small" onClick={doDelete} style={styles.deleteButton}>
                        Delete
                    </button>
                    <button type="button" className="secondary small" onClick={() => setPendingDeleteId(null)}>
                        Cancel
                    </button>
                </div>
            )}

            {insertPickerAnchor && (
                <InsertTypePicker
                    anchor={insertPickerAnchor}
                    disabled={inserting}
                    onPick={doInsert}
                    onCancel={() => setInsertPickerAnchor(null)}
                />
            )}

            <div style={styles.hint}>
                {selectedMomentId
                    ? selectedIsTextEligible
                        ? `Selected — press ${MOD_KEY_LABEL}+E to edit its text, Delete to remove it.`
                        : "Selected — press Delete to remove it, or click it again to open its editor."
                    : presenterAtPlayhead
                    ? `Press ${MOD_KEY_LABEL}+I to insert a moment here.${
                          zoom > 1
                              ? " Click a moment to select it, drag its body to move it or its right edge to resize."
                              : ""
                      }`
                    : zoom > 1
                    ? "Click a moment to select it, drag its body to move it or its right edge to resize, or click empty track to seek."
                    : "Zoom in for precise dragging — at full-episode width a short moment is too thin to grab reliably."}
            </div>
        </div>
    );
}

const INSERT_KIND_LABELS: { kind: MomentInsertKind; label: string }[] = [
    { kind: "text", label: "Text callout" },
    { kind: "image", label: "Image" },
    { kind: "code", label: "Code" },
    { kind: "diagram", label: "Diagram" },
];

// Cmd+I's type picker — a small fixed-position popup near wherever the
// shortcut was pressed, matching InlineTextEditor's own anchor pattern.
// Picking a kind hands off immediately to doInsert; there's no separate
// "confirm" step since picking a kind IS the confirmation (unlike delete,
// this action creates rather than destroys, so the lighter one-click flow
// is appropriate — mirrors why Cmd+E needs no confirmation either).
function InsertTypePicker({
    anchor,
    disabled,
    onPick,
    onCancel,
}: {
    anchor: { x: number; y: number };
    disabled: boolean;
    onPick: (kind: MomentInsertKind) => void;
    onCancel: () => void;
}) {
    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onCancel();
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [onCancel]);

    // Estimated popup height (label + 4 kind buttons + cancel + gaps/
    // padding) — flips to open ABOVE the anchor when there isn't enough
    // room below, same reasoning as the horizontal clamp already here.
    // Cmd+I's anchor is the playhead's own track position, which sits
    // fairly low in a typically-scrolled page, so opening below by
    // default clips off-screen (found live: "Code"/"Diagram" options were
    // unreachable) far more often than InlineTextEditor's click-derived
    // anchors ever did.
    const ESTIMATED_HEIGHT = 210;
    const openAbove = anchor.y + 12 + ESTIMATED_HEIGHT > window.innerHeight;

    return (
        <div
            style={{
                ...styles.insertPicker,
                left: Math.min(anchor.x, window.innerWidth - 220),
                top: openAbove ? Math.max(8, anchor.y - ESTIMATED_HEIGHT) : anchor.y + 12,
            }}
        >
            <div style={styles.insertPickerLabel}>Insert moment</div>
            {INSERT_KIND_LABELS.map(({ kind, label }) => (
                <button
                    key={kind}
                    type="button"
                    className="secondary small"
                    disabled={disabled}
                    onClick={() => onPick(kind)}
                    style={styles.insertPickerButton}
                >
                    {label}
                </button>
            ))}
            <button type="button" className="secondary small" disabled={disabled} onClick={onCancel}>
                Cancel
            </button>
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
    labelRow: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 8,
    },
    label: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
    },
    legend: {
        display: "flex",
        gap: 12,
        fontSize: typography.size.xs,
        color: colors.textMuted,
    },
    legendItem: {
        display: "flex",
        alignItems: "center",
        gap: 4,
    },
    legendDot: {
        width: 8,
        height: 8,
        borderRadius: "50%",
        flexShrink: 0,
    },
    zoomControls: {
        display: "flex",
        gap: 6,
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
        padding: "0 6px",
        fontSize: 10,
        fontWeight: typography.weight.semibold,
        color: "#fff",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        textShadow: "0 1px 2px rgba(0,0,0,0.5)",
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
    insertPicker: {
        position: "fixed",
        zIndex: 50,
        display: "flex",
        flexDirection: "column",
        gap: 4,
        width: 180,
        padding: 10,
        background: colors.surface,
        border: `1px solid ${colors.borderStrong}`,
        borderRadius: radius.lg,
        boxShadow: shadow.elevated,
    },
    insertPickerLabel: {
        fontSize: typography.size.xs,
        color: colors.textMuted,
        marginBottom: 2,
    },
    insertPickerButton: {
        textAlign: "left",
    },
};
