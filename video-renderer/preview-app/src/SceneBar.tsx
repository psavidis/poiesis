import { useEffect, useRef, useState } from "react";
import type { PresenterScene, ScenePlan, TitleScene } from "video-renderer-src/episode/types";
import { colors, radius, typography } from "./tokens";
import { getTitleScenes, saveTitleScenes } from "./api";
import type { TimelineZoom } from "./useTimelineZoom";

// Presenter clips cycle through a small palette of timelinePresenter shades
// (#115) so adjacent clips are distinguishable from each other; titles stay
// a single fixed color since they're rarer and already visually distinct
// from presenter clips by hue. Still deliberately its own hue family from
// ChapterStrip's chapterPalette (which groups scenes by topic, a different
// grouping) so the two strips aren't mistaken for showing the same thing.
const PRESENTER_COLOR_PALETTE = colors.presenterPalette;
const TITLE_COLOR = colors.timelineTitle;

// Display-only label for the edit shortcut's hint text — mirrors BeatBar's
// own MOD_KEY_LABEL constant.
const MOD_KEY_LABEL = navigator.platform.toLowerCase().includes("mac") ? "Cmd" : "Ctrl";

interface Props {
    scenePlan: ScenePlan;
    totalFrames: number;
    currentFrame: number;
    onSeek: (absoluteFrame: number) => void;
    // Passes the click's screen position alongside the title text so the
    // caller can anchor a floating inline text editor near where the user
    // actually clicked (see #34's InlineTextEditor) — not needed for the
    // seek itself, only for positioning that editor.
    onSelectTitle: (titleText: string, anchor: { x: number; y: number }) => void;
    // Fired only when the user presses the edit shortcut (Cmd+E/Ctrl+E)
    // while a PRESENTER (clip) segment is selected — NOT on click, same
    // "select first, edit is a deliberate second step" rule every other
    // bar in this app follows (#78: presenter segments previously had no
    // click handler at all, so there was no way to select — let alone
    // edit — a clip's own trim points or crossfade transition).
    onOpenPresenterEditor: (sceneId: string) => void;
    // Set by EpisodeWorkspace right after a chat edit touches a presenter
    // or title scene on this bar (#54) — unlike ChapterStrip, scenes here
    // do carry their own id, so this is keyed by sceneId directly.
    highlightedId?: string | null;
    // Required for the duration-drag handle (#83) to load/save
    // title_scenes.json directly — same "fetch fresh, patch, save whole
    // array" contract as BeatBar's commitResize.
    episodePath: string;
    onSaved: () => void;
    // Single zoom/pan window shared with Moments/Images/Beats (#86) — owned
    // by EpisodeWorkspace, not this component, so zooming here keeps every
    // other bar in sync instead of each bar tracking its own scale.
    timelineZoom: TimelineZoom;
    // See BeatBar's identical prop's own doc comment — mutual-exclusion
    // signal so this bar's selection (and its Cmd+E listener) clears
    // itself once a different bar becomes the active selection owner.
    activeSelectionBar: string | null;
    onActivateSelection: () => void;
}

// Minimum on-screen duration a dragged title can be shrunk to, so a fast
// drag-past-zero can't produce an unreadable flash-card title.
const MIN_TITLE_DURATION_FRAMES = 6;

