import { describe, expect, it } from "vitest";

import { resolveBoxStyle, LAYOUT_GEOMETRY, SIDE_CONTENT_WIDTH_PCT } from "./timing";
import { sideContentStyle } from "./MomentTreatments";

// resolveBoxStyle backs every treatment's box-override support (#77) — a
// human-set box wins when present, otherwise the treatment's own default
// geometry renders exactly as before this field existed.
describe("resolveBoxStyle", () => {
    const defaultGeometry = { topPct: 8, leftPct: 6, widthPct: 62, heightPct: 34 };

    it("uses the default geometry when no box override is set", () => {
        expect(resolveBoxStyle(defaultGeometry, undefined)).toEqual({
            position: "absolute",
            top: "8%",
            left: "6%",
            width: "62%",
            height: "34%",
        });
    });

    it("uses the override box when present, ignoring the default entirely", () => {
        const box = { xPct: 10, yPct: 20, widthPct: 50, heightPct: 40 };

        expect(resolveBoxStyle(defaultGeometry, box)).toEqual({
            position: "absolute",
            top: "20%",
            left: "10%",
            width: "50%",
            height: "40%",
        });
    });
});

// sideContentStyle is the shared default-geometry source for every
// side-panel treatment (SideText, SideImage, DiagramBlock, CodeBlock
// "side", SideTerms) — a regression here would silently mis-position all
// of them at once.
describe("sideContentStyle", () => {
    it("without a box, flushes content to the side opposite the presenter (unchanged pre-#77 behavior)", () => {
        // presenter on the right (LAYOUT_GEOMETRY.right: leftPct 40) means
        // content occupies the LEFT side, from 0 to SIDE_CONTENT_WIDTH_PCT.
        const contentOnLeft = sideContentStyle(false, undefined);
        expect(contentOnLeft.left).toBe("0%");
        expect(contentOnLeft.width).toBe(`${SIDE_CONTENT_WIDTH_PCT}%`);

        // presenter on the left (LAYOUT_GEOMETRY.left: widthPct 60) means
        // content occupies the RIGHT side, flush against the presenter's
        // own right edge at 60%.
        const contentOnRight = sideContentStyle(true, undefined);
        expect(contentOnRight.left).toBe(`${100 - SIDE_CONTENT_WIDTH_PCT}%`);
        expect(contentOnRight.left).toBe(`${LAYOUT_GEOMETRY.left.widthPct}%`);
    });

    it("with a box, the override replaces the default geometry regardless of presenterOnLeft", () => {
        const box = { xPct: 5, yPct: 5, widthPct: 90, heightPct: 90 };

        const styled = sideContentStyle(true, box);
        expect(styled.left).toBe("5%");
        expect(styled.top).toBe("5%");
        expect(styled.width).toBe("90%");
        expect(styled.height).toBe("90%");
    });
});
