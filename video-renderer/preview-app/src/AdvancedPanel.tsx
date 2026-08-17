import { useRef, useState } from "react";
import { getEpisodeStatus, runOverWebSocket, type EpisodeStageStatus, type EpisodeStatus, type RunHandle, type RunMessage } from "./api";
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
    const [renderFormat, setRenderFormat] = useState<"video" | "davinci">("video");
    const [renderResolution, setRenderResolution] = useState("");
    const runHandleRef = useRef<RunHandle | null>(null);

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
        if (runningId) return;

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

    const runStage = (stageId: string) => startRun("/ws/stage/run", { path: episodePath, stage: stageId }, stageId);

    const runRender = () => {
        const params: Record<string, unknown> = { path: episodePath, format: renderFormat };
        if (renderResolution) params.resolution = renderResolution;
        startRun("/ws/render/run", params, "__render__");
    };

    if (!isActive) return null;

    return (
        <div style={styles.wrap}>
            <label style={styles.captionsRow}>
                <input
                    type="checkbox"
                    checked={includeCaptions}
                    onChange={(e) => onIncludeCaptionsChange(e.target.checked)}
                    disabled={!!runningId}
                />
                Include captions on next full pipeline run (leave unticked to remove any already generated)
            </label>

            <div style={styles.renderOptions}>
                <label style={styles.optionLabel}>
                    Output format
                    <select
                        value={renderFormat}
                        onChange={(e) => setRenderFormat(e.target.value as "video" | "davinci")}
                        disabled={!!runningId}
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
                        disabled={!!runningId}
                    >
                        <option value="">Default (from config.json)</option>
                        <option value="1920x1080">1920x1080</option>
                        <option value="3840x2160">3840x2160</option>
                    </select>
                </label>
                <button className="secondary" onClick={runRender} disabled={!!runningId}>
                    Render
                </button>
                <button className="secondary" onClick={() => runStage("qa_check")} disabled={!!runningId}>
                    QA check
                </button>
            </div>

            <div style={styles.stageList}>
                {status?.stages.map((stage) => (
                    <StageRow key={stage.id} stage={stage} running={runningId === stage.id} disabled={!!runningId} onRun={() => runStage(stage.id)} />
                ))}
                {status?.secondary.map((stage) => (
                    <StageRow key={stage.id} stage={stage} running={runningId === stage.id} disabled={!!runningId} onRun={() => runStage(stage.id)} />
                ))}
            </div>

            {logVisible && (
                <div style={styles.logSection}>
                    <div style={styles.logHeader}>
                        <span>{progressTotal !== null ? "Rendering" : "Output"}</span>
                        {runningId && (
                            <button className="secondary" onClick={cancelRun} style={styles.cancelBtn}>
                                Cancel
                            </button>
                        )}
                    </div>

                    {progressTotal !== null && (
                        <ProgressBar current={progressCurrent} total={progressTotal} />
                    )}

                    <button className="secondary" onClick={() => setLogExpanded((v) => !v)} style={styles.logToggle}>
                        {logExpanded ? "Hide details" : "Show details"}
                    </button>

                    {logExpanded && <pre style={styles.logPanel}>{logLines.join("\n")}</pre>}
                </div>
            )}
        </div>
    );
}

function ProgressBar({ current, total }: { current: number; total: number }) {
    const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
    const done = total > 0 && current >= total;

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
                {current} of {total} clips{done ? " — done" : ""}
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
