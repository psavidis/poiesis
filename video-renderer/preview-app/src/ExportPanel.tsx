import { useEffect, useRef, useState } from "react";
import {
    cancelRender,
    getQaReport,
    getRenderStatus,
    getScenePlan,
    runOverWebSocket,
    type EpisodeStatus,
    type QaIssue,
    type QaReport,
    type RunHandle,
    type RunMessage,
} from "./api";
import { colors, radius, typography } from "./tokens";
import type { ScenePlan } from "video-renderer-src/episode/types";

// Plain-language translations of qa_check.py's internal `check` codes
// (pipeline/qa_check.py) — the report itself is written for a developer
// (sceneId, frame numbers, internal check names), but per CLAUDE.md the
// user isn't supposed to need to know what a "scene plan" or "moment
// window" is. Each entry is the sentence shown on the issue card; a code
// missing from this map falls back to its raw `detail` string so a new
// check added to qa_check.py degrades gracefully instead of disappearing.
const QA_ISSUE_MESSAGES: Record<string, string> = {
    missing_media: "Some footage this episode needs is missing from disk.",
    unknown_video_id: "A part of the edit points at footage that no longer exists.",
    unknown_asset_id: "A part of the edit points at an image or asset that no longer exists.",
    timeline_gap_or_overlap: "Two parts of the video aren't lined up correctly — there may be a gap or overlap.",
    overlay_outside_bounds: "A visual (text, diagram, etc.) is positioned outside the scene it belongs to.",
    moment_presenter_side_mismatch: "The presenter's on-screen position doesn't match the visual treatment for a moment.",
    moment_windows_overlap: "Two visual moments overlap on screen at the same time.",
    duration_mismatch: "The rendered video's length doesn't match what the edit expects.",
    audio_video_duration_mismatch: "The rendered video's audio and picture don't run for the same length of time.",
    missing_audio_stream: "The rendered video has no audio track at all.",
    black_frames: "The rendered video has a stretch of solid black — likely missing or broken footage.",
    silent_audio: "The rendered video has no audible sound.",
};

// Which stage produced the problem, so the card can point at what fixing
// it actually requires instead of leaving the user to guess. Checks not
// listed here operate purely on scene-plan.json/manifest.json (no
// suggestion needed beyond re-running the pipeline stage that built them).
const QA_ISSUE_SUGGESTS_RERENDER = new Set([
    "duration_mismatch",
    "audio_video_duration_mismatch",
    "missing_audio_stream",
    "black_frames",
    "silent_audio",
]);

function formatTimestamp(seconds: number): string {
    const total = Math.max(0, Math.round(seconds));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
}

// Resolves an issue's sceneId to a timeline timestamp via scene-plan.json,
// so "two parts of the video aren't lined up" becomes "around 0:17" —
// something the user can actually act on (scrub the preview there) instead
// of a scene id or frame number they have no way to interpret. Not every
// issue has a sceneId (e.g. missing_audio_stream is about the whole
// render), and the scene plan may not be loaded yet — both are normal,
// not errors, so this degrades to no timestamp rather than throwing.
// Mirrors pipeline/overlay_placement.py's absolute_position: a track scene
// (presenter/title/background/full-display image) carries
// timelineStartFrame directly; an overlay scene (moment/caption/beat/inset
// image) only carries a parent-relative offsetInParentFrames, resolved via
// its parentSceneId (one level of nesting — overlays don't nest further).
function absoluteStartFrame(scene: ScenePlan["scenes"][number], scenePlan: ScenePlan): number | null {
    if ("timelineStartFrame" in scene) return scene.timelineStartFrame;

    if ("parentSceneId" in scene && "offsetInParentFrames" in scene) {
        const parent = scenePlan.scenes.find((s) => s.id === scene.parentSceneId);
        if (!parent || !("timelineStartFrame" in parent)) return null;
        return parent.timelineStartFrame + scene.offsetInParentFrames;
    }

    return null;
}

function issueTimestampSeconds(issue: QaIssue, scenePlan: ScenePlan | null): number | null {
    if (!issue.sceneId || !scenePlan) return null;

    const scene = scenePlan.scenes.find((s) => s.id === issue.sceneId);
    if (!scene) return null;

    const startFrame = absoluteStartFrame(scene, scenePlan);
    return startFrame === null ? null : startFrame / scenePlan.fps;
}

function describeQaIssue(issue: QaIssue, scenePlan: ScenePlan | null): string {
    const message = QA_ISSUE_MESSAGES[issue.check] ?? issue.detail;
    const seconds = issueTimestampSeconds(issue, scenePlan);

    return seconds === null ? message : `${message} (around ${formatTimestamp(seconds)})`;
}

