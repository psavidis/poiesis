export const brand = {
    colors: {
        background: "#0d1b2a",
        backgroundGridLine: "rgba(255, 255, 255, 0.04)",
        accent: "#ff6b35",
        text: "#ffffff",
        textMuted: "rgba(255, 255, 255, 0.7)",
        overlayBackground: "rgba(13, 27, 42, 0.9)",
    },
    fonts: {
        family: "'Helvetica Neue', Helvetica, Arial, sans-serif",
    },
    radii: {
        chip: 10,
        frame: 14,
    },
} as const;

export const BackgroundGrid = ({ cellSize = 64 }: { cellSize?: number }) => (
    <div
        style={{
            position: "absolute",
            inset: 0,
            backgroundImage: `
                linear-gradient(${brand.colors.backgroundGridLine} 1px, transparent 1px),
                linear-gradient(90deg, ${brand.colors.backgroundGridLine} 1px, transparent 1px)
            `,
            backgroundSize: `${cellSize}px ${cellSize}px`,
        }}
    />
);
