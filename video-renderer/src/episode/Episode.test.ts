import { describe, expect, it } from "vitest";

import { CROSSFADE_TRANSITION_FRAMES, clampedMomentDuration, crossfadeInFramesForScene, layoutWindowsForScene } from "./Episode";
import { TRANSITION_FRAMES } from "./timing";
import type { MomentScene, PresenterScene } from "./types";

const presenterScene = (overrides: Partial<PresenterScene> = {}): PresenterScene => ({
    type: "presenter",
    id: "scene-001",
    videoId: "001",
    sourceStartFrame: 0,
    sourceEndFrame: 900,
    timelineStartFrame: 0,
    durationInFrames: 900,
    effects: { captions: true, transition: "none" },
    ...overrides,
});

const sideMoment = (overrides: Partial<MomentScene> = {}): MomentScene => ({
    type: "moment",
    id: "scene-moment-0",
    treatment: "side-text",
    text: "hello",
    presenterSide: "left",
    parentSceneId: "scene-001",
    offsetInParentFrames: 300,
    durationInFrames: 150,
    ...overrides,
});

describe("layoutWindowsForScene", () => {
    it("returns no windows when the scene has no moments", () => {
        const scene = presenterScene();

        expect(layoutWindowsForScene(scene, [])).toEqual([]);
    });

    it("ignores moments belonging to a different parent scene", () => {
        const scene = presenterScene({ id: "scene-001" });
        const moment = sideMoment({ parentSceneId: "scene-999" });

        expect(layoutWindowsForScene(scene, [moment])).toEqual([]);
    });

    it("ignores bottom-callout moments (no presenterSide, presenter never moves)", () => {
        const scene = presenterScene();
        const moment = sideMoment({ treatment: "bottom-callout", presenterSide: undefined });

        expect(layoutWindowsForScene(scene, [moment])).toEqual([]);
    });

    it("pads a moment's own window by TRANSITION_FRAMES on both sides", () => {
        const scene = presenterScene({ durationInFrames: 900 });
        const moment = sideMoment({ offsetInParentFrames: 300, durationInFrames: 150, presenterSide: "left" });

        const windows = layoutWindowsForScene(scene, [moment]);

        expect(windows).toEqual([
            { start: 300 - TRANSITION_FRAMES, end: 300 + 150 + TRANSITION_FRAMES, side: "left" },
        ]);
    });

    it("clamps the padded window to the scene's own bounds — this is the fix for the " +
        "bug where the presenter used to shift for a whole (possibly 60s+) scene instead " +
        "of just around the moment's actual on-screen span", () => {
        const scene = presenterScene({ durationInFrames: 100 });

        // moment starts 5 frames in and runs almost to the end — padding
        // would naturally overshoot both edges of the scene
        const moment = sideMoment({ offsetInParentFrames: 5, durationInFrames: 90, presenterSide: "right" });

        const windows = layoutWindowsForScene(scene, [moment]);

        expect(windows).toEqual([{ start: 0, end: 100, side: "right" }]);
    });

    it("returns multiple windows sorted by start frame", () => {
        const scene = presenterScene({ durationInFrames: 2000 });
        const late = sideMoment({ id: "m-late", offsetInParentFrames: 1000, durationInFrames: 100, presenterSide: "right" });
        const early = sideMoment({ id: "m-early", offsetInParentFrames: 100, durationInFrames: 100, presenterSide: "left" });

        const windows = layoutWindowsForScene(scene, [late, early]);

        expect(windows.map((w) => w.side)).toEqual(["left", "right"]);
        expect(windows[0].start).toBeLessThan(windows[1].start);
    });
});

