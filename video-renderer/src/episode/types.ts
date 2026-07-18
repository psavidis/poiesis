export interface EpisodeVideo {
    id: string;
    filename: string;
    path: string;
    duration: number;
    fps: number;
    width: number;
    height: number;
}

export interface EpisodeProps {
    videos: EpisodeVideo[];
}