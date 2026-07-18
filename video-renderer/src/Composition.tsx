import { Composition } from "remotion";
import { Episode } from "./episode/Episode";

export type EpisodeProps = {
    episodePath: string;
    videos: {
        id: string;
        filename: string;
        path: string;
    }[];
};

export const MyComposition = () => {
    return (
        <Composition
            id="Episode"
            component={Episode}
            durationInFrames={300}
            fps={30}
            width={1920}
            height={1080}
            defaultProps={{
                episodePath:
                    "/Users/petros/Youtube/Philosoftware/Videos/Episode 9 - Dependency Injection",
                videos: [
                    {
                        id: "001",
                        filename: "0. Welcome.mov",
                        path: "original_footage/0. Welcome.mov",
                    },
                ],
            }}
        />
    );
};