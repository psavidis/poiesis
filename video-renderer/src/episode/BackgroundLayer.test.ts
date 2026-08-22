import { describe, expect, it } from "vitest";

import { imageMotionScale } from "./BackgroundLayer";

// imageMotionScale drives a static image background's slow zoom drift
// (BackgroundLayer.tsx) — a regression here silently flattens or
// over-amplifies every image background's motion at once.
describe("imageMotionScale", () => {
    it("returns 1 (no motion) when motion is absent, none, or the span has no duration", () => {
        expect(imageMotionScale(undefined, "normal", 10, 300)).toBe(1);
        expect(imageMotionScale("none", "normal", 10, 300)).toBe(1);
        expect(imageMotionScale("zoom-in", "normal", 10, 0)).toBe(1);
    });

    it("zoom-in starts at 1 and ends at the speed's max scale", () => {
        expect(imageMotionScale("zoom-in", "normal", 0, 300)).toBe(1);
        expect(imageMotionScale("zoom-in", "normal", 300, 300)).toBeCloseTo(1.25);
    });

    it("zoom-out starts at the speed's max scale and ends at 1", () => {
        expect(imageMotionScale("zoom-out", "normal", 0, 300)).toBeCloseTo(1.25);
        expect(imageMotionScale("zoom-out", "normal", 300, 300)).toBe(1);
    });

    it("palindrome peaks at the midpoint and returns to 1 by the end", () => {
        expect(imageMotionScale("palindrome", "normal", 0, 300)).toBe(1);
        expect(imageMotionScale("palindrome", "normal", 150, 300)).toBeCloseTo(1.25);
        expect(imageMotionScale("palindrome", "normal", 300, 300)).toBe(1);
    });

    it("defaults to the normal speed preset when speed is omitted", () => {
        expect(imageMotionScale("zoom-in", undefined, 300, 300)).toBeCloseTo(1.25);
    });

    // Regression for #91: "normal"/"strong" were raised from their
    // original 1.15/1.25 — even "strong" read as barely noticeable motion
    // against a background span running a whole chapter, since the drift
    // always completes over the WHOLE span regardless of how long it is.
    // "subtle" is deliberately unchanged (the original pre-speed-control
    // amount, kept for anyone who specifically wants the gentler drift).
    it("strong is clearly more pronounced than normal, and normal more than subtle", () => {
        const subtle = imageMotionScale("zoom-in", "subtle", 300, 300);
        const normal = imageMotionScale("zoom-in", "normal", 300, 300);
        const strong = imageMotionScale("zoom-in", "strong", 300, 300);

        expect(subtle).toBeCloseTo(1.08);
        expect(normal).toBeCloseTo(1.25);
        expect(strong).toBeCloseTo(1.4);
        expect(strong).toBeGreaterThan(normal);
        expect(normal).toBeGreaterThan(subtle);
    });
});
