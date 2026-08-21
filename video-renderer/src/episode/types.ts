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
    // Authoring hint from the asset's source folder (e.g.
    // graphics/full-screen/x.png — see index_assets.py's
    // default_display_hint), read by generate_moments.py's prompt as a
    // suggestion for the AI's initial presentation choice. Never a
    // constraint: the renderer itself doesn't read this field at all — an
    // image/moment's actual presentation is still whatever display/
    // treatment ends up on its scene, same as before this field existed.
    defaultDisplay?: "full";
    // Which renderer component an asset-driven moment mounts for this
    // asset — <Img> for "image", <OffthreadVideo> for "video" (e.g. an
    // animated/alpha-transparent graphic like a channel bumper). Defaults
    // to "image" when absent so existing episodes generated before this
    // field existed keep rendering exactly as before. Set by
    // index_assets.py from the source file's extension — never inferred
    // client-side, since the renderer has no reliable way to sniff a
    // static file's actual media type from its path alone.
    mediaType?: "image" | "video";
    // Only meaningful when mediaType is "video" — which flat, static
    // background color (if any) index_assets.py detected by sampling the
    // video's four corners (see detect_key_color). "black"/"green" are the
    // only two supported today; absent means either no consistent flat
    // background detected, or the source already has real alpha. Drives
    // which SVG chroma-key filter (see KEY_COLOR_FILTERS in
    // EpisodeImage.tsx/MomentTreatments.tsx) gets applied at render time —
    // never inferred client-side, for the same reason mediaType isn't.
    keyColor?: "black" | "green";
}

// What a code/ file actually IS, not just its extension — "source" (real
// text, Shiki-highlighted via CodeBlock, the gold-standard treatment: real
// tokens, line numbers, progressive reveal) vs. "screenshot" (a static
// image of code, no text to parse — rendered via the same framed-image
// treatment graphics/ images already get) vs. "recording" (a screen
// recording of code being written/scrolled — rendered via the same
// video-asset/keying treatment graphics/ videos already get, see #77/#78).
// Defaults to "source" when absent so every code asset indexed before this
// field existed keeps rendering exactly as before. Set by index_code.py
// from the file's extension — never inferred client-side.
export type CodeAssetKind = "source" | "screenshot" | "recording";

export interface EpisodeCodeAsset {
    id: string;
    filename: string;
    path: string;
    // Only meaningful for kind "source" — Shiki language id. Absent for
    // screenshot/recording, which have no text to highlight.
    language?: string;
    description: string;
    // Only meaningful for kind "source".
    lineCount?: number;
    kind?: CodeAssetKind;
    // Only meaningful for kind "recording" — see EpisodeAsset.keyColor's
    // own doc comment for what this drives.
    keyColor?: "black" | "green";
}