// #83: export (Render/QA check, plus the parameters that shape them —
// output format, resolution, and whether captions are included on the
// next full pipeline run) is a distinct concern from running the pipeline
// itself, and previously lived inline at the top of AdvancedPanel.tsx
// mixed in with the pipeline stage list. This panel owns exactly the five
// parameters the ticket calls out as belonging to Export: "Include
// captions on next full pipeline run", "Output format", "Resolution",
// "Render", "QA check". Deliberately independent React state from
// AdvancedPanel's own runningId/log — the two panels are separate UI
// surfaces now, coordinated only through the same server-side locks
// (episode_lock + machine_lock, #85) both already go through, the same
// way ProgressFlow and AdvancedPanel already coexist without sharing
// client-side run state.
interface Props {
    episodePath: string;
    status: EpisodeStatus | null;
    includeCaptions: boolean;
    onIncludeCaptionsChange: (value: boolean) => void;
    isActive: boolean;
}

// Export needs actual renderable material to act on — scene-plan.json
// (produced by the analyze_scenes stage) is what render-with-progress.js/
// export_davinci.py and qa_check.py all read (see ui/server.py's own
// edit_scene_plan endpoint: "scene-plan.json not found — run the pipeline
// first"). Earlier stages (prepare/transcribe/...) alone aren't enough —
// there's nothing to render yet without a scene plan.
const EXPORT_READY_STAGE_ID = "analyze_scenes";

function pipelineHasRun(status: EpisodeStatus | null): boolean {
    if (!status) return false;
    return status.stages.find((s) => s.id === EXPORT_READY_STAGE_ID)?.complete === true;
}

