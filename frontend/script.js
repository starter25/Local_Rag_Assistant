const state = {
  mode: "fast",
  files: [],
  chats: [
    {
      id: Date.now(),
      title: "현재 채팅",
      messages: [],
    },
  ],
};

const messageList = document.getElementById("messageList");
const questionInput = document.getElementById("questionInput");
const sendBtn = document.getElementById("sendBtn");

const modeButtons = document.querySelectorAll(".mode-btn");
const currentModeText = document.getElementById("currentModeText");

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

const API_BASE_URL =
  window.location.protocol === "http:" || window.location.protocol === "https:"
    ? window.location.origin
    : "http://localhost:8000";

function setMode(mode) {
  state.mode = mode;

  modeButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });

  currentModeText.textContent =
    mode.charAt(0).toUpperCase() + mode.slice(1);
}

function addMessage(role, content, sources = []) {
  const message = document.createElement("div");
  message.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "U" : "AI";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;

  if (sources && sources.length > 0) {
    const sourceBox = document.createElement("div");
    sourceBox.className = "source-box";

    const lines = sources.map((source, index) => {
      const page = source.page ? `, page ${source.page}` : "";
      const distance =
        source.distance !== undefined
          ? ` · distance ${Number(source.distance).toFixed(4)}`
          : "";

      const matchedQuery = source.matched_query
        ? ` · query "${source.matched_query}"`
        : "";

      return `[${index + 1}] ${source.source}${page}, chunk ${source.chunk_index}${distance}${matchedQuery}`;
    });

    sourceBox.textContent = `참고 근거\n${lines.join("\n")}`;
    bubble.appendChild(sourceBox);
  }

  message.appendChild(avatar);
  message.appendChild(bubble);
  messageList.appendChild(message);

  messageList.scrollTop = messageList.scrollHeight;
}

function addLoadingMessage(text = "문서를 검색하고 답변을 생성하는 중...") {
  const message = document.createElement("div");
  message.className = "message assistant";
  message.id = "loadingMessage";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "AI";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  message.appendChild(avatar);
  message.appendChild(bubble);
  messageList.appendChild(message);

  messageList.scrollTop = messageList.scrollHeight;
}

function removeLoadingMessage() {
  const loading = document.getElementById("loadingMessage");

  if (loading) {
    loading.remove();
  }
}

async function askBackend(question, mode) {
  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      mode,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || "백엔드 응답 실패");
  }

  return response.json();
}

async function handleSend() {
  const question = questionInput.value.trim();

  if (!question) {
    return;
  }

  addMessage("user", question);
  questionInput.value = "";
  autoResizeTextarea();

  sendBtn.disabled = true;
  addLoadingMessage();

  try {
    const result = await askBackend(question, state.mode);

    removeLoadingMessage();
    addMessage("assistant", result.answer, result.sources || []);
  } catch (error) {
    removeLoadingMessage();
    addMessage("assistant", `답변 생성 중 오류가 발생했어.\n${error.message}`);
  } finally {
    sendBtn.disabled = false;
    questionInput.focus();
  }
}

function openUploadModal() {
  uploadModal.classList.remove("hidden");
  pendingFiles = [];
  renderSelectedFiles();
}

function closeUploadModal() {
  uploadModal.classList.add("hidden");
  pendingFiles = [];
  fileInput.value = "";
  renderSelectedFiles();
}

function addPendingFiles(files) {
  const allowedExtensions = [".pdf", ".txt", ".md", ".docx"];

  const filtered = Array.from(files).filter((file) => {
    const lower = file.name.toLowerCase();

    return allowedExtensions.some((ext) => lower.endsWith(ext));
  });

  pendingFiles = [...pendingFiles, ...filtered];
  renderSelectedFiles();
}

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

async function loadDocumentsFromBackend() {
  const response = await fetch(`${API_BASE_URL}/documents`);

  if (!response.ok) {
    throw new Error("문서 목록 조회 실패");
  }

  const data = await response.json();

  state.files = normalizeDocumentsFromResponse(data);
  renderFileList();
}

function renderFileList() {
  fileList.innerHTML = "";

  if (state.files.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-text";
    empty.textContent = "아직 추가된 문서가 없어.";
    fileList.appendChild(empty);
    return;
  }

  state.files.forEach((doc) => {
    const item = document.createElement("div");
    item.className = "file-item";

    const info = document.createElement("div");
    info.className = "file-info";

    const name = document.createElement("strong");
    name.textContent = doc.source;

    const meta = document.createElement("span");
    meta.className = "file-meta";
    meta.textContent = `chunk ${doc.chunks}개`;

    info.appendChild(name);
    info.appendChild(meta);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "file-delete";
    deleteBtn.textContent = "×";
    deleteBtn.title = "문서 삭제";
    deleteBtn.addEventListener("click", () => {
      removeFile(doc.source);
    });

    item.appendChild(info);
    item.appendChild(deleteBtn);
    fileList.appendChild(item);
  });
}

