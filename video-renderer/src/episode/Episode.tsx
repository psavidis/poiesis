import {
    AbsoluteFill,
    Audio,
    Easing,
    Loop,
    OffthreadVideo,
    Sequence,
    interpolate,
    staticFile,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

import type { EpisodeAsset, EpisodeCodeAsset, EpisodeProps, EpisodeVideo, MomentScene, PresenterScene, Scene, TitleScene } from "./types";
import { AnimatedTitle } from "./AnimatedTitle";
import { BeatOverlay } from "./BeatOverlay";
import { CaptionText } from "./CaptionText";
import { CodeBlock } from "./CodeBlock";
import { Comparison } from "./Comparison";
import { DiagramBlock } from "./DiagramBlock";
import { EpisodeImage } from "./EpisodeImage";
import { FullVisualMoment } from "./FullVisualMoment";
import { BottomCallout, SideImage, SideText } from "./MomentTreatments";
import { SideTerms } from "./SideTerms";
import { LAYOUT_GEOMETRY, TRANSITION_FRAMES } from "./timing";

// A crossfade "borrows" a few extra source frames immediately before a
// clip's own silence-trimmed sourceStartFrame (real footage that exists,
// just trimmed as dead air) so the incoming clip has something to fade in
// from other than black — the same technique an editor uses when trimming
// leaves no natural pre-roll. Kept short specifically so it stays
// unnoticeable: CLAUDE.md's "animations should feel intentional rather
// than distracting" applies here as much as to moments.
export const CROSSFADE_TRANSITION_FRAMES = 9; // 0.3s at 30fps

// A window (in frames local to a presenter scene) during which the
// presenter should be off-center, derived from a single moment's own
// on-screen span — NOT the whole presenter scene. This is the fix for the
// bug where the presenter used to shift for a whole (possibly 60s+) scene
// even though the side content it was making room for was only visible for
// a few seconds: the presenter now only leaves center immediately before
// the moment appears and returns immediately after it ends.
export interface LayoutWindow {
    // Frame (local to the scene) the slide-out begins — moment's own start
    // minus TRANSITION_FRAMES, clamped to the scene's own bounds.
    start: number;
    // Frame the slide-back-to-center completes — moment's own end plus
    // TRANSITION_FRAMES, clamped.
    end: number;
    // "left"/"right": presenter slides to that side, narrowed. "corner":
    // presenter shrinks to a small picture-in-picture box (#48's
    // "content-dominant-code" — code fills most of the frame, presenter
    // stays visible but small) — reuses the same width/left/top/height
    // interpolation as left/right (see LAYOUT_GEOMETRY's "corner" entry),
    // just a different geometry, not a different animation mechanism.
    // "hidden": presenter fades out entirely (a "full-visual" moment)
    // rather than moving — AnimatedPresenterFrame handles this as an
    // opacity fade, not a width/left interpolation, since there's no
    // meaningful position to slide toward when the presenter isn't on
    // screen at all.
    side: "left" | "right" | "corner" | "hidden";
}

export const layoutWindowsForScene = (scene: PresenterScene, moments: MomentScene[]): LayoutWindow[] => {
    const windows = moments
        .filter(
            (m) =>
                m.parentSceneId === scene.id &&
                (m.presenterSide || m.treatment === "full-visual" || m.treatment === "content-dominant-code")
        )
        .map((m) => ({
            start: Math.max(0, m.offsetInParentFrames - TRANSITION_FRAMES),
            end: Math.min(scene.durationInFrames, m.offsetInParentFrames + m.durationInFrames + TRANSITION_FRAMES),
            side:
                m.treatment === "full-visual"
                    ? ("hidden" as const)
                    : m.treatment === "content-dominant-code"
                    ? ("corner" as const)
                    : (m.presenterSide as "left" | "right"),
        }))
        .sort((a, b) => a.start - b.start);

    return windows;
};

// Frame ranges (local to a presenter scene) during which the transcript
// caption track should be hidden — two distinct reasons, both because a
// moment is occupying the same bottom-center real estate a caption would
// otherwise render into:
//
// - "bottom-callout" doesn't move the presenter (so layoutWindowsForScene
//   doesn't cover it) but sits in the same bottom-center spot as a caption.
//   A callout is a short, verbatim quote from the same speech a caption
//   would otherwise show underneath it, so hiding the caption for exactly
//   the callout's own (unpadded — this isn't a slide animation with a
//   transition pad, just an occupancy window) on-screen window doesn't lose
//   information the viewer needs. Confirmed against a real render: a
//   two-line callout's box grows tall enough to overlap the caption sitting
//   just below it.
//
// - "full-visual" hides the presenter entirely, but the transcript caption
//   track isn't tied to the presenter's own visibility — nothing previously
//   stopped it from continuing to render at its normal bottom position
//   while EpisodeImage/DiagramBlock/FullText's OWN caption or content
//   occupies that same space. Confirmed against a real render (Episode 9's
//   full-screen cables shot): the transcript caption rendered UNDER the
//   full-visual's bordered frame, half-obscured. Uses the SAME padded
//   window as layoutWindowsForScene's "hidden" case (not full-visual's bare
//   offset/duration) so the caption disappears in sync with the presenter's
//   own fade, not a beat early/late relative to it.
//
// Scoped to the same parent scene, frames local to that scene — the same
// convention layoutWindowsForScene and CaptionText's own offset already use.
export const captionHiddenWindowsForScene = (
    scene: PresenterScene,
    moments: MomentScene[]
): { start: number; end: number }[] =>
    moments
        .filter((m) => m.parentSceneId === scene.id && (m.treatment === "bottom-callout" || m.treatment === "full-visual"))
        .map((m) => {
            if (m.treatment === "full-visual") {
                return {
                    start: Math.max(0, m.offsetInParentFrames - TRANSITION_FRAMES),
                    end: Math.min(scene.durationInFrames, m.offsetInParentFrames + m.durationInFrames + TRANSITION_FRAMES),
                };
            }

            return {
                start: m.offsetInParentFrames,
                end: m.offsetInParentFrames + m.durationInFrames,
            };
        });

// Defensive clamp for a moment's rendered duration: generate_moments.py's
// propose_moments() reserves room for TRANSITION_FRAMES at proposal time
// (so this is normally a no-op), but this is the last line of defense
// against any producer that doesn't go through that clamp — a human
// hand-editing moments.json/scene-plan.json directly, or a future
// natural-language edit-plan instruction touching durationInFrames.
// Without this, content could outlive the presenter's own
// already-clamped slide-back-to-center window (layoutWindowsForScene's
// `end`, above), desyncing the two. Exported as a pure function so it can
// be tested directly against layoutWindowsForScene for the same scene.
export const clampedMomentDuration = (scene: MomentScene, parent: PresenterScene): number => {
    return Math.max(
        0,
        Math.min(scene.durationInFrames, parent.durationInFrames - scene.offsetInParentFrames)
    );
};

// A stable left/right side per beat, derived from its own id rather than
// a new data field — generate_emphasis.py's merge step generates ids as
// exactly f"scene-beat-{index}" (the array index in emphasis.json, same
// exact-index convention generate_moments.py uses for scene-moment-{N}),
// so alternating on that index gives a deterministic split with no
// pipeline/schema change: every beat already has a stable position
// without needing an AI or human decision about which side it goes on.
// Falls back to "left" for any id that doesn't match the convention
// (shouldn't happen for a real pipeline-produced scene, but a component
// prop still needs a defined value rather than throwing).
export const beatSideForSceneId = (sceneId: string): "left" | "right" => {
    const match = /^scene-beat-(\d+)$/.exec(sceneId);
    if (!match) return "left";
    return Number(match[1]) % 2 === 0 ? "left" : "right";
};

// How many frames this scene should crossfade in from its predecessor —
// 0 means a hard cut (today's only behavior when absent). Borrows real,
// already-existing footage immediately before this scene's own
// sourceStartFrame (the silence-trim dead air) rather than inventing
// content, and is clamped so it never borrows more than either neighbor
// actually has available:
//   - this scene's own sourceStartFrame (can't play frames before 0)
//   - the previous scene's durationInFrames (can't overlap past its own start)
export const crossfadeInFramesForScene = (scene: PresenterScene, previousScene: PresenterScene | undefined): number => {
    if (scene.effects.transition !== "crossfade" || !previousScene) {
        return 0;
    }

    return Math.max(
        0,
        Math.min(CROSSFADE_TRANSITION_FRAMES, scene.sourceStartFrame, previousScene.durationInFrames)
    );
};

const PresenterSequence = ({
                                scene,
                                video,
                                layoutWindows,
                                crossfadeInFrames,
                            }: {
    scene: PresenterScene;
    video: EpisodeVideo;
    // This scene's own moment-driven shift windows (see layoutWindowsForScene)
    // — everything the animation needs to know is local to this scene, no
    // adjacency with neighboring presenter scenes required anymore.
    layoutWindows: LayoutWindow[];
    // See crossfadeInFramesForScene — already resolved/clamped by the
    // caller, so this component only needs the final frame count.
    crossfadeInFrames: number;
}) => {
    return (
        <Sequence
            from={scene.timelineStartFrame - crossfadeInFrames}
            durationInFrames={scene.durationInFrames + crossfadeInFrames}
        >
            <AnimatedPresenterFrame
                video={video}
                scene={scene}
                layoutWindows={layoutWindows}
                crossfadeInFrames={crossfadeInFrames}
            />
        </Sequence>
    );
};

const AnimatedPresenterFrame = ({
                                     video,
                                     scene,
                                     layoutWindows,
                                     crossfadeInFrames,
                                 }: {
    video: EpisodeVideo;
    scene: PresenterScene;
    layoutWindows: LayoutWindow[];
    crossfadeInFrames: number;
}) => {
    // Raw frame local to this Sequence, whose clock now starts
    // crossfadeInFrames before the scene's true timelineStartFrame (see
    // PresenterSequence). sceneFrame re-aligns back to "0 at the scene's
    // real start" — the same meaning layoutWindows/trim math already
    // assumed before crossfades existed — so only the crossfade-specific
    // code below needs to know about the borrowed lead-in at all.
    const rawFrame = useCurrentFrame();
    const sceneFrame = rawFrame - crossfadeInFrames;

    const centerGeo = LAYOUT_GEOMETRY.center;

    // Find the window (if any) whose padded span contains the current
    // frame, and interpolate: center -> side across the leading pad, hold
    // at the side for the moment's own span, side -> center across the
    // trailing pad. Frames outside every window stay at dead center — most
    // of a long scene is unaffected, which is the whole point of the fix.
    const activeWindow = layoutWindows.find((w) => sceneFrame >= w.start && sceneFrame < w.end);
    const isHidden = activeWindow?.side === "hidden";

    let widthPct = centerGeo.widthPct;
    let leftPct = centerGeo.leftPct;
    let topPct = centerGeo.topPct;
    let heightPct = centerGeo.heightPct;

    if (activeWindow && activeWindow.side !== "hidden") {
        const sideGeo = LAYOUT_GEOMETRY[activeWindow.side];
        const enterEnd = Math.min(activeWindow.start + TRANSITION_FRAMES, activeWindow.end);
        const exitStart = Math.max(activeWindow.end - TRANSITION_FRAMES, enterEnd);

        // Eased (not linear) so the slide reads as a deliberate, weighted
        // move rather than a mechanical pan — accelerates out of center,
        // decelerates into the side position (and the mirror on the way
        // back), same easing on both edges since inOut is symmetric.
        widthPct = interpolate(
            sceneFrame,
            [activeWindow.start, enterEnd, exitStart, activeWindow.end],
            [centerGeo.widthPct, sideGeo.widthPct, sideGeo.widthPct, centerGeo.widthPct],
            { easing: Easing.inOut(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );

        leftPct = interpolate(
            sceneFrame,
            [activeWindow.start, enterEnd, exitStart, activeWindow.end],
            [centerGeo.leftPct, sideGeo.leftPct, sideGeo.leftPct, centerGeo.leftPct],
            { easing: Easing.inOut(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );

        // topPct/heightPct are a no-op (0/100 -> 0/100) for left/right,
        // since only "corner" (#48) actually varies them — kept as a
        // uniform interpolation rather than a conditional branch so the
        // corner PiP's shrink animates in sync with the width/left slide
        // instead of needing its own separate enter/exit timing.
        topPct = interpolate(
            sceneFrame,
            [activeWindow.start, enterEnd, exitStart, activeWindow.end],
            [centerGeo.topPct, sideGeo.topPct, sideGeo.topPct, centerGeo.topPct],
            { easing: Easing.inOut(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );

        heightPct = interpolate(
            sceneFrame,
            [activeWindow.start, enterEnd, exitStart, activeWindow.end],
            [centerGeo.heightPct, sideGeo.heightPct, sideGeo.heightPct, centerGeo.heightPct],
            { easing: Easing.inOut(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
    }

    // "full-visual" fade: the presenter stays at center geometry (no
    // width/left shift — there's no side to move toward) but fades to
    // fully transparent for the window's held span, same enter/exit pad as
    // the side treatments' slide. The video keeps playing underneath
    // (audio always does, per the Sequence below) — this only hides the
    // picture, matching "voice continues as narration" from the design.
    let hiddenOpacity = 1;

    if (isHidden && activeWindow) {
        const enterEnd = Math.min(activeWindow.start + TRANSITION_FRAMES, activeWindow.end);
        const exitStart = Math.max(activeWindow.end - TRANSITION_FRAMES, enterEnd);

        hiddenOpacity = interpolate(
            sceneFrame,
            [activeWindow.start, enterEnd, exitStart, activeWindow.end],
            [1, 0, 0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
    }

    // The video itself always renders at the composition's full 1920x1080
    // size and crop (cover against 100%/100%) — the presenter's on-screen
    // scale never changes between center and a side layout. Only the
    // visible *window* onto that fixed-scale video narrows (via the outer
    // div's overflow: hidden + width), and the video is shifted left/right
    // inside that window so the presenter (who was framed centered in the
    // original shot) stays centered in whatever window is currently
    // visible, rather than shifting the video's own crop/zoom to fit a
    // narrower box (which is what made the presenter appear to shrink).
    //
    // outerLeftPct/outerWidthPct: the visible clipping window, as a
    // fraction of the full composition — same as leftPct/widthPct above.
    //
    // The inner video div is rendered at (100/outerWidthPct)*100% of the
    // window's own width, so at 100% scale relative to the composition —
    // i.e. video position 0%/100% (its own left/right edges) map to
    // composition position 0%/100%, regardless of how narrow the window
    // is. videoShiftPct positions that div (in window-relative %) so
    // composition position 50% (where the presenter is framed) lands at
    // the window's own horizontal center, keeping the presenter visually
    // centered in whatever window is currently visible.
    const outerLeftPct = leftPct;
    const outerWidthPct = widthPct;
    const videoDivWidthPct = outerWidthPct === 0 ? 100 : (100 / outerWidthPct) * 100;
    const videoShiftPct = 50 - (videoDivWidthPct / 2);

    // Vertical mirror of the above — a no-op (0/100 in, 0/100 out) for
    // every layout except "corner" (#48), where the presenter's window
    // shrinks vertically as well as horizontally rather than always
    // spanning the full frame height the way left/right/center do.
    const outerTopPct = topPct;
    const outerHeightPct = heightPct;
    const videoDivHeightPct = outerHeightPct === 0 ? 100 : (100 / outerHeightPct) * 100;
    const videoVerticalShiftPct = 50 - (videoDivHeightPct / 2);

    // Fades in from 0 across the borrowed lead-in (rawFrame 0..crossfadeInFrames)
    // — during that window the outgoing scene's own tail is still rendering
    // underneath (it ends exactly at this scene's true timelineStartFrame,
    // unaffected by this scene's borrowed lead-in), so this dissolves over
    // it rather than cutting. crossfadeInFrames is 0 for every scene that
    // isn't set to "crossfade" or has no previous scene to fade from, so
    // this is a no-op (opacity pinned to 1) for the common case.
    const crossfadeOpacity =
        crossfadeInFrames === 0
            ? 1
            : interpolate(rawFrame, [0, crossfadeInFrames], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
              });

    const opacity = crossfadeOpacity * hiddenOpacity;

    return (
        <AbsoluteFill style={{ opacity }}>
            <div
                style={{
                    position: "absolute",
                    top: `${outerTopPct}%`,
                    height: `${outerHeightPct}%`,
                    left: `${outerLeftPct}%`,
                    width: `${outerWidthPct}%`,
                    overflow: "hidden",
                }}
            >
                <div
                    style={{
                        position: "absolute",
                        top: `${videoVerticalShiftPct}%`,
                        height: `${videoDivHeightPct}%`,
                        left: `${videoShiftPct}%`,
                        width: `${videoDivWidthPct}%`,
                    }}
                >
                    <OffthreadVideo
                        src={staticFile(video.keyedPath ?? video.path)}
                        trimBefore={scene.sourceStartFrame - crossfadeInFrames}
                        trimAfter={scene.sourceEndFrame}
                        transparent={Boolean(video.keyedPath)}
                        muted
                        style={{
                            width: "100%",
                            height: "100%",
                            objectFit: "cover",
                        }}
                    />
                </div>
            </div>
            {/* Nested in its own Sequence, offset past the borrowed video
                lead-in, so audio still cuts cleanly at this scene's true
                start rather than starting crossfadeInFrames early and
                overlapping the outgoing scene's own tail narration — only
                the video dissolves, matching how a hard-cut edit with a
                video crossfade (but no audio crossfade) normally sounds. */}
            <Sequence from={crossfadeInFrames} durationInFrames={scene.durationInFrames}>
                <Audio
                    src={staticFile(video.path)}
                    trimBefore={scene.sourceStartFrame}
                    trimAfter={scene.sourceEndFrame}
                />
            </Sequence>
        </AbsoluteFill>
    );
};

const LoopingBackground = ({ path, duration }: { path: string; duration: number }) => {
    const { fps } = useVideoConfig();

    const durationInFrames = Math.round(duration * fps);

    return (
        <Loop durationInFrames={durationInFrames}>
            <OffthreadVideo
                src={staticFile(path)}
                muted
                style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                }}
            />
        </Loop>
    );
};

const MomentSequence = ({
                             scene,
                             asset,
                             codeAsset,
                         }: {
    scene: MomentScene;
    asset: EpisodeAsset | undefined;
    codeAsset: EpisodeCodeAsset | undefined;
}) => {
    switch (scene.treatment) {
        case "bottom-callout":
            return <BottomCallout text={scene.text ?? ""} entrance={scene.entrance} />;

        case "side-text": {
            const presenterOnLeft = scene.presenterSide === "left";
            return <SideText text={scene.text ?? ""} presenterOnLeft={presenterOnLeft} style={scene.sideTextStyle} />;
        }

        case "side-image": {
            if (!asset) return null;
            const presenterOnLeft = scene.presenterSide === "left";
            return (
                <SideImage
                    path={asset.path}
                    caption={scene.caption}
                    presenterOnLeft={presenterOnLeft}
                />
            );
        }

        case "side-code": {
            if (!codeAsset) return null;
            const presenterOnLeft = scene.presenterSide === "left";
            return (
                <CodeBlock
                    path={codeAsset.path}
                    language={codeAsset.language}
                    presenterOnLeft={presenterOnLeft}
                />
            );
        }

        case "content-dominant-code": {
            // No presenterSide — the presenter shrinks to a fixed
            // bottom-right corner PiP (LAYOUT_GEOMETRY.corner) rather than
            // moving to a chosen side, so there's no left/right slide
            // direction to pass through.
            if (!codeAsset) return null;
            return (
                <CodeBlock
                    path={codeAsset.path}
                    language={codeAsset.language}
                    presenterOnLeft={false}
                    size="dominant"
                />
            );
        }

        case "side-diagram": {
            if (!scene.diagram) return null;
            const presenterOnLeft = scene.presenterSide === "left";
            return <DiagramBlock diagram={scene.diagram} presenterOnLeft={presenterOnLeft} />;
        }

        case "side-terms": {
            if (!scene.terms || scene.terms.length === 0) return null;
            const presenterOnLeft = scene.presenterSide === "left";
            return <SideTerms terms={scene.terms} presenterOnLeft={presenterOnLeft} />;
        }

        case "comparison": {
            if (!scene.comparison) return null;
            return <Comparison comparison={scene.comparison} />;
        }

        case "full-visual": {
            if (!scene.fullVisualKind) return null;
            return (
                <FullVisualMoment
                    kind={scene.fullVisualKind}
                    text={scene.text}
                    assetPath={asset?.path}
                    caption={scene.caption}
                    diagram={scene.diagram}
                    codePath={codeAsset?.path}
                    codeLanguage={codeAsset?.language}
                />
            );
        }
    }
};

export const Episode = ({
                            videos,
                            assets,
                            codeAssets,
                            backgroundVideo,
                            scenePlan: typedScenePlan,
                            onlyTypes,
                        }: EpisodeProps) => {

    const videoMap = new Map(
        videos.map((video) => [
            video.id,
            video,
        ])
    );

    const assetMap = new Map(
        assets.map((asset) => [
            asset.id,
            asset,
        ])
    );

    const codeAssetMap = new Map(
        (codeAssets ?? []).map((codeAsset) => [
            codeAsset.id,
            codeAsset,
        ])
    );

    const presenterSceneMap = new Map(
        typedScenePlan.scenes
            .filter((scene): scene is PresenterScene => scene.type === "presenter")
            .map((scene) => [scene.id, scene])
    );

    const momentScenes = typedScenePlan.scenes.filter(
        (scene): scene is MomentScene => scene.type === "moment"
    );

    // A presenter scene should only crossfade from its immediate track
    // predecessor if that predecessor is ALSO a presenter scene with no
    // gap — a title card (or anything else) sitting between two presenter
    // scenes means there's no adjacent presenter footage to dissolve from,
    // just the title's own display window. Built from every track scene
    // (presenter + title), not presenterSceneMap alone, so a title in
    // between is actually visible to this adjacency check instead of being
    // silently skipped over.
    const orderedTrackScenes = typedScenePlan.scenes
        .filter((scene): scene is PresenterScene | TitleScene => "timelineStartFrame" in scene)
        .sort((a, b) => a.timelineStartFrame - b.timelineStartFrame);

    const previousPresenterSceneById = new Map<string, PresenterScene | undefined>();

    orderedTrackScenes.forEach((scene, index) => {
        if (scene.type !== "presenter") {
            return;
        }

        const previous = orderedTrackScenes[index - 1];

        const isDirectlyAdjacentPresenter =
            previous?.type === "presenter" &&
            previous.timelineStartFrame + previous.durationInFrames === scene.timelineStartFrame;

        previousPresenterSceneById.set(scene.id, isDirectlyAdjacentPresenter ? previous : undefined);
    });

    const renderScene = (scene: Scene) => {
        if (onlyTypes && !onlyTypes.includes(scene.type)) {
            return null;
        }

        switch (scene.type) {
            case "presenter": {
                const video = videoMap.get(scene.videoId);

                if (!video) {
                    return null;
                }

                return (
                    <PresenterSequence
                        key={scene.id}
                        scene={scene}
                        video={video}
                        layoutWindows={layoutWindowsForScene(scene, momentScenes)}
                        crossfadeInFrames={crossfadeInFramesForScene(scene, previousPresenterSceneById.get(scene.id))}
                    />
                );
            }

            case "title": {
                return (
                    <Sequence
                        key={scene.id}
                        from={scene.timelineStartFrame}
                        durationInFrames={scene.durationInFrames}
                    >
                        <AnimatedTitle text={scene.text} />
                    </Sequence>
                );
            }

            case "moment": {
                const parent = presenterSceneMap.get(scene.parentSceneId);

                if (!parent) {
                    return null;
                }

                const asset = scene.assetId ? assetMap.get(scene.assetId) : undefined;
                const codeAsset = scene.codeAssetId ? codeAssetMap.get(scene.codeAssetId) : undefined;

                const durationInFrames = clampedMomentDuration(scene, parent);

                if (durationInFrames <= 0) {
                    return null;
                }

                return (
                    <Sequence
                        key={scene.id}
                        from={parent.timelineStartFrame + scene.offsetInParentFrames}
                        durationInFrames={durationInFrames}
                    >
                        <MomentSequence scene={scene} asset={asset} codeAsset={codeAsset} />
                    </Sequence>
                );
            }

            case "image": {
                const asset = assetMap.get(scene.assetId);
                const parent = presenterSceneMap.get(scene.parentSceneId);

                if (!asset || !parent) {
                    return null;
                }

                return (
                    <Sequence
                        key={scene.id}
                        from={parent.timelineStartFrame + scene.offsetInParentFrames}
                        durationInFrames={scene.durationInFrames}
                    >
                        <EpisodeImage
                            path={asset.path}
                            caption={scene.caption}
                            display={scene.display}
                        />
                    </Sequence>
                );
            }

            case "caption": {
                const parent = presenterSceneMap.get(scene.parentSceneId);

                if (!parent || !parent.effects.captions) {
                    return null;
                }

                // Re-expressed relative to this caption's own Sequence clock
                // (which starts at 0 at scene.offsetInParentFrames, not at
                // the parent scene's start) — see
                // captionHiddenWindowsForScene for why this suppression
                // exists at all.
                const hiddenWindows = captionHiddenWindowsForScene(parent, momentScenes)
                    .map((w) => ({
                        start: w.start - scene.offsetInParentFrames,
                        end: w.end - scene.offsetInParentFrames,
                    }))
                    .filter((w) => w.start < scene.durationInFrames && w.end > 0);

                return (
                    <Sequence
                        key={scene.id}
                        from={parent.timelineStartFrame + scene.offsetInParentFrames}
                        durationInFrames={scene.durationInFrames}
                    >
                        <CaptionText text={scene.text} hiddenWindows={hiddenWindows} />
                    </Sequence>
                );
            }

            case "beat": {
                const parent = presenterSceneMap.get(scene.parentSceneId);

                if (!parent) {
                    return null;
                }

                return (
                    <Sequence
                        key={scene.id}
                        from={parent.timelineStartFrame + scene.offsetInParentFrames}
                        durationInFrames={scene.durationInFrames}
                    >
                        <BeatOverlay
                            kind={scene.kind}
                            text={scene.text}
                            icon={scene.icon}
                            side={beatSideForSceneId(scene.id)}
                        />
                    </Sequence>
                );
            }
        }
    };

    return (
        <AbsoluteFill>
            {backgroundVideo && (
                <LoopingBackground
                    path={backgroundVideo.path}
                    duration={backgroundVideo.duration}
                />
            )}
            {typedScenePlan.scenes.map(renderScene)}
        </AbsoluteFill>
    );
};
