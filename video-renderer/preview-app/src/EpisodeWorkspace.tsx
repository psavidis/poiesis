import { useEffect, useMemo, useRef, useState } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { Episode } from "video-renderer-src/episode/Episode";
import type { EpisodeProps, MomentScene, Scene, ScenePlan } from "video-renderer-src/episode/types";
import { getAssets, getBackgrounds, getCaptionsInfo, getCodeAssets, getManifest, getScenePlan, undoLastEdit, type EpisodeStatus } from "./api";
import { ActiveSceneBar } from "./ActiveSceneBar";
import { AdvancedPanel } from "./AdvancedPanel";
import { AssetLibraryPanel } from "./AssetLibraryPanel";
import { BackgroundBar } from "./BackgroundBar";
import { BeatBar } from "./BeatBar";
import { ChapterStrip } from "./ChapterStrip";
import { EditPlanChat } from "./EditPlanChat";
import { EpisodeAnalysisPanel } from "./EpisodeAnalysisPanel";
import { manifestToEpisodeBaseProps } from "./episodeProps";
import { ImageBar } from "./ImageBar";
import { ImageEditorPanel } from "./ImageEditorPanel";
import { InlineTextEditor, type EditTarget } from "./InlineTextEditor";
import { MomentBar } from "./MomentBar";
import { MomentBoxOverlay } from "./MomentBoxOverlay";
import { MomentEditorPanel } from "./MomentEditorPanel";
import { ProgressFlow } from "./ProgressFlow";
import { RenderStatusBanner } from "./RenderStatusBanner";
import { SceneBar } from "./SceneBar";
import { StoryboardPanel } from "./StoryboardPanel";
import { TitleEditorPanel } from "./TitleEditorPanel";
import { colors, radius, typography } from "./tokens";
import { MAX_ZOOM, MIN_ZOOM, useTimelineZoom } from "./useTimelineZoom";

// Display-only label for the undo shortcut's hint — mirrors BeatBar's own
// MOD_KEY_LABEL constant.
const MOD_KEY_LABEL = navigator.platform.toLowerCase().includes("mac") ? "Cmd" : "Ctrl";

function useQueryParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        episodePath: params.get("path") ?? "",
    };
}

