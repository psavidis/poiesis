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

// Where the presenter sits in the frame. Defaults to "center" (today's only
// behavior — full-frame) when absent, so every existing episode's
// scene-plan.json keeps rendering exactly as before with no migration.
// "left"/"right" free up the opposite side of the frame for a moment's
// side-text/side-image treatment (see MomentScene below) — the presenter
// animates to/from this position rather than cutting, see PresenterSequence.
export type PresenterLayout = "center" | "left" | "right";

export interface PresenterScene {
    type: "presenter";
    id: string;
    videoId: string;
    sourceStartFrame: number;
    sourceEndFrame: number;
    timelineStartFrame: number;
    durationInFrames: number;
    effects: SceneEffects;
    layout?: PresenterLayout;
}

export interface TitleScene {
    type: "title";
    id: string;
    text: string;
    timelineStartFrame: number;
    durationInFrames: number;
}

// A moment's treatment must agree with its parent presenter scene's layout:
// "bottom-callout" requires layout "center" (today's emphasis-chip look);
// "side-text"/"side-image" require layout "left" or "right" (content fills
// whichever side the presenter isn't occupying). Validated in
// pipeline/generate_moments.py, not just assumed.
export type MomentTreatment = "bottom-callout" | "side-text" | "side-image";

export interface MomentScene {
    type: "moment";
    id: string;
    treatment: MomentTreatment;
    text?: string;
    assetId?: string;
    caption?: string;
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

export interface CaptionScene {
    type: "caption";
    id: string;
    text: string;
    parentSceneId: string;
    offsetInParentFrames: number;
    durationInFrames: number;
}

export type Scene = PresenterScene | TitleScene | MomentScene | ImageScene | CaptionScene;

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