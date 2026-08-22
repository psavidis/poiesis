import { useEffect, useState } from "react";
import type { EpisodeBackground } from "video-renderer-src/episode/types";
import { getBackgroundScenes, saveBackgroundScenes } from "./api";
import { deleteBackgroundScene } from "./backgroundInsert";
import { IMAGE_MOTION_OPTIONS, IMAGE_MOTION_SPEED_OPTIONS } from "./BackgroundBar";
import { colors, radius, typography } from "./tokens";

// The structured editor for a background's own motion setting (#91
// follow-up) — replaces BackgroundBar's old MotionEditor, a
// position:absolute popup anchored near the click and dismissed on
// outside-click/Escape (confirmed live: losing that popup meant starting
// over, no persistent access to change the choice again). This panel
// instead follows every other structured editor's own pattern (Beat/
// Moment/Image/Presenter) — a fixed panel in EpisodeWorkspace's
// playerWrap column, opened by selecting a background and staying open
// until explicitly closed, so switching direction/speed is just picking
// another option, never a re-open. Same fetch-whole-array/patch-by-key/
// save-whole-array contract as BeatEditorPanel, keyed by segmentId
// (background_scenes.json's own identity) rather than array index —
// index isn't stable here the way it is for beats/moments, since
// deleting an earlier entry shifts every later one's derived
// scene-background-{i} id, but never its own segmentId.
interface Props {
    episodePath: string;
    segmentId: string;
    backgrounds: EpisodeBackground[];
    refreshKey: number;
    onSaved: () => void;
    onClose: () => void;
}

export function BackgroundEditorPanel({ episodePath, segmentId, backgrounds, refreshKey, onSaved, onClose }: Props) {
    const [scenes, setScenes] = useState<any[] | null>(null);
    const [status, setStatus] = useState("");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        getBackgroundScenes(episodePath)
            .then((data) => setScenes(data ?? []))
            .catch(() => setScenes([]));
    }, [episodePath, refreshKey]);

    if (!scenes) return null;

    const index = scenes.findIndex((s) => s.segmentId === segmentId);

    if (index === -1) {
        return (
            <div style={styles.wrap}>
                <div style={styles.header}>
                    <span>Background</span>
                    <button className="secondary small" onClick={onClose}>
                        Close
                    </button>
                </div>
                <p style={styles.hint}>Couldn't find a matching entry in background_scenes.json for this segment.</p>
            </div>
        );
    }

    const entry = scenes[index];
    const background = backgrounds.find((b) => b.id === entry.backgroundId);
    const motion = entry.imageMotion ?? "none";
    const speed = entry.imageMotionSpeed ?? "3";

    const update = (patch: Record<string, unknown>) => {
        setScenes((prev) => (prev ? prev.map((s, i) => (i === index ? { ...s, ...patch } : s)) : prev));
    };

    // Delegates to deleteBackgroundScene (backgroundInsert.ts), shared
    // with BackgroundBar's own Delete/Backspace — a plain filter-and-save
    // here (without that shared gap-closing logic) was exactly how #91's
    // "deleting the first of two backgrounds leaves a gap" bug reproduced
    // through THIS panel's Remove button even after fixing BackgroundBar's
    // own delete path alone.
    const remove = async () => {
        setStatus("Saving…");
        setError(null);
        const result = await deleteBackgroundScene(episodePath, segmentId);
        if (result.ok) {
            setStatus("Removed.");
            onSaved();
            onClose();
        } else {
            setError(result.error);
        }
    };

    const handleSave = async () => {
        setStatus("Saving…");
        setError(null);
        try {
            await saveBackgroundScenes(episodePath, scenes);
            setStatus("Saved — the next render will pick this up.");
            onSaved();
        } catch (e) {
            setError(String(e));
        }
    };

    return (
        <div style={styles.wrap}>
            <div style={styles.header}>
                <span>{background?.caption || background?.filename || "Background"}</span>
                <button className="secondary small" onClick={onClose}>
                    Close
                </button>
            </div>

            <div style={styles.fieldRow}>
                <label style={styles.presentationLabel}>Motion</label>
                <select
                    value={motion}
                    onChange={(e) => {
                        const nextMotion = e.target.value;
                        update(
                            nextMotion === "none"
                                ? { imageMotion: undefined, imageMotionSpeed: undefined }
                                : { imageMotion: nextMotion, imageMotionSpeed: entry.imageMotionSpeed ?? "3" }
                        );
                    }}
                    style={{ ...styles.input, flex: 1 }}
                >
                    <option value="none">No motion</option>
                    {IMAGE_MOTION_OPTIONS.filter((o) => o.value !== "none").map((option) => (
                        <option key={option.value} value={option.value}>
                            {option.label}
                        </option>
                    ))}
                </select>
            </div>

            {motion !== "none" && (
                <div style={styles.fieldRow}>
                    <label style={styles.presentationLabel}>Speed</label>
                    <select
                        value={speed}
                        onChange={(e) => update({ imageMotionSpeed: e.target.value })}
                        style={{ ...styles.input, flex: 1 }}
                    >
                        {IMAGE_MOTION_SPEED_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </div>
            )}

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
