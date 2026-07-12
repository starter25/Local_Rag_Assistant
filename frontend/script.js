const state = {
  mode: "fast",
  useRag: true,
  answerMode: "strict_rag",
  projectId: "default",
  projects: [],
  projectLoading: false,
  model: "",
  defaultModel: "",
  models: [],
  recommendedModels: [],
  modelPulls: {},
  documentModalOpen: false,
  documentFilter: "all",
  projectPanelOpen: true,
  operations: {
    answer: false,
    document: false,
    modelInstall: false,
  },
  files: [],
  chats: [
    {
      id: Date.now(),
      title: "현재 채팅",
      messages: [],
    },
  ],
  currentChatId: null,
};

state.chats = [];

// DOM 참조는 앱 시작 시 한 번만 잡고 이후 렌더 함수에서 재사용합니다.
const messageList = document.getElementById("messageList");
const questionInput = document.getElementById("questionInput");
const sendBtn = document.getElementById("sendBtn");

const modeButtons = document.querySelectorAll(".mode-btn[data-mode]");
const answerModeButtons = document.querySelectorAll(".answer-mode-btn");
const searchModeSelect = document.getElementById("searchModeSelect");
const answerModeSelect = document.getElementById("answerModeSelect");
const documentModeNotice = document.getElementById("documentModeNotice");
const modelManageBtn = document.getElementById("modelManageBtn");
const modelModal = document.getElementById("modelModal");
const modelModalCloseBtn = document.getElementById("modelModalCloseBtn");
const modelSelect = document.getElementById("modelSelect");
const modelStatusText = document.getElementById("modelStatusText");
const modelPanelSummary = document.getElementById("modelPanelSummary");
const modelModalSummary = document.getElementById("modelModalSummary");
const recommendedModelList = document.getElementById("recommendedModelList");
const currentProjectText = document.getElementById("currentProjectText");
const currentModelText = document.getElementById("currentModelText");
const currentDocumentCountText = document.getElementById("currentDocumentCountText");
const projectPanelToggle = document.getElementById("projectPanelToggle");
const projectPanelToggleLabel = document.getElementById("projectPanelToggleLabel");
const projectPanelBody = document.getElementById("projectPanelBody");
const projectSelect = document.getElementById("projectSelect");
const projectCreateOpenBtn = document.getElementById("projectCreateOpenBtn");
const projectModal = document.getElementById("projectModal");
const projectModalCloseBtn = document.getElementById("projectModalCloseBtn");
const projectCreateCancelBtn = document.getElementById("projectCreateCancelBtn");
const projectNameInput = document.getElementById("projectNameInput");
const projectCreateBtn = document.getElementById("projectCreateBtn");
const projectStatusText = document.getElementById("projectStatusText");
const documentManageBtn = document.getElementById("documentManageBtn");
const documentModal = document.getElementById("documentModal");
const documentModalCloseBtn = document.getElementById("documentModalCloseBtn");
const documentPanelSummary = document.getElementById("documentPanelSummary");
const documentModalSummary = document.getElementById("documentModalSummary");
const documentFilterButtons = document.querySelectorAll(".document-filter-btn");
const toast = document.getElementById("toast");
const deleteConfirmModal = document.getElementById("deleteConfirmModal");
const deleteConfirmTitle = document.getElementById("deleteConfirmTitle");
const deleteConfirmMessage = document.getElementById("deleteConfirmMessage");
const deleteConfirmTarget = document.getElementById("deleteConfirmTarget");
const deleteConfirmCloseBtn = document.getElementById("deleteConfirmCloseBtn");
const deleteConfirmCancelBtn = document.getElementById("deleteConfirmCancelBtn");
const deleteConfirmSubmitBtn = document.getElementById("deleteConfirmSubmitBtn");
const guideOpenBtn = document.getElementById("guideOpenBtn");
const guideModal = document.getElementById("guideModal");
const guideCloseBtn = document.getElementById("guideCloseBtn");

const uploadModal = document.getElementById("uploadModal");
const uploadOpenBtn = document.getElementById("uploadOpenBtn");
const uploadCloseBtn = document.getElementById("uploadCloseBtn");
const uploadCancelBtn = document.getElementById("uploadCancelBtn");

const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const fileSelectBtn = document.getElementById("fileSelectBtn");
const uploadSubmitBtn = document.getElementById("uploadSubmitBtn");

const selectedFileList = document.getElementById("selectedFileList");
const fileList = document.getElementById("fileList");
const newChatBtn = document.getElementById("newChatBtn");
const chatList = document.getElementById("chatList");
const syncBtn = document.getElementById("syncBtn");

let pendingFiles = [];
let appInitialized = false;
let appPrepared = false;
let pendingDeleteConfirmResolve = null;

const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "starting"]);

// API 오류를 HTTP status와 사용자용 메시지를 함께 가진 객체로 다룹니다.
class ApiError extends Error {
  constructor(message, status = 0, detail = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail || message;
  }
}

// 백엔드에서 온 기술적인 오류 문구를 화면에 보여줄 문장으로 변환합니다.
function mapApiErrorMessage(detail, status = 0) {
  const raw = String(detail || "").trim();

  const knownMessages = {
    "Another answer job is already running.": "이미 답변을 생성 중이에요. 완료된 뒤 다시 질문해주세요.",
    "Another document job is already running.": "문서 처리 작업이 진행 중이에요. 완료 후 다시 시도해주세요.",
    "Another model install is already running.": "모델 설치가 이미 진행 중이에요. 설치가 끝난 뒤 다른 모델을 설치해주세요.",
    "Invalid Ollama model name.": "설치할 수 없는 모델 이름이에요.",
  };

  if (knownMessages[raw]) {
    return knownMessages[raw];
  }

  if (raw.includes("Ollama is not running") || raw.includes("Ollama")) {
    return "Ollama에 연결하지 못했어요. Ollama가 실행 중인지 확인해주세요.";
  }

  if (status === 409) {
    return raw || "이미 다른 작업이 진행 중이에요. 잠시 후 다시 시도해주세요.";
  }

  if (status === 400) {
    return raw || "입력값을 확인해주세요.";
  }

  if (status >= 500) {
    return raw || "앱 서버에서 오류가 발생했어요.";
  }

  return raw || "요청을 처리하지 못했어요.";
}

// fetch 응답 실패를 공통 ApiError로 변환합니다.
async function apiErrorFromResponse(response, fallbackMessage) {
  const errorData = await response.json().catch(() => null);
  const detail = errorData?.detail || fallbackMessage;

  return new ApiError(
    mapApiErrorMessage(detail, response.status),
    response.status,
    detail
  );
}

// 네트워크 오류, ApiError, 일반 Error를 모두 사용자용 문구로 통일합니다.
function getFriendlyErrorMessage(error, fallbackMessage = "요청을 처리하지 못했어요.") {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof TypeError) {
    return "앱 서버에 연결하지 못했어요. 서버가 실행 중인지 확인해주세요.";
  }

  return mapApiErrorMessage(error?.message || fallbackMessage);
}

// 현재 job 상태가 아직 진행 중인지 판단합니다.
function isActiveJobStatus(status) {
  return ACTIVE_JOB_STATUSES.has(String(status || "").toLowerCase());
}

// 설치 중인 모델 job이 있으면 다른 설치 버튼을 잠그기 위해 사용합니다.
function hasActiveModelInstall() {
  return Object.values(state.modelPulls).some((job) => isActiveJobStatus(job?.status));
}

// 웹 브라우저 실행과 Tauri/파일 실행의 API base URL을 다르게 잡습니다.
function isWebOrigin() {
  return window.location.protocol === "http:" || window.location.protocol === "https:";
}

function isDesktopShell() {
  return !isWebOrigin();
}

// 현재 실행 환경에서 FastAPI 백엔드에 접근할 base URL을 결정합니다.
function getApiBaseUrl() {
  if (window.__LOCAL_RAG_API_URL__) {
    return window.__LOCAL_RAG_API_URL__;
  }

  if (isWebOrigin()) {
    return window.location.origin;
  }

  return "http://localhost:8000";
}

// 헤더의 앱 연결 상태 문구를 갱신합니다.
function setStatusText(text) {
  const statusText = document.getElementById("statusText");

  if (statusText) {
    statusText.textContent = text;
  }
}

let toastTimer = null;

function showToast(message, type = "info") {
  if (!toast) {
    console.info(message);
    return;
  }

  window.clearTimeout(toastTimer);
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.classList.remove("hidden");

  requestAnimationFrame(() => {
    toast.classList.add("show");
  });

  toastTimer = window.setTimeout(() => {
    toast.classList.remove("show");

    window.setTimeout(() => {
      toast.classList.add("hidden");
    }, 180);
  }, 2600);
}

function closeDeleteConfirmModal(confirmed = false) {
  deleteConfirmModal?.classList.add("hidden");

  if (pendingDeleteConfirmResolve) {
    pendingDeleteConfirmResolve(Boolean(confirmed));
    pendingDeleteConfirmResolve = null;
  }
}

