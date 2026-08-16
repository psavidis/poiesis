import type { MomentScene, PresenterScene, ScenePlan, TitleScene } from "video-renderer-src/episode/types";

// One color regardless of treatment — treatments already have their own
// per-type styling inside the player itself; this strip's job is just
// "where are the moments," not re-encoding treatment as color too.
const MOMENT_COLOR = "#8b5cf6";

interface Props {
    scenePlan: ScenePlan;
    totalFrames: number;
    currentFrame: number;
    onSeek: (absoluteFrame: number) => void;
    // Passes the click's screen position alongside the moment's scene id —
    // see SceneBar's onSelectTitle for why (anchoring InlineTextEditor).
    onSelectMoment: (sceneId: string, anchor: { x: number; y: number }) => void;
}

// Every moment overlay's resolved window across the full episode, so
// sparse, easy-to-miss moments (a few seconds each, scattered across a
// 12-minute episode) are visible and jumpable at a glance instead of only
// discoverable by scrubbing into one. Moments don't carry an absolute
// timelineStartFrame (see types.ts) — position is resolved the same way
// EpisodeWorkspace's activeScenes memo already does, against whichever
// track scene is currently at parentSceneId.
export function MomentBar({ scenePlan, totalFrames, currentFrame, onSeek, onSelectMoment }: Props) {
    if (totalFrames <= 0) return null;

    const trackById = new Map<string, PresenterScene | TitleScene>();
    scenePlan.scenes.forEach((s) => {
        if (s.type === "presenter" || s.type === "title") trackById.set(s.id, s);
    });

    const resolved = scenePlan.scenes
        .filter((s): s is MomentScene => s.type === "moment")
        .map((moment) => {
            const parent = trackById.get(moment.parentSceneId);
            if (!parent) return null;
            return {
                moment,
                startFrame: parent.timelineStartFrame + moment.offsetInParentFrames,
            };
        })
        .filter((m): m is { moment: MomentScene; startFrame: number } => m !== null)
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
            <div style={styles.label}>Moments ({resolved.length})</div>

            <div style={styles.track} onMouseDown={onTrackClick}>
                {resolved.map(({ moment, startFrame }) => {
                    // A floor so very short moments (a few seconds in a
                    // 12-minute episode) stay clickable/visible instead of
                    // rendering as an invisible sliver.
                    const widthPct = Math.max((moment.durationInFrames / totalFrames) * 100, 0.6);
                    const leftPct = (startFrame / totalFrames) * 100;

                    return (
                        <div
                            key={moment.id}
                            style={{
                                ...styles.segment,
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                            }}
                            title={`${moment.id} — ${moment.treatment}`}
                            onClick={(e) => onSelectMoment(moment.id, { x: e.clientX, y: e.clientY })}
                        />
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
        height: 20,
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
        background: MOMENT_COLOR,
        cursor: "pointer",
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
