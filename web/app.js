const state = {
  projects: [],
  selectedProjectId: null,
  currentStoryboard: null,
  apiConfig: null,
};

const el = {
  projectsList: document.getElementById("projects-list"),
  projectTitle: document.getElementById("project-title"),
  projectMeta: document.getElementById("project-meta"),
  plotInput: document.getElementById("plot-input"),
  plotStatus: document.getElementById("plot-status"),
  pipelineStatus: document.getElementById("pipeline-status"),
  storyboardStatus: document.getElementById("storyboard-status"),
  manualCharactersStatus: document.getElementById("manual-characters-status"),
  manualCharacterName: document.getElementById("manual-character-name"),
  manualCharacterDescription: document.getElementById("manual-character-description"),
  storyboardTitle: document.getElementById("storyboard-title"),
  storyboardSummary: document.getElementById("storyboard-summary"),
  storyboardDuration: document.getElementById("storyboard-duration"),
  addSceneBtn: document.getElementById("add-scene-btn"),
  scenesEditor: document.getElementById("scenes-editor"),
  charactersGrid: document.getElementById("characters-grid"),
  sceneImagesGrid: document.getElementById("scene-images-grid"),
  charactersStatus: document.getElementById("characters-status"),
  imagesStatus: document.getElementById("images-status"),
  downloadStoryboardLink: document.getElementById("download-storyboard-link"),
  storyboardFileInput: document.getElementById("storyboard-file-input"),
  deleteStoryboardBtn: document.getElementById("delete-storyboard-btn"),
  renameProjectBtn: document.getElementById("rename-project-btn"),
  sceneReferenceScale: document.getElementById("scene-reference-scale"),
  sceneReferenceScaleValue: document.getElementById("scene-reference-scale-value"),
  apiConfigStatus: document.getElementById("api-config-status"),
  saveApiConfigBtn: document.getElementById("save-api-config-btn"),
  reloadApiConfigBtn: document.getElementById("reload-api-config-btn"),
  apiLlmProvider: document.getElementById("api-llm-provider"),
  apiLlmApiKey: document.getElementById("api-llm-api-key"),
  apiLlmBaseUrl: document.getElementById("api-llm-base-url"),
  apiLlmModel: document.getElementById("api-llm-model"),
  apiVideoProvider: document.getElementById("api-video-provider"),
  apiVolcAccessKey: document.getElementById("api-volc-access-key"),
  apiVolcSecretKey: document.getElementById("api-volc-secret-key"),
  apiJimengModel: document.getElementById("api-jimeng-model"),
  apiRunwayApiKey: document.getElementById("api-runway-api-key"),
  apiPikaApiKey: document.getElementById("api-pika-api-key"),
  apiCharacterImageProvider: document.getElementById("api-character-image-provider"),
  apiCharacterImageModel: document.getElementById("api-character-image-model"),
  apiPublicAssetBaseUrl: document.getElementById("api-public-asset-base-url"),
  apiArkApiKey: document.getElementById("api-ark-api-key"),
  apiArkBaseUrl: document.getElementById("api-ark-base-url"),
  apiVolcTtsAccessToken: document.getElementById("api-volc-tts-access-token"),
  apiVolcTtsAppId: document.getElementById("api-volc-tts-app-id"),
  apiVolcTtsDefaultVoice: document.getElementById("api-volc-tts-default-voice"),
  lightbox: document.getElementById("image-lightbox"),
  lightboxImage: document.getElementById("lightbox-image"),
  lightboxCloseBtn: document.getElementById("lightbox-close-btn"),
};

