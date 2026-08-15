import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { brand } from "./brand";

// Utilitarian and constant, unlike BottomCallout's animated entrance
// (MomentTreatments.tsx) — captions appear on nearly every frame of the
// episode, so a spring/scale entrance on each one would be exhausting
// rather than intentional.
export const CaptionText = ({ text }: { text: string }) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    // Fade envelope needs 4 frames in + 4 out. Below 8 total frames (a
    // caption clipped to a sliver by a scene trim boundary) there isn't
    // room for a separate fade-in and fade-out breakpoint without the
    // interpolate() input range colliding, so just cut straight to full
    // opacity instead.
    const fadeFrames = Math.min(4, Math.floor((durationInFrames - 1) / 2));

    const opacity = fadeFrames <= 0
        ? 1
        : interpolate(
            frame,
            [0, fadeFrames, durationInFrames - fadeFrames, durationInFrames],
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
