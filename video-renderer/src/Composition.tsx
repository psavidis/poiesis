import { Composition } from "remotion";
import { Episode } from "./episode/Episode";
import { episodeProps as generatedEpisodeProps } from "../generated/episode/episode-props";
import { scenePlan as generatedScenePlan } from "../generated/episode/scene-plan";
import type { EpisodeProps, ScenePlan } from "./episode/types";

const defaultEpisodeProps: EpisodeProps = {
    ...generatedEpisodeProps,
    scenePlan: generatedScenePlan as ScenePlan,
};

// Overlay scenes (moment, inset image) are anchored to a parent scene and
// never extend past it, so only track scenes (those with an absolute
// timelineStartFrame) determine the episode's total duration.
const durationForScenePlan = (scenePlan: ScenePlan) =>
    scenePlan.scenes.reduce(
        (total, scene) =>
            "timelineStartFrame" in scene
                ? Math.max(total, scene.timelineStartFrame + scene.durationInFrames)
                : total,
        0
    );

export const MyComposition = () => {
    return (
        <Composition
            id="Episode"
            component={Episode}
            width={defaultEpisodeProps.width}
            height={defaultEpisodeProps.height}
            fps={defaultEpisodeProps.fps}
            durationInFrames={durationForScenePlan(defaultEpisodeProps.scenePlan)}
            defaultProps={defaultEpisodeProps}
            calculateMetadata={async ({ props }) => ({
                durationInFrames: durationForScenePlan(props.scenePlan),
                width: props.width,
                height: props.height,
                fps: props.fps,
            })}
        />
    );
};