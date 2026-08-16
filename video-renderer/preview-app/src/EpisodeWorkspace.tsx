import { useEffect, useMemo, useRef, useState } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { Episode } from "video-renderer-src/episode/Episode";
import type { EpisodeProps, Scene, ScenePlan } from "video-renderer-src/episode/types";
import { getAssets, getCodeAssets, getManifest, getMoments, getScenePlan, type EpisodeStatus } from "./api";
import { ActiveSceneBar } from "./ActiveSceneBar";
import { AdvancedPanel } from "./AdvancedPanel";
import { ChapterStrip } from "./ChapterStrip";
import { EditPlanChat } from "./EditPlanChat";
import { manifestToEpisodeBaseProps } from "./episodeProps";
import { MomentEditorPanel } from "./MomentEditorPanel";
import { ProgressFlow } from "./ProgressFlow";
import { StoryboardPanel } from "./StoryboardPanel";
import { TitleEditorPanel } from "./TitleEditorPanel";

function useQueryParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        episodePath: params.get("path") ?? "",
    };
}

// Everything App.tsx used to render directly — extracted verbatim (see
// #24) so the router root can place this at /episode instead of it being
// the only thing the app can ever show.
//
// Used to also support a "?sceneId=..." scene-scoped mode (a separate
// browser tab, narrower player, OverlayStrip always visible) reached via
// the control panel's "Adjust timing" link — removed in #28. Adjusting a
// moment's timing is now MomentEditorPanel's own "Adjust timing" toggle,
// scoped to whichever moment you clicked, in this same full-episode view.
// That removed the two-buffer problem the old cross-tab design had (this
// component's `moments` state vs. the scene-scoped tab's own copy, kept in
// sync only by a visibilitychange listener re-fetching on focus) — now
// there's exactly one `moments` array, owned by whichever
// MomentEditorPanel is currently open.
export function EpisodeWorkspace() {
    const { episodePath } = useQueryParams();

    const [episodeProps, setEpisodeProps] = useState<EpisodeProps | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [episodeStatus, setEpisodeStatus] = useState<EpisodeStatus | null>(null);
    // Persisted per browser session, matching ui/static/app.js's
    // `includeCaptions` default (unticked = don't generate them —
    // full-sentence captions are tiresome on some episodes). Owned here
    // (not inside AdvancedPanel) since ProgressFlow's "Start" button needs
    // to read it too.
    const [includeCaptions, setIncludeCaptions] = useState(false);

    // Which scene's editor panel is open, if any — set by clicking a
    // title/moment chip in ActiveSceneBar (see #27). Storyboard has no
    // click-to-open equivalent (chapter-keyed, not scene-anchored), so it
    // isn't part of this state.
    const [selectedEditor, setSelectedEditor] = useState<
        { kind: "title"; titleText: string } | { kind: "moment"; sceneId: string } | null
    >(null);

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
            .then(([scenePlan, manifest, assets, codeAssets]) => {
                const baseProps = manifestToEpisodeBaseProps(manifest, assets, codeAssets);
                setEpisodeProps({ ...baseProps, scenePlan: scenePlan as ScenePlan });
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

    const seekToAbsoluteFrame = (absoluteFrame: number) => {
        if (!playerRef.current) return;
        playerRef.current.seekTo(absoluteFrame);
    };

    // The progress flow and Advanced panel render regardless of whether
    // episodeProps has loaded yet — a freshly-picked episode with no
    // pipeline output should show "Start" and empty progress dots, not
    // disappear behind the player's own "Loading preview…"/error guards
    // below. episodePath-less loads (no ?path=) skip both, since there's
    // no episode to run anything against.
    const header = episodePath ? (
        <>
            <div style={styles.brandBanner}>
                <img src="/poiesis-logo.png" alt="" style={styles.brandLogo} />
                <span style={styles.brandText}>Poiesis Preview</span>
            </div>
            <ProgressFlow episodePath={episodePath} skipCaptions={!includeCaptions} onStatusChange={setEpisodeStatus} />
            <AdvancedPanel
                episodePath={episodePath}
                status={episodeStatus}
                onStatusChange={setEpisodeStatus}
                includeCaptions={includeCaptions}
                onIncludeCaptionsChange={setIncludeCaptions}
            />
            <StoryboardPanel episodePath={episodePath} />
        </>
    ) : null;

    if (error) {
        return (
            <div style={styles.container}>
                {header}
                <div style={styles.message}>
                    <div style={styles.messageTitle}>Preview unavailable</div>
                    <div>{error}</div>
                </div>
            </div>
        );
    }

    if (!episodeProps) {
        return (
            <div style={styles.container}>
                {header}
                <div style={styles.message}>Loading preview…</div>
            </div>
        );
    }

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
            {header}

            <div style={styles.playerWrap}>
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
                />
            </div>

            <div style={styles.playerWrap}>
                <ChapterStrip
                    scenePlan={episodeProps.scenePlan}
                    totalFrames={totalFrames}
                    currentFrame={currentFrame}
                    fps={episodeProps.fps}
                    onSeek={seekToAbsoluteFrame}
                />
            </div>

            <div style={styles.playerWrap}>
                <label style={styles.checkboxRow}>
                    <input
                        type="checkbox"
                        checked={showCaptions}
                        onChange={(e) => setShowCaptions(e.target.checked)}
                    />
                    Show captions in this preview (view-only — does not change scene-plan.json)
                </label>
            </div>

            <div style={styles.playerWrap}>
                <ActiveSceneBar
                    track={activeScenes.track}
                    overlays={activeScenes.overlays}
                    onSelectTitle={(titleText) => setSelectedEditor({ kind: "title", titleText })}
                    onSelectMoment={(momentSceneId) => setSelectedEditor({ kind: "moment", sceneId: momentSceneId })}
                />
            </div>

            {selectedEditor?.kind === "title" && (
                <div style={styles.playerWrap}>
                    <TitleEditorPanel
                        episodePath={episodePath}
                        titleText={selectedEditor.titleText}
                        onClose={() => setSelectedEditor(null)}
                    />
                </div>
            )}

            {selectedEditor?.kind === "moment" && (
                <div style={styles.playerWrap}>
                    <MomentEditorPanel
                        episodePath={episodePath}
                        sceneId={selectedEditor.sceneId}
                        scenePlan={episodeProps.scenePlan}
                        currentFrame={currentFrame}
                        onSeek={seekToAbsoluteFrame}
                        onClose={() => setSelectedEditor(null)}
                    />
                </div>
            )}

            <div style={styles.playerWrap}>
                <EditPlanChat episodePath={episodePath} onApplied={reloadScenePlan} />
            </div>
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
    checkboxRow: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: 13,
        color: "#9aa7b4",
        cursor: "pointer",
    },
};
