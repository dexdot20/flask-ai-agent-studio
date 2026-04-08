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

const generalInstructionsEl = document.getElementById("general-instructions-input");
const generalInstructionsTemplateSelectEl = document.getElementById("general-instructions-template-select");
const generalInstructionsTemplateApplyBtn = document.getElementById("general-instructions-template-apply-btn");
const aiPersonalityEl = document.getElementById("ai-personality-input");
const aiPersonalityTemplateSelectEl = document.getElementById("ai-personality-template-select");
const aiPersonalityTemplateApplyBtn = document.getElementById("ai-personality-template-apply-btn");
const temperatureEl = document.getElementById("temperature-input");
const scratchpadListEl = document.getElementById("scratchpad-list");
const scratchpadAddBtn = document.getElementById("scratchpad-add-btn");
const scratchpadCountEl = document.getElementById("scratchpad-count");
const scratchpadReadonlyNoteEl = document.getElementById("scratchpad-readonly-note");
const maxStepsEl = document.getElementById("max-steps-input");
const maxParallelToolsEl = document.getElementById("max-parallel-tools-input");
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
const contextSelectionStrategyEl = document.getElementById("context-selection-strategy-select");
const entropyProfileEl = document.getElementById("entropy-profile-select");
const entropyRagBudgetRatioEl = document.getElementById("entropy-rag-budget-ratio-input");
const entropyProtectCodeBlocksEl = document.getElementById("entropy-protect-code-blocks-toggle");
const entropyProtectToolResultsEl = document.getElementById("entropy-protect-tool-results-toggle");
const entropyReferenceBoostEl = document.getElementById("entropy-reference-boost-toggle");
const reasoningAutoCollapseEl = document.getElementById("reasoning-auto-collapse-toggle");
const pruningEnabledEl = document.getElementById("pruning-enabled-toggle");
const pruningTokenThresholdEl = document.getElementById("pruning-token-threshold-input");
const pruningBatchSizeEl = document.getElementById("pruning-batch-size-input");
const fetchThresholdEl = document.getElementById("fetch-threshold-input");
const fetchAggressivenessEl = document.getElementById("fetch-aggressiveness-input");
const canvasPromptLinesEl = document.getElementById("canvas-prompt-lines-input");
const canvasPromptTokensEl = document.getElementById("canvas-prompt-tokens-input");
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
    description: "Durable uncategorized context that does not fit the other sections.",
  },
  problems: {
    title: "Open Problems",
    description: "Unresolved issues, unknowns, or blockers worth revisiting later.",
  },
  tasks: {
    title: "In-Progress Tasks",
    description: "Longer-running workstreams the assistant should preserve continuity on.",
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

const builtinModelCatalog = Array.isArray(appSettings.available_models)
  ? appSettings.available_models.filter((model) => !Boolean(model?.is_custom))
  : [];

let hasUnsavedChanges = false;
let draftCustomModels = Array.isArray(appSettings.custom_models)
  ? appSettings.custom_models.map((model) => normalizeDraftCustomModel(model))
  : [];
let draftChatModelRows = [];
let draftOperationFallbackRows = {};
let fallbackRowSequence = 0;

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
  markDirty();
}

