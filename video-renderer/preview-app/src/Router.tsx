import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

// Minimal hand-rolled router — two routes ("/" and "/episode") don't
// justify a routing library dependency. Tracks window.location.pathname,
// exposes navigate() for programmatic transitions, and listens to
// popstate so browser back/forward work.
interface RouterState {
    pathname: string;
    navigate: (path: string) => void;
}

const RouterContext = createContext<RouterState | null>(null);

export function RouterProvider({ children }: { children: ReactNode }) {
    const [pathname, setPathname] = useState(window.location.pathname);

    useEffect(() => {
        const onPopState = () => setPathname(window.location.pathname);
        window.addEventListener("popstate", onPopState);
        return () => window.removeEventListener("popstate", onPopState);
    }, []);

    const navigate = (path: string) => {
        if (path === window.location.pathname + window.location.search) return;
        window.history.pushState(null, "", path);
        setPathname(window.location.pathname);
    };

    return <RouterContext.Provider value={{ pathname, navigate }}>{children}</RouterContext.Provider>;
}

export function useRouter(): RouterState {
    const ctx = useContext(RouterContext);
    if (!ctx) throw new Error("useRouter must be used inside a RouterProvider");
    return ctx;
}
