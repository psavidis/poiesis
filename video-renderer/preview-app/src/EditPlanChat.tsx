import { useEffect, useRef, useState } from "react";
import type { ScenePlan } from "video-renderer-src/episode/types";
import { sceneLabel } from "./ActiveSceneBar";
import { editPlan, type EditPlanResult } from "./api";
import { colors, radius, typography } from "./tokens";

// Minimal shape of the Web Speech API this component actually uses — no
// @types/dom-speech-recognition dependency, since only a handful of
// members are needed and the full lib.dom types for this API are still
// inconsistently shipped across TS/lib versions. webkitSpeechRecognition
// is the only implementation Chrome ships (this project's own tooling and
// target browser — see #56's own scoping), so that's the only vendor
// prefix checked.
interface SpeechRecognitionResultLike {
    isFinal: boolean;
    [index: number]: { transcript: string };
}
interface SpeechRecognitionEventLike {
    resultIndex: number;
    results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike extends EventTarget {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    start(): void;
    stop(): void;
    onresult: ((event: SpeechRecognitionEventLike) => void) | null;
    onerror: ((event: { error: string }) => void) | null;
    onend: (() => void) | null;
}

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
    const w = window as unknown as {
        SpeechRecognition?: new () => SpeechRecognitionLike;
        webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

interface Props {
    episodePath: string;
    // touchedIds (#54) — scene ids actually changed/created by this edit,
    // so the caller can highlight and scroll them into view on the
    // relevant timeline bar(s) instead of leaving the user to hunt for
    // what the AI just did.
    onApplied: (touchedIds: string[]) => void;
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

    // Voice input (#56) — push-to-talk only: click to start, click again
    // (or the browser auto-stops on silence) to stop. Populates the same
    // `instruction` state live/incrementally as speech is recognized, so
    // it's visible and editable before Apply, same as typed text — never
    // auto-submitted on its own.
    const [listening, setListening] = useState(false);
    const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
    const speechSupported = useRef(getSpeechRecognitionCtor() !== null).current;

    const stopListening = () => {
        recognitionRef.current?.stop();
    };

    const startListening = () => {
        const Ctor = getSpeechRecognitionCtor();
        if (!Ctor || listening) return;

        setError(null);
        const recognition = new Ctor();
        recognition.continuous = false;
        recognition.interimResults = true;
        recognition.lang = "en-US";

        recognition.onresult = (event) => {
            let transcript = "";
            for (let i = 0; i < event.results.length; i++) {
                transcript += event.results[i][0].transcript;
            }
            setInstruction(transcript);
        };

        recognition.onerror = (event) => {
            setError(
                event.error === "not-allowed" || event.error === "permission-denied"
                    ? "Microphone permission denied — allow microphone access to use voice input."
                    : event.error === "no-speech"
                    ? "No speech detected — try again."
                    : `Voice input error: ${event.error}`
            );
        };

        recognition.onend = () => {
            setListening(false);
            recognitionRef.current = null;
        };

        recognitionRef.current = recognition;
        setListening(true);
        recognition.start();
    };

    // A newly clicked chip should reappear as "Editing: ..." even if a
    // previous selection was dismissed — dismiss only suppresses THIS
    // particular selection, not selection indicators in general.
    useEffect(() => {
        setDismissed(false);
    }, [selectedSceneId]);

    // Stops any in-flight recognition if the component unmounts mid-listen
    // (e.g. the user navigates away) — onend firing after unmount would
    // otherwise touch state on a gone component.
    useEffect(() => {
        return () => {
            recognitionRef.current?.stop();
        };
    }, []);

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

            if (
                editResult.applied.length > 0 ||
                editResult.created.length > 0 ||
                editResult.createdMoments.length > 0 ||
                editResult.createdImages.length > 0
            ) {
                onApplied(editResult.createdSceneIds);
            }
        } catch (e) {
            setError(String(e));
        } finally {
            setStatus("idle");
        }
    };

