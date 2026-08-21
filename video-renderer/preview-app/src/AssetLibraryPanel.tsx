import { useEffect, useState } from "react";
import type { BackgroundImageMotion, BackgroundImageMotionSpeed, EpisodeBackground, ScenePlan } from "video-renderer-src/episode/types";
import { contentTypeAndPresentationFor } from "./MomentEditorPanel";
import { momentIndexFromSceneId, normalizeMoment } from "./momentDuration";
import { getAssets, getCodeAssets, getMoments, saveMoments } from "./api";
import { insertBackgroundAtFrame } from "./backgroundInsert";
import { IMAGE_MOTION_OPTIONS, IMAGE_MOTION_SPEED_OPTIONS } from "./BackgroundBar";
import { colors, radius, typography } from "./tokens";

interface ImageAsset {
    id: string;
    filename: string;
    caption?: string;
    renderPath: string;
    mediaType?: "image" | "video";
}

interface CodeAsset {
    id: string;
    filename: string;
    language?: string;
    description?: string;
    lineCount?: number;
    renderPath: string;
    kind?: "source" | "screenshot" | "recording";
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
    // The selectable background library (see index_backgrounds.py) and
    // the player's current frame — the Backgrounds tab below inserts
    // "at the playhead" the exact same way BackgroundBar's own Cmd+B
    // does (same shared backgroundInsert.ts helper), not "apply to the
    // selected moment" the way Images/Code do, since a background has no
    // per-moment concept at all.
    backgrounds: EpisodeBackground[];
    // Live read of the player's actual current frame, used at insert time
    // — `frameupdate`-derived state only updates on the next event and
    // can lag the true playhead by a couple of frames, which showed up as
    // backgrounds inserted "at 0:00" landing a few frames late (see
    // EpisodeWorkspace.tsx).
    getCurrentFrame: () => number;
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

export function AssetLibraryPanel({
    episodePath,
    scenePlan,
    selectedMomentSceneId,
    onSaved,
    isActive,
    backgrounds: backgroundLibrary,
    getCurrentFrame,
}: Props) {
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
    const [tab, setTab] = useState<"images" | "code" | "backgrounds">("images");
    const [applyingId, setApplyingId] = useState<string | null>(null);
    const [hint, setHint] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    // Which background card's direction row is expanded, and within
    // that, which direction's speed row — same nested reveal as
    // BackgroundBar's own Cmd+B picker (see IMAGE_MOTION_OPTIONS/
    // IMAGE_MOTION_SPEED_OPTIONS, imported from there rather than a
    // second copy). Only relevant on the Backgrounds tab.
    const [expandedBackgroundId, setExpandedBackgroundId] = useState<string | null>(null);
    const [expandedBackgroundMotion, setExpandedBackgroundMotion] = useState<BackgroundImageMotion | null>(null);
    const [insertingBackgroundId, setInsertingBackgroundId] = useState<string | null>(null);

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

            // Caption is never auto-filled from the asset's own stored
            // description (#82) — it's opt-in on-screen text the user
            // writes for THIS moment, unrelated to which asset is shown.
            // Swapping the asset leaves an existing caption exactly as-is;
            // the asset's own caption (shown as this card's label above)
            // stays asset metadata, never copied onto the moment.
            moments[index] = {
                ...moments[index],
                [field]: assetId,
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

    // Inserts the given background at the PLAYER'S CURRENT FRAME — not
    // "apply to the selected moment" the way applyAsset above works,
    // since a background has no per-moment concept at all. Same shared
    // helper (and therefore identical semantics — works at any playhead
    // position, splitting an already-covered span there) as
    // BackgroundBar's own Cmd+B, so inserting from this panel behaves
    // exactly the same as inserting from the timeline bar.
    const insertBackground = async (
        backgroundId: string,
        imageMotion?: BackgroundImageMotion,
        imageMotionSpeed?: BackgroundImageMotionSpeed
    ) => {
        setInsertingBackgroundId(backgroundId);
        setError(null);
        setHint(null);

        const result = await insertBackgroundAtFrame(episodePath, getCurrentFrame(), backgroundId, imageMotion, imageMotionSpeed);

        if (result.ok) {
            onSaved();
            setExpandedBackgroundId(null);
            setExpandedBackgroundMotion(null);
            setHint("Inserted — it runs from the current playhead position until the next background or the episode's end.");
        } else {
            setError(result.error);
        }

        setInsertingBackgroundId(null);
    };

    if (!isActive) return null;

    return (
        <div style={styles.body}>
            <p style={styles.hint}>
                        {tab === "backgrounds"
                            ? "Every image/video the pipeline found in this episode's background/ folder — insert one at the player's current position, independent of what's already there."
                            : "Every image and code file the pipeline can draw from for this episode — browse and apply one to the selected moment, independent of what the AI chose."}
                    </p>

                    {tab !== "backgrounds" &&
                        (selectedMoment ? (
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
                        ))}

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
                        <button
                            className={tab === "backgrounds" ? undefined : "secondary"}
                            style={styles.tabButton}
                            onClick={() => setTab("backgrounds")}
                        >
                            Backgrounds ({backgroundLibrary.length})
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
                                        {asset.mediaType === "video" ? (
                                            <video
                                                src={`/${asset.renderPath}`}
                                                muted
                                                playsInline
                                                style={styles.thumb}
                                            />
                                        ) : (
                                            <img src={`/${asset.renderPath}`} alt="" style={styles.thumb} />
                                        )}
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
                                        {asset.kind === "recording" ? (
                                            <video src={`/${asset.renderPath}`} muted playsInline style={styles.thumb} />
                                        ) : asset.kind === "screenshot" ? (
                                            <img src={`/${asset.renderPath}`} alt="" style={styles.thumb} />
                                        ) : null}
                                        <span style={styles.codeFilename}>{asset.filename}</span>
                                        {asset.description && <span style={styles.cardCaption}>{asset.description}</span>}
                                        <span style={styles.codeMeta}>
                                            {asset.kind === "recording"
                                                ? "screen recording"
                                                : asset.kind === "screenshot"
                                                ? "screenshot"
                                                : asset.language}
                                            {asset.lineCount ? ` · ${asset.lineCount} lines` : ""}
                                        </span>
                                    </button>
                                );
                            })}
                        </div>
                    )}

                    {tab === "backgrounds" && (
                        <div style={styles.grid}>
                            {backgroundLibrary.length === 0 && (
                                <p style={styles.emptyHint}>
                                    No files indexed yet — drop images/videos into the episode's background/
                                    folder and run "Index backgrounds" in Advanced.
                                </p>
                            )}
                            {backgroundLibrary.map((bg) => {
                                const isImage = bg.mediaType === "image";
                                const isExpanded = expandedBackgroundId === bg.id;
                                const isInserting = insertingBackgroundId === bg.id;

                                return (
                                    <div key={bg.id} style={styles.card}>
                                        <button
                                            type="button"
                                            style={styles.backgroundCardButton}
                                            disabled={isInserting}
                                            onClick={() => {
                                                if (!isImage) {
                                                    insertBackground(bg.id);
                                                    return;
                                                }
                                                setExpandedBackgroundId(isExpanded ? null : bg.id);
                                                setExpandedBackgroundMotion(null);
                                            }}
                                            title={bg.filename}
                                        >
                                            {bg.mediaType === "video" ? (
                                                <video src={`/${bg.path}`} muted playsInline style={styles.thumb} />
                                            ) : (
                                                <img src={`/${bg.path}`} alt="" style={styles.thumb} />
                                            )}
                                            <span style={styles.cardCaption}>{bg.caption || bg.filename}</span>
                                        </button>
                                        {isExpanded && (
                                            <div style={styles.motionRow}>
                                                {IMAGE_MOTION_OPTIONS.map((option) => {
                                                    if (option.value === "none") {
                                                        return (
                                                            <button
                                                                key={option.value}
                                                                type="button"
                                                                className="secondary small"
                                                                style={styles.motionOption}
                                                                disabled={isInserting}
                                                                onClick={() => insertBackground(bg.id, "none")}
                                                            >
                                                                {option.label}
                                                            </button>
                                                        );
                                                    }

                                                    const isSpeedExpanded = expandedBackgroundMotion === option.value;

                                                    return (
                                                        <div key={option.value}>
                                                            <button
                                                                type="button"
                                                                className="secondary small"
                                                                style={styles.motionOption}
                                                                disabled={isInserting}
                                                                onClick={() =>
                                                                    setExpandedBackgroundMotion(isSpeedExpanded ? null : option.value)
                                                                }
                                                            >
                                                                {option.label}
                                                            </button>
                                                            {isSpeedExpanded && (
                                                                <div style={styles.speedRow}>
                                                                    {IMAGE_MOTION_SPEED_OPTIONS.map((speedOption) => (
                                                                        <button
                                                                            key={speedOption.value}
                                                                            type="button"
                                                                            className="secondary small"
                                                                            style={styles.speedOption}
                                                                            disabled={isInserting}
                                                                            onClick={() =>
                                                                                insertBackground(bg.id, option.value, speedOption.value)
                                                                            }
                                                                        >
                                                                            {speedOption.label}
                                                                        </button>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </div>
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
    // A background card is a plain div (styles.card, reused as a
    // container here) wrapping this actual clickable button plus an
    // optional expanded motion row below it — unlike the Images/Code
    // cards, which are themselves the whole clickable button with
    // nothing else inside.
    backgroundCardButton: {
        display: "flex",
        flexDirection: "column",
        gap: 6,
        width: "100%",
        padding: 0,
        background: "none",
        border: "none",
        textAlign: "left",
        cursor: "pointer",
        fontSize: typography.size.sm,
        color: colors.textPrimary,
        fontFamily: "inherit",
        fontWeight: typography.weight.regular,
    },
    motionRow: {
        display: "flex",
        flexDirection: "column",
        gap: 4,
        marginTop: 6,
        paddingTop: 6,
        borderTop: `1px solid ${colors.border}`,
    },
    motionOption: {
        textAlign: "left",
        fontSize: typography.size.xs,
        width: "100%",
    },
    speedRow: {
        display: "flex",
        flexDirection: "row",
        gap: 4,
        marginTop: 4,
        marginLeft: 8,
        paddingLeft: 6,
        borderLeft: `2px solid ${colors.border}`,
    },
    speedOption: {
        textAlign: "center",
        fontSize: typography.size.xs,
        flex: 1,
    },
};
