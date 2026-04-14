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
const featureFlags = bootstrapData.features || appSettings.features || {};
const csrfToken = String(bootstrapData.csrf_token || "").trim();

const nativeFetch = typeof globalThis.fetch === "function" ? globalThis.fetch.bind(globalThis) : null;
const CSRF_SAFE_HTTP_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

function resolveFetchMethod(input, init) {
  const explicitMethod = String(init?.method || "").trim();
  if (explicitMethod) {
    return explicitMethod.toUpperCase();
  }
  if (input instanceof Request) {
    return String(input.method || "GET").trim().toUpperCase() || "GET";
  }
  return "GET";
}

function resolveFetchUrl(input) {
  if (input instanceof Request) {
    return input.url;
  }
  return String(input || "").trim();
}

function shouldAttachCsrfHeader(input, init) {
  if (!nativeFetch || !csrfToken) {
    return false;
  }
  const method = resolveFetchMethod(input, init);
  if (CSRF_SAFE_HTTP_METHODS.has(method)) {
    return false;
  }
  const rawUrl = resolveFetchUrl(input);
  if (!rawUrl) {
    return true;
  }
  try {
    const resolvedUrl = new URL(rawUrl, window.location.href);
    return resolvedUrl.origin === window.location.origin;
  } catch (_) {
    return true;
  }
}

if (nativeFetch) {
  globalThis.fetch = (input, init = undefined) => {
    if (!shouldAttachCsrfHeader(input, init)) {
      return nativeFetch(input, init);
    }
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    if (!headers.has("X-CSRF-Token")) {
      headers.set("X-CSRF-Token", csrfToken);
    }
    return nativeFetch(input, { ...(init || {}), headers });
  };
}

const generalInstructionsEl = document.getElementById("general-instructions-input");
const generalInstructionsTemplateSelectEl = document.getElementById("general-instructions-template-select");
const generalInstructionsTemplateApplyBtn = document.getElementById("general-instructions-template-apply-btn");
const aiPersonalityEl = document.getElementById("ai-personality-input");
const aiPersonalityTemplateSelectEl = document.getElementById("ai-personality-template-select");
const aiPersonalityTemplateApplyBtn = document.getElementById("ai-personality-template-apply-btn");
const defaultPersonaEl = document.getElementById("default-persona-select");
const openPersonasTabBtn = document.getElementById("open-personas-tab-btn");
const personaListEl = document.getElementById("persona-list");
const personaNameEl = document.getElementById("persona-name-input");
const personaSaveBtn = document.getElementById("persona-save-btn");
const personaDeleteBtn = document.getElementById("persona-delete-btn");
const personaNewBtn = document.getElementById("persona-new-btn");
const personaStatusEl = document.getElementById("persona-status");
const personaEditorTitleEl = document.getElementById("persona-editor-title");
const personaMemoryListEl = document.getElementById("persona-memory-list");
const personaMemoryKeyEl = document.getElementById("persona-memory-key-input");
const personaMemoryValueEl = document.getElementById("persona-memory-value-input");
const personaMemorySaveBtn = document.getElementById("persona-memory-save-btn");
const personaMemoryCancelBtn = document.getElementById("persona-memory-cancel-btn");
const personaMemoryDeleteBtn = document.getElementById("persona-memory-delete-btn");
const personaMemoryStatusEl = document.getElementById("persona-memory-status");
const personaMemoryNoteEl = document.getElementById("persona-memory-note");
const temperatureEl = document.getElementById("temperature-input");
const scratchpadListEl = document.getElementById("scratchpad-list");
const scratchpadAddBtn = document.getElementById("scratchpad-add-btn");
const scratchpadCountEl = document.getElementById("scratchpad-count");
const scratchpadReadonlyNoteEl = document.getElementById("scratchpad-readonly-note");
const maxStepsEl = document.getElementById("max-steps-input");
const maxParallelToolsEl = document.getElementById("max-parallel-tools-input");
const searchToolQueryLimitEl = document.getElementById("search-tool-query-limit-input");
const subAgentMaxStepsEl = document.getElementById("sub-agent-max-steps-input");
const subAgentTimeoutSecondsEl = document.getElementById("sub-agent-timeout-seconds-input");
const subAgentRetryAttemptsEl = document.getElementById("sub-agent-retry-attempts-input");
const subAgentRetryDelaySecondsEl = document.getElementById("sub-agent-retry-delay-seconds-input");
const subAgentMaxParallelToolsEl = document.getElementById("sub-agent-max-parallel-tools-input");
const webCacheTtlHoursEl = document.getElementById("web-cache-ttl-hours-input");
const openrouterPromptCacheEnabledEl = document.getElementById("openrouter-prompt-cache-enabled-toggle");
const clarificationMaxQuestionsEl = document.getElementById("clarification-max-questions-input");
const summaryModeEl = document.getElementById("summary-mode-select");
const summaryDetailLevelEl = document.getElementById("summary-detail-level-select");
const summaryTriggerEl = document.getElementById("summary-trigger-input");
const summarySkipFirstEl = document.getElementById("summary-skip-first-input");
const summarySkipLastEl = document.getElementById("summary-skip-last-input");
const promptPreflightSummaryTokenCountEl = document.getElementById("prompt-preflight-summary-token-count-input");
const summarySourceTargetTokensEl = document.getElementById("summary-source-target-tokens-input");
const summaryRetryMinSourceTokensEl = document.getElementById("summary-retry-min-source-tokens-input");
const promptMaxInputTokensEl = document.getElementById("prompt-max-input-tokens-input");
const promptResponseTokenReserveEl = document.getElementById("prompt-response-token-reserve-input");
const promptRecentHistoryMaxTokensEl = document.getElementById("prompt-recent-history-max-tokens-input");
const promptSummaryMaxTokensEl = document.getElementById("prompt-summary-max-tokens-input");
const promptRagMaxTokensEl = document.getElementById("prompt-rag-max-tokens-input");
const promptToolMemoryMaxTokensEl = document.getElementById("prompt-tool-memory-max-tokens-input");
const promptToolTraceMaxTokensEl = document.getElementById("prompt-tool-trace-max-tokens-input");
const contextCompactionThresholdEl = document.getElementById("context-compaction-threshold-input");
const contextCompactionKeepRecentRoundsEl = document.getElementById("context-compaction-keep-recent-rounds-input");
const contextSelectionStrategyEl = document.getElementById("context-selection-strategy-select");
const entropyControlsFieldsetEl = document.getElementById("entropy-controls-fieldset");
const entropyRagBudgetClusterEl = document.getElementById("entropy-rag-budget-cluster");
const entropyProfileEl = document.getElementById("entropy-profile-select");
const entropyRagBudgetRatioEl = document.getElementById("entropy-rag-budget-ratio-input");
const entropyProtectCodeBlocksEl = document.getElementById("entropy-protect-code-blocks-toggle");
const entropyProtectToolResultsEl = document.getElementById("entropy-protect-tool-results-toggle");
const entropyReferenceBoostEl = document.getElementById("entropy-reference-boost-toggle");
const reasoningAutoCollapseEl = document.getElementById("reasoning-auto-collapse-toggle");
const toolMemoryAutoInjectEl = document.getElementById("tool-memory-auto-inject-toggle");
const toolMemoryLanePanelEl = document.getElementById("tool-memory-lane-panel");
const pruningEnabledEl = document.getElementById("pruning-enabled-toggle");
const pruningControlsFieldsetEl = document.getElementById("pruning-controls-fieldset");
const pruningTokenThresholdEl = document.getElementById("pruning-token-threshold-input");
const pruningBatchSizeEl = document.getElementById("pruning-batch-size-input");
const pruningTargetReductionRatioEl = document.getElementById("pruning-target-reduction-ratio-input");
const pruningMinTargetTokensEl = document.getElementById("pruning-min-target-tokens-input");
const fetchThresholdEl = document.getElementById("fetch-threshold-input");
const fetchAggressivenessEl = document.getElementById("fetch-aggressiveness-input");
const fetchHtmlConverterModeEl = document.getElementById("fetch-html-converter-mode-select");
const fetchSummarizeMaxInputCharsEl = document.getElementById("fetch-summarize-max-input-chars-input");
const fetchSummarizeMaxOutputTokensEl = document.getElementById("fetch-summarize-max-output-tokens-input");
const canvasPromptLinesEl = document.getElementById("canvas-prompt-lines-input");
const canvasPromptTokensEl = document.getElementById("canvas-prompt-tokens-input");
const canvasPromptCharsEl = document.getElementById("canvas-prompt-chars-input");
const canvasCodeLineCharsEl = document.getElementById("canvas-code-line-chars-input");
const canvasTextLineCharsEl = document.getElementById("canvas-text-line-chars-input");
const canvasExpandLinesEl = document.getElementById("canvas-expand-lines-input");
const canvasScrollLinesEl = document.getElementById("canvas-scroll-lines-input");
const customModelNameEl = document.getElementById("custom-model-name-input");
const customModelApiModelEl = document.getElementById("custom-model-api-model-input");
const customModelRoutingModeEl = document.getElementById("custom-model-routing-mode-select");
const customModelProviderFieldEl = document.getElementById("custom-model-provider-field");
const customModelProviderSlugEl = document.getElementById("custom-model-provider-slug-input");
const customModelReasoningModeEl = document.getElementById("custom-model-reasoning-mode-select");
const customModelReasoningEffortEl = document.getElementById("custom-model-reasoning-effort-select");
const customModelSupportsToolsEl = document.getElementById("custom-model-supports-tools-toggle");
const customModelSupportsVisionEl = document.getElementById("custom-model-supports-vision-toggle");
const customModelSupportsStructuredEl = document.getElementById("custom-model-supports-structured-toggle");
const addCustomModelBtn = document.getElementById("add-custom-model-btn");
const customModelCancelEditBtn = document.getElementById("custom-model-cancel-edit-btn");
const customModelStatusEl = document.getElementById("custom-model-status");
const customModelListEl = document.getElementById("custom-model-list");
const chatModelVisibilityListEl = document.getElementById("chat-model-visibility-list");
const summaryModelPreferenceEl = document.getElementById("summary-model-preference-select");
const fetchSummarizeModelPreferenceEl = document.getElementById("fetch-summarize-model-preference-select");
const pruneModelPreferenceEl = document.getElementById("prune-model-preference-select");
const fixTextModelPreferenceEl = document.getElementById("fix-text-model-preference-select");
const titleModelPreferenceEl = document.getElementById("title-model-preference-select");
const uploadMetadataModelPreferenceEl = document.getElementById("upload-metadata-model-preference-select");
const subAgentModelPreferenceEl = document.getElementById("sub-agent-model-preference-select");
const chatSummaryModelEl = document.getElementById("chat-summary-model-select");
const imageHelperModelEl = document.getElementById("image-helper-model-select");
const summaryModelFallbackListEl = document.getElementById("summary-model-fallback-list");
const fetchSummarizeModelFallbackListEl = document.getElementById("fetch-summarize-model-fallback-list");
const pruneModelFallbackListEl = document.getElementById("prune-model-fallback-list");
const fixTextModelFallbackListEl = document.getElementById("fix-text-model-fallback-list");
const titleModelFallbackListEl = document.getElementById("title-model-fallback-list");
const uploadMetadataModelFallbackListEl = document.getElementById("upload-metadata-model-fallback-list");
const subAgentModelFallbackListEl = document.getElementById("sub-agent-model-fallback-list");
const summaryModelFallbackAddBtn = document.getElementById("summary-model-fallback-add-btn");
const fetchSummarizeModelFallbackAddBtn = document.getElementById("fetch-summarize-model-fallback-add-btn");
const pruneModelFallbackAddBtn = document.getElementById("prune-model-fallback-add-btn");
const fixTextModelFallbackAddBtn = document.getElementById("fix-text-model-fallback-add-btn");
const titleModelFallbackAddBtn = document.getElementById("title-model-fallback-add-btn");
const uploadMetadataModelFallbackAddBtn = document.getElementById("upload-metadata-model-fallback-add-btn");
const subAgentModelFallbackAddBtn = document.getElementById("sub-agent-model-fallback-add-btn");
const imageProcessingMethodEl = document.getElementById("image-processing-method-select");
const ragInjectOptionsEl = document.getElementById("rag-inject-options");
const ragSensitivityEl = document.getElementById("rag-sensitivity-select");
const ragSensitivityHintEl = document.getElementById("rag-sensitivity-hint");
const ragContextSizeEl = document.getElementById("rag-context-size-select");
const ragEnabledEl = document.getElementById("rag-enabled-toggle");
const ragChunkSizeEl = document.getElementById("rag-chunk-size-input");
const ragChunkOverlapEl = document.getElementById("rag-chunk-overlap-input");
const ragMaxChunksPerSourceEl = document.getElementById("rag-max-chunks-per-source-input");
const ragSearchTopKEl = document.getElementById("rag-search-top-k-input");
const ragSearchMinSimilarityEl = document.getElementById("rag-search-min-similarity-input");
const ragQueryExpansionEnabledEl = document.getElementById("rag-query-expansion-enabled-toggle");
const ragQueryExpansionMaxVariantsEl = document.getElementById("rag-query-expansion-max-variants-input");
const openrouterHttpRefererEl = document.getElementById("openrouter-http-referer-input");
const openrouterAppTitleEl = document.getElementById("openrouter-app-title-input");
const conversationMemoryEnabledEl = document.getElementById("conversation-memory-enabled-toggle");
const ocrEnabledEl = document.getElementById("ocr-enabled-toggle");
const ocrProviderEl = document.getElementById("ocr-provider-select");
const loginSessionTimeoutMinutesEl = document.getElementById("login-session-timeout-minutes-input");
const loginMaxFailedAttemptsEl = document.getElementById("login-max-failed-attempts-input");
const loginLockoutSecondsEl = document.getElementById("login-lockout-seconds-input");
const loginRememberSessionDaysEl = document.getElementById("login-remember-session-days-input");
const youtubeTranscriptsEnabledEl = document.getElementById("youtube-transcripts-enabled-toggle");
const youtubeTranscriptLanguageEl = document.getElementById("youtube-transcript-language-input");
const youtubeTranscriptModelSizeEl = document.getElementById("youtube-transcript-model-size-select");
const toolMemoryTtlDefaultSecondsEl = document.getElementById("tool-memory-ttl-default-seconds-input");
const toolMemoryTtlWebSecondsEl = document.getElementById("tool-memory-ttl-web-seconds-input");
const toolMemoryTtlNewsSecondsEl = document.getElementById("tool-memory-ttl-news-seconds-input");
const fetchRawMaxTextCharsEl = document.getElementById("fetch-raw-max-text-chars-input");
const fetchSummaryMaxCharsEl = document.getElementById("fetch-summary-max-chars-input");
const ragSourceTypeEls = Array.from(document.querySelectorAll("input[name='rag-source-type']"));
const ragAutoInjectSourceTypeEls = Array.from(document.querySelectorAll("input[name='rag-auto-inject-source-type']"));
const proxyOperationEls = Array.from(document.querySelectorAll("input[name='proxy-enabled-operation']"));
const subAgentToolToggleEls = Array.from(document.querySelectorAll("input[name='sub-agent-allowed-tool']"));
const ragSourceSummaryEl = document.getElementById("rag-source-summary");
const ragAutoInjectSourceSummaryEl = document.getElementById("rag-auto-inject-source-summary");
const ragDisabledNoteEl = document.getElementById("rag-disabled-note");
const toolToggleEls = Array.from(document.querySelectorAll("#tool-toggles input[type='checkbox']"));
const kbSyncBtn = document.getElementById("kb-sync-btn");
const kbStatusEl = document.getElementById("kb-status");
const kbDocumentsListEl = document.getElementById("kb-documents-list");
const kbUploadFileEl = document.getElementById("kb-upload-file");
const kbUploadTitleEl = document.getElementById("kb-upload-title");
const kbUploadDescriptionEl = document.getElementById("kb-upload-description");
const kbUploadAutoInjectEl = document.getElementById("kb-upload-auto-inject-toggle");
const kbSuggestBtn = document.getElementById("kb-suggest-btn");
const kbUploadBtn = document.getElementById("kb-upload-btn");
const kbUploadStatusEl = document.getElementById("kb-upload-status");
const settingsStatus = document.getElementById("settings-status");
const settingsRestartBannerEl = document.getElementById("settings-restart-banner");
const settingsRestartBannerTextEl = document.getElementById("settings-restart-banner-text");
const saveButtons = Array.from(document.querySelectorAll(".settings-save-trigger"));
const dirtyPillEl = document.getElementById("settings-dirty-pill");
const statScratchpadEl = document.getElementById("settings-stat-scratchpad");
const statToolsEl = document.getElementById("settings-stat-tools");
const statRagEl = document.getElementById("settings-stat-rag");
const tabButtons = Array.from(document.querySelectorAll("[data-settings-tab]"));
const tabPanels = Array.from(document.querySelectorAll("[data-settings-panel]"));
const SETTINGS_TAB_ALIASES = {
  assistant: "general",
  memory: "context",
};

const RAG_SENSITIVITY_HINTS = {
  flexible: "Flexible: uses a lower threshold around 0.20, so broader and weaker matches may still be included when recall matters more than precision.",
  normal: "Normal: uses a balanced threshold around 0.35, which is usually the best tradeoff between relevant recall and prompt cleanliness.",
  strict: "Strict: uses a higher threshold around 0.55, so only stronger matches are injected and weak or tangential context is filtered out more aggressively.",
};

const RAG_SOURCE_TYPE_LABELS = {
  conversation: "Chats",
  tool_result: "Tool outputs",
  tool_memory: "Saved web/fetches",
  uploaded_document: "Uploaded documents",
};

const MODEL_PROVIDER_LABELS = {
  deepseek: "DeepSeek",
  openrouter: "OpenRouter",
};

const GENERAL_INSTRUCTION_TEMPLATES = [
  {
    id: "concise_default",
    label: "Concise default",
    text: "Be concise and direct. Prefer short paragraphs. Use bullets only when they improve scanning. State assumptions briefly and include the next step when useful.",
  },
  {
    id: "teaching_mode",
    label: "Teaching mode",
    text: "Explain clearly and step by step. Define non-obvious terms, surface the reasoning behind decisions, and include one concrete example when it materially helps understanding.",
  },
  {
    id: "engineering_review",
    label: "Engineering review",
    text: "Prioritize correctness, edge cases, regressions, and verification. Keep summaries brief and focus first on concrete findings, risks, and what changed.",
  },
  {
    id: "execution_first",
    label: "Execution first",
    text: "Take action by default instead of proposing abstract plans. Prefer minimal working changes, explain tradeoffs briefly, and avoid unnecessary theory.",
  },
];

const AI_PERSONALITY_TEMPLATES = [
  {
    id: "pragmatic_engineer",
    label: "Pragmatic engineer",
    text: "Adopt the voice of a pragmatic senior engineer: calm, direct, rigorous, and low-fluff. Challenge weak assumptions politely and stay focused on what will actually work.",
  },
  {
    id: "patient_teacher",
    label: "Patient teacher",
    text: "Sound like a patient technical teacher: structured, clear, encouraging without being overly casual, and attentive to knowledge gaps.",
  },
  {
    id: "analytical_strategist",
    label: "Analytical strategist",
    text: "Sound analytical and deliberate. Compare options clearly, explain tradeoffs, and make recommendations with explicit reasoning and constraints.",
  },
  {
    id: "creative_partner",
    label: "Creative partner",
    text: "Sound like a creative but disciplined collaborator: exploratory, idea-rich, and willing to suggest novel directions while staying grounded in the user's goal.",
  },
];

