const DEFAULT_BROWSE_PATH = "/Users/petros/Youtube/Philosoftware/Videos";

const state = {
  episodePath: null,
  status: null,
  runningStageId: null,
  socket: null,
  logText: "",
  logVisible: false,
  // Persisted per browser session (not per episode) — full-sentence
  // captions are tiresome on some episodes, so the default is opt-in
  // (unticked = don't generate them). Ticking this includes captions on
  // the next full pipeline run; translated to the inverted --skip-captions
  // flag only where the backend command is actually built.
  includeCaptions: false,
  // "video" (default, render_episode.sh -> MP4) or "davinci"
  // (pipeline/export_davinci.py -> an OTIO timeline + per-scene
  // transparent clips the user imports into DaVinci Resolve). Both
  // formats accept the same optional resolution override.
  renderFormat: "video",
  renderResolution: "",
};

// Which stages produce an artifact worth showing the human for review —
// this is the "make AI decisions transparent" surface the whole UI exists for.
const ARTIFACT_STAGES = {
  generate_title_scenes: { artifact: "title_scenes.json", render: renderTitleScenes },
  generate_moments: { artifact: "moments.json", render: renderMoments },
  analyze_episode: { artifact: "episode_analysis.json", render: renderEpisodeAnalysis },
};

const app = document.getElementById("app");
const currentPathLabel = document.getElementById("current-episode-path");
const browseButton = document.getElementById("browse-episode");
const browseModal = document.getElementById("browse-modal");
const browseCloseButton = document.getElementById("browse-close");
const browseCurrentPath = document.getElementById("browse-current-path");
const browseList = document.getElementById("browse-list");

browseButton.addEventListener("click", () => {
  openBrowser(state.episodePath || DEFAULT_BROWSE_PATH);
});

browseCloseButton.addEventListener("click", closeBrowser);

browseModal.addEventListener("click", (e) => {
  if (e.target === browseModal) {
    closeBrowser();
  }
});

openBrowser(DEFAULT_BROWSE_PATH);

async function openBrowser(path) {
  browseModal.style.display = "flex";
  await loadBrowseDir(path);
}

function closeBrowser() {
  browseModal.style.display = "none";
}

async function loadBrowseDir(path) {
  browseCurrentPath.textContent = path;
  browseList.innerHTML = `<p class="browse-empty">Loading…</p>`;

  try {
    const res = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
    if (!res.ok) {
      const err = await res.json();
      browseList.innerHTML = `<p class="browse-empty">${escapeHtml(err.detail)}</p>`;
      return;
    }
    const data = await res.json();
    renderBrowseList(data);
  } catch (e) {
    browseList.innerHTML = `<p class="browse-empty">Failed to browse: ${escapeHtml(String(e))}</p>`;
  }
}

function renderBrowseList(data) {
  browseCurrentPath.textContent = data.path;

  const rows = [];

  if (data.parent) {
    rows.push(`
      <div class="browse-row" data-action="up">
        <span class="icon">⬆</span>
        <span class="name">.. (up one level)</span>
      </div>
    `);
  }

  if (data.isEpisode) {
    rows.push(`
      <div class="browse-row episode" data-action="select" data-path="${escapeHtml(data.path)}">
        <span class="icon">📂</span>
        <span class="name">Use this folder</span>
        <span class="badge">Episode</span>
      </div>
    `);
  }

  if (!data.entries.length) {
    rows.push(`<p class="browse-empty">No subfolders here.</p>`);
  } else {
    data.entries.forEach((entry) => {
      rows.push(`
        <div class="browse-row ${entry.isEpisode ? "episode" : ""}" data-action="${entry.isEpisode ? "select" : "open"}" data-path="${escapeHtml(entry.path)}">
          <span class="icon">${entry.isEpisode ? "📂" : "📁"}</span>
          <span class="name">${escapeHtml(entry.name)}</span>
          ${entry.isEpisode ? `<span class="badge">Episode</span>` : ""}
        </div>
      `);
    });
  }

  browseList.innerHTML = rows.join("");

  browseList.querySelectorAll("[data-action]").forEach((el) => {
    el.addEventListener("click", () => {
      const action = el.dataset.action;

      if (action === "up") {
        loadBrowseDir(data.parent);
      } else if (action === "select") {
        closeBrowser();
        loadEpisode(el.dataset.path);
      } else if (action === "open") {
        loadBrowseDir(el.dataset.path);
      }
    });
  });
}

