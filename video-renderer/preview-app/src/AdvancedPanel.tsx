import { useEffect, useState } from "react";
import { getEpisodeStatus, runOverWebSocket, type EpisodeStageStatus, type EpisodeStatus, type RunHandle, type RunMessage } from "./api";
import { colors, radius, typography } from "./tokens";

// The full 15-stage + 2-secondary-stage list with individual Run/Re-run —
// everything ui/static/app.js's control panel exposed as the PRIMARY
// interaction, minus export (Render/QA check/output format/resolution/
// captions), which moved to its own ExportPanel (#83) — export is a
// distinct concern from running the pipeline itself, not just a different
// section of the same screen. One tab in EpisodeWorkspace's shared tab
// strip (#70), not the first thing the user sees (see #26 — the collapsed
// ProgressFlow above the strip is the default surface).
interface Props {
    episodePath: string;
    status: EpisodeStatus | null;
    onStatusChange: (status: EpisodeStatus) => void;
    isActive: boolean;
}

export function AdvancedPanel({ episodePath, status, onStatusChange, isActive }: Props) {
    // Raw output is capped to its last MAX_LOG_LINES lines (an array, not
    // one ever-growing concatenated string) so a long stage's chatter
    // can't force an unbounded string copy + full-panel re-render on
    // every single line (see #65's sibling render-console request). The
    // capped log stays available underneath, collapsed, for debugging a
    // failure.
    const MAX_LOG_LINES = 200;

    const [runningId, setRunningId] = useState<string | null>(null);
    const [logLines, setLogLines] = useState<string[]>([]);
    const [logVisible, setLogVisible] = useState(false);
    const [logExpanded, setLogExpanded] = useState(false);
    // Copy-to-clipboard feedback for the Output panel (#84) — true right
    // after a successful copy, showing a checkmark/"Copied" in place of
    // the copy icon; reset back to copyable the moment logLines changes
    // again (see the effect below), so a stale "Copied" never lingers
    // once the actual content it referred to is no longer what's on
    // screen — matters most for a still-running stage, whose output keeps
    // growing line by line.
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        setCopied(false);
    }, [logLines]);

    const appendLog = (line: string) => {
        setLogLines((prev) => {
            const next = prev.length >= MAX_LOG_LINES ? prev.slice(prev.length - MAX_LOG_LINES + 1) : prev.slice();
            next.push(line);
            return next;
        });
    };

    const copyLogToClipboard = async () => {
        try {
            await navigator.clipboard.writeText(logLines.join("\n"));
            setCopied(true);
        } catch {
            // Clipboard permission denied, insecure context, etc. — the
            // button stays in its normal copyable state rather than
            // falsely claiming success; nothing else to surface here for
            // what's a low-stakes convenience action.
        }
    };

    const refreshStatus = () => {
        getEpisodeStatus(episodePath).then(onStatusChange);
    };

    let runHandle: RunHandle | null = null;

    // force defaults to true (#81): once a stage has already produced its
    // artifact, clicking its button — labeled "Re-run" precisely because
    // stage.complete is true (see StageRow below) — must actually rerun
    // it. Without force, every pipeline stage script exits early on its
    // own "already proposed/indexed, skipping" check (e.g.
    // generate_title_scenes.py's own `if output_file.exists() and not
    // args.force`), so the click looked like it worked (a log line
    // appeared, exit code 0) but silently did nothing. A "Run" click on a
    // stage that has never completed has no existing output to skip in
    // the first place, so passing force there is a no-op — always
    // defaulting it true keeps this one code path correct for both
    // labels instead of needing the caller to track which is which.
    const runStage = (stageId: string) => {
        if (runningId) return;

        setRunningId(stageId);
        setLogLines([]);
        setLogVisible(true);
        setLogExpanded(false);

        runHandle = runOverWebSocket(
            "/ws/stage/run",
            { path: episodePath, stage: stageId, force: true },
            (msg: RunMessage) => {
                if (msg.type === "start") {
                    appendLog(`$ ${msg.command}`);
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
            }
        );
    };

    const cancelRun = () => runHandle?.cancel();

    if (!isActive) return null;

    return (
        <div style={styles.wrap}>
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

                    <button className="secondary" onClick={() => setLogExpanded((v) => !v)} style={styles.logToggle}>
                        {logExpanded ? "Hide details" : "Show details"}
                    </button>

                    {logExpanded && (
                        <div style={styles.logPanelWrap}>
                            <button
                                type="button"
                                className="secondary small"
                                style={styles.copyLogButton}
                                onClick={copyLogToClipboard}
                                disabled={logLines.length === 0}
                                title="Copy output to clipboard"
                                aria-label="Copy output to clipboard"
                            >
                                {copied ? "✓ Copied" : "Copy"}
                            </button>
                            <pre style={styles.logPanel}>{logLines.join("\n")}</pre>
                        </div>
                    )}
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
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 10,
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
    // and needs to stay a pure text container.
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
