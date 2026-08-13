import {
    AbsoluteFill,
    interpolate,
    spring,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

import { brand } from "./brand";

export const EmphasisText = ({ text }: { text: string }) => {
    const frame = useCurrentFrame();
    const { fps, durationInFrames } = useVideoConfig();

    const scale = spring({
        frame,
        fps,
        config: {
            damping: 200,
        },
    });

    const opacity = interpolate(
        frame,
        [0, 8, durationInFrames - 8, durationInFrames],
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
                paddingBottom: "12%",
                pointerEvents: "none",
            }}
        >
            <div
                style={{
                    opacity,
                    transform: `scale(${scale})`,
                    display: "flex",
                    alignItems: "center",
                    maxWidth: "78%",
                    backgroundColor: brand.colors.overlayBackground,
                    borderLeft: `6px solid ${brand.colors.accent}`,
                    borderRadius: brand.radii.chip,
                    padding: "18px 32px",
                }}
            >
                <div
                    style={{
                        fontFamily: brand.fonts.family,
                        fontSize: 44,
                        fontWeight: 600,
                        color: brand.colors.text,
                        textAlign: "left",
                        lineHeight: 1.25,
                    }}
                >
                    {text}
                </div>
            </div>
        </AbsoluteFill>
    );
};
