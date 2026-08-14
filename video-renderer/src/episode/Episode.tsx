import {
    AbsoluteFill,
    Audio,
    Loop,
    OffthreadVideo,
    Sequence,
    staticFile,
    useVideoConfig,
} from "remotion";

import type { EpisodeProps, EpisodeVideo, PresenterScene, Scene } from "./types";
import { AnimatedTitle } from "./AnimatedTitle";
import { EmphasisText } from "./EmphasisText";
import { EpisodeImage } from "./EpisodeImage";

const PresenterSequence = ({
                                scene,
                                video,
                            }: {
    scene: PresenterScene;
    video: EpisodeVideo;
}) => (
    <Sequence
        from={scene.timelineStartFrame}
        durationInFrames={scene.durationInFrames}
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
        <Audio
            src={staticFile(video.path)}
            trimBefore={scene.sourceStartFrame}
            trimAfter={scene.sourceEndFrame}
        />
    </Sequence>
);

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

            case "emphasis": {
                const parent = presenterSceneMap.get(scene.parentSceneId);

                if (!parent) {
                    return null;
                }

                return (
                    <Sequence
                        key={scene.id}
                        from={parent.timelineStartFrame + scene.offsetInParentFrames}
                        durationInFrames={scene.durationInFrames}
                    >
                        <EmphasisText text={scene.text} />
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