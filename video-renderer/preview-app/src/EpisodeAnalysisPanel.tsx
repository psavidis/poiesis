import { useEffect, useState } from "react";
import { getEpisodeAnalysis } from "./api";
import { colors, radius, typography } from "./tokens";

// Read-only dump of analyze_episode's output (AI narrative summary +
// transcript QA) — ports ui/static/app.js's renderEpisodeAnalysis, which
// was likewise just a pretty-printed <pre> of the raw JSON, never editable.
// Mounted unconditionally by EpisodeWorkspace's tab strip (#70), same
// isActive/onHasContentChange contract as StoryboardPanel.
interface Props {
    episodePath: string;
    isActive: boolean;
    onHasContentChange: (hasContent: boolean) => void;
}

export function EpisodeAnalysisPanel({ episodePath, isActive, onHasContentChange }: Props) {
    const [data, setData] = useState<unknown>(null);

    useEffect(() => {
        getEpisodeAnalysis(episodePath)
            .then(setData)
            .catch(() => setData(null)); // episode_analysis.json not produced yet — normal before that stage runs
    }, [episodePath]);

    useEffect(() => {
        onHasContentChange(!!data);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [data]);

    if (!isActive || !data) return null;

    return (
        <div style={styles.body}>
            <p style={styles.hint}>Full AI QA pass output.</p>
            <pre style={styles.jsonView}>{JSON.stringify(data, null, 2)}</pre>
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    body: {
        display: "flex",
        flexDirection: "column",
        gap: 8,
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
