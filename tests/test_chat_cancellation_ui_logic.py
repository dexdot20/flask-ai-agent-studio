from __future__ import annotations

import pathlib
import shutil
import subprocess
import textwrap

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_JS_PATH = REPO_ROOT / "static" / "app.js"
START_MARKER = "async function requestActiveChatCancellation()"
END_MARKER = 'cancelBtn.addEventListener("click", () => {'


def _load_app_js_source() -> str:
    return APP_JS_PATH.read_text(encoding="utf-8")


def _load_cancellation_helper_source() -> str:
    source = _load_app_js_source()
    start = source.find(START_MARKER)
    end = source.find(END_MARKER, start)
    assert start != -1 and end != -1, "requestActiveChatCancellation was not found in static/app.js"
    return source[start:end]


def _run_node_assertions(script_body: str) -> None:
    node_path = shutil.which("node")
    if not node_path:
        pytest.skip("node is not installed")

    helper_source = _load_cancellation_helper_source()
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
            "Node cancellation assertions failed.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def test_request_active_chat_cancellation_source_uses_graceful_cancel_before_abort() -> None:
    helper_source = _load_cancellation_helper_source()

    assert "await fetch(`/api/chat-runs/${encodeURIComponent(runId)}/cancel`" in helper_source
    assert "activeChatCancellationFallbackTimer = window.setTimeout(" in helper_source
    assert "if (!response.ok && activeAbortController)" in helper_source
    assert "} else if (activeAbortController) {" in helper_source


def test_request_active_chat_cancellation_source_clears_fallback_timer_on_failure() -> None:
    helper_source = _load_cancellation_helper_source()

    assert helper_source.count("window.clearTimeout(activeChatCancellationFallbackTimer);") >= 2
    assert "activeChatCancellationFallbackTimer = null;" in helper_source


def test_request_active_chat_cancellation_waits_for_server_cancel_before_abort() -> None:
    _run_node_assertions(
        """
        let activeUserCancelRequested = false;
        let activeChatRunId = 'run-123';
        let activeChatCancellationFallbackTimer = null;
        let fetchCalls = [];
        let clearedBubble = 0;
        let scrolled = 0;
        let timeoutCallback = null;
        let timeoutDelay = null;
        let clearedTimeoutId = null;
        let abortCount = 0;
        const activeAbortController = {{
          abort() {{
            abortCount += 1;
          }},
        }};
        const window = {{
          setTimeout(callback, delay) {{
            timeoutCallback = callback;
            timeoutDelay = delay;
            return 77;
          }},
          clearTimeout(timerId) {{
            clearedTimeoutId = timerId;
          }},
        }};
        const fetch = async (url, options) => {{
          fetchCalls.push({{ url, options }});
          return {{ ok: true }};
        }};
        const clearEmptyAssistantStreamingBubble = () => {{
          clearedBubble += 1;
        }};
        const scrollToBottom = () => {{
          scrolled += 1;
        }};

        globalThis.window = window;
        globalThis.fetch = fetch;
        globalThis.clearEmptyAssistantStreamingBubble = clearEmptyAssistantStreamingBubble;
        globalThis.scrollToBottom = scrollToBottom;
        globalThis.activeUserCancelRequested = activeUserCancelRequested;
        globalThis.activeChatRunId = activeChatRunId;
        globalThis.activeChatCancellationFallbackTimer = activeChatCancellationFallbackTimer;
        globalThis.activeAbortController = activeAbortController;

        await requestActiveChatCancellation();

        assert(globalThis.activeUserCancelRequested === true, 'Cancellation should be marked as user-requested');
        assert(fetchCalls.length === 1, `Expected one cancel request, received ${fetchCalls.length}`);
        assert(fetchCalls[0].url === '/api/chat-runs/run-123/cancel', `Unexpected cancel URL: ${fetchCalls[0].url}`);
        assert(fetchCalls[0].options && fetchCalls[0].options.method === 'POST', 'Cancel request should use POST');
        assert(fetchCalls[0].options && fetchCalls[0].options.keepalive === true, 'Cancel request should preserve keepalive');
        assert(timeoutDelay === 4000, `Expected 4000ms fallback timeout, received ${timeoutDelay}`);
        assert(abortCount === 0, 'AbortController should not fire immediately when the cancel request succeeds');
        assert(clearedBubble === 1, 'Streaming bubble should be cleaned up once');
        assert(scrolled === 1, 'Conversation should scroll after cancellation');

        timeoutCallback();
        assert(abortCount === 1, 'Fallback timeout should still abort the request if the stream never settles');
        """
    )


def test_request_active_chat_cancellation_aborts_immediately_when_cancel_request_fails() -> None:
    _run_node_assertions(
        """
        let activeUserCancelRequested = false;
        let activeChatRunId = 'run-456';
        let activeChatCancellationFallbackTimer = null;
        let abortCount = 0;
        let clearTimeoutCalls = 0;
        const activeAbortController = {{
          abort() {{
            abortCount += 1;
          }},
        }};
        const window = {{
          setTimeout() {{
            return 91;
          }},
          clearTimeout() {{
            clearTimeoutCalls += 1;
          }},
        }};
        const fetch = async () => {{
          throw new Error('network');
        }};
        const clearEmptyAssistantStreamingBubble = () => {{}};
        const scrollToBottom = () => {{}};

        globalThis.window = window;
        globalThis.fetch = fetch;
        globalThis.clearEmptyAssistantStreamingBubble = clearEmptyAssistantStreamingBubble;
        globalThis.scrollToBottom = scrollToBottom;
        globalThis.activeUserCancelRequested = activeUserCancelRequested;
        globalThis.activeChatRunId = activeChatRunId;
        globalThis.activeChatCancellationFallbackTimer = activeChatCancellationFallbackTimer;
        globalThis.activeAbortController = activeAbortController;

        await requestActiveChatCancellation();

        assert(globalThis.activeUserCancelRequested === true, 'Cancellation should still be marked as requested');
        assert(abortCount === 1, 'AbortController should fire immediately when the cancel request fails');
        assert(clearTimeoutCalls === 1, `Expected the fallback timer to be cleared once, received ${clearTimeoutCalls}`);
        """
    )