const DEFAULT_SCRATCHPAD_SECTION_ID = "notes";
const DEFAULT_SCRATCHPAD_SECTION_ORDER = [
  "lessons",
  "profile",
  "notes",
  "problems",
  "tasks",
  "preferences",
  "domain",
];
const DEFAULT_SCRATCHPAD_SECTION_META = {
  lessons: {
    title: "Lessons Learned",
    description: "Reliable takeaways, postmortems, and patterns that should change future decisions.",
  },
  profile: {
    title: "User Profile & Mindset",
    description: "Durable clues about how the user thinks, decides, and frames problems.",
  },
  notes: {
    title: "General Notes",
    description: "Durable general uncategorized context that does not fit the other sections.",
  },
  problems: {
    title: "Open Problems",
    description: "Recurring or durable unresolved issues worth revisiting across conversations.",
  },
  tasks: {
    title: "In-Progress Tasks",
    description: "Longer-running cross-conversation workstreams the assistant should preserve continuity on.",
  },
  preferences: {
    title: "User Preferences",
    description: "Stable language, formatting, and collaboration preferences.",
  },
  domain: {
    title: "Domain Facts",
    description: "Durable facts about the user's stack, systems, or technical domain.",
  },
};

function getCustomModelContract() {
  const contract = appSettings.custom_model_contract && typeof appSettings.custom_model_contract === "object"
    ? appSettings.custom_model_contract
    : {};

  return {
    provider: String(contract.provider || "openrouter"),
    model_prefix: String(contract.model_prefix || "openrouter:"),
    client_uid_prefix: String(contract.client_uid_prefix || "draft-custom-model:"),
    variant_separator: String(contract.variant_separator || "@@"),
    variant_part_separator: String(contract.variant_part_separator || ";"),
    variant_key_value_separator: String(contract.variant_key_value_separator || "="),
    provider_slug_pattern: String(contract.provider_slug_pattern || "^[a-z0-9][a-z0-9._/-]{0,199}$"),
    reasoning_modes: Array.isArray(contract.reasoning_modes) && contract.reasoning_modes.length
      ? contract.reasoning_modes.map((value) => String(value))
      : ["default", "enabled", "disabled"],
    reasoning_efforts: Array.isArray(contract.reasoning_efforts) && contract.reasoning_efforts.length
      ? contract.reasoning_efforts.map((value) => String(value))
      : ["minimal", "low", "medium", "high", "xhigh"],
  };
}

const builtinModelCatalog = Array.isArray(appSettings.available_models)
  ? appSettings.available_models.filter((model) => !Boolean(model?.is_custom))
  : [];

let hasUnsavedChanges = false;
let hasUnsavedSettingsChanges = false;
let hasUnsavedPersonaChanges = false;
let activePersonaId = null;
let activePersonaMemoryEntryId = null;
let isPersonaMemoryLoading = false;
let personaMemoryByPersonaId = {};
let draftCustomModels = Array.isArray(appSettings.custom_models)
  ? appSettings.custom_models.map((model) => normalizeDraftCustomModel(model))
  : [];
let draftChatModelRows = [];
let draftOperationFallbackRows = {};
let fallbackRowSequence = 0;
let customModelClientUidSequence = 0;
let editingCustomModelClientUid = null;

const OPERATION_MODEL_KEYS = ["summarize", "fetch_summarize", "prune", "fix_text", "generate_title", "upload_metadata", "sub_agent"];
const OPERATION_FALLBACK_CONTROL_MAP = {
  summarize: {
    listEl: summaryModelFallbackListEl,
    addBtn: summaryModelFallbackAddBtn,
  },
  fetch_summarize: {
    listEl: fetchSummarizeModelFallbackListEl,
    addBtn: fetchSummarizeModelFallbackAddBtn,
  },
  prune: {
    listEl: pruneModelFallbackListEl,
    addBtn: pruneModelFallbackAddBtn,
  },
  fix_text: {
    listEl: fixTextModelFallbackListEl,
    addBtn: fixTextModelFallbackAddBtn,
  },
  generate_title: {
    listEl: titleModelFallbackListEl,
    addBtn: titleModelFallbackAddBtn,
  },
  upload_metadata: {
    listEl: uploadMetadataModelFallbackListEl,
    addBtn: uploadMetadataModelFallbackAddBtn,
  },
  sub_agent: {
    listEl: subAgentModelFallbackListEl,
    addBtn: subAgentModelFallbackAddBtn,
  },
};

function autoResize(element) {
  if (!element) {
    return;
  }
  element.style.height = "auto";
  element.style.height = `${element.scrollHeight}px`;
}

function populateBehaviorTemplateSelect(selectEl, templates) {
  if (!selectEl) {
    return;
  }
  const fragment = document.createDocumentFragment();
  const placeholderOption = document.createElement("option");
  placeholderOption.value = "";
  placeholderOption.textContent = "Choose a template";
  fragment.append(placeholderOption);

  templates.forEach((template) => {
    const option = document.createElement("option");
    option.value = template.id;
    option.textContent = template.label;
    fragment.append(option);
  });

  selectEl.replaceChildren(fragment);
}

function getBehaviorTemplateById(templates, templateId) {
  return templates.find((template) => template.id === templateId) || null;
}

function applyBehaviorTemplate(selectEl, textareaEl, templates) {
  if (!selectEl || !textareaEl) {
    return;
  }
  const selectedTemplate = getBehaviorTemplateById(templates, selectEl.value);
  if (!selectedTemplate) {
    return;
  }
  textareaEl.value = selectedTemplate.text;
  autoResize(textareaEl);
  markPersonaDirty();
}

function initializeAssistantBehaviorTemplates() {
  populateBehaviorTemplateSelect(generalInstructionsTemplateSelectEl, GENERAL_INSTRUCTION_TEMPLATES);
  populateBehaviorTemplateSelect(aiPersonalityTemplateSelectEl, AI_PERSONALITY_TEMPLATES);
}

function normalizePersonaId(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function getPersonas() {
  return Array.isArray(appSettings.personas) ? appSettings.personas : [];
}

function findPersonaById(personaId) {
  const normalizedPersonaId = normalizePersonaId(personaId);
  if (!normalizedPersonaId) {
    return null;
  }
  return getPersonas().find((persona) => normalizePersonaId(persona?.id) === normalizedPersonaId) || null;
}

function describePersona(persona) {
  const generalInstructions = String(persona?.general_instructions || "")
    .split("\n")
    .map((value) => value.trim())
    .find(Boolean) || "";
  const aiPersonality = String(persona?.ai_personality || "")
    .split("\n")
    .map((value) => value.trim())
    .find(Boolean) || "";
  return generalInstructions || aiPersonality || "No persistent instructions yet.";
}

function setPersonaStatus(message, tone = "muted") {
  if (!personaStatusEl) {
    return;
  }
  personaStatusEl.textContent = message;
  personaStatusEl.dataset.tone = tone;
}

function setPersonaActionsDisabled(disabled) {
  if (personaSaveBtn) {
    personaSaveBtn.disabled = disabled;
  }
  if (personaDeleteBtn) {
    personaDeleteBtn.disabled = disabled || !activePersonaId;
  }
  if (personaNewBtn) {
    personaNewBtn.disabled = disabled;
  }
}

function normalizePersonaMemoryEntryId(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function normalizePersonaMemoryEntries(entries) {
  return (Array.isArray(entries) ? entries : [])
    .map((entry) => {
      const entryId = normalizePersonaMemoryEntryId(entry?.id);
      const key = String(entry?.key || "").trim();
      const value = String(entry?.value || "").trim();
      const createdAt = String(entry?.created_at || "").trim();
      if (!entryId || !key || !value) {
        return null;
      }
      return {
        id: entryId,
        key,
        value,
        created_at: createdAt,
      };
    })
    .filter(Boolean);
}

function getPersonaMemoryEntries(personaId = activePersonaId) {
  const normalizedPersonaId = normalizePersonaId(personaId);
  if (!normalizedPersonaId) {
    return [];
  }
  return Array.isArray(personaMemoryByPersonaId[normalizedPersonaId])
    ? personaMemoryByPersonaId[normalizedPersonaId]
    : [];
}

function setPersonaMemoryEntries(personaId, entries) {
  const normalizedPersonaId = normalizePersonaId(personaId);
  if (!normalizedPersonaId) {
    return [];
  }
  const normalizedEntries = normalizePersonaMemoryEntries(entries);
  personaMemoryByPersonaId[normalizedPersonaId] = normalizedEntries;
  return normalizedEntries;
}

function findPersonaMemoryEntryById(entryId, personaId = activePersonaId) {
  const normalizedEntryId = normalizePersonaMemoryEntryId(entryId);
  if (!normalizedEntryId) {
    return null;
  }
  return getPersonaMemoryEntries(personaId).find((entry) => entry.id === normalizedEntryId) || null;
}

function setPersonaMemoryStatus(message, tone = "muted") {
  if (!personaMemoryStatusEl) {
    return;
  }
  personaMemoryStatusEl.textContent = message;
  personaMemoryStatusEl.dataset.tone = tone;
}

function setPersonaMemoryControlsDisabled(disabled) {
  const noPersonaSelected = !normalizePersonaId(activePersonaId);
  if (personaMemoryKeyEl) {
    personaMemoryKeyEl.disabled = disabled || noPersonaSelected;
  }
  if (personaMemoryValueEl) {
    personaMemoryValueEl.disabled = disabled || noPersonaSelected;
  }
  if (personaMemorySaveBtn) {
    personaMemorySaveBtn.disabled = disabled || noPersonaSelected;
  }
  if (personaMemoryCancelBtn) {
    personaMemoryCancelBtn.disabled = disabled || noPersonaSelected || !activePersonaMemoryEntryId;
  }
  if (personaMemoryDeleteBtn) {
    personaMemoryDeleteBtn.disabled = disabled || noPersonaSelected || !activePersonaMemoryEntryId;
  }
}

function fillPersonaMemoryForm(entry) {
  if (personaMemoryKeyEl) {
    personaMemoryKeyEl.value = String(entry?.key || "");
  }
  if (personaMemoryValueEl) {
    personaMemoryValueEl.value = String(entry?.value || "");
    autoResize(personaMemoryValueEl);
  }
}

function resetPersonaMemoryEditor({ preserveStatus = false } = {}) {
  activePersonaMemoryEntryId = null;
  fillPersonaMemoryForm(null);
  if (personaMemorySaveBtn) {
    personaMemorySaveBtn.textContent = "Save memory";
  }
  if (personaMemoryCancelBtn) {
    personaMemoryCancelBtn.hidden = true;
  }
  if (personaMemoryDeleteBtn) {
    personaMemoryDeleteBtn.hidden = true;
  }
  if (!preserveStatus) {
    if (normalizePersonaId(activePersonaId)) {
      setPersonaMemoryStatus("Ready to add shared persona memory", "muted");
    } else {
      setPersonaMemoryStatus("Save the persona first to manage shared memory.", "muted");
    }
  }
  setPersonaMemoryControlsDisabled(isPersonaMemoryLoading);
}

function selectPersonaMemoryEntry(entryId) {
  const entry = findPersonaMemoryEntryById(entryId);
  if (!entry) {
    resetPersonaMemoryEditor();
    renderPersonaMemoryList();
    return;
  }

  activePersonaMemoryEntryId = entry.id;
  fillPersonaMemoryForm(entry);
  if (personaMemorySaveBtn) {
    personaMemorySaveBtn.textContent = "Update memory";
  }
  if (personaMemoryCancelBtn) {
    personaMemoryCancelBtn.hidden = false;
  }
  if (personaMemoryDeleteBtn) {
    personaMemoryDeleteBtn.hidden = false;
  }
  setPersonaMemoryStatus(`Editing memory: ${entry.key}`, "muted");
  renderPersonaMemoryList();
  setPersonaMemoryControlsDisabled(isPersonaMemoryLoading);
}

function renderPersonaMemoryList() {
  if (!personaMemoryListEl) {
    return;
  }

  const normalizedPersonaId = normalizePersonaId(activePersonaId);
  personaMemoryListEl.innerHTML = "";
  if (!normalizedPersonaId) {
    personaMemoryListEl.innerHTML = '<p class="settings-copy">Create or select a saved persona before editing shared persona memory.</p>';
    if (personaMemoryNoteEl) {
      personaMemoryNoteEl.textContent = "Use this for stable persona-scoped facts shared across conversations. Stored entries are not auto-pruned.";
    }
    return;
  }

  const entries = getPersonaMemoryEntries(normalizedPersonaId);
  if (!entries.length) {
    personaMemoryListEl.innerHTML = '<p class="settings-copy">No persona memory yet. Add short key-value entries that should follow this persona across conversations.</p>';
    if (personaMemoryNoteEl) {
      personaMemoryNoteEl.textContent = "Use this for stable persona-scoped facts shared across conversations. Stored entries are not auto-pruned.";
    }
    return;
  }

  if (personaMemoryNoteEl) {
    personaMemoryNoteEl.textContent = `${entries.length} shared persona memory entr${entries.length === 1 ? "y" : "ies"} currently stored. These entries are not auto-pruned.`;
  }

  entries.forEach((entry) => {
    const row = document.createElement("div");
    row.className = "model-management-row";
    if (entry.id === activePersonaMemoryEntryId) {
      row.classList.add("persona-row--active");
    }

    const meta = document.createElement("div");
    meta.className = "model-management-row__meta";

    const title = document.createElement("strong");
    title.textContent = entry.key;

    const subtitle = document.createElement("div");
    subtitle.className = "model-management-row__subtitle";
    subtitle.textContent = entry.value;

    meta.append(title, subtitle);

    const actions = document.createElement("div");
    actions.className = "settings-inline-actions";

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn-ghost";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", () => {
      selectPersonaMemoryEntry(entry.id);
    });

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "btn-ghost btn-ghost--danger";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", () => {
      void deleteActivePersonaMemoryEntry(entry.id);
    });

    actions.append(editBtn, deleteBtn);
    row.append(meta, actions);
    personaMemoryListEl.append(row);
  });
}

async function loadPersonaMemory(personaId, { force = false } = {}) {
  const normalizedPersonaId = normalizePersonaId(personaId);
  if (!normalizedPersonaId) {
    resetPersonaMemoryEditor();
    renderPersonaMemoryList();
    return [];
  }

  if (!force && Array.isArray(personaMemoryByPersonaId[normalizedPersonaId])) {
    renderPersonaMemoryList();
    if (normalizePersonaId(activePersonaId) === normalizedPersonaId) {
      const entries = getPersonaMemoryEntries(normalizedPersonaId);
      setPersonaMemoryStatus(entries.length ? "Persona memory ready" : "No persona memory yet", "muted");
    }
    setPersonaMemoryControlsDisabled(false);
    return getPersonaMemoryEntries(normalizedPersonaId);
  }

  isPersonaMemoryLoading = true;
  renderPersonaMemoryList();
  setPersonaMemoryControlsDisabled(true);
  setPersonaMemoryStatus("Loading persona memory...", "warning");

  try {
    const response = await fetch(`/api/personas/${normalizedPersonaId}/memory`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Failed to load persona memory.");
    }

    const entries = setPersonaMemoryEntries(normalizedPersonaId, data.persona_memory);
    if (normalizePersonaId(activePersonaId) === normalizedPersonaId) {
      renderPersonaMemoryList();
      setPersonaMemoryStatus(entries.length ? "Persona memory loaded" : "No persona memory yet", "muted");
    }
    return entries;
  } catch (error) {
    if (normalizePersonaId(activePersonaId) === normalizedPersonaId) {
      setPersonaMemoryStatus(error.message || "Failed to load persona memory.", "error");
    }
    return [];
  } finally {
    isPersonaMemoryLoading = false;
    setPersonaMemoryControlsDisabled(false);
  }
}

