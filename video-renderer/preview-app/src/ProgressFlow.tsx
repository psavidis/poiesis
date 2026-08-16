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

    const doneCount = relevant.filter((s) => s.complete).length;

    if (doneCount === relevant.length) return "done";
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
    const runHandleRef = useRef<RunHandle | null>(null);

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

    const start = () => {
        setError(null);
        setRunning(true);

        runHandleRef.current = runOverWebSocket(
            "/ws/pipeline/run",
            { path: episodePath, skipCaptions },
            (msg: RunMessage) => {
                if (msg.type === "error") {
                    setError(msg.message);
                    setRunning(false);
                } else if (msg.type === "done" || msg.type === "cancelled") {
                    setRunning(false);
                    refreshStatus();
                }
            }
        );
    };

    const cancel = () => {
        runHandleRef.current?.cancel();
    };

    const allDone = status ? status.stages.every((s) => s.complete) : false;

    return (
        <div style={styles.wrap}>
            <div style={styles.phases}>
                {PHASES.map((phase) => {
                    const state = phaseState(phase.stageIds, status);
                    return (
                        <div key={phase.label} style={styles.phase}>
                            <span style={{ ...styles.dot, ...dotStyleFor(state) }} />
                            <span style={styles.phaseLabel}>{phase.label}</span>
                        </div>
                    );
                })}
            </div>

            <div style={styles.actions}>
                {!running && (
                    <button onClick={start} disabled={!status}>
                        {allDone ? "Re-run pipeline" : "Start"}
                    </button>
                )}
                {running && (
                    <>
                        <span style={styles.runningLabel}>Processing…</span>
                        <button className="secondary" onClick={cancel}>
                            Cancel
                        </button>
                    </>
                )}
            </div>

            {error && <div style={styles.error}>{error}</div>}
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
    error: {
        fontSize: typography.size.md,
        color: colors.error,
    },
};