const API_FIELD_MAP = [
  ["LLM_PROVIDER", "apiLlmProvider"],
  ["LLM_API_KEY", "apiLlmApiKey"],
  ["LLM_BASE_URL", "apiLlmBaseUrl"],
  ["LLM_MODEL", "apiLlmModel"],
  ["VIDEO_PROVIDER", "apiVideoProvider"],
  ["VOLC_ACCESS_KEY", "apiVolcAccessKey"],
  ["VOLC_SECRET_KEY", "apiVolcSecretKey"],
  ["JIMENG_MODEL", "apiJimengModel"],
  ["RUNWAY_API_KEY", "apiRunwayApiKey"],
  ["PIKA_API_KEY", "apiPikaApiKey"],
  ["CHARACTER_IMAGE_PROVIDER", "apiCharacterImageProvider"],
  ["CHARACTER_IMAGE_MODEL", "apiCharacterImageModel"],
  ["PUBLIC_ASSET_BASE_URL", "apiPublicAssetBaseUrl"],
  ["ARK_API_KEY", "apiArkApiKey"],
  ["ARK_BASE_URL", "apiArkBaseUrl"],
  ["VOLC_TTS_ACCESS_TOKEN", "apiVolcTtsAccessToken"],
  ["VOLC_TTS_APP_ID", "apiVolcTtsAppId"],
  ["VOLC_TTS_DEFAULT_VOICE", "apiVolcTtsDefaultVoice"],
];

const SECRET_API_FIELDS = new Set([
  "LLM_API_KEY",
  "VOLC_ACCESS_KEY",
  "VOLC_SECRET_KEY",
  "RUNWAY_API_KEY",
  "PIKA_API_KEY",
  "ARK_API_KEY",
  "VOLC_TTS_ACCESS_TOKEN",
]);

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "请求失败");
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

async function runAction(action, fallbackMessage = "操作失败") {
  try {
    return await action();
  } catch (error) {
    console.error(error);
    const message = error?.message || fallbackMessage;
    alert(message);
    el.pipelineStatus.textContent = fallbackMessage;
    return null;
  }
}

function escapeHtml(text = "") {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function selectedProject() {
  return state.projects.find((item) => item.id === state.selectedProjectId) || null;
}

function getSceneReferenceScale() {
  return Number(el.sceneReferenceScale?.value || 0.3);
}

function updateSceneReferenceScaleLabel() {
  if (!el.sceneReferenceScaleValue || !el.sceneReferenceScale) return;
  el.sceneReferenceScaleValue.textContent = getSceneReferenceScale().toFixed(2);
}

function setApiConfigStatus(text) {
  if (el.apiConfigStatus) {
    el.apiConfigStatus.textContent = text;
  }
}

function applyApiConfigToForm(data) {
  state.apiConfig = data;
  const values = data?.values || {};
  const configured = data?.configured || {};

  API_FIELD_MAP.forEach(([field, elementKey]) => {
    const input = el[elementKey];
    if (!input) return;

    if (SECRET_API_FIELDS.has(field)) {
      input.value = "";
      input.placeholder = configured[field]
        ? `${field} 已配置，留空则保持不变`
        : `${field}，留空表示暂不配置`;
      return;
    }

    input.value = values[field] || "";
  });

  const configuredSecrets = Object.entries(configured)
    .filter(([, value]) => Boolean(value))
    .length;
  setApiConfigStatus(`已读取 · ${configuredSecrets} 个密钥已配置`);
}

function collectApiConfigPayload() {
  const settings = {};

  API_FIELD_MAP.forEach(([field, elementKey]) => {
    const input = el[elementKey];
    if (!input) return;

    const value = input.value.trim();
    if (SECRET_API_FIELDS.has(field)) {
      settings[field] = value;
    } else {
      settings[field] = value;
    }
  });

  return { settings };
}

async function loadApiConfig() {
  setApiConfigStatus("正在读取...");
  const result = await runAction(() => request("/api/settings/api"), "读取 API 配置失败");
  if (!result) return;
  applyApiConfigToForm(result);
}

async function saveApiConfig() {
  setApiConfigStatus("正在保存...");
  const payload = collectApiConfigPayload();
  const result = await runAction(() => request("/api/settings/api", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }), "保存 API 配置失败");
  if (!result) return;

  applyApiConfigToForm(result);
  setApiConfigStatus("已保存到本机");
}

