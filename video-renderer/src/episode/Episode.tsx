import {
    AbsoluteFill,
    OffthreadVideo,
    Sequence,
    staticFile,
} from "remotion";

import type { EpisodeProps } from "./types";

export const Episode: React.FC<EpisodeProps> = ({
                                                    videos,
                                                }) => {
    let currentFrame = 0;

    return (
        <AbsoluteFill>
            {videos.map((video) => {
                const durationInFrames = Math.round(
                    video.duration * 30
                );

                const sequence = (
                    <Sequence
                        key={video.id}
                        from={currentFrame}
                        durationInFrames={durationInFrames}
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

                currentFrame += durationInFrames;

                return sequence;
            })}
        </AbsoluteFill>
    );
};