function confirmDeleteAction({ title, message, target, submitLabel = "삭제" }) {
  if (!deleteConfirmModal) {
    return Promise.resolve(window.confirm(`${title}\n\n${target || message || ""}`));
  }

  if (pendingDeleteConfirmResolve) {
    closeDeleteConfirmModal(false);
  }

  if (deleteConfirmTitle) {
    deleteConfirmTitle.textContent = title || "삭제할까요?";
  }

  if (deleteConfirmMessage) {
    deleteConfirmMessage.textContent = message || "선택한 항목이 삭제됩니다.";
  }

  if (deleteConfirmTarget) {
    deleteConfirmTarget.textContent = target || "";
    deleteConfirmTarget.hidden = !target;
  }

  if (deleteConfirmSubmitBtn) {
    deleteConfirmSubmitBtn.textContent = submitLabel;
  }

  deleteConfirmModal.classList.remove("hidden");

  return new Promise((resolve) => {
    pendingDeleteConfirmResolve = resolve;
  });
}

// 답변/문서/모델 작업 중복 실행을 막기 위해 버튼 disabled 상태를 한 번에 맞춥니다.
function setProjectStatusText(text) {
  if (projectStatusText) {
    projectStatusText.textContent = text;
  }
}

function updateCurrentProjectText() {
  if (currentProjectText) {
    currentProjectText.textContent = getProjectDisplayName(getCurrentProject());
  }
}

function getSavedProjectPanelOpen() {
  try {
    return localStorage.getItem("localRag.projectPanelOpen") !== "false";
  } catch {
    return true;
  }
}

function saveProjectPanelOpen(open) {
  try {
    localStorage.setItem("localRag.projectPanelOpen", String(Boolean(open)));
  } catch {
    // localStorage can be unavailable in some embedded WebView contexts.
  }
}

function setProjectPanelOpen(open, persist = true) {
  state.projectPanelOpen = Boolean(open);

  if (projectPanelBody) {
    projectPanelBody.hidden = !state.projectPanelOpen;
  }

  if (projectPanelToggle) {
    projectPanelToggle.setAttribute("aria-expanded", String(state.projectPanelOpen));
  }

  if (projectPanelToggleLabel) {
    projectPanelToggleLabel.textContent = state.projectPanelOpen ? "접기" : "펼치기";
  }

  if (persist) {
    saveProjectPanelOpen(state.projectPanelOpen);
  }
}

function openProjectModal() {
  if (state.operations.answer || state.operations.document || state.projectLoading) {
    showToast("작업이 끝난 뒤 새 프로젝트를 만들 수 있어요.", "warning");
    return;
  }

  projectModal?.classList.remove("hidden");
  window.setTimeout(() => projectNameInput?.focus(), 0);
}

function closeProjectModal() {
  projectModal?.classList.add("hidden");

  if (projectNameInput) {
    projectNameInput.value = "";
  }
}

function getDocumentSyncStorageKey(projectId = state.projectId) {
  return `localRag.lastDocumentSyncAt.${projectId || "default"}`;
}

function getLastDocumentSyncAt(projectId = state.projectId) {
  try {
    const value = localStorage.getItem(getDocumentSyncStorageKey(projectId));
    const timestamp = Number(value || 0);

    return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : null;
  } catch {
    return null;
  }
}

function saveLastDocumentSyncAt(timestamp = Date.now(), projectId = state.projectId) {
  try {
    localStorage.setItem(getDocumentSyncStorageKey(projectId), String(timestamp));
  } catch {
    // localStorage can be unavailable in some embedded WebView contexts.
  }
}

function formatLastDocumentSyncText(projectId = state.projectId) {
  const timestamp = getLastDocumentSyncAt(projectId);

  if (!timestamp) {
    return "동기화 기록 없음";
  }

  const formatter = new Intl.DateTimeFormat("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return `마지막 동기화: ${formatter.format(new Date(timestamp))}`;
}

function getDocumentPanelSummaryText() {
  if (state.projectLoading) {
    return `문서를 불러오는 중... · ${formatLastDocumentSyncText()}`;
  }

  if (state.operations.document) {
    return `문서 처리 중... · ${formatLastDocumentSyncText()}`;
  }

  const count = state.files.length;
  const syncText = formatLastDocumentSyncText();

  if (count === 0) {
    return `문서 0개 · ${syncText}`;
  }

  const needsReview = state.files.filter((doc) => {
    const status = doc.status || "indexed";
    return status !== "indexed";
  }).length;

  if (needsReview > 0) {
    return `문서 ${count}개 · 확인 필요 ${needsReview}개 · ${syncText}`;
  }

  return `문서 ${count}개 · ${syncText}`;
}

function updateDocumentPanelSummary() {
  if (documentPanelSummary) {
    documentPanelSummary.textContent = getDocumentPanelSummaryText();
  }

  if (documentModalSummary) {
    documentModalSummary.textContent = getDocumentPanelSummaryText();
  }

  if (currentDocumentCountText) {
    if (state.projectLoading) {
      currentDocumentCountText.textContent = "불러오는 중";
    } else if (state.operations.document) {
      currentDocumentCountText.textContent = "처리 중";
    } else {
      currentDocumentCountText.textContent = `${state.files.length}개`;
    }
  }

  updateDocumentModeNotice();
}

function updateDocumentModeNotice() {
  if (!documentModeNotice) {
    return;
  }

  const usesDocuments = state.answerMode !== "general";
  const hasDocuments = state.files.length > 0;

  documentModeNotice.classList.toggle("hidden", !usesDocuments || hasDocuments);

  if (!usesDocuments || hasDocuments) {
    return;
  }

  if (state.projectLoading) {
    documentModeNotice.textContent = "현재 프로젝트의 문서를 불러오는 중이에요.";
  } else if (state.operations.document) {
    documentModeNotice.textContent = "문서를 처리하는 중이에요. 완료되면 문서 기반 답변을 사용할 수 있어요.";
  } else {
    documentModeNotice.textContent =
      "현재 프로젝트에 문서가 없어요. 문서 기반 답변을 쓰려면 문서를 추가하거나, 답변 모드를 일반 AI로 바꿔주세요.";
  }
}

function openDocumentModal() {
  state.documentModalOpen = true;
  documentModal?.classList.remove("hidden");
  updateDocumentPanelSummary();
}

function closeDocumentModal() {
  state.documentModalOpen = false;
  documentModal?.classList.add("hidden");
}

function normalizeProject(project) {
  return {
    id: String(project?.id || "default"),
    name: String(project?.name || project?.id || "Default"),
  };
}

function getCurrentProject() {
  return state.projects.find((project) => project.id === state.projectId) || {
    id: state.projectId || "default",
    name: state.projectId === "default" ? "Default" : state.projectId,
  };
}

function getProjectDisplayName(project) {
  if (!project || project.id === "default") {
    return "기본";
  }

  return project.name || project.id;
}

function getProjectQueryString() {
  return `project_id=${encodeURIComponent(state.projectId || "default")}`;
}

function renderProjectOptions() {
  if (!projectSelect) {
    return;
  }

  projectSelect.innerHTML = "";

  const projects = state.projects.length
    ? state.projects
    : [{ id: "default", name: "Default" }];

  if (!projects.some((project) => project.id === state.projectId)) {
    state.projectId = projects[0].id;
  }

  projects.forEach((project) => {
    const option = document.createElement("option");
    option.value = project.id;
    option.textContent = getProjectDisplayName(project);
    projectSelect.appendChild(option);
  });

  projectSelect.value = state.projectId;
  setProjectStatusText(`현재 프로젝트: ${getProjectDisplayName(getCurrentProject())}`);
  updateCurrentProjectText();
  updateOperationLocks();
}

async function loadProjectsFromBackend() {
  const response = await fetch(`${getApiBaseUrl()}/projects`);

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "프로젝트 목록을 불러오지 못했어요.");
  }

  const data = await response.json();
  state.projects = Array.isArray(data.projects)
    ? data.projects.map(normalizeProject)
    : [{ id: "default", name: "Default" }];

  const projectIds = new Set(state.projects.map((project) => project.id));

  if (!projectIds.has(state.projectId)) {
    state.projectId = data.active_project_id && projectIds.has(data.active_project_id)
      ? data.active_project_id
      : "default";
  }

  renderProjectOptions();
}

async function createProjectInBackend(name) {
  const response = await fetch(`${getApiBaseUrl()}/projects`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "프로젝트를 만들지 못했어요.");
  }

  return response.json();
}

function updateOperationLocks() {
  const projectBusy = state.projectLoading || state.operations.answer || state.operations.document;

  if (sendBtn) {
    sendBtn.disabled = state.operations.answer;
  }

  if (newChatBtn) {
    newChatBtn.disabled = projectBusy;
  }

  if (syncBtn) {
    syncBtn.disabled = state.operations.document;
    syncBtn.textContent = state.operations.document ? "처리 중" : "동기화";
  }

  if (uploadOpenBtn) {
    uploadOpenBtn.disabled = state.operations.document;
  }

  if (projectSelect) {
    projectSelect.disabled = projectBusy || state.projects.length === 0;
  }

  if (projectNameInput) {
    projectNameInput.disabled = projectBusy;
  }

  if (projectCreateBtn) {
    projectCreateBtn.disabled = projectBusy;
  }

  if (projectCreateOpenBtn) {
    projectCreateOpenBtn.disabled = projectBusy;
  }

  if (uploadSubmitBtn && state.operations.document) {
    uploadSubmitBtn.disabled = true;
  }

  if (modelSelect) {
    modelSelect.disabled = state.models.length === 0;
  }

  updateModelSummary();
  renderRecommendedModels();
  renderFileList();
}

// 긴 작업 시작/종료 시 UI 잠금 상태를 바꾸는 공통 함수입니다.
function setOperationBusy(kind, busy) {
  state.operations[kind] = Boolean(busy);
  updateOperationLocks();
}