function openLightbox(src, alt = "预览图片") {
  if (!src || !el.lightbox || !el.lightboxImage) return;
  el.lightboxImage.src = src;
  el.lightboxImage.alt = alt;
  el.lightbox.classList.remove("hidden");
  el.lightbox.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeLightbox() {
  if (!el.lightbox || !el.lightboxImage) return;
  el.lightbox.classList.add("hidden");
  el.lightbox.setAttribute("aria-hidden", "true");
  el.lightboxImage.src = "";
  document.body.style.overflow = "";
}

function bindPreviewImages() {
  document.querySelectorAll("[data-preview-src]").forEach((node) => {
    node.addEventListener("click", () => {
      openLightbox(node.dataset.previewSrc, node.dataset.previewAlt || "预览图片");
    });
  });
}

function renderProjects() {
  if (!state.projects.length) {
    el.projectsList.innerHTML = `<div class="empty-state">还没有项目，先新建一个。</div>`;
    return;
  }

  el.projectsList.innerHTML = state.projects.map((project) => `
    <div class="project-item ${project.id === state.selectedProjectId ? "active" : ""}" data-project-id="${project.id}">
      <div class="project-item-head">
        <strong>${escapeHtml(project.name)}</strong>
        <button
          type="button"
          class="project-delete-btn"
          data-project-delete="${project.id}"
          aria-label="删除项目 ${escapeHtml(project.name)}"
          title="删除项目"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm-2 6h2v8H7V9Zm4 0h2v8h-2V9Zm4 0h2v8h-2V9ZM6 7h12l-1 13a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L6 7Z" />
          </svg>
        </button>
      </div>
      <p>${escapeHtml((project.plot || "还没有剧情").slice(0, 56))}</p>
      <p>${project.counts.scenes} 个分镜 · ${project.counts.characters} 个角色 · ${project.counts.images} 张分镜图</p>
    </div>
  `).join("");

  document.querySelectorAll(".project-item").forEach((node) => {
    node.addEventListener("click", () => selectProject(node.dataset.projectId));
  });

  document.querySelectorAll("[data-project-delete]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      await deleteProject(button.dataset.projectDelete);
    });
  });
}

function renderStoryboardEditor(storyboard) {
  if (!storyboard) {
    el.storyboardTitle.value = "";
    el.storyboardSummary.value = "";
    el.storyboardDuration.value = "";
    el.scenesEditor.className = "scene-list empty-state";
    el.scenesEditor.innerHTML = "还没有 scene，可以先生成或导入分镜稿。";
    return;
  }

  el.storyboardTitle.value = storyboard.title || "";
  el.storyboardSummary.value = storyboard.summary || "";
  el.storyboardDuration.value = storyboard.total_duration || "";

  el.scenesEditor.className = "scene-list";
  el.scenesEditor.innerHTML = storyboard.scenes.map((scene, index) => `
    <div class="scene-card" data-scene-index="${index}">
      <div class="scene-card-head">
        <h3>场景 ${scene.scene_number}</h3>
        <span class="status-pill">${scene.duration || 0}s</span>
      </div>
      <textarea data-field="description" rows="2" placeholder="场景描述">${escapeHtml(scene.description || "")}</textarea>
      <textarea data-field="prompt" rows="4" placeholder="视频/分镜 prompt">${escapeHtml(scene.prompt || "")}</textarea>
      <div class="grid two compact">
        <input data-field="camera_movement" value="${escapeHtml(scene.camera_movement || "")}" placeholder="镜头运动" />
        <input data-field="mood" value="${escapeHtml(scene.mood || "")}" placeholder="氛围" />
      </div>
      <div class="grid two compact">
        <input data-field="duration" type="number" step="0.1" value="${scene.duration || 5}" placeholder="时长" />
        <input data-field="character_ids" value="${escapeHtml((scene.character_ids || []).join(", "))}" placeholder="角色ID，用逗号分隔" />
      </div>
      <textarea data-field="character_directions" rows="2" placeholder="角色分配说明，例如：1 在左侧挥拳，2 在右侧防守">${escapeHtml(scene.character_directions || "")}</textarea>
      <div class="inline-actions">
        <button type="button" class="ghost" data-scene-upload-trigger="${scene.scene_number}">上传分镜图</button>
        <input type="file" hidden data-scene-upload="${scene.scene_number}" accept="image/*" />
        <button type="button" class="ghost" data-scene-delete="${index}">删除场景</button>
      </div>
    </div>
  `).join("");

  document.querySelectorAll("[data-scene-upload-trigger]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.querySelector(`[data-scene-upload="${button.dataset.sceneUploadTrigger}"]`);
      input?.click();
    });
  });

  document.querySelectorAll("[data-scene-upload]").forEach((input) => {
    input.addEventListener("change", async (event) => {
      const file = event.target.files[0];
      await uploadSceneImage(Number(event.target.dataset.sceneUpload), file);
      event.target.value = "";
    });
  });

  document.querySelectorAll("[data-scene-delete]").forEach((button) => {
    button.addEventListener("click", () => removeScene(Number(button.dataset.sceneDelete)));
  });
}

