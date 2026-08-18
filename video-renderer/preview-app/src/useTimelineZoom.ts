import { useEffect, useState } from "react";

// Same geometric zoom-step/cap rationale every bar (Beats/Images/Moments/
// Scenes) used to define locally before this was unified (#86) — a single
// shared zoom level across all four timeline bars instead of each one
// tracking (and controlling) its own, since they all describe positions
// on the exact same underlying timeline anyway.
const ZOOM_STEP = 1.6;
const MAX_ZOOM = 20;
const MIN_ZOOM = 1;

function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
}

export interface TimelineZoom {
    zoom: number;
    windowFrames: number;
    windowStartFrame: number;
    frameToPct: (frame: number) => number;
    playheadPct: number;
    playheadVisible: boolean;
    // Re-centers the window on centerFrame at nextZoom — used both by the
    // shared Zoom in/out buttons (centered on the current window) and by
    // each bar's own "select this segment" handler (centered on the
    // segment just selected), same call shape as every bar's own former
    // local applyZoom.
    applyZoom: (nextZoom: number, centerFrame: number) => void;
    zoomIn: () => void;
    zoomOut: () => void;
    resetZoom: () => void;
    // Convenience for a bar's own "auto-zoom in on select" handler —
    // zooms to at least 4x (or stays at the current zoom if already
    // beyond that), centered on centerFrame. Mirrors the
    // clamp(zoom > 1 ? zoom : 4, ...) line every bar used to repeat.
    zoomToAtLeast4x: (centerFrame: number) => void;
}

// Single shared zoom/pan window driving every timeline bar (#86) — lives
// once in EpisodeWorkspace and gets threaded down as props, replacing each
// bar's own independent zoom state so scrolling/zooming one bar keeps all
// of them in sync (they're all views onto the same timeline) and so there
// is exactly one Zoom in/out/Reset control row instead of one per bar.
export function useTimelineZoom(totalFrames: number, currentFrame: number): TimelineZoom {
    const [zoom, setZoom] = useState(1);
    // Fraction of totalFrames where the visible window starts — 0 at full
    // zoom-out (whole episode), clamped so the window never extends past
    // either end once zoomed in.
    const [panStartPct, setPanStartPct] = useState(0);

    const windowFrames = totalFrames > 0 ? totalFrames / zoom : 0;
    const maxPanStartPct = 1 - windowFrames / Math.max(totalFrames, 1);
    const clampedPanStartPct = clamp(panStartPct, 0, Math.max(0, maxPanStartPct));
    const windowStartFrame = clampedPanStartPct * totalFrames;

    const frameToPct = (frame: number) => ((frame - windowStartFrame) / windowFrames) * 100;

    const applyZoom = (nextZoom: number, centerFrame: number) => {
        const clampedZoom = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
        const nextWindowFrames = totalFrames / clampedZoom;
        setZoom(clampedZoom);
        setPanStartPct(centerFrame / totalFrames - nextWindowFrames / totalFrames / 2);
    };

    const zoomIn = () => applyZoom(zoom * ZOOM_STEP, windowStartFrame + windowFrames / 2);
    const zoomOut = () => applyZoom(zoom / ZOOM_STEP, windowStartFrame + windowFrames / 2);
    const resetZoom = () => {
        setZoom(1);
        setPanStartPct(0);
    };
    const zoomToAtLeast4x = (centerFrame: number) => {
        applyZoom(clamp(zoom > 1 ? zoom : 4, MIN_ZOOM, MAX_ZOOM), centerFrame);
    };

    // Follows playback while zoomed in (ported from SceneBar's #85 fix to
    // every bar) — without this, the window stays wherever it was
    // centered at zoom time and the playhead runs off the edge and
    // disappears as soon as playback advances past it, instead of the
    // strip panning to keep up. Only re-centers once the playhead
    // actually leaves the window (not on every frame).
    useEffect(() => {
        if (zoom <= 1) return;
        const outOfView = currentFrame < windowStartFrame || currentFrame > windowStartFrame + windowFrames;
        if (!outOfView) return;
        setPanStartPct(currentFrame / totalFrames - windowFrames / totalFrames / 2);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentFrame]);

    const playheadPct = clamp(frameToPct(currentFrame), 0, 100);
    const playheadVisible = currentFrame >= windowStartFrame && currentFrame <= windowStartFrame + windowFrames;

    return {
        zoom,
        windowFrames,
        windowStartFrame,
        frameToPct,
        playheadPct,
        playheadVisible,
        applyZoom,
        zoomIn,
        zoomOut,
        resetZoom,
        zoomToAtLeast4x,
    };
}

export { MAX_ZOOM, MIN_ZOOM };
