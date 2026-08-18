import {
    AbsoluteFill,
    Img,
    interpolate,
    staticFile,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

import { BackgroundGrid, brand } from "./brand";
import { KeyedVideo, type KeyColor } from "./ChromaKey";
import { resolveBoxStyle } from "./timing";
import type { MomentBox } from "./types";

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

// How much of the moment's own box the asset keeps when a caption is
// placed "below" it (#82) — the remainder becomes CAPTION_STRIP_HEIGHT_PCT,
// a reserved strip beneath the asset that the caption renders into instead
// of overlaying the asset. Fixed proportions (not user-adjustable) so
// "below" always works automatically the moment it's picked, no separate
// drag step required.
const ASSET_HEIGHT_PCT_WITH_CAPTION_BELOW = 78;
const CAPTION_STRIP_HEIGHT_PCT = 100 - ASSET_HEIGHT_PCT_WITH_CAPTION_BELOW;

export const EpisodeImage = ({
                                  path,
                                  mediaType = "image",
                                  keyColor,
                                  caption,
                                  captionPlacement = "overlay",
                                  display,
                                  box,
                              }: {
    path: string;
    mediaType?: "image" | "video";
    keyColor?: KeyColor;
    caption?: string;
    // See MomentScene.captionPlacement's own doc comment in types.ts.
    // Defaults to "overlay" — every episode from before this field existed
    // renders unchanged.
    captionPlacement?: "overlay" | "below" | "off";
    display: "full" | "inset";
    box?: MomentBox;
}) => {
    const isVideo = mediaType === "video";
    const showCaption = !!caption && captionPlacement !== "off";
    const captionBelow = showCaption && captionPlacement === "below";
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

    // Inset's non-boxed default is a flush-top-right, 6%-margin, 38%-wide
    // square (aspectRatio 1/1 on a 1920x1080 canvas => ~67.6% tall) — the
    // equivalent fixed geometry resolveBoxStyle needs once a human sets a
    // box (#77): topPct 6, leftPct 100-6-38=56, widthPct 38, heightPct
    // 38*(1920/1080).
    const insetDefaultGeometry = { topPct: 6, leftPct: 56, widthPct: 38, heightPct: (38 * 1920) / 1080 };

    if (display === "inset" && isVideo) {
        // No frame/background box, "screen" blend mode — see SideImage's own
        // comment in MomentTreatments.tsx (#77): a video asset is assumed to
        // be a solid-black-background graphic with no real alpha channel, so
        // boxing it defeats the point of keying the black out.
        return (
            <AbsoluteFill style={{ pointerEvents: "none" }}>
                <div
                    style={
                        box
                            ? { ...resolveBoxStyle(insetDefaultGeometry, box), opacity }
                            : { position: "absolute", top: "6%", right: "6%", width: "38%", aspectRatio: "1 / 1", opacity, display: "flex", alignItems: "center", justifyContent: "center" }
                    }
                >
                    <KeyedVideo
                        path={path}
                        keyColor={keyColor}
                        style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
                    />
                </div>
            </AbsoluteFill>
        );
    }

    if (display === "inset") {
        return (
            <AbsoluteFill style={{ pointerEvents: "none" }}>
                <div
                    style={{
                        ...(box
                            ? { ...resolveBoxStyle(insetDefaultGeometry, box), opacity }
                            : { position: "absolute", top: "6%", right: "6%", width: "38%", aspectRatio: "1 / 1", opacity }),
                        backgroundColor: brand.colors.overlayBackground,
                        border: `2px solid ${brand.colors.accent}`,
                        borderRadius: brand.radii.frame,
                        padding: 20,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        boxShadow: "0 12px 32px rgba(0, 0, 0, 0.45)",
                        boxSizing: "border-box",
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

    const fullDefaultGeometry = { topPct: 9, leftPct: 9, widthPct: 82, heightPct: 82 };
    const outerBoxStyle = box ? resolveBoxStyle(fullDefaultGeometry, box) : { position: "absolute" as const, width: "82%", height: "82%" };

    const assetNode = isVideo ? (
        // No bordered/boxed frame — see the inset branch above (#77): a
        // video asset is assumed to have a flat, keyable static background
        // (black or green), so it's keyed transparent straight against the
        // background behind it rather than boxed inside its own card.
        <KeyedVideo path={path} keyColor={keyColor} style={{ width: "100%", height: "100%", objectFit: "contain" }} />
    ) : (
        <div
            style={{
                width: "100%",
                height: "100%",
                border: `2px solid ${brand.colors.accent}`,
                borderRadius: brand.radii.frame,
                overflow: "hidden",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "0 20px 48px rgba(0, 0, 0, 0.5)",
                boxSizing: "border-box",
            }}
        >
            <KenBurnsImage src={staticFile(path)} />
        </div>
    );

    const captionNode = showCaption && (
        <div
            style={{
                fontFamily: brand.fonts.family,
                fontSize: captionBelow ? 26 : 32,
                fontWeight: 600,
                color: brand.colors.text,
                textAlign: "center",
                padding: captionBelow ? "8px 24px" : "12px 32px",
                borderRadius: brand.radii.chip,
                backgroundColor: brand.colors.overlayBackground,
                borderLeft: `4px solid ${brand.colors.accent}`,
                maxWidth: captionBelow ? "100%" : "80%",
                boxSizing: "border-box",
            }}
        >
            {caption}
        </div>
    );

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

            {captionBelow ? (
                // "below": asset and caption are flow children of ONE
                // container matching the moment's own box — the asset
                // keeps ASSET_HEIGHT_PCT_WITH_CAPTION_BELOW of that box's
                // height, the caption gets the reserved strip beneath it,
                // so they can never collide regardless of where the box
                // itself sits (see #82 — the old "overlay" caption was a
                // separate AbsoluteFill pinned to the bottom of the WHOLE
                // FRAME, unrelated to the asset's actual position/size
                // once box overrides (#77) let it move/resize).
                <div style={{ ...outerBoxStyle, display: "flex", flexDirection: "column", gap: "2%" }}>
                    <div style={{ width: "100%", height: `${ASSET_HEIGHT_PCT_WITH_CAPTION_BELOW}%` }}>{assetNode}</div>
                    <div
                        style={{
                            width: "100%",
                            height: `${CAPTION_STRIP_HEIGHT_PCT}%`,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                        }}
                    >
                        {captionNode}
                    </div>
                </div>
            ) : (
                <>
                    <div style={outerBoxStyle}>{assetNode}</div>
                    {showCaption && (
                        <AbsoluteFill
                            style={{
                                justifyContent: "flex-end",
                                alignItems: "center",
                                paddingBottom: "6%",
                            }}
                        >
                            {captionNode}
                        </AbsoluteFill>
                    )}
                </>
            )}
        </AbsoluteFill>
    );
};
