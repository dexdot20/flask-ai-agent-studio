from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import textwrap

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_JS_PATH = REPO_ROOT / "static" / "app.js"
AGENT_PY_PATH = REPO_ROOT / "agent.py"
CANVAS_DIFF_START_MARKER = "const CANVAS_DIFF_CONTEXT_LINE_COUNT"
CANVAS_DIFF_END_MARKER = "function renderCanvasDiffPreview"
STREAMING_CANVAS_PREVIEW_START_MARKER = "const STREAMING_CANVAS_MARKDOWN_PLAIN_TEXT_CHAR_LIMIT"
STREAMING_CANVAS_PREVIEW_END_MARKER = "function renderCanvasDocumentBody"


def _load_canvas_diff_helper_source() -> str:
    source = APP_JS_PATH.read_text(encoding="utf-8")
    start = source.find(CANVAS_DIFF_START_MARKER)
    end = source.find(CANVAS_DIFF_END_MARKER, start)
    assert start != -1 and end != -1, "Canvas diff helpers were not found in static/app.js"
    return source[start:end]


def _load_streaming_canvas_preview_source() -> str:
    source = APP_JS_PATH.read_text(encoding="utf-8")
    start = source.find(STREAMING_CANVAS_PREVIEW_START_MARKER)
    end = source.find(STREAMING_CANVAS_PREVIEW_END_MARKER, start)
    assert start != -1 and end != -1, "Streaming canvas preview helpers were not found in static/app.js"
    return source[start:end]


def _load_app_js_source() -> str:
    return APP_JS_PATH.read_text(encoding="utf-8")


