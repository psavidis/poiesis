import { useEffect, useState } from "react";
import type { ScenePlan } from "video-renderer-src/episode/types";
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
    isActive: boolean;
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
// Human-readable treatment names — shown in the "Editing: …" status line
// instead of MomentEditorPanel's raw treatment string, since "side-image"/
// "side-diagram" read as internal jargon to someone just trying to tell
// which moment is selected.
const TREATMENT_LABELS: Record<string, string> = {
    "side-image": "inline image",
    "side-code": "inline code",
    "side-diagram": "inline diagram",
    "side-text": "side text",
    "side-terms": "term list",
    "bottom-callout": "bottom callout",
    "full-visual": "full screen",
    "content-dominant-code": "content-dominant code",
};

export function AssetLibraryPanel({ episodePath, scenePlan, selectedMomentSceneId, onSaved, isActive }: Props) {
    const [images, setImages] = useState<ImageAsset[]>([]);
    const [codeAssets, setCodeAssets] = useState<CodeAsset[]>([]);
    // The moment's OWN current assetId/codeAssetId, fetched fresh — not
    // derived from scenePlan, which only carries the fields a given
    // treatment already renders (a side-diagram scene has no assetId key
    // at all in scenePlan even if moments.json happens to carry a stray
    // one). This is what lets a card show "current" and the status line
    // confirm what's actually applied right now, not just what was last
    // clicked.
    const [currentAssetId, setCurrentAssetId] = useState<string | null>(null);
    const [currentCodeAssetId, setCurrentCodeAssetId] = useState<string | null>(null);
    const [tab, setTab] = useState<"images" | "code">("images");
    const [applyingId, setApplyingId] = useState<string | null>(null);
    const [hint, setHint] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!isActive) return;
        getAssets(episodePath).then(setImages).catch(() => setImages([]));
        getCodeAssets(episodePath).then(setCodeAssets).catch(() => setCodeAssets([]));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [episodePath, isActive]);

    useEffect(() => {
        if (!isActive || !selectedMomentSceneId) {
            setCurrentAssetId(null);
            setCurrentCodeAssetId(null);
            return;
        }
        const index = momentIndexFromSceneId(selectedMomentSceneId);
        if (index === null) return;
        getMoments(episodePath).then((data) => {
            const moment = (data.moments ?? [])[index];
            setCurrentAssetId(moment?.assetId ?? null);
            setCurrentCodeAssetId(moment?.codeAssetId ?? null);
        });
    }, [episodePath, isActive, selectedMomentSceneId, hint]);

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

    const selectedTreatmentLabel =
        selectedMoment && "treatment" in selectedMoment
            ? TREATMENT_LABELS[selectedMoment.treatment as string] ?? (selectedMoment.treatment as string)
            : undefined;

    const applyAsset = async (assetId: string, field: "assetId" | "codeAssetId", assetLabel: string) => {
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

            // A moment's caption is a static field copied from the asset
            // at proposal time (generate_moments.py), not resolved live at
            // render time the way codeAsset.description is — so swapping
            // assetId alone leaves the OLD asset's caption showing under
            // the NEW image, which reads as "the image wasn't applied"
            // even though it was. Only image swaps carry this risk (code
            // assets render their description live from codeAssetMap, no
            // stored field to go stale).
            const nextCaption = field === "assetId" ? images.find((a) => a.id === assetId)?.caption : undefined;

            moments[index] = {
                ...moments[index],
                [field]: assetId,
                ...(field === "assetId" ? { caption: nextCaption ?? null } : {}),
            };

            await saveMoments(episodePath, moments);
            onSaved();

            if (field === "assetId") {
                setCurrentAssetId(assetId);
            } else {
                setCurrentCodeAssetId(assetId);
            }

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
                    ? `Applied "${assetLabel}" to this moment. Seek the player to this moment's timestamp to see it, or reopen its editor panel below the timeline.`
                    : `Saved "${assetLabel}", but it isn't indexed yet — re-run "${
                          field === "assetId" ? "Index graphics assets" : "Index code assets"
                      }" in Advanced before it will render.`
            );
        } catch (e) {
            setError(String(e));
        } finally {
            setApplyingId(null);
        }
    };

    if (!isActive) return null;

    return (
        <div style={styles.body}>
            <p style={styles.hint}>
                        Every image and code file the pipeline can draw from for this episode — browse and
                        apply one to the selected moment, independent of what the AI chose.
                    </p>

                    {selectedMoment ? (
                        <p style={styles.selectionStatus}>
                            Editing the <strong>{selectedTreatmentLabel}</strong> moment you selected on the
                            timeline
                            {selectedContentType === "image" || selectedContentType === "code"
                                ? ` — click ${selectedContentType === "image" ? "an image" : "a code file"} below to replace it.`
                                : ". This treatment doesn't use an image or code file, so every card below is disabled."}
                        </p>
                    ) : (
                        <p style={styles.selectionStatus}>
                            No moment selected — click a moment on the timeline first, then come back here to
                            change its image or code.
                        </p>
                    )}

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
                                const isCurrent = !!selectedMoment && currentAssetId === asset.id;
                                return (
                                    <button
                                        key={asset.id}
                                        style={{
                                            ...styles.card,
                                            ...(disabled ? styles.cardDisabled : {}),
                                            ...(isCurrent ? styles.cardCurrent : {}),
                                        }}
                                        onClick={() => applyAsset(asset.id, "assetId", asset.caption || asset.filename)}
                                        disabled={applyingId === asset.id}
                                        title={disabled ? "Selected moment doesn't use an image asset" : asset.filename}
                                    >
                                        {isCurrent && <span style={styles.currentBadge}>Currently used</span>}
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
                                const isCurrent = !!selectedMoment && currentCodeAssetId === asset.id;
                                return (
                                    <button
                                        key={asset.id}
                                        style={{
                                            ...styles.codeCard,
                                            ...(disabled ? styles.cardDisabled : {}),
                                            ...(isCurrent ? styles.cardCurrent : {}),
                                        }}
                                        onClick={() => applyAsset(asset.id, "codeAssetId", asset.filename)}
                                        disabled={applyingId === asset.id}
                                        title={disabled ? "Selected moment doesn't use a code asset" : asset.filename}
                                    >
                                        {isCurrent && <span style={styles.currentBadge}>Currently used</span>}
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
    );
}

const styles: Record<string, React.CSSProperties> = {
    body: {
        display: "flex",
        flexDirection: "column",
        gap: 10,
    },
    hint: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        margin: 0,
        lineHeight: typography.lineHeight.relaxed,
    },
    // Deliberately more prominent than `hint` above — this is the direct
    // answer to "what am I about to change," not background explanation,
    // so it reads at full brightness rather than muted.
    selectionStatus: {
        fontSize: typography.size.sm,
        color: colors.textPrimary,
        margin: 0,
        padding: "6px 10px",
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
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
    // Gold accent border — the same signal EditPlanChat's own user-bubble
    // glow uses for "this is yours/active," reused here for "this is
    // what's currently assigned," so the two don't invent unrelated
    // visual languages for a similar idea.
    cardCurrent: {
        borderColor: colors.accent,
        borderWidth: 2,
    },
    currentBadge: {
        alignSelf: "flex-start",
        fontSize: typography.size.xs,
        fontWeight: typography.weight.bold,
        letterSpacing: 0.4,
        textTransform: "uppercase",
        color: colors.accent,
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
