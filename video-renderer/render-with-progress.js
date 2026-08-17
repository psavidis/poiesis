#!/usr/bin/env node

// Renders the "Video (MP4)" episode composition the same way
// render_episode.sh does (same composition id, same defaultProps-driven
// scene plan, same --width/--height override), but via Remotion's
// programmatic Node API instead of shelling out to `npx remotion render` —
// so this script gets a REAL structured progress callback
// (RenderMediaOnProgress: {renderedFrames, encodedFrames, progress, ...})
// instead of the CLI's ANSI, carriage-return-overwritten progress bar,
// which has no stable machine-readable format to parse (see
// @remotion/cli/dist/progress-bar.js's makeRenderingProgress — colored,
// redrawn in place, not intended to be consumed by another program).
//
// UI-facing only: render_episode.sh remains the documented standalone
// terminal tool (see README.md) and is untouched by this — this script is
// invoked ONLY from ui/server.py's ws_run_render for the plain-video
// format, mirroring the same __TOTAL__/__PROGRESS__/__EXIT_CODE__
// sentinel-line convention pipeline/export_davinci.py already established
// for the DaVinci export path, so ui/server.py's existing _stream_command
// parsing (and the frontend's existing progress bar) work unchanged for
// this path too — no new message types needed on either side.
//
// Usage: node render-with-progress.js <episode-folder> [WIDTHxHEIGHT]

const fs = require("fs");
const path = require("path");
const { bundle } = require("@remotion/bundler");
const { renderMedia, selectComposition } = require("@remotion/renderer");

const RENDERER_DIR = __dirname;

// See the `concurrency` option passed to renderMedia() below for why this
// is capped rather than using every core.
const RENDER_CONCURRENCY = Math.min(4, require("os").cpus().length);

// ui/server.py's _stream_command spawns this script without setting a cwd
// (unlike export_davinci.py's own subprocess.run(..., cwd=RENDERER_DIR)
// for ITS npx remotion render calls), so it inherits the server's cwd
// (ui/) by default — Remotion's bundler/renderer cache their headless-
// browser download relative to process.cwd(), not this script's own
// __dirname, which left a stray ui/.remotion/ cache directory behind
// (confirmed live). Explicit chdir here keeps that cache colocated with
// video-renderer/node_modules/.remotion — where it already was for every
// other render path — instead of leaking into ui/.
process.chdir(RENDERER_DIR);

async function main() {
    const episodeFolder = process.argv[2];
    const resolution = process.argv[3];

    if (!episodeFolder) {
        console.error("Usage: node render-with-progress.js <episode-folder> [WIDTHxHEIGHT]");
        process.exit(1);
    }

    let width;
    let height;

    if (resolution) {
        const match = resolution.match(/^(\d+)x(\d+)$/);
        if (!match) {
            console.error(`ERROR: resolution must be WIDTHxHEIGHT, e.g. 3840x2160 (got "${resolution}")`);
            process.exit(1);
        }
        width = Number(match[1]);
        height = Number(match[2]);
        console.log(`Resolution override: ${width}x${height}`);
    }

    const outputDir = path.join(episodeFolder, "rendered");
    const episodeName = path.basename(episodeFolder);
    const output = path.join(outputDir, `${episodeName}.mp4`);

    // render_episode.sh's own `mkdir -p "$OUTPUT_DIR"` — renderMedia does
    // not create the output directory itself.
    fs.mkdirSync(outputDir, { recursive: true });

    console.log("Rendering episode:");
    console.log(episodeFolder);

    // Same bundling step `npx remotion render` performs internally —
    // entryPoint matches remotion.config.ts's own root (src/index.ts, the
    // registerRoot call render_episode.sh's CLI invocation resolves the
    // same way via the project's remotion.config.ts).
    const bundleLocation = await bundle({
        entryPoint: path.join(RENDERER_DIR, "src", "index.ts"),
        onProgress: () => {
            // Bundling's own onProgress reports webpack's internal
            // progress-plugin percentage, NOT a clean 0-1 fraction
            // (confirmed live: raw values like 10000, nowhere near 0-1) —
            // not a stable/documented value worth surfacing as a real
            // number, so this stays a no-op. Bundling is a small, fast
            // fraction of total render time (webpack compiling the
            // composition once) and has no frame count to report progress
            // against anyway, unlike the __PROGRESS__ line below.
        },
    });

    // selectComposition's return value IS the VideoConfig directly (not
    // wrapped in a {composition} object — confirmed live: destructuring it
    // that way crashed with "Cannot read properties of undefined" on the
    // very next line).
    const composition = await selectComposition({
        serveUrl: bundleLocation,
        id: "Episode",
        inputProps: {},
    });

    const totalFrames = composition.durationInFrames;
    console.log(`__TOTAL__${totalFrames}`);

    let lastReportedFrame = -1;

    await renderMedia({
        composition: width && height ? { ...composition, width, height } : composition,
        serveUrl: bundleLocation,
        codec: "h264",
        // remotion.config.ts's own Config.setVideoImageFormat("jpeg")/
        // Config.setOverwriteOutput(true) do NOT apply to the Node.js API
        // (that file's own top comment says so explicitly) — replicated
        // here directly so this path matches render_episode.sh's actual
        // behavior instead of silently falling back to renderMedia's own
        // defaults (png images, no overwrite).
        imageFormat: "jpeg",
        overwrite: true,
        outputLocation: output,
        // Each unit of concurrency opens its own headless-Chromium tab to
        // render frames in parallel (mirrors export_davinci.py's
        // ThreadPoolExecutor clip parallelism, same idea applied at the
        // frame level instead of the clip level — this path has only one
        // composition, so there's no clip boundary to parallelize across).
        // Capped well below the full core count: browser tabs are far
        // heavier than the DaVinci path's CLI subprocesses (each one is a
        // full Chromium renderer process), so naively using all 12 cores
        // risks memory pressure/thrashing rather than a clean speedup.
        concurrency: RENDER_CONCURRENCY,
        onProgress: ({ renderedFrames }) => {
            // renderMedia's onProgress fires far more often than once per
            // frame (encoding/muxing ticks too) — only emit a line when
            // the rendered-frame count actually advances, so this doesn't
            // flood the websocket with duplicate __PROGRESS__ lines the
            // way a naive "print on every callback" would (the DaVinci
            // path's __PROGRESS__ is genuinely one-per-clip; this keeps
            // the same "one line per real unit of progress" contract for
            // a frame-based render instead of a clip-based one).
            if (renderedFrames !== lastReportedFrame) {
                lastReportedFrame = renderedFrames;
                console.log(`__PROGRESS__${renderedFrames}/${totalFrames}`);
            }
        },
    });

    console.log("");
    console.log("================================");
    console.log("Render completed");
    console.log("Output:");
    console.log(output);
    console.log("================================");
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
