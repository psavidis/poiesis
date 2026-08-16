import type { PresenterLayout } from "./types";

// Shared transition-timing constant for moment content — imported by both
// Episode.tsx (the presenter's own slide-aside/slide-back animation) and
// MomentTreatments.tsx (the moment content's fade-in/fade-out). Both used
// to hardcode independent frame counts that only agreed by coincidence
// (both authors picked values that happened to fit inside the same
// offset/offset+duration anchors) — tuning one without the other would
// silently desync the presenter's slide from the content's own fade.
// Deriving both from this one constant means they can never drift apart.
export const TRANSITION_FRAMES = 24;

// Frame geometry for each presenter layout, as a fraction of the full
// frame — "left"/"right" leave the opposite side free for a moment's
// side-text/side-image/side-code/side-diagram/side-terms treatment. Lives
// here (not in Episode.tsx) for the same reason TRANSITION_FRAMES does:
// Episode.tsx imports FROM MomentTreatments.tsx (SideText/SideImage/
// BottomCallout), so MomentTreatments.tsx can't import LAYOUT_GEOMETRY
// back from Episode.tsx without a cycle — this file has no dependents
// among episode components, so both sides can import it safely.
//
// widthPct 60 (not a literal half): objectFit stays "cover" at the same
// scale as center (see Episode.tsx's AnimatedPresenterFrame) — the
// presenter never shrinks when moving to a side, only the visible window
// onto them narrows. A narrower box than this starts regularly clipping
// gesturing arms/hands during ordinary talking-head motion (verified
// against real footage — see #35's rendered-frame checks); 60% is the
// narrowest split that reliably keeps typical gesture range in frame
// while still reading as a clear, deliberate "made room" shift rather
// than the previous 72% split, which registered as barely-there panning.
// SIDE_CONTENT_WIDTH_PCT below is exactly 100 - widthPct, so
// MomentTreatments.tsx's content panel and the presenter's freed space
// can never drift apart the way two independently-hardcoded percentages
// could.
// topPct/heightPct default to full-height (0/100) for every layout except
// "corner" — added alongside widthPct/leftPct (not replacing them) so
// center/left/right's existing full-height behavior is unchanged; only
// "corner" (content-dominant code, #48) actually shrinks vertically as
// well as horizontally, since it's a small picture-in-picture box rather
// than a full-height side window.
export const LAYOUT_GEOMETRY: Record<
    PresenterLayout,
    { widthPct: number; leftPct: number; topPct: number; heightPct: number }
> = {
    center: { widthPct: 100, leftPct: 0, topPct: 0, heightPct: 100 },
    left: { widthPct: 60, leftPct: 0, topPct: 0, heightPct: 100 },
    right: { widthPct: 60, leftPct: 40, topPct: 0, heightPct: 100 },
    // Bottom-right corner PiP for content-dominant code (#48) — the code
    // itself uses most of the frame (see FullVisualMoment-adjacent sizing
    // in ContentDominantCode), the presenter shrinks to a small box rather
    // than losing only width the way left/right do. Margins (4%/6%) keep
    // it clear of the frame edge and match the visual weight of a
    // deliberate PiP rather than a flush-mounted corner crop.
    corner: { widthPct: 26, leftPct: 70, topPct: 62, heightPct: 34 },
};

export const SIDE_CONTENT_WIDTH_PCT = 100 - LAYOUT_GEOMETRY.right.widthPct;
