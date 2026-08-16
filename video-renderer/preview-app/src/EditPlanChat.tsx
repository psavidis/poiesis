import { useEffect, useState } from "react";
import type { ScenePlan } from "video-renderer-src/episode/types";
import { sceneLabel } from "./ActiveSceneBar";
import { editPlan, type EditPlanResult } from "./api";

interface Props {
    episodePath: string;
    onApplied: () => void;
    // Set by EpisodeWorkspace when a scene chip in ActiveSceneBar is
    // clicked (see #29) — passed to the backend as structured context
    // (#51), not typed text, so "make this bigger" can resolve to the
    // selected scene without the user ever typing its id. Previously this
    // pre-filled the instruction box with "edit scene-XXX: " text; now
    // the box stays free-text and the indicator below it shows what
    // "this" currently refers to.
    selectedSceneId?: string;
    // Needed to render the selection indicator's label (scene type/
    // content) — the id alone isn't meaningful to read at a glance.
    scenePlan?: ScenePlan;
}

// The in-app natural-language edit loop: type an instruction, the backend
// asks the LLM to propose remove/update operations against the CURRENT
// scene-plan.json (validated server-side — unknown scene ids or
// non-editable fields are rejected, never silently trusted), applies what's
// valid, and this component shows exactly what happened before the caller
// reloads the plan. Each submission is an independent request against
// whatever the plan currently is — there's no multi-turn conversation state
// kept here, matching the scope decided for the first version.
export function EditPlanChat({ episodePath, onApplied, selectedSceneId, scenePlan }: Props) {
    const [instruction, setInstruction] = useState("");
    const [status, setStatus] = useState<"idle" | "submitting">("idle");
    const [result, setResult] = useState<EditPlanResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    // Local dismiss, separate from EpisodeWorkspace's own selection state
    // — clicking another chip still re-selects normally; this only lets
    // the user clear "this" from the current instruction without needing
    // a track/timeline click elsewhere to deselect.
    const [dismissed, setDismissed] = useState(false);

    // A newly clicked chip should reappear as "Editing: ..." even if a
    // previous selection was dismissed — dismiss only suppresses THIS
    // particular selection, not selection indicators in general.
    useEffect(() => {
        setDismissed(false);
    }, [selectedSceneId]);

    const selectedScene = scenePlan?.scenes.find((s) => s.id === selectedSceneId);
    const showSelection = selectedSceneId && selectedScene && !dismissed;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!instruction.trim() || status === "submitting") return;

        setStatus("submitting");
        setError(null);
        setResult(null);

        try {
            const editResult = await editPlan(
                episodePath,
                instruction,
                showSelection ? selectedSceneId : undefined
            );
            setResult(editResult);
            setInstruction("");

            if (editResult.applied.length > 0 || editResult.created.length > 0) {
                onApplied();
            }
        } catch (e) {
            setError(String(e));
        } finally {
            setStatus("idle");
        }
    };

    return (
        <div style={styles.wrap}>
            {showSelection && (
                <div style={styles.selectionRow}>
                    <span style={styles.selectionLabel}>
                        Editing: <strong>{selectedScene.type}</strong> — {sceneLabel(selectedScene)}
                    </span>
                    <button
                        type="button"
                        className="secondary small"
                        onClick={() => setDismissed(true)}
                        title='Clear selection — "this" will no longer resolve to it'
                    >
                        Clear
                    </button>
                </div>
            )}

            <form onSubmit={handleSubmit} style={styles.form}>
                <input
                    type="text"
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    placeholder={
                        showSelection
                            ? 'e.g. "make this bigger" or "remove this"'
                            : 'e.g. "remove the third title card" or "trim 10 frames off the end of scene-009"'
                    }
                    style={styles.input}
                    disabled={status === "submitting"}
                />
                <button type="submit" disabled={status === "submitting" || !instruction.trim()}>
                    {status === "submitting" ? "Thinking…" : "Apply"}
                </button>
            </form>

            {error && <div style={styles.error}>{error}</div>}

            {result && (
                <div style={styles.resultBox}>
                    {result.applied.length === 0 && result.rejected.length === 0 && result.created.length === 0 && (
                        <div style={styles.hint}>
                            No matching scene found for that instruction — nothing changed.
                        </div>
                    )}

                    {result.applied.map((op, i) => (
                        <div key={`applied-${i}`} style={styles.appliedRow}>
                            <span style={styles.opBadge}>{op.op === "remove" ? "REMOVED" : "UPDATED"}</span>
                            <span>
                                {op.sceneId}
                                {op.reason ? ` — ${op.reason}` : ""}
                            </span>
                        </div>
                    ))}

                    {result.created.map((beat, i) => (
                        <div key={`created-${i}`} style={styles.appliedRow}>
                            <span style={styles.opBadge}>CREATED</span>
                            <span>
                                {beat.kind} on {beat.sceneId}: "{beat.text}"
                                {beat.reason ? ` — ${beat.reason}` : ""}
                            </span>
                        </div>
                    ))}

                    {result.rejected.map((r, i) => (
                        <div key={`rejected-${i}`} style={styles.rejectedRow}>
                            <span style={styles.opBadge}>REJECTED</span>
                            <span>{r.reason}</span>
                        </div>
                    ))}

                    {(result.applied.length > 0 || result.created.length > 0) && (
                        <div style={styles.hint}>
                            Applied to scene-plan.json — the next render will pick this up.
                        </div>
                    )}
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
    form: {
        display: "flex",
        gap: 8,
    },
    selectionRow: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        padding: "6px 10px",
        background: "#161d24",
        border: "1px solid #3a4552",
        borderRadius: 6,
        fontSize: 12,
    },
    selectionLabel: {
        color: "#9aa7b4",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
    },
    input: {
        flex: 1,
        padding: "8px 12px",
        background: "#161d24",
        border: "1px solid #2a333d",
        borderRadius: 6,
        color: "#e8edf2",
        fontSize: 14,
    },
    error: {
        color: "#ff8f8f",
        fontSize: 13,
    },
    resultBox: {
        display: "flex",
        flexDirection: "column",
        gap: 4,
        fontSize: 13,
    },
    appliedRow: {
        display: "flex",
        gap: 8,
        alignItems: "baseline",
        color: "#e8edf2",
    },
    rejectedRow: {
        display: "flex",
        gap: 8,
        alignItems: "baseline",
        color: "#c96f6f",
    },
    opBadge: {
        flexShrink: 0,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: 0.5,
        color: "#9aa7b4",
    },
    hint: {
        fontSize: 12,
        color: "#6b7683",
        marginTop: 4,
    },
};
