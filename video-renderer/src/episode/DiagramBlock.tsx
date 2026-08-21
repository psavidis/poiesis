import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { brand } from "./brand";
import { computeDiagramLayout } from "./diagramLayout";
import { sideContentStyle } from "./MomentTreatments";
import { SIDE_CONTENT_WIDTH_PCT, TRANSITION_FRAMES } from "./timing";
import type { DiagramData, MomentBox } from "./types";

// Each node fades in slightly after the previous one (by its original
// array order, not dagre's layout order — see LayoutNode.index), guiding
// the eye through the relationship in sequence — justified here (unlike
// code/text) because that's exactly what a diagram is for.
const NODE_STAGGER_FRAMES = 6;

export const DiagramBlock = ({
                                  diagram,
                                  presenterOnLeft,
                                  full = false,
                                  box,
                              }: {
    diagram: DiagramData;
    presenterOnLeft: boolean;
    // Full-frame variant for "full-visual" moments (see
    // FullVisualMoment.tsx) — same node/edge data and reveal
    // choreography, just centered at a larger scale instead of confined
    // to the side panel a presenter is sharing the frame with.
    full?: boolean;
    // Only meaningful when full is false — FullDiagram (FullVisualMoment.tsx)
    // already has its own centered full-frame wrapper, no side-panel box to
    // override (see #77).
    box?: MomentBox;
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames, width: frameWidth, height: frameHeight } = useVideoConfig();

    const layout = computeDiagramLayout(diagram, full);

    // Dagre lays out nodes at their natural fixed box size (see
    // diagramLayout.ts's NODE_WIDTH/NODE_HEIGHT) with no knowledge of how
    // much screen space is actually available — a wide horizontal diagram
    // or a tall vertical one can exceed the side panel (see timing.ts's
    // SIDE_CONTENT_WIDTH_PCT) or even the full frame. Scale the whole
    // layout down (never up — a
    // small 2-node diagram shouldn't blow up to fill the available box)
    // so it always fits, rather than silently clipping against the
    // AbsoluteFill's overflow:hidden.
    const availableWidth = full ? frameWidth * 0.86 : frameWidth * (SIDE_CONTENT_WIDTH_PCT / 100) * 0.88;
    const availableHeight = full ? frameHeight * 0.7 : frameHeight * 0.88;
    const fitScale = Math.min(
        1,
        layout.width > 0 ? availableWidth / layout.width : 1,
        layout.height > 0 ? availableHeight / layout.height : 1
    );

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
                transform: `translateX(${translateX}px) scale(${fitScale})`,
                transformOrigin: "center",
                position: "relative",
                width: layout.width,
                height: layout.height,
            }}
        >
            <svg
                width={layout.width}
                height={layout.height}
                style={{ position: "absolute", top: 0, left: 0, overflow: "visible" }}
            >
                <defs>
                    <marker
                        id="diagram-arrowhead"
                        markerWidth="10"
                        markerHeight="10"
                        refX="8"
                        refY="5"
                        orient="auto"
                    >
                        <polygon points="0,0 10,5 0,10" fill={brand.colors.accent} />
                    </marker>
                </defs>
                {layout.edges.map((edge) => {
                    const path = edge.points
                        .map((point, i) => `${i === 0 ? "M" : "L"} ${point.x} ${point.y}`)
                        .join(" ");

                    // Midpoint of the path is a reasonable, simple spot
                    // for the edge label — dagre already routes points
                    // around node boxes, so the path's middle segment
                    // sits in open space between the two nodes it connects.
                    const midpoint = edge.points[Math.floor(edge.points.length / 2)];

                    return (
                        <g key={`${edge.from}-${edge.to}`}>
                            <path
                                d={path}
                                fill="none"
                                stroke={brand.colors.accent}
                                strokeWidth={2}
                                markerEnd="url(#diagram-arrowhead)"
                            />
                            {edge.label && midpoint && (
                                <text
                                    x={midpoint.x}
                                    y={midpoint.y - 8}
                                    fill={brand.colors.textMuted}
                                    fontFamily={brand.fonts.family}
                                    fontSize={full ? 15 : 13}
                                    textAnchor="middle"
                                >
                                    {edge.label}
                                </text>
                            )}
                        </g>
                    );
                })}
            </svg>

            {layout.nodes.map((node) => {
                const nodeStart = TRANSITION_FRAMES + node.index * NODE_STAGGER_FRAMES;
                const nodeOpacity = interpolate(
                    frame,
                    [nodeStart, nodeStart + NODE_STAGGER_FRAMES],
                    [0, 1],
                    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
                );

                return (
                    <div
                        key={node.id}
                        style={{
                            position: "absolute",
                            left: node.x - node.width / 2,
                            top: node.y - node.height / 2,
                            width: node.width,
                            height: node.height,
                            opacity: nodeOpacity,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            backgroundColor: brand.colors.overlayBackground,
                            border: `2px solid ${brand.colors.accent}`,
                            borderRadius: brand.radii.frame,
                            padding: full ? "22px 32px" : "14px 20px",
                            boxSizing: "border-box",
                        }}
                    >
                        <div
                            style={{
                                fontFamily: brand.fonts.family,
                                fontSize: full ? 34 : 22,
                                fontWeight: 600,
                                color: brand.colors.text,
                                textAlign: "center",
                                lineHeight: 1.15,
                            }}
                        >
                            {node.label}
                        </div>
                    </div>
                );
            })}
        </div>
    );

    if (full) {
        return (
            <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
                {content}
            </AbsoluteFill>
        );
    }

    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <div style={sideContentStyle(presenterOnLeft, box)}>{content}</div>
        </AbsoluteFill>
    );
};
