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

// One turn in the visible thread — either what the user typed/spoke, or
// what came back for it. Kept as a flat list of independent turns, not a
// nested {instruction, response} pair, since a bubble UI (#66) renders
// each side as its own row regardless of how they pair up.
type ChatMessage =
    | { role: "user"; id: string; text: string }
    | { role: "ai"; id: string; result: EditPlanResult }
    | { role: "ai-error"; id: string; message: string };

let messageIdCounter = 0;
function nextMessageId(): string {
    messageIdCounter += 1;
    return `msg-${messageIdCounter}`;
}

// The in-app natural-language edit loop: type an instruction, the backend
// asks the LLM to propose remove/update operations against the CURRENT
// scene-plan.json (validated server-side — unknown scene ids or
// non-editable fields are rejected, never silently trusted), applies what's
// valid, and this component shows exactly what happened before the caller
// reloads the plan. Each submission is an INDEPENDENT request against
// whatever the plan currently is — the server has no multi-turn memory, a
// later instruction doesn't reference earlier ones. `messages` below is
// purely a client-side visual history (#66 — a real conversation thread of
// bubbles, not a single input that only ever shows its latest result) and
// is lost on refresh; it is not conversation state the backend knows about.
export function EditPlanChat({ episodePath, onApplied, selectedSceneId, scenePlan }: Props) {
    const [instruction, setInstruction] = useState("");
    const [status, setStatus] = useState<"idle" | "submitting">("idle");
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const threadEndRef = useRef<HTMLDivElement>(null);
    // Transient mic feedback (permission denied, no speech detected) — kept
    // separate from `messages` since it's about the INPUT mechanism, not a
    // failed edit request, so it doesn't belong in the thread as a turn.
    const [voiceError, setVoiceError] = useState<string | null>(null);
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

        setVoiceError(null);
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
            setVoiceError(
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

    // Auto-scrolls the thread to the newest message — matches the
    // ChatGPT/Canva convention of always landing on the latest turn rather
    // than leaving the reader scrolled wherever they were.
    useEffect(() => {
        threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }, [messages]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        const submitted = instruction.trim();
        if (!submitted || status === "submitting") return;

        setMessages((prev) => [...prev, { role: "user", id: nextMessageId(), text: submitted }]);
        setStatus("submitting");
        setInstruction("");

        try {
            const editResult = await editPlan(
                episodePath,
                submitted,
                showSelection ? selectedSceneId : undefined
            );
            setMessages((prev) => [...prev, { role: "ai", id: nextMessageId(), result: editResult }]);

            if (
                editResult.applied.length > 0 ||
                editResult.created.length > 0 ||
                editResult.createdMoments.length > 0 ||
                editResult.createdImages.length > 0
            ) {
                onApplied(editResult.createdSceneIds);
            }
        } catch (e) {
            setMessages((prev) => [...prev, { role: "ai-error", id: nextMessageId(), message: String(e) }]);
        } finally {
            setStatus("idle");
        }
    };

    return (
        <div style={styles.wrap}>
            <div style={styles.heading}>Ask AI</div>

            <div style={styles.thread}>
                {messages.length === 0 && (
                    <div style={styles.emptyHint}>
                        Type an instruction below — e.g. "remove the third title card" or "make this bigger".
                    </div>
                )}

                {messages.map((message) => (
                    <ChatBubble key={message.id} message={message} />
                ))}

                {status === "submitting" && (
                    <div style={styles.bubbleRowAi}>
                        <div style={{ ...styles.bubble, ...styles.bubbleAi }}>
                            <span style={styles.thinkingHint}>Thinking…</span>
                        </div>
                    </div>
                )}

                <div ref={threadEndRef} />
            </div>

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

            {voiceError && <div style={styles.error}>{voiceError}</div>}
        </div>
    );
}

// One message row — right-aligned/accent-colored for the user, left-aligned
// for the AI, matching the ChatGPT/Canva convention (#66) instead of the
// previous single "latest result" block. AI content reuses exactly the
// same applied/created/rejected rendering the old single-result box had —
// only where it's mounted (once per turn, inside a bubble) changed.
function ChatBubble({ message }: { message: ChatMessage }) {
    if (message.role === "user") {
        return (
            <div style={styles.bubbleRowUser}>
                <div style={{ ...styles.bubble, ...styles.bubbleUser }}>{message.text}</div>
            </div>
        );
    }

    if (message.role === "ai-error") {
        return (
            <div style={styles.bubbleRowAi}>
                <div style={{ ...styles.bubble, ...styles.bubbleAi }}>
                    <div style={styles.error}>{message.message}</div>
                </div>
            </div>
        );
    }

    const result = message.result;
    const hasAnyChange =
        result.applied.length > 0 ||
        result.created.length > 0 ||
        result.createdMoments.length > 0 ||
        result.createdImages.length > 0;

    return (
        <div style={styles.bubbleRowAi}>
            <div style={{ ...styles.bubble, ...styles.bubbleAi }}>
                {!hasAnyChange && result.rejected.length === 0 && (
                    <div style={styles.explanationText}>
                        {result.explanation ?? "No matching scene found for that instruction — nothing changed."}
                    </div>
                )}

                {result.applied.map((op, i) => (
                    <div key={`applied-${i}`} style={styles.appliedRow}>
                        <span style={{ ...styles.opBadge, ...styles.opBadgeSuccess }}>{op.op === "remove" ? "REMOVED" : "UPDATED"}</span>
                        <span>
                            {op.sceneId}
                            {op.reason ? ` — ${op.reason}` : ""}
                        </span>
                    </div>
                ))}

                {result.created.map((beat, i) => (
                    <div key={`created-beat-${i}`} style={styles.appliedRow}>
                        <span style={{ ...styles.opBadge, ...styles.opBadgeSuccess }}>CREATED</span>
                        <span>
                            {beat.kind} on {beat.sceneId}: "{beat.text}"
                            {beat.reason ? ` — ${beat.reason}` : ""}
                        </span>
                    </div>
                ))}

                {result.createdMoments.map((moment, i) => {
                    // A diagram-created moment has no "text" — summarize its
                    // node labels instead (mirrors edit_plan.py's own CLI
                    // summary for the same case).
                    const summary = moment.text ?? moment.diagram?.nodes.map((n) => n.label).join(", ") ?? "";
                    return (
                        <div key={`created-moment-${i}`} style={styles.appliedRow}>
                            <span style={{ ...styles.opBadge, ...styles.opBadgeSuccess }}>CREATED</span>
                            <span>
                                {moment.treatment} on {moment.sceneId}: "{summary}"
                                {moment.reason ? ` — ${moment.reason}` : ""}
                            </span>
                        </div>
                    );
                })}

                {result.createdImages.map((image, i) => (
                    <div key={`created-image-${i}`} style={styles.appliedRow}>
                        <span style={{ ...styles.opBadge, ...styles.opBadgeSuccess }}>CREATED</span>
                        <span>
                            inset image on {image.parentSceneId}: {image.assetId}
                        </span>
                    </div>
                ))}

                {result.rejected.map((r, i) => (
                    <div key={`rejected-${i}`} style={styles.rejectedRow}>
                        <span style={{ ...styles.opBadge, ...styles.opBadgeRejected }}>REJECTED</span>
                        <span>{r.reason}</span>
                    </div>
                ))}

                {hasAnyChange && (
                    <div style={styles.metaNote}>Applied to scene-plan.json — the next render will pick this up.</div>
                )}
            </div>
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 10,
        // Fills the sidebar's fixed height so `thread` below (flex: 1,
        // minHeight: 0) can claim the remaining space and scroll on its
        // own, while heading/form stay their natural size.
        height: "100%",
        minHeight: 0,
    },
    heading: {
        fontSize: typography.size.lg,
        // semibold, not bold — bold at this size read heavier than the
        // rest of the panel's restrained weight; semibold plus the
        // widened tracking below carries the same presence without
        // feeling clunky.
        fontWeight: typography.weight.semibold,
        color: colors.textPrimary,
        letterSpacing: 0.3,
        lineHeight: typography.lineHeight.tight,
    },
    // Scrolls independently of the input row below it, which stays pinned
    // — the conversation grows upward from the input, same as ChatGPT/
    // Canva's chat panels, rather than pushing the input off-screen.
    thread: {
        display: "flex",
        flexDirection: "column",
        gap: 10,
        flex: 1,
        minHeight: 0,
        overflowY: "auto",
    },
    emptyHint: {
        fontSize: typography.size.reading,
        // textSecondary, not textMuted — textMuted's ~3.8:1 contrast on
        // this dark surface falls below WCAG AA's 4.5:1 minimum for body
        // text, which read as illegible gray-on-navy. textSecondary is the
        // muted-but-still-readable tier; textMuted is reserved for
        // decorative/non-content use only from here on.
        color: colors.textSecondary,
        lineHeight: typography.lineHeight.relaxed,
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
        lineHeight: typography.lineHeight.tight,
    },
    selectionLabel: {
        color: colors.textSecondary,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
    },
    input: {
        flex: 1,
        // Matches the reading-sized text above it, so what you type looks
        // like it belongs to the same conversation as what's above it
        // rather than reverting to smaller UI-label sizing right where
        // the thread ends.
        padding: "10px 13px",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        color: colors.textPrimary,
        fontSize: typography.size.reading,
        lineHeight: typography.lineHeight.tight,
    },
    error: {
        color: colors.error,
        fontSize: typography.size.md,
        lineHeight: typography.lineHeight.relaxed,
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
    bubbleRowUser: {
        display: "flex",
        justifyContent: "flex-end",
    },
    bubbleRowAi: {
        display: "flex",
        justifyContent: "flex-start",
    },
    // 12px radius, not the smaller radius.lg (8px) used elsewhere in the
    // app's boxier panels/inputs — a conversation bubble reads softer and
    // more considered with a rounder shape than a form control does, and
    // the extra roundness is what makes the small "tail" corner (4px, via
    // radius.sm below) register as a deliberate speech-bubble cue instead
    // of just an inconsistent corner.
    bubble: {
        display: "flex",
        flexDirection: "column",
        gap: 7,
        maxWidth: "86%",
        padding: "11px 15px",
        borderRadius: 12,
        fontSize: typography.size.reading,
        lineHeight: typography.lineHeight.relaxed,
        wordBreak: "break-word",
    },
    // Neither a solid gold fill (text sitting directly on a saturated
    // mid-tone never reads crisp — dark text goes muddy, light text fails
    // contrast outright) nor a plain thin outline (too quiet a
    // differentiator once it sits next to the AI bubble's own border —
    // the two read as near-identical dark boxes). This is the third path:
    // a warm gold-TINTED dark surface (12:1 contrast for textPrimary, same
    // as everywhere else) carrying a bold solid accent bar down the left
    // edge — the gold does its job as a strong, immediate visual signature
    // without ever being the surface text has to sit on top of.
    // A soft gold bloom, not a bright neon glow — CLAUDE.md's own design
    // directive names "excessive/generic glowing UI" as a thing to avoid,
    // so the shadow here stays low-opacity and wide-blurred (a haze, not
    // a hard-edged effect) and is exclusive to the user's OWN bubble, not
    // applied ambiently across the panel — it's a deliberate signature
    // for "this is what you said," not decoration.
    bubbleUser: {
        // 10% accent over surface — warm enough to read as clearly its
        // own thing next to bubbleAi's neutral surfaceElevated, subtle
        // enough that it's still obviously the same dark family, not a
        // jump to a foreign color.
        background: "#292c31",
        border: `1px solid rgba(212, 162, 78, 0.45)`,
        boxShadow: "0 0 18px rgba(212, 162, 78, 0.22), 0 0 3px rgba(212, 162, 78, 0.3)",
        // A pale warm gold, not textPrimary's neutral off-white — the
        // glow effect wants the text itself carrying the accent hue, not
        // just the border/shadow around it. Still ~11:1 contrast on this
        // background (see the numbers this was checked against), so nothing
        // is traded for the color — it's exactly as legible as textPrimary,
        // just warmer. The text-shadow is a tight, low-spread glow (not a
        // wide neon blur) so it reads as "this text is lit," not smeared.
        color: "#f6ead0",
        textShadow: "0 0 8px rgba(212, 162, 78, 0.5)",
        borderBottomRightRadius: radius.sm,
    },
    // The AI's own half of the same glow language bubbleUser establishes
    // — cool blue rather than gold, both so the two sides stay clearly
    // differentiated at a glance and because blue is this app's own
    // existing "text/AI content" semantic (colors.timelineText, reused
    // here rather than inventing a new hue). Covers the "Thinking…"
    // placeholder and error bubble too, since both share this style.
    bubbleAi: {
        background: colors.surfaceElevated,
        border: `1px solid rgba(74, 143, 209, 0.4)`,
        boxShadow: "0 0 16px rgba(74, 143, 209, 0.16), 0 0 3px rgba(74, 143, 209, 0.22)",
        color: "#dce8f7",
        textShadow: "0 0 7px rgba(74, 143, 209, 0.35)",
        borderBottomLeftRadius: radius.sm,
    },
    thinkingHint: {
        fontSize: typography.size.reading,
        // textSecondary — see emptyHint's comment on why textMuted is
        // avoided for anything read as content.
        color: colors.textSecondary,
        fontStyle: "italic",
        lineHeight: typography.lineHeight.relaxed,
    },
    // font-size/line-height intentionally NOT set here — both rows sit
    // inside .bubble, which already establishes the reading size/relaxed
    // line-height for this whole surface; repeating it per-row is how the
    // panel drifted out of one coherent scale last time.
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
        color: colors.textSecondary,
    },
    // A small solid label rather than plain colored text — gives each
    // operation an immediately scannable outcome at a glance (success
    // green for applied/created, the semantic error red for rejected)
    // instead of every row reading as one undifferentiated color, which
    // matters once a bubble lists several operations at once. Uppercase
    // + wide tracking is what keeps an 11px label legible on its own —
    // small text needs weight and space, not just a smaller font-size.
    opBadge: {
        flexShrink: 0,
        fontSize: typography.size.xs,
        fontWeight: typography.weight.bold,
        letterSpacing: 0.6,
        textTransform: "uppercase",
        padding: "2px 7px",
        borderRadius: radius.sm,
        lineHeight: typography.lineHeight.tight,
    },
    opBadgeSuccess: {
        color: colors.success,
        background: "rgba(75, 179, 131, 0.14)",
    },
    opBadgeRejected: {
        color: colors.error,
        background: "rgba(255, 148, 132, 0.14)",
    },
    // The AI's own explanation when it declines an instruction — this IS
    // the message's content, not a footnote, so it reads at the bubble's
    // normal textPrimary color/weight and reading size, not muted or
    // shrunk down.
    explanationText: {
        color: colors.textPrimary,
    },
    // The trailing "Applied to scene-plan.json…" confirmation note — a
    // genuinely secondary meta-line after the real content above it, so
    // it drops one size down (sm, not the bubble's reading size) and
    // uses textSecondary (not textMuted, which fails contrast on this
    // surface) rather than fighting the content above it for attention.
    metaNote: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        lineHeight: typography.lineHeight.relaxed,
        marginTop: 1,
    },
};
