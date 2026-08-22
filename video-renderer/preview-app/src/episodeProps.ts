import type { EpisodeBackground, EpisodeBaseProps } from "video-renderer-src/episode/types";

// backgrounds.json's raw renderPath -> EpisodeBackground's own path field,
// same renderPath/path field-name mapping every other asset type gets in
// manifestToEpisodeBaseProps below. Exported separately (not just inlined
// in that function's own backgrounds.map call) because AssetLibraryPanel's
// reindex/delete calls return this SAME raw backgrounds.json shape
// directly from the API — EpisodeWorkspace's handleBackgroundsChanged must
// apply this identical mapping before merging the result back into
// episodeProps.backgrounds, or every EpisodeBackground consumer downstream
// (the Remotion <Player>'s own BackgroundLayer, AssetLibraryPanel's own
// thumbnails) ends up with the raw, non-servable `path` instead — confirmed
// live: every background thumbnail broken-image icon'd after a reindex
// (#92 follow-up), since the initial load's correctly-mapped path got
// overwritten by the raw one.
export function mapBackground(background: any): EpisodeBackground {
    return {
        id: background.id,
        filename: background.filename,
        path: background.renderPath,
        caption: background.caption,
        mediaType: background.mediaType,
        duration: background.duration,
        fps: background.fps,
    };
}

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
            keyedAudioPath: video.keyedAudioRenderPath,
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
        backgrounds: backgrounds.map(mapBackground),
    };
}