// 대화가 비어 있을 때 첫 화면 안내를 렌더링합니다.
function renderEmptyChatState() {
  messageList.innerHTML = "";

  const empty = document.createElement("div");
  empty.id = "emptyChatState";
  empty.className = "empty-chat-state";

  const title = document.createElement("div");
  title.className = "empty-chat-title";
  title.textContent = "문서를 넣고 대화를 시작해보세요";

  const subtitle = document.createElement("div");
  subtitle.className = "empty-chat-subtitle";
  subtitle.textContent =
    "문서 기반은 문서 안에서만 답하고, 문서+해석은 문서 근거에 AI 해석을 더하며, 일반 AI는 일반 질문과 코딩 질문에 답합니다.";

  const actions = document.createElement("div");
  actions.className = "empty-chat-actions";

  const uploadHint = document.createElement("span");
  uploadHint.textContent = "왼쪽 문서 패널에서 파일을 추가하거나";

  const askHint = document.createElement("span");
  askHint.textContent = "아래 입력창에 바로 질문하세요";

  actions.appendChild(uploadHint);
  actions.appendChild(askHint);
  empty.appendChild(title);
  empty.appendChild(subtitle);
  empty.appendChild(actions);
  messageList.appendChild(empty);
}

// 첫 질문이 입력되면 빈 화면 안내를 제거합니다.
function removeEmptyChatState() {
  const empty = document.getElementById("emptyChatState");

  if (empty) {
    empty.remove();
  }
}

// 검색 깊이 빠름/균형/깊게 선택 상태를 갱신합니다.
function setMode(mode) {
  state.mode = mode;

  modeButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });

  if (searchModeSelect && searchModeSelect.value !== mode) {
    searchModeSelect.value = mode;
  }
}


// 문서 기반/문서+해석/일반 AI 모드를 상태와 버튼 UI에 반영합니다.
function setAnswerMode(answerMode) {
  state.answerMode = answerMode || "strict_rag";
  state.useRag = state.answerMode !== "general";

  answerModeButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.answerMode === state.answerMode);
  });

  if (answerModeSelect && answerModeSelect.value !== state.answerMode) {
    answerModeSelect.value = state.answerMode;
  }

  updateDocumentModeNotice();
}

function getModelSummaryText() {
  if (state.operations.modelInstall || hasActiveModelInstall()) {
    return "모델 설치 중...";
  }

  if (state.model) {
    return state.model;
  }

  if (state.defaultModel) {
    return state.defaultModel;
  }

  if (state.models.length === 0) {
    return "설치된 대화 모델 없음";
  }

  return "모델 선택 필요";
}

function getModelDisplayName(modelName) {
  return modelName || "기본";
}

function updateModelSummary() {
  const summary = getModelSummaryText();

  if (modelPanelSummary) {
    modelPanelSummary.textContent = summary;
  }

  if (modelModalSummary) {
    modelModalSummary.textContent = summary;
  }
}

function openModelModal() {
  modelModal?.classList.remove("hidden");
  updateModelSummary();
}

function closeModelModal() {
  modelModal?.classList.add("hidden");
}

// 선택된 Ollama chat 모델을 전역 상태와 헤더/셀렉트 UI에 반영합니다.
function setModel(model) {
  state.model = model || state.defaultModel || "";

  if (modelSelect && modelSelect.value !== state.model) {
    modelSelect.value = state.model;
  }

  if (currentModelText) {
    currentModelText.textContent = getModelDisplayName(state.model);
  }

  updateModelSummary();
}

function formatModelSize(bytes) {
  if (!bytes) {
    return "";
  }

  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
  }

  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

// 설치된 모델 목록으로 select option을 다시 구성합니다.
function renderModelOptions(models, defaultModel) {
  if (!modelSelect) {
    return;
  }

  modelSelect.innerHTML = "";

  if (!models.length) {
    const option = document.createElement("option");
    option.value = defaultModel || "";
    option.textContent = defaultModel || "설치된 Ollama 모델 없음";
    modelSelect.appendChild(option);
    modelSelect.disabled = true;
    setModel(defaultModel || "");
    updateModelSummary();
    return;
  }

  models.forEach((model) => {
    const option = document.createElement("option");
    const sizeText = formatModelSize(model.size);
    option.value = model.name;
    option.textContent = sizeText ? `${model.name} (${sizeText})` : model.name;
    modelSelect.appendChild(option);
  });

  modelSelect.disabled = false;

  const preferredModel =
    models.find((model) => model.name === state.model)?.name ||
    models.find((model) => model.name === defaultModel)?.name ||
    models[0].name;
  setModel(preferredModel);
  updateModelSummary();
}

// 추천 모델 카드에 표시할 현재 설치 job 상태를 찾습니다.
function getPullState(modelName) {
  return state.modelPulls[modelName] || null;
}


// 추천 모델 목록과 Install/Use/Retry 버튼 상태를 렌더링합니다.
function renderRecommendedModels() {
  if (!recommendedModelList) {
    return;
  }

  recommendedModelList.innerHTML = "";

  if (!state.recommendedModels.length) {
    const empty = document.createElement("div");
    empty.className = "empty-text";
    empty.textContent = "추천 모델 정보를 불러오지 못했어요.";
    recommendedModelList.appendChild(empty);
    return;
  }

  const modelInstallBusy = state.operations.modelInstall || hasActiveModelInstall();
  const installableModels = state.recommendedModels.filter((model) => !model.installed);

  if (!installableModels.length) {
    const empty = document.createElement("div");
    empty.className = "empty-text";
    empty.textContent = "추천 모델은 모두 설치되어 있어요.";
    recommendedModelList.appendChild(empty);
    return;
  }

  installableModels.forEach((model) => {
    const pullState = getPullState(model.name);
    const item = document.createElement("div");
    item.className = "model-install-item";

    const info = document.createElement("div");
    info.className = "model-install-info";

    const title = document.createElement("div");
    title.className = "model-install-title";
    title.textContent = model.label || model.name;

    const detail = document.createElement("div");
    detail.className = "model-install-detail";
    detail.textContent = `${model.name} · ${model.size_hint || "크기 다름"}`;

    const description = document.createElement("div");
    description.className = "model-install-description";
    description.textContent = model.description || "";

    info.appendChild(title);
    info.appendChild(detail);
    info.appendChild(description);

    const action = document.createElement("button");
    action.className = "small-btn model-install-btn";

    if (pullState && pullState.status !== "completed" && pullState.status !== "failed") {
      action.disabled = true;
      action.textContent = `${pullState.progress || 0}%`;
    } else {
      action.textContent = pullState?.status === "failed" ? "다시 시도" : "설치";
      action.disabled = modelInstallBusy;
      action.addEventListener("click", () => {
        installRecommendedModel(model);
      });
    }

    item.appendChild(info);
    item.appendChild(action);

    if (pullState) {
      const status = document.createElement("div");
      status.className = `model-install-progress ${pullState.status}`;
      status.textContent = pullState.error
        ? pullState.error
        : pullState.message || pullState.status;
      item.appendChild(status);
    }

    recommendedModelList.appendChild(item);
  });
}


// Ollama에 설치된 모델과 추천 모델 설치 여부를 백엔드에서 불러옵니다.
async function loadModelsFromBackend() {
  const response = await fetch(`${getApiBaseUrl()}/models`);

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "모델 목록을 불러오지 못했어요.");
  }

  const data = await response.json();
  state.models = Array.isArray(data.models) ? data.models : [];
  state.defaultModel = data.default_model || "";
  state.recommendedModels = Array.isArray(data.recommended_models)
    ? data.recommended_models
    : [];

  renderModelOptions(state.models, state.defaultModel);
  renderRecommendedModels();

  if (modelStatusText) {
    const embedModel = data.embedding_model || "default";
    modelStatusText.textContent = `임베딩 모델은 고정 사용: ${embedModel}`;
  }

  updateModelSummary();
}


// 모델 설치 job을 시작합니다.
async function startModelPull(modelName) {
  const response = await fetch(`${getApiBaseUrl()}/models/pull`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: modelName,
    }),
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "모델 설치를 시작하지 못했어요.");
  }

  return response.json();
}


// 모델 설치 job의 현재 진행률을 조회합니다.
async function getModelPullStatus(jobId) {
  const response = await fetch(`${getApiBaseUrl()}/models/pull/${jobId}`);

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "모델 설치 상태를 확인하지 못했어요.");
  }

  return response.json();
}