// Every track scene (presenter clip or title card) as its own segment
// across the full episode, so individual clips/titles are visible and
// jumpable without scrubbing — ChapterStrip only shows chapter-level
// grouping, not where each underlying clip/title actually starts. Title
// segments use the same select-then-Cmd+E lifecycle as ChapterStrip (#40)
// and BeatBar (#39) — click selects/highlights only, Cmd+E/Ctrl+E opens
// the title editor.
export function SceneBar({
    scenePlan,
    totalFrames,
    currentFrame,
    onSeek,
    onSelectTitle,
    onOpenPresenterEditor,
    highlightedId,
    episodePath,
    onSaved,
    timelineZoom,
    activeSelectionBar,
    onActivateSelection,
}: Props) {
    const { zoom, windowFrames, windowStartFrame, frameToPct, playheadPct, playheadVisible, zoomToAtLeast4x } =
        timelineZoom;

    const [selectedTitle, setSelectedTitle] = useState<string | null>(null);
    // The clicked-but-not-editing PRESENTER segment, by sceneId — mutually
    // exclusive with selectedTitle (only one segment on this bar is ever
    // selected at a time; clicking one type clears the other below).
    const [selectedPresenterId, setSelectedPresenterId] = useState<string | null>(null);
    const selectedAnchorRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
    const trackRef = useRef<HTMLDivElement>(null);
    // Tracks the track div's own on-screen width for the label-fit check
    // below (#115) — reading trackRef.current.getBoundingClientRect()
    // directly during render would return 0 on the very first render (the
    // ref only attaches AFTER that render commits), hiding every label
    // until some unrelated state change happened to force a re-render.
    // ResizeObserver keeps this correct across window resizes too, not
    // just the initial mount.
    const [trackWidthPx, setTrackWidthPx] = useState(0);

    useEffect(() => {
        const el = trackRef.current;
        if (!el) return;
        const observer = new ResizeObserver(([entry]) => setTrackWidthPx(entry.contentRect.width));
        observer.observe(el);
        return () => observer.disconnect();
    }, []);

    // See BeatBar's identical effect's own doc comment — clears this bar's
    // selection once a different bar takes over the shared selection.
    useEffect(() => {
        if (activeSelectionBar !== "scene") {
            setSelectedTitle(null);
            setSelectedPresenterId(null);
        }
    }, [activeSelectionBar]);

    // Drag-to-resize a selected title's on-screen duration (#83) — same
    // ref-driven "mutate during move, commit once on mouseup" pattern as
    // BeatBar's startResize/commitResize, adapted to titles being matched
    // by their stable segmentId rather than a positional array index.
    const [dragSegmentId, setDragSegmentId] = useState<string | null>(null);
    const [liveDuration, setLiveDuration] = useState<number>(0);
    const dragRef = useRef<{
        segmentId: string;
        startX: number;
        startDuration: number;
        liveDuration: number;
    } | null>(null);
    const [saveError, setSaveError] = useState<string | null>(null);

    // Seeds selection from an AI chat edit (#54). Only title scenes have a
    // highlight affordance here (selectedTitle is text-keyed, matching the
    // click handler below) — a highlighted presenter scene still seeks the
    // player there, it just has no distinct highlighted style to seed.
    useEffect(() => {
        if (!highlightedId) return;
        const scene = scenePlan.scenes.find((s) => s.id === highlightedId);
        if (!scene || (scene.type !== "presenter" && scene.type !== "title")) return;
        if (scene.type === "title") {
            onActivateSelection();
            setSelectedTitle(scene.text);
            zoomToAtLeast4x(scene.timelineStartFrame + scene.durationInFrames / 2);
        }
        onSeek(scene.timelineStartFrame);
        trackRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [highlightedId]);

    useEffect(() => {
        if (!selectedTitle) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "e" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            onSelectTitle(selectedTitle, selectedAnchorRef.current);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedTitle, onSelectTitle]);

    // Cmd+E/Ctrl+E on a selected PRESENTER segment opens the structured
    // trim/transition editor (#78) — mirrors the title listener directly
    // above, just targeting onOpenPresenterEditor instead of the inline
    // text editor (a presenter scene has no single text field to edit
    // inline, only sourceStartFrame/sourceEndFrame/effects, which need
    // PresenterEditorPanel's own form).
    useEffect(() => {
        if (!selectedPresenterId) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "e" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            onOpenPresenterEditor(selectedPresenterId);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedPresenterId, onOpenPresenterEditor]);

    const startResize = (e: React.MouseEvent, scene: TitleScene) => {
        e.preventDefault();
        e.stopPropagation();
        setSaveError(null);
        dragRef.current = {
            segmentId: scene.text,
            startX: e.clientX,
            startDuration: scene.durationInFrames,
            liveDuration: scene.durationInFrames,
        };
        setDragSegmentId(scene.text);
        setLiveDuration(scene.durationInFrames);
    };

    // Writes the FULL titles array back (matching saveBeats/saveMoments's
    // own "rewrite the whole file" contract). Titles have no positional
    // index to key off in SceneBar (unlike BeatBar) but DO have unique text
    // at any given time, so this reuses ChapterStrip's own
    // match-by-.text convention (see commitBoundaryMove) for consistency.
    const commitResize = async (titleText: string, newDuration: number) => {
        try {
            const current = await getTitleScenes(episodePath);
            const index = current.findIndex((t) => t.text === titleText);
            if (index === -1) return;

            const next = current.map((t, i) =>
                i === index ? { ...t, durationFrames: newDuration } : t
            );

            await saveTitleScenes(episodePath, next);
            onSaved();
        } catch (err) {
            setSaveError(String(err));
        }
    };

    // Same "subscribe once per drag, mutate a ref in the hot path, commit
    // once on mouseup" pattern as BeatBar's own resize effect.
    useEffect(() => {
        if (!dragSegmentId) return;

        const onMouseMove = (e: MouseEvent) => {
            const drag = dragRef.current;
            if (!drag || !trackRef.current) return;
            const rect = trackRef.current.getBoundingClientRect();
            const framesPerPixel = windowFrames / rect.width;
            const deltaFrames = Math.round((e.clientX - drag.startX) * framesPerPixel);
            const newDuration = Math.max(MIN_TITLE_DURATION_FRAMES, drag.startDuration + deltaFrames);

            drag.liveDuration = newDuration;
            setLiveDuration(newDuration);
        };

        const onMouseUp = () => {
            const drag = dragRef.current;
            dragRef.current = null;
            setDragSegmentId(null);
            if (drag) commitResize(drag.segmentId, drag.liveDuration);
        };

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
        return () => {
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dragSegmentId, windowFrames]);

    if (totalFrames <= 0) return null;

    const scenes = scenePlan.scenes.filter(
        (s): s is PresenterScene | TitleScene => s.type === "presenter" || s.type === "title"
    );

    if (scenes.length === 0) return null;

    const sorted = [...scenes].sort((a, b) => a.timelineStartFrame - b.timelineStartFrame);

    // Running index across presenter scenes only (titles keep their own
    // fixed TITLE_COLOR) — used to cycle PRESENTER_COLOR_PALETTE below so
    // adjacent clips are visually distinguishable, computed once here
    // rather than inline in the map since "adjacent" needs each presenter
    // scene's position among *other presenter scenes*, not its position in
    // the combined presenter+title `sorted` array.
    let presenterCounter = 0;
    const presenterIndexById = new Map<string, number>();
    for (const scene of sorted) {
        if (scene.type === "presenter") presenterIndexById.set(scene.id, presenterCounter++);
    }

    const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
        if (dragSegmentId) return;
        setSelectedTitle(null);
        setSelectedPresenterId(null);
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
        onSeek(Math.round(windowStartFrame + pct * windowFrames));
    };

    return (
        <div style={styles.wrap}>
            <div style={styles.label}>Scenes ({sorted.length})</div>

            <div ref={trackRef} style={styles.track} onMouseDown={onTrackClick}>
                {sorted.map((scene) => {
                    const isTitle = scene.type === "title";
                    const isDragging = isTitle && dragSegmentId === scene.text;
                    const durationFrames = isDragging ? liveDuration : scene.durationInFrames;

                    const leftPct = frameToPct(scene.timelineStartFrame);
                    const rawWidthPct = (durationFrames / windowFrames) * 100;

                    // Skip segments entirely outside the visible window —
                    // same rationale as BeatBar's own skip, avoids
                    // clamp-distorting far-off-screen scenes into visible
                    // slivers at high zoom.
                    if (leftPct + rawWidthPct < 0 || leftPct > 100) return null;

                    const widthPct = Math.max(rawWidthPct, 0.4);
                    const label = isTitle ? scene.text : `clip ${scene.videoId}`;
                    const isSelected = isTitle
                        ? selectedTitle === scene.text
                        : selectedPresenterId === scene.id;
                    const presenterIndex = presenterIndexById.get(scene.id) ?? 0;
                    // Roughly how many px this segment gets at the track's
                    // current on-screen width — segmentLabel's own font/padding
                    // (10px + 6px each side) need ~7px per character, so a
                    // label that can't fit is hidden rather than left to
                    // CSS text-overflow ellipsis, which for a short label like
                    // "clip 007" renders as the barely-there "clip …" (#115 —
                    // reads as a missing name, not a legitimately truncated
                    // one). The full label is still always available via this
                    // segment's title tooltip below.
                    const segmentWidthPx = (widthPct / 100) * trackWidthPx;
                    const labelFits = segmentWidthPx >= label.length * 7 + 12;

                    return (
                        <div
                            key={scene.id}
                            style={{
                                ...styles.segment,
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                background: isTitle
                                    ? TITLE_COLOR
                                    : PRESENTER_COLOR_PALETTE[presenterIndex % PRESENTER_COLOR_PALETTE.length],
                                cursor: "pointer",
                                ...(isSelected ? styles.segmentSelected : {}),
                            }}
                            title={
                                isSelected
                                    ? isTitle
                                        ? `${label} — press ${MOD_KEY_LABEL}+E to edit, drag right edge to resize`
                                        : `${scene.id} — press ${MOD_KEY_LABEL}+E to edit this clip's trim/transition`
                                    : `${scene.id} — click to select, then ${MOD_KEY_LABEL}+E to edit: ${label}`
                            }
                            onClick={(e) => {
                                if (isDragging) return;
                                e.stopPropagation();
                                selectedAnchorRef.current = { x: e.clientX, y: e.clientY };
                                onActivateSelection();
                                onSeek(scene.timelineStartFrame);
                                if (isTitle) {
                                    setSelectedTitle(scene.text);
                                    setSelectedPresenterId(null);
                                    // Auto-zooms in around the just-selected title so
                                    // its resize handle is a comfortable drag target
                                    // right away, instead of requiring a separate
                                    // manual zoom step first (this session's ask).
                                    zoomToAtLeast4x(scene.timelineStartFrame + scene.durationInFrames / 2);
                                } else {
                                    setSelectedPresenterId(scene.id);
                                    setSelectedTitle(null);
                                }
                            }}
                        >
                            {labelFits && <span style={styles.segmentLabel}>{label}</span>}
                            {/* Only offered once selected, and only for titles — matches
                                BeatBar/MomentBar's own rule (#82): while free-navigating
                                (this title not yet selected), the only available action is
                                click-to-select, so the cursor/handle shouldn't imply a resize
                                is available yet. A presenter clip's duration is derived from
                                its own source trim, not an independently draggable on-screen
                                span the way a title card's is — its own editable window
                                (sourceStartFrame/sourceEndFrame) lives in PresenterEditorPanel
                                instead (#78), not this inline drag handle. */}
                            {isTitle && isSelected && (
                                <div
                                    style={styles.resizeHandle}
                                    onMouseDown={(e) => startResize(e, scene)}
                                    title="Drag to resize this title's on-screen duration"
                                />
                            )}
                            {isDragging && (
                                <div style={styles.readout}>{(durationFrames / 30).toFixed(1)}s</div>
                            )}
                        </div>
                    );
                })}

                {playheadVisible && <div style={{ ...styles.playhead, left: `${playheadPct}%` }} />}
            </div>

            {saveError && <div style={styles.error}>{saveError}</div>}

            <div style={styles.hint}>
                {selectedTitle
                    ? `Selected — press ${MOD_KEY_LABEL}+E to edit, drag its right edge to resize.`
                    : selectedPresenterId
                    ? `Selected — press ${MOD_KEY_LABEL}+E to edit this clip's trim/transition.`
                    : zoom > 1
                    ? "Click a title or clip to select it, or click anywhere to seek."
                    : "Select a title or clip — titles resize by dragging once zoomed in; clips open an editor for trim/transition."}
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
    // Mirrors BeatBar/ChapterStrip's selected styling.
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
    error: {
        fontSize: typography.size.sm,
        color: colors.error,
    },
    hint: {
        fontSize: typography.size.xs,
        color: colors.textMuted,
    },
};
