import { useEffect, useMemo, useRef, useState } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { Episode } from "video-renderer-src/episode/Episode";
import type { EpisodeProps, PresenterScene, Scene, ScenePlan } from "video-renderer-src/episode/types";
import { getAssets, getManifest, getScenePlan, getVisualScenes, saveVisualScenes } from "./api";
import { ActiveSceneBar } from "./ActiveSceneBar";
import { EditPlanChat } from "./EditPlanChat";
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
    const [currentFrame, setCurrentFrame] = useState(0);

    // Tracks the player's current frame so the UI can show which scene(s)
    // are actually on screen right now — otherwise there's no way to know
    // which scene id to reference in a natural-language edit instruction
    // without opening scene-plan.json separately. frameupdate fires during
    // both playback and scrubbing, so this stays live either way.
    useEffect(() => {
        const player = playerRef.current;
        if (!player) return;

        const onFrameUpdate = (e: { detail: { frame: number } }) => setCurrentFrame(e.detail.frame);

        player.addEventListener("frameupdate", onFrameUpdate);
        return () => player.removeEventListener("frameupdate", onFrameUpdate);
    }, [episodeProps]);

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
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [episodePath]);

    // Re-fetches only scene-plan.json (not manifest/assets, which an edit-plan
    // instruction never changes) and merges it into the existing episodeProps
    // so the player picks up an applied edit without a full page reload.
    const reloadScenePlan = () => {
        if (!episodePath) return;
        getScenePlan(episodePath).then((scenePlan) => {
            setEpisodeProps((prev) => (prev ? { ...prev, scenePlan: scenePlan as ScenePlan } : prev));
        });
    };

    const parentScene: PresenterScene | undefined = useMemo(() => {
        if (!episodeProps || !sceneId) return undefined;
        return episodeProps.scenePlan.scenes.find(
            (s): s is PresenterScene => s.type === "presenter" && s.id === sceneId
        );
    }, [episodeProps, sceneId]);

    // What's actually on screen at currentFrame: exactly one track scene
    // (presenter/title, absolute timelineStartFrame) plus zero or more
    // overlay scenes (emphasis/caption/image) anchored to whichever
    // presenter scene is active — so the id shown here is always something
    // that can be typed straight into an edit-plan instruction ("shorten
    // scene-caption-42") without having to open scene-plan.json to find it.
    const activeScenes = useMemo(() => {
        if (!episodeProps) return { track: undefined as Scene | undefined, overlays: [] as Scene[] };

        const scenes = episodeProps.scenePlan.scenes;

        const track = scenes.find(
            (s): s is Scene & { timelineStartFrame: number; durationInFrames: number } =>
                "timelineStartFrame" in s &&
                currentFrame >= s.timelineStartFrame &&
                currentFrame < s.timelineStartFrame + s.durationInFrames
        );

        if (!track) return { track: undefined, overlays: [] };

        const overlays = scenes.filter((s): s is Scene & { parentSceneId: string; offsetInParentFrames: number; durationInFrames: number } => {
            if (!("parentSceneId" in s) || s.parentSceneId !== track.id) return false;
            const start = track.timelineStartFrame + s.offsetInParentFrames;
            return currentFrame >= start && currentFrame < start + s.durationInFrames;
        });

        return { track, overlays };
    }, [episodeProps, currentFrame]);

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

    const seekToAbsoluteFrame = (absoluteFrame: number) => {
        if (!playerRef.current) return;
        playerRef.current.seekTo(absoluteFrame);
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

    // With no sceneId, this is a full-episode preview rather than a
    // scene-scoped timing editor — give the player the full page width
    // instead of the narrow strip-editor width, since there's no
    // OverlayStrip/save UI competing for space below it.
    const playerWrapStyle = sceneId ? styles.playerWrap : styles.playerWrapFullEpisode;

    return (
        <div style={styles.container}>
            <div style={styles.brandBanner}>
                <img src="/poiesis-logo.png" alt="" style={styles.brandLogo} />
                <span style={styles.brandText}>Poiesis Preview</span>
            </div>

            <div style={playerWrapStyle}>
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
                    // Constrain the scrubber to the scene being edited so
                    // its range matches the overlay strip below one-to-one —
                    // dragging a block to a position and seeing the player
                    // land on the same position are the same frame number,
                    // not two independently-scaled coordinate spaces.
                    inFrame={parentScene ? parentScene.timelineStartFrame : undefined}
                    outFrame={
                        parentScene
                            ? parentScene.timelineStartFrame + parentScene.durationInFrames - 1
                            : undefined
                    }
                />
            </div>

            <div style={playerWrapStyle}>
                <ActiveSceneBar track={activeScenes.track} overlays={activeScenes.overlays} />
            </div>

            <div style={playerWrapStyle}>
                <EditPlanChat episodePath={episodePath} onApplied={reloadScenePlan} />
            </div>

            {parentScene && (
                <OverlayStrip
                    parentScene={parentScene}
                    overlays={editableOverlays}
                    onChange={updateOverlay}
                    onSeek={seekToAbsoluteFrame}
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
    brandBanner: {
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
        padding: "20px 0",
    },
    brandLogo: {
        width: 88,
        height: 88,
        borderRadius: 16,
        objectFit: "cover",
    },
    brandText: {
        fontSize: 26,
        fontWeight: 700,
        color: "#e8edf2",
        letterSpacing: 0.3,
    },
    playerWrap: {
        width: "100%",
        maxWidth: 720,
    },
    playerWrapFullEpisode: {
        width: "100%",
        maxWidth: 1280,
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
