import { useRef, useState } from "react";
import { getEpisodeStatus, runOverWebSocket, type EpisodeStageStatus, type EpisodeStatus, type RunHandle, type RunMessage } from "./api";
import { colors, radius, typography } from "./tokens";

// The full 15-stage + 2-secondary-stage list, individual Run/Re-run,
// force/skip-captions, and render controls — everything ui/static/app.js's
// control panel exposed as the PRIMARY interaction. Here it's the same
// capability, collapsed behind an explicit "Advanced" toggle instead of
// being the first thing the user sees (see #26 — the collapsed
// ProgressFlow above this is now the default surface).
interface Props {
    episodePath: string;
    status: EpisodeStatus | null;
    onStatusChange: (status: EpisodeStatus) => void;
    includeCaptions: boolean;
    onIncludeCaptionsChange: (value: boolean) => void;
}

export function AdvancedPanel({
    episodePath,
    status,
    onStatusChange,
    includeCaptions,
    onIncludeCaptionsChange,
}: Props) {
    const [expanded, setExpanded] = useState(false);
    const [runningId, setRunningId] = useState<string | null>(null);
    const [log, setLog] = useState("");
    const [logVisible, setLogVisible] = useState(false);
    const [renderFormat, setRenderFormat] = useState<"video" | "davinci">("video");
    const [renderResolution, setRenderResolution] = useState("");
    const runHandleRef = useRef<RunHandle | null>(null);

    const refreshStatus = () => {
        getEpisodeStatus(episodePath).then(onStatusChange);
    };

    const startRun = (wsPath: string, params: Record<string, unknown>, id: string) => {
        if (runningId) return;

        setRunningId(id);
        setLog("");
        setLogVisible(true);

        runHandleRef.current = runOverWebSocket(wsPath, params, (msg: RunMessage) => {
            if (msg.type === "start") {
                setLog((prev) => prev + `$ ${msg.command}\n`);
            } else if (msg.type === "log") {
                setLog((prev) => prev + msg.line + "\n");
            } else if (msg.type === "error") {
                setLog((prev) => prev + `\nERROR: ${msg.message}\n`);
                setRunningId(null);
            } else if (msg.type === "done") {
                setLog((prev) => prev + `\n(exit code ${msg.exitCode})\n`);
                setRunningId(null);
                refreshStatus();
            } else if (msg.type === "cancelled") {
                setLog((prev) => prev + `\nCancelled.\n`);
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

    if (!expanded) {
        return (
            <button className="secondary" onClick={() => setExpanded(true)} style={styles.toggle}>
                Advanced ▸
            </button>
        );
    }

    return (
        <div style={styles.wrap}>
            <button className="secondary" onClick={() => setExpanded(false)} style={styles.toggle}>
                Advanced ▾
            </button>

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
                        <span>Output</span>
                        {runningId && (
                            <button className="secondary" onClick={cancelRun} style={styles.cancelBtn}>
                                Cancel
                            </button>
                        )}
                    </div>
                    <pre style={styles.logPanel}>{log}</pre>
                </div>
            )}
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
    toggle: {
        alignSelf: "flex-start",
        fontSize: typography.size.md,
    },
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 10,
        padding: "12px 14px",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.lg,
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
