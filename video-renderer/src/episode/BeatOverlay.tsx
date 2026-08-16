import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { brand } from "./brand";
import type { BeatKind } from "./types";

// Beats used to sit top-center (justifyContent: flex-start, 5% top
// padding), on the theory that a presenter framed center-and-tall only
// fills the top ~55-60% of frame, leaving a clear sliver above the
// hairline. Pixel-measured against a real rendered frame (see #36) and
// found that assumption didn't hold: the presenter's head/hair already
// spans up to ~58% of frame width by 150-200px down — well within where
// a beat chip's own rendered height reaches — so the chip visibly
// overlapped his head rather than sitting in clear background.
//
// Beats never move the presenter (unlike moments — see
// layoutWindowsForScene in Episode.tsx, which only reads MomentScene) and
// shouldn't start doing so: at up to twice the frequency of moments in a
// typical episode, that would turn a "light rhythm under the presenter"
// (see BeatScene's own doc comment in types.ts) into constant
// distracting motion. Instead, beats now sit to one side at roughly mid
// height — the same clear-space zone moments' own side content already
// uses (see MomentTreatments.tsx's sideContentStyle), reliably outside
// the presenter's own footprint (roughly the center 40-60% of frame at
// this framing) without requiring him to make room.
function beatContainerStyle(side: "left" | "right"): React.CSSProperties {
    return {
        justifyContent: "center",
        alignItems: side === "left" ? "flex-start" : "flex-end",
        paddingLeft: side === "left" ? "6%" : 0,
        paddingRight: side === "right" ? "6%" : 0,
        pointerEvents: "none",
    };
}

// A handful of small bundled icons for "icon-accent" beats — a static map
// keyed by a short string (BeatScene.icon), not an open-ended asset
// reference, matching the "small, seed the set later" scope from the
// design. Pure inline SVG so there's no extra asset file to index/ship.
const ICONS: Record<string, React.ReactNode> = {
    arrow: (
        <svg width={28} height={28} viewBox="0 0 24 24" fill="none">
            <path d="M4 12h14M13 6l6 6-6 6" stroke={brand.colors.accent} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    ),
    check: (
        <svg width={28} height={28} viewBox="0 0 24 24" fill="none">
            <path d="M4 12.5l5 5L20 6" stroke={brand.colors.accent} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    ),
    warning: (
        <svg width={28} height={28} viewBox="0 0 24 24" fill="none">
            <path d="M12 3l10 18H2L12 3z" stroke={brand.colors.accent} strokeWidth={2.5} strokeLinejoin="round" />
            <line x1={12} y1={10} x2={12} y2={14} stroke={brand.colors.accent} strokeWidth={2.5} strokeLinecap="round" />
            <circle cx={12} cy={17} r={1.2} fill={brand.colors.accent} />
        </svg>
    ),
    gear: (
        <svg width={28} height={28} viewBox="0 0 24 24" fill="none">
            <circle cx={12} cy={12} r={3} stroke={brand.colors.accent} strokeWidth={2.5} />
            <path
                d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"
                stroke={brand.colors.accent}
                strokeWidth={2.5}
                strokeLinecap="round"
            />
        </svg>
    ),
};

const WordPop = ({ text }: { text: string }) => {
    const frame = useCurrentFrame();
    const { fps, durationInFrames } = useVideoConfig();

    const scale = spring({
        frame,
        fps,
        config: { damping: 14, mass: 0.4 },
    });

    const opacity = interpolate(
        frame,
        [0, 3, Math.max(3, durationInFrames - 5), durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
        <div
            style={{
                opacity,
                transform: `scale(${scale})`,
                backgroundColor: brand.colors.overlayBackground,
                borderRadius: brand.radii.chip,
                padding: "10px 28px",
                fontFamily: brand.fonts.family,
                fontSize: 46,
                fontWeight: 700,
                color: brand.colors.accent,
            }}
        >
            {text}
        </div>
    );
};

const Underline = ({ text }: { text: string }) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const opacity = interpolate(
        frame,
        [0, 3, Math.max(3, durationInFrames - 5), durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    // The line draws left-to-right under the word over the first ~40% of
    // the beat's own duration, then holds — a quick underline stroke, not
    // a lingering animation, since the beat itself is already short.
    const drawEnd = Math.max(1, Math.round(durationInFrames * 0.4));

    const lineScaleX = interpolate(
        frame,
        [0, drawEnd],
        [0, 1],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
        <div style={{ opacity, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
            <div
                style={{
                    fontFamily: brand.fonts.family,
                    fontSize: 46,
                    fontWeight: 700,
                    color: brand.colors.text,
                }}
            >
                {text}
            </div>
            <div
                style={{
                    width: "100%",
                    height: 4,
                    backgroundColor: brand.colors.accent,
                    borderRadius: 2,
                    transform: `scaleX(${lineScaleX})`,
                    transformOrigin: "left center",
                }}
            />
        </div>
    );
};

const IconAccent = ({ text, icon }: { text: string; icon?: string }) => {
    const frame = useCurrentFrame();
    const { fps, durationInFrames } = useVideoConfig();

    const scale = spring({
        frame,
        fps,
        config: { damping: 14, mass: 0.4 },
    });

    const opacity = interpolate(
        frame,
        [0, 3, Math.max(3, durationInFrames - 5), durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const resolvedIcon = icon ? ICONS[icon] : undefined;

    return (
        <div
            style={{
                opacity,
                transform: `scale(${scale})`,
                display: "flex",
                alignItems: "center",
                gap: 12,
                backgroundColor: brand.colors.overlayBackground,
                borderRadius: brand.radii.chip,
                padding: "10px 24px",
            }}
        >
            {resolvedIcon}
            <div
                style={{
                    fontFamily: brand.fonts.family,
                    fontSize: 40,
                    fontWeight: 700,
                    color: brand.colors.text,
                }}
            >
                {text}
            </div>
        </div>
    );
};

export const BeatOverlay = ({
    kind,
    text,
    icon,
    side,
}: {
    kind: BeatKind;
    text: string;
    icon?: string;
    side: "left" | "right";
}) => {
    return (
        <AbsoluteFill style={beatContainerStyle(side)}>
            {kind === "word-pop" && <WordPop text={text} />}
            {kind === "underline" && <Underline text={text} />}
            {kind === "icon-accent" && <IconAccent text={text} icon={icon} />}
        </AbsoluteFill>
    );
};
