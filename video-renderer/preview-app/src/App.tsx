import { useEffect, useMemo, useRef, useState } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { Episode } from "video-renderer-src/episode/Episode";
import type { EpisodeProps, PresenterScene, ScenePlan } from "video-renderer-src/episode/types";
import { getAssets, getManifest, getScenePlan, getVisualScenes, saveVisualScenes } from "./api";
import { manifestToEpisodeBaseProps } from "./episodeProps";
import { OverlayStrip, type EditableOverlay } from "./OverlayStrip";

function useQueryParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        episodePath: params.get("path") ?? "",
        sceneId: params.get("sceneId"),
    };
}

export function App() {
    const { episodePath, sceneId } = useQueryParams();

    const [episodeProps, setEpisodeProps] = useState<EpisodeProps | null>(null);
    const [visualScenes, setVisualScenes] = useState<{ emphases: any[]; images: any[] } | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [saveStatus, setSaveStatus] = useState("");

    const playerRef = useRef<PlayerRef>(null);

    useEffect(() => {
        if (!episodePath) {
            setError("No episode path provided (expected ?path=... query param)");
            return;
        }

        Promise.all([
            getScenePlan(episodePath),
            getManifest(episodePath),
            getAssets(episodePath),
            getVisualScenes(episodePath),
        ])
            .then(([scenePlan, manifest, assets, visualScenesData]) => {
                const baseProps = manifestToEpisodeBaseProps(manifest, assets);
                setEpisodeProps({ ...baseProps, scenePlan: scenePlan as ScenePlan });
                setVisualScenes(visualScenesData);
            })
            .catch((e) => {
                // A raw network failure (browser's generic "Failed to
                // fetch"/"NetworkError") almost always means the control
                // panel backend (ui/server.py, normally started via
                // ./start_ui.sh) isn't running — that's a much more
                // actionable message than the raw TypeError.
                if (e instanceof TypeError) {
                    setError(
                        "Can't reach the control panel backend. Make sure it's running: " +
                            "./start_ui.sh from the repo root."
                    );
                } else {
                    setError(String(e));
                }
            });
    }, [episodePath]);

    const parentScene: PresenterScene | undefined = useMemo(() => {
        if (!episodeProps || !sceneId) return undefined;
        return episodeProps.scenePlan.scenes.find(
            (s): s is PresenterScene => s.type === "presenter" && s.id === sceneId
        );
    }, [episodeProps, sceneId]);

    const editableOverlays: EditableOverlay[] = useMemo(() => {
        if (!visualScenes || !sceneId) return [];

        const emphases: EditableOverlay[] = visualScenes.emphases
            .filter((e: any) => e.sceneId === sceneId)
            .map((e: any) => ({ kind: "emphasis" as const, data: e }));

        const images: EditableOverlay[] = visualScenes.images
            .filter((i: any) => i.sceneId === sceneId)
            .map((i: any) => ({ kind: "image" as const, data: i }));

        return [...emphases, ...images];
    }, [visualScenes, sceneId]);

    const updateOverlay = (updated: EditableOverlay) => {
        if (!visualScenes) return;

        setVisualScenes({
            emphases: visualScenes.emphases.map((e: any) =>
                updated.kind === "emphasis" && e.windowId === updated.data.windowId ? updated.data : e
            ),
            images: visualScenes.images.map((i: any) =>
                updated.kind === "image" && i.windowId === updated.data.windowId ? updated.data : i
            ),
        });
    };

    const handleSave = async () => {
        if (!visualScenes) return;
        setSaveStatus("Saving…");
        try {
            await saveVisualScenes(episodePath, visualScenes.emphases, visualScenes.images);
            setSaveStatus('Saved. Re-run "Generate Remotion codegen" to apply to a render.');
        } catch (e) {
            setSaveStatus(`Save failed: ${e}`);
        }
    };

    const seekToParentFrame = (offsetInParentFrames: number) => {
        if (!playerRef.current || !parentScene) return;
        playerRef.current.seekTo(parentScene.timelineStartFrame + offsetInParentFrames);
    };

    if (error) {
        return (
            <div style={styles.message}>
                <div style={styles.messageTitle}>Preview unavailable</div>
                <div>{error}</div>
            </div>
        );
    }

    if (!episodeProps) {
        return <div style={styles.message}>Loading preview…</div>;
    }

    if (sceneId && !parentScene) {
        return <div style={styles.message}>Scene "{sceneId}" not found in scene-plan.json</div>;
    }

    return (
        <div style={styles.container}>
            <div style={styles.playerWrap}>
                <Player
                    ref={playerRef}
                    component={Episode as any}
                    inputProps={episodeProps}
                    durationInFrames={Math.max(
                        1,
                        episodeProps.scenePlan.scenes.reduce(
                            (total, s) =>
                                "timelineStartFrame" in s
                                    ? Math.max(total, s.timelineStartFrame + s.durationInFrames)
                                    : total,
                            0
                        )
                    )}
                    compositionWidth={episodeProps.width}
                    compositionHeight={episodeProps.height}
                    fps={episodeProps.fps}
                    style={{ width: "100%" }}
                    controls
                    initialFrame={parentScene ? parentScene.timelineStartFrame : 0}
                />
            </div>

            {parentScene && (
                <OverlayStrip
                    parentScene={parentScene}
                    overlays={editableOverlays}
                    onChange={updateOverlay}
                    onSeek={seekToParentFrame}
                />
            )}

            {parentScene && (
                <div style={styles.actions}>
                    <button onClick={handleSave}>Save changes</button>
                    <span>{saveStatus}</span>
                </div>
            )}
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    container: {
        fontFamily: "system-ui, sans-serif",
        color: "#e8edf2",
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 12,
    },
    playerWrap: {
        width: "100%",
        maxWidth: 720,
    },
    message: {
        fontFamily: "system-ui, sans-serif",
        color: "#e8edf2",
        padding: 24,
        fontSize: 15,
        lineHeight: 1.5,
        maxWidth: 560,
    },
    messageTitle: {
        fontSize: 18,
        fontWeight: 600,
        marginBottom: 8,
    },
    actions: {
        display: "flex",
        alignItems: "center",
        gap: 12,
    },
};
