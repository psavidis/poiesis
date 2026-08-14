const API_BASE = "http://127.0.0.1:8000";

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
export const getVisualScenes = (episodePath: string) => getArtifact(episodePath, "visual_scenes.json");

export async function saveVisualScenes(
    episodePath: string,
    emphases: unknown[],
    images: unknown[]
) {
    const res = await fetch(
        `${API_BASE}/api/episode/visual-scenes?path=${encodeURIComponent(episodePath)}`,
        {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ emphases, images }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Save failed");
    }
    return res.json();
}
