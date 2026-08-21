import { describe, expect, it } from "vitest";

import { computeTransform } from "./MomentTreatments";

// computeTransform backs BottomCallout's configurable entrance (see
// MomentEntrance in types.ts — docs/specs/ai-assisted-editing-and-
// conversational-control.md section 7's animation-configuration
// prerequisite). Three pre-existing animation patterns, exposed as a
// choice for the first time rather than each being hardcoded per
// component.
describe("computeTransform", () => {
    it("returns no transform for fade (opacity-only, no motion)", () => {
        expect(computeTransform("fade", 0, 30)).toBe("none");
        expect(computeTransform("fade", 15, 30)).toBe("none");
    });

    it("returns a scale(...) transform for scale", () => {
        const result = computeTransform("scale", 10, 30);
        expect(result.startsWith("scale(")).toBe(true);
    });

    it("returns a translateY(...) transform for slide", () => {
        const result = computeTransform("slide", 10, 30);
        expect(result.startsWith("translateY(")).toBe(true);
        expect(result.endsWith("px)")).toBe(true);
    });

    it("slide settles toward translateY(0px) as the spring completes", () => {
        // At a frame comfortably past the spring's settle time, translateY
        // should be at (or extremely close to) 0 — the entrance has
        // finished, matching AnimatedTitle.tsx's own spring settling
        // behavior at the same damping config.
        const result = computeTransform("slide", 60, 30);
        const match = /translateY\(([-\d.]+)px\)/.exec(result);
        expect(match).not.toBeNull();
        expect(Math.abs(Number(match![1]))).toBeLessThan(0.5);
    });

    it("scale settles toward scale(1) as the spring completes", () => {
        const result = computeTransform("scale", 60, 30);
        const match = /scale\(([-\d.]+)\)/.exec(result);
        expect(match).not.toBeNull();
        expect(Math.abs(Number(match![1]) - 1)).toBeLessThan(0.05);
    });

    it("scale and slide both start away from their settled value at frame 0", () => {
        // Confirms the entrance actually animates (frame 0 isn't already
        // at the settled value) — a regression guard against an entrance
        // that silently does nothing.
        const scaleAtZero = /scale\(([-\d.]+)\)/.exec(computeTransform("scale", 0, 30))![1];
        expect(Number(scaleAtZero)).not.toBeCloseTo(1, 1);

        const slideAtZero = /translateY\(([-\d.]+)px\)/.exec(computeTransform("slide", 0, 30))![1];
        expect(Number(slideAtZero)).not.toBeCloseTo(0, 1);
    });
});
