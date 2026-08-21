import {
    AbsoluteFill,
    Easing,
    Img,
    interpolate,
    spring,
    staticFile,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

import { brand } from "./brand";
import { KeyedVideo, type KeyColor } from "./ChromaKey";
import { SIDE_CONTENT_WIDTH_PCT, TRANSITION_FRAMES, resolveBoxStyle } from "./timing";
import type { MomentBox, MomentEntrance } from "./types";

// SideText/SideImage's own fade timing is derived from the same
// TRANSITION_FRAMES constant Episode.tsx uses for the presenter's
// slide-aside/slide-back animation. Previously these were independent
// hardcoded literals (12 in, 10 out) that only stayed synchronized with
// the presenter's 24-frame slide by coincidence — tuning either value
// later could silently desync content visibility from the presenter's
// on-screen position. Deriving both from one constant means that can't
// happen: fade-in/out is always exactly as long as the presenter's own
// slide, so content is never still fading while the presenter is already
// mid-motion (or vice versa).
const FADE_IN_FRAMES = TRANSITION_FRAMES;
const FADE_OUT_FRAMES = TRANSITION_FRAMES;

// The bottom-center callout — ported as-is from the pre-moments EmphasisText
// component. Requires the parent presenter scene's layout to be "center"
// (the presenter still fills the frame; this is a pure overlay, same as
// before moments existed).
//
// entrance selects among three ALREADY-EXISTING animation patterns in this
// codebase (see MomentEntrance's own doc comment in types.ts for where
// each one is otherwise used) rather than introducing new motion design —
// this is what makes an entrance actually configurable (docs/specs/
// ai-assisted-editing-and-conversational-control.md section 7's "if it
// corresponds to an existing supported animation, configure it") instead
// of every moment being stuck with whichever entrance its component
// happened to hardcode. Defaults to "scale" — this component's own
// original, only-ever behavior before this field existed, so an episode
// with no entrance field set renders byte-identical to before.
export const computeTransform = (entrance: MomentEntrance, frame: number, fps: number): string => {
    if (entrance === "fade") return "none";

    const progress = spring({ frame, fps, config: { damping: 200 } });

    if (entrance === "slide") {
        // Same spring-translateY-up pattern AnimatedTitle.tsx already uses
        // for its own entrance — geometrically appropriate here too, since
        // BottomCallout is also bottom-anchored (unlike Comparison.tsx's
        // left/right slide, which assumes a side-flanking position this
        // element doesn't have).
        const translateY = interpolate(progress, [0, 1], [24, 0]);
        return `translateY(${translateY}px)`;
    }

    // "scale" — the original hardcoded behavior.
    return `scale(${progress})`;
};

export const BottomCallout = ({
                                   text,
                                   entrance = "scale",
                                   box,
                               }: {
    text: string;
    entrance?: MomentEntrance;
    box?: MomentBox;
}) => {
    const frame = useCurrentFrame();
    const { fps, durationInFrames } = useVideoConfig();

    const transform = computeTransform(entrance, frame, fps);

    const opacity = interpolate(
        frame,
        [0, 8, durationInFrames - 8, durationInFrames],
        [0, 1, 1, 0],
        {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        }
    );

    const chip = (
        <div
            style={{
                opacity,
                transform,
                display: "flex",
                alignItems: "center",
                maxWidth: box ? "100%" : "78%",
                width: box ? "100%" : undefined,
                height: box ? "100%" : undefined,
                backgroundColor: brand.colors.overlayBackground,
                borderLeft: `6px solid ${brand.colors.accent}`,
                borderRadius: brand.radii.chip,
                padding: "18px 32px",
                boxSizing: "border-box",
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
    );

    // No natural fixed box by default — this treatment centers an
    // intrinsically-sized chip via flexbox rather than an absolute
    // top/left/width/height, so there's no single "default geometry" to
    // feed resolveBoxStyle the way the side-panel treatments have. Only
    // switches to absolute positioning when a human has actually set a box
    // (#77); every episode without one renders exactly as before.
    if (box) {
        return (
            <AbsoluteFill style={{ pointerEvents: "none" }}>
                <div style={resolveBoxStyle({ topPct: 0, leftPct: 0, widthPct: 100, heightPct: 100 }, box)}>{chip}</div>
            </AbsoluteFill>
        );
    }

    return (
        <AbsoluteFill
            style={{
                justifyContent: "flex-end",
                alignItems: "center",
                paddingBottom: "12%",
                pointerEvents: "none",
            }}
        >
            {chip}
        </AbsoluteFill>
    );
};

// Shared positioning for the "content fills whichever side the presenter
// isn't occupying" treatments. presenterOnLeft mirrors the content to the
// opposite side. Width is derived from timing.ts's LAYOUT_GEOMETRY (100 -
// the presenter's own widthPct) rather than a second hardcoded
// percentage, so this can never silently drift out of sync with how much
// room the presenter's own slide animation actually frees up.
//
// box (see #77) overrides this default via resolveBoxStyle when a human
// has dragged/resized this specific moment on the preview-app's player —
// absent (every episode before this field existed) renders byte-identical
// to before.
export const sideContentStyle = (presenterOnLeft: boolean, box?: MomentBox): React.CSSProperties => ({
    ...resolveBoxStyle(
        {
            topPct: 0,
            leftPct: presenterOnLeft ? 100 - SIDE_CONTENT_WIDTH_PCT : 0,
            widthPct: SIDE_CONTENT_WIDTH_PCT,
            heightPct: 100,
        },
        box
    ),
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "6%",
});

// "quote" (default) vs. "title" — see SideTextStyle in types.ts. Both share
// the same slide/fade choreography; only the typographic treatment
// differs, so this is one lookup table rather than two components.
const SIDE_TEXT_STYLE = {
    quote: { fontSize: 52, fontWeight: 700, letterSpacing: "normal", textTransform: "none" as const },
    title: { fontSize: 58, fontWeight: 800, letterSpacing: "0.02em", textTransform: "uppercase" as const },
};

export const SideText = ({
                              text,
                              presenterOnLeft,
                              style = "quote",
                              box,
                          }: {
    text: string;
    presenterOnLeft: boolean;
    style?: "quote" | "title";
    box?: MomentBox;
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    // Slides in from its own edge (the side the presenter just vacated)
    // rather than fading in place, so it visually arrives together with the
    // presenter's own slide animation instead of feeling like an unrelated
    // overlay — eased (not linear), matching the presenter's own eased
    // slide (see Episode.tsx's AnimatedPresenterFrame), so the two motions
    // read as one choreographed move rather than arriving on different
    // rhythms.
    const translateX = interpolate(
        frame,
        [0, TRANSITION_FRAMES],
        [presenterOnLeft ? -40 : 40, 0],
        { easing: Easing.out(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const opacity = interpolate(
        frame,
        [0, FADE_IN_FRAMES, durationInFrames - FADE_OUT_FRAMES, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const typeStyle = SIDE_TEXT_STYLE[style];

    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <div style={sideContentStyle(presenterOnLeft, box)}>
                <div
                    style={{
                        opacity,
                        transform: `translateX(${translateX}px)`,
                        fontFamily: brand.fonts.family,
                        fontSize: typeStyle.fontSize,
                        fontWeight: typeStyle.fontWeight,
                        letterSpacing: typeStyle.letterSpacing,
                        textTransform: typeStyle.textTransform,
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
                               mediaType = "image",
                               keyColor,
                               caption,
                               captionPlacement = "overlay",
                               presenterOnLeft,
                               box,
                           }: {
    path: string;
    mediaType?: "image" | "video";
    keyColor?: KeyColor;
    caption?: string;
    // This treatment's own layout already stacks image-then-caption as
    // flow children (no overlay mode exists here to begin with — see the
    // caption's own render below), so "overlay" vs. "below" makes no
    // visual difference for SideImage specifically; only "off" actually
    // changes anything. Accepted anyway so every treatment shares one
    // prop shape (#82).
    captionPlacement?: "overlay" | "below" | "off";
    presenterOnLeft: boolean;
    box?: MomentBox;
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    // Eased slide-in, matching the presenter's own eased slide (see
    // Episode.tsx's AnimatedPresenterFrame) so the two motions read as one
    // choreographed move rather than the content arriving on a different
    // rhythm than the presenter making room for it.
    const translateX = interpolate(
        frame,
        [0, TRANSITION_FRAMES],
        [presenterOnLeft ? -40 : 40, 0],
        { easing: Easing.out(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const opacity = interpolate(
        frame,
        [0, FADE_IN_FRAMES, durationInFrames - FADE_OUT_FRAMES, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <div style={sideContentStyle(presenterOnLeft, box)}>
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
                    {mediaType === "video" ? (
                        // No frame/background box: unlike a still image, this is
                        // assumed to be a graphic authored on a solid black
                        // background with no real alpha channel (see #77) — a
                        // "screen" blend mode makes black pixels transparent
                        // against whatever's behind (presenter/background video),
                        // so boxing it in its own colored card would defeat the
                        // point by putting a visible frame around the keyed area.
                        <div style={{ width: "100%", aspectRatio: "1 / 1", display: "flex", alignItems: "center", justifyContent: "center" }}>
                            <KeyedVideo
                                path={path}
                                keyColor={keyColor}
                                style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
                            />
                        </div>
                    ) : (
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
                    )}

                    {caption && captionPlacement !== "off" && (
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

// A screenshot/recording sibling of CodeBlock's "dominant" size — same
// top-left anchor and 62% width (leaving LAYOUT_GEOMETRY.corner's
// bottom-right free for the presenter's PiP box) so a code-folder image/
// video demonstrating code slots into the same on-screen position a real
// source CodeBlock would, regardless of which of the two the AI/human
// actually picked for a given moment.
export const DominantMedia = ({
                                   path,
                                   mediaType,
                                   keyColor,
                                   caption,
                                   captionPlacement = "overlay",
                                   box,
                               }: {
    path: string;
    mediaType: "image" | "video";
    keyColor?: KeyColor;
    caption?: string;
    // See MomentScene.captionPlacement's own doc comment (#82). "below"
    // renders the caption as a flow sibling AFTER the media instead of
    // overlaid — unlike EpisodeImage's fixed-box "full" mode, this
    // treatment's box has no fixed height by default (content-sized to
    // the media's own aspect ratio), so there's no reserved bottom strip
    // to compute; a flow sibling naturally sits below regardless.
    captionPlacement?: "overlay" | "below" | "off";
    box?: MomentBox;
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const opacity = interpolate(
        frame,
        [0, TRANSITION_FRAMES, durationInFrames - TRANSITION_FRAMES, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const media =
        mediaType === "video" ? (
            <KeyedVideo path={path} keyColor={keyColor} style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
        ) : (
            <Img src={staticFile(path)} style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain", borderRadius: 6 }} />
        );

    // No default height (the box is content-sized, only top/left/width are
    // fixed) — box overrides (#77) DO fix a height once set, via
    // resolveBoxStyle, same conditional-wrapper pattern as BottomCallout
    // above for the same reason (no single default geometry shape to feed
    // it otherwise).
    const positionStyle: React.CSSProperties = box
        ? resolveBoxStyle({ topPct: 8, leftPct: 6, widthPct: 62, heightPct: 100 }, box)
        : { position: "absolute", top: "8%", left: "6%", width: "62%" };

    const showCaption = !!caption && captionPlacement !== "off";
    const captionBelow = showCaption && captionPlacement === "below";

    const mediaNode =
        mediaType === "video" ? (
            media
        ) : (
            <div
                style={{
                    backgroundColor: brand.colors.overlayBackground,
                    border: `2px solid ${brand.colors.accent}`,
                    borderRadius: brand.radii.frame,
                    padding: 20,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    boxShadow: "0 12px 32px rgba(0, 0, 0, 0.45)",
                    height: box && !captionBelow ? "100%" : undefined,
                    boxSizing: "border-box",
                }}
            >
                {media}
            </div>
        );

    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <div
                style={{
                    ...positionStyle,
                    opacity,
                    ...(captionBelow ? { display: "flex", flexDirection: "column", gap: 12 } : {}),
                }}
            >
                {mediaNode}
                {showCaption && (
                    <div
                        style={{
                            fontFamily: brand.fonts.family,
                            fontSize: 22,
                            fontWeight: 600,
                            color: brand.colors.text,
                            textAlign: "center",
                            ...(captionBelow
                                ? {}
                                : {
                                      // Genuinely overlaid on the media's own
                                      // bottom edge (inside the box), not the
                                      // whole frame — a background chip keeps
                                      // it legible against whatever the image
                                      // shows underneath, matching the visual
                                      // language BottomCallout/SideImage's own
                                      // caption chips already use elsewhere.
                                      position: "absolute",
                                      bottom: 12,
                                      left: 12,
                                      right: 12,
                                      padding: "8px 16px",
                                      borderRadius: brand.radii.chip,
                                      backgroundColor: brand.colors.overlayBackground,
                                      borderLeft: `3px solid ${brand.colors.accent}`,
                                      boxSizing: "border-box",
                                  }),
                        }}
                    >
                        {caption}
                    </div>
                )}
            </div>
        </AbsoluteFill>
    );
};
