import {
    AbsoluteFill,
    OffthreadVideo,
    Sequence,
    staticFile,
} from "remotion";

import type { EpisodeProps } from "../Composition";

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
                            src={staticFile(
                                `episodes/episode-9/original_footage/${video.filename}`
                            )}
                        />
                    </Sequence>
                );

                currentFrame += durationInFrames;

                return sequence;
            })}
        </AbsoluteFill>
    );
};