// 모델 설치가 끝날 때까지 polling하며 추천 모델 UI를 갱신합니다.
async function pollModelPull(jobId, modelName) {
  while (true) {
    const status = await getModelPullStatus(jobId);
    state.modelPulls[modelName] = status;
    renderRecommendedModels();
    updateModelSummary();

    if (status.status === "completed") {
      await loadModelsFromBackend();
      setModel(modelName);
      setOperationBusy("modelInstall", false);
      renderRecommendedModels();
      showToast(`${modelName} 모델 설치가 완료됐고 현재 모델로 선택했어요.`, "success");
      return;
    }

    if (status.status === "failed") {
      setOperationBusy("modelInstall", false);
      renderRecommendedModels();
      updateModelSummary();
      showToast(`${modelName} 모델 설치에 실패했어요. ${mapApiErrorMessage(status.error || status.message)}`, "error");
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}


// 사용자가 추천 모델 Install 버튼을 눌렀을 때 확인 후 설치 job을 시작합니다.
async function installRecommendedModel(model) {
  if (state.operations.modelInstall || hasActiveModelInstall()) {
    showToast("모델 설치가 이미 진행 중이에요. 설치가 끝난 뒤 다시 시도해주세요.", "warning");
    return;
  }

  const confirmed = confirm(
    `${model.name} 모델을 Ollama에 설치할까?\n\n예상 크기: ${model.size_hint || "모델에 따라 다름"}\n인터넷 연결과 디스크 공간이 필요해.`
  );

  if (!confirmed) {
    return;
  }

  try {
    setOperationBusy("modelInstall", true);

    if (modelStatusText) {
      modelStatusText.textContent = `${model.name} 설치를 시작하는 중...`;
    }

    const job = await startModelPull(model.name);
    state.modelPulls[model.name] = job;
    renderRecommendedModels();
    updateModelSummary();
    pollModelPull(job.job_id, model.name).catch((error) => {
      setOperationBusy("modelInstall", false);
      state.modelPulls[model.name] = {
        ...state.modelPulls[model.name],
        status: "failed",
        message: "모델 설치 실패",
        error: getFriendlyErrorMessage(error),
      };
      renderRecommendedModels();
      updateModelSummary();
      showToast(`${model.name} 모델 설치 중 오류가 발생했어요. ${getFriendlyErrorMessage(error)}`, "error");
    });
  } catch (error) {
    setOperationBusy("modelInstall", false);
    updateModelSummary();
    showToast(`${model.name} 모델 설치를 시작하지 못했어요. ${getFriendlyErrorMessage(error)}`, "error");
  }
}

function getSourceQualityLabel(sourceQuality) {
  const quality = sourceQuality?.quality || "none";

  if (quality === "strong") {
    return "근거 강함";
  }

  if (quality === "medium") {
    return "근거 보통";
  }

  if (quality === "weak") {
    return "근거 약함";
  }

  return "문서 근거 없음";
}

function buildAnswerMetadataFromMessage(message = {}) {
  const sources = Array.isArray(message.sources) ? message.sources : [];
  const sourceQuality = message.source_quality || null;

  return {
    sources,
    sourceQuality,
    answerMode: message.answer_mode || null,
    retrievalMode: message.retrieval_mode || message.mode || null,
    model: message.model || null,
    useRag: message.use_rag,
    showDetails: Boolean(
      message.show_details ||
        (message.role === "assistant" && (sources.length > 0 || sourceQuality))
    ),
  };
}

function buildAnswerMetadataFromResult(result = {}) {
  return {
    sources: Array.isArray(result.sources) ? result.sources : [],
    sourceQuality: result.source_quality || null,
    answerMode: result.answer_mode || state.answerMode,
    retrievalMode: result.mode || state.mode,
    model: result.model || state.model || state.defaultModel,
    useRag: result.use_rag,
    showDetails: true,
  };
}

function normalizeAnswerMetadata(metadata = {}) {
  const sources = Array.isArray(metadata.sources) ? metadata.sources : [];
  const sourceQuality = metadata.sourceQuality || metadata.source_quality || null;
  const answerMode = metadata.answerMode || metadata.answer_mode || null;
  const retrievalMode = metadata.retrievalMode || metadata.retrieval_mode || metadata.mode || null;
  const model = metadata.model || null;
  const useRag =
    metadata.useRag !== undefined
      ? metadata.useRag
      : metadata.use_rag !== undefined
        ? metadata.use_rag
        : sources.length > 0 || Boolean(sourceQuality);

  return {
    sources,
    sourceQuality,
    answerMode,
    retrievalMode,
    model,
    useRag,
    showDetails: Boolean(metadata.showDetails),
  };
}

function formatAnswerModeForDetails(answerMode, useRag) {
  if (useRag === false || answerMode === "general") {
    return "일반 AI";
  }

  if (answerMode === "hybrid") {
    return "문서+해석";
  }

  return "문서 기반";
}

function formatRetrievalModeForDetails(retrievalMode) {
  if (retrievalMode === "balanced") {
    return "균형";
  }

  if (retrievalMode === "deep") {
    return "깊게";
  }

  return "빠름";
}

function getAnswerPolicyLabel(answerMode, useRag) {
  if (useRag === false || answerMode === "general") {
    return "문서 검색 없이 일반 모델 답변";
  }

  if (answerMode === "hybrid") {
    return "문서 근거에 AI 해석 추가";
  }

  return "검색된 문서 근거 안에서만 답변";
}

function formatDistance(value) {
  if (value === undefined || value === null || value === "") {
    return "";
  }

  const number = Number(value);

  if (Number.isNaN(number)) {
    return "";
  }

  return number.toFixed(3);
}

function createAnswerDetailRow(label, value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }

  const row = document.createElement("div");
  row.className = "answer-detail-row";

  const labelEl = document.createElement("span");
  labelEl.textContent = label;

  const valueEl = document.createElement("strong");
  valueEl.textContent = String(value);

  row.appendChild(labelEl);
  row.appendChild(valueEl);
  return row;
}

function createAnswerSourceItem(source, index) {
  const item = document.createElement("div");
  item.className = "answer-source-item";

  const title = document.createElement("strong");
  title.textContent = `${index + 1}. ${source.source || "알 수 없는 근거"}`;

  const positionParts = [];

  if (source.page) {
    positionParts.push(`페이지 ${source.page}`);
  }

  if (source.chunk_index !== undefined && source.chunk_index !== "") {
    positionParts.push(`청크 ${source.chunk_index}`);
  }

  item.appendChild(title);

  if (positionParts.length > 0) {
    const position = document.createElement("span");
    position.className = "answer-source-position";
    position.textContent = positionParts.join(" · ");
    item.appendChild(position);
  }

  const technicalParts = [];
  const distance = formatDistance(source.distance);

  if (distance) {
    technicalParts.push(`거리 ${distance}`);
  }

  if (source.matched_query) {
    technicalParts.push(`검색어 "${source.matched_query}"`);
  }

  if (technicalParts.length > 0) {
    const meta = document.createElement("span");
    meta.className = "answer-source-meta";
    meta.textContent = technicalParts.join(" · ");
    item.appendChild(meta);
  }

  return item;
}

function renderAnswerDetails(metadata = {}) {
  const detailsData = normalizeAnswerMetadata(metadata);
  const {
    sources,
    sourceQuality,
    answerMode,
    retrievalMode,
    model,
    useRag,
  } = detailsData;
  const sourceCount = sourceQuality?.source_count ?? sources.length;
  const bestDistance = formatDistance(sourceQuality?.best_distance);
  const details = document.createElement("details");
  details.className = "answer-details";

  const summary = document.createElement("summary");
  summary.textContent = sources.length > 0 ? `근거 보기 ${sources.length}개` : "답변 정보";
  details.appendChild(summary);

  if (sources.length > 0) {
    const sourceList = document.createElement("div");
    sourceList.className = "answer-source-list";

    sources.forEach((source, index) => {
      sourceList.appendChild(createAnswerSourceItem(source, index));
    });

    details.appendChild(sourceList);
  }

  const technicalRows = [
    createAnswerDetailRow("답변 모드", formatAnswerModeForDetails(answerMode, useRag)),
    createAnswerDetailRow("검색 모드", useRag === false ? "꺼짐" : formatRetrievalModeForDetails(retrievalMode)),
    createAnswerDetailRow("모델", model),
    createAnswerDetailRow("RAG 검색", useRag === false ? "꺼짐" : "켜짐"),
    createAnswerDetailRow("답변 정책", getAnswerPolicyLabel(answerMode, useRag)),
    createAnswerDetailRow("근거 품질", sourceQuality ? getSourceQualityLabel(sourceQuality) : "없음"),
    createAnswerDetailRow("근거 수", sourceCount),
    createAnswerDetailRow("최고 관련 거리", bestDistance),
  ]
    .filter(Boolean);

  if (technicalRows.length > 0) {
    const technicalDetails = document.createElement("details");
    technicalDetails.className = "answer-technical-details";

    const technicalSummary = document.createElement("summary");
    technicalSummary.textContent = "상세 정보";
    technicalDetails.appendChild(technicalSummary);

    const grid = document.createElement("div");
    grid.className = "answer-detail-grid";

    technicalRows.forEach((row) => grid.appendChild(row));
    technicalDetails.appendChild(grid);
    details.appendChild(technicalDetails);
  }

  return details;
}

// 채팅 메시지를 화면에 그리며 sources와 source quality 배지를 함께 표시합니다.
function appendMessageToView(role, content, sources = [], sourceQuality = null, metadata = {}) {
  removeEmptyChatState();

  const message = document.createElement("div");
  message.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "U" : "AI";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;

  if (sourceQuality) {
    const quality = sourceQuality.quality || "none";
    const qualityBadge = document.createElement("div");
    qualityBadge.className = `source-quality source-quality-${quality}`;
    qualityBadge.textContent = `${getSourceQualityLabel(sourceQuality)} · ${sourceQuality.message || ""}`;
    bubble.appendChild(qualityBadge);
  }

  const answerMetadata = normalizeAnswerMetadata({
    ...metadata,
    sources,
    sourceQuality,
  });

  if (role === "assistant" && answerMetadata.showDetails) {
    bubble.appendChild(
      renderAnswerDetails(answerMetadata)
    );
  }

  message.appendChild(avatar);
  message.appendChild(bubble);
  messageList.appendChild(message);

  messageList.scrollTop = messageList.scrollHeight;
}

// 현재 선택된 채팅 객체를 반환합니다.
function getCurrentChat() {
  return state.chats.find((chat) => chat.id === state.currentChatId) || null;
}

// 첫 사용자 메시지를 기반으로 채팅 목록에 표시할 제목을 만듭니다.
function buildChatTitleFromMessage(content) {
  const title = String(content || "")
    .replace(/\s+/g, " ")
    .trim();

  if (!title) {
    return "New chat";
  }

  return title.length > 28 ? `${title.slice(0, 28)}...` : title;
}

// 백엔드에서 받은 채팅 데이터를 프론트가 기대하는 구조로 맞춥니다.
function normalizeChat(chat) {
  return {
    id: String(chat.id),
    title: chat.title || "New chat",
    messages: Array.isArray(chat.messages) ? chat.messages : [],
    created_at: chat.created_at || Date.now() / 1000,
    updated_at: chat.updated_at || Date.now() / 1000,
  };
}

// 백엔드 저장소에 새 채팅을 생성합니다.
async function createChatInBackend(title = "New chat") {
  const response = await fetch(`${getApiBaseUrl()}/chats?${getProjectQueryString()}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title }),
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "채팅을 만들지 못했어요.");
  }

  return normalizeChat(await response.json());
}

// 현재 채팅 메시지를 백엔드 JSON 저장소에 저장합니다.
async function saveChatToBackend(chat) {
  const response = await fetch(`${getApiBaseUrl()}/chats/${encodeURIComponent(chat.id)}?${getProjectQueryString()}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      title: chat.title,
      messages: chat.messages,
    }),
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "채팅을 저장하지 못했어요.");
  }

  const savedChat = normalizeChat(await response.json());
  const index = state.chats.findIndex((item) => item.id === savedChat.id);

  if (index >= 0) {
    state.chats[index].updated_at = savedChat.updated_at;
  }

  renderChatList();
  return savedChat;
}

