import { useEffect, useState } from "react";
import { getStoryboard, saveStoryboard, type StoryboardChapter } from "./api";
import { colors, radius, typography } from "./tokens";

// Chapter-level visual-story reasoning — not scene-anchored (chapters are
// keyed by chapterId, not a scene in the timeline), so unlike titles/
// moments this is an always-visible panel rather than click-to-open.
// Ports ui/static/app.js's renderStoryboard/wireStoryboardEditor.
interface Props {
    episodePath: string;
}

export function StoryboardPanel({ episodePath }: Props) {
    const [chapters, setChapters] = useState<StoryboardChapter[] | null>(null);
    const [expanded, setExpanded] = useState(false);
    const [status, setStatus] = useState("");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        getStoryboard(episodePath)
            .then(setChapters)
            .catch(() => setChapters([])); // storyboard.json not produced yet — normal before that stage runs
    }, [episodePath]);

    if (!chapters || chapters.length === 0) return null;

    const updateNotes = (index: number, notes: string) => {
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

    return (
        <div style={styles.wrap}>
            <button className="secondary" onClick={() => setExpanded((v) => !v)} style={styles.toggle}>
                {expanded ? "Storyboard ▾" : "Storyboard ▸"}
            </button>

            {expanded && (
                <div style={styles.body}>
                    <p style={styles.hint}>
                        Claude's chapter-by-chapter visual-story reasoning — this is what "Propose moment
                        scenes" reads before deciding individual treatments. Edit a chapter's notes and
                        save; this doesn't change scene-plan.json or produce scenes on its own.
                    </p>

                    {chapters.map((c, i) => (
                        <div key={c.chapterId} style={styles.row}>
                            <span style={styles.chapterLabel}>{c.chapterText || c.chapterId}</span>
                            <textarea
                                value={c.notes}
                                onChange={(e) => updateNotes(i, e.target.value)}
                                rows={2}
                                style={styles.textarea}
                            />
                        </div>
                    ))}

                    <div style={styles.actions}>
                        <button onClick={handleSave}>Save changes</button>
                        <span style={styles.status}>{status}</span>
                        {error && <span style={styles.error}>{error}</span>}
                    </div>
                </div>
            )}
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 8,
    },
    toggle: {
        alignSelf: "flex-start",
        fontSize: 13,
    },
    body: {
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: "12px 14px",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.lg,
    },
    hint: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        margin: 0,
    },
    row: {
        display: "flex",
        flexDirection: "column",
        gap: 4,
    },
    chapterLabel: {
        fontSize: typography.size.sm,
        fontWeight: typography.weight.bold,
        color: colors.textPrimary,
    },
    textarea: {
        padding: "6px 10px",
        background: colors.background,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        color: colors.textPrimary,
        fontSize: typography.size.md,
        fontFamily: "inherit",
        resize: "vertical",
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
