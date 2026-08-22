import { useEffect, useRef, useState } from "react";
import { getEpisodeStatus, runOverWebSocket, type EpisodeStatus, type RunHandle, type RunMessage } from "./api";
import { colors, radius, typography } from "./tokens";

// Groups the 15 chained pipeline stages (ui/pipeline_stages.py's
// PIPELINE_STAGES, mirrored here by id — no backend change, this is pure
// client-side aggregation of GET /api/episode/status's per-stage
// "complete" flags) into phases a user who doesn't know the pipeline
// internals can actually read. Order matches PIPELINE_STAGES exactly.
const PHASES: { label: string; stageIds: string[] }[] = [
    {
        label: "Ingest",
        stageIds: ["prepare", "transcribe", "validate_transcripts", "normalize_transcripts", "merge_segments"],
    },
    {
        label: "Understand",
        stageIds: ["analyze_episode", "analyze_scenes", "index_assets"],
    },
    {
        label: "Draft edit",
        stageIds: [
            "generate_title_scenes",
            "generate_storyboard",
            "generate_moments",
            "generate_captions",
            "generate_emphasis",
        ],
    },
    {
        label: "Finalize",
        stageIds: ["generate_scene_plan_ts", "generate_episode_assets"],
    },
];

type PhaseState = "done" | "in-progress" | "not-started";

function phaseState(stageIds: string[], status: EpisodeStatus | null): PhaseState {
    if (!status) return "not-started";

    const relevant = status.stages.filter((s) => stageIds.includes(s.id));
    if (relevant.length === 0) return "not-started";

    // A stage with complete === null (e.g. generate_scene_plan_ts, which
    // has no artifact file to check — see pipeline_stages.py's Stage)
    // reports "unknown," not "incomplete." Counting it against doneCount
    // meant a phase containing one could never reach "done" at all, no
    // matter how far the run actually got — Finalize's dot was
    // permanently stuck at amber (#68). Judge completeness only from
    // stages that CAN report it; a phase made ENTIRELY of unknowable
    // stages still needs an in-progress signal, so that case falls
    // through to the true/false-checkable set being empty below.
    const checkable = relevant.filter((s) => s.complete !== null);
    const doneCount = checkable.filter((s) => s.complete).length;

    if (checkable.length > 0 && doneCount === checkable.length) return "done";
    if (doneCount > 0) return "in-progress";
    return "not-started";
}

// While a run is active, polling GET /api/episode/status is the only
// reliable way to know which stage just completed — the WebSocket stream
// itself only carries raw log lines (see RunMessage), no structured
// per-stage event, so parsing log text for stage boundaries would be
// fragile and coupled to run_pipeline.py's print format.
const POLL_INTERVAL_MS = 2000;

interface Props {
    episodePath: string;
    skipCaptions: boolean;
    onStatusChange?: (status: EpisodeStatus) => void;
}

