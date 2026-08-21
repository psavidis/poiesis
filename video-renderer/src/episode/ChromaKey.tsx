import { OffthreadVideo, staticFile } from "remotion";

// A video asset's static background color, if index_assets.py's
// detect_key_color sampled one consistently across all four corners (see
// EpisodeAsset.keyColor in types.ts) — the only two supported today (see
// that field's own doc comment for why not an open palette).
export type KeyColor = "black" | "green";

// "black" is keyed with a plain CSS mix-blend-mode: screen — screening
// against black is a no-op for every other pixel (screen(black, x) = x)
// and fully transparent-reads black itself, no SVG filter needed. "green"
// can't be done this way (screening green would tint the whole video, not
// remove it), so it gets a real chroma-key SVG filter chain instead — see
// GreenKeyFilterDefs below. Keeping both under one component/prop means a
// caller never has to know which technique a given key color actually uses.
const GREEN_KEY_FILTER_ID = "poiesis-green-chroma-key";

// One feColorMatrix + feComponentTransfer + feComposite chain, the
// standard SVG recipe for chroma keying:
//   1. feColorMatrix projects each pixel's RGB onto a single "how green is
//      this" scalar (green minus the average of red/blue, roughly — a
//      pixel that's actually key-green scores high, anything else scores
//      low/negative) and writes it into that scratch layer's alpha.
//   2. feComponentTransfer's discrete alpha ramp thresholds that scalar
//      into a near-binary mask (green -> transparent, everything else ->
//      opaque) rather than a soft gradient, so the key doesn't leave a
//      washed-out result over non-green content.
//   3. feComposite "in" clips the ORIGINAL colors (not the scratch
//      layer's own colors, which are meaningless outside its alpha) to
//      that mask, so the output is the source video with only its
//      background removed.
// Cruder than true per-pixel distance-based chroma keying (a Canvas2D
// approach could do): may leave a slight green fringe on soft/anti-aliased
// edges. Chosen anyway because it composites identically in the Player
// preview and the headless `remotion render` output — see #77's design
// discussion for why a Canvas2D key was rejected (OffthreadVideo doesn't
// expose a live <video> element for per-frame pixel access the way that
// technique needs).
export const GreenKeyFilterDefs = () => (
    <svg width="0" height="0" style={{ position: "absolute" }}>
        <defs>
            <filter id={GREEN_KEY_FILTER_ID} colorInterpolationFilters="sRGB">
                <feColorMatrix
                    type="matrix"
                    values="0 0 0 0 0
                            0 0 0 0 0
                            0 0 0 0 0
                            -1 2 -1 0 0"
                    result="greenness"
                />
                <feComponentTransfer in="greenness" result="mask">
                    <feFuncA type="discrete" tableValues="0 0 0 0 0 1 1 1 1 1" />
                </feComponentTransfer>
                <feComposite in="SourceGraphic" in2="mask" operator="in" />
            </filter>
        </defs>
    </svg>
);

// Renders a video asset with whichever key technique its detected
// background needs, or plain (no key) when keyColor is absent — the single
// place SideImage/EpisodeImage delegate to instead of each re-implementing
// the black-vs-green branch.
export const KeyedVideo = ({
                                path,
                                keyColor,
                                style,
                            }: {
    path: string;
    keyColor?: KeyColor;
    style?: React.CSSProperties;
}) => (
    <OffthreadVideo
        src={staticFile(path)}
        muted
        style={{
            ...style,
            ...(keyColor === "black" ? { mixBlendMode: "screen" } : {}),
            ...(keyColor === "green" ? { filter: `url(#${GREEN_KEY_FILTER_ID})` } : {}),
        }}
    />
);
