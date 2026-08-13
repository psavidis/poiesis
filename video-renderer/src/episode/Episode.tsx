import {
    AbsoluteFill,
    OffthreadVideo,
    Sequence,
    staticFile,
} from "remotion";

import type { EpisodeProps, EpisodeVideo, PresenterScene, Scene, ScenePlan } from "./types";
import { scenePlan } from "../../generated/episode/scene-plan";
import { AnimatedTitle } from "./AnimatedTitle";

const typedScenePlan = scenePlan as ScenePlan;

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
            src={staticFile(video.path)}
            trimBefore={scene.sourceStartFrame}
            trimAfter={scene.sourceEndFrame}
            style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
            }}
        />
    </Sequence>
);

export const Episode = ({
                            videos,
                        }: EpisodeProps) => {

    const videoMap = new Map(
        videos.map((video) => [
            video.id,
            video,
        ])
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
        }
    };

    return (
        <AbsoluteFill>
            {typedScenePlan.scenes.map(renderScene)}
        </AbsoluteFill>
    );
};