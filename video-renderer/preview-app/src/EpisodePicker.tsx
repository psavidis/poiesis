import { useEffect, useState } from "react";
import { browse, DEFAULT_BROWSE_PATH, type BrowseResult } from "./api";
import { useRouter } from "./Router";
import { colors, radius, typography } from "./tokens";

// Where the last-picked episode path is remembered across reloads — a
// picker action is always explicit (this never auto-navigates away from
// "/"), but reopening the picker should start where you left off instead
// of always resetting to DEFAULT_BROWSE_PATH.
const LAST_EPISODE_PATH_KEY = "poiesis.lastEpisodePath";

export function EpisodePicker() {
    const { navigate } = useRouter();

    const [data, setData] = useState<BrowseResult | null>(null);
    const [error, setError] = useState<string | null>(null);

    const load = (path?: string) => {
        setError(null);
        browse(path)
            .then(setData)
            .catch((e) => setError(String(e.message ?? e)));
    };

    useEffect(() => {
        const remembered = localStorage.getItem(LAST_EPISODE_PATH_KEY);
        load(remembered ?? DEFAULT_BROWSE_PATH);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const selectEpisode = (path: string) => {
        localStorage.setItem(LAST_EPISODE_PATH_KEY, path);
        navigate("/episode?path=" + encodeURIComponent(path));
    };

    return (
        <div style={styles.container}>
            <div style={styles.brandBanner}>
                <img src="/poiesis-logo.png" alt="" style={styles.brandLogo} />
                <span style={styles.brandText}>Poiesis</span>
            </div>

            <div style={styles.panel}>
                <div style={styles.currentPath}>{data?.path ?? ""}</div>

                {error && <p style={styles.error}>{error}</p>}

                {!error && !data && <p style={styles.empty}>Loading…</p>}

                {data && (
                    <div style={styles.list}>
                        {data.parent && (
                            <button
                                style={styles.row}
                                onClick={() => load(data.parent!)}
                            >
                                <span style={styles.icon}>⬆</span>
                                <span style={styles.name}>.. (up one level)</span>
                            </button>
                        )}

                        {data.isEpisode && (
                            <button
                                style={{ ...styles.row, ...styles.episodeRow }}
                                onClick={() => selectEpisode(data.path)}
                            >
                                <span style={styles.icon}>📂</span>
                                <span style={styles.name}>Use this folder</span>
                                <span style={styles.badge}>Episode</span>
                            </button>
                        )}

                        {data.entries.length === 0 && (
                            <p style={styles.empty}>No subfolders here.</p>
                        )}

                        {data.entries.map((entry) => (
                            <button
                                key={entry.path}
                                style={{ ...styles.row, ...(entry.isEpisode ? styles.episodeRow : {}) }}
                                onClick={() =>
                                    entry.isEpisode ? selectEpisode(entry.path) : load(entry.path)
                                }
                            >
                                <span style={styles.icon}>{entry.isEpisode ? "📂" : "📁"}</span>
                                <span style={styles.name}>{entry.name}</span>
                                {entry.isEpisode && <span style={styles.badge}>Episode</span>}
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    container: {
        fontFamily: "system-ui, sans-serif",
        color: colors.textPrimary,
        padding: 12,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 12,
    },
    brandBanner: {
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
        padding: "20px 0",
    },
    brandLogo: {
        width: 88,
        height: 88,
        borderRadius: 16,
        objectFit: "cover",
    },
    brandText: {
        fontSize: 26,
        fontWeight: typography.weight.bold,
        color: colors.textPrimary,
        letterSpacing: 0.3,
    },
    panel: {
        width: "100%",
        maxWidth: 640,
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.lg,
        overflow: "hidden",
    },
    currentPath: {
        padding: "10px 14px",
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        borderBottom: `1px solid ${colors.border}`,
        wordBreak: "break-all",
    },
    list: {
        display: "flex",
        flexDirection: "column",
    },
    row: {
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        textAlign: "left",
        padding: "10px 14px",
        background: "none",
        border: "none",
        borderBottom: `1px solid ${colors.surfaceElevated}`,
        color: colors.textPrimary,
        fontSize: typography.size.base,
        cursor: "pointer",
    },
    episodeRow: {
        background: "rgba(255, 165, 0, 0.06)",
    },
    icon: {
        flexShrink: 0,
    },
    name: {
        flex: 1,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
    },
    badge: {
        fontSize: typography.size.xs,
        fontWeight: typography.weight.bold,
        letterSpacing: 0.3,
        textTransform: "uppercase",
        color: colors.warning,
        border: `1px solid ${colors.warning}`,
        borderRadius: radius.sm,
        padding: "2px 6px",
        flexShrink: 0,
    },
    empty: {
        padding: 14,
        fontSize: typography.size.md,
        color: colors.textMuted,
    },
    error: {
        padding: 14,
        fontSize: typography.size.md,
        color: colors.errorStrong,
    },
};