async function saveActivePersonaMemoryEntry() {
  const normalizedPersonaId = normalizePersonaId(activePersonaId);
  if (!normalizedPersonaId) {
    setPersonaMemoryStatus("Save the persona first to manage shared memory.", "warning");
    return false;
  }

  const payload = {
    key: personaMemoryKeyEl?.value.trim() || "",
    value: personaMemoryValueEl?.value.trim() || "",
  };
  const isUpdate = Boolean(activePersonaMemoryEntryId);
  if (!payload.key || !payload.value) {
    setPersonaMemoryStatus("Both memory key and value are required.", "error");
    return false;
  }

  setPersonaMemoryControlsDisabled(true);
  setPersonaMemoryStatus(isUpdate ? "Updating persona memory..." : "Saving persona memory...", "warning");

  try {
    const response = await fetch(
      isUpdate
        ? `/api/personas/${normalizedPersonaId}/memory/${activePersonaMemoryEntryId}`
        : `/api/personas/${normalizedPersonaId}/memory`,
      {
        method: isUpdate ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Persona memory save failed.");
    }

    setPersonaMemoryEntries(normalizedPersonaId, data.persona_memory);
    if (isUpdate && data.entry?.id) {
      selectPersonaMemoryEntry(data.entry.id);
    } else {
      resetPersonaMemoryEditor({ preserveStatus: true });
      renderPersonaMemoryList();
    }
    setPersonaMemoryStatus(isUpdate ? "Persona memory updated" : "Persona memory saved", "success");
    return true;
  } catch (error) {
    setPersonaMemoryStatus(error.message || "Persona memory save failed.", "error");
    return false;
  } finally {
    setPersonaMemoryControlsDisabled(false);
  }
}

async function deleteActivePersonaMemoryEntry(entryId = activePersonaMemoryEntryId) {
  const normalizedPersonaId = normalizePersonaId(activePersonaId);
  const entry = findPersonaMemoryEntryById(entryId, normalizedPersonaId);
  if (!normalizedPersonaId || !entry) {
    setPersonaMemoryStatus("Select a persona memory entry first.", "warning");
    return false;
  }

  if (!window.confirm(`Delete persona memory "${entry.key}"?`)) {
    return false;
  }

  setPersonaMemoryControlsDisabled(true);
  setPersonaMemoryStatus("Deleting persona memory...", "warning");

  try {
    const response = await fetch(`/api/personas/${normalizedPersonaId}/memory/${entry.id}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Persona memory delete failed.");
    }

    setPersonaMemoryEntries(normalizedPersonaId, data.persona_memory);
    resetPersonaMemoryEditor({ preserveStatus: true });
    renderPersonaMemoryList();
    setPersonaMemoryStatus(`Deleted persona memory: ${entry.key}`, "success");
    return true;
  } catch (error) {
    setPersonaMemoryStatus(error.message || "Persona memory delete failed.", "error");
    return false;
  } finally {
    setPersonaMemoryControlsDisabled(false);
  }
}

function renderDefaultPersonaSelect() {
  if (!defaultPersonaEl) {
    return;
  }
  const selectedDefaultPersonaId = normalizePersonaId(appSettings.default_persona_id);
  const fragment = document.createDocumentFragment();

  const emptyOption = document.createElement("option");
  emptyOption.value = "";
  emptyOption.textContent = "No default persona";
  fragment.append(emptyOption);

  getPersonas().forEach((persona) => {
    const option = document.createElement("option");
    option.value = String(persona.id);
    option.textContent = String(persona.name || `Persona ${persona.id}`).trim() || `Persona ${persona.id}`;
    fragment.append(option);
  });

  defaultPersonaEl.replaceChildren(fragment);
  defaultPersonaEl.value = selectedDefaultPersonaId ? String(selectedDefaultPersonaId) : "";
}

function fillPersonaForm(persona) {
  if (personaNameEl) {
    personaNameEl.value = String(persona?.name || "");
  }
  if (generalInstructionsEl) {
    generalInstructionsEl.value = String(persona?.general_instructions || "");
    autoResize(generalInstructionsEl);
  }
  if (aiPersonalityEl) {
    aiPersonalityEl.value = String(persona?.ai_personality || "");
    autoResize(aiPersonalityEl);
  }
}

function selectPersonaForEditing(personaId) {
  activePersonaId = normalizePersonaId(personaId);
  const persona = findPersonaById(activePersonaId);
  if (persona) {
    if (personaEditorTitleEl) {
      personaEditorTitleEl.textContent = `Edit ${persona.name}`;
    }
    if (personaSaveBtn) {
      personaSaveBtn.textContent = "Save persona";
    }
    if (personaDeleteBtn) {
      personaDeleteBtn.hidden = false;
    }
    fillPersonaForm(persona);
    setPersonaStatus(`Editing ${persona.name}`, "muted");
  } else {
    activePersonaId = null;
    if (personaEditorTitleEl) {
      personaEditorTitleEl.textContent = "Create persona";
    }
    if (personaSaveBtn) {
      personaSaveBtn.textContent = "Create persona";
    }
    if (personaDeleteBtn) {
      personaDeleteBtn.hidden = true;
    }
    fillPersonaForm(null);
    setPersonaStatus("Ready to create a persona", "muted");
  }
  clearPersonaDirty();
  renderPersonaList();
  setPersonaActionsDisabled(false);

  resetPersonaMemoryEditor({ preserveStatus: true });
  renderPersonaMemoryList();
  if (activePersonaId) {
    setPersonaMemoryStatus("Loading persona memory...", "warning");
    void loadPersonaMemory(activePersonaId);
  } else {
    setPersonaMemoryStatus("Save the persona first to manage shared memory.", "muted");
    setPersonaMemoryControlsDisabled(true);
  }
}

function renderPersonaList() {
  if (!personaListEl) {
    return;
  }

  const personas = getPersonas();
  personaListEl.innerHTML = "";
  if (!personas.length) {
    personaListEl.innerHTML = '<p class="settings-copy">No personas yet. Create one to define persistent tone and behavior.</p>';
    return;
  }

  const defaultPersonaId = normalizePersonaId(appSettings.default_persona_id);
  personas.forEach((persona) => {
    const row = document.createElement("div");
    row.className = "model-management-row";
    if (normalizePersonaId(persona.id) === activePersonaId) {
      row.classList.add("persona-row--active");
    }

    const meta = document.createElement("div");
    meta.className = "model-management-row__meta";

    const title = document.createElement("strong");
    title.textContent = String(persona.name || `Persona ${persona.id}`).trim() || `Persona ${persona.id}`;

    const subtitle = document.createElement("div");
    subtitle.className = "model-management-row__subtitle";
    subtitle.textContent = describePersona(persona);

    meta.append(title, subtitle);

    const badges = document.createElement("div");
    badges.className = "model-management-row__badges";
    if (normalizePersonaId(persona.id) === defaultPersonaId) {
      const badge = document.createElement("span");
      badge.className = "model-management-badge";
      badge.textContent = "Default";
      badges.append(badge);
    }
    if (badges.childElementCount) {
      meta.append(badges);
    }

    const actions = document.createElement("div");
    actions.className = "settings-inline-actions";

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn-ghost";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", () => {
      if (
        hasUnsavedPersonaChanges
        && normalizePersonaId(persona.id) !== activePersonaId
        && !window.confirm("Discard unsaved persona changes?")
      ) {
        return;
      }
      selectPersonaForEditing(persona.id);
    });

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "btn-ghost btn-ghost--danger";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", () => {
      if (
        hasUnsavedPersonaChanges
        && normalizePersonaId(persona.id) !== activePersonaId
        && !window.confirm("Discard unsaved persona changes?")
      ) {
        return;
      }
      selectPersonaForEditing(persona.id);
      void deleteActivePersona();
    });

    actions.append(editBtn, deleteBtn);
    row.append(meta, actions);
    personaListEl.append(row);
  });
}

function applyPersonaResponseData(data, { preserveSelection = true } = {}) {
  appSettings.personas = Array.isArray(data?.personas) ? data.personas : [];
  appSettings.default_persona_id = normalizePersonaId(data?.default_persona_id);
  const availablePersonaIds = new Set(
    getPersonas()
      .map((persona) => normalizePersonaId(persona?.id))
      .filter(Boolean),
  );
  Object.keys(personaMemoryByPersonaId).forEach((personaId) => {
    if (!availablePersonaIds.has(normalizePersonaId(personaId))) {
      delete personaMemoryByPersonaId[personaId];
    }
  });
  renderDefaultPersonaSelect();

  const responsePersonaId = normalizePersonaId(data?.persona?.id);
  const nextPersonaId = responsePersonaId || (preserveSelection ? activePersonaId : null);
  if (nextPersonaId && findPersonaById(nextPersonaId)) {
    selectPersonaForEditing(nextPersonaId);
    return;
  }
  if (getPersonas().length) {
    selectPersonaForEditing(getPersonas()[0].id);
    return;
  }
  selectPersonaForEditing(null);
}

function collectPersonaFormPayload() {
  return {
    name: personaNameEl?.value.trim() || "",
    general_instructions: generalInstructionsEl?.value.trim() || "",
    ai_personality: aiPersonalityEl?.value.trim() || "",
  };
}

async function saveActivePersona() {
  const payload = collectPersonaFormPayload();
  const isUpdate = Boolean(activePersonaId);
  if (!payload.name) {
    setPersonaStatus("Persona name is required.", "error");
    return false;
  }

  setPersonaActionsDisabled(true);
  setPersonaStatus(isUpdate ? "Saving persona..." : "Creating persona...", "warning");

  try {
    const response = await fetch(activePersonaId ? `/api/personas/${activePersonaId}` : "/api/personas", {
      method: isUpdate ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Persona save failed.");
    }

    applyPersonaResponseData(data, { preserveSelection: false });
    clearPersonaDirty();
    setPersonaStatus(isUpdate ? "Persona saved" : "Persona created", "success");
    return true;
  } catch (error) {
    setPersonaStatus(error.message || "Persona save failed.", "error");
    return false;
  } finally {
    setPersonaActionsDisabled(false);
  }
}

async function deleteActivePersona() {
  const persona = findPersonaById(activePersonaId);
  if (!persona) {
    setPersonaStatus("Select a persona first.", "warning");
    return false;
  }
  if (!window.confirm(`Delete persona \"${persona.name}\"?`)) {
    return false;
  }

  setPersonaActionsDisabled(true);
  setPersonaStatus("Deleting persona...", "warning");

  try {
    const response = await fetch(`/api/personas/${persona.id}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Persona delete failed.");
    }

    applyPersonaResponseData(data, { preserveSelection: false });
    clearPersonaDirty();
    setPersonaStatus(`${persona.name} deleted`, "success");
    return true;
  } catch (error) {
    setPersonaStatus(error.message || "Persona delete failed.", "error");
    return false;
  } finally {
    setPersonaActionsDisabled(false);
  }
}

async function saveAllSettings() {
  if (hasUnsavedPersonaChanges) {
    const personaSaved = await saveActivePersona();
    if (!personaSaved) {
      return;
    }
  }
  if (hasUnsavedSettingsChanges) {
    await saveSettings();
  }
}

function setSettingsStatus(message, tone = "muted") {
  if (!settingsStatus) {
    return;
  }
  settingsStatus.textContent = message;
  settingsStatus.dataset.tone = tone;
}

function setDirtyPill(message, tone = "muted") {
  if (!dirtyPillEl) {
    return;
  }
  dirtyPillEl.textContent = message;
  dirtyPillEl.dataset.tone = tone;
}

const RESTART_REQUIRED_SETTING_KEYS = [
  "openrouter_http_referer",
  "openrouter_app_title",
  "login_session_timeout_minutes",
  "login_max_failed_attempts",
  "login_lockout_seconds",
  "login_remember_session_days",
  "rag_enabled",
  "ocr_enabled",
  "ocr_provider",
  "conversation_memory_enabled",
  "youtube_transcripts_enabled",
  "youtube_transcript_language",
  "youtube_transcript_model_size",
  "chat_summary_model",
  "rag_chunk_size",
  "rag_chunk_overlap",
  "rag_max_chunks_per_source",
  "rag_search_top_k",
  "rag_search_min_similarity",
  "rag_query_expansion_enabled",
  "rag_query_expansion_max_variants",
  "tool_memory_ttl_default_seconds",
  "tool_memory_ttl_web_seconds",
  "tool_memory_ttl_news_seconds",
  "fetch_raw_max_text_chars",
  "fetch_summary_max_chars",
];

function valueAsComparableString(value) {
  if (Array.isArray(value) || (value && typeof value === "object")) {
    return JSON.stringify(value);
  }
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

function hasRestartRequiredChanges(payload, previousSettings) {
  return RESTART_REQUIRED_SETTING_KEYS.some((key) => valueAsComparableString(payload[key]) !== valueAsComparableString(previousSettings?.[key]));
}

function showRestartWarning(message) {
  if (!settingsRestartBannerEl) {
    return;
  }
  if (settingsRestartBannerTextEl) {
    settingsRestartBannerTextEl.textContent = message;
  }
  settingsRestartBannerEl.hidden = false;
}

function hideRestartWarning() {
  if (!settingsRestartBannerEl) {
    return;
  }
  settingsRestartBannerEl.hidden = true;
}

function updateDirtyIndicators() {
  hasUnsavedChanges = hasUnsavedSettingsChanges || hasUnsavedPersonaChanges;
  if (hasUnsavedSettingsChanges && hasUnsavedPersonaChanges) {
    setSettingsStatus("Unsaved settings and persona", "warning");
    setDirtyPill("Unsaved settings and persona", "warning");
    return;
  }
  if (hasUnsavedSettingsChanges) {
    setSettingsStatus("Unsaved changes", "warning");
    setDirtyPill("Unsaved changes", "warning");
    return;
  }
  if (hasUnsavedPersonaChanges) {
    setSettingsStatus("Unsaved persona draft", "warning");
    setDirtyPill("Unsaved persona draft", "warning");
    return;
  }
  setSettingsStatus("Saved", "success");
  setDirtyPill("All changes saved", "success");
}

function markDirty() {
  hasUnsavedSettingsChanges = true;
  updateDirtyIndicators();
}

function clearDirtyState() {
  hasUnsavedSettingsChanges = false;
  updateDirtyIndicators();
}

function markPersonaDirty() {
  hasUnsavedPersonaChanges = true;
  updateDirtyIndicators();
}

function clearPersonaDirty() {
  hasUnsavedPersonaChanges = false;
  updateDirtyIndicators();
}

function normalizeScratchpadNote(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeScratchpadNotesList(values) {
  const notes = [];
  const seen = new Set();
  for (const value of Array.isArray(values) ? values : []) {
    const note = normalizeScratchpadNote(value);
    if (!note || seen.has(note)) {
      continue;
    }
    seen.add(note);
    notes.push(note);
  }
  return notes;
}

function splitScratchpadContent(value) {
  return normalizeScratchpadNotesList(
    String(value || "")
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n")
      .split("\n")
  );
}

function getScratchpadSectionPayloads() {
  const serverSections = appSettings.scratchpad_sections && typeof appSettings.scratchpad_sections === "object"
    ? appSettings.scratchpad_sections
    : {};

  return DEFAULT_SCRATCHPAD_SECTION_ORDER.map((sectionId) => {
    const fallback = DEFAULT_SCRATCHPAD_SECTION_META[sectionId] || { title: sectionId, description: "" };
    const serverSection = serverSections[sectionId] && typeof serverSections[sectionId] === "object"
      ? serverSections[sectionId]
      : {};
    return {
      id: sectionId,
      title: String(serverSection.title || fallback.title || sectionId),
      description: String(serverSection.description || fallback.description || ""),
      content: String(serverSection.content || ""),
      note_count: Number.isFinite(serverSection.note_count) ? serverSection.note_count : 0,
    };
  });
}

function getScratchpadSectionsFromSettings() {
  const sections = {};
  getScratchpadSectionPayloads().forEach((section) => {
    sections[section.id] = splitScratchpadContent(section.content);
  });

  if (!Object.values(sections).some((notes) => notes.length)) {
    sections[DEFAULT_SCRATCHPAD_SECTION_ID] = splitScratchpadContent(appSettings.scratchpad || "");
  }

  return sections;
}

function readNumericSetting(element, defaultValue, { allowZero = true, min = null, max = null } = {}) {
  if (!element) {
    return defaultValue;
  }
  const rawValue = String(element.value || "").trim();
  if (!rawValue) {
    return defaultValue;
  }
  const parsed = Number.parseInt(rawValue, 10);
  if (Number.isNaN(parsed)) {
    return defaultValue;
  }
  if (!allowZero && parsed === 0) {
    return defaultValue;
  }
  const resolvedMin = Number.isFinite(min)
    ? min
    : (String(element.min || "").trim() ? Number.parseInt(element.min, 10) : null);
  const resolvedMax = Number.isFinite(max)
    ? max
    : (String(element.max || "").trim() ? Number.parseInt(element.max, 10) : null);
  let value = parsed;
  if (Number.isFinite(resolvedMin)) {
    value = Math.max(Number(resolvedMin), value);
  }
  if (Number.isFinite(resolvedMax)) {
    value = Math.min(Number(resolvedMax), value);
  }
  return value;
}

function readFloatSetting(element, defaultValue, { min = -Infinity, max = Infinity } = {}) {
  if (!element) {
    return defaultValue;
  }
  const rawValue = String(element.value || "").trim();
  if (!rawValue) {
    return defaultValue;
  }
  const parsed = Number.parseFloat(rawValue);
  if (Number.isNaN(parsed)) {
    return defaultValue;
  }
  return Math.min(max, Math.max(min, parsed));
}

function setCustomModelStatus(message, tone = "muted") {
  if (!customModelStatusEl) {
    return;
  }
  customModelStatusEl.textContent = message;
  customModelStatusEl.dataset.tone = tone;
}

function normalizeOpenRouterApiModel(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return "";
  }
  const { model_prefix: modelPrefix } = getCustomModelContract();
  if (rawValue.startsWith(modelPrefix)) {
    return rawValue.slice(modelPrefix.length).replace(/^\/+/, "").trim();
  }
  return rawValue.replace(/^\/+/, "").trim();
}

function splitOpenRouterModelId(value) {
  const normalizedValue = normalizeOpenRouterApiModel(value);
  if (!normalizedValue) {
    return { apiModel: "", variantSuffix: "" };
  }

  const { variant_separator: variantSeparator } = getCustomModelContract();
  const separatorIndex = normalizedValue.indexOf(variantSeparator);
  if (separatorIndex < 0) {
    return { apiModel: normalizedValue, variantSuffix: "" };
  }

  return {
    apiModel: normalizedValue.slice(0, separatorIndex),
    variantSuffix: normalizedValue.slice(separatorIndex + variantSeparator.length),
  };
}

function parseOpenRouterModelVariantSuffix(value) {
  const {
    variant_part_separator: variantPartSeparator,
    variant_key_value_separator: variantKeyValueSeparator,
  } = getCustomModelContract();
  const parsed = {
    reasoning_mode: "default",
    reasoning_effort: "",
    provider_slug: "",
    supports_tools: undefined,
    supports_vision: undefined,
    supports_structured_outputs: undefined,
  };

  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return parsed;
  }

  rawValue.split(variantPartSeparator).forEach((part) => {
    const separatorIndex = part.indexOf(variantKeyValueSeparator);
    if (separatorIndex < 0) {
      return;
    }
    const key = part.slice(0, separatorIndex).trim().toLowerCase();
    const partValue = part.slice(separatorIndex + 1).trim();
    if (!partValue) {
      return;
    }

    if (key === "r") {
      const [modeValue, effortValue = ""] = partValue.split(":", 2);
      const reasoning = normalizeOpenRouterReasoningConfig(modeValue, effortValue);
      parsed.reasoning_mode = reasoning.mode;
      parsed.reasoning_effort = reasoning.effort;
    } else if (key === "p") {
      parsed.provider_slug = normalizeOpenRouterProviderSlug(partValue);
    } else if (key === "t") {
      parsed.supports_tools = !["0", "false", "no", "off"].includes(partValue.toLowerCase());
    } else if (key === "v") {
      parsed.supports_vision = ["1", "true", "yes", "on"].includes(partValue.toLowerCase());
    } else if (key === "s") {
      parsed.supports_structured_outputs = ["1", "true", "yes", "on"].includes(partValue.toLowerCase());
    }
  });

  return parsed;
}
function normalizeOpenRouterProviderSlug(value) {
  const rawValue = String(value || "").trim().replace(/^\/+|\/+$/g, "").toLowerCase();
  if (!rawValue) {
    return "";
  }
  try {
    const pattern = new RegExp(getCustomModelContract().provider_slug_pattern);
    return pattern.test(rawValue) ? rawValue : "";
  } catch {
    return /^[a-z0-9][a-z0-9._/-]{0,199}$/.test(rawValue) ? rawValue : "";
  }
}

function normalizeOpenRouterReasoningMode(value) {
  const { reasoning_modes: reasoningModes } = getCustomModelContract();
  const fallbackMode = reasoningModes.includes("default") ? "default" : (reasoningModes[0] || "default");
  if (typeof value === "boolean") {
    const boolMode = value ? "enabled" : "disabled";
    return reasoningModes.includes(boolMode) ? boolMode : fallbackMode;
  }
  const rawValue = String(value || "").trim().toLowerCase();
  if (["enabled", "1", "true", "yes", "on"].includes(rawValue)) {
    return reasoningModes.includes("enabled") ? "enabled" : fallbackMode;
  }
  if (["disabled", "0", "false", "no", "off"].includes(rawValue)) {
    return reasoningModes.includes("disabled") ? "disabled" : fallbackMode;
  }
  return reasoningModes.includes(rawValue) ? rawValue : fallbackMode;
}

function normalizeOpenRouterReasoningEffort(value) {
  const rawValue = String(value || "").trim().toLowerCase();
  return getCustomModelContract().reasoning_efforts.includes(rawValue) ? rawValue : "";
}

function normalizeOpenRouterReasoningConfig(modeValue, effortValue) {
  const rawEffort = String(effortValue || "").trim().toLowerCase();
  if (rawEffort === "none") {
    return { mode: "disabled", effort: "" };
  }

  let mode = normalizeOpenRouterReasoningMode(modeValue);
  let effort = normalizeOpenRouterReasoningEffort(rawEffort);

  if (mode === "default" && effort) {
    mode = "enabled";
  }
  if (mode !== "enabled") {
    effort = "";
  }
  return { mode, effort };
}

function normalizeCustomModelClientUid(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return "";
  }

  const { client_uid_prefix: clientUidPrefix } = getCustomModelContract();
  return rawValue.startsWith(clientUidPrefix) ? rawValue : "";
}

function createCustomModelClientUid() {
  const { client_uid_prefix: clientUidPrefix } = getCustomModelContract();
  customModelClientUidSequence += 1;
  return `${clientUidPrefix}${customModelClientUidSequence}`;
}

function getDraftCustomModelReference(model) {
  return String(model?.client_uid || model?.id || "").trim();
}

function getDraftCustomModelSignature(model) {
  const normalizedModel = normalizeDraftCustomModel(model);
  return JSON.stringify({
    api_model: String(normalizedModel?.api_model || ""),
    provider_slug: String(normalizedModel?.provider_slug || ""),
    reasoning_mode: String(normalizedModel?.reasoning_mode || "default"),
    reasoning_effort: String(normalizedModel?.reasoning_effort || ""),
    supports_tools: Boolean(normalizedModel?.supports_tools ?? true),
    supports_vision: Boolean(normalizedModel?.supports_vision ?? false),
    supports_structured_outputs: Boolean(normalizedModel?.supports_structured_outputs ?? false),
  });
}

function normalizeDraftCustomModel(model) {
  const persistedModelId = String(model?.id || "").trim();
  const explicitApiModel = normalizeOpenRouterApiModel(model?.api_model || model?.model || "");
  const shouldParseLegacyIdentity = (
    !explicitApiModel
    || model?.reasoning_mode === undefined
    || model?.reasoning_enabled === undefined
    || model?.reasoning_effort === undefined
    || model?.provider_slug === undefined
    || model?.openrouter_provider === undefined
    || model?.supports_tools === undefined
    || model?.supports_vision === undefined
    || model?.supports_structured_outputs === undefined
  );
  const parsedIdentity = shouldParseLegacyIdentity
    ? splitOpenRouterModelId(model?.id || model?.api_model || model?.model || "")
    : { apiModel: "", variantSuffix: "" };
  const parsedVariant = shouldParseLegacyIdentity
    ? parseOpenRouterModelVariantSuffix(parsedIdentity.variantSuffix)
    : {};
  const apiModel = explicitApiModel || normalizeOpenRouterApiModel(parsedIdentity.apiModel || "");
  const reasoning = normalizeOpenRouterReasoningConfig(
    model?.reasoning_mode ?? model?.reasoning_enabled ?? parsedVariant.reasoning_mode,
    model?.reasoning_effort ?? parsedVariant.reasoning_effort
  );
  const providerSlug = normalizeOpenRouterProviderSlug(model?.provider_slug || model?.openrouter_provider || parsedVariant.provider_slug || "");
  const supportsTools = model?.supports_tools !== undefined ? Boolean(model.supports_tools) : (parsedVariant.supports_tools ?? true);
  const supportsVision = model?.supports_vision !== undefined ? Boolean(model.supports_vision) : (parsedVariant.supports_vision ?? false);
  const supportsStructuredOutputs = model?.supports_structured_outputs !== undefined
    ? Boolean(model.supports_structured_outputs)
    : (parsedVariant.supports_structured_outputs ?? false);
  const clientUid = normalizeCustomModelClientUid(model?.client_uid) || persistedModelId || createCustomModelClientUid();
  return {
    ...model,
    id: persistedModelId,
    client_uid: clientUid,
    name: String(model?.name || apiModel || persistedModelId || clientUid).trim() || apiModel || persistedModelId || clientUid,
    provider: String(model?.provider || getCustomModelContract().provider || "openrouter"),
    api_model: apiModel,
    provider_slug: providerSlug,
    reasoning_mode: reasoning.mode,
    reasoning_effort: reasoning.effort,
    supports_tools: supportsTools,
    supports_vision: supportsVision,
    supports_structured_outputs: supportsStructuredOutputs,
    is_custom: true,
  };
}

function serializeDraftCustomModel(model) {
  const normalizedModel = normalizeDraftCustomModel(model);
  return {
    client_uid: getDraftCustomModelReference(normalizedModel),
    name: String(normalizedModel?.name || normalizedModel?.api_model || "").trim(),
    api_model: String(normalizedModel?.api_model || "").trim(),
    provider_slug: String(normalizedModel?.provider_slug || "").trim(),
    reasoning_mode: String(normalizedModel?.reasoning_mode || "default"),
    reasoning_effort: String(normalizedModel?.reasoning_effort || ""),
    supports_tools: Boolean(normalizedModel?.supports_tools ?? true),
    supports_vision: Boolean(normalizedModel?.supports_vision ?? false),
    supports_structured_outputs: Boolean(normalizedModel?.supports_structured_outputs ?? false),
  };
}

function getCustomModelReasoningLabel(model) {
  if (model?.reasoning_mode === "disabled") {
    return "reasoning off";
  }
  if (model?.reasoning_mode === "enabled") {
    return model?.reasoning_effort ? `reasoning ${model.reasoning_effort}` : "reasoning on";
  }
  return "reasoning default";
}

function syncCustomModelReasoningControls() {
  if (!customModelReasoningModeEl || !customModelReasoningEffortEl) {
    return;
  }
  customModelReasoningEffortEl.disabled = customModelReasoningModeEl.value !== "enabled";
}

function syncCustomModelProviderControls() {
  const routingMode = customModelRoutingModeEl?.value || "auto";
  const specificProviderEnabled = routingMode === "specific";

  if (customModelProviderFieldEl) {
    customModelProviderFieldEl.hidden = !specificProviderEnabled;
  }
  if (customModelProviderSlugEl) {
    customModelProviderSlugEl.disabled = !specificProviderEnabled;
  }
}

function readCustomModelProviderSlug() {
  const routingMode = customModelRoutingModeEl?.value || "auto";
  if (routingMode !== "specific") {
    return { providerSlug: "", error: "" };
  }

  const rawProviderSlug = String(customModelProviderSlugEl?.value || "").trim();
  if (!rawProviderSlug) {
    return {
      providerSlug: "",
      error: "Choose a provider slug or switch routing back to automatic.",
    };
  }

  const providerSlug = normalizeOpenRouterProviderSlug(rawProviderSlug);
  if (!providerSlug) {
    return {
      providerSlug: "",
      error: "Provider slug is invalid. Use a value like anthropic, azure, or deepinfra/turbo.",
    };
  }

  return { providerSlug, error: "" };
}

function getDraftAvailableModels() {
  const customModelCatalog = draftCustomModels.map((model) => ({
    ...model,
    id: getDraftCustomModelReference(model),
  }));
  return [...builtinModelCatalog, ...customModelCatalog].map((model) => ({ ...model }));
}

function getDraftChatCapableModels() {
  return getDraftAvailableModels().filter((model) => Boolean(model?.supports_tools));
}

function getModelProviderLabel(model) {
  return MODEL_PROVIDER_LABELS[String(model?.provider || "").trim()] || String(model?.provider || "model");
}

function getOperationPreferenceValue(key) {
  const defaults = appSettings.operation_model_preferences || {};
  const elementMap = {
    summarize: summaryModelPreferenceEl,
    fetch_summarize: fetchSummarizeModelPreferenceEl,
    prune: pruneModelPreferenceEl,
    fix_text: fixTextModelPreferenceEl,
    generate_title: titleModelPreferenceEl,
    upload_metadata: uploadMetadataModelPreferenceEl,
    sub_agent: subAgentModelPreferenceEl,
  };
  const el = elementMap[key];
  return el ? String(el.value || "") : String(defaults[key] || "");
}

function getOperationModelPreferencesDraft() {
  return {
    summarize: getOperationPreferenceValue("summarize"),
    fetch_summarize: getOperationPreferenceValue("fetch_summarize"),
    prune: getOperationPreferenceValue("prune"),
    fix_text: getOperationPreferenceValue("fix_text"),
    generate_title: getOperationPreferenceValue("generate_title"),
    upload_metadata: getOperationPreferenceValue("upload_metadata"),
    sub_agent: getOperationPreferenceValue("sub_agent"),
  };
}

function createOperationFallbackRow(modelId = "") {
  return {
    id: `operation-fallback-${fallbackRowSequence += 1}`,
    modelId: String(modelId || "").trim(),
  };
}

function normalizeOperationFallbackRows(rawValue) {
  if (Array.isArray(rawValue)) {
    return rawValue.map((modelId) => createOperationFallbackRow(modelId));
  }
  if (typeof rawValue === "string" && rawValue.trim()) {
    return [createOperationFallbackRow(rawValue)];
  }
  return [];
}

function initializeOperationFallbackDraftRows(rawPreferences) {
  const preferences = rawPreferences && typeof rawPreferences === "object" ? rawPreferences : {};
  const nextRows = {};
  OPERATION_MODEL_KEYS.forEach((key) => {
    nextRows[key] = normalizeOperationFallbackRows(preferences[key]);
  });
  draftOperationFallbackRows = nextRows;
}

function getDraftOperationFallbackRows(operationKey) {
  return Array.isArray(draftOperationFallbackRows[operationKey]) ? draftOperationFallbackRows[operationKey] : [];
}

function addOperationFallbackRow(operationKey, modelId = "") {
  const rows = [...getDraftOperationFallbackRows(operationKey), createOperationFallbackRow(modelId)];
  draftOperationFallbackRows = {
    ...draftOperationFallbackRows,
    [operationKey]: rows,
  };
  renderModelManagementPanels();
  markDirty();
}

function removeOperationFallbackRow(operationKey, rowId) {
  const rows = getDraftOperationFallbackRows(operationKey).filter((row) => row.id !== rowId);
  draftOperationFallbackRows = {
    ...draftOperationFallbackRows,
    [operationKey]: rows,
  };
  renderModelManagementPanels();
  markDirty();
}

function moveOperationFallbackRow(operationKey, rowIndex, direction) {
  const rows = [...getDraftOperationFallbackRows(operationKey)];
  const nextIndex = rowIndex + direction;
  if (nextIndex < 0 || nextIndex >= rows.length) {
    return;
  }
  const [row] = rows.splice(rowIndex, 1);
  rows.splice(nextIndex, 0, row);
  draftOperationFallbackRows = {
    ...draftOperationFallbackRows,
    [operationKey]: rows,
  };
  renderModelManagementPanels();
  markDirty();
}

function setOperationFallbackRowModel(operationKey, rowId, modelId) {
  const rows = getDraftOperationFallbackRows(operationKey).map((row) => (
    row.id === rowId
      ? { ...row, modelId: String(modelId || "").trim() }
      : row
  ));
  draftOperationFallbackRows = {
    ...draftOperationFallbackRows,
    [operationKey]: rows,
  };
  markDirty();
}

function renderOperationFallbackList(operationKey) {
  const controls = OPERATION_FALLBACK_CONTROL_MAP[operationKey];
  if (!controls?.listEl) {
    return;
  }

  const listEl = controls.listEl;
  const rows = getDraftOperationFallbackRows(operationKey);
  listEl.replaceChildren();

  if (!rows.length) {
    const emptyState = document.createElement("p");
    emptyState.className = "settings-copy";
    emptyState.textContent = "No fallback models added yet.";
    listEl.append(emptyState);
    return;
  }

  rows.forEach((rowState, index) => {
    const row = document.createElement("div");
    row.className = "model-management-row";

    const select = document.createElement("select");
    select.className = "settings-select";
    populateOperationModelSelect(select, rowState.modelId, "Use built-in fallback");
    if (select.value !== rowState.modelId) {
      rowState.modelId = select.value;
    }
    select.addEventListener("change", () => {
      setOperationFallbackRowModel(operationKey, rowState.id, select.value);
    });

    const actions = document.createElement("div");
    actions.className = "settings-inline-actions";

    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "btn-ghost";
    upBtn.textContent = "Up";
    upBtn.disabled = index === 0;
    upBtn.addEventListener("click", () => moveOperationFallbackRow(operationKey, index, -1));

    const downBtn = document.createElement("button");
    downBtn.type = "button";
    downBtn.className = "btn-ghost";
    downBtn.textContent = "Down";
    downBtn.disabled = index === rows.length - 1;
    downBtn.addEventListener("click", () => moveOperationFallbackRow(operationKey, index, 1));

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-ghost btn-ghost--danger";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => removeOperationFallbackRow(operationKey, rowState.id));

    actions.append(upBtn, downBtn, removeBtn);
    row.append(select, actions);
    listEl.append(row);
  });
}

function renderOperationFallbackLists() {
  OPERATION_MODEL_KEYS.forEach((operationKey) => {
    renderOperationFallbackList(operationKey);
  });
}

function getOperationModelFallbackPreferencesDraft() {
  const preferences = {};
  OPERATION_MODEL_KEYS.forEach((operationKey) => {
    const rows = getDraftOperationFallbackRows(operationKey)
      .map((row) => String(row.modelId || "").trim())
      .filter((modelId) => Boolean(modelId));
    preferences[operationKey] = [...new Set(rows)];
  });
  return preferences;
}

function syncDraftChatModelRows({ preferVisibleId = "" } = {}) {
  const candidates = getDraftChatCapableModels();
  const candidateMap = new Map(candidates.map((model) => [model.id, model]));
  const initialVisible = new Set(Array.isArray(appSettings.visible_model_order) ? appSettings.visible_model_order : []);
  const nextRows = Array.isArray(draftChatModelRows)
    ? draftChatModelRows.filter((row) => candidateMap.has(row.id)).map((row) => ({ ...row }))
    : [];
  const knownIds = new Set(nextRows.map((row) => row.id));

  for (const model of candidates) {
    if (knownIds.has(model.id)) {
      continue;
    }
    nextRows.push({
      id: model.id,
      visible: preferVisibleId ? model.id === preferVisibleId : initialVisible.has(model.id),
    });
    knownIds.add(model.id);
  }

  if (!nextRows.length) {
    draftChatModelRows = [];
    return;
  }

  if (!nextRows.some((row) => row.visible)) {
    nextRows[0].visible = true;
  }

  draftChatModelRows = nextRows;
}

function getDraftVisibleModelOrder() {
  return draftChatModelRows.filter((row) => row.visible).map((row) => row.id);
}

function renderCustomModelList() {
  if (!customModelListEl) {
    return;
  }

  customModelListEl.replaceChildren();
  if (!draftCustomModels.length) {
    const emptyState = document.createElement("p");
    emptyState.className = "settings-copy";
    emptyState.textContent = "No custom models configured yet.";
    customModelListEl.append(emptyState);
    return;
  }

  for (const model of draftCustomModels) {
    const row = document.createElement("div");
    row.className = "model-management-row";
    if (editingCustomModelClientUid && editingCustomModelClientUid === model.client_uid) {
      row.classList.add("custom-model-row--editing");
    }

    const meta = document.createElement("div");
    meta.className = "model-management-row__meta";

    const title = document.createElement("strong");
    title.textContent = model.name || model.api_model || model.id || model.client_uid;

    const subtitle = document.createElement("div");
    subtitle.className = "model-management-row__subtitle";
    subtitle.textContent = [model.api_model || model.id || model.client_uid, model.provider_slug ? `Route: ${model.provider_slug}` : ""]
      .filter(Boolean)
      .join(" · ");

    const badges = document.createElement("div");
    badges.className = "model-management-row__badges";
    [
      getModelProviderLabel(model),
      model.provider_slug ? `route ${model.provider_slug}` : null,
      getCustomModelReasoningLabel(model),
      model.supports_tools ? "tools" : "no tools",
      model.supports_vision ? "vision" : "text-only",
      model.supports_structured_outputs ? "structured" : "freeform",
    ].forEach((label) => {
      if (!label) {
        return;
      }
      const badge = document.createElement("span");
      badge.className = "model-management-badge";
      badge.textContent = label;
      badges.append(badge);
    });

    meta.append(title, subtitle, badges);

    const actions = document.createElement("div");
    actions.className = "settings-inline-actions";

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn-ghost";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", () => {
      startEditingCustomModel(model.client_uid);
    });

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-ghost btn-ghost--danger";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => {
      const wasEditing = editingCustomModelClientUid === model.client_uid;
      draftCustomModels = draftCustomModels.filter((entry) => entry.client_uid !== model.client_uid);
      if (wasEditing) {
        cancelEditingCustomModel({ silent: true });
      }
      syncDraftChatModelRows();
      renderModelManagementPanels();
      markDirty();
      setCustomModelStatus("Custom model removed. Save to apply.", "warning");
    });

    actions.append(editBtn, removeBtn);
    row.append(meta, actions);
    customModelListEl.append(row);
  }
}

function fillCustomModelForm(model) {
  if (customModelNameEl) {
    customModelNameEl.value = String(model?.name || "");
  }
  if (customModelApiModelEl) {
    customModelApiModelEl.value = String(model?.api_model || model?.id || "");
  }
  if (customModelRoutingModeEl) {
    customModelRoutingModeEl.value = model?.provider_slug ? "specific" : "auto";
  }
  if (customModelProviderSlugEl) {
    customModelProviderSlugEl.value = String(model?.provider_slug || "");
  }
  if (customModelReasoningModeEl) {
    customModelReasoningModeEl.value = String(model?.reasoning_mode || "default");
  }
  if (customModelReasoningEffortEl) {
    customModelReasoningEffortEl.value = String(model?.reasoning_effort || "");
  }
  if (customModelSupportsToolsEl) {
    customModelSupportsToolsEl.checked = Boolean(model?.supports_tools ?? true);
  }
  if (customModelSupportsVisionEl) {
    customModelSupportsVisionEl.checked = Boolean(model?.supports_vision ?? false);
  }
  if (customModelSupportsStructuredEl) {
    customModelSupportsStructuredEl.checked = Boolean(model?.supports_structured_outputs ?? false);
  }
  syncCustomModelReasoningControls();
  syncCustomModelProviderControls();
}

function updateCustomModelEditControls() {
  if (addCustomModelBtn) {
    addCustomModelBtn.textContent = editingCustomModelClientUid ? "Update model" : "Add custom model";
  }
  if (customModelCancelEditBtn) {
    customModelCancelEditBtn.hidden = !editingCustomModelClientUid;
  }
}

function startEditingCustomModel(modelClientUid) {
  const model = draftCustomModels.find((entry) => entry.client_uid === modelClientUid);
  if (!model) {
    return;
  }
  editingCustomModelClientUid = model.client_uid;
  fillCustomModelForm(model);
  updateCustomModelEditControls();
  renderCustomModelList();
  setCustomModelStatus(`Editing ${model.name || model.api_model || model.client_uid}.`, "muted");
}

function cancelEditingCustomModel({ silent = false } = {}) {
  editingCustomModelClientUid = null;
  resetCustomModelForm();
  updateCustomModelEditControls();
  renderCustomModelList();
  if (!silent) {
    setCustomModelStatus("No pending model changes", "muted");
  }
}

function moveDraftChatModelRow(index, direction) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= draftChatModelRows.length) {
    return;
  }
  const rows = [...draftChatModelRows];
  const [row] = rows.splice(index, 1);
  rows.splice(nextIndex, 0, row);
  draftChatModelRows = rows;
  renderModelManagementPanels();
  markDirty();
}

function renderChatModelVisibilityList() {
  if (!chatModelVisibilityListEl) {
    return;
  }

  chatModelVisibilityListEl.replaceChildren();
  const candidateMap = new Map(getDraftChatCapableModels().map((model) => [model.id, model]));
  if (!draftChatModelRows.length) {
    const emptyState = document.createElement("p");
    emptyState.className = "settings-copy";
    emptyState.textContent = "No tool-capable models are available for the chat selector.";
    chatModelVisibilityListEl.append(emptyState);
    return;
  }

  draftChatModelRows.forEach((rowState, index) => {
    const model = candidateMap.get(rowState.id);
    if (!model) {
      return;
    }

    const row = document.createElement("div");
    row.className = "model-management-row";

    const toggleLabel = document.createElement("label");
    toggleLabel.className = "tool-toggle";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = Boolean(rowState.visible);
    checkbox.addEventListener("change", () => {
      rowState.visible = checkbox.checked;
      if (!draftChatModelRows.some((entry) => entry.visible)) {
        rowState.visible = true;
        checkbox.checked = true;
        setCustomModelStatus("At least one chat model must stay visible.", "warning");
        return;
      }
      markDirty();
    });

    const body = document.createElement("span");
    body.className = "model-management-row__toggle-body";
    const title = document.createElement("strong");
    title.textContent = model.name || model.id;
    const subtitle = document.createElement("small");
    subtitle.textContent = `${getModelProviderLabel(model)} · ${model.api_model || model.id}`;
    body.append(title, subtitle);
    toggleLabel.append(checkbox, body);

    const actions = document.createElement("div");
    actions.className = "settings-inline-actions";

    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "btn-ghost";
    upBtn.textContent = "Up";
    upBtn.disabled = index === 0;
    upBtn.addEventListener("click", () => moveDraftChatModelRow(index, -1));

    const downBtn = document.createElement("button");
    downBtn.type = "button";
    downBtn.className = "btn-ghost";
    downBtn.textContent = "Down";
    downBtn.disabled = index === draftChatModelRows.length - 1;
    downBtn.addEventListener("click", () => moveDraftChatModelRow(index, 1));

    actions.append(upBtn, downBtn);
    row.append(toggleLabel, actions);
    chatModelVisibilityListEl.append(row);
  });
}

function populateOperationModelSelect(selectEl, selectedValue, emptyLabel = "Use default chat model") {
  if (!selectEl) {
    return;
  }
  const options = getDraftAvailableModels();
  const fragment = document.createDocumentFragment();

  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = emptyLabel;
  fragment.append(defaultOption);

  options.forEach((model) => {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = `${model.name || model.id} (${getModelProviderLabel(model)})`;
    fragment.append(option);
  });

  selectEl.replaceChildren(fragment);
  selectEl.value = selectedValue || "";
  if (selectEl.value !== (selectedValue || "")) {
    selectEl.value = "";
  }
}

function populateVisionModelSelect(selectEl, selectedValue, emptyLabel = "Use default chat model when needed") {
  if (!selectEl) {
    return;
  }
  const options = getDraftAvailableModels().filter((model) => Boolean(model?.supports_vision));
  const fragment = document.createDocumentFragment();

  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = emptyLabel;
  fragment.append(defaultOption);

  options.forEach((model) => {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = `${model.name || model.id} (${getModelProviderLabel(model)})`;
    fragment.append(option);
  });

  selectEl.replaceChildren(fragment);
  selectEl.value = selectedValue || "";
  if (selectEl.value !== (selectedValue || "")) {
    selectEl.value = "";
  }
}

function renderOperationModelSelects(preferences = null) {
  const currentChatSummaryModel = chatSummaryModelEl
    ? String(chatSummaryModelEl.value || appSettings.chat_summary_model || "")
    : String(appSettings.chat_summary_model || "");
  const currentImageHelperModel = imageHelperModelEl
    ? String(imageHelperModelEl.value || appSettings.image_helper_model || "")
    : String(appSettings.image_helper_model || "");
  const currentSelections = preferences && typeof preferences === "object"
    ? {
        summarize: String(preferences.summarize || ""),
        fetch_summarize: String(preferences.fetch_summarize || ""),
        prune: String(preferences.prune || ""),
        fix_text: String(preferences.fix_text || ""),
        generate_title: String(preferences.generate_title || ""),
        upload_metadata: String(preferences.upload_metadata || ""),
        sub_agent: String(preferences.sub_agent || ""),
      }
    : getOperationModelPreferencesDraft();
  populateOperationModelSelect(summaryModelPreferenceEl, currentSelections.summarize);
  populateOperationModelSelect(fetchSummarizeModelPreferenceEl, currentSelections.fetch_summarize);
  populateOperationModelSelect(pruneModelPreferenceEl, currentSelections.prune);
  populateOperationModelSelect(fixTextModelPreferenceEl, currentSelections.fix_text);
  populateOperationModelSelect(titleModelPreferenceEl, currentSelections.generate_title);
  populateOperationModelSelect(uploadMetadataModelPreferenceEl, currentSelections.upload_metadata);
  populateOperationModelSelect(subAgentModelPreferenceEl, currentSelections.sub_agent);
  populateOperationModelSelect(chatSummaryModelEl, currentChatSummaryModel, "Use default chat model");
  populateVisionModelSelect(imageHelperModelEl, currentImageHelperModel, "Use default chat model when needed");
}

function renderModelManagementPanels({ preferVisibleId = "", operationPreferences = null } = {}) {
  syncDraftChatModelRows({ preferVisibleId });
  renderCustomModelList();
  renderChatModelVisibilityList();
  renderOperationModelSelects(operationPreferences);
  renderOperationFallbackLists();
  updateCustomModelEditControls();
}

function resetCustomModelForm() {
  if (customModelNameEl) customModelNameEl.value = "";
  if (customModelApiModelEl) customModelApiModelEl.value = "";
  if (customModelRoutingModeEl) customModelRoutingModeEl.value = "auto";
  if (customModelProviderSlugEl) customModelProviderSlugEl.value = "";
  if (customModelReasoningModeEl) customModelReasoningModeEl.value = "default";
  if (customModelReasoningEffortEl) customModelReasoningEffortEl.value = "";
  if (customModelSupportsToolsEl) customModelSupportsToolsEl.checked = true;
  if (customModelSupportsVisionEl) customModelSupportsVisionEl.checked = false;
  if (customModelSupportsStructuredEl) customModelSupportsStructuredEl.checked = false;
  syncCustomModelReasoningControls();
  syncCustomModelProviderControls();
}

function addCustomModelFromInputs() {
  const apiModel = normalizeOpenRouterApiModel(customModelApiModelEl?.value || "");
  const providerSelection = readCustomModelProviderSlug();
  const reasoning = normalizeOpenRouterReasoningConfig(
    customModelReasoningModeEl?.value || "default",
    customModelReasoningEffortEl?.value || ""
  );
  if (!apiModel) {
    setCustomModelStatus("Custom model API id is required.", "error");
    return;
  }
  if (providerSelection.error) {
    setCustomModelStatus(providerSelection.error, "error");
    return;
  }

  const providerSlug = providerSelection.providerSlug;
  const existingIndex = editingCustomModelClientUid
    ? draftCustomModels.findIndex((model) => model.client_uid === editingCustomModelClientUid)
    : -1;
  const existingModel = existingIndex >= 0 ? draftCustomModels[existingIndex] : null;

  const normalizedModel = normalizeDraftCustomModel({
    id: existingModel?.id || "",
    client_uid: existingModel?.client_uid || createCustomModelClientUid(),
    name: String(customModelNameEl?.value || "").trim() || apiModel,
    provider: "openrouter",
    api_model: apiModel,
    provider_slug: providerSlug,
    reasoning_mode: reasoning.mode,
    reasoning_effort: reasoning.effort,
    supports_tools: Boolean(customModelSupportsToolsEl?.checked),
    supports_vision: Boolean(customModelSupportsVisionEl?.checked),
    supports_structured_outputs: Boolean(customModelSupportsStructuredEl?.checked),
    is_custom: true,
  });
  const normalizedSignature = getDraftCustomModelSignature(normalizedModel);
  const duplicateIndex = draftCustomModels.findIndex((model, index) => (
    getDraftCustomModelSignature(model) === normalizedSignature && index !== existingIndex
  ));
  if (duplicateIndex >= 0) {
    setCustomModelStatus("That custom model configuration is already configured.", "warning");
    return;
  }
  const preferredModelReference = getDraftCustomModelReference(normalizedModel);

  if (existingIndex >= 0) {
    const nextModels = [...draftCustomModels];
    nextModels.splice(existingIndex, 1, normalizedModel);
    draftCustomModels = nextModels;
  } else {
    draftCustomModels = [...draftCustomModels, normalizedModel];
  }

  cancelEditingCustomModel({ silent: true });
  renderModelManagementPanels({ preferVisibleId: preferredModelReference });
  markDirty();
  setCustomModelStatus(existingIndex >= 0 ? "Custom model updated. Save to apply." : "Custom model added. Save to apply.", "success");
}

function flattenScratchpadSections(sectionMap) {
  const flattened = [];
  DEFAULT_SCRATCHPAD_SECTION_ORDER.forEach((sectionId) => {
    const notes = Array.isArray(sectionMap?.[sectionId]) ? sectionMap[sectionId] : [];
    flattened.push(...notes);
  });
  return flattened;
}

function readScratchpadNotesFromSection(sectionId) {
  if (!scratchpadListEl) {
    return getScratchpadSectionsFromSettings()[sectionId] || [];
  }

  const sectionEl = scratchpadListEl.querySelector(`.scratchpad-section[data-section="${sectionId}"]`);
  if (!sectionEl) {
    return [];
  }

  return normalizeScratchpadNotesList(
    Array.from(sectionEl.querySelectorAll(".scratchpad-note-input"), (input) => input.value)
  );
}

function readScratchpadSectionsFromList() {
  const sections = {};
  if (!scratchpadListEl) {
    return getScratchpadSectionsFromSettings();
  }

  DEFAULT_SCRATCHPAD_SECTION_ORDER.forEach((sectionId) => {
    sections[sectionId] = readScratchpadNotesFromSection(sectionId);
  });
  return sections;
}

function readScratchpadNotesFromList() {
  return flattenScratchpadSections(readScratchpadSectionsFromList());
}

function getScratchpadNotesFromSettings() {
  return flattenScratchpadSections(getScratchpadSectionsFromSettings());
}

function getVisibleScratchpadSections() {
  return scratchpadListEl ? readScratchpadSectionsFromList() : getScratchpadSectionsFromSettings();
}

function getVisibleScratchpadNotes() {
  return flattenScratchpadSections(getVisibleScratchpadSections());
}

function updateScratchpadCount() {
  if (!scratchpadCountEl) {
    return;
  }
  const count = getVisibleScratchpadNotes().length;
  scratchpadCountEl.textContent = count === 1 ? "1 note" : `${count} notes`;
}

function updateScratchpadSectionCount(sectionId) {
  if (!scratchpadListEl) {
    return;
  }
  const countEl = scratchpadListEl.querySelector(`[data-scratchpad-section-count="${sectionId}"]`);
  if (!countEl) {
    return;
  }
  const count = readScratchpadNotesFromSection(sectionId).length;
  countEl.textContent = count === 1 ? "1 note" : `${count} notes`;
}

function createScratchpadEmptyState(message = "No notes in this section yet.") {
  const emptyState = document.createElement("div");
  emptyState.className = "scratchpad-empty-state";
  emptyState.textContent = message;
  return emptyState;
}

function setScratchpadEmptyState(sectionListEl, message = "No notes in this section yet.") {
  if (!sectionListEl) {
    return;
  }
  sectionListEl.replaceChildren(createScratchpadEmptyState(message));
}

function createScratchpadNoteRow(sectionId, note = "") {
  const row = document.createElement("div");
  row.className = "scratchpad-note-row";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "settings-text scratchpad-note-input";
  input.dataset.section = sectionId;
  input.placeholder = "One durable note";
  input.value = note;
  input.addEventListener("input", () => {
    markDirty();
    updateScratchpadSectionCount(sectionId);
    updateScratchpadCount();
    syncOverviewStats();
  });

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "btn-ghost btn-ghost--danger scratchpad-note-remove";
  removeBtn.textContent = "Remove";
  removeBtn.addEventListener("click", () => {
    const sectionListEl = row.closest("[data-scratchpad-section-list]");
    row.remove();
    if (sectionListEl && !sectionListEl.querySelector(".scratchpad-note-row")) {
      setScratchpadEmptyState(sectionListEl);
    }
    updateScratchpadSectionCount(sectionId);
    updateScratchpadCount();
    syncOverviewStats();
    markDirty();
  });

  row.append(input, removeBtn);
  return row;
}

function createScratchpadReadonlyRow(note = "") {
  const row = document.createElement("div");
  row.className = "scratchpad-note-static";
  row.textContent = note;
  return row;
}

function renderScratchpadSectionList(sectionListEl, sectionId, notes, { editable = true } = {}) {
  if (!sectionListEl) {
    return;
  }

  sectionListEl.replaceChildren();
  if (!Array.isArray(notes) || !notes.length) {
    setScratchpadEmptyState(
      sectionListEl,
      editable ? "No notes in this section yet. Add one when it becomes useful." : "No notes stored in this section."
    );
    return;
  }

  notes.forEach((note) => {
    sectionListEl.append(editable ? createScratchpadNoteRow(sectionId, note) : createScratchpadReadonlyRow(note));
  });
}

function createScratchpadSectionCard(section, notes, { editable = true } = {}) {
  const card = document.createElement("section");
  card.className = "scratchpad-section";
  card.dataset.section = section.id;

  const header = document.createElement("div");
  header.className = "scratchpad-section__header";

  const titleGroup = document.createElement("div");
  titleGroup.className = "scratchpad-section__title-group";

  const title = document.createElement("h4");
  title.className = "scratchpad-section__title";
  title.textContent = section.title;

  const description = document.createElement("p");
  description.className = "scratchpad-section__description";
  description.textContent = section.description;

  const count = document.createElement("span");
  count.className = "scratchpad-section__count";
  count.dataset.scratchpadSectionCount = section.id;
  count.textContent = notes.length === 1 ? "1 note" : `${notes.length} notes`;

  titleGroup.append(title, description);
  header.append(titleGroup, count);

  const sectionListEl = document.createElement("div");
  sectionListEl.className = "scratchpad-list scratchpad-list--section";
  sectionListEl.dataset.scratchpadSectionList = section.id;
  renderScratchpadSectionList(sectionListEl, section.id, notes, { editable });

  const toolbar = document.createElement("div");
  toolbar.className = "scratchpad-toolbar scratchpad-toolbar--section";
  if (editable) {
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "btn-ghost scratchpad-section-add-btn";
    addBtn.dataset.section = section.id;
    addBtn.textContent = `Add to ${section.title}`;
    addBtn.addEventListener("click", () => addScratchpadNote(section.id));
    toolbar.append(addBtn);
  }

  card.append(header, sectionListEl, toolbar);
  return card;
}

function renderScratchpad(editable = true) {
  if (!scratchpadListEl) {
    return;
  }

  const sectionNotes = getScratchpadSectionsFromSettings();
  scratchpadListEl.replaceChildren();
  getScratchpadSectionPayloads().forEach((section) => {
    const notes = Array.isArray(sectionNotes[section.id]) ? sectionNotes[section.id] : [];
    scratchpadListEl.append(createScratchpadSectionCard(section, notes, { editable }));
  });
  updateScratchpadCount();
  syncOverviewStats();
}

function addScratchpadNote(sectionId = DEFAULT_SCRATCHPAD_SECTION_ID, note = "") {
  if (!scratchpadListEl) {
    return;
  }

  const sectionEl = scratchpadListEl.querySelector(`.scratchpad-section[data-section="${sectionId}"]`);
  const sectionListEl = sectionEl?.querySelector("[data-scratchpad-section-list]");
  if (!sectionListEl) {
    return;
  }

  const emptyState = sectionListEl.querySelector(".scratchpad-empty-state");
  if (emptyState) {
    emptyState.remove();
  }

  const row = createScratchpadNoteRow(sectionId, note);
  sectionListEl.append(row);
  row.querySelector(".scratchpad-note-input")?.focus();
  updateScratchpadSectionCount(sectionId);
  updateScratchpadCount();
  syncOverviewStats();
  markDirty();
}

function updateRagSensitivityHint() {
  if (!ragSensitivityHintEl || !ragSensitivityEl) {
    return;
  }
  const sensitivity = ragSensitivityEl.value || "normal";
  ragSensitivityHintEl.textContent = RAG_SENSITIVITY_HINTS[sensitivity] || RAG_SENSITIVITY_HINTS.normal;
}

function getSelectedTools() {
  return toolToggleEls.filter((element) => element.checked).map((element) => element.value);
}

function getSelectedRagSourceTypes() {
  return ragSourceTypeEls.filter((element) => element.checked).map((element) => element.value);
}

function getSelectedRagAutoInjectSourceTypes() {
  return ragAutoInjectSourceTypeEls.filter((element) => element.checked).map((element) => element.value);
}

function getSelectedProxyOperations() {
  return proxyOperationEls.filter((element) => element.checked).map((element) => element.value);
}

function getSelectedSubAgentTools() {
  return subAgentToolToggleEls.filter((element) => element.checked).map((element) => element.value);
}

function getRagSourceControlContainer(element) {
  return element?.closest(".rag-source-mode-toggle") || null;
}

function applySelectedTools(selected) {
  const active = new Set(Array.isArray(selected) ? selected : []);
  toolToggleEls.forEach((element) => {
    element.checked = active.has(element.value);
  });
}

function applySelectedRagSourceTypes(selected) {
  const active = new Set(Array.isArray(selected) ? selected : []);
  ragSourceTypeEls.forEach((element) => {
    element.checked = active.has(element.value);
  });
  syncRagAutoInjectSourceAvailability();
  updateRagSourceSummary();
}

function applySelectedRagAutoInjectSourceTypes(selected) {
  const active = new Set(Array.isArray(selected) ? selected : []);
  ragAutoInjectSourceTypeEls.forEach((element) => {
    element.checked = active.has(element.value);
  });
  syncRagAutoInjectSourceAvailability();
}

function applySelectedProxyOperations(selected) {
  const active = new Set(Array.isArray(selected) ? selected : []);
  proxyOperationEls.forEach((element) => {
    element.checked = active.has(element.value);
  });
}

function applySelectedSubAgentTools(selected) {
  const active = new Set(Array.isArray(selected) ? selected : []);
  subAgentToolToggleEls.forEach((element) => {
    element.checked = active.has(element.value);
  });
}

function updateRagSourceSummary() {
  if (!ragSourceSummaryEl) {
    return;
  }

  if (!Boolean(featureFlags.rag_enabled)) {
    ragSourceSummaryEl.textContent = "RAG is disabled in .env, so source pool selection is inactive.";
    return;
  }

  const selected = getSelectedRagSourceTypes();
  if (!selected.length) {
    ragSourceSummaryEl.textContent = "No source pool is enabled for Search. The assistant will skip generic RAG retrieval from chats, tool outputs, and uploaded documents.";
    return;
  }

  ragSourceSummaryEl.textContent = `Search is enabled for: ${formatRagSourceLabels(selected)}. Only these pools can supply generic retrieved context.`;
}

function updateRagAutoInjectSourceSummary() {
  if (!ragAutoInjectSourceSummaryEl) {
    return;
  }

  if (!Boolean(featureFlags.rag_enabled)) {
    ragAutoInjectSourceSummaryEl.textContent = "RAG is disabled in .env, so per-source auto-injection is inactive.";
    return;
  }

  const selected = getSelectedRagAutoInjectSourceTypes();
  if (!selected.length) {
    ragAutoInjectSourceSummaryEl.textContent = "No source pool is marked for Auto inject. Retrieved context can still be searched manually, but nothing will be inserted automatically.";
    return;
  }

  ragAutoInjectSourceSummaryEl.textContent = `Auto inject is configured for: ${formatRagSourceLabels(selected)}. These pools are eligible for automatic prompt insertion.`;
}

function formatRagSourceLabels(selectedValues) {
  const values = Array.isArray(selectedValues) ? selectedValues : [];
  const toolDerivedSelected = values.includes("tool_result") && values.includes("tool_memory");
  const labels = values
    .filter((value) => !toolDerivedSelected || (value !== "tool_result" && value !== "tool_memory"))
    .map((value) => RAG_SOURCE_TYPE_LABELS[value] || value);
  if (toolDerivedSelected) {
    labels.splice(1, 0, "Tool-derived context");
  }
  return labels.join(", ");
}

function syncRagAutoInjectSourceAvailability() {
  const ragEnabled = Boolean(featureFlags.rag_enabled);

  ragAutoInjectSourceTypeEls.forEach((element) => {
    element.disabled = !ragEnabled;
    getRagSourceControlContainer(element)?.classList.toggle("is-muted", !ragEnabled);
  });

  updateRagAutoInjectSourceSummary();
  syncOverviewStats();
}

function applyConditionalSectionState(element, { disabled = false, hidden = null } = {}) {
  if (!element) {
    return;
  }

  if ("disabled" in element) {
    element.disabled = disabled;
  }
  element.classList.toggle("is-disabled", disabled);
  element.setAttribute("aria-disabled", disabled ? "true" : "false");

  if (typeof hidden === "boolean") {
    element.hidden = hidden;
    element.setAttribute("aria-hidden", hidden ? "true" : "false");
  }
}

function syncContextStrategyAvailability() {
  const strategy = contextSelectionStrategyEl?.value || "classic";
  const entropyEnabled = strategy === "entropy" || strategy === "entropy_rag_hybrid";
  const hybridEnabled = strategy === "entropy_rag_hybrid";

  applyConditionalSectionState(entropyControlsFieldsetEl, { disabled: !entropyEnabled, hidden: !entropyEnabled });
  if (entropyRagBudgetRatioEl) {
    entropyRagBudgetRatioEl.disabled = !hybridEnabled;
  }
  applyConditionalSectionState(entropyRagBudgetClusterEl, { disabled: !hybridEnabled, hidden: !hybridEnabled });
}

function syncPruningSettingsAvailability() {
  applyConditionalSectionState(pruningControlsFieldsetEl, { disabled: !Boolean(pruningEnabledEl?.checked) });
}

function syncOverviewStats() {
  if (statScratchpadEl) {
    const noteCount = getVisibleScratchpadNotes().length;
    statScratchpadEl.textContent = noteCount === 1 ? "1 note" : `${noteCount} notes`;
  }

  if (statToolsEl) {
    const toolCount = getSelectedTools().length;
    statToolsEl.textContent = toolCount === 1 ? "1 enabled" : `${toolCount} enabled`;
  }

  if (statRagEl) {
    if (!featureFlags.rag_enabled) {
      statRagEl.textContent = "Disabled";
    } else {
      const sourceCount = getSelectedRagSourceTypes().length;
      const autoInjectCount = getSelectedRagAutoInjectSourceTypes().length;
      statRagEl.textContent = `${sourceCount} search / ${autoInjectCount} inject`;
    }
  }
}

function applySettingsToForm() {
  renderDefaultPersonaSelect();
  if (getPersonas().length) {
    const nextPersonaId = findPersonaById(activePersonaId) ? activePersonaId : getPersonas()[0].id;
    selectPersonaForEditing(nextPersonaId);
  } else {
    selectPersonaForEditing(null);
  }
  if (temperatureEl) temperatureEl.value = String(appSettings.temperature ?? 0.7);
  if (maxStepsEl) maxStepsEl.value = String(appSettings.max_steps || 5);
  if (maxParallelToolsEl) maxParallelToolsEl.value = String(appSettings.max_parallel_tools ?? 4);
  if (searchToolQueryLimitEl) searchToolQueryLimitEl.value = String(appSettings.search_tool_query_limit ?? 5);
  if (subAgentMaxStepsEl) subAgentMaxStepsEl.value = String(appSettings.sub_agent_max_steps ?? 6);
  if (subAgentTimeoutSecondsEl) subAgentTimeoutSecondsEl.value = String(appSettings.sub_agent_timeout_seconds ?? 240);
  if (subAgentRetryAttemptsEl) subAgentRetryAttemptsEl.value = String(appSettings.sub_agent_retry_attempts ?? 2);
  if (subAgentRetryDelaySecondsEl) subAgentRetryDelaySecondsEl.value = String(appSettings.sub_agent_retry_delay_seconds ?? 5);
  if (subAgentMaxParallelToolsEl) subAgentMaxParallelToolsEl.value = String(appSettings.sub_agent_max_parallel_tools ?? appSettings.max_parallel_tools ?? 2);
  if (webCacheTtlHoursEl) webCacheTtlHoursEl.value = String(appSettings.web_cache_ttl_hours ?? 24);
  if (openrouterPromptCacheEnabledEl) openrouterPromptCacheEnabledEl.checked = Boolean(appSettings.openrouter_prompt_cache_enabled ?? true);
  if (openrouterHttpRefererEl) openrouterHttpRefererEl.value = String(appSettings.openrouter_http_referer || "");
  if (openrouterAppTitleEl) openrouterAppTitleEl.value = String(appSettings.openrouter_app_title || "");
  if (loginSessionTimeoutMinutesEl) loginSessionTimeoutMinutesEl.value = String(appSettings.login_session_timeout_minutes ?? 30);
  if (loginMaxFailedAttemptsEl) loginMaxFailedAttemptsEl.value = String(appSettings.login_max_failed_attempts ?? 3);
  if (loginLockoutSecondsEl) loginLockoutSecondsEl.value = String(appSettings.login_lockout_seconds ?? 300);
  if (loginRememberSessionDaysEl) loginRememberSessionDaysEl.value = String(appSettings.login_remember_session_days ?? 3650);
  if (clarificationMaxQuestionsEl) clarificationMaxQuestionsEl.value = String(appSettings.clarification_max_questions || 5);
  if (summaryModeEl) summaryModeEl.value = appSettings.chat_summary_mode || "auto";
  if (summaryDetailLevelEl) summaryDetailLevelEl.value = appSettings.chat_summary_detail_level || "balanced";
  if (summaryTriggerEl) summaryTriggerEl.value = String(appSettings.chat_summary_trigger_token_count || 80000);
  if (summarySkipFirstEl) summarySkipFirstEl.value = String(appSettings.summary_skip_first ?? 2);
  if (summarySkipLastEl) summarySkipLastEl.value = String(appSettings.summary_skip_last ?? 1);
  if (promptPreflightSummaryTokenCountEl) {
    promptPreflightSummaryTokenCountEl.value = String(appSettings.prompt_preflight_summary_token_count ?? 90000);
  }
  if (summarySourceTargetTokensEl) {
    summarySourceTargetTokensEl.value = String(appSettings.summary_source_target_tokens ?? 6000);
  }
  if (summaryRetryMinSourceTokensEl) {
    summaryRetryMinSourceTokensEl.value = String(appSettings.summary_retry_min_source_tokens ?? 1500);
  }
  if (promptMaxInputTokensEl) promptMaxInputTokensEl.value = String(appSettings.prompt_max_input_tokens ?? 80000);
  if (promptResponseTokenReserveEl) promptResponseTokenReserveEl.value = String(appSettings.prompt_response_token_reserve ?? 8000);
  if (promptRecentHistoryMaxTokensEl) promptRecentHistoryMaxTokensEl.value = String(appSettings.prompt_recent_history_max_tokens ?? 32000);
  if (promptSummaryMaxTokensEl) promptSummaryMaxTokensEl.value = String(appSettings.prompt_summary_max_tokens ?? 12000);
  if (promptRagMaxTokensEl) promptRagMaxTokensEl.value = String(appSettings.prompt_rag_max_tokens ?? 18000);
  if (promptToolMemoryMaxTokensEl) promptToolMemoryMaxTokensEl.value = String(appSettings.prompt_tool_memory_max_tokens ?? 10000);
  if (promptToolTraceMaxTokensEl) promptToolTraceMaxTokensEl.value = String(appSettings.prompt_tool_trace_max_tokens ?? 9000);
  if (contextCompactionThresholdEl) contextCompactionThresholdEl.value = String(appSettings.context_compaction_threshold ?? 0.85);
  if (contextCompactionKeepRecentRoundsEl) contextCompactionKeepRecentRoundsEl.value = String(appSettings.context_compaction_keep_recent_rounds ?? 2);
  if (contextSelectionStrategyEl) contextSelectionStrategyEl.value = appSettings.context_selection_strategy || "classic";
  if (entropyProfileEl) entropyProfileEl.value = appSettings.entropy_profile || "balanced";
  if (entropyRagBudgetRatioEl) entropyRagBudgetRatioEl.value = String(appSettings.entropy_rag_budget_ratio ?? 35);
  if (entropyProtectCodeBlocksEl) entropyProtectCodeBlocksEl.checked = Boolean(appSettings.entropy_protect_code_blocks ?? true);
  if (entropyProtectToolResultsEl) entropyProtectToolResultsEl.checked = Boolean(appSettings.entropy_protect_tool_results ?? true);
  if (entropyReferenceBoostEl) entropyReferenceBoostEl.checked = Boolean(appSettings.entropy_reference_boost ?? true);
  if (reasoningAutoCollapseEl) reasoningAutoCollapseEl.checked = Boolean(appSettings.reasoning_auto_collapse);
  if (toolMemoryAutoInjectEl) toolMemoryAutoInjectEl.checked = Boolean(appSettings.tool_memory_auto_inject);
  if (pruningEnabledEl) pruningEnabledEl.checked = Boolean(appSettings.pruning_enabled);
  if (pruningTokenThresholdEl) pruningTokenThresholdEl.value = String(appSettings.pruning_token_threshold || 80000);
  if (pruningBatchSizeEl) pruningBatchSizeEl.value = String(appSettings.pruning_batch_size || 10);
  if (pruningTargetReductionRatioEl) pruningTargetReductionRatioEl.value = String(appSettings.pruning_target_reduction_ratio ?? 0.65);
  if (pruningMinTargetTokensEl) pruningMinTargetTokensEl.value = String(appSettings.pruning_min_target_tokens ?? 160);
  if (fetchThresholdEl) fetchThresholdEl.value = String(appSettings.fetch_url_token_threshold || 3500);
  if (fetchAggressivenessEl) fetchAggressivenessEl.value = String(appSettings.fetch_url_clip_aggressiveness || 50);
  if (fetchHtmlConverterModeEl) fetchHtmlConverterModeEl.value = String(appSettings.fetch_html_converter_mode || "hybrid");
  if (fetchSummarizeMaxInputCharsEl) fetchSummarizeMaxInputCharsEl.value = String(appSettings.fetch_url_summarized_max_input_chars || 80000);
  if (fetchSummarizeMaxOutputTokensEl) fetchSummarizeMaxOutputTokensEl.value = String(appSettings.fetch_url_summarized_max_output_tokens || 2400);
  if (canvasPromptLinesEl) canvasPromptLinesEl.value = String(appSettings.canvas_prompt_max_lines || 250);
  if (canvasPromptTokensEl) canvasPromptTokensEl.value = String(appSettings.canvas_prompt_max_tokens || 4000);
  if (canvasPromptCharsEl) canvasPromptCharsEl.value = String(appSettings.canvas_prompt_max_chars || 20000);
  if (canvasCodeLineCharsEl) canvasCodeLineCharsEl.value = String(appSettings.canvas_prompt_code_line_max_chars || 180);
  if (canvasTextLineCharsEl) canvasTextLineCharsEl.value = String(appSettings.canvas_prompt_text_line_max_chars || 100);
  if (canvasExpandLinesEl) canvasExpandLinesEl.value = String(appSettings.canvas_expand_max_lines || 1600);
  if (canvasScrollLinesEl) canvasScrollLinesEl.value = String(appSettings.canvas_scroll_window_lines || 200);
  if (conversationMemoryEnabledEl) conversationMemoryEnabledEl.checked = Boolean(appSettings.conversation_memory_enabled);
  if (ocrEnabledEl) ocrEnabledEl.checked = Boolean(appSettings.ocr_enabled);
  if (ocrProviderEl) ocrProviderEl.value = String(appSettings.ocr_provider || "paddleocr");
  if (ragEnabledEl) ragEnabledEl.checked = Boolean(appSettings.rag_enabled);
  if (youtubeTranscriptsEnabledEl) youtubeTranscriptsEnabledEl.checked = Boolean(appSettings.youtube_transcripts_enabled);
  if (youtubeTranscriptLanguageEl) youtubeTranscriptLanguageEl.value = String(appSettings.youtube_transcript_language || "");
  if (youtubeTranscriptModelSizeEl) youtubeTranscriptModelSizeEl.value = String(appSettings.youtube_transcript_model_size || "small");
  if (chatSummaryModelEl) chatSummaryModelEl.value = String(appSettings.chat_summary_model || "");
  if (ragChunkSizeEl) ragChunkSizeEl.value = String(appSettings.rag_chunk_size ?? 1800);
  if (ragChunkOverlapEl) ragChunkOverlapEl.value = String(appSettings.rag_chunk_overlap ?? 250);
  if (ragMaxChunksPerSourceEl) ragMaxChunksPerSourceEl.value = String(appSettings.rag_max_chunks_per_source ?? 2);
  if (ragSearchTopKEl) ragSearchTopKEl.value = String(appSettings.rag_search_top_k ?? 5);
  if (ragSearchMinSimilarityEl) ragSearchMinSimilarityEl.value = String(appSettings.rag_search_min_similarity ?? 0.35);
  if (ragQueryExpansionEnabledEl) ragQueryExpansionEnabledEl.checked = Boolean(appSettings.rag_query_expansion_enabled ?? true);
  if (ragQueryExpansionMaxVariantsEl) ragQueryExpansionMaxVariantsEl.value = String(appSettings.rag_query_expansion_max_variants ?? 2);
  if (toolMemoryTtlDefaultSecondsEl) toolMemoryTtlDefaultSecondsEl.value = String(appSettings.tool_memory_ttl_default_seconds ?? 604800);
  if (toolMemoryTtlWebSecondsEl) toolMemoryTtlWebSecondsEl.value = String(appSettings.tool_memory_ttl_web_seconds ?? 43200);
  if (toolMemoryTtlNewsSecondsEl) toolMemoryTtlNewsSecondsEl.value = String(appSettings.tool_memory_ttl_news_seconds ?? 7200);
  if (fetchRawMaxTextCharsEl) fetchRawMaxTextCharsEl.value = String(appSettings.fetch_raw_max_text_chars ?? 24000);
  if (fetchSummaryMaxCharsEl) fetchSummaryMaxCharsEl.value = String(appSettings.fetch_summary_max_chars ?? 8000);
  applySelectedTools(appSettings.active_tools || []);
  applySelectedSubAgentTools(appSettings.sub_agent_allowed_tool_names || []);
  applySelectedProxyOperations(appSettings.proxy_enabled_operations || []);
  if (ragSensitivityEl) {
    ragSensitivityEl.value = appSettings.rag_sensitivity || "normal";
  }
  if (ragContextSizeEl) {
    ragContextSizeEl.value = appSettings.rag_context_size || "medium";
  }
  applySelectedRagSourceTypes(appSettings.rag_source_types || []);
  applySelectedRagAutoInjectSourceTypes(appSettings.rag_auto_inject_source_types || appSettings.rag_source_types || []);
  if (imageProcessingMethodEl) {
    imageProcessingMethodEl.value = appSettings.image_processing_method || "auto";
  }
  if (imageHelperModelEl) {
    imageHelperModelEl.value = appSettings.image_helper_model || "";
  }
  draftCustomModels = Array.isArray(appSettings.custom_models)
    ? appSettings.custom_models.map((model) => normalizeDraftCustomModel(model))
    : [];
  editingCustomModelClientUid = null;
  draftChatModelRows = [];
  initializeOperationFallbackDraftRows(appSettings.operation_model_fallback_preferences || {});
  renderModelManagementPanels({
    operationPreferences: appSettings.operation_model_preferences || {},
  });
  setCustomModelStatus("No pending model changes", "muted");
  updateCustomModelEditControls();
  syncCustomModelReasoningControls();
  syncCustomModelProviderControls();
  updateRagSensitivityHint();
  syncContextStrategyAvailability();
  syncPruningSettingsAvailability();
  if (scratchpadListEl || scratchpadAddBtn || scratchpadCountEl) {
    renderScratchpad(true);
  }
  syncOverviewStats();
}

function applyFeatureAvailability() {
  const ragEnabled = Boolean(featureFlags.rag_enabled);

  if (ragSensitivityEl) ragSensitivityEl.disabled = !ragEnabled;
  if (ragContextSizeEl) ragContextSizeEl.disabled = !ragEnabled;
  ragSourceTypeEls.forEach((element) => {
    element.disabled = !ragEnabled;
  });
  ragAutoInjectSourceTypeEls.forEach((element) => {
    element.disabled = !ragEnabled;
  });
  if (kbSyncBtn) kbSyncBtn.disabled = !ragEnabled;
  if (kbUploadFileEl) kbUploadFileEl.disabled = !ragEnabled;
  if (kbUploadTitleEl) kbUploadTitleEl.disabled = !ragEnabled;
  if (kbUploadDescriptionEl) kbUploadDescriptionEl.disabled = !ragEnabled;
  if (kbUploadAutoInjectEl) kbUploadAutoInjectEl.disabled = !ragEnabled;
  if (kbUploadBtn) kbUploadBtn.disabled = !ragEnabled;
  if (ragInjectOptionsEl) {
    ragInjectOptionsEl.classList.toggle("is-disabled", !ragEnabled);
    ragInjectOptionsEl.setAttribute("aria-disabled", !ragEnabled ? "true" : "false");
  }
  if (toolMemoryAutoInjectEl) {
    toolMemoryAutoInjectEl.disabled = !ragEnabled;
  }
  applyConditionalSectionState(toolMemoryLanePanelEl, { disabled: !ragEnabled });
  if (ragDisabledNoteEl) {
    ragDisabledNoteEl.hidden = ragEnabled;
  }
  if (scratchpadAddBtn) {
    scratchpadAddBtn.hidden = false;
  }
  if (scratchpadReadonlyNoteEl) {
    scratchpadReadonlyNoteEl.hidden = false;
  }
  if (!ragEnabled) {
    setKbStatus("RAG disabled in .env", "warning");
    setKbUploadStatus("Upload disabled because RAG is off", "warning");
  } else {
    setKbUploadStatus("Ready to upload", "muted");
  }
  syncRagAutoInjectSourceAvailability();
  syncContextStrategyAvailability();
  syncPruningSettingsAvailability();
  updateRagSourceSummary();
  syncOverviewStats();
}

function applyServerSettingsData(data) {
  personaMemoryByPersonaId = {};
  activePersonaMemoryEntryId = null;
  isPersonaMemoryLoading = false;
  appSettings.general_instructions = data.general_instructions || data.user_preferences || "";
  appSettings.ai_personality = data.ai_personality || "";
  appSettings.user_preferences = appSettings.general_instructions;
  appSettings.effective_user_preferences = data.effective_user_preferences || "";
  appSettings.default_persona_id = normalizePersonaId(data.default_persona_id);
  appSettings.personas = Array.isArray(data.personas) ? data.personas : [];
  appSettings.scratchpad = data.scratchpad || "";
  appSettings.scratchpad_sections = data.scratchpad_sections && typeof data.scratchpad_sections === "object"
    ? data.scratchpad_sections
    : {};
  appSettings.max_steps = data.max_steps || 5;
  appSettings.max_parallel_tools = data.max_parallel_tools ?? 4;
  appSettings.search_tool_query_limit = data.search_tool_query_limit ?? 5;
  appSettings.sub_agent_max_steps = data.sub_agent_max_steps ?? 6;
  appSettings.sub_agent_timeout_seconds = data.sub_agent_timeout_seconds ?? 240;
  appSettings.sub_agent_retry_attempts = data.sub_agent_retry_attempts ?? 2;
  appSettings.sub_agent_retry_delay_seconds = data.sub_agent_retry_delay_seconds ?? 5;
  appSettings.sub_agent_max_parallel_tools = data.sub_agent_max_parallel_tools ?? data.max_parallel_tools ?? 2;
  appSettings.web_cache_ttl_hours = data.web_cache_ttl_hours ?? 24;
  appSettings.openrouter_prompt_cache_enabled = Boolean(data.openrouter_prompt_cache_enabled ?? true);
  appSettings.openrouter_http_referer = data.openrouter_http_referer || "";
  appSettings.openrouter_app_title = data.openrouter_app_title || "";
  appSettings.login_session_timeout_minutes = data.login_session_timeout_minutes ?? 30;
  appSettings.login_max_failed_attempts = data.login_max_failed_attempts ?? 3;
  appSettings.login_lockout_seconds = data.login_lockout_seconds ?? 300;
  appSettings.login_remember_session_days = data.login_remember_session_days ?? 3650;
  appSettings.temperature = data.temperature ?? 0.7;
  appSettings.clarification_max_questions = data.clarification_max_questions || 5;
  appSettings.available_models = Array.isArray(data.available_models) ? data.available_models : [];
  appSettings.custom_model_contract = data.custom_model_contract && typeof data.custom_model_contract === "object"
    ? data.custom_model_contract
    : {};
  appSettings.custom_models = Array.isArray(data.custom_models) ? data.custom_models : [];
  appSettings.visible_model_order = Array.isArray(data.visible_model_order) ? data.visible_model_order : [];
  appSettings.default_chat_model = data.default_chat_model || "";
  appSettings.operation_model_preferences = data.operation_model_preferences && typeof data.operation_model_preferences === "object"
    ? data.operation_model_preferences
    : {};
  appSettings.operation_model_fallback_preferences = data.operation_model_fallback_preferences && typeof data.operation_model_fallback_preferences === "object"
    ? data.operation_model_fallback_preferences
    : {};
  appSettings.image_processing_method = data.image_processing_method || "auto";
  appSettings.image_helper_model = data.image_helper_model || "";
  appSettings.conversation_memory_enabled = Boolean(data.conversation_memory_enabled);
  appSettings.ocr_enabled = Boolean(data.ocr_enabled);
  appSettings.ocr_provider = data.ocr_provider || "paddleocr";
  appSettings.rag_enabled = Boolean(data.rag_enabled);
  appSettings.youtube_transcripts_enabled = Boolean(data.youtube_transcripts_enabled);
  appSettings.youtube_transcript_language = data.youtube_transcript_language || "";
  appSettings.youtube_transcript_model_size = data.youtube_transcript_model_size || "small";
  appSettings.chat_summary_model = data.chat_summary_model || "";
  appSettings.chat_summary_mode = data.chat_summary_mode || "auto";
  appSettings.chat_summary_detail_level = data.chat_summary_detail_level || "balanced";
  appSettings.chat_summary_trigger_token_count = data.chat_summary_trigger_token_count || 80000;
  appSettings.summary_skip_first = data.summary_skip_first ?? 2;
  appSettings.summary_skip_last = data.summary_skip_last ?? 1;
  appSettings.prompt_preflight_summary_token_count = data.prompt_preflight_summary_token_count ?? 90000;
  appSettings.summary_source_target_tokens = data.summary_source_target_tokens ?? 6000;
  appSettings.summary_retry_min_source_tokens = data.summary_retry_min_source_tokens ?? 1500;
  appSettings.prompt_max_input_tokens = data.prompt_max_input_tokens ?? 80000;
  appSettings.prompt_response_token_reserve = data.prompt_response_token_reserve ?? 8000;
  appSettings.prompt_recent_history_max_tokens = data.prompt_recent_history_max_tokens ?? 32000;
  appSettings.prompt_summary_max_tokens = data.prompt_summary_max_tokens ?? 12000;
  appSettings.prompt_rag_max_tokens = data.prompt_rag_max_tokens ?? 18000;
  appSettings.prompt_tool_memory_max_tokens = data.prompt_tool_memory_max_tokens ?? 10000;
  appSettings.prompt_tool_trace_max_tokens = data.prompt_tool_trace_max_tokens ?? 9000;
  appSettings.context_compaction_threshold = data.context_compaction_threshold ?? 0.85;
  appSettings.context_compaction_keep_recent_rounds = data.context_compaction_keep_recent_rounds ?? 2;
  appSettings.context_selection_strategy = data.context_selection_strategy || "classic";
  appSettings.entropy_profile = data.entropy_profile || "balanced";
  appSettings.entropy_rag_budget_ratio = data.entropy_rag_budget_ratio ?? 35;
  appSettings.entropy_protect_code_blocks = Boolean(data.entropy_protect_code_blocks ?? true);
  appSettings.entropy_protect_tool_results = Boolean(data.entropy_protect_tool_results ?? true);
  appSettings.entropy_reference_boost = Boolean(data.entropy_reference_boost ?? true);
  appSettings.reasoning_auto_collapse = Boolean(data.reasoning_auto_collapse);
  appSettings.tool_memory_auto_inject = Boolean(data.tool_memory_auto_inject);
  appSettings.pruning_enabled = Boolean(data.pruning_enabled);
  appSettings.pruning_token_threshold = data.pruning_token_threshold || 80000;
  appSettings.pruning_batch_size = data.pruning_batch_size || 10;
  appSettings.pruning_target_reduction_ratio = data.pruning_target_reduction_ratio ?? 0.65;
  appSettings.pruning_min_target_tokens = data.pruning_min_target_tokens ?? 160;
  appSettings.fetch_url_token_threshold = data.fetch_url_token_threshold || 3500;
  appSettings.fetch_url_clip_aggressiveness = data.fetch_url_clip_aggressiveness ?? 50;
  appSettings.fetch_html_converter_mode = data.fetch_html_converter_mode || "hybrid";
  appSettings.fetch_url_summarized_max_input_chars = data.fetch_url_summarized_max_input_chars || 80000;
  appSettings.fetch_url_summarized_max_output_tokens = data.fetch_url_summarized_max_output_tokens || 2400;
  appSettings.canvas_prompt_max_lines = data.canvas_prompt_max_lines || 250;
  appSettings.canvas_prompt_max_tokens = data.canvas_prompt_max_tokens || 4000;
  appSettings.canvas_prompt_max_chars = data.canvas_prompt_max_chars || 20000;
  appSettings.canvas_prompt_code_line_max_chars = data.canvas_prompt_code_line_max_chars || 180;
  appSettings.canvas_prompt_text_line_max_chars = data.canvas_prompt_text_line_max_chars || 100;
  appSettings.canvas_expand_max_lines = data.canvas_expand_max_lines || 1600;
  appSettings.canvas_scroll_window_lines = data.canvas_scroll_window_lines || 200;
  appSettings.rag_chunk_size = data.rag_chunk_size ?? 1800;
  appSettings.rag_chunk_overlap = data.rag_chunk_overlap ?? 250;
  appSettings.rag_max_chunks_per_source = data.rag_max_chunks_per_source ?? 2;
  appSettings.rag_search_top_k = data.rag_search_top_k ?? 5;
  appSettings.rag_search_min_similarity = data.rag_search_min_similarity ?? 0.35;
  appSettings.rag_query_expansion_enabled = Boolean(data.rag_query_expansion_enabled ?? true);
  appSettings.rag_query_expansion_max_variants = data.rag_query_expansion_max_variants ?? 2;
  appSettings.tool_memory_ttl_default_seconds = data.tool_memory_ttl_default_seconds ?? 604800;
  appSettings.tool_memory_ttl_web_seconds = data.tool_memory_ttl_web_seconds ?? 43200;
  appSettings.tool_memory_ttl_news_seconds = data.tool_memory_ttl_news_seconds ?? 7200;
  appSettings.fetch_raw_max_text_chars = data.fetch_raw_max_text_chars ?? 24000;
  appSettings.fetch_summary_max_chars = data.fetch_summary_max_chars ?? 8000;
  appSettings.sub_agent_allowed_tool_names = Array.isArray(data.sub_agent_allowed_tool_names) ? data.sub_agent_allowed_tool_names : [];
  appSettings.active_tools = Array.isArray(data.active_tools) ? data.active_tools : [];
  appSettings.proxy_enabled_operations = Array.isArray(data.proxy_enabled_operations) ? data.proxy_enabled_operations : [];
  appSettings.rag_auto_inject = Boolean(data.rag_auto_inject);
  appSettings.rag_sensitivity = data.rag_sensitivity || "normal";
  appSettings.rag_context_size = data.rag_context_size || "medium";
  appSettings.rag_source_types = Array.isArray(data.rag_source_types) ? data.rag_source_types : [];
  appSettings.rag_auto_inject_source_types = Array.isArray(data.rag_auto_inject_source_types)
    ? data.rag_auto_inject_source_types
    : appSettings.rag_source_types;
  if (data.features && typeof data.features === "object") {
    Object.assign(featureFlags, data.features);
  }
}

async function refreshSettings() {
  try {
    const response = await fetch("/api/settings");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to load settings.");
    }

    applyServerSettingsData(data);

    applySettingsToForm();
    applyFeatureAvailability();
    hasUnsavedSettingsChanges = false;
    hasUnsavedPersonaChanges = false;
    updateDirtyIndicators();
    setSettingsStatus("Ready");
    setDirtyPill("All changes saved", "muted");
  } catch (error) {
    setSettingsStatus(error.message || "Failed to load settings.", "error");
    setDirtyPill("Load failed", "error");
  }
}

async function saveSettings() {
  const scratchpadSections = readScratchpadSectionsFromList();
  const previousSettingsSnapshot = { ...appSettings };
  const isRagEnabledDraft = Boolean(ragEnabledEl?.checked);
  const payload = {
    default_persona_id: defaultPersonaEl?.value || "",
    temperature: readFloatSetting(temperatureEl, 0.7, { min: 0, max: 2 }),
    max_steps: readNumericSetting(maxStepsEl, 5, { allowZero: false }),
    max_parallel_tools: readNumericSetting(maxParallelToolsEl, 4, { allowZero: false }),
    search_tool_query_limit: readNumericSetting(searchToolQueryLimitEl, 5, { allowZero: false, min: 1, max: 20 }),
    sub_agent_max_steps: readNumericSetting(subAgentMaxStepsEl, 6, { allowZero: false }),
    sub_agent_timeout_seconds: readNumericSetting(subAgentTimeoutSecondsEl, 240, { allowZero: false }),
    sub_agent_retry_attempts: readNumericSetting(subAgentRetryAttemptsEl, 2),
    sub_agent_retry_delay_seconds: readNumericSetting(subAgentRetryDelaySecondsEl, 5),
    sub_agent_max_parallel_tools: readNumericSetting(subAgentMaxParallelToolsEl, 2, { allowZero: false }),
    web_cache_ttl_hours: readNumericSetting(webCacheTtlHoursEl, 24),
    openrouter_prompt_cache_enabled: Boolean(openrouterPromptCacheEnabledEl?.checked),
    openrouter_http_referer: String(openrouterHttpRefererEl?.value || "").trim(),
    openrouter_app_title: String(openrouterAppTitleEl?.value || "").trim(),
    login_session_timeout_minutes: readNumericSetting(loginSessionTimeoutMinutesEl, 30, { allowZero: false }),
    login_max_failed_attempts: readNumericSetting(loginMaxFailedAttemptsEl, 3, { allowZero: false }),
    login_lockout_seconds: readNumericSetting(loginLockoutSecondsEl, 300, { allowZero: false }),
    login_remember_session_days: readNumericSetting(loginRememberSessionDaysEl, 3650, { allowZero: false }),
    clarification_max_questions: readNumericSetting(clarificationMaxQuestionsEl, 5, { allowZero: false }),
    chat_summary_mode: summaryModeEl?.value || "auto",
    chat_summary_detail_level: summaryDetailLevelEl?.value || "balanced",
    chat_summary_trigger_token_count: readNumericSetting(summaryTriggerEl, 80000, { allowZero: false }),
    summary_skip_first: readNumericSetting(summarySkipFirstEl, 0),
    summary_skip_last: readNumericSetting(summarySkipLastEl, 1),
    prompt_preflight_summary_token_count: readNumericSetting(promptPreflightSummaryTokenCountEl, 90000, { allowZero: false, min: 2000, max: 200000 }),
    summary_source_target_tokens: readNumericSetting(summarySourceTargetTokensEl, 6000, { allowZero: false, min: 1000, max: 40000 }),
    summary_retry_min_source_tokens: readNumericSetting(summaryRetryMinSourceTokensEl, 1500, { allowZero: false, min: 500, max: 40000 }),
    prompt_max_input_tokens: readNumericSetting(promptMaxInputTokensEl, 80000, { allowZero: false, min: 8000, max: 120000 }),
    prompt_response_token_reserve: readNumericSetting(promptResponseTokenReserveEl, 8000, { allowZero: false, min: 1000, max: 32000 }),
    prompt_recent_history_max_tokens: readNumericSetting(promptRecentHistoryMaxTokensEl, 32000, { allowZero: false, min: 1000, max: 120000 }),
    prompt_summary_max_tokens: readNumericSetting(promptSummaryMaxTokensEl, 12000, { allowZero: false, min: 500, max: 120000 }),
    prompt_rag_max_tokens: readNumericSetting(promptRagMaxTokensEl, 18000, { min: 0, max: 120000 }),
    prompt_tool_memory_max_tokens: readNumericSetting(promptToolMemoryMaxTokensEl, 10000, { min: 0, max: 120000 }),
    prompt_tool_trace_max_tokens: readNumericSetting(promptToolTraceMaxTokensEl, 9000, { min: 0, max: 120000 }),
    context_compaction_threshold: readFloatSetting(contextCompactionThresholdEl, 0.85, { min: 0.5, max: 0.98 }),
    context_compaction_keep_recent_rounds: readNumericSetting(contextCompactionKeepRecentRoundsEl, 2, { min: 0, max: 6 }),
    context_selection_strategy: contextSelectionStrategyEl?.value || "classic",
    entropy_profile: entropyProfileEl?.value || "balanced",
    entropy_rag_budget_ratio: readNumericSetting(entropyRagBudgetRatioEl, 35, { min: 0, max: 80 }),
    entropy_protect_code_blocks: Boolean(entropyProtectCodeBlocksEl?.checked),
    entropy_protect_tool_results: Boolean(entropyProtectToolResultsEl?.checked),
    entropy_reference_boost: Boolean(entropyReferenceBoostEl?.checked),
    tool_memory_auto_inject: isRagEnabledDraft ? Boolean(toolMemoryAutoInjectEl?.checked) : false,
    pruning_enabled: Boolean(pruningEnabledEl?.checked),
    pruning_token_threshold: readNumericSetting(pruningTokenThresholdEl, 80000, { allowZero: false }),
    pruning_batch_size: readNumericSetting(pruningBatchSizeEl, 10, { allowZero: false }),
    pruning_target_reduction_ratio: readFloatSetting(pruningTargetReductionRatioEl, 0.65, { min: 0.1, max: 0.9 }),
    pruning_min_target_tokens: readNumericSetting(pruningMinTargetTokensEl, 160, { allowZero: false, min: 50, max: 5000 }),
    fetch_url_token_threshold: readNumericSetting(fetchThresholdEl, 3500, { allowZero: false }),
    fetch_url_clip_aggressiveness: readNumericSetting(fetchAggressivenessEl, 50),
    fetch_html_converter_mode: String(fetchHtmlConverterModeEl?.value || "hybrid"),
    fetch_url_summarized_max_input_chars: readNumericSetting(fetchSummarizeMaxInputCharsEl, 80000, { allowZero: false, min: 4000, max: 100000 }),
    fetch_url_summarized_max_output_tokens: readNumericSetting(fetchSummarizeMaxOutputTokensEl, 2400, { allowZero: false, min: 200, max: 4000 }),
    canvas_prompt_max_lines: readNumericSetting(canvasPromptLinesEl, 250, { allowZero: false }),
    canvas_prompt_max_tokens: readNumericSetting(canvasPromptTokensEl, 4000, { allowZero: false }),
    canvas_prompt_max_chars: readNumericSetting(canvasPromptCharsEl, 20000, { allowZero: false }),
    canvas_prompt_code_line_max_chars: readNumericSetting(canvasCodeLineCharsEl, 180, { allowZero: false }),
    canvas_prompt_text_line_max_chars: readNumericSetting(canvasTextLineCharsEl, 100, { allowZero: false }),
    canvas_expand_max_lines: readNumericSetting(canvasExpandLinesEl, 1600, { allowZero: false }),
    canvas_scroll_window_lines: readNumericSetting(canvasScrollLinesEl, 200, { allowZero: false }),
    conversation_memory_enabled: Boolean(conversationMemoryEnabledEl?.checked),
    ocr_enabled: Boolean(ocrEnabledEl?.checked),
    ocr_provider: String(ocrProviderEl?.value || "paddleocr"),
    rag_enabled: Boolean(ragEnabledEl?.checked),
    youtube_transcripts_enabled: Boolean(youtubeTranscriptsEnabledEl?.checked),
    youtube_transcript_language: String(youtubeTranscriptLanguageEl?.value || "").trim(),
    youtube_transcript_model_size: String(youtubeTranscriptModelSizeEl?.value || "small"),
    chat_summary_model: String(chatSummaryModelEl?.value || ""),
    rag_chunk_size: readNumericSetting(ragChunkSizeEl, 1800, { allowZero: false, min: 100, max: 8000 }),
    rag_chunk_overlap: readNumericSetting(ragChunkOverlapEl, 250, { min: 0, max: 4000 }),
    rag_max_chunks_per_source: readNumericSetting(ragMaxChunksPerSourceEl, 2, { allowZero: false, min: 1, max: 20 }),
    rag_search_top_k: readNumericSetting(ragSearchTopKEl, 5, { allowZero: false, min: 1, max: 50 }),
    rag_search_min_similarity: readFloatSetting(ragSearchMinSimilarityEl, 0.35, { min: 0, max: 1 }),
    rag_query_expansion_enabled: Boolean(ragQueryExpansionEnabledEl?.checked),
    rag_query_expansion_max_variants: readNumericSetting(ragQueryExpansionMaxVariantsEl, 2, { allowZero: false, min: 1, max: 10 }),
    tool_memory_ttl_default_seconds: readNumericSetting(toolMemoryTtlDefaultSecondsEl, 604800, { allowZero: false, min: 60 }),
    tool_memory_ttl_web_seconds: readNumericSetting(toolMemoryTtlWebSecondsEl, 43200, { allowZero: false, min: 60 }),
    tool_memory_ttl_news_seconds: readNumericSetting(toolMemoryTtlNewsSecondsEl, 7200, { allowZero: false, min: 60 }),
    fetch_raw_max_text_chars: readNumericSetting(fetchRawMaxTextCharsEl, 24000, { allowZero: false, min: 1000 }),
    fetch_summary_max_chars: readNumericSetting(fetchSummaryMaxCharsEl, 8000, { allowZero: false, min: 500 }),
    custom_models: draftCustomModels.map((model) => serializeDraftCustomModel(model)),
    visible_model_order: getDraftVisibleModelOrder(),
    operation_model_preferences: getOperationModelPreferencesDraft(),
    operation_model_fallback_preferences: getOperationModelFallbackPreferencesDraft(),
    image_processing_method: imageProcessingMethodEl?.value || "auto",
    image_helper_model: imageHelperModelEl?.value || "",
    active_tools: getSelectedTools(),
    sub_agent_allowed_tool_names: getSelectedSubAgentTools(),
    proxy_enabled_operations: getSelectedProxyOperations(),
    rag_auto_inject: isRagEnabledDraft ? getSelectedRagAutoInjectSourceTypes().length > 0 : false,
    rag_sensitivity: ragSensitivityEl?.value || "normal",
    rag_context_size: ragContextSizeEl?.value || "medium",
    rag_source_types: isRagEnabledDraft ? getSelectedRagSourceTypes() : [],
    rag_auto_inject_source_types: isRagEnabledDraft ? getSelectedRagAutoInjectSourceTypes() : [],
    scratchpad: (scratchpadSections[DEFAULT_SCRATCHPAD_SECTION_ID] || []).join("\n"),
    scratchpad_sections: DEFAULT_SCRATCHPAD_SECTION_ORDER.reduce((acc, sectionId) => {
      acc[sectionId] = (scratchpadSections[sectionId] || []).join("\n");
      return acc;
    }, {}),
  };

  if (reasoningAutoCollapseEl) {
    payload.reasoning_auto_collapse = Boolean(reasoningAutoCollapseEl.checked);
  }

  saveButtons.forEach((button) => {
    button.disabled = true;
  });
  setSettingsStatus("Saving...");
  setDirtyPill("Saving...", "warning");

  try {
    const response = await fetch("/api/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to save settings.");
    }

    const restartNeeded = hasRestartRequiredChanges(payload, previousSettingsSnapshot);
    applyServerSettingsData(data);

    applySettingsToForm();
    applyFeatureAvailability();
    clearDirtyState();
    if (restartNeeded) {
      showRestartWarning("Some changes are saved but will take effect after restarting the server.");
      setSettingsStatus("Saved — restart required for some changes.", "warning");
    } else {
      hideRestartWarning();
    }
  } catch (error) {
    setSettingsStatus(error.message || "Failed to save settings.", "error");
    setDirtyPill("Save failed", "error");
  } finally {
    saveButtons.forEach((button) => {
      button.disabled = false;
    });
  }
}

function setKbStatus(message, tone = "muted") {
  if (!kbStatusEl) {
    return;
  }
  kbStatusEl.textContent = message;
  kbStatusEl.dataset.tone = tone;
}

function setKbUploadStatus(message, tone = "muted") {
  if (!kbUploadStatusEl) {
    return;
  }
  kbUploadStatusEl.textContent = message;
  kbUploadStatusEl.dataset.tone = tone;
}

function syncKbUploadActionState() {
  const ragEnabled = Boolean(featureFlags.rag_enabled);
  const hasFile = Boolean(kbUploadFileEl?.files?.length);

  if (kbSuggestBtn) {
    kbSuggestBtn.disabled = !ragEnabled || !hasFile;
  }
  if (kbUploadBtn) {
    kbUploadBtn.disabled = !ragEnabled || !hasFile;
  }
}

function summarizeKbDocument(doc) {
  const metadata = doc && typeof doc.metadata === "object" ? doc.metadata : {};
  const parts = [RAG_SOURCE_TYPE_LABELS[doc.source_type] || doc.source_type || "Document"];
  if (doc.category) {
    parts.push(doc.category);
  }
  parts.push(`${doc.chunk_count || 0} chunks`);
  if (metadata.file_name) {
    parts.unshift(metadata.file_name);
  }
  return parts.join(" · ");
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
    sub.textContent = summarizeKbDocument(doc);

    meta.append(title, sub);

    const metadata = doc && typeof doc.metadata === "object" ? doc.metadata : {};
    const description = String(metadata.description || "").trim();
    if (description) {
      const descriptionEl = document.createElement("div");
      descriptionEl.className = "kb-doc-description";
      descriptionEl.textContent = description;
      meta.append(descriptionEl);
    }

    const badges = document.createElement("div");
    badges.className = "kb-doc-badges";
    if (doc.source_type === "uploaded_document") {
      const uploadBadge = document.createElement("span");
      uploadBadge.className = "kb-doc-badge";
      uploadBadge.textContent = "manual upload";
      badges.append(uploadBadge);
    }
    const autoInjectBadge = document.createElement("span");
    autoInjectBadge.className = "kb-doc-badge";
    autoInjectBadge.dataset.tone = metadata.auto_inject_enabled === false ? "muted" : "success";
    autoInjectBadge.textContent = metadata.auto_inject_enabled === false ? "manual only" : "auto inject on";
    badges.append(autoInjectBadge);
    meta.append(badges);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "kb-doc-delete";
    del.textContent = "Delete";
    del.addEventListener("click", () => {
      void deleteKnowledgeBaseDocument(doc.source_key);
    });

    item.append(meta, del);
    kbDocumentsListEl.append(item);
  });
}

async function loadKnowledgeBaseDocuments() {
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
    setKbStatus("Failed to load indexed sources.", "error");
  }
}

async function deleteKnowledgeBaseDocument(sourceKey) {
  if (!sourceKey) {
    return;
  }
  setKbStatus("Deleting source...");
  try {
    const response = await fetch(`/api/rag/documents/${encodeURIComponent(sourceKey)}`, { method: "DELETE" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Delete failed.");
    }
    setKbStatus("Source deleted", "success");
    await loadKnowledgeBaseDocuments();
  } catch (error) {
    setKbStatus(error.message || "Delete failed.", "error");
  }
}

async function uploadKnowledgeBaseDocument() {
  if (!Boolean(featureFlags.rag_enabled)) {
    setKbUploadStatus("RAG disabled in .env", "warning");
    return;
  }

  const file = kbUploadFileEl?.files?.[0];
  if (!file) {
    setKbUploadStatus("Choose a document to upload.", "warning");
    return;
  }

  const formData = new FormData();
  formData.append("document", file);
  formData.append("source_name", kbUploadTitleEl?.value.trim() || "");
  formData.append("description", kbUploadDescriptionEl?.value.trim() || "");
  formData.append("auto_inject_enabled", kbUploadAutoInjectEl?.checked ? "true" : "false");

  if (kbUploadBtn) {
    kbUploadBtn.disabled = true;
  }
  if (kbSuggestBtn) {
    kbSuggestBtn.disabled = true;
  }
  setKbUploadStatus("Uploading document...");

  try {
    const response = await fetch("/api/rag/ingest", {
      method: "POST",
      body: formData,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Upload failed.");
    }

    if (kbUploadFileEl) {
      kbUploadFileEl.value = "";
    }
    if (kbUploadTitleEl) {
      kbUploadTitleEl.value = "";
    }
    if (kbUploadDescriptionEl) {
      kbUploadDescriptionEl.value = "";
      autoResize(kbUploadDescriptionEl);
    }
    if (kbUploadAutoInjectEl) {
      kbUploadAutoInjectEl.checked = true;
    }

    const sourceName = data.document?.source_name || data.file_name || "Document";
    setKbUploadStatus(`${sourceName} indexed`, "success");
    await loadKnowledgeBaseDocuments();
  } catch (error) {
    setKbUploadStatus(error.message || "Upload failed.", "error");
  } finally {
    syncKbUploadActionState();
  }
}

async function generateKnowledgeBaseMetadata() {
  if (!Boolean(featureFlags.rag_enabled)) {
    setKbUploadStatus("RAG disabled in .env", "warning");
    return;
  }

  const file = kbUploadFileEl?.files?.[0];
  if (!file) {
    setKbUploadStatus("Choose a document first.", "warning");
    return;
  }

  const formData = new FormData();
  formData.append("document", file);
  formData.append("source_name", kbUploadTitleEl?.value.trim() || "");
  formData.append("description", kbUploadDescriptionEl?.value.trim() || "");

  if (kbSuggestBtn) {
    kbSuggestBtn.disabled = true;
  }
  if (kbUploadBtn) {
    kbUploadBtn.disabled = true;
  }
  setKbUploadStatus("Generating title and description...", "muted");

  try {
    const response = await fetch("/api/rag/upload-metadata", {
      method: "POST",
      body: formData,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Metadata generation failed.");
    }

    if (kbUploadTitleEl && typeof data.title === "string") {
      kbUploadTitleEl.value = data.title;
    }
    if (kbUploadDescriptionEl && typeof data.description === "string") {
      kbUploadDescriptionEl.value = data.description;
      autoResize(kbUploadDescriptionEl);
    }

    setKbUploadStatus("Title and description generated.", "success");
  } catch (error) {
    setKbUploadStatus(error.message || "Metadata generation failed.", "error");
  } finally {
    syncKbUploadActionState();
  }
}

async function syncKnowledgeBaseConversations() {
  if (!Boolean(featureFlags.rag_enabled)) {
    setKbStatus("RAG disabled in .env", "warning");
    return;
  }

  if (kbSyncBtn) {
    kbSyncBtn.disabled = true;
  }
  setKbStatus("Syncing conversations into RAG...");

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
    await loadKnowledgeBaseDocuments();
  } catch (error) {
    setKbStatus(error.message || "Conversation sync failed.", "error");
  } finally {
    if (kbSyncBtn) {
      kbSyncBtn.disabled = false;
    }
  }
}

function activateTab(tabId, updateHash = true) {
  const normalizedTabId = String(tabId || "general");
  const nextId = SETTINGS_TAB_ALIASES[normalizedTabId] || normalizedTabId;

  tabButtons.forEach((button) => {
    const isActive = button.dataset.settingsTab === nextId;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });

  tabPanels.forEach((panel) => {
    const isActive = panel.dataset.settingsPanel === nextId;
    panel.classList.toggle("active", isActive);
    panel.toggleAttribute("hidden", !isActive);
  });

  if (updateHash) {
    history.replaceState(null, "", `#${nextId}`);
  }
}

function initializeTabs() {
  tabButtons.forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.settingsTab));
  });

  const hash = String(window.location.hash || "").replace(/^#/, "");
  const resolvedHash = SETTINGS_TAB_ALIASES[hash] || hash;
  const initialTab = tabButtons.some((button) => button.dataset.settingsTab === resolvedHash) ? resolvedHash : "general";
  activateTab(initialTab, false);
}

