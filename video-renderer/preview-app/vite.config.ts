import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Serves the real footage/graphics from ../public so staticFile() calls
// inside the actual Episode component resolve to real files — the preview
// renders the real composition against real assets, not a mock.
export default defineConfig({
    plugins: [react()],
    publicDir: path.resolve(import.meta.dirname, "../public"),
    server: {
        // Bind IPv4 explicitly — the rest of the app (control-panel UI's
        // links to this app, this app's own fetches to the control-panel
        // API, its CORS allow_origins) all use 127.0.0.1 consistently.
        // Vite's default host binds IPv6-only in some environments, which
        // makes 127.0.0.1 connection-refused while "localhost" still works.
        host: "127.0.0.1",
        port: 5173,
    },
    resolve: {
        alias: {
            "video-renderer-src": path.resolve(import.meta.dirname, "../src"),
            // Episode.tsx (imported from ../src via the alias above) and its
            // remotion imports must resolve against the SAME react/react-dom/
            // remotion instances this app uses — otherwise two copies of React
            // end up loaded (this app's own node_modules vs. the ones Episode.tsx
            // would naturally resolve from ../node_modules), which breaks hooks
            // with "Cannot read properties of null (reading 'useMemo')".
            react: path.resolve(import.meta.dirname, "node_modules/react"),
            "react-dom": path.resolve(import.meta.dirname, "node_modules/react-dom"),
            remotion: path.resolve(import.meta.dirname, "node_modules/remotion"),
        },
    },
});
