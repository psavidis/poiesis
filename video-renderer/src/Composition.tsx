import { Composition } from "remotion";
import { Episode } from "./episode/Episode";
import { episodeProps } from "../generated/episode/episode-props";
import { scenePlan } from "../generated/episode/scene-plan";
import type { ScenePlan } from "./episode/types";

const typedScenePlan = scenePlan as ScenePlan;

export const MyComposition = () => {
    const durationInFrames = typedScenePlan.scenes.reduce(
        (total, scene) =>
            Math.max(total, scene.timelineStartFrame + scene.durationInFrames),
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