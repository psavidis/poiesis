import { AbsoluteFill, Img, Loop, OffthreadVideo, Sequence, staticFile, useCurrentFrame, interpolate } from "remotion";
import type { BackgroundImageMotion, BackgroundImageMotionSpeed } from "./types";

// How long (in frames) the loop's own seam gets a crossfade dissolve
// instead of a hard cut — "a little animation to smoothen the loop" (the
// feature's own ask). Short enough that it reads as a seamless loop, not
// a visible fade transition, long enough (~0.5s at 30fps) to actually
// hide a jump cut between the clip's last and first frames.
const LOOP_CROSSFADE_FRAMES = 15;

// How far a static image drifts in/out, per speed preset — fixed values,
// not a free-form dial (see BackgroundImageMotionSpeed's own doc
// comment: "does not distract" is a hard design constraint here). "subtle"
// is the ORIGINAL amount from before speed control existed; "normal" and
// "strong" are raised from their original 1.15/1.25 (#91 — even "strong"
// read as barely-there motion against a background span running for a
// whole chapter, since the drift always completes over the WHOLE span
// regardless of how long that span is) to a clearly noticeable but still
// smooth drift — all three still complete over the whole span, so
// "faster" here means a bigger zoom amount in the same time, not a
// shorter cycle.
const IMAGE_MOTION_MAX_SCALE_BY_SPEED: Record<BackgroundImageMotionSpeed, number> = {
    subtle: 1.08,
    normal: 1.25,
    strong: 1.4,
};

export function imageMotionScale(
    motion: BackgroundImageMotion | undefined,
    speed: BackgroundImageMotionSpeed | undefined,
    frame: number,
    durationInFrames: number
): number {
    if (!motion || motion === "none" || durationInFrames <= 0) return 1;

    const maxScale = IMAGE_MOTION_MAX_SCALE_BY_SPEED[speed ?? "normal"];

    if (motion === "zoom-in") {
        return interpolate(frame, [0, durationInFrames], [1, maxScale], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        });
    }

    if (motion === "zoom-out") {
        return interpolate(frame, [0, durationInFrames], [maxScale, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        });
    }

    // "palindrome": zooms in across the first half, back out across the
    // second — one full cycle always exactly matches durationInFrames
    // (see BackgroundImageMotion's own doc comment), so it never needs
    // its own separate loop/seam handling the way the video background
    // does.
    const midpoint = durationInFrames / 2;
    return interpolate(frame, [0, midpoint, durationInFrames], [1, maxScale, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
    });
}

