import type { Scene } from "video-renderer-src/episode/types";

interface Props {
    track: Scene | undefined;
    overlays: Scene[];
}

// Shows which scene(s) are on screen at the player's current frame, so a
// scene id is always visible to type straight into an edit-plan
// instruction ("shorten scene-caption-42") instead of having to guess or
// open scene-plan.json separately.
export function ActiveSceneBar({ track, overlays }: Props) {
    if (!track) {
        return <div style={styles.wrap}>No scene at this frame (gap in the timeline).</div>;
    }

    return (
        <div style={styles.wrap}>
            <SceneChip scene={track} kind="track" />
            {overlays.map((s) => (
                <SceneChip key={s.id} scene={s} kind="overlay" />
            ))}
        </div>
    );
}

function sceneLabel(scene: Scene): string {
    switch (scene.type) {
        case "presenter":
            return `clip ${scene.videoId}`;
        case "title":
        case "caption":
            return truncate(scene.text);
        case "moment":
            return scene.text ? truncate(scene.text) : (scene.assetId ?? scene.treatment);
        case "image":
            return scene.assetId;
    }
}

function truncate(text: string, max = 60): string {
    return text.length > max ? `${text.slice(0, max)}…` : text;
}

function SceneChip({ scene, kind }: { scene: Scene; kind: "track" | "overlay" }) {
    return (
        <div style={{ ...styles.chip, ...(kind === "overlay" ? styles.overlayChip : {}) }}>
            <span style={styles.chipType}>{scene.type}</span>
            <span style={styles.chipId}>{scene.id}</span>
            <span style={styles.chipLabel}>{sceneLabel(scene)}</span>
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexWrap: "wrap",
        gap: 6,
        fontSize: 12,
        color: "#6b7683",
    },
    chip: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 8px",
        background: "#161d24",
        border: "1px solid #2a333d",
        borderRadius: 4,
    },
    overlayChip: {
        borderStyle: "dashed",
    },
    chipType: {
        textTransform: "uppercase",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: 0.5,
        color: "#9aa7b4",
    },
    chipId: {
        fontFamily: "monospace",
        color: "#e8edf2",
    },
    chipLabel: {
        color: "#9aa7b4",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        maxWidth: 260,
    },
};
