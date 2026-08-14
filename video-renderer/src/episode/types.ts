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

export interface EpisodeCodeAsset {
    id: string;
    filename: string;
    path: string;
    language: string;
    description: string;
    lineCount: number;
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

// Where the presenter sits in the frame. "center" (full-frame) is the
// default everywhere the presenter isn't actively making room for a
// side-text/side-image moment. Deliberately NOT a field on PresenterScene:
// the presenter's position is derived per-frame from whichever MomentScene
// is currently active (see Episode.tsx's layoutWindowsForScene), not a
// static property of the whole scene — otherwise the presenter shifts for
// the scene's entire duration even though the moment content it's making
// room for is only on screen for a few seconds in the middle. See
// MomentScene.presenterSide below.
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
}

export interface TitleScene {
    type: "title";
    id: string;
    text: string;
    timelineStartFrame: number;
    durationInFrames: number;
}

// A moment's treatment implies whether/how the presenter moves:
// "bottom-callout" leaves the presenter full-frame (presenterSide absent);
// "side-text"/"side-image"/"side-code"/"side-diagram" require a
// presenterSide ("left" or "right") — the presenter animates to that side
// only for this moment's own window (plus a short transition pad either
// side), then animates back to center once the moment ends, rather than
// for its whole parent scene's duration. Validated in
// pipeline/generate_moments.py, not just assumed.
export type MomentTreatment = "bottom-callout" | "side-text" | "side-image" | "side-code" | "side-diagram";

export interface DiagramNode {
    id: string;
    label: string;
}

export interface DiagramEdge {
    from: string;
    to: string;
    label?: string;
}

// Deliberately minimal for a first version — no node coordinates (layout
// is computed deterministically from `layout` + node array order, not an
// LLM decision), no shapes/colors beyond one brand style, no nested/
// grouped nodes. Unlike assetId/codeAssetId, this is inline data rather
// than a reference into an indexed file — there is no pre-existing
// "diagram asset" to select from, since a diagram's whole value is
// visualizing a relationship the AI identifies in the explanation.
export interface DiagramData {
    nodes: DiagramNode[];
    edges: DiagramEdge[];
    layout: "horizontal" | "vertical";
}

export interface MomentScene {
    type: "moment";
    id: string;
    treatment: MomentTreatment;
    text?: string;
    assetId?: string;
    codeAssetId?: string;
    diagram?: DiagramData;
    caption?: string;
    presenterSide?: "left" | "right";
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
    codeAssets?: EpisodeCodeAsset[];
    backgroundVideo?: BackgroundVideo;
};

export type EpisodeProps = EpisodeBaseProps & {
    scenePlan: ScenePlan;
};