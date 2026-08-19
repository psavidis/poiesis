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

export interface RenderStatus {
    running: boolean;
    current: number | null;
    total: number | null;
    // Set once, up front, when the render starts (see ui/server.py's
    // ws_run_render) — recoverable even in the brief window before the
    // first total/progress message has arrived, so a client can show
    // "Rendering DaVinci export (1920x1080)" rather than a bare
    // "Rendering..." with no indication of what's actually being produced.
    format: "video" | "davinci" | null;
    resolution: string | null;
}

// Recovers a render's live N-of-M progress (and what kind of render it is)
// after losing the websocket connection that started it (e.g. a page
// refresh) — see ui/server.py's render_status. Polled once on
// AdvancedPanel's mount and continuously by RenderStatusBanner, not a live
// subscription; the running render itself is unaffected either way, since
// it's a server-side process independent of any one client.
export async function getRenderStatus(episodePath: string): Promise<RenderStatus> {
    const res = await fetch(
        `${API_BASE}/api/episode/render-status?path=${encodeURIComponent(episodePath)}`
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Failed to load render status: ${res.status}`);
    }
    return res.json();
}

// Cancels a render that's still running but whose original websocket
// connection is gone — e.g. the tab that clicked Render was refreshed, so
// there's no RunHandle left to call .cancel() on over that specific
// connection (see AdvancedPanel's recoveredRender state, which has no
// working Cancel button today). Looks up the actual subprocess server-side
// via ui/server.py's render_cancel — works regardless of which tab/
// connection is asking.
export async function cancelRender(episodePath: string): Promise<void> {
    const res = await fetch(
        `${API_BASE}/api/episode/render-cancel?path=${encodeURIComponent(episodePath)}`,
        { method: "POST" }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Failed to cancel render: ${res.status}`);
    }
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

// The selectable background library (see index_backgrounds.py) — every
// image/video discovered under background/. Optional/empty is a normal,
// common case (no background/ folder at all), same as codeAssets above.
export const getBackgrounds = (episodePath: string) =>
    getArtifact(episodePath, "backgrounds.json")
        .then((data) => data.backgrounds ?? [])
        .catch(() => []);

export interface BackgroundSceneProposal {
    segmentId: string;
    backgroundId: string;
    // Slow zoom drift for a static-image background (see
    // BackgroundImageMotion in episode/types.ts). Absent means no
    // motion, only meaningful when the referenced background's own
    // mediaType is "image".
    imageMotion?: "none" | "zoom-in" | "zoom-out" | "palindrome";
    // How much the drift scales (see BackgroundImageMotionSpeed in
    // episode/types.ts). Absent means "normal", only meaningful when
    // imageMotion is set.
    imageMotionSpeed?: "subtle" | "normal" | "strong";
}

// The human-authored per-span selections (see
// generate_background_scenes.py) — unlike titles/moments/beats, never
// AI-proposed, so there is no "regenerate" concept here, only get/save.
export const getBackgroundScenes = (episodePath: string) =>
    getArtifact(episodePath, "background_scenes.json")
        .then((data) => (data.scenes ?? []) as BackgroundSceneProposal[])
        .catch(() => [] as BackgroundSceneProposal[]);

export async function saveBackgroundScenes(episodePath: string, scenes: BackgroundSceneProposal[]) {
    const res = await fetch(
        `${API_BASE}/api/episode/background-scenes?path=${encodeURIComponent(episodePath)}`,
        {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scenes }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Save failed");
    }
    return res.json();
}

// Lets the UI initialize "Include captions"/"Show captions" from the
// episode's ACTUAL last-run state instead of a fixed default that's the
// same for every episode regardless of what really happened (see #72 —
// "Show captions" stayed checked and silently did nothing on an episode
// where generate_captions.py had run with --disable, and "Include
// captions" showed unticked even on an episode that already had real
// captions). null return means the stage hasn't produced captions.json
// yet at all — genuinely different from "ran and produced zero captions."
export const getCaptionsInfo = (episodePath: string) =>
    getArtifact(episodePath, "captions.json")
        .then((data) => ({
            enabled: data.disabled !== true,
            count: Array.isArray(data.captions) ? data.captions.length : 0,
        }))
        .catch(() => null);
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

export type MomentInsertKind = "text" | "image" | "code" | "diagram";

// Cmd+I: inserts a minimal, content-empty moment at the playhead — the
// server resolves default duration/placement (resolve_manual_moment_
// creation) and appends it, returning the new moment's sceneId so the
// caller can select it and open its editor immediately.
export async function insertMoment(
    episodePath: string,
    sceneId: string,
    offsetInParentFrames: number,
    kind: MomentInsertKind
): Promise<{ moments: unknown[]; sceneId: string }> {
    const res = await fetch(
        `${API_BASE}/api/episode/moments/insert?path=${encodeURIComponent(episodePath)}`,
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sceneId, offsetInParentFrames, kind }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Insert failed");
    }
    return res.json();
}

