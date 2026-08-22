import { useEffect, useRef, useState } from "react";
import type { EpisodeVideo, PresenterScene, ScenePlan, TitleScene } from "video-renderer-src/episode/types";
import { colors, radius, typography } from "./tokens";
import { getChapterBoundaryPositions, getTitleScenes, saveTitleScenes, type ChapterBoundaryPosition } from "./api";

// Display-only label for the edit shortcut's hint text — mirrors BeatBar's
// own MOD_KEY_LABEL constant (kept per-file rather than shared since it's
// a one-line platform sniff, not worth a shared module for).
const MOD_KEY_LABEL = navigator.platform.toLowerCase().includes("mac") ? "Cmd" : "Ctrl";

interface Chapter {
    title: string | null; // null = the lead-in before the first title card — NOT a real
                           // TitleScene, so it must stay unselectable/uneditable (see `selectable` below)
    label: string; // always a display string — `title`, or a lead-in-only fallback, never editable itself
    startFrame: number;
    endFrame: number;
}

// Chapter 0 (the lead-in before any title card) never gets a title card by
// design (generate_title_scenes.py: "the opening segment is always the
// presenter's performed intro, never a topic that needs its own title
// card"), so its display label has to come from somewhere other than
// TitleScene text. Source filenames follow a "chapterNumber[.part][
// description]" convention (e.g. "0. Welcome.mov", "9 outro.mov") — the
// free-text part after the numeric prefix is exactly the human-readable
// label the creator already wrote, so this strips the same leading
// "digits[.digits]" prefix prepare_footage.py's footage_sort_key parses on
// the Python side, leaving whatever description survives. Falls back to
// null (renders as the generic "Intro" placeholder) when there's no
// description to recover, e.g. a bare "0.mov" with no free text at all.
const FILENAME_PREFIX_RE = /^\d+(?:\.\d+)?\.?\s*/;

function leadInLabelFromFilename(filename: string): string | null {
    const withoutExtension = filename.replace(/\.[^./]+$/, "");
    const description = withoutExtension.replace(FILENAME_PREFIX_RE, "").trim();
    return description.length > 0 ? description : null;
}

