import { useEffect, useState } from "react";
import { getStoryboard, saveStoryboard, type StoryboardChapter } from "./api";
import { colors, radius, spacing, typography } from "./tokens";

// Same rotating per-index palette ChapterStrip uses for its own chapter
// segments — reusing it here (rather than inventing a second palette)
// keeps a chapter's identity color consistent between the full-episode
// strip and this one-at-a-time card view.
const CHAPTER_COLORS = colors.chapterPalette;

// Chapter-level visual-story reasoning — not scene-anchored (chapters are
// keyed by chapterId, not a scene in the timeline). Ports ui/static/
// app.js's renderStoryboard/wireStoryboardEditor. Mounted unconditionally
// by EpisodeWorkspace's tab strip (#70) so its own data fetch can decide
// whether the "Storyboard" tab button should even appear — only its BODY
// is gated on isActive, matching every other panel in that strip.
interface Props {
    episodePath: string;
    isActive: boolean;
    // Reports "there's something to show" up to the tab strip, which
    // hides the tab entirely when false (empty state was previously this
    // component's own `return null` — the outer strip needs to know that
    // before the user ever clicks the tab, not after).
    onHasContentChange: (hasContent: boolean) => void;
}

export function StoryboardPanel({ episodePath, isActive, onHasContentChange }: Props) {
    const [chapters, setChapters] = useState<StoryboardChapter[] | null>(null);
    const [index, setIndex] = useState(0);
    // "forward" slides the incoming card in from the right, "back" from the
    // left — set right before an index change, read once by the card's own
    // mount animation (see the `key={index}` remount below).
    const [direction, setDirection] = useState<"forward" | "back">("forward");
    const [status, setStatus] = useState("");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        getStoryboard(episodePath)
            .then((c) => {
                setChapters(c);
                setIndex(0);
            })
            .catch(() => setChapters([])); // storyboard.json not produced yet — normal before that stage runs
    }, [episodePath]);

    useEffect(() => {
        onHasContentChange(!!chapters && chapters.length > 0);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [chapters]);

    // Left/Right arrow keys page between cards — only while this panel is
    // the active tab, and not while the user is typing in the notes
    // textarea (where arrow keys need to move the caret, not the card).
    useEffect(() => {
        if (!isActive || !chapters || chapters.length <= 1) return;

        const onKeyDown = (e: KeyboardEvent) => {
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT")) return;
            if (e.key === "ArrowLeft") goTo(index - 1);
            else if (e.key === "ArrowRight") goTo(index + 1);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isActive, chapters, index]);

    if (!isActive || !chapters || chapters.length === 0) return null;

    const goTo = (next: number) => {
        const clamped = Math.max(0, Math.min(chapters.length - 1, next));
        if (clamped === index) return;
        setDirection(clamped > index ? "forward" : "back");
        setIndex(clamped);
    };

    const updateNotes = (notes: string) => {
        setChapters((prev) => (prev ? prev.map((c, i) => (i === index ? { ...c, notes } : c)) : prev));
    };

    const handleSave = async () => {
        if (!chapters) return;
        setStatus("Saving…");
        setError(null);
        try {
            await saveStoryboard(episodePath, chapters);
            setStatus('Saved — re-run "Propose moment scenes" to use the edited reasoning.');
        } catch (e) {
            setError(String(e));
        }
    };

    const chapter = chapters[index];
    const color = CHAPTER_COLORS[index % CHAPTER_COLORS.length];

    return (
        <div style={styles.body}>
            <p style={styles.hint}>
                Claude's chapter-by-chapter visual-story reasoning — this is what "Propose moment
                scenes" reads before deciding individual treatments. Edit a chapter's notes and
                save; this doesn't change scene-plan.json or produce scenes on its own.
            </p>

            <div style={styles.carousel}>
                <button
                    type="button"
                    className="secondary"
                    style={styles.navButton}
                    onClick={() => goTo(index - 1)}
                    disabled={index === 0}
                    aria-label="Previous chapter"
                >
                    ‹
                </button>

                <div
                    key={chapter.chapterId}
                    className={direction === "forward" ? "storyboard-card-forward" : "storyboard-card-back"}
                    style={{ ...styles.card, borderTopColor: color }}
                >
                    <div style={styles.cardHeader}>
                        <span style={{ ...styles.chapterDot, background: color }} />
                        <span style={styles.chapterLabel}>{chapter.chapterText || chapter.chapterId}</span>
                        <span style={styles.counter}>
                            {index + 1} / {chapters.length}
                        </span>
                    </div>
                    <textarea
                        value={chapter.notes}
                        onChange={(e) => updateNotes(e.target.value)}
                        rows={6}
                        style={styles.textarea}
                        placeholder="Visual-story notes for this chapter…"
                    />
                </div>

                <button
                    type="button"
                    className="secondary"
                    style={styles.navButton}
                    onClick={() => goTo(index + 1)}
                    disabled={index === chapters.length - 1}
                    aria-label="Next chapter"
                >
                    ›
                </button>
            </div>

            <div style={styles.dots}>
                {chapters.map((c, i) => (
                    <button
                        key={c.chapterId}
                        type="button"
                        onClick={() => goTo(i)}
                        title={c.chapterText || c.chapterId}
                        style={{
                            ...styles.dot,
                            background: i === index ? CHAPTER_COLORS[i % CHAPTER_COLORS.length] : colors.border,
                        }}
                    />
                ))}
            </div>

            <div style={styles.actions}>
                <button onClick={handleSave}>Save changes</button>
                <span style={styles.status}>{status}</span>
                {error && <span style={styles.error}>{error}</span>}
            </div>
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    body: {
        display: "flex",
        flexDirection: "column",
        gap: 8,
    },
    hint: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        margin: 0,
    },
    carousel: {
        display: "flex",
        alignItems: "stretch",
        gap: spacing.sm,
    },
    navButton: {
        flexShrink: 0,
        width: 36,
        fontSize: typography.size.lg + 4,
        lineHeight: 1,
        color: colors.textPrimary,
    },
    card: {
        flex: 1,
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        gap: spacing.sm,
        padding: spacing.lg,
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderTop: "3px solid transparent",
        borderRadius: radius.lg,
    },
    cardHeader: {
        display: "flex",
        alignItems: "center",
        gap: spacing.sm,
    },
    chapterDot: {
        width: 8,
        height: 8,
        borderRadius: "50%",
        flexShrink: 0,
    },
    chapterLabel: {
        flex: 1,
        minWidth: 0,
        fontSize: typography.size.lg,
        fontWeight: typography.weight.bold,
        color: colors.textPrimary,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
    },
    counter: {
        flexShrink: 0,
        fontSize: typography.size.sm,
        color: colors.textMuted,
        fontVariantNumeric: "tabular-nums",
    },
    textarea: {
        padding: "10px 12px",
        background: colors.background,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        color: colors.textPrimary,
        fontSize: typography.size.reading,
        lineHeight: typography.lineHeight.relaxed,
        fontFamily: "inherit",
        resize: "vertical",
    },
    dots: {
        display: "flex",
        justifyContent: "center",
        gap: spacing.xs,
        padding: "4px 0",
    },
    dot: {
        width: 8,
        height: 8,
        padding: 0,
        borderRadius: "50%",
        border: "none",
        cursor: "pointer",
    },
    actions: {
        display: "flex",
        alignItems: "center",
        gap: 10,
    },
    status: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
    },
    error: {
        fontSize: typography.size.sm,
        color: colors.error,
    },
};