function registerDirtyListeners() {
  personaNameEl?.addEventListener("input", markPersonaDirty);
  generalInstructionsEl?.addEventListener("input", () => {
    autoResize(generalInstructionsEl);
    markPersonaDirty();
  });
  aiPersonalityEl?.addEventListener("input", () => {
    autoResize(aiPersonalityEl);
    markPersonaDirty();
  });
  defaultPersonaEl?.addEventListener("change", markDirty);
  maxStepsEl?.addEventListener("input", markDirty);
  maxParallelToolsEl?.addEventListener("input", markDirty);
  searchToolQueryLimitEl?.addEventListener("input", markDirty);
  subAgentMaxStepsEl?.addEventListener("input", markDirty);
  subAgentTimeoutSecondsEl?.addEventListener("input", markDirty);
  subAgentRetryAttemptsEl?.addEventListener("input", markDirty);
  subAgentRetryDelaySecondsEl?.addEventListener("input", markDirty);
  subAgentMaxParallelToolsEl?.addEventListener("input", markDirty);
  webCacheTtlHoursEl?.addEventListener("input", markDirty);
  openrouterPromptCacheEnabledEl?.addEventListener("change", markDirty);
  clarificationMaxQuestionsEl?.addEventListener("input", markDirty);
  summaryModeEl?.addEventListener("change", markDirty);
  summaryDetailLevelEl?.addEventListener("change", markDirty);
  summaryTriggerEl?.addEventListener("input", markDirty);
  summarySkipFirstEl?.addEventListener("input", markDirty);
  summarySkipLastEl?.addEventListener("input", markDirty);
  promptPreflightSummaryTokenCountEl?.addEventListener("input", markDirty);
  summarySourceTargetTokensEl?.addEventListener("input", markDirty);
  summaryRetryMinSourceTokensEl?.addEventListener("input", markDirty);
  promptMaxInputTokensEl?.addEventListener("input", markDirty);
  promptResponseTokenReserveEl?.addEventListener("input", markDirty);
  promptRecentHistoryMaxTokensEl?.addEventListener("input", markDirty);
  promptSummaryMaxTokensEl?.addEventListener("input", markDirty);
  promptRagMaxTokensEl?.addEventListener("input", markDirty);
  promptToolMemoryMaxTokensEl?.addEventListener("input", markDirty);
  promptToolTraceMaxTokensEl?.addEventListener("input", markDirty);
  contextCompactionThresholdEl?.addEventListener("input", markDirty);
  contextCompactionKeepRecentRoundsEl?.addEventListener("input", markDirty);
  contextSelectionStrategyEl?.addEventListener("change", () => {
    syncContextStrategyAvailability();
    markDirty();
  });
  entropyProfileEl?.addEventListener("change", markDirty);
  entropyRagBudgetRatioEl?.addEventListener("input", markDirty);
  entropyProtectCodeBlocksEl?.addEventListener("change", markDirty);
  entropyProtectToolResultsEl?.addEventListener("change", markDirty);
  entropyReferenceBoostEl?.addEventListener("change", markDirty);
  reasoningAutoCollapseEl?.addEventListener("change", markDirty);
  toolMemoryAutoInjectEl?.addEventListener("change", markDirty);
  pruningEnabledEl?.addEventListener("change", () => {
    syncPruningSettingsAvailability();
    markDirty();
  });
  pruningTokenThresholdEl?.addEventListener("input", markDirty);
  pruningBatchSizeEl?.addEventListener("input", markDirty);
  pruningTargetReductionRatioEl?.addEventListener("input", markDirty);
  pruningMinTargetTokensEl?.addEventListener("input", markDirty);
  fetchThresholdEl?.addEventListener("input", markDirty);
  fetchAggressivenessEl?.addEventListener("input", markDirty);
  fetchHtmlConverterModeEl?.addEventListener("change", markDirty);
  fetchSummarizeMaxInputCharsEl?.addEventListener("input", markDirty);
  fetchSummarizeMaxOutputTokensEl?.addEventListener("input", markDirty);
  canvasPromptLinesEl?.addEventListener("input", markDirty);
  canvasPromptTokensEl?.addEventListener("input", markDirty);
  canvasPromptCharsEl?.addEventListener("input", markDirty);
  canvasCodeLineCharsEl?.addEventListener("input", markDirty);
  canvasTextLineCharsEl?.addEventListener("input", markDirty);
  canvasExpandLinesEl?.addEventListener("input", markDirty);
  canvasScrollLinesEl?.addEventListener("input", markDirty);
  summaryModelPreferenceEl?.addEventListener("change", markDirty);
  fetchSummarizeModelPreferenceEl?.addEventListener("change", markDirty);
  pruneModelPreferenceEl?.addEventListener("change", markDirty);
  fixTextModelPreferenceEl?.addEventListener("change", markDirty);
  titleModelPreferenceEl?.addEventListener("change", markDirty);
  uploadMetadataModelPreferenceEl?.addEventListener("change", markDirty);
  subAgentModelPreferenceEl?.addEventListener("change", markDirty);
  imageHelperModelEl?.addEventListener("change", markDirty);
  imageProcessingMethodEl?.addEventListener("change", markDirty);
  ragSensitivityEl?.addEventListener("change", () => {
    updateRagSensitivityHint();
    markDirty();
  });
  ragContextSizeEl?.addEventListener("change", markDirty);
  ragSourceTypeEls.forEach((element) => {
    element.addEventListener("change", () => {
      syncRagAutoInjectSourceAvailability();
      updateRagSourceSummary();
      syncOverviewStats();
      markDirty();
    });
  });
  ragAutoInjectSourceTypeEls.forEach((element) => {
    element.addEventListener("change", () => {
      updateRagAutoInjectSourceSummary();
      syncOverviewStats();
      markDirty();
    });
  });
  toolToggleEls.forEach((element) => {
    element.addEventListener("change", () => {
      markDirty();
      syncOverviewStats();
    });
  });
  proxyOperationEls.forEach((element) => {
    element.addEventListener("change", markDirty);
  });
  subAgentToolToggleEls.forEach((element) => {
    element.addEventListener("change", markDirty);
  });
}

