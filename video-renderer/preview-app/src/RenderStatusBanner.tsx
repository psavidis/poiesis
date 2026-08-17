import { useEffect, useState } from "react";
import { getRenderStatus } from "./api";
import { colors, radius, typography } from "./tokens";

interface Props {
    episodePath: string;
    // Whether the Advanced tab (where the full progress bar / cancel
    // control live) is currently open — the banner hides itself there to
    // avoid showing the same "N of M clips" information twice on screen
    // at once.
    advancedTabOpen: boolean;
    onOpenAdvanced: () => void;
}

// A persistent, always-visible strip shown above the tab strip whenever a
// DaVinci render is running for this episode — regardless of which tab is
// currently open. Without this, render progress was only visible inside
// the Advanced tab (see AdvancedPanel.tsx's own progress bar), so a render
// kicked off and then left running while the user browsed Storyboard/Asset
// library/Episode analysis gave no indication anything was still going —
// exactly the gap this component closes.
//
// Independent from AdvancedPanel's own websocket-driven progress state —
// this is a second, simple poller of the same read-only
// GET /api/episode/render-status endpoint AdvancedPanel already uses for
// its own post-refresh recovery (see that file's own recovery effect).
// Two independent pollers of one cheap, idempotent GET is a smaller,
// safer change than lifting AdvancedPanel's whole websocket/run-state
// management up into EpisodeWorkspace just so one banner can read it.
interface RenderStatusSnapshot {
    current: number | null;
    total: number | null;
    format: "video" | "davinci" | null;
    resolution: string | null;
}

function formatLabel(format: "video" | "davinci" | null, resolution: string | null): string {
    const kind = format === "davinci" ? "DaVinci Resolve project" : format === "video" ? "MP4" : null;
    if (!kind && !resolution) return "";
    return [kind, resolution ? `(${resolution})` : null].filter(Boolean).join(" ");
}

export function RenderStatusBanner({ episodePath, advancedTabOpen, onOpenAdvanced }: Props) {
    const [status, setStatus] = useState<RenderStatusSnapshot | null>(null);

    useEffect(() => {
        let cancelled = false;
        let pollTimer: ReturnType<typeof setTimeout> | null = null;

        const poll = () => {
            getRenderStatus(episodePath)
                .then((s) => {
                    if (cancelled) return;

                    if (!s.running) {
                        setStatus(null);
                        pollTimer = setTimeout(poll, 4000);
                        return;
                    }

                    setStatus({ current: s.current, total: s.total, format: s.format, resolution: s.resolution });
                    pollTimer = setTimeout(poll, 2000);
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

    if (!status || advancedTabOpen) return null;

    const { current, total, format, resolution } = status;
    const pct = total && total > 0 && current !== null ? Math.min(100, Math.round((current / total) * 100)) : null;
    const kindLabel = formatLabel(format, resolution);

    return (
        <button style={styles.banner} onClick={onOpenAdvanced}>
            <span className="phase-dot-active" style={styles.dot} />
            <span className="processing-label" style={styles.label}>
                {current !== null && total !== null ? `Rendering — ${current} of ${total} clips` : "Rendering…"}
                {kindLabel && <span style={styles.kindLabel}> — {kindLabel}</span>}
            </span>
            {pct !== null && (
                <span style={styles.trackWrap}>
                    <span style={styles.track}>
                        <span style={{ ...styles.fill, width: `${pct}%` }} />
                    </span>
                </span>
            )}
            <span style={styles.viewLink}>View</span>
        </button>
    );
}

const styles = {
    banner: {
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        padding: "8px 16px",
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        marginBottom: 10,
        cursor: "pointer",
        textAlign: "left" as const,
        font: "inherit",
        color: colors.textPrimary,
    },
    dot: {
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: colors.accent,
        flexShrink: 0,
    },
    label: {
        fontSize: typography.size.md,
        whiteSpace: "nowrap" as const,
    },
    kindLabel: {
        color: colors.textSecondary,
        fontWeight: "normal" as const,
    },
    trackWrap: {
        flex: 1,
        minWidth: 60,
    },
    track: {
        display: "block",
        height: 6,
        borderRadius: radius.md,
        background: colors.background,
        border: `1px solid ${colors.border}`,
        overflow: "hidden",
    },
    fill: {
        display: "block",
        height: "100%",
        background: colors.accent,
        borderRadius: radius.md,
        transition: "width 0.2s ease",
    },
    viewLink: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        flexShrink: 0,
    },
};
