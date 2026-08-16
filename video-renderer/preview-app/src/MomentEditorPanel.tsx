import { useEffect, useState } from "react";
import type { PresenterScene, ScenePlan } from "video-renderer-src/episode/types";
import { getAssets, getMoments, saveMoments, switchMomentTreatment } from "./api";
import { momentIndexFromSceneId, normalizeMoment } from "./momentDuration";
import { OverlayStrip, type EditableOverlay } from "./OverlayStrip";

interface Asset {
    id: string;
    caption: string;
}

const VALID_TERM_LEVELS = ["muted", "primary", "accent"] as const;

// Treatments whose content doesn't live in m.text and has no per-field
// editor yet get a read-only summary — matches ui/static/app.js's
// NO_TEXT_EDIT_TREATMENTS (side-terms and side-text/sideTextStyle got
// real editors, side-diagram/side-code/comparison have not yet).
// content-dominant-code (#48) is the same codeAssetId-driven content as
// side-code, just a different presenter layout, so it gets the same
// treatment here.
const NO_TEXT_EDIT_TREATMENTS = new Set(["side-diagram", "side-code", "comparison", "content-dominant-code"]);

// The three treatments PUT /api/episode/moment-treatment (#62) knows how
// to switch between — mirrors generate_moments.py's CODE_TREATMENTS.
// Human-readable labels for the dropdown, since the raw treatment strings
// don't read well as UI copy (matches the spec's own presentation-name
// vocabulary — docs/specs/content-types-and-presentation-editing.md).
const CODE_TREATMENT_LABELS: Record<string, string> = {
    "side-code": "Split Screen",
    "content-dominant-code": "Content Dominant",
    "full-visual": "Full Screen",
};
const CODE_TREATMENTS = Object.keys(CODE_TREATMENT_LABELS);

function summarizeMomentContent(m: any): string {
    if (m.treatment === "comparison" && m.comparison) {
        return `${m.comparison.left || "?"} vs ${m.comparison.right || "?"}`;
    }
    if (m.treatment === "side-diagram" && m.diagram) {
        return (m.diagram.nodes || []).map((n: any) => n.label).join(" → ");
    }
    if (m.treatment === "side-code" || m.treatment === "content-dominant-code") {
        return m.codeAssetId || "";
    }
    return "";
}

interface Props {
    episodePath: string;
    sceneId: string;
    scenePlan: ScenePlan;
    currentFrame: number;
    onSeek: (absoluteFrame: number) => void;
    // Bumped by EpisodeWorkspace whenever an edit-plan chat instruction is
    // applied, so this panel re-fetches instead of saving stale data back
    // over a chat-applied removal — see EpisodeWorkspace's refreshKey.
    refreshKey: number;
    onClose: () => void;
}

