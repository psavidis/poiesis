import { useState } from "react";
import { editPlan, type EditPlanResult } from "./api";

interface Props {
    episodePath: string;
    onApplied: () => void;
}

// The in-app natural-language edit loop: type an instruction, the backend
// asks the LLM to propose remove/update operations against the CURRENT
// scene-plan.json (validated server-side — unknown scene ids or
// non-editable fields are rejected, never silently trusted), applies what's
// valid, and this component shows exactly what happened before the caller
// reloads the plan. Each submission is an independent request against
// whatever the plan currently is — there's no multi-turn conversation state
// kept here, matching the scope decided for the first version.
export function EditPlanChat({ episodePath, onApplied }: Props) {
    const [instruction, setInstruction] = useState("");
    const [status, setStatus] = useState<"idle" | "submitting">("idle");
    const [result, setResult] = useState<EditPlanResult | null>(null);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!instruction.trim() || status === "submitting") return;

        setStatus("submitting");
        setError(null);
        setResult(null);

        try {
            const editResult = await editPlan(episodePath, instruction);
            setResult(editResult);
            setInstruction("");

            if (editResult.applied.length > 0) {
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
            <form onSubmit={handleSubmit} style={styles.form}>
                <input
                    type="text"
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    placeholder='e.g. "remove the third title card" or "trim 10 frames off the end of scene-009"'
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
                    {result.applied.length === 0 && result.rejected.length === 0 && (
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

                    {result.rejected.map((r, i) => (
                        <div key={`rejected-${i}`} style={styles.rejectedRow}>
                            <span style={styles.opBadge}>REJECTED</span>
                            <span>{r.reason}</span>
                        </div>
                    ))}

                    {result.applied.length > 0 && (
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
