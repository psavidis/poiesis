import { useEffect, useRef, useState } from "react";
import { cancelRender, getEpisodeStatus, getRenderStatus, runOverWebSocket, type EpisodeStageStatus, type EpisodeStatus, type RunHandle, type RunMessage } from "./api";
import { colors, radius, typography } from "./tokens";

// The full 15-stage + 2-secondary-stage list, individual Run/Re-run,
// force/skip-captions, and render controls — everything ui/static/app.js's
// control panel exposed as the PRIMARY interaction. Here it's the same
// capability, one tab in EpisodeWorkspace's shared tab strip (#70) instead
// of the first thing the user sees (see #26 — the collapsed ProgressFlow
// above the strip is the default surface).
interface Props {
    episodePath: string;
    status: EpisodeStatus | null;
    onStatusChange: (status: EpisodeStatus) => void;
    includeCaptions: boolean;
    onIncludeCaptionsChange: (value: boolean) => void;
    isActive: boolean;
}

export function AdvancedPanel({
    episodePath,
    status,
    onStatusChange,
    includeCaptions,
    onIncludeCaptionsChange,
    isActive,
}: Props) {
    // Raw output is capped to its last MAX_LOG_LINES lines (an array, not
    // one ever-growing concatenated string) so a long DaVinci export's
    // per-clip Remotion CLI chatter — hundreds of short-lived websocket
    // "log" messages — can't force an unbounded string copy + full-panel
    // re-render on every single line (the previous `log` string state did
    // exactly that; see #65's sibling render-console request). A real
    // progress bar (from the "total"/"progress" messages export_davinci.py
    // now emits) is the primary UI during a run; the capped log stays
    // available underneath, collapsed, for debugging a failure.
    const MAX_LOG_LINES = 200;

    const [runningId, setRunningId] = useState<string | null>(null);
    const [logLines, setLogLines] = useState<string[]>([]);
    const [logVisible, setLogVisible] = useState(false);
    const [logExpanded, setLogExpanded] = useState(false);
    const [progressTotal, setProgressTotal] = useState<number | null>(null);
    const [progressCurrent, setProgressCurrent] = useState(0);
    // True when the progress bar is showing state RECOVERED via
    // getRenderStatus (e.g. after a page refresh mid-render) rather than
    // live over this component's own websocket — Cancel isn't offered in
    // that case (there's no RunHandle for a run this tab didn't start;
    // see runHandleRef below) and no further live updates will arrive
    // until the render finishes (checked by re-polling, not a
    // reconnected stream — see the recovery effect below).
    const [recoveredRender, setRecoveredRender] = useState(false);
    const [recoveredFormat, setRecoveredFormat] = useState<"video" | "davinci" | null>(null);
    const [recoveredResolution, setRecoveredResolution] = useState<string | null>(null);
    const [cancellingRecovered, setCancellingRecovered] = useState(false);
    const [renderFormat, setRenderFormat] = useState<"video" | "davinci">("video");
    const [renderResolution, setRenderResolution] = useState("");
    const runHandleRef = useRef<RunHandle | null>(null);
    // Mirrors runningId for the recovery-poll effect below, which only
    // depends on [episodePath] and therefore closes over whatever
    // runningId was at mount time — a ref always reads the CURRENT value
    // instead, so the poll can tell "this tab already has its own live
    // websocket run going" apart from "nothing is happening here, but the
    // lock says something's running elsewhere" on every tick, not just
    // the first one.
    const runningIdRef = useRef<string | null>(null);

    useEffect(() => {
        runningIdRef.current = runningId;
    }, [runningId]);

    // On mount (and whenever the episode changes), check whether a render
    // is already in flight for THIS episode — e.g. this tab was refreshed,
    // or a render was started from a different tab — and if so, recover
    // its last-known progress instead of showing a blank Render button
    // with no indication anything is happening (#65's sibling
    // render-progress-recovery request). Polls every few seconds while a
    // recovered render is showing, since there's no live stream to push
    // updates — stops polling once the render is no longer running.
    useEffect(() => {
        let cancelled = false;
        let pollTimer: ReturnType<typeof setTimeout> | null = null;

        const poll = () => {
            // Skip entirely while THIS tab has its own live websocket run
            // going (runningId set via startRun) — otherwise this poll
            // would see the lock as held (correctly — the live run holds
            // it) and mark the live run as "recovered," hiding its actual
            // log/Cancel behind the recovered-run UI branch. Still
            // reschedules so polling resumes as soon as the live run ends.
            if (runningIdRef.current) {
                pollTimer = setTimeout(poll, 4000);
                return;
            }

            getRenderStatus(episodePath)
                .then((status) => {
                    if (cancelled) return;

                    if (!status.running) {
                        // Only clear the recovered-run UI if it was actually
                        // showing one — avoids clobbering unrelated state on
                        // every idle tick (the common case).
                        setRecoveredRender((wasRecovered) => {
                            if (wasRecovered) {
                                setLogVisible(false);
                                setProgressTotal(null);
                                setProgressCurrent(0);
                                setRecoveredFormat(null);
                                setRecoveredResolution(null);
                            }
                            return false;
                        });

                        // Keep polling (at the slower "idle" cadence) so a
                        // render started LATER — from this tab or another —
                        // is still picked up without needing another
                        // refresh.
                        pollTimer = setTimeout(poll, 4000);
                        return;
                    }

                    setRecoveredRender(true);
                    setLogVisible(true);
                    setProgressCurrent(status.current ?? 0);
                    setProgressTotal(status.total);
                    setRecoveredFormat(status.format);
                    setRecoveredResolution(status.resolution);

                    pollTimer = setTimeout(poll, 4000);
                })
                .catch(() => {
                    // Episode not resolvable yet, or the request raced a
                    // navigation — not worth surfacing as an error for a
                    // background recovery check. Keep the poll loop alive.
                    pollTimer = setTimeout(poll, 4000);
                });
        };

        poll();

        return () => {
            cancelled = true;
            if (pollTimer) clearTimeout(pollTimer);
        };
    }, [episodePath]);

    const appendLog = (line: string) => {
        setLogLines((prev) => {
            const next = prev.length >= MAX_LOG_LINES ? prev.slice(prev.length - MAX_LOG_LINES + 1) : prev.slice();
            next.push(line);
            return next;
        });
    };

    const refreshStatus = () => {
        getEpisodeStatus(episodePath).then(onStatusChange);
    };

    const startRun = (wsPath: string, params: Record<string, unknown>, id: string) => {
        if (runningId || recoveredRender) return;

        setRunningId(id);
        setLogLines([]);
        setLogVisible(true);
        setLogExpanded(false);
        setProgressTotal(null);
        setProgressCurrent(0);

        runHandleRef.current = runOverWebSocket(wsPath, params, (msg: RunMessage) => {
            if (msg.type === "start") {
                appendLog(`$ ${msg.command}`);
            } else if (msg.type === "total") {
                setProgressTotal(msg.count);
            } else if (msg.type === "progress") {
                setProgressCurrent(msg.current);
                setProgressTotal(msg.total);
            } else if (msg.type === "log") {
                appendLog(msg.line);
            } else if (msg.type === "error") {
                appendLog(`ERROR: ${msg.message}`);
                setRunningId(null);
            } else if (msg.type === "done") {
                appendLog(`(exit code ${msg.exitCode})`);
                setRunningId(null);
                refreshStatus();
            } else if (msg.type === "cancelled") {
                appendLog("Cancelled.");
                setRunningId(null);
                refreshStatus();
            }
        });
    };

    const cancelRun = () => runHandleRef.current?.cancel();

    // A recovered run (see the recovery effect above) has no RunHandle —
    // this tab never opened the websocket that started it, so there's
    // nothing for cancelRun's runHandleRef to call. Cancels the actual
    // subprocess server-side instead, via the episode path alone (see
    // ui/server.py's render_cancel / _render_handles).
    const cancelRecoveredRun = () => {
        if (cancellingRecovered) return;
        setCancellingRecovered(true);
        cancelRender(episodePath)
            .catch(() => {
                // A 404 here just means the render finished on its own
                // between the click and this request landing — not worth
                // surfacing as an error; the next poll tick will notice
                // recoveredRender is no longer true and clear this state.
            })
            .finally(() => setCancellingRecovered(false));
    };

    const runStage = (stageId: string) => startRun("/ws/stage/run", { path: episodePath, stage: stageId }, stageId);

    const runRender = () => {
        const params: Record<string, unknown> = { path: episodePath, format: renderFormat };
        if (renderResolution) params.resolution = renderResolution;
        startRun("/ws/render/run", params, "__render__");
    };

    // Covers both "this tab started a live run" and "a run recovered from
    // getRenderStatus is still going, started by some OTHER tab/session" —
    // either way, the controls should be locked out the same way, even
    // though only the first case has a RunHandle to Cancel.
    const busy = !!runningId || recoveredRender;

    if (!isActive) return null;

    return (
        <div style={styles.wrap}>
            <label style={styles.captionsRow}>
                <input
                    type="checkbox"
                    checked={includeCaptions}
                    onChange={(e) => onIncludeCaptionsChange(e.target.checked)}
                    disabled={busy}
                />
                Include captions on next full pipeline run (leave unticked to remove any already generated)
            </label>

            <div style={styles.renderOptions}>
                <label style={styles.optionLabel}>
                    Output format
                    <select
                        value={renderFormat}
                        onChange={(e) => setRenderFormat(e.target.value as "video" | "davinci")}
                        disabled={busy}
                    >
                        <option value="video">Video (MP4)</option>
                        <option value="davinci">DaVinci Resolve project (OTIO timeline)</option>
                    </select>
                </label>
                <label style={styles.optionLabel}>
                    Resolution
                    <select
                        value={renderResolution}
                        onChange={(e) => setRenderResolution(e.target.value)}
                        disabled={busy}
                    >
                        <option value="">Default (from config.json)</option>
                        <option value="1920x1080">1920x1080</option>
                        <option value="3840x2160">3840x2160</option>
                    </select>
                </label>
                <button className="secondary" onClick={runRender} disabled={busy}>
                    Render
                </button>
                <button className="secondary" onClick={() => runStage("qa_check")} disabled={busy}>
                    QA check
                </button>
            </div>

            <div style={styles.stageList}>
                {status?.stages.map((stage) => (
                    <StageRow key={stage.id} stage={stage} running={runningId === stage.id} disabled={busy} onRun={() => runStage(stage.id)} />
                ))}
                {status?.secondary.map((stage) => (
                    <StageRow key={stage.id} stage={stage} running={runningId === stage.id} disabled={busy} onRun={() => runStage(stage.id)} />
                ))}
            </div>

            {(logVisible || recoveredRender) && (
                <div style={styles.logSection}>
                    <div style={styles.logHeader}>
                        <span>
                            {recoveredRender || progressTotal !== null ? "Rendering" : "Output"}
                            {recoveredRender && (recoveredFormat || recoveredResolution) && (
                                <span style={styles.runDescription}>
                                    {" — "}
                                    {recoveredFormat === "davinci" ? "DaVinci Resolve project" : recoveredFormat === "video" ? "Video (MP4)" : ""}
                                    {recoveredResolution ? ` (${recoveredResolution})` : ""}
                                </span>
                            )}
                        </span>
                        {runningId && (
                            <button className="secondary" onClick={cancelRun} style={styles.cancelBtn}>
                                Cancel
                            </button>
                        )}
                        {recoveredRender && (
                            <button
                                className="secondary"
                                onClick={cancelRecoveredRun}
                                disabled={cancellingRecovered}
                                style={styles.cancelBtn}
                            >
                                {cancellingRecovered ? "Cancelling…" : "Cancel"}
                            </button>
                        )}
                    </div>

                    {recoveredRender ? (
                        progressTotal !== null ? (
                            <ProgressBar current={progressCurrent} total={progressTotal} format={recoveredFormat} />
                        ) : (
                            <span style={styles.progressLabel}>
                                A render is already running for this episode (started elsewhere) — waiting for progress...
                            </span>
                        )
                    ) : (
                        progressTotal !== null && <ProgressBar current={progressCurrent} total={progressTotal} format={renderFormat} />
                    )}

                    {recoveredRender && (
                        <span style={styles.progressLabel}>
                            Reconnected after a refresh — live output isn't available for a run this tab didn't start, but Cancel still works.
                        </span>
                    )}

                    {!recoveredRender && (
                        <button className="secondary" onClick={() => setLogExpanded((v) => !v)} style={styles.logToggle}>
                            {logExpanded ? "Hide details" : "Show details"}
                        </button>
                    )}

                    {!recoveredRender && logExpanded && <pre style={styles.logPanel}>{logLines.join("\n")}</pre>}
                </div>
            )}
        </div>
    );
}

