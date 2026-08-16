import type { ScenePlan, TitleScene } from "video-renderer-src/episode/types";

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
const CHAPTER_COLORS = ["#3a7bd5", "#c96f2a", "#3aa66d", "#8b5cf6", "#d5473a", "#2aa1a1"];

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
}

// A full-episode strip dividing the video into chapters at each title
// card, so the shape of the whole episode is visible at a glance — how
// long each topic runs, how many chapters there are, and where the
// current playhead sits relative to all of them. Clicking always seeks;
// clicking a chapter (not the pre-title "Intro" segment) also opens that
// chapter's underlying title text editor via onSelectTitle (see #34) —
// chapters ARE title scenes, so this is the same click-to-edit path
// ActiveSceneBar's title chips already use. Only rendered in the
// full-episode preview, not the scene-scoped "Adjust timing" view, which
// already has its own OverlayStrip.
export function ChapterStrip({ scenePlan, totalFrames, currentFrame, fps, onSeek, onSelectTitle }: Props) {
    const titles = scenePlan.scenes.filter((s): s is TitleScene => s.type === "title");

    if (totalFrames <= 0) return null;

    const chapters = chaptersFromTitles(titles, totalFrames);

    const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
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

            <div style={styles.track} onMouseDown={onTrackClick}>
                {chapters.map((chapter, i) => {
                    const widthPct = ((chapter.endFrame - chapter.startFrame) / totalFrames) * 100;
                    const color = chapter.title === null ? "#3a4552" : CHAPTER_COLORS[i % CHAPTER_COLORS.length];

                    const clickable = chapter.title !== null && !!onSelectTitle;

                    return (
                        <div
                            key={i}
                            style={{
                                ...styles.chapter,
                                width: `${widthPct}%`,
                                background: color,
                                cursor: clickable ? "pointer" : "inherit",
                            }}
                            title={
                                clickable
                                    ? `Click to seek here, or edit title: ${chapter.title}`
                                    : chapter.title ?? "Intro (before first title card)"
                            }
                            onClick={
                                clickable
                                    ? (e) => onSelectTitle!(chapter.title!, { x: e.clientX, y: e.clientY })
                                    : undefined
                            }
                        >
                            {widthPct > 4 && (
                                <span style={styles.chapterLabel}>
                                    {chapter.title ?? "Intro"}
                                </span>
                            )}
                        </div>
                    );
                })}

                <div style={{ ...styles.playhead, left: `${playheadPct}%` }} />
            </div>

            <div style={styles.hint}>
                Click anywhere to jump the player there
                {onSelectTitle ? " — clicking a chapter also opens its title editor" : ""}.
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
        fontSize: 12,
        color: "#9aa7b4",
    },
    track: {
        position: "relative",
        height: 44,
        display: "flex",
        borderRadius: 6,
        overflow: "hidden",
        border: "1px solid #2a333d",
        userSelect: "none",
        cursor: "pointer",
    },
    chapter: {
        position: "relative",
        height: "100%",
        display: "flex",
        alignItems: "center",
        borderRight: "1px solid rgba(0,0,0,0.35)",
        overflow: "hidden",
    },
    chapterLabel: {
        padding: "0 8px",
        fontSize: 11,
        fontWeight: 600,
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
        background: "#ff5a3c",
        pointerEvents: "none",
        boxShadow: "0 0 4px rgba(255,90,60,0.8)",
    },
    hint: {
        fontSize: 12,
        color: "#6b7683",
    },
};