scratchpadAddBtn?.addEventListener("click", () => addScratchpadNote());
generalInstructionsTemplateApplyBtn?.addEventListener("click", () => {
  applyBehaviorTemplate(generalInstructionsTemplateSelectEl, generalInstructionsEl, GENERAL_INSTRUCTION_TEMPLATES);
});
aiPersonalityTemplateApplyBtn?.addEventListener("click", () => {
  applyBehaviorTemplate(aiPersonalityTemplateSelectEl, aiPersonalityEl, AI_PERSONALITY_TEMPLATES);
});
openPersonasTabBtn?.addEventListener("click", () => activateTab("personas"));
personaNewBtn?.addEventListener("click", () => {
  if (hasUnsavedPersonaChanges && !window.confirm("Discard unsaved persona changes?")) {
    return;
  }
  selectPersonaForEditing(null);
});
personaSaveBtn?.addEventListener("click", () => {
  void saveActivePersona();
});
personaDeleteBtn?.addEventListener("click", () => {
  void deleteActivePersona();
});
personaMemoryValueEl?.addEventListener("input", () => {
  autoResize(personaMemoryValueEl);
});
personaMemorySaveBtn?.addEventListener("click", () => {
  void saveActivePersonaMemoryEntry();
});
personaMemoryCancelBtn?.addEventListener("click", () => {
  resetPersonaMemoryEditor();
  renderPersonaMemoryList();
});
personaMemoryDeleteBtn?.addEventListener("click", () => {
  void deleteActivePersonaMemoryEntry();
});
addCustomModelBtn?.addEventListener("click", addCustomModelFromInputs);
  customModelCancelEditBtn?.addEventListener("click", () => {
    cancelEditingCustomModel();
  });
