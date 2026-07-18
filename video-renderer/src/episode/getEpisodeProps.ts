import fs from "fs";
import path from "path";

export const getEpisodeProps = (episodePath: string) => {
    const manifestPath = path.join(
        episodePath,
        "processing",
        "manifest.json"
    );

    const manifest = JSON.parse(
        fs.readFileSync(manifestPath, "utf8")
    );

    return {
        episodePath,
        videos: manifest.videos,
    };
};