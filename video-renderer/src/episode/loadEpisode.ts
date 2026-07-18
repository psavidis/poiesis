import fs from "node:fs";
import path from "node:path";
import type { EpisodeManifest } from "./types";

export function loadEpisodeManifest(
    episodePath: string
): EpisodeManifest {

    const manifestPath = path.join(
        episodePath,
        "processing",
        "manifest.json"
    );

    return JSON.parse(
        fs.readFileSync(manifestPath, "utf8")
    );
}