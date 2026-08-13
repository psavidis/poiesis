import {
    AbsoluteFill,
    interpolate,
    spring,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

import { BackgroundGrid, brand } from "./brand";

export const AnimatedTitle = ({ text }: { text: string }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();

    const entrance = spring({
        frame,
        fps,
        config: {
            damping: 200,
        },
    });

    const translateY = interpolate(entrance, [0, 1], [24, 0]);
    const opacity = interpolate(frame, [0, 10], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
    });

    const accentWidth = interpolate(frame, [4, 20], [0, 96], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
    });

    return (
        <AbsoluteFill
            style={{
                backgroundColor: brand.colors.background,
                justifyContent: "center",
                alignItems: "center",
                overflow: "hidden",
            }}
        >
            <BackgroundGrid />

            <div
                style={{
                    opacity,
                    transform: `translateY(${translateY}px)`,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    padding: "0 100px",
                }}
            >
                <div
                    style={{
                        width: accentWidth,
                        height: 6,
                        backgroundColor: brand.colors.accent,
                        marginBottom: 28,
                        borderRadius: 3,
                    }}
                />

                <div
                    style={{
                        fontFamily: brand.fonts.family,
                        fontSize: 68,
                        fontWeight: 700,
                        letterSpacing: -0.5,
                        color: brand.colors.text,
                        textAlign: "center",
                        lineHeight: 1.15,
                    }}
                >
                    {text}
                </div>
            </div>
        </AbsoluteFill>
    );
};