def _run_canvas_diff_assertions(script_body: str) -> None:
    node_path = shutil.which("node")
    if not node_path:
        pytest.skip("node is not installed")

    helper_source = _load_canvas_diff_helper_source()
    node_script = textwrap.dedent(
        f"""
        {helper_source}

        const assert = (condition, message) => {{
          if (!condition) {{
            throw new Error(message);
          }}
        }};

        {script_body}
        """
    )
    result = subprocess.run(
        [node_path, "-e", node_script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Node canvas diff assertions failed.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def _run_streaming_canvas_preview_assertions(script_body: str) -> None:
    node_path = shutil.which("node")
    if not node_path:
        pytest.skip("node is not installed")

    helper_source = _load_streaming_canvas_preview_source()
    node_script = textwrap.dedent(
        f"""
        const escHtml = (value) => String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;");
        const renderStreamingMarkdown = (text) => `<div class="rendered-stream">${{escHtml(String(text || ""))}}</div>`;

        {helper_source}

        const assert = (condition, message) => {{
            if (!condition) {{
                throw new Error(message);
            }}
        }};

        {script_body}
        """
    )
    result = subprocess.run(
        [node_path, "-e", node_script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Node streaming canvas preview assertions failed.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def test_build_canvas_diff_preserves_separate_hunks() -> None:
    _run_canvas_diff_assertions(
        """
        const diff = buildCanvasDiff(
          [
            "line 1",
            "old alpha",
            "line 3",
            "line 4",
            "line 5",
            "line 6",
            "line 7",
            "old beta",
            "line 9",
          ].join("\\n"),
          [
            "line 1",
            "new alpha",
            "line 3",
            "line 4",
            "line 5",
            "line 6",
            "line 7",
            "new beta",
            "line 9",
          ].join("\\n"),
        );

        assert(diff !== null, "Expected a diff payload");
        assert(diff.hunkCount === 2, `Expected 2 hunks, received ${diff && diff.hunkCount}`);
        assert(diff.hunks.length === 2, `Expected 2 visible hunks, received ${diff && diff.hunks && diff.hunks.length}`);
        assert(diff.addedCount === 2, `Expected 2 added lines, received ${diff && diff.addedCount}`);
        assert(diff.removedCount === 2, `Expected 2 removed lines, received ${diff && diff.removedCount}`);
        assert(diff.hunks.every((hunk) => hunk.lines.some((line) => line.kind !== "context")), "Each hunk should include at least one changed line");
        """
    )


def test_build_canvas_diff_tracks_context_and_line_numbers() -> None:
    _run_canvas_diff_assertions(
        """
        const diff = buildCanvasDiff(
          ["one", "two", "three", "four"].join("\\n"),
          ["one", "TWO", "three", "four", "five"].join("\\n"),
        );

        assert(diff !== null, "Expected a diff payload");
        const firstHunk = diff.hunks[0];
        assert(firstHunk.lines[0].kind === "context", "Expected leading context to be preserved");
        assert(firstHunk.lines[0].previousLineNumber === 1, `Expected old line number 1, received ${firstHunk.lines[0].previousLineNumber}`);
        assert(firstHunk.lines[0].nextLineNumber === 1, `Expected new line number 1, received ${firstHunk.lines[0].nextLineNumber}`);
        assert(firstHunk.lines.some((line) => line.kind === "removed" && line.previousLineNumber === 2 && line.nextLineNumber === null && line.text === "two"), "Removed line metadata is incorrect");
        assert(firstHunk.lines.some((line) => line.kind === "added" && line.previousLineNumber === null && line.nextLineNumber === 2 && line.text === "TWO"), "Changed line metadata is incorrect");
        assert(firstHunk.lines.some((line) => line.kind === "added" && line.previousLineNumber === null && line.nextLineNumber === 5 && line.text === "five"), "Trailing inserted line metadata is incorrect");
        """
    )


def test_streaming_canvas_preview_keeps_markdown_rendering_for_small_drafts() -> None:
    _run_streaming_canvas_preview_assertions(
        """
        const document = {
          format: "markdown",
          content: "# Draft\\n\\nShort preview",
          line_count: 3,
        };

        assert(getStreamingCanvasPreviewRenderMode(document) === "markdown", "Small markdown drafts should keep rendered preview mode");
        const html = renderStreamingCanvasPreviewBody(document);
        assert(html.includes("rendered-stream"), "Small markdown drafts should still use rendered markdown previews");
        assert(!html.includes("canvas-stream-markdown-block"), "Small markdown drafts should not use plaintext fallback");
        """
    )


def test_streaming_canvas_preview_uses_plaintext_fallback_for_large_markdown() -> None:
    _run_streaming_canvas_preview_assertions(
        """
        // Limit is now 800 lines / 30000 chars — use values that clearly exceed both.
        const longText = Array.from({ length: 900 }, (_, index) => `line ${index + 1}`).join("\\n");
        const document = {
          format: "markdown",
          content: longText,
          line_count: 900,
        };

        assert(getStreamingCanvasPreviewRenderMode(document) === "markdown-plain", "Large markdown drafts should switch to plaintext fallback mode");
        const html = renderStreamingCanvasPreviewBody(document);
        assert(html.includes("canvas-stream-markdown-block"), "Large markdown drafts should render with the plaintext preview shell");
        assert(!html.includes("rendered-stream"), "Large markdown drafts should skip expensive live markdown rendering");

        // Documents well below the new limits must still render with proper markdown.
        const shortText = Array.from({ length: 120 }, (_, index) => `line ${index + 1}`).join("\\n");
        const shortDoc = { format: "markdown", content: shortText, line_count: 120 };
        assert(getStreamingCanvasPreviewRenderMode(shortDoc) === "markdown", "Typical-length markdown drafts (120 lines) must keep full markdown rendering");
        """
    )


def test_streaming_canvas_preview_infers_heading_title_for_generic_drafts() -> None:
    source = _load_app_js_source()
    infer_match = re.search(
        r"function inferStreamingCanvasPreviewTitleFromContent\(content\) \{(?P<body>.*?)\n\}",
        source,
        re.S,
    )
    assert infer_match, "inferStreamingCanvasPreviewTitleFromContent was not found in static/app.js"
    infer_body = infer_match.group("body")
    assert 'match(/^#\\s+(.+?)\\s*$/m)' in infer_body

    normalize_match = re.search(
        r"function normalizeStreamingCanvasPreviewDocument\(document\) \{(?P<body>.*?)\n\}",
        source,
        re.S,
    )
    assert normalize_match, "normalizeStreamingCanvasPreviewDocument was not found in static/app.js"
    normalize_body = normalize_match.group("body")
    assert "document?.isStreamingPreview" in normalize_body
    assert "isGenericStreamingCanvasPreviewTitle(normalized.title)" in normalize_body
    assert "inferStreamingCanvasPreviewTitleFromContent(normalized.content)" in normalize_body


def test_expand_canvas_document_is_not_treated_as_streaming_canvas_preview() -> None:
    source = AGENT_PY_PATH.read_text(encoding="utf-8")
    match = re.search(r"CANVAS_STREAM_OPEN_TOOL_NAMES = \{(?P<body>.*?)\n\}", source, re.S)
    assert match, "CANVAS_STREAM_OPEN_TOOL_NAMES was not found in agent.py"
    body = match.group("body")
    assert '"expand_canvas_document"' not in body


def test_update_streaming_canvas_preview_element_uses_text_content_fast_paths() -> None:
    source = _load_app_js_source()
    update_match = re.search(r"function updateStreamingCanvasPreviewElement\(containerEl, document\) \{(?P<body>.*?)\n\}", source, re.S)
    assert update_match, "updateStreamingCanvasPreviewElement function was not found in static/app.js"
    update_body = update_match.group("body")

    assert 'previewBody.setAttribute("data-canvas-streaming-preview-mode", renderMode);' in update_body
    assert "codeEl.textContent = previewText;" in update_body
    assert "previewTextEl.textContent = previewText;" in update_body


def test_canvas_sync_no_longer_suppresses_diff_after_live_preview() -> None:
    source = _load_app_js_source()
    canvas_sync_match = re.search(r"else if \(event\.type === \"canvas_sync\"\) \{(?P<body>.*?)\n\s*\} else if \(event\.type === \"history_sync\"\)", source, re.S)
    assert canvas_sync_match, "canvas_sync block was not found in static/app.js"
    canvas_sync_body = canvas_sync_match.group("body")

    assert "!hadStreamingPreviewForDoc &&" not in canvas_sync_body
    assert 'source: hadStreamingPreviewForDoc ? "live-preview" : "direct-sync"' in canvas_sync_body
    assert "const nextDiff = previousVersionOfNextDocument.content !== nextActiveCandidate.content" in canvas_sync_body
    assert "const shouldPrioritizeCommittedCanvasRender = hadStreamingPreviewForDoc || isCanvasOpen();" in canvas_sync_body
    assert "requestCanvasPanelRender({ deferForStreaming: !shouldPrioritizeCommittedCanvasRender });" in canvas_sync_body


def test_render_canvas_diff_preview_is_not_hidden_by_edit_mode() -> None:
    source = _load_app_js_source()
    render_match = re.search(r"function renderCanvasDiffPreview\(activeDocument\) \{(?P<body>.*?)\n\}", source, re.S)
    assert render_match, "renderCanvasDiffPreview function was not found in static/app.js"
    render_body = render_match.group("body")

    hide_guard_match = re.search(r"if \((?P<guard>.*?)\) \{\n\s*canvasDiffEl\.hidden = true;", render_body, re.S)
    assert hide_guard_match, "renderCanvasDiffPreview hide guard was not found"
    assert "isCanvasEditing" not in hide_guard_match.group("guard")
    assert "canvas-diff__hunk-header" in render_body
    assert "Saved after live preview" in render_body


def test_render_canvas_diff_preview_shows_scroll_hint_for_long_diffs() -> None:
    source = _load_app_js_source()
    render_match = re.search(r"function renderCanvasDiffPreview\(activeDocument\) \{(?P<body>.*?)\n\}", source, re.S)
    assert render_match, "renderCanvasDiffPreview function was not found in static/app.js"
    render_body = render_match.group("body")

    # The scroll hint must live INSIDE the diff body (as the second-to-last flex item)
    # so that hovering over it and scrolling targets the correct scroll container.
    assert 'canvas-diff__scroll-hint' in render_body, "scroll hint element must be present inside the diff body"
    assert 'canvas-diff__scroll-sentinel' in render_body, "scroll sentinel element must be present after the scroll hint"
    assert "↓ scroll to see more" in render_body, "scroll hint must have descriptive text"

    # Display must be toggled by IntersectionObserver on the sentinel, not rAF.
    assert "IntersectionObserver" in render_body, "IntersectionObserver must be used to show/hide the scroll hint"
    assert "root: diffBodyEl" in render_body, "IntersectionObserver root must target the diff body scroll container"

    # Old rAF-based scroll detection must be gone.
    assert "syncScrollHint" not in render_body, "old rAF-based syncScrollHint approach must be removed"
    assert "diffBodyEl.scrollHeight" not in render_body, "old scrollHeight measurement must be removed"


def test_canvas_sync_does_not_clear_pending_diff_on_repeat_sync() -> None:
    source = _load_app_js_source()
    canvas_sync_match = re.search(r"else if \(event\.type === \"canvas_sync\"\) \{(?P<body>.*?)\n\s*\} else if \(event\.type === \"history_sync\"\)", source, re.S)
    assert canvas_sync_match, "canvas_sync block was not found in static/app.js"
    canvas_sync_body = canvas_sync_match.group("body")

    # The old `else if (pendingCanvasDiff?.documentId === nextActiveCandidate.id) { pendingCanvasDiff = null; }`
    # branch must be absent.  It caused the diff to disappear when a second canvas_sync event
    # (from the final agent tool_capture after an early commit emit) arrived with identical
    # content on both sides (nextDiff === null) and cleared the still-valid pending diff.
    assert "} else if (pendingCanvasDiff?.documentId === nextActiveCandidate.id)" not in canvas_sync_body, (
        "Auto-clear of pendingCanvasDiff on no-diff canvas_sync must be removed; "
        "it caused the diff to disappear when a second redundant canvas_sync arrived."
    )


def _load_canvas_doc_list_signature_source() -> str:
    source = APP_JS_PATH.read_text(encoding="utf-8")
    start = source.find("function buildCanvasDocListSignature(")
    assert start != -1, "buildCanvasDocListSignature was not found in static/app.js"
    end = source.find("function renderCanvasPreviewFrame()", start)
    assert end != -1, "renderCanvasPreviewFrame was not found after buildCanvasDocListSignature"
    return source[start:end]


def _run_canvas_doc_list_signature_assertions(script_body: str) -> None:
    node_path = shutil.which("node")
    if not node_path:
        pytest.skip("node is not installed")

    helper_source = _load_canvas_doc_list_signature_source()
    node_script = textwrap.dedent(
        f"""
        {helper_source}

        const assert = (condition, message) => {{
          if (!condition) throw new Error(message);
        }};

        {script_body}
        """
    )
    result = subprocess.run(
        [node_path, "-e", node_script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Node buildCanvasDocListSignature assertions failed.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def test_build_canvas_doc_list_signature_distinguishes_stored_vs_preview() -> None:
    _run_canvas_doc_list_signature_assertions(
        """
        const stored = [{ id: "doc-1", isStreamingPreview: false }];
        const preview = [{ id: "doc-1", isStreamingPreview: true }];

        assert(
          buildCanvasDocListSignature(stored) !== buildCanvasDocListSignature(preview),
          "Stored and preview documents with the same ID must produce different doc-list signatures"
        );
        """
    )


def test_build_canvas_doc_list_signature_ignores_title_changes() -> None:
    _run_canvas_doc_list_signature_assertions(
        """
        const docA = [{ id: "doc-1", isStreamingPreview: true, title: "Part" }];
        const docB = [{ id: "doc-1", isStreamingPreview: true, title: "Full Title" }];

        assert(
          buildCanvasDocListSignature(docA) === buildCanvasDocListSignature(docB),
          "Title changes on a streaming preview must not change the doc-list signature"
        );
        """
    )


def test_build_canvas_doc_list_signature_detects_document_added() -> None:
    _run_canvas_doc_list_signature_assertions(
        """
        const before = [{ id: "doc-1", isStreamingPreview: true }];
        const after = [
          { id: "doc-1", isStreamingPreview: true },
          { id: "doc-2", isStreamingPreview: false },
        ];

        assert(
          buildCanvasDocListSignature(before) !== buildCanvasDocListSignature(after),
          "Adding a document must change the doc-list signature"
        );
        """
    )


def test_ensure_streaming_canvas_preview_skips_rebuild_on_existing_preview() -> None:
    """Verify the lazy rebuild guard is present in the ensureStreamingCanvasPreview source."""
    source = _load_app_js_source()
    func_match = re.search(
        r"function ensureStreamingCanvasPreview\(toolName, previewKey.*?\) \{(?P<body>.*?)\n\}",
        source,
        re.S,
    )
    assert func_match, "ensureStreamingCanvasPreview was not found in static/app.js"
    body = func_match.group("body")

    assert "const needsRebuild = !existing || existing.tool !== normalizedToolName;" in body, (
        "ensureStreamingCanvasPreview must use a needsRebuild guard before calling "
        "buildStreamingCanvasPreviewDocument"
    )
    assert "if (needsRebuild) {" in body, (
        "buildStreamingCanvasPreviewDocument must be inside the needsRebuild branch"
    )


def test_render_canvas_preview_frame_uses_doc_list_signature_for_fast_path() -> None:
    """Verify renderCanvasPreviewFrame distinguishes structural from metadata-only changes."""
    source = _load_app_js_source()
    func_match = re.search(
        r"function renderCanvasPreviewFrame\(\) \{(?P<body>.*?)\n\}",
        source,
        re.S,
    )
    assert func_match, "renderCanvasPreviewFrame was not found in static/app.js"
    body = func_match.group("body")

    assert "buildCanvasDocListSignature(renderState.documents)" in body, (
        "renderCanvasPreviewFrame must call buildCanvasDocListSignature to detect real list changes"
    )
    assert "lastCanvasDocListSignature" in body, (
        "renderCanvasPreviewFrame must compare against lastCanvasDocListSignature"
    )
    assert "lastCanvasStructureSignature = renderState.structureSignature;" in body, (
        "renderCanvasPreviewFrame must silently advance lastCanvasStructureSignature "
        "on metadata-only changes to stay in sync"
    )


def test_schedule_canvas_preview_render_defers_when_answer_frame_is_pending() -> None:
    source = _load_app_js_source()
    func_match = re.search(
        r"function scheduleCanvasPreviewRender\(options = \{\}\) \{(?P<body>.*?)\n\}",
        source,
        re.S,
    )
    assert func_match, "scheduleCanvasPreviewRender was not found in static/app.js"
    body = func_match.group("body")

    assert "shouldDeferCanvasRenderForStreaming" in body, (
        "scheduleCanvasPreviewRender must consult the shared deferred-render helper before drawing Canvas previews"
    )
    assert "deferredCanvasPreviewRender = true;" in body, (
        "scheduleCanvasPreviewRender must mark preview updates as deferred when chat rendering has priority"
    )
    assert "scheduleDeferredCanvasRenderFlush" in body, (
        "Deferred preview updates must be rescheduled after the answer frame finishes"
    )
    assert "CANVAS_STREAMING_PREVIEW_THROTTLE_MS" in body, (
        "Streaming canvas preview updates should be throttled while answer rendering is active"
    )


def test_open_canvas_uses_deferred_panel_render_during_streaming() -> None:
    source = _load_app_js_source()
    func_match = re.search(
        r"function openCanvas\(triggerEl = null, options = \{\}\) \{(?P<body>.*?)\n\}",
        source,
        re.S,
    )
    assert func_match, "openCanvas was not found in static/app.js"
    body = func_match.group("body")

    assert "requestCanvasPanelRender" in body, (
        "openCanvas must route panel rendering through the deferred render coordinator"
    )
    assert "options.deferPanelRender !== false" in body, (
        "openCanvas should keep deferred panel rendering enabled by default during streaming"
    )


def test_send_message_validates_create_conversation_response_before_state_update() -> None:
    source = _load_app_js_source()
    send_match = re.search(r"async function sendMessage\(options = \{\}\) \{(?P<body>.*?)\n\}", source, re.S)
    assert send_match, "sendMessage was not found in static/app.js"
    body = send_match.group("body")

    create_conv_match = re.search(r"if \(!currentConvId\) \{(?P<section>.*?)\n\s*\}\n\n\s*let userMetadata", body, re.S)
    assert create_conv_match, "create-conversation bootstrap block was not found in sendMessage"
    section = create_conv_match.group("section")

    assert "if (!response.ok)" in section, "create-conversation bootstrap must guard non-OK responses"
    assert "Number.isInteger(Number(conversation?.id))" in section, "create-conversation bootstrap must validate returned conversation id"
    assert "throw new Error" in section, "create-conversation bootstrap must throw on invalid bootstrap response"


def test_is_canvas_streaming_preview_tool_accepts_event_payload_markers() -> None:
    source = _load_app_js_source()
    func_match = re.search(r"function isCanvasStreamingPreviewTool\(toolName, eventPayload = null\) \{(?P<body>.*?)\n\}", source, re.S)
    assert func_match, "isCanvasStreamingPreviewTool(toolName, eventPayload) was not found in static/app.js"
    body = func_match.group("body")

    assert "eventPayload.preview_key" in body, "preview_key marker should enable streaming preview detection"
    assert "eventPayload.snapshot" in body, "snapshot marker should enable streaming preview detection"
    assert "eventPayload.delta" in body, "delta marker should enable streaming preview detection"
    assert "replace_content" in body, "replace_content marker should enable streaming preview detection"