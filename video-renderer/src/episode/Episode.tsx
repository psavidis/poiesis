import {
    AbsoluteFill,
    Audio,
    Easing,
    OffthreadVideo,
    Sequence,
    interpolate,
    staticFile,
    useCurrentFrame,
} from "remotion";

import type { BackgroundScene, EpisodeAsset, EpisodeCodeAsset, EpisodeProps, EpisodeVideo, MomentScene, PresenterScene, Scene, TitleScene } from "./types";
import { AnimatedTitle } from "./AnimatedTitle";
import { BackgroundLayer } from "./BackgroundLayer";
import { BeatOverlay } from "./BeatOverlay";
import { CaptionText } from "./CaptionText";
import { CodeBlock } from "./CodeBlock";
import { Comparison } from "./Comparison";
import { GreenKeyFilterDefs } from "./ChromaKey";
import { DiagramBlock } from "./DiagramBlock";
import { EpisodeImage } from "./EpisodeImage";
import { FullVisualMoment } from "./FullVisualMoment";
import { BottomCallout, DominantMedia, SideImage, SideText } from "./MomentTreatments";
import { SideTerms } from "./SideTerms";
import { LAYOUT_GEOMETRY, TRANSITION_FRAMES } from "./timing";

// A crossfade "borrows" a few extra source frames immediately before a
// clip's own silence-trimmed sourceStartFrame (real footage that exists,
// just trimmed as dead air) so the incoming clip has something to fade in
// from other than black — the same technique an editor uses when trimming
// leaves no natural pre-roll. Widened from 9 (0.3s): at 9 frames a cut
// between two separately-recorded takes (different lighting/framing/
// energy) still read as an abrupt stop-start, not a real dissolve — too
// quick to actually register as a transition rather than a fast cut.
export const CROSSFADE_TRANSITION_FRAMES = 18; // 0.6s at 30fps

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
            holdFromPrevious: m.holdFromPrevious ?? false,
        }))
        .sort((a, b) => a.start - b.start);

    // Merges a window into the immediately preceding one (in sorted order)
    // when its own moment asked to holdFromPrevious AND the sides actually
    // match — see MomentScene.holdFromPrevious's own comment. Merging
    // collapses two independent center->side->side->center cycles into one
    // continuous side hold spanning both moments (and the gap between
    // them), since AnimatedPresenterFrame's interpolation only ever looks
    // at a window's own start/end/side — it doesn't need to know two
    // moments contributed to this one window. A mismatched side (or no
    // preceding window at all) leaves the flag as a no-op: the moment
    // keeps its own independent window exactly as if holdFromPrevious were
    // unset, rather than erroring on an edit that doesn't actually chain.
    const merged: { start: number; end: number; side: LayoutWindow["side"] }[] = [];

    for (const w of windows) {
        const prev = merged[merged.length - 1];

        if (w.holdFromPrevious && prev && prev.side === w.side) {
            prev.end = w.end;
        } else {
            merged.push({ start: w.start, end: w.end, side: w.side });
        }
    }

    return merged;
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

// The presenter scene's own <Audio volume> curve (#115) — silences the
// borrowed video lead-in (frame < crossfadeInFrames) so audio still cuts in
// cleanly at the scene's true start even though the <Audio> element itself
// is now mounted crossfadeInFrames early, alongside the video, rather than
// in its own inner Sequence offset to start later (that extra Sequence
// boundary sat exactly at this scene's true start — where a seek/click
// into the scene lands — and was a likely source of a brief silent gap
// while the browser mounted+buffered a fresh <audio> element there).
// frame is local to the enclosing Sequence (PresenterSequence), same as
// AnimatedPresenterFrame's own rawFrame.
export const presenterAudioVolume = (frame: number, crossfadeInFrames: number): number =>
    frame < crossfadeInFrames ? 0 : 1;

