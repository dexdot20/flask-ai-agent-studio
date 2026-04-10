const bootstrapEl = document.getElementById("app-bootstrap");
const bootstrapData = (() => {
  if (!bootstrapEl) {
    return { settings: {} };
  }
  try {
    return JSON.parse(bootstrapEl.textContent || "{}") || { settings: {} };
  } catch (_) {
    return { settings: {} };
  }
})();

const appSettings = bootstrapData.settings || {};
const knownModelOptions = Array.isArray(appSettings.available_models) ? appSettings.available_models : [];

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("user-input");
const imageInputEl = document.getElementById("image-input");
const docInputEl = document.getElementById("doc-input");
const attachBtn = document.getElementById("attach-btn");
const youtubeUrlBtn = document.getElementById("youtube-url-btn");
const attachmentPreviewEl = document.getElementById("attachment-preview");
const chatAreaEl = document.getElementById("chat-area");
const chatDropOverlay = document.getElementById("chat-drop-overlay");
const summaryNowBtn = document.getElementById("summary-now-btn");
const summaryUndoBtn = document.getElementById("summary-undo-btn");
const kbSyncBtn = document.getElementById("kb-sync-btn");
const kbStatusEl = document.getElementById("kb-status");
const kbDocumentsListEl = document.getElementById("kb-documents-list");
const cancelBtn = document.getElementById("cancel-btn");
const fixBtn = document.getElementById("fix-btn");
const sendBtn = document.getElementById("send-btn");
const modelSel = document.getElementById("model-select");
const mobileModelSel = document.getElementById("mobile-model-select");
const personaSel = document.getElementById("persona-select");
const mobilePersonaSel = document.getElementById("mobile-persona-select");
const emptyState = document.getElementById("empty-state");
const errorArea = document.getElementById("error-area");
const editBanner = document.getElementById("edit-banner");
const editBannerText = document.getElementById("edit-banner-text");
const editBannerCancelBtn = document.getElementById("edit-banner-cancel");
const summaryInspectorBadge = document.getElementById("summary-inspector-badge");
const summaryInspectorHeadline = document.getElementById("summary-inspector-headline");
const summaryInspectorCurrent = document.getElementById("summary-inspector-current");
const summaryInspectorTrigger = document.getElementById("summary-inspector-trigger");
const summaryInspectorGap = document.getElementById("summary-inspector-gap");
const summaryInspectorDetail = document.getElementById("summary-inspector-detail");
const summaryInspectorToolMessages = document.getElementById("summary-inspector-tool-messages");
const summaryInspectorReason = document.getElementById("summary-inspector-reason");
const summaryInspectorLast = document.getElementById("summary-inspector-last");
const canvasToggleBtn = document.getElementById("canvas-toggle-btn");
const memoryToggleBtn = document.getElementById("memory-toggle-btn");
const canvasPanel = document.getElementById("canvas-panel");
const canvasOverlay = document.getElementById("canvas-overlay");
const canvasClose = document.getElementById("canvas-close");
const canvasSearchInput = document.getElementById("canvas-search-input");
const canvasSearchStatus = document.getElementById("canvas-search-status");
const canvasFormatSelect = document.getElementById("canvas-format-select");
const canvasRoleFilter = document.getElementById("canvas-role-filter");
const canvasPathFilter = document.getElementById("canvas-path-filter");
const canvasTreePanel = document.getElementById("canvas-tree-panel");
const canvasTreeCount = document.getElementById("canvas-tree-count");
const canvasTreeEl = document.getElementById("canvas-tree");
const canvasTreeToggleBtn = document.getElementById("canvas-tree-toggle");
const canvasSubtitle = document.getElementById("canvas-subtitle");
const canvasStatus = document.getElementById("canvas-status");
const canvasHint = document.getElementById("canvas-hint");
const canvasDiffEl = document.getElementById("canvas-diff");
const canvasEmptyState = document.getElementById("canvas-empty-state");
const canvasEditorEl = document.getElementById("canvas-editor");
const canvasDocumentEl = document.getElementById("canvas-document");
const canvasWorkspaceMain = canvasDocumentEl?.closest(".canvas-workspace-main") || null;
const canvasDocumentTabsEl = document.getElementById("canvas-document-tabs");
const canvasMetaBar = document.getElementById("canvas-meta-bar");
const canvasMetaChips = document.getElementById("canvas-meta-chips");
const canvasCopyRefBtn = document.getElementById("canvas-copy-ref-btn");
const canvasResetFiltersBtn = document.getElementById("canvas-reset-filters-btn");
const canvasEditBtn = document.getElementById("canvas-edit-btn");
const canvasNewBtn = document.getElementById("canvas-new-btn");
const canvasUploadBtn = document.getElementById("canvas-upload-btn");
const canvasUploadInput = document.getElementById("canvas-upload-input");
const canvasSaveBtn = document.getElementById("canvas-save-btn");
const canvasCancelBtn = document.getElementById("canvas-cancel-btn");
const canvasCopyBtn = document.getElementById("canvas-copy-btn");
const canvasDeleteBtn = document.getElementById("canvas-delete-btn");
const canvasClearBtn = document.getElementById("canvas-clear-btn");
const canvasRenameBtn = document.getElementById("canvas-rename-btn");
const canvasDownloadHtmlBtn = document.getElementById("canvas-download-html-btn");
const canvasDownloadMdBtn = document.getElementById("canvas-download-md-btn");
const canvasDownloadPdfBtn = document.getElementById("canvas-download-pdf-btn");
const canvasMoreBtn = document.getElementById("canvas-more-btn");
const canvasOverflowMenu = document.getElementById("canvas-overflow-menu");
const canvasResizeHandle = document.getElementById("canvas-resize-handle");
const canvasBtnIndicator = document.getElementById("canvas-btn-indicator");
const canvasConfirmModal = document.getElementById("canvas-confirm-modal");
const canvasConfirmOverlay = document.getElementById("canvas-confirm-overlay");
const canvasConfirmTitle = document.getElementById("canvas-confirm-title");
const canvasConfirmMessage = document.getElementById("canvas-confirm-message");
const canvasConfirmOpenBtn = document.getElementById("canvas-confirm-open");
const canvasConfirmLaterBtn = document.getElementById("canvas-confirm-later");
const canvasConfirmCloseBtn = document.getElementById("canvas-confirm-close");
const tokensBadge = document.getElementById("tokens-badge");
const statsPanel = document.getElementById("stats-panel");
const statsOverlay = document.getElementById("stats-overlay");
const statsClose = document.getElementById("stats-close");
const headerEl = document.querySelector("header");
const sidebarList = document.getElementById("sidebar-list");
const sidebarToggleBtn = document.getElementById("sidebar-toggle-btn");
const sidebarOverlay = document.getElementById("sidebar-overlay");
const newChatBtn = document.getElementById("new-chat-btn");
const mobileToolsBtn = document.getElementById("mobile-tools-btn");
const mobileToolsPanel = document.getElementById("mobile-tools-panel");
const mobileToolsOverlay = document.getElementById("mobile-tools-overlay");
const mobileToolsClose = document.getElementById("mobile-tools-close");
const mobileCanvasBtn = document.getElementById("mobile-canvas-btn");
const mobileMemoryBtn = document.getElementById("mobile-memory-btn");
const mobileExportBtn = document.getElementById("mobile-export-btn");
const mobilePruneBtn = document.getElementById("mobile-prune-btn");
const mobileSettingsBtn = document.getElementById("mobile-settings-btn");
const mobileLogoutBtn = document.getElementById("mobile-logout-btn");
const mobileTokensBtn = document.getElementById("mobile-tokens-btn");
const exportPanel = document.getElementById("export-panel");
const exportOverlay = document.getElementById("export-overlay");
const exportClose = document.getElementById("export-close");
const exportSubtitle = document.getElementById("export-subtitle");
const exportStatus = document.getElementById("export-status");
const summaryPanel = document.getElementById("summary-panel");
const summaryOverlay = document.getElementById("summary-overlay");
const summaryClose = document.getElementById("summary-close");
const memoryPanel = document.getElementById("memory-panel");
const memoryOverlay = document.getElementById("memory-overlay");
const memoryClose = document.getElementById("memory-close");
const memorySubtitle = document.getElementById("memory-panel-subtitle");
const memoryStatusEl = document.getElementById("memory-status");
const memoryCountEl = document.getElementById("memory-count");
const memoryListEl = document.getElementById("memory-list");
const memoryAddBtn = document.getElementById("memory-add-btn");
const memoryNewTypeEl = document.getElementById("memory-new-type");
const memoryNewKeyEl = document.getElementById("memory-new-key");
const memoryNewValueEl = document.getElementById("memory-new-value");
const summaryFocusPresetGrid = document.getElementById("summary-focus-presets");
const summaryFocusInput = document.getElementById("summary-focus-input");
const summaryDetailSelect = document.getElementById("summary-detail-select");
const summaryDetailOptionGrid = document.getElementById("summary-detail-options");
const summaryMessageCountInput = document.getElementById("summary-message-count-input");
const summaryAllMessagesCheckbox = document.getElementById("summary-all-messages-checkbox");
const summarySelectionNote = document.getElementById("summary-selection-note");
const summarySettingsNote = document.getElementById("summary-settings-note");
const summarySubmitBtn = document.getElementById("summary-submit-btn");
const summaryPreviewBtn = document.getElementById("summary-preview-btn");
const summaryProgress = document.getElementById("summary-progress");
const summaryProgressLabel = document.getElementById("summary-progress-label");
const summaryProgressValue = document.getElementById("summary-progress-value");
const summaryProgressBar = document.getElementById("summary-progress-bar");
const summaryProgressTrack = summaryProgress?.querySelector(".summary-progress__track") || null;
const summaryPreviewCard = document.getElementById("summary-preview-card");
const summaryPreviewMeta = document.getElementById("summary-preview-meta");
const summaryPreviewList = document.getElementById("summary-preview-list");
const summaryHistoryList = document.getElementById("summary-history-list");
const mobileSummaryBtn = document.getElementById("mobile-summary-btn");
const conversationExportMdBtn = document.getElementById("conversation-export-md-btn");
const conversationExportJsonBtn = document.getElementById("conversation-export-json-btn");
const conversationExportDocxBtn = document.getElementById("conversation-export-docx-btn");
const conversationExportPdfBtn = document.getElementById("conversation-export-pdf-btn");

const SUMMARY_FOCUS_PRESETS = [
  {
    id: "action_items",
    label: "Action items",
    text: "action items, owners, and next steps",
  },
  {
    id: "decisions",
    label: "Decisions",
    text: "decisions made and why they were chosen",
  },
  {
    id: "unresolved_questions",
    label: "Unresolved questions",
    text: "open questions, blockers, and what still needs confirmation",
  },
  {
    id: "risks",
    label: "Risks",
    text: "risks, tradeoffs, and anything that could go wrong",
  },
  {
    id: "key_facts",
    label: "Key facts",
    text: "the most important facts, constraints, and context to retain",
  },
  {
    id: "next_steps",
    label: "Next steps",
    text: "the next concrete steps and the order they should happen in",
  },
];

const SUMMARY_DETAIL_OPTIONS = [
  {
    value: "very_concise",
    label: "Very concise",
    description: "Shortest useful form. Keeps only essentials.",
  },
  {
    value: "concise",
    label: "Concise",
    description: "Keeps high-value facts, decisions, and open questions.",
  },
  {
    value: "balanced",
    label: "Balanced",
    description: "Default choice. Preserves context without adding noise.",
  },
  {
    value: "detailed",
    label: "Detailed",
    description: "Preserves more nuance while staying compact.",
  },
  {
    value: "comprehensive",
    label: "Comprehensive",
    description: "Largest context retention for the least ambiguity.",
  },
];

const SUMMARY_DETAIL_LABELS = Object.fromEntries(
  SUMMARY_DETAIL_OPTIONS.map((option) => [option.value, option.label])
);

const SUMMARY_MODE_LABELS = {
  auto: "Auto",
  conservative: "Conservative",
  aggressive: "Aggressive",
  never: "Never",
};

const SUMMARY_SOURCE_LABELS = {
  conversation_history: "Conversation history",
  summary_history: "Summary history",
};

const CONVERSATION_MEMORY_ENTRY_TYPES = [
  { value: "user_info", label: "User info" },
  { value: "task_context", label: "Task context" },
  { value: "tool_result", label: "Tool result" },
  { value: "decision", label: "Decision" },
];

const CONVERSATION_MEMORY_ENTRY_LABELS = Object.fromEntries(
  CONVERSATION_MEMORY_ENTRY_TYPES.map((entryType) => [entryType.value, entryType.label])
);

if (summaryDetailSelect) {
  summaryDetailSelect.value = String(appSettings.chat_summary_detail_level || "balanced").trim();
}

function setSummaryDetailLevel(value) {
  if (!summaryDetailSelect) {
    return;
  }
  summaryDetailSelect.value = value;
  updateSummaryDetailOptionsState();
}

function updateSummaryDetailOptionsState() {
  const selectedValue = String(summaryDetailSelect?.value || "balanced").trim() || "balanced";
  summaryDetailOptionGrid?.querySelectorAll("[data-summary-detail-value]").forEach((element) => {
    const isSelected = element.getAttribute("data-summary-detail-value") === selectedValue;
    element.classList.toggle("is-active", isSelected);
    element.setAttribute("aria-pressed", String(isSelected));
  });
}

function renderSummaryDetailOptions() {
  if (!summaryDetailOptionGrid) {
    return;
  }

  const fragment = document.createDocumentFragment();
  const selectFragment = document.createDocumentFragment();
  SUMMARY_DETAIL_OPTIONS.forEach((option) => {
    if (summaryDetailSelect) {
      const selectOption = document.createElement("option");
      selectOption.value = option.value;
      selectOption.textContent = option.label;
      selectFragment.append(selectOption);
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "summary-option";
    button.dataset.summaryDetailValue = option.value;
    button.setAttribute("aria-pressed", "false");

    const label = document.createElement("span");
    label.className = "summary-option__label";
    label.textContent = option.label;

    const description = document.createElement("span");
    description.className = "summary-option__description";
    description.textContent = option.description;

    button.append(label, description);
    button.addEventListener("click", () => setSummaryDetailLevel(option.value));
    fragment.append(button);
  });

  summaryDetailSelect?.replaceChildren(selectFragment);
  if (summaryDetailSelect) {
    const preferredValue = String(appSettings.chat_summary_detail_level || "balanced").trim() || "balanced";
    summaryDetailSelect.value = preferredValue;
  }
  summaryDetailOptionGrid.replaceChildren(fragment);
  updateSummaryDetailOptionsState();
}

function getSummaryDetailLabel(value) {
  const normalizedValue = String(value || "balanced").trim() || "balanced";
  return SUMMARY_DETAIL_LABELS[normalizedValue] || SUMMARY_DETAIL_LABELS.balanced;
}

function clearSummaryProgressTimer() {
  if (!summaryProgressTimer) {
    return;
  }
  window.clearInterval(summaryProgressTimer);
  summaryProgressTimer = 0;
}

function setSummaryProgressState(value, label, { visible = true } = {}) {
  const normalizedValue = Math.max(0, Math.min(100, Number(value) || 0));
  summaryProgressCurrentValue = normalizedValue;
  if (summaryProgress) {
    summaryProgress.hidden = !visible;
  }
  if (summaryProgressLabel) {
    summaryProgressLabel.textContent = String(label || "Preparing summary…").trim() || "Preparing summary…";
  }
  if (summaryProgressValue) {
    summaryProgressValue.textContent = `${Math.round(normalizedValue)}%`;
  }
  if (summaryProgressBar) {
    summaryProgressBar.style.width = `${normalizedValue}%`;
  }
  if (summaryProgressTrack) {
    summaryProgressTrack.setAttribute("aria-valuenow", String(Math.round(normalizedValue)));
  }
}

function resetSummaryProgress({ hide = true } = {}) {
  clearSummaryProgressTimer();
  setSummaryProgressState(0, "Preparing summary…", { visible: !hide });
  if (hide && summaryProgress) {
    summaryProgress.hidden = true;
  }
}

function startSummaryProgress(label = "Selecting messages…") {
  clearSummaryProgressTimer();
  setSummaryProgressState(8, label, { visible: true });
  summaryProgressTimer = window.setInterval(() => {
    const nextValue = summaryProgressCurrentValue < 42
      ? summaryProgressCurrentValue + 7
      : summaryProgressCurrentValue < 72
        ? summaryProgressCurrentValue + 4
        : summaryProgressCurrentValue + 2;
    const clampedValue = Math.min(nextValue, 86);
    const nextLabel = clampedValue < 28
      ? "Selecting messages…"
      : clampedValue < 70
        ? "Generating summary…"
        : "Applying summary…";
    setSummaryProgressState(clampedValue, nextLabel, { visible: true });
    if (clampedValue >= 86) {
      clearSummaryProgressTimer();
    }
  }, 220);
}

function finishSummaryProgress(label = "Summary completed.") {
  clearSummaryProgressTimer();
  setSummaryProgressState(100, label, { visible: true });
  window.setTimeout(() => {
    if (!isSummaryOperationInFlight) {
      resetSummaryProgress({ hide: true });
    }
  }, 900);
}

function failSummaryProgress(label = "Summary failed.") {
  clearSummaryProgressTimer();
  const fallbackValue = summaryProgressCurrentValue > 0 ? summaryProgressCurrentValue : 18;
  setSummaryProgressState(fallbackValue, label, { visible: true });
}

function setSummaryBusyState(isBusy) {
  isSummaryOperationInFlight = Boolean(isBusy);
  if (summarySubmitBtn) {
    summarySubmitBtn.disabled = isSummaryOperationInFlight;
  }
  if (summaryPreviewBtn) {
    summaryPreviewBtn.disabled = isSummaryOperationInFlight;
  }
  if (summaryNowBtn) {
    summaryNowBtn.disabled = isSummaryOperationInFlight || !currentConvId;
  }
  if (summaryFocusInput) {
    summaryFocusInput.disabled = isSummaryOperationInFlight;
  }
  if (summaryDetailSelect) {
    summaryDetailSelect.disabled = isSummaryOperationInFlight;
  }
  summaryDetailOptionGrid?.querySelectorAll("[data-summary-detail-value]").forEach((button) => {
    button.disabled = isSummaryOperationInFlight;
  });
  if (summaryMessageCountInput) {
    summaryMessageCountInput.disabled = isSummaryOperationInFlight || !currentConvId;
  }
}

function buildSummaryRequestBody() {
  const requestedMessageCount = parseSummaryMessageCount();
  const requestBody = {
    force: true,
    summary_focus: String(summaryFocusInput?.value || "").trim(),
    summary_detail_level: String(summaryDetailSelect?.value || "balanced").trim(),
  };
  if (summaryAllMessagesCheckbox?.checked === true) {
    requestBody.summarize_all_messages = true;
  }
  if (requestedMessageCount !== null) {
    requestBody.message_count = requestedMessageCount;
  }
  return requestBody;
}

function resetSummaryPreview({ hide = true } = {}) {
  if (summaryPreviewMeta) {
    summaryPreviewMeta.textContent = "Run preview to inspect which messages will be summarized before applying changes.";
  }
  if (summaryPreviewList) {
    summaryPreviewList.innerHTML = "";
  }
  if (summaryPreviewCard) {
    summaryPreviewCard.hidden = hide;
  }
  if (hide) {
    summaryPreviewConversationId = null;
  }
}

function renderSummaryPreview(data) {
  if (!summaryPreviewCard || !summaryPreviewMeta || !summaryPreviewList) {
    return;
  }

  const previewRows = Array.isArray(data?.messages_preview) ? data.messages_preview : [];
  const candidateCount = Number(data?.candidate_message_count || 0);
  const sourceTokens = Number(data?.estimated_source_tokens || 0);
  const promptTokens = Number(data?.estimated_prompt_tokens || 0);
  const sourceKind = SUMMARY_SOURCE_LABELS[String(data?.source_kind || "").trim()] || "Conversation history";
  const detailLevel = getSummaryDetailLabel(data?.detail_level || summaryDetailSelect?.value || "balanced");

  summaryPreviewConversationId = currentConvId;
  summaryPreviewCard.hidden = false;
  summaryPreviewMeta.textContent =
    `${fmt(candidateCount)} selected • ${fmt(sourceTokens)} source tokens • ${fmt(promptTokens)} prompt tokens • ${sourceKind} • ${detailLevel}`;

  if (!previewRows.length) {
    summaryPreviewList.innerHTML = '<div class="summary-preview-empty">No messages are currently eligible for summary with the current options.</div>';
    return;
  }

  const fragment = document.createDocumentFragment();
  previewRows.forEach((entry) => {
    const article = document.createElement("article");
    article.className = "summary-preview-item";

    const header = document.createElement("div");
    header.className = "summary-preview-item__header";

    const roleText = String(entry?.role || "message").trim().toUpperCase();
    const position = Number(entry?.position || 0);
    const title = document.createElement("span");
    title.className = "summary-preview-item__title";
    title.textContent = position > 0 ? `${roleText} #${position}` : roleText;

    const tokenChip = document.createElement("span");
    tokenChip.className = "summary-preview-item__chip";
    tokenChip.textContent = `${fmt(Number(entry?.token_estimate || 0))} tok`;

    header.append(title, tokenChip);

    const content = document.createElement("p");
    content.className = "summary-preview-item__content";
    content.textContent = String(entry?.content_preview || "").trim() || "(empty)";

    article.append(header, content);
    fragment.appendChild(article);
  });

  summaryPreviewList.replaceChildren(fragment);
}

async function refreshSummarySettingsFromServer() {
  try {
    const response = await fetch("/api/settings");
    if (!response.ok) {
      return;
    }
    const data = await response.json().catch(() => null);
    if (!data || typeof data !== "object") {
      return;
    }
    Object.assign(appSettings, {
      chat_summary_mode: data.chat_summary_mode,
      chat_summary_detail_level: data.chat_summary_detail_level,
      chat_summary_trigger_token_count: data.chat_summary_trigger_token_count,
      summary_skip_first: data.summary_skip_first,
      summary_skip_last: data.summary_skip_last,
    });
    setSummaryDetailLevel(String(appSettings.chat_summary_detail_level || "balanced").trim() || "balanced");
    renderSummaryInspector();
  } catch (_) {
    // Ignore settings refresh failures and keep the bootstrapped values.
  }
}

function applySummaryFocusPreset(preset) {
  if (!summaryFocusInput || !preset) {
    return;
  }
  summaryFocusInput.value = preset.text;
  autoResize(summaryFocusInput);
  summaryFocusInput.focus({ preventScroll: true });
}

function renderSummaryFocusPresets() {
  if (!summaryFocusPresetGrid) {
    return;
  }

  const fragment = document.createDocumentFragment();
  SUMMARY_FOCUS_PRESETS.forEach((preset) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "summary-preset";
    button.textContent = preset.label;
    button.title = preset.text;
    button.addEventListener("click", () => applySummaryFocusPreset(preset));
    fragment.append(button);
  });

  summaryFocusPresetGrid.replaceChildren(fragment);
}

renderSummaryFocusPresets();
renderSummaryDetailOptions();

let history = [];
let isStreaming = false;
let isFixing = false;
let currentConvId = null;
let currentConvTitle = "New Chat";
let currentConversationPersonaId = null;
let conversationMemoryEntries = [];
let conversationMemoryEnabled = false;
let activeAbortController = null;
let activeAssistantStreamingBubble = null;
let activeAssistantStreamingHasVisibleAnswer = false;
let selectedImageFiles = [];
let selectedDocumentFiles = [];
let selectedDocumentSubmissionModes = new Map();
const attachmentFileKeyByObject = new WeakMap();
let nextAttachmentFileKeyId = 1;
let selectedYouTubeUrl = "";
let pendingDocumentCanvasOpen = null;
let editingMessageId = null;
let inlineEditingMessageId = null;
let inlineEditingDraft = "";
let savingEditedMessageId = null;
let pendingDeleteMessageId = null;
let deletingMessageId = null;
let activeDeleteMessageAbortController = null;
let activeCanvasDocumentId = null;
let streamingCanvasDocuments = [];
let isCanvasEditing = false;
let editingCanvasDocumentId = null;
let pendingCanvasDiff = null;
let canvasPageByDocumentId = new Map();
let pendingCanvasPageSyncFrame = 0;
let canvasHasUnreadUpdates = false;
let lastCanvasTriggerEl = null;
let lastCanvasConfirmTriggerEl = null;
let lastExportTriggerEl = null;
let lastSummaryTriggerEl = null;
let lastMemoryTriggerEl = null;
let streamingCanvasPreviews = new Map();
let pendingCanvasPreviewTimer = 0;
let pendingCanvasEditorPreviewTimer = 0;
let lastCanvasStructureSignature = "";
let latestSummaryStatus = null;
let isSummaryOperationInFlight = false;
let summaryProgressTimer = 0;
let summaryProgressCurrentValue = 0;
let summaryPreviewConversationId = null;
let conversationRefreshGeneration = 0;
let pendingConversationRefreshTimers = new Set();
let lastConversationSignature = "";
let lastConversationMemorySignature = "";
let userScrolledUp = false;
let pendingCanvasConfirmAction = null;
let pendingCanvasMutation = "";

const CANVAS_EMPTY_STATES = Object.freeze({
  no_documents: Object.freeze({
    title: "No canvas document yet",
    message: "Create a blank file with New file, upload an existing text file, or ask the assistant to draft something substantial and keep refining it with line-based edits.",
  }),
  no_matches: Object.freeze({
    title: "No files match the current filters",
    message: "Adjust the search term, role, or path filter to bring files back into view.",
  }),
});

const CANVAS_MUTATION_LABELS = Object.freeze({
  create: "file creation",
  upload: "file upload",
  delete: "file deletion",
  clear: "canvas clearing",
  rename: "rename",
  save: "save",
});

function renderConversationMemoryTypeOptions() {
  if (!memoryNewTypeEl) {
    return;
  }

  const fragment = document.createDocumentFragment();
  CONVERSATION_MEMORY_ENTRY_TYPES.forEach((entryType) => {
    const option = document.createElement("option");
    option.value = entryType.value;
    option.textContent = entryType.label;
    fragment.append(option);
  });
  memoryNewTypeEl.replaceChildren(fragment);
  if (!memoryNewTypeEl.value) {
    memoryNewTypeEl.value = CONVERSATION_MEMORY_ENTRY_TYPES[0]?.value || "user_info";
  }
}

function normalizeConversationMemoryEntry(entry) {
  const normalizedId = Number(entry?.id);
  const normalizedMessageId = Number(entry?.message_id);
  return {
    id: Number.isInteger(normalizedId) && normalizedId > 0 ? normalizedId : null,
    conversation_id: Number.isInteger(Number(entry?.conversation_id)) ? Number(entry?.conversation_id) : null,
    message_id: Number.isInteger(normalizedMessageId) && normalizedMessageId > 0 ? normalizedMessageId : null,
    entry_type: String(entry?.entry_type || "").trim().toLowerCase(),
    key: String(entry?.key || "").trim(),
    value: String(entry?.value || "").trim(),
    created_at: String(entry?.created_at || "").trim(),
  };
}

function getConversationMemoryEntryLabel(entryType) {
  const normalizedEntryType = String(entryType || "").trim().toLowerCase();
  return CONVERSATION_MEMORY_ENTRY_LABELS[normalizedEntryType] || normalizedEntryType || "Entry";
}

function getConversationMemorySignature(entries) {
  return JSON.stringify(
    (Array.isArray(entries) ? entries : []).map((entry) => [
      Number.isInteger(Number(entry?.id)) ? Number(entry.id) : null,
      String(entry?.entry_type || "").trim().toLowerCase(),
      String(entry?.key || "").trim(),
      String(entry?.value || "").trim(),
      Number.isInteger(Number(entry?.message_id)) ? Number(entry.message_id) : null,
      String(entry?.created_at || "").trim(),
    ])
  );
}

function syncMemoryToggleButton() {
  if (!memoryToggleBtn) {
    return;
  }
  memoryToggleBtn.setAttribute("aria-expanded", String(isMemoryPanelOpen()));
}

function setMemoryStatus(message, tone = "muted") {
  if (!memoryStatusEl) {
    return;
  }
  memoryStatusEl.textContent = String(message || "").trim() || "Waiting for a conversation.";
  memoryStatusEl.dataset.tone = tone;
}

function setMemoryFormDisabled(disabled) {
  [memoryNewTypeEl, memoryNewKeyEl, memoryNewValueEl, memoryAddBtn].forEach((element) => {
    if (element) {
      element.disabled = Boolean(disabled);
    }
  });
}

function setMemoryPanelBusy(card, busy) {
  if (!card) {
    return;
  }
  card.querySelectorAll("button, input, textarea, select").forEach((element) => {
    if (element.id === "memory-close") {
      return;
    }
    element.disabled = Boolean(busy);
  });
}

function renderConversationMemoryPanel() {
  if (memoryNewTypeEl && memoryNewTypeEl.options.length === 0) {
    renderConversationMemoryTypeOptions();
  }

  if (!memoryPanel) {
    return;
  }

  const hasConversation = Boolean(currentConvId);
  const isEditable = hasConversation && conversationMemoryEnabled;
  const entryCount = conversationMemoryEntries.length;

  if (memorySubtitle) {
    memorySubtitle.textContent = hasConversation
      ? `Current conversation: ${currentConvTitle || `Chat #${currentConvId}`}`
      : "Open or create a conversation to view and manage memory entries.";
  }

  if (memoryCountEl) {
    memoryCountEl.textContent = `${entryCount} entr${entryCount === 1 ? "y" : "ies"}`;
  }

  if (!conversationMemoryEnabled) {
    setMemoryStatus("Conversation memory is disabled in Settings.", "warning");
  } else if (!hasConversation) {
    setMemoryStatus("Open a conversation to view memory entries.", "muted");
  } else {
    setMemoryStatus(entryCount ? "Edit, save, or delete the entries below." : "No memory entries yet. Add one below.", entryCount ? "success" : "muted");
  }

  setMemoryFormDisabled(!isEditable);

  if (!memoryListEl) {
    return;
  }

  const fragment = document.createDocumentFragment();
  if (!entryCount) {
    const empty = document.createElement("p");
    empty.className = "memory-empty";
    empty.textContent = hasConversation
      ? "This conversation does not have any memory entries yet."
      : "Open a conversation to manage its memory entries.";
    fragment.append(empty);
    memoryListEl.replaceChildren(fragment);
    return;
  }

  conversationMemoryEntries.forEach((entry, index) => {
    const card = document.createElement("article");
    card.className = "memory-entry";
    card.dataset.entryId = String(entry.id || "");
    card.dataset.entryIndex = String(index + 1);

    const header = document.createElement("div");
    header.className = "memory-entry__header";

    const meta = document.createElement("div");
    meta.className = "memory-entry__meta";

    const title = document.createElement("div");
    title.className = "memory-entry__title";

    const badge = document.createElement("span");
    badge.className = "memory-entry__badge";
    badge.textContent = getConversationMemoryEntryLabel(entry.entry_type);
    title.append(badge);

    const entryIndexLabel = document.createElement("span");
    entryIndexLabel.textContent = `#${index + 1}`;
    entryIndexLabel.title = entry.id ? `Record ID #${entry.id}` : "Record ID unavailable";
    title.append(entryIndexLabel);

    meta.append(title);

    const timestamp = document.createElement("div");
    timestamp.className = "memory-entry__timestamp";
    timestamp.textContent = entry.created_at ? `Created ${entry.created_at}` : "Created time unavailable";
    meta.append(timestamp);

    if (entry.message_id) {
      const linked = document.createElement("div");
      linked.className = "memory-entry__linked";
      linked.textContent = `Linked to message #${entry.message_id}`;
      meta.append(linked);
    }

    header.append(meta);

    const actions = document.createElement("div");
    actions.className = "memory-entry__actions";

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "btn-primary";
    saveBtn.textContent = "Save";

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "btn-ghost";
    deleteBtn.textContent = "Delete";

    actions.append(saveBtn, deleteBtn);
    header.append(actions);
    card.append(header);

    const grid = document.createElement("div");
    grid.className = "memory-entry__grid";

    const typeField = document.createElement("label");
    typeField.className = "summary-field";
    const typeLabel = document.createElement("span");
    typeLabel.textContent = "Type";
    const typeSelect = document.createElement("select");
    typeSelect.className = "summary-input";
    CONVERSATION_MEMORY_ENTRY_TYPES.forEach((entryType) => {
      const option = document.createElement("option");
      option.value = entryType.value;
      option.textContent = entryType.label;
      typeSelect.append(option);
    });
    typeSelect.value = entry.entry_type || CONVERSATION_MEMORY_ENTRY_TYPES[0]?.value || "user_info";
    typeField.append(typeLabel, typeSelect);

    const keyField = document.createElement("label");
    keyField.className = "summary-field";
    const keyLabel = document.createElement("span");
    keyLabel.textContent = "Key";
    const keyInput = document.createElement("input");
    keyInput.className = "summary-input";
    keyInput.type = "text";
    keyInput.maxLength = 120;
    keyInput.value = entry.key || "";
    keyField.append(keyLabel, keyInput);

    const valueField = document.createElement("label");
    valueField.className = "summary-field memory-field--wide";
    const valueLabel = document.createElement("span");
    valueLabel.textContent = "Value";
    const valueInput = document.createElement("textarea");
    valueInput.rows = 3;
    valueInput.value = entry.value || "";
    valueField.append(valueLabel, valueInput);

    grid.append(typeField, keyField, valueField);
    card.append(grid);

    const setCardBusy = (busy) => {
      [saveBtn, deleteBtn, typeSelect, keyInput, valueInput].forEach((element) => {
        element.disabled = Boolean(busy);
      });
    };

    saveBtn.addEventListener("click", () => {
      void updateConversationMemoryFromCard(card, {
        entryId: entry.id,
        typeSelect,
        keyInput,
        valueInput,
        saveBtn,
        deleteBtn,
        setCardBusy,
      });
    });

    deleteBtn.addEventListener("click", () => {
      void deleteConversationMemoryFromCard(card, entry.id, { saveBtn, deleteBtn, setCardBusy });
    });

    if (!isEditable) {
      setCardBusy(true);
    }

    fragment.append(card);
  });

  memoryListEl.replaceChildren(fragment);
}

function applyConversationMemoryState(data) {
  conversationMemoryEnabled = data?.conversation_memory_enabled !== false;
  conversationMemoryEntries = conversationMemoryEnabled && Array.isArray(data?.memory)
    ? data.memory.map(normalizeConversationMemoryEntry).filter((entry) => entry.id !== null && entry.key && entry.value)
    : [];
  lastConversationMemorySignature = getConversationMemorySignature(conversationMemoryEntries);
  renderConversationMemoryPanel();
}

function isMemoryPanelOpen() {
  return Boolean(memoryPanel?.classList.contains("open"));
}

function openMemoryPanel(triggerEl = null) {
  closeMobileTools();
  closeStats();
  closeCanvas();
  closeExportPanel();
  closeSummaryPanel();
  memoryPanel?.classList.add("open");
  memoryOverlay?.classList.add("open");
  memoryPanel?.setAttribute("aria-hidden", "false");
  syncMemoryToggleButton();
  lastMemoryTriggerEl = triggerEl instanceof HTMLElement
    ? triggerEl
    : (document.activeElement instanceof HTMLElement ? document.activeElement : memoryToggleBtn);
  renderConversationMemoryPanel();
  window.setTimeout(() => {
    if (memoryNewKeyEl && !memoryNewKeyEl.disabled) {
      memoryNewKeyEl.focus({ preventScroll: true });
      memoryNewKeyEl.select();
    } else {
      memoryClose?.focus();
    }
  }, 0);
}

function closeMemoryPanel({ restoreFocus = true } = {}) {
  memoryPanel?.classList.remove("open");
  memoryOverlay?.classList.remove("open");
  memoryPanel?.setAttribute("aria-hidden", "true");
  syncMemoryToggleButton();
  if (restoreFocus && lastMemoryTriggerEl && typeof lastMemoryTriggerEl.focus === "function") {
    lastMemoryTriggerEl.focus();
  }
}

async function updateConversationMemoryFromCard(card, { entryId, typeSelect, keyInput, valueInput, saveBtn, deleteBtn, setCardBusy }) {
  if (!currentConvId || !conversationMemoryEnabled) {
    showToast("Open a conversation before editing memory.", "warning");
    return;
  }

  const entryType = String(typeSelect?.value || "").trim();
  const key = String(keyInput?.value || "").trim();
  const value = String(valueInput?.value || "").trim();
  if (!key || !value) {
    showToast("Memory key and value are required.", "warning");
    return;
  }

  const payload = {
    entry_type: entryType,
    key,
    value,
  };

  setCardBusy(true);
  if (saveBtn) {
    saveBtn.disabled = true;
  }
  if (deleteBtn) {
    deleteBtn.disabled = true;
  }

  try {
    const response = await fetch(`/api/conversations/${currentConvId}/memory/${entryId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(data?.error || "Unable to update memory entry.");
    }

    applyConversationMemoryState(data);
    await loadSidebar();
    showToast("Memory entry updated.", "success");
  } catch (error) {
    showError(error.message || "Unable to update memory entry.");
    setCardBusy(false);
  }
}

async function deleteConversationMemoryFromCard(card, entryId, { saveBtn, deleteBtn, setCardBusy }) {
  if (!currentConvId || !conversationMemoryEnabled) {
    showToast("Open a conversation before editing memory.", "warning");
    return;
  }

  if (!window.confirm(`Delete memory entry #${entryId}?`)) {
    return;
  }

  setCardBusy(true);
  if (saveBtn) {
    saveBtn.disabled = true;
  }
  if (deleteBtn) {
    deleteBtn.disabled = true;
  }

  try {
    const response = await fetch(`/api/conversations/${currentConvId}/memory/${entryId}`, {
      method: "DELETE",
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(data?.error || "Unable to delete memory entry.");
    }

    applyConversationMemoryState(data);
    await loadSidebar();
    showToast("Memory entry deleted.", "success");
  } catch (error) {
    showError(error.message || "Unable to delete memory entry.");
    setCardBusy(false);
  }
}

async function createConversationMemoryEntry() {
  if (!currentConvId || !conversationMemoryEnabled) {
    showToast("Open a conversation before editing memory.", "warning");
    return;
  }

  const entryType = String(memoryNewTypeEl?.value || "user_info").trim() || "user_info";
  const key = String(memoryNewKeyEl?.value || "").trim();
  const value = String(memoryNewValueEl?.value || "").trim();
  if (!key || !value) {
    showToast("Memory key and value are required.", "warning");
    return;
  }

  if (memoryAddBtn) {
    memoryAddBtn.disabled = true;
  }
  setMemoryFormDisabled(true);

  try {
    const response = await fetch(`/api/conversations/${currentConvId}/memory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entry_type: entryType, key, value }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(data?.error || "Unable to save memory entry.");
    }

    applyConversationMemoryState(data);
    await loadSidebar();
    if (memoryNewKeyEl) {
      memoryNewKeyEl.value = "";
    }
    if (memoryNewValueEl) {
      memoryNewValueEl.value = "";
    }
    if (memoryNewTypeEl) {
      memoryNewTypeEl.value = entryType;
    }
    showToast("Memory entry saved.", "success");
  } catch (error) {
    showError(error.message || "Unable to save memory entry.");
  } finally {
    setMemoryFormDisabled(!currentConvId || !conversationMemoryEnabled);
  }
}

renderConversationMemoryTypeOptions();
const DEFAULT_CANVAS_CONFIRM_LABEL = "Open Canvas";
const DEFAULT_CANVAS_CONFIRM_CANCEL_LABEL = "Later";
let activeSidebarRename = null;
let collapsedCanvasFolders = new Set();
let lastCanvasTreeTypeAheadValue = "";
let lastCanvasTreeTypeAheadAt = 0;
let nextToastId = 1;
let activeToastTimers = new Map();
let chatDragDepth = 0;
let isCanvasMobileTreeOpen = false;
const featureFlags = bootstrapData.features || appSettings.features || {};
conversationMemoryEnabled = featureFlags.conversation_memory_enabled !== false;
if (youtubeUrlBtn && !Boolean(featureFlags.youtube_transcripts_enabled)) {
  youtubeUrlBtn.hidden = true;
}
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const MAX_DOCUMENT_BYTES = 20 * 1024 * 1024;
const ALLOWED_DOCUMENT_TYPES = new Set([
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/pdf",
  "text/plain",
  "text/csv",
  "text/markdown",
]);
const DOCUMENT_EXTENSIONS = new Set([".docx", ".pdf", ".txt", ".csv", ".md"]);
const VISUAL_PDF_PAGE_LIMIT = 3;
const STREAM_RENDER_FALLBACK_INTERVAL_MS = 16;
const CANVAS_PANEL_WIDTH_STORAGE_KEY = "chatbot.canvasPanelWidth";
const MODEL_PREFERENCE_STORAGE_KEY = "chatbot.selectedModel";
const CANVAS_PANEL_DEFAULT_WIDTH = 620;
const CANVAS_PANEL_MIN_WIDTH = 420;
const CANVAS_PANEL_MAX_WIDTH = 1100;
const CANVAS_ROOT_PATH_FILTER = "__root__";
const CANVAS_PREVIEW_RENDER_INTERVAL_MS = 32;
const CANVAS_CODE_FILE_EXTENSIONS = new Set([
  ".bat",
  ".c",
  ".cc",
  ".cfg",
  ".conf",
  ".cpp",
  ".cs",
  ".css",
  ".env",
  ".go",
  ".h",
  ".hpp",
  ".html",
  ".ini",
  ".java",
  ".js",
  ".json",
  ".jsx",
  ".kt",
  ".kts",
  ".less",
  ".lua",
  ".mjs",
  ".php",
  ".ps1",
  ".py",
  ".rb",
  ".rs",
  ".sass",
  ".scss",
  ".sh",
  ".sql",
  ".swift",
  ".toml",
  ".ts",
  ".tsx",
  ".vue",
  ".xml",
  ".yaml",
  ".yml",
  ".zsh",
]);

function isDocumentFile(file) {
  if (ALLOWED_DOCUMENT_TYPES.has(file.type)) return true;
  const ext = (file.name || "").toLowerCase().match(/\.[^.]+$/);
  return ext ? DOCUMENT_EXTENSIONS.has(ext[0]) : false;
}

function isPdfDocumentFile(file) {
  if (!file) {
    return false;
  }
  if (String(file.type || "").trim().toLowerCase() === "application/pdf") {
    return true;
  }
  return /\.pdf$/i.test(String(file.name || "").trim());
}

function getDocumentSubmissionMode(file) {
  if (!isPdfDocumentFile(file)) {
    return "text";
  }
  const fileKey = getAttachmentFileKey(file);
  return selectedDocumentSubmissionModes.get(fileKey) === "visual" ? "visual" : "text";
}

function setDocumentSubmissionMode(file, mode) {
  if (!file) {
    return;
  }
  const fileKey = getAttachmentFileKey(file);
  if (!fileKey) {
    return;
  }
  selectedDocumentSubmissionModes.set(fileKey, mode === "visual" ? "visual" : "text");
}

function syncSelectedDocumentSubmissionModes() {
  const nextModes = new Map();
  selectedDocumentFiles.forEach((file) => {
    const fileKey = getAttachmentFileKey(file);
    if (!fileKey) {
      return;
    }
    if (!isPdfDocumentFile(file)) {
      nextModes.set(fileKey, "text");
      return;
    }
    nextModes.set(fileKey, selectedDocumentSubmissionModes.get(fileKey) === "visual" ? "visual" : "text");
  });
  selectedDocumentSubmissionModes = nextModes;
}

function getAttachmentDeduplicationKey(file) {
  return [file?.name || "", file?.size || 0, file?.type || "", file?.lastModified || 0].join("::");
}

function getAttachmentFileKey(file) {
  if (!file || (typeof file !== "object" && typeof file !== "function")) {
    return "";
  }

  const existingKey = attachmentFileKeyByObject.get(file);
  if (existingKey) {
    return existingKey;
  }

  const nextKey = [
    "attachment",
    nextAttachmentFileKeyId,
    file?.name || "",
    file?.size || 0,
    file?.type || "",
    file?.lastModified || 0,
  ].join("::");
  nextAttachmentFileKeyId += 1;
  attachmentFileKeyByObject.set(file, nextKey);
  return nextKey;
}

function dedupeFiles(files) {
  const deduped = [];
  const seen = new Set();
  (files || []).forEach((file) => {
    if (!file) {
      return;
    }
    const key = getAttachmentDeduplicationKey(file);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    deduped.push(file);
  });
  return deduped;
}

function hasDraggedFiles(dataTransfer) {
  return Array.from(dataTransfer?.types || []).includes("Files");
}

function normalizeMessageAttachment(entry) {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const kind = String(entry.kind || "").trim().toLowerCase();
  if (kind !== "image" && kind !== "document" && kind !== "video") {
    return null;
  }

  if (kind === "image") {
    const imageId = String(entry.image_id || "").trim();
    const imageName = String(entry.image_name || "").trim();
    if (!imageId && !imageName) {
      return null;
    }
    return {
      kind,
      image_id: imageId,
      image_name: imageName,
      image_mime_type: String(entry.image_mime_type || "").trim(),
      analysis_method: String(entry.analysis_method || "").trim(),
      ocr_text: String(entry.ocr_text || "").trim(),
      vision_summary: String(entry.vision_summary || "").trim(),
      assistant_guidance: String(entry.assistant_guidance || "").trim(),
      key_points: Array.isArray(entry.key_points) ? entry.key_points.filter(Boolean).map((value) => String(value)) : [],
    };
  }

  const fileId = String(entry.file_id || "").trim();
  const fileName = String(entry.file_name || "").trim();
  if (!fileId && !fileName) {
    if (kind !== "video") {
      return null;
    }
  }

  if (kind === "video") {
    const videoId = String(entry.video_id || "").trim();
    const videoTitle = String(entry.video_title || "").trim();
    const videoUrl = String(entry.video_url || "").trim();
    if (!videoId && !videoUrl) {
      return null;
    }
    return {
      kind,
      video_id: videoId,
      video_title: videoTitle,
      video_url: videoUrl,
      video_platform: String(entry.video_platform || "").trim(),
      transcript_context_block: String(entry.transcript_context_block || "").trim(),
      transcript_language: String(entry.transcript_language || "").trim(),
      transcript_text_truncated: entry.transcript_text_truncated === true,
    };
  }

  return {
    kind,
    file_id: fileId,
    file_name: fileName,
    file_mime_type: String(entry.file_mime_type || "").trim(),
    file_text_truncated: entry.file_text_truncated === true,
    file_context_block: String(entry.file_context_block || "").trim(),
  };
}

function getAttachmentIdentityKeys(attachment) {
  if (!attachment || typeof attachment !== "object") {
    return [];
  }

  if (attachment.kind === "image") {
    return [attachment.image_id, attachment.image_name].map((value) => String(value || "").trim()).filter(Boolean);
  }

  if (attachment.kind === "document") {
    return [attachment.file_id, attachment.file_name].map((value) => String(value || "").trim()).filter(Boolean);
  }

  if (attachment.kind === "video") {
    return [attachment.video_id, attachment.video_url].map((value) => String(value || "").trim()).filter(Boolean);
  }

  return [];
}

function getMessageAttachments(metadata) {
  if (!metadata || typeof metadata !== "object") {
    return [];
  }

  const attachments = [];
  const seen = new Set();

  const appendAttachment = (entry) => {
    const normalized = normalizeMessageAttachment(entry);
    if (!normalized) {
      return;
    }
    const identityKeys = getAttachmentIdentityKeys(normalized);
    if (identityKeys.some((key) => seen.has(key))) {
      return;
    }
    identityKeys.forEach((key) => seen.add(key));
    attachments.push(normalized);
  };

  if (Array.isArray(metadata.attachments)) {
    metadata.attachments.forEach((entry) => appendAttachment(entry));
  }
  appendAttachment({
    kind: "image",
    image_id: metadata.image_id,
    image_name: metadata.image_name,
    image_mime_type: metadata.image_mime_type,
    analysis_method: metadata.analysis_method,
    ocr_text: metadata.ocr_text,
    vision_summary: metadata.vision_summary,
    assistant_guidance: metadata.assistant_guidance,
    key_points: metadata.key_points,
  });
  appendAttachment({
    kind: "document",
    file_id: metadata.file_id,
    file_name: metadata.file_name,
    file_mime_type: metadata.file_mime_type,
    file_text_truncated: metadata.file_text_truncated === true,
    file_context_block: metadata.file_context_block,
  });
  appendAttachment({
    kind: "video",
    video_id: metadata.video_id,
    video_title: metadata.video_title,
    video_url: metadata.video_url,
    video_platform: metadata.video_platform,
    transcript_context_block: metadata.transcript_context_block,
    transcript_language: metadata.transcript_language,
    transcript_text_truncated: metadata.transcript_text_truncated === true,
  });

  return attachments;
}

function buildLegacyAttachmentMetadata(attachments) {
  const legacy = {};
  const primaryImage = (attachments || []).find((entry) => entry.kind === "image") || null;
  const primaryDocument = (attachments || []).find((entry) => entry.kind === "document") || null;

  if (primaryImage) {
    if (primaryImage.image_id) legacy.image_id = primaryImage.image_id;
    if (primaryImage.image_name) legacy.image_name = primaryImage.image_name;
    if (primaryImage.image_mime_type) legacy.image_mime_type = primaryImage.image_mime_type;
    if (primaryImage.analysis_method) legacy.analysis_method = primaryImage.analysis_method;
    if (primaryImage.ocr_text) legacy.ocr_text = primaryImage.ocr_text;
    if (primaryImage.vision_summary) legacy.vision_summary = primaryImage.vision_summary;
    if (primaryImage.assistant_guidance) legacy.assistant_guidance = primaryImage.assistant_guidance;
    if (primaryImage.key_points?.length) legacy.key_points = [...primaryImage.key_points];
  }

  if (primaryDocument) {
    if (primaryDocument.file_id) legacy.file_id = primaryDocument.file_id;
    if (primaryDocument.file_name) legacy.file_name = primaryDocument.file_name;
    if (primaryDocument.file_mime_type) legacy.file_mime_type = primaryDocument.file_mime_type;
    if (primaryDocument.file_text_truncated) legacy.file_text_truncated = true;
  }

  const contextBlocks = (attachments || [])
    .filter((entry) => entry.kind === "document" && entry.file_context_block)
    .map((entry) => entry.file_context_block);
  if (contextBlocks.length) {
    legacy.file_context_block = contextBlocks.join("\n\n");
  }

  return legacy;
}

function mergeAttachmentMetadata(metadata, attachment) {
  const base = metadata && typeof metadata === "object" ? { ...metadata } : {};
  const blockedKeys = [
    "attachments",
    "image_id",
    "image_name",
    "image_mime_type",
    "analysis_method",
    "ocr_text",
    "vision_summary",
    "assistant_guidance",
    "key_points",
    "file_id",
    "file_name",
    "file_mime_type",
    "file_text_truncated",
    "file_context_block",
    "video_id",
    "video_title",
    "video_url",
    "video_platform",
    "transcript_context_block",
    "transcript_language",
    "transcript_text_truncated",
  ];
  blockedKeys.forEach((key) => delete base[key]);

  const attachments = getMessageAttachments(metadata);
  const normalized = normalizeMessageAttachment(attachment);
  const nextAttachments = normalized
    ? [...attachments.filter((entry) => {
        if (entry.kind !== normalized.kind) {
          return true;
        }
        const entryKeys = getAttachmentIdentityKeys(entry);
        const normalizedKeys = getAttachmentIdentityKeys(normalized);
        return !entryKeys.some((key) => normalizedKeys.includes(key));
      }), normalized]
    : attachments;

  return {
    ...base,
    ...(nextAttachments.length ? { attachments: nextAttachments } : {}),
    ...buildLegacyAttachmentMetadata(nextAttachments),
  };
}

function buildPendingAttachmentMetadata(imageFiles, documentFiles, youtubeUrl = "") {
  const attachments = [
    ...(imageFiles || []).map((file) => ({ kind: "image", image_name: file.name })),
    ...(documentFiles || []).map((file) => ({
      kind: "document",
      file_name: file.name,
      submission_mode: getDocumentSubmissionMode(file),
      canvas_mode: getDocumentSubmissionMode(file) === "visual" ? "preview_only" : "editable",
    })),
    ...(youtubeUrl ? [{ kind: "video", video_url: youtubeUrl, video_title: "YouTube video" }] : []),
  ];
  return attachments.length
    ? {
        attachments,
        ...buildLegacyAttachmentMetadata(getMessageAttachments({ attachments })),
      }
    : null;
}

function sanitizeEditedUserMetadata(metadata) {
  const attachments = getMessageAttachments(metadata);
  if (!attachments.length) {
    return null;
  }

  return {
    attachments,
    ...buildLegacyAttachmentMetadata(attachments),
  };
}
const ragDisabledNoteEl = document.getElementById("rag-disabled-note");
const visionDisabledNoteEl = document.getElementById("vision-disabled-note");
const RAG_SENSITIVITY_HINTS = {
  flexible: "Flexible: lower threshold around 0.20, so the system injects broader matches.",
  normal: "Normal: balanced matching with an approximate threshold of 0.35.",
  strict: "Strict: higher threshold around 0.55, so only stronger matches are injected.",
};

const markdownEngine = globalThis.marked || null;
const sanitizer = globalThis.DOMPurify || null;
const highlighter = globalThis.hljs || null;
const SIDEBAR_STORAGE_KEY = "chatbot.sidebarOpen";
const CLARIFICATION_DRAFT_STORAGE_PREFIX = "chatbot.clarificationDraft";
const CANVAS_STREAMING_PREVIEW_TOOLS = new Set(["create_canvas_document", "rewrite_canvas_document", "batch_canvas_edits", "transform_canvas_lines", "replace_canvas_lines", "insert_canvas_lines", "delete_canvas_lines"]);
const CANVAS_EDIT_PREVIEW_TOOLS = new Set(["batch_canvas_edits", "transform_canvas_lines", "replace_canvas_lines", "insert_canvas_lines", "delete_canvas_lines"]);
const CANVAS_PAGE_HEADING_TEXT_RE = /^Page\s+(\d+)$/i;
const PENDING_CANVAS_UPLOAD_PREVIEW_KEY = "pending-canvas-upload";

function isCanvasStreamingPreviewTool(toolName) {
  return CANVAS_STREAMING_PREVIEW_TOOLS.has(String(toolName || "").trim());
}

function getCanvasStreamingPreviewLabel(document) {
  return getCanvasDocumentDisplayName(document) || "Canvas";
}

function getCanvasStreamingStatusMessage(toolName, document, phase = "loading") {
  const normalizedToolName = String(toolName || "").trim();
  const label = getCanvasStreamingPreviewLabel(document);
  if (phase === "streaming") {
    if (normalizedToolName === "create_canvas_document") {
      return `Drafting ${label} live...`;
    }
    if (normalizedToolName === "rewrite_canvas_document") {
      return `Rewriting ${label} live...`;
    }
    if (CANVAS_EDIT_PREVIEW_TOOLS.has(normalizedToolName)) {
      return `Previewing edits in ${label}...`;
    }
    return `Updating ${label} live...`;
  }
  if (phase === "executing") {
    if (normalizedToolName === "create_canvas_document") return `Creating ${label}...`;
    if (normalizedToolName === "rewrite_canvas_document") return `Rewriting ${label}...`;
    if (CANVAS_EDIT_PREVIEW_TOOLS.has(normalizedToolName)) return `Applying edits to ${label}...`;
    return `Updating ${label}...`;
  }
  if (normalizedToolName === "create_canvas_document") {
    return `Preparing live draft for ${label}...`;
  }
  if (normalizedToolName === "rewrite_canvas_document") {
    return `Preparing live rewrite for ${label}...`;
  }
  if (CANVAS_EDIT_PREVIEW_TOOLS.has(normalizedToolName)) {
    return `Preparing live edit preview for ${label}...`;
  }
  return `Preparing live Canvas preview for ${label}...`;
}

function normalizeCanvasDocument(document) {
  if (!document || typeof document !== "object") {
    return null;
  }
  const format = String(document.format || "markdown").trim().toLowerCase();
  const normalizedFormat = format === "code" ? "code" : "markdown";
  const content = String(document.content || "").replace(/\r\n?/g, "\n");
  const rawPageCount = Number.parseInt(String(document.page_count ?? "0"), 10);
  const contentMode = String(document.content_mode || "text").trim().toLowerCase();
  const canvasMode = String(document.canvas_mode || (contentMode === "visual" ? "preview_only" : "editable")).trim().toLowerCase();
  const visualPageImageIds = Array.isArray(document.visual_page_image_ids)
    ? document.visual_page_image_ids.map((value) => String(value || "").trim()).filter(Boolean)
    : [];
  return {
    id: String(document.id || "").trim(),
    title: String(document.title || "Canvas").trim() || "Canvas",
    path: String(document.path || "").trim().replace(/\\/g, "/"),
    role: String(document.role || "").trim().toLowerCase(),
    summary: String(document.summary || "").trim(),
    format: normalizedFormat,
    language: String(document.language || "").trim().toLowerCase(),
    content,
    line_count: Number.isInteger(Number(document.line_count)) ? Number(document.line_count) : content.split("\n").length,
    page_count: Number.isFinite(rawPageCount) && rawPageCount > 0 ? rawPageCount : 0,
    source_message_id: Number.isInteger(Number(document.source_message_id)) ? Number(document.source_message_id) : null,
    content_mode: contentMode === "visual" || contentMode === "hybrid" ? contentMode : "text",
    canvas_mode: canvasMode === "preview_only" ? "preview_only" : "editable",
    source_file_id: String(document.source_file_id || "").trim(),
    source_mime_type: String(document.source_mime_type || "").trim().toLowerCase(),
    visual_page_image_ids: visualPageImageIds,
  };
}

function isVisualCanvasDocument(document) {
  return String(document?.content_mode || "text").trim().toLowerCase() === "visual";
}

function isCanvasDocumentEditable(document) {
  return String(document?.canvas_mode || "editable").trim().toLowerCase() !== "preview_only";
}

function getVisualCanvasPageImageId(document, pageNumber) {
  if (!isVisualCanvasDocument(document)) {
    return "";
  }
  const normalizedPage = clampCanvasPageNumber(document, pageNumber || 1);
  if (normalizedPage < 1) {
    return "";
  }
  return String(document.visual_page_image_ids?.[normalizedPage - 1] || "").trim();
}

function getVisualCanvasPageImageUrl(document, pageNumber) {
  const imageId = getVisualCanvasPageImageId(document, pageNumber);
  if (!imageId || !currentConvId) {
    return "";
  }
  return `/api/conversations/${encodeURIComponent(String(currentConvId))}/images/${encodeURIComponent(imageId)}`;
}

function buildVisualCanvasImageUnavailableMarkup(document, pageNumber) {
  const normalizedPage = clampCanvasPageNumber(document, pageNumber || 1) || 1;
  const showPageNav = Number(document?.page_count || 0) > 1;
  return (
    `<div class="canvas-visual-page__caption">Read-only visual preview${showPageNav ? ` · Page ${normalizedPage}` : ""}</div>` +
    `<div class="canvas-visual-page__empty">` +
      `<p>Visual page preview could not be loaded.</p>` +
      `<button type="button" class="canvas-visual-page__retry" data-canvas-visual-retry>Retry preview</button>` +
    `</div>`
  );
}

function bindVisualCanvasPreview(document) {
  if (!canvasDocumentEl || !isVisualCanvasDocument(document)) {
    return;
  }

  const retryButton = canvasDocumentEl.querySelector("[data-canvas-visual-retry]");
  if (retryButton) {
    retryButton.addEventListener("click", () => {
      canvasDocumentEl.innerHTML = renderCanvasDocumentBody(document);
      bindCanvasPageNavigation(document);
    }, { once: true });
  }

  const imageEl = canvasDocumentEl.querySelector(".canvas-visual-page__image");
  if (!imageEl) {
    return;
  }

  imageEl.addEventListener("error", () => {
    const visualPageEl = imageEl.closest(".canvas-visual-page");
    if (!visualPageEl) {
      return;
    }
    const pageContainer = imageEl.closest("[data-canvas-page-number]");
    const currentPage = clampCanvasPageNumber(
      document,
      Number.parseInt(String(pageContainer?.getAttribute("data-canvas-page-number") || getCanvasCurrentPage(document) || 1), 10) || 1,
    ) || 1;
    visualPageEl.innerHTML = buildVisualCanvasImageUnavailableMarkup(document, currentPage);
    bindVisualCanvasPreview(document);
  }, { once: true });
}

function isCanvasPageAwareDocument(document) {
  return Boolean(document && !shouldRenderCanvasAsCode(document) && Number(document.page_count) > 1);
}

function getCanvasPageAnchorId(documentId, pageNumber) {
  const normalizedDocumentId = String(documentId || "canvas")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-") || "canvas";
  return `canvas-page-${normalizedDocumentId}-${pageNumber}`;
}

function clampCanvasPageNumber(document, pageNumber) {
  const totalPages = Number(document?.page_count || 0);
  if (!totalPages) {
    return 0;
  }
  const normalizedPage = Number.parseInt(String(pageNumber || 1), 10);
  if (!Number.isFinite(normalizedPage)) {
    return 1;
  }
  return Math.min(Math.max(normalizedPage, 1), totalPages);
}

function getCanvasCurrentPage(document) {
  if (!isCanvasPageAwareDocument(document)) {
    return 0;
  }
  return clampCanvasPageNumber(document, canvasPageByDocumentId.get(document.id) || 1);
}

function setCanvasCurrentPage(document, pageNumber) {
  if (!document?.id || !isCanvasPageAwareDocument(document)) {
    return 0;
  }
  const nextPage = clampCanvasPageNumber(document, pageNumber);
  canvasPageByDocumentId.set(document.id, nextPage);
  return nextPage;
}

function getCanvasPageHeadingNodes() {
  if (!canvasDocumentEl) {
    return [];
  }
  return Array.from(canvasDocumentEl.querySelectorAll("[data-canvas-page-number]"));
}

function extractCanvasPageSectionsFromContent(content) {
  const normalizedContent = String(content || "").replace(/\r\n?/g, "\n");
  const matches = Array.from(normalizedContent.matchAll(/^##\s+Page\s+(\d+)\s*$/gm));
  if (!matches.length) {
    return [];
  }
  return matches.map((match, index) => {
    const pageNumber = Number.parseInt(match[1], 10);
    const start = match.index ?? 0;
    const end = index + 1 < matches.length ? (matches[index + 1].index ?? normalizedContent.length) : normalizedContent.length;
    return {
      pageNumber,
      content: normalizedContent.slice(start, end).trim(),
    };
  }).filter((section) => Number.isFinite(section.pageNumber) && section.pageNumber > 0 && section.content);
}

function getCanvasPageSection(document, pageNumber) {
  const sections = extractCanvasPageSectionsFromContent(document?.content || "");
  if (!sections.length) {
    return null;
  }
  return sections.find((section) => section.pageNumber === clampCanvasPageNumber(document, pageNumber)) || sections[0];
}

function updateCanvasPageNavigationUi(document) {
  if (!canvasDocumentEl || !isCanvasPageAwareDocument(document)) {
    return;
  }
  const currentPage = getCanvasCurrentPage(document);
  const totalPages = clampCanvasPageNumber(document, document.page_count);
  const labelEl = canvasDocumentEl.querySelector("[data-canvas-page-label]");
  const prevBtn = canvasDocumentEl.querySelector('[data-canvas-page-action="prev"]');
  const nextBtn = canvasDocumentEl.querySelector('[data-canvas-page-action="next"]');
  if (labelEl) {
    labelEl.textContent = `Page ${currentPage} / ${totalPages}`;
  }
  if (prevBtn) {
    prevBtn.disabled = currentPage <= 1;
  }
  if (nextBtn) {
    nextBtn.disabled = currentPage >= totalPages;
  }
}

function syncCanvasCurrentPageFromScroll(document) {
  if (!canvasDocumentEl || !isCanvasPageAwareDocument(document)) {
    return;
  }
  const headings = getCanvasPageHeadingNodes();
  if (!headings.length) {
    return;
  }
  const containerRect = canvasDocumentEl.getBoundingClientRect();
  let currentPage = 1;
  headings.forEach((heading) => {
    const topOffset = heading.getBoundingClientRect().top - containerRect.top;
    if (topOffset <= 88) {
      currentPage = Number.parseInt(String(heading.dataset.canvasPageNumber || "1"), 10) || currentPage;
    }
  });
  setCanvasCurrentPage(document, currentPage);
  updateCanvasPageNavigationUi(document);
}

function scheduleCanvasPageSync(document) {
  if (!isCanvasPageAwareDocument(document) || pendingCanvasPageSyncFrame) {
    return;
  }
  pendingCanvasPageSyncFrame = globalThis.requestAnimationFrame(() => {
    pendingCanvasPageSyncFrame = 0;
    syncCanvasCurrentPageFromScroll(document);
  });
}

function scrollCanvasToPage(document, pageNumber, behavior = "smooth") {
  if (!canvasDocumentEl || !isCanvasPageAwareDocument(document)) {
    return;
  }
  const normalizedPage = setCanvasCurrentPage(document, pageNumber);
  const pageSection = getCanvasPageSection(document, normalizedPage);
  if (pageSection) {
    canvasDocumentEl.innerHTML = renderCanvasDocumentBody(document);
    bindCanvasPageNavigation(document);
    canvasDocumentEl.scrollTo({ top: 0, behavior: behavior === "auto" ? "auto" : "smooth" });
    return;
  }
  const target = canvasDocumentEl.querySelector(`#${getCanvasPageAnchorId(document.id, normalizedPage)}`);
  if (target) {
    target.scrollIntoView({ behavior, block: "start" });
  }
  updateCanvasPageNavigationUi(document);
}

function bindCanvasPageNavigation(document) {
  if (!canvasDocumentEl) {
    return;
  }
  canvasDocumentEl.onscroll = null;
  bindVisualCanvasPreview(document);
  if (!isCanvasPageAwareDocument(document)) {
    return;
  }

  const pageSection = getCanvasPageSection(document, getCanvasCurrentPage(document) || 1);
  if (pageSection) {
    canvasDocumentEl.querySelector('[data-canvas-page-action="prev"]')?.addEventListener("click", () => {
      scrollCanvasToPage(document, getCanvasCurrentPage(document) - 1, "auto");
    });
    canvasDocumentEl.querySelector('[data-canvas-page-action="next"]')?.addEventListener("click", () => {
      scrollCanvasToPage(document, getCanvasCurrentPage(document) + 1, "auto");
    });
    updateCanvasPageNavigationUi(document);
    return;
  }

  const headings = Array.from(canvasDocumentEl.querySelectorAll("h1, h2, h3, h4, h5, h6"));
  headings.forEach((heading) => {
    const match = CANVAS_PAGE_HEADING_TEXT_RE.exec(String(heading.textContent || "").trim());
    if (!match) {
      return;
    }
    const pageNumber = Number.parseInt(match[1], 10);
    heading.id = getCanvasPageAnchorId(document.id, pageNumber);
    heading.dataset.canvasPageNumber = String(pageNumber);
    heading.classList.add("canvas-page-heading");
  });

  canvasDocumentEl.querySelector('[data-canvas-page-action="prev"]')?.addEventListener("click", () => {
    scrollCanvasToPage(document, getCanvasCurrentPage(document) - 1);
  });
  canvasDocumentEl.querySelector('[data-canvas-page-action="next"]')?.addEventListener("click", () => {
    scrollCanvasToPage(document, getCanvasCurrentPage(document) + 1);
  });

  updateCanvasPageNavigationUi(document);
  canvasDocumentEl.onscroll = () => scheduleCanvasPageSync(document);
  if (getCanvasCurrentPage(document) > 1) {
    scrollCanvasToPage(document, getCanvasCurrentPage(document), "auto");
  } else {
    syncCanvasCurrentPageFromScroll(document);
  }
}

function getCanvasMode(documents) {
  return Array.isArray(documents) && documents.some((document) => document.path || document.role) ? "project" : "document";
}

function getCanvasPreferredActiveDocumentId(entries = history) {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const metadata = entries[index]?.metadata;
    const candidate = typeof metadata?.active_document_id === "string"
      ? metadata.active_document_id.trim()
      : "";
    if (candidate) {
      return candidate;
    }
  }
  return "";
}

function getCanvasDocumentLabel(document) {
  if (!document) {
    return "";
  }
  return String(document.path || document.title || "").trim();
}

function getCanvasDocumentReference(document) {
  return getCanvasDocumentLabel(document);
}

function getCanvasDocumentDisplayName(document) {
  return getCanvasDocumentReference(document) || String(document?.title || "Canvas").trim() || "Canvas";
}

function getCanvasFileName(document) {
  const label = getCanvasDocumentLabel(document);
  const parts = label.split("/");
  return parts[parts.length - 1] || label;
}

function shouldRenderCanvasAsCode(document) {
  if (!document || typeof document !== "object") {
    return false;
  }

  const explicitFormat = String(document.format || "").trim().toLowerCase();
  if (explicitFormat === "code") {
    return true;
  }

  const language = String(document.language || "").trim().toLowerCase();
  if (language && !["markdown", "md", "plain", "text", "txt"].includes(language)) {
    return true;
  }

  const candidateLabel = String(document.path || document.title || "").trim().toLowerCase();
  const extensionMatch = candidateLabel.match(/\.[^.\/]+$/);
  return Boolean(extensionMatch && CANVAS_CODE_FILE_EXTENSIONS.has(extensionMatch[0]));
}

function normalizeStreamingCanvasPreviewDocument(document) {
  const normalized = normalizeCanvasDocument(document);
  if (!normalized) {
    return null;
  }
  if (shouldRenderCanvasAsCode(normalized)) {
    normalized.format = "code";
  }
  return normalized;
}

function getCanvasPathFilterValue() {
  return String(canvasPathFilter?.value || "").trim();
}

function resetCanvasWorkspaceState() {
  isCanvasEditing = false;
  editingCanvasDocumentId = null;
  pendingCanvasDiff = null;
  if (pendingCanvasPageSyncFrame) {
    globalThis.cancelAnimationFrame(pendingCanvasPageSyncFrame);
    pendingCanvasPageSyncFrame = 0;
  }
  canvasPageByDocumentId = new Map();
  resetStreamingCanvasPreview();
  lastCanvasStructureSignature = "";
  collapsedCanvasFolders = new Set();
  lastCanvasTreeTypeAheadValue = "";
  lastCanvasTreeTypeAheadAt = 0;
  setCanvasAttention(false);
  setCanvasSearchStatus("");
  setCanvasStatus("Canvas idle", "muted");
  if (canvasSearchInput) {
    canvasSearchInput.value = "";
  }
  if (canvasRoleFilter) {
    canvasRoleFilter.value = "";
  }
  if (canvasPathFilter) {
    canvasPathFilter.value = "";
  }
}

function hasActiveCanvasFilters() {
  return Boolean(
    String(canvasSearchInput?.value || "").trim()
    || String(canvasRoleFilter?.value || "").trim()
    || getCanvasPathFilterValue()
  );
}

function resetCanvasMetaBar() {
  if (canvasMetaBar) {
    canvasMetaBar.hidden = true;
  }
  if (canvasMetaChips) {
    canvasMetaChips.innerHTML = "";
  }
  if (canvasCopyRefBtn) {
    canvasCopyRefBtn.disabled = true;
    canvasCopyRefBtn.textContent = "Copy reference";
  }
  if (canvasResetFiltersBtn) {
    canvasResetFiltersBtn.disabled = true;
  }
}

function resetCanvasFilters({ silent = false } = {}) {
  if (canvasSearchInput) {
    canvasSearchInput.value = "";
  }
  if (canvasRoleFilter) {
    canvasRoleFilter.value = "";
  }
  if (canvasPathFilter) {
    canvasPathFilter.value = "";
  }
  renderCanvasPanel();
  if (!silent) {
    setCanvasSearchStatus("Canvas filters cleared.", "muted");
  }
}

function documentMatchesCanvasFilters(document, searchTerm, roleValue, pathValue) {
  if (!document) {
    return false;
  }

  if (document.isStreamingPreview) {
    return true;
  }

  const normalizedRole = String(roleValue || "").trim().toLowerCase();
  const normalizedPath = String(pathValue || "").trim();
  const normalizedSearch = String(searchTerm || "").trim().toLowerCase();

  if (normalizedRole && document.role !== normalizedRole) {
    return false;
  }

  if (normalizedPath === CANVAS_ROOT_PATH_FILTER) {
    if ((document.path || "").includes("/")) {
      return false;
    }
  } else if (normalizedPath) {
    const candidatePath = getCanvasDocumentLabel(document);
    if (!(candidatePath === normalizedPath || candidatePath.startsWith(`${normalizedPath}/`))) {
      return false;
    }
  }

  if (!normalizedSearch) {
    return true;
  }

  const haystack = [document.title, document.path, document.role, document.summary, document.content]
    .filter(Boolean)
    .join("\n")
    .toLowerCase();
  return haystack.includes(normalizedSearch);
}

function getCanvasVisibleDocuments(documents) {
  const searchTerm = String(canvasSearchInput?.value || "").trim();
  const roleValue = String(canvasRoleFilter?.value || "").trim();
  const pathValue = getCanvasPathFilterValue();
  return (documents || []).filter((document) => documentMatchesCanvasFilters(document, searchTerm, roleValue, pathValue));
}

function buildCanvasPathFilterOptions(documents) {
  const options = [{ value: "", label: "All paths" }];
  const seen = new Set([""]);
  let hasRootFile = false;

  (documents || []).forEach((document) => {
    const path = String(document.path || "").trim();
    if (!path || !path.includes("/")) {
      hasRootFile = true;
      return;
    }

    const parts = path.split("/");
    let prefix = "";
    parts.slice(0, -1).forEach((part) => {
      prefix = prefix ? `${prefix}/${part}` : part;
      if (!seen.has(prefix)) {
        seen.add(prefix);
        options.push({ value: prefix, label: prefix });
      }
    });
  });

  if (hasRootFile) {
    options.push({ value: CANVAS_ROOT_PATH_FILTER, label: "Root files" });
  }

  return options;
}

function syncCanvasFilterControls(documents) {
  if (canvasRoleFilter) {
    const currentValue = String(canvasRoleFilter.value || "").trim();
    const roles = Array.from(new Set((documents || []).map((document) => document.role).filter(Boolean))).sort();
    canvasRoleFilter.innerHTML = '<option value="">All roles</option>' + roles.map((role) => `<option value="${escHtml(role)}">${escHtml(role)}</option>`).join("");
    canvasRoleFilter.value = roles.includes(currentValue) ? currentValue : "";
  }

  if (canvasPathFilter) {
    const currentValue = getCanvasPathFilterValue();
    const options = buildCanvasPathFilterOptions(documents);
    canvasPathFilter.innerHTML = options.map((option) => `<option value="${escHtml(option.value)}">${escHtml(option.label)}</option>`).join("");
    canvasPathFilter.value = options.some((option) => option.value === currentValue) ? currentValue : "";
  }
}

function buildCanvasTreeNodes(documents) {
  const root = { folders: new Map(), files: [] };

  (documents || []).forEach((document) => {
    const path = String(document.path || "").trim();
    if (!path || !path.includes("/")) {
      root.files.push({ name: getCanvasFileName(document), document });
      return;
    }

    const parts = path.split("/");
    let cursor = root;
    let prefix = "";
    parts.slice(0, -1).forEach((part) => {
      prefix = prefix ? `${prefix}/${part}` : part;
      if (!cursor.folders.has(part)) {
        cursor.folders.set(part, { name: part, path: prefix, folders: new Map(), files: [] });
      }
      cursor = cursor.folders.get(part);
    });

    cursor.files.push({ name: parts[parts.length - 1], document });
  });

  return root;
}

function getCanvasTreeItems() {
  if (!canvasTreeEl) {
    return [];
  }
  return Array.from(canvasTreeEl.querySelectorAll('[data-canvas-tree-item="true"]')).filter((item) => item instanceof HTMLElement && !item.hidden);
}

function syncCanvasTreeTabStops(preferredItem = null) {
  const items = getCanvasTreeItems().filter((item) => !item.disabled);
  if (!items.length) {
    return null;
  }

  const preferredActiveId = String(activeCanvasDocumentId || getCanvasPreferredActiveDocumentId() || "").trim();
  const nextItem = preferredItem instanceof HTMLElement
    ? preferredItem
    : items.find((item) => item.dataset.canvasDocumentId === preferredActiveId)
      || items[0];

  items.forEach((item) => {
    item.tabIndex = item === nextItem ? 0 : -1;
  });
  return nextItem;
}

function focusCanvasTreeItem(targetItem) {
  const nextItem = syncCanvasTreeTabStops(targetItem);
  if (nextItem && typeof nextItem.focus === "function") {
    nextItem.focus();
  }
  return nextItem;
}

function getCanvasTreeDocumentItem(documentId) {
  const targetId = String(documentId || "").trim();
  if (!targetId) {
    return null;
  }
  return getCanvasTreeItems().find((item) => item.dataset.canvasDocumentId === targetId) || null;
}

function getCanvasTreeFolderItem(folderPath) {
  const targetPath = String(folderPath || "").trim();
  if (!targetPath) {
    return null;
  }
  return getCanvasTreeItems().find((item) => item.dataset.canvasTreeFolder === "true" && item.dataset.folderPath === targetPath) || null;
}

function getCanvasTreeParentItem(treeItem) {
  if (!(treeItem instanceof HTMLElement)) {
    return null;
  }
  const parentGroup = treeItem.closest('[role="group"]');
  if (!(parentGroup instanceof HTMLElement)) {
    return null;
  }
  const parentSection = parentGroup.parentElement;
  if (!(parentSection instanceof HTMLElement)) {
    return null;
  }
  return parentSection.querySelector(':scope > [data-canvas-tree-folder="true"]');
}

function getCanvasTreeFirstChildItem(treeItem) {
  if (!(treeItem instanceof HTMLElement)) {
    return null;
  }
  const section = treeItem.closest('.canvas-tree-node');
  if (!(section instanceof HTMLElement)) {
    return null;
  }
  return section.querySelector(':scope > [role="group"] [data-canvas-tree-item="true"]');
}

function restoreCanvasTreeFocus({ documentId = "", folderPath = "", firstChild = false } = {}) {
  globalThis.requestAnimationFrame(() => {
    let targetItem = null;
    if (documentId) {
      targetItem = getCanvasTreeDocumentItem(documentId);
    } else if (folderPath) {
      targetItem = getCanvasTreeFolderItem(folderPath);
      if (firstChild) {
        targetItem = getCanvasTreeFirstChildItem(targetItem) || targetItem;
      }
    }
    focusCanvasTreeItem(targetItem);
  });
}

function setCanvasTreeFolderExpanded(folderPath, expanded = null, { focusTarget = "self" } = {}) {
  const normalizedPath = String(folderPath || "").trim();
  if (!normalizedPath) {
    return;
  }
  const isExpanded = !collapsedCanvasFolders.has(normalizedPath);
  const nextExpanded = typeof expanded === "boolean" ? expanded : !isExpanded;
  if (nextExpanded) {
    collapsedCanvasFolders.delete(normalizedPath);
  } else {
    collapsedCanvasFolders.add(normalizedPath);
  }
  renderCanvasPanel();
  restoreCanvasTreeFocus({ folderPath: normalizedPath, firstChild: focusTarget === "child" });
}

function handleCanvasTreeItemKeydown(event) {
  const currentItem = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
  if (!currentItem) {
    return;
  }

  const items = getCanvasTreeItems().filter((item) => !item.disabled);
  if (!items.length) {
    return;
  }

  const currentIndex = items.indexOf(currentItem);
  const folderPath = String(currentItem.dataset.folderPath || "").trim();
  const isFolder = currentItem.dataset.canvasTreeFolder === "true";
  const isExpanded = currentItem.getAttribute("aria-expanded") === "true";

  if (event.key === "ArrowDown") {
    event.preventDefault();
    focusCanvasTreeItem(items[Math.min(currentIndex + 1, items.length - 1)]);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    focusCanvasTreeItem(items[Math.max(currentIndex - 1, 0)]);
    return;
  }
  if (event.key === "Home") {
    event.preventDefault();
    focusCanvasTreeItem(items[0]);
    return;
  }
  if (event.key === "End") {
    event.preventDefault();
    focusCanvasTreeItem(items[items.length - 1]);
    return;
  }
  if (event.key === "ArrowRight") {
    if (isFolder && !isExpanded) {
      event.preventDefault();
      setCanvasTreeFolderExpanded(folderPath, true);
      return;
    }
    if (isFolder && isExpanded) {
      const firstChild = getCanvasTreeFirstChildItem(currentItem);
      if (firstChild) {
        event.preventDefault();
        focusCanvasTreeItem(firstChild);
      }
    }
    return;
  }
  if (event.key === "ArrowLeft") {
    if (isFolder && isExpanded) {
      event.preventDefault();
      setCanvasTreeFolderExpanded(folderPath, false);
      return;
    }
    const parentItem = getCanvasTreeParentItem(currentItem);
    if (parentItem) {
      event.preventDefault();
      focusCanvasTreeItem(parentItem);
    }
    return;
  }
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    currentItem.click();
    return;
  }

  const isTypeAheadKey = event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey && /\S/.test(event.key);
  if (!isTypeAheadKey) {
    return;
  }

  const now = Date.now();
  const resetWindowMs = 700;
  lastCanvasTreeTypeAheadValue = now - lastCanvasTreeTypeAheadAt > resetWindowMs
    ? event.key.toLowerCase()
    : `${lastCanvasTreeTypeAheadValue}${event.key.toLowerCase()}`;
  lastCanvasTreeTypeAheadAt = now;

  const normalizedQuery = lastCanvasTreeTypeAheadValue;
  const searchPool = [...items.slice(currentIndex + 1), ...items.slice(0, currentIndex + 1)];
  const matchedItem = searchPool.find((item) => {
    const label = String(item.dataset.treeLabel || item.textContent || "").trim().toLowerCase();
    return label.startsWith(normalizedQuery);
  });
  if (matchedItem) {
    event.preventDefault();
    focusCanvasTreeItem(matchedItem);
  }
}

function renderCanvasTreeFile(document, depth, activeDocument) {
  const button = globalThis.document.createElement("button");
  const isActive = Boolean(activeDocument && activeDocument.id === document.id);
  const roleBadge = document.role ? `<span class="canvas-tree-file__role">${escHtml(document.role)}</span>` : "";
  const pathLabel = document.path ? `<span class="canvas-tree-file__path">${escHtml(document.path)}</span>` : "";

  button.type = "button";
  button.className = `canvas-tree-file${isActive ? " active" : ""}`;
  button.style.setProperty("--canvas-tree-depth", String(depth));
  button.disabled = isCanvasEditing && !isActive;
  button.dataset.canvasTreeItem = "true";
  button.dataset.canvasDocumentId = document.id;
  button.dataset.treeLabel = getCanvasFileName(document).toLowerCase();
  button.setAttribute("role", "treeitem");
  button.setAttribute("aria-level", String(depth + 1));
  button.setAttribute("aria-selected", isActive ? "true" : "false");
  button.tabIndex = -1;
  button.innerHTML = `<span class="canvas-tree-file__name">${escHtml(getCanvasFileName(document))}</span>${roleBadge}${pathLabel}`;
  button.title = getCanvasDocumentLabel(document);
  button.addEventListener("click", () => {
    activeCanvasDocumentId = document.id;
    if (isMobileViewport()) {
      setCanvasMobileTreeOpen(false);
    }
    renderCanvasPanel();
    if (isMobileViewport()) {
      canvasSearchInput?.focus();
    } else {
      restoreCanvasTreeFocus({ documentId: document.id });
    }
  });
  button.addEventListener("keydown", handleCanvasTreeItemKeydown);
  return button;
}

function renderCanvasTree(documents, activeDocument) {
  if (!canvasTreePanel || !canvasTreeEl) {
    return;
  }

  const shouldShowTree = getCanvasMode(documents) === "project" || (documents || []).length > 1;
  canvasTreePanel.hidden = !shouldShowTree;
  if (!shouldShowTree) {
    setCanvasMobileTreeOpen(false);
    canvasTreeEl.innerHTML = "";
    if (canvasTreeCount) {
      canvasTreeCount.textContent = "";
    }
    return;
  }

  if (!isMobileViewport()) {
    isCanvasMobileTreeOpen = false;
    canvasPanel?.classList.remove("canvas-panel--tree-open");
  }
  syncCanvasTreeToggleButton();

  const visibleDocuments = getCanvasVisibleDocuments(documents);
  if (canvasTreeCount) {
    canvasTreeCount.textContent = `${visibleDocuments.length} shown`;
  }
  if (!visibleDocuments.length) {
    canvasTreeEl.innerHTML = '<div class="canvas-tree-empty">No files match the current filters.</div>';
    return;
  }

  const tree = buildCanvasTreeNodes(visibleDocuments);
  const fragment = document.createDocumentFragment();

  const renderFolder = (folder, depth = 0) => {
    const section = document.createElement("section");
    const isCollapsed = collapsedCanvasFolders.has(folder.path);
    section.className = "canvas-tree-node";

    const header = document.createElement("button");
    const bodyId = `canvas-tree-group-${encodeURIComponent(String(folder.path || "root"))}`;
    header.type = "button";
    header.className = `canvas-tree-folder${isCollapsed ? " collapsed" : ""}`;
    header.style.setProperty("--canvas-tree-depth", String(depth));
    header.dataset.canvasTreeItem = "true";
    header.dataset.canvasTreeFolder = "true";
    header.dataset.folderPath = folder.path;
    header.dataset.treeLabel = folder.name.toLowerCase();
    header.setAttribute("role", "treeitem");
    header.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
    header.setAttribute("aria-level", String(depth + 1));
    header.setAttribute("aria-controls", bodyId);
    header.tabIndex = -1;
    header.innerHTML = `<span class="canvas-tree-folder__caret">▾</span><span class="canvas-tree-folder__label">${escHtml(folder.name)}</span>`;
    header.addEventListener("click", () => {
      setCanvasTreeFolderExpanded(folder.path);
    });
    header.addEventListener("keydown", handleCanvasTreeItemKeydown);
    section.appendChild(header);

    if (!isCollapsed) {
      const body = document.createElement("div");
      body.id = bodyId;
      body.className = "canvas-tree-children";
      body.setAttribute("role", "group");
      Array.from(folder.folders.values())
        .sort((left, right) => left.name.localeCompare(right.name))
        .forEach((childFolder) => body.appendChild(renderFolder(childFolder, depth + 1)));
      folder.files
        .sort((left, right) => left.name.localeCompare(right.name))
        .forEach((entry) => body.appendChild(renderCanvasTreeFile(entry.document, depth + 1, activeDocument)));
      section.appendChild(body);
    }

    return section;
  };

  Array.from(tree.folders.values())
    .sort((left, right) => left.name.localeCompare(right.name))
    .forEach((folder) => fragment.appendChild(renderFolder(folder, 0)));
  tree.files
    .sort((left, right) => left.name.localeCompare(right.name))
    .forEach((entry) => fragment.appendChild(renderCanvasTreeFile(entry.document, 0, activeDocument)));

  canvasTreeEl.innerHTML = "";
  canvasTreeEl.appendChild(fragment);
  syncCanvasTreeTabStops();
}

function renderHighlightedCodeBlock(codeText, rawLang = null) {
  const normalizedCode = String(codeText || "").replace(/\r\n?/g, "\n");
  const lines = normalizedCode.split("\n");
  const lang = rawLang && highlighter && highlighter.getLanguage(rawLang) ? rawLang : null;
  const renderedLines = lines.map((line, index) => {
    let highlightedLine = line ? escHtml(line) : "&nbsp;";
    if (highlighter) {
      try {
        const sourceLine = line || " ";
        highlightedLine = lang
          ? highlighter.highlight(sourceLine, { language: lang, ignoreIllegals: true }).value
          : highlighter.highlightAuto(sourceLine).value;
      } catch (_) {
        highlightedLine = line ? escHtml(line) : "&nbsp;";
      }
    }
    return `<span class="canvas-code-line"><span class="canvas-code-line__number">${index + 1}</span><span class="canvas-code-line__content">${highlightedLine}</span></span>`;
  }).join("");
  const langClass = lang ? ` language-${lang}` : "";
  const langLabel = `<span class="canvas-code-lang">${escHtml(lang || "Code")}</span>`;
  return (
    `<div class="code-block-shell">` +
      `<div class="code-block-toolbar">` +
        `${langLabel}` +
        `<button type="button" class="code-copy-btn" aria-label="Copy code">Copy code</button>` +
      `</div>` +
      `<pre class="canvas-code-block"><code class="hljs${langClass}">${renderedLines}</code></pre>` +
    `</div>`
  );
}

if (markdownEngine && typeof markdownEngine.use === "function") {
  markdownEngine.use({
    breaks: true,
    gfm: true,
  });
  if (highlighter) {
    markdownEngine.use({
      renderer: {
        // Compatible with both marked v4 (code: string, language: string)
        // and marked v5+ (code: token object with .text and .lang properties).
        code(tokenOrCode, languageHint) {
          const isToken = tokenOrCode !== null && typeof tokenOrCode === "object";
          const codeText = isToken ? String(tokenOrCode.text || "") : String(tokenOrCode || "");
          const rawLang = isToken ? (tokenOrCode.lang || null) : (languageHint || null);
          return `${renderHighlightedCodeBlock(codeText, rawLang)}\n`;
        },
      },
    });
  }
}

function sanitizeHtml(html) {
  const rawHtml = String(html || "");
  if (sanitizer && typeof sanitizer.sanitize === "function") {
    return sanitizer.sanitize(rawHtml);
  }
  return rawHtml;
}

function closeUnclosedCodeFences(text) {
  const fenceCount = (text.match(/^```/gm) || []).length;
  return fenceCount % 2 !== 0 ? text + "\n```" : text;
}

function canRenderCanvasMath() {
  return Boolean(globalThis.katex && typeof globalThis.katex.renderToString === "function");
}

function findClosingMathDelimiter(text, startIndex, delimiter) {
  let searchIndex = startIndex;
  while (searchIndex < text.length) {
    const delimiterIndex = text.indexOf(delimiter, searchIndex);
    if (delimiterIndex < 0) {
      return -1;
    }
    if (delimiterIndex > startIndex && text[delimiterIndex - 1] === "\\") {
      searchIndex = delimiterIndex + delimiter.length;
      continue;
    }
    if (delimiter === "$" && text.slice(startIndex, delimiterIndex).includes("\n")) {
      searchIndex = delimiterIndex + delimiter.length;
      continue;
    }
    return delimiterIndex;
  }
  return -1;
}

function appendCanvasMathFragment(fragment, mathText, displayMode) {
  const wrapper = document.createElement("span");
  try {
    wrapper.innerHTML = globalThis.katex.renderToString(mathText, {
      displayMode,
      throwOnError: false,
      strict(errorCode) {
        return errorCode === "unicodeTextInMathMode" ? "ignore" : "warn";
      },
      trust: false,
      output: "html",
    });
  } catch (_) {
    fragment.appendChild(document.createTextNode(displayMode ? `$$${mathText}$$` : `$${mathText}$`));
    return;
  }

  while (wrapper.firstChild) {
    fragment.appendChild(wrapper.firstChild);
  }
}

function renderMathExpressionsInHtml(html) {
  const rawHtml = String(html || "");
  if (!rawHtml || !rawHtml.includes("$") || !canRenderCanvasMath()) {
    return rawHtml;
  }

  const container = document.createElement("div");
  container.innerHTML = rawHtml;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const text = String(node.textContent || "");
      if (!text.includes("$")) {
        return NodeFilter.FILTER_REJECT;
      }
      const parent = node.parentNode;
      if (!parent || !(parent instanceof Element)) {
        return NodeFilter.FILTER_REJECT;
      }
      if (parent.closest("pre, code, script, style, textarea, kbd, samp, svg, math, .katex")) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });

  const textNodes = [];
  let currentNode;
  while ((currentNode = walker.nextNode())) {
    textNodes.push(currentNode);
  }

  textNodes.forEach((textNode) => {
    const source = String(textNode.textContent || "");
    const fragment = document.createDocumentFragment();
    let buffer = "";
    let index = 0;

    const flushBuffer = () => {
      if (!buffer) {
        return;
      }
      fragment.appendChild(document.createTextNode(buffer));
      buffer = "";
    };

    while (index < source.length) {
      const character = source[index];
      if (character === "\\") {
        const nextCharacter = source[index + 1] || "";
        if (nextCharacter === "$") {
          buffer += "$";
          index += 2;
          continue;
        }
        buffer += character;
        index += 1;
        continue;
      }

      if (character !== "$") {
        buffer += character;
        index += 1;
        continue;
      }

      const displayMode = source[index + 1] === "$";
      const delimiter = displayMode ? "$$" : "$";
      const mathStart = index + delimiter.length;
      const mathEnd = findClosingMathDelimiter(source, mathStart, delimiter);
      if (mathEnd < 0) {
        buffer += character;
        index += 1;
        continue;
      }

      const mathText = source.slice(mathStart, mathEnd).trim();
      if (!mathText) {
        buffer += delimiter;
        index = mathStart;
        continue;
      }

      flushBuffer();
      appendCanvasMathFragment(fragment, mathText, displayMode);
      index = mathEnd + delimiter.length;
    }

    flushBuffer();
    textNode.parentNode.replaceChild(fragment, textNode);
  });

  return container.innerHTML;
}

function renderMarkdown(text) {
  const rawText = closeUnclosedCodeFences(String(text || ""));
  if (markdownEngine && typeof markdownEngine.parse === "function") {
    try {
      return renderMathExpressionsInHtml(sanitizeHtml(markdownEngine.parse(rawText)));
    } catch (_) {
      // Fall through to plain-text fallback if the markdown engine throws.
    }
  }
  return renderMathExpressionsInHtml(sanitizeHtml(escHtml(rawText).replace(/\n/g, "<br>")));
}

function buildStreamingMarkdownRenderer() {
  const rendererCtor = globalThis.marked && typeof globalThis.marked.Renderer === "function"
    ? globalThis.marked.Renderer
    : null;
  if (!rendererCtor) {
    return null;
  }

  const renderer = new rendererCtor();
  renderer.code = (tokenOrCode, languageHint) => {
    const isToken = tokenOrCode !== null && typeof tokenOrCode === "object";
    const codeText = isToken ? String(tokenOrCode.text || "") : String(tokenOrCode || "");
    const rawLang = isToken ? (tokenOrCode.lang || null) : (languageHint || null);
    const language = String(rawLang || "").trim().toLowerCase();
    const languageClass = language ? ` class="language-${escHtml(language)}"` : "";
    return `<pre class="canvas-stream-code-block"><code${languageClass}>${escHtml(codeText)}</code></pre>`;
  };
  return renderer;
}

const streamingMarkdownRenderer = buildStreamingMarkdownRenderer();

function renderStreamingMarkdown(text) {
  const rawText = closeUnclosedCodeFences(String(text || ""));
  if (markdownEngine && typeof markdownEngine.parse === "function") {
    try {
      const parsed = streamingMarkdownRenderer
        ? markdownEngine.parse(rawText, { breaks: true, gfm: true, renderer: streamingMarkdownRenderer })
        : markdownEngine.parse(rawText);
      return sanitizeHtml(parsed);
    } catch (_) {
      return sanitizeHtml(escHtml(rawText).replace(/\n/g, "<br>"));
    }
  }
  return sanitizeHtml(escHtml(rawText).replace(/\n/g, "<br>"));
}

function renderCanvasMarkdownSheet(contentHtml, options = {}) {
  const extraClasses = Array.isArray(options.extraClasses) ? options.extraClasses.filter(Boolean) : [];
  const classes = ["canvas-page-sheet", ...extraClasses].join(" ");
  const rawAttributes = options.attributes && typeof options.attributes === "object"
    ? Object.entries(options.attributes)
        .filter(([, value]) => value !== undefined && value !== null && value !== "")
        .map(([key, value]) => `${key}="${escHtml(String(value))}"`)
        .join(" ")
    : "";
  const attributeText = rawAttributes ? ` ${rawAttributes}` : "";
  return (
    `<div class="canvas-document-shell">` +
      `<div class="canvas-page-content">` +
        `<article class="${classes}"${attributeText}>${contentHtml}</article>` +
      `</div>` +
    `</div>`
  );
}

function getStreamingCanvasPreviewFormat(document) {
  return document?.format === "code" ? "code" : "markdown";
}

function getStreamingCanvasPreviewLabel(document) {
  const format = getStreamingCanvasPreviewFormat(document);
  if (format === "code") {
    return String(document?.language || "Code draft").trim() || "Code draft";
  }
  return "Markdown draft";
}

function getStreamingCanvasPreviewText(document) {
  return String(document?.content || "").replace(/\r\n?/g, "\n");
}

function getStreamingCanvasPreviewPlaceholder(document) {
  return getStreamingCanvasPreviewFormat(document) === "code"
    ? "// Streaming code draft will appear here..."
    : "Streaming draft will appear here...";
}

function countCanvasLines(text) {
  const normalizedText = String(text || "");
  return normalizedText ? normalizedText.split("\n").length : 0;
}

function countCanvasNewlines(text) {
  const matches = String(text || "").match(/\n/g);
  return matches ? matches.length : 0;
}

function renderStreamingCanvasPreviewBody(document) {
  const format = getStreamingCanvasPreviewFormat(document);
  if (format === "code") {
    const language = String(document?.language || "").trim().toLowerCase();
    const languageClass = language ? ` language-${escHtml(language)}` : "";
    return `<pre class="canvas-stream-code-block"><code class="canvas-stream-code${languageClass}">${escHtml(getStreamingCanvasPreviewText(document) || getStreamingCanvasPreviewPlaceholder(document))}</code></pre>`;
  }
  return renderStreamingMarkdown(getStreamingCanvasPreviewText(document) || getStreamingCanvasPreviewPlaceholder(document));
}

function renderStreamingCanvasPreviewContent(document) {
  const format = getStreamingCanvasPreviewFormat(document);
  return `<div class="canvas-stream-preview canvas-stream-preview--${format}" data-canvas-streaming-preview-body="true">${renderStreamingCanvasPreviewBody(document)}</div>`;
}

function updateStreamingCanvasPreviewElement(containerEl, document) {
  if (!containerEl) {
    return;
  }

  const previewBody = containerEl.querySelector('[data-canvas-streaming-preview-body="true"]');
  if (!previewBody) {
    containerEl.innerHTML = renderStreamingCanvasPreviewContent(document);
    return;
  }

  const format = getStreamingCanvasPreviewFormat(document);
  previewBody.className = `canvas-stream-preview canvas-stream-preview--${format}`;
  previewBody.innerHTML = renderStreamingCanvasPreviewBody(document);
}

function renderStreamingCanvasDocumentBody(document) {
  const documentId = escHtml(String(document?.id || "").trim());
  const format = escHtml(String(document?.format || "markdown").trim().toLowerCase() || "markdown");
  return renderCanvasMarkdownSheet(renderStreamingCanvasPreviewContent(document), {
    extraClasses: ["canvas-page-sheet--streaming"],
    attributes: {
      "data-canvas-streaming-preview-container": "true",
      "data-canvas-streaming-preview-id": documentId,
      "data-canvas-streaming-preview-format": format,
    },
  });
}

function renderCanvasDocumentBody(document) {
  if (!document) {
    return "";
  }
  if (document.isStreamingPreview) {
    return renderStreamingCanvasDocumentBody(document);
  }
  if (document.format === "code") {
    return sanitizeHtml(`<div class="canvas-code-document">${renderHighlightedCodeBlock(document.content, document.language || null)}</div>`);
  }
  if (isVisualCanvasDocument(document)) {
    const currentPage = getCanvasCurrentPage(document) || setCanvasCurrentPage(document, 1) || 1;
    const imageUrl = getVisualCanvasPageImageUrl(document, currentPage);
    const showPageNav = Number(document.page_count) > 1;
    return (
      `<div class="canvas-document-shell">` +
        (showPageNav
          ? `<div class="canvas-page-nav" data-canvas-page-nav>` +
              `<button type="button" class="canvas-page-nav__button" data-canvas-page-action="prev" aria-label="Previous page">&larr;</button>` +
              `<div class="canvas-page-nav__status" data-canvas-page-label>Page ${currentPage} / ${document.page_count}</div>` +
              `<button type="button" class="canvas-page-nav__button" data-canvas-page-action="next" aria-label="Next page">&rarr;</button>` +
            `</div>`
          : "") +
        `<div class="canvas-page-content">` +
          `<article class="canvas-page-sheet canvas-page-sheet--visual" data-canvas-page-sheet data-canvas-page-number="${currentPage}">` +
            `<div class="canvas-visual-page">` +
              `<div class="canvas-visual-page__caption">Read-only visual preview${showPageNav ? ` · Page ${currentPage}` : ""}</div>` +
              (imageUrl
                ? `<img class="canvas-visual-page__image" src="${escHtml(imageUrl)}" alt="${escHtml(`${document.title} page ${currentPage}`)}" loading="lazy">`
                : `<div class="canvas-visual-page__empty">Visual page preview is unavailable.</div>`) +
            `</div>` +
          `</article>` +
        `</div>` +
      `</div>`
    );
  }
  if (!isCanvasPageAwareDocument(document)) {
    return renderCanvasMarkdownSheet(renderMarkdown(document.content));
  }
  const currentPage = getCanvasCurrentPage(document) || setCanvasCurrentPage(document, 1);
  const currentSection = getCanvasPageSection(document, currentPage);
  const markdownHtml = renderMarkdown(currentSection?.content || document.content);
  return (
    `<div class="canvas-document-shell">` +
      `<div class="canvas-page-nav" data-canvas-page-nav>` +
        `<button type="button" class="canvas-page-nav__button" data-canvas-page-action="prev" aria-label="Previous page">&larr;</button>` +
        `<div class="canvas-page-nav__status" data-canvas-page-label>Page ${currentPage} / ${document.page_count}</div>` +
        `<button type="button" class="canvas-page-nav__button" data-canvas-page-action="next" aria-label="Next page">&rarr;</button>` +
      `</div>` +
      `<div class="canvas-page-content"><article class="canvas-page-sheet" data-canvas-page-sheet data-canvas-page-number="${currentPage}">${markdownHtml}</article></div>` +
    `</div>`
  );
}

function getCanvasDocumentById(documents, documentId) {
  const targetId = String(documentId || "").trim();
  if (!targetId) {
    return null;
  }
  return documents.find((document) => document.id === targetId) || null;
}

const CANVAS_DIFF_CONTEXT_LINE_COUNT = 2;
const CANVAS_DIFF_MAX_VISIBLE_LINES = 160;
const CANVAS_DIFF_MAX_MATRIX_CELLS = 60000;

function buildCanvasDiffOperations(previousLines, nextLines) {
  const previousLength = previousLines.length;
  const nextLength = nextLines.length;
  if (!previousLength && !nextLength) {
    return [];
  }

  if (previousLength && nextLength && previousLength * nextLength <= CANVAS_DIFF_MAX_MATRIX_CELLS) {
    const lcsMatrix = Array.from({ length: previousLength + 1 }, () => new Uint32Array(nextLength + 1));
    for (let previousIndex = previousLength - 1; previousIndex >= 0; previousIndex -= 1) {
      for (let nextIndex = nextLength - 1; nextIndex >= 0; nextIndex -= 1) {
        lcsMatrix[previousIndex][nextIndex] = previousLines[previousIndex] === nextLines[nextIndex]
          ? lcsMatrix[previousIndex + 1][nextIndex + 1] + 1
          : Math.max(lcsMatrix[previousIndex + 1][nextIndex], lcsMatrix[previousIndex][nextIndex + 1]);
      }
    }

    const operations = [];
    let previousIndex = 0;
    let nextIndex = 0;
    while (previousIndex < previousLength && nextIndex < nextLength) {
      if (previousLines[previousIndex] === nextLines[nextIndex]) {
        operations.push({ kind: "context", text: previousLines[previousIndex] });
        previousIndex += 1;
        nextIndex += 1;
        continue;
      }

      if (lcsMatrix[previousIndex + 1][nextIndex] >= lcsMatrix[previousIndex][nextIndex + 1]) {
        operations.push({ kind: "removed", text: previousLines[previousIndex] });
        previousIndex += 1;
        continue;
      }

      operations.push({ kind: "added", text: nextLines[nextIndex] });
      nextIndex += 1;
    }

    while (previousIndex < previousLength) {
      operations.push({ kind: "removed", text: previousLines[previousIndex] });
      previousIndex += 1;
    }

    while (nextIndex < nextLength) {
      operations.push({ kind: "added", text: nextLines[nextIndex] });
      nextIndex += 1;
    }

    return operations;
  }

  return [
    ...previousLines.map((text) => ({ kind: "removed", text })),
    ...nextLines.map((text) => ({ kind: "added", text })),
  ];
}

function buildCanvasDiffHunkLabel(lines) {
  const firstChangedLine = lines.find((line) => line.kind !== "context") || lines[0] || null;
  const oldAnchor = firstChangedLine?.previousLineNumber
    ?? lines.find((line) => Number.isInteger(line.previousLineNumber))?.previousLineNumber
    ?? null;
  const newAnchor = firstChangedLine?.nextLineNumber
    ?? lines.find((line) => Number.isInteger(line.nextLineNumber))?.nextLineNumber
    ?? null;

  if (Number.isInteger(oldAnchor) && Number.isInteger(newAnchor)) {
    return `Around old line ${oldAnchor} · new line ${newAnchor}`;
  }
  if (Number.isInteger(oldAnchor)) {
    return `Around old line ${oldAnchor}`;
  }
  if (Number.isInteger(newAnchor)) {
    return `Around new line ${newAnchor}`;
  }
  return "Changed lines";
}

function buildCanvasDiffHunks(lines, contextLineCount = CANVAS_DIFF_CONTEXT_LINE_COUNT, maxVisibleLines = CANVAS_DIFF_MAX_VISIBLE_LINES) {
  const changeIndices = [];
  lines.forEach((line, index) => {
    if (line.kind !== "context") {
      changeIndices.push(index);
    }
  });

  if (!changeIndices.length) {
    return {
      hunks: [],
      truncated: false,
      totalHunkCount: 0,
      visibleLineCount: 0,
    };
  }

  const mergedRanges = [];
  changeIndices.forEach((changeIndex) => {
    const nextRange = {
      start: Math.max(0, changeIndex - contextLineCount),
      end: Math.min(lines.length - 1, changeIndex + contextLineCount),
    };
    const previousRange = mergedRanges[mergedRanges.length - 1] || null;
    if (previousRange && nextRange.start <= previousRange.end + 1) {
      previousRange.end = Math.max(previousRange.end, nextRange.end);
      return;
    }
    mergedRanges.push(nextRange);
  });

  const hunks = [];
  let visibleLineCount = 0;
  let truncated = false;
  mergedRanges.forEach((range) => {
    if (visibleLineCount >= maxVisibleLines) {
      truncated = true;
      return;
    }

    const remainingLineBudget = maxVisibleLines - visibleLineCount;
    const fullLines = lines.slice(range.start, range.end + 1);
    const visibleLines = fullLines.slice(0, remainingLineBudget);
    if (!visibleLines.length) {
      truncated = true;
      return;
    }

    if (visibleLines.length < fullLines.length) {
      truncated = true;
    }

    hunks.push({
      label: buildCanvasDiffHunkLabel(visibleLines),
      lines: visibleLines,
    });
    visibleLineCount += visibleLines.length;
  });

  if (mergedRanges.length > hunks.length) {
    truncated = true;
  }

  return {
    hunks,
    truncated,
    totalHunkCount: mergedRanges.length,
    visibleLineCount,
  };
}

function buildCanvasDiff(previousContent, nextContent) {
  const previousLines = String(previousContent || "").replace(/\r\n?/g, "\n").split("\n");
  const nextLines = String(nextContent || "").replace(/\r\n?/g, "\n").split("\n");
  let start = 0;
  while (start < previousLines.length && start < nextLines.length && previousLines[start] === nextLines[start]) {
    start += 1;
  }

  let previousEnd = previousLines.length - 1;
  let nextEnd = nextLines.length - 1;
  while (previousEnd >= start && nextEnd >= start && previousLines[previousEnd] === nextLines[nextEnd]) {
    previousEnd -= 1;
    nextEnd -= 1;
  }

  const removed = previousEnd >= start ? previousLines.slice(start, previousEnd + 1) : [];
  const added = nextEnd >= start ? nextLines.slice(start, nextEnd + 1) : [];
  if (!removed.length && !added.length) {
    return null;
  }

  const numberedLines = [];
  const prefixContextStart = Math.max(0, start - CANVAS_DIFF_CONTEXT_LINE_COUNT);
  for (let index = prefixContextStart; index < start; index += 1) {
    numberedLines.push({
      kind: "context",
      previousLineNumber: index + 1,
      nextLineNumber: index + 1,
      text: previousLines[index],
    });
  }

  let previousLineNumber = start + 1;
  let nextLineNumber = start + 1;
  buildCanvasDiffOperations(removed, added).forEach((operation) => {
    if (operation.kind === "context") {
      numberedLines.push({
        kind: operation.kind,
        previousLineNumber,
        nextLineNumber,
        text: operation.text,
      });
      previousLineNumber += 1;
      nextLineNumber += 1;
      return;
    }

    if (operation.kind === "removed") {
      numberedLines.push({
        kind: operation.kind,
        previousLineNumber,
        nextLineNumber: null,
        text: operation.text,
      });
      previousLineNumber += 1;
      return;
    }

    numberedLines.push({
      kind: operation.kind,
      previousLineNumber: null,
      nextLineNumber,
      text: operation.text,
    });
    nextLineNumber += 1;
  });

  const sharedSuffixCount = Math.min(
    CANVAS_DIFF_CONTEXT_LINE_COUNT,
    Math.max(0, previousLines.length - (previousEnd + 1)),
    Math.max(0, nextLines.length - (nextEnd + 1)),
  );
  for (let offset = 0; offset < sharedSuffixCount; offset += 1) {
    numberedLines.push({
      kind: "context",
      previousLineNumber,
      nextLineNumber,
      text: previousLines[previousEnd + 1 + offset],
    });
    previousLineNumber += 1;
    nextLineNumber += 1;
  }

  const addedCount = numberedLines.filter((line) => line.kind === "added").length;
  const removedCount = numberedLines.filter((line) => line.kind === "removed").length;
  const { hunks, truncated, totalHunkCount, visibleLineCount } = buildCanvasDiffHunks(numberedLines);

  return {
    startLine: start + 1,
    removed,
    added,
    addedCount,
    removedCount,
    hunkCount: totalHunkCount,
    hunks,
    truncated,
    visibleLineCount,
  };
}

function renderCanvasDiffPreview(activeDocument) {
  if (!canvasDiffEl) {
    return;
  }
  if (!pendingCanvasDiff || pendingCanvasDiff.documentId !== activeDocument?.id || activeDocument?.isStreamingPreview) {
    canvasDiffEl.hidden = true;
    canvasDiffEl.innerHTML = "";
    return;
  }

  const diff = pendingCanvasDiff.diff;
  const fileLabel = getCanvasDocumentLabel(activeDocument);
  const metaParts = [
    fileLabel,
    `+${diff.addedCount}`,
    `-${diff.removedCount}`,
    `${diff.hunkCount} hunk${diff.hunkCount === 1 ? "" : "s"}`,
  ];
  if (diff.truncated) {
    metaParts.push(`showing first ${diff.visibleLineCount} diff line${diff.visibleLineCount === 1 ? "" : "s"}`);
  }
  const sourceBadge = pendingCanvasDiff.source === "live-preview"
    ? '<span class="canvas-diff__badge">Saved after live preview</span>'
    : "";

  canvasDiffEl.hidden = false;
  canvasDiffEl.innerHTML =
    `<div class="canvas-diff__header">` +
      `<div class="canvas-diff__summary">` +
        `<div class="canvas-diff__title-row">` +
          `<div class="canvas-diff__title">Recent AI change</div>` +
          sourceBadge +
        `</div>` +
        `<div class="canvas-diff__meta">${escHtml(metaParts.join(" · "))}</div>` +
      `</div>` +
      `<div class="canvas-diff__actions">` +
        `<button class="canvas-diff__close" type="button" data-action="dismiss-canvas-diff">Hide diff</button>` +
      `</div>` +
    `</div>` +
    `<div class="canvas-diff__body">` +
      diff.hunks.map((hunk) =>
        `<section class="canvas-diff__hunk">` +
          `<div class="canvas-diff__hunk-header">${escHtml(hunk.label)}</div>` +
          hunk.lines.map((line) => {
            const marker = line.kind === "added" ? "+" : line.kind === "removed" ? "-" : "·";
            const previousLineNumber = Number.isInteger(line.previousLineNumber) ? String(line.previousLineNumber) : "";
            const nextLineNumber = Number.isInteger(line.nextLineNumber) ? String(line.nextLineNumber) : "";
            return `<div class="canvas-diff__line canvas-diff__line--${line.kind}"><span class="canvas-diff__line-marker">${marker}</span><span class="canvas-diff__line-num">${previousLineNumber}</span><span class="canvas-diff__line-num">${nextLineNumber}</span><span class="canvas-diff__line-text">${escHtml(line.text || " ")}</span></div>`;
          }).join("") +
        `</section>`
      ).join("") +
    `</div>`;

  canvasDiffEl.querySelector('[data-action="dismiss-canvas-diff"]')?.addEventListener("click", () => {
    pendingCanvasDiff = null;
    renderCanvasDiffPreview(getActiveCanvasDocument());
  });
}

function setCanvasEditing(enabled) {
  if (enabled && guardCanvasMutation("edit the active file")) {
    return;
  }
  const activeDocument = getActiveCanvasDocument();
  if (enabled && activeDocument && !isCanvasDocumentEditable(activeDocument)) {
    setCanvasStatus("Visual canvas previews are read-only.", "muted");
    renderCanvasPanel();
    return;
  }
  if (enabled) {
    closeCanvasOverflowMenu();
    setCanvasMobileTreeOpen(false);
  }
  isCanvasEditing = Boolean(enabled && activeDocument);
  editingCanvasDocumentId = isCanvasEditing ? activeDocument.id : null;
  if (isCanvasEditing && canvasEditorEl) {
    canvasEditorEl.value = activeDocument.content || "";
  }
  renderCanvasPanel();
}

function cancelCanvasEditing({ statusMessage = "", tone = "muted" } = {}) {
  if (guardCanvasMutation("leave edit mode")) {
    return;
  }
  if (!isCanvasEditing && !editingCanvasDocumentId) {
    return;
  }
  clearCanvasEditingPreviewRender();
  isCanvasEditing = false;
  editingCanvasDocumentId = null;
  renderCanvasPanel();
  if (statusMessage) {
    setCanvasStatus(statusMessage, tone);
  }
}

function clearCanvasSearchInput({ statusMessage = "", tone = "muted" } = {}) {
  if (!canvasSearchInput?.value) {
    return false;
  }
  canvasSearchInput.value = "";
  renderCanvasPanel();
  if (statusMessage) {
    setCanvasSearchStatus(statusMessage, tone);
  }
  return true;
}

const CANVAS_UPLOAD_MARKDOWN_EXTENSIONS = new Set([".md", ".markdown", ".mdx", ".txt", ".rst", ".adoc", ".org"]);
const CANVAS_UPLOAD_LANGUAGE_MAP = {
  ".py": "python",
  ".pyw": "python",
  ".js": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".ts": "typescript",
  ".mts": "typescript",
  ".tsx": "tsx",
  ".jsx": "jsx",
  ".json": "json",
  ".jsonc": "json",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".html": "html",
  ".htm": "html",
  ".css": "css",
  ".sh": "bash",
  ".bash": "bash",
  ".zsh": "bash",
  ".sql": "sql",
  ".xml": "xml",
  ".toml": "toml",
  ".ini": "ini",
  ".cfg": "ini",
  ".c": "c",
  ".h": "c",
  ".cpp": "cpp",
  ".cc": "cpp",
  ".cxx": "cpp",
  ".hpp": "cpp",
  ".hh": "cpp",
  ".go": "go",
  ".rs": "rust",
  ".java": "java",
  ".rb": "ruby",
  ".php": "php",
};

function getCanvasUploadExtension(fileName) {
  const normalizedName = String(fileName || "").trim().toLowerCase();
  const dotIndex = normalizedName.lastIndexOf(".");
  if (dotIndex < 0) {
    return "";
  }
  return normalizedName.slice(dotIndex);
}

function inferCanvasUploadFormat(fileName) {
  return CANVAS_UPLOAD_MARKDOWN_EXTENSIONS.has(getCanvasUploadExtension(fileName)) ? "markdown" : "code";
}

function inferCanvasUploadLanguage(fileName) {
  return CANVAS_UPLOAD_LANGUAGE_MAP[getCanvasUploadExtension(fileName)] || null;
}

function showPendingCanvasUploadPreview(fileName) {
  const nextTitle = String(fileName || "Uploaded file").trim() || "Uploaded file";
  const nextFormat = inferCanvasUploadFormat(nextTitle);
  const nextLanguage = inferCanvasUploadLanguage(nextTitle) || "";
  const preview = buildStreamingCanvasPreviewDocument("create_canvas_document", PENDING_CANVAS_UPLOAD_PREVIEW_KEY, {
    title: nextTitle,
    format: nextFormat,
    language: nextLanguage,
  });
  if (!preview) {
    return;
  }
  preview.content = nextFormat === "code"
    ? "// Upload is being processed..."
    : getCanvasUploadExtension(nextTitle) === ".pdf"
      ? `## Processing ${nextTitle}\n\nPreparing pages for Canvas...`
      : `# ${nextTitle}\n\nUploading file...`;
  preview.line_count = preview.content.split("\n").length;
  preview.page_count = 0;
  preview.isStreamingPreview = true;
  streamingCanvasPreviews.set(PENDING_CANVAS_UPLOAD_PREVIEW_KEY, preview);
  activeCanvasDocumentId = preview.id;
  isCanvasEditing = false;
  editingCanvasDocumentId = null;
  renderCanvasPanel();
}

function clearPendingCanvasUploadPreview() {
  if (!streamingCanvasPreviews.has(PENDING_CANVAS_UPLOAD_PREVIEW_KEY)) {
    return;
  }
  streamingCanvasPreviews.delete(PENDING_CANVAS_UPLOAD_PREVIEW_KEY);
}

function scheduleCanvasAutoRefreshAfterUpload(delay = 350) {
  if (!currentConvId) {
    return;
  }
  window.setTimeout(() => {
    if (!currentConvId || isStreaming || isFixing) {
      return;
    }
    void refreshConversationFromServer();
  }, delay);
}

async function createCanvasDocumentFromData({ title, content, format, language = null, statusMessage = "Creating canvas file..." }) {
  if (!currentConvId) {
    setCanvasStatus("Conversation is not available yet.", "warning");
    return;
  }
  if (guardCanvasMutation("create another file")) {
    return;
  }

  cancelPendingConversationRefreshes();

  if (canvasNewBtn) {
    canvasNewBtn.disabled = true;
  }
  if (canvasUploadBtn) {
    canvasUploadBtn.disabled = true;
  }

  setCanvasMutationState("create");
  setCanvasStatus(statusMessage, "muted");

  try {
    const response = await fetch(`/api/conversations/${currentConvId}/canvas`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title,
        content,
        format,
        language,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Canvas create failed.");
    }

    clearPendingCanvasUploadPreview();
    setCanvasMutationState("", { rerender: false });
    history = Array.isArray(payload.messages) ? payload.messages.map(normalizeHistoryEntry) : history;
    streamingCanvasDocuments = [];
    pendingCanvasDiff = null;
    activeCanvasDocumentId = String(payload.active_document_id || payload.document?.id || "").trim() || null;
    isCanvasEditing = true;
    editingCanvasDocumentId = null;
    renderConversationHistory();
    renderCanvasPanel();
    scheduleCanvasAutoRefreshAfterUpload();
    setCanvasStatus("Canvas file created.", "success");
    globalThis.requestAnimationFrame(() => {
      if (!canvasEditorEl) {
        return;
      }
      canvasEditorEl.focus();
      const cursorPosition = canvasEditorEl.value.length;
      canvasEditorEl.setSelectionRange(cursorPosition, cursorPosition);
    });
  } catch (error) {
    clearPendingCanvasUploadPreview();
    setCanvasMutationState("", { rerender: false });
    setCanvasStatus(error.message || "Canvas create failed.", "danger");
    renderCanvasPanel();
  }
}

async function createCanvasDocumentFromPrompt() {
  if (guardCanvasMutation("create another file")) {
    return;
  }
  const nextTitle = String(globalThis.prompt("New canvas file name", "Untitled") || "").trim();
  if (!nextTitle) {
    setCanvasStatus("Canvas file creation cancelled.", "muted");
    return;
  }

  const nextFormat = getCanvasFormatControlValue();
  await createCanvasDocumentFromData({
    title: nextTitle,
    content: "",
    format: nextFormat,
  });
}

async function createCanvasDocumentFromFile(file) {
  const nextTitle = String(file?.name || "").trim() || "Uploaded file";

  if (!currentConvId) {
    setCanvasStatus("Conversation is not available yet.", "warning");
    return;
  }
  if (guardCanvasMutation("upload another file")) {
    return;
  }

  if (canvasNewBtn) {
    canvasNewBtn.disabled = true;
  }
  if (canvasUploadBtn) {
    canvasUploadBtn.disabled = true;
  }

  cancelPendingConversationRefreshes();
  setCanvasMutationState("upload");
  showPendingCanvasUploadPreview(nextTitle);
  setCanvasStatus(`Uploading ${nextTitle}...`, "muted");

  try {
    const formData = new FormData();
    formData.append("file", file, nextTitle);
    formData.append("title", nextTitle);

    const response = await fetch(`/api/conversations/${currentConvId}/canvas`, {
      method: "POST",
      body: formData,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Canvas upload failed.");
    }

    clearPendingCanvasUploadPreview();
    setCanvasMutationState("", { rerender: false });
    history = Array.isArray(payload.messages) ? payload.messages.map(normalizeHistoryEntry) : history;
    streamingCanvasDocuments = [];
    pendingCanvasDiff = null;
    activeCanvasDocumentId = String(payload.active_document_id || payload.document?.id || "").trim() || null;
    isCanvasEditing = true;
    editingCanvasDocumentId = null;
    renderConversationHistory();
    renderCanvasPanel();
    setCanvasStatus("Canvas file created.", "success");
    globalThis.requestAnimationFrame(() => {
      if (!canvasEditorEl) {
        return;
      }
      canvasEditorEl.focus();
      const cursorPosition = canvasEditorEl.value.length;
      canvasEditorEl.setSelectionRange(cursorPosition, cursorPosition);
    });
  } catch (error) {
    clearPendingCanvasUploadPreview();
    setCanvasMutationState("", { rerender: false });
    setCanvasStatus(error.message || "Canvas upload failed.", "danger");
    renderCanvasPanel();
  }
}

function openCanvasUploadPicker() {
  if (guardCanvasMutation("upload a file")) {
    return;
  }
  if (!canvasUploadInput) {
    setCanvasStatus("File upload is not available.", "warning");
    return;
  }
  canvasUploadInput.value = "";
  canvasUploadInput.click();
}

function readCanvasWidthPreference() {
  try {
    const value = Number.parseInt(localStorage.getItem(CANVAS_PANEL_WIDTH_STORAGE_KEY) || "", 10);
    return Number.isFinite(value) ? value : CANVAS_PANEL_DEFAULT_WIDTH;
  } catch (_) {
    return CANVAS_PANEL_DEFAULT_WIDTH;
  }
}

function clampCanvasWidth(width) {
  const viewportLimit = Math.max(CANVAS_PANEL_MIN_WIDTH, globalThis.innerWidth - 24);
  return Math.min(Math.max(width, CANVAS_PANEL_MIN_WIDTH), Math.min(CANVAS_PANEL_MAX_WIDTH, viewportLimit));
}

function applyCanvasPanelWidth(width, persist = true) {
  if (!canvasPanel || globalThis.innerWidth <= 900) {
    if (canvasPanel) {
      canvasPanel.style.width = "";
    }
    return;
  }
  const nextWidth = clampCanvasWidth(width);
  canvasPanel.style.width = `${nextWidth}px`;
  if (persist) {
    try {
      localStorage.setItem(CANVAS_PANEL_WIDTH_STORAGE_KEY, String(nextWidth));
    } catch (_) {
      // Ignore storage errors.
    }
  }
}

function getCanvasDocuments(metadata) {
  if (!metadata || typeof metadata !== "object" || !Array.isArray(metadata.canvas_documents)) {
    return [];
  }

  return metadata.canvas_documents
    .map((document) => normalizeCanvasDocument(document))
    .filter((document) => document.id);
}

function getCanvasDocumentCollection(entries = history) {
  if (streamingCanvasDocuments.length) {
    return streamingCanvasDocuments;
  }

  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const message = entries[index];
    if (message?.metadata && message.metadata.canvas_cleared === true) {
      return [];
    }
    const documents = getCanvasDocuments(message?.metadata);
    if (!documents.length) {
      continue;
    }
    return documents;
  }

  return [];
}

function resetStreamingCanvasPreview() {
  streamingCanvasPreviews.clear();
  clearCanvasRenderJob("preview");
}

function queueStreamingCanvasPreviewDelta(previewDocument, delta, replaceContent = false) {
  if (!previewDocument) {
    return false;
  }

  const nextDelta = String(delta || "");
  if (!replaceContent && !nextDelta) {
    return false;
  }

  if (replaceContent) {
    previewDocument.pendingContentReplacement = nextDelta;
    previewDocument.pendingContentAppends = [];
    return true;
  }

  if (!Array.isArray(previewDocument.pendingContentAppends)) {
    previewDocument.pendingContentAppends = [];
  }
  previewDocument.pendingContentAppends.push(nextDelta);
  return true;
}

function flushStreamingCanvasPreviewDelta(previewDocument) {
  if (!previewDocument || typeof previewDocument !== "object") {
    return false;
  }

  const hasReplacement = Object.prototype.hasOwnProperty.call(previewDocument, "pendingContentReplacement");
  const replacementContent = hasReplacement ? String(previewDocument.pendingContentReplacement || "") : "";
  const appendedContent = Array.isArray(previewDocument.pendingContentAppends)
    ? previewDocument.pendingContentAppends.join("")
    : "";
  if (!hasReplacement && !appendedContent) {
    return false;
  }

  const previousContent = String(previewDocument.content || "");
  let nextContent = hasReplacement ? replacementContent : previousContent;
  if (appendedContent) {
    nextContent += appendedContent;
  }
  previewDocument.content = nextContent;

  if (!nextContent) {
    previewDocument.line_count = 0;
  } else if (hasReplacement || !previousContent) {
    previewDocument.line_count = countCanvasLines(nextContent);
  } else {
    const currentLineCount = Number.isFinite(Number(previewDocument.line_count)) && Number(previewDocument.line_count) > 0
      ? Number(previewDocument.line_count)
      : countCanvasLines(previousContent);
    previewDocument.line_count = currentLineCount + countCanvasNewlines(appendedContent);
  }

  delete previewDocument.pendingContentReplacement;
  previewDocument.pendingContentAppends = [];
  return true;
}

function flushStreamingCanvasPreviewDeltas() {
  let changed = false;
  streamingCanvasPreviews.forEach((previewDocument) => {
    if (flushStreamingCanvasPreviewDelta(previewDocument)) {
      changed = true;
    }
  });
  return changed;
}

function buildStreamingCanvasPreviewDocument(toolName, previewKey = "", snapshot = {}) {
  const normalizedToolName = String(toolName || "").trim();
  const normalizedPreviewKey = String(previewKey || "").trim() || "canvas-call-0";
  const snapshotData = snapshot && typeof snapshot === "object" ? snapshot : {};
  const allDocuments = getCanvasDocumentCollection(history);
  const activeDocument = getActiveCanvasDocument(history);

  // For rewrite and edit operations (replace/insert/delete lines), prefer the
  // document explicitly identified in the snapshot over the generic active doc.
  const needsTargetDoc = normalizedToolName === "rewrite_canvas_document" || CANVAS_EDIT_PREVIEW_TOOLS.has(normalizedToolName);
  let targetDocument = activeDocument;
  if (needsTargetDoc) {
    const snapshotDocId = String(snapshotData.document_id || "").trim();
    const snapshotDocPath = String(snapshotData.document_path || "").trim();
    if (snapshotDocId) {
      targetDocument = getCanvasDocumentById(allDocuments, snapshotDocId) || activeDocument;
    } else if (snapshotDocPath) {
      targetDocument = allDocuments.find((d) => d.path === snapshotDocPath) || activeDocument;
    }
  }

  const isRewritePreview = normalizedToolName === "rewrite_canvas_document" && targetDocument;
  const isEditPreview = CANVAS_EDIT_PREVIEW_TOOLS.has(normalizedToolName) && targetDocument;
  const baseDocument = (isRewritePreview || isEditPreview) ? targetDocument : null;
  const normalized = normalizeStreamingCanvasPreviewDocument({
    id: baseDocument ? baseDocument.id : `streaming-canvas-preview-${normalizedPreviewKey}`,
    title: String(snapshotData.title || (baseDocument ? baseDocument.title : "Canvas draft")).trim() || "Canvas draft",
    path: String(snapshotData.path || (baseDocument ? baseDocument.path : "")).trim(),
    role: String(snapshotData.role || (baseDocument ? baseDocument.role : "note")).trim(),
    summary: baseDocument ? String(baseDocument.summary || "") : "",
    format: String(snapshotData.format || (baseDocument ? baseDocument.format : "markdown")).trim() || "markdown",
    language: String(snapshotData.language || (baseDocument ? baseDocument.language : "")).trim(),
    content: isEditPreview ? String(targetDocument.content || "") : "",
    source_message_id: baseDocument ? baseDocument.source_message_id : null,
  });
  return normalized ? { ...normalized, isStreamingPreview: true, tool: normalizedToolName, previewKey: normalizedPreviewKey } : null;
}

function applyStreamingCanvasPreviewSnapshot(previewDoc, snapshot = {}) {
  if (!previewDoc || !snapshot || typeof snapshot !== "object") {
    return false;
  }
  let changed = false;
  if (typeof snapshot.title === "string" && snapshot.title.trim()) {
    const nextTitle = snapshot.title.trim();
    if (nextTitle !== previewDoc.title) {
      previewDoc.title = nextTitle;
      changed = true;
    }
  }
  if (typeof snapshot.path === "string") {
    const nextPath = snapshot.path.trim().replace(/\\/g, "/");
    if (nextPath && nextPath !== previewDoc.path) {
      previewDoc.path = nextPath;
      changed = true;
    }
  }
  if (typeof snapshot.role === "string") {
    const nextRole = snapshot.role.trim().toLowerCase();
    if (nextRole && nextRole !== previewDoc.role) {
      previewDoc.role = nextRole;
      changed = true;
    }
  }
  if (typeof snapshot.format === "string") {
    const normalizedFormat = snapshot.format.trim().toLowerCase();
    const nextFormat = normalizedFormat === "code" ? "code" : "markdown";
    if (nextFormat !== previewDoc.format) {
      previewDoc.format = nextFormat;
      changed = true;
    }
  }
  if (typeof snapshot.language === "string") {
    const nextLanguage = snapshot.language.trim().toLowerCase();
    if (nextLanguage && nextLanguage !== previewDoc.language) {
      previewDoc.language = nextLanguage;
      changed = true;
    }
  }

  const normalizedPreview = normalizeStreamingCanvasPreviewDocument(previewDoc);
  if (normalizedPreview) {
    ["title", "path", "role", "format", "language", "summary"].forEach((key) => {
      if (normalizedPreview[key] !== previewDoc[key]) {
        previewDoc[key] = normalizedPreview[key];
        changed = true;
      }
    });
  }

  return changed;
}

function ensureStreamingCanvasPreview(toolName, previewKey = "", snapshot = {}) {
  const normalizedToolName = String(toolName || "").trim();
  const normalizedPreviewKey = String(previewKey || "").trim() || "canvas-call-0";
  if (!normalizedToolName) {
    return null;
  }
  const existing = streamingCanvasPreviews.get(normalizedPreviewKey);
  const rebuiltPreview = buildStreamingCanvasPreviewDocument(normalizedToolName, normalizedPreviewKey, snapshot);
  const shouldRebuild = !existing
    || existing.tool !== normalizedToolName
    || (rebuiltPreview && rebuiltPreview.id && rebuiltPreview.id !== existing.id);
  const isNewPreview = !existing || shouldRebuild;
  let preview = existing;
  if (shouldRebuild) {
    preview = rebuiltPreview;
    if (preview) {
      streamingCanvasPreviews.set(normalizedPreviewKey, preview);
    }
  }
  if (!preview) {
    return null;
  }
  applyStreamingCanvasPreviewSnapshot(preview, snapshot);
  // Only switch the active view to the streaming preview when a new streaming
  // operation starts. If the user has manually selected a different document
  // during an ongoing stream, do not force the view back to the preview.
  if (isNewPreview || activeCanvasDocumentId === preview.id) {
    activeCanvasDocumentId = preview.id;
  }
  return preview;
}

function getCanvasRenderableDocuments(entries = history) {
  const documents = getCanvasDocumentCollection(entries);
  if (!streamingCanvasPreviews.size) {
    return documents;
  }
  let result = [...documents];
  for (const preview of streamingCanvasPreviews.values()) {
    if (!preview?.id) {
      continue;
    }
    const previewIndex = result.findIndex((document) => document.id === preview.id);
    if (previewIndex >= 0) {
      result = [...result.slice(0, previewIndex), preview, ...result.slice(previewIndex + 1)];
    } else {
      result = [...result, preview];
    }
  }
  return result;
}

function buildCanvasStructureSignature(documents, visibleDocuments = documents) {
  const documentSignature = (documents || []).map((document) => [
    String(document.id || "").trim(),
    String(document.title || "").trim(),
    String(document.path || "").trim(),
    String(document.role || "").trim(),
    String(document.format || "").trim(),
    String(document.language || "").trim(),
    document.isStreamingPreview ? "preview" : "stored",
  ].join("\u241f")).join("\u241e");
  const visibleSignature = (visibleDocuments || []).map((document) => String(document.id || "").trim()).join("\u241e");
  const filterSignature = [
    String(canvasSearchInput?.value || "").trim(),
    String(canvasRoleFilter?.value || "").trim(),
    getCanvasPathFilterValue(),
    isCanvasEditing ? "editing" : "view",
  ].join("\u241f");
  return [documentSignature, visibleSignature, filterSignature].join("\u241d");
}

function buildCanvasRenderState(documents = getCanvasRenderableDocuments()) {
  const visibleDocuments = getCanvasVisibleDocuments(documents);
  const preferredActiveId = [
    String(activeCanvasDocumentId || "").trim(),
    String(getCanvasPreferredActiveDocumentId() || "").trim(),
  ].find(Boolean) || "";
  const activeDocument = visibleDocuments.length
    ? getCanvasDocumentById(visibleDocuments, preferredActiveId) || visibleDocuments[visibleDocuments.length - 1]
    : null;

  return {
    isCanvasPanelOpen: isCanvasOpen(),
    documents,
    visibleDocuments,
    activeDocument,
    isStreamingPreviewActive: Boolean(activeDocument?.isStreamingPreview),
    searchTerm: String(canvasSearchInput?.value || "").trim(),
    structureSignature: buildCanvasStructureSignature(documents, visibleDocuments),
  };
}

function scheduleCanvasPreviewRender() {
  scheduleCanvasRenderJob("preview", () => {
    renderCanvasPreviewFrame();
  });
}

function getActiveCanvasDocument(entries = history) {
  const documents = getCanvasDocumentCollection(entries);
  if (!documents.length) {
    return null;
  }

  const preferredId = String(activeCanvasDocumentId || getCanvasPreferredActiveDocumentId(entries) || "").trim();
  if (preferredId) {
    const matched = documents.find((document) => document.id === preferredId);
    if (matched) {
      return matched;
    }
  }

  return documents[documents.length - 1];
}

function setCanvasStatus(message, tone = "muted") {
  if (!canvasStatus) {
    return;
  }
  canvasStatus.textContent = String(message || "").trim() || "Canvas idle";
  canvasStatus.dataset.tone = tone;
}

function setCanvasSearchStatus(message, tone = "muted") {
  if (!canvasSearchStatus) {
    return;
  }

  const text = String(message || "").trim();
  canvasSearchStatus.dataset.tone = tone;
  canvasSearchStatus.hidden = !text;
  canvasSearchStatus.textContent = text;
}

function updateCanvasSearchFeedback(renderState, matchCount = 0) {
  const {
    documents,
    visibleDocuments,
    isStreamingPreviewActive,
    searchTerm,
  } = renderState;

  if (!documents.length || isCanvasEditing || isStreamingPreviewActive) {
    setCanvasSearchStatus("");
    return;
  }

  const roleValue = String(canvasRoleFilter?.value || "").trim();
  const pathValue = getCanvasPathFilterValue();
  if (!searchTerm && !roleValue && !pathValue) {
    setCanvasSearchStatus("");
    return;
  }

  if (!visibleDocuments.length) {
    const filterParts = [];
    if (searchTerm) {
      filterParts.push(`search \"${searchTerm}\"`);
    }
    if (roleValue) {
      filterParts.push(`role ${roleValue}`);
    }
    if (pathValue) {
      filterParts.push(pathValue === CANVAS_ROOT_PATH_FILTER ? "root files" : `path ${pathValue}`);
    }
    setCanvasSearchStatus(`No canvas files match ${filterParts.join(" · ")}.`, "warning");
    return;
  }

  if (searchTerm) {
    setCanvasSearchStatus(
      matchCount
        ? `${matchCount} search match${matchCount === 1 ? "" : "es"} across ${visibleDocuments.length} file${visibleDocuments.length === 1 ? "" : "s"}.`
        : `No text matches in ${visibleDocuments.length} filtered file${visibleDocuments.length === 1 ? "" : "s"}.`,
      matchCount ? "muted" : "warning"
    );
    return;
  }

  const filterCount = visibleDocuments.length;
  setCanvasSearchStatus(
    `${filterCount} file${filterCount === 1 ? "" : "s"} shown after filtering.`,
    "muted"
  );
}

function describeCanvasActiveDocumentChange(previousDocument, nextDocument, requestedDocumentId = "") {
  if (!nextDocument) {
    return "";
  }

  const previousId = String(previousDocument?.id || "").trim();
  const nextId = String(nextDocument.id || "").trim();
  const requestedId = String(requestedDocumentId || "").trim();
  const nextLabel = getCanvasDocumentDisplayName(nextDocument);
  if (requestedId && requestedId === nextId && requestedId !== previousId) {
    return `Active canvas switched to ${nextLabel}.`;
  }
  if (previousId && previousId !== nextId) {
    return `Previous active canvas is unavailable. Focus moved to ${nextLabel}.`;
  }
  return "";
}

function setCanvasHint(message, tone = "muted") {
  if (!canvasHint) {
    return;
  }

  const text = String(message || "").trim();
  if (!text) {
    canvasHint.hidden = true;
    canvasHint.textContent = "";
    canvasHint.dataset.tone = tone;
    return;
  }

  canvasHint.hidden = false;
  canvasHint.textContent = text;
  canvasHint.dataset.tone = tone;
}

function getCanvasFormatControlValue() {
  return canvasFormatSelect?.value === "code" ? "code" : "markdown";
}

function isCanvasMutationPending() {
  return Boolean(pendingCanvasMutation);
}

function getCanvasPendingMutationLabel() {
  return CANVAS_MUTATION_LABELS[pendingCanvasMutation] || "canvas update";
}

function guardCanvasMutation(actionLabel = "continue") {
  if (!isCanvasMutationPending()) {
    return false;
  }
  const normalizedActionLabel = String(actionLabel || "").trim();
  const actionSuffix = normalizedActionLabel ? ` before you ${normalizedActionLabel}` : "";
  setCanvasStatus(`Please wait for the current ${getCanvasPendingMutationLabel()} to finish${actionSuffix}.`, "muted");
  return true;
}

function setCanvasMutationState(nextMutation = "", { rerender = true } = {}) {
  const normalizedMutation = String(nextMutation || "").trim();
  if (pendingCanvasMutation === normalizedMutation) {
    return;
  }
  pendingCanvasMutation = normalizedMutation;
  if (canvasPanel) {
    canvasPanel.setAttribute("aria-busy", normalizedMutation ? "true" : "false");
    if (normalizedMutation) {
      canvasPanel.dataset.canvasMutation = normalizedMutation;
    } else {
      delete canvasPanel.dataset.canvasMutation;
    }
  }
  if (rerender && isCanvasOpen()) {
    renderCanvasPanel();
  }
}

function setCanvasButtonState(button, { disabled, hidden } = {}) {
  if (!button) {
    return;
  }
  if (typeof disabled === "boolean") {
    button.disabled = disabled;
  }
  if (typeof hidden === "boolean") {
    button.hidden = hidden;
  }
}

function setCanvasEmptyState(stateKey = "no_documents") {
  if (!canvasEmptyState) {
    return;
  }

  const state = CANVAS_EMPTY_STATES[stateKey] || CANVAS_EMPTY_STATES.no_documents;
  canvasEmptyState.hidden = false;
  canvasEmptyState.innerHTML = `<h3>${state.title}</h3><p>${state.message}</p>`;
}

function syncCanvasFormControls({
  formatDisabled = false,
  formatValue = null,
  searchDisabled = false,
  roleDisabled = false,
  pathDisabled = false,
} = {}) {
  const isBusy = isCanvasMutationPending();
  if (canvasFormatSelect) {
    canvasFormatSelect.disabled = formatDisabled || isBusy;
    if (formatValue !== null) {
      canvasFormatSelect.value = formatValue === "code" ? "code" : "markdown";
    }
  }
  if (canvasSearchInput) {
    canvasSearchInput.disabled = searchDisabled || isBusy;
  }
  if (canvasRoleFilter) {
    canvasRoleFilter.disabled = roleDisabled || isBusy;
  }
  if (canvasPathFilter) {
    canvasPathFilter.disabled = pathDisabled || isBusy;
  }
}

function syncCanvasActionButtons({
  hasDocuments = false,
  hasActiveDocument = false,
  isEditing = false,
  isStreamingPreviewActive = false,
  isPanelOpen = false,
  canEditDocument = false,
  canCopyDocument = false,
} = {}) {
  const isBusy = isCanvasMutationPending();
  setCanvasButtonState(canvasEditBtn, {
    hidden: isEditing,
    disabled: !hasActiveDocument || isStreamingPreviewActive || !canEditDocument || isBusy,
  });
  setCanvasButtonState(canvasNewBtn, {
    hidden: false,
    disabled: isStreamingPreviewActive || isBusy,
  });
  setCanvasButtonState(canvasUploadBtn, {
    hidden: false,
    disabled: isStreamingPreviewActive || isBusy,
  });
  setCanvasButtonState(canvasSaveBtn, {
    hidden: !isEditing,
    disabled: !isEditing || isStreamingPreviewActive || !hasActiveDocument || isBusy,
  });
  setCanvasButtonState(canvasCancelBtn, {
    hidden: !isEditing,
    disabled: !isEditing || isStreamingPreviewActive || isBusy,
  });
  setCanvasButtonState(canvasCopyBtn, {
    hidden: !isPanelOpen || !hasActiveDocument,
    disabled: !hasActiveDocument || isEditing || !canCopyDocument || isBusy,
  });
  setCanvasButtonState(canvasDeleteBtn, {
    disabled: !hasActiveDocument || isStreamingPreviewActive || isBusy,
  });
  setCanvasButtonState(canvasRenameBtn, {
    disabled: !hasActiveDocument || isEditing || isStreamingPreviewActive || isBusy,
  });
  setCanvasButtonState(canvasClearBtn, {
    disabled: !hasDocuments || isStreamingPreviewActive || isBusy,
  });
  setCanvasButtonState(canvasDownloadHtmlBtn, {
    disabled: !hasActiveDocument || isStreamingPreviewActive || isBusy,
  });
  setCanvasButtonState(canvasDownloadMdBtn, {
    disabled: !hasActiveDocument || isStreamingPreviewActive || isBusy,
  });
  setCanvasButtonState(canvasDownloadPdfBtn, {
    disabled: !hasActiveDocument || isStreamingPreviewActive || isBusy,
  });
}

function resetCanvasContentDisplay({ clearEditorValue = true, clearTabs = true } = {}) {
  clearCanvasEditingPreviewRender();
  isCanvasEditing = false;
  editingCanvasDocumentId = null;
  canvasWorkspaceMain?.classList.remove("canvas-workspace-main--editing");

  if (canvasEditorEl) {
    canvasEditorEl.classList.remove("canvas-editor--editing");
    canvasEditorEl.hidden = true;
    if (clearEditorValue) {
      canvasEditorEl.value = "";
    }
  }

  if (canvasDocumentEl) {
    canvasDocumentEl.hidden = true;
    canvasDocumentEl.classList.remove("canvas-document--editing-preview");
    canvasDocumentEl.innerHTML = "";
  }

  if (canvasDiffEl) {
    canvasDiffEl.hidden = true;
    canvasDiffEl.innerHTML = "";
  }

  if (clearTabs && canvasDocumentTabsEl) {
    canvasDocumentTabsEl.hidden = true;
    canvasDocumentTabsEl.innerHTML = "";
  }
}

function renderCanvasUnavailableState({
  subtitle,
  emptyStateKey,
  documents = [],
  isStreamingPreviewActive = false,
  enableFilters = false,
  clearSearchStatus = false,
} = {}) {
  resetCanvasMetaBar();
  if (canvasSubtitle) {
    canvasSubtitle.textContent = subtitle;
  }
  setCanvasHint("");
  if (clearSearchStatus) {
    setCanvasSearchStatus("");
  }
  setCanvasEmptyState(emptyStateKey);
  resetCanvasContentDisplay();
  syncCanvasFormControls({
    formatDisabled: isStreamingPreviewActive,
    formatValue: getCanvasFormatControlValue(),
    searchDisabled: !enableFilters,
    roleDisabled: !enableFilters,
    pathDisabled: !enableFilters,
  });
  syncCanvasActionButtons({
    hasDocuments: documents.length > 0,
    hasActiveDocument: false,
    isEditing: false,
    isStreamingPreviewActive,
    isPanelOpen: isCanvasOpen(),
    canEditDocument: false,
    canCopyDocument: false,
  });
  closeCanvasOverflowMenu();
}

function clearCanvasRenderJob(jobType) {
  const timer = jobType === "editing-preview" ? pendingCanvasEditorPreviewTimer : pendingCanvasPreviewTimer;
  if (!timer) {
    return;
  }
  if (typeof globalThis.cancelAnimationFrame === "function") {
    globalThis.cancelAnimationFrame(timer);
  } else {
    globalThis.clearTimeout(timer);
  }
  if (jobType === "editing-preview") {
    pendingCanvasEditorPreviewTimer = 0;
    return;
  }
  pendingCanvasPreviewTimer = 0;
}

function scheduleCanvasRenderJob(jobType, callback) {
  const isEditingPreviewJob = jobType === "editing-preview";
  if (isEditingPreviewJob ? pendingCanvasEditorPreviewTimer : pendingCanvasPreviewTimer) {
    return;
  }

  const flushRenderJob = () => {
    if (isEditingPreviewJob) {
      pendingCanvasEditorPreviewTimer = 0;
    } else {
      pendingCanvasPreviewTimer = 0;
    }
    callback();
  };

  const timer = typeof globalThis.requestAnimationFrame === "function"
    ? globalThis.requestAnimationFrame(flushRenderJob)
    : globalThis.setTimeout(flushRenderJob, CANVAS_PREVIEW_RENDER_INTERVAL_MS);

  if (isEditingPreviewJob) {
    pendingCanvasEditorPreviewTimer = timer;
    return;
  }
  pendingCanvasPreviewTimer = timer;
}

function clearCanvasEditingPreviewRender() {
  clearCanvasRenderJob("editing-preview");
}

function getCanvasEditingPreviewDocument(activeDocument = getActiveCanvasDocument()) {
  if (!activeDocument || !isCanvasEditing || !canvasEditorEl) {
    return activeDocument;
  }

  const previewFormat = getCanvasFormatControlValue();
  return normalizeCanvasDocument({
    ...activeDocument,
    format: previewFormat,
    content: canvasEditorEl.value,
  }) || activeDocument;
}

function scheduleCanvasEditingPreviewRender() {
  if (!isCanvasEditing) {
    return;
  }

  scheduleCanvasRenderJob("editing-preview", () => {
    if (!isCanvasEditing) {
      return;
    }
    const renderState = buildCanvasRenderState();
    if (!renderState.activeDocument) {
      renderCanvasPanel();
      return;
    }
    updateCanvasActiveDocumentDisplay(renderState);
  });
}

function setPendingDocumentCanvasOpen(files) {
  const documentItems = getDocumentCanvasPromptItems(files);
  if (!documentItems.length) {
    pendingDocumentCanvasOpen = null;
    return;
  }

  pendingDocumentCanvasOpen = {
    fileCount: documentItems.length,
    fileName: String(documentItems[0]?.name || "Document").trim() || "Document",
  };
}

function renderCanvasMetaBar(renderState) {
  if (!canvasMetaBar || !canvasMetaChips) {
    return;
  }

  const { activeDocument: baseActiveDocument, documents, isStreamingPreviewActive, visibleDocuments } = renderState;
  if (!baseActiveDocument || !(documents || []).length) {
    resetCanvasMetaBar();
    return;
  }

  const activeDocument = getCanvasEditingPreviewDocument(baseActiveDocument);

  const modeLabel = getCanvasMode(documents) === "project" ? "Project mode" : "Document mode";
  const countLabel = visibleDocuments.length === documents.length
    ? `${documents.length} file${documents.length === 1 ? "" : "s"}`
    : `${visibleDocuments.length}/${documents.length} shown`;
  const chips = [
    { label: modeLabel, className: "canvas-meta-chip canvas-meta-chip--primary" },
    { label: countLabel, className: "canvas-meta-chip" },
  ];

  if (isStreamingPreviewActive) {
    chips.push({ label: "Live preview", className: "canvas-meta-chip canvas-meta-chip--live" });
  }
  if (Number(activeDocument.page_count) > 1) {
    chips.push({ label: `${activeDocument.page_count} pages`, className: "canvas-meta-chip" });
  }
  if (activeDocument.role) {
    chips.push({ label: activeDocument.role, className: "canvas-meta-chip" });
  }
  chips.push({ label: activeDocument.format === "code" ? "Code" : "Markdown", className: "canvas-meta-chip" });
  if (activeDocument.language) {
    chips.push({ label: activeDocument.language, className: "canvas-meta-chip" });
  }

  const reference = getCanvasDocumentReference(activeDocument);
  if (reference) {
    chips.push({
      label: reference,
      className: "canvas-meta-chip canvas-meta-chip--path",
      title: reference,
    });
  }

  canvasMetaChips.innerHTML = chips.map((chip) => {
    const titleAttr = chip.title ? ` title="${escHtml(chip.title)}"` : "";
    return `<span class="${chip.className}"${titleAttr}>${escHtml(chip.label)}</span>`;
  }).join("");
  canvasMetaBar.hidden = false;

  if (canvasCopyRefBtn) {
    canvasCopyRefBtn.disabled = !reference;
    canvasCopyRefBtn.textContent = activeDocument.path ? "Copy path" : "Copy title";
  }
  if (canvasResetFiltersBtn) {
    canvasResetFiltersBtn.disabled = !hasActiveCanvasFilters();
  }
}

function renderCanvasDocumentTabs(visibleDocuments) {
  if (!canvasDocumentTabsEl) {
    return;
  }

  canvasDocumentTabsEl.hidden = visibleDocuments.length <= 1;
  canvasDocumentTabsEl.innerHTML = "";
  visibleDocuments.forEach((entry) => {
    const button = globalThis.document.createElement("button");
    button.type = "button";
    button.className = `canvas-document-tab${entry.id === activeCanvasDocumentId ? " active" : ""}`;
    button.textContent = getCanvasFileName(entry);
    button.title = `${getCanvasDocumentLabel(entry)} · ${entry.line_count} lines`;
    button.disabled = isCanvasEditing && entry.id !== activeCanvasDocumentId;
    button.addEventListener("click", () => {
      activeCanvasDocumentId = entry.id;
      renderCanvasPanel();
    });
    canvasDocumentTabsEl.appendChild(button);
  });
}

function updateCanvasActiveDocumentDisplay(renderState) {
  const {
    activeDocument,
    documents,
    isCanvasPanelOpen,
    isStreamingPreviewActive,
    searchTerm,
    visibleDocuments,
  } = renderState;

  const displayDocument = getCanvasEditingPreviewDocument(activeDocument);
  activeCanvasDocumentId = activeDocument.id;
  canvasWorkspaceMain?.classList.toggle("canvas-workspace-main--editing", Boolean(isCanvasEditing));
  const modeLabel = getCanvasMode(documents) === "project" ? "Project mode" : "Document mode";
  const detailLabel = displayDocument.path || displayDocument.title;
  const pageLabel = Number(displayDocument.page_count) > 1 ? ` · ${displayDocument.page_count} pages` : "";
  const roleLabel = displayDocument.role ? ` · ${displayDocument.role}` : "";
  const languageLabel = displayDocument.language ? ` · ${displayDocument.language}` : "";
  const visualLabel = isVisualCanvasDocument(displayDocument) ? " · visual preview" : "";
  canvasSubtitle.textContent = `${modeLabel} · ${visibleDocuments.length}/${documents.length} files · ${detailLabel} · ${displayDocument.line_count} lines${pageLabel}${roleLabel}${languageLabel}${visualLabel}`;
  renderCanvasMetaBar(renderState);
  const activeToolNames = Array.isArray(appSettings.active_tools) ? new Set(appSettings.active_tools) : new Set();
  const canScrollCanvas = activeToolNames.has("scroll_canvas_document");
  const canExpandCanvas = activeToolNames.has("expand_canvas_document");
  const promptLineLimit = Number(appSettings.canvas_prompt_max_lines || 250);
  const expandLineLimit = Number(appSettings.canvas_expand_max_lines || 1600);
  if (isStreamingPreviewActive) {
    const previewTool = String(displayDocument.tool || "").trim();
    setCanvasHint(
      CANVAS_EDIT_PREVIEW_TOOLS.has(previewTool)
        ? "Live Canvas edit preview. The preview updates as tool arguments stream in and is replaced by the committed document when the tool finishes."
        : "Live Canvas preview. The preview updates as the assistant streams content and is replaced by the committed document when the tool finishes.",
      "muted"
    );
  } else if (isCanvasEditing) {
    setCanvasHint("Edit mode. Make changes and save to commit.", "muted");
  } else if (isVisualCanvasDocument(displayDocument)) {
    setCanvasHint(
      "Visual canvas preview detected. This document is read-only and backed by page images, so line-based canvas edits do not apply.",
      "muted"
    );
  } else if (Number.isFinite(displayDocument.line_count) && displayDocument.line_count > promptLineLimit) {
    const hasExpandedRoom = displayDocument.line_count > expandLineLimit;
    setCanvasHint(
      hasExpandedRoom
        ? canScrollCanvas && canExpandCanvas
          ? "Large canvas detected. The default view is truncated. Use scroll_canvas_document for a targeted range or expand_canvas_document for a wider slice."
          : canExpandCanvas
            ? "Large canvas detected. The default view is truncated. Use expand_canvas_document for a wider slice."
            : canScrollCanvas
              ? "Large canvas detected. The default view is truncated. Use scroll_canvas_document for a targeted range."
              : "Large canvas detected. The default view is truncated."
        : canScrollCanvas
          ? `Large canvas detected. The default view is truncated to the first ${promptLineLimit} lines; use scroll_canvas_document for a targeted range.`
          : canExpandCanvas
            ? `Large canvas detected. The default view is truncated to the first ${promptLineLimit} lines; use expand_canvas_document for a wider slice.`
            : `Large canvas detected. The default view is truncated to the first ${promptLineLimit} lines.`,
      "warning"
    );
  } else {
    setCanvasHint("");
  }
  canvasEmptyState.hidden = true;
  syncCanvasFormControls({
    formatDisabled: !isCanvasEditing || isStreamingPreviewActive,
    formatValue: displayDocument.format || "markdown",
    searchDisabled: isCanvasEditing || isStreamingPreviewActive,
    roleDisabled: isCanvasEditing || isStreamingPreviewActive,
    pathDisabled: isCanvasEditing || isStreamingPreviewActive,
  });

  if (isCanvasEditing && canvasEditorEl) {
    if (editingCanvasDocumentId !== activeDocument.id) {
      editingCanvasDocumentId = activeDocument.id;
      canvasEditorEl.value = activeDocument.content || "";
    }
    canvasEditorEl.classList.add("canvas-editor--editing");
    canvasEditorEl.hidden = false;
    canvasDocumentEl.hidden = true;
  } else {
    canvasDocumentEl.classList.remove("canvas-document--editing-preview");
    canvasDocumentEl.hidden = false;
    if (activeDocument.isStreamingPreview) {
      const existingPreviewEl = canvasDocumentEl.querySelector('[data-canvas-streaming-preview-container="true"]');
      const existingPreviewId = String(existingPreviewEl?.getAttribute("data-canvas-streaming-preview-id") || "").trim();
      const existingPreviewFormat = String(existingPreviewEl?.getAttribute("data-canvas-streaming-preview-format") || "").trim();
      const nextPreviewId = String(activeDocument.id || "").trim();
      const nextPreviewFormat = String(activeDocument.format || "markdown").trim().toLowerCase() || "markdown";
      if (existingPreviewEl && existingPreviewId === nextPreviewId && existingPreviewFormat === nextPreviewFormat) {
        updateStreamingCanvasPreviewElement(existingPreviewEl, activeDocument);
      } else {
        canvasDocumentEl.innerHTML = renderStreamingCanvasDocumentBody(activeDocument);
      }
    } else {
      canvasDocumentEl.innerHTML = renderCanvasDocumentBody(activeDocument);
      bindCanvasPageNavigation(activeDocument);
    }
    if (canvasEditorEl) {
      canvasEditorEl.classList.remove("canvas-editor--editing");
      canvasEditorEl.hidden = true;
    }
  }

  renderCanvasDiffPreview(activeDocument);
  const matchCount = !isCanvasEditing && !isStreamingPreviewActive ? applyCanvasSearchHighlight(searchTerm) : 0;
  updateCanvasSearchFeedback(renderState, matchCount);
  const copySourceText = isCanvasEditing && canvasEditorEl ? canvasEditorEl.value : displayDocument.content;
  syncCanvasActionButtons({
    hasDocuments: documents.length > 0,
    hasActiveDocument: Boolean(activeDocument),
    isEditing: isCanvasEditing,
    isStreamingPreviewActive,
    isPanelOpen: isCanvasPanelOpen,
    canEditDocument: isCanvasDocumentEditable(displayDocument),
    canCopyDocument: !isVisualCanvasDocument(displayDocument) && Boolean(String(copySourceText || "").length),
  });
  closeCanvasOverflowMenu();
}

function renderCanvasPreviewFrame() {
  if (!canvasDocumentEl || !canvasEmptyState || !canvasSubtitle) {
    return;
  }

  flushStreamingCanvasPreviewDeltas();
  const renderState = buildCanvasRenderState();
  if (!renderState.documents.length || !renderState.activeDocument || isCanvasEditing || !renderState.isStreamingPreviewActive) {
    renderCanvasPanel();
    return;
  }

  if (renderState.structureSignature !== lastCanvasStructureSignature) {
    renderCanvasPanel();
    return;
  }

  updateCanvasActiveDocumentDisplay(renderState);
}

function consumePendingDocumentCanvasOpen() {
  const pendingRequest = pendingDocumentCanvasOpen;
  pendingDocumentCanvasOpen = null;
  return pendingRequest;
}

function isCanvasConfirmOpen() {
  return Boolean(canvasConfirmModal?.classList.contains("open"));
}

function closeCanvasConfirmModal(action = "cancel", executeHandler = true) {
  if (!canvasConfirmModal) {
    return;
  }

  const pendingAction = pendingCanvasConfirmAction;
  pendingCanvasConfirmAction = null;
  canvasConfirmModal.classList.remove("open");
  canvasConfirmOverlay?.classList.remove("open");
  canvasConfirmModal.setAttribute("aria-hidden", "true");
  if (canvasConfirmOpenBtn) {
    canvasConfirmOpenBtn.textContent = DEFAULT_CANVAS_CONFIRM_LABEL;
  }
  if (canvasConfirmLaterBtn) {
    canvasConfirmLaterBtn.textContent = DEFAULT_CANVAS_CONFIRM_CANCEL_LABEL;
  }

  if (lastCanvasConfirmTriggerEl && typeof lastCanvasConfirmTriggerEl.focus === "function") {
    lastCanvasConfirmTriggerEl.focus();
  }

  if (!executeHandler || !pendingAction) {
    return;
  }

  if (action === "confirm") {
    pendingAction.onConfirm?.();
    return;
  }

  if (action === "cancel") {
    pendingAction.onCancel?.();
    return;
  }

  pendingAction.onDismiss?.();
}

function openCanvasConfirmModal(options = {}) {
  if (!canvasConfirmModal || !canvasConfirmTitle || !canvasConfirmMessage) {
    options.onConfirm?.();
    return;
  }

  if (isCanvasConfirmOpen()) {
    closeCanvasConfirmModal("cancel", false);
  }

  closeMobileTools();
  closeExportPanel();
  closeStats();
  lastCanvasConfirmTriggerEl = document.activeElement instanceof HTMLElement ? document.activeElement : attachBtn;
  pendingCanvasConfirmAction = {
    onConfirm: typeof options.onConfirm === "function" ? options.onConfirm : null,
    onCancel: typeof options.onCancel === "function" ? options.onCancel : null,
    onDismiss: typeof options.onDismiss === "function"
      ? options.onDismiss
      : typeof options.onCancel === "function"
        ? options.onCancel
        : null,
  };
  canvasConfirmTitle.textContent = String(options.title || "Open document in Canvas?").trim() || "Open document in Canvas?";
  canvasConfirmMessage.textContent = String(options.message || "Your uploaded document is ready in Canvas.").trim() || "Your uploaded document is ready in Canvas.";
  if (canvasConfirmOpenBtn) {
    canvasConfirmOpenBtn.textContent = String(options.confirmLabel || DEFAULT_CANVAS_CONFIRM_LABEL).trim() || DEFAULT_CANVAS_CONFIRM_LABEL;
  }
  if (canvasConfirmLaterBtn) {
    canvasConfirmLaterBtn.textContent = String(options.cancelLabel || DEFAULT_CANVAS_CONFIRM_CANCEL_LABEL).trim() || DEFAULT_CANVAS_CONFIRM_CANCEL_LABEL;
  }
  canvasConfirmModal.classList.add("open");
  canvasConfirmOverlay?.classList.add("open");
  canvasConfirmModal.setAttribute("aria-hidden", "false");
  canvasConfirmOpenBtn?.focus();
}

function promptPdfSubmissionMode(files) {
  const pdfFiles = (files || []).filter((file) => isPdfDocumentFile(file));
  if (!pdfFiles.length) {
    return Promise.resolve(true);
  }

  const requestLabel = pdfFiles.length === 1
    ? `How should ${String(pdfFiles[0]?.name || "this PDF").trim() || "this PDF"} be sent?`
    : `How should these ${pdfFiles.length} PDFs be sent?`;
  const message = pdfFiles.length === 1
    ? `Choose visual mode for page-image analysis with vision-capable models. Visual mode sends up to the first ${VISUAL_PDF_PAGE_LIMIT} pages as images, while text mode extracts text and keeps Canvas editing available.`
    : `Choose one mode for this PDF batch. Visual mode sends up to the first ${VISUAL_PDF_PAGE_LIMIT} pages of each PDF as images. Text mode extracts text and keeps Canvas editing available.`;

  return new Promise((resolve) => {
    openCanvasConfirmModal({
      title: requestLabel,
      message,
      confirmLabel: "Send visually",
      cancelLabel: "Send as text",
      onConfirm: () => {
        pdfFiles.forEach((file) => setDocumentSubmissionMode(file, "visual"));
        renderAttachmentPreview();
        resolve(true);
      },
      onCancel: () => {
        pdfFiles.forEach((file) => setDocumentSubmissionMode(file, "text"));
        renderAttachmentPreview();
        resolve(true);
      },
      onDismiss: () => resolve(false),
    });
  });
}

function normalizeDocumentCanvasPromptItem(item) {
  if (!item || typeof item !== "object") {
    return null;
  }

  if (typeof File !== "undefined" && item instanceof File) {
    if (!isDocumentFile(item)) {
      return null;
    }
    const fileName = String(item.name || "document").trim() || "document";
    return { name: fileName };
  }

  const kind = String(item.kind || "").trim().toLowerCase();
  if (kind && kind !== "document") {
    return null;
  }

  const fileName = String(item.file_name || item.name || "document").trim() || "document";
  return { name: fileName };
}

function getDocumentCanvasPromptItems(items) {
  return (items || [])
    .map((item) => normalizeDocumentCanvasPromptItem(item))
    .filter(Boolean);
}

function getExistingDocumentAttachmentsForCanvasPrompt(message) {
  return getMessageAttachments(message?.metadata).filter((attachment) => String(attachment.kind || "").trim().toLowerCase() === "document");
}

function escapeRegExp(text) {
  return String(text || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function promptDocumentCanvasAction(files) {
  const documentItems = getDocumentCanvasPromptItems(files);
  if (!documentItems.length) {
    return Promise.resolve("prompt");
  }

  if (!canvasConfirmModal || !canvasConfirmTitle || !canvasConfirmMessage) {
    return Promise.resolve("prompt");
  }

  const fileCount = documentItems.length;
  const fileName = String(documentItems[0]?.name || "document").trim() || "document";
  const requestLabel = fileCount > 1 ? `${fileCount} documents` : fileName;
  const pronoun = fileCount > 1 ? "them" : "it";

  return new Promise((resolve) => {
    openCanvasConfirmModal({
      title: "Open document in Canvas?",
      message: `${requestLabel} can be added to AI Canvas for editing and later reuse. Choose Later to keep ${pronoun} attached to this message only.`,
      onConfirm: () => resolve("open"),
      onCancel: () => resolve("skip"),
      onDismiss: () => resolve("skip"),
    });
  });
}

function setCanvasAttention(enabled) {
  canvasHasUnreadUpdates = Boolean(enabled);
  if (canvasBtnIndicator) {
    canvasBtnIndicator.hidden = !canvasHasUnreadUpdates;
  }
}

function setExportStatus(message, tone = "muted") {
  if (!exportStatus) {
    return;
  }
  exportStatus.textContent = String(message || "").trim() || "Export idle";
  exportStatus.dataset.tone = tone;
}

function updateExportPanel() {
  if (!exportSubtitle) {
    return;
  }
  exportSubtitle.textContent = currentConvId
    ? `Current conversation: ${currentConvTitle || `Chat #${currentConvId}`}`
    : "Open or create a conversation before exporting.";
}

function isCanvasOpen() {
  return Boolean(canvasPanel?.classList.contains("open"));
}

function syncCanvasToggleButton() {
  if (!canvasToggleBtn) {
    return;
  }
  canvasToggleBtn.setAttribute("aria-expanded", String(isCanvasOpen()));
}

function canToggleCanvasTreeOnMobile() {
  return Boolean(isMobileViewport() && canvasTreePanel && !canvasTreePanel.hidden);
}

function syncCanvasTreeToggleButton() {
  if (!canvasTreeToggleBtn) {
    return;
  }
  const isAvailable = canToggleCanvasTreeOnMobile();
  if (!isAvailable) {
    isCanvasMobileTreeOpen = false;
    canvasPanel?.classList.remove("canvas-panel--tree-open");
  }
  canvasTreeToggleBtn.hidden = !isAvailable;
  canvasTreeToggleBtn.setAttribute("aria-expanded", isAvailable && isCanvasMobileTreeOpen ? "true" : "false");
  canvasTreeToggleBtn.textContent = isAvailable && isCanvasMobileTreeOpen ? "Hide files" : "Files";
}

function setCanvasMobileTreeOpen(isOpen) {
  const shouldOpen = Boolean(canToggleCanvasTreeOnMobile() && isOpen);
  isCanvasMobileTreeOpen = shouldOpen;
  canvasPanel?.classList.toggle("canvas-panel--tree-open", shouldOpen);
  syncCanvasTreeToggleButton();
}

function getCanvasFocusableElements() {
  if (!canvasPanel) {
    return [];
  }
  return Array.from(
    canvasPanel.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
  ).filter((element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true");
}

function applyCanvasSearchHighlight(query) {
  if (!canvasDocumentEl) {
    return 0;
  }

  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) {
    return 0;
  }

  const pattern = escapeRegExp(normalizedQuery);
  const selectorMatcher = new RegExp(pattern, "i");
  const walker = document.createTreeWalker(canvasDocumentEl, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parentName = node.parentNode?.nodeName;
      if (!node.textContent?.trim()) {
        return NodeFilter.FILTER_REJECT;
      }
      if (parentName === "SCRIPT" || parentName === "STYLE" || parentName === "MARK") {
        return NodeFilter.FILTER_REJECT;
      }
      return selectorMatcher.test(node.textContent) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });

  const textNodes = [];
  let currentNode;
  while ((currentNode = walker.nextNode())) {
    textNodes.push(currentNode);
  }

  let matchCount = 0;
  textNodes.forEach((textNode) => {
    const source = textNode.textContent || "";
    const fragment = document.createDocumentFragment();
    const highlightMatcher = new RegExp(pattern, "gi");
    let lastIndex = 0;

    source.replace(highlightMatcher, (matched, offset) => {
      if (offset > lastIndex) {
        fragment.appendChild(document.createTextNode(source.slice(lastIndex, offset)));
      }
      const mark = document.createElement("mark");
      mark.textContent = matched;
      fragment.appendChild(mark);
      lastIndex = offset + matched.length;
      matchCount += 1;
      return matched;
    });

    if (lastIndex < source.length) {
      fragment.appendChild(document.createTextNode(source.slice(lastIndex)));
    }

    textNode.parentNode.replaceChild(fragment, textNode);
  });

  return matchCount;
}

function renderCanvasPanel() {
  if (!canvasDocumentEl || !canvasEmptyState || !canvasSubtitle) {
    return;
  }

  flushStreamingCanvasPreviewDeltas();
  const documents = getCanvasRenderableDocuments();
  syncCanvasFilterControls(documents);
  const renderState = buildCanvasRenderState(documents);
  const {
    activeDocument,
    documents: renderDocuments,
    isStreamingPreviewActive,
    visibleDocuments,
  } = renderState;
  lastCanvasStructureSignature = renderState.structureSignature;

  renderCanvasTree(renderDocuments, activeDocument);
  if (!renderDocuments.length) {
    renderCanvasUnavailableState({
      subtitle: "No canvas document yet.",
      emptyStateKey: "no_documents",
      documents: renderDocuments,
      isStreamingPreviewActive,
      enableFilters: false,
      clearSearchStatus: true,
    });
    return;
  }

  if (!activeDocument) {
    const modeLabel = getCanvasMode(renderDocuments) === "project" ? "Project mode" : "Document mode";
    renderCanvasUnavailableState({
      subtitle: `${modeLabel} · ${renderDocuments.length} file${renderDocuments.length === 1 ? "" : "s"} · no matches`,
      emptyStateKey: "no_matches",
      documents: renderDocuments,
      isStreamingPreviewActive,
      enableFilters: true,
    });
    updateCanvasSearchFeedback(renderState, 0);
    return;
  }

  updateCanvasActiveDocumentDisplay(renderState);
  renderCanvasDocumentTabs(visibleDocuments);
}

function openCanvas(triggerEl = null, options = {}) {
  const shouldFocusPanel = options.focusPanel !== false;
  closeMemoryPanel();
  closeSummaryPanel();
  closeMobileTools();
  closeCanvasConfirmModal("cancel", false);
  closeStats();
  closeExportPanel();
  closeSidebarOnMobile();
  canvasPanel?.classList.add("open");
  canvasOverlay?.classList.add("open");
  canvasPanel?.setAttribute("aria-hidden", "false");
  syncCanvasToggleButton();
  lastCanvasTriggerEl = triggerEl instanceof HTMLElement
    ? triggerEl
    : (document.activeElement instanceof HTMLElement ? document.activeElement : mobileToolsBtn);
  setCanvasAttention(false);
  setCanvasMobileTreeOpen(false);
  applyCanvasPanelWidth(readCanvasWidthPreference(), false);
  closeCanvasOverflowMenu();
  renderCanvasPanel();
  if (shouldFocusPanel) {
    canvasClose?.focus();
  }
}

function closeCanvas() {
  clearCanvasEditingPreviewRender();
  isCanvasEditing = false;
  editingCanvasDocumentId = null;
  canvasWorkspaceMain?.classList.remove("canvas-workspace-main--editing");
  canvasEditorEl?.classList.remove("canvas-editor--editing");
  canvasDocumentEl?.classList.remove("canvas-document--editing-preview");
  setCanvasMobileTreeOpen(false);
  canvasPanel?.classList.remove("open");
  canvasOverlay?.classList.remove("open");
  canvasPanel?.setAttribute("aria-hidden", "true");
  closeCanvasOverflowMenu();
  syncCanvasToggleButton();
  if (canvasCopyBtn) {
    canvasCopyBtn.hidden = true;
  }
  if (lastCanvasTriggerEl && typeof lastCanvasTriggerEl.focus === "function") {
    lastCanvasTriggerEl.focus();
  }
}

function isCanvasOverflowMenuOpen() {
  return Boolean(canvasOverflowMenu && !canvasOverflowMenu.hidden);
}

function getCanvasOverflowMenuItems() {
  if (!canvasOverflowMenu) {
    return [];
  }
  return Array.from(canvasOverflowMenu.querySelectorAll('[role="menuitem"]')).filter((item) => {
    if (!(item instanceof HTMLElement) || item.hidden || item.getAttribute("aria-hidden") === "true") {
      return false;
    }
    if ("disabled" in item && item.disabled) {
      return false;
    }
    return true;
  });
}

function focusCanvasOverflowMenuItem(target = "first") {
  const items = getCanvasOverflowMenuItems();
  if (!items.length) {
    return;
  }
  if (target === "last") {
    items[items.length - 1].focus();
    return;
  }
  items[0].focus();
}

function closeCanvasOverflowMenu({ restoreFocus = false } = {}) {
  if (!canvasOverflowMenu || !canvasMoreBtn) {
    return;
  }
  canvasOverflowMenu.hidden = true;
  canvasOverflowMenu.classList.remove("open");
  canvasMoreBtn.setAttribute("aria-expanded", "false");
  if (restoreFocus) {
    canvasMoreBtn.focus();
  }
}

function openCanvasOverflowMenu({ focusTarget = null } = {}) {
  if (!canvasOverflowMenu || !canvasMoreBtn) {
    return;
  }
  canvasOverflowMenu.hidden = false;
  canvasOverflowMenu.classList.add("open");
  canvasMoreBtn.setAttribute("aria-expanded", "true");
  if (focusTarget) {
    globalThis.requestAnimationFrame(() => {
      focusCanvasOverflowMenuItem(focusTarget);
    });
  }
}

function moveCanvasOverflowMenuFocus(step = 1) {
  const items = getCanvasOverflowMenuItems();
  if (!items.length) {
    return;
  }
  const currentIndex = items.indexOf(document.activeElement);
  const baseIndex = currentIndex >= 0 ? currentIndex : (step < 0 ? 0 : -1);
  const nextIndex = (baseIndex + step + items.length) % items.length;
  items[nextIndex].focus();
}

function handleCanvasOverflowMenuKeydown(event) {
  if (!isCanvasOverflowMenuOpen()) {
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    closeCanvasOverflowMenu({ restoreFocus: true });
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    moveCanvasOverflowMenuFocus(1);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    moveCanvasOverflowMenuFocus(-1);
    return;
  }
  if (event.key === "Home") {
    event.preventDefault();
    focusCanvasOverflowMenuItem("first");
    return;
  }
  if (event.key === "End") {
    event.preventDefault();
    focusCanvasOverflowMenuItem("last");
  }
}

function toggleCanvasOverflowMenu(options = {}) {
  if (isCanvasOverflowMenuOpen()) {
    closeCanvasOverflowMenu();
    return;
  }
  if (isCanvasMobileTreeOpen) {
    setCanvasMobileTreeOpen(false);
  }
  openCanvasOverflowMenu(options);
}

function openExportPanel(triggerEl = null) {
  closeMobileTools();
  closeStats();
  closeCanvas();
  closeSummaryPanel();
  closeMemoryPanel();
  updateExportPanel();
  exportPanel?.classList.add("open");
  exportOverlay?.classList.add("open");
  exportPanel?.setAttribute("aria-hidden", "false");
  lastExportTriggerEl = triggerEl instanceof HTMLElement
    ? triggerEl
    : (document.activeElement instanceof HTMLElement ? document.activeElement : mobileToolsBtn);
  exportClose?.focus();
}

async function pruneConversationHistory() {
  if (!currentConvId) {
    showToast("No active conversation.", "warning");
    return;
  }
  const raw = window.prompt("How many of the first unpruned messages should be pruned?", "5");
  if (raw === null) {
    return;
  }
  const count = parseInt(raw, 10);
  if (!Number.isInteger(count) || count < 1 || count > 50) {
    showToast("Please enter a number between 1 and 50.", "warning");
    return;
  }
  if (mobilePruneBtn) {
    mobilePruneBtn.disabled = true;
  }
  try {
    const response = await fetch(`/api/conversations/${currentConvId}/prune-batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ count }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(data?.error || "Pruning failed.");
    }
    if (Array.isArray(data.messages)) {
      history = data.messages.map(normalizeHistoryEntry);
      rebuildTokenStatsFromHistory();
      renderConversationHistory();
    }
    loadSidebar();
    showToast(
      data.pruned_count > 0
        ? `${data.pruned_count} message${data.pruned_count === 1 ? " was" : "s were"} pruned.`
        : "No eligible messages found.",
      "success",
    );
  } catch (error) {
    showError(error.message || "Pruning failed.");
  } finally {
    if (mobilePruneBtn) {
      mobilePruneBtn.disabled = false;
    }
  }
}

function closeExportPanel() {
  exportPanel?.classList.remove("open");
  exportOverlay?.classList.remove("open");
  exportPanel?.setAttribute("aria-hidden", "true");
  if (lastExportTriggerEl && typeof lastExportTriggerEl.focus === "function") {
    lastExportTriggerEl.focus();
  }
}

function isSummaryPanelOpen() {
  return Boolean(summaryPanel?.classList.contains("open"));
}

function openSummaryPanel(triggerEl = null) {
  closeMobileTools();
  closeStats();
  closeCanvas();
  closeExportPanel();
  closeMemoryPanel();
  summaryPanel?.classList.add("open");
  summaryOverlay?.classList.add("open");
  summaryPanel?.setAttribute("aria-hidden", "false");
  lastSummaryTriggerEl = triggerEl instanceof HTMLElement
    ? triggerEl
    : (document.activeElement instanceof HTMLElement ? document.activeElement : mobileSummaryBtn);
  if (!isSummaryOperationInFlight) {
    resetSummaryProgress({ hide: true });
  }
  if (summaryPreviewConversationId !== currentConvId) {
    resetSummaryPreview({ hide: true });
  }
  renderSummaryInspector();
  setSummaryBusyState(isSummaryOperationInFlight);
  void refreshSummarySettingsFromServer();
  if (summaryFocusInput) {
    window.setTimeout(() => summaryFocusInput.focus({ preventScroll: true }), 0);
  }
}

function closeSummaryPanel({ restoreFocus = true } = {}) {
  summaryPanel?.classList.remove("open");
  summaryOverlay?.classList.remove("open");
  summaryPanel?.setAttribute("aria-hidden", "true");
  if (restoreFocus && lastSummaryTriggerEl && typeof lastSummaryTriggerEl.focus === "function") {
    lastSummaryTriggerEl.focus();
  }
}

async function runConversationSummary({ triggerButton = null, closePanel = false } = {}) {
  if (!currentConvId) {
    showToast("No active conversation to summarize.", "warning");
    return;
  }

  const originalButtonText = triggerButton ? triggerButton.textContent : "";
  const requestBody = buildSummaryRequestBody();

  setSummaryBusyState(true);
  startSummaryProgress("Selecting messages…");
  if (triggerButton) {
    triggerButton.disabled = true;
    triggerButton.textContent = "Summarizing…";
  }

  try {
    const response = await fetch(`/api/conversations/${currentConvId}/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to summarize.");
    }
    if (data.applied) {
      if (Array.isArray(data.messages)) {
        history = data.messages.map(normalizeHistoryEntry);
        rebuildTokenStatsFromHistory();
        renderConversationHistory();
      }
      resetSummaryPreview({ hide: true });
      const coveredCount = Number(data.covered_message_count || 0);
      finishSummaryProgress(
        coveredCount > 0
          ? `${coveredCount} message${coveredCount === 1 ? " was" : "s were"} summarized.`
          : "Summary completed."
      );
      showToast(
        coveredCount > 0
          ? `${coveredCount} message${coveredCount === 1 ? " was" : "s were"} summarized.`
          : "Summary completed.",
        "success"
      );
      latestSummaryStatus = { applied: true, reason: "applied", failure_stage: null, failure_detail: "Manual summary completed." };
    } else {
      failSummaryProgress(data.failure_detail || data.reason || "Summary was not applied.");
      showToast(data.failure_detail || data.reason || "Summary was not applied.", "warning");
      latestSummaryStatus = { applied: false, reason: data.reason, failure_detail: data.failure_detail };
    }
    renderSummaryInspector();
  } catch (error) {
    failSummaryProgress(error.message || "Failed to summarize.");
    showToast(error.message, "error");
  } finally {
    setSummaryBusyState(false);
    if (triggerButton) {
      triggerButton.disabled = false;
      triggerButton.textContent = originalButtonText || (closePanel ? "Summarize Conversation" : "Summarize now");
      if (closePanel && typeof triggerButton.focus === "function") {
        triggerButton.focus();
      }
    }
    renderSummaryInspector();
  }
}

async function previewConversationSummary({ triggerButton = null } = {}) {
  if (!currentConvId) {
    showToast("No active conversation to preview.", "warning");
    return;
  }

  const originalButtonText = triggerButton ? triggerButton.textContent : "";
  const requestBody = buildSummaryRequestBody();

  setSummaryBusyState(true);
  startSummaryProgress("Preparing preview…");
  if (triggerButton) {
    triggerButton.disabled = true;
    triggerButton.textContent = "Previewing…";
  }

  try {
    const response = await fetch(`/api/conversations/${currentConvId}/summarize/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to preview summary.");
    }

    if (data.preview && data.reason === "preview") {
      renderSummaryPreview(data);
      finishSummaryProgress("Preview ready.");
      showToast("Summary preview updated.", "success");
      return;
    }

    resetSummaryPreview({ hide: false });
    if (summaryPreviewList) {
      summaryPreviewList.innerHTML = `<div class="summary-preview-empty">${escHtml(String(data.failure_detail || data.reason || "No preview data available."))}</div>`;
    }
    failSummaryProgress(data.failure_detail || data.reason || "Preview was not available.");
    showToast(data.failure_detail || data.reason || "Preview was not available.", "warning");
  } catch (error) {
    failSummaryProgress(error.message || "Failed to preview summary.");
    showToast(error.message || "Failed to preview summary.", "error");
  } finally {
    setSummaryBusyState(false);
    if (triggerButton) {
      triggerButton.disabled = false;
      triggerButton.textContent = originalButtonText || "Preview Selection";
    }
  }
}

async function downloadConversation(format) {
  if (!currentConvId) {
    setExportStatus("Conversation is not available yet.", "warning");
    return;
  }

  setExportStatus(`Preparing ${format.toUpperCase()} export…`, "muted");
  try {
    const reasoningByMessageId = collectConversationReasoningExportMap();
    const response = await fetch(`/api/conversations/${currentConvId}/export?format=${encodeURIComponent(format)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reasoning_by_message_id: reasoningByMessageId }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Conversation export failed.");
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = getSuggestedDownloadFilename(response, `${currentConvTitle || "conversation"}.${format}`);
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setExportStatus(`${format.toUpperCase()} download is ready.`, "success");
  } catch (error) {
    setExportStatus(error.message || "Conversation export failed.", "danger");
  }
}

function getSuggestedDownloadFilename(response, fallbackFilename) {
  const contentDisposition = response.headers.get("content-disposition") || "";
  const utf8Match = contentDisposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  const plainMatch = contentDisposition.match(/filename\s*=\s*"([^"]+)"/i) || contentDisposition.match(/filename\s*=\s*([^;]+)/i);
  const rawFilename = (utf8Match && utf8Match[1]) || (plainMatch && plainMatch[1]) || "";
  if (!rawFilename) {
    return fallbackFilename;
  }

  try {
    return decodeURIComponent(rawFilename);
  } catch (_) {
    return rawFilename;
  }
}

function collectConversationReasoningExportMap(entries = history, conversationId = currentConvId) {
  const reasoningByMessageId = {};
  getVisibleHistoryEntries(entries).forEach((message) => {
    if (!message || message.role !== "assistant" || !isPersistedMessageId(message.id)) {
      return;
    }

    const reasoningText = getReasoningText(message.metadata, message.id, conversationId);
    if (!reasoningText) {
      return;
    }

    reasoningByMessageId[String(message.id)] = reasoningText;
  });
  return reasoningByMessageId;
}

async function downloadCanvasDocument(format) {
  const canvasDocument = getActiveCanvasDocument();
  if (!canvasDocument || !currentConvId) {
    setCanvasStatus("Canvas document is not available yet.", "warning");
    return;
  }

  setCanvasStatus(`Preparing ${format.toUpperCase()} download…`, "muted");
  try {
    const response = await fetch(`/api/conversations/${currentConvId}/canvas/export?format=${encodeURIComponent(format)}&document_id=${encodeURIComponent(canvasDocument.id)}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Canvas export failed.");
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = getSuggestedDownloadFilename(response, `${canvasDocument.title}.${format}`);
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setCanvasStatus(`${format.toUpperCase()} download is ready.`, "success");
  } catch (error) {
    setCanvasStatus(error.message || "Canvas export failed.", "danger");
  }
}

async function deleteCanvasDocuments({ documentId = null, clearAll = false, confirmed = false } = {}) {
  if (!currentConvId) {
    setCanvasStatus("Canvas is not available yet.", "warning");
    return;
  }

  const activeDocument = getActiveCanvasDocument();
  const targetDocumentId = documentId || activeDocument?.id || null;
  if (!clearAll && !targetDocumentId) {
    setCanvasStatus("No canvas document is available to delete.", "warning");
    return;
  }
  if (guardCanvasMutation(clearAll ? "clear Canvas" : "delete the active file")) {
    return;
  }

  if (!confirmed) {
    openCanvasConfirmModal({
      title: "Are you sure?",
      message: clearAll
        ? "This will permanently remove every file from Canvas."
        : `This will permanently remove ${activeDocument?.title || "this canvas document"} from Canvas.`,
      confirmLabel: clearAll ? "Clear all" : "Delete",
      cancelLabel: "Cancel",
      onConfirm: () => {
        void deleteCanvasDocuments({ documentId: targetDocumentId, clearAll, confirmed: true });
      },
    });
    return;
  }

  cancelPendingConversationRefreshes();
  setCanvasMutationState(clearAll ? "clear" : "delete");
  try {
    const params = new URLSearchParams();
    if (targetDocumentId) {
      params.set("document_id", targetDocumentId);
    }
    if (clearAll) {
      params.set("clear_all", "true");
    }

    const query = params.toString();
    const response = await fetch(`/api/conversations/${currentConvId}/canvas${query ? `?${query}` : ""}`, {
      method: "DELETE",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Canvas delete failed.");
    }
    setCanvasMutationState("", { rerender: false });
    history = Array.isArray(payload.messages) ? payload.messages.map(normalizeHistoryEntry) : history;
    streamingCanvasDocuments = [];
    pendingCanvasDiff = null;
    isCanvasEditing = false;
    editingCanvasDocumentId = null;
    activeCanvasDocumentId = payload.cleared
      ? null
      : String(payload.active_document_id || getActiveCanvasDocument(history)?.id || "").trim() || null;
    renderConversationHistory();
    renderCanvasPanel();

    if (payload.cleared) {
      setCanvasAttention(false);
      setCanvasStatus("Canvas cleared.", "success");
      return;
    }

    setCanvasStatus("Canvas document deleted.", "success");
  } catch (error) {
    setCanvasMutationState("", { rerender: false });
    renderCanvasPanel();
    setCanvasStatus(error.message || "Canvas delete failed.", "danger");
  }
}

async function renameCanvasDocument() {
  const activeDocument = getActiveCanvasDocument();
  if (!currentConvId || !activeDocument) {
    setCanvasStatus("No canvas document to rename.", "warning");
    return;
  }
  if (guardCanvasMutation("rename the active file")) {
    return;
  }
  const currentTitle = String(activeDocument.path || activeDocument.title || "").trim() || "Untitled";
  const nextTitle = String(globalThis.prompt("Rename document", currentTitle) || "").trim();
  if (!nextTitle || nextTitle === currentTitle) {
    return;
  }
  setCanvasStatus("Renaming...", "muted");
  setCanvasMutationState("rename");
  try {
    const response = await fetch(`/api/conversations/${currentConvId}/canvas`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_id: activeDocument.id, title: nextTitle }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Rename failed.");
    }
    setCanvasMutationState("", { rerender: false });
    history = Array.isArray(payload.messages) ? payload.messages.map(normalizeHistoryEntry) : history;
    activeCanvasDocumentId = String(payload.active_document_id || activeDocument.id || "").trim() || activeCanvasDocumentId;
    renderConversationHistory({ preserveScroll: true });
    renderCanvasPanel();
    setCanvasStatus(`Renamed to "${nextTitle}".`, "success");
  } catch (error) {
    setCanvasMutationState("", { rerender: false });
    renderCanvasPanel();
    setCanvasStatus(error.message || "Rename failed.", "danger");
  }
}

async function saveCanvasEdits() {
  const activeDocument = getActiveCanvasDocument();
  if (!currentConvId || !activeDocument || !canvasEditorEl) {
    setCanvasStatus("Canvas document is not available yet.", "warning");
    return;
  }
  if (guardCanvasMutation("save the active file again")) {
    return;
  }

  const nextContent = canvasEditorEl.value.replace(/\r\n?/g, "\n");
  const nextFormat = getCanvasFormatControlValue();
  cancelPendingConversationRefreshes();
  setCanvasMutationState("save");
  setCanvasStatus("Saving canvas edits...", "muted");

  try {
    const response = await fetch(`/api/conversations/${currentConvId}/canvas`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        document_id: activeDocument.id,
        content: nextContent,
        format: nextFormat,
        language: activeDocument.language || null,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Canvas save failed.");
    }

    setCanvasMutationState("", { rerender: false });
    history = Array.isArray(payload.messages) ? payload.messages.map(normalizeHistoryEntry) : history;
    streamingCanvasDocuments = [];
    pendingCanvasDiff = null;
    activeCanvasDocumentId = String(payload.active_document_id || activeDocument.id).trim() || activeDocument.id;
    isCanvasEditing = false;
    editingCanvasDocumentId = null;
    renderConversationHistory();
    renderCanvasPanel();
    setCanvasStatus("Canvas saved.", "success");
  } catch (error) {
    setCanvasMutationState("", { rerender: false });
    renderCanvasPanel();
    setCanvasStatus(error.message || "Canvas save failed.", "danger");
  }
}

function renderBubbleWithCursor(bubbleEl, text) {
  if (!bubbleEl) {
    return;
  }

  bubbleEl.hidden = false;
  bubbleEl.classList.add("streaming-text");
  bubbleEl.innerHTML = renderStreamingMarkdown(text);

  const findStreamingCursorContainer = (rootEl) => {
    let cursorHost = rootEl;
    while (cursorHost instanceof Element && cursorHost.lastChild) {
      const lastChild = cursorHost.lastChild;
      if (lastChild.nodeType === Node.TEXT_NODE) {
        if (String(lastChild.textContent || "").trim()) {
          return cursorHost;
        }
        lastChild.remove();
        continue;
      }
      if (!(lastChild instanceof Element)) {
        return cursorHost;
      }
      if (["BR", "HR", "IMG", "INPUT"].includes(lastChild.tagName)) {
        return cursorHost;
      }
      cursorHost = lastChild;
    }
    return rootEl;
  };

  const cursorEl = document.createElement("span");
  cursorEl.className = "stream-cursor";
  cursorEl.textContent = "▋";
  findStreamingCursorContainer(bubbleEl).appendChild(cursorEl);
}

function renderBubbleMarkdown(bubbleEl, text) {
  if (!bubbleEl) {
    return;
  }

  bubbleEl.hidden = false;
  bubbleEl.classList.remove("streaming-text");
  bubbleEl.innerHTML = renderMarkdown(text);
}

function finalizeAssistantBubble(asstBubble, text) {
  if (!asstBubble) {
    return;
  }

  const normalizedText = String(text || "").trim();
  if (!normalizedText) {
    asstBubble.remove();
    return;
  }

  asstBubble.classList.remove("thinking");
  asstBubble.classList.remove("cursor");
  renderBubbleMarkdown(asstBubble, normalizedText);
}

const INPUT_BREAKDOWN_ORDER = [
  "core_instructions",
  "tool_specs",
  "canvas",
  "scratchpad",
  "tool_trace",
  "tool_memory",
  "rag_context",
  "internal_state",
  "user_messages",
  "assistant_history",
  "assistant_tool_calls",
  "tool_results",
  "unknown_provider_overhead",
];

const INPUT_BREAKDOWN_LABELS = {
  core_instructions: "Core instructions",
  tool_specs: "Tool definitions",
  canvas: "Canvas",
  scratchpad: "Scratchpad",
  tool_trace: "Tool trace",
  tool_memory: "Tool memory",
  rag_context: "RAG context",
  internal_state: "Agent working state",
  user_messages: "User messages",
  assistant_history: "Assistant history",
  assistant_tool_calls: "Assistant tool calls",
  tool_results: "Tool results",
  unknown_provider_overhead: "Unknown/Provider overhead",
};

const INPUT_BREAKDOWN_HELP_TEXT = {
  tool_specs: "Prompt tool list plus API function schema sent with the request.",
  internal_state: "Short internal working-memory instructions added during blocker handling or recovery.",
  unknown_provider_overhead: "The remaining billed prompt tokens left after local content, tool, and request-framing estimates are aligned to the provider total.",
};

const BREAKDOWN_WARNING_RATIO = 0.03;

const BREAKDOWN_REDUCTION_ORDER = [
  "tool_specs",
  "internal_state",
  "canvas",
  "scratchpad",
  "tool_trace",
  "tool_memory",
  "rag_context",
  "assistant_tool_calls",
  "tool_results",
  "assistant_history",
  "user_messages",
  "core_instructions",
];

const BREAKDOWN_FLOOR_KEYS = ["user_messages", "tool_results"];

const MODEL_CALL_TYPE_LABELS = {
  agent_step: "Agent step",
  final_answer: "Final answer",
};

const tokenTurns = [];

function createEmptyBreakdown() {
  return INPUT_BREAKDOWN_ORDER.reduce((acc, key) => {
    acc[key] = 0;
    return acc;
  }, {});
}

function toFiniteNumber(value, fallback = 0) {
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function toNonNegativeIntOrNull(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const normalized = Number(value);
  if (!Number.isFinite(normalized)) {
    return null;
  }
  return Math.max(0, Math.round(normalized));
}

function getProtectedBreakdownKeys(breakdown, targetTotal) {
  const parsedTarget = toNonNegativeIntOrNull(targetTotal);
  if (parsedTarget === null || parsedTarget <= 0) {
    return new Set();
  }

  const presentKeys = BREAKDOWN_FLOOR_KEYS.filter((key) => toFiniteNumber(breakdown[key], 0) > 0);
  return new Set(presentKeys.slice(0, Math.min(presentKeys.length, parsedTarget)));
}

function alignBreakdownToTotal(breakdown, targetTotal) {
  const normalized = createEmptyBreakdown();
  INPUT_BREAKDOWN_ORDER.forEach((key) => {
    normalized[key] = Math.max(0, Math.round(toFiniteNumber(breakdown[key], 0)));
  });

  const parsedTarget = toNonNegativeIntOrNull(targetTotal);
  if (parsedTarget === null) {
    return normalized;
  }

  let currentTotal = sumBreakdown(normalized);
  if (currentTotal < parsedTarget) {
    normalized.unknown_provider_overhead += parsedTarget - currentTotal;
    return normalized;
  }

  let overflow = currentTotal - parsedTarget;
  if (overflow <= 0) {
    return normalized;
  }

  const protectedKeys = getProtectedBreakdownKeys(normalized, parsedTarget);

  BREAKDOWN_REDUCTION_ORDER.forEach((key) => {
    if (overflow <= 0) {
      return;
    }
    const floor = protectedKeys.has(key) ? 1 : 0;
    const available = (normalized[key] || 0) - floor;
    if (available <= 0) {
      return;
    }
    const reduction = Math.min(available, overflow);
    normalized[key] = available - reduction + floor;
    overflow -= reduction;
  });

  if (overflow > 0) {
    INPUT_BREAKDOWN_ORDER
      .slice()
      .sort((left, right) => (normalized[right] || 0) - (normalized[left] || 0))
      .forEach((key) => {
        if (overflow <= 0) {
          return;
        }
        const floor = protectedKeys.has(key) ? 1 : 0;
        const available = (normalized[key] || 0) - floor;
        if (available <= 0) {
          return;
        }
        const reduction = Math.min(available, overflow);
        normalized[key] = available - reduction + floor;
        overflow -= reduction;
      });
  }

  return normalized;
}

function normalizeBreakdown(rawBreakdown, targetTotal = null) {
  const normalized = createEmptyBreakdown();
  const source = rawBreakdown && typeof rawBreakdown === "object" ? rawBreakdown : {};
  const legacyCoreInstructions =
    toFiniteNumber(source.core_instructions, 0) +
    toFiniteNumber(source.system_prompt, 0) +
    toFiniteNumber(source.final_instruction, 0);
  INPUT_BREAKDOWN_ORDER.forEach((key) => {
    if (key === "core_instructions") {
      normalized[key] = Math.max(0, Math.round(toFiniteNumber(legacyCoreInstructions, 0)));
      return;
    }
    normalized[key] = Math.max(0, Math.round(toFiniteNumber(source[key], 0)));
  });
  return alignBreakdownToTotal(normalized, targetTotal);
}

function sumBreakdown(breakdown) {
  return INPUT_BREAKDOWN_ORDER.reduce((sum, key) => sum + toFiniteNumber(breakdown[key], 0), 0);
}

function getModelCallInputTokens(call) {
  if (!call || typeof call !== "object") {
    return 0;
  }

  const promptTokens = toNonNegativeIntOrNull(call.prompt_tokens);
  if (promptTokens !== null) {
    return promptTokens;
  }

  return toNonNegativeIntOrNull(call.estimated_input_tokens) ?? 0;
}

function getMaxInputTokensPerCall(modelCalls, fallbackPromptTokens = 0) {
  const peak = (Array.isArray(modelCalls) ? modelCalls : []).reduce(
    (maxValue, call) => Math.max(maxValue, getModelCallInputTokens(call)),
    0,
  );
  if (peak > 0) {
    return peak;
  }
  return Math.max(0, Math.round(toFiniteNumber(fallbackPromptTokens, 0)));
}

function hasCacheUsageMetrics(entry) {
  return Boolean(
    entry && typeof entry === "object" && (
      entry.prompt_cache_hit_tokens !== null ||
      entry.prompt_cache_miss_tokens !== null
    )
  );
}

function normalizeModelCallPayload(callEntry) {
  const source = callEntry && typeof callEntry === "object" ? callEntry : {};
  const promptTokens = toNonNegativeIntOrNull(source.prompt_tokens);
  const promptCacheHitTokens = toNonNegativeIntOrNull(source.prompt_cache_hit_tokens);
  const promptCacheMissTokens = toNonNegativeIntOrNull(source.prompt_cache_miss_tokens);
  const completionTokens = toNonNegativeIntOrNull(source.completion_tokens);
  const totalTokens = toNonNegativeIntOrNull(source.total_tokens);
  const estimatedTarget = promptTokens ?? toNonNegativeIntOrNull(source.estimated_input_tokens);
  const inputBreakdown = normalizeBreakdown(source.input_breakdown, estimatedTarget);

  return {
    index: toNonNegativeIntOrNull(source.index),
    step: toNonNegativeIntOrNull(source.step),
    call_type: String(source.call_type || "agent_step") || "agent_step",
    is_retry: source.is_retry === true,
    retry_reason: String(source.retry_reason || "").trim(),
    message_count: toNonNegativeIntOrNull(source.message_count),
    tool_schema_tokens: toNonNegativeIntOrNull(source.tool_schema_tokens),
    prompt_tokens: promptTokens,
    prompt_cache_hit_tokens: promptCacheHitTokens,
    prompt_cache_miss_tokens: promptCacheMissTokens,
    completion_tokens: completionTokens,
    total_tokens: totalTokens,
    estimated_input_tokens: estimatedTarget ?? sumBreakdown(inputBreakdown),
    input_breakdown: inputBreakdown,
    missing_provider_usage: source.missing_provider_usage === true,
    cache_metrics_estimated: source.cache_metrics_estimated === true,
  };
}

function normalizePromptBudgetPayload(promptBudget) {
  const source = promptBudget && typeof promptBudget === "object" ? promptBudget : null;
  if (!source) {
    return null;
  }

  return {
    archived_conversation_match_count: Math.max(0, Math.round(toFiniteNumber(source.archived_conversation_match_count, 0))),
    archived_conversation_source_count: Math.max(0, Math.round(toFiniteNumber(source.archived_conversation_source_count, 0))),
    archived_conversation_message_count: Math.max(0, Math.round(toFiniteNumber(source.archived_conversation_message_count, 0))),
    archived_conversation_tokens: Math.max(0, Math.round(toFiniteNumber(source.archived_conversation_tokens, 0))),
  };
}

function normalizeUsagePayload(usage) {
  const source = usage && typeof usage === "object" ? usage : {};
  const promptTokens = Math.max(0, Math.round(toFiniteNumber(source.prompt_tokens, 0)));
  const promptCacheHitTokens = toNonNegativeIntOrNull(source.prompt_cache_hit_tokens);
  const promptCacheMissTokens = toNonNegativeIntOrNull(source.prompt_cache_miss_tokens);
  const estimatedSourceTokens = Math.max(0, Math.round(toFiniteNumber(source.estimated_input_tokens, 0)));
  const inputBreakdown = normalizeBreakdown(source.input_breakdown, promptTokens || estimatedSourceTokens || null);
  const modelCalls = Array.isArray(source.model_calls)
    ? source.model_calls.map(normalizeModelCallPayload)
    : [];
  const modelCallCount = Math.max(
    modelCalls.length,
    Math.round(toFiniteNumber(source.model_call_count, 0)),
  );
  const estimatedInputTokens = promptTokens || sumBreakdown(inputBreakdown) || estimatedSourceTokens;
  const configuredPromptMaxInputTokens = toNonNegativeIntOrNull(source.configured_prompt_max_input_tokens);
  const maxInputTokensPerCall =
    toNonNegativeIntOrNull(source.max_input_tokens_per_call) ??
    getMaxInputTokensPerCall(modelCalls, promptTokens || estimatedInputTokens);
  const preflightPromptBudget = normalizePromptBudgetPayload(source.preflight_prompt_budget);
  const cost = typeof source.cost === "number" && Number.isFinite(source.cost) && source.cost >= 0
    ? Number(source.cost)
    : null;
  const costAvailable = source.cost_available === true;
  const currency = String(source.currency || "").trim() || null;

  return {
    prompt_tokens: promptTokens,
    prompt_cache_hit_tokens: promptCacheHitTokens,
    prompt_cache_miss_tokens: promptCacheMissTokens,
    completion_tokens: Math.max(0, Math.round(toFiniteNumber(source.completion_tokens, 0))),
    total_tokens: Math.max(0, Math.round(toFiniteNumber(source.total_tokens, 0))),
    estimated_input_tokens: estimatedInputTokens,
    input_breakdown: inputBreakdown,
    model_call_count: modelCallCount,
    model_calls: modelCalls,
    max_input_tokens_per_call: maxInputTokensPerCall,
    configured_prompt_max_input_tokens: configuredPromptMaxInputTokens,
    preflight_prompt_budget: preflightPromptBudget,
    provider: String(source.provider || "").trim() || null,
    model: String(source.model || "—") || "—",
    cache_metrics_estimated: source.cache_metrics_estimated === true,
    provider_usage_partial: source.provider_usage_partial === true,
    cost,
    cost_available: costAvailable,
    currency,
  };
}

function formatUsageCost(value, currency = "USD") {
  if (!Number.isFinite(value)) {
    return "—";
  }

  const normalizedCurrency = String(currency || "USD").trim().toUpperCase() || "USD";
  if (normalizedCurrency === "USD") {
    return `$${Number(value).toFixed(6)}`;
  }
  return `${Number(value).toFixed(6)} ${normalizedCurrency}`;
}

function summarizeValueList(values, fallback = "—") {
  const normalizedValues = Array.from(
    new Set(
      (Array.isArray(values) ? values : [])
        .map((value) => String(value || "").trim())
        .filter(Boolean),
    ),
  );
  if (!normalizedValues.length) {
    return fallback;
  }
  if (normalizedValues.length <= 2) {
    return normalizedValues.join(", ");
  }
  return `${normalizedValues.slice(0, 2).join(", ")} +${normalizedValues.length - 2}`;
}


function formatCacheMetricValue(value, estimated = false) {
  const formattedValue = fmt(toFiniteNumber(value, 0));
  return estimated ? `${formattedValue} est.` : formattedValue;
}

function hasPartialProviderUsage(entry) {
  if (!entry || typeof entry !== "object") {
    return false;
  }
  if (entry.provider_usage_partial === true) {
    return true;
  }
  const modelCalls = Array.isArray(entry.model_calls) ? entry.model_calls : [];
  return modelCalls.some((call) => call && typeof call === "object" && call.missing_provider_usage === true);
}

function formatPartialSummaryValue(value, partial = false) {
  const numericValue = Math.max(0, Math.round(toFiniteNumber(value, 0)));
  if (!partial) {
    return fmt(numericValue);
  }
  if (!numericValue) {
    return "Partial / unavailable";
  }
  return `${fmt(numericValue)} partial`;
}

function formatPartialSummaryText(text, partial = false) {
  const normalizedText = String(text || "").trim() || "—";
  if (!partial) {
    return normalizedText;
  }
  if (normalizedText === "—") {
    return "Partial / unavailable";
  }
  return `${normalizedText} partial`;
}

function aggregateBreakdown(turns) {
  const aggregate = createEmptyBreakdown();
  turns.forEach((turn) => {
    INPUT_BREAKDOWN_ORDER.forEach((key) => {
      aggregate[key] += toFiniteNumber(turn.input_breakdown[key], 0);
    });
  });
  return aggregate;
}

function getBreakdownWarningRatio(breakdown, totalTokens) {
  const total = Math.max(0, Math.round(toFiniteNumber(totalTokens, 0)));
  if (!total) {
    return 0;
  }
  return toFiniteNumber(breakdown.unknown_provider_overhead, 0) / total;
}

function renderBreakdownWarning(breakdown, totalTokens) {
  const ratio = getBreakdownWarningRatio(breakdown, totalTokens);
  if (ratio < BREAKDOWN_WARNING_RATIO) {
    return "";
  }

  return (
    `<div class="breakdown-warning">` +
      `Unknown/Provider overhead is ${Math.round(ratio * 1000) / 10}% of the billed prompt total.` +
    `</div>`
  );
}

function renderBreakdownList(containerId, breakdown, options = {}) {
  const container = document.getElementById(containerId);
  if (!container) {
    return;
  }

  const entries = INPUT_BREAKDOWN_ORDER.filter((key) => toFiniteNumber(breakdown[key], 0) > 0);
  if (!entries.length) {
    container.innerHTML = '<div class="breakdown-empty">No input-source estimate available yet.</div>';
    return;
  }

  container.innerHTML = entries
    .map(
      (key) => {
        const helpText = INPUT_BREAKDOWN_HELP_TEXT[key];
        const labelAttrs = helpText ? ` title="${escHtml(helpText)}"` : "";
        return (
        `<div class="breakdown-row">` +
          `<span class="breakdown-label"${labelAttrs}>${escHtml(INPUT_BREAKDOWN_LABELS[key] || key)}</span>` +
          `<span class="breakdown-value">${fmt(breakdown[key])}</span>` +
        `</div>`
        );
      },
    )
    .join("") + renderBreakdownWarning(breakdown, options.totalTokens);
}

function renderBreakdownChips(breakdown, className = "turn-breakdown-chip") {
  const entries = INPUT_BREAKDOWN_ORDER.filter((key) => toFiniteNumber(breakdown[key], 0) > 0);
  return entries
    .map(
      (key) =>
        `<span class="${className}">${escHtml(INPUT_BREAKDOWN_LABELS[key] || key)}: ${fmt(breakdown[key])}</span>`,
    )
    .join("");
}

function renderTurnBreakdownInline(breakdown) {
  const entries = INPUT_BREAKDOWN_ORDER.filter((key) => toFiniteNumber(breakdown[key], 0) > 0);
  if (!entries.length) {
    return "";
  }

  return (
    `<div class="turn-breakdown">` +
      renderBreakdownChips(breakdown) +
    `</div>`
  );
}

function renderUnknownWarningBadge(breakdown, totalTokens) {
  const ratio = getBreakdownWarningRatio(breakdown, totalTokens);
  if (ratio < BREAKDOWN_WARNING_RATIO) {
    return "";
  }
  return `<span class="turn-warning-badge">Unknown ${Math.round(ratio * 1000) / 10}%</span>`;
}

function renderModelCallItem(call) {
  const callTypeLabel = MODEL_CALL_TYPE_LABELS[call.call_type] || "Model call";
  const stepLabel = call.step ? ` · step ${call.step}` : "";
  const retryReason = call.retry_reason ? ` · ${call.retry_reason.replaceAll("_", " ")}` : "";
  const promptStat = call.prompt_tokens !== null
    ? `<span class="turn-call-stat">${fmt(call.prompt_tokens)} prompt</span>`
    : `<span class="turn-call-stat">${fmt(call.estimated_input_tokens)} estimated prompt</span>`;
  const cacheHitLabel = call.cache_metrics_estimated ? "estimated cache hit" : "cache hit";
  const cacheMissLabel = call.cache_metrics_estimated ? "estimated cache miss" : "cache miss";
  const cacheHitStat = call.prompt_cache_hit_tokens !== null
    ? `<span class="turn-call-stat">${formatCacheMetricValue(call.prompt_cache_hit_tokens, call.cache_metrics_estimated)} ${cacheHitLabel}</span>`
    : "";
  const cacheMissStat = call.prompt_cache_miss_tokens !== null
    ? `<span class="turn-call-stat">${formatCacheMetricValue(call.prompt_cache_miss_tokens, call.cache_metrics_estimated)} ${cacheMissLabel}</span>`
    : "";
  const completionStat = call.completion_tokens !== null
    ? `<span class="turn-call-stat">${fmt(call.completion_tokens)} completion</span>`
    : "";
  const messageCountStat = call.message_count !== null
    ? `<span class="turn-call-stat">${fmt(call.message_count)} messages</span>`
    : "";
  const schemaStat = call.tool_schema_tokens !== null && call.tool_schema_tokens > 0
    ? `<span class="turn-call-stat">${fmt(call.tool_schema_tokens)} tool schema</span>`
    : "";
  const missingBadge = call.missing_provider_usage
    ? `<span class="turn-call-badge">Missing provider usage</span>`
    : "";

  return (
    `<div class="turn-call-item">` +
      `<div class="turn-call-title-row">` +
        `<span class="turn-call-title">Call ${fmt(call.index || 0)} · ${escHtml(callTypeLabel)}${escHtml(stepLabel)}${escHtml(retryReason)}</span>` +
        missingBadge +
      `</div>` +
      `<div class="turn-call-meta">` +
        promptStat + cacheHitStat + cacheMissStat + completionStat + messageCountStat + schemaStat +
      `</div>` +
      `<div class="turn-call-breakdown">${renderBreakdownChips(call.input_breakdown, "turn-call-breakdown-chip")}</div>` +
    `</div>`
  );
}

function renderModelCallSection(title, calls) {
  if (!calls.length) {
    return "";
  }
  return (
    `<div class="turn-call-section">` +
      `<div class="turn-call-section-title">${escHtml(title)}</div>` +
      `<div class="turn-call-list">${calls.map(renderModelCallItem).join("")}</div>` +
    `</div>`
  );
}

function renderModelCallDrawer(turn) {
  const calls = Array.isArray(turn.model_calls) ? turn.model_calls : [];
  if (!calls.length) {
    return "";
  }

  const primaryCalls = calls.filter((call) => !call.is_retry);
  const retryCalls = calls.filter((call) => call.is_retry);
  return (
    `<details class="turn-call-drawer">` +
      `<summary class="turn-call-summary">View ${fmt(calls.length)} model calls</summary>` +
      `<div class="turn-call-sections">` +
        renderModelCallSection("Primary calls", primaryCalls) +
        renderModelCallSection("Retry and recovery calls", retryCalls) +
      `</div>` +
    `</details>`
  );
}

function renderTokenStats() {
  const totalUser = tokenTurns.reduce((sum, turn) => sum + turn.prompt_tokens, 0);
  const totalCacheHit = tokenTurns.reduce((sum, turn) => sum + toFiniteNumber(turn.prompt_cache_hit_tokens, 0), 0);
  const totalCacheMiss = tokenTurns.reduce((sum, turn) => sum + toFiniteNumber(turn.prompt_cache_miss_tokens, 0), 0);
  const totalAsst = tokenTurns.reduce((sum, turn) => sum + turn.completion_tokens, 0);
  const grandTotal = tokenTurns.reduce((sum, turn) => sum + turn.total_tokens, 0);
  const turnsWithKnownCost = tokenTurns.filter((turn) => turn?.cost_available === true && Number.isFinite(turn.cost));
  const sessionCostCurrencies = Array.from(
    new Set(turnsWithKnownCost.map((turn) => String(turn.currency || "USD").trim().toUpperCase()).filter(Boolean)),
  );
  const sessionCost = turnsWithKnownCost.reduce((sum, turn) => sum + toFiniteNumber(turn.cost, 0), 0);
  const sessionCostLabel = !turnsWithKnownCost.length
    ? "—"
    : sessionCostCurrencies.length !== 1
      ? "Mixed currencies"
      : tokenTurns.length !== turnsWithKnownCost.length
        ? `${formatUsageCost(sessionCost, sessionCostCurrencies[0])} partial`
        : formatUsageCost(sessionCost, sessionCostCurrencies[0]);
  const sessionBreakdown = aggregateBreakdown(tokenTurns);
  const lastTurn = tokenTurns.length ? tokenTurns[tokenTurns.length - 1] : null;
  const sessionHasCacheMetrics = tokenTurns.some(hasCacheUsageMetrics);
  const sessionHasEstimatedCacheMetrics = tokenTurns.some((turn) => turn?.cache_metrics_estimated === true);
  const sessionHasPartialProviderUsage = tokenTurns.some(hasPartialProviderUsage);
  const lastTurnHasCacheMetrics = hasCacheUsageMetrics(lastTurn);
  const lastTurnHasPartialProviderUsage = hasPartialProviderUsage(lastTurn);
  const sessionProviders = summarizeValueList(tokenTurns.map((turn) => turn.provider));

  document.getElementById("stat-user").textContent = formatPartialSummaryValue(totalUser, sessionHasPartialProviderUsage);
  document.getElementById("stat-cache-hit").textContent = sessionHasCacheMetrics
    ? formatPartialSummaryText(
      formatCacheMetricValue(totalCacheHit, sessionHasEstimatedCacheMetrics),
      sessionHasPartialProviderUsage,
    )
    : formatPartialSummaryText("—", sessionHasPartialProviderUsage);
  document.getElementById("stat-cache-miss").textContent = sessionHasCacheMetrics
    ? formatPartialSummaryText(
      formatCacheMetricValue(totalCacheMiss, sessionHasEstimatedCacheMetrics),
      sessionHasPartialProviderUsage,
    )
    : formatPartialSummaryText("—", sessionHasPartialProviderUsage);
  document.getElementById("stat-asst").textContent = formatPartialSummaryValue(totalAsst, sessionHasPartialProviderUsage);
  document.getElementById("stat-total").textContent = formatPartialSummaryValue(grandTotal, sessionHasPartialProviderUsage);
  document.getElementById("stat-cost").textContent = formatPartialSummaryText(sessionCostLabel, sessionHasPartialProviderUsage);
  document.getElementById("stat-session-providers").textContent = sessionProviders;
  document.getElementById("stat-last-input").textContent = lastTurn
    ? formatPartialSummaryValue(lastTurn.prompt_tokens, lastTurnHasPartialProviderUsage)
    : "—";
  document.getElementById("stat-last-cache-hit").textContent = lastTurnHasCacheMetrics
    ? formatPartialSummaryText(
      formatCacheMetricValue(toFiniteNumber(lastTurn.prompt_cache_hit_tokens, 0), lastTurn?.cache_metrics_estimated === true),
      lastTurnHasPartialProviderUsage,
    )
    : formatPartialSummaryText("—", lastTurnHasPartialProviderUsage);
  document.getElementById("stat-last-cache-miss").textContent = lastTurnHasCacheMetrics
    ? formatPartialSummaryText(
      formatCacheMetricValue(toFiniteNumber(lastTurn.prompt_cache_miss_tokens, 0), lastTurn?.cache_metrics_estimated === true),
      lastTurnHasPartialProviderUsage,
    )
    : formatPartialSummaryText("—", lastTurnHasPartialProviderUsage);
  document.getElementById("stat-last-peak-input").textContent = lastTurn
    ? fmt(lastTurn.max_input_tokens_per_call)
    : "—";
  document.getElementById("stat-last-call-count").textContent = lastTurn
    ? fmt(lastTurn.model_call_count)
    : "—";
  document.getElementById("stat-last-prompt-cap").textContent = lastTurn && lastTurn.configured_prompt_max_input_tokens !== null
    ? fmt(lastTurn.configured_prompt_max_input_tokens)
    : "—";
  document.getElementById("stat-last-output").textContent = lastTurn
    ? formatPartialSummaryValue(lastTurn.completion_tokens, lastTurnHasPartialProviderUsage)
    : "—";
  document.getElementById("stat-last-total").textContent = lastTurn
    ? formatPartialSummaryValue(lastTurn.total_tokens, lastTurnHasPartialProviderUsage)
    : "—";
  document.getElementById("stat-last-cost").textContent = lastTurn?.cost_available === true && Number.isFinite(lastTurn.cost)
    ? formatPartialSummaryText(formatUsageCost(lastTurn.cost, lastTurn.currency || "USD"), lastTurnHasPartialProviderUsage)
    : formatPartialSummaryText("—", lastTurnHasPartialProviderUsage);
  document.getElementById("stat-last-model").textContent = lastTurn ? lastTurn.model : "—";
  document.getElementById("stat-last-provider").textContent = lastTurn?.provider || "—";
  const archivedPromptBudget = lastTurn?.preflight_prompt_budget;
  document.getElementById("stat-last-archived-rag").textContent = archivedPromptBudget && archivedPromptBudget.archived_conversation_match_count > 0
    ? `${fmt(archivedPromptBudget.archived_conversation_match_count)} matches · ${fmt(archivedPromptBudget.archived_conversation_message_count)} hidden msgs · ~${fmt(archivedPromptBudget.archived_conversation_tokens)} tokens`
    : "—";
  document.getElementById("stat-breakdown-session-total").textContent = formatPartialSummaryValue(
    sumBreakdown(sessionBreakdown),
    sessionHasPartialProviderUsage,
  );
  document.getElementById("stat-breakdown-latest-total").textContent = lastTurn
    ? formatPartialSummaryValue(lastTurn.estimated_input_tokens, lastTurnHasPartialProviderUsage)
    : "—";
  tokensBadge.textContent = fmt(grandTotal);

  renderBreakdownList("session-breakdown-list", sessionBreakdown, { totalTokens: totalUser });
  renderBreakdownList("latest-breakdown-list", lastTurn ? lastTurn.input_breakdown : createEmptyBreakdown(), {
    totalTokens: lastTurn ? lastTurn.prompt_tokens : 0,
  });

  const list = document.getElementById("turns-list");
  if (!tokenTurns.length) {
    list.innerHTML = '<div class="breakdown-empty">No completed assistant turns yet.</div>';
    return;
  }

  list.innerHTML = tokenTurns
    .map(
      (turn, index) => {
        const callCount = Math.max(turn.model_call_count || 0, Array.isArray(turn.model_calls) ? turn.model_calls.length : 0);
        const turnHasPartialProviderUsage = hasPartialProviderUsage(turn);
        const peakPromptStat = turn.max_input_tokens_per_call
          ? `<span class="turn-stat">${fmt(turn.max_input_tokens_per_call)} peak call prompt</span>`
          : "";
        const promptCapStat = turn.configured_prompt_max_input_tokens !== null
          ? `<span class="turn-stat">${fmt(turn.configured_prompt_max_input_tokens)} per-call prompt cap</span>`
          : "";
        const cacheHitStat = hasCacheUsageMetrics(turn)
          ? `<span class="turn-stat">${formatCacheMetricValue(toFiniteNumber(turn.prompt_cache_hit_tokens, 0), turn.cache_metrics_estimated === true)} ${turn.cache_metrics_estimated === true ? "estimated cache hit" : "cache hit"}</span>`
          : "";
        const cacheMissStat = hasCacheUsageMetrics(turn)
          ? `<span class="turn-stat">${formatCacheMetricValue(toFiniteNumber(turn.prompt_cache_miss_tokens, 0), turn.cache_metrics_estimated === true)} ${turn.cache_metrics_estimated === true ? "estimated cache miss" : "cache miss"}</span>`
          : "";
        const costStat = turn.cost_available === true && Number.isFinite(turn.cost)
          ? `<span class="turn-stat">${formatPartialSummaryText(formatUsageCost(turn.cost, turn.currency || "USD"), turnHasPartialProviderUsage)} cost</span>`
          : "";
        const partialProviderBadge = turnHasPartialProviderUsage
          ? `<span class="turn-warning-badge">Partial provider usage</span>`
          : "";
        const promptStatLabel = turnHasPartialProviderUsage && turn.prompt_tokens <= 0
          ? "Provider prompt unavailable"
          : `${formatPartialSummaryValue(turn.prompt_tokens, turnHasPartialProviderUsage)} prompt (all calls)`;
        const completionStatLabel = turnHasPartialProviderUsage && turn.completion_tokens <= 0
          ? "Provider completion unavailable"
          : `${formatPartialSummaryValue(turn.completion_tokens, turnHasPartialProviderUsage)} completion`;
        const totalStatLabel = turnHasPartialProviderUsage && turn.total_tokens <= 0
          ? "Provider total unavailable"
          : `${formatPartialSummaryValue(turn.total_tokens, turnHasPartialProviderUsage)} total`;
        const archivedPromptBudget = turn.preflight_prompt_budget;
        const archivedRagStat = archivedPromptBudget && archivedPromptBudget.archived_conversation_match_count > 0
          ? `<span class="turn-stat">${fmt(archivedPromptBudget.archived_conversation_match_count)} archived RAG matches · ${fmt(archivedPromptBudget.archived_conversation_message_count)} hidden msgs</span>`
          : "";
        return (
        `<div class="turn-item">` +
          `<div class="turn-header">` +
            `<span class="turn-label">Assistant turn ${index + 1}</span>` +
            `<div class="turn-header-meta">` +
              (callCount ? `<span class="turn-call-count">${fmt(callCount)} calls</span>` : "") +
              partialProviderBadge +
              renderUnknownWarningBadge(turn.input_breakdown, turn.prompt_tokens) +
              (turn.provider ? `<span class="turn-provider">${escHtml(turn.provider)}</span>` : "") +
              `<span class="turn-model">${escHtml(turn.model || "—")}</span>` +
            `</div>` +
          `</div>` +
          `<div class="turn-details">` +
            `<span class="turn-stat"><span class="stats-dot dot-user"></span>${escHtml(promptStatLabel)}</span>` +
            peakPromptStat +
            promptCapStat +
            cacheHitStat +
            cacheMissStat +
            costStat +
            archivedRagStat +
            `<span class="turn-stat"><span class="stats-dot dot-asst"></span>${escHtml(completionStatLabel)}</span>` +
            `<span class="turn-stat">${escHtml(totalStatLabel)}</span>` +
          `</div>` +
          renderTurnBreakdownInline(turn.input_breakdown) +
          renderModelCallDrawer(turn) +
        `</div>`
        );
      },
    )
    .join("");
}

function normalizeHistoryEntry(entry) {
  const source = entry && typeof entry === "object" ? entry : {};
  const normalizedId = Number(source.id);
  const usage = source.usage && typeof source.usage === "object" ? normalizeUsagePayload(source.usage) : null;
  const role = ["assistant", "user", "tool", "system", "summary"].includes(source.role) ? source.role : "user";
  const toolCalls = Array.isArray(source.tool_calls) ? source.tool_calls : [];
  const toolCallId = typeof source.tool_call_id === "string" && source.tool_call_id.trim()
    ? source.tool_call_id.trim()
    : null;
  return {
    id: Number.isInteger(normalizedId) ? normalizedId : null,
    role,
    content: String(source.content || ""),
    metadata: source.metadata && typeof source.metadata === "object" ? source.metadata : null,
    tool_calls: toolCalls,
    tool_call_id: toolCallId,
    usage,
  };
}

function buildRequestMessagesFromHistory(entries = history) {
  return getVisibleHistoryEntries(entries).map((item) => ({
    role: item.role,
    content: item.content,
    metadata: item.metadata || null,
    tool_calls: Array.isArray(item.tool_calls) ? item.tool_calls : [],
    tool_call_id: item.tool_call_id || null,
  }));
}

function isRenderableHistoryEntry(message) {
  if (!message) {
    return false;
  }

  if (message.role === "assistant" && Array.isArray(message.tool_calls) && message.tool_calls.length > 0) {
    return false;
  }

  const metadata = message.metadata && typeof message.metadata === "object" ? message.metadata : null;
  if (metadata?.is_pruned === true) {
    return false;
  }

  return message.role === "user" || message.role === "assistant" || message.role === "summary";
}

function getVisibleHistoryEntries(entries = history) {
  return entries.filter(isRenderableHistoryEntry);
}

function getConversationSignature(entries = history) {
  return getVisibleHistoryEntries(entries)
    .map((message) => {
      const metadata = message.metadata ? JSON.stringify(message.metadata) : "";
      return `${message.role}:${message.content}:${metadata}`;
    })
    .join("\u0001");
}

function buildAssistantMetadata({
  reasoning = "",
  toolTrace = [],
  tool_trace = null,
  toolResults = [],
  tool_results = null,
  subAgentTraces = [],
  sub_agent_traces = null,
  canvasDocuments = [],
  canvas_documents = null,
  usage = null,
  pendingClarification = null,
  pending_clarification = null,
} = {}) {
  const normalizedToolTrace = Array.isArray(tool_trace) ? tool_trace : toolTrace;
  const normalizedToolResults = Array.isArray(tool_results) ? tool_results : toolResults;
  const normalizedSubAgentTraces = Array.isArray(sub_agent_traces) ? sub_agent_traces : subAgentTraces;
  const normalizedCanvasDocuments = Array.isArray(canvas_documents) ? canvas_documents : canvasDocuments;
  const normalizedPendingClarification = pending_clarification && typeof pending_clarification === "object"
    ? pending_clarification
    : pendingClarification && typeof pendingClarification === "object"
      ? pendingClarification
      : null;

  return reasoning || usage || normalizedToolResults.length || normalizedToolTrace.length || normalizedSubAgentTraces.length || normalizedCanvasDocuments.length || normalizedPendingClarification
    ? {
        ...(reasoning ? { reasoning_content: reasoning } : {}),
        ...(normalizedToolTrace.length ? { tool_trace: normalizedToolTrace } : {}),
        ...(normalizedToolResults.length ? { tool_results: normalizedToolResults } : {}),
        ...(normalizedSubAgentTraces.length ? { sub_agent_traces: normalizedSubAgentTraces } : {}),
        ...(normalizedCanvasDocuments.length ? { canvas_documents: normalizedCanvasDocuments } : {}),
        ...(normalizedPendingClarification ? { pending_clarification: normalizedPendingClarification } : {}),
        ...(usage ? { usage } : {}),
      }
    : null;
}

function getAssistantReasoningStorageKey(conversationId, messageId) {
  const normalizedConversationId = String(conversationId || "").trim();
  const normalizedMessageId = Number(messageId);
  if (!normalizedConversationId || !Number.isInteger(normalizedMessageId) || normalizedMessageId <= 0) {
    return null;
  }
  return `assistant-reasoning:${normalizedConversationId}:${normalizedMessageId}`;
}

function saveAssistantReasoning(conversationId, messageId, reasoningText) {
  const storageKey = getAssistantReasoningStorageKey(conversationId, messageId);
  if (!storageKey) {
    return;
  }

  const text = String(reasoningText || "").trim();
  try {
    if (text) {
      sessionStorage.setItem(storageKey, text);
    } else {
      sessionStorage.removeItem(storageKey);
    }
  } catch (_) {
    // Ignore storage errors.
  }
}

function getAssistantReasoning(conversationId, messageId) {
  const storageKey = getAssistantReasoningStorageKey(conversationId, messageId);
  if (!storageKey) {
    return "";
  }

  try {
    return String(sessionStorage.getItem(storageKey) || "").trim();
  } catch (_) {
    return "";
  }
}

function normalizeClarificationQuestion(question, index) {
  if (!question || typeof question !== "object") {
    return null;
  }

  const inputType = String(question.input_type || "text").trim();
  if (!["text", "single_select", "multi_select"].includes(inputType)) {
    return null;
  }

  const label = String(question.label || "").trim();
  if (!label) {
    return null;
  }

  const normalized = {
    id: String(question.id || `question_${index + 1}`).trim() || `question_${index + 1}`,
    label,
    input_type: inputType,
    required: question.required !== false,
    placeholder: String(question.placeholder || "").trim(),
    allow_free_text: question.allow_free_text === true,
    options: [],
  };

  const dependsOn = normalizeClarificationDependency(question.depends_on);
  if (dependsOn) {
    normalized.depends_on = dependsOn;
  }

  const rawOptions = Array.isArray(question.options) ? question.options : [];
  normalized.options = rawOptions
    .map((option) => {
      if (!option || typeof option !== "object") {
        return null;
      }
      const optionLabel = String(option.label || option.value || "").trim();
      const optionValue = String(option.value || option.label || "").trim();
      const optionDescription = String(option.description || "").trim();
      if (!optionLabel || !optionValue) {
        return null;
      }
      return {
        label: optionLabel,
        value: optionValue,
        ...(optionDescription ? { description: optionDescription } : {}),
      };
    })
    .filter(Boolean);

  return normalized;
}

function normalizeClarificationDependency(dependsOn) {
  if (!dependsOn || typeof dependsOn !== "object") {
    return null;
  }

  const questionId = String(dependsOn.question_id || dependsOn.id || dependsOn.question || "").trim();
  const rawValues = Array.isArray(dependsOn.values) ? [...dependsOn.values] : [];
  if (dependsOn.value !== undefined && dependsOn.value !== null && String(dependsOn.value).trim()) {
    rawValues.unshift(dependsOn.value);
  }

  const values = rawValues
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .filter((value, idx, array) => array.findIndex((entry) => entry === value) === idx)
    .slice(0, 10);

  if (!questionId || !values.length) {
    return null;
  }

  return {
    question_id: questionId,
    values,
  };
}

function getPendingClarification(metadata) {
  if (!metadata || typeof metadata !== "object") {
    return null;
  }

  const payload = metadata.pending_clarification;
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const questions = Array.isArray(payload.questions)
    ? payload.questions.map(normalizeClarificationQuestion).filter(Boolean)
    : [];
  if (!questions.length) {
    return null;
  }

  return {
    intro: String(payload.intro || "").trim(),
    submit_label: String(payload.submit_label || "").trim() || "Send answers",
    questions,
  };
}

function findLatestPendingClarificationMessageId(entries = history) {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const message = entries[index];
    if (!message || message.role !== "assistant") {
      continue;
    }
    if (!getPendingClarification(message.metadata)) {
      continue;
    }
    const messageId = Number(message.id);
    if (Number.isInteger(messageId) && messageId > 0) {
      return messageId;
    }
  }
  return null;
}

function getClarificationLiveValue(form, question, index) {
  const fieldName = `clarify_${index}`;
  if (question.input_type === "text") {
    return String(form.elements[fieldName]?.value || "").trim();
  }
  if (question.input_type === "single_select") {
    return String(form.querySelector(`input[name="${fieldName}"]:checked`)?.value || "").trim();
  }
  return Array.from(form.querySelectorAll(`input[name="${fieldName}"]:checked`))
    .map((element) => String(element.value || "").trim())
    .filter(Boolean);
}

function matchesClarificationDependency(dependsOn, answerValue) {
  if (!dependsOn || typeof dependsOn !== "object") {
    return true;
  }

  const allowedValues = Array.isArray(dependsOn.values)
    ? dependsOn.values.map((value) => String(value || "").trim()).filter(Boolean)
    : [];
  if (!allowedValues.length) {
    return true;
  }

  const actualValues = Array.isArray(answerValue)
    ? answerValue.map((value) => String(value || "").trim()).filter(Boolean)
    : [String(answerValue || "").trim()].filter(Boolean);
  return actualValues.some((value) => allowedValues.includes(value));
}

function setClarificationFieldDisabled(field, disabled) {
  if (!(field instanceof HTMLElement)) {
    return;
  }
  field.querySelectorAll("input, textarea").forEach((element) => {
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      element.disabled = disabled;
    }
  });
}

function updateClarificationFieldVisibility(form, clarification) {
  const answersByQuestionId = {};
  clarification.questions.forEach((question, index) => {
    answersByQuestionId[question.id] = getClarificationLiveValue(form, question, index);
  });

  clarification.questions.forEach((question) => {
    const field = form.querySelector(`.clarification-field[data-question-id="${CSS.escape(question.id)}"]`);
    if (!(field instanceof HTMLElement)) {
      return;
    }
    const visible = !question.depends_on
      || matchesClarificationDependency(question.depends_on, answersByQuestionId[question.depends_on.question_id]);
    field.hidden = !visible;
    setClarificationFieldDisabled(field, !visible);
  });
}

function getClarificationDraftStorageKey(messageId) {
  const normalizedConvId = Number.isInteger(Number(currentConvId)) ? String(Number(currentConvId)) : "conversation";
  const normalizedMessageId = Number.isInteger(Number(messageId)) ? String(Number(messageId)) : "message";
  return `${CLARIFICATION_DRAFT_STORAGE_PREFIX}.${normalizedConvId}.${normalizedMessageId}`;
}

function loadClarificationDraft(messageId) {
  const key = getClarificationDraftStorageKey(messageId);
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_) {
    return null;
  }
}

function saveClarificationDraft(messageId, draft) {
  const key = getClarificationDraftStorageKey(messageId);
  try {
    if (!draft || typeof draft !== "object") {
      localStorage.removeItem(key);
      return;
    }
    localStorage.setItem(key, JSON.stringify(draft));
  } catch (_) {
    // Ignore storage failures.
  }
}

function collectClarificationDraft(form, clarification) {
  const draft = {};

  clarification.questions.forEach((question, index) => {
    const fieldName = `clarify_${index}`;
    const freeTextName = `${fieldName}_free`;

    if (question.input_type === "text") {
      const input = form.elements[fieldName];
      draft[question.id] = { value: String(input?.value || "") };
      return;
    }

    if (question.input_type === "single_select") {
      const selected = form.querySelector(`input[name="${fieldName}"]:checked`);
      const freeTextInput = form.elements[freeTextName];
      draft[question.id] = {
        value: selected ? String(selected.value || "") : "",
        free_text: String(freeTextInput?.value || ""),
      };
      return;
    }

    const selected = Array.from(form.querySelectorAll(`input[name="${fieldName}"]:checked`));
    const freeTextInput = form.elements[freeTextName];
    draft[question.id] = {
      value: selected.map((element) => String(element.value || "").trim()).filter(Boolean),
      free_text: String(freeTextInput?.value || ""),
    };
  });

  return draft;
}

function applyClarificationDraft(form, clarification, draft) {
  if (!draft || typeof draft !== "object") {
    return;
  }

  clarification.questions.forEach((question, index) => {
    const entry = draft[question.id];
    if (!entry || typeof entry !== "object") {
      return;
    }

    const fieldName = `clarify_${index}`;
    const freeTextName = `${fieldName}_free`;

    if (question.input_type === "text") {
      const input = form.elements[fieldName];
      if (input instanceof HTMLTextAreaElement) {
        input.value = String(entry.value || "");
        autoResize(input);
      }
    } else if (question.input_type === "single_select") {
      const selectedValue = String(entry.value || "").trim();
      if (selectedValue) {
        const selected = form.querySelector(`input[name="${fieldName}"][value="${CSS.escape(selectedValue)}"]`);
        if (selected instanceof HTMLInputElement) {
          selected.checked = true;
        }
      }
    } else if (Array.isArray(entry.value)) {
      entry.value.forEach((selectedValue) => {
        const normalizedValue = String(selectedValue || "").trim();
        if (!normalizedValue) {
          return;
        }
        const selected = form.querySelector(`input[name="${fieldName}"][value="${CSS.escape(normalizedValue)}"]`);
        if (selected instanceof HTMLInputElement) {
          selected.checked = true;
        }
      });
    }

    const freeTextInput = form.elements[freeTextName];
    if (freeTextInput instanceof HTMLInputElement) {
      freeTextInput.value = String(entry.free_text || "");
    }
  });
}

function formatClarificationResponse(clarification, answers) {
  const lines = [];
  clarification.questions.forEach((question) => {
    const answer = answers[question.id];
    if (!answer || !String(answer.display || "").trim()) {
      return;
    }
    lines.push(`- ${question.label} → ${String(answer.display).trim()}`);
  });
  return lines.join("\n");
}

function collectClarificationAnswers(form, clarification) {
  const answers = {};

  for (let index = 0; index < clarification.questions.length; index += 1) {
    const question = clarification.questions[index];
    const field = form.querySelector(`.clarification-field[data-question-id="${CSS.escape(question.id)}"]`);
    if (field instanceof HTMLElement && field.hidden) {
      continue;
    }
    const fieldName = `clarify_${index}`;
    const freeTextName = `${fieldName}_free`;
    let display = "";
    let value = null;

    if (question.input_type === "text") {
      const input = form.elements[fieldName];
      display = String(input?.value || "").trim();
      value = display;
    } else if (question.input_type === "single_select") {
      const selected = form.querySelector(`input[name="${fieldName}"]:checked`);
      value = selected ? String(selected.value || "").trim() : "";
      const selectedOption = question.options.find((option) => option.value === value);
      display = selectedOption ? selectedOption.label : value;
    } else if (question.input_type === "multi_select") {
      const selected = Array.from(form.querySelectorAll(`input[name="${fieldName}"]:checked`));
      value = selected.map((element) => String(element.value || "").trim()).filter(Boolean);
      display = value
        .map((entry) => question.options.find((option) => option.value === entry)?.label || entry)
        .filter(Boolean)
        .join(", ");
    }

    const freeTextInput = form.elements[freeTextName];
    const freeText = String(freeTextInput?.value || "").trim();
    if (freeText) {
      display = display ? `${display} (${freeText})` : freeText;
      if (Array.isArray(value)) {
        value = [...value, freeText];
      } else if (value) {
        value = { selection: value, free_text: freeText };
      } else {
        value = freeText;
      }
    }

    if (question.required && !String(display || "").trim()) {
      return { error: `${question.label} is required.` };
    }

    answers[question.id] = { value, display };
  }

  return {
    answers,
    text: formatClarificationResponse(clarification, answers),
  };
}

function shouldGenerateConversationTitle() {
  const visibleEntries = getVisibleHistoryEntries();
  return Boolean(
    currentConvId &&
    visibleEntries.length === 2 &&
    visibleEntries[0]?.role === "user" &&
    visibleEntries[1]?.role === "assistant" &&
    !getPendingClarification(visibleEntries[1]?.metadata),
  );
}

async function streamNdjsonResponse(response, onEvent) {
  if (!response.body) {
    throw new Error("The server returned an empty response stream.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const processLine = (line) => {
    if (!line.trim()) {
      return;
    }
    try {
      onEvent(JSON.parse(line));
    } catch (_) {
      // Ignore malformed partial chunks.
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    lines.forEach(processLine);
  }

  buffer += decoder.decode();
  processLine(buffer);
}

function getHistoryMessageIndex(messageId) {
  const normalizedId = Number(messageId);
  if (!Number.isInteger(normalizedId) || normalizedId <= 0) {
    return -1;
  }
  return history.findIndex((item) => Number(item.id) === normalizedId);
}

function isPersistedMessageId(messageId) {
  const normalizedId = Number(messageId);
  return Number.isInteger(normalizedId) && normalizedId > 0;
}

function getHistoryMessage(messageId) {
  const index = getHistoryMessageIndex(messageId);
  return index >= 0 ? history[index] : null;
}

function isPrunableHistoryMessage(message) {
  if (!message || (message.role !== "user" && message.role !== "assistant")) {
    return false;
  }
  if (message.role === "assistant" && Array.isArray(message.tool_calls) && message.tool_calls.length > 0) {
    return false;
  }
  const metadata = message.metadata && typeof message.metadata === "object" ? message.metadata : null;
  if (metadata?.is_summary === true || metadata?.is_pruned === true) {
    return false;
  }
  return String(message.content || "").trim().length > 0;
}

function isEditableHistoryMessage(message) {
  if (!message || !isPersistedMessageId(message.id)) {
    return false;
  }

  if (message.role !== "user" && message.role !== "assistant") {
    return false;
  }

  if (message.role === "assistant" && Array.isArray(message.tool_calls) && message.tool_calls.length > 0) {
    return false;
  }

  const metadata = message.metadata && typeof message.metadata === "object" ? message.metadata : null;
  return metadata?.is_summary !== true;
}

function isInlineEditingTarget(messageId) {
  return isPersistedMessageId(messageId)
    && isPersistedMessageId(inlineEditingMessageId)
    && Number(messageId) === Number(inlineEditingMessageId);
}

function clearInlineEditingTarget({ preserveDraft = false } = {}) {
  inlineEditingMessageId = null;
  if (!preserveDraft) {
    inlineEditingDraft = "";
  }
  savingEditedMessageId = null;
}

function autoResizeInlineEditor(textarea) {
  if (!(textarea instanceof HTMLTextAreaElement)) {
    return;
  }

  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 360)}px`;
}

function focusInlineEditor(messageId) {
  if (!isPersistedMessageId(messageId)) {
    return;
  }

  window.requestAnimationFrame(() => {
    const editor = messagesEl.querySelector(
      `.msg-group[data-message-id="${String(messageId)}"] .message-inline-editor__input`
    );
    if (!(editor instanceof HTMLTextAreaElement)) {
      return;
    }

    autoResizeInlineEditor(editor);
    editor.focus();
    editor.setSelectionRange(editor.value.length, editor.value.length);
  });
}

function beginInlineEditingMessage(messageId) {
  if (isStreaming || isFixing) {
    return;
  }

  const message = getHistoryMessage(messageId);
  if (!isEditableHistoryMessage(message)) {
    return;
  }

  clearEditTarget();
  inlineEditingMessageId = Number(message.id);
  inlineEditingDraft = String(message.content || "");
  savingEditedMessageId = null;
  renderConversationHistory({ preserveScroll: true });
  focusInlineEditor(message.id);
}

function cancelInlineEditingMessage({ focusAction = false } = {}) {
  const previousMessageId = inlineEditingMessageId;
  clearInlineEditingTarget();
  renderConversationHistory({ preserveScroll: true });

  if (!focusAction || !isPersistedMessageId(previousMessageId)) {
    return;
  }

  window.requestAnimationFrame(() => {
    const editButton = messagesEl.querySelector(
      `.msg-group[data-message-id="${String(previousMessageId)}"] .msg-action-btn[data-action="edit-message"]`
    );
    if (editButton instanceof HTMLButtonElement) {
      editButton.focus();
    }
  });
}

async function saveEditedHistoryMessage(messageId, nextContent, options = {}) {
  if (isStreaming || isFixing) {
    return;
  }

  const message = getHistoryMessage(messageId);
  if (!isEditableHistoryMessage(message)) {
    showError("Mesaj artık düzenlenemiyor.");
    clearInlineEditingTarget();
    renderConversationHistory({ preserveScroll: true });
    return;
  }

  const normalizedContent = String(nextContent ?? "").replace(/\r\n/g, "\n");
  const attachments = getMessageAttachments(message.metadata);
  if (!normalizedContent.trim() && (message.role !== "user" || attachments.length === 0)) {
    showToast(
      message.role === "assistant" ? "Assistant message cannot be empty." : "Message cannot be empty.",
      "warning",
    );
    focusInlineEditor(messageId);
    return;
  }

  const shouldSendAfterSave = Boolean(options.sendAfterSave && message.role === "user");
  const contentChanged = normalizedContent !== String(message.content || "");

  if (!contentChanged && !shouldSendAfterSave) {
    cancelInlineEditingMessage();
    return;
  }

  savingEditedMessageId = Number(messageId);
  renderConversationHistory({ preserveScroll: true });

  try {
    if (contentChanged) {
      const response = await fetch(`/api/messages/${messageId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: currentConvId,
          content: normalizedContent,
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.error || "Message could not be updated.");
      }

      const updatedMessage = data?.message ? normalizeHistoryEntry(data.message) : null;
      const index = getHistoryMessageIndex(messageId);
      if (updatedMessage && index >= 0) {
        history[index] = updatedMessage;
      }
    }

    if (shouldSendAfterSave) {
      editingMessageId = Number(messageId);
      clearInlineEditingTarget();
      renderConversationHistory({ preserveScroll: true });
      refreshEditBanner();
      await sendMessage({ forcedText: normalizedContent });
      return;
    }

    clearInlineEditingTarget();
    renderConversationHistory({ preserveScroll: true });
    showToast("Message updated.", "success");
  } catch (error) {
    savingEditedMessageId = null;
    renderConversationHistory({ preserveScroll: true });
    showError(error.message || "Message could not be updated.");
    focusInlineEditor(messageId);
  }
}

function clearEditTarget() {
  editingMessageId = null;
  editBanner.hidden = true;
  editBannerText.textContent = "";
}

function refreshEditBanner() {
  const message = getHistoryMessage(editingMessageId);
  if (!message || message.role !== "user") {
    clearEditTarget();
    return;
  }

  editBanner.hidden = false;
  editBannerText.textContent = "Editing an earlier message. Sending now will replace that turn and continue from there.";
}

function beginEditingMessage(messageId) {
  if (isStreaming || isFixing) {
    return;
  }

  const message = getHistoryMessage(messageId);
  if (!message || message.role !== "user") {
    return;
  }

  clearInlineEditingTarget();
  editingMessageId = Number(message.id);
  inputEl.value = message.content;
  autoResize(inputEl);
  clearSelectedImage();
  refreshEditBanner();
  renderConversationHistory();
  inputEl.focus();
  inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length);
}

function createMessageActions(message, options = {}) {
  if (!message) {
    return null;
  }

  const actions = document.createElement("div");
  actions.className = "msg-actions msg-actions--footer";

  const messageId = message.id;
    const isDeletingThisMessage = messageId !== null && deletingMessageId !== null && Number(deletingMessageId) === Number(messageId);
    const isDeleteConfirmationOpen = messageId !== null && pendingDeleteMessageId !== null && Number(pendingDeleteMessageId) === Number(messageId);
  if (message.role === "user" || message.role === "assistant") {
    if (options.editable && isEditableHistoryMessage(message)) {
      const editBtn = createMessageActionButton({
        label: "Edit",
        title: "Edit message",
        icon: MESSAGE_ACTION_ICONS.edit,
        showLabel: true,
        onClick: () => beginInlineEditingMessage(messageId),
        disabled: !isPersistedMessageId(messageId) || Number(savingEditedMessageId) === Number(messageId) || isDeletingThisMessage,
      });
      actions.appendChild(editBtn);
    }

    const copyButton = createMessageActionButton({
      label: "Copy",
      title: message.role === "assistant" ? "Copy as Markdown" : "Copy message",
      icon: MESSAGE_ACTION_ICONS.copy,
      showLabel: true,
      onClick: () => {
        void (message.role === "assistant" ? copyAssistantMessageMarkdown(message) : copyUserMessageContent(message));
      },
      disabled: !String(message.content || "").trim() || isDeletingThisMessage,
    });
    actions.appendChild(copyButton);

    const deleteButton = createMessageActionButton({
      label: isDeleteConfirmationOpen ? "Cancel delete" : "Delete",
      title: isDeleteConfirmationOpen ? "Cancel delete" : "Delete message",
      icon: MESSAGE_ACTION_ICONS.delete,
      showLabel: true,
      onClick: () => {
        if (isDeleteConfirmationOpen) {
          clearPendingDeleteMessage({ preserveScroll: true });
          return;
        }
        openDeleteMessageConfirm(messageId);
      },
      disabled: !isPersistedMessageId(messageId) || isDeletingThisMessage || isStreaming || isFixing,
    });
    deleteButton.classList.add("msg-action-btn--danger");
    actions.appendChild(deleteButton);

    if (message.role === "assistant") {
      const regenerateButton = createMessageActionButton({
        label: "Regenerate",
        title: "Regenerate reply",
        icon: MESSAGE_ACTION_ICONS.regenerate,
        onClick: () => {
          void regenerateAssistantMessage(message.id);
        },
        disabled: !getPreviousUserMessage(message.id) || isDeletingThisMessage,
      });
      actions.appendChild(regenerateButton);
    }

    if (isDeleteConfirmationOpen) {
      const confirmBox = document.createElement("div");
      confirmBox.className = "msg-delete-confirm";

      const confirmText = document.createElement("span");
      confirmText.className = "msg-delete-confirm__text";
      confirmText.textContent = "Delete this message?";
      confirmBox.appendChild(confirmText);

      const confirmBtn = document.createElement("button");
      confirmBtn.type = "button";
      confirmBtn.className = "msg-action-btn msg-delete-confirm__btn msg-delete-confirm__btn--confirm";
      confirmBtn.textContent = isDeletingThisMessage ? "Deleting..." : "Delete";
      confirmBtn.disabled = isDeletingThisMessage;
      confirmBtn.addEventListener("click", () => {
        void deleteConversationMessage(messageId);
      });
      confirmBox.appendChild(confirmBtn);

      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "msg-action-btn msg-delete-confirm__btn";
      cancelBtn.textContent = "Cancel";
      cancelBtn.addEventListener("click", () => {
        if (isDeletingThisMessage && activeDeleteMessageAbortController) {
          activeDeleteMessageAbortController.abort();
        }
        clearPendingDeleteMessage({ preserveScroll: true });
      });
      confirmBox.appendChild(cancelBtn);

      actions.appendChild(confirmBox);
    }
  }

  if (!actions.childElementCount) {
    return null;
  }
  return actions;
}

function createMessageActionButton({ label, title, icon, onClick, disabled = false, showLabel = false }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "msg-action-btn msg-action-btn--icon";
  if (showLabel) {
    button.classList.add("msg-action-btn--with-label");
  }
  button.title = title;
  button.setAttribute("aria-label", label);
  button.innerHTML = showLabel
    ? `${icon}<span class="msg-action-btn__label">${escHtml(label)}</span>`
    : `${icon}<span class="sr-only">${escHtml(label)}</span>`;
  button.disabled = disabled;
  if (onClick) {
    button.addEventListener("click", onClick);
  }
  return button;
}

const MESSAGE_ACTION_ICONS = {
  copy: `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
      <rect x="9" y="9" width="10" height="10" rx="2" stroke="currentColor" stroke-width="1.8" />
      <path d="M7 15H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  `,
  edit: `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
      <path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0 0-3l-1-1a2.1 2.1 0 0 0-3 0L4 16v4Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      <path d="m13 7 4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  `,
  regenerate: `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
      <path d="M3 12a9 9 0 0 1 15.3-6.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      <path d="M17 4h4v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      <path d="M21 12a9 9 0 0 1-15.3 6.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      <path d="M7 20H3v-4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  `,
  delete: `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
      <path d="M4 7h16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      <path d="M10 11v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      <path d="M14 11v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      <path d="M6 7l1 12a2 2 0 0 0 2 1.8h6a2 2 0 0 0 2-1.8L18 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      <path d="M9 7V5.8A1.8 1.8 0 0 1 10.8 4h2.4A1.8 1.8 0 0 1 15 5.8V7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  `,
};

function clearPendingDeleteMessage(options = {}) {
  const preserveScroll = options.preserveScroll !== false;
  if (activeDeleteMessageAbortController) {
    activeDeleteMessageAbortController.abort();
    activeDeleteMessageAbortController = null;
  }
  pendingDeleteMessageId = null;
  deletingMessageId = null;
  if (options.render !== false) {
    renderConversationHistory({ preserveScroll });
  }
}

function openDeleteMessageConfirm(messageId) {
  if (isStreaming || isFixing) {
    return;
  }
  pendingDeleteMessageId = Number(messageId);
  renderConversationHistory({ preserveScroll: true });
}

async function deleteConversationMessage(messageId) {
  const normalizedMessageId = Number(messageId);
  if (!isPersistedMessageId(normalizedMessageId) || !currentConvId) {
    showToast("Message could not be deleted.", "error");
    return;
  }

  deletingMessageId = normalizedMessageId;
  activeDeleteMessageAbortController = new AbortController();
  renderConversationHistory({ preserveScroll: true });

  try {
    const response = await fetch(`/api/messages/${normalizedMessageId}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      signal: activeDeleteMessageAbortController.signal,
      body: JSON.stringify({ conversation_id: currentConvId }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Message could not be deleted.");
    }

    if (Number(editingMessageId) === normalizedMessageId) {
      clearEditTarget();
    }
    if (Number(inlineEditingMessageId) === normalizedMessageId) {
      cancelInlineEditingMessage({ focusAction: false });
    }

    history = Array.isArray(payload.messages)
      ? payload.messages.map(normalizeHistoryEntry)
      : history.filter((item) => Number(item.id) !== normalizedMessageId);
    pendingDeleteMessageId = null;
    deletingMessageId = null;
    activeDeleteMessageAbortController = null;
    rebuildTokenStatsFromHistory();
    renderConversationHistory({ preserveScroll: true });
    renderCanvasPanel();
    refreshEditBanner();
    showToast("Message deleted.", "success");
  } catch (error) {
    deletingMessageId = null;
    pendingDeleteMessageId = null;
    activeDeleteMessageAbortController = null;
    renderConversationHistory({ preserveScroll: true });
    if (error.name !== "AbortError") {
      showError(error.message || "Message could not be deleted.");
    }
  }
}

function fallbackCopyText(text) {
  const normalizedText = String(text || "");
  if (!normalizedText) {
    return false;
  }

  const textarea = document.createElement("textarea");
  textarea.value = normalizedText;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "-9999px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);

  let copied = false;
  try {
    textarea.focus({ preventScroll: true });
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    copied = Boolean(document.execCommand && document.execCommand("copy"));
  } catch (_) {
    copied = false;
  } finally {
    textarea.remove();
  }

  return copied;
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      // Fall through to the legacy copy fallback.
    }
  }

  return fallbackCopyText(text);
}

async function copyMessageContent(content, messages) {
  const text = String(content || "");
  if (!text.trim()) {
    showToast(messages.empty, "warning");
    return false;
  }

  try {
    const copied = await copyTextToClipboard(text);
    if (!copied) {
      showToast(messages.unavailable, "warning");
      return false;
    }
    showToast(messages.success, "success");
    return true;
  } catch (_) {
    showToast(messages.error, "error");
    return false;
  }
}

function getCodeBlockCopyText(button) {
  const shell = button.closest(".code-block-shell");
  if (!(shell instanceof HTMLElement)) {
    return "";
  }

  const lineNodes = shell.querySelectorAll(".canvas-code-line__content");
  if (lineNodes.length) {
    return Array.from(lineNodes).map((node) => node.textContent || "").join("\n");
  }

  return shell.querySelector("code")?.textContent || "";
}

function setCodeCopyButtonLabel(button, label) {
  if (!(button instanceof HTMLButtonElement)) {
    return;
  }
  button.textContent = label;
}

async function copyCodeBlock(button) {
  if (!(button instanceof HTMLButtonElement)) {
    return;
  }

  const codeText = getCodeBlockCopyText(button);
  if (!codeText.trim()) {
    showToast("No code to copy.", "warning");
    return;
  }

  const originalLabel = button.textContent || "Copy code";
  const copied = await copyTextToClipboard(codeText);
  if (!copied) {
    setCodeCopyButtonLabel(button, "Copy failed");
    showToast("Clipboard is not available.", "warning");
    window.setTimeout(() => setCodeCopyButtonLabel(button, originalLabel), 1800);
    return;
  }

  setCodeCopyButtonLabel(button, "Copied");
  showToast("Code copied to clipboard.", "success");
  window.setTimeout(() => setCodeCopyButtonLabel(button, originalLabel), 1800);
}

function getPreviousUserMessage(messageId) {
  const index = getHistoryMessageIndex(messageId);
  if (index < 0) {
    return null;
  }

  for (let candidateIndex = index - 1; candidateIndex >= 0; candidateIndex -= 1) {
    const candidate = history[candidateIndex];
    if (candidate && candidate.role === "user") {
      return candidate;
    }
  }

  return null;
}

async function copyAssistantMessageMarkdown(message) {
  await copyMessageContent(message?.content, {
    empty: "No Markdown content to copy.",
    unavailable: "Clipboard is not available.",
    success: "Markdown copied to clipboard.",
    error: "Copy failed.",
  });
}

async function copyUserMessageContent(message) {
  await copyMessageContent(message?.content, {
    empty: "No message text to copy.",
    unavailable: "Clipboard is not available.",
    success: "Message copied to clipboard.",
    error: "Copy failed.",
  });
}

async function regenerateAssistantMessage(messageId) {
  if (isStreaming || isFixing) {
    return;
  }

  const assistantMessage = getHistoryMessage(messageId);
  if (!assistantMessage || assistantMessage.role !== "assistant") {
    return;
  }

  const previousUserMessage = getPreviousUserMessage(messageId);
  if (!previousUserMessage) {
    showToast("No earlier user message is available to regenerate.", "warning");
    return;
  }

  editingMessageId = Number(previousUserMessage.id);
  clearInlineEditingTarget();
  await sendMessage({ forcedText: String(previousUserMessage.content || "") });
}

function createAssistantMessageActions(message) {
  if (!message || message.role !== "assistant") {
    return null;
  }

  return createMessageActions(message, { editable: true });
}

function createInlineMessageEditor(message) {
  const form = document.createElement("form");
  form.className = "message-inline-editor";
  form.dataset.messageId = String(message.id || "");

  const textarea = document.createElement("textarea");
  textarea.className = "message-inline-editor__input";
  textarea.value = isInlineEditingTarget(message.id) ? inlineEditingDraft : String(message.content || "");
  textarea.placeholder = message.role === "assistant"
    ? "Edit the assistant reply"
    : "Edit the message";
  textarea.rows = Math.max(3, Math.min(16, textarea.value.split(/\n/).length + 1));
  textarea.disabled = Number(savingEditedMessageId) === Number(message.id);
  textarea.addEventListener("input", () => {
    inlineEditingDraft = textarea.value;
    autoResizeInlineEditor(textarea);
  });
  textarea.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      form.requestSubmit();
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      cancelInlineEditingMessage({ focusAction: true });
    }
  });
  form.appendChild(textarea);

  const hint = document.createElement("div");
  hint.className = "message-inline-editor__hint";
  hint.textContent = message.role === "assistant"
    ? "Markdown is supported. Use Ctrl/Cmd+Enter to save."
    : "Use Ctrl/Cmd+Enter to save.";
  form.appendChild(hint);

  const actions = document.createElement("div");
  actions.className = "message-inline-editor__actions";

  const saveBtn = document.createElement("button");
  saveBtn.type = "submit";
  saveBtn.className = "msg-action-btn";
  saveBtn.textContent = Number(savingEditedMessageId) === Number(message.id) ? "Saving..." : "Save";
  saveBtn.disabled = Number(savingEditedMessageId) === Number(message.id);
  actions.appendChild(saveBtn);

  if (message.role === "user") {
    const saveAndSendBtn = document.createElement("button");
    saveAndSendBtn.type = "button";
    saveAndSendBtn.className = "msg-action-btn";
    saveAndSendBtn.textContent = "Save and Send";
    saveAndSendBtn.disabled = Number(savingEditedMessageId) === Number(message.id);
    saveAndSendBtn.addEventListener("click", () => {
      void saveEditedHistoryMessage(message.id, textarea.value, { sendAfterSave: true });
    });
    actions.appendChild(saveAndSendBtn);
  }

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "msg-action-btn";
  cancelBtn.textContent = "Cancel";
  cancelBtn.disabled = Number(savingEditedMessageId) === Number(message.id);
  cancelBtn.addEventListener("click", () => cancelInlineEditingMessage({ focusAction: true }));
  actions.appendChild(cancelBtn);

  form.appendChild(actions);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveEditedHistoryMessage(message.id, textarea.value);
  });

  return form;
}

async function pruneMessage(messageId) {
  if (isStreaming || isFixing) {
    return;
  }

  const message = getHistoryMessage(messageId);
  if (!isPrunableHistoryMessage(message)) {
    return;
  }

  try {
    const response = await fetch(`/api/messages/${messageId}/prune`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: currentConvId }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(data?.error || "Message could not be pruned.");
    }
    if (!data?.message) {
      throw new Error("Pruned message payload is missing.");
    }

    const index = getHistoryMessageIndex(messageId);
    if (index >= 0) {
      history[index] = normalizeHistoryEntry(data.message);
      renderConversationHistory();
    } else {
      await refreshConversationFromServer();
    }
    showToast("Message pruned.", "success");
  } catch (error) {
    showError(error.message || "Message could not be pruned.");
  }
}

function renderConversationHistory(options = {}) {
  const activeInlineMessage = getHistoryMessage(inlineEditingMessageId);
  if (inlineEditingMessageId !== null && !isEditableHistoryMessage(activeInlineMessage)) {
    clearInlineEditingTarget();
  }

  const preserveScroll = options && options.preserveScroll === true;
  const previousDistanceFromBottom = preserveScroll
    ? messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight
    : 0;
  const fragment = document.createDocumentFragment();
  fragment.appendChild(emptyState);

  if (!history.length) {
    emptyState.style.display = "";
    messagesEl.replaceChildren(fragment);
    scrollToBottom();
    renderSummaryInspector();
    return;
  }

  emptyState.style.display = "none";
  const visibleEntries = getVisibleHistoryEntries();
  visibleEntries.forEach((message, index) => {
    if (!isRenderableHistoryEntry(message)) {
      return;
    }
    fragment.appendChild(createMessageGroup(message.role, message.content, message.metadata || null, {
      messageId: message.id,
      editable: message.role === "user" || message.role === "assistant",
      isEditingTarget: isPersistedMessageId(message.id)
        && isPersistedMessageId(editingMessageId)
        && Number(message.id) === Number(editingMessageId),
      isInlineEditingTarget: isInlineEditingTarget(message.id),
      isLatestVisible: index === visibleEntries.length - 1,
      toolCalls: message.tool_calls,
    }));
  });
  messagesEl.replaceChildren(fragment);
  if (preserveScroll) {
    if (previousDistanceFromBottom <= 100) {
      scrollToBottom();
    } else {
      messagesEl.scrollTop = Math.max(0, messagesEl.scrollHeight - messagesEl.clientHeight - previousDistanceFromBottom);
    }
  } else {
    scrollToBottom();
  }
  renderSummaryInspector();
}

async function refreshConversationFromServer() {
  if (!currentConvId) {
    return false;
  }

  const response = await fetch(`/api/conversations/${currentConvId}`);
  if (!response.ok) {
    return false;
  }

  const data = await response.json().catch(() => null);
  if (!data || Number(data.conversation?.id) !== Number(currentConvId)) {
    return false;
  }

  const serverHistory = Array.isArray(data.messages) ? data.messages.map(normalizeHistoryEntry) : [];
  const serverSignature = getConversationSignature(serverHistory);
  const serverMemorySignature = getConversationMemorySignature(data.memory || []);
  const messagesChanged = serverSignature !== lastConversationSignature;
  const memoryChanged = serverMemorySignature !== lastConversationMemorySignature;

  if (!messagesChanged && !memoryChanged) {
    return false;
  }

  if (messagesChanged) {
    history = serverHistory;
    currentConvTitle = String(data.conversation?.title || currentConvTitle || "New Chat").trim() || "New Chat";
    latestSummaryStatus = null;
    clearPendingDeleteMessage({ render: false });
    streamingCanvasDocuments = [];
    resetStreamingCanvasPreview();
    activeCanvasDocumentId = getActiveCanvasDocument(history)?.id || null;
    lastConversationSignature = serverSignature;
    renderConversationHistory({ preserveScroll: true });
    renderCanvasPanel();
    updateExportPanel();
    rebuildTokenStatsFromHistory();
  }

  if (memoryChanged) {
    applyConversationMemoryState(data);
  }

  loadSidebar();
  return true;
}

function scheduleConversationRefreshAfterStream() {
  if (!currentConvId) {
    return;
  }

  const refreshGeneration = ++conversationRefreshGeneration;
  pendingConversationRefreshTimers.forEach((timerId) => window.clearTimeout(timerId));
  pendingConversationRefreshTimers.clear();

  [800, 2000, 5000, 10000].forEach((delay) => {
    const timerId = window.setTimeout(async () => {
      pendingConversationRefreshTimers.delete(timerId);
      if (refreshGeneration !== conversationRefreshGeneration || !currentConvId || isStreaming || isFixing) {
        return;
      }

      try {
        const refreshed = await refreshConversationFromServer();
        if (refreshed) {
          pendingConversationRefreshTimers.forEach((pendingTimerId) => window.clearTimeout(pendingTimerId));
          pendingConversationRefreshTimers.clear();
        }
      } catch (_) {
        // Ignore transient refresh errors and keep polling.
      }
    }, delay);
    pendingConversationRefreshTimers.add(timerId);
  });
}

function cancelPendingConversationRefreshes() {
  conversationRefreshGeneration += 1;
  pendingConversationRefreshTimers.forEach((timerId) => window.clearTimeout(timerId));
  pendingConversationRefreshTimers.clear();
}

function rebuildTokenStatsFromHistory() {
  resetTokenStats();
  history.forEach((message) => {
    if (message.role === "assistant" && message.usage) {
      updateStats(message.usage);
    }
  });
}

function createAssistantStreamingGroup() {
  const asstGroup = document.createElement("div");
  asstGroup.className = "msg-group assistant";

  const metaRow = document.createElement("div");
  metaRow.className = "msg-meta-row";

  const asstLabel = document.createElement("div");
  asstLabel.className = "msg-label";
  asstLabel.textContent = "Assistant";

  metaRow.appendChild(asstLabel);

  const stepLog = document.createElement("div");
  stepLog.className = "step-log";
  stepLog.style.display = "none";

  const asstBubble = document.createElement("div");
  asstBubble.className = "bubble";
  asstBubble.hidden = true;

  activeAssistantStreamingBubble = asstBubble;
  activeAssistantStreamingHasVisibleAnswer = false;

  asstGroup.appendChild(metaRow);
  asstGroup.appendChild(stepLog);
  asstGroup.appendChild(asstBubble);
  messagesEl.appendChild(asstGroup);
  scrollToBottom();

  return { asstGroup, stepLog, asstBubble };
}

function clearEmptyAssistantStreamingBubble() {
  if (!activeAssistantStreamingBubble || activeAssistantStreamingHasVisibleAnswer) {
    return false;
  }

  activeAssistantStreamingBubble.remove();
  activeAssistantStreamingBubble = null;
  return true;
}

function resetAssistantStreamingBubbleState() {
  activeAssistantStreamingBubble = null;
  activeAssistantStreamingHasVisibleAnswer = false;
}

function shouldAutoCollapseReasoning() {
  return Boolean(appSettings.reasoning_auto_collapse);
}

function finalizeAssistantStreamingGroup(asstGroup, stepLog, metadata) {
  if (!asstGroup) {
    return;
  }

  if (stepLog) {
    stepLog.style.display = "none";
  }

  updateAssistantFetchBadge(asstGroup, metadata);
  updateAssistantToolTrace(asstGroup, metadata);
  updateAssistantSubAgentTrace(asstGroup, metadata);
  updateReasoningPanel(asstGroup, getReasoningText(metadata), { forceOpen: true });
  appendClarificationPanel(asstGroup, metadata, {});
}

function applyPersistedMessageIds(persistedIds, assistantEntry) {
  if (!persistedIds || typeof persistedIds !== "object") {
    return;
  }

  const userId = Number(persistedIds.user_message_id);
  if (isPersistedMessageId(userId)) {
    for (let index = history.length - 1; index >= 0; index -= 1) {
      if (history[index].role === "user") {
        history[index].id = userId;
        break;
      }
    }
  }

  const assistantId = Number(persistedIds.assistant_message_id);
  if (assistantEntry && isPersistedMessageId(assistantId)) {
    assistantEntry.id = assistantId;
    saveAssistantReasoning(currentConvId, assistantId, assistantEntry?.metadata?.reasoning_content || "");
  }
}

function updateStats(usage, { replaceLast = false } = {}) {
  const normalizedUsage = normalizeUsagePayload(usage);
  if (replaceLast && tokenTurns.length) {
    tokenTurns[tokenTurns.length - 1] = normalizedUsage;
  } else {
    tokenTurns.push(normalizedUsage);
  }
  renderTokenStats();
}

function fmt(value) {
  return Number.isFinite(value) ? value.toLocaleString() : "—";
}

function estimateLocalTokens(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return 0;
  }

  const words = normalized.split(/\s+/).filter(Boolean).length;
  const charEstimate = normalized.length / 4;
  const wordEstimate = words * 1.35;
  return Math.max(1, Math.round(Math.max(charEstimate, wordEstimate)));
}

function getSummaryModeValue() {
  return String(appSettings.chat_summary_mode || "auto").trim() || "auto";
}

function getSummarySkipFirstValue() {
  const rawValue = Number.parseInt(String(appSettings.summary_skip_first || "0"), 10);
  return Number.isFinite(rawValue) ? Math.max(0, rawValue) : 0;
}

function getSummarySkipLastValue() {
  const rawValue = Number.parseInt(String(appSettings.summary_skip_last || "0"), 10);
  return Number.isFinite(rawValue) ? Math.max(0, rawValue) : 0;
}

function getSummaryTriggerValue() {
  const rawValue = parseInt(appSettings.chat_summary_trigger_token_count || 80000, 10);
  return Number.isFinite(rawValue) ? rawValue : 80000;
}

function getEffectiveSummaryTriggerValue() {
  const baseTrigger = getSummaryTriggerValue();
  const mode = getSummaryModeValue();
  if (mode === "aggressive") {
    return Math.max(1000, Math.floor(baseTrigger / 2));
  }
  if (mode === "conservative") {
    return Math.min(200000, Math.max(1000, Math.ceil(baseTrigger * 1.5)));
  }
  return baseTrigger;
}

function estimateSummaryTriggerTokens(entries = history) {
  return (entries || []).reduce((total, entry) => {
    const role = String(entry?.role || "").trim();
    if (!role) {
      return total;
    }
    const metadata = entry?.metadata && typeof entry.metadata === "object" ? entry.metadata : null;
    if (metadata?.is_pruned === true) {
      return total;
    }
    if (role === "assistant" && Array.isArray(entry?.tool_calls) && entry.tool_calls.length > 0) {
      return total;
    }
    if (!["user", "assistant", "tool", "summary"].includes(role)) {
      return total;
    }
    return total + estimateLocalTokens(entry.content);
  }, 0);
}

function findLatestSummaryEntry(entries = history) {
  for (let index = (entries || []).length - 1; index >= 0; index -= 1) {
    const entry = entries[index];
    if (entry?.role === "summary") {
      return entry;
    }
  }
  return null;
}

function getSummaryEligibleMessages(entries = history, skipFirst = getSummarySkipFirstValue(), skipLast = getSummarySkipLastValue()) {
  const candidates = (entries || [])
    .filter((entry) => isPrunableHistoryMessage(entry))
    .sort((left, right) => {
      const leftPosition = Number(left?.position || 0);
      const rightPosition = Number(right?.position || 0);
      if (leftPosition !== rightPosition) {
        return leftPosition - rightPosition;
      }
      return Number(left?.id || 0) - Number(right?.id || 0);
    });

  if (skipFirst + skipLast >= candidates.length) {
    return [];
  }
  return skipLast > 0 ? candidates.slice(skipFirst, candidates.length - skipLast) : candidates.slice(skipFirst);
}

function parseSummaryMessageCount() {
  if (summaryAllMessagesCheckbox?.checked === true) {
    return null;
  }
  const rawValue = String(summaryMessageCountInput?.value || "").trim();
  if (!rawValue) {
    return null;
  }
  const parsed = Number.parseInt(rawValue, 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return null;
  }
  return parsed;
}

function getSummaryHistoryEntries(entries = history) {
  return (entries || [])
    .filter((entry) => entry?.role === "summary")
    .slice()
    .sort((left, right) => {
      const leftMeta = left?.metadata && typeof left.metadata === "object" ? left.metadata : null;
      const rightMeta = right?.metadata && typeof right.metadata === "object" ? right.metadata : null;
      const leftGeneratedAt = String(leftMeta?.generated_at || "").trim();
      const rightGeneratedAt = String(rightMeta?.generated_at || "").trim();
      const leftTime = leftGeneratedAt ? Date.parse(leftGeneratedAt) : Number.NaN;
      const rightTime = rightGeneratedAt ? Date.parse(rightGeneratedAt) : Number.NaN;
      if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
        return rightTime - leftTime;
      }
      const leftPosition = Number(left?.position || 0);
      const rightPosition = Number(right?.position || 0);
      if (leftPosition !== rightPosition) {
        return rightPosition - leftPosition;
      }
      return Number(right?.id || 0) - Number(left?.id || 0);
    });
}

function renderSummaryHistoryList() {
  if (!summaryHistoryList) {
    return;
  }

  const summaryEntries = getSummaryHistoryEntries(history);
  if (!currentConvId) {
    summaryHistoryList.innerHTML = '<div class="summary-history-empty">Open a conversation to review generated summaries.</div>';
    return;
  }
  if (!summaryEntries.length) {
    summaryHistoryList.innerHTML = '<div class="summary-history-empty">No summaries have been generated for this conversation yet.</div>';
    return;
  }

  const fragment = document.createDocumentFragment();
  const latestSummaryId = Number(findLatestSummaryEntry(history)?.id || 0);

  summaryEntries.forEach((entry) => {
    const metadata = entry?.metadata && typeof entry.metadata === "object" ? entry.metadata : {};
    const article = document.createElement("article");
    article.className = "summary-history-item";

    const header = document.createElement("div");
    header.className = "summary-history-item__header";

    const copy = document.createElement("div");
    const title = document.createElement("div");
    title.className = "summary-history-item__title";
    title.textContent = `Summary from ${formatSummaryTimestamp(metadata.generated_at)}`;
    copy.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "summary-history-item__meta";
    const metaValues = [
      Number(metadata.covered_message_count || 0) > 0 ? `${metadata.covered_message_count} messages` : "Summary",
      SUMMARY_SOURCE_LABELS[String(metadata.summary_source || "").trim()] || "Conversation history",
      `Level ${Math.max(1, Number(metadata.summary_level || 1) || 1)}`,
      Number(entry?.id || 0) === latestSummaryId ? "Latest" : "Visible",
    ];
    metaValues.forEach((value) => {
      const chip = document.createElement("span");
      chip.className = "summary-history-item__chip";
      chip.textContent = value;
      meta.appendChild(chip);
    });
    copy.appendChild(meta);
    header.appendChild(copy);

    const actions = document.createElement("div");
    actions.className = "summary-history-item__actions";

    const viewButton = document.createElement("button");
    viewButton.type = "button";
    viewButton.className = "btn-ghost";
    viewButton.textContent = "View summary";

    const undoButton = document.createElement("button");
    undoButton.type = "button";
    undoButton.className = "btn-ghost";
    undoButton.textContent = "Undo";
    undoButton.disabled = isSummaryOperationInFlight;

    actions.append(viewButton, undoButton);
    header.appendChild(actions);

    const preview = document.createElement("p");
    preview.className = "summary-history-item__preview";
    const normalizedPreview = String(entry?.content || "").replace(/\s+/g, " ").trim();
    preview.textContent = normalizedPreview.length > 180 ? `${normalizedPreview.slice(0, 180).trimEnd()}…` : (normalizedPreview || "Summary content is empty.");

    const body = document.createElement("div");
    body.className = "summary-history-item__body";
    body.hidden = true;
    body.innerHTML = renderMarkdown(entry?.content || "");

    viewButton.addEventListener("click", () => {
      const nextHidden = !body.hidden;
      body.hidden = nextHidden;
      viewButton.textContent = nextHidden ? "View summary" : "Hide summary";
    });
    undoButton.addEventListener("click", () => {
      void undoConversationSummary(Number(entry?.id || 0), { triggerButton: undoButton });
    });

    article.append(header, preview, body);
    fragment.appendChild(article);
  });

  summaryHistoryList.replaceChildren(fragment);
}

function formatSummaryTimestamp(value) {
  const timestamp = String(value || "").trim();
  if (!timestamp) {
    return "—";
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toLocaleString();
}

function describeSummaryFailure(status) {
  const reason = String(status?.reason || "").trim();
  const stage = String(status?.failure_stage || "").trim();
  const detail = String(status?.failure_detail || "").trim();

  if (reason === "mode_never") {
    return "Auto summary is disabled by settings.";
  }
  if (reason === "below_threshold") {
    const tokenGap = Number(status?.token_gap || 0);
    return tokenGap > 0
      ? `Below threshold by ${fmt(tokenGap)} counted tokens.`
      : "Still below the summary trigger threshold.";
  }
  if (reason === "no_source_messages") {
    return "There are no older unsummarized user or assistant messages left to compress.";
  }
  if (reason === "no_prompt_messages") {
    return "Candidate messages existed, but all of them were empty or invalid after prompt sanitization.";
  }
  if (reason === "locked") {
    return "Another summary pass was already running, so this turn skipped a duplicate summary attempt.";
  }
  if (reason !== "summary_generation_failed") {
    return detail || "Waiting for the next completed assistant turn to evaluate summary conditions.";
  }

  if (stage === "context_too_large") {
    return "The provider rejected the summary request because the summary prompt itself exceeded the model context limit.";
  }
  if (stage === "invalid_message_sequence") {
    return "The provider rejected the summary prompt because the message sequence was invalid.";
  }
  if (stage === "tool_call_unexpected") {
    return "The model attempted a tool-style response during summary generation, so the result was rejected for safety.";
  }
  if (stage === "empty_output") {
    return "The provider returned no assistant summary content.";
  }
  if (stage === "too_short") {
    return "The provider returned a summary that was too short to keep as reliable compressed context.";
  }
  if (stage === "provider_error") {
    return "The provider returned an error while generating the summary.";
  }
  return detail || "The summary attempt failed validation, so no messages were compressed.";
}

function updateSummarySelectionUi() {
  const eligibleMessages = getSummaryEligibleMessages(history);
  const eligibleCount = eligibleMessages.length;
  const allMessagesEligibleCount = eligibleCount;
  const skipFirst = getSummarySkipFirstValue();
  const skipLast = getSummarySkipLastValue();
  const mode = SUMMARY_MODE_LABELS[getSummaryModeValue()] || SUMMARY_MODE_LABELS.auto;
  const detailLabel = getSummaryDetailLabel(appSettings.chat_summary_detail_level || "balanced");
  const summarizeAllMessages = summaryAllMessagesCheckbox?.checked === true;

  if (summaryMessageCountInput) {
    const requestedCount = parseSummaryMessageCount();
    summaryMessageCountInput.max = String(Math.max(eligibleCount, 1));
    summaryMessageCountInput.disabled = isSummaryOperationInFlight || !currentConvId || eligibleCount === 0 || summarizeAllMessages;
    if (eligibleCount === 0 || summarizeAllMessages) {
      summaryMessageCountInput.value = "";
    } else if (requestedCount !== null && requestedCount > eligibleCount) {
      summaryMessageCountInput.value = String(eligibleCount);
    }
  }

  if (summaryAllMessagesCheckbox) {
    summaryAllMessagesCheckbox.disabled = isSummaryOperationInFlight || !currentConvId || allMessagesEligibleCount === 0;
  }

  if (summarySelectionNote) {
    if (!currentConvId) {
      summarySelectionNote.textContent = "Open a conversation to see which messages are currently eligible for summary.";
    } else if (summarizeAllMessages) {
      summarySelectionNote.textContent = allMessagesEligibleCount > 0
        ? `All ${fmt(allMessagesEligibleCount)} eligible messages will be summarized. The protected messages from Settings stay in place.`
        : "No messages are currently eligible for summary.";
    } else if (!eligibleCount) {
      summarySelectionNote.textContent = "No messages are currently eligible after the protected first/last message window from Settings is applied.";
    } else {
      summarySelectionNote.textContent = `Eligible after Settings protection: ${eligibleCount} messages. Leave the field blank for automatic selection or choose any value from 1 to ${eligibleCount}.`;
    }
  }

  if (summarySettingsNote) {
    summarySettingsNote.textContent = `Current Settings: mode ${mode}, detail ${detailLabel}, protect first ${skipFirst}, protect last ${skipLast}.`;
  }
}

async function undoConversationSummary(summaryId, { triggerButton = null } = {}) {
  const normalizedSummaryId = Number(summaryId || 0);
  if (!currentConvId || !normalizedSummaryId) {
    showToast("No summary is available to undo.", "warning");
    return;
  }

  const originalButtonText = triggerButton ? triggerButton.textContent : "";
  setSummaryBusyState(true);
  startSummaryProgress("Restoring summary…");
  if (triggerButton) {
    triggerButton.disabled = true;
    triggerButton.textContent = "Restoring…";
  }

  try {
    const response = await fetch(`/api/conversations/${currentConvId}/summaries/${normalizedSummaryId}/undo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to undo summary.");
    }

    if (Array.isArray(data.messages)) {
      history = data.messages.map(normalizeHistoryEntry);
      rebuildTokenStatsFromHistory();
      renderConversationHistory();
    }
    resetSummaryPreview({ hide: true });

    latestSummaryStatus = {
      applied: false,
      reason: "summary_undone",
      failure_stage: null,
      failure_detail: "The selected summary was reverted and the covered messages were restored.",
    };
    const restoredCount = Number(data.restored_message_count || 0);
    finishSummaryProgress(
      restoredCount > 0
        ? `${restoredCount} message${restoredCount === 1 ? " was" : "s were"} restored.`
        : "Summary was undone."
    );
    showToast(
      restoredCount > 0
        ? `${restoredCount} message${restoredCount === 1 ? " was" : "s were"} restored.`
        : "Summary was undone.",
      "success"
    );
    renderSummaryInspector();
  } catch (error) {
    failSummaryProgress(error.message || "Failed to undo summary.");
    showToast(error.message || "Failed to undo summary.", "error");
    renderSummaryInspector();
  } finally {
    setSummaryBusyState(false);
    if (triggerButton) {
      triggerButton.textContent = originalButtonText || "Undo";
    }
    renderSummaryInspector();
  }
}

function renderSummaryInspector() {
  if (!summaryInspectorBadge || !summaryInspectorHeadline) {
    return;
  }

  const mode = getSummaryModeValue();
  const effectiveTrigger = getEffectiveSummaryTriggerValue();
  const currentEstimate = estimateSummaryTriggerTokens(history);
  const latestSummary = findLatestSummaryEntry(history);
  const lastSummaryMeta = latestSummary?.metadata && typeof latestSummary.metadata === "object"
    ? latestSummary.metadata
    : null;
  const canUndoLatestSummary = Boolean(currentConvId && Number.isInteger(Number(latestSummary?.id)) && lastSummaryMeta?.is_summary);
  const remaining = Math.max(0, effectiveTrigger - currentEstimate);
  const overBy = Math.max(0, currentEstimate - effectiveTrigger);
  const latestServerCheck = Number(latestSummaryStatus?.visible_token_count || 0);
  const mergedAssistantCount = Number(latestSummaryStatus?.merged_assistant_message_count || 0);
  const skippedErrorCount = Number(latestSummaryStatus?.skipped_error_message_count || 0);

  let badgeTone = "muted";
  let badgeText = "Waiting";
  let headline = "Start chatting to see when automatic summary will run.";

  if (mode === "never") {
    badgeTone = "warning";
    badgeText = "Disabled";
    headline = "Auto summary is disabled. Long chats will keep growing until you re-enable it.";
  } else if (mode === "conservative") {
    badgeTone = "muted";
    badgeText = "Conservative";
    headline = "Auto summary is using a higher threshold, so it will compress less often.";
  } else if (!currentConvId) {
    badgeTone = "muted";
    badgeText = "Idle";
    headline = "Auto summary watches each conversation after messages are saved.";
  } else if (latestSummaryStatus?.reason === "summary_generation_failed") {
    badgeTone = "error";
    badgeText = "Failed";
    headline = describeSummaryFailure(latestSummaryStatus);
  } else if (latestSummaryStatus?.reason === "locked") {
    badgeTone = "warning";
    badgeText = "Busy";
    headline = "A summary pass was already in progress for this conversation, so this turn skipped a duplicate run.";
  } else if (currentEstimate >= effectiveTrigger) {
    badgeTone = "accent";
    badgeText = "Ready";
    headline = "This conversation is large enough for auto summary. The next completed turn can compress older user and assistant messages.";
  } else if (latestSummary) {
    badgeTone = "success";
    badgeText = "Tracked";
    headline = "This conversation has already been summarized before and is being monitored for the next pass.";
  } else {
    badgeTone = "muted";
    badgeText = "Tracking";
    headline = `Current conversation is ${fmt(remaining)} estimated tokens below the next auto-summary pass.`;
  }

  summaryInspectorBadge.dataset.tone = badgeTone;
  summaryInspectorBadge.textContent = badgeText;
  summaryInspectorHeadline.textContent = headline;
  summaryInspectorCurrent.textContent = fmt(currentEstimate);
  summaryInspectorTrigger.textContent = fmt(effectiveTrigger);
  summaryInspectorGap.textContent = overBy > 0 ? `${fmt(overBy)} over` : `${fmt(remaining)} left`;

  const detailParts = [
    "Counts user, assistant, tool, and summary history toward the summary trigger, while ignoring assistant tool-call placeholders and stored context-injection metadata.",
    "Does not count runtime system prompt, RAG context, or final-answer instructions.",
  ];
  if (latestServerCheck > 0) {
    detailParts.push(`Last server-side check saw ${fmt(latestServerCheck)} counted tokens.`);
  }
  if (mergedAssistantCount > 0) {
    detailParts.push(`Merged ${fmt(mergedAssistantCount)} consecutive assistant blocks before sending the summary prompt.`);
  }
  if (skippedErrorCount > 0) {
    detailParts.push(`Skipped ${fmt(skippedErrorCount)} assistant error placeholders during prompt cleanup.`);
  }
  summaryInspectorDetail.textContent = detailParts.join(" ");

  if (summaryInspectorToolMessages) {
    const toolMessageParts = [
      "Assistant tool-call placeholders are excluded from the trigger estimate.",
      "Tool outputs and cleaned assistant content still count toward summary readiness.",
    ];
    if (mergedAssistantCount > 0) {
      toolMessageParts.push(`${fmt(mergedAssistantCount)} assistant blocks were merged during the latest cleanup pass.`);
    }
    if (skippedErrorCount > 0) {
      toolMessageParts.push(`${fmt(skippedErrorCount)} assistant error placeholders were skipped.`);
    }
    summaryInspectorToolMessages.textContent = toolMessageParts.join(" ");
  }

  if (summaryInspectorReason) {
    let reasonText = "The latest summary decision will appear here after each completed assistant turn.";
    if (latestSummaryStatus) {
      if (latestSummaryStatus.reason === "summary_generation_failed" || latestSummaryStatus.reason === "locked" || latestSummaryStatus.reason === "below_threshold" || latestSummaryStatus.reason === "mode_never") {
        reasonText = describeSummaryFailure(latestSummaryStatus);
      } else if (latestSummaryStatus.applied) {
        reasonText = "Latest summary pass completed successfully.";
      } else {
        reasonText = "Latest summary check completed.";
      }
      const failureDetail = String(latestSummaryStatus.failure_detail || "").trim();
      const failureSummary = describeSummaryFailure(latestSummaryStatus);
      if (failureDetail && failureDetail !== failureSummary) {
        reasonText = `${reasonText} ${failureDetail}`;
      }
    }
    summaryInspectorReason.textContent = reasonText;
  }

  if (lastSummaryMeta?.is_summary) {
    const generatedAt = formatSummaryTimestamp(lastSummaryMeta.generated_at);
    const coveredCount = Number(lastSummaryMeta.covered_message_count || 0);
    const summaryModel = String(lastSummaryMeta.summary_model || latestSummaryStatus?.summary_model || "—").trim() || "—";
    summaryInspectorLast.textContent = `Last pass: ${fmt(coveredCount)} messages compressed on ${generatedAt} using ${summaryModel}.`;
  } else if (latestSummaryStatus?.reason === "summary_generation_failed") {
    const checkedAt = formatSummaryTimestamp(latestSummaryStatus.checked_at);
    summaryInspectorLast.textContent = `Last attempt: failed on ${checkedAt}. No messages were deleted because failed summaries are never applied.`;
  } else if (latestSummaryStatus?.reason === "below_threshold") {
    summaryInspectorLast.textContent = "No summary pass was needed on the latest turn because the conversation stayed below the trigger.";
  } else if (latestSummaryStatus?.reason === "mode_never") {
    summaryInspectorLast.textContent = "No summary pass will run while summary mode is set to Never.";
  } else {
    summaryInspectorLast.textContent = "No summary pass has run in this conversation yet.";
  }

  if (summaryUndoBtn) {
    summaryUndoBtn.disabled = isSummaryOperationInFlight || !canUndoLatestSummary;
    summaryUndoBtn.title = canUndoLatestSummary
      ? "Restore the messages covered by the latest summary."
      : "No summary is available to undo in this conversation.";
  }
  if (summaryNowBtn) {
    summaryNowBtn.disabled = isSummaryOperationInFlight || !currentConvId;
    summaryNowBtn.title = currentConvId
      ? "Run a manual summary using the current panel settings."
      : "Open a conversation before running a summary.";
  }
  if (summaryPreviewBtn) {
    summaryPreviewBtn.disabled = isSummaryOperationInFlight || !currentConvId;
    summaryPreviewBtn.title = currentConvId
      ? "Preview which messages will be summarized without applying changes."
      : "Open a conversation before running a preview.";
  }
  updateSummarySelectionUi();
  renderSummaryHistoryList();
}

function openStats() {
  closeMobileTools();
  closeCanvas();
  closeExportPanel();
  closeSummaryPanel();
  closeMemoryPanel();
  statsPanel.classList.add("open");
  statsOverlay.classList.add("open");
}

function closeStats() {
  statsPanel.classList.remove("open");
  statsOverlay.classList.remove("open");
}

function openMobileTools() {
  closeStats();
  closeCanvas();
  closeExportPanel();
  closeSummaryPanel();
  closeMemoryPanel();
  mobileToolsPanel?.classList.add("open");
  mobileToolsOverlay?.classList.add("open");
  mobileToolsBtn?.setAttribute("aria-expanded", "true");
  mobileToolsPanel?.setAttribute("aria-hidden", "false");
}

function closeMobileTools() {
  mobileToolsPanel?.classList.remove("open");
  mobileToolsOverlay?.classList.remove("open");
  mobileToolsBtn?.setAttribute("aria-expanded", "false");
  mobileToolsPanel?.setAttribute("aria-hidden", "true");
}

function getKnownModelLabel(modelId) {
  const normalizedId = String(modelId || "").trim();
  if (!normalizedId) {
    return "";
  }
  const match = knownModelOptions.find((model) => String(model?.id || "") === normalizedId);
  return String(match?.name || "").trim();
}

function isKnownModelId(modelId) {
  const normalizedId = String(modelId || "").trim();
  if (!normalizedId) {
    return false;
  }
  return knownModelOptions.some((model) => String(model?.id || "").trim() === normalizedId);
}

function readModelPreference() {
  try {
    const stored = String(localStorage.getItem(MODEL_PREFERENCE_STORAGE_KEY) || "").trim();
    return isKnownModelId(stored) ? stored : "";
  } catch (_) {
    return "";
  }
}

function writeModelPreference(modelId) {
  try {
    const normalizedId = String(modelId || "").trim();
    if (normalizedId && isKnownModelId(normalizedId)) {
      localStorage.setItem(MODEL_PREFERENCE_STORAGE_KEY, normalizedId);
    } else {
      localStorage.removeItem(MODEL_PREFERENCE_STORAGE_KEY);
    }
  } catch (_) {
    // Ignore storage errors.
  }
}

function resolvePreferredModelSelection(fallbackModelId = "") {
  const candidateValues = [
    isMobileViewport() ? mobileModelSel?.value : modelSel?.value,
    modelSel?.value,
    mobileModelSel?.value,
    readModelPreference(),
    fallbackModelId,
  ];

  for (const candidateValue of candidateValues) {
    const normalizedId = String(candidateValue || "").trim();
    if (isKnownModelId(normalizedId)) {
      return normalizedId;
    }
  }

  return "";
}

function ensureModelSelectorOption(selectEl, modelId, label = "") {
  if (!selectEl) {
    return;
  }
  const normalizedId = String(modelId || "").trim();
  if (!normalizedId) {
    return;
  }

  let option = Array.from(selectEl.options).find((entry) => entry.value === normalizedId) || null;
  const nextLabel = String(label || getKnownModelLabel(normalizedId) || normalizedId).trim() || normalizedId;
  if (!option) {
    option = document.createElement("option");
    option.value = normalizedId;
    option.textContent = nextLabel;
    selectEl.append(option);
    return;
  }
  if (nextLabel && option.textContent !== nextLabel) {
    option.textContent = nextLabel;
  }
}

function syncModelSelectors(value, label = "") {
  const nextValue = String(value || "");
  if (nextValue) {
    ensureModelSelectorOption(modelSel, nextValue, label);
    ensureModelSelectorOption(mobileModelSel, nextValue, label);
  }
  if (modelSel && modelSel.value !== nextValue) {
    modelSel.value = nextValue;
  }
  if (mobileModelSel && mobileModelSel.value !== nextValue) {
    mobileModelSel.value = nextValue;
  }
  writeModelPreference(nextValue);
}

function normalizePersonaId(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) && parsed > 0 ? String(parsed) : "";
}

function getKnownPersonas() {
  return Array.isArray(appSettings.personas) ? appSettings.personas : [];
}

function findPersonaById(personaId) {
  const normalizedPersonaId = normalizePersonaId(personaId);
  if (!normalizedPersonaId) {
    return null;
  }
  return getKnownPersonas().find((persona) => normalizePersonaId(persona?.id) === normalizedPersonaId) || null;
}

function getDefaultPersonaId() {
  return normalizePersonaId(appSettings.default_persona_id);
}

function buildDefaultPersonaLabel() {
  const defaultPersona = findPersonaById(getDefaultPersonaId());
  return defaultPersona ? `Default: ${defaultPersona.name}` : "No persona";
}

function populatePersonaSelectors() {
  const selectors = [personaSel, mobilePersonaSel].filter(Boolean);
  if (!selectors.length) {
    return;
  }

  const options = [
    { value: "", label: buildDefaultPersonaLabel() },
    ...getKnownPersonas().map((persona) => ({
      value: normalizePersonaId(persona?.id),
      label: String(persona?.name || `Persona ${persona?.id || ""}`).trim() || `Persona ${persona?.id || ""}`,
    })),
  ];

  selectors.forEach((selectEl) => {
    const fragment = document.createDocumentFragment();
    options.forEach((optionData) => {
      const option = document.createElement("option");
      option.value = optionData.value;
      option.textContent = optionData.label;
      fragment.append(option);
    });
    selectEl.replaceChildren(fragment);
  });
}

function syncPersonaSelectors(value = "") {
  const nextValue = normalizePersonaId(value);
  populatePersonaSelectors();
  if (personaSel) {
    personaSel.value = nextValue;
  }
  if (mobilePersonaSel) {
    mobilePersonaSel.value = nextValue;
  }
}

function applyConversationPersonaSelection(personaId) {
  currentConversationPersonaId = normalizePersonaId(personaId);
  syncPersonaSelectors(currentConversationPersonaId);
}

async function persistConversationPersona(personaId) {
  if (!currentConvId) {
    return;
  }
  const response = await fetch(`/api/conversations/${currentConvId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona_id: normalizePersonaId(personaId) || null }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Unable to update conversation persona.");
  }
  applyConversationPersonaSelection(data.persona_id);
}

function isMobileViewport() {
  return window.matchMedia("(max-width: 980px)").matches;
}

function updateHeaderOffset() {
  if (!headerEl) {
    return;
  }
  document.documentElement.style.setProperty("--header-offset", `${headerEl.offsetHeight}px`);
}

function readSidebarPreference() {
  try {
    const stored = localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (stored === null) {
      return null;
    }
    return stored === "true";
  } catch (_) {
    return null;
  }
}

function writeSidebarPreference(isOpen) {
  try {
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(Boolean(isOpen)));
  } catch (_) {
    // Ignore storage errors.
  }
}

function updateSidebarToggleLabel(isOpen) {
  if (!sidebarToggleBtn) {
    return;
  }
  sidebarToggleBtn.setAttribute("aria-expanded", String(Boolean(isOpen)));
  sidebarToggleBtn.title = isOpen ? "Hide conversations" : "Show conversations";
}

function setSidebarOpen(isOpen, persist = true) {
  document.body.classList.toggle("sidebar-collapsed", !isOpen);
  updateSidebarToggleLabel(isOpen);
  if (persist) {
    writeSidebarPreference(isOpen);
  }
}

function toggleSidebar() {
  const isOpen = !document.body.classList.contains("sidebar-collapsed");
  setSidebarOpen(!isOpen);
}

function closeSidebarOnMobile() {
  if (isMobileViewport()) {
    setSidebarOpen(false);
  }
}

statsClose.addEventListener("click", closeStats);
statsOverlay.addEventListener("click", closeStats);
if (canvasClose) {
  canvasClose.addEventListener("click", closeCanvas);
}
if (canvasOverlay) {
  canvasOverlay.addEventListener("click", closeCanvas);
}
if (canvasEditBtn) {
  canvasEditBtn.addEventListener("click", () => setCanvasEditing(true));
}
if (canvasNewBtn) {
  canvasNewBtn.addEventListener("click", () => {
    void createCanvasDocumentFromPrompt();
  });
}
if (canvasUploadBtn) {
  canvasUploadBtn.addEventListener("click", () => {
    openCanvasUploadPicker();
  });
}
if (canvasUploadInput) {
  canvasUploadInput.addEventListener("change", () => {
    const selectedFile = canvasUploadInput.files?.[0] || null;
    if (!selectedFile) {
      return;
    }
    canvasUploadInput.value = "";
    void createCanvasDocumentFromFile(selectedFile);
  });
}
if (canvasSaveBtn) {
  canvasSaveBtn.addEventListener("click", () => {
    void saveCanvasEdits();
  });
}
if (canvasCancelBtn) {
  canvasCancelBtn.addEventListener("click", () => {
    cancelCanvasEditing({ statusMessage: "Canvas edit cancelled.", tone: "muted" });
  });
}
if (mobileCanvasBtn) {
  mobileCanvasBtn.addEventListener("click", () => openCanvas(mobileToolsBtn || mobileCanvasBtn));
}
if (canvasToggleBtn) {
  canvasToggleBtn.addEventListener("click", () => {
    if (isCanvasOpen()) {
      closeCanvas();
    } else {
      openCanvas(canvasToggleBtn);
    }
  });
}
if (memoryToggleBtn) {
  memoryToggleBtn.addEventListener("click", () => {
    if (isMemoryPanelOpen()) {
      closeMemoryPanel();
    } else {
      openMemoryPanel(memoryToggleBtn);
    }
  });
}
if (mobileExportBtn) {
  mobileExportBtn.addEventListener("click", () => openExportPanel(mobileToolsBtn || mobileExportBtn));
}
if (mobileMemoryBtn) {
  mobileMemoryBtn.addEventListener("click", () => openMemoryPanel(mobileToolsBtn || mobileMemoryBtn));
}
if (mobilePruneBtn) {
  mobilePruneBtn.addEventListener("click", () => {
    closeMobileTools();
    void pruneConversationHistory();
  });
}
if (exportClose) {
  exportClose.addEventListener("click", closeExportPanel);
}
if (exportOverlay) {
  exportOverlay.addEventListener("click", closeExportPanel);
}
if (conversationExportMdBtn) {
  conversationExportMdBtn.addEventListener("click", () => downloadConversation("md"));
}
if (conversationExportJsonBtn) {
  conversationExportJsonBtn.addEventListener("click", () => downloadConversation("json"));
}
if (conversationExportDocxBtn) {
  conversationExportDocxBtn.addEventListener("click", () => downloadConversation("docx"));
}
if (conversationExportPdfBtn) {
  conversationExportPdfBtn.addEventListener("click", () => downloadConversation("pdf"));
}
if (canvasCopyBtn) {
  canvasCopyBtn.addEventListener("click", async () => {
    closeCanvasOverflowMenu();
    const document = getCanvasDocumentById(getCanvasRenderableDocuments(), activeCanvasDocumentId) || getActiveCanvasDocument();
    if (!document) {
      setCanvasStatus("Clipboard is not available.", "warning");
      return;
    }
    try {
      const copied = await copyTextToClipboard(document.content || "");
      if (!copied) {
        setCanvasStatus("Clipboard is not available.", "warning");
        return;
      }
      setCanvasStatus("Canvas copied to clipboard.", "success");
    } catch (_) {
      setCanvasStatus("Copy failed.", "danger");
    }
  });
}
if (canvasCopyRefBtn) {
  canvasCopyRefBtn.addEventListener("click", async () => {
    const document = getCanvasDocumentById(getCanvasRenderableDocuments(), activeCanvasDocumentId) || getActiveCanvasDocument();
    const reference = getCanvasDocumentReference(document);
    if (!reference) {
      setCanvasStatus("Reference copy is not available.", "warning");
      return;
    }
    try {
      const copied = await copyTextToClipboard(reference);
      if (!copied) {
        setCanvasStatus("Reference copy is not available.", "warning");
        return;
      }
      setCanvasStatus(document?.path ? "Canvas path copied." : "Canvas title copied.", "success");
    } catch (_) {
      setCanvasStatus("Reference copy failed.", "danger");
    }
  });
}
if (canvasResetFiltersBtn) {
  canvasResetFiltersBtn.addEventListener("click", () => resetCanvasFilters());
}
if (canvasDeleteBtn) {
  canvasDeleteBtn.addEventListener("click", () => {
    closeCanvasOverflowMenu();
    void deleteCanvasDocuments();
  });
}
if (canvasRenameBtn) {
  canvasRenameBtn.addEventListener("click", () => {
    closeCanvasOverflowMenu();
    void renameCanvasDocument();
  });
}
if (canvasClearBtn) {
  canvasClearBtn.addEventListener("click", () => {
    closeCanvasOverflowMenu();
    void deleteCanvasDocuments({ clearAll: true });
  });
}
if (canvasDownloadHtmlBtn) {
  canvasDownloadHtmlBtn.addEventListener("click", () => {
    closeCanvasOverflowMenu();
    downloadCanvasDocument("html");
  });
}
if (canvasDownloadMdBtn) {
  canvasDownloadMdBtn.addEventListener("click", () => {
    closeCanvasOverflowMenu();
    downloadCanvasDocument("md");
  });
}
if (canvasDownloadPdfBtn) {
  canvasDownloadPdfBtn.addEventListener("click", () => {
    closeCanvasOverflowMenu();
    downloadCanvasDocument("pdf");
  });
}
if (canvasMoreBtn) {
  canvasMoreBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleCanvasOverflowMenu();
  });
  canvasMoreBtn.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      openCanvasOverflowMenu({ focusTarget: "first" });
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      openCanvasOverflowMenu({ focusTarget: "last" });
      return;
    }
    if (event.key === "Escape" && isCanvasOverflowMenuOpen()) {
      event.preventDefault();
      closeCanvasOverflowMenu({ restoreFocus: true });
    }
  });
}
if (canvasOverflowMenu) {
  canvasOverflowMenu.addEventListener("keydown", handleCanvasOverflowMenuKeydown);
}
if (canvasTreeToggleBtn) {
  canvasTreeToggleBtn.addEventListener("click", () => {
    closeCanvasOverflowMenu();
    setCanvasMobileTreeOpen(!isCanvasMobileTreeOpen);
  });
}
if (canvasSearchInput) {
  canvasSearchInput.addEventListener("input", () => renderCanvasPanel());
}
if (canvasRoleFilter) {
  canvasRoleFilter.addEventListener("change", () => renderCanvasPanel());
}
if (canvasPathFilter) {
  canvasPathFilter.addEventListener("change", () => renderCanvasPanel());
}
if (canvasFormatSelect) {
  canvasFormatSelect.addEventListener("change", () => {
    if (isCanvasEditing) {
      scheduleCanvasEditingPreviewRender();
    }
  });
}
if (canvasEditorEl) {
  canvasEditorEl.addEventListener("input", () => {
    scheduleCanvasEditingPreviewRender();
  });
  canvasEditorEl.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      void saveCanvasEdits();
    }
  });
}
if (sidebarToggleBtn) {
  sidebarToggleBtn.addEventListener("click", toggleSidebar);
}
if (sidebarOverlay) {
  sidebarOverlay.addEventListener("click", () => setSidebarOpen(false));
}
if (mobileToolsBtn) {
  mobileToolsBtn.addEventListener("click", () => {
    if (mobileToolsPanel?.classList.contains("open")) {
      closeMobileTools();
    } else {
      openMobileTools();
    }
  });
}
if (mobileToolsClose) {
  mobileToolsClose.addEventListener("click", closeMobileTools);
}
if (mobileToolsOverlay) {
  mobileToolsOverlay.addEventListener("click", closeMobileTools);
}
if (canvasConfirmOverlay) {
  canvasConfirmOverlay.addEventListener("click", () => closeCanvasConfirmModal("dismiss"));
}
if (canvasConfirmCloseBtn) {
  canvasConfirmCloseBtn.addEventListener("click", () => closeCanvasConfirmModal("dismiss"));
}
if (canvasConfirmLaterBtn) {
  canvasConfirmLaterBtn.addEventListener("click", () => closeCanvasConfirmModal("cancel"));
}
if (canvasConfirmOpenBtn) {
  canvasConfirmOpenBtn.addEventListener("click", () => closeCanvasConfirmModal("confirm"));
}
if (mobileTokensBtn) {
  mobileTokensBtn.addEventListener("click", () => {
    openStats();
    closeMobileTools();
  });
}
if (mobileSettingsBtn) {
  mobileSettingsBtn.addEventListener("click", closeMobileTools);
}
if (mobileLogoutBtn) {
  mobileLogoutBtn.addEventListener("click", closeMobileTools);
}
if (mobileSummaryBtn) {
  mobileSummaryBtn.addEventListener("click", () => openSummaryPanel(mobileSummaryBtn));
}

async function handlePersonaSelectionChange(nextPersonaId) {
  const previousPersonaId = currentConversationPersonaId;
  applyConversationPersonaSelection(nextPersonaId);
  if (!currentConvId) {
    return;
  }
  try {
    await persistConversationPersona(currentConversationPersonaId);
  } catch (error) {
    applyConversationPersonaSelection(previousPersonaId);
    showError(error.message || "Unable to update conversation persona.");
  }
}

if (modelSel) {
  modelSel.addEventListener("change", () => {
    syncModelSelectors(modelSel.value);
  });
}
if (mobileModelSel) {
  mobileModelSel.addEventListener("change", () => {
    syncModelSelectors(mobileModelSel.value);
  });
}
if (personaSel) {
  personaSel.addEventListener("change", () => {
    void handlePersonaSelectionChange(personaSel.value);
  });
}
if (mobilePersonaSel) {
  mobilePersonaSel.addEventListener("change", () => {
    void handlePersonaSelectionChange(mobilePersonaSel.value);
  });
}
summaryClose?.addEventListener("click", closeSummaryPanel);
summaryOverlay?.addEventListener("click", closeSummaryPanel);
memoryClose?.addEventListener("click", closeMemoryPanel);
memoryOverlay?.addEventListener("click", closeMemoryPanel);
summarySubmitBtn?.addEventListener("click", () => {
  void runConversationSummary({ triggerButton: summarySubmitBtn, closePanel: false });
});
summaryPreviewBtn?.addEventListener("click", () => {
  void previewConversationSummary({ triggerButton: summaryPreviewBtn });
});
summaryMessageCountInput?.addEventListener("input", updateSummarySelectionUi);
summaryAllMessagesCheckbox?.addEventListener("change", () => {
  if (summaryAllMessagesCheckbox.checked && summaryMessageCountInput) {
    summaryMessageCountInput.value = "";
  }
  updateSummarySelectionUi();
});
memoryAddBtn?.addEventListener("click", () => {
  void createConversationMemoryEntry();
});
if (memoryNewKeyEl) {
  memoryNewKeyEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void createConversationMemoryEntry();
    }
  });
}

window.addEventListener("resize", () => {
  updateHeaderOffset();
  if (!isMobileViewport()) {
    closeMobileTools();
  }
  setCanvasMobileTreeOpen(false);
  closeCanvasOverflowMenu();
  applyCanvasPanelWidth(readCanvasWidthPreference(), false);
  syncCanvasToggleButton();
}, { passive: true });

if (canvasResizeHandle) {
  canvasResizeHandle.addEventListener("mousedown", (event) => {
    if (isMobileViewport()) {
      return;
    }
    event.preventDefault();
    const onMouseMove = (moveEvent) => {
      const nextWidth = window.innerWidth - moveEvent.clientX;
      applyCanvasPanelWidth(nextWidth);
    };
    const onMouseUp = () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  });
}

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && isMemoryPanelOpen()) {
    closeMemoryPanel();
    return;
  }
  if (event.key === "Escape" && isSummaryPanelOpen()) {
    closeSummaryPanel();
    return;
  }
  if (event.key === "Escape" && isCanvasOverflowMenuOpen()) {
    closeCanvasOverflowMenu({ restoreFocus: true });
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "c") {
    event.preventDefault();
    if (isCanvasOpen()) {
      closeCanvas();
    } else {
      openCanvas();
    }
    return;
  }
  if (event.key === "Escape") {
    if (isCanvasConfirmOpen()) {
      closeCanvasConfirmModal("dismiss");
      return;
    }
    if (isCanvasOpen()) {
      if (isCanvasMobileTreeOpen) {
        setCanvasMobileTreeOpen(false);
        return;
      }
      if (isCanvasEditing) {
        cancelCanvasEditing({ statusMessage: "Canvas edit cancelled.", tone: "muted" });
      } else if (clearCanvasSearchInput({ statusMessage: "Canvas search cleared.", tone: "muted" })) {
        return;
      } else {
        closeCanvas();
      }
      return;
    }
    if (mobileToolsPanel?.classList.contains("open")) {
      closeMobileTools();
      return;
    }
  }
  if (event.key === "Tab" && isCanvasOpen()) {
    const focusable = getCanvasFocusableElements();
    if (!focusable.length) {
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const activeElement = document.activeElement;
    if (event.shiftKey && activeElement === first) {
      event.preventDefault();
      last.focus();
      return;
    }
    if (!event.shiftKey && activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
  if (event.key === "Escape" && !document.body.classList.contains("sidebar-collapsed") && isMobileViewport()) {
    setSidebarOpen(false);
  }
});

document.addEventListener("click", (event) => {
  const target = event.target;
  if (isCanvasOverflowMenuOpen()) {
    const clickedInsideMenu = target instanceof Node && (canvasOverflowMenu?.contains(target) || canvasMoreBtn?.contains(target));
    if (!clickedInsideMenu) {
      closeCanvasOverflowMenu();
    }
  }

  if (isCanvasMobileTreeOpen && isMobileViewport()) {
    const clickedInsideTree = target instanceof Node && (canvasTreePanel?.contains(target) || canvasTreeToggleBtn?.contains(target));
    if (!clickedInsideTree) {
      setCanvasMobileTreeOpen(false);
    }
  }
});

async function loadSidebar() {
  cancelSidebarRename();
  try {
    const response = await fetch("/api/conversations");
    const list = await response.json();
    sidebarList.innerHTML = "";
    if (list.length === 0) {
      sidebarList.innerHTML = '<p class="sidebar-empty">No conversations yet.</p>';
      return;
    }
    buildConversationSidebarSections(list).forEach(({ label, conversations }) => {
      const section = document.createElement("section");
      section.className = "sidebar-section";

      const heading = document.createElement("div");
      heading.className = "sidebar-section__heading";
      heading.textContent = label;
      section.appendChild(heading);

      const items = document.createElement("div");
      items.className = "sidebar-section__items";

      conversations.forEach((conversation) => {
        if (conversation.id === currentConvId) {
          currentConvTitle = String(conversation.title || "New Chat").trim() || "New Chat";
        }
        const item = document.createElement("div");
        item.className = "sidebar-item" + (conversation.id === currentConvId ? " active" : "");
        item.dataset.id = conversation.id;
        item.innerHTML =
          `<span class="sidebar-title">${escHtml(conversation.title)}</span>` +
          `<button class="sidebar-edit" title="Rename" aria-label="Rename" data-id="${conversation.id}">` +
          `  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">` +
          `    <path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>` +
          `  </svg>` +
          `</button>` +
          `<button class="sidebar-del" title="Delete" data-id="${conversation.id}">` +
          `  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">` +
          `    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>` +
          `  </svg>` +
          `</button>`;
        item.addEventListener("click", (event) => {
          if (event.target.closest(".sidebar-del") || event.target.closest(".sidebar-edit")) {
            return;
          }
          if (conversation.id !== currentConvId) {
            openConversation(conversation.id);
            closeSidebarOnMobile();
          }
        });
        item.querySelector(".sidebar-edit").addEventListener("click", (event) => {
          event.stopPropagation();
          startSidebarRename(conversation, item);
        });
        item.querySelector(".sidebar-del").addEventListener("click", (event) => {
          event.stopPropagation();
          if (!window.confirm("Are you sure you want to delete this conversation?")) {
            return;
          }
          deleteConversation(conversation.id);
        });
        items.appendChild(item);
      });

      section.appendChild(items);
      sidebarList.appendChild(section);
    });
  } catch (error) {
    if (sidebarList.childElementCount === 0) {
      sidebarList.innerHTML = '<p class="sidebar-empty">Could not load conversations.</p>';
    }
  }
}

function updateConversationTitleInState(conversationId, title) {
  const normalizedTitle = String(title || "New Chat").trim() || "New Chat";
  if (Number(conversationId) === Number(currentConvId)) {
    currentConvTitle = normalizedTitle;
    updateExportPanel();
  }
}

function cancelSidebarRename() {
  if (!activeSidebarRename) {
    return;
  }

  const { item, originalTitle } = activeSidebarRename;
  const titleInput = item.querySelector(".sidebar-title-input");
  if (titleInput) {
    titleInput.replaceWith(createSidebarTitleSpan(originalTitle));
  }
  item.classList.remove("editing");
  activeSidebarRename = null;
}

function createSidebarTitleSpan(title) {
  const span = document.createElement("span");
  span.className = "sidebar-title";
  span.textContent = String(title || "New Chat").trim() || "New Chat";
  return span;
}

function startSidebarRename(conversation, item) {
  if (!conversation || !item) {
    return;
  }

  if (activeSidebarRename && activeSidebarRename.item !== item) {
    cancelSidebarRename();
  }

  const titleNode = item.querySelector(".sidebar-title");
  if (!titleNode || item.querySelector(".sidebar-title-input")) {
    return;
  }

  const originalTitle = String(conversation.title || "New Chat").trim() || "New Chat";
  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.className = "sidebar-title-input";
  titleInput.value = originalTitle;
  titleInput.spellcheck = false;
  titleInput.autocomplete = "off";
  titleInput.setAttribute("aria-label", "Rename conversation");

  item.classList.add("editing");
  titleNode.replaceWith(titleInput);
  activeSidebarRename = {
    item,
    conversationId: conversation.id,
    originalTitle,
    committing: false,
  };

  const submitRename = async () => {
    if (!activeSidebarRename || activeSidebarRename.item !== item || activeSidebarRename.committing) {
      return;
    }

    const nextTitle = titleInput.value.trim();
    if (!nextTitle) {
      cancelSidebarRename();
      return;
    }

    activeSidebarRename.committing = true;
    try {
      const response = await fetch(`/api/conversations/${conversation.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: nextTitle }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || "Unable to rename conversation.");
      }

      updateConversationTitleInState(conversation.id, data.title || nextTitle);
      activeSidebarRename = null;
      await loadSidebar();
    } catch (error) {
      activeSidebarRename = null;
      showError(error.message || "Unable to rename conversation.");
      await loadSidebar();
    }
  };

  const cancelRename = () => {
    if (!activeSidebarRename || activeSidebarRename.item !== item || activeSidebarRename.committing) {
      return;
    }
    cancelSidebarRename();
  };

  titleInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submitRename();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelRename();
    }
  });
  titleInput.addEventListener("blur", () => {
    window.setTimeout(cancelRename, 0);
  });

  titleInput.focus();
  titleInput.select();
}

function parseConversationUpdatedAt(value) {
  const date = new Date(String(value || "").trim());
  return Number.isNaN(date.getTime()) ? null : date;
}

function getConversationSectionKey(updatedAt) {
  const date = parseConversationUpdatedAt(updatedAt);
  if (!date) {
    return "older";
  }

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const targetDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((today.getTime() - targetDay.getTime()) / 86400000);

  if (diffDays <= 0) {
    return "today";
  }
  if (diffDays === 1) {
    return "yesterday";
  }
  if (diffDays < 7) {
    return "week";
  }
  if (date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth()) {
    return "month";
  }
  return "older";
}

function buildConversationSidebarSections(conversations) {
  const order = ["today", "yesterday", "week", "month", "older"];
  const labels = {
    today: "Today",
    yesterday: "Yesterday",
    week: "This Week",
    month: "This Month",
    older: "Earlier",
  };
  const grouped = new Map(order.map((key) => [key, []]));

  (Array.isArray(conversations) ? conversations : []).forEach((conversation) => {
    const key = getConversationSectionKey(conversation?.updated_at);
    grouped.get(key)?.push(conversation);
  });

  return order
    .map((key) => ({ label: labels[key], conversations: grouped.get(key) || [] }))
    .filter((entry) => entry.conversations.length > 0);
}

async function openConversation(id) {
  const response = await fetch(`/api/conversations/${id}`);
  const data = await response.json();
  if (!response.ok) {
    return;
  }

  clearPendingDeleteMessage({ render: false });
  resetTokenStats();
  history = [];
  latestSummaryStatus = null;
  userScrolledUp = false;
  currentConvId = id;
  currentConvTitle = String(data.conversation?.title || "New Chat").trim() || "New Chat";
  currentConversationPersonaId = normalizePersonaId(data.conversation?.persona_id);
  syncPersonaSelectors(currentConversationPersonaId);
  const conversationModelId = String(data.conversation?.model || "").trim();
  const nextModelId = resolvePreferredModelSelection(conversationModelId);
  if (nextModelId) {
    const nextModelLabel = nextModelId === conversationModelId
      ? (data.conversation.model_label || "")
      : getKnownModelLabel(nextModelId);
    syncModelSelectors(nextModelId, nextModelLabel);
  }
  clearEditTarget();
  clearInlineEditingTarget();
  resetCanvasWorkspaceState();

  history = Array.isArray(data.messages) ? data.messages.map(normalizeHistoryEntry) : [];
  applyConversationMemoryState(data);
  streamingCanvasDocuments = [];
  resetStreamingCanvasPreview();
  activeCanvasDocumentId = getActiveCanvasDocument(history)?.id || null;
  lastConversationSignature = getConversationSignature(history);
  renderConversationHistory();
  renderCanvasPanel();
  updateExportPanel();
  rebuildTokenStatsFromHistory();

  loadSidebar();
  scrollToBottom();
  inputEl.focus();
}

async function deleteConversation(id) {
  try {
    await fetch(`/api/conversations/${id}`, { method: "DELETE" });
    if (id === currentConvId) {
      startNewChat();
    } else {
      loadSidebar();
    }
  } catch (error) {
    showError("Could not delete conversation.");
  }
}

function startNewChat() {
  clearPendingDeleteMessage({ render: false });
  conversationRefreshGeneration += 1;
  pendingConversationRefreshTimers.forEach((timerId) => window.clearTimeout(timerId));
  pendingConversationRefreshTimers.clear();
  userScrolledUp = false;
  currentConvId = null;
  currentConvTitle = "New Chat";
  currentConversationPersonaId = "";
  history = [];
  conversationMemoryEntries = [];
  conversationMemoryEnabled = featureFlags.conversation_memory_enabled !== false;
  latestSummaryStatus = null;
  streamingCanvasDocuments = [];
  resetStreamingCanvasPreview();
  activeCanvasDocumentId = null;
  lastConversationSignature = "";
  lastConversationMemorySignature = "";
  clearEditTarget();
  clearInlineEditingTarget();
  resetCanvasWorkspaceState();
  clearSelectedImage();
  resetTokenStats();
  renderConversationHistory();
  renderCanvasPanel();
  renderConversationMemoryPanel();
  updateExportPanel();
  const preferredModelId = resolvePreferredModelSelection(modelSel ? modelSel.value : "");
  if (preferredModelId) {
    syncModelSelectors(preferredModelId, getKnownModelLabel(preferredModelId));
  }
  syncPersonaSelectors(currentConversationPersonaId);
  clearToastRegion();
  loadSidebar();
  inputEl.focus();
  closeSidebarOnMobile();
}

function escHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const TOOL_UI_CONFIG = {
  search_knowledge_base: {
    icon: "🧠",
    label: "Knowledge Base",
    runningTitle: "Searching knowledge base",
    doneTitle: "Knowledge results ready",
    errorTitle: "Knowledge search failed",
    fallbackDetail: "Looking through indexed context and synced chat memory.",
  },
  search_web: {
    icon: "🔎",
    label: "Web Search",
    runningTitle: "Searching the web",
    doneTitle: "Web results ready",
    errorTitle: "Web search failed",
    fallbackDetail: "Collecting live sources from the open web.",
  },
  fetch_url: {
    icon: "🌐",
    label: "Web Fetch",
    runningTitle: "Reading page",
    doneTitle: "Page content extracted",
    errorTitle: "Page read failed",
    fallbackDetail: "Opening the source and extracting readable content.",
  },
  search_news_ddgs: {
    icon: "📰",
    label: "News Search",
    runningTitle: "Scanning news sources",
    doneTitle: "News results ready",
    errorTitle: "News search failed",
    fallbackDetail: "Checking recent headlines and source coverage.",
  },
  search_news_google: {
    icon: "🗞️",
    label: "Google News",
    runningTitle: "Scanning Google News",
    doneTitle: "Google News results ready",
    errorTitle: "Google News search failed",
    fallbackDetail: "Checking recent headlines and publisher coverage.",
  },
};

function getToolUiConfig(toolName) {
  return TOOL_UI_CONFIG[toolName] || {
    icon: "⚙️",
    label: "Tool",
    runningTitle: "Running tool",
    doneTitle: "Tool completed",
    errorTitle: "Tool failed",
    fallbackDetail: "Processing tool call.",
  };
}

function formatToolDuration(durationMs) {
  if (!Number.isFinite(durationMs) || durationMs < 0) {
    return "";
  }
  if (durationMs < 1000) {
    return `${Math.max(1, Math.round(durationMs))} ms`;
  }
  if (durationMs < 10_000) {
    return `${(durationMs / 1000).toFixed(1)} s`;
  }
  return `${Math.round(durationMs / 1000)} s`;
}

function extractHost(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  try {
    return new URL(text).hostname.replace(/^www\./i, "");
  } catch (_) {
    return "";
  }
}

function normalizeToolSummary(summary) {
  const raw = String(summary || "").trim();
  if (!raw) {
    return { text: "", cached: false, isError: false };
  }

  const cached = /\(cached\)$/i.test(raw);
  const withoutCached = raw.replace(/\s*\(cached\)$/i, "").trim();
  const isError = /^error:/i.test(withoutCached) || /^failed:/i.test(withoutCached) || /^[^:]{0,120}\bfailed:\s*/i.test(withoutCached);
  const text = isError ? withoutCached.replace(/^error:\s*/i, "").trim() : withoutCached;
  return { text, cached, isError };
}

function buildToolMeta(toolName, preview, options = {}) {
  const meta = [];
  const detail = String(preview || "").trim();
  const { cached = false, durationMs = null } = options;

  if (toolName === "fetch_url") {
    const host = extractHost(detail);
    if (host) {
      meta.push(host);
    }
    if (detail) {
      meta.push("URL");
    }
  } else if (["search_web", "search_news_ddgs", "search_news_google"].includes(toolName) && detail) {
    const queryCount = detail
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean).length;
    if (queryCount > 0) {
      meta.push(`${queryCount} quer${queryCount === 1 ? "y" : "ies"}`);
    }
  } else if (toolName === "search_knowledge_base") {
    meta.push("semantic retrieval");
  }

  if (cached) {
    meta.push("cached");
  }

  const durationText = formatToolDuration(durationMs);
  if (durationText) {
    meta.push(durationText);
  }

  return meta;
}

function ensureToolStepSection(stepLog, stepSections, step, maxSteps) {
  const stepKey = String(step || 1);
  if (stepSections[stepKey]) {
    return stepSections[stepKey];
  }

  const section = document.createElement("section");
  section.className = "step-section";

  const header = document.createElement("div");
  header.className = "step-section-header";

  const title = document.createElement("div");
  title.className = "step-section-title";
  title.textContent = `Step ${stepKey}`;

  const caption = document.createElement("div");
  caption.className = "step-section-caption";
  caption.textContent = maxSteps ? `Tool round ${stepKey}/${maxSteps}` : "Tool round";

  header.appendChild(title);
  header.appendChild(caption);

  const items = document.createElement("div");
  items.className = "step-section-items";

  section.appendChild(header);
  section.appendChild(items);
  stepLog.appendChild(section);

  stepSections[stepKey] = items;
  return items;
}

function createToolStepItem(toolName) {
  const config = getToolUiConfig(toolName);
  const item = document.createElement("details");
  item.className = "step-item step-running";
  item.open = true;
  item.innerHTML = [
    '<summary class="step-item-summary">',
    '  <div class="step-item-icon"></div>',
    '  <div class="step-item-body">',
    '    <div class="step-item-top">',
    '      <span class="step-status-badge"></span>',
    '      <span class="step-item-label"></span>',
    '      <span class="step-time"></span>',
    "    </div>",
    '    <div class="step-title"></div>',
    "  </div>",
    "</summary>",
    '<div class="step-item-content">',
    '  <div class="step-detail"></div>',
    '  <div class="step-meta"></div>',
    '  <div class="step-summary"></div>',
    "</div>",
  ].join("");
  item.querySelector(".step-item-icon").textContent = config.icon;
  return item;
}

function setToolStepState(item, payload) {
  const config = getToolUiConfig(payload.toolName);
  const state = payload.state || "running";
  const preview = String(payload.preview || "").trim();
  const durationMs = Number.isFinite(payload.durationMs) ? payload.durationMs : null;
  const metaItems = buildToolMeta(payload.toolName, preview, {
    cached: Boolean(payload.cached),
    durationMs,
  });

  item.classList.remove("step-running", "step-done", "step-error");
  item.classList.add(`step-${state}`);
  item.open = state !== "done";

  const badge = item.querySelector(".step-status-badge");
  const label = item.querySelector(".step-item-label");
  const time = item.querySelector(".step-time");
  const title = item.querySelector(".step-title");
  const detail = item.querySelector(".step-detail");
  const meta = item.querySelector(".step-meta");
  const summary = item.querySelector(".step-summary");
  const icon = item.querySelector(".step-item-icon");

  badge.textContent = state === "running" ? "Running" : state === "error" ? "Failed" : payload.cached ? "Cached" : "Done";
  label.textContent = config.label;
  time.textContent = state === "running" ? "" : formatToolDuration(durationMs);
  title.textContent = state === "running" ? config.runningTitle : state === "error" ? config.errorTitle : config.doneTitle;

  const detailText = preview || config.fallbackDetail;
  detail.textContent = detailText;
  detail.style.display = detailText ? "" : "none";

  meta.innerHTML = metaItems.map((value) => `<span class="step-chip">${escHtml(value)}</span>`).join("");
  meta.style.display = metaItems.length ? "" : "none";

  summary.textContent = String(payload.summary || "").trim();
  summary.style.display = summary.textContent ? "" : "none";

  icon.textContent = config.icon;
  item.dataset.state = state;
}

newChatBtn.addEventListener("click", startNewChat);

function autoResize(element) {
  element.style.height = "auto";
  element.style.height = element.scrollHeight + "px";
}
inputEl.addEventListener("input", () => {
  if (pendingDeleteMessageId !== null) {
    clearPendingDeleteMessage({ preserveScroll: true });
  }
  autoResize(inputEl);
});

messagesEl.addEventListener("scroll", () => {
  if (!isStreaming) {
    return;
  }
  const distanceFromBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight;
  userScrolledUp = distanceFromBottom > 100;
});

if (summaryNowBtn) {
  summaryNowBtn.addEventListener("click", () => {
    void runConversationSummary({ triggerButton: summaryNowBtn, closePanel: false });
  });
}

if (summaryUndoBtn) {
  summaryUndoBtn.addEventListener("click", () => {
    const latestSummary = findLatestSummaryEntry(history);
    void undoConversationSummary(Number(latestSummary?.id || 0), { triggerButton: summaryUndoBtn });
  });
}

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    if ("ontouchstart" in window || navigator.maxTouchPoints > 0) return;
    event.preventDefault();
    if (!isStreaming && !isFixing) {
      sendMessage();
    }
  }
});

cancelBtn.addEventListener("click", () => {
  if (activeAbortController) {
    activeAbortController.abort();
  }
  clearEmptyAssistantStreamingBubble();
  scrollToBottom();
});

editBannerCancelBtn.addEventListener("click", () => {
  clearEditTarget();
  inputEl.focus();
});

sendBtn.addEventListener("click", () => {
  if (!isStreaming && !isFixing) {
    sendMessage();
  }
});
messagesEl.addEventListener("click", (event) => {
  const button = event.target.closest(".code-copy-btn");
  if (!(button instanceof HTMLButtonElement)) {
    return;
  }
  event.preventDefault();
  void copyCodeBlock(button);
});
canvasDocumentEl?.addEventListener("click", (event) => {
  const button = event.target.closest(".code-copy-btn");
  if (!(button instanceof HTMLButtonElement)) {
    return;
  }
  event.preventDefault();
  void copyCodeBlock(button);
});
fixBtn.addEventListener("click", () => {
  if (!isStreaming && !isFixing) {
    fixMessage();
  }
});
attachBtn.addEventListener("click", () => {
  if (isStreaming || isFixing) return;
  imageInputEl.click();
});

attachBtn.addEventListener("contextmenu", (e) => {
  if (isStreaming || isFixing) return;
  e.preventDefault();
  docInputEl.click();
});
kbSyncBtn?.addEventListener("click", syncKnowledgeBaseConversations);

imageInputEl.addEventListener("change", () => {
  const files = Array.from(imageInputEl.files || []);
  imageInputEl.value = "";
  if (!files.length) {
    return;
  }
  handleSelectedFiles(files);
});

docInputEl.addEventListener("change", () => {
  const files = Array.from(docInputEl.files || []);
  docInputEl.value = "";
  if (!files.length) return;
  handleSelectedFiles(files, { documentsOnly: true });
});

function extractYouTubeVideoIdFromUrl(value) {
  try {
    const url = new URL(String(value || "").trim());
    const host = url.hostname.toLowerCase();
    if (host === "youtu.be" || host === "www.youtu.be") {
      const candidate = url.pathname.replace(/^\//, "").split("/", 1)[0];
      return /^[A-Za-z0-9_-]{11}$/.test(candidate) ? candidate : "";
    }
    if (!["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"].includes(host)) {
      return "";
    }
    if (url.pathname === "/watch") {
      const candidate = url.searchParams.get("v") || "";
      return /^[A-Za-z0-9_-]{11}$/.test(candidate) ? candidate : "";
    }
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts.length >= 2 && ["shorts", "embed", "live"].includes(parts[0])) {
      return /^[A-Za-z0-9_-]{11}$/.test(parts[1]) ? parts[1] : "";
    }
  } catch (_error) {
    return "";
  }
  return "";
}

function normalizeYouTubeUrlInput(value) {
  const videoId = extractYouTubeVideoIdFromUrl(value);
  return videoId ? `https://www.youtube.com/watch?v=${videoId}` : "";
}

function promptForYouTubeUrl() {
  const initialValue = selectedYouTubeUrl || "https://www.youtube.com/watch?v=";
  const nextValue = window.prompt("Paste a YouTube video URL", initialValue);
  if (nextValue === null) {
    return;
  }
  const normalizedUrl = normalizeYouTubeUrlInput(nextValue);
  if (!normalizedUrl) {
    showError("Enter a valid YouTube URL.");
    return;
  }
  selectedYouTubeUrl = normalizedUrl;
  renderAttachmentPreview();
}

youtubeUrlBtn?.addEventListener("click", () => {
  if (isStreaming || isFixing) return;
  if (!Boolean(featureFlags.youtube_transcripts_enabled)) {
    showError("YouTube transcript feature is disabled in .env.");
    return;
  }
  promptForYouTubeUrl();
});

function setChatDropOverlayVisible(visible) {
  if (!chatAreaEl || !chatDropOverlay) {
    return;
  }
  chatAreaEl.classList.toggle("chat-area--dragover", visible);
  chatDropOverlay.hidden = !visible;
}

function resetChatDragState() {
  chatDragDepth = 0;
  setChatDropOverlayVisible(false);
}

function handleChatDragEnter(event) {
  if (isStreaming || isFixing || !hasDraggedFiles(event.dataTransfer)) {
    return;
  }
  event.preventDefault();
  chatDragDepth += 1;
  setChatDropOverlayVisible(true);
}

function handleChatDragOver(event) {
  if (isStreaming || isFixing || !hasDraggedFiles(event.dataTransfer)) {
    return;
  }
  event.preventDefault();
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = "copy";
  }
  setChatDropOverlayVisible(true);
}

function handleChatDragLeave(event) {
  if (!hasDraggedFiles(event.dataTransfer)) {
    return;
  }
  event.preventDefault();
  chatDragDepth = Math.max(0, chatDragDepth - 1);
  if (chatDragDepth === 0) {
    setChatDropOverlayVisible(false);
  }
}

function handleChatDrop(event) {
  if (isStreaming || isFixing || !hasDraggedFiles(event.dataTransfer)) {
    return;
  }
  event.preventDefault();
  const files = Array.from(event.dataTransfer?.files || []);
  resetChatDragState();
  if (!files.length) {
    return;
  }
  handleSelectedFiles(files);
}

chatAreaEl?.addEventListener("dragenter", handleChatDragEnter);
chatAreaEl?.addEventListener("dragover", handleChatDragOver);
chatAreaEl?.addEventListener("dragleave", handleChatDragLeave);
chatAreaEl?.addEventListener("drop", handleChatDrop);
window.addEventListener("drop", resetChatDragState);
window.addEventListener("dragend", resetChatDragState);

function handleSelectedFiles(files, options = {}) {
  const documentsOnly = options.documentsOnly === true;
  const nextImages = [...selectedImageFiles];
  const nextDocuments = [...selectedDocumentFiles];

  for (const file of files || []) {
    if (!file) {
      continue;
    }
    if (isDocumentFile(file)) {
      if (file.size > MAX_DOCUMENT_BYTES) {
        showError(`Document ${file.name} is too large. Upload a maximum of 20 MB.`);
        continue;
      }
      nextDocuments.push(file);
      continue;
    }
    if (documentsOnly) {
      showError(`Unsupported document type: ${file.name}`);
      continue;
    }
    if (!featureFlags.image_uploads_enabled) {
      showError("Image uploads are disabled. Only documents can be attached.");
      continue;
    }
    if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
      showError(`Unsupported file type: ${file.name}`);
      continue;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      showError(`Image ${file.name} is too large. Upload a maximum of 10 MB.`);
      continue;
    }
    nextImages.push(file);
  }

  selectedImageFiles = dedupeFiles(nextImages);
  selectedDocumentFiles = dedupeFiles(nextDocuments);
  syncSelectedDocumentSubmissionModes();
  renderAttachmentPreview();
}

function resetTokenStats() {
  tokenTurns.length = 0;
  renderTokenStats();
}

function setStreaming(active) {
  isStreaming = active;
  if (!active) {
    userScrolledUp = false;
  }
  sendBtn.style.display = active ? "none" : "";
  cancelBtn.hidden = !active;
  fixBtn.disabled = active;
  inputEl.disabled = active;
  attachBtn.disabled = active;
  if (youtubeUrlBtn) {
    youtubeUrlBtn.disabled = active;
  }
  if (mobilePruneBtn) {
    mobilePruneBtn.disabled = active;
  }
}

function setFixing(active) {
  isFixing = active;
  sendBtn.disabled = active;
  fixBtn.disabled = active;
  inputEl.disabled = active;
  attachBtn.disabled = active;
  if (youtubeUrlBtn) {
    youtubeUrlBtn.disabled = active;
  }
}

function showToast(message, tone = "error") {
  if (!errorArea) {
    return;
  }

  const toastId = nextToastId;
  nextToastId += 1;

  const toast = document.createElement("div");
  toast.className = "error-toast";
  toast.dataset.tone = String(tone || "error");
  toast.dataset.toastId = String(toastId);
  toast.setAttribute("role", tone === "error" ? "alert" : "status");
  toast.textContent = String(message || "An unexpected event occurred.");
  errorArea.appendChild(toast);

  while (errorArea.childElementCount > 4) {
    const oldestToast = errorArea.firstElementChild;
    if (!(oldestToast instanceof HTMLElement)) {
      break;
    }
    const oldestId = Number(oldestToast.dataset.toastId || 0);
    const oldestTimer = activeToastTimers.get(oldestId);
    if (oldestTimer) {
      window.clearTimeout(oldestTimer);
      activeToastTimers.delete(oldestId);
    }
    oldestToast.remove();
  }

  const timerId = window.setTimeout(() => {
    toast.remove();
    activeToastTimers.delete(toastId);
  }, 5000);
  activeToastTimers.set(toastId, timerId);
}

function clearToastRegion() {
  activeToastTimers.forEach((timerId) => window.clearTimeout(timerId));
  activeToastTimers.clear();
  if (errorArea) {
    errorArea.replaceChildren();
  }
}

function showError(message) {
  showToast(message, "error");
}

function setKbStatus(message, tone = "muted") {
  if (!kbStatusEl) {
    return;
  }
  kbStatusEl.textContent = message;
  kbStatusEl.dataset.tone = tone;
}

async function loadKnowledgeBaseDocuments() {
  if (!kbDocumentsListEl || !kbStatusEl) {
    return;
  }
  if (!Boolean(featureFlags.rag_enabled)) {
    renderKnowledgeBaseDocuments([]);
    setKbStatus("RAG disabled in .env", "warning");
    return;
  }
  try {
    const response = await fetch("/api/rag/documents");
    if (response.status === 410) {
      renderKnowledgeBaseDocuments([]);
      setKbStatus("RAG disabled in .env", "warning");
      return;
    }
    const docs = await response.json();
    renderKnowledgeBaseDocuments(Array.isArray(docs) ? docs : []);
  } catch (_) {
    renderKnowledgeBaseDocuments([]);
  }
}

function renderKnowledgeBaseDocuments(docs) {
  if (!kbDocumentsListEl) {
    return;
  }
  kbDocumentsListEl.innerHTML = "";

  if (!docs.length) {
    kbDocumentsListEl.innerHTML = '<p class="kb-empty">No indexed sources yet.</p>';
    return;
  }

  docs.forEach((doc) => {
    const item = document.createElement("div");
    item.className = "kb-doc-item";

    const meta = document.createElement("div");
    meta.className = "kb-doc-meta";

    const title = document.createElement("div");
    title.className = "kb-doc-title";
    title.textContent = doc.source_name || "Untitled source";

    const sub = document.createElement("div");
    sub.className = "kb-doc-subtitle";
    sub.textContent = `${doc.source_type || "document"} · ${doc.category || "general"} · ${doc.chunk_count || 0} chunks`;

    meta.appendChild(title);
    meta.appendChild(sub);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "kb-doc-delete";
    del.textContent = "Delete";
    del.addEventListener("click", () => deleteKnowledgeBaseDocument(doc.source_key));

    item.appendChild(meta);
    item.appendChild(del);
    kbDocumentsListEl.appendChild(item);
  });
}

async function deleteKnowledgeBaseDocument(sourceKey) {
  if (!sourceKey) {
    return;
  }
  setKbStatus("Deleting source…");
  try {
    const response = await fetch(`/api/rag/documents/${encodeURIComponent(sourceKey)}`, { method: "DELETE" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Delete failed.");
    }
    setKbStatus("Source deleted", "success");
    loadKnowledgeBaseDocuments();
  } catch (error) {
    setKbStatus(error.message, "error");
  }
}

async function syncKnowledgeBaseConversations() {
  if (!kbSyncBtn) {
    return;
  }
  if (!Boolean(featureFlags.rag_enabled)) {
    setKbStatus("RAG disabled in .env", "warning");
    return;
  }
  setKbStatus("Syncing conversations into RAG…");
  if (kbSyncBtn) {
    kbSyncBtn.disabled = true;
  }
  try {
    const response = await fetch("/api/rag/sync-conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Conversation sync failed.");
    }
    setKbStatus(`${data.count || 0} RAG sources synced`, "success");
    loadKnowledgeBaseDocuments();
  } catch (error) {
    setKbStatus(error.message, "error");
  } finally {
    if (kbSyncBtn) {
      kbSyncBtn.disabled = false;
    }
  }
}

function formatFileSize(size) {
  if (!Number.isFinite(size) || size <= 0) {
    return "0 KB";
  }
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function clearSelectedImage() {
  selectedImageFiles = [];
  imageInputEl.value = "";
  renderAttachmentPreview();
}

function clearSelectedDocument() {
  selectedDocumentFiles = [];
  selectedDocumentSubmissionModes = new Map();
  docInputEl.value = "";
  renderAttachmentPreview();
}

function removeSelectedAttachment(kind, fileKey) {
  if (kind === "image") {
    selectedImageFiles = selectedImageFiles.filter((file) => getAttachmentFileKey(file) !== fileKey);
  } else if (kind === "document") {
    selectedDocumentFiles = selectedDocumentFiles.filter((file) => getAttachmentFileKey(file) !== fileKey);
    selectedDocumentSubmissionModes.delete(String(fileKey || ""));
  } else if (kind === "video") {
    selectedYouTubeUrl = "";
  }
  syncSelectedDocumentSubmissionModes();
  renderAttachmentPreview();
}

function clearAllAttachments() {
  selectedImageFiles = [];
  selectedDocumentFiles = [];
  selectedDocumentSubmissionModes = new Map();
  selectedYouTubeUrl = "";
  imageInputEl.value = "";
  docInputEl.value = "";
  renderAttachmentPreview();
}

function describePreferredImageAnalysisMethod() {
  switch (String(appSettings.image_processing_method || "auto").trim().toLowerCase()) {
    case "llm_helper":
      return "Helper LLM description preferred";
    case "llm_direct":
      return "Direct multimodal input preferred";
    case "local_ocr":
      return "Local OCR preferred";
    default:
      return "Auto image analysis";
  }
}

function renderAttachmentPreview() {
  const attachments = [
    ...selectedImageFiles.map((file) => ({ kind: "image", file })),
    ...selectedDocumentFiles.map((file) => ({ kind: "document", file })),
    ...(selectedYouTubeUrl ? [{ kind: "video", url: selectedYouTubeUrl }] : []),
  ];

  if (!attachments.length) {
    attachmentPreviewEl.hidden = true;
    attachmentPreviewEl.innerHTML = "";
    return;
  }

  attachmentPreviewEl.hidden = false;

  attachmentPreviewEl.innerHTML = attachments.map(({ kind, file, url }) => {
    const fileKey = kind === "video" ? String(url || "") : getAttachmentFileKey(file);
    const icon = kind === "image" ? "🖼️" : kind === "video" ? "▶️" : "📄";
    const preferredImageAnalysis = describePreferredImageAnalysisMethod();
    const documentSubmissionMode = kind === "document" ? getDocumentSubmissionMode(file) : null;
    const documentProcessingDescription = documentSubmissionMode === "visual"
      ? `first ${VISUAL_PDF_PAGE_LIMIT} pages as images`
      : "text extraction";
    const description = kind === "image"
      ? `${preferredImageAnalysis} · ${formatFileSize(file.size)}`
      : kind === "video"
        ? "YouTube transcript will be generated locally"
        : `${((file.name || "").split(".").pop() || "FILE").toUpperCase()} document · ${documentSubmissionMode === "visual" ? "visual analysis" : "text extraction"} · ${documentProcessingDescription} · ${formatFileSize(file.size)}`;
    const name = kind === "video" ? String(url || "YouTube video") : file.name;
    const removeLabel = kind === "image" ? "Remove image" : kind === "video" ? "Remove video" : "Remove document";
    return (
      `<div class="attachment-chip">` +
        `<span class="attachment-chip__icon">${icon}</span>` +
        `<span class="attachment-chip__meta">` +
          `<strong>${escHtml(name)}</strong>` +
          `<small>${escHtml(description)}</small>` +
        `</span>` +
        `<button type="button" class="attachment-chip__remove" data-kind="${escHtml(kind)}" data-file-key="${escHtml(fileKey)}" title="${removeLabel}">×</button>` +
      `</div>`
    );
  }).join("");

  attachmentPreviewEl.querySelectorAll(".attachment-chip__remove").forEach((button) => {
    button.addEventListener("click", () => {
      removeSelectedAttachment(button.dataset.kind, button.dataset.fileKey);
    });
  });
}

function appendAttachmentBadge(group, metadata) {
  const attachments = getMessageAttachments(metadata);
  if (!attachments.length) {
    return;
  }

  group.querySelectorAll(".message-attachment").forEach((node) => node.remove());

  attachments.forEach((attachment) => {
    const badge = document.createElement("div");
    badge.className = "message-attachment";
    if (attachment.kind === "document") {
      const fileId = attachment.file_id ? String(attachment.file_id).trim() : "";
      const fileName = String(attachment.file_name || "Document").trim() || "Document";
      const submissionMode = String(attachment.submission_mode || "text").trim().toLowerCase();
      const modeLabel = submissionMode === "visual" ? "visual" : "text";
      const baseLabel = fileId ? `${fileName} · ${fileId}` : fileName;
      const label = `${baseLabel} · ${modeLabel}`;
      badge.innerHTML =
        `<span class="message-attachment__icon">📄</span>` +
        `<span class="message-attachment__name">${escHtml(label)}</span>` +
        `<span class="message-attachment__state">Document uploaded · Canvas</span>`;
      group.appendChild(badge);
      return;
    }

    if (attachment.kind === "video") {
      const videoTitle = String(attachment.video_title || "YouTube video").trim() || "YouTube video";
      const transcriptReady = Boolean(String(attachment.transcript_context_block || "").trim());
      const stateLabel = transcriptReady ? "Transcript ready" : "Video linked";
      badge.innerHTML =
        `<span class="message-attachment__icon">▶️</span>` +
        `<span class="message-attachment__name">${escHtml(videoTitle)}</span>` +
        `<span class="message-attachment__state">${escHtml(stateLabel)}</span>`;
      group.appendChild(badge);
      return;
    }

    const imageName = String(attachment.image_name || "Image").trim() || "Image";
    const summary = String(attachment.vision_summary || "").trim();
    const ocrText = String(attachment.ocr_text || "").trim();
    const keyPoints = Array.isArray(attachment.key_points) ? attachment.key_points.filter(Boolean) : [];
    const hasVisualRead = Boolean((summary && summary !== "Readable text was detected in the image and added to the context.") || keyPoints.length);
    const stateLabel = hasVisualRead ? "Visual context ready" : (ocrText ? "Text extracted" : "Image attached");
    badge.innerHTML =
      `<span class="message-attachment__icon">🖼️</span>` +
      `<span class="message-attachment__name">${escHtml(imageName)}</span>` +
      `<span class="message-attachment__state">${escHtml(stateLabel)}</span>`;
    group.appendChild(badge);
  });
}

function updateAttachmentBadge(group, metadata) {
  appendAttachmentBadge(group, metadata);
}

function isGenericOcrVisionSummary(summary) {
  return String(summary || "").trim() === "Readable text was detected in the image and added to the context.";
}

function formatImageAnalysisMethod(method) {
  switch (String(method || "").trim().toLowerCase()) {
    case "llm_helper":
      return "Helper description";
    case "llm_direct":
      return "Direct multimodal";
    case "local_ocr":
      return "OCR";
    default:
      return "";
  }
}

function buildVisionNoteHtml(metadata) {
  const imageAttachments = getMessageAttachments(metadata).filter((attachment) => attachment.kind === "image");
  if (!imageAttachments.length) {
    return "";
  }

  const hasVisionContent = imageAttachments.some((attachment) => {
    const summary = String(attachment.vision_summary || "").trim();
    const ocrText = String(attachment.ocr_text || "").trim();
    const keyPoints = Array.isArray(attachment.key_points) ? attachment.key_points.filter(Boolean) : [];
    return Boolean(summary || ocrText || keyPoints.length);
  });
  if (!hasVisionContent) {
    return "";
  }

  return imageAttachments.map((attachment, index) => {
    const summary = String(attachment.vision_summary || "").trim();
    const visibleSummary = isGenericOcrVisionSummary(summary) ? "" : summary;
    const keyPoints = Array.isArray(attachment.key_points) ? attachment.key_points.filter(Boolean) : [];
    const ocrText = String(attachment.ocr_text || "").trim();
    const imageName = String(attachment.image_name || `Image ${index + 1}`).trim() || `Image ${index + 1}`;
    const methodLabel = formatImageAnalysisMethod(attachment.analysis_method);
    const eyebrow = visibleSummary || keyPoints.length ? "Visual read" : "Text read";
    const parts = [];

    parts.push(
      `<div class="message-vision-note__header">` +
        `<div class="message-vision-note__heading">` +
          `<span class="message-vision-note__eyebrow">${escHtml(eyebrow)}</span>` +
          `<strong class="message-vision-note__title">${escHtml(imageName)}</strong>` +
        `</div>` +
        (methodLabel ? `<span class="message-vision-note__method">${escHtml(methodLabel)}</span>` : "") +
      `</div>`
    );
    if (visibleSummary) {
      parts.push(`<p class="message-vision-note__summary">${escHtml(visibleSummary)}</p>`);
    }
    if (keyPoints.length) {
      parts.push(
        `<div class="message-vision-note__section">` +
          `<span class="message-vision-note__label">Highlights</span>` +
          `<ul class="message-vision-note__list">` +
            keyPoints.slice(0, 5).map((point) => `<li>${escHtml(String(point))}</li>`).join("") +
          `</ul>` +
        `</div>`
      );
    }
    if (ocrText) {
      parts.push(
        `<div class="message-vision-note__section">` +
          `<span class="message-vision-note__label">Detected text</span>` +
          `<div class="message-vision-note__ocr">${escHtml(ocrText.slice(0, 320))}${ocrText.length > 320 ? "…" : ""}</div>` +
        `</div>`
      );
    }

    return `<section class="message-vision-note__item" data-index="${index}">${parts.join("")}</section>`;
  }).join("");
}

function appendVisionDetails(group, metadata) {
  const noteHtml = buildVisionNoteHtml(metadata);
  if (!noteHtml) {
    return;
  }

  const note = document.createElement("div");
  note.className = "message-vision-note";
  note.innerHTML = noteHtml;
  group.appendChild(note);
}

function updateVisionDetails(group, metadata) {
  const existing = group.querySelector(".message-vision-note");
  const noteHtml = buildVisionNoteHtml(metadata);

  if (!noteHtml) {
    if (existing) {
      existing.remove();
    }
    return;
  }

  if (existing) {
    existing.innerHTML = noteHtml;
    return;
  }

  appendVisionDetails(group, metadata);
}

function getReasoningText(metadata, messageId = null, conversationId = currentConvId) {
  if (!metadata || typeof metadata !== "object") {
    return getAssistantReasoning(conversationId, messageId);
  }

  const reasoningText = String(metadata.reasoning_content || "").trim();
  if (reasoningText) {
    return reasoningText;
  }

  return getAssistantReasoning(conversationId, messageId);
}

function getToolTraceEntries(metadata) {
  if (!metadata || typeof metadata !== "object" || !Array.isArray(metadata.tool_trace)) {
    return [];
  }

  return metadata.tool_trace
    .filter((entry) => entry && typeof entry === "object" && String(entry.tool_name || "").trim())
    .map((entry) => ({
      step: Number.isFinite(Number(entry.step)) ? Math.max(1, Number(entry.step)) : 1,
      tool_name: String(entry.tool_name || "").trim(),
      preview: String(entry.preview || "").trim(),
      summary: String(entry.summary || "").trim(),
      state: ["running", "done", "error"].includes(String(entry.state || "").trim())
        ? String(entry.state || "").trim()
        : "done",
      cached: entry.cached === true,
    }));
}

function setMarkdownBlockContent(element, text) {
  if (!element) {
    return false;
  }

  const normalizedText = String(text || "").trim();
  if (!normalizedText) {
    element.innerHTML = "";
    element.style.display = "none";
    return false;
  }

  element.innerHTML = renderMarkdown(normalizedText);
  element.style.display = "";
  return true;
}

function getSubAgentTaskHeading(text, limit = 160) {
  const normalized = String(text || "")
    .replace(/```[\s\S]*?```/g, " code block ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/[>*_~|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (!normalized) {
    return "Sub-agent";
  }
  if (normalized.length <= limit) {
    return normalized;
  }
  return `${normalized.slice(0, limit).trim()}...`;
}

function shouldShowSubAgentInstructions(taskInstructions, taskHeading) {
  const normalizedInstructions = String(taskInstructions || "").trim();
  const normalizedHeading = String(taskHeading || "").trim();
  if (!normalizedInstructions) {
    return false;
  }
  if (normalizedInstructions !== normalizedHeading) {
    return true;
  }
  return /(^|\n)\s*(#{1,6}\s|[-*+]\s|\d+\.\s|>|\|)|```|`/.test(normalizedInstructions);
}

function getSubAgentTraceEntries(metadata) {
  if (!metadata || typeof metadata !== "object" || !Array.isArray(metadata.sub_agent_traces)) {
    return [];
  }

  return metadata.sub_agent_traces
    .filter((entry) => entry && typeof entry === "object")
    .map((entry) => ({
      task: String(entry.task || "").trim(),
      task_full: String(entry.task_full || "").trim(),
      status: ["running", "ok", "partial", "error"].includes(String(entry.status || "").trim())
        ? String(entry.status || "").trim()
        : "ok",
      summary: String(entry.summary || "").trim(),
      model: String(entry.model || "").trim(),
      error: String(entry.error || "").trim(),
      timed_out: entry.timed_out === true,
      fallback_note: String(entry.fallback_note || "").trim(),
      canvas_saved: entry.canvas_saved === true,
      canvas_document_id: String(entry.canvas_document_id || "").trim(),
      canvas_document_title: String(entry.canvas_document_title || "").trim(),
      artifacts: Array.isArray(entry.artifacts) ? entry.artifacts.filter((artifact) => artifact && typeof artifact === "object") : [],
      tool_trace: getToolTraceEntries({ tool_trace: Array.isArray(entry.tool_trace) ? entry.tool_trace : [] }),
    }))
    .filter((entry) => entry.task || entry.summary || entry.error || entry.fallback_note || entry.tool_trace.length || entry.canvas_saved);
}

function mergeAssistantSubAgentTraceEntry(entries, entry) {
  const normalizedEntries = getSubAgentTraceEntries({ sub_agent_traces: [entry] });
  if (!normalizedEntries.length) {
    return Array.isArray(entries) ? entries : [];
  }

  const nextEntries = Array.isArray(entries) ? [...entries] : [];
  const nextEntry = normalizedEntries[0];
  const lastEntry = nextEntries[nextEntries.length - 1];

  if (lastEntry && lastEntry.status === "running") {
    nextEntries[nextEntries.length - 1] = nextEntry;
    return nextEntries;
  }

  nextEntries.push(nextEntry);
  return nextEntries;
}

function getAssistantFetchIndicator(metadata) {
  if (!metadata || typeof metadata !== "object" || !Array.isArray(metadata.tool_results)) {
    return null;
  }

  const fetchResults = metadata.tool_results.filter(
    (entry) => entry && typeof entry === "object" && entry.tool_name === "fetch_url",
  );
  if (!fetchResults.length) {
    return null;
  }

  const clippedEntry = fetchResults.find((entry) => String(entry.content_mode || "").trim() === "clipped_text");
  if (clippedEntry) {
    return {
      label: fetchResults.length > 1 ? `${fetchResults.length} web sources clipped` : "Web source clipped",
      title: String(clippedEntry.summary_notice || "").trim()
        || "Long fetched content was cleaned and clipped before the model used it.",
      tone: "summary",
    };
  }

  const summarizedEntry = fetchResults.find((entry) => String(entry.content_mode || "").trim() === "rag_summary");
  if (summarizedEntry) {
    return {
      label: fetchResults.length > 1 ? `${fetchResults.length} web sources summarized` : "Web source summarized",
      title: String(summarizedEntry.summary_notice || "").trim()
        || "Long fetched content was cleaned and summarized before the model used it.",
      tone: "summary",
    };
  }

  const cleanedEntry = fetchResults.find((entry) => entry.cleanup_applied === true);
  if (cleanedEntry) {
    return {
      label: fetchResults.length > 1 ? `${fetchResults.length} web sources cleaned` : "Web source cleaned",
      title: "Fetched web content was cleaned before the model used it.",
      tone: "clean",
    };
  }

  return null;
}

function updateAssistantFetchBadge(group, metadata) {
  const indicator = getAssistantFetchIndicator(metadata);
  const existing = group.querySelector(".assistant-context-badge");

  if (!indicator) {
    if (existing) {
      existing.remove();
    }
    return;
  }

  const badge = existing || document.createElement("div");
  badge.className = `assistant-context-badge assistant-context-badge--${indicator.tone}`;
  badge.title = indicator.title;
  badge.innerHTML =
    `<span class="assistant-context-badge__icon">${indicator.tone === "summary" ? "✦" : "🧹"}</span>` +
    `<span class="assistant-context-badge__label">${escHtml(indicator.label)}</span>`;

  if (!existing) {
    const anchor = group.querySelector(".tool-trace-panel") || group.querySelector(".reasoning-panel") || group.querySelector(".bubble");
    if (anchor) {
      group.insertBefore(badge, anchor);
    } else {
      group.appendChild(badge);
    }
  }
}

function updateAssistantToolTrace(group, metadata) {
  const entries = getToolTraceEntries(metadata);
  const existing = group.querySelector(".tool-trace-panel");

  if (!entries.length) {
    if (existing) {
      existing.remove();
    }
    return;
  }

  const panel = existing || document.createElement("section");
  panel.className = "tool-trace-panel";

  const title = document.createElement("div");
  title.className = "tool-trace-panel__title";
  title.textContent = entries.length === 1 ? "Tool used" : `Tools used (${entries.length})`;

  const body = document.createElement("div");
  body.className = "tool-trace-panel__body";

  const sections = {};
  entries.forEach((entry) => {
    const sectionItems = ensureToolStepSection(body, sections, entry.step, null);
    const item = createToolStepItem(entry.tool_name);
    const normalizedSummary = normalizeToolSummary(entry.summary);
    setToolStepState(item, {
      toolName: entry.tool_name,
      preview: entry.preview,
      summary: normalizedSummary.text,
      state: normalizedSummary.isError ? "error" : entry.state || "done",
      cached: entry.cached || normalizedSummary.cached,
    });
    sectionItems.appendChild(item);
  });

  panel.innerHTML = "";
  panel.appendChild(title);
  panel.appendChild(body);

  if (!existing) {
    const anchor = group.querySelector(".reasoning-panel") || group.querySelector(".bubble");
    if (anchor) {
      group.insertBefore(panel, anchor);
    } else {
      group.appendChild(panel);
    }
  }
}

function getSubAgentStatusLabel(entry) {
  if (entry.fallback_note) {
    return "Fallback";
  }
  if (entry.timed_out) {
    return "Timed out";
  }
  if (entry.status === "running") {
    return "Live";
  }
  if (entry.status === "partial") {
    return "Partial";
  }
  if (entry.status === "error") {
    return "Error";
  }
  return "Done";
}

function getLatestUnsavedCompletedSubAgentTrace(metadata) {
  const entries = getSubAgentTraceEntries(metadata);
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index];
    if (!entry || entry.status === "running" || entry.canvas_saved) {
      continue;
    }
    if (entry.status === "error" && !String(entry.summary || "").trim() && !entry.tool_trace.length) {
      continue;
    }
    return { index, entry };
  }
  return null;
}

function getSubAgentCanvasPromptStorageKey(conversationId, assistantMessageId, traceIndex) {
  const normalizedConversationId = String(conversationId || "").trim();
  const normalizedAssistantMessageId = String(assistantMessageId || "").trim();
  const normalizedTraceIndex = Number.isInteger(traceIndex) ? traceIndex : Number.parseInt(traceIndex, 10);
  if (!normalizedConversationId || !normalizedAssistantMessageId || !Number.isInteger(normalizedTraceIndex)) {
    return null;
  }
  return `sub-agent-canvas-prompted:${normalizedConversationId}:${normalizedAssistantMessageId}:${normalizedTraceIndex}`;
}

function hasSubAgentCanvasPromptBeenShown(conversationId, assistantMessageId, traceIndex) {
  const storageKey = getSubAgentCanvasPromptStorageKey(conversationId, assistantMessageId, traceIndex);
  if (!storageKey) {
    return false;
  }
  try {
    return localStorage.getItem(storageKey) === "1";
  } catch (_) {
    return false;
  }
}

function markSubAgentCanvasPromptShown(conversationId, assistantMessageId, traceIndex) {
  const storageKey = getSubAgentCanvasPromptStorageKey(conversationId, assistantMessageId, traceIndex);
  if (!storageKey) {
    return;
  }
  try {
    localStorage.setItem(storageKey, "1");
  } catch (_) {
    // Ignore storage errors.
  }
}

function findPersistedAssistantEntryForSubAgentPrompt(preferredAssistantId = null) {
  const normalizedPreferredId = Number(preferredAssistantId || 0);
  if (!isPersistedMessageId(normalizedPreferredId)) {
    return null;
  }

  for (let index = history.length - 1; index >= 0; index -= 1) {
    const entry = history[index];
    if (!entry || entry.role !== "assistant") {
      continue;
    }
    if (Number(entry.id || 0) !== normalizedPreferredId) {
      continue;
    }
    return getLatestUnsavedCompletedSubAgentTrace(entry.metadata) ? entry : null;
  }

  return null;
}

function buildSubAgentResearchCanvasTitle(entry) {
  const taskInstructions = String(entry?.task_full || entry?.task || "").trim();
  const taskHeading = getSubAgentTaskHeading(taskInstructions || entry?.summary || "Research");
  const normalizedHeading = String(taskHeading || "Research").trim();
  return `Research - ${normalizedHeading}`.slice(0, 120).trim() || "Research";
}

function buildSubAgentResearchCanvasContent(entry) {
  const lines = [`# ${buildSubAgentResearchCanvasTitle(entry)}`, ""];

  const summaryText = String(entry?.summary || "").trim();
  if (summaryText) {
    lines.push("## Summary", "", summaryText, "");
  }

  if (!summaryText) {
    const fallbackNote = String(entry?.fallback_note || "").trim();
    if (fallbackNote) {
      lines.push("## Note", "", fallbackNote, "");
    }

    const errorText = String(entry?.error || "").trim();
    if (!fallbackNote && errorText) {
      lines.push("## Error", "", errorText, "");
    }
  }

  return lines.join("\n").trim();
}

async function saveSubAgentResearchToCanvas(assistantMessageId, traceIndex, traceEntry) {
  if (!currentConvId) {
    showError("Create a conversation first so the research can be saved to Canvas.");
    return;
  }

  const response = await fetch(`/api/conversations/${currentConvId}/canvas`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: buildSubAgentResearchCanvasTitle(traceEntry),
      content: buildSubAgentResearchCanvasContent(traceEntry),
      format: "markdown",
      source_assistant_message_id: assistantMessageId,
      source_sub_agent_trace_index: traceIndex,
      summary: String(traceEntry.summary || "").trim() || null,
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "Research could not be saved to Canvas.");
  }

  history = Array.isArray(payload.messages) ? payload.messages.map(normalizeHistoryEntry) : history;
  streamingCanvasDocuments = [];
  resetStreamingCanvasPreview();
  activeCanvasDocumentId = String(payload.active_document_id || "").trim() || getActiveCanvasDocument(history)?.id || null;
  rebuildTokenStatsFromHistory();
  renderConversationHistory({ preserveScroll: true });
  renderCanvasPanel();
  lastConversationSignature = getConversationSignature(history);
  loadSidebar();
  openCanvas();
  setCanvasStatus("Research saved to Canvas.", "success");
  showToast("Research saved to Canvas.", "success");
}

function maybePromptToSaveSubAgentResearch(assistantEntry) {
  const resolvedEntry = isPersistedMessageId(assistantEntry?.id)
    ? assistantEntry
    : findPersistedAssistantEntryForSubAgentPrompt(assistantEntry?.id);

  if (!resolvedEntry || !isPersistedMessageId(resolvedEntry.id) || !currentConvId) {
    return;
  }

  const pendingTrace = getLatestUnsavedCompletedSubAgentTrace(resolvedEntry.metadata);
  if (!pendingTrace) {
    return;
  }

  if (hasSubAgentCanvasPromptBeenShown(currentConvId, resolvedEntry.id, pendingTrace.index)) {
    return;
  }

  markSubAgentCanvasPromptShown(currentConvId, resolvedEntry.id, pendingTrace.index);

  const taskHeading = getSubAgentTaskHeading(
    String(pendingTrace.entry.task_full || pendingTrace.entry.task || pendingTrace.entry.summary || "Research").trim(),
  );

  openCanvasConfirmModal({
    title: "Should the research be saved to the Canvas?",
    message: `${taskHeading} is ready. If you save it to the Canvas, future turns can rely on the Canvas copy instead of the raw sub-agent research text.`,
    confirmLabel: "Save to Canvas",
    cancelLabel: "Not now",
    onConfirm: async () => {
      try {
        await saveSubAgentResearchToCanvas(resolvedEntry.id, pendingTrace.index, pendingTrace.entry);
      } catch (error) {
        showError(error.message || "Research could not be saved to Canvas.");
      }
    },
  });
}

function createSubAgentStep(traceEntry) {
  const item = document.createElement("div");
  item.className = `sub-agent-step sub-agent-step--${traceEntry.state || "done"}`;

  const top = document.createElement("div");
  top.className = "sub-agent-step__top";

  const label = document.createElement("div");
  label.className = "sub-agent-step__label";
  label.textContent = getToolUiConfig(traceEntry.tool_name).label;

  const state = document.createElement("span");
  state.className = `sub-agent-step__state sub-agent-step__state--${traceEntry.state || "done"}`;
  state.textContent = traceEntry.state === "running"
    ? "Running"
    : traceEntry.state === "error"
      ? "Failed"
      : traceEntry.cached
        ? "Cached"
        : "Done";

  top.append(label, state);
  item.appendChild(top);

  const detailText = String(traceEntry.preview || "").trim();
  if (detailText) {
    const detail = document.createElement("div");
    detail.className = "sub-agent-step__detail sub-agent-markdown";
    setMarkdownBlockContent(detail, detailText);
    item.appendChild(detail);
  }

  const summaryText = String(traceEntry.summary || "").trim();
  if (summaryText && summaryText !== detailText) {
    const summary = document.createElement("div");
    summary.className = "sub-agent-step__summary sub-agent-markdown";
    setMarkdownBlockContent(summary, summaryText);
    item.appendChild(summary);
  }

  return item;
}

function updateAssistantSubAgentTrace(group, metadata) {
  const entries = getSubAgentTraceEntries(metadata);
  const existing = group.querySelector(".sub-agent-trace-panel");

  if (!entries.length) {
    if (existing) {
      existing.remove();
    }
    return;
  }

  const panel = existing || document.createElement("section");
  panel.className = "sub-agent-trace-panel";

  const title = document.createElement("div");
  title.className = "sub-agent-trace-panel__title";
  title.textContent = entries.length === 1 ? "Sub-agent activity" : `Sub-agent activity (${entries.length})`;

  const body = document.createElement("div");
  body.className = "sub-agent-trace-panel__body";

  entries.forEach((entry) => {
    const run = document.createElement("section");
    run.className = `sub-agent-run sub-agent-run--${entry.status}`;

    const header = document.createElement("div");
    header.className = "sub-agent-run__header";

    const task = document.createElement("div");
    task.className = "sub-agent-run__task";
    const taskInstructions = String(entry.task_full || entry.task || "").trim();
    const taskHeading = getSubAgentTaskHeading(taskInstructions || entry.summary || "Sub-agent");
    task.textContent = taskHeading;

    const status = document.createElement("span");
    status.className = `sub-agent-run__status sub-agent-run__status--${entry.status}`;
    status.textContent = getSubAgentStatusLabel(entry);

    header.append(task, status);
    run.appendChild(header);

    if (shouldShowSubAgentInstructions(taskInstructions, taskHeading)) {
      const instructions = document.createElement("details");
      instructions.className = "sub-agent-run__instructions";
      instructions.open = entry.status === "running";

      const instructionsSummary = document.createElement("summary");
      instructionsSummary.className = "sub-agent-run__instructions-summary";
      instructionsSummary.textContent = "Parent instructions";

      const instructionsBody = document.createElement("div");
      instructionsBody.className = "sub-agent-run__instructions-body sub-agent-markdown";
      setMarkdownBlockContent(instructionsBody, taskInstructions);

      instructions.append(instructionsSummary, instructionsBody);
      run.appendChild(instructions);
    }

    const fallbackNote = String(entry.fallback_note || "").trim();
    if (fallbackNote) {
      const note = document.createElement("div");
      note.className = "sub-agent-run__note sub-agent-markdown";
      setMarkdownBlockContent(note, fallbackNote);
      run.appendChild(note);
    }

    if (entry.tool_trace.length) {
      const toolTrace = document.createElement("div");
      toolTrace.className = "sub-agent-run__steps";
      entry.tool_trace.forEach((traceEntry) => {
        const normalizedSummary = normalizeToolSummary(traceEntry.summary);
        toolTrace.appendChild(createSubAgentStep({
          ...traceEntry,
          summary: normalizedSummary.text,
          state: normalizedSummary.isError ? "error" : traceEntry.state || "done",
          cached: traceEntry.cached || normalizedSummary.cached,
        }));
      });
      run.appendChild(toolTrace);
    }

    const summaryText = String(entry.summary || "").trim();
    const supportingText = entry.error || ((entry.status !== "ok" || !entry.tool_trace.length) && summaryText && summaryText !== fallbackNote ? entry.summary : "");
    if (supportingText) {
      const message = document.createElement("div");
      message.className = `${entry.error ? "sub-agent-run__error" : "sub-agent-run__result"} sub-agent-markdown`;
      setMarkdownBlockContent(message, supportingText);
      run.appendChild(message);
    }

    if (entry.canvas_saved) {
      const savedNote = document.createElement("div");
      savedNote.className = "sub-agent-run__canvas-note";
      savedNote.textContent = entry.canvas_document_title
        ? `Saved to Canvas as ${entry.canvas_document_title}.`
        : "Saved to Canvas.";
      run.appendChild(savedNote);
    }

    body.appendChild(run);
  });

  panel.innerHTML = "";
  panel.appendChild(title);
  panel.appendChild(body);

  if (!existing) {
    const anchor = group.querySelector(".reasoning-panel") || group.querySelector(".bubble");
    if (anchor) {
      group.insertBefore(panel, anchor);
    } else {
      group.appendChild(panel);
    }
  }
}

function buildReasoningPanel(reasoningText, options = {}) {
  const text = String(reasoningText || "").trim();
  if (!text) {
    return null;
  }

  const renderReasoning = options.streaming === true ? renderStreamingMarkdown : renderMarkdown;

  const details = document.createElement("details");
  details.className = "reasoning-panel";
  details.open = Boolean(options.forceOpen) || !shouldAutoCollapseReasoning();

  const summary = document.createElement("summary");
  summary.textContent = "Reasoning";

  const body = document.createElement("div");
  body.className = "reasoning-body";
  body.innerHTML = renderReasoning(text);

  details.appendChild(summary);
  details.appendChild(body);
  return details;
}

function updateReasoningPanel(group, reasoningText, options = {}) {
  const text = String(reasoningText || "").trim();
  const existing = group.querySelector(".reasoning-panel");
  const renderReasoning = options.streaming === true ? renderStreamingMarkdown : renderMarkdown;

  if (!text) {
    if (existing) {
      existing.remove();
    }
    return;
  }

  if (existing) {
    const body = existing.querySelector(".reasoning-body");
    if (body) {
      body.innerHTML = renderReasoning(text);
    }
    if (options.forceOpen) {
      existing.open = true;
    } else if (options.autoCollapse && shouldAutoCollapseReasoning()) {
      existing.open = false;
    }
    return;
  }

  const panel = buildReasoningPanel(text, options);
  if (!panel) {
    return;
  }

  const bubble = group.querySelector(".bubble");
  if (bubble) {
    group.insertBefore(panel, bubble);
  } else {
    group.appendChild(panel);
  }
}

function appendClarificationPanel(group, metadata, options = {}) {
  const clarification = getPendingClarification(metadata);
  if (!clarification) {
    return;
  }

  const panel = document.createElement("section");
  panel.className = "clarification-card";

  const title = document.createElement("div");
  title.className = "clarification-card__title";
  title.textContent = clarification.questions.length === 1 ? "Clarification needed" : "Clarifications needed";
  panel.appendChild(title);

  const summary = document.createElement("div");
  summary.className = "clarification-card__summary";
  summary.textContent = `${clarification.questions.length} question${clarification.questions.length === 1 ? "" : "s"} to answer`;
  panel.appendChild(summary);

  if (clarification.intro) {
    const intro = document.createElement("div");
    intro.className = "clarification-card__intro";
    intro.textContent = clarification.intro;
    panel.appendChild(intro);
  }

  const isInteractive = Boolean(options.isLatestVisible && Number.isInteger(Number(options.messageId)));
  if (!isInteractive) {
    const state = document.createElement("div");
    state.className = "clarification-card__state";
    state.textContent = "Waiting for a reply in this thread.";
    panel.appendChild(state);
    group.appendChild(panel);
    const bubble = group.querySelector(".bubble");
    if (bubble && !bubble.textContent.trim()) {
      bubble.remove();
    }
    return;
  }

  const form = document.createElement("form");
  form.className = "clarification-form";

  const helper = document.createElement("div");
  helper.className = "clarification-card__helper";
  helper.textContent = "Your draft answers stay in this browser until you send them.";
  form.appendChild(helper);

  clarification.questions.forEach((question, index) => {
    const field = document.createElement("div");
    field.className = "clarification-field";
    field.dataset.questionId = question.id;

    const label = document.createElement("label");
    label.className = "clarification-field__label";
    label.textContent = `${question.required ? "* " : ""}${question.label}`;
    field.appendChild(label);

    const fieldName = `clarify_${index}`;
    const freeTextName = `${fieldName}_free`;

    if (question.input_type === "text") {
      const input = document.createElement("textarea");
      input.name = fieldName;
      input.rows = 2;
      input.placeholder = question.placeholder || "A: Type your answer";
      input.className = "clarification-field__textarea";
      input.addEventListener("input", () => autoResize(input));
      field.appendChild(input);
    } else {
      let optionsSearchInput = null;
      const optionsList = document.createElement("div");
      optionsList.className = "clarification-options";
      const optionEntries = [];
      question.options.forEach((option) => {
        const optionLabel = document.createElement("label");
        optionLabel.className = "clarification-option";

        const input = document.createElement("input");
        input.type = question.input_type === "single_select" ? "radio" : "checkbox";
        input.name = fieldName;
        input.value = option.value;

        const textBlock = document.createElement("span");
        textBlock.className = "clarification-option__text";
        textBlock.innerHTML = `<strong>${escHtml(option.label)}</strong>${option.description ? `<small>${escHtml(option.description)}</small>` : ""}`;

        optionLabel.appendChild(input);
        optionLabel.appendChild(textBlock);
        optionsList.appendChild(optionLabel);
        optionEntries.push({
          element: optionLabel,
          searchText: `${option.label} ${option.description || ""}`.toLowerCase(),
        });
      });

      if (question.options.length > 5) {
        optionsSearchInput = document.createElement("input");
        optionsSearchInput.type = "search";
        optionsSearchInput.className = "clarification-field__input clarification-options__search";
        optionsSearchInput.placeholder = "Filter options";
        field.appendChild(optionsSearchInput);

        const emptyState = document.createElement("div");
        emptyState.className = "clarification-options__empty";
        emptyState.textContent = "No matching options.";
        emptyState.hidden = true;

        const applyOptionFilter = () => {
          const query = String(optionsSearchInput.value || "").trim().toLowerCase();
          let visibleCount = 0;
          optionEntries.forEach((entry) => {
            const matches = !query || entry.searchText.includes(query);
            entry.element.hidden = !matches;
            if (matches) {
              visibleCount += 1;
            }
          });
          emptyState.hidden = visibleCount > 0;
        };

        optionsSearchInput.addEventListener("input", applyOptionFilter);
        field.appendChild(optionsList);
        field.appendChild(emptyState);
        applyOptionFilter();
      } else {
        field.appendChild(optionsList);
      }

      if (question.allow_free_text) {
        const freeTextInput = document.createElement("input");
        freeTextInput.type = "text";
        freeTextInput.name = freeTextName;
        freeTextInput.className = "clarification-field__input";
        freeTextInput.placeholder = question.placeholder || "A: Add details if needed";
        field.appendChild(freeTextInput);
      }
    }

    form.appendChild(field);
  });

  applyClarificationDraft(form, clarification, loadClarificationDraft(options.messageId));

  const syncClarificationFormState = () => {
    updateClarificationFieldVisibility(form, clarification);
    saveClarificationDraft(options.messageId, collectClarificationDraft(form, clarification));
  };

  updateClarificationFieldVisibility(form, clarification);

  form.addEventListener("input", () => {
    syncClarificationFormState();
  });

  form.addEventListener("change", () => {
    syncClarificationFormState();
  });

  const error = document.createElement("div");
  error.className = "clarification-form__error";
  error.hidden = true;
  form.appendChild(error);

  const submitButton = document.createElement("button");
  submitButton.type = "submit";
  submitButton.className = "msg-action-btn clarification-form__submit";
  submitButton.textContent = clarification.submit_label;
  form.appendChild(submitButton);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isStreaming || isFixing) {
      return;
    }

    const collected = collectClarificationAnswers(form, clarification);
    if (collected.error) {
      error.hidden = false;
      error.textContent = collected.error;
      return;
    }

    error.hidden = true;
    const draft = collectClarificationDraft(form, clarification);
    saveClarificationDraft(options.messageId, draft);
    submitButton.disabled = true;
    try {
      const result = await sendMessage({
        forcedText: collected.text,
        forcedMetadata: {
          clarification_response: {
            assistant_message_id: Number(options.messageId),
            answers: collected.answers,
          },
        },
      });

      if (result?.ok) {
        saveClarificationDraft(options.messageId, null);
        return;
      }

      if (result?.errorCode === "stale_clarification_response") {
        const latestPendingMessageId = findLatestPendingClarificationMessageId();
        if (Number.isInteger(latestPendingMessageId) && latestPendingMessageId !== Number(options.messageId)) {
          saveClarificationDraft(latestPendingMessageId, draft);
          renderConversationHistory({ preserveScroll: true });
        }
      }
    } finally {
      submitButton.disabled = false;
    }
  });

  panel.appendChild(form);
  group.appendChild(panel);
  const bubble = group.querySelector(".bubble");
  if (bubble && !bubble.textContent.trim()) {
    bubble.remove();
  }
}

function createMessageGroup(role, text, metadata = null, options = {}) {
  emptyState.style.display = "none";

  const group = document.createElement("div");
  group.className = `msg-group ${role}`;
  if (Number.isInteger(Number(options.messageId))) {
    group.dataset.messageId = String(options.messageId);
  }
  if (options.isEditingTarget) {
    group.classList.add("editing-target");
  }
  if (options.isInlineEditingTarget) {
    group.classList.add("inline-editing-target");
  }

  const metaRow = document.createElement("div");
  metaRow.className = "msg-meta-row";

  const normalizedMetadata = metadata && typeof metadata === "object" ? metadata : null;
  const labelGroup = document.createElement("div");
  labelGroup.className = "msg-meta-label-group";

  const label = document.createElement("div");
  label.className = "msg-label";
  label.textContent = role === "user" ? "You" : role === "summary" ? "Summary" : "Assistant";

  labelGroup.appendChild(label);
  if (role === "summary" && normalizedMetadata?.is_summary) {
    const coveredCount = Number(normalizedMetadata.covered_message_count || 0);
    const generatedAt = formatSummaryTimestamp(normalizedMetadata.generated_at);
    const sourceLabel = SUMMARY_SOURCE_LABELS[String(normalizedMetadata.summary_source || "").trim()] || "Conversation history";
    const formatLabel = String(normalizedMetadata.summary_format || "").trim() === "structured_json"
      ? "Structured"
      : "Plain text";
    const summaryMetaParts = [];
    if (coveredCount > 0) {
      summaryMetaParts.push(`${coveredCount} msgs`);
    }
    summaryMetaParts.push(sourceLabel);
    summaryMetaParts.push(formatLabel);
    if (generatedAt && generatedAt !== "—") {
      summaryMetaParts.push(generatedAt);
    }
    if (normalizedMetadata.covered_ids_truncated === true) {
      summaryMetaParts.push("ID list truncated");
    }
    const summaryMeta = document.createElement("span");
    summaryMeta.className = "summary-inline-meta";
    summaryMeta.textContent = summaryMetaParts.join(" • ");
    labelGroup.appendChild(summaryMeta);
  }
  if (normalizedMetadata?.is_pruned === true) {
    const prunedBadge = document.createElement("span");
    prunedBadge.className = "pruned-badge";
    prunedBadge.textContent = "Pruned";
    labelGroup.appendChild(prunedBadge);
  }

  metaRow.appendChild(labelGroup);

  let summaryToggleButton = null;
  let summaryUndoButton = null;
  if (role === "summary" && normalizedMetadata?.is_summary) {
    const summaryActions = document.createElement("div");
    summaryActions.className = "msg-actions";

    summaryToggleButton = document.createElement("button");
    summaryToggleButton.type = "button";
    summaryToggleButton.className = "msg-action-btn msg-action-btn--with-label";
    summaryToggleButton.textContent = "Show summary";

    summaryUndoButton = document.createElement("button");
    summaryUndoButton.type = "button";
    summaryUndoButton.className = "msg-action-btn msg-action-btn--with-label";
    summaryUndoButton.textContent = "Undo";
    const canUndoSummary = Number.isInteger(Number(options.messageId)) && Number(options.messageId) > 0 && Boolean(currentConvId);
    summaryUndoButton.disabled = isSummaryOperationInFlight || !canUndoSummary;
    summaryUndoButton.addEventListener("click", () => {
      void undoConversationSummary(Number(options.messageId || 0), { triggerButton: summaryUndoButton });
    });

    summaryActions.append(summaryToggleButton, summaryUndoButton);
    metaRow.appendChild(summaryActions);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const attachments = getMessageAttachments(metadata);
  const hasImage = attachments.some((attachment) => attachment.kind === "image");
  const hasDocument = attachments.some((attachment) => attachment.kind === "document");
  const displayText = text || (attachments.length ? "Attachments uploaded." : hasImage ? "Image uploaded." : hasDocument ? "Document uploaded." : "");
  const pendingClarification = role === "assistant" ? getPendingClarification(normalizedMetadata) : null;
  const footerActions = createMessageActions(
    {
      id: options.messageId,
      role,
      content: text,
      metadata: normalizedMetadata,
      tool_calls: Array.isArray(options.toolCalls) ? options.toolCalls : [],
    },
    options,
  );

  group.appendChild(metaRow);
  if (role === "assistant") {
    updateAssistantFetchBadge(group, metadata);
    updateAssistantToolTrace(group, metadata);
    updateAssistantSubAgentTrace(group, metadata);
    updateReasoningPanel(group, getReasoningText(metadata, options.messageId));
  }

  if (options.isInlineEditingTarget) {
    group.appendChild(createInlineMessageEditor({
      id: options.messageId,
      role,
      content: text,
      metadata: normalizedMetadata,
      tool_calls: Array.isArray(options.toolCalls) ? options.toolCalls : [],
    }));
  } else {
    if ((role === "assistant" || role === "summary") && text !== "Working…") {
      bubble.innerHTML = renderMarkdown(text);
    } else {
      bubble.textContent = displayText;
    }
    if (displayText) {
      if (role === "summary") {
        bubble.classList.add("summary-inline-body");
        bubble.hidden = true;
      }
      group.appendChild(bubble);
    }
  }

  if (summaryToggleButton) {
    const canToggleSummary = Boolean(displayText);
    summaryToggleButton.disabled = !canToggleSummary;
    const syncSummaryToggleLabel = () => {
      summaryToggleButton.textContent = bubble.hidden ? "Show summary" : "Hide summary";
    };
    syncSummaryToggleLabel();
    if (canToggleSummary) {
      summaryToggleButton.addEventListener("click", () => {
        bubble.hidden = !bubble.hidden;
        syncSummaryToggleLabel();
        if (!bubble.hidden) {
          scrollToBottom();
        }
      });
    }
  }

  if (role === "assistant" && !options.isInlineEditingTarget) {
    appendClarificationPanel(group, metadata, options);
  }
  if (role === "user" && attachments.length) {
    appendAttachmentBadge(group, metadata);
    if (hasImage) {
      appendVisionDetails(group, metadata);
    }
  }
  if (!options.isInlineEditingTarget && footerActions) {
    group.appendChild(footerActions);
  }
  return group;
}

function appendGroup(role, text, metadata = null, options = {}) {
  const group = createMessageGroup(role, text, metadata, options);
  messagesEl.appendChild(group);
  scrollToBottom();
  return group;
}

let scrollToBottomFrame = null;

function scrollToBottom() {
  if (userScrolledUp) {
    return;
  }
  if (scrollToBottomFrame !== null) {
    return;
  }

  const flushScroll = () => {
    scrollToBottomFrame = null;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
    scrollToBottomFrame = window.requestAnimationFrame(flushScroll);
    return;
  }

  scrollToBottomFrame = window.setTimeout(flushScroll, 16);
}

async function fixMessage() {
  const text = inputEl.value.trim();
  if (!text) {
    return;
  }

  clearToastRegion();
  setFixing(true);

  try {
    const response = await fetch("/api/fix-text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    const data = await response.json().catch(() => ({ error: "An unexpected error occurred." }));
    if (!response.ok) {
      throw new Error(data.error || "An unexpected error occurred.");
    }

    inputEl.value = data.text || text;
    autoResize(inputEl);
    inputEl.focus();
    inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length);
  } catch (error) {
    showError(error.message);
  } finally {
    setFixing(false);
  }
}

async function sendMessage(options = {}) {
  const forcedText = typeof options.forcedText === "string" ? options.forcedText.trim() : "";
  const forcedMetadata = options.forcedMetadata && typeof options.forcedMetadata === "object"
    ? options.forcedMetadata
    : null;
  const text = forcedText || inputEl.value.trim();
  const pendingImages = [...selectedImageFiles];
  const pendingDocuments = [...selectedDocumentFiles];
  const pendingYouTubeUrl = selectedYouTubeUrl;
  if (!text && !pendingImages.length && !pendingDocuments.length && !pendingYouTubeUrl) {
    return { ok: false, errorCode: "" };
  }

  const editingEntry = getHistoryMessage(editingMessageId);
  const isEditing = Boolean(editingEntry && editingEntry.role === "user");
  const editedMessageId = isEditing ? Number(editingEntry.id) : null;

  if (pendingDeleteMessageId !== null) {
    clearPendingDeleteMessage({ preserveScroll: true });
  }

  if (inlineEditingMessageId !== null) {
    clearInlineEditingTarget();
    renderConversationHistory({ preserveScroll: true });
  }

  if (pendingDocuments.length) {
    const modeSelectionAccepted = await promptPdfSubmissionMode(pendingDocuments);
    if (!modeSelectionAccepted) {
      return { ok: false, errorCode: "" };
    }
  }

  const existingDocumentAttachments = !pendingDocuments.length && isEditing
    ? getExistingDocumentAttachmentsForCanvasPrompt(editingEntry)
    : [];
  const documentCanvasPromptItems = pendingDocuments.length ? pendingDocuments : existingDocumentAttachments;

  let documentCanvasAction = "prompt";
  if (documentCanvasPromptItems.length) {
    documentCanvasAction = await promptDocumentCanvasAction(documentCanvasPromptItems);
  }

  setPendingDocumentCanvasOpen(documentCanvasAction === "open" ? documentCanvasPromptItems : null);

  if (pendingImages.length && !Boolean(featureFlags.image_uploads_enabled)) {
    clearSelectedImage();
    showError("Image uploads are disabled in .env.");
    return { ok: false, errorCode: "" };
  }
  if (!isEditing) {
    clearEditTarget();
  }

  let sendSucceeded = false;
  let sendErrorCode = "";

  clearToastRegion();
  inputEl.value = "";
  inputEl.style.height = "auto";
  clearAllAttachments();

  if (!currentConvId) {
    const response = await fetch("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "New Chat",
        model: modelSel.value,
        persona_id: currentConversationPersonaId || null,
      }),
    });
    const conversation = await response.json();
    currentConvId = conversation.id;
    currentConvTitle = String(conversation.title || "New Chat").trim() || "New Chat";
    currentConversationPersonaId = normalizePersonaId(conversation.persona_id);
    syncPersonaSelectors(currentConversationPersonaId);
    loadSidebar();
    updateExportPanel();
  }

  let userMetadata = buildPendingAttachmentMetadata(pendingImages, pendingDocuments, pendingYouTubeUrl);
  if (forcedMetadata) {
    userMetadata = {
      ...(userMetadata || {}),
      ...forcedMetadata,
    };
  }
  if (userMetadata && !Object.keys(userMetadata).length) {
    userMetadata = null;
  }
  let userGroup;

  if (isEditing) {
    const editIndex = getHistoryMessageIndex(editedMessageId);
    if (editIndex < 0) {
      clearEditTarget();
      showError("The selected message could not be edited.");
      return { ok: false, errorCode: "" };
    }

    if (!pendingImages.length && !pendingDocuments.length && !pendingYouTubeUrl) {
      userMetadata = sanitizeEditedUserMetadata(editingEntry.metadata);
    }

    history = history.slice(0, editIndex + 1).map((item) => ({
      ...normalizeHistoryEntry(item),
      metadata: item.metadata && typeof item.metadata === "object" ? { ...item.metadata } : null,
    }));
    history[editIndex] = {
      ...history[editIndex],
      content: text,
      metadata: userMetadata,
    };
    streamingCanvasDocuments = [];
    resetStreamingCanvasPreview();
    pendingCanvasDiff = null;
    isCanvasEditing = false;
    editingCanvasDocumentId = null;
    activeCanvasDocumentId = getActiveCanvasDocument(history)?.id || null;
    rebuildTokenStatsFromHistory();
    renderConversationHistory({ preserveScroll: true });
    renderCanvasPanel();
    clearEditTarget();
  } else {
    const userEntry = { id: null, role: "user", content: text, metadata: userMetadata };
    history.push(userEntry);
  }

  const controller = new AbortController();
  activeAbortController = controller;
  conversationRefreshGeneration += 1;
  pendingConversationRefreshTimers.forEach((timerId) => window.clearTimeout(timerId));
  pendingConversationRefreshTimers.clear();
  setStreaming(true);
  renderConversationHistory({ preserveScroll: true });
  userGroup = messagesEl.querySelector(".msg-group.user:last-of-type");

  const { asstGroup, stepLog, asstBubble } = createAssistantStreamingGroup();

  let rawAnswer = "";
  let rawReasoning = "";
  let fullAnswer = "";
  let latestUsage = null;
  let hasLiveUsageTurn = false;
  let assistantToolResults = [];
  let assistantToolTrace = [];
  let assistantSubAgentTraces = [];
  let assistantToolHistory = [];
  let pendingClarification = null;
  let persistedMessageIds = null;
  let receivedHistorySync = false;
  const stepItems = {};
  const stepSections = {};
  const assistantTraceByKey = {};
  let latestStepInfo = { step: 1, maxSteps: null };
  let pendingAnswerRenderTimer = null;
  let pendingReasoningRenderTimer = null;
  let visibleAnswer = "";

  const scheduleAnswerRender = () => {
    if (pendingAnswerRenderTimer !== null) {
      return;
    }

    const flushStreamingAnswerFrame = () => {
      pendingAnswerRenderTimer = null;
      if (visibleAnswer === fullAnswer) {
        return;
      }
      if (!String(fullAnswer || "").trim()) {
        visibleAnswer = fullAnswer;
        return;
      }

      visibleAnswer = fullAnswer;
      renderBubbleWithCursor(asstBubble, visibleAnswer);
      if (String(visibleAnswer || "").trim()) {
        activeAssistantStreamingHasVisibleAnswer = true;
      }
      scrollToBottom();
    };

    if (typeof window.requestAnimationFrame === "function") {
      pendingAnswerRenderTimer = window.requestAnimationFrame(flushStreamingAnswerFrame);
      return;
    }

    pendingAnswerRenderTimer = window.setTimeout(flushStreamingAnswerFrame, STREAM_RENDER_FALLBACK_INTERVAL_MS);
  };

  const flushAnswerRender = () => {
    if (pendingAnswerRenderTimer !== null) {
      if (typeof window.cancelAnimationFrame === "function") {
        window.cancelAnimationFrame(pendingAnswerRenderTimer);
      } else {
        window.clearTimeout(pendingAnswerRenderTimer);
      }
      pendingAnswerRenderTimer = null;
    }
    if (!String(fullAnswer || "").trim()) {
      visibleAnswer = fullAnswer;
      return;
    }

    visibleAnswer = fullAnswer;
    renderBubbleWithCursor(asstBubble, visibleAnswer);
    if (String(visibleAnswer || "").trim()) {
      activeAssistantStreamingHasVisibleAnswer = true;
    }
  };

  const scheduleReasoningRender = () => {
    if (pendingReasoningRenderTimer !== null) {
      return;
    }

    const flushStreamingReasoningFrame = () => {
      pendingReasoningRenderTimer = null;
      updateReasoningPanel(asstGroup, rawReasoning, { forceOpen: true, streaming: true });
      scrollToBottom();
    };

    if (typeof window.requestAnimationFrame === "function") {
      pendingReasoningRenderTimer = window.requestAnimationFrame(flushStreamingReasoningFrame);
      return;
    }

    pendingReasoningRenderTimer = window.setTimeout(flushStreamingReasoningFrame, STREAM_RENDER_FALLBACK_INTERVAL_MS);
  };

  const flushReasoningRender = () => {
    if (pendingReasoningRenderTimer !== null) {
      if (typeof window.cancelAnimationFrame === "function") {
        window.cancelAnimationFrame(pendingReasoningRenderTimer);
      } else {
        window.clearTimeout(pendingReasoningRenderTimer);
      }
      pendingReasoningRenderTimer = null;
    }
    updateReasoningPanel(asstGroup, rawReasoning, { forceOpen: true, streaming: true });
  };

  try {
    const requestMessages = buildRequestMessagesFromHistory();

    let response;
    if (pendingImages.length || pendingDocuments.length) {
      const formData = new FormData();
      formData.append("messages", JSON.stringify(requestMessages));
      formData.append("model", modelSel.value);
      formData.append("conversation_id", String(currentConvId));
      formData.append("user_content", text);
      if (editedMessageId !== null) {
        formData.append("edited_message_id", String(editedMessageId));
      }
      pendingImages.forEach((file) => formData.append("image", file));
      pendingDocuments.forEach((file) => formData.append("document", file));
      formData.append("document_modes", JSON.stringify(
        pendingDocuments.map((file) => ({
          file_name: file.name,
          submission_mode: getDocumentSubmissionMode(file),
        }))
      ));
      formData.append("document_canvas_action", documentCanvasAction);
      if (pendingYouTubeUrl) {
        formData.append("youtube_url", pendingYouTubeUrl);
      }

      response = await fetch("/chat", {
        method: "POST",
        signal: controller.signal,
        body: formData,
      });
    } else {
      response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          messages: requestMessages,
          model: modelSel.value,
          conversation_id: currentConvId,
          edited_message_id: editedMessageId,
          user_content: text,
          document_canvas_action: documentCanvasAction,
          youtube_url: pendingYouTubeUrl,
        }),
      });
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: "An unexpected error occurred.", code: "" }));
      const requestError = new Error(error.error || "An unexpected error occurred.");
      requestError.code = typeof error.code === "string" ? error.code : "";
      throw requestError;
    }

    await streamNdjsonResponse(response, (event) => {
      if (event.type === "status" && event.status === "compacting") {
        if (activeAssistantStreamingHasVisibleAnswer) {
          const compactingMessage = String(event.message || "Compacting conversation...").trim() || "Compacting conversation...";
          asstBubble.hidden = false;
          asstBubble.classList.add("thinking");
          asstBubble.classList.add("cursor");
          asstBubble.textContent = compactingMessage;
          scrollToBottom();
        }
      } else if (event.type === "step_started") {
        latestStepInfo = {
          step: event.step || latestStepInfo.step,
          maxSteps: event.max_steps || latestStepInfo.maxSteps,
        };
      } else if (event.type === "vision_complete" || event.type === "ocr_complete") {
        const lastMessage = history[history.length - 1];
        if (lastMessage && lastMessage.role === "user") {
          const attachment = event.attachment || {
            kind: "image",
            image_id: event.image_id,
            image_name: event.image_name,
            analysis_method: event.analysis_method,
            ocr_text: event.ocr_text,
            vision_summary: event.vision_summary,
            assistant_guidance: event.assistant_guidance,
            key_points: Array.isArray(event.key_points) ? event.key_points : [],
          };
          lastMessage.metadata = mergeAttachmentMetadata(lastMessage.metadata, attachment);
          updateAttachmentBadge(userGroup, lastMessage.metadata);
          updateVisionDetails(userGroup, lastMessage.metadata);
        }
        scrollToBottom();
      } else if (event.type === "video_transcript_ready") {
        const lastMessage = history[history.length - 1];
        if (lastMessage && lastMessage.role === "user") {
          const attachment = event.attachment || {
            kind: "video",
            video_id: event.video_id,
            video_title: event.video_title,
            video_url: event.video_url,
            transcript_language: event.transcript_language,
          };
          lastMessage.metadata = mergeAttachmentMetadata(lastMessage.metadata, attachment);
          updateAttachmentBadge(userGroup, lastMessage.metadata);
        }
        scrollToBottom();
      } else if (event.type === "document_processed") {
        const lastMessage = history[history.length - 1];
        if (lastMessage && lastMessage.role === "user") {
          const attachment = event.attachment || {
            kind: "document",
            file_id: event.file_id,
            file_name: event.file_name,
            file_mime_type: event.file_mime_type,
          };
          lastMessage.metadata = mergeAttachmentMetadata(lastMessage.metadata, attachment);
          appendAttachmentBadge(userGroup, lastMessage.metadata);
        }

        if (event.visual_only) {
          setCanvasStatus(`${String(event.file_name || "PDF").trim() || "PDF"} attached in visual mode. Up to the first ${VISUAL_PDF_PAGE_LIMIT} pages will be used for image analysis, and Canvas editing is unavailable for this upload.`, "muted");
        }

        if (event.canvas_document && !isCanvasOpen()) {
          setCanvasAttention(true);
        }
        scrollToBottom();
      } else if (event.type === "step_update") {
        stepLog.style.display = "";
        const toolKey = event.call_id || event.tool || "__generic__";
        const sectionItems = ensureToolStepSection(
          stepLog,
          stepSections,
          event.step || latestStepInfo.step,
          event.max_steps || latestStepInfo.maxSteps,
        );
        if (!stepItems[toolKey]) {
          const item = createToolStepItem(event.tool);
          sectionItems.appendChild(item);
          stepItems[toolKey] = {
            el: item,
            toolName: event.tool,
            preview: event.preview || "",
            startedAt: performance.now(),
          };
        }
        const itemRef = stepItems[toolKey];
        itemRef.toolName = event.tool || itemRef.toolName;
        itemRef.preview = event.preview || itemRef.preview;
        setToolStepState(itemRef.el, {
          toolName: itemRef.toolName,
          preview: itemRef.preview,
          state: "running",
        });
        if (event.tool) {
          const traceEntry = assistantTraceByKey[toolKey] || {
            tool_name: event.tool,
            step: event.step || latestStepInfo.step || 1,
            preview: event.preview || "",
            summary: "",
            state: "running",
            cached: false,
          };
          traceEntry.tool_name = event.tool || traceEntry.tool_name;
          traceEntry.step = event.step || traceEntry.step || 1;
          traceEntry.preview = event.preview || traceEntry.preview || "";
          traceEntry.state = "running";
          assistantTraceByKey[toolKey] = traceEntry;
          if (!assistantToolTrace.includes(traceEntry)) {
            assistantToolTrace.push(traceEntry);
          }
        }
        scrollToBottom();
      } else if (event.type === "tool_result") {
        const toolKey = event.call_id || event.tool || "__generic__";
        const itemRef = stepItems[toolKey];
        if (itemRef) {
          const normalizedSummary = normalizeToolSummary(event.summary);
          const durationMs = performance.now() - itemRef.startedAt;
          setToolStepState(itemRef.el, {
            toolName: event.tool || itemRef.toolName,
            preview: itemRef.preview,
            summary: normalizedSummary.text,
            state: normalizedSummary.isError ? "error" : "done",
            cached: normalizedSummary.cached,
            durationMs,
          });
          const traceEntry = assistantTraceByKey[toolKey] || {
            tool_name: event.tool || itemRef.toolName,
            step: event.step || latestStepInfo.step || 1,
            preview: itemRef.preview || "",
            summary: "",
            state: "done",
            cached: false,
          };
          traceEntry.tool_name = event.tool || traceEntry.tool_name;
          traceEntry.step = event.step || traceEntry.step || 1;
          traceEntry.preview = itemRef.preview || traceEntry.preview || "";
          traceEntry.summary = normalizedSummary.text;
          traceEntry.state = normalizedSummary.isError ? "error" : "done";
          traceEntry.cached = normalizedSummary.cached;
          assistantTraceByKey[toolKey] = traceEntry;
          if (!assistantToolTrace.includes(traceEntry)) {
            assistantToolTrace.push(traceEntry);
          }
          scrollToBottom();
        }
      } else if (event.type === "tool_error") {
        const toolKey = event.call_id || event.tool || "__generic__";
        let itemRef = stepItems[toolKey];
        if (!itemRef) {
          const sectionItems = ensureToolStepSection(
            stepLog,
            stepSections,
            event.step || latestStepInfo.step,
            latestStepInfo.maxSteps,
          );
          const item = createToolStepItem(event.tool);
          sectionItems.appendChild(item);
          itemRef = {
            el: item,
            toolName: event.tool,
            preview: "",
            startedAt: performance.now(),
          };
          stepItems[toolKey] = itemRef;
        }

        if (itemRef) {
          const durationMs = performance.now() - itemRef.startedAt;
          stepLog.style.display = "";
          setToolStepState(itemRef.el, {
            toolName: event.tool || itemRef.toolName,
            preview: itemRef.preview,
            summary: event.error || "Error",
            state: "error",
            durationMs,
          });
          if (event.tool) {
            const traceEntry = assistantTraceByKey[toolKey] || {
              tool_name: event.tool || itemRef.toolName,
              step: event.step || latestStepInfo.step || 1,
              preview: itemRef.preview || "",
              summary: "",
              state: "error",
              cached: false,
            };
            traceEntry.tool_name = event.tool || traceEntry.tool_name;
            traceEntry.step = event.step || traceEntry.step || 1;
            traceEntry.preview = itemRef.preview || traceEntry.preview || "";
            traceEntry.summary = event.error || "Error";
            traceEntry.state = "error";
            assistantTraceByKey[toolKey] = traceEntry;
            if (!assistantToolTrace.includes(traceEntry)) {
              assistantToolTrace.push(traceEntry);
            }
          }
        } else {
          const errItem = document.createElement("div");
          errItem.className = "step-item step-error";
          errItem.textContent = event.error || "Error";
          stepLog.style.display = "";
          stepLog.appendChild(errItem);
        }
        scrollToBottom();
      } else if (event.type === "answer_start") {
        asstBubble.classList.remove("thinking");
        asstBubble.classList.remove("cursor");
      } else if (event.type === "reasoning_start") {
        updateReasoningPanel(asstGroup, rawReasoning, { forceOpen: true, streaming: true });
        scrollToBottom();
      } else if (event.type === "reasoning_delta") {
        rawReasoning += event.text || "";
        scheduleReasoningRender();
      } else if (event.type === "answer_sync") {
        const syncedAnswer = String(event.text || "").trim();
        if (!syncedAnswer) {
          return;
        }
        rawAnswer = syncedAnswer;
        fullAnswer = rawAnswer;
        activeAssistantStreamingHasVisibleAnswer = true;
        flushAnswerRender();
        asstBubble.classList.remove("thinking");
        asstBubble.classList.remove("cursor");
        renderBubbleMarkdown(asstBubble, fullAnswer);
        scrollToBottom();
      } else if (event.type === "answer_delta") {
        rawAnswer += event.text || "";
        fullAnswer = rawAnswer;
        if (String(fullAnswer || "").trim()) {
          activeAssistantStreamingHasVisibleAnswer = true;
        }
        scheduleAnswerRender();
      } else if (event.type === "clarification_request") {
        pendingClarification = event.clarification && typeof event.clarification === "object" ? event.clarification : null;
        rawAnswer = String(event.text || "").trim();
        fullAnswer = rawAnswer;
        if (String(fullAnswer || "").trim()) {
          activeAssistantStreamingHasVisibleAnswer = true;
        }
        asstBubble.classList.remove("thinking");
        asstBubble.classList.remove("cursor");
        if (fullAnswer) {
          flushAnswerRender();
          renderBubbleMarkdown(asstBubble, fullAnswer);
        } else {
          asstBubble.remove();
        }
        scrollToBottom();
      } else if (event.type === "usage") {
        latestUsage = normalizeUsagePayload(event);
        updateStats(latestUsage, { replaceLast: hasLiveUsageTurn });
        hasLiveUsageTurn = true;
      } else if (event.type === "assistant_tool_results") {
        assistantToolResults = Array.isArray(event.tool_results) ? event.tool_results : [];
        updateAssistantFetchBadge(asstGroup, { tool_results: assistantToolResults });
        scrollToBottom();
      } else if (event.type === "assistant_sub_agent_traces") {
        assistantSubAgentTraces = Array.isArray(event.sub_agent_traces) ? event.sub_agent_traces : [];
        updateAssistantSubAgentTrace(asstGroup, { sub_agent_traces: assistantSubAgentTraces });
        scrollToBottom();
      } else if (event.type === "assistant_sub_agent_trace_update") {
        assistantSubAgentTraces = mergeAssistantSubAgentTraceEntry(assistantSubAgentTraces, event.entry);
        updateAssistantSubAgentTrace(asstGroup, { sub_agent_traces: assistantSubAgentTraces });
        scrollToBottom();
      } else if (event.type === "assistant_tool_history") {
        const nextToolHistory = Array.isArray(event.messages)
          ? event.messages.map(normalizeHistoryEntry).filter((item) => item.role === "assistant" || item.role === "tool")
          : [];
        assistantToolHistory.push(...nextToolHistory);
      } else if (event.type === "canvas_loading") {
        if (!isCanvasStreamingPreviewTool(event.tool)) {
          return;
        }
        const previewDocument = ensureStreamingCanvasPreview(event.tool, event.preview_key, event.snapshot);
        if (!isCanvasOpen()) {
          openCanvas(null, { focusPanel: false });
        } else {
          renderCanvasPanel();
        }
        setCanvasStatus(getCanvasStreamingStatusMessage(event.tool, previewDocument, "loading"), "muted");
      } else if (event.type === "canvas_executing") {
        if (isCanvasStreamingPreviewTool(event.tool)) {
          const executingPreview = [...streamingCanvasPreviews.values()][0] || null;
          setCanvasStatus(getCanvasStreamingStatusMessage(event.tool, executingPreview, "executing"), "muted");
        }
      } else if (event.type === "canvas_content_delta") {
        if (!isCanvasStreamingPreviewTool(event.tool)) {
          return;
        }
        const previewDocument = ensureStreamingCanvasPreview(event.tool, event.preview_key, event.snapshot);
        if (previewDocument) {
          queueStreamingCanvasPreviewDelta(previewDocument, event.delta, event.replace_content);
          if (!isCanvasOpen()) {
            openCanvas(null, { focusPanel: false });
          }
          setCanvasStatus(getCanvasStreamingStatusMessage(event.tool, previewDocument, "streaming"), "muted");
          scheduleCanvasPreviewRender();
        }
      } else if (event.type === "canvas_sync") {
        const previousDocuments = getCanvasDocumentCollection();
        const nextDocuments = Array.isArray(event.documents)
          ? event.documents.map((document) => normalizeCanvasDocument(document)).filter((document) => document.id)
          : [];
        const previousActiveId = String(activeCanvasDocumentId || "").trim();
        const requestedActiveId = String(event.active_document_id || "").trim();
        const nextActiveCandidate = getCanvasDocumentById(nextDocuments, requestedActiveId)
          || getCanvasDocumentById(nextDocuments, previousActiveId)
          || nextDocuments[nextDocuments.length - 1]
          || null;
        const previousSelectedDocument = getCanvasDocumentById(previousDocuments, previousActiveId);
        const previousVersionOfNextDocument = getCanvasDocumentById(previousDocuments, nextActiveCandidate?.id || previousActiveId);
        const hadStreamingPreviewForDoc =
          nextActiveCandidate &&
          [...streamingCanvasPreviews.values()].some((p) => p.id === nextActiveCandidate.id);
        if (previousVersionOfNextDocument && nextActiveCandidate) {
          const nextDiff = previousVersionOfNextDocument.content !== nextActiveCandidate.content
            ? buildCanvasDiff(previousVersionOfNextDocument.content, nextActiveCandidate.content)
            : null;
          if (nextDiff) {
            pendingCanvasDiff = {
              documentId: nextActiveCandidate.id,
              source: hadStreamingPreviewForDoc ? "live-preview" : "direct-sync",
              diff: nextDiff,
            };
          } else if (pendingCanvasDiff?.documentId === nextActiveCandidate.id) {
            pendingCanvasDiff = null;
          }
        }
        resetStreamingCanvasPreview();
        streamingCanvasDocuments = nextDocuments;
        if (streamingCanvasDocuments.length) {
          activeCanvasDocumentId = String(nextActiveCandidate?.id || "").trim() || streamingCanvasDocuments[streamingCanvasDocuments.length - 1].id;
          renderCanvasPanel();
          const pendingCanvasRequest = pendingDocumentCanvasOpen;
          const canvasWasOpen = isCanvasOpen();
          const activeDocumentChangeMessage = describeCanvasActiveDocumentChange(previousSelectedDocument, nextActiveCandidate, requestedActiveId);
          if (pendingCanvasRequest) {
            consumePendingDocumentCanvasOpen();
          }

          if (pendingCanvasRequest && event.auto_open && !canvasWasOpen) {
            const requestLabel = Number(pendingCanvasRequest.fileCount || 1) > 1
              ? `${pendingCanvasRequest.fileCount} documents`
              : pendingCanvasRequest.fileName;
            openCanvas(null, { focusPanel: false });
            setCanvasStatus(`${requestLabel} opened in Canvas.`, "success");
          } else if (event.auto_open && !canvasWasOpen) {
            openCanvas(null, { focusPanel: false });
            setCanvasStatus(activeDocumentChangeMessage || "Canvas updated.", "success");
          } else if (activeDocumentChangeMessage) {
            if (canvasWasOpen) {
              setCanvasAttention(false);
              setCanvasStatus(activeDocumentChangeMessage || "Canvas updated.", "success");
            } else {
              setCanvasAttention(true);
              setCanvasStatus(activeDocumentChangeMessage, "muted");
            }
          } else if (isCanvasOpen()) {
            setCanvasAttention(false);
            setCanvasStatus("Canvas updated.", "success");
          } else {
            setCanvasAttention(true);
            setCanvasStatus("Canvas updated. Open the panel to review.", "success");
          }
        } else if (event.cleared) {
          pendingCanvasDiff = null;
          isCanvasEditing = false;
          editingCanvasDocumentId = null;
          activeCanvasDocumentId = null;
          renderCanvasPanel();
          if (isCanvasOpen()) {
            closeCanvas();
          }
          setCanvasAttention(false);
          setCanvasStatus("Canvas cleared.", "success");
        }
      } else if (event.type === "history_sync") {
        receivedHistorySync = true;
        history = Array.isArray(event.messages) ? event.messages.map(normalizeHistoryEntry) : [];
        streamingCanvasDocuments = [];
        resetStreamingCanvasPreview();
        activeCanvasDocumentId = getActiveCanvasDocument(history)?.id || null;
        rebuildTokenStatsFromHistory();
        renderConversationHistory();
        renderCanvasPanel();
      } else if (event.type === "conversation_summary_status") {
        latestSummaryStatus = event && typeof event === "object" ? { ...event } : null;
        renderSummaryInspector();
      } else if (event.type === "conversation_summary_applied") {
        latestSummaryStatus = event && typeof event === "object"
          ? { ...event, applied: true, reason: "applied", failure_stage: null, failure_detail: "Summary completed successfully." }
          : { applied: true, reason: "applied", failure_stage: null, failure_detail: "Summary completed successfully." };
        const coveredCount = Number(event.covered_message_count || 0);
        const mode = String(event.mode || "auto").trim() || "auto";
        const tokenCount = Number(event.visible_token_count || 0);
        const parts = [
          coveredCount > 0
            ? `${coveredCount} older message${coveredCount === 1 ? " was" : "s were"} summarized`
            : "Conversation summary updated",
        ];
        parts.push(`mode: ${mode}`);
        if (tokenCount > 0) {
          parts.push(`visible tokens: ${tokenCount}`);
        }
        showToast(parts.join(" • "), "success");
      } else if (event.type === "message_ids") {
        persistedMessageIds = event;
      } else if (event.type === "done") {
        // no-op
      }
    });

    if (pendingAnswerRenderTimer !== null) {
      flushAnswerRender();
    }
    if (pendingReasoningRenderTimer !== null) {
      flushReasoningRender();
    }
    pendingDocumentCanvasOpen = null;
    finalizeAssistantBubble(asstBubble, fullAnswer);
    const assistantEntry = {
      id: null,
      role: "assistant",
      content: fullAnswer,
      usage: latestUsage,
      metadata: buildAssistantMetadata({
        reasoning: rawReasoning,
        tool_trace: assistantToolTrace,
        tool_results: assistantToolResults,
        sub_agent_traces: assistantSubAgentTraces,
        canvas_documents: streamingCanvasDocuments,
        usage: latestUsage,
        pending_clarification: pendingClarification,
      }),
    };
    if (!receivedHistorySync) {
      history.push(...assistantToolHistory, assistantEntry);
      applyPersistedMessageIds(persistedMessageIds, assistantEntry);
    }
    saveAssistantReasoning(currentConvId, persistedMessageIds?.assistant_message_id || assistantEntry.id, rawReasoning);
    finalizeAssistantStreamingGroup(asstGroup, stepLog, assistantEntry.metadata);
    maybePromptToSaveSubAgentResearch(
      receivedHistorySync
        ? findPersistedAssistantEntryForSubAgentPrompt(persistedMessageIds?.assistant_message_id)
        : assistantEntry
    );
    clearEditTarget();
    renderSummaryInspector();

    if (shouldGenerateConversationTitle()) {
      generateTitle(currentConvId);
    } else {
      loadSidebar();
    }
    lastConversationSignature = getConversationSignature(history);
    scheduleConversationRefreshAfterStream();
    sendSucceeded = true;
  } catch (error) {
    sendErrorCode = String(error?.code || "").trim();
    if (pendingAnswerRenderTimer !== null) {
      flushAnswerRender();
    }
    if (pendingReasoningRenderTimer !== null) {
      flushReasoningRender();
    }
    pendingDocumentCanvasOpen = null;
    clearEmptyAssistantStreamingBubble();
    if (fullAnswer.trim() || rawReasoning.trim()) {
      finalizeAssistantBubble(asstBubble, fullAnswer);

      const assistantEntry = {
        id: null,
        role: "assistant",
        content: fullAnswer,
        usage: latestUsage,
        metadata: buildAssistantMetadata({
          reasoning: rawReasoning,
          tool_trace: assistantToolTrace,
          tool_results: assistantToolResults,
          sub_agent_traces: assistantSubAgentTraces,
          canvas_documents: streamingCanvasDocuments,
          usage: latestUsage,
          pending_clarification: pendingClarification,
        }),
      };
      if (!receivedHistorySync) {
        history.push(...assistantToolHistory, assistantEntry);
        applyPersistedMessageIds(persistedMessageIds, assistantEntry);
      }
      saveAssistantReasoning(currentConvId, persistedMessageIds?.assistant_message_id || assistantEntry.id, rawReasoning);
      finalizeAssistantStreamingGroup(asstGroup, stepLog, assistantEntry.metadata);
      maybePromptToSaveSubAgentResearch(
        receivedHistorySync
          ? findPersistedAssistantEntryForSubAgentPrompt(persistedMessageIds?.assistant_message_id)
          : assistantEntry
      );
      clearEditTarget();
      renderSummaryInspector();
      loadSidebar();

      if (error.name !== "AbortError") {
        showError("Connection was interrupted. The partial answer was preserved.");
      }
      lastConversationSignature = getConversationSignature(history);
      scheduleConversationRefreshAfterStream();
    } else {
      if (currentConvId) {
        await openConversation(currentConvId);
      } else {
        startNewChat();
      }
      if (error.name !== "AbortError") {
        showError(error.message);
      }
    }
  } finally {
    activeAbortController = null;
    setStreaming(false);
    renderConversationHistory({ preserveScroll: true });
    resetAssistantStreamingBubbleState();
    refreshEditBanner();
    inputEl.focus();
  }

  return { ok: sendSucceeded, errorCode: sendErrorCode };
}

async function generateTitle(convId) {
  try {
    const response = await fetch(`/api/conversations/${convId}/generate-title`, { method: "POST" });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      console.warn(data.error || "Conversation title generation failed.");
    }
  } catch (error) {
    console.warn("Failed to generate title:", error);
  } finally {
    loadSidebar();
  }
}

setKbStatus("Knowledge base idle");
clearEditTarget();
updateHeaderOffset();
applyCanvasPanelWidth(readCanvasWidthPreference(), false);
syncCanvasToggleButton();
const initialSidebarPref = readSidebarPreference();
setSidebarOpen(initialSidebarPref === null ? !isMobileViewport() : initialSidebarPref, false);
const initialModelId = resolvePreferredModelSelection(modelSel ? modelSel.value : "");
syncModelSelectors(initialModelId, getKnownModelLabel(initialModelId));
applyConversationPersonaSelection("");
loadSidebar();
updateExportPanel();
void loadKnowledgeBaseDocuments();