function ProgressBar({ current, total, format }: { current: number; total: number; format: "video" | "davinci" | null }) {
    const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
    const done = total > 0 && current >= total;
    // DaVinci exports report progress per rendered CLIP (one file per
    // scene — see export_davinci.py's __PROGRESS__); the plain MP4 path
    // reports per FRAME (render-with-progress.js's renderedFrames) — a
    // single "clips" label was wrong (and confusing at a 5-figure total)
    // for the frame-based case. Defaults to "clip" when format is
    // unknown (e.g. briefly, before render-status's first response) —
    // matches the original, DaVinci-only behavior this bar was written
    // for, so an unresolved format doesn't flip the label to something
    // new by default.
    const unit = format === "video" ? "frame" : "clip";

    return (
        <div style={styles.progressWrap}>
            <div style={styles.progressTrack}>
                <div
                    style={{
                        ...styles.progressFill,
                        width: `${pct}%`,
                        background: done ? colors.success : colors.accent,
                    }}
                />
            </div>
            <span style={styles.progressLabel}>
                {current} of {total} {unit}
                {total === 1 ? "" : "s"}
                {done ? " — done" : ""}
            </span>
        </div>
    );
}

function StageRow({
    stage,
    running,
    disabled,
    onRun,
}: {
    stage: EpisodeStageStatus;
    running: boolean;
    disabled: boolean;
    onRun: () => void;
}) {
    return (
        <div style={styles.stageRow}>
            <span
                style={{
                    ...styles.stageDot,
                    background: running ? colors.warning : stage.complete ? colors.success : "transparent",
                    borderColor: running ? colors.warning : stage.complete ? colors.success : colors.borderStrong,
                }}
            />
            <span style={styles.stageLabel}>{stage.label}</span>
            <button className="secondary small" onClick={onRun} disabled={disabled}>
                {stage.complete ? "Re-run" : "Run"}
            </button>
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 10,
    },
    captionsRow: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: typography.size.md,
        color: colors.textSecondary,
    },
    renderOptions: {
        display: "flex",
        alignItems: "center",
        gap: 14,
        flexWrap: "wrap",
        fontSize: typography.size.md,
        color: colors.textSecondary,
    },
    optionLabel: {
        display: "flex",
        flexDirection: "column",
        gap: 4,
    },
    stageList: {
        display: "flex",
        flexDirection: "column",
        gap: 2,
    },
    stageRow: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "4px 0",
    },
    stageDot: {
        width: 8,
        height: 8,
        borderRadius: "50%",
        border: "2px solid",
        flexShrink: 0,
    },
    stageLabel: {
        flex: 1,
        fontSize: typography.size.md,
        color: colors.textPrimary,
    },
    logSection: {
        display: "flex",
        flexDirection: "column",
        gap: 6,
    },
    logHeader: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: typography.size.md,
        color: colors.textSecondary,
    },
    cancelBtn: {
        fontSize: typography.size.sm,
    },
    runDescription: {
        color: colors.textSecondary,
        fontWeight: "normal" as const,
    },
    progressWrap: {
        display: "flex",
        flexDirection: "column",
        gap: 4,
    },
    progressTrack: {
        height: 8,
        borderRadius: radius.md,
        background: colors.background,
        border: `1px solid ${colors.border}`,
        overflow: "hidden",
    },
    progressFill: {
        height: "100%",
        borderRadius: radius.md,
        transition: "width 0.2s ease",
    },
    progressLabel: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        fontVariantNumeric: "tabular-nums",
    },
    logToggle: {
        alignSelf: "flex-start",
        fontSize: typography.size.sm,
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
