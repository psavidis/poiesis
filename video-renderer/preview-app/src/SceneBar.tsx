import type { PresenterScene, ScenePlan, TitleScene } from "video-renderer-src/episode/types";

// Distinct from ChapterStrip's per-chapter color cycle (which groups scenes
// by topic) — this strip shows the actual scene boundaries underneath that
// grouping, so a fixed two-color-by-type scheme keeps the two strips
// visually distinguishable at a glance.
const PRESENTER_COLOR = "#2a7d6f";
const TITLE_COLOR = "#c98a2a";

interface Props {
    scenePlan: ScenePlan;
    totalFrames: number;
    currentFrame: number;
    onSeek: (absoluteFrame: number) => void;
    // Passes the click's screen position alongside the title text so the
    // caller can anchor a floating inline text editor near where the user
    // actually clicked (see #34's InlineTextEditor) — not needed for the
    // seek itself, only for positioning that editor.
    onSelectTitle: (titleText: string, anchor: { x: number; y: number }) => void;
}

// Every track scene (presenter clip or title card) as its own segment
// across the full episode, so individual clips/titles are visible and
// jumpable without scrubbing — ChapterStrip only shows chapter-level
// grouping, not where each underlying clip/title actually starts.
export function SceneBar({ scenePlan, totalFrames, currentFrame, onSeek, onSelectTitle }: Props) {
    if (totalFrames <= 0) return null;

    const scenes = scenePlan.scenes.filter(
        (s): s is PresenterScene | TitleScene => s.type === "presenter" || s.type === "title"
    );

    if (scenes.length === 0) return null;

    const sorted = [...scenes].sort((a, b) => a.timelineStartFrame - b.timelineStartFrame);

    const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
        onSeek(Math.round(pct * totalFrames));
    };

    const playheadPct = clamp((currentFrame / totalFrames) * 100, 0, 100);

    return (
        <div style={styles.wrap}>
            <div style={styles.label}>Scenes ({sorted.length})</div>

            <div style={styles.track} onMouseDown={onTrackClick}>
                {sorted.map((scene) => {
                    const widthPct = (scene.durationInFrames / totalFrames) * 100;
                    const isTitle = scene.type === "title";
                    const label = isTitle ? scene.text : `clip ${scene.videoId}`;

                    return (
                        <div
                            key={scene.id}
                            style={{
                                ...styles.segment,
                                width: `${widthPct}%`,
                                background: isTitle ? TITLE_COLOR : PRESENTER_COLOR,
                                cursor: isTitle ? "pointer" : "default",
                            }}
                            title={`${scene.id} — ${label}`}
                            onClick={
                                isTitle
                                    ? (e) => onSelectTitle(scene.text, { x: e.clientX, y: e.clientY })
                                    : undefined
                            }
                        >
                            {widthPct > 3 && <span style={styles.segmentLabel}>{label}</span>}
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
        height: 28,
        display: "flex",
        borderRadius: 6,
        overflow: "hidden",
        border: "1px solid #2a333d",
        userSelect: "none",
        cursor: "pointer",
    },
    segment: {
        position: "relative",
        height: "100%",
        display: "flex",
        alignItems: "center",
        borderRight: "1px solid rgba(0,0,0,0.35)",
        overflow: "hidden",
    },
    segmentLabel: {
        padding: "0 6px",
        fontSize: 10,
        fontWeight: 600,
        color: "#fff",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        textShadow: "0 1px 2px rgba(0,0,0,0.5)",
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
