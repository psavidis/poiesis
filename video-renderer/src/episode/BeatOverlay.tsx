import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { brand } from "./brand";
import type { BeatKind } from "./types";

// A beat's total on-screen duration (durationInFrames) comes from
// pipeline/style.py's emphasis.defaultDurationFrames — 60 frames (2s at
// 30fps) as of #37. FADE_FRAMES is deliberately NOT a fraction of
// durationInFrames (e.g. "10% of whatever the style value is") — a fixed
// frame count keeps the ease-in/ease-out feeling the same regardless of
// what the style default happens to be tuned to later, the same way
// MomentTreatments.tsx's fade timing is pinned to TRANSITION_FRAMES
// rather than derived from each moment's own (widely varying) duration.
// 12 frames (0.4s) in, 12 out — leaves the phrase held at full opacity
// for whatever's left of durationInFrames in between, long enough to
// read a short phrase and connect it to what's being said (see #37;
// #35's easing pass established the same "eased, not linear" direction
// for motion elsewhere in the renderer).
const FADE_FRAMES = 12;

// Shared fade shape for all three beat kinds (WordPop/Underline/
// IconAccent) — eased in and out (not linear) so the animation reads as
// a deliberate, graceful arrival/departure rather than a mechanical
// on/off flicker, matching the eased motion direction #35 established
// for the presenter's own side-shift. Clamped so a beat shorter than
// 2*FADE_FRAMES (shouldn't happen with the current style default, but a
// human hand-editing durationInFrames down is possible) still fades
// in/out symmetrically instead of overshooting past the hold.
function beatOpacity(frame: number, durationInFrames: number): number {
    // interpolate() requires strictly increasing keyframes — clamped so a
    // duration shorter than 2*FADE_FRAMES (well below anything the
    // pipeline actually produces, which floors durationInFrames at 1, but
    // cheap insurance against a hand-edited scene-plan.json) still yields
    // two distinct fade points instead of a duplicate midpoint.
    const fadeIn = Math.max(1, Math.min(FADE_FRAMES, Math.floor(durationInFrames / 2)));
    const fadeOutStart = Math.max(fadeIn + 1, durationInFrames - FADE_FRAMES);

    return interpolate(
        frame,
        [0, fadeIn, fadeOutStart, Math.max(fadeOutStart + 1, durationInFrames)],
        [0, 1, 1, 0],
        { easing: Easing.inOut(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );
}

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

    const opacity = beatOpacity(frame, durationInFrames);

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

    const opacity = beatOpacity(frame, durationInFrames);

    // The line draws left-to-right under the word, then holds — a quick
    // stroke, not a lingering animation. Pinned to FADE_FRAMES (not a
    // percentage of durationInFrames) for the same reason beatOpacity's
    // fade timing is: a percentage-based draw would slow down every time
    // the style default's hold duration is tuned longer, even though the
    // stroke itself should always read as the same quick accent.
    const drawEnd = Math.min(FADE_FRAMES, Math.max(1, Math.floor(durationInFrames / 2)));

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

    const opacity = beatOpacity(frame, durationInFrames);

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
