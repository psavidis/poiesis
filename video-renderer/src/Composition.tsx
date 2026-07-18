import { Composition } from "remotion";
import { Episode } from "./episode/Episode";
import { episodeProps } from "../generated/episode/episode-props";

export const MyComposition = () => {
    const durationInFrames = episodeProps.videos.reduce(
        (total, video) =>
            total + Math.round(video.duration * episodeProps.fps),
        0
    );

    return (
        <Composition
            id="Episode"
            component={Episode as any}
            width={episodeProps.width}
            height={episodeProps.height}
            fps={episodeProps.fps}
            durationInFrames={durationInFrames}
            defaultProps={episodeProps}
        />
    );
};