customModelReasoningModeEl?.addEventListener("change", syncCustomModelReasoningControls);
customModelRoutingModeEl?.addEventListener("change", syncCustomModelProviderControls);
summaryModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("summarize"));
fetchSummarizeModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("fetch_summarize"));
pruneModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("prune"));
fixTextModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("fix_text"));
titleModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("generate_title"));
uploadMetadataModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("upload_metadata"));
subAgentModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("sub_agent"));
  openrouterHttpRefererEl?.addEventListener("input", markDirty);
  openrouterAppTitleEl?.addEventListener("input", markDirty);
  loginSessionTimeoutMinutesEl?.addEventListener("input", markDirty);
  loginMaxFailedAttemptsEl?.addEventListener("input", markDirty);
  loginLockoutSecondsEl?.addEventListener("input", markDirty);
  loginRememberSessionDaysEl?.addEventListener("input", markDirty);
  conversationMemoryEnabledEl?.addEventListener("change", markDirty);
  ocrEnabledEl?.addEventListener("change", markDirty);
  ocrProviderEl?.addEventListener("change", markDirty);
  ragEnabledEl?.addEventListener("change", markDirty);
  youtubeTranscriptsEnabledEl?.addEventListener("change", markDirty);
  youtubeTranscriptLanguageEl?.addEventListener("input", markDirty);
  youtubeTranscriptModelSizeEl?.addEventListener("change", markDirty);
  chatSummaryModelEl?.addEventListener("change", markDirty);
  ragChunkSizeEl?.addEventListener("input", markDirty);
  ragChunkOverlapEl?.addEventListener("input", markDirty);
  ragMaxChunksPerSourceEl?.addEventListener("input", markDirty);
  ragSearchTopKEl?.addEventListener("input", markDirty);
  ragSearchMinSimilarityEl?.addEventListener("input", markDirty);
  ragQueryExpansionEnabledEl?.addEventListener("change", markDirty);
  ragQueryExpansionMaxVariantsEl?.addEventListener("input", markDirty);
  toolMemoryTtlDefaultSecondsEl?.addEventListener("input", markDirty);
  toolMemoryTtlWebSecondsEl?.addEventListener("input", markDirty);
  toolMemoryTtlNewsSecondsEl?.addEventListener("input", markDirty);
  fetchRawMaxTextCharsEl?.addEventListener("input", markDirty);
  fetchSummaryMaxCharsEl?.addEventListener("input", markDirty);