function renderCharacters(project) {
  const storyboard = project?.storyboard;
  const storyboardCharacters = storyboard?.characters || [];
  const manualCharacters = project?.manual_characters || [];
  const merged = new Map();
  [...manualCharacters, ...storyboardCharacters].forEach((character) => {
    merged.set(character.id, character);
  });
  const characters = [...merged.values()];
  el.manualCharactersStatus.textContent = `${manualCharacters.length} 个手动角色`;
  el.charactersStatus.textContent = `${characters.length} 个角色`;

  if (!characters.length) {
    el.charactersGrid.className = "asset-grid empty-state";
    el.charactersGrid.innerHTML = "角色会显示在这里。你也可以上传自己的角色图替换。";
    return;
  }

  el.charactersGrid.className = "asset-grid";
  el.charactersGrid.innerHTML = characters.map((character) => `
    <div class="asset-card">
      ${character.image_url ? `<img src="${character.image_url}" alt="${escapeHtml(character.name)}" data-preview-src="${character.image_url}" data-preview-alt="${escapeHtml(character.name)}" />` : `<div class="empty-state">暂无角色图</div>`}
      <input data-character-name="${character.id}" value="${escapeHtml(character.name || "")}" placeholder="角色名称" />
      <p class="muted small">内部编号 ${escapeHtml(character.id || "")}</p>
      <textarea data-character-description="${character.id}" rows="5" placeholder="角色描述">${escapeHtml(character.description || "")}</textarea>
      <div class="inline-actions">
        <button type="button" class="ghost" data-character-upload-trigger="${character.id}">上传角色图</button>
        <button type="button" class="ghost" data-character-assist="${character.id}">AI 辅助</button>
        <button type="button" class="ghost" data-character-save="${character.id}">保存角色</button>
        <button type="button" class="ghost danger" data-character-delete="${character.id}">删除角色</button>
        <input type="file" hidden data-character-upload="${character.id}" accept="image/*" />
      </div>
    </div>
  `).join("");

  document.querySelectorAll("[data-character-upload-trigger]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.querySelector(`[data-character-upload="${button.dataset.characterUploadTrigger}"]`);
      input?.click();
    });
  });

  document.querySelectorAll("[data-character-upload]").forEach((input) => {
    input.addEventListener("change", async (event) => {
      const file = event.target.files[0];
      await uploadCharacterImage(event.target.dataset.characterUpload, file);
      event.target.value = "";
    });
  });

  document.querySelectorAll("[data-character-assist]").forEach((button) => {
    button.addEventListener("click", async () => {
      await assistCharacter(button.dataset.characterAssist);
    });
  });

  document.querySelectorAll("[data-character-save]").forEach((button) => {
    button.addEventListener("click", async () => {
      await saveCharacter(button.dataset.characterSave);
    });
  });

  document.querySelectorAll("[data-character-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteCharacter(button.dataset.characterDelete);
    });
  });

  bindPreviewImages();
}

