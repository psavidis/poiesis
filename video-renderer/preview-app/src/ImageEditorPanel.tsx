import { useEffect, useState } from "react";
import type { ImageScene, ScenePlan } from "video-renderer-src/episode/types";
import { deleteScene, getAssets, updateSceneFields } from "./api";
import { colors, radius, typography } from "./tokens";

interface Asset {
    id: string;
    caption: string;
}

// The structured editor for an image scene's presentation (see docs/specs/
// content-types-and-presentation-editing.md, sections 3/8/9: Full Screen
// is a first-class presentation, and the user must be able to change how
// content is presented without replacing it). Reached from ImageBar's
// Cmd+E (#46) — image scenes have no single text field, so unlike
// text-eligible moments there's no lighter InlineTextEditor path, only
// this panel. Unlike MomentEditorPanel, there's no separate moments.json-
// style source file to fetch/rewrite: image scenes live only in
// scene-plan.json, so this reads straight from the scenePlan prop and
// saves via the direct scene-field-update endpoint (api.ts's
// updateSceneFields).
interface Props {
    episodePath: string;
    sceneId: string;
    scenePlan: ScenePlan;
    onSaved: () => void;
    onClose: () => void;
}

export function ImageEditorPanel({ episodePath, sceneId, scenePlan, onSaved, onClose }: Props) {
    const [assetOptions, setAssetOptions] = useState<Asset[]>([]);
    const [status, setStatus] = useState("");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        getAssets(episodePath).then(setAssetOptions).catch(() => setAssetOptions([]));
    }, [episodePath]);

    const image = scenePlan.scenes.find((s): s is ImageScene => s.type === "image" && s.id === sceneId);

    if (!image) {
        return (
            <div style={styles.wrap}>
                <div style={styles.header}>
                    <span>Image</span>
                    <button className="secondary small" onClick={onClose}>
                        Close
                    </button>
                </div>
                <p style={styles.hint}>Couldn't find this image scene — it may have been removed elsewhere.</p>
            </div>
        );
    }

    const save = async (fields: Record<string, unknown>) => {
        setStatus("Saving…");
        setError(null);
        try {
            await updateSceneFields(episodePath, sceneId, fields);
            setStatus("Saved — the next render will pick this up.");
            onSaved();
        } catch (e) {
            setError(String(e));
            setStatus("");
        }
    };

    const remove = async () => {
        setStatus("Removing…");
        setError(null);
        try {
            await deleteScene(episodePath, sceneId);
            onSaved();
            onClose();
        } catch (e) {
            setError(String(e));
            setStatus("");
        }
    };

    return (
        <div style={styles.wrap}>
            <div style={styles.header}>
                <span>IMAGE — {image.display.toUpperCase()}</span>
                <button className="secondary small" onClick={onClose}>
                    Close
                </button>
            </div>

            <label style={styles.fieldLabel}>
                Asset
                <select
                    value={image.assetId}
                    onChange={(e) => save({ assetId: e.target.value })}
                    style={styles.input}
                >
                    {assetOptions.map((a) => (
                        <option key={a.id} value={a.id}>
                            {a.id} — {a.caption || ""}
                        </option>
                    ))}
                </select>
            </label>

            <label style={styles.fieldLabel}>
                Presentation
                <select
                    value={image.display}
                    onChange={(e) => save({ display: e.target.value })}
                    style={styles.input}
                >
                    <option value="inset">Inset (picture-in-picture)</option>
                    <option value="full">Full Screen</option>
                </select>
            </label>

            <label style={styles.fieldLabel}>
                Caption
                <input
                    type="text"
                    defaultValue={image.caption ?? ""}
                    onBlur={(e) => {
                        if (e.target.value !== (image.caption ?? "")) save({ caption: e.target.value });
                    }}
                    style={styles.input}
                />
            </label>

            <div style={styles.actions}>
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
    fieldLabel: {
        display: "flex",
        flexDirection: "column",
        gap: 4,
        fontSize: typography.size.sm,
        color: colors.textSecondary,
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
