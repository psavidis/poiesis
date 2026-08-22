import { useState } from "react";
import type { PresenterScene, ScenePlan } from "video-renderer-src/episode/types";
import { updateSceneFields } from "./api";
import { colors, radius, typography } from "./tokens";

interface Props {
    episodePath: string;
    sceneId: string;
    scenePlan: ScenePlan;
    onSaved: () => void;
    onClose: () => void;
}

// The structured editor for a presenter (clip) scene — reached from
// SceneBar's Cmd+E (#78: previously a clip segment had no click handler at
// all, so there was no way to select one, let alone edit it).
//
// Deliberately does NOT expose sourceStartFrame/sourceEndFrame as free-
// typed numeric fields here, even though edit_plan.py's EDITABLE_FIELDS
// technically allows updating them via the generic "update" op — that op
// path has NO bounds validation on those two fields (see
// validate_operations's own "update" branch: only entrance gets a value
// check; sourceStartFrame/sourceEndFrame just need to be present in the
// allowlist by NAME). The pipeline's own dedicated "trim" op DOES validate
// a cut falls strictly within the scene's existing source range, but
// that's wired only to cut_candidates.json's accept flow (see ui/server.py's
// update_cut_candidates), not a general-purpose editor. Shipping raw
// numeric inputs for these two fields here could silently write an
// out-of-bounds or start>=end source range with no server-side guard,
// corrupting the render with no warning — exactly the kind of unsafe
// half-feature CLAUDE.md's engineering workflow says to avoid rather than
// ship. Trim-range editing belongs in a follow-up once that validation
// gap is closed; this panel sticks to what's genuinely safe today.
//
// "effects.transition" IS exposed — it's a small, bounded concept (see
// Episode.tsx's crossfadeInFramesForScene: only "crossfade" vs. anything
// else/absent, i.e. a hard cut, is ever meaningfully different) with no
// equivalent out-of-bounds risk, and is the most direct match for the
// issue's own "editing the transitions of the selected scene" wording.
export function PresenterEditorPanel({ episodePath, sceneId, scenePlan, onSaved, onClose }: Props) {
    const [status, setStatus] = useState("");
    const [error, setError] = useState<string | null>(null);

    const scene = scenePlan.scenes.find((s): s is PresenterScene => s.type === "presenter" && s.id === sceneId);

    if (!scene) {
        return (
            <div style={styles.wrap}>
                <div style={styles.header}>
                    <span>Clip</span>
                    <button className="secondary small" onClick={onClose}>
                        Close
                    </button>
                </div>
                <p style={styles.hint}>Couldn't find this clip — it may have been removed elsewhere.</p>
            </div>
        );
    }

    const transition = scene.effects?.transition === "crossfade" ? "crossfade" : "cut";

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

    const sourceDurationFrames = scene.sourceEndFrame - scene.sourceStartFrame;

    return (
        <div style={styles.wrap}>
            <div style={styles.header}>
                <span>CLIP — {scene.videoId}</span>
                <button className="secondary small" onClick={onClose}>
                    Close
                </button>
            </div>

            <div style={styles.infoRow}>
                <span style={styles.infoLabel}>Source range</span>
                <span style={styles.infoValue}>
                    frame {scene.sourceStartFrame} – {scene.sourceEndFrame} ({(sourceDurationFrames / 30).toFixed(1)}s)
                </span>
            </div>
            <p style={styles.hint}>
                Trimming a clip's source range isn't editable here yet — use "Propose pause cuts" in Advanced to
                trim dead air at the start/end, which goes through the pipeline's own validated cut path.
            </p>

            <label style={styles.fieldLabel}>
                Transition in from the previous clip
                <select
                    value={transition}
                    onChange={(e) =>
                        save({
                            effects: { ...scene.effects, transition: e.target.value },
                        })
                    }
                    style={styles.input}
                >
                    <option value="cut">Hard cut</option>
                    <option value="crossfade">Crossfade</option>
                </select>
            </label>

            <div style={styles.actions}>
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
        lineHeight: typography.lineHeight.relaxed,
    },
    infoRow: {
        display: "flex",
        flexDirection: "column",
        gap: 2,
        fontSize: typography.size.sm,
    },
    infoLabel: {
        color: colors.textSecondary,
    },
    infoValue: {
        color: colors.textPrimary,
        fontFamily: "monospace",
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