function renderSceneImages(project) {
  const storyboard = project?.storyboard;
  const scenes = storyboard?.scenes || [];
  const imageCount = scenes.filter((scene) => scene.scene_image_path).length;
  el.imagesStatus.textContent = `${imageCount} 张分镜图`;

  if (!scenes.length) {
    el.sceneImagesGrid.className = "asset-grid empty-state";
    el.sceneImagesGrid.innerHTML = "分镜图会显示在这里。";
    return;
  }

  el.sceneImagesGrid.className = "asset-grid";
  el.sceneImagesGrid.innerHTML = scenes.map((scene) => `
    <div class="asset-card scene">
      ${scene.scene_image_url ? `<img src="${scene.scene_image_url}" alt="scene ${scene.scene_number}" data-preview-src="${scene.scene_image_url}" data-preview-alt="场景 ${scene.scene_number}" />` : `<div class="empty-state">暂无分镜图</div>`}
      <h3>场景 ${scene.scene_number}</h3>
      <p class="muted small">${escapeHtml(scene.description || "")}</p>
      <div class="inline-actions">
        <button type="button" class="ghost danger" data-scene-image-delete="${scene.scene_number}">删除分镜图</button>
      </div>
    </div>
  `).join("");

  document.querySelectorAll("[data-scene-image-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteSceneImage(Number(button.dataset.sceneImageDelete));
    });
  });

  bindPreviewImages();
}

function collectStoryboardFromEditor() {
  const project = selectedProject();
  if (!project?.storyboard) return null;

  const storyboard = structuredClone(project.storyboard);
  storyboard.title = el.storyboardTitle.value.trim();
  storyboard.summary = el.storyboardSummary.value.trim();
  storyboard.total_duration = Number(el.storyboardDuration.value || storyboard.total_duration || 0);

  document.querySelectorAll(".scene-card").forEach((card, index) => {
    const scene = storyboard.scenes[index];
    scene.description = card.querySelector('[data-field="description"]').value.trim();
    scene.prompt = card.querySelector('[data-field="prompt"]').value.trim();
    scene.camera_movement = card.querySelector('[data-field="camera_movement"]').value.trim() || null;
    scene.mood = card.querySelector('[data-field="mood"]').value.trim() || null;
    scene.duration = Number(card.querySelector('[data-field="duration"]').value || scene.duration || 5);
    scene.character_ids = card.querySelector('[data-field="character_ids"]').value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    scene.character_directions = card.querySelector('[data-field="character_directions"]').value.trim() || null;
  });

  return storyboard;
}

async function refreshProjects(selectId = state.selectedProjectId) {
  state.projects = await request("/api/projects");
  renderProjects();
  if (selectId && state.projects.some((item) => item.id === selectId)) {
    await selectProject(selectId, false);
  } else if (state.projects[0]) {
    await selectProject(state.projects[0].id, false);
  } else {
    renderProjectDetail(null);
  }
}

function renderProjectDetail(project) {
  if (!project) {
    state.currentStoryboard = null;
    el.projectTitle.textContent = "先从左边创建或选择一个项目";
    el.projectMeta.textContent = "第一版前端重点支持：剧情输入、分镜编辑、角色图和分镜图。";
    el.plotInput.value = "";
    el.plotStatus.textContent = "未选择项目";
    el.pipelineStatus.textContent = "待开始";
    el.storyboardStatus.textContent = "暂无分镜稿";
    el.downloadStoryboardLink.href = "#";
    el.renameProjectBtn.disabled = true;
    renderStoryboardEditor(null);
    renderCharacters(null);
    renderSceneImages(null);
    return;
  }

  state.currentStoryboard = project.storyboard;
  el.projectTitle.textContent = project.name;
  el.projectMeta.textContent = project.plot || "你可以输入剧情让 AI 自动拆分，也可以导入你自己的分镜稿和角色图。";
  el.plotInput.value = project.plot || "";
  el.plotStatus.textContent = project.plot ? "剧情已填写" : "等待输入剧情";
  el.pipelineStatus.textContent = `${project.counts.scenes} 个分镜 / ${project.counts.characters} 个角色 / ${project.counts.images} 张分镜图`;
  el.storyboardStatus.textContent = project.storyboard ? "已加载分镜稿" : "暂无分镜稿";
  el.downloadStoryboardLink.href = `/api/projects/${project.id}/storyboard/export`;
  el.renameProjectBtn.disabled = false;
  el.deleteStoryboardBtn.disabled = !project.storyboard;
  renderStoryboardEditor(project.storyboard);
  renderCharacters(project);
  renderSceneImages(project);
}