// 백엔드 저장소에서 채팅 하나를 삭제합니다.
async function deleteChatFromBackend(chatId) {
  const response = await fetch(`${getApiBaseUrl()}/chats/${encodeURIComponent(chatId)}?${getProjectQueryString()}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "채팅을 삭제하지 못했어요.");
  }
}

// 메시지 추가 후 호출되는 자동 저장 함수입니다.
async function saveCurrentChat() {
  const chat = getCurrentChat();

  if (!chat) {
    return;
  }

  try {
    await saveChatToBackend(chat);
  } catch (error) {
    console.error(error);
  }
}

// 화면에 메시지를 추가하고, persist가 true이면 현재 채팅에도 저장합니다.
function addMessage(role, content, sources = [], persist = true, sourceQuality = null, metadata = {}) {
  appendMessageToView(role, content, sources, sourceQuality, metadata);

  if (!persist) {
    return;
  }

  const chat = getCurrentChat();

  if (!chat) {
    return;
  }

  const message = {
    role,
    content,
    sources: Array.isArray(sources) ? sources : [],
    source_quality: sourceQuality,
    created_at: new Date().toISOString(),
  };

  if (metadata.showDetails) {
    message.show_details = true;
    message.answer_mode = metadata.answerMode || metadata.answer_mode || null;
    message.retrieval_mode = metadata.retrievalMode || metadata.retrieval_mode || metadata.mode || null;
    message.model = metadata.model || null;
    message.use_rag = metadata.useRag !== undefined ? metadata.useRag : metadata.use_rag;
  }

  chat.messages.push(message);

  if (role === "user" && (!chat.title || chat.title === "New chat" || chat.title.startsWith("새 채팅"))) {
    chat.title = buildChatTitleFromMessage(content);
  }

  chat.updated_at = Date.now() / 1000;
  renderChatList();
  saveCurrentChat();
}

// 오래 걸리는 작업 중 표시할 임시 assistant 메시지를 만듭니다.
function addLoadingMessage(text = "문서를 검색하고 답변을 생성하는 중...", withStatus = false) {
  const message = document.createElement("div");
  message.className = "message assistant";
  message.id = "loadingMessage";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "AI";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (withStatus) {
    const loadingText = document.createElement("div");
    loadingText.className = "loading-text";
    loadingText.textContent = text;

    const loadingMeta = document.createElement("div");
    loadingMeta.className = "loading-meta";
    loadingMeta.textContent = "0초";

    bubble.appendChild(loadingText);
    bubble.appendChild(loadingMeta);
  } else {
    bubble.textContent = text;
  }

  message.appendChild(avatar);
  message.appendChild(bubble);
  messageList.appendChild(message);

  messageList.scrollTop = messageList.scrollHeight;
}


// 백엔드 elapsed_seconds 값을 읽기 쉬운 분/초 문자열로 바꿉니다.
function formatElapsedTime(elapsedMs) {
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes > 0) {
    return `${minutes}분 ${seconds}초`;
  }

  return `${seconds}초`;
}


// 백그라운드 job 진행 단계 메시지와 경과 시간을 loading bubble에 반영합니다.
function updateLoadingMessage(text, elapsedSeconds = null) {
  const loading = document.getElementById("loadingMessage");

  if (!loading) {
    return;
  }

  const bubble = loading.querySelector(".bubble");

  if (bubble) {
    const loadingText = bubble.querySelector(".loading-text");
    const loadingMeta = bubble.querySelector(".loading-meta");

    if (loadingText) {
      loadingText.textContent = text;
    } else {
      bubble.textContent = text;
    }

    if (loadingMeta && elapsedSeconds !== null) {
      loadingMeta.textContent = formatElapsedTime(elapsedSeconds * 1000);
    }

    messageList.scrollTop = messageList.scrollHeight;
  }
}


// 작업 완료/실패 후 loading bubble을 제거합니다.
function removeLoadingMessage() {
  const loading = document.getElementById("loadingMessage");

  if (loading) {
    loading.remove();
  }
}

// 오른쪽 위 Guide 모달을 엽니다.
function openGuideModal() {
  if (guideModal) {
    guideModal.classList.remove("hidden");
  }
}

// Guide 모달을 닫습니다.
function closeGuideModal() {
  if (guideModal) {
    guideModal.classList.add("hidden");
  }
}

// 모델에 넘길 이전 대화 일부를 현재 채팅에서 추립니다.
function getChatHistoryForRequest(limit = 10) {
  const chat = getCurrentChat();

  if (!chat || !Array.isArray(chat.messages)) {
    return [];
  }

  return chat.messages
    .filter((message) => {
      return (
        (message.role === "user" || message.role === "assistant") &&
        String(message.content || "").trim()
      );
    })
    .slice(-limit)
    .map((message) => ({
      role: message.role,
      content: String(message.content || ""),
    }));
}

// 답변 생성 job을 시작합니다.
async function startAskJob(question, mode, model, useRag, answerMode, chatHistory = []) {
  const response = await fetch(`${getApiBaseUrl()}/ask/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      mode,
      model,
      use_rag: useRag,
      answer_mode: answerMode,
      chat_history: chatHistory,
      project_id: state.projectId,
    }),
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "답변 작업을 시작하지 못했어요.");
  }

  return response.json();
}


// 답변 생성 job 상태를 조회합니다.
async function getAskJobStatus(jobId) {
  const response = await fetch(`${getApiBaseUrl()}/ask/jobs/${jobId}`);

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "답변 작업 상태를 확인하지 못했어요.");
  }

  return response.json();
}


// 답변 job이 끝날 때까지 polling하고 완료 결과를 반환합니다.
async function pollAskJob(jobId) {
  while (true) {
    const status = await getAskJobStatus(jobId);

    updateLoadingMessage(status.message || "답변을 준비하는 중...", status.elapsed_seconds || 0);

    if (status.status === "completed") {
      return status.result;
    }

    if (status.status === "failed") {
      throw new Error(status.error || status.message || "답변 생성 실패");
    }

    await new Promise((resolve) => setTimeout(resolve, 700));
  }
}

// 사용자가 전송 버튼이나 Enter를 눌렀을 때 질문을 job으로 보냅니다.
async function handleSend() {
  if (state.operations.answer) {
    addMessage("assistant", "이미 답변을 생성 중이에요. 완료된 뒤 다시 질문해주세요.");
    return;
  }

  const question = questionInput.value.trim();

  if (!question) {
    return;
  }

  const chatHistory = getChatHistoryForRequest();

  addMessage("user", question);
  questionInput.value = "";
  autoResizeTextarea();

  setOperationBusy("answer", true);
  addLoadingMessage("질문 처리를 시작하는 중...", true);

  try {
    const job = await startAskJob(
      question,
      state.mode,
      state.model,
      state.useRag,
      state.answerMode,
      chatHistory
    );
    updateLoadingMessage(job.message || "질문 처리를 시작하는 중...", job.elapsed_seconds || 0);
    const result = await pollAskJob(job.job_id);
    const answerMetadata = buildAnswerMetadataFromResult(result);

    removeLoadingMessage();
    addMessage(
      "assistant",
      result.answer,
      result.sources || [],
      true,
      result.source_quality || null,
      answerMetadata
    );
  } catch (error) {
    removeLoadingMessage();
    addMessage("assistant", `답변 생성 중 오류가 발생했어.\n${getFriendlyErrorMessage(error)}`);
  } finally {
    setOperationBusy("answer", false);
    questionInput.focus();
  }
}

function openUploadModal() {
  uploadModal.classList.remove("hidden");
  pendingFiles = [];
  renderSelectedFiles();
}

