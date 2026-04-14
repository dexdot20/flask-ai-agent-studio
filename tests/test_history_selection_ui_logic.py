from __future__ import annotations

import pathlib
import shutil
import subprocess
import textwrap

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_JS_PATH = REPO_ROOT / "static" / "app.js"
STYLE_CSS_PATH = REPO_ROOT / "static" / "style.css"
SELECTION_HELPERS_START_MARKER = "function getHistoryMessageSortValue(message)"
SELECTION_HELPERS_END_MARKER = "function isSummaryPanelOpen()"
SUMMARY_REQUEST_START_MARKER = "function buildSummaryRequestBody()"
SUMMARY_REQUEST_END_MARKER = "function resetSummaryPreview"
SELECTION_TOGGLE_START_MARKER = "function createHistorySelectionToggle(message, mode)"
SELECTION_TOGGLE_END_MARKER = "function createMessageGroup(role, text, metadata = null, options = {})"
CREATE_MESSAGE_GROUP_START_MARKER = "function createMessageGroup(role, text, metadata = null, options = {})"
CREATE_MESSAGE_GROUP_END_MARKER = "function appendGroup(role, text, metadata = null, options = {})"


def _load_app_js_source() -> str:
    return APP_JS_PATH.read_text(encoding="utf-8")


def _load_style_css_source() -> str:
  return STYLE_CSS_PATH.read_text(encoding="utf-8")


def _load_selection_helper_source() -> str:
    source = _load_app_js_source()
    start = source.find(SELECTION_HELPERS_START_MARKER)
    end = source.find(SELECTION_HELPERS_END_MARKER, start)
    assert start != -1 and end != -1, "History selection helpers were not found in static/app.js"
    return source[start:end]


def _load_summary_request_body_source() -> str:
    source = _load_app_js_source()
    start = source.find(SUMMARY_REQUEST_START_MARKER)
    end = source.find(SUMMARY_REQUEST_END_MARKER, start)
    assert start != -1 and end != -1, "buildSummaryRequestBody was not found in static/app.js"
    return source[start:end]


def _load_source_between(start_marker: str, end_marker: str) -> str:
    source = _load_app_js_source()
    start = source.find(start_marker)
    end = source.find(end_marker, start)
    assert start != -1 and end != -1, f"Could not find source between markers: {start_marker} -> {end_marker}"
    return source[start:end]


