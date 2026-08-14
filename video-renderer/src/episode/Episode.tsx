import {
    AbsoluteFill,
    Audio,
    Loop,
    OffthreadVideo,
    Sequence,
    interpolate,
    staticFile,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

import type { EpisodeAsset, EpisodeProps, EpisodeVideo, MomentScene, PresenterLayout, PresenterScene, Scene } from "./types";
import { AnimatedTitle } from "./AnimatedTitle";
import { CaptionText } from "./CaptionText";
import { EpisodeImage } from "./EpisodeImage";
import { BottomCallout, SideImage, SideText } from "./MomentTreatments";

// Frame geometry for each layout, as a fraction of the full frame. "left"/
// "right" leave the opposite side free for a moment's side-text/side-image
// treatment. Widened slightly past a literal half so the presenter doesn't
// feel cramped — matches SideText/SideImage's own content width in
// MomentTreatments.tsx, which assume this same split.
const LAYOUT_GEOMETRY: Record<PresenterLayout, { widthPct: number; leftPct: number }> = {
    center: { widthPct: 100, leftPct: 0 },
    left: { widthPct: 55, leftPct: 0 },
    right: { widthPct: 55, leftPct: 45 },
};

const TRANSITION_FRAMES = 24;

// A window (in frames local to a presenter scene) during which the
// presenter should be off-center, derived from a single moment's own
// on-screen span — NOT the whole presenter scene. This is the fix for the
// bug where the presenter used to shift for a whole (possibly 60s+) scene
// even though the side content it was making room for was only visible for
// a few seconds: the presenter now only leaves center immediately before
// the moment appears and returns immediately after it ends.
interface LayoutWindow {
    // Frame (local to the scene) the slide-out begins — moment's own start
    // minus TRANSITION_FRAMES, clamped to the scene's own bounds.
    start: number;
    // Frame the slide-back-to-center completes — moment's own end plus
    // TRANSITION_FRAMES, clamped.
    end: number;
    side: "left" | "right";
}

const layoutWindowsForScene = (scene: PresenterScene, moments: MomentScene[]): LayoutWindow[] => {
    const windows = moments
        .filter((m) => m.parentSceneId === scene.id && m.presenterSide)
        .map((m) => ({
            start: Math.max(0, m.offsetInParentFrames - TRANSITION_FRAMES),
            end: Math.min(scene.durationInFrames, m.offsetInParentFrames + m.durationInFrames + TRANSITION_FRAMES),
            side: m.presenterSide as "left" | "right",
        }))
        .sort((a, b) => a.start - b.start);

    return windows;
};

const PresenterSequence = ({
                                scene,
                                video,
                                layoutWindows,
                            }: {
    scene: PresenterScene;
    video: EpisodeVideo;
    // This scene's own moment-driven shift windows (see layoutWindowsForScene)
    // — everything the animation needs to know is local to this scene, no
    // adjacency with neighboring presenter scenes required anymore.
    layoutWindows: LayoutWindow[];
}) => {
    return (
        <Sequence
            from={scene.timelineStartFrame}
            durationInFrames={scene.durationInFrames}
        >
            <AnimatedPresenterFrame
                video={video}
                scene={scene}
                layoutWindows={layoutWindows}
            />
        </Sequence>
    );
};

const AnimatedPresenterFrame = ({
                                     video,
                                     scene,
                                     layoutWindows,
                                 }: {
    video: EpisodeVideo;
    scene: PresenterScene;
    layoutWindows: LayoutWindow[];
}) => {
    const frame = useCurrentFrame();

    const centerGeo = LAYOUT_GEOMETRY.center;

    // Find the window (if any) whose padded span contains the current
    // frame, and interpolate: center -> side across the leading pad, hold
    // at the side for the moment's own span, side -> center across the
    // trailing pad. Frames outside every window stay at dead center — most
    // of a long scene is unaffected, which is the whole point of the fix.
    const activeWindow = layoutWindows.find((w) => frame >= w.start && frame < w.end);

    let widthPct = centerGeo.widthPct;
    let leftPct = centerGeo.leftPct;

    if (activeWindow) {
        const sideGeo = LAYOUT_GEOMETRY[activeWindow.side];
        const enterEnd = Math.min(activeWindow.start + TRANSITION_FRAMES, activeWindow.end);
        const exitStart = Math.max(activeWindow.end - TRANSITION_FRAMES, enterEnd);

        widthPct = interpolate(
            frame,
            [activeWindow.start, enterEnd, exitStart, activeWindow.end],
            [centerGeo.widthPct, sideGeo.widthPct, sideGeo.widthPct, centerGeo.widthPct],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );

        leftPct = interpolate(
            frame,
            [activeWindow.start, enterEnd, exitStart, activeWindow.end],
            [centerGeo.leftPct, sideGeo.leftPct, sideGeo.leftPct, centerGeo.leftPct],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
    }

    return (
        <AbsoluteFill>
            <div
                style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: `${leftPct}%`,
                    width: `${widthPct}%`,
                }}
            >
                <OffthreadVideo
                    src={staticFile(video.keyedPath ?? video.path)}
                    trimBefore={scene.sourceStartFrame}
                    trimAfter={scene.sourceEndFrame}
                    transparent={Boolean(video.keyedPath)}
                    muted
                    style={{
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                    }}
                />
            </div>
            <Audio
                src={staticFile(video.path)}
                trimBefore={scene.sourceStartFrame}
                trimAfter={scene.sourceEndFrame}
            />
        </AbsoluteFill>
    );
};