function initializeAssistantBehaviorTemplates() {
  populateBehaviorTemplateSelect(generalInstructionsTemplateSelectEl, GENERAL_INSTRUCTION_TEMPLATES);
  populateBehaviorTemplateSelect(aiPersonalityTemplateSelectEl, AI_PERSONALITY_TEMPLATES);
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

function markDirty() {
  hasUnsavedChanges = true;
  setSettingsStatus("Unsaved changes", "warning");
  setDirtyPill("Unsaved changes", "warning");
}

function clearDirtyState() {
  hasUnsavedChanges = false;
  setSettingsStatus("Saved", "success");
  setDirtyPill("All changes saved", "success");
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

function readNumericSetting(element, defaultValue, { allowZero = true } = {}) {
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
  return parsed;
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
  if (Number.isNaN(parsed) || parsed < min || parsed > max) {
    return defaultValue;
  }
  return parsed;
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
  if (rawValue.startsWith("openrouter:")) {
    return rawValue.slice("openrouter:".length).replace(/^\/+/, "").trim();
  }
  return rawValue.replace(/^\/+/, "").trim();
}

function splitOpenRouterModelId(value) {
  const normalizedValue = normalizeOpenRouterApiModel(value);
  if (!normalizedValue) {
    return { apiModel: "", variantSuffix: "" };
  }

  const separatorIndex = normalizedValue.indexOf("@@");
  if (separatorIndex < 0) {
    return { apiModel: normalizedValue, variantSuffix: "" };
  }

  return {
    apiModel: normalizedValue.slice(0, separatorIndex),
    variantSuffix: normalizedValue.slice(separatorIndex + 2),
  };
}

function normalizeOpenRouterVariantBool(value, defaultValue) {
  if (value === undefined || value === null || value === "") {
    return defaultValue;
  }
  return Boolean(value);
}

function parseOpenRouterModelVariantSuffix(value) {
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

  rawValue.split(";").forEach((part) => {
    const separatorIndex = part.indexOf("=");
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

function buildOpenRouterModelVariantSuffix(variant = {}) {
  const parts = [];
  const reasoning = normalizeOpenRouterReasoningConfig(variant.reasoning_mode ?? variant.reasoning_enabled, variant.reasoning_effort);

  if (reasoning.mode !== "default" || reasoning.effort) {
    parts.push(`r=${reasoning.effort ? `${reasoning.mode}:${reasoning.effort}` : reasoning.mode}`);
  }

  const providerSlug = normalizeOpenRouterProviderSlug(variant.provider_slug || variant.openrouter_provider || "");
  if (providerSlug) {
    parts.push(`p=${providerSlug}`);
  }

  if (normalizeOpenRouterVariantBool(variant.supports_tools, true) === false) {
    parts.push("t=0");
  }
  if (normalizeOpenRouterVariantBool(variant.supports_vision, false) === true) {
    parts.push("v=1");
  }
  if (normalizeOpenRouterVariantBool(variant.supports_structured_outputs, false) === true) {
    parts.push("s=1");
  }

  return parts.length ? `@@${parts.join(";")}` : "";
}

function buildOpenRouterModelId(apiModel, variant = {}) {
  const normalizedApiModel = normalizeOpenRouterApiModel(apiModel);
  if (!normalizedApiModel) {
    return "";
  }

  const split = splitOpenRouterModelId(normalizedApiModel);
  const variantSuffix = buildOpenRouterModelVariantSuffix(variant) || (split.variantSuffix ? `@@${split.variantSuffix}` : "");
  return `openrouter:${split.apiModel || normalizedApiModel}${variantSuffix}`;
}

function normalizeOpenRouterProviderSlug(value) {
  const rawValue = String(value || "").trim().replace(/^\/+|\/+$/g, "").toLowerCase();
  if (!rawValue) {
    return "";
  }
  return /^[a-z0-9][a-z0-9._/-]{0,199}$/.test(rawValue) ? rawValue : "";
}

function normalizeOpenRouterReasoningMode(value) {
  if (typeof value === "boolean") {
    return value ? "enabled" : "disabled";
  }
  const rawValue = String(value || "").trim().toLowerCase();
  if (["enabled", "1", "true", "yes", "on"].includes(rawValue)) {
    return "enabled";
  }
  if (["disabled", "0", "false", "no", "off"].includes(rawValue)) {
    return "disabled";
  }
  return "default";
}

function normalizeOpenRouterReasoningEffort(value) {
  const rawValue = String(value || "").trim().toLowerCase();
  return ["minimal", "low", "medium", "high", "xhigh"].includes(rawValue) ? rawValue : "";
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

function normalizeDraftCustomModel(model) {
  const parsedIdentity = splitOpenRouterModelId(model?.id || model?.api_model || model?.model || "");
  const parsedVariant = parseOpenRouterModelVariantSuffix(parsedIdentity.variantSuffix);
  const apiModel = normalizeOpenRouterApiModel(model?.api_model || model?.model || parsedIdentity.apiModel || "");
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
  const modelId = buildOpenRouterModelId(apiModel, {
    reasoning_mode: reasoning.mode,
    reasoning_effort: reasoning.effort,
    provider_slug: providerSlug,
    supports_tools: supportsTools,
    supports_vision: supportsVision,
    supports_structured_outputs: supportsStructuredOutputs,
  }) || String(model?.id || "").trim();
  return {
    ...model,
    id: modelId,
    name: String(model?.name || apiModel || modelId).trim() || apiModel || modelId,
    provider: "openrouter",
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
  return [...builtinModelCatalog, ...draftCustomModels].map((model) => ({ ...model }));
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
    emptyState.textContent = "No custom OpenRouter models configured yet.";
    customModelListEl.append(emptyState);
    return;
  }

  for (const model of draftCustomModels) {
    const row = document.createElement("div");
    row.className = "model-management-row";

    const meta = document.createElement("div");
    meta.className = "model-management-row__meta";

    const title = document.createElement("strong");
    title.textContent = model.name || model.api_model || model.id;

    const subtitle = document.createElement("div");
    subtitle.className = "model-management-row__subtitle";
    subtitle.textContent = [model.api_model || model.id, model.provider_slug ? `Route: ${model.provider_slug}` : ""]
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

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-ghost btn-ghost--danger";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => {
      draftCustomModels = draftCustomModels.filter((entry) => entry.id !== model.id);
      syncDraftChatModelRows();
      renderModelManagementPanels();
      markDirty();
      setCustomModelStatus("Custom model removed. Save to apply.", "warning");
    });

    row.append(meta, removeBtn);
    customModelListEl.append(row);
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

function renderOperationModelSelects(preferences = null) {
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
}

function renderModelManagementPanels({ preferVisibleId = "", operationPreferences = null } = {}) {
  syncDraftChatModelRows({ preferVisibleId });
  renderCustomModelList();
  renderChatModelVisibilityList();
  renderOperationModelSelects(operationPreferences);
  renderOperationFallbackLists();
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
    setCustomModelStatus("OpenRouter model id is required.", "error");
    return;
  }
  if (providerSelection.error) {
    setCustomModelStatus(providerSelection.error, "error");
    return;
  }

  const providerSlug = providerSelection.providerSlug;

  const modelId = buildOpenRouterModelId(apiModel, {
    reasoning_mode: reasoning.mode,
    reasoning_effort: reasoning.effort,
    provider_slug: providerSlug,
    supports_tools: Boolean(customModelSupportsToolsEl?.checked),
    supports_vision: Boolean(customModelSupportsVisionEl?.checked),
    supports_structured_outputs: Boolean(customModelSupportsStructuredEl?.checked),
  });
  if (!modelId) {
    setCustomModelStatus("OpenRouter model id is invalid.", "error");
    return;
  }
  if (draftCustomModels.some((model) => model.id === modelId)) {
    setCustomModelStatus("That OpenRouter model configuration is already configured.", "warning");
    return;
  }

  draftCustomModels = [
    ...draftCustomModels,
    normalizeDraftCustomModel({
      id: modelId,
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
    }),
  ];
  resetCustomModelForm();
  renderModelManagementPanels({ preferVisibleId: modelId });
  markDirty();
  setCustomModelStatus("OpenRouter model added. Save to apply.", "success");
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
  if (generalInstructionsEl) {
    generalInstructionsEl.value = appSettings.general_instructions || appSettings.user_preferences || "";
    autoResize(generalInstructionsEl);
  }
  if (aiPersonalityEl) {
    aiPersonalityEl.value = appSettings.ai_personality || "";
    autoResize(aiPersonalityEl);
  }
  if (temperatureEl) temperatureEl.value = String(appSettings.temperature ?? 0.7);
  if (maxStepsEl) maxStepsEl.value = String(appSettings.max_steps || 5);
  if (maxParallelToolsEl) maxParallelToolsEl.value = String(appSettings.max_parallel_tools ?? 4);
  if (subAgentMaxStepsEl) subAgentMaxStepsEl.value = String(appSettings.sub_agent_max_steps ?? 6);
  if (subAgentTimeoutSecondsEl) subAgentTimeoutSecondsEl.value = String(appSettings.sub_agent_timeout_seconds ?? 240);
  if (subAgentRetryAttemptsEl) subAgentRetryAttemptsEl.value = String(appSettings.sub_agent_retry_attempts ?? 2);
  if (subAgentRetryDelaySecondsEl) subAgentRetryDelaySecondsEl.value = String(appSettings.sub_agent_retry_delay_seconds ?? 5);
  if (subAgentMaxParallelToolsEl) subAgentMaxParallelToolsEl.value = String(appSettings.sub_agent_max_parallel_tools ?? appSettings.max_parallel_tools ?? 2);
  if (webCacheTtlHoursEl) webCacheTtlHoursEl.value = String(appSettings.web_cache_ttl_hours ?? 24);
  if (openrouterPromptCacheEnabledEl) openrouterPromptCacheEnabledEl.checked = Boolean(appSettings.openrouter_prompt_cache_enabled ?? true);
  if (clarificationMaxQuestionsEl) clarificationMaxQuestionsEl.value = String(appSettings.clarification_max_questions || 5);
  if (summaryModeEl) summaryModeEl.value = appSettings.chat_summary_mode || "auto";
  if (summaryDetailLevelEl) summaryDetailLevelEl.value = appSettings.chat_summary_detail_level || "balanced";
  if (summaryTriggerEl) summaryTriggerEl.value = String(appSettings.chat_summary_trigger_token_count || 80000);
  if (summarySkipFirstEl) summarySkipFirstEl.value = String(appSettings.summary_skip_first ?? 2);
  if (summarySkipLastEl) summarySkipLastEl.value = String(appSettings.summary_skip_last ?? 1);
  if (contextSelectionStrategyEl) contextSelectionStrategyEl.value = appSettings.context_selection_strategy || "classic";
  if (entropyProfileEl) entropyProfileEl.value = appSettings.entropy_profile || "balanced";
  if (entropyRagBudgetRatioEl) entropyRagBudgetRatioEl.value = String(appSettings.entropy_rag_budget_ratio ?? 35);
  if (entropyProtectCodeBlocksEl) entropyProtectCodeBlocksEl.checked = Boolean(appSettings.entropy_protect_code_blocks ?? true);
  if (entropyProtectToolResultsEl) entropyProtectToolResultsEl.checked = Boolean(appSettings.entropy_protect_tool_results ?? true);
  if (entropyReferenceBoostEl) entropyReferenceBoostEl.checked = Boolean(appSettings.entropy_reference_boost ?? true);
  if (reasoningAutoCollapseEl) reasoningAutoCollapseEl.checked = Boolean(appSettings.reasoning_auto_collapse);
  if (pruningEnabledEl) pruningEnabledEl.checked = Boolean(appSettings.pruning_enabled);
  if (pruningTokenThresholdEl) pruningTokenThresholdEl.value = String(appSettings.pruning_token_threshold || 80000);
  if (pruningBatchSizeEl) pruningBatchSizeEl.value = String(appSettings.pruning_batch_size || 10);
  if (fetchThresholdEl) fetchThresholdEl.value = String(appSettings.fetch_url_token_threshold || 3500);
  if (fetchAggressivenessEl) fetchAggressivenessEl.value = String(appSettings.fetch_url_clip_aggressiveness || 50);
  if (canvasPromptLinesEl) canvasPromptLinesEl.value = String(appSettings.canvas_prompt_max_lines || 100);
  if (canvasPromptTokensEl) canvasPromptTokensEl.value = String(appSettings.canvas_prompt_max_tokens || 2000);
  if (canvasExpandLinesEl) canvasExpandLinesEl.value = String(appSettings.canvas_expand_max_lines || 1600);
  if (canvasScrollLinesEl) canvasScrollLinesEl.value = String(appSettings.canvas_scroll_window_lines || 200);
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
  draftCustomModels = Array.isArray(appSettings.custom_models)
    ? appSettings.custom_models.map((model) => normalizeDraftCustomModel(model))
    : [];
  draftChatModelRows = [];
  initializeOperationFallbackDraftRows(appSettings.operation_model_fallback_preferences || {});
  renderModelManagementPanels({
    operationPreferences: appSettings.operation_model_preferences || {},
  });
  setCustomModelStatus("No pending model changes", "muted");
  syncCustomModelReasoningControls();
  syncCustomModelProviderControls();
  updateRagSensitivityHint();
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
  }
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
  updateRagSourceSummary();
  syncOverviewStats();
}

function applyServerSettingsData(data) {
  appSettings.general_instructions = data.general_instructions || data.user_preferences || "";
  appSettings.ai_personality = data.ai_personality || "";
  appSettings.user_preferences = appSettings.general_instructions;
  appSettings.effective_user_preferences = data.effective_user_preferences || "";
  appSettings.scratchpad = data.scratchpad || "";
  appSettings.scratchpad_sections = data.scratchpad_sections && typeof data.scratchpad_sections === "object"
    ? data.scratchpad_sections
    : {};
  appSettings.max_steps = data.max_steps || 5;
  appSettings.max_parallel_tools = data.max_parallel_tools ?? 4;
  appSettings.sub_agent_max_steps = data.sub_agent_max_steps ?? 6;
  appSettings.sub_agent_timeout_seconds = data.sub_agent_timeout_seconds ?? 240;
  appSettings.sub_agent_retry_attempts = data.sub_agent_retry_attempts ?? 2;
  appSettings.sub_agent_retry_delay_seconds = data.sub_agent_retry_delay_seconds ?? 5;
  appSettings.sub_agent_max_parallel_tools = data.sub_agent_max_parallel_tools ?? data.max_parallel_tools ?? 2;
  appSettings.web_cache_ttl_hours = data.web_cache_ttl_hours ?? 24;
  appSettings.openrouter_prompt_cache_enabled = Boolean(data.openrouter_prompt_cache_enabled ?? true);
  appSettings.temperature = data.temperature ?? 0.7;
  appSettings.clarification_max_questions = data.clarification_max_questions || 5;
  appSettings.available_models = Array.isArray(data.available_models) ? data.available_models : [];
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
  appSettings.chat_summary_mode = data.chat_summary_mode || "auto";
  appSettings.chat_summary_detail_level = data.chat_summary_detail_level || "balanced";
  appSettings.chat_summary_trigger_token_count = data.chat_summary_trigger_token_count || 80000;
  appSettings.summary_skip_first = data.summary_skip_first ?? 2;
  appSettings.summary_skip_last = data.summary_skip_last ?? 1;
  appSettings.context_selection_strategy = data.context_selection_strategy || "classic";
  appSettings.entropy_profile = data.entropy_profile || "balanced";
  appSettings.entropy_rag_budget_ratio = data.entropy_rag_budget_ratio ?? 35;
  appSettings.entropy_protect_code_blocks = Boolean(data.entropy_protect_code_blocks ?? true);
  appSettings.entropy_protect_tool_results = Boolean(data.entropy_protect_tool_results ?? true);
  appSettings.entropy_reference_boost = Boolean(data.entropy_reference_boost ?? true);
  appSettings.reasoning_auto_collapse = Boolean(data.reasoning_auto_collapse);
  appSettings.pruning_enabled = Boolean(data.pruning_enabled);
  appSettings.pruning_token_threshold = data.pruning_token_threshold || 80000;
  appSettings.pruning_batch_size = data.pruning_batch_size || 10;
  appSettings.fetch_url_token_threshold = data.fetch_url_token_threshold || 3500;
  appSettings.fetch_url_clip_aggressiveness = data.fetch_url_clip_aggressiveness ?? 50;
  appSettings.canvas_prompt_max_lines = data.canvas_prompt_max_lines || 100;
  appSettings.canvas_prompt_max_tokens = data.canvas_prompt_max_tokens || 2000;
  appSettings.canvas_expand_max_lines = data.canvas_expand_max_lines || 1600;
  appSettings.canvas_scroll_window_lines = data.canvas_scroll_window_lines || 200;
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
    setSettingsStatus("Ready");
    setDirtyPill("All changes saved", "muted");
  } catch (error) {
    setSettingsStatus(error.message || "Failed to load settings.", "error");
    setDirtyPill("Load failed", "error");
  }
}

async function saveSettings() {
  const scratchpadSections = readScratchpadSectionsFromList();
  const generalInstructions = generalInstructionsEl?.value.trim() || "";
  const aiPersonality = aiPersonalityEl?.value.trim() || "";
  const payload = {
    user_preferences: generalInstructions,
    general_instructions: generalInstructions,
    ai_personality: aiPersonality,
    temperature: readFloatSetting(temperatureEl, 0.7, { min: 0, max: 2 }),
    max_steps: readNumericSetting(maxStepsEl, 5, { allowZero: false }),
    max_parallel_tools: readNumericSetting(maxParallelToolsEl, 4, { allowZero: false }),
    sub_agent_max_steps: readNumericSetting(subAgentMaxStepsEl, 6, { allowZero: false }),
    sub_agent_timeout_seconds: readNumericSetting(subAgentTimeoutSecondsEl, 240, { allowZero: false }),
    sub_agent_retry_attempts: readNumericSetting(subAgentRetryAttemptsEl, 2),
    sub_agent_retry_delay_seconds: readNumericSetting(subAgentRetryDelaySecondsEl, 5),
    sub_agent_max_parallel_tools: readNumericSetting(subAgentMaxParallelToolsEl, 2, { allowZero: false }),
    web_cache_ttl_hours: readNumericSetting(webCacheTtlHoursEl, 24),
    openrouter_prompt_cache_enabled: Boolean(openrouterPromptCacheEnabledEl?.checked),
    clarification_max_questions: readNumericSetting(clarificationMaxQuestionsEl, 5, { allowZero: false }),
    chat_summary_mode: summaryModeEl?.value || "auto",
    chat_summary_detail_level: summaryDetailLevelEl?.value || "balanced",
    chat_summary_trigger_token_count: readNumericSetting(summaryTriggerEl, 80000, { allowZero: false }),
    summary_skip_first: readNumericSetting(summarySkipFirstEl, 0),
    summary_skip_last: readNumericSetting(summarySkipLastEl, 1),
    context_selection_strategy: contextSelectionStrategyEl?.value || "classic",
    entropy_profile: entropyProfileEl?.value || "balanced",
    entropy_rag_budget_ratio: readNumericSetting(entropyRagBudgetRatioEl, 35),
    entropy_protect_code_blocks: Boolean(entropyProtectCodeBlocksEl?.checked),
    entropy_protect_tool_results: Boolean(entropyProtectToolResultsEl?.checked),
    entropy_reference_boost: Boolean(entropyReferenceBoostEl?.checked),
    reasoning_auto_collapse: Boolean(reasoningAutoCollapseEl?.checked),
    pruning_enabled: Boolean(pruningEnabledEl?.checked),
    pruning_token_threshold: readNumericSetting(pruningTokenThresholdEl, 80000, { allowZero: false }),
    pruning_batch_size: readNumericSetting(pruningBatchSizeEl, 10, { allowZero: false }),
    fetch_url_token_threshold: readNumericSetting(fetchThresholdEl, 3500, { allowZero: false }),
    fetch_url_clip_aggressiveness: readNumericSetting(fetchAggressivenessEl, 50),
    canvas_prompt_max_lines: readNumericSetting(canvasPromptLinesEl, 100, { allowZero: false }),
    canvas_prompt_max_tokens: readNumericSetting(canvasPromptTokensEl, 2000, { allowZero: false }),
    canvas_expand_max_lines: readNumericSetting(canvasExpandLinesEl, 1600, { allowZero: false }),
    canvas_scroll_window_lines: readNumericSetting(canvasScrollLinesEl, 200, { allowZero: false }),
    custom_models: draftCustomModels.map((model) => ({ ...model })),
    visible_model_order: getDraftVisibleModelOrder(),
    operation_model_preferences: getOperationModelPreferencesDraft(),
    operation_model_fallback_preferences: getOperationModelFallbackPreferencesDraft(),
    image_processing_method: imageProcessingMethodEl?.value || "auto",
    active_tools: getSelectedTools(),
    sub_agent_allowed_tool_names: getSelectedSubAgentTools(),
    proxy_enabled_operations: getSelectedProxyOperations(),
    rag_auto_inject: featureFlags.rag_enabled ? getSelectedRagAutoInjectSourceTypes().length > 0 : false,
    rag_sensitivity: ragSensitivityEl?.value || "normal",
    rag_context_size: ragContextSizeEl?.value || "medium",
    rag_source_types: featureFlags.rag_enabled ? getSelectedRagSourceTypes() : [],
    rag_auto_inject_source_types: featureFlags.rag_enabled ? getSelectedRagAutoInjectSourceTypes() : [],
    tool_memory_auto_inject: false,
    scratchpad: (scratchpadSections[DEFAULT_SCRATCHPAD_SECTION_ID] || []).join("\n"),
    scratchpad_sections: DEFAULT_SCRATCHPAD_SECTION_ORDER.reduce((acc, sectionId) => {
      acc[sectionId] = (scratchpadSections[sectionId] || []).join("\n");
      return acc;
    }, {}),
  };

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

    applyServerSettingsData(data);

    applySettingsToForm();
    applyFeatureAvailability();
    clearDirtyState();
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
  generalInstructionsEl?.addEventListener("input", () => {
    autoResize(generalInstructionsEl);
    markDirty();
  });
  aiPersonalityEl?.addEventListener("input", () => {
    autoResize(aiPersonalityEl);
    markDirty();
  });
  maxStepsEl?.addEventListener("input", markDirty);
  maxParallelToolsEl?.addEventListener("input", markDirty);
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
  contextSelectionStrategyEl?.addEventListener("change", markDirty);
  entropyProfileEl?.addEventListener("change", markDirty);
  entropyRagBudgetRatioEl?.addEventListener("input", markDirty);
  entropyProtectCodeBlocksEl?.addEventListener("change", markDirty);
  entropyProtectToolResultsEl?.addEventListener("change", markDirty);
  entropyReferenceBoostEl?.addEventListener("change", markDirty);
  pruningEnabledEl?.addEventListener("change", markDirty);
  pruningTokenThresholdEl?.addEventListener("input", markDirty);
  pruningBatchSizeEl?.addEventListener("input", markDirty);
  fetchThresholdEl?.addEventListener("input", markDirty);
  fetchAggressivenessEl?.addEventListener("input", markDirty);
  canvasPromptLinesEl?.addEventListener("input", markDirty);
  canvasPromptTokensEl?.addEventListener("input", markDirty);
  canvasExpandLinesEl?.addEventListener("input", markDirty);
  canvasScrollLinesEl?.addEventListener("input", markDirty);
  summaryModelPreferenceEl?.addEventListener("change", markDirty);
  fetchSummarizeModelPreferenceEl?.addEventListener("change", markDirty);
  pruneModelPreferenceEl?.addEventListener("change", markDirty);
  fixTextModelPreferenceEl?.addEventListener("change", markDirty);
  titleModelPreferenceEl?.addEventListener("change", markDirty);
  uploadMetadataModelPreferenceEl?.addEventListener("change", markDirty);
  subAgentModelPreferenceEl?.addEventListener("change", markDirty);
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
addCustomModelBtn?.addEventListener("click", addCustomModelFromInputs);
customModelReasoningModeEl?.addEventListener("change", syncCustomModelReasoningControls);
customModelRoutingModeEl?.addEventListener("change", syncCustomModelProviderControls);
summaryModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("summarize"));
fetchSummarizeModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("fetch_summarize"));
pruneModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("prune"));
fixTextModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("fix_text"));
titleModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("generate_title"));
uploadMetadataModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("upload_metadata"));
subAgentModelFallbackAddBtn?.addEventListener("click", () => addOperationFallbackRow("sub_agent"));
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
    void saveSettings();
  });
});

window.addEventListener("beforeunload", (event) => {
  if (!hasUnsavedChanges) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
});

window.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    void saveSettings();
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
