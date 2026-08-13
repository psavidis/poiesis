import { Composition } from "remotion";
import { Episode } from "./episode/Episode";
import { episodeProps } from "../generated/episode/episode-props";
import { scenePlan } from "../generated/episode/scene-plan";
import type { ScenePlan } from "./episode/types";

const typedScenePlan = scenePlan as ScenePlan;

export const MyComposition = () => {
    // Overlay scenes (emphasis, inset image) are anchored to a parent scene
    // and never extend past it, so only track scenes (those with an
    // absolute timelineStartFrame) determine the episode's total duration.
    const durationInFrames = typedScenePlan.scenes.reduce(
        (total, scene) =>
            "timelineStartFrame" in scene
                ? Math.max(total, scene.timelineStartFrame + scene.durationInFrames)
                : total,
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