import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { BackgroundGrid, brand } from "./brand";
import { CodeBlock } from "./CodeBlock";
import { DiagramBlock } from "./DiagramBlock";
import { EpisodeImage } from "./EpisodeImage";
import { TRANSITION_FRAMES } from "./timing";
import type { DiagramData } from "./types";

// A full-frame sibling of DiagramBlock's side-panel layout: same node/edge
// data and reveal choreography (via DiagramBlock itself, in "full" mode),
// just centered and scaled up to use the whole frame now that there's no
// presenter sharing it. Kept as a thin wrapper rather than duplicating
// DiagramBlock's layout logic — the only real difference is container
// sizing/typography scale, which "full" mode threads through.
const FullDiagram = ({ diagram }: { diagram: DiagramData }) => (
    <AbsoluteFill
        style={{
            backgroundColor: brand.colors.background,
            justifyContent: "center",
            alignItems: "center",
            overflow: "hidden",
        }}
    >
        <BackgroundGrid />
        <DiagramBlock diagram={diagram} presenterOnLeft={false} full />
    </AbsoluteFill>
);

// A short headline-scale phrase with full visual weight — for moments that
// deserve the whole frame without an image/diagram to show (a strong claim
// or a section's core idea stated plainly, per the design). Reuses the
// same brand background/grid as EpisodeImage's "full" display and
// DiagramBlock's full mode so all three full-visual kinds read as one
// consistent "the video pauses to make a point" moment, not three
// unrelated looks.
const FullText = ({ text }: { text: string }) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const opacity = interpolate(
        frame,
        [0, TRANSITION_FRAMES, durationInFrames - TRANSITION_FRAMES, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const scale = interpolate(
        frame,
        [0, TRANSITION_FRAMES],
        [0.92, 1],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
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
                    transform: `scale(${scale})`,
                    maxWidth: "76%",
                    fontFamily: brand.fonts.family,
                    fontSize: 72,
                    fontWeight: 700,
                    lineHeight: 1.25,
                    color: brand.colors.text,
                    textAlign: "center",
                }}
            >
                {text}
            </div>
        </AbsoluteFill>
    );
};

export const FullVisualMoment = ({
                                      kind,
                                      text,
                                      assetPath,
                                      caption,
                                      diagram,
                                      codePath,
                                      codeLanguage,
                                  }: {
    kind: "image" | "diagram" | "text" | "code";
    text?: string;
    assetPath?: string;
    caption?: string;
    diagram?: DiagramData;
    codePath?: string;
    codeLanguage?: string;
}) => {
    if (kind === "image" && assetPath) {
        return <EpisodeImage path={assetPath} caption={caption} display="full" />;
    }

    if (kind === "diagram" && diagram) {
        return <FullDiagram diagram={diagram} />;
    }

    if (kind === "text" && text) {
        return <FullText text={text} />;
    }

    if (kind === "code" && codePath && codeLanguage) {
        return <CodeBlock path={codePath} language={codeLanguage} presenterOnLeft={false} full />;
    }

    return null;
};