// One selectable background from the episode's background/ folder (see
// index_backgrounds.py) — the library a user picks from when assigning a
// BackgroundScene span. Always rendered as an opaque full-frame fill — a
// background REPLACES whatever is behind the presenter, it doesn't
// composite with anything under it — so unlike EpisodeAsset there is no
// keyColor here.
export interface EpisodeBackground {
    id: string;
    filename: string;
    path: string;
    caption: string;
    mediaType: "image" | "video";
    // Only present for mediaType "video".
    duration?: number;
    fps?: number;
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

// A user-selected background, active behind the presenter for its own
// timeline span — see generate_background_scenes.py's merge_background_
// scenes, which auto-closes each span at the next one's start (or episode
// end for the last one), the same "sorted list of start points" model
// chapters/titles already use. Absent for any stretch with no
// BackgroundScene covering it, meaning "no override — presenter's own
// natural footage" (unchanged rendering, per the feature's own design
// decision), not a synthetic "none" entry.
// A slow drift applied to a STATIC IMAGE background over its own span's
// full duration — "does not distract" is a hard design constraint here
// (see the feature's own ask), so this is a small, fixed set of presets
// (see BackgroundImageMotionSpeed), never a free-form slider. Only
// meaningful when the referenced EpisodeBackground has mediaType "image"
// — a video background already has its own motion and this field is
// ignored for it. "none" (absent/undefined also means this) is a flat,
// static image with no motion at all, unchanged from before this field
// existed. "zoom-in"/"zoom-out" run linearly across the whole span;
// "palindrome" zooms in across the first half and back out across the
// second half, so one full cycle always exactly matches the span's own
// length regardless of how long it ends up being (see
// BackgroundLayer.tsx).
export type BackgroundImageMotion = "none" | "zoom-in" | "zoom-out" | "palindrome";

// How much the image scales across its drift — a preset, not a tunable
// number (see BackgroundImageMotion's own doc comment for why). Absent
// means "normal", the default going forward — "subtle" is kept as the
// ORIGINAL fixed amount from before speed control existed, for anyone
// who already picked it and specifically wants the gentler drift.
export type BackgroundImageMotionSpeed = "subtle" | "normal" | "strong";

export interface BackgroundScene {
    type: "background";
    id: string;
    backgroundId: string;
    timelineStartFrame: number;
    durationInFrames: number;
    imageMotion?: BackgroundImageMotion;
    // Only meaningful when imageMotion is set to anything other than
    // "none"/absent.
    imageMotionSpeed?: BackgroundImageMotionSpeed;
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
export type FullVisualKind = "image" | "video" | "diagram" | "text" | "code";

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

// Which entrance animation a moment uses — only meaningful for treatments
// whose component actually reads it (currently "bottom-callout" only, see
// BottomCallout in MomentTreatments.tsx). Absent/undefined means "scale"
// (today's only behavior, unchanged for every existing episode). The three
// values are not new animation code — each already existed hardcoded in a
// different component before this field existed ("scale": BottomCallout's
// own pre-existing spring-scale entrance; "slide": the same spring-
// translateY pattern AnimatedTitle.tsx already uses for its own entrance;
// "fade": the plain opacity-only pattern CaptionText.tsx already uses,
// deliberately calm for elements that shouldn't demand attention). This is
// the prerequisite docs/specs/ai-assisted-editing-and-conversational-
// control.md section 7 needs ("if the requested animation corresponds to
// an existing supported animation, configure it") — before this field
// existed, no moment animation was configurable at all, only hardcoded per
// component.
export type MomentEntrance = "scale" | "slide" | "fade";

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
    // When true, the presenter's slide-out to this moment's own side skips
    // the center->side leading transition and instead holds continuously
    // from wherever the IMMEDIATELY PRECEDING moment's layout window left
    // off — see layoutWindowsForScene's merge pass. Only takes effect when
    // that preceding moment already shares this moment's own presenterSide;
    // otherwise this is a silent no-op and the moment slides in normally.
    // Never inferred from timing alone (two side-image moments placed close
    // together for unrelated reasons must not silently merge) — this is a
    // deliberate signal set by a human or the chat edit-plan on their behalf.
    holdFromPrevious?: boolean;
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
    // Only meaningful when treatment is "bottom-callout" — see MomentEntrance.
    entrance?: MomentEntrance;
    // Human-set override for this moment's on-screen position/size,
    // percentage-of-1920x1080-canvas units — set by dragging/resizing the
    // moment directly on the preview-app's player (see #77). Absent means
    // "use the treatment's own default geometry" (LAYOUT_GEOMETRY / each
    // treatment component's own hardcoded layout), unchanged from before
    // this field existed. Layered ON TOP of the treatment system, not a
    // replacement for it — the treatment still decides WHAT the moment is
    // (side-image vs full-visual vs bottom-callout), this only overrides
    // WHERE/HOW BIG it renders. See timing.ts's resolveBoxStyle, which
    // every treatment component's outer wrapper calls instead of
    // hardcoding its own position/size style object.
    box?: MomentBox;
    // Where `caption` renders relative to the asset/video it's captioning
    // (side-image, full-visual image/video/code, content-dominant-code —
    // any treatment with both an asset and a caption). "overlay" (absent
    // defaults here too, so every episode from before this field existed
    // renders unchanged) draws it on top of the asset, same as the
    // original always-on behavior; "below" reserves a fixed strip beneath
    // the asset within the moment's own box so the two never collide,
    // shrinking the asset region to make room; "off" suppresses the
    // caption entirely regardless of whether `caption` text is set (lets a
    // human keep a caption's text around without showing it, rather than
    // forcing them to delete and retype it later).
    captionPlacement?: "overlay" | "below" | "off";
    parentSceneId: string;
    offsetInParentFrames: number;
    durationInFrames: number;
}

export interface MomentBox {
    xPct: number;
    yPct: number;
    widthPct: number;
    heightPct: number;
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

export type Scene = PresenterScene | TitleScene | MomentScene | ImageScene | CaptionScene | BeatScene | BackgroundScene;

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
    // The selectable library backgroundScene entries reference by
    // backgroundId (see EpisodeBackground) — absent/empty for an episode
    // with no background/ folder contents, same "additive, never a hard
    // requirement" convention assets/codeAssets already follow.
    backgrounds?: EpisodeBackground[];
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