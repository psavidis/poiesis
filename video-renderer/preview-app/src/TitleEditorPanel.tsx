import { useEffect, useState } from "react";
import { getTitleScenes, saveTitleScenes, type TitleSceneProposal } from "./api";

// Scoped to editing ONE title, opened by clicking its chip in
// ActiveSceneBar. title_scenes.json entries have no id shared with the
// merged scene-plan.json TitleScene (only segmentId vs. scene id — see
// #32), so the clicked title is correlated to its title_scenes.json entry
// by exact text match. Fine in practice since title text is expected to
// be unique per episode; if that assumption breaks, matching gets
// ambiguous — a known, accepted limitation of this correlation approach.
interface Props {
    episodePath: string;
    titleText: string;
    // Bumped by EpisodeWorkspace whenever an edit-plan chat instruction is
    // applied, so this panel re-fetches instead of saving stale data back
    // over a chat-applied removal — see EpisodeWorkspace's refreshKey.
    refreshKey: number;
    onClose: () => void;
}

export function TitleEditorPanel({ episodePath, titleText, refreshKey, onClose }: Props) {
    const [titles, setTitles] = useState<TitleSceneProposal[] | null>(null);
    const [status, setStatus] = useState("");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        getTitleScenes(episodePath).then(setTitles).catch(() => setTitles([]));
    }, [episodePath, refreshKey]);

    if (!titles) return null;

    const index = titles.findIndex((t) => t.text === titleText);

    if (index === -1) {
        return (
            <div style={styles.wrap}>
                <div style={styles.header}>
                    <span>Title</span>
                    <button className="secondary small" onClick={onClose}>
                        Close
                    </button>
                </div>
                <p style={styles.hint}>
                    Couldn't find a matching entry in title_scenes.json for this title's current text — it
                    may have already been edited or removed elsewhere.
                </p>
            </div>
        );
    }

    const title = titles[index];

    const updateText = (text: string) => {
        setTitles((prev) => (prev ? prev.map((t, i) => (i === index ? { ...t, text } : t)) : prev));
    };

    // Reset to Automatic (#59, mirrors #57/#58): clears "text" from
    // overriddenFields so it's eligible for the AI to change again on the
    // next --force regeneration. No value change here — same as moments'
    // own reset affordance, the user must still click "Save changes" for
    // this to take effect server-side.
    const isTextOverridden = (title.overriddenFields || []).includes("text");
    const resetText = () => {
        setTitles((prev) =>
            prev
                ? prev.map((t, i) =>
                      i === index ? { ...t, overriddenFields: (t.overriddenFields || []).filter((f) => f !== "text") } : t
                  )
                : prev
        );
    };

    const remove = async () => {
        const next = titles.filter((_, i) => i !== index);
        setStatus("Saving…");
        setError(null);
        try {
            await saveTitleScenes(episodePath, next);
            setStatus("Removed.");
            onClose();
        } catch (e) {
            setError(String(e));
        }
    };

    const handleSave = async () => {
        setStatus("Saving…");
        setError(null);
        try {
            await saveTitleScenes(episodePath, titles);
            setStatus("Saved — the next render will pick this up.");
        } catch (e) {
            setError(String(e));
        }
    };

    return (
        <div style={styles.wrap}>
            <div style={styles.header}>
                <span>Title</span>
                <button className="secondary small" onClick={onClose}>
                    Close
                </button>
            </div>

            <input
                type="text"
                value={title.text}
                onChange={(e) => updateText(e.target.value)}
                style={styles.input}
            />

            <div style={styles.actions}>
                <button onClick={handleSave}>Save changes</button>
                <button className="secondary" onClick={remove}>
                    Remove
                </button>
                {isTextOverridden && (
                    <button
                        type="button"
                        className="secondary small"
                        onClick={resetText}
                        title="This text was manually edited — reset to let the AI decide it again next time"
                    >
                        Reset to Automatic
                    </button>
                )}
                <span style={styles.status}>{status}</span>
                {error && <span style={styles.error}>{error}</span>}
            </div>
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: "12px 14px",
        background: "#161d24",
        border: "1px solid #2a333d",
        borderRadius: 8,
    },
    header: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: 12,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: 0.5,
        color: "#9aa7b4",
    },
    hint: {
        fontSize: 12,
        color: "#9aa7b4",
        margin: 0,
    },
    input: {
        padding: "8px 12px",
        background: "#0b0f14",
        border: "1px solid #2a333d",
        borderRadius: 6,
        color: "#e8edf2",
        fontSize: 14,
    },
    actions: {
        display: "flex",
        alignItems: "center",
        gap: 10,
    },
    status: {
        fontSize: 12,
        color: "#9aa7b4",
    },
    error: {
        fontSize: 12,
        color: "#ff8f8f",
    },
};
