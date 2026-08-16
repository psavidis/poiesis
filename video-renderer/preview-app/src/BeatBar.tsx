import type { BeatScene, PresenterScene, ScenePlan } from "video-renderer-src/episode/types";

// A third, distinct color from SceneBar/MomentBar — beats are a
// genuinely different scene type (word-pop/underline/icon-accent, not a
// text/image treatment choice), so this doesn't reuse MomentBar's
// text/visual categories.
const BEAT_COLOR = "#e8a23a";

interface Props {
    scenePlan: ScenePlan;
    totalFrames: number;
    currentFrame: number;
    onSeek: (absoluteFrame: number) => void;
}

// Every beat's resolved window across the full episode — beats are
// higher-frequency than moments (a light, constant rhythm rather than a
// rare event, per BeatScene's own doc comment in types.ts) and were
// previously invisible in the app entirely: no chip in ActiveSceneBar, no
// marker anywhere, discoverable only by scrubbing into one by accident
// (see #36). View-only, same as SceneBar/MomentBar — no click-to-edit yet
// (beats have no structured editor), just click-to-seek.
export function BeatBar({ scenePlan, totalFrames, currentFrame, onSeek }: Props) {
    if (totalFrames <= 0) return null;

    const trackById = new Map<string, PresenterScene>();
    scenePlan.scenes.forEach((s) => {
        if (s.type === "presenter") trackById.set(s.id, s);
    });

    const resolved = scenePlan.scenes
        .filter((s): s is BeatScene => s.type === "beat")
        .map((beat) => {
            const parent = trackById.get(beat.parentSceneId);
            if (!parent) return null;
            return { beat, startFrame: parent.timelineStartFrame + beat.offsetInParentFrames };
        })
        .filter((b): b is { beat: BeatScene; startFrame: number } => b !== null)
        .sort((a, b) => a.startFrame - b.startFrame);

    if (resolved.length === 0) return null;

    const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
        onSeek(Math.round(pct * totalFrames));
    };

    const playheadPct = clamp((currentFrame / totalFrames) * 100, 0, 100);

    return (
        <div style={styles.wrap}>
            <div style={styles.label}>Beats ({resolved.length})</div>

            <div style={styles.track} onMouseDown={onTrackClick}>
                {resolved.map(({ beat, startFrame }) => {
                    // Beats are very short (under a second) — a floor so
                    // they stay clickable/visible instead of an invisible
                    // sliver, same reasoning as MomentBar's floor.
                    const widthPct = Math.max((beat.durationInFrames / totalFrames) * 100, 0.4);
                    const leftPct = (startFrame / totalFrames) * 100;

                    return (
                        <div
                            key={beat.id}
                            style={{
                                ...styles.segment,
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                            }}
                            title={`${beat.id} — ${beat.kind}: ${beat.text}`}
                            onClick={(e) => {
                                e.stopPropagation();
                                onSeek(startFrame);
                            }}
                        >
                            {widthPct > 3 && <span style={styles.segmentLabel}>{beat.text}</span>}
                        </div>
                    );
                })}

                <div style={{ ...styles.playhead, left: `${playheadPct}%` }} />
            </div>
        </div>
    );
}

function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 6,
    },
    label: {
        fontSize: 12,
        color: "#9aa7b4",
    },
    track: {
        position: "relative",
        height: 22,
        borderRadius: 6,
        background: "#161d24",
        border: "1px solid #2a333d",
        userSelect: "none",
        cursor: "pointer",
    },
    segment: {
        position: "absolute",
        top: 2,
        bottom: 2,
        borderRadius: 3,
        background: BEAT_COLOR,
        display: "flex",
        alignItems: "center",
        overflow: "hidden",
        cursor: "pointer",
    },
    segmentLabel: {
        padding: "0 5px",
        fontSize: 10,
        fontWeight: 600,
        color: "#1a1300",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
    },
    playhead: {
        position: "absolute",
        top: 0,
        bottom: 0,
        width: 2,
        background: "#ff5a3c",
        pointerEvents: "none",
        boxShadow: "0 0 4px rgba(255,90,60,0.8)",
    },
};
