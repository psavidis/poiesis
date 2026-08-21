import { useEffect, useMemo, useState } from "react";
import {
    AbsoluteFill,
    continueRender,
    delayRender,
    interpolate,
    staticFile,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";
import type { BundledLanguage, BundledTheme, HighlighterGeneric } from "shiki";
import { createHighlighter } from "shiki";

import { brand } from "./brand";
import { sideContentStyle } from "./MomentTreatments";
import { TRANSITION_FRAMES, resolveBoxStyle } from "./timing";
import type { MomentBox } from "./types";

const THEME = "github-dark";

// Shiki's highlighter (grammar/theme loading) is genuinely expensive to
// create — shared across every CodeBlock instance in a render rather than
// recreated per moment. Keyed by language so a render only pays the cost
// of loading a grammar once per language actually used, not once per
// highlighter instance.
let highlighterPromise: Promise<HighlighterGeneric<BundledLanguage, BundledTheme>> | null = null;
const loadedLanguages = new Set<string>();

async function getHighlighter(language: BundledLanguage) {
    if (!highlighterPromise) {
        highlighterPromise = createHighlighter({ themes: [THEME], langs: [] });
    }

    const highlighter = await highlighterPromise;

    if (!loadedLanguages.has(language)) {
        await highlighter.loadLanguage(language);
        loadedLanguages.add(language);
    }

    return highlighter;
}

type Token = { content: string; color?: string };

// Three size tiers instead of a `full` boolean, since #48 added a third:
// "side" (default, ~40%-width panel next to the presenter), "dominant"
// (content-dominant-code — most of the frame, presenter shrunk to a
// corner PiP rather than hidden), "full" (full-visual — presenter hidden
// entirely). Each gets its own line count and type scale, same reasoning
// as DiagramBlock's `full` prop: more screen space, more lines actually
// fit before truncating.
export type CodeBlockSize = "side" | "dominant" | "full";

const MAX_VISIBLE_LINES: Record<CodeBlockSize, number> = {
    side: 14,
    dominant: 18,
    full: 22,
};

const FONT_SIZE: Record<CodeBlockSize, number> = {
    side: 20,
    dominant: 23,
    full: 26,
};

export const CodeBlock = ({
                               path,
                               language,
                               presenterOnLeft,
                               size = "side",
                               box,
                           }: {
    path: string;
    language: string;
    presenterOnLeft: boolean;
    // See CodeBlockSize above. "side" (default) keeps today's side-panel
    // behavior unchanged.
    size?: CodeBlockSize;
    box?: MomentBox;
}) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    const [lines, setLines] = useState<Token[][] | null>(null);
    const [handle] = useState(() => delayRender("Loading and highlighting code snippet"));

    // language comes from EpisodeCodeAsset.language, a plain string
    // mechanically derived from a file extension on the Python side (see
    // index_code.py's LANGUAGE_BY_EXTENSION) — not a TS union Shiki can
    // check statically. Cast once here at the boundary rather than
    // threading `as never` through every Shiki call.
    const shikiLanguage = language as BundledLanguage;

    useEffect(() => {
        let cancelled = false;

        (async () => {
            try {
                const response = await fetch(staticFile(path));
                const code = await response.text();
                const highlighter = await getHighlighter(shikiLanguage);

                const tokens = highlighter.codeToTokensBase(code, { lang: shikiLanguage, theme: THEME });

                if (!cancelled) {
                    setLines(tokens as Token[][]);
                }
            } finally {
                if (!cancelled) {
                    continueRender(handle);
                }
            }
        })();

        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [path, language]);

    const maxVisibleLines = MAX_VISIBLE_LINES[size];

    const visibleLines = useMemo(() => {
        if (!lines) return [];
        return lines.slice(0, maxVisibleLines);
    }, [lines, maxVisibleLines]);

    const isTruncated = (lines?.length ?? 0) > maxVisibleLines;

    // Only "side" slides in from the presenter's opposite side — "dominant"
    // and "full" have no side panel to slide from (dominant is
    // center-weighted with the presenter in a corner, not beside it), so
    // both use a plain fade like FullText's entrance.
    const translateX =
        size === "side"
            ? interpolate(
                  frame,
                  [0, TRANSITION_FRAMES],
                  [presenterOnLeft ? -40 : 40, 0],
                  { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
              )
            : 0;

    const opacity = interpolate(
        frame,
        [0, TRANSITION_FRAMES, durationInFrames - TRANSITION_FRAMES, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    if (!lines) {
        return null;
    }

    const fontSize = FONT_SIZE[size];

    const content = (
        <div
            style={{
                opacity,
                transform: `translateX(${translateX}px)`,
                width: "100%",
                maxHeight: "80%",
                backgroundColor: brand.colors.overlayBackground,
                border: `2px solid ${brand.colors.accent}`,
                borderRadius: brand.radii.frame,
                padding: size === "side" ? "20px 24px" : "28px 36px",
                boxShadow: "0 12px 32px rgba(0, 0, 0, 0.45)",
                overflow: "hidden",
                position: "relative",
            }}
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {visibleLines.map((lineTokens, lineIndex) => (
                    <div
                        key={lineIndex}
                        style={{
                            display: "flex",
                            fontFamily: "'SF Mono', 'Fira Code', Menlo, Consolas, monospace",
                            fontSize,
                            lineHeight: 1.6,
                            whiteSpace: "pre",
                        }}
                    >
                        <span
                            style={{
                                color: "rgba(255, 255, 255, 0.3)",
                                width: 28,
                                flexShrink: 0,
                                textAlign: "right",
                                marginRight: 12,
                                userSelect: "none",
                            }}
                        >
                            {lineIndex + 1}
                        </span>
                        <span>
                            {lineTokens.map((token, tokenIndex) => (
                                <span key={tokenIndex} style={{ color: token.color }}>
                                    {token.content}
                                </span>
                            ))}
                        </span>
                    </div>
                ))}
            </div>

            {isTruncated && (
                <div
                    style={{
                        position: "absolute",
                        bottom: 0,
                        left: 0,
                        right: 0,
                        height: 48,
                        background: `linear-gradient(transparent, ${brand.colors.overlayBackground})`,
                    }}
                />
            )}
        </div>
    );

    if (size === "full") {
        return (
            <AbsoluteFill style={{ pointerEvents: "none", alignItems: "center", justifyContent: "center" }}>
                <div style={box ? resolveBoxStyle({ topPct: 12, leftPct: 12, widthPct: 76, heightPct: 76 }, box) : { width: "76%" }}>
                    {content}
                </div>
            </AbsoluteFill>
        );
    }

    if (size === "dominant") {
        // Anchored top-left rather than centered — leaves the bottom-right
        // corner clear for the presenter's PiP box (LAYOUT_GEOMETRY.corner
        // in timing.ts: leftPct 70/topPct 62), so the two never overlap.
        // Sized to comfortably fill the remaining space without touching
        // that corner. Same default geometry as MomentTreatments.tsx's
        // DominantMedia, which shows a code-folder screenshot/recording at
        // this exact position when the code asset isn't real source text.
        return (
            <AbsoluteFill style={{ pointerEvents: "none" }}>
                <div style={box ? resolveBoxStyle({ topPct: 8, leftPct: 6, widthPct: 62, heightPct: 100 }, box) : { position: "absolute", top: "8%", left: "6%", width: "62%" }}>
                    {content}
                </div>
            </AbsoluteFill>
        );
    }

    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <div style={sideContentStyle(presenterOnLeft, box)}>{content}</div>
        </AbsoluteFill>
    );
};
