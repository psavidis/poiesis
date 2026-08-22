import { useEffect, useRef, useState } from "react";
import type { BeatScene, PresenterScene, ScenePlan } from "video-renderer-src/episode/types";
import { getBeats, insertBeat, saveBeats } from "./api";
import { colors, radius, typography } from "./tokens";
import type { TimelineZoom } from "./useTimelineZoom";

// A third, distinct color from SceneBar/MomentBar — beats are a
// genuinely different scene type (word-pop/underline/icon-accent, not a
// text/image treatment choice), so this doesn't reuse MomentBar's
// text/visual categories.
const BEAT_COLOR = colors.timelineBeat;

// Display-only label for the edit shortcut's hint text — the actual
// keydown check accepts either metaKey or ctrlKey regardless of platform,
// this only affects what the tooltip/hint says to press.
const MOD_KEY_LABEL = navigator.platform.toLowerCase().includes("mac") ? "Cmd" : "Ctrl";

interface Props {
    scenePlan: ScenePlan;
    totalFrames: number;
    currentFrame: number;
    onSeek: (absoluteFrame: number) => void;
    episodePath: string;
    onSaved: () => void;
    // Fired only when the user presses the edit shortcut (Cmd+E / Ctrl+E)
    // while a beat is selected — NOT on click. Selecting (clicking) a beat
    // highlights it and seeks the player there, same as before, but no
    // longer opens anything by itself; editing is a deliberate second step
    // (see #39 — explicitly not "click opens edit mode").
    onEditRequested: (sceneId: string, anchor: { x: number; y: number }) => void;
    // Set by EpisodeWorkspace right after a chat edit touches a beat on
    // this bar (#54) — seeds selection and re-centers the view on it.
    highlightedId?: string | null;
    // Single zoom/pan window shared with Scenes/Images/Moments (#86) —
    // owned by EpisodeWorkspace, not this component.
    timelineZoom: TimelineZoom;
    // Which bar currently owns the shared "selected segment" affordance —
    // set to "beat" via onActivateSelection whenever THIS bar's own click
    // selects a beat, so a sibling bar's stale selection (e.g. a moment
    // clicked earlier) gets cleared instead of both bars' Cmd+E listeners
    // staying live at once (see EpisodeWorkspace's activeSelectionBar).
    // When this prop stops being "beat" (another bar just took over),
    // this bar clears its own selectedBeatId in response.
    activeSelectionBar: string | null;
    onActivateSelection: () => void;
}

type DragState = {
    beatId: string;
    startX: number;
    startDuration: number;
    liveDuration: number;
};

// Mirrors DragState but lives in a ref, not useState — onMouseMove reads
// and writes this directly instead of going through setDragging on every
// pixel of movement. Both OverlayStrip.tsx (the moment-timing-adjustment
// equivalent this ports the pattern from) and an earlier version of this
// component put the whole drag object in useState with the effect
// depending on it — since onMouseMove called setDragging on every pixel,
// that made the drag effect (which does window.addEventListener) tear
// down and re-subscribe on every single mousemove event during a drag.
// That's harmless when mouseup only does setDragging(null) (OverlayStrip's
// case — double-firing a no-op is invisible), but this component's
// mouseup also PUTs to the server: the same tear-down/re-subscribe race
// let two mouseup listeners end up registered at once, firing two
// concurrent saves for one drag (confirmed via a live test against
// Episode 9 — one request got a real 409 Conflict from the two racing
// for the same episode's lock). The ref carries the mutable state the
// effect never needs to react to; dragBeatId (state) is the only piece
// that needs to trigger a re-render, and the effect depends on THAT
// (which only changes at drag start/end, not every pixel) instead of the
// whole mutable object.

