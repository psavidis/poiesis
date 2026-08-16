import { useEffect, useState } from "react";
import { getEpisodeAnalysis } from "./api";

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
        background: "#161d24",
        border: "1px solid #2a333d",
        borderRadius: 8,
    },
    hint: {
        fontSize: 12,
        color: "#9aa7b4",
        margin: 0,
    },
    jsonView: {
        maxHeight: 400,
        overflow: "auto",
        background: "#0b0f14",
        border: "1px solid #2a333d",
        borderRadius: 6,
        padding: 10,
        fontSize: 12,
        fontFamily: "monospace",
        color: "#c9d2da",
        whiteSpace: "pre-wrap",
        margin: 0,
    },
};
