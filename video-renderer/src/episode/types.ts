export interface EpisodeVideo {
    id: string;
    filename: string;
    path: string;
    duration: number;
    fps: number;
    width: number;
    height: number;
}

export interface EpisodeScene {
    id: string;
    videoId: string;
    startFrame: number;
    durationInFrames: number;
}

export interface EpisodeProps {
    width: number;
    height: number;
    fps: number;
    videos: EpisodeVideo[];
    scenes: EpisodeScene[];
}