// Everything App.tsx used to render directly — extracted verbatim (see
// #24) so the router root can place this at /episode instead of it being
// the only thing the app can ever show.
//
// Used to also support a "?sceneId=..." scene-scoped mode (a separate
// browser tab, narrower player, OverlayStrip always visible) reached via
// the control panel's "Adjust timing" link — removed in #28. Adjusting a
// moment's timing is now MomentEditorPanel's own "Adjust timing" toggle,
// scoped to whichever moment you clicked, in this same full-episode view.
// That removed the two-buffer problem the old cross-tab design had (this
// component's `moments` state vs. the scene-scoped tab's own copy, kept in
// sync only by a visibilitychange listener re-fetching on focus) — now
// there's exactly one `moments` array, owned by whichever
// MomentEditorPanel is currently open.
export function EpisodeWorkspace() {
    const { episodePath } = useQueryParams();

    const [episodeProps, setEpisodeProps] = useState<EpisodeProps | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [episodeStatus, setEpisodeStatus] = useState<EpisodeStatus | null>(null);
    // Starts false (matching ui/static/app.js's old default — full-
    // sentence captions are tiresome on some episodes) but is corrected
    // to the episode's ACTUAL last-run state as soon as captions.json
    // loads (see #72 — this used to always show unticked on load even for
    // an episode that already had real captions enabled, which read as
    // "captions are off" when they weren't). Owned here (not inside
    // AdvancedPanel) since ProgressFlow's "Start" button needs to read it
    // too.
    const [includeCaptions, setIncludeCaptions] = useState(false);
    // null = captions.json doesn't exist yet (stage never ran on this
    // episode) — genuinely different from {enabled:false/true, count:0},
    // which means it ran and produced zero/some captions. Drives whether
    // "Show captions in this preview" is actionable at all (#72).
    const [captionsInfo, setCaptionsInfo] = useState<{ enabled: boolean; count: number } | null>(null);

    // Bumped every time an edit-plan chat instruction is applied — passed
    // to TitleEditorPanel/MomentEditorPanel so their own fetch effects
    // re-run and pick up whatever the chat just changed. Without this, a
    // chat edit (e.g. "remove the third title card") only updates the
    // player (via reloadScenePlan below); those panels each fetch their
    // own copy of title_scenes.json/moments.json once on mount and have no
    // other reason to refetch, so they'd keep showing the (now stale)
    // pre-chat data. A save from a stale panel afterward would silently
    // resurrect whatever the chat just removed, since PUT
    // /api/episode/title-scenes and .../moments both rebuild their target
    // scenes from scratch out of whatever array the panel sends — see #29.
    // StoryboardPanel isn't included: edit_plan.py only ever writes
    // scene-plan.json, and chapter storyboard notes aren't scenes, so a
    // chat instruction can never make storyboard.json stale.
    const [refreshKey, setRefreshKey] = useState(0);

    // Which scene's editor panel is open, if any — set by clicking a
    // title/moment chip in ActiveSceneBar (see #27). Storyboard has no
    // click-to-open equivalent (chapter-keyed, not scene-anchored), so it
    // isn't part of this state.
    const [selectedEditor, setSelectedEditor] = useState<
        | { kind: "title"; titleText: string }
        | { kind: "moment"; sceneId: string }
        | { kind: "image"; sceneId: string }
        | null
    >(null);

    // Which moment AssetLibraryPanel is targeting — deliberately separate
    // from selectedEditor above, which only tracks a moment when its
    // STRUCTURED editor panel is open. A text-eligible moment (full-visual/
    // side-text/bottom-callout) is clickable and highlightable on
    // MomentBar but never opens that structured panel (Cmd+E does, not a
    // click), so relying on selectedEditor alone left those moments
    // permanently unselectable for the asset panel even though the user
    // had visibly clicked one (see #69). Set on every moment click via
    // MomentBar's onSelect, regardless of treatment.
    const [assetLibraryMomentId, setAssetLibraryMomentId] = useState<string | null>(null);

    // Which of the Advanced/Storyboard/Asset library/Episode analysis
    // panels is open, if any — previously each of these 4 owned its own
    // "expanded" boolean and rendered its own independent toggle button,
    // which is why they used to appear as 4 disconnected, left-aligned
    // buttons stacked vertically with no shared container (#71). Now
    // exactly one tab strip, one shared body box, one thing open at a
    // time — closer to a standard tabbed inspector than 4 unrelated
    // accordions.
    const [activeTab, setActiveTab] = useState<"advanced" | "storyboard" | "assets" | "analysis" | null>(null);
    // Storyboard/Episode analysis tabs hide themselves entirely when their
    // backing data doesn't exist yet (previously each panel's own `return
    // null`) — both components report this up via onHasContentChange
    // since the tab STRIP now owns whether the button appears at all, not
    // each panel body deciding for itself after the fact.
    const [hasStoryboard, setHasStoryboard] = useState(false);
    const [hasAnalysis, setHasAnalysis] = useState(false);

    // The scene currently selected for chat context (see #51) — set when
    // an ActiveSceneBar scene chip is clicked (see #29). Originally this
    // pre-filled the chat's TEXT with "edit <id>: " so the user had to
    // type the rest around it; now it's passed to EditPlanChat as
    // structured context instead, so "make this bigger" resolves against
    // it without any scene id appearing in what the user types (the
    // server still degrades gracefully if this is stale/unset — see
    // edit_plan.describe_selected_scene).
    const [selectedSceneIdForChat, setSelectedSceneIdForChat] = useState<string | undefined>(undefined);

    // The scene(s) an AI chat edit just touched (#54) — routed to whichever
    // bar(s) each id belongs to, below, so the change is visible on the
    // timeline immediately instead of the user needing to find it
    // themselves. Cleared on the next scene-plan reload's own effect below
    // isn't needed: a stale highlight simply won't match anything once the
    // id no longer resolves to a scene of the expected type, and a fresh
    // chat submission always overwrites it with the new result anyway.
    const [highlightedIds, setHighlightedIds] = useState<string[]>([]);

    // The floating text-only editor (see #34) — reached only from SceneBar/
    // MomentBar/ChapterStrip's segment clicks, deliberately NOT from
    // ActiveSceneBar's chips (those keep opening the full structured
    // panel, unchanged, per the decision to avoid touching existing
    // one-click behavior). Mutually exclusive with selectedEditor — opening
    // one closes the other, so there's never two panels racing to save the
    // same underlying array.
    const [inlineEditTarget, setInlineEditTarget] = useState<EditTarget | null>(null);
    const [inlineEditAnchor, setInlineEditAnchor] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

    const openInlineTitleEditor = (titleText: string, anchor: { x: number; y: number }) => {
        setSelectedEditor(null);
        setInlineEditAnchor(anchor);
        setInlineEditTarget({ kind: "title", titleText });
    };

    // Lead-in chapter's own entry point (#83) — distinct from
    // openInlineTitleEditor since there's no existing title to match by
    // text yet; InlineTextEditor's "new-title" branch creates the entry
    // on save instead.
    const openInlineLeadInTitleEditor = (segmentId: string, anchor: { x: number; y: number }) => {
        setSelectedEditor(null);
        setInlineEditAnchor(anchor);
        setInlineEditTarget({ kind: "new-title", newTitleSegmentId: segmentId });
    };

    const openInlineBeatEditor = (sceneId: string, anchor: { x: number; y: number }) => {
        setSelectedEditor(null);
        setInlineEditAnchor(anchor);
        setInlineEditTarget({ kind: "beat", sceneId });
    };

    // Patches the selected beat's text directly in local episodeProps state
    // on every keystroke — playerProps (below) re-derives from this, so the
    // Player picks up the edit immediately, before the real save commits
    // (see #39). The real save (InlineTextEditor's onSaved) still calls
    // reloadScenePlan afterward, which re-fetches from disk and overwrites
    // this local patch with the authoritative value.
    const applyLiveBeatText = (sceneId: string, text: string) => {
        setEpisodeProps((prev) => {
            if (!prev) return prev;
            return {
                ...prev,
                scenePlan: {
                    ...prev.scenePlan,
                    scenes: prev.scenePlan.scenes.map((s) =>
                        s.type === "beat" && s.id === sceneId ? { ...s, text } : s
                    ),
                },
            };
        });
    };

    // Same live-patch-before-real-save pattern as applyLiveBeatText above,
    // for MomentBoxOverlay's drag/resize (#77) — called on every
    // pointermove, not just once at drag-end, so the Player's actual
    // composited output grows/shrinks/moves in step with the drag instead
    // of only jumping to the new box after the save round-trip completes.
    const applyLiveMomentBox = (sceneId: string, box: { xPct: number; yPct: number; widthPct: number; heightPct: number }) => {
        setEpisodeProps((prev) => {
            if (!prev) return prev;
            return {
                ...prev,
                scenePlan: {
                    ...prev.scenePlan,
                    scenes: prev.scenePlan.scenes.map((s) =>
                        s.type === "moment" && s.id === sceneId ? { ...s, box } : s
                    ),
                },
            };
        });
    };

    const playerRef = useRef<PlayerRef>(null);
    // Measured for MomentBoxOverlay's screen-px <-> canvas-% conversion
    // (#77) — the Player fills this frame's width and derives its own
    // height from the composition's aspect ratio, so this div's own
    // rendered rect IS the composition's on-screen box.
    const playerFrameRef = useRef<HTMLDivElement>(null);
    const [currentFrame, setCurrentFrame] = useState(0);

    // Computed unconditionally (episodeProps may still be null on first
    // render, before either of the early returns below) so the shared
    // zoom hook — which must itself be called unconditionally, like any
    // hook — always has a real totalFrames to work with. Mirrors the
    // later, "real" totalFrames computed after episodeProps is confirmed
    // loaded; that duplication is intentional rather than hoisting the
    // whole render past the early returns.
    const totalFramesForZoom = Math.max(
        1,
        episodeProps?.scenePlan.scenes.reduce(
            (total, s) =>
                "timelineStartFrame" in s ? Math.max(total, s.timelineStartFrame + s.durationInFrames) : total,
            0
        ) ?? 1
    );
    // Single zoom/pan window shared by every timeline bar (#86) — replaces
    // each bar's own independent zoom state, so scrolling/zooming one bar
    // keeps them all in sync and there's one Zoom in/out/Reset row instead
    // of one per bar.
    const timelineZoom = useTimelineZoom(totalFramesForZoom, currentFrame);

    // Tracks the player's current frame so the UI can show which scene(s)
    // are actually on screen right now — otherwise there's no way to know
    // which scene id to reference in a natural-language edit instruction
    // without opening scene-plan.json separately. frameupdate fires during
    // both playback and scrubbing, so this stays live either way.
    useEffect(() => {
        const player = playerRef.current;
        if (!player) return;

        const onFrameUpdate = (e: { detail: { frame: number } }) => setCurrentFrame(e.detail.frame);

        player.addEventListener("frameupdate", onFrameUpdate);
        return () => player.removeEventListener("frameupdate", onFrameUpdate);
    }, [episodeProps]);

    // scene-plan.json first exists once analyze_scenes (stage 7 of 15)
    // completes — well before any AI-proposal stage has run. Gate the
    // initial fetch on that stage specifically, rather than firing blindly
    // on mount, so a freshly-started run doesn't 404 its way into the
    // generic error screen while still on stage 1-6 (see #30).
    const scenePlanExists =
        episodeStatus?.stages.find((s) => s.id === "analyze_scenes")?.complete ?? false;

    // Stages whose output enriches scene-plan.json content once analyze_scenes
    // has already produced the plain-cut plan (see pipeline_stages.py — each
    // of these reads scene-plan.json, merges its own proposals in, and
    // rewrites it in place). Joining their complete flags into one string
    // gives a value that only changes when one of THESE stages flips, so the
    // fetch effect below re-runs on real enrichment, not on every 2s status
    // poll tick regardless of whether anything changed.
    const ENRICHMENT_STAGE_IDS = [
        "analyze_scenes",
        "index_assets",
        "index_code",
        "generate_title_scenes",
        "generate_storyboard",
        "generate_moments",
        "generate_captions",
        "generate_emphasis",
    ];
    const enrichmentSignature = (episodeStatus?.stages ?? [])
        .filter((s) => ENRICHMENT_STAGE_IDS.includes(s.id))
        .map((s) => (s.complete ? "1" : "0"))
        .join("");

    useEffect(() => {
        if (!episodePath) {
            setError("No episode path provided (expected ?path=... query param)");
            return;
        }

        if (!scenePlanExists) return;

        Promise.all([
            getScenePlan(episodePath),
            getManifest(episodePath),
            getAssets(episodePath),
            getCodeAssets(episodePath),
            getCaptionsInfo(episodePath),
            getBackgrounds(episodePath),
        ])
            .then(([scenePlan, manifest, assets, codeAssets, captions, backgrounds]) => {
                const baseProps = manifestToEpisodeBaseProps(manifest, assets, codeAssets, backgrounds);
                setEpisodeProps({ ...baseProps, scenePlan: scenePlan as ScenePlan });
                // Corrects "Include captions" from the episode's real
                // last-run state (#72) — only when captions.json actually
                // exists; a fresh episode that's never run this stage
                // keeps whatever the user has already chosen rather than
                // being silently reset to false on every reload.
                if (captions) {
                    setCaptionsInfo(captions);
                    setIncludeCaptions(captions.enabled);
                }
            })
            .catch((e) => {
                // A raw network failure (browser's generic "Failed to
                // fetch"/"NetworkError") almost always means the control
                // panel backend (ui/server.py, normally started via
                // ./start_ui.sh) isn't running — that's a much more
                // actionable message than the raw TypeError.
                if (e instanceof TypeError) {
                    setError(
                        "Can't reach the control panel backend. Make sure it's running: " +
                            "./start_ui.sh from the repo root."
                    );
                } else {
                    setError(String(e));
                }
            });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [episodePath, scenePlanExists, enrichmentSignature]);

    // Re-fetches only scene-plan.json (not manifest/assets, which an edit-plan
    // instruction never changes) and merges it into the existing episodeProps
    // so the player picks up an applied edit without a full page reload. Also
    // bumps refreshKey so any open structured editor re-fetches its own
    // source artifact — see refreshKey's own comment above for why this
    // matters, not just for freshness.
    const reloadScenePlan = () => {
        if (!episodePath) return;
        getScenePlan(episodePath).then((scenePlan) => {
            setEpisodeProps((prev) => (prev ? { ...prev, scenePlan: scenePlan as ScenePlan } : prev));
        });
        setRefreshKey((k) => k + 1);
    };

    // #54 — reloads the plan (same as any other applied edit) and records
    // which scene ids the chat instruction actually touched, so each bar
    // below can seed its own selection/highlight state from whichever of
    // these ids belongs to it.
    const handleChatApplied = (touchedIds: string[]) => {
        reloadScenePlan();
        setHighlightedIds(touchedIds);
    };

    // Splits the touched ids (#54) by which bar owns that scene type, so
    // each bar only ever receives an id it can actually resolve — a
    // multi-scene edit (e.g. remove a title AND create a moment) highlights
    // on both bars at once rather than only the first match winning.
    // ChapterStrip/SceneBar's title highlight is keyed by title TEXT, not
    // sceneId (see their own comments), hence the separate lookup.
    const highlightedByType = useMemo(() => {
        const empty = { presenterOrTitleId: null as string | null, titleText: null as string | null, momentId: null as string | null, beatId: null as string | null, imageId: null as string | null };
        if (!episodeProps) return empty;
        const scenesById = new Map(episodeProps.scenePlan.scenes.map((s) => [s.id, s] as const));
        const result = { ...empty };
        for (const id of highlightedIds) {
            const scene = scenesById.get(id);
            if (!scene) continue;
            if (scene.type === "title") {
                result.presenterOrTitleId ??= id;
                result.titleText ??= scene.text;
            } else if (scene.type === "presenter") {
                result.presenterOrTitleId ??= id;
            } else if (scene.type === "moment") {
                result.momentId ??= id;
            } else if (scene.type === "beat") {
                result.beatId ??= id;
            } else if (scene.type === "image") {
                result.imageId ??= id;
            }
        }
        return result;
    }, [episodeProps, highlightedIds]);

    // #50 — a single Undo button/shortcut covering every write path
    // (moment/beat/title/storyboard/scene-field edits, and edit-plan chat
    // instructions) uniformly, since the server-side checkpoint each of
    // those endpoints saves already knows exactly which files that
    // specific write touched. Reuses reloadScenePlan (same as every other
    // save's onSaved callback) rather than a separate refresh path, so
    // undo's result reaches the player/panels the same way any other edit
    // already does.
    const [undoStatus, setUndoStatus] = useState<string | null>(null);

    const handleUndo = async () => {
        if (!episodePath) return;
        try {
            const result = await undoLastEdit(episodePath);
            if (result.restored) {
                setUndoStatus(`Undid: ${result.restored.label}`);
                reloadScenePlan();
            } else {
                setUndoStatus("Nothing to undo.");
            }
        } catch (e) {
            setUndoStatus(String(e));
        }
    };

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== "z" || !(e.metaKey || e.ctrlKey)) return;
            const target = e.target as HTMLElement | null;
            if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

            e.preventDefault();
            handleUndo();
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [episodePath]);

    // Escape exits whichever structured editor (title/moment/image) is
    // currently open — deliberately global, not scoped to the panel's own
    // DOM (unlike the Cmd+Z/Cmd+E-style shortcuts above, this one should
    // still fire even while focus is inside one of the panel's own text
    // inputs, matching the everywhere-else convention that Escape closes
    // whatever's open). For a moment specifically, this is also what gets
    // the user OUT of "edit mode" — MomentBoxOverlay is only mounted while
    // selectedEditor.kind === "moment" (see selectedMomentScene below), so
    // closing the editor here also removes the drag/resize box from the
    // player, exactly mirroring how it appeared (Cmd+E only) in the first
    // place.
    useEffect(() => {
        if (!selectedEditor) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key !== "Escape") return;
            e.preventDefault();
            setSelectedEditor(null);
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [selectedEditor]);

    // Client-side only — never written back to scene-plan.json. Lets you
    // quickly check "how does this look without captions" without touching
    // saved data; pipeline/generate_captions.py --disable (via the control
    // panel's "Skip captions" checkbox) is the persisted equivalent.
    const [showCaptions, setShowCaptions] = useState(true);

    const playerProps = useMemo(() => {
        if (!episodeProps || showCaptions) return episodeProps;

        return {
            ...episodeProps,
            scenePlan: {
                ...episodeProps.scenePlan,
                scenes: episodeProps.scenePlan.scenes.map((s) =>
                    s.type === "presenter" ? { ...s, effects: { ...s.effects, captions: false } } : s
                ),
            },
        };
    }, [episodeProps, showCaptions]);

    // What's actually on screen at currentFrame: exactly one track scene
    // (presenter/title, absolute timelineStartFrame) plus zero or more
    // overlay scenes (moment/caption/image) anchored to whichever
    // presenter scene is active — so the id shown here is always something
    // that can be typed straight into an edit-plan instruction ("shorten
    // scene-caption-42") without having to open scene-plan.json to find it.
    const activeScenes = useMemo(() => {
        if (!episodeProps) return { track: undefined as Scene | undefined, overlays: [] as Scene[] };

        const scenes = episodeProps.scenePlan.scenes;

        const track = scenes.find(
            (s): s is Scene & { timelineStartFrame: number; durationInFrames: number } =>
                "timelineStartFrame" in s &&
                currentFrame >= s.timelineStartFrame &&
                currentFrame < s.timelineStartFrame + s.durationInFrames
        );

        if (!track) return { track: undefined, overlays: [] };

        const overlays = scenes.filter((s): s is Scene & { parentSceneId: string; offsetInParentFrames: number; durationInFrames: number } => {
            if (!("parentSceneId" in s) || s.parentSceneId !== track.id) return false;
            const start = track.timelineStartFrame + s.offsetInParentFrames;
            return currentFrame >= start && currentFrame < start + s.durationInFrames;
        });

        return { track, overlays };
    }, [episodeProps, currentFrame]);

    const seekToAbsoluteFrame = (absoluteFrame: number) => {
        if (!playerRef.current) return;
        playerRef.current.seekTo(absoluteFrame);
    };

    // The progress flow and Advanced panel render regardless of whether
    // episodeProps has loaded yet — a freshly-picked episode with no
    // pipeline output should show "Start" and empty progress dots, not
    // disappear behind the player's own "Loading preview…"/error guards
    // below. episodePath-less loads (no ?path=) skip both, since there's
    // no episode to run anything against.
    const header = episodePath ? (
        <>
            <div style={styles.brandBanner}>
                {/* Left spacer — same flex basis as undoWrap on the right, so
                    brandGroup stays visually centered via three equal-ish flex
                    regions instead of undoWrap's old position:absolute (which
                    had no reserved space and could overlap brandGroup's text
                    on a narrow viewport — see #45's responsive-behavior pass,
                    docs/specs/poiesis-product-theme-and-ui-design-system.md
                    section 17). An empty div, not text, so it only takes up
                    space, never wraps oddly on its own. */}
                <div style={styles.brandSpacer} />
                <div style={styles.brandGroup}>
                    <img src="/poiesis-logo.png" alt="" style={styles.brandLogo} />
                    <span style={styles.brandText}>Poiesis Preview</span>
                </div>
                <div style={styles.undoWrap}>
                    <button className="secondary small" onClick={handleUndo} title={`Undo the last edit (${MOD_KEY_LABEL}+Z)`}>
                        Undo ({MOD_KEY_LABEL}+Z)
                    </button>
                    {undoStatus && <span style={styles.undoStatus}>{undoStatus}</span>}
                </div>
            </div>
            <ProgressFlow episodePath={episodePath} skipCaptions={!includeCaptions} onStatusChange={setEpisodeStatus} />

            <RenderStatusBanner
                episodePath={episodePath}
                advancedTabOpen={activeTab === "advanced"}
                onOpenAdvanced={() => setActiveTab("advanced")}
            />

            <div style={styles.tabStrip}>
                <button
                    className={activeTab === "advanced" ? undefined : "secondary"}
                    style={styles.tabStripButton}
                    onClick={() => setActiveTab((t) => (t === "advanced" ? null : "advanced"))}
                >
                    Advanced
                </button>
                {hasStoryboard && (
                    <button
                        className={activeTab === "storyboard" ? undefined : "secondary"}
                        style={styles.tabStripButton}
                        onClick={() => setActiveTab((t) => (t === "storyboard" ? null : "storyboard"))}
                    >
                        Storyboard
                    </button>
                )}
                <button
                    className={activeTab === "assets" ? undefined : "secondary"}
                    style={styles.tabStripButton}
                    onClick={() => setActiveTab((t) => (t === "assets" ? null : "assets"))}
                >
                    Asset library
                </button>
                {hasAnalysis && (
                    <button
                        className={activeTab === "analysis" ? undefined : "secondary"}
                        style={styles.tabStripButton}
                        onClick={() => setActiveTab((t) => (t === "analysis" ? null : "analysis"))}
                    >
                        Episode analysis
                    </button>
                )}
            </div>

            {/* One shared box for whichever tab is open — each panel below
                is mounted unconditionally (so its own data effects can run
                and, for Storyboard/Analysis, report hasContent even before
                its tab is ever opened) but only renders visible content
                when it's the active one. */}
            {activeTab && (
                <div style={styles.tabBody}>
                    <AdvancedPanel
                        episodePath={episodePath}
                        status={episodeStatus}
                        onStatusChange={setEpisodeStatus}
                        includeCaptions={includeCaptions}
                        onIncludeCaptionsChange={setIncludeCaptions}
                        isActive={activeTab === "advanced"}
                    />
                    <StoryboardPanel
                        episodePath={episodePath}
                        isActive={activeTab === "storyboard"}
                        onHasContentChange={setHasStoryboard}
                    />
                    {episodeProps && (
                        <AssetLibraryPanel
                            episodePath={episodePath}
                            scenePlan={episodeProps.scenePlan}
                            selectedMomentSceneId={assetLibraryMomentId ?? undefined}
                            onSaved={reloadScenePlan}
                            isActive={activeTab === "assets"}
                            backgrounds={episodeProps.backgrounds ?? []}
                            currentFrame={currentFrame}
                        />
                    )}
                    <EpisodeAnalysisPanel
                        episodePath={episodePath}
                        isActive={activeTab === "analysis"}
                        onHasContentChange={setHasAnalysis}
                    />
                </div>
            )}

            {/* Mounted even while no tab is open, so Storyboard/Analysis's
                own data fetch can still determine tab visibility (#70) —
                isActive: false keeps their bodies from rendering. */}
            {!activeTab && (
                <>
                    <StoryboardPanel episodePath={episodePath} isActive={false} onHasContentChange={setHasStoryboard} />
                    <EpisodeAnalysisPanel episodePath={episodePath} isActive={false} onHasContentChange={setHasAnalysis} />
                </>
            )}
        </>
    ) : null;

    // The chat sidebar (#65 — left-docked, always-visible AI panel instead
    // of a footer strip, matching the left-panel convention other creative
    // tools like Canva use) needs episodeProps for scenePlan context, but
    // should still render even before the plan finishes loading, so the
    // input isn't unavailable during that window — episodePath alone is
    // enough for EditPlanChat's own effects to be safe.
    const sidebar = episodePath ? (
        <div style={styles.sidebar}>
            <EditPlanChat
                episodePath={episodePath}
                onApplied={handleChatApplied}
                selectedSceneId={selectedSceneIdForChat}
                scenePlan={episodeProps?.scenePlan}
            />
        </div>
    ) : null;

    if (error) {
        return (
            <div style={styles.shell}>
                {sidebar}
                <div style={styles.container}>
                    {header}
                    <div style={styles.message}>
                        <div style={styles.messageTitle}>Preview unavailable</div>
                        <div>{error}</div>
                    </div>
                </div>
            </div>
        );
    }

    if (!episodeProps) {
        return (
            <div style={styles.shell}>
                {sidebar}
                <div style={styles.container}>
                    {header}
                    <div style={styles.message}>
                        {scenePlanExists
                            ? "Loading preview…"
                            : "Waiting for the first scene plan (Understand stage)… the preview will appear automatically as soon as it's ready."}
                    </div>
                </div>
            </div>
        );
    }

    // Same value as totalFramesForZoom above (episodeProps is confirmed
    // non-null past this point) — kept as its own binding since every JSX
    // reference below already reads `totalFrames`.
    const totalFrames = totalFramesForZoom;

    // MomentBoxOverlay (#77) only appears once the user has actually
    // entered edit mode for a moment (Cmd+E -> selectedEditor.kind ===
    // "moment", which opens MomentEditorPanel below), NOT on a plain
    // click/select — a merely-selected moment's box would otherwise sit on
    // top of the player at all times, including over Remotion's own
    // play/scrub controls whenever a moment's box happens to cover that
    // area, silently swallowing clicks meant for them. Gating on edit mode
    // means the overlay is only present while the user has deliberately
    // asked to edit this specific moment, mirroring the same "select,
    // then a further deliberate step to act" rule the resize handle
    // itself already follows on MomentBar. Also requires the moment to
    // actually be on screen right now — a moment being edited whose
    // window has scrolled past the playhead has nothing to drag on top of.
    const selectedMomentScene =
        selectedEditor?.kind === "moment" &&
        activeScenes.overlays.find((s): s is MomentScene => s.type === "moment" && s.id === selectedEditor.sceneId);

    return (
        <div style={styles.shell}>
            {sidebar}
            <div style={styles.container}>
            {header}

            <div style={styles.playerWrap}>
                <div style={styles.playerFrame} ref={playerFrameRef}>
                    <Player
                        ref={playerRef}
                        component={Episode as any}
                        inputProps={playerProps}
                        durationInFrames={totalFrames}
                        compositionWidth={episodeProps.width}
                        compositionHeight={episodeProps.height}
                        fps={episodeProps.fps}
                        style={{ width: "100%", display: "block" }}
                        controls
                    />
                    {selectedMomentScene && (
                        <MomentBoxOverlay
                            playerContainerRef={playerFrameRef}
                            scene={selectedMomentScene}
                            episodePath={episodePath}
                            onLiveChange={(box) => applyLiveMomentBox(selectedMomentScene.id, box)}
                            onSaved={reloadScenePlan}
                        />
                    )}
                </div>
            </div>

            <div style={styles.playerWrap}>
                <ChapterStrip
                    scenePlan={episodeProps.scenePlan}
                    videos={episodeProps.videos}
                    totalFrames={totalFrames}
                    currentFrame={currentFrame}
                    fps={episodeProps.fps}
                    onSeek={seekToAbsoluteFrame}
                    onSelectTitle={openInlineTitleEditor}
                    onCreateLeadInTitle={openInlineLeadInTitleEditor}
                    highlightedTitleText={highlightedByType.titleText}
                    episodePath={episodePath}
                    onSaved={reloadScenePlan}
                />
            </div>

            <div style={styles.playerWrap}>
                {/* One shared zoom/pan window for Background/Scenes/Moments/Images/Beats
                    below (#86) — previously each bar had its own independent
                    zoom level and its own row of Zoom in/out/Reset buttons;
                    since they're all views onto the exact same underlying
                    timeline, one control row driving all four at once is
                    both less UI and less confusing (zooming one no longer
                    leaves the others at a different, unrelated scale). */}
                <div style={styles.zoomControls}>
                    <span style={styles.zoomLabel}>Timeline zoom</span>
                    <button
                        className="secondary small"
                        onClick={timelineZoom.zoomIn}
                        disabled={timelineZoom.zoom >= MAX_ZOOM}
                    >
                        Zoom in
                    </button>
                    <button
                        className="secondary small"
                        onClick={timelineZoom.zoomOut}
                        disabled={timelineZoom.zoom <= MIN_ZOOM}
                    >
                        Zoom out
                    </button>
                    <button
                        className="secondary small"
                        onClick={timelineZoom.resetZoom}
                        disabled={timelineZoom.zoom === 1}
                    >
                        Reset
                    </button>
                </div>
            </div>

            <div style={styles.playerWrap}>
                <BackgroundBar
                    scenePlan={episodeProps.scenePlan}
                    totalFrames={totalFrames}
                    currentFrame={currentFrame}
                    onSeek={seekToAbsoluteFrame}
                    episodePath={episodePath}
                    onSaved={reloadScenePlan}
                    backgrounds={episodeProps.backgrounds ?? []}
                    timelineZoom={timelineZoom}
                />
            </div>

            <div style={styles.playerWrap}>
                <SceneBar
                    scenePlan={episodeProps.scenePlan}
                    totalFrames={totalFrames}
                    currentFrame={currentFrame}
                    onSeek={seekToAbsoluteFrame}
                    onSelectTitle={openInlineTitleEditor}
                    highlightedId={highlightedByType.presenterOrTitleId}
                    episodePath={episodePath}
                    onSaved={reloadScenePlan}
                    timelineZoom={timelineZoom}
                />
            </div>

            <div style={styles.playerWrap}>
                <MomentBar
                    scenePlan={episodeProps.scenePlan}
                    totalFrames={totalFrames}
                    currentFrame={currentFrame}
                    onSeek={seekToAbsoluteFrame}
                    episodePath={episodePath}
                    onSaved={reloadScenePlan}
                    onOpenStructuredEditor={(sceneId) => {
                        setInlineEditTarget(null);
                        setSelectedEditor({ kind: "moment", sceneId });
                    }}
                    onSelect={setAssetLibraryMomentId}
                    highlightedId={highlightedByType.momentId}
                    timelineZoom={timelineZoom}
                />
            </div>

            <div style={styles.playerWrap}>
                <ImageBar
                    scenePlan={episodeProps.scenePlan}
                    totalFrames={totalFrames}
                    currentFrame={currentFrame}
                    onSeek={seekToAbsoluteFrame}
                    episodePath={episodePath}
                    onSaved={reloadScenePlan}
                    onEditRequested={(sceneId) => {
                        setInlineEditTarget(null);
                        setSelectedEditor({ kind: "image", sceneId });
                    }}
                    highlightedId={highlightedByType.imageId}
                    timelineZoom={timelineZoom}
                />
            </div>

            <div style={styles.playerWrap}>
                <BeatBar
                    scenePlan={episodeProps.scenePlan}
                    totalFrames={totalFrames}
                    currentFrame={currentFrame}
                    onSeek={seekToAbsoluteFrame}
                    episodePath={episodePath}
                    onSaved={reloadScenePlan}
                    onEditRequested={openInlineBeatEditor}
                    highlightedId={highlightedByType.beatId}
                    timelineZoom={timelineZoom}
                />
            </div>

            {inlineEditTarget && (
                <InlineTextEditor
                    episodePath={episodePath}
                    target={inlineEditTarget}
                    anchor={inlineEditAnchor}
                    onSaved={reloadScenePlan}
                    onClose={() => setInlineEditTarget(null)}
                    onLiveChange={
                        inlineEditTarget.kind === "beat"
                            ? (text) => applyLiveBeatText(inlineEditTarget.sceneId, text)
                            : undefined
                    }
                />
            )}

            <div style={styles.playerWrap}>
                <label
                    style={styles.checkboxRow}
                    title={
                        captionsInfo && captionsInfo.count === 0
                            ? 'No captions exist for this episode yet — tick "Include captions" in Advanced and re-run "Generate captions" first.'
                            : undefined
                    }
                >
                    <input
                        type="checkbox"
                        checked={showCaptions}
                        onChange={(e) => setShowCaptions(e.target.checked)}
                        disabled={!!captionsInfo && captionsInfo.count === 0}
                    />
                    {captionsInfo && captionsInfo.count === 0
                        ? "Show captions in this preview (none generated yet for this episode)"
                        : "Show captions in this preview (view-only — does not change scene-plan.json)"}
                </label>
            </div>

            <div style={styles.playerWrap}>
                <ActiveSceneBar
                    track={activeScenes.track}
                    overlays={activeScenes.overlays}
                    onSelectTitle={(titleText) => {
                        setInlineEditTarget(null);
                        setSelectedEditor({ kind: "title", titleText });
                    }}
                    onSelectMoment={(momentSceneId) => {
                        setInlineEditTarget(null);
                        setSelectedEditor({ kind: "moment", sceneId: momentSceneId });
                    }}
                    onSelectScene={(sceneId) => setSelectedSceneIdForChat(sceneId)}
                />
            </div>

            {selectedEditor?.kind === "title" && (
                <div style={styles.playerWrap}>
                    <TitleEditorPanel
                        episodePath={episodePath}
                        titleText={selectedEditor.titleText}
                        refreshKey={refreshKey}
                        onClose={() => setSelectedEditor(null)}
                    />
                </div>
            )}

            {selectedEditor?.kind === "moment" && (
                <div style={styles.playerWrap}>
                    <MomentEditorPanel
                        episodePath={episodePath}
                        sceneId={selectedEditor.sceneId}
                        scenePlan={episodeProps.scenePlan}
                        currentFrame={currentFrame}
                        onSeek={seekToAbsoluteFrame}
                        refreshKey={refreshKey}
                        onSaved={reloadScenePlan}
                        onClose={() => setSelectedEditor(null)}
                    />
                </div>
            )}

            {selectedEditor?.kind === "image" && (
                <div style={styles.playerWrap}>
                    <ImageEditorPanel
                        episodePath={episodePath}
                        sceneId={selectedEditor.sceneId}
                        scenePlan={episodeProps.scenePlan}
                        onSaved={reloadScenePlan}
                        onClose={() => setSelectedEditor(null)}
                    />
                </div>
            )}

            </div>
        </div>
    );
}

