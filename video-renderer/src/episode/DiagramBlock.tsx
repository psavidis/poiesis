import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { brand } from "./brand";
import { sideContentStyle } from "./MomentTreatments";
import { TRANSITION_FRAMES } from "./timing";
import type { DiagramData } from "./types";

// Pure layout computation, no external graph-layout library — at the v1
// scale (max 6 nodes, propose_moments.py enforces this before a diagram
// ever reaches here), a straight line of boxes is enough for the simple
// flow/hierarchy/comparison patterns this feature targets. Edges are
// assumed to connect consecutive nodes in a sensible order (the LLM emits
// them that way); a node with multiple outgoing edges just draws multiple
// arrows from the same box, still simple to lay out this way.
const NODE_STAGGER_FRAMES = 6;

export const DiagramBlock = ({
                                  diagram,
                                  presenterOnLeft,
                                  full = false,
                              }: {
    diagram: DiagramData;
    presenterOnLeft: boolean;
    // Full-frame variant for "full-visual" moments (see
    // FullVisualMoment.tsx) — same node/edge data and reveal
    // choreography, just centered at a larger scale instead of confined
    // to the side panel a presenter is sharing the frame with.
    full?: boolean;
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const isVertical = diagram.layout === "vertical";

    const nodePositions = new Map(diagram.nodes.map((node, index) => [node.id, index]));

    const containerOpacity = interpolate(
        frame,
        [0, TRANSITION_FRAMES, durationInFrames - TRANSITION_FRAMES, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const translateX = full
        ? 0
        : interpolate(
              frame,
              [0, TRANSITION_FRAMES],
              [presenterOnLeft ? -40 : 40, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );

    const content = (
        <div
            style={{
                opacity: containerOpacity,
                transform: `translateX(${translateX}px)`,
                width: "100%",
                display: "flex",
                flexDirection: isVertical ? "column" : "row",
                alignItems: "center",
                justifyContent: "center",
                gap: full ? 24 : 8,
            }}
        >
            {diagram.nodes.map((node, index) => {
                // Sequential reveal: each node fades in slightly
                // after the previous one, guiding the eye through
                // the relationship in order — justified here
                // (unlike code/text) because that's exactly what a
                // diagram is for.
                const nodeStart = TRANSITION_FRAMES + index * NODE_STAGGER_FRAMES;
                const nodeOpacity = interpolate(
                    frame,
                    [nodeStart, nodeStart + NODE_STAGGER_FRAMES],
                    [0, 1],
                    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
                );

                const outgoingEdges = diagram.edges.filter((edge) => edge.from === node.id);

                return (
                    <div
                        key={node.id}
                        style={{
                            display: "flex",
                            flexDirection: isVertical ? "column" : "row",
                            alignItems: "center",
                            opacity: nodeOpacity,
                        }}
                    >
                        <div
                            style={{
                                backgroundColor: brand.colors.overlayBackground,
                                border: `2px solid ${brand.colors.accent}`,
                                borderRadius: brand.radii.frame,
                                padding: full ? "22px 32px" : "14px 20px",
                                fontFamily: brand.fonts.family,
                                fontSize: full ? 34 : 22,
                                fontWeight: 600,
                                color: brand.colors.text,
                                textAlign: "center",
                                whiteSpace: "nowrap",
                            }}
                        >
                            {node.label}
                        </div>

                        {outgoingEdges.map((edge) => {
                            const toIndex = nodePositions.get(edge.to);
                            if (toIndex === undefined || toIndex <= index) return null;

                            return (
                                <DiagramArrow
                                    key={`${edge.from}-${edge.to}`}
                                    label={edge.label}
                                    vertical={isVertical}
                                    scale={full ? 1.6 : 1}
                                />
                            );
                        })}
                    </div>
                );
            })}
        </div>
    );

    if (full) {
        return content;
    }

    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <div style={sideContentStyle(presenterOnLeft)}>{content}</div>
        </AbsoluteFill>
    );
};

const DiagramArrow = ({
                           label,
                           vertical,
                           scale = 1,
                       }: {
    label?: string;
    vertical: boolean;
    // Full-frame diagrams (DiagramBlock's full=true) scale arrows up to
    // match the larger node type — same proportions, just bigger.
    scale?: number;
}) => (
    <div
        style={{
            display: "flex",
            flexDirection: vertical ? "column" : "row",
            alignItems: "center",
            justifyContent: "center",
            padding: vertical ? "4px 0" : "0 4px",
            gap: 2,
        }}
    >
        {label && (
            <div
                style={{
                    fontFamily: brand.fonts.family,
                    fontSize: 13 * scale,
                    color: brand.colors.textMuted,
                    whiteSpace: "nowrap",
                }}
            >
                {label}
            </div>
        )}
        <svg
            width={(vertical ? 20 : 32) * scale}
            height={(vertical ? 32 : 20) * scale}
            viewBox={vertical ? "0 0 20 32" : "0 0 32 20"}
        >
            {vertical ? (
                <>
                    <line x1={10} y1={0} x2={10} y2={24} stroke={brand.colors.accent} strokeWidth={2} />
                    <polygon points="10,32 4,22 16,22" fill={brand.colors.accent} />
                </>
            ) : (
                <>
                    <line x1={0} y1={10} x2={24} y2={10} stroke={brand.colors.accent} strokeWidth={2} />
                    <polygon points="32,10 22,4 22,16" fill={brand.colors.accent} />
                </>
            )}
        </svg>
    </div>
);
