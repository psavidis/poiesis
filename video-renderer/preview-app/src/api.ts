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
    getArtifact(episodePath, "assets.json").then((data) => data.assets ?? []);
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