async function loadEpisode(path) {
  state.episodePath = path;
  currentPathLabel.textContent = path;

  try {
    const res = await fetch(`/api/episode/status?path=${encodeURIComponent(path)}`);
    if (!res.ok) {
      const err = await res.json();
      app.innerHTML = `<p class="error">${escapeHtml(err.detail)}</p>`;
      return;
    }
    state.status = await res.json();
    render();
  } catch (e) {
    app.innerHTML = `<p class="error">Failed to load episode: ${escapeHtml(String(e))}</p>`;
  }
}

async function refreshStatus() {
  const res = await fetch(`/api/episode/status?path=${encodeURIComponent(state.episodePath)}`);
  if (res.ok) {
    state.status = await res.json();
    render();
  }
}

function render() {
  const status = state.status;
  const running = state.runningStageId;

  app.innerHTML = `
    <div class="section">
      <div class="section-header">
        <h2>${escapeHtml(status.episode)}</h2>
        <div class="actions">
          <button id="run-all" ${running ? "disabled" : ""}>Run full pipeline</button>
          <a class="secondary" href="${previewAppUrl(state.episodePath)}" target="_blank" rel="noopener">Preview episode</a>
          <button id="run-qa" class="secondary" ${running ? "disabled" : ""}>QA check</button>
          <button id="run-render" class="secondary" ${running ? "disabled" : ""}>Render</button>
        </div>
      </div>
      <label class="checkbox-row">
        <input type="checkbox" id="include-captions-toggle" ${state.includeCaptions ? "checked" : ""} ${running ? "disabled" : ""} />
        Include captions on next full pipeline run (leave unticked to remove any already generated)
      </label>
      <div class="render-options">
        <label>
          Output format
          <select id="render-format-select" ${running ? "disabled" : ""}>
            <option value="video" ${state.renderFormat === "video" ? "selected" : ""}>Video (MP4)</option>
            <option value="davinci" ${state.renderFormat === "davinci" ? "selected" : ""}>DaVinci Resolve project (OTIO timeline)</option>
          </select>
        </label>
        <label>
          Resolution
          <select id="render-resolution-select" ${running ? "disabled" : ""}>
            <option value="" ${state.renderResolution === "" ? "selected" : ""}>Default (from config.json)</option>
            <option value="1920x1080" ${state.renderResolution === "1920x1080" ? "selected" : ""}>1920x1080</option>
            <option value="3840x2160" ${state.renderResolution === "3840x2160" ? "selected" : ""}>3840x2160</option>
          </select>
        </label>
      </div>
      <p class="hint">"DaVinci Resolve project" renders presenter + overlays only (titles,
      moments, captions already baked in) as one transparent clip per scene, plus a
      timeline.otio you import via Resolve's File → Import Timeline → OpenTimelineIO —
      background/intro/outro/music stay a manual step in Resolve either way, same as
      today's transparent render workflow.</p>
      <p class="hint">Every stage below shells out to the same scripts you'd run from the
      terminal, using your Claude Code CLI login — no separate API key, nothing hidden.</p>
      <div class="stage-list" id="stage-list"></div>
    </div>

    <div class="section" id="log-section" style="${state.logVisible ? "" : "display:none"}">
      <div class="section-header">
        <h2>Output</h2>
        ${running ? `<button id="cancel-run" class="danger small">Cancel</button>` : ""}
      </div>
      <div class="log-panel" id="log-panel">${escapeHtml(state.logText)}</div>
    </div>

    <div class="section" id="review-section">
      <h2>AI decisions to review</h2>
      <div id="review-body">
        <p class="hint">Run the AI stages above, then their proposals will show up here for you to inspect before rendering.</p>
      </div>
    </div>
  `;

  const stageList = document.getElementById("stage-list");
  stageList.innerHTML = status.stages
    .map((stage) => stageRowHtml(stage, running)).join("");

  status.stages.forEach((stage) => {
    const btn = document.getElementById(`run-stage-${stage.id}`);
    if (btn) btn.addEventListener("click", () => runStage(stage.id));

    const viewBtn = document.getElementById(`view-stage-${stage.id}`);
    if (viewBtn) viewBtn.addEventListener("click", () => showArtifact(stage.id));
  });

  document.getElementById("run-all").addEventListener("click", runFullPipeline);
  document.getElementById("run-qa").addEventListener("click", () => runSecondaryStage("qa_check"));
  document.getElementById("run-render").addEventListener("click", runRender);

  document.getElementById("include-captions-toggle").addEventListener("change", (e) => {
    state.includeCaptions = e.target.checked;
  });

  document.getElementById("render-format-select").addEventListener("change", (e) => {
    state.renderFormat = e.target.value;
  });

  document.getElementById("render-resolution-select").addEventListener("change", (e) => {
    state.renderResolution = e.target.value;
  });

  const cancelBtn = document.getElementById("cancel-run");
  if (cancelBtn) cancelBtn.addEventListener("click", cancelRun);

  if (state.logVisible) {
    const logPanel = document.getElementById("log-panel");
    logPanel.scrollTop = logPanel.scrollHeight;
  }

  // Re-render whichever AI stage's artifact is furthest along, so the review
  // panel stays populated across reloads instead of only right after a run.
  const reviewable = status.stages
    .filter((s) => ARTIFACT_STAGES[s.id] && s.complete)
    .map((s) => s.id);
  if (reviewable.length) {
    showArtifact(reviewable[reviewable.length - 1]);
  }
}

