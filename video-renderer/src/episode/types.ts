export interface EpisodeVideo {
    id: string;
    filename: string;
    path: string;
    keyedPath?: string;
    duration: number;
    fps: number;
    width: number;
    height: number;
}

export interface EpisodeAsset {
    id: string;
    filename: string;
    path: string;
    caption: string;
}

export interface BackgroundVideo {
    filename: string;
    path: string;
    duration: number;
    fps: number;
}

export interface SceneEffects {
    captions: boolean;
    transition: string;
}

export interface PresenterScene {
    type: "presenter";
    id: string;
    videoId: string;
    sourceStartFrame: number;
    sourceEndFrame: number;
    timelineStartFrame: number;
    durationInFrames: number;
    effects: SceneEffects;
}

export interface TitleScene {
    type: "title";
    id: string;
    text: string;
    timelineStartFrame: number;
    durationInFrames: number;
}

export interface EmphasisScene {
    type: "emphasis";
    id: string;
    text: string;
    parentSceneId: string;
    offsetInParentFrames: number;
    durationInFrames: number;
}

export interface ImageScene {
    type: "image";
    id: string;
    assetId: string;
    caption?: string;
    display: "full" | "inset";
    parentSceneId: string;
    offsetInParentFrames: number;
    durationInFrames: number;
}

export type Scene = PresenterScene | TitleScene | EmphasisScene | ImageScene;

export interface ScenePlan {
    version: number;
    episode: string;
    fps: number;
    scenes: Scene[];
}

// What pipeline/prepare_footage.py's generate_episode_props_ts writes to
// generated/episode/episode-props.ts. scenePlan isn't included there — it's
// a separate generated artifact (generated/episode/scene-plan.ts, written
// later in the pipeline by generate_scene_plan_ts.py) composed together with
// this at the Composition.tsx level.
export type EpisodeBaseProps = {
    width: number;
    height: number;
    fps: number;
    videos: EpisodeVideo[];
    assets: EpisodeAsset[];
    backgroundVideo?: BackgroundVideo;
};

export type EpisodeProps = EpisodeBaseProps & {
    scenePlan: ScenePlan;
};