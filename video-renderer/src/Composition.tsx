import { Composition } from "remotion";
import { Episode } from "./episode/Episode";
import { episodeProps } from "../generated/episode/episode-props";
import type { EpisodeVideo } from "./episode/types";

export const MyComposition = () => {
    const durationInFrames = episodeProps.videos.reduce(
        (total: number, video: EpisodeVideo) =>
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