const LoopingBackground = ({ path, duration }: { path: string; duration: number }) => {
    const { fps } = useVideoConfig();

    const durationInFrames = Math.round(duration * fps);

    return (
        <Loop durationInFrames={durationInFrames}>
            <OffthreadVideo
                src={staticFile(path)}
                muted
                style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                }}
            />
        </Loop>
    );
};

const MomentSequence = ({
                             scene,
                             asset,
                         }: {
    scene: MomentScene;
    asset: EpisodeAsset | undefined;
}) => {
    switch (scene.treatment) {
        case "bottom-callout":
            return <BottomCallout text={scene.text ?? ""} />;

        case "side-text": {
            const presenterOnLeft = scene.presenterSide === "left";
            return <SideText text={scene.text ?? ""} presenterOnLeft={presenterOnLeft} />;
        }

        case "side-image": {
            if (!asset) return null;
            const presenterOnLeft = scene.presenterSide === "left";
            return (
                <SideImage
                    path={asset.path}
                    caption={scene.caption}
                    presenterOnLeft={presenterOnLeft}
                />
            );
        }
    }
};

export const Episode = ({
                            videos,
                            assets,
                            backgroundVideo,
                            scenePlan: typedScenePlan,
                        }: EpisodeProps) => {

    const videoMap = new Map(
        videos.map((video) => [
            video.id,
            video,
        ])
    );

    const assetMap = new Map(
        assets.map((asset) => [
            asset.id,
            asset,
        ])
    );

    const presenterSceneMap = new Map(
        typedScenePlan.scenes
            .filter((scene): scene is PresenterScene => scene.type === "presenter")
            .map((scene) => [scene.id, scene])
    );

    const momentScenes = typedScenePlan.scenes.filter(
        (scene): scene is MomentScene => scene.type === "moment"
    );

    const renderScene = (scene: Scene) => {
        switch (scene.type) {
            case "presenter": {
                const video = videoMap.get(scene.videoId);

                if (!video) {
                    return null;
                }

                return (
                    <PresenterSequence
                        key={scene.id}
                        scene={scene}
                        video={video}
                        layoutWindows={layoutWindowsForScene(scene, momentScenes)}
                    />
                );
            }

            case "title": {
                return (
                    <Sequence
                        key={scene.id}
                        from={scene.timelineStartFrame}
                        durationInFrames={scene.durationInFrames}
                    >
                        <AnimatedTitle text={scene.text} />
                    </Sequence>
                );
            }

            case "moment": {
                const parent = presenterSceneMap.get(scene.parentSceneId);

                if (!parent) {
                    return null;
                }

                const asset = scene.assetId ? assetMap.get(scene.assetId) : undefined;

                return (
                    <Sequence
                        key={scene.id}
                        from={parent.timelineStartFrame + scene.offsetInParentFrames}
                        durationInFrames={scene.durationInFrames}
                    >
                        <MomentSequence scene={scene} asset={asset} />
                    </Sequence>
                );
            }

            case "image": {
                const asset = assetMap.get(scene.assetId);
                const parent = presenterSceneMap.get(scene.parentSceneId);

                if (!asset || !parent) {
                    return null;
                }

                return (
                    <Sequence
                        key={scene.id}
                        from={parent.timelineStartFrame + scene.offsetInParentFrames}
                        durationInFrames={scene.durationInFrames}
                    >
                        <EpisodeImage
                            path={asset.path}
                            caption={scene.caption}
                            display={scene.display}
                        />
                    </Sequence>
                );
            }

            case "caption": {
                const parent = presenterSceneMap.get(scene.parentSceneId);

                if (!parent || !parent.effects.captions) {
                    return null;
                }

                return (
                    <Sequence
                        key={scene.id}
                        from={parent.timelineStartFrame + scene.offsetInParentFrames}
                        durationInFrames={scene.durationInFrames}
                    >
                        <CaptionText text={scene.text} />
                    </Sequence>
                );
            }
        }
    };

    return (
        <AbsoluteFill>
            {backgroundVideo && (
                <LoopingBackground
                    path={backgroundVideo.path}
                    duration={backgroundVideo.duration}
                />
            )}
            {typedScenePlan.scenes.map(renderScene)}
        </AbsoluteFill>
    );
};