def _run_node_assertions(script_body: str) -> None:
    node_path = shutil.which("node")
    if not node_path:
        pytest.skip("node is not installed")

    result = subprocess.run(
        [node_path, "-e", script_body],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Node assertions failed.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def test_selection_helpers_filter_ineligible_ids_and_keep_history_order() -> None:
    helper_source = _load_selection_helper_source()
    _run_node_assertions(
        textwrap.dedent(
            f"""
            let history = [];
            let messageSelectionMode = null;
            let selectedSummaryMessageIds = new Set();
            let selectedPruneMessageIds = new Set();
            let pruneScores = [];
            let pruneRecommendedBatchSize = 5;
            let currentConvId = 9;

            const createClassList = () => {{
              const values = new Set();
              return {{
                toggle(name, force) {{
                  const nextValue = force === undefined ? !values.has(name) : Boolean(force);
                  if (nextValue) {{
                    values.add(name);
                  }} else {{
                    values.delete(name);
                  }}
                }},
                contains(name) {{
                  return values.has(name);
                }},
              }};
            }};

            const chatAreaEl = {{ classList: createClassList(), dataset: {{}} }};
            const messagesEl = {{ classList: createClassList() }};
            const historySelectionBar = {{ hidden: false }};
            const historySelectionLabel = {{ textContent: "" }};
            const historySelectionDetail = {{ textContent: "" }};
            const historySelectionClear = {{ disabled: false }};
            const historySelectionCancel = {{ textContent: "" }};
            const fmt = (value) => String(value);
            const updateSummarySelectionUi = () => {{}};
            const updatePrunePanelUi = () => {{}};
            const renderConversationHistory = () => {{}};

            const isPrunableHistoryMessage = (message) => Boolean(
              message &&
              (message.role === "user" || message.role === "assistant") &&
              message.summaryEligible !== false &&
              message.pruneEligible !== false
            );

            const getHistoryMessage = (messageId) =>
              history.find((entry) => Number(entry.id) === Number(messageId)) || null;

            const getSummaryEligibleMessages = (entries = history) =>
              sortHistoryMessagesByPosition((entries || []).filter((message) => isPrunableHistoryMessage(message) && message.summaryEligible !== false));

            {helper_source}

            const assert = (condition, message) => {{
              if (!condition) {{
                throw new Error(message);
              }}
            }};

            history = [
              {{ id: 8, position: 8, role: "assistant" }},
              {{ id: 2, position: 2, role: "user" }},
              {{ id: 5, position: 5, role: "assistant" }},
              {{ id: 11, position: 11, role: "assistant", summaryEligible: false }},
            ];

            replaceSelectionSet("summary", [11, 5, 2, 999, 8]);
            const selected = getSelectedMessageIds("summary");

            assert(JSON.stringify(selected) === JSON.stringify([2, 5, 8]), `Expected history order [2,5,8], received ${{JSON.stringify(selected)}}`);
            assert(!selected.includes(11), "Ineligible summary ids must be dropped");
            """
        )
    )


def test_selection_helpers_prune_stale_ids_after_history_changes() -> None:
    helper_source = _load_selection_helper_source()
    _run_node_assertions(
        textwrap.dedent(
            f"""
            let history = [];
            let messageSelectionMode = null;
            let selectedSummaryMessageIds = new Set();
            let selectedPruneMessageIds = new Set();
            let pruneScores = [];
            let pruneRecommendedBatchSize = 5;
            let currentConvId = 7;

            const createClassList = () => ({{ toggle() {{}}, contains() {{ return false; }} }});
            const chatAreaEl = {{ classList: createClassList(), dataset: {{}} }};
            const messagesEl = {{ classList: createClassList() }};
            const historySelectionBar = {{ hidden: false }};
            const historySelectionLabel = {{ textContent: "" }};
            const historySelectionDetail = {{ textContent: "" }};
            const historySelectionClear = {{ disabled: false }};
            const historySelectionCancel = {{ textContent: "" }};
            const fmt = (value) => String(value);
            const updateSummarySelectionUi = () => {{}};
            const updatePrunePanelUi = () => {{}};
            const renderConversationHistory = () => {{}};

            const isPrunableHistoryMessage = (message) => Boolean(
              message &&
              (message.role === "user" || message.role === "assistant") &&
              message.summaryEligible !== false &&
              message.pruneEligible !== false
            );

            const getHistoryMessage = (messageId) =>
              history.find((entry) => Number(entry.id) === Number(messageId)) || null;

            const getSummaryEligibleMessages = (entries = history) =>
              sortHistoryMessagesByPosition((entries || []).filter((message) => isPrunableHistoryMessage(message) && message.summaryEligible !== false));

            {helper_source}

            const assert = (condition, message) => {{
              if (!condition) {{
                throw new Error(message);
              }}
            }};

            history = [
              {{ id: 1, position: 1, role: "user" }},
              {{ id: 2, position: 2, role: "assistant" }},
              {{ id: 3, position: 3, role: "user" }},
            ];

            replaceSelectionSet("summary", [1, 2, 3]);
            replaceSelectionSet("prune", [2, 3]);

            history = [
              {{ id: 2, position: 2, role: "assistant" }},
              {{ id: 4, position: 4, role: "user" }},
            ];

            const changed = pruneStaleMessageSelections();
            const remainingSummary = Array.from(selectedSummaryMessageIds).sort((left, right) => left - right);
            const remainingPrune = Array.from(selectedPruneMessageIds).sort((left, right) => left - right);
            assert(changed === true, "Expected stale selection cleanup to report a change");
            assert(JSON.stringify(remainingSummary) === JSON.stringify([2]), "Summary selection should keep only still-eligible ids");
            assert(JSON.stringify(remainingPrune) === JSON.stringify([2]), "Prune selection should keep only still-eligible ids");
            """
        )
    )


def test_render_history_selection_bar_reflects_mode_and_count() -> None:
    helper_source = _load_selection_helper_source()
    _run_node_assertions(
        textwrap.dedent(
            f"""
            let history = [];
            let messageSelectionMode = "summary";
            let selectedSummaryMessageIds = new Set([2, 4]);
            let selectedPruneMessageIds = new Set();
            let pruneScores = [];
            let pruneRecommendedBatchSize = 5;
            let currentConvId = 11;

            const createClassList = () => {{
              const values = new Set();
              return {{
                toggle(name, force) {{
                  const nextValue = force === undefined ? !values.has(name) : Boolean(force);
                  if (nextValue) {{
                    values.add(name);
                  }} else {{
                    values.delete(name);
                  }}
                }},
                contains(name) {{
                  return values.has(name);
                }},
              }};
            }};

            const chatAreaEl = {{ classList: createClassList(), dataset: {{}} }};
            const messagesEl = {{ classList: createClassList() }};
            const historySelectionBar = {{ hidden: true }};
            const historySelectionLabel = {{ textContent: "" }};
            const historySelectionDetail = {{ textContent: "" }};
            const historySelectionClear = {{ disabled: false }};
            const historySelectionCancel = {{ textContent: "" }};
            const fmt = (value) => String(value);
            const updateSummarySelectionUi = () => {{}};
            const updatePrunePanelUi = () => {{}};
            const renderConversationHistory = () => {{}};

            const isPrunableHistoryMessage = (message) => Boolean(message && (message.role === "user" || message.role === "assistant"));
            const getHistoryMessage = (messageId) => history.find((entry) => Number(entry.id) === Number(messageId)) || null;
            const getSummaryEligibleMessages = (entries = history) => sortHistoryMessagesByPosition((entries || []).filter(isPrunableHistoryMessage));

            {helper_source}

            const assert = (condition, message) => {{
              if (!condition) {{
                throw new Error(message);
              }}
            }};

            history = [
              {{ id: 2, position: 2, role: "user" }},
              {{ id: 4, position: 4, role: "assistant" }},
            ];

            renderHistorySelectionBar();

            assert(historySelectionBar.hidden === false, "Selection bar should be visible while a mode is active");
            assert(historySelectionLabel.textContent.includes("Summary selection"), "Selection bar should mention summary mode");
            assert(historySelectionLabel.textContent.includes("2"), "Selection bar label should include the selected count");
            assert(historySelectionDetail.textContent.includes("message bubble"), "Selection bar detail should mention bubble click selection");
            assert(historySelectionCancel.textContent === "Close summary", "Selection bar close copy should follow the active mode");
            """
        )
    )


def test_build_summary_request_body_prefers_explicit_selection() -> None:
    request_source = _load_summary_request_body_source()
    _run_node_assertions(
        textwrap.dedent(
            f"""
            let summaryFocusInput = {{ value: "decisions and next steps" }};
            let summaryDetailSelect = {{ value: "detailed" }};
            let summaryAllMessagesCheckbox = {{ checked: true }};

            const getSelectedMessageIds = () => [4, 9];
            const parseSummaryMessageCount = () => 12;

            {request_source}

            const assert = (condition, message) => {{
              if (!condition) {{
                throw new Error(message);
              }}
            }};

            const payload = buildSummaryRequestBody();
            assert(JSON.stringify(payload.include_message_ids) === JSON.stringify([4, 9]), "Explicit selection should be forwarded as include_message_ids");
            assert(!("message_count" in payload), "message_count must not be sent when explicit selection exists");
            assert(!("summarize_all_messages" in payload), "summarize_all_messages must not be sent when explicit selection exists");
            assert(payload.summary_focus === "decisions and next steps", "Summary focus should be preserved");
            assert(payload.summary_detail_level === "detailed", "Summary detail should be preserved");
            """
        )
    )


def test_create_history_selection_toggle_uses_checkbox_semantics() -> None:
    body = _load_source_between(SELECTION_TOGGLE_START_MARKER, SELECTION_TOGGLE_END_MARKER)

    assert 'setAttribute("role", "checkbox")' in body
    assert 'setAttribute("aria-checked", String(isSelected))' in body


def test_create_message_group_uses_clickable_content_row_for_selection_mode() -> None:
    body = _load_source_between(CREATE_MESSAGE_GROUP_START_MARKER, CREATE_MESSAGE_GROUP_END_MARKER)

    assert 'const shouldRenderContentRow = Boolean(displayText) || Boolean(selectionToggle);' in body
    assert 'contentRow.className = "msg-content-row"' in body
    assert 'bindHistorySelectionClickTarget(contentRow, options.messageId, activeSelectionMode);' in body


def test_selection_desktop_css_keeps_summary_and_prune_overlays_click_through() -> None:
  style_source = _load_style_css_source()

  assert '@media (min-width: 901px)' in style_source
  assert '#summary-overlay,' in style_source
  assert '#prune-overlay {' in style_source
  assert 'pointer-events: none;' in style_source
  assert '.chat-area.chat-area--selection-mode {' in style_source
