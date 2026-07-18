import { Composition } from "remotion";
import { Episode } from "./episode/Episode";
import { episodeProps } from "./episode/episode-props";

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

export const MyComposition = () => {
    const durationInFrames = episodeProps.videos.reduce(
        (total, video) =>
            total + Math.round(video.duration * 30),
        0
    );

    return (
        <Composition
            id="Episode"
            component={Episode}
            width={1280}
            height={720}
            fps={30}
            durationInFrames={durationInFrames}
            defaultProps={episodeProps}
        />
    );
};