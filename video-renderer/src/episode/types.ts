export interface EpisodeVideo {
    id: string;
    filename: string;
    path: string;
    duration: number;
    fps: number;
    width: number;
    height: number;
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

export type Scene = PresenterScene | TitleScene;

export interface ScenePlan {
    version: number;
    episode: string;
    fps: number;
    scenes: Scene[];
}

export interface EpisodeProps {
    width: number;
    height: number;
    fps: number;
    videos: EpisodeVideo[];
}