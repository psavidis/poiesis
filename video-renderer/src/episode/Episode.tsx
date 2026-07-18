import { AbsoluteFill } from "remotion";
import type { EpisodeProps } from "../Composition";

export const Episode: React.FC<EpisodeProps> = ({
                                                    episodePath,
                                                    videos,
                                                }) => {
    return (
        <AbsoluteFill
            style={{
                backgroundColor: "black",
                color: "white",
                fontSize: 50,
                justifyContent: "center",
                alignItems: "center",
                flexDirection: "column",
            }}
        >
            <div>
                {episodePath}
            </div>

            <div>
                {videos.length} clips loaded
            </div>
        </AbsoluteFill>
    );
};