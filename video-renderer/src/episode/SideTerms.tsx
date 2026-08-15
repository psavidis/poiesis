import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { brand } from "./brand";
import { sideContentStyle } from "./MomentTreatments";
import { TRANSITION_FRAMES } from "./timing";
import type { TermEmphasis, TermEmphasisLevel } from "./types";

// Each term fades/slides in slightly after the previous one — same
// staggered-reveal choreography DiagramBlock already uses for node reveal,
// applied here to a vertical stack of terms instead of boxes/arrows. Kept
// as its own constant (not imported from DiagramBlock) since the two
// components' reveal cadences are allowed to diverge independently later.
const TERM_STAGGER_FRAMES = 8;

// Fixed type styles per emphasis level — a small, bounded set (not
// freeform per-term size/weight/color) so independently-generated
// side-terms moments read as one consistent visual language rather than
// each moment inventing its own type scale. Mirrors the reference shot
// this component was built from: one small muted label, one large bold
// term, one accent-colored term.
const LEVEL_STYLE: Record<TermEmphasisLevel, { fontSize: number; fontWeight: number; color: string }> = {
    muted: { fontSize: 30, fontWeight: 500, color: brand.colors.textMuted },
    primary: { fontSize: 52, fontWeight: 700, color: brand.colors.text },
    accent: { fontSize: 44, fontWeight: 700, color: brand.colors.accent },
};

const Term = ({
                  term,
                  index,
                  presenterOnLeft,
              }: {
    term: TermEmphasis;
    index: number;
    presenterOnLeft: boolean;
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const revealStart = TRANSITION_FRAMES + index * TERM_STAGGER_FRAMES;

    const opacity = interpolate(
        frame,
        [revealStart, revealStart + TERM_STAGGER_FRAMES, durationInFrames - TRANSITION_FRAMES, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const translateY = interpolate(
        frame,
        [revealStart, revealStart + TERM_STAGGER_FRAMES],
        [12, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const style = LEVEL_STYLE[term.level];

    return (
        <div
            style={{
                opacity,
                transform: `translateY(${translateY}px)`,
                fontFamily: brand.fonts.family,
                fontSize: style.fontSize,
                fontWeight: style.fontWeight,
                color: style.color,
                lineHeight: 1.2,
                textAlign: presenterOnLeft ? "right" : "left",
            }}
        >
            {term.text}
        </div>
    );
};

export const SideTerms = ({
                               terms,
                               presenterOnLeft,
                           }: {
    terms: TermEmphasis[];
    presenterOnLeft: boolean;
}) => {
    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <div style={sideContentStyle(presenterOnLeft)}>
                <div
                    style={{
                        width: "100%",
                        display: "flex",
                        flexDirection: "column",
                        alignItems: presenterOnLeft ? "flex-end" : "flex-start",
                        gap: 10,
                    }}
                >
                    {terms.map((term, index) => (
                        <Term key={`${term.text}-${index}`} term={term} index={index} presenterOnLeft={presenterOnLeft} />
                    ))}
                </div>
            </div>
        </AbsoluteFill>
    );
};
