// Shared transition-timing constant for moment content — imported by both
// Episode.tsx (the presenter's own slide-aside/slide-back animation) and
// MomentTreatments.tsx (the moment content's fade-in/fade-out). Both used
// to hardcode independent frame counts that only agreed by coincidence
// (both authors picked values that happened to fit inside the same
// offset/offset+duration anchors) — tuning one without the other would
// silently desync the presenter's slide from the content's own fade.
// Deriving both from this one constant means they can never drift apart.
export const TRANSITION_FRAMES = 24;
