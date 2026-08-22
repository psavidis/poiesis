import { describe, expect, it } from "vitest";

import { imageMotionScale } from "./BackgroundLayer";

// imageMotionScale drives a static image background's slow zoom drift
// (BackgroundLayer.tsx) — a regression here silently flattens or
// over-amplifies every image background's motion at once.
describe("imageMotionScale", () => {
    it("returns 1 (no motion) when motion is absent, none, or the span has no duration", () => {
        expect(imageMotionScale(undefined, "3", 10, 300)).toBe(1);
        expect(imageMotionScale("none", "3", 10, 300)).toBe(1);
        expect(imageMotionScale("zoom-in", "3", 10, 0)).toBe(1);
    });

    it("zoom-in starts at 1 and ends at the speed's max scale", () => {
        expect(imageMotionScale("zoom-in", "3", 0, 300)).toBe(1);
        expect(imageMotionScale("zoom-in", "3", 300, 300)).toBeCloseTo(2.016);
    });

    it("zoom-out starts at the speed's max scale and ends at 1", () => {
        expect(imageMotionScale("zoom-out", "3", 0, 300)).toBeCloseTo(2.016);
        expect(imageMotionScale("zoom-out", "3", 300, 300)).toBe(1);
    });

    it("palindrome peaks at the midpoint and returns to 1 by the end", () => {
        expect(imageMotionScale("palindrome", "3", 0, 300)).toBe(1);
        expect(imageMotionScale("palindrome", "3", 150, 300)).toBeCloseTo(2.016);
        expect(imageMotionScale("palindrome", "3", 300, 300)).toBe(1);
    });

    it("defaults to level 3 when speed is omitted", () => {
        expect(imageMotionScale("zoom-in", undefined, 300, 300)).toBeCloseTo(2.016);
    });

    // Regression for #119: the old three-preset scale (subtle/normal/
    // strong) topped out at 1.4 for "strong", which still read as
    // barely-there motion against a background span running a whole
    // chapter (#91). Five numbered levels replace it, each exactly 20%
    // faster than the previous, with level "1" set to the OLD "strong"
    // value — the whole scale shifts up from what used to be the fastest
    // option, so the new level "5" is unmistakably fast.
    it("each numbered level is exactly 20% faster than the previous", () => {
        const levels = ["1", "2", "3", "4", "5"] as const;
        const scales = levels.map((level) => imageMotionScale("zoom-in", level, 300, 300));

        expect(scales[0]).toBeCloseTo(1.4);
        for (let i = 1; i < scales.length; i++) {
            expect(scales[i]).toBeCloseTo(scales[i - 1] * 1.2);
        }
        expect(scales[4]).toBeCloseTo(2.903, 2);
    });

    // The legacy subtle/normal/strong values must keep resolving to a
    // valid scale (not throw, not fall back to 1x/no-motion) so an
    // already-saved episode's background motion doesn't silently break —
    // see BackgroundImageMotionSpeed's own doc comment for why these
    // stay in the type instead of requiring a data migration.
    it("legacy subtle/normal/strong values still resolve to a valid scale", () => {
        expect(imageMotionScale("zoom-in", "subtle", 300, 300)).toBeCloseTo(1.4);
        expect(imageMotionScale("zoom-in", "normal", 300, 300)).toBeCloseTo(2.016);
        expect(imageMotionScale("zoom-in", "strong", 300, 300)).toBeCloseTo(1.4);
    });
});