// Switches an existing moment among the three code presentations
// (side-code / content-dominant-code / full-visual+code) while keeping
// the same codeAssetId — see #62, first slice of #42. Unlike saveMoments'
// generic field round-trip, the server computes the new duration/field
// cleanup itself; this only sends which scene and which target treatment.
export async function switchMomentTreatment(episodePath: string, sceneId: string, newTreatment: string) {
    const res = await fetch(
        `${API_BASE}/api/episode/moment-treatment?path=${encodeURIComponent(episodePath)}`,
        {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sceneId, newTreatment }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Save failed");
    }
    return res.json();
}

export const getBeats = (episodePath: string) => getArtifact(episodePath, "emphasis.json");

export async function saveBeats(episodePath: string, beats: unknown[]) {
    const res = await fetch(
        `${API_BASE}/api/episode/beats?path=${encodeURIComponent(episodePath)}`,
        {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ beats }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Save failed");
    }
    return res.json();
}

// Direct, non-LLM field update against a single scene in scene-plan.json
// (see ui/server.py's PUT /api/episode/scene) — used by ImageBar's
// drag-to-move/resize and display toggle (#46), which already know
// exactly which scene/field to change and don't need the edit-plan chat's
// natural-language interpretation. Server-side validation rejects an
// unknown scene id or a field outside that scene type's editable
// allowlist (422), same discipline as the chat endpoint.
export async function updateSceneFields(episodePath: string, sceneId: string, fields: Record<string, unknown>) {
    const res = await fetch(
        `${API_BASE}/api/episode/scene?path=${encodeURIComponent(episodePath)}`,
        {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sceneId, fields }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Save failed");
    }
    return res.json();
}

// Removes a single scene by id — the deterministic counterpart to
// updateSceneFields, for scene types (image scenes today) with no
// separate source-of-truth file to also update.
export async function deleteScene(episodePath: string, sceneId: string) {
    const res = await fetch(
        `${API_BASE}/api/episode/scene?path=${encodeURIComponent(episodePath)}&sceneId=${encodeURIComponent(sceneId)}`,
        { method: "DELETE" }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Delete failed");
    }
    return res.json();
}