// Matches playerWrap's own maxWidth below — the workspace is centered as
// ONE coherent column (video, timeline, editing controls, AI chat all
// share this width), not just the player in isolation. Previously only
// playerWrap had a maxWidth; the outer container had none and was never
// centered (no margin: 0 auto), so the whole workspace sat flush against
// the left edge of wide viewports — docs/specs/poiesis-product-theme-and-
// ui-design-system.md section 2's "the current interface is visually
// biased toward the left side of the screen."
const WORKSPACE_MAX_WIDTH = 1280;

// Fixed, not resizable — the chat instruction box/result summary never
// needs more than this to stay readable, and a fixed width avoids adding
// drag-to-resize state for a first version (#65).
const SIDEBAR_WIDTH = 340;

const styles: Record<string, React.CSSProperties> = {
    // Top-level app shell: a fixed-width, always-visible AI chat sidebar on
    // the left (#65 — Canva-style left panel, not a footer strip) plus the
    // existing centered workspace column filling the rest of the width.
    shell: {
        display: "flex",
        flexDirection: "row",
        alignItems: "stretch",
        minHeight: "100vh",
    },
    sidebar: {
        width: SIDEBAR_WIDTH,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        padding: 16,
        borderRight: `1px solid ${colors.border}`,
        background: colors.surface,
        // Sticky and viewport-height, matching how Canva's left panel stays
        // pinned while the (much taller) main column scrolls past it.
        // No overflow here, deliberately — EditPlanChat's own message
        // thread is the ONE scrollable region inside the sidebar, so its
        // input row can stay pinned to the sidebar's bottom edge; a second
        // scroll container here would scroll the whole panel (input
        // included) instead of just the conversation history.
        position: "sticky",
        top: 0,
        alignSelf: "flex-start",
        height: "100vh",
        overflow: "hidden",
        // border-box, not the browser default content-box — otherwise this
        // 16px padding adds on TOP of the 100vh height instead of being
        // carved out of it, pushing the form (pinned to the bottom of this
        // box) below the actual viewport with no way to scroll back to it,
        // since overflow is hidden here by design (see above).
        boxSizing: "border-box",
    },
    container: {
        fontFamily: typography.fontFamily,
        color: colors.textPrimary,
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        maxWidth: WORKSPACE_MAX_WIDTH,
        margin: "0 auto",
        flex: 1,
        minWidth: 0,
    },
    // One row of tab buttons (#70/#71) replacing 4 independently-toggled
    // accordion buttons that used to stack vertically with no shared
    // container. A bottom border, not a full box — the strip visually
    // introduces tabBody below it rather than looking like its own
    // separate panel.
    tabStrip: {
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
        borderBottom: `1px solid ${colors.border}`,
        paddingBottom: 10,
    },
    tabStripButton: {
        fontSize: typography.size.md,
    },
    // The one shared box for whichever tab is currently open — every
    // panel used to carry its own near-identical padding/background/
    // border/radius; centralizing it here means exactly one visible box
    // per open tab instead of each panel nesting its own inside this one.
    tabBody: {
        padding: "12px 14px",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderTop: "none",
        borderRadius: `0 0 ${radius.lg}px ${radius.lg}px`,
    },
    // Three-region row (spacer / brandGroup / undoWrap) instead of the
    // previous "justify-content: center + position: absolute undo button"
    // — that had no space reserved for undoWrap at all, so on a narrow
    // viewport a long undoStatus message could overlap the centered brand
    // text. brandSpacer/undoWrap share flex: 1 so brandGroup stays
    // centered at any width, and flexWrap lets the row stack vertically
    // rather than clip/overlap if it ever gets too narrow for one line
    // (spec section 17: "should not become unusable on smaller screens").
    brandBanner: {
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 12,
        padding: "20px 0",
    },
    brandSpacer: {
        flex: 1,
        minWidth: 0,
    },
    brandGroup: {
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        gap: 16,
    },
    undoWrap: {
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: 10,
        minWidth: 0,
    },
    undoStatus: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        maxWidth: 260,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
    },
    brandLogo: {
        width: 88,
        height: 88,
        borderRadius: 16,
        objectFit: "cover",
        flexShrink: 0,
    },
    brandText: {
        fontSize: 26,
        fontWeight: typography.weight.bold,
        color: colors.textPrimary,
        letterSpacing: 0.3,
    },
    playerWrap: {
        width: "100%",
        maxWidth: WORKSPACE_MAX_WIDTH,
    },
    // Shared zoom control row (#86) — mirrors each bar's own former
    // zoomControls/label styling, just promoted to apply once for all of
    // Scenes/Moments/Images/Beats instead of once per bar.
    zoomControls: {
        display: "flex",
        alignItems: "center",
        gap: 6,
    },
    zoomLabel: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
        marginRight: 4,
    },
    // The video is the "primary visual focus" (spec section 12/15) — a
    // deliberate frame (border, radius, shadow) distinguishes it from
    // every other section below, which share plain playerWrap with no
    // framing of their own. overflow: hidden clips the Player's own
    // corners to match the frame's borderRadius.
    playerFrame: {
        position: "relative",
        borderRadius: 10,
        overflow: "hidden",
        border: `1px solid ${colors.border}`,
        boxShadow: "0 8px 28px rgba(0,0,0,0.45)",
    },
    message: {
        fontFamily: typography.fontFamily,
        color: colors.textPrimary,
        padding: 24,
        fontSize: 15,
        lineHeight: 1.5,
        maxWidth: 560,
    },
    messageTitle: {
        fontSize: 18,
        fontWeight: typography.weight.semibold,
        marginBottom: 8,
    },
    checkboxRow: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: typography.size.md,
        color: colors.textSecondary,
        cursor: "pointer",
    },
};
