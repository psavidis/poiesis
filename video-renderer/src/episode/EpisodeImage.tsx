import {
    AbsoluteFill,
    Img,
    interpolate,
    staticFile,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

import { BackgroundGrid, brand } from "./brand";

const KenBurnsImage = ({ src }: { src: string }) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const scale = interpolate(
        frame,
        [0, durationInFrames],
        [1, 1.08],
        {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        }
    );

    return (
        <Img
            src={src}
            style={{
                width: "100%",
                height: "100%",
                objectFit: "contain",
                transform: `scale(${scale})`,
            }}
        />
    );
};

export const EpisodeImage = ({
                                  path,
                                  caption,
                                  display,
                              }: {
    path: string;
    caption?: string;
    display: "full" | "inset";
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const opacity = interpolate(
        frame,
        [0, 10, durationInFrames - 10, durationInFrames],
        [0, 1, 1, 0],
        {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        }
    );

    if (display === "inset") {
        return (
            <AbsoluteFill
                style={{
                    justifyContent: "flex-start",
                    alignItems: "flex-end",
                    padding: "6%",
                    pointerEvents: "none",
                }}
            >
                <div
                    style={{
                        opacity,
                        width: "38%",
                        aspectRatio: "1 / 1",
                        backgroundColor: brand.colors.overlayBackground,
                        border: `2px solid ${brand.colors.accent}`,
                        borderRadius: brand.radii.frame,
                        padding: 20,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        boxShadow: "0 12px 32px rgba(0, 0, 0, 0.45)",
                    }}
                >
                    <Img
                        src={staticFile(path)}
                        style={{
                            maxWidth: "100%",
                            maxHeight: "100%",
                            objectFit: "contain",
                            borderRadius: 6,
                        }}
                    />
                </div>
            </AbsoluteFill>
        );
    }

    return (
        <AbsoluteFill
            style={{
                backgroundColor: brand.colors.background,
                justifyContent: "center",
                alignItems: "center",
                opacity,
                overflow: "hidden",
            }}
        >
            <BackgroundGrid />

            <div
                style={{
                    width: "82%",
                    height: "82%",
                    border: `2px solid ${brand.colors.accent}`,
                    borderRadius: brand.radii.frame,
                    overflow: "hidden",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    boxShadow: "0 20px 48px rgba(0, 0, 0, 0.5)",
                }}
            >
                <KenBurnsImage src={staticFile(path)} />
            </div>

            {caption && (
                <AbsoluteFill
                    style={{
                        justifyContent: "flex-end",
                        alignItems: "center",
                        paddingBottom: "6%",
                    }}
                >
                    <div
                        style={{
                            fontFamily: brand.fonts.family,
                            fontSize: 32,
                            fontWeight: 600,
                            color: brand.colors.text,
                            textAlign: "center",
                            padding: "12px 32px",
                            borderRadius: brand.radii.chip,
                            backgroundColor: brand.colors.overlayBackground,
                            borderLeft: `4px solid ${brand.colors.accent}`,
                            maxWidth: "80%",
                        }}
                    >
                        {caption}
                    </div>
                </AbsoluteFill>
            )}
        </AbsoluteFill>
    );
};
