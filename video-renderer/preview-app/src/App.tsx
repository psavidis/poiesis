import { useEffect } from "react";
import { EpisodeWorkspace } from "./EpisodeWorkspace";
import { RouterProvider, useRouter } from "./Router";

// Every existing caller of this app — ui/static/app.js's previewAppUrl(),
// anyone's saved bookmark from before this router existed — always links
// to the bare "/" with a ?path= (and optionally &sceneId=) query param.
// Redirecting "/" with a path param straight to "/episode" (preserving the
// full query string) means none of those callers need to change for this
// issue to land; #25 will replace this redirect with a real picker once
// there's somewhere else for a path-less "/" to go.
function RootRedirect() {
    const { navigate } = useRouter();

    useEffect(() => {
        const hasPath = new URLSearchParams(window.location.search).has("path");
        if (hasPath) {
            navigate("/episode" + window.location.search);
        }
    }, [navigate]);

    if (new URLSearchParams(window.location.search).has("path")) {
        return null;
    }

    // #25 replaces this with a real episode picker.
    return <div style={{ fontFamily: "system-ui, sans-serif", color: "#e8edf2", padding: 24 }}>Episode picker coming soon.</div>;
}

function Routes() {
    const { pathname } = useRouter();

    if (pathname === "/episode") {
        return <EpisodeWorkspace />;
    }

    return <RootRedirect />;
}

export function App() {
    return (
        <RouterProvider>
            <Routes />
        </RouterProvider>
    );
}
