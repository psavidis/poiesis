import { useEffect, useState } from "react";
import { getStoryboard, saveStoryboard, type StoryboardChapter } from "./api";
import { colors, radius, typography } from "./tokens";

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
    const [status, setStatus] = useState("");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        getStoryboard(episodePath)
            .then(setChapters)
            .catch(() => setChapters([])); // storyboard.json not produced yet — normal before that stage runs
    }, [episodePath]);

    useEffect(() => {
        onHasContentChange(!!chapters && chapters.length > 0);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [chapters]);

    if (!isActive || !chapters || chapters.length === 0) return null;

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