function stageRowHtml(stage, running) {
  const isRunning = running === stage.id;
  const statusClass = isRunning ? "running" : stage.complete ? "complete" : "";
  const canView = ARTIFACT_STAGES[stage.id] && stage.complete;

  return `
    <div class="stage-row">
      <span class="stage-status ${statusClass}"></span>
      <span class="stage-label">${escapeHtml(stage.label)}</span>
      <span class="stage-row-actions">
        ${canView ? `<button class="secondary small" id="view-stage-${stage.id}">View</button>` : ""}
        <button class="secondary small" id="run-stage-${stage.id}" ${running ? "disabled" : ""}>
          ${stage.complete ? "Re-run" : "Run"}
        </button>
      </span>
    </div>
  `;
}

function runStage(stageId) {
  runOverWebSocket("/ws/stage/run", { path: state.episodePath, stage: stageId }, stageId);
}

function runSecondaryStage(stageId) {
  runOverWebSocket("/ws/stage/run", { path: state.episodePath, stage: stageId }, stageId);
}

function runFullPipeline() {
  runOverWebSocket(
    "/ws/pipeline/run",
    { path: state.episodePath, skipCaptions: !state.includeCaptions },
    "__pipeline__"
  );
}

function runRender() {
  const params = { path: state.episodePath, format: state.renderFormat };
  if (state.renderResolution) {
    params.resolution = state.renderResolution;
  }
  runOverWebSocket("/ws/render/run", params, "__render__");
}

