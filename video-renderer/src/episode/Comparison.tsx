import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { brand } from "./brand";
import { TRANSITION_FRAMES } from "./timing";
import type { ComparisonData } from "./types";

// Unlike SideText/SideImage/SideTerms, the presenter never moves for this
// treatment — it stays centered/full-frame (see MomentTreatment in
// types.ts), so the two labels sit in fixed margins flanking the frame
// rather than in a single 28%-wide side panel. Each label slides in from
// its own outer edge, mirroring SideText's "arrive from the side you're
// on" choreography but applied symmetrically instead of to one side only.
const LABEL_WIDTH_PCT = 24;

const Label = ({
                   text,
                   side,
               }: {
    text: string;
    side: "left" | "right";
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const translateX = interpolate(
        frame,
        [0, TRANSITION_FRAMES],
        [side === "left" ? -40 : 40, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const opacity = interpolate(
        frame,
        [0, TRANSITION_FRAMES, durationInFrames - TRANSITION_FRAMES, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
        <div
            style={{
                position: "absolute",
                top: 0,
                bottom: 0,
                [side]: 0,
                width: `${LABEL_WIDTH_PCT}%`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: "6%",
            }}
        >
            <div
                style={{
                    opacity,
                    transform: `translateX(${translateX}px)`,
                    fontFamily: brand.fonts.family,
                    fontSize: 52,
                    fontWeight: 700,
                    lineHeight: 1.15,
                    color: brand.colors.text,
                    textAlign: "center",
                }}
            >
                {text}
            </div>
        </div>
    );
};

export const Comparison = ({ comparison }: { comparison: ComparisonData }) => {
    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <Label text={comparison.left} side="left" />
            <Label text={comparison.right} side="right" />
        </AbsoluteFill>
    );
};
