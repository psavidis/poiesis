import {
    AbsoluteFill,
    interpolate,
    spring,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

import { BackgroundGrid, brand } from "./brand";

// Entrance phase lengths, in frames — the exit phase mirrors these exactly
// (same durations, same easing, played backward) so a shortened title
// still gets a full, symmetric in/out rather than an abrupt cut, and a
// resize (#83) never has to touch these numbers directly: they're always
// measured from each end of whatever durationInFrames currently is.
const OPACITY_PHASE_FRAMES = 10;
const ACCENT_START_DELAY_FRAMES = 4;
const ACCENT_GROW_FRAMES = 16; // matches the original interpolate(frame, [4, 20], ...) span

export const AnimatedTitle = ({
    text,
    durationInFrames,
}: {
    text: string;
    durationInFrames: number;
}) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();

    // Exit mirrors entrance frame-for-frame from the end, but the two
    // phases are clamped to never overlap on a very short (drag-shrunk)
    // title — each gets at most half the total duration, so a title
    // shrunk below ~2x the entrance length still animates cleanly instead
    // of the in/out phases fighting over the same frames.
    const accentPhaseFrames = Math.min(ACCENT_START_DELAY_FRAMES + ACCENT_GROW_FRAMES, durationInFrames / 2);
    const opacityPhaseFrames = Math.min(OPACITY_PHASE_FRAMES, durationInFrames / 2);
    const accentStartDelay = Math.min(ACCENT_START_DELAY_FRAMES, accentPhaseFrames);
    const accentGrowFrames = accentPhaseFrames - accentStartDelay;

    const entrance = spring({
        frame,
        fps,
        config: {
            damping: 200,
        },
    });
    const exitFrame = durationInFrames - 1 - frame;
    const exitSpring = spring({
        frame: exitFrame,
        fps,
        config: {
            damping: 200,
        },
    });

    const translateY = interpolate(Math.min(entrance, exitSpring), [0, 1], [24, 0]);
    const opacity = Math.min(
        interpolate(frame, [0, opacityPhaseFrames], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        }),
        interpolate(exitFrame, [0, opacityPhaseFrames], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        })
    );

    const accentWidth = Math.min(
        interpolate(frame, [accentStartDelay, accentStartDelay + accentGrowFrames], [0, 96], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        }),
        interpolate(exitFrame, [accentStartDelay, accentStartDelay + accentGrowFrames], [0, 96], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        })
    );

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
