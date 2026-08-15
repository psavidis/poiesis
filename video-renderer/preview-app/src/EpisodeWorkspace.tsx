import { useEffect, useMemo, useRef, useState } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { Episode } from "video-renderer-src/episode/Episode";
import type { EpisodeProps, PresenterScene, Scene, ScenePlan } from "video-renderer-src/episode/types";
import { getAssets, getCodeAssets, getManifest, getMoments, getScenePlan, saveMoments } from "./api";
import { ActiveSceneBar } from "./ActiveSceneBar";
import { ChapterStrip } from "./ChapterStrip";
import { EditPlanChat } from "./EditPlanChat";
import { manifestToEpisodeBaseProps } from "./episodeProps";
import { normalizeMoment } from "./momentDuration";
import { OverlayStrip, type EditableOverlay } from "./OverlayStrip";

function useQueryParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        episodePath: params.get("path") ?? "",
        sceneId: params.get("sceneId"),
    };
}

// Everything App.tsx used to render directly — extracted verbatim (see
// #24) so the router root can place this at /episode instead of it being
// the only thing the app can ever show. No logic changed from the
// pre-router version; only the file it lives in and its name.
export function EpisodeWorkspace() {
    const { episodePath, sceneId } = useQueryParams();

    const [episodeProps, setEpisodeProps] = useState<EpisodeProps | null>(null);
    const [moments, setMoments] = useState<{ moments: any[] } | null>(null);
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
            getCodeAssets(episodePath),
            getMoments(episodePath),
        ])
            .then(([scenePlan, manifest, assets, codeAssets, momentsData]) => {
                const baseProps = manifestToEpisodeBaseProps(manifest, assets, codeAssets);
                setEpisodeProps({ ...baseProps, scenePlan: scenePlan as ScenePlan });
                // Defensive normalization for moments.json written by an
                // older pipeline version — see momentDuration.ts. A no-op
                // for anything the current pipeline wrote.
                setMoments({
                    moments: (momentsData?.moments ?? []).map(normalizeMoment),
                });
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

    // Client-side only — never written back to scene-plan.json. Lets you
    // quickly check "how does this look without captions" without touching
    // saved data; pipeline/generate_captions.py --disable (via the control
    // panel's "Skip captions" checkbox) is the persisted equivalent.
    const [showCaptions, setShowCaptions] = useState(true);

    const playerProps = useMemo(() => {
        if (!episodeProps || showCaptions) return episodeProps;

        return {
            ...episodeProps,
            scenePlan: {
                ...episodeProps.scenePlan,
                scenes: episodeProps.scenePlan.scenes.map((s) =>
                    s.type === "presenter" ? { ...s, effects: { ...s.effects, captions: false } } : s
                ),
            },
        };
    }, [episodeProps, showCaptions]);

    const parentScene: PresenterScene | undefined = useMemo(() => {
        if (!episodeProps || !sceneId) return undefined;
        return episodeProps.scenePlan.scenes.find(
            (s): s is PresenterScene => s.type === "presenter" && s.id === sceneId
        );
    }, [episodeProps, sceneId]);

    // What's actually on screen at currentFrame: exactly one track scene
    // (presenter/title, absolute timelineStartFrame) plus zero or more
    // overlay scenes (moment/caption/image) anchored to whichever
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
        if (!moments || !sceneId) return [];

        // moments state is already normalized (see the fetch effect above)
        // — maxDurationInParentFrames here is the real, currently-editable
        // duration, not the raw window ceiling.
        return moments.moments
            .filter((m: any) => m.sceneId === sceneId)
            .map((m: any) => ({ kind: "moment" as const, data: m }));
    }, [moments, sceneId]);

    const updateOverlay = (updated: EditableOverlay) => {
        if (!moments) return;

        setMoments({
            moments: moments.moments.map((m: any) =>
                updated.kind === "moment" && m.windowId === updated.data.windowId ? updated.data : m
            ),
        });
    };

    const handleSave = async () => {
        if (!moments) return;
        setSaveStatus("Saving…");
        try {
            await saveMoments(episodePath, moments.moments);
            setSaveStatus("Saved — the next render will pick this up.");
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

    const totalFrames = Math.max(
        1,
        episodeProps.scenePlan.scenes.reduce(
            (total, s) =>
                "timelineStartFrame" in s ? Math.max(total, s.timelineStartFrame + s.durationInFrames) : total,
            0
        )
    );

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
                    inputProps={playerProps}
                    durationInFrames={totalFrames}
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

            {!parentScene && (
                <div style={playerWrapStyle}>
                    <ChapterStrip
                        scenePlan={episodeProps.scenePlan}
                        totalFrames={totalFrames}
                        currentFrame={currentFrame}
                        fps={episodeProps.fps}
                        onSeek={seekToAbsoluteFrame}
                    />
                </div>
            )}

            <div style={playerWrapStyle}>
                <label style={styles.checkboxRow}>
                    <input
                        type="checkbox"
                        checked={showCaptions}
                        onChange={(e) => setShowCaptions(e.target.checked)}
                    />
                    Show captions in this preview (view-only — does not change scene-plan.json)
                </label>
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
                    currentFrame={currentFrame}
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
    checkboxRow: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: 13,
        color: "#9aa7b4",
        cursor: "pointer",
    },
};
