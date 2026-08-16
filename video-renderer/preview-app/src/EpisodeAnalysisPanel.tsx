import { useEffect, useState } from "react";
import { getEpisodeAnalysis } from "./api";
import { colors, radius, typography } from "./tokens";

// Read-only dump of analyze_episode's output (AI narrative summary +
// transcript QA) — ports ui/static/app.js's renderEpisodeAnalysis, which
// was likewise just a pretty-printed <pre> of the raw JSON, never editable.
// Always-visible collapsible panel, same pattern as StoryboardPanel, since
// this data isn't scene-anchored either.
interface Props {
    episodePath: string;
}

export function EpisodeAnalysisPanel({ episodePath }: Props) {
    const [data, setData] = useState<unknown>(null);
    const [expanded, setExpanded] = useState(false);

    useEffect(() => {
        getEpisodeAnalysis(episodePath)
            .then(setData)
            .catch(() => setData(null)); // episode_analysis.json not produced yet — normal before that stage runs
    }, [episodePath]);

    if (!data) return null;

    return (
        <div style={styles.wrap}>
            <button className="secondary" onClick={() => setExpanded((v) => !v)} style={styles.toggle}>
                {expanded ? "Episode analysis ▾" : "Episode analysis ▸"}
            </button>

            {expanded && (
                <div style={styles.body}>
                    <p style={styles.hint}>Full AI QA pass output.</p>
                    <pre style={styles.jsonView}>{JSON.stringify(data, null, 2)}</pre>
                </div>
            )}
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        display: "flex",
        flexDirection: "column",
        gap: 8,
    },
    toggle: {
        alignSelf: "flex-start",
        fontSize: 13,
    },
    body: {
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: "12px 14px",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.lg,
    },
    hint: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        margin: 0,
    },
    jsonView: {
        maxHeight: 400,
        overflow: "auto",
        background: colors.background,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        padding: 10,
        fontSize: typography.size.sm,
        fontFamily: "monospace",
        color: colors.codeText,
        whiteSpace: "pre-wrap",
        margin: 0,
    },
};
