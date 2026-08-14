import { config } from "@remotion/eslint-config-flat";

export default [
    ...config,
    {
        // Test files contain plain fixture data (e.g. `durationInFrames: 900`
        // as a test prop), not real Remotion animation code — the
        // non-pure-animation rule pattern-matches prop names and false
        // positives on that data with no actual animation involved.
        files: ["**/*.test.ts", "**/*.test.tsx"],
        rules: {
            "@remotion/non-pure-animation": "off",
        },
    },
];
