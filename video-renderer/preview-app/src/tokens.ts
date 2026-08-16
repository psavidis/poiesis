// Centralized design tokens (docs/specs/poiesis-product-theme-and-ui-design-system.md,
// section 6) — the current dark palette extracted verbatim from what was
// already consistently used across BeatBar/MomentBar/ImageBar/ChapterStrip/
// MomentEditorPanel/etc. (confirmed via a full-repo hex-literal audit
// before writing this file), not a new visual direction. This is a
// PURE refactor: every value here matches what components already
// rendered, so swapping a component from its own inline hex literal to
// `colors.surface` etc. must not change anything on screen. The spec's
// eventual light/white theme (section 4) is a separate, deliberately
// deferred decision — confirmed with the user before starting this file,
// since that part is a full visual reversal, not a token extraction.

export const colors = {
    // Surfaces
    background: "#0b0f14",
    surface: "#161d24",
    surfaceElevated: "#1c242c",
    border: "#2a333d",
    borderStrong: "#3a4552",

    // Text
    textPrimary: "#e8edf2",
    textSecondary: "#9aa7b4",
    textMuted: "#6b7683",

    // Semantic
    error: "#ff8f8f",
    errorStrong: "#e5484d",
    success: "#3fa66a",
    warning: "#e8a23a",

    // Selection / accent — the warm orange used for both the beat/warning
    // accent and the "this was manually overridden" reset-affordance
    // styling (see #57's resetButton), and the red-orange used for the
    // timeline playhead specifically.
    accent: "#e8a23a",
    playhead: "#ff5a3c",

    // Per-element-type timeline colors — deliberately distinct from the
    // semantic palette above (each timeline bar type needs to be visually
    // distinguishable from the others at a glance), but centralized here
    // so a color is never redefined ad hoc in more than one component.
    timelineText: "#3a9bd5",
    timelineVisual: "#8b5cf6",
    timelineImage: "#2ac9a0",
    timelineBeat: "#e8a23a",
    timelinePresenter: "#2a7d6f",
    timelineTitle: "#c98a2a",

    // Chapter strip's own rotating categorical palette (ChapterStrip.tsx) —
    // kept as its own named array (not folded into the flat token list
    // above) since it's used by index, not by semantic name.
    chapterPalette: ["#3a7bd5", "#c96f2a", "#3aa66d", "#8b5cf6", "#d5473a", "#2aa1a1"],
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
} as const;