export function MomentEditorPanel({ episodePath, sceneId, scenePlan, currentFrame, onSeek, refreshKey, onClose }: Props) {
    const [moments, setMoments] = useState<any[] | null>(null);
    const [assetOptions, setAssetOptions] = useState<Asset[]>([]);
    const [status, setStatus] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [timingExpanded, setTimingExpanded] = useState(false);
    const [switchingTreatment, setSwitchingTreatment] = useState(false);

    useEffect(() => {
        getMoments(episodePath)
            // Defensive normalization for moments.json written by an older
            // pipeline version — see momentDuration.ts. A no-op for
            // anything the current pipeline wrote; matters here since
            // OverlayStrip's drag math depends on maxDurationInParentFrames
            // already being the real, clamped duration.
            .then((data) => setMoments((data.moments ?? []).map(normalizeMoment)))
            .catch(() => setMoments([]));
        getAssets(episodePath)
            .then(setAssetOptions)
            .catch(() => setAssetOptions([]));
    }, [episodePath, refreshKey]);

    if (!moments) return null;

    const index = momentIndexFromSceneId(sceneId);

    if (index === null || !moments[index]) {
        return (
            <div style={styles.wrap}>
                <div style={styles.header}>
                    <span>Moment</span>
                    <button className="secondary small" onClick={onClose}>
                        Close
                    </button>
                </div>
                <p style={styles.hint}>Couldn't find a matching entry in moments.json for this scene.</p>
            </div>
        );
    }

    const moment = moments[index];

    const update = (patch: Record<string, unknown>) => {
        setMoments((prev) => (prev ? prev.map((m, i) => (i === index ? { ...m, ...patch } : m)) : prev));
    };

    // Reset to Automatic (#57): clears the field from overriddenFields so
    // it's eligible for the AI to change again on the next --force
    // regeneration — does NOT recompute a value right now (no scoped
    // "re-propose just this one field" endpoint exists, and the value
    // sitting here is still a perfectly valid current value either way).
    // The user sees no visible field-value change from clicking this; what
    // changes is only whether a future regeneration is allowed to touch it.
    const resetField = (field: string) => {
        const overriddenFields = (moment.overriddenFields || []).filter((f: string) => f !== field);
        update({ overriddenFields });
    };

    const isOverridden = (field: string) => (moment.overriddenFields || []).includes(field);

    const resetButton = (field: string) =>
        isOverridden(field) ? (
            <button
                type="button"
                className="secondary small"
                onClick={() => resetField(field)}
                title={`This field was manually edited — reset to let the AI decide it again next time`}
                style={styles.resetButton}
            >
                Reset to Automatic
            </button>
        ) : null;

    const updateTerm = (termIndex: number, patch: Record<string, unknown>) => {
        const terms = (moment.terms || []).map((t: any, ti: number) =>
            ti === termIndex ? { ...t, ...patch } : t
        );
        update({ terms });
    };

    // A code presentation switch (#62) is only offered when the moment is
    // ACTUALLY one of the three code treatments — "full-visual" also
    // covers image/diagram/text fullVisualKinds, which this endpoint
    // rejects, so it's gated on fullVisualKind === "code" specifically,
    // not just the treatment string.
    const isCodeMoment =
        moment.treatment === "side-code" ||
        moment.treatment === "content-dominant-code" ||
        (moment.treatment === "full-visual" && moment.fullVisualKind === "code");

    const switchTreatment = async (newTreatment: string) => {
        if (newTreatment === moment.treatment) return;
        setSwitchingTreatment(true);
        setStatus("Switching presentation…");
        setError(null);
        try {
            const result = await switchMomentTreatment(episodePath, sceneId, newTreatment);
            setMoments((result.moments ?? moments).map(normalizeMoment));
            setStatus("Presentation switched — the next render will pick this up.");
        } catch (e) {
            setError(String(e));
        } finally {
            setSwitchingTreatment(false);
        }
    };

    // "Adjust timing" used to be a separate scene-scoped page reached via a
    // new browser tab (?sceneId=... — see #28), which needed a
    // visibilitychange listener to notice edits made over there and
    // re-fetch moments.json. Now it's this same component's own state —
    // dragging a block writes directly into the `moments` array this panel
    // already saves from, so there's exactly one buffer, not two racing
    // each other.
    const parentScene = scenePlan.scenes.find(
        (s): s is PresenterScene => s.type === "presenter" && s.id === moment.sceneId
    );

    const editableOverlays: EditableOverlay[] = moments
        .filter((m) => m.sceneId === moment.sceneId)
        .map((m) => ({ kind: "moment" as const, data: m }));

    const updateOverlay = (updated: EditableOverlay) => {
        setMoments((prev) =>
            prev
                ? prev.map((m) =>
                      updated.kind === "moment" && m.windowId === updated.data.windowId ? updated.data : m
                  )
                : prev
        );
    };

    const remove = async () => {
        const next = moments.filter((_, i) => i !== index);
        setStatus("Saving…");
        setError(null);
        try {
            await saveMoments(episodePath, next);
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
            // The response's own moments (not the request's) carry
            // server-recomputed overriddenFields (#57) — using it, rather
            // than leaving local state as whatever was sent, means the
            // "Reset to Automatic" affordance appears immediately after a
            // save that just created an override, with no extra fetch.
            const result = await saveMoments(episodePath, moments);
            setMoments((result.moments ?? moments).map(normalizeMoment));
            setStatus("Saved — the next render will pick this up.");
        } catch (e) {
            setError(String(e));
        }
    };

    return (
        <div style={styles.wrap}>
            <div style={styles.header}>
                <span>{moment.treatment.toUpperCase()}</span>
                <button className="secondary small" onClick={onClose}>
                    Close
                </button>
            </div>

            {isCodeMoment && (
                <div style={styles.fieldRow}>
                    <label style={styles.presentationLabel}>Presentation</label>
                    <select
                        value={moment.treatment}
                        onChange={(e) => switchTreatment(e.target.value)}
                        disabled={switchingTreatment}
                        style={{ ...styles.input, flex: 1 }}
                    >
                        {CODE_TREATMENTS.map((t) => (
                            <option key={t} value={t}>
                                {CODE_TREATMENT_LABELS[t]}
                            </option>
                        ))}
                    </select>
                </div>
            )}

            {moment.treatment === "side-image" && (
                <select
                    value={moment.assetId ?? ""}
                    onChange={(e) => {
                        const asset = assetOptions.find((a) => a.id === e.target.value);
                        update({ assetId: e.target.value, caption: asset ? asset.caption : moment.caption });
                    }}
                    style={styles.input}
                >
                    {assetOptions.map((a) => (
                        <option key={a.id} value={a.id}>
                            {a.id} — {a.caption || ""}
                        </option>
                    ))}
                </select>
            )}

            {moment.treatment === "side-terms" && (
                <div style={styles.termsList}>
                    {(moment.terms || []).map((t: any, ti: number) => (
                        <div key={ti} style={styles.termRow}>
                            <input
                                type="text"
                                value={t.text || ""}
                                onChange={(e) => updateTerm(ti, { text: e.target.value })}
                                style={styles.termInput}
                            />
                            <select
                                value={t.level}
                                onChange={(e) => updateTerm(ti, { level: e.target.value })}
                                style={styles.termSelect}
                            >
                                {VALID_TERM_LEVELS.map((level) => (
                                    <option key={level} value={level}>
                                        {level}
                                    </option>
                                ))}
                            </select>
                        </div>
                    ))}
                </div>
            )}

            {NO_TEXT_EDIT_TREATMENTS.has(moment.treatment) && (
                <span style={styles.readonly}>{summarizeMomentContent(moment)}</span>
            )}

            {!["side-image", "side-terms"].includes(moment.treatment) &&
                !NO_TEXT_EDIT_TREATMENTS.has(moment.treatment) && (
                    <div style={styles.fieldRow}>
                        <input
                            type="text"
                            value={moment.text || ""}
                            onChange={(e) => update({ text: e.target.value })}
                            style={{ ...styles.input, flex: 1 }}
                        />
                        {resetButton("text")}
                    </div>
                )}

            {moment.treatment === "side-text" && (
                <div style={styles.fieldRow}>
                    <select
                        value={moment.sideTextStyle || "quote"}
                        onChange={(e) => update({ sideTextStyle: e.target.value })}
                        style={{ ...styles.input, flex: 1 }}
                    >
                        <option value="quote">quote</option>
                        <option value="title">title</option>
                    </select>
                    {resetButton("sideTextStyle")}
                </div>
            )}

            {moment.reason && <p style={styles.reason}>{moment.reason}</p>}

            {parentScene && (
                <div style={styles.fieldRow}>
                    <button className="secondary small" onClick={() => setTimingExpanded((v) => !v)} style={styles.timingToggle}>
                        {timingExpanded ? "Adjust timing ▾" : "Adjust timing ▸"}
                    </button>
                    {resetButton("offsetInParentFrames")}
                    {resetButton("maxDurationInParentFrames")}
                </div>
            )}

            {timingExpanded && parentScene && (
                <OverlayStrip
                    parentScene={parentScene}
                    overlays={editableOverlays}
                    onChange={updateOverlay}
                    onSeek={onSeek}
                    currentFrame={currentFrame}
                />
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
    fieldRow: {
        display: "flex",
        alignItems: "center",
        gap: 8,
    },
    presentationLabel: {
        fontSize: 12,
        color: "#9aa7b4",
        flexShrink: 0,
    },
    resetButton: {
        flexShrink: 0,
        fontSize: 11,
        color: "#e8a23a",
        borderColor: "#e8a23a",
    },
    termsList: {
        display: "flex",
        flexDirection: "column",
        gap: 6,
    },
    termRow: {
        display: "flex",
        gap: 6,
    },
    termInput: {
        flex: 1,
        padding: "6px 10px",
        background: "#0b0f14",
        border: "1px solid #2a333d",
        borderRadius: 6,
        color: "#e8edf2",
        fontSize: 13,
    },
    termSelect: {
        padding: "6px 10px",
        background: "#0b0f14",
        border: "1px solid #2a333d",
        borderRadius: 6,
        color: "#e8edf2",
        fontSize: 13,
    },
    readonly: {
        fontSize: 13,
        color: "#9aa7b4",
        fontStyle: "italic",
    },
    reason: {
        fontSize: 12,
        color: "#6b7683",
        margin: 0,
    },
    timingToggle: {
        alignSelf: "flex-start",
        fontSize: 12,
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