export interface TitleSceneProposal {
    segmentId: string;
    text: string;
    // Human-set override for this title's own on-screen display duration
    // (#83) — set by dragging the title's segment edge in SceneBar. Absent
    // means "use the shared config default".
    durationFrames?: number;
    // Field names a human has explicitly changed since the AI last
    // proposed this title (#59) — server-recomputed on every save from a
    // segmentId-matched diff, same pattern as moments/beats (#57/#58).
    overriddenFields?: string[];
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

export interface ChapterBoundaryPosition {
    segmentId: string;
    timelineFrame: number;
}

// For ChapterStrip's drag-to-move boundary UI — every transcript
// segment's resolved absolute timeline frame, fetched once so a drag can
// snap client-side with no per-pixel server round trip. Segment text is
// deliberately not included (see resolvable_segment_positions).
export const getChapterBoundaryPositions = (episodePath: string) =>
    fetch(`${API_BASE}/api/episode/chapter-boundary-positions?path=${encodeURIComponent(episodePath)}`)
        .then((res) => (res.ok ? res.json() : { positions: [] }))
        .then((data) => (data.positions ?? []) as ChapterBoundaryPosition[])
        .catch(() => [] as ChapterBoundaryPosition[]);

// For background insertion (BackgroundBar's Cmd+B, AssetLibraryPanel's
// Backgrounds tab) — every position getChapterBoundaryPositions offers
// PLUS each presenter piece's own clip-start frame ("clip:{sceneId}"
// segmentIds — a second, disjoint namespace from real transcript "sN"
// ids). Without the clip-start entries, "insert at frame 0" snaps to the
// nearest transcript segment instead, which routinely starts a few frames
// after the clip's own start (silence trimmed before the first spoken
// word) — landing the background a few frames late. Deliberately a
// separate fetch from getChapterBoundaryPositions rather than reusing it
// for backgrounds too: ChapterStrip's title-boundary drag writes its
// snapped segmentId straight into title_scenes.json, which only ever
// resolves real "sN" ids — mixing "clip:..." ids into that shared list
// would make a title dragged onto one silently fail to resolve. See
// background_insertable_positions (generate_background_scenes.py) for the
// server-side counterpart.
export const getBackgroundInsertablePositions = (episodePath: string) =>
    fetch(`${API_BASE}/api/episode/background-insertable-positions?path=${encodeURIComponent(episodePath)}`)
        .then((res) => (res.ok ? res.json() : { positions: [] }))
        .then((data) => (data.positions ?? []) as ChapterBoundaryPosition[])
        .catch(() => [] as ChapterBoundaryPosition[]);

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

// A beat created via chat (#52) — grounded against real word-level
// transcript timing the same way an AI-pipeline-proposed beat is, not a
// free-floating LLM-guessed offset. Written to emphasis.json server-side,
// same shape as any other beat proposal there.
export interface CreatedBeat {
    // The PARENT presenter scene this beat attaches to — NOT the beat's
    // own id (that's only resolved server-side at write time; see
    // EditPlanResult.createdSceneIds below for the id to highlight).
    sceneId: string;
    kind: "word-pop" | "underline" | "icon-accent";
    text: string;
    icon: string | null;
    offsetInParentFrames: number;
    durationInFrames: number;
    reason?: string;
}

// A moment created via chat — either a bottom-callout (#53, grounded
// against what's actually said in the target scene's transcript) or a
// Full Screen diagram (treatment "full-visual", fullVisualKind "diagram" —
// grounded the same way generate_moments.py's own full-visual diagram
// proposals are, via is_diagram_grounded; see docs/specs/ai-assisted-
// editing-and-conversational-control.md section 5). Written to
// moments.json server-side, same shape as any other moment proposal
// there — text/diagram are mutually exclusive depending on treatment.
export interface CreatedMoment {
    // The PARENT presenter scene this moment attaches to — NOT the
    // moment's own id (see EditPlanResult.createdSceneIds below).
    sceneId: string;
    videoId: string;
    treatment: "bottom-callout" | "full-visual";
    text?: string;
    diagram?: { nodes: { id: string; label: string }[]; edges: { from: string; to: string; label?: string }[]; layout: "horizontal" | "vertical" };
    fullVisualKind?: "diagram";
    presenterSide: null;
    offsetInParentFrames: number;
    maxDurationInParentFrames: number;
    reason?: string;
}

// An inset image scene created via chat — the AI-creation path for
// ImageScene (previously unreachable by any real workflow: not the
// pipeline, not the editor UI, not chat — see
// docs/specs/content-types-and-presentation-editing.md). Unlike
// CreatedBeat/CreatedMoment, this already carries its own parentSceneId
// (not a bare "sceneId" meaning the parent) since image scenes have no
// separate source file to round-trip through — the server appends this
// straight into scene-plan.json.
export interface CreatedImage {
    type: "image";
    assetId: string;
    caption?: string;
    display: "inset";
    parentSceneId: string;
    offsetInParentFrames: number;
    durationInFrames: number;
}

export interface EditPlanResult {
    applied: EditPlanOperation[];
    rejected: { operation: EditPlanOperation; reason: string }[];
    created: CreatedBeat[];
    createdMoments: CreatedMoment[];
    createdImages: CreatedImage[];
    // Every scene id this instruction actually touched (#54) — each
    // `applied` op's own sceneId, plus the resolved scene-beat-{N}/
    // scene-moment-{N}/scene-image-{N} id for each created_beats/
    // createdMoments/createdImages entry (those entries' own `sceneId`/
    // `parentSceneId` field means their PARENT scene, not themselves —
    // see CreatedBeat/CreatedMoment/CreatedImage above). Used to
    // highlight/scroll to what changed on the relevant timeline bar(s).
    createdSceneIds: string[];
    // Only ever set when every other field above is empty — the model's
    // own reason for proposing no operations at all (e.g. "that exact
    // wording isn't something said in the transcript"), so a declined
    // instruction reaches the creator as an explanation, not a bare
    // generic message (#67).
    explanation: string | null;
}

// selectedSceneId (#51) — the scene currently selected in the editor when
// the instruction was submitted, so "make this bigger" can resolve
// without the user typing a scene id. Optional/best-effort: the server
// degrades gracefully (edit_plan.describe_selected_scene) if the id is
// stale or absent.
export async function editPlan(
    episodePath: string,
    instruction: string,
    selectedSceneId?: string
): Promise<EditPlanResult> {
    const res = await fetch(
        `${API_BASE}/api/episode/edit-plan?path=${encodeURIComponent(episodePath)}`,
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ instruction, selectedSceneId }),
        }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Edit request failed");
    }
    return res.json();
}

export interface UndoResult {
    restored: { label: string; files: { relative: string; existed: boolean }[] } | null;
}

// #50 — restores the most recent server-side checkpoint (see ui/undo.py),
// covering every write path (moments/beats/titles/storyboard/scene-field/
// edit-plan chat) uniformly, since each of those endpoints snapshots
// every file it's about to touch before writing. `restored: null` means
// there was nothing to undo (not an error) — the caller should treat that
// as a no-op, e.g. show "nothing to undo" rather than reloading.
export async function undoLastEdit(episodePath: string): Promise<UndoResult> {
    const res = await fetch(
        `${API_BASE}/api/episode/undo?path=${encodeURIComponent(episodePath)}`,
        { method: "POST" }
    );
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Undo failed");
    }
    return res.json();
}

export type RunMessage =
    | { type: "start"; command: string }
    | { type: "log"; line: string }
    // Only ever sent for a DaVinci export (export_davinci.py's __TOTAL__/
    // __PROGRESS__ sentinel lines — see ui/server.py's _stream_command);
    // every other run (pipeline stage, video render, QA check) never emits
    // these, so a caller not expecting them simply never receives them.
    | { type: "total"; count: number }
    | { type: "progress"; current: number; total: number }
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
