export interface EpisodeVideo {
    id: string;
    filename: string;
    path: string;
    keyedPath?: string;
    duration: number;
    fps: number;
    width: number;
    height: number;
}

export interface EpisodeAsset {
    id: string;
    filename: string;
    path: string;
    caption: string;
}

export interface EpisodeCodeAsset {
    id: string;
    filename: string;
    path: string;
    language: string;
    description: string;
    lineCount: number;
}

export interface BackgroundVideo {
    filename: string;
    path: string;
    duration: number;
    fps: number;
}

export interface SceneEffects {
    captions: boolean;
    transition: string;
}

// Where the presenter sits in the frame. "center" (full-frame) is the
// default everywhere the presenter isn't actively making room for a
// side-text/side-image moment. Deliberately NOT a field on PresenterScene:
// the presenter's position is derived per-frame from whichever MomentScene
// is currently active (see Episode.tsx's layoutWindowsForScene), not a
// static property of the whole scene — otherwise the presenter shifts for
// the scene's entire duration even though the moment content it's making
// room for is only on screen for a few seconds in the middle. See
// MomentScene.presenterSide below.
// "corner": a small picture-in-picture box (bottom-right) for
// "content-dominant-code" moments (#48) — the presenter shrinks in both
// width AND height, unlike left/right which only narrow (see
// LAYOUT_GEOMETRY in timing.ts).
export type PresenterLayout = "center" | "left" | "right" | "corner";

export interface PresenterScene {
    type: "presenter";
    id: string;
    videoId: string;
    sourceStartFrame: number;
    sourceEndFrame: number;
    timelineStartFrame: number;
    durationInFrames: number;
    effects: SceneEffects;
}

export interface TitleScene {
    type: "title";
    id: string;
    text: string;
    timelineStartFrame: number;
    durationInFrames: number;
}

// A moment's treatment implies whether/how the presenter moves:
// "bottom-callout" and "comparison" leave the presenter full-frame
// (presenterSide absent); "side-text"/"side-image"/"side-code"/
// "side-diagram"/"side-terms" require a presenterSide ("left" or "right")
// — the presenter animates to that side only for this moment's own window
// (plus a short transition pad either side), then animates back to center
// once the moment ends, rather than for its whole parent scene's duration.
// "full-visual" hides the presenter entirely for its own window (plus the
// same transition pad) instead of moving it to a side — presenterSide is
// absent, same as bottom-callout, but Episode.tsx's layoutWindowsForScene
// treats it as a fourth ("hidden") state rather than reusing bottom-callout's
// "stays centered" meaning. Validated in pipeline/generate_moments.py, not
// just assumed.
// "content-dominant-code" (#48) is a fifth presenter state: the presenter
// shrinks to a small corner picture-in-picture (PresenterLayout "corner")
// while the code fills most of the frame — reuses codeAssetId, same as
// side-code, since it's the same content, just a different layout
// decision (per SideTextStyle's own precedent above: a layout-affecting
// difference gets a new treatment value, not a field on an existing one).
export type MomentTreatment = "bottom-callout" | "side-text" | "side-image" | "side-code" | "side-diagram" | "side-terms" | "comparison" | "full-visual" | "content-dominant-code";

// "quote" (default, existing behavior unchanged) renders a single phrase
// exactly as before. "title" is a bolder/larger typographic treatment for a
// moment that's announcing a chapter/concept rather than quoting a claim —
// same component, same grounding, same side-panel positioning, only the
// type-scale branch differs. Only meaningful when treatment is "side-text";
// deliberately NOT a new MomentTreatment value, since the only real
// difference from ordinary side-text is typographic weight, not layout or
// validation.
export type SideTextStyle = "quote" | "title";

// One term in a "side-terms" moment's layered typography stack (see
// SideTerms.tsx) — a small, fixed set of emphasis levels rather than
// freeform size/weight/color per term, so independently-generated moments
// stay visually consistent with each other instead of each one inventing
// its own type scale.
export type TermEmphasisLevel = "muted" | "primary" | "accent";

export interface TermEmphasis {
    text: string;
    level: TermEmphasisLevel;
}

// Exactly two labels in fixed left/right slots — deliberately not TermEmphasis's
// N-item stack, since a comparison is always a two-way contrast, not a list of
// related terms. The presenter stays centered/full-frame between them (see
// MomentTreatment above), unlike every side-* treatment.
export interface ComparisonData {
    left: string;
    right: string;
}

