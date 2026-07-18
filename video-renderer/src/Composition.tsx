import { CalculateMetadataFunction, Composition } from "remotion";
import { Episode } from "./episode/Episode";

export type EpisodeVideo = {
    id: string;
    filename: string;
    path: string;
    duration: number;
    fps: number;
    width: number;
    height: number;
};

export type EpisodeProps = {
    videos: EpisodeVideo[];
};

const calculateMetadata: CalculateMetadataFunction<EpisodeProps> = ({
                                                                        props,
                                                                    }) => {
    const fps = 30;

    const durationInFrames = props.videos.reduce(
        (total, video) => total + Math.round(video.duration * fps),
        0
    );

    return {
        durationInFrames,
        fps,
    };
};

export const MyComposition = () => {
    return (
        <Composition
            id="Episode"
            component={Episode}
            width={1280}
            height={720}
            fps={30}
            durationInFrames={1}
            defaultProps={{
                videos: [
                    {
                        id: "001",
                        filename: "0. Welcome.mov",
                        path: "original_footage/0. Welcome.mov",
                        duration: 9.283333,
                        fps: 60,
                        width: 2592,
                        height: 1674,
                    },
                    {
                        id: "002",
                        filename: "1. The DI Promise.mov",
                        path: "original_footage/1. The DI Promise.mov",
                        duration: 38.666667,
                        fps: 60,
                        width: 2592,
                        height: 1674,
                    },
                    {
                        id: "003",
                        filename: "2. The Spring Boot Trap.mov",
                        path: "original_footage/2. The Spring Boot Trap.mov",
                        duration: 102.483333,
                        fps: 60,
                        width: 2592,
                        height: 1674,
                    },
                ],
            }}
            calculateMetadata={calculateMetadata}
        />
    );
};