kbUploadFileEl?.addEventListener("change", () => {
  const filename = kbUploadFileEl.files?.[0]?.name || "";
  if (filename && kbUploadTitleEl && !kbUploadTitleEl.value.trim()) {
    kbUploadTitleEl.value = filename.replace(/\.[^.]+$/, "");
  }
  syncKbUploadActionState();
});
kbUploadDescriptionEl?.addEventListener("input", () => autoResize(kbUploadDescriptionEl));
kbSuggestBtn?.addEventListener("click", () => {
  void generateKnowledgeBaseMetadata();
});
kbUploadBtn?.addEventListener("click", () => {
  void uploadKnowledgeBaseDocument();
});
kbSyncBtn?.addEventListener("click", () => {
  void syncKnowledgeBaseConversations();
});
saveButtons.forEach((button) => {
  button.addEventListener("click", () => {
    void saveAllSettings();
  });
});

window.addEventListener("beforeunload", (event) => {
  if (!hasUnsavedSettingsChanges && !hasUnsavedPersonaChanges) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
});

window.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    void saveAllSettings();
  }
});

initializeTabs();
initializeAssistantBehaviorTemplates();
registerDirtyListeners();
applySettingsToForm();
applyFeatureAvailability();
syncKbUploadActionState();
setSettingsStatus("Ready");
setDirtyPill("All changes saved", "muted");
void refreshSettings();
void loadKnowledgeBaseDocuments();