// 업로드 모달을 닫고 선택된 임시 파일 목록을 비웁니다.
function closeUploadModal() {
  uploadModal.classList.add("hidden");
  pendingFiles = [];
  fileInput.value = "";
  renderSelectedFiles();
}

// 드래그/파일 선택으로 들어온 파일 중 지원 확장자만 pending 목록에 추가합니다.
function addPendingFiles(files) {
  const allowedExtensions = [
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".csv",
    ".xlsx",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".json",
    ".yaml",
    ".yml",
    ".java",
    ".cpp",
    ".c",
    ".cs",
    ".go",
    ".rs",
    ".php",
    ".sql",
    ".sh",
    ".ps1",
    ".bat",
  ];

  const filtered = Array.from(files).filter((file) => {
    const lower = file.name.toLowerCase();

    return allowedExtensions.some((ext) => lower.endsWith(ext));
  });

  pendingFiles = [...pendingFiles, ...filtered];
  renderSelectedFiles();
}

// 업로드 모달 안에 현재 선택된 파일 목록을 표시합니다.
function renderSelectedFiles() {
  selectedFileList.innerHTML = "";

  if (pendingFiles.length === 0) {
    return;
  }

  pendingFiles.forEach((file) => {
    const item = document.createElement("div");
    item.className = "selected-file";
    item.textContent = `${file.name} · ${formatFileSize(file.size)}`;
    selectedFileList.appendChild(item);
  });
}

// 문서 목록 응답이 직접 documents이든 document_state이든 같은 배열로 맞춥니다.
function normalizeDocumentsFromResponse(data) {
  if (!data) {
    return [];
  }

  if (Array.isArray(data.documents)) {
    return data.documents;
  }

  if (data.document_state && Array.isArray(data.document_state.documents)) {
    return data.document_state.documents;
  }

  return [];
}

// 현재 ChromaDB 문서 목록을 백엔드에서 읽어 왼쪽 패널을 갱신합니다.
const DOCUMENT_STATUS_META = {
  indexed: {
    label: "정상",
    hint: "",
  },
  processing: {
    label: "처리 중",
    hint: "문서 인덱싱이 아직 진행 중입니다.",
  },
  empty: {
    label: "텍스트 없음",
    hint: "이 파일은 OCR이 필요할 수 있습니다.",
  },
  failed: {
    label: "실패",
    hint: "파일을 확인한 뒤 다시 동기화해보세요.",
  },
  needs_sync: {
    label: "동기화 필요",
    hint: "동기화를 실행해 벡터 인덱스를 갱신하세요.",
  },
  missing_file: {
    label: "파일 없음",
    hint: "원본 파일이 documents 폴더에 없습니다.",
  },
  unsupported: {
    label: "미지원",
    hint: "이 파일 형식은 인덱싱되지 않습니다.",
  },
};

function getDocumentStatusMeta(doc) {
  const status = doc.status || "indexed";

  return {
    status,
    ...(DOCUMENT_STATUS_META[status] || {
      label: doc.status_label || status,
      hint: "",
    }),
  };
}

function getDocumentFilterCounts() {
  return state.files.reduce(
    (counts, doc) => {
      const status = doc.status || "indexed";
      counts.all += 1;

      if (status === "indexed") {
        counts.indexed += 1;
      } else if (status === "needs_sync") {
        counts.needs_sync += 1;
      } else if (status !== "processing") {
        counts.problem += 1;
      }

      return counts;
    },
    {
      all: 0,
      indexed: 0,
      needs_sync: 0,
      problem: 0,
    }
  );
}

function getDocumentFilterLabel(filter) {
  const labels = {
    all: "전체",
    indexed: "정상",
    needs_sync: "동기화 필요",
    problem: "문제 있음",
  };

  return labels[filter] || labels.all;
}

function documentMatchesFilter(doc, filter) {
  const status = doc.status || "indexed";

  if (filter === "indexed") {
    return status === "indexed";
  }

  if (filter === "needs_sync") {
    return status === "needs_sync";
  }

  if (filter === "problem") {
    return status !== "indexed" && status !== "needs_sync" && status !== "processing";
  }

  return true;
}

function updateDocumentFilterButtons() {
  const counts = getDocumentFilterCounts();

  documentFilterButtons.forEach((button) => {
    const filter = button.dataset.documentFilter || "all";
    button.classList.toggle("active", filter === state.documentFilter);
    button.textContent = `${getDocumentFilterLabel(filter)} ${counts[filter] || 0}`;
  });
}

function setDocumentFilter(filter) {
  state.documentFilter = filter || "all";
  updateDocumentFilterButtons();
  renderFileList();
}

function formatDocumentDetails(doc) {
  const parts = [];
  const chunks = Number(doc.chunks || 0);
  const pages = Number(doc.pages || 0);
  const characters = Number(doc.characters || 0);

  parts.push(`청크 ${chunks}`);

  if (pages > 0) {
    parts.push(`페이지 ${pages}`);
  }

  if (characters > 0) {
    parts.push(`${characters.toLocaleString()}자`);
  }

  if (doc.ocr_used) {
    const ocrPages = Number(doc.ocr_pages || 0);
    parts.push(ocrPages > 0 ? `OCR ${ocrPages}p` : "OCR");
  }

  return parts.join(" · ");
}

function getDocumentWarningText(doc, statusMeta) {
  if (doc.error) {
    return doc.error;
  }

  if (Array.isArray(doc.reindex_reasons) && doc.reindex_reasons.length > 0) {
    return `재인덱싱 필요: ${doc.reindex_reasons[0]}`;
  }

  if (Array.isArray(doc.warnings) && doc.warnings.length > 0) {
    return doc.warnings[0];
  }

  return statusMeta.hint || "";
}

async function loadDocumentsFromBackend() {
  const response = await fetch(`${getApiBaseUrl()}/documents?${getProjectQueryString()}`);

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "문서 목록을 불러오지 못했어요.");
  }

  const data = await response.json();

  state.files = normalizeDocumentsFromResponse(data);
  renderFileList();
}

// 왼쪽 문서 패널의 파일 목록과 삭제 버튼을 렌더링합니다.
function renderFileList() {
  updateDocumentPanelSummary();
  updateDocumentFilterButtons();
  fileList.innerHTML = "";

  if (state.projectLoading) {
    const loading = document.createElement("div");
    loading.className = "empty-text";
    loading.textContent = "이 프로젝트의 문서를 불러오는 중...";
    fileList.appendChild(loading);
    updateDocumentPanelSummary();
    return;
  }

  if (state.files.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-text";
    empty.textContent = "아직 추가된 문서가 없어.";
    empty.textContent = `${getCurrentProject().name} 프로젝트에 아직 문서가 없어요.`;
    fileList.appendChild(empty);
    updateDocumentPanelSummary();
    return;
  }

  const visibleFiles = state.files.filter((doc) => documentMatchesFilter(doc, state.documentFilter));

  if (visibleFiles.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-text";
    empty.textContent = `${getDocumentFilterLabel(state.documentFilter)} 상태의 문서가 없어요.`;
    fileList.appendChild(empty);
    updateDocumentPanelSummary();
    return;
  }

  visibleFiles.forEach((doc) => {
    const item = document.createElement("div");
    const statusMeta = getDocumentStatusMeta(doc);
    item.className = `file-item document-status-${statusMeta.status}`;

    const info = document.createElement("div");
    info.className = "file-info";

    const name = document.createElement("strong");
    name.textContent = doc.source;

    const status = document.createElement("span");
    status.className = `document-status-badge document-status-badge-${statusMeta.status}`;
    status.textContent = statusMeta.label;

    const meta = document.createElement("span");
    meta.className = "file-meta";
    meta.textContent = formatDocumentDetails(doc);

    const warningText = getDocumentWarningText(doc, statusMeta);

    info.appendChild(name);
    info.appendChild(status);
    info.appendChild(meta);

    if (warningText) {
      const warning = document.createElement("span");
      warning.className = "file-warning";
      warning.textContent = warningText;
      info.appendChild(warning);
    }

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "file-delete";
    deleteBtn.textContent = "×";
    deleteBtn.title = "문서 삭제";
    deleteBtn.disabled = state.operations.document;
    deleteBtn.addEventListener("click", () => {
      removeFile(doc.source);
    });

    item.appendChild(info);
    item.appendChild(deleteBtn);
    fileList.appendChild(item);
  });

  updateDocumentPanelSummary();
}

// 선택한 파일들을 multipart/form-data로 업로드하고 문서 처리 job을 받습니다.
async function uploadFilesToBackend(files) {
  const formData = new FormData();

  files.forEach((file) => {
    formData.append("files", file);
  });

  const response = await fetch(`${getApiBaseUrl()}/documents/upload?${getProjectQueryString()}`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "파일 업로드를 시작하지 못했어요.");
  }

  return response.json();
}

// 문서 업로드/동기화 job의 현재 상태를 조회합니다.
async function getDocumentJobStatus(jobId) {
  const response = await fetch(`${getApiBaseUrl()}/documents/jobs/${jobId}`);

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "문서 처리 상태를 확인하지 못했어요.");
  }

  return response.json();
}

// 문서 처리 job이 끝날 때까지 polling합니다.
async function pollDocumentJob(jobId) {
  while (true) {
    const status = await getDocumentJobStatus(jobId);

    updateLoadingMessage(status.message || "문서를 처리하는 중...", status.elapsed_seconds || 0);

    if (status.status === "completed") {
      return status.result || {};
    }

    if (status.status === "failed") {
      throw new Error(status.error || status.message || "문서 처리에 실패했어.");
    }

    await new Promise((resolve) => setTimeout(resolve, 700));
  }
}