describe("clampedMomentDuration", () => {
    it("returns the moment's own duration unchanged when it fits well within the parent", () => {
        const scene = presenterScene({ durationInFrames: 900 });
        const moment = sideMoment({ offsetInParentFrames: 300, durationInFrames: 150 });

        expect(clampedMomentDuration(moment, scene)).toBe(150);
    });

    it("clamps content to stay in sync with layoutWindowsForScene's own clamped " +
        "window end for the same near-end-of-scene moment — this is the fix for the " +
        "bug where content could outlive the presenter's already-clamped slide-back " +
        "animation", () => {
        const scene = presenterScene({ durationInFrames: 100 });
        // moment starts 5 frames in and claims a duration that would run
        // past the scene's own end once TRANSITION_FRAMES is added
        const moment = sideMoment({ offsetInParentFrames: 5, durationInFrames: 90, presenterSide: "right" });

        const windows = layoutWindowsForScene(scene, [moment]);
        const clampedDuration = clampedMomentDuration(moment, scene);

        // The presenter's own window is clamped to the scene bounds (see
        // the "clamps the padded window to the scene's own bounds" test
        // above) — the moment's content must never extend past that same
        // scene bound either.
        expect(moment.offsetInParentFrames + clampedDuration).toBeLessThanOrEqual(scene.durationInFrames);
        expect(windows[0].end).toBe(scene.durationInFrames);
        expect(clampedDuration).toBe(90); // min(requested 90, 100 - 5 room) = 90, already fits
    });

    it("clamps content that individually WOULD overflow the parent's remaining room", () => {
        const scene = presenterScene({ durationInFrames: 100 });
        // requests more than the 20 frames actually remaining after offset
        const moment = sideMoment({ offsetInParentFrames: 80, durationInFrames: 50, presenterSide: "right" });

        expect(clampedMomentDuration(moment, scene)).toBe(20); // 100 - 80
    });

    it("never returns a negative duration even if the moment starts past the parent's own end", () => {
        const scene = presenterScene({ durationInFrames: 100 });
        const moment = sideMoment({ offsetInParentFrames: 150, durationInFrames: 50 });

        expect(clampedMomentDuration(moment, scene)).toBe(0);
    });
});

describe("crossfadeInFramesForScene", () => {
    it("returns 0 when there is no previous scene (first scene in the episode)", () => {
        const scene = presenterScene({ effects: { captions: true, transition: "crossfade" } });

        expect(crossfadeInFramesForScene(scene, undefined)).toBe(0);
    });

    it("returns 0 when the scene's own transition is \"none\" (today's default/hard cut)", () => {
        const scene = presenterScene({ effects: { captions: true, transition: "none" } });
        const previous = presenterScene({ id: "scene-000" });

        expect(crossfadeInFramesForScene(scene, previous)).toBe(0);
    });

    it("returns CROSSFADE_TRANSITION_FRAMES when both scenes have enough room", () => {
        const scene = presenterScene({
            sourceStartFrame: 500,
            effects: { captions: true, transition: "crossfade" },
        });
        const previous = presenterScene({ id: "scene-000", durationInFrames: 900 });

        expect(crossfadeInFramesForScene(scene, previous)).toBe(CROSSFADE_TRANSITION_FRAMES);
    });

    it("clamps to the incoming scene's own sourceStartFrame — can't borrow frames " +
        "before the start of the source video", () => {
        const scene = presenterScene({
            sourceStartFrame: 3, // less than CROSSFADE_TRANSITION_FRAMES
            effects: { captions: true, transition: "crossfade" },
        });
        const previous = presenterScene({ id: "scene-000", durationInFrames: 900 });

        expect(crossfadeInFramesForScene(scene, previous)).toBe(3);
    });

    it("clamps to the previous scene's own durationInFrames — can't overlap past " +
        "where the previous scene itself starts", () => {
        const scene = presenterScene({
            sourceStartFrame: 500,
            effects: { captions: true, transition: "crossfade" },
        });
        const previous = presenterScene({ id: "scene-000", durationInFrames: 4 }); // very short clip

        expect(crossfadeInFramesForScene(scene, previous)).toBe(4);
    });

    it("never returns a negative number even if both clamps are 0", () => {
        const scene = presenterScene({
            sourceStartFrame: 0,
            effects: { captions: true, transition: "crossfade" },
        });
        const previous = presenterScene({ id: "scene-000", durationInFrames: 900 });

        expect(crossfadeInFramesForScene(scene, previous)).toBe(0);
    });
});