// A single background span's content, behind everything else (see
// Episode.tsx's "background" case in renderScene, mounted before the
// presenter/moments/etc. in z-order). Video backgrounds loop for exactly
// this span's own durationInFrames (not the source clip's own length —
// the loop math below handles a span shorter OR longer than one
// playthrough transparently); a static image fills the frame with an
// optional slow zoom drift (see imageMotionScale) instead of the plain,
// motionless <Img> this used before BackgroundImageMotion existed.
export const BackgroundLayer = ({
    path,
    mediaType,
    sourceDurationInFrames,
    crossfadeInFrames = 0,
    durationInFrames,
    imageMotion,
    imageMotionSpeed,
}: {
    path: string;
    mediaType: "image" | "video";
    // Only meaningful for mediaType "video" — the underlying clip's own
    // length, so LoopingBackgroundVideo knows where its own seam falls
    // regardless of how long the span using it runs for.
    sourceDurationInFrames?: number;
    // How many frames of lead-in this layer's own enclosing Sequence was
    // given (see Episode.tsx's crossfadeInFramesForBackgroundScene) so it
    // can dissolve in over the PREVIOUS BackgroundScene, still rendering
    // underneath for that same overlapping span, instead of cutting
    // straight in — "smooth transition... for the background" whenever
    // one background hands off to a different one.
    crossfadeInFrames?: number;
    // The BackgroundScene's own real span length (NOT including the
    // borrowed crossfade lead-in above) — only meaningful for mediaType
    // "image", to scale the zoom motion to exactly this span regardless
    // of how long it ends up being. Required whenever imageMotion is set
    // to anything other than "none"/absent.
    durationInFrames?: number;
    imageMotion?: BackgroundImageMotion;
    imageMotionSpeed?: BackgroundImageMotionSpeed;
}) => {
    const rawFrame = useCurrentFrame();
    // Re-aligned so frame 0 is the span's OWN start, not the Sequence's
    // borrowed lead-in start — the zoom motion (and its "one cycle = one
    // span" contract for "palindrome") must be measured against the real
    // span, the same re-alignment PresenterSequence's own sceneFrame
    // already does for its crossfade lead-in.
    const frame = rawFrame - crossfadeInFrames;

    const opacity =
        crossfadeInFrames > 0
            ? interpolate(rawFrame, [0, crossfadeInFrames], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
              })
            : 1;

    if (mediaType === "image") {
        const scale = imageMotionScale(imageMotion, imageMotionSpeed, frame, durationInFrames ?? 0);

        return (
            <AbsoluteFill style={{ opacity, overflow: "hidden" }}>
                <Img
                    src={staticFile(path)}
                    style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${scale})` }}
                />
            </AbsoluteFill>
        );
    }

    return (
        <AbsoluteFill style={{ opacity }}>
            <LoopingBackgroundVideo path={path} sourceDurationInFrames={sourceDurationInFrames ?? 1} />
        </AbsoluteFill>
    );
};

// Uses Remotion's own <Loop> as the base playback (exactly what the
// ORIGINAL always-on LoopingBackground already did correctly — see
// Episode.tsx's backward-compat fallback) rather than manually juggling
// an OffthreadVideo's trimBefore prop across loop iterations.
//
// A prior version of this component tried the manual approach: one
// OffthreadVideo whose trimBefore was recomputed each loop iteration
// (trimBefore = loopIndex * sourceDurationInFrames). That's wrong —
// changing trimBefore on an already-mounted OffthreadVideo does NOT reset
// its playback position; trimBefore only takes effect at the LOCAL frame
// 0 of whatever Sequence actually mounted it. Without a fresh Sequence
// per iteration, the displayed source position just kept monotonically
// increasing past the source clip's own real length (confirmed live:
// Episode 9's 29s background clip froze on its last decoded frame at
// exactly 0:29, the point where that runaway position first exceeded the
// file's actual duration). <Loop> avoids this because it really does
// remount a fresh Sequence (with its own local frame 0) each iteration.
const LoopingBackgroundVideo = ({ path, sourceDurationInFrames }: { path: string; sourceDurationInFrames: number }) => {
    const frame = useCurrentFrame();

    // A crossfade needs the loop to be at least twice its own length, or
    // the two overlapping copies would visibly double up mid-clip — falls
    // back to a plain hard-cut loop for a very short background clip
    // rather than producing a visibly broken overlap.
    const crossfadeFrames = sourceDurationInFrames > LOOP_CROSSFADE_FRAMES * 2 ? LOOP_CROSSFADE_FRAMES : 0;

    const loopIndex = Math.floor(frame / sourceDurationInFrames);
    const positionInLoop = frame - loopIndex * sourceDurationInFrames;
    const nearSeam = crossfadeFrames > 0 && positionInLoop >= sourceDurationInFrames - crossfadeFrames;

    const incomingOpacity = nearSeam
        ? interpolate(
              positionInLoop,
              [sourceDurationInFrames - crossfadeFrames, sourceDurationInFrames],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          )
        : 0;

    return (
        <AbsoluteFill>
            <Loop durationInFrames={sourceDurationInFrames}>
                <OffthreadVideo
                    src={staticFile(path)}
                    muted
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
            </Loop>
            {/* The NEXT playthrough, dissolved in early on top of the
                outgoing playthrough's tail — its own Sequence starts
                crossfadeFrames BEFORE the true seam and plays from source
                frame 0 (trimBefore=0), so this copy is crossfadeFrames
                "ahead of schedule" for the length of the fade. That means
                the clip's own opening ~0.5s plays twice in a row across
                the seam (once here during the fade-in, once again a
                moment later once this copy becomes the new base <Loop>
                iteration) — a small, deliberate tradeoff: OffthreadVideo's
                trimBefore can't go negative (Remotion validates it), so
                there's no way to have this copy's local frame 0 land
                exactly ON the true seam while still being mounted early
                enough to fade in beforehand. A ~0.5s repeat of ambient
                background motion is far less noticeable than either a
                hard-cut seam or the alternative of not crossfading at
                all. Only mounted near the seam so this isn't a second
                permanently-decoding video track for the other ~29.5s of
                every loop. */}
            {nearSeam && (
                <Sequence from={(loopIndex + 1) * sourceDurationInFrames - crossfadeFrames} layout="none">
                    <AbsoluteFill style={{ opacity: incomingOpacity }}>
                        <OffthreadVideo
                            src={staticFile(path)}
                            muted
                            style={{ width: "100%", height: "100%", objectFit: "cover" }}
                        />
                    </AbsoluteFill>
                </Sequence>
            )}
        </AbsoluteFill>
    );
};