function runOverWebSocket(path, params, runningId) {
  if (state.socket) {
    return;
  }

  state.runningStageId = runningId;
  state.logText = "";
  state.logVisible = true;
  render();

  const logPanel = document.getElementById("log-panel");

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}${path}`);
  state.socket = socket;

  socket.addEventListener("open", () => {
    socket.send(JSON.stringify(params));
  });

  socket.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);

    if (msg.type === "start") {
      appendLog(logPanel, `$ ${msg.command}\n`);
    } else if (msg.type === "log") {
      appendLog(logPanel, `${msg.line}\n`);
    } else if (msg.type === "error") {
      appendLog(logPanel, `\nERROR: ${msg.message}\n`);
      finishRun(false);
    } else if (msg.type === "done") {
      appendLog(logPanel, `\n(exit code ${msg.exitCode})\n`);
      finishRun(msg.exitCode === 0);
    } else if (msg.type === "cancelled") {
      appendLog(logPanel, `\nCancelled.\n`);
      finishRun(false);
    }
  });

  socket.addEventListener("close", () => {
    state.socket = null;
  });
}

function cancelRun() {
  if (state.socket && state.socket.readyState === WebSocket.OPEN) {
    state.socket.send(JSON.stringify({ type: "cancel" }));
  }
}

function finishRun(success) {
  state.runningStageId = null;
  if (state.socket) {
    state.socket.close();
    state.socket = null;
  }
  refreshStatus();
}

function appendLog(panel, text) {
  state.logText += text;
  panel.textContent += text;
  panel.scrollTop = panel.scrollHeight;
}

async function showArtifact(stageId) {
  const config = ARTIFACT_STAGES[stageId];
  const reviewBody = document.getElementById("review-body");
  if (!config || !reviewBody) return;

  try {
    const res = await fetch(
      `/api/episode/artifact?path=${encodeURIComponent(state.episodePath)}&name=${encodeURIComponent(config.artifact)}`
    );
    if (!res.ok) {
      const err = await res.json();
      reviewBody.innerHTML = `<p class="error">${escapeHtml(err.detail)}</p>`;
      return;
    }
    const data = await res.json();
    reviewBody.innerHTML = config.render(data);

    if (stageId === "generate_title_scenes") {
      wireTitleSceneEditor(data.titles || []);
    }

    if (stageId === "generate_moments") {
      await wireMomentEditor(data.moments || []);
    }
  } catch (e) {
    reviewBody.innerHTML = `<p class="error">Failed to load artifact: ${escapeHtml(String(e))}</p>`;
  }
}

function renderTitleScenes(data) {
  const titles = data.titles || [];

  return `
    <p class="hint">Titles Claude proposed for topic-change moments. Edit the text or remove
    a title below, then save — this rewrites title_scenes.json and re-merges scene-plan.json
    deterministically (no AI call), regenerating the Remotion codegen automatically so the next
    render picks up the change.</p>
    <div class="scene-list" id="title-scene-editor">
      ${
        titles.length
          ? titles
              .map(
                (t, i) => `
        <div class="ai-decision editable-scene" data-index="${i}">
          <span class="scene-type">TITLE</span>
          <input type="text" class="title-text-input" value="${escapeHtml(t.text || "")}" data-video-id="${escapeHtml(t.videoId || "")}" />
          <span class="reason">clip ${escapeHtml(t.videoId || "?")}</span>
          <button class="secondary small remove-title-btn" data-index="${i}">Remove</button>
        </div>
      `
              )
              .join("")
          : `<p class="hint" id="no-titles-hint">No title scenes proposed.</p>`
      }
    </div>
    <div class="editor-actions">
      <button id="save-titles-btn">Save changes</button>
      <span id="save-titles-status" class="hint"></span>
    </div>
  `;
}

function wireTitleSceneEditor(initialTitles) {
  let titles = initialTitles.map((t) => ({ videoId: t.videoId, text: t.text }));

  const editor = document.getElementById("title-scene-editor");
  const statusLabel = document.getElementById("save-titles-status");
  const saveBtn = document.getElementById("save-titles-btn");

  if (!editor || !saveBtn) return;

  editor.querySelectorAll(".title-text-input").forEach((input) => {
    input.addEventListener("input", () => {
      const index = Number(input.closest(".editable-scene").dataset.index);
      titles[index] = { ...titles[index], text: input.value };
    });
  });

  editor.querySelectorAll(".remove-title-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const index = Number(btn.dataset.index);
      titles.splice(index, 1);
      const reviewBody = document.getElementById("review-body");
      reviewBody.innerHTML = renderTitleScenes({ titles });
      wireTitleSceneEditor(titles);
    });
  });

  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    statusLabel.textContent = "Saving…";
    statusLabel.classList.remove("error");

    try {
      const res = await fetch(
        `/api/episode/title-scenes?path=${encodeURIComponent(state.episodePath)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ titles }),
        }
      );

      if (!res.ok) {
        const err = await res.json();
        statusLabel.textContent = err.detail || "Save failed.";
        statusLabel.classList.add("error");
        return;
      }

      statusLabel.textContent = "Saved — the next render will pick this up.";
    } catch (e) {
      statusLabel.textContent = `Save failed: ${e}`;
      statusLabel.classList.add("error");
    } finally {
      saveBtn.disabled = false;
    }
  });
}

