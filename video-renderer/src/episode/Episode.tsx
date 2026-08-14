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

const layoutOf = (scene: PresenterScene | undefined): PresenterLayout => scene?.layout ?? "center";

const PresenterSequence = ({
                                scene,
                                video,
                                previousLayout,
                                nextLayout,
                            }: {
    scene: PresenterScene;
    video: EpisodeVideo;
    // The chronologically adjacent presenter scenes' layouts (not the scenes
    // themselves — that's all the animation needs), so this scene's own
    // <Sequence> — which has its own frame clock starting at 0 — can
    // interpolate from where the presenter was, and toward where it's about
    // to go, instead of cutting instantly at the boundary.
    previousLayout: PresenterLayout;
    nextLayout: PresenterLayout;
}) => {
    const thisLayout = layoutOf(scene);

    return (
        <Sequence
            from={scene.timelineStartFrame}
            durationInFrames={scene.durationInFrames}
        >
            <AnimatedPresenterFrame
                video={video}
                scene={scene}
                fromLayout={previousLayout}
                thisLayout={thisLayout}
                toLayout={nextLayout}
            />
        </Sequence>
    );
};

const AnimatedPresenterFrame = ({
                                     video,
                                     scene,
                                     fromLayout,
                                     thisLayout,
                                     toLayout,
                                 }: {
    video: EpisodeVideo;
    scene: PresenterScene;
    fromLayout: PresenterLayout;
    thisLayout: PresenterLayout;
    toLayout: PresenterLayout;
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const enterWindow = Math.min(TRANSITION_FRAMES, Math.floor(durationInFrames / 2));
    const exitWindow = Math.min(TRANSITION_FRAMES, Math.ceil(durationInFrames / 2));
    const exitStart = Math.max(enterWindow, durationInFrames - exitWindow);

    const fromGeo = LAYOUT_GEOMETRY[fromLayout];
    const thisGeo = LAYOUT_GEOMETRY[thisLayout];
    const toGeo = LAYOUT_GEOMETRY[toLayout];

    // Only actually animate when the layout is changing at that boundary —
    // a scene surrounded by the same layout on both sides never moves,
    // avoiding a pointless micro-animation on every single cut.
    const widthPct =
        fromLayout === thisLayout && toLayout === thisLayout
            ? thisGeo.widthPct
            : interpolate(
                  frame,
                  [0, enterWindow, exitStart, durationInFrames],
                  [fromGeo.widthPct, thisGeo.widthPct, thisGeo.widthPct, toGeo.widthPct],
                  { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
              );

    const leftPct =
        fromLayout === thisLayout && toLayout === thisLayout
            ? thisGeo.leftPct
            : interpolate(
                  frame,
                  [0, enterWindow, exitStart, durationInFrames],
                  [fromGeo.leftPct, thisGeo.leftPct, thisGeo.leftPct, toGeo.leftPct],
                  { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
              );

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
                             parent,
                             asset,
                         }: {
    scene: MomentScene;
    parent: PresenterScene;
    asset: EpisodeAsset | undefined;
}) => {
    switch (scene.treatment) {
        case "bottom-callout":
            return <BottomCallout text={scene.text ?? ""} />;

        case "side-text": {
            const presenterOnLeft = layoutOf(parent) === "left";
            return <SideText text={scene.text ?? ""} presenterOnLeft={presenterOnLeft} />;
        }

        case "side-image": {
            if (!asset) return null;
            const presenterOnLeft = layoutOf(parent) === "left";
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

    // Presenter scenes in timeline order, so each one can look up its
    // chronological predecessor/successor's layout for the slide animation
    // at its boundaries — the scene plan doesn't otherwise encode adjacency.
    const orderedPresenterScenes = [...presenterSceneMap.values()].sort(
        (a, b) => a.timelineStartFrame - b.timelineStartFrame
    );

    const previousLayoutById = new Map<string, PresenterLayout>();
    const nextLayoutById = new Map<string, PresenterLayout>();

    orderedPresenterScenes.forEach((scene, index) => {
        previousLayoutById.set(scene.id, layoutOf(orderedPresenterScenes[index - 1]));
        nextLayoutById.set(scene.id, layoutOf(orderedPresenterScenes[index + 1]));
    });

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
                        previousLayout={previousLayoutById.get(scene.id) ?? "center"}
                        nextLayout={nextLayoutById.get(scene.id) ?? "center"}
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
                        <MomentSequence scene={scene} parent={parent} asset={asset} />
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
