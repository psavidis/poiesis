import type { Scene } from "video-renderer-src/episode/types";
import { colors, radius, typography } from "./tokens";

interface Props {
    track: Scene | undefined;
    overlays: Scene[];
    // Clicking a title/moment chip opens that scene's editor (see #27) —
    // other scene types (presenter, caption, image, beat) have no editor
    // yet, so their chips stay inert for these.
    onSelectTitle?: (titleText: string) => void;
    onSelectMoment?: (sceneId: string) => void;
    // Fires alongside onSelectTitle/onSelectMoment on the SAME click (see
    // #29) — prefills the edit-plan chat with this scene's real id, so one
    // click both opens the structured editor AND primes the
    // natural-language correction path for the same scene. Only wired for
    // clickable (title/moment) chips, same restriction as above.
    onSelectScene?: (sceneId: string) => void;
}

// Shows which scene(s) are on screen at the player's current frame, so a
// scene id is always visible to type straight into an edit-plan
// instruction ("shorten scene-caption-42") without having to open
// scene-plan.json separately.
export function ActiveSceneBar({ track, overlays, onSelectTitle, onSelectMoment, onSelectScene }: Props) {
    if (!track) {
        return <div style={styles.wrap}>No scene at this frame (gap in the timeline).</div>;
    }

    return (
        <div style={styles.wrap}>
            <SceneChip
                scene={track}
                kind="track"
                onSelectTitle={onSelectTitle}
                onSelectMoment={onSelectMoment}
                onSelectScene={onSelectScene}
            />
            {overlays.map((s) => (
                <SceneChip
                    key={s.id}
                    scene={s}
                    kind="overlay"
                    onSelectTitle={onSelectTitle}
                    onSelectMoment={onSelectMoment}
                    onSelectScene={onSelectScene}
                />
            ))}
        </div>
    );
}

// Exported for EditPlanChat's selection indicator (#51) — same
// "what does this scene actually show" summarization, no reason to
// duplicate the per-type switch there.
export function sceneLabel(scene: Scene): string {
    switch (scene.type) {
        case "presenter":
            return `clip ${scene.videoId}`;
        case "title":
        case "caption":
        case "beat":
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

function SceneChip({
    scene,
    kind,
    onSelectTitle,
    onSelectMoment,
    onSelectScene,
}: {
    scene: Scene;
    kind: "track" | "overlay";
    onSelectTitle?: (titleText: string) => void;
    onSelectMoment?: (sceneId: string) => void;
    onSelectScene?: (sceneId: string) => void;
}) {
    const clickable =
        (scene.type === "title" && onSelectTitle) || (scene.type === "moment" && onSelectMoment);

    const handleClick = () => {
        if (scene.type === "title" && onSelectTitle) onSelectTitle(scene.text);
        if (scene.type === "moment" && onSelectMoment) onSelectMoment(scene.id);
        if (clickable && onSelectScene) onSelectScene(scene.id);
    };

    return (
        <div
            style={{
                ...styles.chip,
                ...(kind === "overlay" ? styles.overlayChip : {}),
                ...(clickable ? styles.clickableChip : {}),
            }}
            onClick={clickable ? handleClick : undefined}
            role={clickable ? "button" : undefined}
            tabIndex={clickable ? 0 : undefined}
        >
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
        fontSize: typography.size.sm,
        color: colors.textMuted,
    },
    chip: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 8px",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.sm,
    },
    overlayChip: {
        borderStyle: "dashed",
    },
    clickableChip: {
        cursor: "pointer",
    },
    chipType: {
        textTransform: "uppercase",
        fontSize: 10,
        fontWeight: typography.weight.bold,
        letterSpacing: 0.5,
        color: colors.textSecondary,
    },
    chipId: {
        fontFamily: "monospace",
        color: colors.textPrimary,
    },
    chipLabel: {
        color: colors.textSecondary,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        maxWidth: 260,
    },
};
