import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { brand } from "./brand";

// Utilitarian and constant, unlike EmphasisText's animated callout — captions
// appear on nearly every frame of the episode, so a spring/scale entrance
// on each one would be exhausting rather than intentional.
export const CaptionText = ({ text }: { text: string }) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const opacity = interpolate(
        frame,
        [0, 4, durationInFrames - 4, durationInFrames],
        [0, 1, 1, 0],
        {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        }
    );

    return (
        <AbsoluteFill
            style={{
                justifyContent: "flex-end",
                alignItems: "center",
                paddingBottom: "6%",
                pointerEvents: "none",
            }}
        >
            <div
                style={{
                    opacity,
                    maxWidth: "82%",
                    backgroundColor: brand.colors.overlayBackground,
                    borderRadius: brand.radii.chip,
                    padding: "10px 24px",
                }}
            >
                <div
                    style={{
                        fontFamily: brand.fonts.family,
                        fontSize: 32,
                        fontWeight: 500,
                        color: brand.colors.text,
                        textAlign: "center",
                        lineHeight: 1.3,
                    }}
                >
                    {text}
                </div>
            </div>
        </AbsoluteFill>
    );
};
