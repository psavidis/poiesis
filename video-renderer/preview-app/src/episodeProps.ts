import type { EpisodeBaseProps } from "video-renderer-src/episode/types";

// Mirrors pipeline/prepare_footage.py's generate_episode_props_ts field
// mapping (manifest.json's renderPath/keyedRenderPath -> EpisodeBaseProps'
// path/keyedPath), so the preview reads the same manifest.json the pipeline
// already produces instead of parsing the generated episode-props.ts.
export function manifestToEpisodeBaseProps(
    manifest: any,
    assets: any[],
    codeAssets: any[] = [],
    backgrounds: any[] = []
): EpisodeBaseProps {
    return {
        width: manifest.width,
        height: manifest.height,
        fps: manifest.fps,
        videos: manifest.videos.map((video: any) => ({
            id: video.id,
            filename: video.filename,
            path: video.renderPath,
            keyedPath: video.keyedRenderPath,
            duration: video.duration,
            fps: video.fps,
            width: video.width,
            height: video.height,
        })),
        assets: assets.map((asset: any) => ({
            id: asset.id,
            filename: asset.filename,
            path: asset.renderPath,
            caption: asset.caption,
            mediaType: asset.mediaType,
            keyColor: asset.keyColor,
        })),
        codeAssets: codeAssets.map((codeAsset: any) => ({
            id: codeAsset.id,
            filename: codeAsset.filename,
            path: codeAsset.renderPath,
            language: codeAsset.language,
            description: codeAsset.description,
            lineCount: codeAsset.lineCount,
            kind: codeAsset.kind,
            keyColor: codeAsset.keyColor,
        })),
        backgrounds: backgrounds.map((background: any) => ({
            id: background.id,
            filename: background.filename,
            path: background.renderPath,
            caption: background.caption,
            mediaType: background.mediaType,
            duration: background.duration,
            fps: background.fps,
        })),
    };
}