// 업로드 모달의 추가하기 버튼을 눌렀을 때 파일 저장과 벡터화 job을 시작합니다.
async function handleUploadSubmit() {
  if (state.operations.document) {
    addMessage("assistant", "문서 처리 작업이 진행 중이에요. 완료 후 다시 시도해주세요.");
    return;
  }

  if (pendingFiles.length === 0) {
    closeUploadModal();
    return;
  }

  const uploadCount = pendingFiles.length;

  setOperationBusy("document", true);
  uploadSubmitBtn.disabled = true;
  uploadSubmitBtn.textContent = "처리 중...";

  try {
    addLoadingMessage("파일을 저장하고 문서 처리 작업을 시작하는 중...", true);

    const job = await uploadFilesToBackend(pendingFiles);
    updateLoadingMessage(job.message || "문서 처리 작업을 시작하는 중...", job.elapsed_seconds || 0);
    await pollDocumentJob(job.job_id);

    await loadDocumentsFromBackend();

    removeLoadingMessage();
    closeUploadModal();

    addMessage(
      "assistant",
      `파일 ${uploadCount}개를 추가했고 ChromaDB 벡터화까지 완료했어.`
    );
  } catch (error) {
    removeLoadingMessage();
    addMessage("assistant", `파일 업로드 중 오류가 발생했어.\n${getFriendlyErrorMessage(error)}`);
  } finally {
    setOperationBusy("document", false);
    uploadSubmitBtn.disabled = false;
    uploadSubmitBtn.textContent = "추가하기";
  }
}

// 문서 원본 파일과 ChromaDB chunk를 함께 삭제합니다.
async function removeFile(fileName) {
  if (state.operations.document) {
    addMessage("assistant", "문서 처리 작업이 진행 중이라 삭제할 수 없어요. 완료 후 다시 시도해주세요.");
    return;
  }

  const confirmed = await confirmDeleteAction({
    title: "문서를 삭제할까요?",
    message: "문서 파일과 저장된 벡터 근거가 함께 삭제됩니다.",
    target: fileName,
  });

  if (!confirmed) {
    return;
  }

  try {
    const response = await fetch(
      `${getApiBaseUrl()}/documents/${encodeURIComponent(fileName)}?${getProjectQueryString()}`,
      {
        method: "DELETE",
      }
    );

    if (!response.ok) {
      throw await apiErrorFromResponse(response, "파일 삭제에 실패했어요.");
    }

    const data = await response.json();

    state.files = normalizeDocumentsFromResponse(data);
    renderFileList();

    addMessage("assistant", `${fileName} 문서를 삭제했어.`);
  } catch (error) {
    addMessage("assistant", `파일 삭제 중 오류가 발생했어.\n${getFriendlyErrorMessage(error)}`);
  }
}

// documents 폴더와 ChromaDB를 비교해 추가/수정/삭제를 반영합니다.
async function syncDocuments() {
  if (state.operations.document) {
    addMessage("assistant", "문서 처리 작업이 진행 중이에요. 완료 후 다시 시도해주세요.");
    return;
  }

  setOperationBusy("document", true);

  try {
    addLoadingMessage("documents 폴더 동기화 작업을 시작하는 중...", true);

    const response = await fetch(`${getApiBaseUrl()}/documents/sync?${getProjectQueryString()}`, {
      method: "POST",
    });

    if (!response.ok) {
      throw await apiErrorFromResponse(response, "동기화를 시작하지 못했어요.");
    }

    const job = await response.json();
    updateLoadingMessage(job.message || "동기화 작업을 시작하는 중...", job.elapsed_seconds || 0);
    const data = await pollDocumentJob(job.job_id);

    await loadDocumentsFromBackend();
    saveLastDocumentSyncAt();
    updateDocumentPanelSummary();

    removeLoadingMessage();

    const summary = data.summary || data.document_state || {};

    addMessage(
      "assistant",
      `동기화 완료.\n추가: ${summary.added_count || 0}개\n업데이트: ${summary.updated_count || 0}개\n삭제: ${summary.deleted_count || 0}개\n전체 chunk: ${summary.total_chunks || 0}개`
    );
  } catch (error) {
    removeLoadingMessage();
    addMessage("assistant", `동기화 중 오류가 발생했어.\n${getFriendlyErrorMessage(error)}`);
  } finally {
    setOperationBusy("document", false);
  }
}

function createLegacyNewChat() {
  const id = Date.now();

  state.chats.push({
    id,
    title: `새 채팅 ${state.chats.length}`,
    messages: [],
  });

  renderChatList();

  messageList.innerHTML = "";
  addMessage(
    "assistant",
    "새 채팅을 시작했어. 문서에 대해 질문해봐."
  );
}

// 왼쪽 채팅 목록을 최신 순서대로 렌더링합니다.
function renderChatList() {
  chatList.innerHTML = "";

  state.chats.forEach((chat) => {
    const item = document.createElement("div");
    item.className = `chat-item ${chat.id === state.currentChatId ? "active" : ""}`;

    const selectBtn = document.createElement("button");
    selectBtn.className = "chat-select";
    selectBtn.title = chat.title;
    selectBtn.addEventListener("click", () => {
      selectChat(chat.id);
    });

    const title = document.createElement("span");
    title.textContent = chat.title || "New chat";
    selectBtn.appendChild(title);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "chat-delete";
    deleteBtn.title = "채팅 삭제";
    deleteBtn.textContent = "×";
    deleteBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteChat(chat.id);
    });

    item.appendChild(selectBtn);
    item.appendChild(deleteBtn);
    chatList.appendChild(item);
  });
}

// 저장된 채팅 목록을 불러오고 없으면 첫 채팅을 생성합니다.
async function loadChatsFromBackend() {
  const response = await fetch(`${getApiBaseUrl()}/chats?${getProjectQueryString()}`);

  if (!response.ok) {
    throw await apiErrorFromResponse(response, "채팅 목록을 불러오지 못했어요.");
  }

  const data = await response.json();
  state.chats = Array.isArray(data.chats) ? data.chats.map(normalizeChat) : [];

  if (state.chats.length === 0) {
    const chat = await createChatInBackend("New chat");
    state.chats = [chat];
  }

  state.currentChatId = state.chats[0].id;
  renderChatList();
  renderCurrentChatMessages();
}

// 현재 선택된 채팅의 메시지를 화면에 다시 그립니다.
function renderCurrentChatMessages() {
  const chat = getCurrentChat();
  messageList.innerHTML = "";

  if (!chat || chat.messages.length === 0) {
    renderEmptyChatState();
    return;

    addMessage(
      "assistant",
      "새 채팅을 시작했어. 문서 질문, 일반 질문, 코딩 질문을 바로 물어봐.",
      [],
      false
    );
    return;
  }

  chat.messages.forEach((message) => {
    const metadata = buildAnswerMetadataFromMessage(message);
    appendMessageToView(
      message.role || "assistant",
      message.content || "",
      message.sources || [],
      message.source_quality || null,
      metadata
    );
  });
}

// 왼쪽 채팅 목록에서 선택한 대화로 전환합니다.
function selectChat(chatId) {
  state.currentChatId = chatId;
  renderChatList();
  renderCurrentChatMessages();
}

// 새 채팅을 만들고 현재 채팅으로 전환합니다.
async function createNewChat() {
  try {
    const chat = await createChatInBackend("New chat");
    state.chats.unshift(chat);
    state.currentChatId = chat.id;
    renderChatList();
    renderCurrentChatMessages();
  } catch (error) {
    addMessage("assistant", `새 채팅을 만들지 못했어.\n${getFriendlyErrorMessage(error)}`);
  }
}

// 저장된 채팅 하나를 삭제하고 필요하면 새 기본 채팅을 만듭니다.
async function deleteChat(chatId) {
  const chat = state.chats.find((item) => item.id === chatId);
  const confirmed = await confirmDeleteAction({
    title: "채팅을 삭제할까요?",
    message: "이 대화 내용은 목록에서 사라집니다.",
    target: chat?.title || "이 채팅",
  });

  if (!confirmed) {
    return;
  }

  try {
    await deleteChatFromBackend(chatId);
    state.chats = state.chats.filter((item) => item.id !== chatId);

    if (state.currentChatId === chatId) {
      if (state.chats.length > 0) {
        state.currentChatId = state.chats[0].id;
      } else {
        const newChat = await createChatInBackend("New chat");
        state.chats = [newChat];
        state.currentChatId = newChat.id;
      }

      renderCurrentChatMessages();
    }

    renderChatList();
  } catch (error) {
    addMessage("assistant", `채팅을 삭제하지 못했어.\n${getFriendlyErrorMessage(error)}`);
  }
}

function renderLegacyChatList() {
  chatList.innerHTML = "";

  state.chats.forEach((chat) => {
    const item = document.createElement("div");
    item.className = `chat-item ${chat.id === state.currentChatId ? "active" : ""}`;

    const selectBtn = document.createElement("button");
    selectBtn.className = "chat-select";
    selectBtn.title = chat.title;
    selectBtn.addEventListener("click", () => {
      selectChat(chat.id);
    });

    const title = document.createElement("span");
    title.textContent = chat.title || "New chat";
    selectBtn.appendChild(title);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "chat-delete";
    deleteBtn.title = "채팅 삭제";
    deleteBtn.textContent = "×";
    deleteBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteChat(chat.id);
    });

    item.appendChild(selectBtn);
    item.appendChild(deleteBtn);
    chatList.appendChild(item);
  });
}