// What fills the frame for a "full-visual" moment — reuses the same
// underlying data (assetId/diagram/text/codeAssetId) other treatments
// already carry rather than introducing new fields, since this is a
// layout/prominence choice (full-frame vs. a side panel), not a new kind
// of content. "code" reuses codeAssetId, the same field side-code already
// carries.
export type FullVisualKind = "image" | "diagram" | "text" | "code";

export interface DiagramNode {
    id: string;
    label: string;
}

export interface DiagramEdge {
    from: string;
    to: string;
    label?: string;
}

// Deliberately minimal for a first version — no node coordinates (layout
// is computed deterministically from `layout` + node array order, not an
// LLM decision), no shapes/colors beyond one brand style, no nested/
// grouped nodes. Unlike assetId/codeAssetId, this is inline data rather
// than a reference into an indexed file — there is no pre-existing
// "diagram asset" to select from, since a diagram's whole value is
// visualizing a relationship the AI identifies in the explanation.
export interface DiagramData {
    nodes: DiagramNode[];
    edges: DiagramEdge[];
    layout: "horizontal" | "vertical";
}

export interface MomentScene {
    type: "moment";
    id: string;
    treatment: MomentTreatment;
    text?: string;
    assetId?: string;
    codeAssetId?: string;
    diagram?: DiagramData;
    caption?: string;
    presenterSide?: "left" | "right";
    // Only meaningful when treatment is "full-visual" — which of text/
    // assetId/diagram (already-present fields above) the full-frame
    // content should render from.
    fullVisualKind?: FullVisualKind;
    // Only meaningful when treatment is "side-text" — see SideTextStyle.
    // Absent/undefined means "quote", same as before this field existed.
    sideTextStyle?: SideTextStyle;
    // Required for "side-terms" — the layered term list (see TermEmphasis).
    terms?: TermEmphasis[];
    // Required for "comparison" — the two flanking labels (see ComparisonData).
    comparison?: ComparisonData;
    parentSceneId: string;
    offsetInParentFrames: number;
    durationInFrames: number;
}

export interface ImageScene {
    type: "image";
    id: string;
    assetId: string;
    caption?: string;
    display: "full" | "inset";
    parentSceneId: string;
    offsetInParentFrames: number;
    durationInFrames: number;
}

export interface CaptionScene {
    type: "caption";
    id: string;
    text: string;
    parentSceneId: string;
    offsetInParentFrames: number;
    durationInFrames: number;
}

// A "beat" is a short, frequent kinetic accent on a single word/short
// phrase, timed to when it's actually spoken (word-level transcript
// timestamps — see pipeline/generate_emphasis.py) — distinct from
// captions (which stay verbatim/unabridged) and from moments (which are
// deliberately rare and claim a side/full frame). Beats are meant to be a
// constant light rhythm under the presenter, not an event.
export type BeatKind = "word-pop" | "underline" | "icon-accent";

export interface BeatScene {
    type: "beat";
    id: string;
    kind: BeatKind;
    text: string;
    // Only meaningful for kind "icon-accent" — a key into a small static
    // icon map in BeatOverlay.tsx (e.g. "arrow", "check"), not an
    // open-ended asset reference.
    icon?: string;
    parentSceneId: string;
    offsetInParentFrames: number;
    durationInFrames: number;
}

export type Scene = PresenterScene | TitleScene | MomentScene | ImageScene | CaptionScene | BeatScene;

export interface ScenePlan {
    version: number;
    episode: string;
    fps: number;
    scenes: Scene[];
}

// What pipeline/prepare_footage.py's generate_episode_props_ts writes to
// generated/episode/episode-props.ts. scenePlan isn't included there — it's
// a separate generated artifact (generated/episode/scene-plan.ts, written
// later in the pipeline by generate_scene_plan_ts.py) composed together with
// this at the Composition.tsx level.
export type EpisodeBaseProps = {
    width: number;
    height: number;
    fps: number;
    videos: EpisodeVideo[];
    assets: EpisodeAsset[];
    codeAssets?: EpisodeCodeAsset[];
    backgroundVideo?: BackgroundVideo;
};

export type EpisodeProps = EpisodeBaseProps & {
    scenePlan: ScenePlan;
    // Restricts rendering to only these scene types, e.g. ["caption"] to
    // render a transparent clip containing just captions with everything
    // else (presenter, titles, moments, images) omitted. Omitted/undefined
    // renders every scene, matching all prior behavior. Scenes of other
    // types are still present in scenePlan and still resolved for parent
    // lookups (e.g. a caption scene still finds its parent presenter scene
    // to compute its own timelineStartFrame) — only their own rendering is
    // skipped, so this doesn't require the caller to prune scenePlan itself.
    onlyTypes?: Scene["type"][];
};