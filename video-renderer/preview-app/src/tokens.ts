// Centralized design tokens (docs/specs/poiesis-product-theme-and-ui-design-system.md,
// section 6). Every component reads color/spacing/radius/typography from
// here rather than its own inline literal, so retheming is a token-value
// change in this one file, not a per-component rewrite.
//
// Deliberately dark, not the spec's literal light/white direction (section
// 4) — confirmed with the user after trying the light theme live: for a
// video-editing tool specifically, a dark surface keeps the (usually
// bright, high-contrast) footage as the eye's natural focal point instead
// of competing with a bright chrome around it, and is easier on the eyes
// across a long edit session. This palette is brand-derived (section 5)
// from the Poiesis logo (public/poiesis-logo.png) rather than a generic
// dev-tool slate-gray: sampling the logo's actual pixels (not eyeballed)
// found its two real accent hues are a deep NAVY (#3f5575/#374b68 family)
// and a warm GOLD/bronze (#956c3f/#a67c4b family) on a cream ground — no
// teal despite how it can read at small icon size. The theme below builds
// outward from that: a navy-TINTED near-black base (not neutral gray) and
// the gold as the singular accent, so the product has a distinctive,
// classical/editorial character instead of looking like an interchangeable
// dark-mode IDE.
export const colors = {
    // Surfaces — navy-tinted, not neutral gray, so the base itself carries
    // the brand rather than being a generic dark backdrop the accent sits
    // on top of.
    background: "#0d1420",
    surface: "#161f2e",
    surfaceElevated: "#1c2738",
    border: "#2a3a52",
    borderStrong: "#3d5170",

    // Text — a warm off-white (not cool blue-white) to balance the navy
    // surfaces without the page feeling cold/clinical.
    textPrimary: "#eef0ea",
    textSecondary: "#a3aec2",
    textMuted: "#71809c",
    // Monospace/log/JSON output text — a softer tone than textPrimary,
    // deliberately distinct since dense pre-formatted text reads better
    // slightly muted.
    codeText: "#c4cbdb",

    // Semantic
    error: "#ff9484",
    errorStrong: "#e8574a",
    success: "#4bb383",
    warning: "#e0a542",

    // Selection / accent — the warm gold sampled from the logo (section
    // 5's "brand should influence accent/highlight/selection/focus
    // states"), not an arbitrary orange — this is what makes the theme
    // read as distinctly Poiesis rather than a generic dark UI.
    accent: "#d4a24e",
    playhead: "#ff6b4a",

    // Per-element-type timeline colors — kept as a genuinely distinct,
    // legible-on-navy hue set (each timeline bar type needs to be visually
    // distinguishable from the others at a glance), tuned slightly cooler/
    // richer than a generic bright palette to sit comfortably against the
    // navy base rather than fighting it.
    timelineText: "#4a8fd1",
    timelineVisual: "#9868e0",
    timelineImage: "#33c9a0",
    timelineBeat: "#d4a24e",
    timelinePresenter: "#2f8f78",
    timelineTitle: "#c99a4a",

    // Chapter strip's own rotating categorical palette (ChapterStrip.tsx) —
    // kept as its own named array (not folded into the flat token list
    // above) since it's used by index, not by semantic name.
    chapterPalette: ["#4a8fd1", "#c9873a", "#4aad7a", "#9868e0", "#e0645a", "#3aafaf"],
} as const;

export const spacing = {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 24,
    xxl: 32,
    xxxl: 48,
} as const;

export const radius = {
    sm: 4,
    md: 6,
    lg: 8,
    pill: 999,
} as const;

export const shadow = {
    // The one elevation level currently in use (floating boxes like
    // InlineTextEditor's edit popup) — a single shared value rather than
    // each component inventing its own shadow string.
    elevated: "0 8px 24px rgba(0,0,0,0.5)",
} as const;

export const typography = {
    fontFamily:
        '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    size: {
        xs: 11,
        sm: 12,
        md: 13,
        base: 14,
        lg: 16,
    },
    weight: {
        regular: 400,
        semibold: 600,
        bold: 700,
    },
    // Unitless multipliers (× font-size), not px — CSS line-height best
    // practice, so a nested element with a different font-size still gets
    // a proportionally correct line-height instead of inheriting a fixed
    // px value meant for a different size. tight suits single-line UI
    // labels/buttons; relaxed is for anything the reader actually reads
    // in sentences (AI conversation text — spec section 7 names this as
    // its own typography category — where default/tight reads cramped).
    lineHeight: {
        tight: 1.2,
        relaxed: 1.5,
    },
} as const;