// Every beat's resolved window across the full episode, so sparse,
// easy-to-miss beats are visible and jumpable at a glance instead of
// only discoverable by scrubbing into one (see #36). Zoom + drag-to-
// resize (see #38) let a beat's duration be lengthened/shortened
// directly here — at 1x (full episode), a 2s beat is too thin a sliver
// to grab reliably, so zooming narrows the visible window (in frames)
// around the current pan position until the target beat is a
// comfortable drag target. Saves live on drag-end, matching
// OverlayStrip's moment-timing-adjustment interaction — no separate
// "Save changes" step.
export function BeatBar({
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
    // Which beat is being dragged, if any — the only piece of drag state
    // that needs to be reactive (it controls which segment renders its
    // "isDragging" styling/readout). See DragState's own comment above
    // for why the rest of the drag's mutable state lives in a ref instead.
    const [dragBeatId, setDragBeatId] = useState<string | null>(null);
    const [liveDuration, setLiveDuration] = useState(0);
    const [saveError, setSaveError] = useState<string | null>(null);
    // The clicked-but-not-editing beat — highlighted, and the target of
    // Cmd+E/Ctrl+E (see #39). Click selects only; it never opens the
    // editor by itself, matching the explicit "should not enter edit mode
    // by default" requirement.
    const [selectedBeatId, setSelectedBeatId] = useState<string | null>(null);
    // Raw emphasis.json overriddenFields for whichever beat is selected —
    // not present on scenePlan's own merged BeatScene (see #58, mirrors
    // #57's provenance tracking for moments), so it's fetched separately
    // whenever selection changes rather than plumbing a new field through
    // the whole scene-plan merge just for this reset affordance.
    const [selectedOverriddenFields, setSelectedOverriddenFields] = useState<string[]>([]);
    // Delete/Backspace on a selected beat shows this inline confirm —
    // same pattern as MomentBar/ChapterStrip/ImageBar.
    const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
    const selectedAnchorRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

    // Another bar (moment/image/scene/chapter/background) just became the
    // active selection owner — clear this bar's own selection so its Cmd+E
    // listener below goes dormant instead of firing alongside whichever
    // bar the user actually clicked into (see activeSelectionBar's own doc
    // comment in EpisodeWorkspace for the bug this fixes).
    useEffect(() => {
        if (activeSelectionBar !== "beat") setSelectedBeatId(null);
    }, [activeSelectionBar]);
    const trackRef = useRef<HTMLDivElement>(null);
    const dragRef = useRef<DragState | null>(null);

    // resolved is computed unconditionally, NOT gated behind an early
    // return here — every hook in this component must be declared before
    // any conditional return, or deleting the last beat (item count
    // N -> 0) renders fewer hooks than the previous pass and React
    // crashes with "Rendered fewer hooks than expected" (confirmed live
    // in the identically-shaped ImageBar.tsx — see its own comment on
    // this exact bug). The actual early return sits just before the JSX
    // return, after every hook below has run.
    const trackById = new Map<string, PresenterScene>();
    scenePlan.scenes.forEach((s) => {
        if (s.type === "presenter") trackById.set(s.id, s);
    });

    const resolved = scenePlan.scenes
        .filter((s): s is BeatScene => s.type === "beat")
        .map((beat) => {
            const parent = trackById.get(beat.parentSceneId);
            if (!parent) return null;
            return { beat, parent, startFrame: parent.timelineStartFrame + beat.offsetInParentFrames };
        })
        .filter(
            (b): b is { beat: BeatScene; parent: PresenterScene; startFrame: number } => b !== null
        )
        .sort((a, b) => a.startFrame - b.startFrame);

    // The presenter scene under the playhead right now, if any — Cmd+I
    // inserts there, at the playhead's own offset into it. Mirrors
    // MomentBar's identical presenterAtPlayhead: a beat can only be
    // parented to a presenter scene (resolve_manual_beat_creation rejects
    // a title parent), so Cmd+I is simply unavailable while the playhead
    // sits over a title card.
    const presenterAtPlayhead = scenePlan.scenes.find(
        (s): s is PresenterScene =>
            s.type === "presenter" &&
            currentFrame >= s.timelineStartFrame &&
            currentFrame < s.timelineStartFrame + s.durationInFrames
    );

    const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
        if (dragBeatId) return;
        // A click that reaches here (not a segment — those stopPropagation)
        // is on empty track space, so it deselects rather than leaving a
        // stale selection highlighted after the user's attention has moved
        // elsewhere on the timeline.
        setSelectedBeatId(null);
        setPendingDeleteId(null);
        // Claims activeSelectionBar even though this click doesn't select a
        // particular beat (#86 follow-up, matches every other bar's own
        // onTrackClick) — without this, a plain click into this track to
        // position the playhead left whatever bar was last selected owning
        // the shared shortcuts (Cmd+I etc.) instead of this one.
        onActivateSelection();
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
        onSeek(Math.round(windowStartFrame + pct * windowFrames));
    };

    const startResize = (e: React.MouseEvent, beat: BeatScene) => {
        e.preventDefault();
        e.stopPropagation();
        setSaveError(null);
        dragRef.current = {
            beatId: beat.id,
            startX: e.clientX,
            startDuration: beat.durationInFrames,
            liveDuration: beat.durationInFrames,
        };
        setDragBeatId(beat.id);
        setLiveDuration(beat.durationInFrames);
    };

    // Subscribes exactly once per drag (dragBeatId only changes at
    // start/end, never mid-drag) instead of once per pixel of movement —
    // see DragState's comment for why that distinction is the actual fix,
    // not just a performance nicety. onMouseMove mutates dragRef.current
    // directly (no setState in the hot path) and only calls setLiveDuration
    // for the visual readout; onMouseUp reads the ref once, commits
    // whatever it holds, and clears both the ref and the state in one place.
    useEffect(() => {
        if (!dragBeatId) return;

        const onMouseMove = (e: MouseEvent) => {
            const drag = dragRef.current;
            if (!drag || !trackRef.current) return;
            const rect = trackRef.current.getBoundingClientRect();
            const framesPerPixel = windowFrames / rect.width;
            const deltaFrames = Math.round((e.clientX - drag.startX) * framesPerPixel);
            const newDuration = Math.max(1, drag.startDuration + deltaFrames);

            drag.liveDuration = newDuration;
            setLiveDuration(newDuration);
        };

        const onMouseUp = () => {
            const drag = dragRef.current;
            dragRef.current = null;
            setDragBeatId(null);
            if (drag) commitResize(drag.beatId, drag.liveDuration);
        };

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
        return () => {
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dragBeatId, windowFrames]);

    // Refetches the selected beat's raw overriddenFields (#58) whenever
    // selection changes — cleared immediately on deselect/reselect so a
    // stale reset button from a previously-selected beat can't flash
    // before the new fetch resolves.
    useEffect(() => {
        setSelectedOverriddenFields([]);
        if (!selectedBeatId) return;
        const match = /^scene-beat-(\d+)$/.exec(selectedBeatId);
        const index = match ? Number(match[1]) : null;
        if (index === null) return;
        let cancelled = false;
        getBeats(episodePath).then((data) => {
            if (cancelled) return;
            const beat = (data.beats ?? [])[index];
            setSelectedOverriddenFields(beat?.overriddenFields ?? []);
        });
        return () => {
            cancelled = true;
        };
    }, [selectedBeatId, episodePath]);

    const resetSelectedDuration = async () => {
        if (!selectedBeatId) return;
        const match = /^scene-beat-(\d+)$/.exec(selectedBeatId);
        const index = match ? Number(match[1]) : null;
        if (index === null) return;

        try {
            const data = await getBeats(episodePath);
            const beats = data.beats ?? [];
            if (!beats[index]) return;

            const nextOverridden = (beats[index].overriddenFields || []).filter(
                (f: string) => f !== "durationInFrames"
            );
            const next = beats.map((b: any, i: number) =>
                i === index ? { ...b, overriddenFields: nextOverridden } : b
            );

            await saveBeats(episodePath, next);
            setSelectedOverriddenFields(nextOverridden);
            onSaved();
        } catch (e) {
            setSaveError(String(e));
        }
    };

    // Seeds selection from an AI chat edit (#54) and re-centers the view on
    // it — mirrors MomentBar's own highlightedId effect.
    useEffect(() => {
        if (!highlightedId) return;
        const entry = resolved.find((r) => r.beat.id === highlightedId);
        if (!entry) return;
        onActivateSelection();
        setSelectedBeatId(highlightedId);
        onSeek(entry.startFrame);
        zoomToAtLeast4x(entry.startFrame);
        trackRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [highlightedId]);

    // Cmd+E (Mac) / Ctrl+E (elsewhere) opens the text editor for whichever
    // beat is currently selected — only while something IS selected, and
    // only via this explicit shortcut, never on the click that selects it
    // (see #39's explicit "should not enter edit mode by default").
    // Global, not scoped to the track element, since a beat can be
    // selected and then the shortcut pressed with focus anywhere on the
    // page — the same way a text editor's own keyboard shortcuts aren't
    // scoped to a specific DOM node either.
    useEffect(() => {
        if (!selectedBeatId) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "e" || !(e.metaKey || e.ctrlKey)) return;
            // Don't hijack Cmd+E while focus is already inside a text
            // field (e.g. the edit-plan chat box) — that keystroke belongs
            // to whatever the user is actually typing into.
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            onEditRequested(selectedBeatId, selectedAnchorRef.current);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedBeatId, onEditRequested]);

    // Cmd+I (Mac) / Ctrl+I (elsewhere) inserts a brand-new, content-empty
    // beat at the playhead (#86 follow-up) — mirrors MomentBar's own Cmd+I
    // exactly, including the activeSelectionBar gate (this bar's click
    // into empty track space now claims "beat" via onActivateSelection,
    // same as every other bar) that keeps ChapterStrip's own Cmd+I from
    // firing at the same time. Requires a presenter scene under the
    // playhead (see presenterAtPlayhead above) — silently does nothing
    // otherwise, matching MomentBar's identical "no valid target, no-op"
    // behavior. No type picker (unlike MomentBar's text/image/code/
    // diagram choice) — a beat has only one meaningful "kind" decision
    // (word-pop/underline/icon-accent) and it's made in BeatEditorPanel
    // right after insertion, not up front.
    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "i" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
            if (activeSelectionBar !== "beat") return;
            if (!presenterAtPlayhead || !trackRef.current) return;

            e.preventDefault();
            doInsert();
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [presenterAtPlayhead?.id, currentFrame, activeSelectionBar]);

    // Inserts a content-empty beat at the playhead, then immediately opens
    // BeatEditorPanel to fill in kind/text — same "insert empty, open
    // editor" flow as MomentBar's doInsert, just with no kind param (the
    // server always defaults to word-pop, see insertBeat's own comment).
    const doInsert = async () => {
        if (!presenterAtPlayhead) return;

        setSaveError(null);

        try {
            const offsetInParentFrames = currentFrame - presenterAtPlayhead.timelineStartFrame;
            const result = await insertBeat(episodePath, presenterAtPlayhead.id, offsetInParentFrames);
            onSaved();
            onActivateSelection();
            setSelectedBeatId(result.sceneId);
            onEditRequested(result.sceneId, selectedAnchorRef.current);
        } catch (e) {
            setSaveError(String(e));
        }
    };

    // Delete/Backspace on a selected beat shows the inline confirm —
    // mirrors MomentBar's own delete effect.
    useEffect(() => {
        if (!selectedBeatId) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key !== "Delete" && e.key !== "Backspace") return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            setPendingDeleteId(selectedBeatId);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedBeatId]);

    // Escape dismisses the delete confirm without deleting (found missing
    // during a live keyboard-shortcut sweep — mirrors the fix in
    // MomentBar/ChapterStrip/ImageBar).
    useEffect(() => {
        if (!pendingDeleteId) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") setPendingDeleteId(null);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [pendingDeleteId]);

    // Removes the beat at pendingDeleteId from the full array and saves —
    // same "fetch fresh, filter by index, save the whole array" contract
    // as commitResize, just filtering the index out instead of patching it.
    const doDelete = async () => {
        if (!pendingDeleteId) return;
        const match = /^scene-beat-(\d+)$/.exec(pendingDeleteId);
        const index = match ? Number(match[1]) : null;
        if (index === null) return;

        try {
            const data = await getBeats(episodePath);
            const beats = data.beats ?? [];
            const next = beats.filter((_: unknown, i: number) => i !== index);

            await saveBeats(episodePath, next);
            onSaved();
            setPendingDeleteId(null);
            setSelectedBeatId(null);
        } catch (e) {
            setSaveError(String(e));
        }
    };

    // Writes the FULL beats array back (matching saveMoments/
    // saveTitleScenes's own "rewrite the whole file" contract) — fetches
    // emphasis.json fresh rather than reconstructing it from scenePlan's
    // already-merged beat scenes, since a beat scene has lost fields
    // (reason) that only exist in emphasis.json and must round-trip
    // unchanged. Server-side merge_beat_scenes clamps the new duration to
    // whatever room is left in the parent scene, so a drag that
    // overshoots still saves successfully rather than failing outright.
    const commitResize = async (beatId: string, newDuration: number) => {
        const match = /^scene-beat-(\d+)$/.exec(beatId);
        const index = match ? Number(match[1]) : null;
        if (index === null) return;

        try {
            const data = await getBeats(episodePath);
            const beats = data.beats ?? [];
            if (!beats[index]) return;

            const next = beats.map((b: any, i: number) =>
                i === index ? { ...b, durationInFrames: newDuration } : b
            );

            const saved = await saveBeats(episodePath, next);
            if (beatId === selectedBeatId) {
                setSelectedOverriddenFields(saved?.beats?.[index]?.overriddenFields ?? []);
            }
            onSaved();
        } catch (e) {
            setSaveError(String(e));
        }
    };

    // Every hook above has now run unconditionally on every render — safe
    // to bail on rendering anything from here on.
    //
    // Deliberately does NOT also bail on resolved.length === 0 (#86
    // follow-up, same fix as #79's MomentBar equivalent) — now that Cmd+I
    // can insert a beat here, returning null when resolved is empty would
    // make a beat-less episode's first beat unreachable: this bar's Cmd+I
    // listener needs trackRef.current to actually be mounted to insert at
    // all. totalFrames <= 0 is kept as the only bail-out — that's a
    // genuinely unloaded episode, not an empty-but-valid beats list.
    if (totalFrames <= 0) return null;

    return (
        <div style={styles.wrap}>
            <div style={styles.label}>Beats ({resolved.length})</div>

            <div ref={trackRef} style={styles.track} onMouseDown={onTrackClick}>
                {resolved.map(({ beat, parent, startFrame }) => {
                    const isDragging = dragBeatId === beat.id;
                    const duration = isDragging ? liveDuration : beat.durationInFrames;

                    const leftPct = frameToPct(startFrame);
                    const rawWidthPct = (duration / windowFrames) * 100;

                    // Skip segments entirely outside the visible window —
                    // avoids rendering (and clamp-distorting into visible
                    // slivers) hundreds of off-screen beats at high zoom.
                    if (leftPct + rawWidthPct < 0 || leftPct > 100) return null;

                    const widthPct = Math.max(rawWidthPct, 0.4);
                    const maxDuration = Math.max(1, parent.durationInFrames - beat.offsetInParentFrames);

                    const isSelected = selectedBeatId === beat.id;

                    return (
                        <div
                            key={beat.id}
                            style={{
                                ...styles.segment,
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                ...(isSelected ? styles.segmentSelected : {}),
                            }}
                            title={
                                isSelected
                                    ? `${beat.id} — ${beat.kind}: ${beat.text} (${duration}f) — press ${MOD_KEY_LABEL}+E to edit`
                                    : `${beat.id} — ${beat.kind}: ${beat.text} (${duration}f)`
                            }
                            onClick={(e) => {
                                if (isDragging) return;
                                e.stopPropagation();
                                selectedAnchorRef.current = { x: e.clientX, y: e.clientY };
                                onActivateSelection();
                                setSelectedBeatId(beat.id);
                                setPendingDeleteId(null);
                                onSeek(startFrame);
                            }}
                        >
                            {widthPct > 3 && <span style={styles.segmentLabel}>{beat.text}</span>}
                            {isSelected && (
                                // Only offered once selected — matches
                                // MomentBar's own rule (#82): while free-
                                // navigating (this beat not yet selected),
                                // the only available action is
                                // click-to-select, so the cursor/handle
                                // shouldn't imply a resize is available yet.
                                <div
                                    style={styles.resizeHandle}
                                    onMouseDown={(e) => startResize(e, beat)}
                                    title={`Drag to resize (max ${maxDuration}f)`}
                                />
                            )}
                            {isDragging && (
                                <div style={styles.readout}>{(duration / 30).toFixed(1)}s</div>
                            )}
                        </div>
                    );
                })}

                {playheadVisible && <div style={{ ...styles.playhead, left: `${playheadPct}%` }} />}
            </div>

            {saveError && <div style={styles.error}>{saveError}</div>}

            {pendingDeleteId && (
                <div style={styles.deleteConfirm}>
                    <span>Delete this beat?</span>
                    <button type="button" className="secondary small" onClick={doDelete} style={styles.deleteButton}>
                        Delete
                    </button>
                    <button type="button" className="secondary small" onClick={() => setPendingDeleteId(null)}>
                        Cancel
                    </button>
                </div>
            )}

            <div style={styles.hintRow}>
                <div style={styles.hint}>
                    {selectedBeatId
                        ? `Selected — press ${MOD_KEY_LABEL}+E to edit its text, Delete to remove it.`
                        : presenterAtPlayhead
                        ? `Press ${MOD_KEY_LABEL}+I to insert a beat here.${
                              zoom > 1 ? " Click a beat to select it." : ""
                          }`
                        : zoom > 1
                        ? "Click a beat to select it, drag its right edge to resize, or click anywhere to seek."
                        : "Zoom in to drag a beat's duration — at full-episode width a 2s beat is too thin to grab reliably."}
                </div>
                {selectedBeatId && selectedOverriddenFields.includes("durationInFrames") && (
                    <button
                        type="button"
                        className="secondary small"
                        onClick={resetSelectedDuration}
                        title="This duration was manually resized — reset to let the AI decide it again next time"
                    >
                        Reset duration to Automatic
                    </button>
                )}
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
        background: BEAT_COLOR,
        display: "flex",
        alignItems: "center",
        overflow: "visible",
        cursor: "pointer",
        boxShadow: "0 0 0 0px transparent",
    },
    // Whole-segment highlight for the selected beat — a visibly thicker,
    // brighter outline (not just a subtle tint) so "this beat is selected,
    // press Cmd+E to edit" reads as a distinct state from the normal
    // resting/hover appearance.
    segmentSelected: {
        boxShadow: "0 0 0 2px #ffffff, 0 0 8px rgba(255,255,255,0.5)",
        zIndex: 1,
    },
    segmentLabel: {
        padding: "0 5px",
        fontSize: 10,
        fontWeight: typography.weight.semibold,
        // Dark text on the orange beat background specifically — not a
        // shared token, since it's a computed contrast color for
        // BEAT_COLOR, not a reused UI color elsewhere.
        color: "#1a1300",
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
    hintRow: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
    },
    hint: {
        fontSize: typography.size.xs,
        color: colors.textMuted,
    },
};
