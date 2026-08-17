import { useEffect, useRef, useState } from "react";
import type { ScenePlan, TitleScene } from "video-renderer-src/episode/types";
import { colors, radius, typography } from "./tokens";
import { getChapterBoundaryPositions, getTitleScenes, saveTitleScenes, type ChapterBoundaryPosition } from "./api";

// Display-only label for the edit shortcut's hint text — mirrors BeatBar's
// own MOD_KEY_LABEL constant (kept per-file rather than shared since it's
// a one-line platform sniff, not worth a shared module for).
const MOD_KEY_LABEL = navigator.platform.toLowerCase().includes("mac") ? "Cmd" : "Ctrl";

interface Chapter {
    title: string | null; // null = the lead-in before the first title card
    startFrame: number;
    endFrame: number;
}

// Title scenes mark where a new topic starts (see CLAUDE.md: "titles get
// proposed once per clip, only for genuine topic changes") but only carry
// their own on-screen duration, not a "chapter length" — a chapter runs
// from one title's start to the next title's start (or to the end of the
// episode for the last one), which is what this derives.
function chaptersFromTitles(titles: TitleScene[], totalFrames: number): Chapter[] {
    const sorted = [...titles].sort((a, b) => a.timelineStartFrame - b.timelineStartFrame);

    const chapters: Chapter[] = [];

    if (sorted.length === 0 || sorted[0].timelineStartFrame > 0) {
        chapters.push({
            title: null,
            startFrame: 0,
            endFrame: sorted[0]?.timelineStartFrame ?? totalFrames,
        });
    }

    sorted.forEach((title, i) => {
        const next = sorted[i + 1];
        chapters.push({
            title: title.text,
            startFrame: title.timelineStartFrame,
            endFrame: next ? next.timelineStartFrame : totalFrames,
        });
    });

    return chapters;
}

// A pleasant, stable-per-index palette so adjacent chapters are visually
// distinct without needing per-episode color assignment — cycles rather
// than growing unboundedly for episodes with many chapters.
const CHAPTER_COLORS = colors.chapterPalette;

interface Props {
    scenePlan: ScenePlan;
    totalFrames: number;
    currentFrame: number;
    fps: number;
    onSeek: (absoluteFrame: number) => void;
    // Opens the inline text editor for a chapter's underlying TitleScene
    // (see #34) — chapters ARE title scenes (chaptersFromTitles derives
    // one chapter per TitleScene, see above). Same anchor-aware signature
    // as SceneBar/MomentBar's onSelect* callbacks. Optional so ChapterStrip
    // still works standalone without every caller needing to pass a no-op.
    onSelectTitle?: (titleText: string, anchor: { x: number; y: number }) => void;
    // Set by EpisodeWorkspace right after a chat edit touches a title
    // scene (#54) — keyed by title text (a chapter's own identity here,
    // since chapters aren't derived with their own scene id), not sceneId.
    highlightedTitleText?: string | null;
    episodePath: string;
    onSaved?: () => void;
}

type DragState = {
    // Index into `titles` (sorted by timelineStartFrame) of the boundary
    // being dragged — a chapter boundary IS a title's own position, so
    // moving it means changing that title's segmentId.
    titleIndex: number;
    liveFrame: number;
};

