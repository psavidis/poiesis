import {
    AbsoluteFill,
    Audio,
    Loop,
    OffthreadVideo,
    Sequence,
    interpolate,
    staticFile,
    useCurrentFrame,
    useVideoConfig,
} from "remotion";

import type { EpisodeAsset, EpisodeProps, EpisodeVideo, MomentScene, PresenterLayout, PresenterScene, Scene, TitleScene } from "./types";
import { AnimatedTitle } from "./AnimatedTitle";
import { CaptionText } from "./CaptionText";
import { EpisodeImage } from "./EpisodeImage";
import { BottomCallout, SideImage, SideText } from "./MomentTreatments";

// Frame geometry for each layout, as a fraction of the full frame. "left"/
// "right" leave the opposite side free for a moment's side-text/side-image
// treatment. The presenter box stays wide (72%) rather than a literal half
// — objectFit stays "cover" at the same scale as center (see
// AnimatedPresenterFrame), so the presenter never shrinks when moving to a
// side. A narrower box would force either shrinking the presenter to fit
// (feels wrong — the whole point of the slide is to free up room, not
// visually diminish the presenter) or cropping at the box edges tight
// enough to regularly clip gesturing arms/hands. 72% only crops the far
// background at the box edge, not the presenter's own motion range for
// ordinary talking-head gesturing. MomentTreatments.tsx's SideText/SideImage
// use the matching 28% remaining width.
export const LAYOUT_GEOMETRY: Record<PresenterLayout, { widthPct: number; leftPct: number }> = {
    center: { widthPct: 100, leftPct: 0 },
    left: { widthPct: 72, leftPct: 0 },
    right: { widthPct: 72, leftPct: 28 },
};

export const TRANSITION_FRAMES = 24;

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
    side: "left" | "right";
}

export const layoutWindowsForScene = (scene: PresenterScene, moments: MomentScene[]): LayoutWindow[] => {
    const windows = moments
        .filter((m) => m.parentSceneId === scene.id && m.presenterSide)
        .map((m) => ({
            start: Math.max(0, m.offsetInParentFrames - TRANSITION_FRAMES),
            end: Math.min(scene.durationInFrames, m.offsetInParentFrames + m.durationInFrames + TRANSITION_FRAMES),
            side: m.presenterSide as "left" | "right",
        }))
        .sort((a, b) => a.start - b.start);

    return windows;
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

    let widthPct = centerGeo.widthPct;
    let leftPct = centerGeo.leftPct;

    if (activeWindow) {
        const sideGeo = LAYOUT_GEOMETRY[activeWindow.side];
        const enterEnd = Math.min(activeWindow.start + TRANSITION_FRAMES, activeWindow.end);
        const exitStart = Math.max(activeWindow.end - TRANSITION_FRAMES, enterEnd);

        widthPct = interpolate(
            sceneFrame,
            [activeWindow.start, enterEnd, exitStart, activeWindow.end],
            [centerGeo.widthPct, sideGeo.widthPct, sideGeo.widthPct, centerGeo.widthPct],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );

        leftPct = interpolate(
            sceneFrame,
            [activeWindow.start, enterEnd, exitStart, activeWindow.end],
            [centerGeo.leftPct, sideGeo.leftPct, sideGeo.leftPct, centerGeo.leftPct],
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

    // Fades in from 0 across the borrowed lead-in (rawFrame 0..crossfadeInFrames)
    // — during that window the outgoing scene's own tail is still rendering
    // underneath (it ends exactly at this scene's true timelineStartFrame,
    // unaffected by this scene's borrowed lead-in), so this dissolves over
    // it rather than cutting. crossfadeInFrames is 0 for every scene that
    // isn't set to "crossfade" or has no previous scene to fade from, so
    // this is a no-op (opacity pinned to 1) for the common case.
    const opacity =
        crossfadeInFrames === 0
            ? 1
            : interpolate(rawFrame, [0, crossfadeInFrames], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
              });

    return (
        <AbsoluteFill style={{ opacity }}>
            <div
                style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: `${outerLeftPct}%`,
                    width: `${outerWidthPct}%`,
                    overflow: "hidden",
                }}
            >
                <div
                    style={{
                        position: "absolute",
                        top: 0,
                        bottom: 0,
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
                         }: {
    scene: MomentScene;
    asset: EpisodeAsset | undefined;
}) => {
    switch (scene.treatment) {
        case "bottom-callout":
            return <BottomCallout text={scene.text ?? ""} />;

        case "side-text": {
            const presenterOnLeft = scene.presenterSide === "left";
            return <SideText text={scene.text ?? ""} presenterOnLeft={presenterOnLeft} />;
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
    }
};

export const Episode = ({
                            videos,
                            assets,
                            backgroundVideo,
                            scenePlan: typedScenePlan,
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

                return (
                    <Sequence
                        key={scene.id}
                        from={parent.timelineStartFrame + scene.offsetInParentFrames}
                        durationInFrames={scene.durationInFrames}
                    >
                        <MomentSequence scene={scene} asset={asset} />
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

                return (
                    <Sequence
                        key={scene.id}
                        from={parent.timelineStartFrame + scene.offsetInParentFrames}
                        durationInFrames={scene.durationInFrames}
                    >
                        <CaptionText text={scene.text} />
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