async function selectProject(projectId, options = {}) {
  const nextProjectId = projectId || "default";
  const previousProjectId = state.projectId;
  const previousFiles = state.files;
  const previousChats = state.chats;
  const previousChatId = state.currentChatId;
  const reloadDocuments = options.reloadDocuments !== false;
  const announce = Boolean(options.announce);

  if (state.operations.answer || state.operations.document) {
    renderProjectOptions();
    showToast("작업이 진행 중이에요. 완료 후 다시 시도해주세요.", "warning");
    return;
  }

  state.projectId = nextProjectId;
  renderProjectOptions();

  if (!reloadDocuments) {
    updateOperationLocks();
    return;
  }

  state.projectLoading = true;
  state.files = [];
  state.chats = [];
  state.currentChatId = null;
  setProjectStatusText(`${getProjectDisplayName(getCurrentProject())} 문서를 불러오는 중...`);
  renderFileList();
  renderChatList();
  renderEmptyChatState();
  updateOperationLocks();

  try {
    await loadDocumentsFromBackend();
    await loadChatsFromBackend();

    if (announce && previousProjectId !== nextProjectId) {
      console.info(`Project switched: ${getProjectDisplayName(getCurrentProject())}`);
    }
  } catch (error) {
    state.projectId = previousProjectId;
    state.files = previousFiles;
    state.chats = previousChats;
    state.currentChatId = previousChatId;
    renderProjectOptions();
    renderFileList();
    renderChatList();
    renderCurrentChatMessages();
    showToast(`프로젝트를 전환하지 못했어요. ${getFriendlyErrorMessage(error)}`, "error");
  } finally {
    state.projectLoading = false;
    setProjectStatusText(`현재 프로젝트: ${getProjectDisplayName(getCurrentProject())}`);
    updateOperationLocks();
  }
}

async function handleProjectCreate() {
  const name = projectNameInput?.value.trim() || "";

  if (!name) {
    showToast("새 프로젝트 이름을 입력해주세요.", "error");
    projectNameInput?.focus();
    return;
  }

  if (state.operations.answer || state.operations.document || state.projectLoading) {
    showToast("작업이 끝난 뒤 새 프로젝트를 만들 수 있어요.", "warning");
    return;
  }

  state.projectLoading = true;
  setProjectStatusText("새 프로젝트를 만드는 중...");
  updateOperationLocks();

  try {
    const project = await createProjectInBackend(name);

    if (projectNameInput) {
      projectNameInput.value = "";
    }

    await loadProjectsFromBackend();
    await selectProject(project.id, { announce: true });
    setProjectPanelOpen(true);
    closeProjectModal();
    showToast(`${project.name || name} 프로젝트를 만들었어요.`, "success");
  } catch (error) {
    showToast(`프로젝트 생성 중 오류가 발생했어요. ${getFriendlyErrorMessage(error)}`, "error");
  } finally {
    state.projectLoading = false;
    updateOperationLocks();
    setProjectStatusText(`현재 프로젝트: ${getProjectDisplayName(getCurrentProject())}`);
  }
}

function formatFileSize(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// textarea 높이를 입력 내용에 맞게 조정합니다.
function autoResizeTextarea() {
  questionInput.style.height = "auto";
  questionInput.style.height = `${questionInput.scrollHeight}px`;
}

// 앱 시작 시 문서, 채팅, 모델 목록을 불러와 초기 화면을 준비합니다.
async function initializeApp() {
  if (appInitialized) {
    return;
  }

  if (!appPrepared) {
    renderChatList();
    renderProjectOptions();
    setProjectPanelOpen(getSavedProjectPanelOpen(), false);
    setMode("fast");
    setAnswerMode("strict_rag");
    appPrepared = true;
  }

  const maxAttempts = isDesktopShell() ? 20 : 1;
  let lastError = null;

  if (isDesktopShell()) {
    setStatusText("앱 서버 연결 중...");
  }

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      await loadProjectsFromBackend();
      await loadDocumentsFromBackend();
      await loadChatsFromBackend();

      try {
        await loadModelsFromBackend();
      } catch (modelError) {
        if (modelStatusText) {
          modelStatusText.textContent = `모델 목록을 불러오지 못했어요: ${getFriendlyErrorMessage(modelError)}`;
        }

        renderModelOptions([], state.defaultModel);
      }
      appInitialized = true;
      setStatusText("로컬 앱 연결 완료");
      return;
    } catch (error) {
      lastError = error;

      if (attempt < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, 600));
      }
    }
  }

  renderFileList();
  addMessage(
    "assistant",
    `백엔드 문서 목록을 불러오지 못했어.\n${getFriendlyErrorMessage(lastError, "앱 서버 연결 실패")}`
  );
  setStatusText("앱 서버 연결 실패");
}

modeButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    setMode(btn.dataset.mode);
  });
});

answerModeButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    setAnswerMode(btn.dataset.answerMode || "strict_rag");
  });
});

if (searchModeSelect) {
  searchModeSelect.addEventListener("change", () => {
    setMode(searchModeSelect.value || "fast");
  });
}

if (answerModeSelect) {
  answerModeSelect.addEventListener("change", () => {
    setAnswerMode(answerModeSelect.value || "strict_rag");
  });
}

if (modelSelect) {
  modelSelect.addEventListener("change", () => {
    setModel(modelSelect.value);
  });
}

if (modelManageBtn) {
  modelManageBtn.addEventListener("click", openModelModal);
}

if (modelModalCloseBtn) {
  modelModalCloseBtn.addEventListener("click", closeModelModal);
}

if (modelModal) {
  const modelBackdrop = modelModal.querySelector(".modal-backdrop");

  if (modelBackdrop) {
    modelBackdrop.addEventListener("click", closeModelModal);
  }
}

if (documentManageBtn) {
  documentManageBtn.addEventListener("click", openDocumentModal);
}

if (documentModalCloseBtn) {
  documentModalCloseBtn.addEventListener("click", closeDocumentModal);
}

if (documentModal) {
  const documentBackdrop = documentModal.querySelector(".modal-backdrop");

  if (documentBackdrop) {
    documentBackdrop.addEventListener("click", closeDocumentModal);
  }
}

documentFilterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setDocumentFilter(button.dataset.documentFilter || "all");
  });
});

if (projectSelect) {
  projectSelect.addEventListener("change", () => {
    selectProject(projectSelect.value, { announce: true });
  });
}

if (projectPanelToggle) {
  projectPanelToggle.addEventListener("click", () => {
    setProjectPanelOpen(!state.projectPanelOpen);
  });
}

if (projectCreateOpenBtn) {
  projectCreateOpenBtn.addEventListener("click", openProjectModal);
}

if (projectModalCloseBtn) {
  projectModalCloseBtn.addEventListener("click", closeProjectModal);
}

if (projectCreateCancelBtn) {
  projectCreateCancelBtn.addEventListener("click", closeProjectModal);
}

if (projectModal) {
  const projectBackdrop = projectModal.querySelector(".modal-backdrop");

  if (projectBackdrop) {
    projectBackdrop.addEventListener("click", closeProjectModal);
  }
}

if (projectCreateBtn) {
  projectCreateBtn.addEventListener("click", handleProjectCreate);
}

if (projectNameInput) {
  projectNameInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleProjectCreate();
    }
  });
}

sendBtn.addEventListener("click", handleSend);

questionInput.addEventListener("input", autoResizeTextarea);

questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    handleSend();
  }
});

if (guideOpenBtn) {
  guideOpenBtn.addEventListener("click", openGuideModal);
}

if (guideCloseBtn) {
  guideCloseBtn.addEventListener("click", closeGuideModal);
}

if (guideModal) {
  const guideBackdrop = guideModal.querySelector(".modal-backdrop");

  if (guideBackdrop) {
    guideBackdrop.addEventListener("click", closeGuideModal);
  }
}

if (deleteConfirmCloseBtn) {
  deleteConfirmCloseBtn.addEventListener("click", () => {
    closeDeleteConfirmModal(false);
  });
}

if (deleteConfirmCancelBtn) {
  deleteConfirmCancelBtn.addEventListener("click", () => {
    closeDeleteConfirmModal(false);
  });
}

if (deleteConfirmSubmitBtn) {
  deleteConfirmSubmitBtn.addEventListener("click", () => {
    closeDeleteConfirmModal(true);
  });
}

if (deleteConfirmModal) {
  const deleteBackdrop = deleteConfirmModal.querySelector(".modal-backdrop");

  if (deleteBackdrop) {
    deleteBackdrop.addEventListener("click", () => {
      closeDeleteConfirmModal(false);
    });
  }
}

uploadOpenBtn.addEventListener("click", openUploadModal);
uploadCloseBtn.addEventListener("click", closeUploadModal);
uploadCancelBtn.addEventListener("click", closeUploadModal);

fileSelectBtn.addEventListener("click", () => {
  fileInput.click();
});

fileInput.addEventListener("change", (event) => {
  addPendingFiles(event.target.files);
});

uploadSubmitBtn.addEventListener("click", handleUploadSubmit);

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragover");
  addPendingFiles(event.dataTransfer.files);
});

newChatBtn.addEventListener("click", createNewChat);
syncBtn.addEventListener("click", syncDocuments);

window.addEventListener("local-rag-api-ready", () => {
  initializeApp();
});

renderEmptyChatState();
initializeApp();