export function ProgressFlow({ episodePath, skipCaptions, onStatusChange }: Props) {
    const [status, setStatus] = useState<EpisodeStatus | null>(null);
    const [running, setRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [log, setLog] = useState("");
    // Kept independent of `running` — the log used to unmount the instant
    // a run stopped, whether it succeeded, failed, or was cancelled, so a
    // real failure vanished with no trace right when the user most needed
    // to see it (#68). Defaults to shown once a run has produced any
    // output; the user can still collapse it.
    const [logVisible, setLogVisible] = useState(false);
    // Explicit opt-in, not just inferred from "every stage already has
    // output" — a user re-running only some stages (e.g. after a manual
    // tweak upstream) still needs a way to force regeneration even when
    // the pipeline isn't fully done, which allDone-only forcing can't
    // express. Defaults off so a plain "Start"/accidental click never
    // discards existing work.
    const [forceRerun, setForceRerun] = useState(false);
    const runHandleRef = useRef<RunHandle | null>(null);
    const logRef = useRef<HTMLPreElement>(null);

    const refreshStatus = () => {
        getEpisodeStatus(episodePath)
            .then((s) => {
                setStatus(s);
                onStatusChange?.(s);
            })
            .catch((e) => setError(String(e)));
    };

    useEffect(() => {
        refreshStatus();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [episodePath]);

    useEffect(() => {
        if (!running) return;
        const interval = setInterval(refreshStatus, POLL_INTERVAL_MS);
        return () => clearInterval(interval);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [running]);

    useEffect(() => {
        if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    }, [log]);

    // Same complete === null handling as phaseState below — a stage with
    // no artifact to check (generate_scene_plan_ts) must not permanently
    // block "Re-run pipeline" from ever being offered.
    const allDone = status ? status.stages.every((s) => s.complete !== false) : false;

    const start = () => {
        setError(null);
        setRunning(true);
        setLog("");
        setLogVisible(true);

        runHandleRef.current = runOverWebSocket(
            "/ws/pipeline/run",
            // force is driven ONLY by the explicit "Force regenerate all
            // stages" checkbox (forceRerun) — an earlier version also
            // forced whenever every stage already had output (`|| allDone`),
            // so clicking "Re-run pipeline" on a fully-complete episode
            // silently force-regenerated everything (including a full
            // re-transcription) with no separate confirmation, regardless
            // of the checkbox. Confirmed live: this destroyed several
            // clips' original transcripts on a real episode before the
            // user could react. Without force, a fully-complete episode's
            // "Re-run pipeline" is now a correct no-op (every stage's own
            // Stage.is_complete check skips it) rather than a silent
            // full regenerate — the user must explicitly tick the
            // checkbox to force anything.
            { path: episodePath, skipCaptions, force: forceRerun },
            (msg: RunMessage) => {
                if (msg.type === "start") {
                    setLog((prev) => prev + `$ ${msg.command}\n`);
                } else if (msg.type === "log") {
                    setLog((prev) => prev + msg.line + "\n");
                } else if (msg.type === "error") {
                    setLog((prev) => prev + `\nERROR: ${msg.message}\n`);
                    setError(msg.message);
                    setRunning(false);
                } else if (msg.type === "done") {
                    // A pipeline stage failing exits non-zero but still
                    // reaches this "done" branch, not "error" — create_
                    // episode.sh just stops chaining further stages
                    // (see run_pipeline.py). Previously that looked
                    // identical to a clean finish: dots stopped moving,
                    // "Processing…" reverted to "Start", log vanished
                    // with it (logVisible used to be tied to `running`)
                    // — no signal anything had gone wrong (#68).
                    if (msg.exitCode !== 0) {
                        setLog((prev) => prev + `\nPipeline failed (exit code ${msg.exitCode}) — see output above.\n`);
                        setError(`Pipeline stopped with exit code ${msg.exitCode}. See output below for details.`);
                    } else {
                        setLog((prev) => prev + `\n(exit code ${msg.exitCode})\n`);
                    }
                    setRunning(false);
                    refreshStatus();
                } else if (msg.type === "cancelled") {
                    setLog((prev) => prev + `\nCancelled.\n`);
                    setRunning(false);
                    refreshStatus();
                }
            }
        );
    };

    const cancel = () => {
        runHandleRef.current?.cancel();
    };

    return (
        <div style={styles.wrap}>
            <div style={styles.phases}>
                {PHASES.map((phase) => {
                    const state = phaseState(phase.stageIds, status);
                    // Only the phase actually running right now pulses —
                    // running=true alone isn't enough, since Draft edit's
                    // dot shouldn't animate while Ingest is still going.
                    const isActive = running && state === "in-progress";
                    return (
                        <div key={phase.label} style={styles.phase}>
                            <span
                                className={isActive ? "phase-dot-active" : undefined}
                                style={{ ...styles.dot, ...dotStyleFor(state) }}
                            />
                            <span style={styles.phaseLabel}>{phase.label}</span>
                        </div>
                    );
                })}
            </div>

            <div style={styles.actions}>
                {!running && (
                    <button onClick={start} disabled={!status}>
                        {forceRerun ? "Force re-run" : allDone ? "Re-run pipeline" : "Start"}
                    </button>
                )}
                {running && (
                    <>
                        <span className="processing-label" style={styles.runningLabel}>
                            Processing…
                        </span>
                        <button className="secondary" onClick={cancel}>
                            Cancel
                        </button>
                    </>
                )}
                {log && (
                    <button className="secondary small" onClick={() => setLogVisible((v) => !v)}>
                        {logVisible ? "Hide output" : "Show output"}
                    </button>
                )}
            </div>

            {!running && (
                <label
                    style={styles.forceRow}
                    title="Regenerates every stage from scratch, ignoring existing output — including stages that already finished"
                >
                    <input
                        type="checkbox"
                        checked={forceRerun}
                        onChange={(e) => setForceRerun(e.target.checked)}
                    />
                    Force regenerate all stages
                </label>
            )}

            {error && <div style={styles.error}>{error}</div>}

            {logVisible && log && (
                <div style={styles.logSection}>
                    <span style={styles.logHeader}>Output</span>
                    <pre style={styles.logPanel} ref={logRef}>
                        {log}
                    </pre>
                </div>
            )}
        </div>
    );
}

function dotStyleFor(state: PhaseState): React.CSSProperties {
    if (state === "done") return { background: colors.success, borderColor: colors.success };
    if (state === "in-progress") return { background: colors.warning, borderColor: colors.warning };
    return { background: "transparent", borderColor: colors.borderStrong };
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 10,
        padding: "12px 14px",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.lg,
    },
    phases: {
        display: "flex",
        alignItems: "center",
        gap: 18,
        flexWrap: "wrap",
    },
    phase: {
        display: "flex",
        alignItems: "center",
        gap: 6,
    },
    dot: {
        width: 10,
        height: 10,
        borderRadius: "50%",
        border: "2px solid",
        flexShrink: 0,
    },
    phaseLabel: {
        fontSize: typography.size.md,
        color: colors.textPrimary,
    },
    actions: {
        display: "flex",
        alignItems: "center",
        gap: 10,
    },
    runningLabel: {
        fontSize: typography.size.md,
        color: colors.textSecondary,
    },
    forceRow: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: typography.size.md,
        color: colors.textSecondary,
    },
    error: {
        fontSize: typography.size.md,
        color: colors.error,
    },
    logSection: {
        display: "flex",
        flexDirection: "column",
        gap: 6,
    },
    logHeader: {
        fontSize: typography.size.md,
        color: colors.textSecondary,
    },
    logPanel: {
        maxHeight: 240,
        overflowY: "auto",
        background: colors.background,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        padding: 10,
        fontSize: typography.size.sm,
        fontFamily: "monospace",
        color: colors.codeText,
        whiteSpace: "pre-wrap",
        margin: 0,
    },
};