export function ExportPanel({ episodePath, status, includeCaptions, onIncludeCaptionsChange, isActive }: Props) {
    const MAX_LOG_LINES = 200;

    const [runningKind, setRunningKind] = useState<"render" | "qa_check" | null>(null);
    const [qaReport, setQaReport] = useState<QaReport | null>(null);
    const [qaReportError, setQaReportError] = useState(false);
    const [scenePlan, setScenePlan] = useState<ScenePlan | null>(null);
    const [logLines, setLogLines] = useState<string[]>([]);
    const [logVisible, setLogVisible] = useState(false);
    const [logExpanded, setLogExpanded] = useState(false);
    const [copied, setCopied] = useState(false);
    const [progressTotal, setProgressTotal] = useState<number | null>(null);
    const [progressCurrent, setProgressCurrent] = useState(0);
    // Mirrors AdvancedPanel's own recoveredRender (#85) — true when a
    // render is showing state RECOVERED via getRenderStatus (e.g. a page
    // refresh mid-render, or a render started from a different tab/panel)
    // rather than live over this panel's own websocket. QA check has no
    // equivalent recovery here: it emits no __TOTAL__/__PROGRESS__
    // sentinels and finishes quickly enough that recovering its exact
    // in-flight state isn't worth the same machinery — a recovered QA
    // check just shows as "Render disabled, something is running" via
    // `busy` below (machine_lock also blocks it either way).
    const [recoveredRender, setRecoveredRender] = useState(false);
    const [recoveredFormat, setRecoveredFormat] = useState<"video" | "davinci" | null>(null);
    const [recoveredResolution, setRecoveredResolution] = useState<string | null>(null);
    const [cancellingRecovered, setCancellingRecovered] = useState(false);
    const [renderFormat, setRenderFormat] = useState<"video" | "davinci">("video");
    const [renderResolution, setRenderResolution] = useState("");
    const runHandleRef = useRef<RunHandle | null>(null);
    const runningKindRef = useRef<"render" | "qa_check" | null>(null);

    useEffect(() => {
        runningKindRef.current = runningKind;
    }, [runningKind]);

    // Same recovery-poll pattern as AdvancedPanel's own render-recovery
    // effect (#85) — kept independent (not shared/lifted) since this is a
    // genuinely separate panel now.
    useEffect(() => {
        let cancelled = false;
        let pollTimer: ReturnType<typeof setTimeout> | null = null;

        const poll = () => {
            if (runningKindRef.current) {
                pollTimer = setTimeout(poll, 4000);
                return;
            }

            getRenderStatus(episodePath)
                .then((s) => {
                    if (cancelled) return;

                    if (!s.running || s.kind !== "render") {
                        setRecoveredRender((was) => {
                            if (was) {
                                setLogVisible(false);
                                setProgressTotal(null);
                                setProgressCurrent(0);
                                setRecoveredFormat(null);
                                setRecoveredResolution(null);
                            }
                            return false;
                        });
                        pollTimer = setTimeout(poll, 4000);
                        return;
                    }

                    setRecoveredRender(true);
                    setLogVisible(true);
                    setProgressCurrent(s.current ?? 0);
                    setProgressTotal(s.total);
                    setRecoveredFormat(s.format);
                    setRecoveredResolution(s.resolution);

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
        setCopied(false);
    }, [logLines]);

    // Show a QA report already on disk from an earlier run (e.g. before
    // this tab was opened), rather than only ever showing one produced by
    // a run started from this panel this session.
    useEffect(() => {
        setQaReport(null);
        setQaReportError(false);
        getQaReport(episodePath)
            .then(setQaReport)
            .catch(() => {
                // qa-report.json not produced yet — normal before QA check has ever run.
            });
    }, [episodePath]);

    // Loaded once per episode (not reset per QA run) purely to resolve an
    // issue's sceneId to a timestamp for display — scene-plan.json is
    // already required for Export to be usable at all (see ready/
    // pipelineHasRun below), so it's safe to assume present here too.
    useEffect(() => {
        setScenePlan(null);
        getScenePlan(episodePath)
            .then((data) => setScenePlan(data as ScenePlan))
            .catch(() => {
                // Not ready yet, or this episode's export isn't ready either — the
                // summary just shows issues without a timestamp in that case.
            });
    }, [episodePath]);

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
            // Clipboard permission denied, insecure context, etc. — stays
            // in its normal copyable state rather than falsely claiming
            // success.
        }
    };

    const startRun = (wsPath: string, params: Record<string, unknown>, kind: "render" | "qa_check") => {
        if (runningKind || recoveredRender) return;

        setRunningKind(kind);
        setLogLines([]);
        setLogVisible(true);
        setLogExpanded(false);
        setProgressTotal(null);
        setProgressCurrent(0);
        if (kind === "qa_check") {
            setQaReport(null);
            setQaReportError(false);
        }

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
                setRunningKind(null);
            } else if (msg.type === "done") {
                appendLog(`(exit code ${msg.exitCode})`);
                setRunningKind(null);
                // qa_check.py exits 1 whenever it found issues (that's a
                // successful check reporting a warning status, not a
                // crash) — always try to load the report it just wrote,
                // regardless of exit code.
                if (kind === "qa_check") {
                    getQaReport(episodePath)
                        .then(setQaReport)
                        .catch(() => setQaReportError(true));
                }
            } else if (msg.type === "cancelled") {
                appendLog("Cancelled.");
                setRunningKind(null);
            }
        });
    };

    const cancelRun = () => runHandleRef.current?.cancel();

    const cancelRecoveredRun = () => {
        if (cancellingRecovered) return;
        setCancellingRecovered(true);
        cancelRender(episodePath)
            .catch(() => {
                // A 404 here just means the render finished on its own
                // between the click and this request landing.
            })
            .finally(() => setCancellingRecovered(false));
    };

    const runRender = () => {
        const params: Record<string, unknown> = { path: episodePath, format: renderFormat };
        if (renderResolution) params.resolution = renderResolution;
        startRun("/ws/render/run", params, "render");
    };

    const runQaCheck = () =>
        startRun("/ws/stage/run", { path: episodePath, stage: "qa_check", force: true }, "qa_check");

    const busy = !!runningKind || recoveredRender;
    const ready = pipelineHasRun(status);

    if (!isActive) return null;

    return (
        <div style={styles.wrap}>
            {!ready && (
                <div style={styles.notReadyNote}>
                    Export becomes available once the pipeline has produced a scene plan — run the pipeline (or at
                    least "Analyze scenes") first.
                </div>
            )}

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
                        disabled={busy || !ready}
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
                        disabled={busy || !ready}
                    >
                        <option value="">Default (from config.json)</option>
                        <option value="1920x1080">1920x1080</option>
                        <option value="3840x2160">3840x2160</option>
                    </select>
                </label>
                <button className="secondary" onClick={runRender} disabled={busy || !ready}>
                    Render
                </button>
                <button className="secondary" onClick={runQaCheck} disabled={busy || !ready}>
                    QA check
                </button>
            </div>

            {runningKind === "qa_check" && <span style={styles.progressLabel}>Checking the episode…</span>}

            {runningKind !== "qa_check" && qaReport && <QaReportSummary report={qaReport} scenePlan={scenePlan} />}

            {runningKind !== "qa_check" && !qaReport && qaReportError && (
                <span style={styles.qaErrorNote}>Couldn't load the QA report — see details below.</span>
            )}

            {(logVisible || recoveredRender) && (
                <div style={styles.logSection}>
                    <div style={styles.logHeader}>
                        <span>
                            {recoveredRender || progressTotal !== null
                                ? "Rendering"
                                : runningKind === "qa_check"
                                  ? "QA check"
                                  : "Output"}
                            {recoveredRender && (recoveredFormat || recoveredResolution) && (
                                <span style={styles.runDescription}>
                                    {" — "}
                                    {recoveredFormat === "davinci"
                                        ? "DaVinci Resolve project"
                                        : recoveredFormat === "video"
                                          ? "Video (MP4)"
                                          : ""}
                                    {recoveredResolution ? ` (${recoveredResolution})` : ""}
                                </span>
                            )}
                        </span>
                        {runningKind && (
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
                                A render is already running for this episode (started elsewhere) — waiting for
                                progress...
                            </span>
                        )
                    ) : (
                        progressTotal !== null && (
                            <ProgressBar current={progressCurrent} total={progressTotal} format={renderFormat} />
                        )
                    )}

                    {recoveredRender && (
                        <span style={styles.progressLabel}>
                            Reconnected after a refresh — live output isn't available for a run this tab didn't
                            start, but Cancel still works.
                        </span>
                    )}

                    {!recoveredRender && (
                        <button className="secondary" onClick={() => setLogExpanded((v) => !v)} style={styles.logToggle}>
                            {logExpanded ? "Hide details" : "Show details"}
                        </button>
                    )}

                    {!recoveredRender && logExpanded && (
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

// Structured, plain-language view of qa-report.json (pipeline/qa_check.py)
// — replaces asking the user to expand the raw log and read `sceneId`s and
// frame numbers to find out what's wrong. The raw log is still available
// under "Show details" for whoever actually wants that.
function QaReportSummary({ report, scenePlan }: { report: QaReport; scenePlan: ScenePlan | null }) {
    if (report.status === "ok") {
        return (
            <div style={styles.qaSummaryOk}>
                <span style={{ ...styles.qaStatusDot, background: colors.success }} />
                No problems found.
            </div>
        );
    }

    const suggestRerender = report.issues.some((issue) => QA_ISSUE_SUGGESTS_RERENDER.has(issue.check));
    const suggestRepipeline = report.issues.some((issue) => !QA_ISSUE_SUGGESTS_RERENDER.has(issue.check));

    return (
        <div style={styles.qaSummary}>
            <div style={styles.qaSummaryHeader}>
                <span style={{ ...styles.qaStatusDot, background: colors.warning }} />
                {report.issues_count} {report.issues_count === 1 ? "problem" : "problems"} found
            </div>
            <ul style={styles.qaIssueList}>
                {report.issues.map((issue, i) => (
                    <li key={i} style={styles.qaIssueItem}>
                        {describeQaIssue(issue, scenePlan)}
                    </li>
                ))}
            </ul>
            <p style={styles.qaSuggestion}>
                {suggestRerender && suggestRepipeline
                    ? "Try re-running the pipeline and rendering again."
                    : suggestRerender
                      ? "Try rendering again — if the problem persists, the footage or edit itself may need fixing."
                      : "Re-running the pipeline may fix this before your next render."}
            </p>
        </div>
    );
}

function ProgressBar({ current, total, format }: { current: number; total: number; format: "video" | "davinci" | null }) {
    const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
    const done = total > 0 && current >= total;
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

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 10,
    },
    notReadyNote: {
        fontSize: typography.size.md,
        color: colors.textSecondary,
        fontStyle: "italic",
    },
    qaSummary: {
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: 12,
        borderRadius: radius.md,
        border: `1px solid ${colors.border}`,
        background: colors.background,
    },
    qaSummaryOk: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: 12,
        borderRadius: radius.md,
        border: `1px solid ${colors.border}`,
        background: colors.background,
        fontSize: typography.size.md,
        color: colors.textPrimary,
    },
    qaSummaryHeader: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: typography.size.md,
        fontWeight: "bold" as const,
        color: colors.textPrimary,
    },
    qaStatusDot: {
        width: 8,
        height: 8,
        borderRadius: "50%",
        flexShrink: 0,
    },
    qaIssueList: {
        margin: 0,
        paddingLeft: 20,
        display: "flex",
        flexDirection: "column",
        gap: 4,
    },
    qaIssueItem: {
        fontSize: typography.size.md,
        color: colors.textSecondary,
    },
    qaSuggestion: {
        margin: 0,
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        fontStyle: "italic",
    },
    qaErrorNote: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        fontStyle: "italic",
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
        paddingTop: 34,
        fontSize: typography.size.sm,
        fontFamily: "monospace",
        color: colors.codeText,
        whiteSpace: "pre-wrap",
        margin: 0,
    },
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
