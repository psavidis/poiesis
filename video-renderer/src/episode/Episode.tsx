import {
    AbsoluteFill,
    OffthreadVideo,
    Sequence,
    staticFile,
} from "remotion";

import type { EpisodeProps } from "./types";

export const Episode = ({
                            videos,
                            scenes,
                        }: EpisodeProps) => {

    const videoMap = new Map(
        videos.map((video) => [
            video.id,
            video,
        ])
    );

    return (
        <AbsoluteFill>
            {scenes.map((scene) => {
                const video = videoMap.get(
                    scene.videoId
                );

                if (!video) {
                    return null;
                }

                return (
                    <Sequence
                        key={scene.id}
                        from={scene.startFrame}
                        durationInFrames={
                            scene.durationInFrames
                        }
                    >
                        <OffthreadVideo
                            src={staticFile(video.path)}
                            style={{
                                width: "100%",
                                height: "100%",
                                objectFit: "cover",
                            }}
                        />
                    </Sequence>
                );
            })}
        </AbsoluteFill>
    );
};