import { useEffect, useState } from "react";
import type { ImageScene, ScenePlan } from "video-renderer-src/episode/types";
import { getAssets, updateSceneFields } from "./api";

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

    const remove = () => {
        // Removal (unlike a field update) needs the LLM-free deterministic
        // "remove" op, not a "fields" update — reuses the same endpoint's
        // op contract, matching ui/server.py's PUT /api/episode/scene body
        // shape (sceneId + fields is the only shape that endpoint accepts
        // for this panel's scope; broader remove support is #42/#46
        // follow-up work, not needed for the display/asset/caption editing
        // this panel targets today).
        setError("Removing an image scene isn't supported here yet — use the edit-plan chat (e.g. \"remove this image\").");
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
    fieldLabel: {
        display: "flex",
        flexDirection: "column",
        gap: 4,
        fontSize: 12,
        color: "#9aa7b4",
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