async function selectProject(projectId, fetchSingle = true) {
  state.selectedProjectId = projectId;
  if (fetchSingle) {
    const project = await request(`/api/projects/${projectId}`);
    state.projects = state.projects.map((item) => item.id === projectId ? project : item);
  }
  renderProjects();
  renderProjectDetail(selectedProject());
}

async function createProject(event) {
  event.preventDefault();
  const name = document.getElementById("project-name").value.trim();
  const plot = document.getElementById("project-plot").value.trim();
  if (!name) return;

  const project = await runAction(() => request("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, plot }),
  }), "创建项目失败");
  if (!project) return;

  document.getElementById("create-project-form").reset();
  state.projects.unshift(project);
  await selectProject(project.id, false);
}

async function renameProject() {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");

  const nextName = window.prompt("请输入新的项目名称", project.name);
  if (!nextName) return;

  const trimmedName = nextName.trim();
  if (!trimmedName || trimmedName === project.name) return;

  el.pipelineStatus.textContent = `正在重命名项目：${project.name}`;
  const result = await runAction(() => request(`/api/projects/${project.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: trimmedName }),
  }), "重命名项目失败");
  if (!result) return;

  state.selectedProjectId = result.id;
  await refreshProjects(result.id);
}

async function addManualCharacter() {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");
  const name = el.manualCharacterName.value.trim();
  const description = el.manualCharacterDescription.value.trim();
  if (!name) return alert("请先填写角色名");

  el.pipelineStatus.textContent = "正在新增手动角色...";
  const result = await runAction(() => request(`/api/projects/${project.id}/characters/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  }), "新增手动角色失败");
  if (!result) return;

  el.manualCharacterName.value = "";
  el.manualCharacterDescription.value = "";
  await refreshProjects(project.id);
}

function getCharacterEditorValues(characterId) {
  const nameInput = document.querySelector(`[data-character-name="${characterId}"]`);
  const descriptionInput = document.querySelector(`[data-character-description="${characterId}"]`);
  return {
    name: nameInput?.value.trim() || "",
    description: descriptionInput?.value.trim() || "",
  };
}

async function assistCharacter(characterId) {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");
  const { name, description } = getCharacterEditorValues(characterId);
  if (!name) return alert("请先填写角色名称");

  el.pipelineStatus.textContent = `AI 正在辅助优化角色：${name}`;
  const result = await runAction(() => request(`/api/projects/${project.id}/characters/assist-description`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  }), "AI 辅助角色描述失败");
  if (!result) return;

  const nameInput = document.querySelector(`[data-character-name="${characterId}"]`);
  const descriptionInput = document.querySelector(`[data-character-description="${characterId}"]`);
  if (nameInput && result.name) nameInput.value = result.name;
  if (descriptionInput && result.description) descriptionInput.value = result.description;
  el.pipelineStatus.textContent = "AI 辅助完成，你可以继续修改后再保存";
}