function renderMoments(data) {
  const moments = data.moments || [];

  if (!moments.length) {
    return `<p class="hint">No moment scenes proposed.</p>`;
  }

  return `
    <p class="hint">Moments Claude proposed for stretches that went too long without a visual
    change — a bottom callout, or a side text/image treatment that also slides the presenter to
    the opposite side of the frame for that moment's own window. Each one is grounded in
    something actually said, with the AI's stated reason. Edit text/asset or remove one, then
    save — this rewrites moments.json and re-merges scene-plan.json deterministically (no AI
    call), regenerating the Remotion codegen automatically so the next render picks up the
    change. Use "Adjust timing" to scrub/drag when a moment appears and how long it shows
    against the real footage (opens in a new tab — video-renderer/preview-app must be running
    via <code>npm run dev</code> in that folder; saves there apply immediately, no separate save
    step here).</p>
    <div class="scene-list" id="moment-scene-list"></div>
    <div class="editor-actions">
      <button id="save-moments-btn">Save changes</button>
      <span id="save-moments-status" class="hint"></span>
    </div>
  `;
}

// Preview app dev server (video-renderer/preview-app, `npm run dev` there) —
// where "Adjust timing" opens a scrubbable, drag-to-adjust view of an
// overlay's timing against the real presenter footage. Timing edits save
// straight to the backend from that tab; this panel only re-fetches
// moments.json when you come back to it (see wireMomentEditor's focus
// listener) rather than trying to keep two live edit buffers in sync.
const PREVIEW_APP_BASE = "http://127.0.0.1:5173";

function previewAppUrl(episodePath, sceneId) {
  const base = `${PREVIEW_APP_BASE}/?path=${encodeURIComponent(episodePath)}`;
  return sceneId ? `${base}&sceneId=${encodeURIComponent(sceneId)}` : base;
}

const TREATMENT_LABELS = {
  "bottom-callout": "BOTTOM CALLOUT",
  "side-text": "SIDE TEXT",
  "side-image": "SIDE IMAGE",
};

function renderMomentRow(m, i, assetOptions) {
  const label = TREATMENT_LABELS[m.treatment] || m.treatment.toUpperCase();

  const contentInput =
    m.treatment === "side-image"
      ? `
      <select class="moment-asset-input">
        ${assetOptions
          .map(
            (a) =>
              `<option value="${escapeHtml(a.id)}" ${a.id === m.assetId ? "selected" : ""}>${escapeHtml(a.id)} — ${escapeHtml(a.caption || "")}</option>`
          )
          .join("")}
      </select>
    `
      : `<input type="text" class="moment-text-input" value="${escapeHtml(m.text || "")}" />`;

  const sideNote = m.presenterSide ? `presenter → ${escapeHtml(m.presenterSide)} — ` : "";

  return `
    <div class="ai-decision editable-scene" data-index="${i}">
      <span class="scene-type">${escapeHtml(label)}</span>
      ${contentInput}
      <span class="reason">${sideNote}clip ${escapeHtml(m.videoId || "?")} — offset ${m.offsetInParentFrames}f, up to ${m.maxDurationInParentFrames}f${m.reason ? ` — ${escapeHtml(m.reason)}` : ""}</span>
      <a class="secondary small adjust-timing-link" href="${previewAppUrl(state.episodePath, m.sceneId)}" target="_blank" rel="noopener">Adjust timing</a>
      <button class="secondary small remove-moment-btn" data-index="${i}">Remove</button>
    </div>
  `;
}

