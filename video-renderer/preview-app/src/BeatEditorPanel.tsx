import { useEffect, useState } from "react";
import { getBeats, saveBeats } from "./api";
import { beatIndexFromSceneId } from "./InlineTextEditor";
import { colors, radius, typography } from "./tokens";

// Kept in sync with BeatOverlay.tsx's own ICONS map (video-renderer/src/
// episode/BeatOverlay.tsx) — that's the actual set a rendered icon-accent
// beat can show, so this dropdown must offer exactly those keys and no
// others (an icon value outside this set silently renders no icon at all,
// per BeatOverlay's own `icon ? ICONS[icon] : undefined` lookup).
const ICON_OPTIONS = ["arrow", "check", "warning", "gear"] as const;

// The structured editor for a beat's full emphasis.json entry — kind
// (word-pop/underline/icon-accent), icon (icon-accent only), and text.
// Reached from BeatBar's Cmd+E instead of the plain-text InlineTextEditor
// (see EpisodeWorkspace's openInlineBeatEditor) once this panel exists,
// mirroring how MomentEditorPanel is the structured sibling to a moment's
// own InlineTextEditor path — a beat previously had no equivalent, only
// ever reachable as a bare text field. Same fetch-whole-array/patch-by-
// index/save-whole-array contract as MomentEditorPanel (beats live in
// emphasis.json, not scene-plan.json directly), including the same
// "Reset to Automatic" per-field affordance driven by overriddenFields.
interface Props {
    episodePath: string;
    sceneId: string;
    // Bumped by EpisodeWorkspace whenever an edit-plan chat instruction is
    // applied, so this panel re-fetches instead of saving stale data back
    // over a chat-applied removal — mirrors MomentEditorPanel's refreshKey.
    refreshKey: number;
    onSaved: () => void;
    onClose: () => void;
}

export function BeatEditorPanel({ episodePath, sceneId, refreshKey, onSaved, onClose }: Props) {
    const [beats, setBeats] = useState<any[] | null>(null);
    const [status, setStatus] = useState("");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        getBeats(episodePath)
            .then((data) => setBeats(data.beats ?? []))
            .catch(() => setBeats([]));
    }, [episodePath, refreshKey]);

    if (!beats) return null;

    const index = beatIndexFromSceneId(sceneId);

    if (index === null || !beats[index]) {
        return (
            <div style={styles.wrap}>
                <div style={styles.header}>
                    <span>Beat</span>
                    <button className="secondary small" onClick={onClose}>
                        Close
                    </button>
                </div>
                <p style={styles.hint}>Couldn't find a matching entry in emphasis.json for this scene.</p>
            </div>
        );
    }

    const beat = beats[index];

    const update = (patch: Record<string, unknown>) => {
        setBeats((prev) => (prev ? prev.map((b, i) => (i === index ? { ...b, ...patch } : b)) : prev));
    };

    // Reset to Automatic (#57's pattern, mirrored from MomentEditorPanel):
    // clears the field from overriddenFields so it's eligible for the AI
    // to change again on the next --force regeneration. Doesn't recompute
    // a value now — the current value stays exactly what's shown.
    const resetField = (field: string) => {
        const overriddenFields = (beat.overriddenFields || []).filter((f: string) => f !== field);
        update({ overriddenFields });
    };

    const isOverridden = (field: string) => (beat.overriddenFields || []).includes(field);

    const resetButton = (field: string) =>
        isOverridden(field) ? (
            <button
                type="button"
                className="secondary small"
                onClick={() => resetField(field)}
                title="This field was manually edited — reset to let the AI decide it again next time"
                style={styles.resetButton}
            >
                Reset to Automatic
            </button>
        ) : null;

    const remove = async () => {
        const next = beats.filter((_, i) => i !== index);
        setStatus("Saving…");
        setError(null);
        try {
            await saveBeats(episodePath, next);
            setStatus("Removed.");
            onSaved();
            onClose();
        } catch (e) {
            setError(String(e));
        }
    };

    const handleSave = async () => {
        setStatus("Saving…");
        setError(null);
        try {
            // The response's own beats (not the request's) carry server-
            // recomputed overriddenFields — using it, rather than leaving
            // local state as whatever was sent, means "Reset to Automatic"
            // appears immediately after a save that just created an
            // override, with no extra fetch (mirrors MomentEditorPanel's
            // handleSave).
            const result = await saveBeats(episodePath, beats);
            setBeats(result.beats ?? beats);
            setStatus("Saved — the next render will pick this up.");
            onSaved();
        } catch (e) {
            setError(String(e));
        }
    };

    return (
        <div style={styles.wrap}>
            <div style={styles.header}>
                <span>{beat.kind.toUpperCase().replace("-", " ")}</span>
                <button className="secondary small" onClick={onClose}>
                    Close
                </button>
            </div>

            <div style={styles.fieldRow}>
                <label style={styles.presentationLabel}>Style</label>
                <select
                    value={beat.kind}
                    onChange={(e) => update({ kind: e.target.value })}
                    style={{ ...styles.input, flex: 1 }}
                >
                    <option value="word-pop">Word pop</option>
                    <option value="underline">Underline</option>
                    <option value="icon-accent">Icon accent</option>
                </select>
                {resetButton("kind")}
            </div>

            <div style={styles.fieldRow}>
                <label style={styles.presentationLabel}>Text</label>
                <input
                    type="text"
                    value={beat.text}
                    onChange={(e) => update({ text: e.target.value })}
                    style={{ ...styles.input, flex: 1 }}
                />
                {resetButton("text")}
            </div>

            {beat.kind === "icon-accent" && (
                <div style={styles.fieldRow}>
                    <label style={styles.presentationLabel}>Icon</label>
                    <select
                        value={beat.icon || ""}
                        onChange={(e) => update({ icon: e.target.value || null })}
                        style={{ ...styles.input, flex: 1 }}
                    >
                        <option value="">None</option>
                        {ICON_OPTIONS.map((icon) => (
                            <option key={icon} value={icon}>
                                {icon}
                            </option>
                        ))}
                    </select>
                    {resetButton("icon")}
                </div>
            )}

            {beat.reason && <p style={styles.reason}>{beat.reason}</p>}

            <div style={styles.actions}>
                <button onClick={handleSave}>Save changes</button>
                <button className="secondary" onClick={remove}>
                    Remove
                </button>
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
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.lg,
    },
    header: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: typography.size.sm,
        fontWeight: typography.weight.bold,
        textTransform: "uppercase",
        letterSpacing: 0.5,
        color: colors.textSecondary,
    },
    hint: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        margin: 0,
    },
    fieldRow: {
        display: "flex",
        alignItems: "center",
        gap: 8,
    },
    presentationLabel: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        width: 80,
        flexShrink: 0,
    },
    input: {
        padding: "8px 12px",
        background: colors.background,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        color: colors.textPrimary,
        fontSize: typography.size.base,
    },
    resetButton: {
        flexShrink: 0,
    },
    reason: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        fontStyle: "italic",
        margin: 0,
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