async function saveCharacter(characterId) {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");
  const { name, description } = getCharacterEditorValues(characterId);
  if (!name) return alert("请先填写角色名称");

  el.pipelineStatus.textContent = `正在保存角色：${name}`;
  const result = await runAction(() => request(`/api/projects/${project.id}/characters/${characterId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: characterId, name, description }),
  }), "保存角色失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function deleteCharacter(characterId) {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");
  const { name } = getCharacterEditorValues(characterId);
  const label = name || characterId;
  if (!window.confirm(`确认删除角色“${label}”吗？对应角色图也会一起删除。`)) return;

  el.pipelineStatus.textContent = `正在删除角色：${label}`;
  const result = await runAction(() => request(`/api/projects/${project.id}/characters/${characterId}`, {
    method: "DELETE",
  }), "删除角色失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function generateStoryboard() {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");
  const plot = el.plotInput.value.trim();
  if (!plot) return alert("请先输入剧情");

  el.pipelineStatus.textContent = "正在生成分镜稿...";
  const result = await runAction(() => request(`/api/projects/${project.id}/storyboard/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plot, extract_characters: true }),
  }), "生成分镜稿失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function createManualStoryboard() {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");
  const plot = el.plotInput.value.trim();

  el.pipelineStatus.textContent = "正在创建空白分镜稿...";
  const result = await runAction(() => request(`/api/projects/${project.id}/storyboard/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: plot ? `${plot.slice(0, 18)}...` : project.name,
      summary: plot || "手动创建的分镜稿",
      plot,
    }),
  }), "创建空白分镜稿失败");
  if (!result) return;
  await refreshProjects(project.id);
}

function addScene() {
  const project = selectedProject();
  if (!project?.storyboard) return alert("请先生成、导入或手动创建分镜稿");
  const storyboard = structuredClone(project.storyboard);
  const nextNumber = (storyboard.scenes.at(-1)?.scene_number || 0) + 1;
  storyboard.scenes.push({
    scene_number: nextNumber,
    description: "请填写这一镜的中文描述",
    prompt: "please write your visual prompt here",
    duration: 5,
    camera_movement: "",
    mood: "",
    character_ids: [],
    character_directions: "",
    dialogues: [],
    narration: null,
    audio_configs: [],
    reference_image: null,
    scene_image_path: null,
  });
  storyboard.total_duration = storyboard.scenes.reduce((sum, scene) => sum + Number(scene.duration || 0), 0);
  project.storyboard = storyboard;
  renderProjectDetail(project);
}

function removeScene(index) {
  const project = selectedProject();
  if (!project?.storyboard) return;
  const storyboard = structuredClone(project.storyboard);
  storyboard.scenes.splice(index, 1);
  storyboard.scenes = storyboard.scenes.map((scene, idx) => ({
    ...scene,
    scene_number: idx + 1,
  }));
  storyboard.total_duration = storyboard.scenes.reduce((sum, scene) => sum + Number(scene.duration || 0), 0);
  project.storyboard = storyboard;
  renderProjectDetail(project);
}

async function saveStoryboard() {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");
  const storyboard = collectStoryboardFromEditor();
  if (!storyboard) return alert("当前没有分镜稿可保存");

  const result = await runAction(() => request(`/api/projects/${project.id}/storyboard`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ storyboard }),
  }), "保存分镜稿失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function deleteStoryboard() {
  const project = selectedProject();
  if (!project?.storyboard) return alert("当前没有分镜稿可删除");
  if (!window.confirm("确认删除整份分镜稿吗？当前分镜图也会一起清掉。")) return;

  el.pipelineStatus.textContent = "正在删除分镜稿...";
  const result = await runAction(() => request(`/api/projects/${project.id}/storyboard`, {
    method: "DELETE",
  }), "删除分镜稿失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function generateCharacters() {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");
  const formData = new FormData();
  formData.set("regenerate", "true");
  el.pipelineStatus.textContent = "正在生成角色图...";
  const result = await runAction(() => request(`/api/projects/${project.id}/characters/generate`, {
    method: "POST",
    body: formData,
  }), "生成角色图失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function generateSceneImages() {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");
  const formData = new FormData();
  formData.set("regenerate", "true");
  formData.set("reference_scale", String(getSceneReferenceScale()));
  el.pipelineStatus.textContent = "正在生成分镜图...";
  const result = await runAction(() => request(`/api/projects/${project.id}/scene-images/generate`, {
    method: "POST",
    body: formData,
  }), "生成分镜图失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function uploadCharacterImage(characterId, file) {
  const project = selectedProject();
  if (!project || !file) return;
  const formData = new FormData();
  formData.set("file", file);
  el.pipelineStatus.textContent = `正在上传角色图：${file.name}`;
  const result = await runAction(() => request(`/api/projects/${project.id}/characters/${characterId}/upload`, {
    method: "POST",
    body: formData,
  }), "上传角色图失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function uploadSceneImage(sceneNumber, file) {
  const project = selectedProject();
  if (!project || !file) return;
  const formData = new FormData();
  formData.set("file", file);
  el.pipelineStatus.textContent = `正在上传分镜图：${file.name}`;
  const result = await runAction(() => request(`/api/projects/${project.id}/scene-images/${sceneNumber}/upload`, {
    method: "POST",
    body: formData,
  }), "上传分镜图失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function deleteSceneImage(sceneNumber) {
  const project = selectedProject();
  if (!project) return alert("请先选择项目");
  if (!window.confirm(`确认删除场景 ${sceneNumber} 的分镜图吗？`)) return;

  el.pipelineStatus.textContent = `正在删除场景 ${sceneNumber} 的分镜图...`;
  const result = await runAction(() => request(`/api/projects/${project.id}/scene-images/${sceneNumber}`, {
    method: "DELETE",
  }), "删除分镜图失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function importStoryboard(file) {
  const project = selectedProject();
  if (!project || !file) return;
  const formData = new FormData();
  formData.set("file", file);
  el.pipelineStatus.textContent = `正在导入分镜：${file.name}`;
  const result = await runAction(() => request(`/api/projects/${project.id}/storyboard/import`, {
    method: "POST",
    body: formData,
  }), "导入分镜稿失败");
  if (!result) return;
  await refreshProjects(project.id);
}

async function deleteProject(projectId) {
  const project = state.projects.find((item) => item.id === projectId);
  if (!project) return alert("项目不存在或已被删除");
  if (!window.confirm(`确认删除项目“${project.name}”吗？项目下的角色、分镜图、视频等文件都会一起删除。`)) return;

  el.pipelineStatus.textContent = `正在删除项目：${project.name}`;
  const result = await runAction(() => request(`/api/projects/${project.id}`, {
    method: "DELETE",
  }), "删除项目失败");
  if (!result) return;

  state.selectedProjectId = null;
  await refreshProjects();
}

document.getElementById("create-project-form").addEventListener("submit", createProject);
document.getElementById("refresh-projects").addEventListener("click", () => refreshProjects());
document.getElementById("add-manual-character-btn").addEventListener("click", addManualCharacter);
document.getElementById("generate-storyboard-btn").addEventListener("click", generateStoryboard);
document.getElementById("create-manual-storyboard-btn").addEventListener("click", createManualStoryboard);
document.getElementById("save-storyboard-btn").addEventListener("click", saveStoryboard);
document.getElementById("generate-characters-btn").addEventListener("click", generateCharacters);
document.getElementById("generate-scene-images-btn").addEventListener("click", generateSceneImages);
el.addSceneBtn.addEventListener("click", addScene);
el.deleteStoryboardBtn.addEventListener("click", deleteStoryboard);
el.renameProjectBtn.addEventListener("click", renameProject);
el.sceneReferenceScale.addEventListener("input", updateSceneReferenceScaleLabel);
el.saveApiConfigBtn.addEventListener("click", saveApiConfig);
el.reloadApiConfigBtn.addEventListener("click", loadApiConfig);
el.lightboxCloseBtn.addEventListener("click", closeLightbox);
el.lightbox.addEventListener("click", (event) => {
  if (event.target.dataset.lightboxClose === "true") {
    closeLightbox();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !el.lightbox.classList.contains("hidden")) {
    closeLightbox();
  }
});
document.getElementById("import-storyboard-btn").addEventListener("click", () => el.storyboardFileInput.click());
el.storyboardFileInput.addEventListener("change", (event) => importStoryboard(event.target.files[0]));

el.deleteStoryboardBtn.disabled = true;
el.renameProjectBtn.disabled = true;
updateSceneReferenceScaleLabel();

loadApiConfig();
refreshProjects();
