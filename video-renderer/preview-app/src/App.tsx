import { useEffect } from "react";
import { EpisodePicker } from "./EpisodePicker";
import { EpisodeWorkspace } from "./EpisodeWorkspace";
import { RouterProvider, useRouter } from "./Router";

// Every existing caller of this app — ui/static/app.js's previewAppUrl(),
// anyone's saved bookmark from before this router existed — always links
// to the bare "/" with a ?path= (and optionally &sceneId=) query param.
// Redirecting "/" with a path param straight to "/episode" (preserving the
// full query string) means none of those callers need to change: a "/"
// with a path still goes straight to the workspace, while a bare "/" now
// shows the real picker instead of #24's placeholder.
function Root() {
    const { navigate } = useRouter();

    const hasPath = new URLSearchParams(window.location.search).has("path");

    useEffect(() => {
        if (hasPath) {
            navigate("/episode" + window.location.search);
        }
    }, [navigate, hasPath]);

    if (hasPath) {
        return null;
    }

    return <EpisodePicker />;
}

function Routes() {
    const { pathname } = useRouter();

    if (pathname === "/episode") {
        return <EpisodeWorkspace />;
    }

    return <Root />;
}

export function App() {
    return (
        <RouterProvider>
            <Routes />
        </RouterProvider>
    );
}
