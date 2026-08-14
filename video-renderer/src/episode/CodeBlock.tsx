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
import { TRANSITION_FRAMES } from "./timing";

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

const MAX_VISIBLE_LINES = 14;

export const CodeBlock = ({
                               path,
                               language,
                               presenterOnLeft,
                           }: {
    path: string;
    language: string;
    presenterOnLeft: boolean;
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

    const visibleLines = useMemo(() => {
        if (!lines) return [];
        return lines.slice(0, MAX_VISIBLE_LINES);
    }, [lines]);

    const isTruncated = (lines?.length ?? 0) > MAX_VISIBLE_LINES;

    const translateX = interpolate(
        frame,
        [0, TRANSITION_FRAMES],
        [presenterOnLeft ? -40 : 40, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const opacity = interpolate(
        frame,
        [0, TRANSITION_FRAMES, durationInFrames - TRANSITION_FRAMES, durationInFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    if (!lines) {
        return null;
    }

    return (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
            <div style={sideContentStyle(presenterOnLeft)}>
                <div
                    style={{
                        opacity,
                        transform: `translateX(${translateX}px)`,
                        width: "100%",
                        maxHeight: "80%",
                        backgroundColor: brand.colors.overlayBackground,
                        border: `2px solid ${brand.colors.accent}`,
                        borderRadius: brand.radii.frame,
                        padding: "20px 24px",
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
                                    fontSize: 20,
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
            </div>
        </AbsoluteFill>
    );
};
