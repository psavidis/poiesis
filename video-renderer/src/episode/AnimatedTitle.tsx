import {
    AbsoluteFill,
    interpolate,
    spring,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

export const AnimatedTitle = ({ text }: { text: string }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();

    const scale = spring({
        frame,
        fps,
        config: {
            damping: 200,
        },
    });

    const opacity = interpolate(frame, [0, 10], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
    });

    return (
        <AbsoluteFill
            style={{
                backgroundColor: "#0b0b0f",
                justifyContent: "center",
                alignItems: "center",
            }}
        >
            <div
                style={{
                    opacity,
                    transform: `scale(${scale})`,
                    fontFamily: "sans-serif",
                    fontSize: 72,
                    fontWeight: 700,
                    color: "#ffffff",
                    textAlign: "center",
                    padding: "0 80px",
                }}
            >
                {text}
            </div>
        </AbsoluteFill>
    );
};
