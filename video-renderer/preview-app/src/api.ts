const API_BASE = "http://127.0.0.1:8000";

// Matches ui/server.py's own default — used when the picker has nowhere
// else to start (no remembered localStorage path yet), so a fresh install
// opens at the same place the old control panel did.
export const DEFAULT_BROWSE_PATH = "/Users/petros/Youtube/Philosoftware/Videos";

export interface BrowseEntry {
    name: string;
    path: string;
    isEpisode: boolean;
}

export interface BrowseResult {
    path: string;
    parent: string | null;
    isEpisode: boolean;
    entries: BrowseEntry[];
}

export async function browse(path?: string): Promise<BrowseResult> {
    const url = path
        ? `${API_BASE}/api/browse?path=${encodeURIComponent(path)}`
        : `${API_BASE}/api/browse`;
    const res = await fetch(url);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Failed to browse: ${res.status}`);
    }
    return res.json();
}

export interface EpisodeStageStatus {
    id: string;
    label: string;
    complete: boolean | null;
}

export interface EpisodeStatus {
    episode: string;
    path: string;
    stages: EpisodeStageStatus[];
    secondary: EpisodeStageStatus[];
    hasRender: boolean;
}

export async function getEpisodeStatus(episodePath: string): Promise<EpisodeStatus> {
    const res = await fetch(
        `${API_BASE}/api/episode/status?path=${encodeURIComponent(episodePath)}`
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Failed to load episode status: ${res.status}`);
    }
    return res.json();
}

async function getArtifact(episodePath: string, name: string) {
    const res = await fetch(
        `${API_BASE}/api/episode/artifact?path=${encodeURIComponent(episodePath)}&name=${encodeURIComponent(name)}`
    );
    if (!res.ok) {
        throw new Error(`Failed to load ${name}: ${res.status}`);
    }
    return res.json();
}

export const getScenePlan = (episodePath: string) => getArtifact(episodePath, "scene-plan.json");
export const getManifest = (episodePath: string) => getArtifact(episodePath, "manifest.json");
export const getAssets = (episodePath: string) =>
    getArtifact(episodePath, "assets.json")
        .then((data) => data.assets ?? [])
        .catch(() => []); // index_assets hasn't run yet (see #30) — a normal state while the plan is still filling in, not a failure
export const getCodeAssets = (episodePath: string) =>
    getArtifact(episodePath, "code_assets.json")
        .then((data) => data.codeAssets ?? [])
        .catch(() => []); // code_assets.json is optional — no code/ folder is a normal, common case
export const getMoments = (episodePath: string) => getArtifact(episodePath, "moments.json");

export async function saveMoments(episodePath: string, moments: unknown[]) {
    const res = await fetch(
        `${API_BASE}/api/episode/moments?path=${encodeURIComponent(episodePath)}`,
        {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ moments }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Save failed");
    }
    return res.json();
}

export interface TitleSceneProposal {
    segmentId: string;
    text: string;
}

export const getTitleScenes = (episodePath: string) =>
    getArtifact(episodePath, "title_scenes.json").then((data) => (data.titles ?? []) as TitleSceneProposal[]);

export async function saveTitleScenes(episodePath: string, titles: TitleSceneProposal[]) {
    const res = await fetch(
        `${API_BASE}/api/episode/title-scenes?path=${encodeURIComponent(episodePath)}`,
        {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ titles }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Save failed");
    }
    return res.json();
}

export interface StoryboardChapter {
    chapterId: string;
    chapterText: string;
    notes: string;
}

export const getStoryboard = (episodePath: string) =>
    getArtifact(episodePath, "storyboard.json").then((data) => (data.chapters ?? []) as StoryboardChapter[]);

// Read-only — ui/static/app.js's renderEpisodeAnalysis never offered editing,
// just a pretty-printed dump of analyze_episode's output (AI narrative
// summary + transcript QA).
export const getEpisodeAnalysis = (episodePath: string) => getArtifact(episodePath, "episode_analysis.json");

export async function saveStoryboard(episodePath: string, chapters: StoryboardChapter[]) {
    const res = await fetch(
        `${API_BASE}/api/episode/storyboard?path=${encodeURIComponent(episodePath)}`,
        {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ chapters }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Save failed");
    }
    return res.json();
}

export interface EditPlanOperation {
    op: "remove" | "update";
    sceneId: string;
    fields?: Record<string, unknown>;
    reason?: string;
}

export interface EditPlanResult {
    applied: EditPlanOperation[];
    rejected: { operation: EditPlanOperation; reason: string }[];
}

export async function editPlan(episodePath: string, instruction: string): Promise<EditPlanResult> {
    const res = await fetch(
        `${API_BASE}/api/episode/edit-plan?path=${encodeURIComponent(episodePath)}`,
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ instruction }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Edit request failed");
    }
    return res.json();
}

export type RunMessage =
    | { type: "start"; command: string }
    | { type: "log"; line: string }
    | { type: "error"; message: string }
    | { type: "done"; exitCode: number }
    | { type: "cancelled" };

export interface RunHandle {
    cancel: () => void;
}

// Shared WebSocket-run helper for /ws/pipeline/run, /ws/stage/run, and
// /ws/render/run — all three speak the identical {type: start|log|error|
// done|cancelled} protocol (see ui/server.py's _stream_command), so every
// caller (the collapsed progress flow's "Start" button, Advanced's
// per-stage Run/Re-run, its Render/QA-check buttons) shares one
// implementation instead of three copies of the same WebSocket plumbing
// ui/static/app.js's runOverWebSocket() used to be.
export function runOverWebSocket(
    path: string,
    params: Record<string, unknown>,
    onMessage: (msg: RunMessage) => void
): RunHandle {
    const protocol = API_BASE.startsWith("https:") ? "wss:" : "ws:";
    const wsBase = API_BASE.replace(/^https?:/, protocol);
    const socket = new WebSocket(`${wsBase}${path}`);

    socket.addEventListener("open", () => {
        socket.send(JSON.stringify(params));
    });

    socket.addEventListener("message", (event) => {
        onMessage(JSON.parse(event.data) as RunMessage);
    });

    return {
        cancel: () => {
            if (socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: "cancel" }));
            }
        },
    };
}
