import {
    AbsoluteFill,
    Img,
    interpolate,
    spring,
    staticFile,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

import { brand } from "./brand";

// The bottom-center callout — ported as-is from the pre-moments EmphasisText
// component. Requires the parent presenter scene's layout to be "center"
// (the presenter still fills the frame; this is a pure overlay, same as
// before moments existed).
export const BottomCallout = ({ text }: { text: string }) => {
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

// Shared positioning for the "content fills whichever side the presenter
// isn't occupying" treatments. presenterOnLeft mirrors the content to the
// opposite side, matching Episode.tsx's LAYOUT_GEOMETRY split (presenter
// stays at full on-screen scale in a 72%-wide window, content in the
// remaining 28%).
const sideContentStyle = (presenterOnLeft: boolean): React.CSSProperties => ({
    position: "absolute",
    top: 0,
    bottom: 0,
    [presenterOnLeft ? "right" : "left"]: 0,
    width: "28%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "6%",
});

export const SideText = ({ text, presenterOnLeft }: { text: string; presenterOnLeft: boolean }) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    // Slides in from its own edge (the side the presenter just vacated)
    // rather than fading in place, so it visually arrives together with the
    // presenter's own slide animation instead of feeling like an unrelated
    // overlay.
    const translateX = interpolate(
        frame,
        [0, 16],
        [presenterOnLeft ? -40 : 40, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const opacity = interpolate(
        frame,
        [0, 12, durationInFrames - 10, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <div style={sideContentStyle(presenterOnLeft)}>
                <div
                    style={{
                        opacity,
                        transform: `translateX(${translateX}px)`,
                        fontFamily: brand.fonts.family,
                        fontSize: 52,
                        fontWeight: 700,
                        lineHeight: 1.2,
                        color: brand.colors.text,
                        textAlign: presenterOnLeft ? "right" : "left",
                    }}
                >
                    {text}
                </div>
            </div>
        </AbsoluteFill>
    );
};

export const SideImage = ({
                               path,
                               caption,
                               presenterOnLeft,
                           }: {
    path: string;
    caption?: string;
    presenterOnLeft: boolean;
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const translateX = interpolate(
        frame,
        [0, 16],
        [presenterOnLeft ? -40 : 40, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const opacity = interpolate(
        frame,
        [0, 12, durationInFrames - 10, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <div style={sideContentStyle(presenterOnLeft)}>
                <div
                    style={{
                        opacity,
                        transform: `translateX(${translateX}px)`,
                        width: "100%",
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        gap: 16,
                    }}
                >
                    <div
                        style={{
                            width: "100%",
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

                    {caption && (
                        <div
                            style={{
                                fontFamily: brand.fonts.family,
                                fontSize: 24,
                                fontWeight: 600,
                                color: brand.colors.textMuted,
                                textAlign: "center",
                            }}
                        >
                            {caption}
                        </div>
                    )}
                </div>
            </div>
        </AbsoluteFill>
    );
};