// A full-episode strip dividing the video into chapters at each title
// card, so the shape of the whole episode is visible at a glance — how
// long each topic runs, how many chapters there are, and where the
// current playhead sits relative to all of them. Clicking a chapter (not
// the pre-title "Intro" segment) selects/highlights it and seeks there;
// pressing Cmd+E (Mac) / Ctrl+E while selected opens that chapter's
// underlying title text editor via onSelectTitle (see #40) — chapters ARE
// title scenes, same select-then-edit lifecycle already used by BeatBar
// (#39), not click-opens-immediately. Only rendered in the full-episode
// preview, not the scene-scoped "Adjust timing" view, which already has
// its own OverlayStrip.
export function ChapterStrip({
    scenePlan,
    totalFrames,
    currentFrame,
    fps,
    onSeek,
    onSelectTitle,
    highlightedTitleText,
    episodePath,
    onSaved,
}: Props) {
    const titles = scenePlan.scenes
        .filter((s): s is TitleScene => s.type === "title")
        .sort((a, b) => a.timelineStartFrame - b.timelineStartFrame);

    // The clicked-but-not-editing chapter's title text — highlighted, and
    // the target of Cmd+E/Ctrl+E. Click selects only; it never opens the
    // editor by itself (mirrors BeatBar's selectedBeatId).
    const [selectedTitle, setSelectedTitle] = useState<string | null>(null);
    const selectedAnchorRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
    const trackRef = useRef<HTMLDivElement>(null);

    // Every transcript segment's resolved timeline frame — fetched once
    // per episode so a boundary drag can snap client-side with no
    // per-pixel server round trip (see getChapterBoundaryPositions).
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

    // Which chapter boundary (by index into `titles`) is being dragged, if
    // any — the only piece of drag state that needs to be reactive (it
    // controls the live readout/handle styling). Mirrors BeatBar's
    // dragBeatId/dragRef split: the ref carries the mutable live frame so
    // onMouseMove never re-subscribes the window listeners on every pixel
    // (see BeatBar.tsx's DragState comment for the concurrent-save bug
    // that split avoids).
    const [dragTitleIndex, setDragTitleIndex] = useState<number | null>(null);
    const [liveFrame, setLiveFrame] = useState(0);
    const [dragError, setDragError] = useState<string | null>(null);
    const dragRef = useRef<DragState | null>(null);
    // Delete/Backspace on a selected title shows this inline confirm
    // rather than deleting immediately — same pattern as MomentBar's
    // pendingDeleteId. Set to the SELECTED title's text (chapters/titles
    // are correlated by text throughout this file, not id).
    const [pendingDeleteText, setPendingDeleteText] = useState<string | null>(null);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    // Seeds selection from an AI chat edit (#54) — no zoom/pan to
    // re-center here (unlike MomentBar/BeatBar/ImageBar), this strip
    // already spans the full episode at a fixed scale, so the chapter is
    // always in view horizontally once selected; onSeek still jumps the
    // player there, and scrollIntoView handles the strip itself being
    // vertically off-screen on a long page.
    useEffect(() => {
        if (!highlightedTitleText) return;
        const chapter = titles.find((t) => t.text === highlightedTitleText);
        if (!chapter) return;
        setSelectedTitle(highlightedTitleText);
        onSeek(chapter.timelineStartFrame);
        trackRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [highlightedTitleText]);

    // Global (not scoped to the track element) so the shortcut fires with
    // focus anywhere on the page, same reasoning as BeatBar's own listener.
    useEffect(() => {
        if (!selectedTitle || !onSelectTitle) return;

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

    // Delete/Backspace on a selected title shows the inline confirm —
    // mirrors MomentBar's own delete effect. Unlike Cmd+E (which only
    // fires when onSelectTitle is wired up), deleting doesn't depend on
    // that prop, so this listener registers whenever something's selected.
    useEffect(() => {
        if (!selectedTitle) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key !== "Delete" && e.key !== "Backspace") return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            setPendingDeleteText(selectedTitle);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedTitle]);

    // Escape dismisses the delete confirm without deleting (found missing
    // during a live keyboard-shortcut sweep — mirrors the fix in
    // MomentBar/BeatBar/ImageBar).
    useEffect(() => {
        if (!pendingDeleteText) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") setPendingDeleteText(null);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [pendingDeleteText]);

    // Same "fetch fresh, filter by index, save the whole array" contract
    // as TitleEditorPanel's own remove() — matched by text, the only
    // identity title_scenes.json entries and merged scene-plan TitleScenes
    // share (see this file's own comments on that known limitation).
    const doDelete = async () => {
        if (!pendingDeleteText) return;

        try {
            const current = await getTitleScenes(episodePath);
            const index = current.findIndex((t) => t.text === pendingDeleteText);
            if (index === -1) return;

            const next = current.filter((_, i) => i !== index);
            await saveTitleScenes(episodePath, next);
            onSaved?.();
            setPendingDeleteText(null);
            setSelectedTitle(null);
        } catch (e) {
            setDeleteError(String(e));
        }
    };

    // Nearest resolvable segment position to a raw pixel-derived frame —
    // the actual "snap" a drag performs, purely client-side against the
    // positions fetched above.
    const snapToNearestPosition = (rawFrame: number): ChapterBoundaryPosition | null => {
        if (boundaryPositions.length === 0) return null;
        return boundaryPositions.reduce((nearest, p) =>
            Math.abs(p.timelineFrame - rawFrame) < Math.abs(nearest.timelineFrame - rawFrame) ? p : nearest
        );
    };

    const startDrag = (e: React.MouseEvent, titleIndex: number) => {
        e.preventDefault();
        e.stopPropagation();
        setDragError(null);
        const startFrame = titles[titleIndex].timelineStartFrame;
        dragRef.current = { titleIndex, liveFrame: startFrame };
        setDragTitleIndex(titleIndex);
        setLiveFrame(startFrame);
    };

    // Subscribed only while dragTitleIndex is set (start/end, not every
    // pixel) — same rationale as BeatBar's onMouseMove/onMouseUp effect.
    useEffect(() => {
        if (dragTitleIndex === null) return;

        const onMouseMove = (e: MouseEvent) => {
            const drag = dragRef.current;
            if (!drag || !trackRef.current) return;
            const rect = trackRef.current.getBoundingClientRect();
            const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
            const rawFrame = Math.round(pct * totalFrames);
            const snapped = snapToNearestPosition(rawFrame);
            const nextFrame = snapped ? snapped.timelineFrame : rawFrame;

            drag.liveFrame = nextFrame;
            setLiveFrame(nextFrame);
        };

        const onMouseUp = () => {
            const drag = dragRef.current;
            dragRef.current = null;
            setDragTitleIndex(null);
            if (drag) commitBoundaryMove(drag.titleIndex, drag.liveFrame);
        };

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
        return () => {
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dragTitleIndex, totalFrames, boundaryPositions]);

    // Resolves the dropped frame to its nearest segmentId and rewrites
    // just that title's segmentId, then does the same full-array PUT
    // saveTitleScenes always does — the server re-derives every title's
    // (and every presenter piece's) timelineStartFrame from scratch via
    // merge_title_scenes, so this single field change is enough to move
    // the actual footage split point, not just a display position.
    // title_scenes.json entries have no id shared with the merged
    // scene-plan TitleScene (same known limitation as #32/#33's title
    // removal) — matched by text, the only identity the two share.
    const commitBoundaryMove = async (titleIndex: number, droppedFrame: number) => {
        const snapped = snapToNearestPosition(droppedFrame);
        if (!snapped) return;

        const title = titles[titleIndex];

        try {
            const current = await getTitleScenes(episodePath);
            const index = current.findIndex((t) => t.text === title.text);
            if (index === -1) return;
            if (current[index].segmentId === snapped.segmentId) return; // no-op — dropped back where it started

            const next = current.map((t, i) => (i === index ? { ...t, segmentId: snapped.segmentId } : t));
            await saveTitleScenes(episodePath, next);
            onSaved?.();
        } catch (e) {
            setDragError(String(e));
        }
    };

    if (totalFrames <= 0) return null;

    const chapters = chaptersFromTitles(titles, totalFrames);

    const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
        // A click that reaches here (not a chapter segment — those
        // stopPropagation) is on empty track space, so it deselects rather
        // than leaving a stale selection highlighted.
        setSelectedTitle(null);
        setPendingDeleteText(null);
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
        onSeek(Math.round(pct * totalFrames));
    };

    const playheadPct = clamp((currentFrame / totalFrames) * 100, 0, 100);

    return (
        <div style={styles.wrap}>
            <div style={styles.label}>
                {chapters.filter((c) => c.title !== null).length} chapter
                {chapters.filter((c) => c.title !== null).length === 1 ? "" : "s"} —{" "}
                {formatFrames(totalFrames, fps)} total
            </div>

            <div ref={trackRef} style={styles.track} onMouseDown={onTrackClick}>
                {chapters.map((chapter, i) => {
                    // Each titled chapter's boundary IS that title's own
                    // position — find its index into `titles` (sorted the
                    // same way chaptersFromTitles sorts) so its drag handle
                    // knows which title to move. The leading null-title
                    // intro chapter (if present) has no boundary of its
                    // own to drag.
                    const titleIndex = chapter.title === null ? -1 : titles.findIndex((t) => t.text === chapter.title);
                    const isDraggingThis = dragTitleIndex === titleIndex && titleIndex !== -1;

                    // While dragging this chapter's leading boundary, its
                    // start (and the previous chapter's end) follow the
                    // live snapped frame instead of the saved position —
                    // purely a render-time override, no state write yet.
                    const startFrame = isDraggingThis ? liveFrame : chapter.startFrame;
                    const effectiveEndFrame =
                        dragTitleIndex !== null && chapters[i + 1] && titles.findIndex((t) => t.text === chapters[i + 1].title) === dragTitleIndex
                            ? liveFrame
                            : chapter.endFrame;

                    const widthPct = ((effectiveEndFrame - startFrame) / totalFrames) * 100;
                    const leftPct = (startFrame / totalFrames) * 100;
                    const color = chapter.title === null ? colors.borderStrong : CHAPTER_COLORS[i % CHAPTER_COLORS.length];

                    const selectable = chapter.title !== null && !!onSelectTitle;
                    const isSelected = selectable && selectedTitle === chapter.title;
                    const draggable = titleIndex !== -1;

                    return (
                        <div
                            key={i}
                            style={{
                                ...styles.chapter,
                                position: "absolute",
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                background: color,
                                cursor: selectable ? "pointer" : "inherit",
                                ...(isSelected ? styles.chapterSelected : {}),
                            }}
                            title={
                                isSelected
                                    ? `${chapter.title} — press ${MOD_KEY_LABEL}+E to edit`
                                    : selectable
                                    ? `Click to select, then ${MOD_KEY_LABEL}+E to edit: ${chapter.title}`
                                    : chapter.title ?? "Intro (before first title card)"
                            }
                            onClick={
                                selectable
                                    ? (e) => {
                                          e.stopPropagation();
                                          selectedAnchorRef.current = { x: e.clientX, y: e.clientY };
                                          setSelectedTitle(chapter.title!);
                                          setPendingDeleteText(null);
                                          onSeek(chapter.startFrame);
                                      }
                                    : undefined
                            }
                        >
                            {draggable && (
                                <div
                                    style={styles.boundaryHandle}
                                    onMouseDown={(e) => startDrag(e, titleIndex)}
                                    title="Drag to move this chapter's boundary (snaps to the nearest transcript segment)"
                                />
                            )}
                            {widthPct > 4 && (
                                <span style={styles.chapterLabel}>
                                    {chapter.title ?? "Intro"}
                                </span>
                            )}
                            {isDraggingThis && (
                                <div style={styles.readout}>{formatFrames(liveFrame, fps)}</div>
                            )}
                        </div>
                    );
                })}

                <div style={{ ...styles.playhead, left: `${playheadPct}%` }} />
            </div>

            {dragError && <div style={styles.error}>{dragError}</div>}
            {deleteError && <div style={styles.error}>{deleteError}</div>}

            {pendingDeleteText && (
                <div style={styles.deleteConfirm}>
                    <span>Delete this chapter's title card?</span>
                    <button type="button" className="secondary small" onClick={doDelete} style={styles.deleteButton}>
                        Delete
                    </button>
                    <button type="button" className="secondary small" onClick={() => setPendingDeleteText(null)}>
                        Cancel
                    </button>
                </div>
            )}

            <div style={styles.hint}>
                {selectedTitle
                    ? `Selected — press ${MOD_KEY_LABEL}+E to edit its title, Delete to remove it.`
                    : `Click anywhere to jump the player there${
                          onSelectTitle ? `, or click a chapter to select it, then ${MOD_KEY_LABEL}+E to edit` : ""
                      }. Drag a chapter's left edge to move its boundary.`}
            </div>
        </div>
    );
}

function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
}

function formatFrames(frames: number, fps: number) {
    const totalSeconds = Math.round(frames / fps);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
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
        height: 44,
        borderRadius: radius.md,
        border: `1px solid ${colors.border}`,
        userSelect: "none",
        cursor: "pointer",
    },
    chapter: {
        top: 0,
        height: "100%",
        display: "flex",
        alignItems: "center",
        borderRight: "1px solid rgba(0,0,0,0.35)",
        overflow: "hidden",
    },
    // Mirrors BeatBar's segmentSelected — a visibly thicker, brighter
    // outline so "this chapter is selected, press Cmd+E to edit" reads as
    // a distinct state from the normal resting/hover appearance.
    chapterSelected: {
        boxShadow: "inset 0 0 0 2px #ffffff, 0 0 8px rgba(255,255,255,0.5)",
        zIndex: 1,
    },
    chapterLabel: {
        padding: "0 8px",
        fontSize: typography.size.xs,
        fontWeight: typography.weight.semibold,
        color: "#fff",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        textShadow: "0 1px 2px rgba(0,0,0,0.5)",
    },
    boundaryHandle: {
        position: "absolute",
        left: -4,
        top: 0,
        bottom: 0,
        width: 8,
        cursor: "ew-resize",
        zIndex: 2,
    },
    readout: {
        position: "absolute",
        bottom: "100%",
        left: 0,
        marginBottom: 4,
        padding: "2px 6px",
        background: colors.background,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.sm,
        fontSize: typography.size.xs,
        color: colors.textPrimary,
        whiteSpace: "nowrap",
        zIndex: 3,
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
    playhead: {
        position: "absolute",
        top: 0,
        bottom: 0,
        width: 2,
        background: colors.playhead,
        pointerEvents: "none",
        boxShadow: "0 0 4px rgba(255,90,60,0.8)",
    },
    hint: {
        fontSize: typography.size.sm,
        color: colors.textMuted,
    },
};