// BackgroundScene's own equivalent of the above — always crossfades (no
// per-scene effects.transition opt-out the way presenter cuts have,
// since a background changing IS itself always a "this replaced that"
// moment worth dissolving, never a moment-to-moment cut a human would
// want hard). Simpler clamp than the presenter version: a background has
// no "trimmed dead air" to borrow lead-in from — both the outgoing and
// incoming background are already continuously looping/playing, so the
// only real constraint is not borrowing more than the previous span
// actually had.
const crossfadeInFramesForBackgroundScene = (
    scene: BackgroundScene,
    previousScene: BackgroundScene | undefined
): number => {
    if (!previousScene) {
        return 0;
    }

    return Math.max(0, Math.min(CROSSFADE_TRANSITION_FRAMES, previousScene.durationInFrames));
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

    // widthPct/leftPct/topPct/heightPct describe the presenter's own
    // on-screen FRAMING (where his body sits, how much of the frame he
    // occupies) — this still slides for every window kind, "corner"
    // included, so the presenter genuinely moves to make room for
    // whichever side the moment content is on rather than staying put.
    // What's DIFFERENT per kind is only how the video is clipped against
    // that framing (see outerLeftPct etc. below): "corner" clips hard (a
    // deliberate picture-in-picture), "left"/"right" don't clip at all
    // (a gesture reaching past the framing naturally overlays the moment
    // content instead of being sliced off), "hidden"/center never had a
    // window to slide toward in the first place.
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
    // div's width), and the video is shifted left/right inside that window
    // so the presenter (who was framed centered in the original shot)
    // stays centered in whatever window is currently visible, rather than
    // shifting the video's own crop/zoom to fit a narrower box (which is
    // what made the presenter appear to shrink).
    //
    // outerLeftPct/outerWidthPct: the presenter's own on-screen framing,
    // as a fraction of the full composition — same as leftPct/widthPct.
    //
    // clipToWindow controls whether that window is actually a hard crop
    // (overflow: hidden) or just a positioning reference the video is
    // centered against with nothing hiding what spills past it. "corner"
    // (#48's content-dominant-code PiP) is a deliberate picture-in-
    // picture and keeps the hard crop. "left"/"right" don't: the
    // presenter still visibly moves/narrows toward one side (so there's
    // real room made for the moment content), but a gesture or hair
    // reaching past that framing isn't sliced off by a straight clip
    // line — it naturally overlays the moment content instead, the way a
    // real editor keys a presenter over a graphic rather than cropping
    // him away from it whenever he moves. See the moment this replaced
    // hard clipping (and briefly, full-frame-with-no-framing-at-all)
    // entirely.
    const clipToWindow = activeWindow?.side === "corner";

    const outerLeftPct = leftPct;
    const outerWidthPct = widthPct;
    const videoDivWidthPct = outerWidthPct === 0 ? 100 : (100 / outerWidthPct) * 100;
    const videoShiftPct = 50 - (videoDivWidthPct / 2);

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
                    overflow: clipToWindow ? "hidden" : "visible",
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
            {/* Mounted once, alongside the video, for this scene's entire
                Sequence lifetime — NOT wrapped in its own inner Sequence
                offset past the borrowed lead-in (the previous approach).
                That extra Sequence boundary sat right at this scene's real
                start, exactly where the playhead lands on a seek/click into
                this scene, and forced the browser to mount a fresh <audio>
                element (and buffer it) at that precise moment — a likely
                source of the brief silent gap reported in #115 when
                selecting a clip on SceneBar. Silencing the borrowed lead-in
                via `volume` instead achieves the identical audible result
                (audio cuts in cleanly at the scene's true start, only the
                video dissolves) with no extra mount point: this element has
                the same single mount boundary as the video track above. */}
            <Audio
                src={staticFile(video.path)}
                trimBefore={scene.sourceStartFrame - crossfadeInFrames}
                trimAfter={scene.sourceEndFrame}
                volume={(f) => presenterAudioVolume(f, crossfadeInFrames)}
            />
        </AbsoluteFill>
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
            return <BottomCallout text={scene.text ?? ""} entrance={scene.entrance} box={scene.box} />;

        case "side-text": {
            const presenterOnLeft = scene.presenterSide === "left";
            return <SideText text={scene.text ?? ""} presenterOnLeft={presenterOnLeft} style={scene.sideTextStyle} box={scene.box} />;
        }

        case "side-image": {
            if (!asset) return null;
            const presenterOnLeft = scene.presenterSide === "left";
            return (
                <SideImage
                    path={asset.path}
                    mediaType={asset.mediaType}
                    keyColor={asset.keyColor}
                    caption={scene.caption}
                    captionPlacement={scene.captionPlacement}
                    presenterOnLeft={presenterOnLeft}
                    box={scene.box}
                />
            );
        }

        case "side-code": {
            if (!codeAsset) return null;
            const presenterOnLeft = scene.presenterSide === "left";

            // A screenshot/recording has no text to highlight — reuse the
            // same framed image/video treatment graphics/ assets already
            // get (SideImage already branches on mediaType), rather than
            // hand CodeBlock a path it can't read as source text.
            if (codeAsset.kind === "screenshot" || codeAsset.kind === "recording") {
                return (
                    <SideImage
                        path={codeAsset.path}
                        mediaType={codeAsset.kind === "recording" ? "video" : "image"}
                        keyColor={codeAsset.keyColor}
                        presenterOnLeft={presenterOnLeft}
                        box={scene.box}
                    />
                );
            }

            return (
                <CodeBlock
                    path={codeAsset.path}
                    language={codeAsset.language ?? "text"}
                    presenterOnLeft={presenterOnLeft}
                    box={scene.box}
                />
            );
        }

        case "content-dominant-code": {
            // No presenterSide — the presenter shrinks to a fixed
            // bottom-right corner PiP (LAYOUT_GEOMETRY.corner) rather than
            // moving to a chosen side, so there's no left/right slide
            // direction to pass through.
            if (!codeAsset) return null;

            if (codeAsset.kind === "screenshot" || codeAsset.kind === "recording") {
                return (
                    <DominantMedia
                        path={codeAsset.path}
                        mediaType={codeAsset.kind === "recording" ? "video" : "image"}
                        keyColor={codeAsset.keyColor}
                        caption={scene.caption}
                        captionPlacement={scene.captionPlacement}
                        box={scene.box}
                    />
                );
            }

            return (
                <CodeBlock
                    path={codeAsset.path}
                    language={codeAsset.language ?? "text"}
                    presenterOnLeft={false}
                    size="dominant"
                    box={scene.box}
                />
            );
        }

        case "side-diagram": {
            if (!scene.diagram) return null;
            const presenterOnLeft = scene.presenterSide === "left";
            return <DiagramBlock diagram={scene.diagram} presenterOnLeft={presenterOnLeft} box={scene.box} />;
        }

        case "side-terms": {
            if (!scene.terms || scene.terms.length === 0) return null;
            const presenterOnLeft = scene.presenterSide === "left";
            return <SideTerms terms={scene.terms} presenterOnLeft={presenterOnLeft} box={scene.box} />;
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
                    assetMediaType={asset?.mediaType}
                    assetKeyColor={asset?.keyColor}
                    caption={scene.caption}
                    captionPlacement={scene.captionPlacement}
                    diagram={scene.diagram}
                    codePath={codeAsset?.path}
                    codeLanguage={codeAsset?.language}
                    codeAssetKind={codeAsset?.kind}
                    codeAssetKeyColor={codeAsset?.keyColor}
                    box={scene.box}
                />
            );
        }
    }
};

