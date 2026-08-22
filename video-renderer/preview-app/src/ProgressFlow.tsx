import { useEffect, useRef, useState } from "react";
import { cancelRender, getEpisodeStatus, getRenderStatus, runOverWebSocket, type EpisodeStatus, type RunHandle, type RunMessage } from "./api";
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
    // #88: explicit opt-in, same reasoning as forceRerun above — skips
    // every AI-calling stage (see pipeline/run_pipeline.py's own --no-ai
    // help text). Defaults off so AI proposals stay the normal default
    // behavior; the user ticks this only when AI is genuinely unavailable
    // or unwanted for this run.
    const [noAi, setNoAi] = useState(false);
    // Mirrors AdvancedPanel's own copy-to-clipboard button (#84) — that
    // ticket asked for a copy option "anywhere there is a console on the
    // UI," and this pipeline-run console (running or finished) was the one
    // place still missing it, unlike the QA-check console it first shipped
    // on.
    const [copied, setCopied] = useState(false);
    // True when "running" reflects a pipeline run RECOVERED via
    // getRenderStatus (e.g. after a page refresh mid-run, or a run
    // started from a different tab) rather than this component's own live
    // websocket (#85) — mirrors AdvancedPanel's identical recoveredRender
    // state for the render case. No RunHandle exists for a run this tab
    // didn't start, so Cancel goes through cancelRender (despite the name,
    // works for any run kind — see ui/server.py's render_cancel) instead
    // of runHandleRef.
    const [recovered, setRecovered] = useState(false);
    const [cancellingRecovered, setCancellingRecovered] = useState(false);
    const runHandleRef = useRef<RunHandle | null>(null);
    const logRef = useRef<HTMLPreElement>(null);
    // Mirrors `running` for the recovery-poll effect below, which only
    // depends on [episodePath] and therefore closes over whatever
    // `running` was at mount time — a ref always reads the CURRENT value,
    // so the poll can tell "this tab already has its own live run going"
    // apart from "nothing here, but something's running elsewhere" on
    // every tick, not just the first (same reasoning as AdvancedPanel's
    // own runningIdRef).
    const runningRef = useRef(false);

    useEffect(() => {
        runningRef.current = running;
    }, [running]);

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

    // #134: recovers a FINISHED pipeline run's console output once on
    // mount/episode change — distinct from the recovery-poll effect below,
    // which only surfaces state (banner, Cancel) for a run that's still
    // actually live elsewhere. A run that already finished has no "running"
    // signal to poll for, but its log is still sitting in _run_log server-
    // side (see ui/server.py) and is otherwise lost the moment this
    // component mounts fresh with an empty `log` state.
    useEffect(() => {
        setLog("");
        getRenderStatus(episodePath)
            .then((s) => {
                if (s.kind === "pipeline" && s.log.length > 0) {
                    setLog(s.log.join("\n") + "\n");
                    setLogVisible(true);
                }
            })
            .catch(() => {
                // No prior run for this episode this server process, or the
                // request failed — nothing to recover either way.
            });
    }, [episodePath]);

    useEffect(() => {
        if (!running) return;
        const interval = setInterval(refreshStatus, POLL_INTERVAL_MS);
        return () => clearInterval(interval);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [running]);

    // On mount (and whenever the episode changes), check whether A
    // PIPELINE run is already in flight for THIS episode — this tab was
    // refreshed mid-run, or a run was started from a different tab — and
    // if so, recover the "Processing…"/Cancel UI instead of showing a
    // blank Start/Re-run button with no indication anything is happening
    // (#85). Mirrors AdvancedPanel's identical render-recovery effect;
    // "kind" distinguishes a recovered PIPELINE run from a recovered
    // RENDER or single-STAGE run, which this component has no UI for and
    // must leave alone (episode_lock still protects the files regardless
    // — this is purely about what this panel shows). Only "pipeline" (the
    // full "Re-run pipeline"/Start button this component owns) is
    // recovered here; a single-stage run started from AdvancedPanel has
    // no equivalent surface in this component and is intentionally left
    // to show nothing more than the (still-accurate) phase dots.
    useEffect(() => {
        let cancelled = false;
        let pollTimer: ReturnType<typeof setTimeout> | null = null;

        const poll = () => {
            if (runningRef.current) {
                pollTimer = setTimeout(poll, 4000);
                return;
            }

            getRenderStatus(episodePath)
                .then((s) => {
                    if (cancelled) return;

                    // #134: a FINISHED run still has a kind/log worth
                    // showing (recovered's whole point), but "running"
                    // false means there's no live process to recover a
                    // Cancel button for — only surface the recovered
                    // banner/log while a run for THIS episode is still
                    // actually in flight elsewhere. A finished run's log
                    // is instead picked up once, below, independent of
                    // this polling loop.
                    if (!s.running || s.kind !== "pipeline") {
                        setRecovered((wasRecovered) => {
                            if (wasRecovered) {
                                setLogVisible(false);
                            }
                            return false;
                        });
                        pollTimer = setTimeout(poll, 4000);
                        return;
                    }

                    setRecovered(true);
                    setLogVisible(true);
                    if (s.log.length > 0) setLog(s.log.join("\n") + "\n");
                    pollTimer = setTimeout(poll, 4000);
                })
                .catch(() => {
                    pollTimer = setTimeout(poll, 4000);
                });
        };

        poll();

        return () => {
            cancelled = true;
            if (pollTimer) clearTimeout(pollTimer);
        };
    }, [episodePath]);

    useEffect(() => {
        if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    }, [log]);

    // Reverts the copy button back to its copyable state as soon as the
    // output actually changes (#84's own requirement, same as
    // AdvancedPanel's identical effect) — a still-running pipeline appends
    // new lines every few moments, so "Copied" must not keep showing once
    // what's on screen is no longer what got copied.
    useEffect(() => {
        setCopied(false);
    }, [log]);

    const copyLogToClipboard = async () => {
        try {
            await navigator.clipboard.writeText(log);
            setCopied(true);
        } catch {
            // Clipboard permission denied, insecure context, etc. — the
            // button stays in its normal copyable state rather than
            // falsely claiming success; nothing else to surface here for
            // what's a low-stakes convenience action.
        }
    };

    // Same complete === null handling as phaseState below — a stage with
    // no artifact to check (generate_scene_plan_ts) must not permanently
    // block "Re-run pipeline" from ever being offered.
    const allDone = status ? status.stages.every((s) => s.complete !== false) : false;

    const start = () => {
        if (running || recovered) return;

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
            { path: episodePath, skipCaptions, force: forceRerun, noAi },
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

    // A recovered run (see the recovery effect above) has no RunHandle —
    // this tab never opened the websocket that started it, so there's
    // nothing for cancel's runHandleRef to call. Cancels the actual
    // subprocess server-side instead, via the episode path alone (see
    // ui/server.py's render_cancel — works for any run kind despite the
    // name).
    const cancelRecoveredRun = () => {
        if (cancellingRecovered) return;
        setCancellingRecovered(true);
        cancelRender(episodePath)
            .catch(() => {
                // A 404 here just means the run finished on its own
                // between the click and this request landing — not worth
                // surfacing as an error; the next poll tick will notice
                // `recovered` is no longer true and clear this state.
            })
            .finally(() => setCancellingRecovered(false));
    };

    // Covers both "this tab started a live run" and "a run recovered from
    // getRenderStatus is still going, started by some OTHER tab/session" —
    // either way, Start/Re-run pipeline must be locked out the same way,
    // even though only the first case has a RunHandle to Cancel normally.
    const busy = running || recovered;

    return (
        <div style={styles.wrap}>
            <div style={styles.phases}>
                {PHASES.map((phase) => {
                    const state = phaseState(phase.stageIds, status);
                    // Only the phase actually running right now pulses —
                    // busy alone isn't enough, since Draft edit's dot
                    // shouldn't animate while Ingest is still going. Uses
                    // `busy` (not just `running`) so a RECOVERED run
                    // (#85) still shows live-feeling phase dots even
                    // though there's no websocket pushing updates for it.
                    const isActive = busy && state === "in-progress";
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
                {!busy && (
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
                {recovered && (
                    <>
                        <span className="processing-label" style={styles.runningLabel}>
                            Processing… (started elsewhere)
                        </span>
                        <button className="secondary" onClick={cancelRecoveredRun} disabled={cancellingRecovered}>
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

            {!busy && (
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

            {!busy && (
                <label
                    style={styles.forceRow}
                    title="Skips every stage that calls an LLM (analyze episode, propose title scenes/storyboard/moments/emphasis beats) — for when AI is unavailable or you'd rather not use it. Scene cuts, backgrounds, and captions are unaffected, and titles/moments/beats can still be added by hand in the editor afterward."
                >
                    <input type="checkbox" checked={noAi} onChange={(e) => setNoAi(e.target.checked)} />
                    Run without AI
                </label>
            )}

            {error && <div style={styles.error}>{error}</div>}

            {/* #134: recovered output is now populated from the server's
                own _run_log (see the recovery effects above), so this note
                only appears in the brief real edge case where a run was
                JUST recovered and hasn't produced any lines yet — not the
                general "recovered runs never have output" case this used
                to describe. The phase dots above still give real,
                artifact-backed progress either way. */}
            {recovered && !log && (
                <div style={styles.recoveredNote}>
                    Waiting for output from the run that's already in progress — the phase indicators above still
                    reflect real progress.
                </div>
            )}

            {logVisible && log && (
                <div style={styles.logSection}>
                    <span style={styles.logHeader}>Output</span>
                    <div style={styles.logPanelWrap}>
                        <button
                            type="button"
                            className="secondary small"
                            style={styles.copyLogButton}
                            onClick={copyLogToClipboard}
                            title="Copy output to clipboard"
                            aria-label="Copy output to clipboard"
                        >
                            {copied ? "✓ Copied" : "Copy"}
                        </button>
                        <pre style={styles.logPanel} ref={logRef}>
                            {log}
                        </pre>
                    </div>
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
    recoveredNote: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        fontStyle: "italic",
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
        // Room for copyLogButton (top-right, absolutely positioned) so it
        // never overlaps the first line of real output.
        paddingTop: 34,
        fontSize: typography.size.sm,
        fontFamily: "monospace",
        color: colors.codeText,
        whiteSpace: "pre-wrap",
        margin: 0,
    },
    // Anchors copyLogButton to logPanel's own top-right corner (#84's "a
    // copy option is displayed at the output area top-right corner") —
    // a plain wrapper div, not logPanel itself, since logPanel is a <pre>
    // and needs to stay a pure text container. Mirrors AdvancedPanel's
    // identical logPanelWrap/copyLogButton pair.
    logPanelWrap: {
        position: "relative",
    },
    copyLogButton: {
        position: "absolute",
        top: 6,
        right: 6,
        zIndex: 1,
    },
};