async function getMomentsArtifact() {
  const res = await fetch(
    `/api/episode/artifact?path=${encodeURIComponent(state.episodePath)}&name=moments.json`
  );
  if (!res.ok) {
    throw new Error(`Failed to reload moments.json: ${res.status}`);
  }
  return res.json();
}

// Tracks the currently-active visibilitychange listener so switching stages
// (or re-opening this one) doesn't stack up duplicate listeners — each call
// to wireMomentEditor owns exactly one.
let activeMomentFocusListener = null;

async function wireMomentEditor(initialMoments) {
  if (activeMomentFocusListener) {
    document.removeEventListener("visibilitychange", activeMomentFocusListener);
    activeMomentFocusListener = null;
  }

  let moments = initialMoments.map((m) => ({ ...m }));

  let assetOptions = [];
  try {
    const res = await fetch(
      `/api/episode/artifact?path=${encodeURIComponent(state.episodePath)}&name=assets.json`
    );
    if (res.ok) {
      const data = await res.json();
      assetOptions = data.assets || [];
    }
  } catch (e) {
    // assets.json may not exist yet — side-image rows just won't offer a dropdown
  }

  const momentList = document.getElementById("moment-scene-list");
  const statusLabel = document.getElementById("save-moments-status");
  const saveBtn = document.getElementById("save-moments-btn");

  if (!momentList || !saveBtn) return;

  function renderList() {
    momentList.innerHTML = moments.length
      ? moments.map((m, i) => renderMomentRow(m, i, assetOptions)).join("")
      : `<p class="hint">No moment scenes proposed.</p>`;
    wireRows();
  }

  function wireRows() {
    momentList.querySelectorAll(".editable-scene").forEach((row) => {
      const index = Number(row.dataset.index);

      const textInput = row.querySelector(".moment-text-input");
      if (textInput) {
        textInput.addEventListener("input", (e) => {
          moments[index] = { ...moments[index], text: e.target.value };
        });
      }

      const assetSelect = row.querySelector(".moment-asset-input");
      if (assetSelect) {
        assetSelect.addEventListener("change", (e) => {
          const asset = assetOptions.find((a) => a.id === e.target.value);
          moments[index] = {
            ...moments[index],
            assetId: e.target.value,
            caption: asset ? asset.caption : moments[index].caption,
          };
        });
      }

      row.querySelector(".remove-moment-btn").addEventListener("click", () => {
        moments.splice(index, 1);
        renderList();
      });
    });
  }

  // Timing edits happen in the preview app (new tab, "Adjust timing") and
  // save straight to moments.json there. Re-fetch and re-render whenever
  // this tab regains focus so a timing change made in the preview tab shows
  // up here too, instead of being silently overwritten by this panel's own
  // (stale) local buffer on its next "Save changes".
  activeMomentFocusListener = async () => {
    if (document.visibilityState !== "visible") return;
    try {
      const fresh = await getMomentsArtifact();
      moments = (fresh.moments || []).map((m) => ({ ...m }));
      renderList();
    } catch (e) {
      // control panel's own fetch failed — leave the current buffer as-is
    }
  };
  document.addEventListener("visibilitychange", activeMomentFocusListener);

  renderList();

  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    statusLabel.textContent = "Saving…";
    statusLabel.classList.remove("error");

    try {
      const res = await fetch(
        `/api/episode/moments?path=${encodeURIComponent(state.episodePath)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ moments }),
        }
      );

      if (!res.ok) {
        const err = await res.json();
        statusLabel.textContent = err.detail || "Save failed.";
        statusLabel.classList.add("error");
        return;
      }

      statusLabel.textContent = "Saved — the next render will pick this up.";
    } catch (e) {
      statusLabel.textContent = `Save failed: ${e}`;
      statusLabel.classList.add("error");
    } finally {
      saveBtn.disabled = false;
    }
  });
}

function renderEpisodeAnalysis(data) {
  return `
    <p class="hint">Full AI QA pass output.</p>
    <pre class="json-view">${escapeHtml(JSON.stringify(data, null, 2))}</pre>
  `;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