// Title scenes mark where a new topic starts (see CLAUDE.md: "titles get
// proposed once per clip, only for genuine topic changes") but only carry
// their own on-screen duration, not a "chapter length" — a chapter runs
// from one title's start to the next title's start (or to the end of the
// episode for the last one), which is what this derives.
function chaptersFromTitles(titles: TitleScene[], totalFrames: number, leadInLabel: string | null): Chapter[] {
    const sorted = [...titles].sort((a, b) => a.timelineStartFrame - b.timelineStartFrame);

    const chapters: Chapter[] = [];

    if (sorted.length === 0 || sorted[0].timelineStartFrame > 0) {
        chapters.push({
            title: null,
            label: leadInLabel ?? "Intro",
            startFrame: 0,
            endFrame: sorted[0]?.timelineStartFrame ?? totalFrames,
        });
    }

    sorted.forEach((title, i) => {
        const next = sorted[i + 1];
        chapters.push({
            title: title.text,
            label: title.text,
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
    videos: EpisodeVideo[];
    totalFrames: number;
    currentFrame: number;
    fps: number;
    onSeek: (absoluteFrame: number) => void;
    // Live playhead read (bypasses the currentFrame prop's render-cycle lag
    // — see EpisodeWorkspace's own getCurrentFrame doc comment) for Cmd+I's
    // insert-at-playhead (#86), the same reason BackgroundBar's Cmd+B reads
    // getCurrentFrame() rather than its currentFrame prop: reading the
    // stale prop right after a chapter-select click (which itself just
    // called onSeek) can snap to the WRONG nearest boundary — the one
    // before the click, not the one just seeked to.
    getCurrentFrame: () => number;
    // Opens the inline text editor for a chapter's underlying TitleScene
    // (see #34) — chapters ARE title scenes (chaptersFromTitles derives
    // one chapter per TitleScene, see above). Same anchor-aware signature
    // as SceneBar/MomentBar's onSelect* callbacks. Optional so ChapterStrip
    // still works standalone without every caller needing to pass a no-op.
    onSelectTitle?: (titleText: string, anchor: { x: number; y: number }) => void;
    // Opens the inline text editor to CREATE a brand-new title/chapter at a
    // given segmentId, rather than editing an existing one — used both by
    // clicking the lead-in chapter (#83, which has no existing TitleScene
    // to key onSelectTitle's text-match off of) and by Cmd+I (#86) at the
    // playhead, which inserts a new chapter boundary anywhere in the
    // episode, not only before the first title card.
    onCreateTitleAt?: (segmentId: string, anchor: { x: number; y: number }) => void;
    // Set by EpisodeWorkspace right after a chat edit touches a title
    // scene (#54) — keyed by title text (a chapter's own identity here,
    // since chapters aren't derived with their own scene id), not sceneId.
    highlightedTitleText?: string | null;
    episodePath: string;
    onSaved?: () => void;
    // See BeatBar's identical prop's own doc comment — mutual-exclusion
    // signal so this bar's selection (and its Cmd+E listener) clears
    // itself once a different bar becomes the active selection owner.
    // Optional, like onSelectTitle/onSaved above: a standalone caller with
    // no sibling bars to coordinate with can omit both and this bar's
    // selection just behaves as it always did (never cleared externally).
    activeSelectionBar?: string | null;
    onActivateSelection?: () => void;
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
    videos,
    totalFrames,
    currentFrame,
    fps,
    onSeek,
    getCurrentFrame,
    onSelectTitle,
    onCreateTitleAt,
    highlightedTitleText,
    episodePath,
    onSaved,
    activeSelectionBar,
    onActivateSelection,
}: Props) {
    const titles = scenePlan.scenes
        .filter((s): s is TitleScene => s.type === "title")
        .sort((a, b) => a.timelineStartFrame - b.timelineStartFrame);

    // The lead-in chapter's label comes from its own source clip's
    // filename, not a TitleScene (see leadInLabelFromFilename above) — the
    // earliest-starting presenter scene on the timeline is always that
    // clip, regardless of scene id/array order.
    const leadInVideoId = scenePlan.scenes
        .filter((s): s is PresenterScene => s.type === "presenter")
        .sort((a, b) => a.timelineStartFrame - b.timelineStartFrame)[0]?.videoId;
    const leadInVideo = videos.find((v) => v.id === leadInVideoId);
    const leadInLabel = leadInVideo ? leadInLabelFromFilename(leadInVideo.filename) : null;

    // The clicked-but-not-editing chapter's title text — highlighted, and
    // the target of Cmd+E/Ctrl+E. Click selects only; it never opens the
    // editor by itself (mirrors BeatBar's selectedBeatId).
    const [selectedTitle, setSelectedTitle] = useState<string | null>(null);
    // Separate from selectedTitle since the lead-in chapter (#83) has no
    // title text to key off of — true when it's the selected segment
    // instead of any real title. Mutually exclusive with selectedTitle
    // (selecting one clears the other).
    const [leadInSelected, setLeadInSelected] = useState(false);
    const selectedAnchorRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
    const trackRef = useRef<HTMLDivElement>(null);

    // See BeatBar's identical effect's own doc comment — clears this bar's
    // selection once a different bar takes over the shared selection.
    // undefined activeSelectionBar (standalone use, see the prop's own
    // comment) means this never fires, matching the pre-existing behavior.
    useEffect(() => {
        if (activeSelectionBar === undefined) return;
        if (activeSelectionBar !== "chapter") {
            setSelectedTitle(null);
            setLeadInSelected(false);
        }
    }, [activeSelectionBar]);

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
        onActivateSelection?.();
        setSelectedTitle(highlightedTitleText);
        setLeadInSelected(false);
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

    // Same Cmd+E convention as above, for the lead-in chapter (#83) —
    // needs the earliest resolvable segment position (never the very
    // first segment itself, which merge_title_scenes's split logic would
    // place the title at frame 0 of, correctly turning "no title" into a
    // real one at the start) to seed a brand-new title_scenes.json entry.
    useEffect(() => {
        if (!leadInSelected || !onCreateTitleAt) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "e" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
            if (boundaryPositions.length === 0) return;

            e.preventDefault();
            onCreateTitleAt(boundaryPositions[0].segmentId, selectedAnchorRef.current);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [leadInSelected, onCreateTitleAt, boundaryPositions]);

    // A playhead frame this close to an existing title's own boundary is
    // treated as "already a chapter here" by Cmd+I below — matches the
    // backend's own MIN_PIECE_FRAMES_SECONDS (generate_title_scenes.py),
    // which snaps a split landing this close to a boundary onto it rather
    // than leaving a sliver piece.
    const MIN_CHAPTER_SPACING_FRAMES = fps;

    // Cmd+I (Mac) / Ctrl+I (elsewhere) inserts a brand-new chapter boundary
    // at the playhead (#86) — global like MomentBar/BackgroundBar's own
    // Cmd+I/Cmd+B, doesn't require a chapter to be selected first (inserting
    // is independent of selection). Checked against the RAW playhead frame
    // first — a title's own timelineStartFrame is NOT generally one of
    // boundaryPositions's resolvable transcript-segment positions (the
    // title card's own on-screen duration shifts everything after it, see
    // merge_title_scenes), so snapping to the nearest transcript segment
    // before comparing against existing titles could land tens of frames
    // away from a title that already sits almost exactly at the playhead —
    // confirmed live: the nearest transcript segment to a real title's own
    // start landed 90 frames (3s) away, well outside any reasonable
    // "already a title here" tolerance. Only once past that check does the
    // playhead snap to the nearest resolvable segment position, to seed a
    // real title_scenes.json entry. Reads getCurrentFrame() rather than the
    // currentFrame prop — see the prop's own doc comment: clicking a
    // chapter to select it also seeks there, and currentFrame hasn't caught
    // up to that seek yet on the very next keystroke.
    useEffect(() => {
        if (!onCreateTitleAt) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "i" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
            if (boundaryPositions.length === 0 || !trackRef.current) return;

            const frame = getCurrentFrame();

            const tooCloseToExistingTitle = titles.some(
                (t) => Math.abs(t.timelineStartFrame - frame) < MIN_CHAPTER_SPACING_FRAMES
            );
            if (tooCloseToExistingTitle) return;

            const nearest = boundaryPositions.reduce((closest, p) =>
                Math.abs(p.timelineFrame - frame) < Math.abs(closest.timelineFrame - frame) ? p : closest
            );

            e.preventDefault();
            const rect = trackRef.current.getBoundingClientRect();
            const anchorX = rect.left + (nearest.timelineFrame / totalFrames) * rect.width;
            setSelectedTitle(null);
            setLeadInSelected(false);
            onCreateTitleAt(nearest.segmentId, { x: anchorX, y: rect.bottom });
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [onCreateTitleAt, boundaryPositions, getCurrentFrame, totalFrames, titles]);

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

    const chapters = chaptersFromTitles(titles, totalFrames, leadInLabel);

    const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
        // A click that reaches here (not a chapter segment — those
        // stopPropagation) is on empty track space, so it deselects rather
        // than leaving a stale selection highlighted.
        setSelectedTitle(null);
        setLeadInSelected(false);
        setPendingDeleteText(null);
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
        onSeek(Math.round(pct * totalFrames));
    };

    const playheadPct = clamp((currentFrame / totalFrames) * 100, 0, 100);

    return (
        <div style={styles.wrap}>
            <div style={styles.label}>
                {chapters.length} chapter
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

                    const isLeadIn = chapter.title === null;
                    const selectable = isLeadIn ? !!onCreateTitleAt : !!onSelectTitle;
                    const isSelected = isLeadIn ? leadInSelected : selectedTitle === chapter.title;
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
                                    ? `${chapter.label} — press ${MOD_KEY_LABEL}+E to ${isLeadIn ? "add a title card" : "edit"}`
                                    : selectable
                                    ? `Click to select, then ${MOD_KEY_LABEL}+E to ${isLeadIn ? "add a title card" : `edit: ${chapter.title}`}`
                                    : chapter.label
                            }
                            onClick={
                                selectable
                                    ? (e) => {
                                          e.stopPropagation();
                                          selectedAnchorRef.current = { x: e.clientX, y: e.clientY };
                                          onActivateSelection?.();
                                          if (isLeadIn) {
                                              setLeadInSelected(true);
                                              setSelectedTitle(null);
                                          } else {
                                              setSelectedTitle(chapter.title!);
                                              setLeadInSelected(false);
                                          }
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
                                    {chapter.label}
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
                    : leadInSelected
                    ? `Selected — press ${MOD_KEY_LABEL}+E to give this lead-in a title card.`
                    : `Click anywhere to jump the player there${
                          onSelectTitle ? `, or click a chapter to select it, then ${MOD_KEY_LABEL}+E to edit` : ""
                      }. Drag a chapter's left edge to move its boundary.${
                          onCreateTitleAt ? ` Press ${MOD_KEY_LABEL}+I to insert a new chapter at the playhead.` : ""
                      }`}
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