async function uploadFilesToBackend(files) {
  const formData = new FormData();

  files.forEach((file) => {
    formData.append("files", file);
  });

  const response = await fetch(`${API_BASE_URL}/documents/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || "파일 업로드 실패");
  }

  return response.json();
}

async function handleUploadSubmit() {
  if (pendingFiles.length === 0) {
    closeUploadModal();
    return;
  }

  const uploadCount = pendingFiles.length;

  uploadSubmitBtn.disabled = true;
  uploadSubmitBtn.textContent = "처리 중...";

  try {
    addLoadingMessage("파일을 업로드하고 벡터화하는 중...");

    const data = await uploadFilesToBackend(pendingFiles);

    state.files = normalizeDocumentsFromResponse(data);
    renderFileList();

    removeLoadingMessage();
    closeUploadModal();

    addMessage(
      "assistant",
      `파일 ${uploadCount}개가 추가되었고, ChromaDB 벡터화까지 완료됐어.`
    );
  } catch (error) {
    removeLoadingMessage();
    addMessage("assistant", `파일 업로드 중 오류가 발생했어.\n${error.message}`);
  } finally {
    uploadSubmitBtn.disabled = false;
    uploadSubmitBtn.textContent = "추가하기";
  }
}

async function removeFile(fileName) {
  const confirmed = confirm(`${fileName} 문서를 삭제할까?`);

  if (!confirmed) {
    return;
  }

  try {
    const response = await fetch(
      `${API_BASE_URL}/documents/${encodeURIComponent(fileName)}`,
      {
        method: "DELETE",
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || "파일 삭제 실패");
    }

    const data = await response.json();

    state.files = normalizeDocumentsFromResponse(data);
    renderFileList();

    addMessage("assistant", `${fileName} 문서를 삭제했어.`);
  } catch (error) {
    addMessage("assistant", `파일 삭제 중 오류가 발생했어.\n${error.message}`);
  }
}

async function syncDocuments() {
  syncBtn.disabled = true;
  syncBtn.textContent = "동기화 중";

  try {
    addLoadingMessage("documents 폴더와 ChromaDB를 동기화하는 중...");

    const response = await fetch(`${API_BASE_URL}/documents/sync`, {
      method: "POST",
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || "동기화 실패");
    }

    const data = await response.json();

    state.files = normalizeDocumentsFromResponse(data);
    renderFileList();

    removeLoadingMessage();

    const summary = data.summary || {};

    addMessage(
      "assistant",
      `동기화 완료.\n추가: ${summary.added_count || 0}개\n업데이트: ${summary.updated_count || 0}개\n삭제: ${summary.deleted_count || 0}개\n전체 chunk: ${summary.total_chunks || 0}개`
    );
  } catch (error) {
    removeLoadingMessage();
    addMessage("assistant", `동기화 중 오류가 발생했어.\n${error.message}`);
  } finally {
    syncBtn.disabled = false;
    syncBtn.textContent = "동기화";
  }
}

function createNewChat() {
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

function renderChatList() {
  chatList.innerHTML = "";

  state.chats.forEach((chat, index) => {
    const item = document.createElement("button");
    item.className = `chat-item ${index === state.chats.length - 1 ? "active" : ""}`;
    item.innerHTML = `<span>${chat.title}</span>`;
    chatList.appendChild(item);
  });
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

function autoResizeTextarea() {
  questionInput.style.height = "auto";
  questionInput.style.height = `${questionInput.scrollHeight}px`;
}

async function initializeApp() {
  renderChatList();
  setMode("fast");

  try {
    await loadDocumentsFromBackend();
  } catch (error) {
    renderFileList();
    addMessage(
      "assistant",
      "백엔드 문서 목록을 불러오지 못했어. FastAPI 서버가 켜져 있는지 확인해줘."
    );
  }
}

modeButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    setMode(btn.dataset.mode);
  });
});

sendBtn.addEventListener("click", handleSend);

questionInput.addEventListener("input", autoResizeTextarea);

questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    handleSend();
  }
});

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

initializeApp();