    return (
        <div style={styles.wrap}>
            <div style={styles.heading}>Ask AI</div>

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
                <div style={styles.formActions}>
                    {speechSupported && (
                        <button
                            type="button"
                            className="secondary"
                            onClick={listening ? stopListening : startListening}
                            disabled={status === "submitting"}
                            title={listening ? "Stop listening" : "Speak an instruction"}
                            style={listening ? styles.micButtonListening : undefined}
                        >
                            {listening ? "● Listening…" : "🎤"}
                        </button>
                    )}
                    <button
                        type="submit"
                        style={styles.applyButton}
                        disabled={status === "submitting" || !instruction.trim()}
                    >
                        {status === "submitting" ? "Thinking…" : "Apply"}
                    </button>
                </div>
            </form>

            {error && <div style={styles.error}>{error}</div>}

            {result && (
                <div style={styles.resultBox}>
                    {result.applied.length === 0 &&
                        result.rejected.length === 0 &&
                        result.created.length === 0 &&
                        result.createdMoments.length === 0 &&
                        result.createdImages.length === 0 && (
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
                        <div key={`created-beat-${i}`} style={styles.appliedRow}>
                            <span style={styles.opBadge}>CREATED</span>
                            <span>
                                {beat.kind} on {beat.sceneId}: "{beat.text}"
                                {beat.reason ? ` — ${beat.reason}` : ""}
                            </span>
                        </div>
                    ))}

                    {result.createdMoments.map((moment, i) => {
                        // A diagram-created moment has no "text" — summarize
                        // its node labels instead (mirrors edit_plan.py's
                        // own CLI summary for the same case).
                        const summary = moment.text ?? moment.diagram?.nodes.map((n) => n.label).join(", ") ?? "";
                        return (
                            <div key={`created-moment-${i}`} style={styles.appliedRow}>
                                <span style={styles.opBadge}>CREATED</span>
                                <span>
                                    {moment.treatment} on {moment.sceneId}: "{summary}"
                                    {moment.reason ? ` — ${moment.reason}` : ""}
                                </span>
                            </div>
                        );
                    })}

                    {result.createdImages.map((image, i) => (
                        <div key={`created-image-${i}`} style={styles.appliedRow}>
                            <span style={styles.opBadge}>CREATED</span>
                            <span>
                                inset image on {image.parentSceneId}: {image.assetId}
                            </span>
                        </div>
                    ))}

                    {result.rejected.map((r, i) => (
                        <div key={`rejected-${i}`} style={styles.rejectedRow}>
                            <span style={styles.opBadge}>REJECTED</span>
                            <span>{r.reason}</span>
                        </div>
                    ))}

                    {(result.applied.length > 0 ||
                        result.created.length > 0 ||
                        result.createdMoments.length > 0 ||
                        result.createdImages.length > 0) && (
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
        gap: 10,
    },
    heading: {
        fontSize: typography.size.lg,
        fontWeight: typography.weight.bold,
        color: colors.textPrimary,
    },
    form: {
        display: "flex",
        flexDirection: "column",
        gap: 8,
    },
    formActions: {
        display: "flex",
        gap: 8,
    },
    applyButton: {
        flex: 1,
    },
    selectionRow: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        padding: "6px 10px",
        background: colors.surface,
        border: `1px solid ${colors.borderStrong}`,
        borderRadius: radius.md,
        fontSize: typography.size.sm,
    },
    selectionLabel: {
        color: colors.textSecondary,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
    },
    input: {
        flex: 1,
        padding: "8px 12px",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        color: colors.textPrimary,
        fontSize: typography.size.base,
    },
    error: {
        color: colors.error,
        fontSize: typography.size.md,
    },
    // Single-use recording-active/rejected-text reds — not promoted to
    // tokens.ts since nothing else in the app currently reuses these
    // exact shades (see tokens.ts's own comment: only genuinely shared
    // values belong there).
    micButtonListening: {
        background: "#c94a3c",
        borderColor: "#c94a3c",
        color: "#fff",
    },
    resultBox: {
        display: "flex",
        flexDirection: "column",
        gap: 4,
        fontSize: typography.size.md,
    },
    appliedRow: {
        display: "flex",
        gap: 8,
        alignItems: "baseline",
        color: colors.textPrimary,
    },
    rejectedRow: {
        display: "flex",
        gap: 8,
        alignItems: "baseline",
        color: "#c96f6f",
    },
    opBadge: {
        flexShrink: 0,
        fontSize: typography.size.xs,
        fontWeight: typography.weight.bold,
        letterSpacing: 0.5,
        color: colors.textSecondary,
    },
    hint: {
        fontSize: typography.size.sm,
        color: colors.textMuted,
        marginTop: 4,
    },
};