export const Episode = ({
                            videos,
                            assets,
                            codeAssets,
                            backgrounds,
                            scenePlan: typedScenePlan,
                            onlyTypes,
                        }: EpisodeProps) => {

    const videoMap = new Map(
        videos.map((video) => [
            video.id,
            video,
        ])
    );

    const backgroundMap = new Map(
        (backgrounds ?? []).map((background) => [
            background.id,
            background,
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

    // Mirrors previousPresenterSceneById above, for BackgroundScenes — a
    // background change should dissolve into the next one exactly the
    // same way a presenter cut does ("smooth transition... both for the
    // talking head and the background"), but only when the two spans are
    // directly adjacent (background_scenes.json's own auto-closed model
    // guarantees this for every real gap-free run) AND actually reference
    // a DIFFERENT background — two adjacent spans that happen to reuse
    // the same backgroundId need no dissolve, there's nothing visually
    // changing at that boundary.
    const orderedBackgroundScenes = typedScenePlan.scenes
        .filter((scene): scene is BackgroundScene => scene.type === "background")
        .sort((a, b) => a.timelineStartFrame - b.timelineStartFrame);

    const previousBackgroundSceneById = new Map<string, BackgroundScene | undefined>();

    orderedBackgroundScenes.forEach((scene, index) => {
        const previous = orderedBackgroundScenes[index - 1];

        const isDirectlyAdjacentDifferentBackground =
            previous !== undefined &&
            previous.timelineStartFrame + previous.durationInFrames === scene.timelineStartFrame &&
            previous.backgroundId !== scene.backgroundId;

        previousBackgroundSceneById.set(scene.id, isDirectlyAdjacentDifferentBackground ? previous : undefined);
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
                        <AnimatedTitle text={scene.text} durationInFrames={scene.durationInFrames} />
                    </Sequence>
                );
            }

            case "background": {
                const background = backgroundMap.get(scene.backgroundId);

                if (!background) {
                    return null;
                }

                const sourceDurationInFrames =
                    background.mediaType === "video" && background.duration
                        ? Math.round(background.duration * typedScenePlan.fps)
                        : undefined;

                // Same "borrow a few extra frames of lead-in, dissolve
                // over them" technique PresenterSequence uses — the
                // Sequence starts crossfadeInFrames early so
                // BackgroundLayer has something to fade in FROM (the
                // outgoing background, still rendering underneath) rather
                // than fading in from black.
                const crossfadeInFrames = crossfadeInFramesForBackgroundScene(scene, previousBackgroundSceneById.get(scene.id));

                return (
                    <Sequence
                        key={scene.id}
                        from={scene.timelineStartFrame - crossfadeInFrames}
                        durationInFrames={scene.durationInFrames + crossfadeInFrames}
                        layout="none"
                    >
                        <BackgroundLayer
                            path={background.path}
                            mediaType={background.mediaType}
                            sourceDurationInFrames={sourceDurationInFrames}
                            crossfadeInFrames={crossfadeInFrames}
                            durationInFrames={scene.durationInFrames}
                            imageMotion={scene.imageMotion}
                            imageMotionSpeed={scene.imageMotionSpeed}
                        />
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
                            mediaType={asset.mediaType}
                            keyColor={asset.keyColor}
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

    // Background scenes must render BELOW everything else regardless of
    // their position in scenePlan.scenes' own array order — rendered
    // separately, first, rather than relying on array order to imply
    // z-order the way every other scene type safely can (they're all
    // full-frame overlays/cutaways that don't care what's behind them).
    // Sorted explicitly (not just trusting scene-plan.json's own array
    // order) since render order here IS z-order for background layers —
    // during a crossfade's overlap window, the OUTGOING (earlier) span
    // must paint first so the INCOMING (later) span's dissolve-in
    // actually shows on top of it, not underneath.
    const backgroundScenes = orderedBackgroundScenes;
    const nonBackgroundScenes = typedScenePlan.scenes.filter((scene) => scene.type !== "background");

    return (
        <AbsoluteFill>
            {/* Mounted once for the whole episode — every green-keyed video
                asset references this by id (see ChromaKey.tsx), an SVG
                filter def doesn't need to be duplicated per use. */}
            <GreenKeyFilterDefs />
            {backgroundScenes.map(renderScene)}
            {nonBackgroundScenes.map(renderScene)}
        </AbsoluteFill>
    );
};
