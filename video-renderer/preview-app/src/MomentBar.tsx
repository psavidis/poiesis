import type { MomentScene, PresenterScene, ScenePlan, TitleScene } from "video-renderer-src/episode/types";

// Two-category color scheme, not per-treatment — the question this strip
// answers is "where does text appear on screen" (see #35), not "what
// exact treatment is this." Text-bearing: the viewer will see words
// rendered as this moment's primary content. Visual-bearing: an
// image/diagram/code block is the primary content (its own caption, if
// any, is secondary). "full-visual" is data-driven (fullVisualKind), not
// a fixed treatment->category mapping, so it needs the whole moment, not
// just its treatment string.
const TEXT_COLOR = "#3a9bd5";
const VISUAL_COLOR = "#8b5cf6";

const TEXT_TREATMENTS = new Set(["bottom-callout", "side-text", "side-terms", "comparison"]);

function isTextMoment(moment: MomentScene): boolean {
    if (moment.treatment === "full-visual") return moment.fullVisualKind === "text";
    return TEXT_TREATMENTS.has(moment.treatment);
}

// Best-effort label for what a moment actually shows, for the inline
// label on wide-enough segments and the hover tooltip on narrow ones —
// mirrors MomentEditorPanel's summarizeMomentContent for the treatments
// that don't carry a single m.text field.
function momentLabel(moment: MomentScene): string {
    if (moment.text) return moment.text;
    if (moment.treatment === "side-terms" && moment.terms?.length) {
        return moment.terms.map((t) => t.text).join(", ");
    }
    if (moment.treatment === "comparison" && moment.comparison) {
        return `${moment.comparison.left} vs ${moment.comparison.right}`;
    }
    if (moment.treatment === "side-diagram" && moment.diagram) {
        return moment.diagram.nodes.map((n) => n.label).join(" → ");
    }
    if (moment.treatment === "side-code") return moment.codeAssetId ?? moment.treatment;
    if (moment.treatment === "side-image") return moment.caption || moment.assetId || moment.treatment;
    return moment.treatment;
}

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
            <div style={styles.labelRow}>
                <span style={styles.label}>Moments ({resolved.length})</span>
                <span style={styles.legend}>
                    <span style={styles.legendItem}>
                        <span style={{ ...styles.legendDot, background: TEXT_COLOR }} /> text
                    </span>
                    <span style={styles.legendItem}>
                        <span style={{ ...styles.legendDot, background: VISUAL_COLOR }} /> image/diagram/code
                    </span>
                </span>
            </div>

            <div style={styles.track} onMouseDown={onTrackClick}>
                {resolved.map(({ moment, startFrame }) => {
                    // A floor so very short moments (a few seconds in a
                    // 12-minute episode) stay clickable/visible instead of
                    // rendering as an invisible sliver.
                    const widthPct = Math.max((moment.durationInFrames / totalFrames) * 100, 0.6);
                    const leftPct = (startFrame / totalFrames) * 100;
                    const label = momentLabel(moment);
                    const color = isTextMoment(moment) ? TEXT_COLOR : VISUAL_COLOR;

                    return (
                        <div
                            key={moment.id}
                            style={{
                                ...styles.segment,
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                background: color,
                            }}
                            title={`${moment.id} — ${moment.treatment}: ${label}`}
                            onClick={(e) => onSelectMoment(moment.id, { x: e.clientX, y: e.clientY })}
                        >
                            {widthPct > 4 && <span style={styles.segmentLabel}>{label}</span>}
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
    labelRow: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 8,
    },
    label: {
        fontSize: 12,
        color: "#9aa7b4",
    },
    legend: {
        display: "flex",
        gap: 12,
        fontSize: 11,
        color: "#6b7683",
    },
    legendItem: {
        display: "flex",
        alignItems: "center",
        gap: 4,
    },
    legendDot: {
        width: 8,
        height: 8,
        borderRadius: "50%",
        flexShrink: 0,
    },
    track: {
        position: "relative",
        height: 28,
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
        display: "flex",
        alignItems: "center",
        overflow: "hidden",
        cursor: "pointer",
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
