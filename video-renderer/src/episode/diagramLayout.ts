import dagre from "@dagrejs/dagre";

import type { DiagramData } from "./types";

// Pure layout computation — takes the AI-facing DiagramData (nodes/edges/
// layout, no coordinates: the LLM never reasons about pixel positions, see
// DiagramData's own comment in types.ts) and returns concrete positions via
// dagre's DAG layout algorithm. Replaces the old straight-line-only layout
// (a flexbox row/column that could only draw arrows between consecutive
// array entries, silently dropping any edge that branched or skipped —
// see the removed NODE_STAGGER_FRAMES-era DiagramBlock) with a real graph
// layout that handles branching, merging, and non-adjacent edges.
//
// No React/Remotion imports here on purpose — this is directly unit-
// testable the same way Episode.tsx's layoutWindowsForScene is, without
// needing a render environment.

export interface LayoutNode {
    id: string;
    label: string;
    x: number;
    y: number;
    width: number;
    height: number;
    // Original index in diagram.nodes — DiagramBlock's stagger-reveal
    // animation times each node's fade-in off this, not off dagre's
    // internal rank/order, so the reveal sequence still matches the order
    // the AI listed nodes in (usually the order they're introduced in the
    // narration) rather than dagre's layout-driven ordering.
    index: number;
}

export interface LayoutEdge {
    from: string;
    to: string;
    label?: string;
    points: { x: number; y: number }[];
}

export interface DiagramLayout {
    nodes: LayoutNode[];
    edges: LayoutEdge[];
    width: number;
    height: number;
}

// Fixed box size the layout is computed against — DiagramBlock renders
// each node at this same size (see its nodeWidth/nodeHeight usage), so
// dagre's spacing math and the actual rendered boxes agree. Node labels
// are short phrases by convention (enforced in generate_moments.py's
// prompt), so a fixed size is simpler and predictable than measuring
// text — this is a layout algorithm, not a text-fitting one.
const NODE_WIDTH = 180;
const NODE_HEIGHT = 56;
const NODE_WIDTH_FULL = 260;
const NODE_HEIGHT_FULL = 76;

export function computeDiagramLayout(diagram: DiagramData, full = false): DiagramLayout {
    const graph = new dagre.graphlib.Graph();

    const nodeWidth = full ? NODE_WIDTH_FULL : NODE_WIDTH;
    const nodeHeight = full ? NODE_HEIGHT_FULL : NODE_HEIGHT;

    graph.setGraph({
        rankdir: diagram.layout === "vertical" ? "TB" : "LR",
        nodesep: full ? 40 : 24,
        ranksep: full ? 64 : 40,
        marginx: 8,
        marginy: 8,
    });
    graph.setDefaultEdgeLabel(() => ({}));

    const indexById = new Map(diagram.nodes.map((node, index) => [node.id, index]));

    for (const node of diagram.nodes) {
        graph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
    }

    for (const edge of diagram.edges) {
        // Skip edges referencing a node id that isn't in this diagram —
        // defensive only; generate_moments.py already validates edge
        // endpoints match real node ids before a diagram ever reaches
        // rendering, so this should never trigger in practice.
        if (!indexById.has(edge.from) || !indexById.has(edge.to)) continue;
        graph.setEdge(edge.from, edge.to, { label: edge.label });
    }

    dagre.layout(graph);

    const nodes: LayoutNode[] = diagram.nodes.map((node) => {
        const positioned = graph.node(node.id);
        return {
            id: node.id,
            label: node.label,
            x: positioned.x,
            y: positioned.y,
            width: nodeWidth,
            height: nodeHeight,
            index: indexById.get(node.id) ?? 0,
        };
    });

    const edges: LayoutEdge[] = diagram.edges
        .filter((edge) => indexById.has(edge.from) && indexById.has(edge.to))
        .map((edge) => {
            const positioned = graph.edge(edge.from, edge.to);
            return {
                from: edge.from,
                to: edge.to,
                label: edge.label,
                points: positioned.points,
            };
        });

    const graphLabel = graph.graph();

    return {
        nodes,
        edges,
        width: graphLabel.width ?? 0,
        height: graphLabel.height ?? 0,
    };
}
