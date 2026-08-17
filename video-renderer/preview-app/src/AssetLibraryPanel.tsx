import { useEffect, useState } from "react";
import type { ScenePlan } from "video-renderer-src/episode/types";
import { sceneLabel } from "./ActiveSceneBar";
import { contentTypeAndPresentationFor } from "./MomentEditorPanel";
import { momentIndexFromSceneId, normalizeMoment } from "./momentDuration";
import { getAssets, getCodeAssets, getMoments, saveMoments } from "./api";
import { colors, radius, typography } from "./tokens";

interface ImageAsset {
    id: string;
    filename: string;
    caption?: string;
    renderPath: string;
}

interface CodeAsset {
    id: string;
    filename: string;
    language?: string;
    description?: string;
    lineCount?: number;
    renderPath: string;
}

interface Props {
    episodePath: string;
    scenePlan: ScenePlan;
    // The moment currently open in MomentEditorPanel, if any — reused
    // from EpisodeWorkspace's own selectedEditor rather than a second,
    // parallel selection concept. Only {kind: "moment"} is relevant here;
    // title/image editor selections don't have an applicable moment.
    selectedMomentSceneId?: string;
    onSaved: () => void;
}

// A standing, always-browsable library of the episode's indexed images/
// code files (docs: "make it transparent what the pipeline draws assets
// from, and let the user pick instead of just accepting the AI's choice")
// — separate from MomentEditorPanel's own asset dropdown, which only
// exists once a side-image moment is already open. This panel needs no
// moment open at all to be useful: browse first, apply second, matching
// StoryboardPanel's already-established "always visible, collapsible"
// pattern in this same header row rather than being buried in a
// per-moment editor.
export function AssetLibraryPanel({ episodePath, scenePlan, selectedMomentSceneId, onSaved }: Props) {
    const [expanded, setExpanded] = useState(false);
    const [images, setImages] = useState<ImageAsset[]>([]);
    const [codeAssets, setCodeAssets] = useState<CodeAsset[]>([]);
    const [tab, setTab] = useState<"images" | "code">("images");
    const [applyingId, setApplyingId] = useState<string | null>(null);
    const [hint, setHint] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!expanded) return;
        getAssets(episodePath).then(setImages).catch(() => setImages([]));
        getCodeAssets(episodePath).then(setCodeAssets).catch(() => setCodeAssets([]));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [episodePath, expanded]);

    // Unlike StoryboardPanel (which hides itself until populated), this
    // toggle always renders even with zero indexed assets — "nothing
    // indexed yet" is itself useful, transparent information about what
    // the pipeline has to draw from, not a state worth hiding.
    const selectedMoment = selectedMomentSceneId
        ? scenePlan.scenes.find((s) => s.id === selectedMomentSceneId)
        : undefined;

    // Only relevant when a moment is actually selected — governs which
    // asset cards are enabled vs. grayed out below. contentTypeAndPresentationFor
    // returns [null, null] for treatments this model doesn't cover (e.g.
    // bottom-callout/side-text), which correctly disables everything for
    // those, since neither an image nor a code asset applies to them.
    const [selectedContentType] = selectedMoment ? contentTypeAndPresentationFor(selectedMoment) : [null];

    const applyAsset = async (assetId: string, field: "assetId" | "codeAssetId") => {
        if (!selectedMomentSceneId) {
            setHint("Select a moment on the timeline first.");
            return;
        }

        const index = momentIndexFromSceneId(selectedMomentSceneId);
        if (index === null) return;

        setApplyingId(assetId);
        setError(null);
        setHint(null);

        try {
            const data = await getMoments(episodePath);
            const moments = (data.moments ?? []).map(normalizeMoment);
            if (!moments[index]) return;

            moments[index] = { ...moments[index], [field]: assetId };

            await saveMoments(episodePath, moments);
            onSaved();

            // The panel's own fetch above is the authoritative "what's
            // actually indexed" list — comparing against it (not against
            // episodeProps, which only refreshes on enrichment-stage
            // completion and can lag one cycle behind) is what makes this
            // check always accurate right after a fresh index_assets/
            // index_code run.
            const stillIndexed =
                field === "assetId"
                    ? images.some((a) => a.id === assetId)
                    : codeAssets.some((a) => a.id === assetId);

            setHint(
                stillIndexed
                    ? "Applied."
                    : `Saved, but "${assetId}" isn't indexed yet — re-run "${
                          field === "assetId" ? "Index graphics assets" : "Index code assets"
                      }" in Advanced before it will render.`
            );
        } catch (e) {
            setError(String(e));
        } finally {
            setApplyingId(null);
        }
    };

    return (
        <div style={styles.wrap}>
            <button className="secondary" onClick={() => setExpanded((v) => !v)} style={styles.toggle}>
                {expanded ? "Asset library ▾" : "Asset library ▸"}
            </button>

            {expanded && (
                <div style={styles.body}>
                    <p style={styles.hint}>
                        Every image and code file the pipeline can draw from for this episode — browse and
                        apply one to the selected moment, independent of what the AI chose.
                        {selectedMoment
                            ? ` Editing: ${selectedMoment.type} — ${sceneLabel(selectedMoment)}.`
                            : " Select a moment on the timeline to apply an asset."}
                    </p>

                    <div style={styles.tabRow}>
                        <button
                            className={tab === "images" ? undefined : "secondary"}
                            style={styles.tabButton}
                            onClick={() => setTab("images")}
                        >
                            Images ({images.length})
                        </button>
                        <button
                            className={tab === "code" ? undefined : "secondary"}
                            style={styles.tabButton}
                            onClick={() => setTab("code")}
                        >
                            Code ({codeAssets.length})
                        </button>
                    </div>

                    {tab === "images" && (
                        <div style={styles.grid}>
                            {images.length === 0 && (
                                <p style={styles.emptyHint}>
                                    No graphics indexed yet — drop files into the episode's graphics/ folder and
                                    run "Index graphics assets" in Advanced.
                                </p>
                            )}
                            {images.map((asset) => {
                                // A moment is selected but this asset's content type
                                // doesn't match its treatment — disabled rather than
                                // silently ignored on click, so a mismatched click
                                // isn't a confusing no-op.
                                const disabled = !!selectedMoment && selectedContentType !== "image";
                                return (
                                    <button
                                        key={asset.id}
                                        style={{ ...styles.card, ...(disabled ? styles.cardDisabled : {}) }}
                                        onClick={() => applyAsset(asset.id, "assetId")}
                                        disabled={applyingId === asset.id}
                                        title={disabled ? "Selected moment doesn't use an image asset" : asset.filename}
                                    >
                                        <img src={`/${asset.renderPath}`} alt="" style={styles.thumb} />
                                        <span style={styles.cardCaption}>{asset.caption || asset.filename}</span>
                                    </button>
                                );
                            })}
                        </div>
                    )}

                    {tab === "code" && (
                        <div style={styles.grid}>
                            {codeAssets.length === 0 && (
                                <p style={styles.emptyHint}>
                                    No code files indexed yet — drop files into the episode's code/ folder and
                                    run "Index code assets" in Advanced.
                                </p>
                            )}
                            {codeAssets.map((asset) => {
                                const disabled = !!selectedMoment && selectedContentType !== "code";
                                return (
                                    <button
                                        key={asset.id}
                                        style={{ ...styles.codeCard, ...(disabled ? styles.cardDisabled : {}) }}
                                        onClick={() => applyAsset(asset.id, "codeAssetId")}
                                        disabled={applyingId === asset.id}
                                        title={disabled ? "Selected moment doesn't use a code asset" : asset.filename}
                                    >
                                        <span style={styles.codeFilename}>{asset.filename}</span>
                                        {asset.description && <span style={styles.cardCaption}>{asset.description}</span>}
                                        <span style={styles.codeMeta}>
                                            {asset.language}
                                            {asset.lineCount ? ` · ${asset.lineCount} lines` : ""}
                                        </span>
                                    </button>
                                );
                            })}
                        </div>
                    )}

                    {hint && <div style={styles.statusHint}>{hint}</div>}
                    {error && <div style={styles.error}>{error}</div>}
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
        gap: 10,
        padding: "12px 14px",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.lg,
    },
    hint: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        margin: 0,
        lineHeight: typography.lineHeight.relaxed,
    },
    tabRow: {
        display: "flex",
        gap: 8,
    },
    tabButton: {
        fontSize: typography.size.sm,
    },
    grid: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
        gap: 10,
    },
    emptyHint: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        margin: 0,
        gridColumn: "1 / -1",
    },
    card: {
        display: "flex",
        flexDirection: "column",
        gap: 6,
        padding: 8,
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        textAlign: "left",
        cursor: "pointer",
        fontSize: typography.size.sm,
        color: colors.textPrimary,
        fontFamily: "inherit",
        fontWeight: typography.weight.regular,
    },
    codeCard: {
        display: "flex",
        flexDirection: "column",
        gap: 4,
        padding: "10px 12px",
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        textAlign: "left",
        cursor: "pointer",
        fontSize: typography.size.sm,
        color: colors.textPrimary,
        fontFamily: "inherit",
        fontWeight: typography.weight.regular,
    },
    cardDisabled: {
        opacity: 0.4,
        cursor: "default",
    },
    thumb: {
        width: "100%",
        height: 80,
        objectFit: "cover",
        borderRadius: radius.sm,
        background: colors.background,
    },
    cardCaption: {
        fontSize: typography.size.xs,
        color: colors.textSecondary,
        lineHeight: typography.lineHeight.relaxed,
    },
    codeFilename: {
        fontSize: typography.size.sm,
        fontWeight: typography.weight.semibold,
        color: colors.textPrimary,
        fontFamily: "monospace",
    },
    codeMeta: {
        fontSize: typography.size.xs,
        color: colors.textMuted,
    },
    statusHint: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
    },
    error: {
        fontSize: typography.size.sm,
        color: colors.error,
    },
};
