const state = {
  episodePath: null,
  status: null,
  runningStageId: null,
  socket: null,
  logText: "",
  logVisible: false,
};

// Which stages produce an artifact worth showing the human for review —
// this is the "make AI decisions transparent" surface the whole UI exists for.
const ARTIFACT_STAGES = {
  generate_title_scenes: { artifact: "title_scenes.json", render: renderTitleScenes },
  generate_visual_scenes: { artifact: "visual_scenes.json", render: renderVisualScenes },
  analyze_episode: { artifact: "episode_analysis.json", render: renderEpisodeAnalysis },
};

const app = document.getElementById("app");
const pathInput = document.getElementById("episode-path");
const loadButton = document.getElementById("load-episode");

loadButton.addEventListener("click", () => {
  const path = pathInput.value.trim();
  if (path) {
    loadEpisode(path);
  }
});

pathInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    loadButton.click();
  }
});

async function loadEpisode(path) {
  state.episodePath = path;

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
          <button id="run-qa" class="secondary" ${running ? "disabled" : ""}>QA check</button>
          <button id="run-render" class="secondary" ${running ? "disabled" : ""}>Render</button>
        </div>
      </div>
      <p class="hint">Every stage below shells out to the same scripts you'd run from the
      terminal, using your Claude Code CLI login — no separate API key, nothing hidden.</p>
      <div class="stage-list" id="stage-list"></div>
    </div>

    <div class="section" id="log-section" style="${state.logVisible ? "" : "display:none"}">
      <h2>Output</h2>
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
  runOverWebSocket("/ws/pipeline/run", { path: state.episodePath }, "__pipeline__");
}

function runRender() {
  runOverWebSocket("/ws/render/run", { path: state.episodePath }, "__render__");
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
    }
  });

  socket.addEventListener("close", () => {
    state.socket = null;
  });
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
  } catch (e) {
    reviewBody.innerHTML = `<p class="error">Failed to load artifact: ${escapeHtml(String(e))}</p>`;
  }
}

function renderTitleScenes(data) {
  const titles = data.titles || [];
  if (!titles.length) return `<p class="hint">No title scenes proposed.</p>`;

  return `
    <p class="hint">Titles Claude proposed for topic-change moments. Nothing here changes
    the video until you re-run the codegen/render steps.</p>
    <div class="scene-list">
      ${titles
        .map(
          (t) => `
        <div class="ai-decision">
          <div><span class="scene-type">TITLE</span> <strong>${escapeHtml(t.text || "")}</strong></div>
          <div class="reason">clip ${escapeHtml(t.videoId || "?")}</div>
        </div>
      `
        )
        .join("")}
    </div>
  `;
}

function renderVisualScenes(data) {
  const emphases = data.emphases || [];
  const images = data.images || [];

  if (!emphases.length && !images.length) {
    return `<p class="hint">No emphasis/image scenes proposed.</p>`;
  }

  return `
    <p class="hint">Overlays Claude proposed for moments that went too long without a visual
    change. Each one is grounded in something actually said, with the AI's stated reason.</p>
    <div class="scene-list">
      ${emphases
        .map(
          (e) => `
        <div class="ai-decision">
          <div><span class="scene-type">EMPHASIS</span> <strong>${escapeHtml(e.text || "")}</strong></div>
          ${e.reason ? `<div class="reason">${escapeHtml(e.reason)}</div>` : ""}
        </div>
      `
        )
        .join("")}
      ${images
        .map(
          (i) => `
        <div class="ai-decision">
          <div><span class="scene-type">IMAGE</span> <strong>${escapeHtml(i.assetId || "")}</strong> — ${escapeHtml(i.caption || "")}</div>
          ${i.reason ? `<div class="reason">${escapeHtml(i.reason)}</div>` : ""}
        </div>
      `
        )
        .join("")}
    </div>
  `;
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
