from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import textwrap

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_JS_PATH = REPO_ROOT / "static" / "app.js"
CANVAS_DIFF_START_MARKER = "const CANVAS_DIFF_CONTEXT_LINE_COUNT"
CANVAS_DIFF_END_MARKER = "function renderCanvasDiffPreview"


def _load_canvas_diff_helper_source() -> str:
    source = APP_JS_PATH.read_text(encoding="utf-8")
    start = source.find(CANVAS_DIFF_START_MARKER)
    end = source.find(CANVAS_DIFF_END_MARKER, start)
    assert start != -1 and end != -1, "Canvas diff helpers were not found in static/app.js"
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


def test_canvas_sync_no_longer_suppresses_diff_after_live_preview() -> None:
    source = _load_app_js_source()
    canvas_sync_match = re.search(r"else if \(event\.type === \"canvas_sync\"\) \{(?P<body>.*?)\n\s*\} else if \(event\.type === \"history_sync\"\)", source, re.S)
    assert canvas_sync_match, "canvas_sync block was not found in static/app.js"
    canvas_sync_body = canvas_sync_match.group("body")

    assert "!hadStreamingPreviewForDoc &&" not in canvas_sync_body
    assert 'source: hadStreamingPreviewForDoc ? "live-preview" : "direct-sync"' in canvas_sync_body
    assert "const nextDiff = previousVersionOfNextDocument.content !== nextActiveCandidate.content" in canvas_sync_body


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
