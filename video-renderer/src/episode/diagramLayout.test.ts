import { describe, expect, it } from "vitest";

import { computeDiagramLayout } from "./diagramLayout";
import type { DiagramData } from "./types";

const linearDiagram: DiagramData = {
    nodes: [
        { id: "a", label: "Client" },
        { id: "b", label: "API" },
        { id: "c", label: "Database" },
    ],
    edges: [
        { from: "a", to: "b" },
        { from: "b", to: "c" },
    ],
    layout: "horizontal",
};

const branchingDiagram: DiagramData = {
    nodes: [
        { id: "a", label: "Service" },
        { id: "b", label: "DB" },
        { id: "c", label: "Cache" },
    ],
    edges: [
        { from: "a", to: "b" },
        { from: "a", to: "c" },
    ],
    layout: "horizontal",
};

describe("computeDiagramLayout", () => {
    it("positions every node from the input diagram", () => {
        const layout = computeDiagramLayout(linearDiagram);

        expect(layout.nodes.map((n) => n.id)).toEqual(["a", "b", "c"]);
    });

    it("lays a linear horizontal chain out left to right", () => {
        const layout = computeDiagramLayout(linearDiagram);
        const byId = new Map(layout.nodes.map((n) => [n.id, n]));

        expect(byId.get("a")!.x).toBeLessThan(byId.get("b")!.x);
        expect(byId.get("b")!.x).toBeLessThan(byId.get("c")!.x);
    });

    it("lays a linear vertical chain out top to bottom", () => {
        const verticalDiagram: DiagramData = { ...linearDiagram, layout: "vertical" };
        const layout = computeDiagramLayout(verticalDiagram);
        const byId = new Map(layout.nodes.map((n) => [n.id, n]));

        expect(byId.get("a")!.y).toBeLessThan(byId.get("b")!.y);
        expect(byId.get("b")!.y).toBeLessThan(byId.get("c")!.y);
    });

    it("gives two children of a branching node distinct, non-overlapping positions", () => {
        const layout = computeDiagramLayout(branchingDiagram);
        const byId = new Map(layout.nodes.map((n) => [n.id, n]));

        const db = byId.get("b")!;
        const cache = byId.get("c")!;

        // Both are children of the same parent in the same rank, so they
        // must be separated on the cross-axis (y, for a horizontal/LR
        // layout) rather than colliding at the same position — this is
        // exactly the case the old straight-line layout couldn't handle
        // (it only ever drew arrows between consecutive array entries).
        expect(db.y).not.toBe(cache.y);
    });

    it("includes a path for every edge, connecting real node ids", () => {
        const layout = computeDiagramLayout(linearDiagram);

        expect(layout.edges).toHaveLength(2);
        for (const edge of layout.edges) {
            expect(edge.points.length).toBeGreaterThan(0);
        }
    });

    it("passes edge labels through unchanged", () => {
        const labeled: DiagramData = {
            nodes: linearDiagram.nodes,
            edges: [{ from: "a", to: "b", label: "HTTP" }],
            layout: "horizontal",
        };

        const layout = computeDiagramLayout(labeled);

        expect(layout.edges[0].label).toBe("HTTP");
    });

    it("still positions a node with no edges at all", () => {
        const isolated: DiagramData = {
            nodes: [{ id: "solo", label: "Standalone" }],
            edges: [],
            layout: "horizontal",
        };

        const layout = computeDiagramLayout(isolated);

        expect(layout.nodes).toHaveLength(1);
        expect(layout.nodes[0].id).toBe("solo");
    });

    it("silently drops an edge referencing an unknown node id", () => {
        const badEdge: DiagramData = {
            nodes: [{ id: "a", label: "A" }],
            edges: [{ from: "a", to: "nonexistent" }],
            layout: "horizontal",
        };

        const layout = computeDiagramLayout(badEdge);

        expect(layout.edges).toHaveLength(0);
    });

    it("preserves each node's original array index for reveal-order timing", () => {
        const layout = computeDiagramLayout(branchingDiagram);
        const byId = new Map(layout.nodes.map((n) => [n.id, n]));

        expect(byId.get("a")!.index).toBe(0);
        expect(byId.get("b")!.index).toBe(1);
        expect(byId.get("c")!.index).toBe(2);
    });

    it("produces a larger node box in full mode than side-panel mode", () => {
        const sideLayout = computeDiagramLayout(linearDiagram, false);
        const fullLayout = computeDiagramLayout(linearDiagram, true);

        expect(fullLayout.nodes[0].width).toBeGreaterThan(sideLayout.nodes[0].width);
        expect(fullLayout.nodes[0].height).toBeGreaterThan(sideLayout.nodes[0].height);
    });
});
