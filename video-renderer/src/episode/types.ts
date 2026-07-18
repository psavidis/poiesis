export type EpisodeManifest = {
    episode: string;
    videos: {
        id: string;
        order: number;
        filename: string;
        path: string;
    }[];
};

export type EpisodeTranscript = {
    episode: string;
    segments: {
        source: string;
        start: number;
        end: number;
        text: string;
    }[];
};