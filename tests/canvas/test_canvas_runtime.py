from __future__ import annotations

import unittest

from agent import (
    _build_streaming_canvas_tool_preview,
    _collect_canvas_mutation_locators,
    _execute_tool,
    _extract_partial_json_string_value,
    _parse_tool_call_arguments,
    _should_skip_canvas_read_after_same_turn_mutation,
)
from canvas_service import (
    batch_read_canvas_documents,
    create_canvas_runtime_state,
    focus_canvas_page,
    get_canvas_viewport_payloads,
    normalize_canvas_document,
    scroll_canvas_document,
    search_canvas_document,
    set_canvas_viewport,
    validate_canvas_document,
)
from db import (
    get_app_settings,
    get_canvas_expand_max_lines,
    get_canvas_prompt_code_line_max_chars,
    get_canvas_prompt_max_chars,
    get_canvas_prompt_max_lines,
    get_canvas_prompt_max_tokens,
    get_canvas_prompt_text_line_max_chars,
    get_canvas_scroll_window_lines,
)
from messages import _build_canvas_prompt_payload, build_runtime_system_message


class TestCanvasRuntime(unittest.TestCase):
    def test_canvas_limit_getters_clamp_values(self):
        settings = get_app_settings()
        settings["canvas_prompt_max_lines"] = "50000"
        settings["canvas_prompt_max_tokens"] = "60000"
        settings["canvas_prompt_max_chars"] = "999999"
        settings["canvas_prompt_code_line_max_chars"] = "0"
        settings["canvas_prompt_text_line_max_chars"] = "5000"
        settings["canvas_expand_max_lines"] = "-1"
        settings["canvas_scroll_window_lines"] = "nope"

        self.assertEqual(get_canvas_prompt_max_lines(settings), 3000)
        self.assertEqual(get_canvas_prompt_max_tokens(settings), 50000)
        self.assertEqual(get_canvas_prompt_max_chars(settings), 200000)
        self.assertEqual(get_canvas_prompt_code_line_max_chars(settings), 40)
        self.assertEqual(get_canvas_prompt_text_line_max_chars(settings), 1000)
        self.assertEqual(get_canvas_expand_max_lines(settings), 100)
        self.assertEqual(get_canvas_scroll_window_lines(settings), 200)

    def test_build_canvas_prompt_payload_respects_max_lines(self):
        content = "\n".join(f"line {index}" for index in range(1, 51))
        document = normalize_canvas_document(
            {
                "id": "doc-1",
                "title": "Large file",
                "format": "code",
                "language": "python",
                "content": content,
            }
        )

        payload = _build_canvas_prompt_payload([document], max_lines=10)

        self.assertIsNotNone(payload)
        self.assertEqual(len(payload["visible_lines"]), 10)
        self.assertEqual(payload["visible_line_end"], 10)
        self.assertTrue(payload["is_truncated"])

        small_document = normalize_canvas_document(
            {
                "id": "doc-2",
                "title": "Small file",
                "format": "code",
                "language": "python",
                "content": "line 1\nline 2\nline 3",
            }
        )

        full_payload = _build_canvas_prompt_payload([small_document], max_lines=10)

        self.assertIsNotNone(full_payload)
        self.assertEqual(len(full_payload["visible_lines"]), 3)
        self.assertEqual(full_payload["visible_line_end"], 3)
        self.assertFalse(full_payload["is_truncated"])

    def test_build_canvas_prompt_payload_hides_ignored_active_document_content(self):
        payload = _build_canvas_prompt_payload(
            [
                {
                    "id": "canvas-1",
                    "title": "legacy.py",
                    "path": "src/legacy.py",
                    "format": "code",
                    "language": "python",
                    "role": "source",
                    "content": "SECRET_VALUE = 'hidden'\nprint(SECRET_VALUE)",
                    "ignored": True,
                    "ignored_reason": "Superseded by src/app.py",
                    "symbols": ["legacy_main"],
                },
                {
                    "id": "canvas-2",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "language": "python",
                    "role": "source",
                    "content": "print('active')",
                },
            ],
            active_document_id="canvas-1",
            canvas_viewports=[
                {"document_id": "canvas-1", "document_path": "src/legacy.py", "start_line": 1, "end_line": 1},
                {"document_id": "canvas-2", "document_path": "src/app.py", "start_line": 1, "end_line": 1},
            ],
            max_lines=10,
        )

        self.assertIsNotNone(payload)
        self.assertTrue(payload["active_document_ignored"])
        self.assertEqual(payload["visible_lines"], [])
        self.assertEqual(payload["visible_line_end"], 0)
        self.assertEqual([entry["id"] for entry in payload["ignored_documents"]], ["canvas-1"])
        self.assertEqual(payload["ignored_documents"][0]["ignored_reason"], "Superseded by src/app.py")
        self.assertEqual([entry["id"] for entry in payload["other_documents"]], ["canvas-2"])
        self.assertEqual([viewport["document_id"] for viewport in payload["viewports"]], ["canvas-2"])

    def test_build_canvas_prompt_payload_keeps_full_long_markdown_lines_when_document_fits_budget(self):
        long_line = "A" * 220
        document = normalize_canvas_document(
            {
                "id": "doc-1",
                "title": "report.md",
                "format": "markdown",
                "language": "markdown",
                "content": f"{long_line}\nshort line",
            }
        )

        payload = _build_canvas_prompt_payload([document], max_lines=10)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["clipped_line_count"], 0)
        self.assertEqual(payload["visible_lines"][0], f"1: {long_line}")
        self.assertEqual(payload["visible_lines"][1], "2: short line")

    def test_build_canvas_prompt_payload_clips_long_markdown_lines_when_needed_to_fit_budget(self):
        long_line = "A" * 220
        document = normalize_canvas_document(
            {
                "id": "doc-1",
                "title": "report.md",
                "format": "markdown",
                "language": "markdown",
                "content": f"{long_line}\nshort line",
            }
        )

        payload = _build_canvas_prompt_payload([document], max_lines=10, max_chars=120)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["clipped_line_count"], 1)
        self.assertTrue(payload["visible_lines"][0].startswith("1: "))
        self.assertTrue(payload["visible_lines"][0].endswith(".."))
        self.assertLess(len(payload["visible_lines"][0]), len(f"1: {long_line}"))

    def test_build_canvas_prompt_payload_uses_custom_line_clip_limits(self):
        code_line = "x" * 220
        markdown_line = "A" * 220
        code_document = normalize_canvas_document(
            {
                "id": "doc-code",
                "title": "app.py",
                "format": "code",
                "language": "python",
                "content": f"{code_line}\nprint('done')",
            }
        )
        markdown_document = normalize_canvas_document(
            {
                "id": "doc-md",
                "title": "notes.md",
                "format": "markdown",
                "language": "markdown",
                "content": f"{markdown_line}\nshort line",
            }
        )

        code_payload = _build_canvas_prompt_payload(
            [code_document],
            max_lines=10,
            max_chars=120,
            code_line_max_chars=60,
        )
        markdown_payload = _build_canvas_prompt_payload(
            [markdown_document],
            max_lines=10,
            max_chars=120,
            text_line_max_chars=55,
        )

        self.assertIsNotNone(code_payload)
        self.assertIsNotNone(markdown_payload)
        self.assertTrue(code_payload["visible_lines"][0].endswith(".."))
        self.assertTrue(markdown_payload["visible_lines"][0].endswith(".."))
        self.assertLessEqual(len(code_payload["visible_lines"][0]), len("1: ") + 60)
        self.assertLessEqual(len(markdown_payload["visible_lines"][0]), len("1: ") + 55)

    def test_normalize_canvas_document_detects_page_count_from_markers(self):
        document = normalize_canvas_document(
            {
                "id": "pdf-1",
                "title": "report.pdf",
                "format": "markdown",
                "content": "## Page 1\n\nAlpha\n\n---\n\n## Page 2\n\nBeta",
            }
        )

        self.assertEqual(document["page_count"], 2)

    def test_normalize_canvas_document_ignores_page_markers_in_code_documents(self):
        document = normalize_canvas_document(
            {
                "id": "code-1",
                "title": "app.py",
                "format": "code",
                "content": "## Page 1\nprint('hello')",
            }
        )

        self.assertNotIn("page_count", document)

    def test_scroll_canvas_document_returns_window_flags(self):
        content = "\n".join(f"line {index}" for index in range(1, 101))
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "Large file",
                    "format": "code",
                    "language": "python",
                    "content": content,
                }
            ]
        )

        result = scroll_canvas_document(runtime_state, 20, 60, max_window_lines=15)

        self.assertEqual(result["start_line"], 20)
        self.assertEqual(result["end_line_actual"], 34)
        self.assertEqual(len(result["visible_lines"]), 15)
        self.assertTrue(result["has_more_above"])
        self.assertTrue(result["has_more_below"])

    def test_scroll_canvas_document_visual_mode_error_includes_guidance(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-visual",
                    "title": "scan.pdf",
                    "path": "docs/scan.pdf",
                    "format": "markdown",
                    "content_mode": "visual",
                    "canvas_mode": "preview_only",
                    "content": "## Page 1\n\n[Visual page 1 preview is available in the Canvas panel.]",
                }
            ],
            active_document_id="doc-visual",
        )

        with self.assertRaisesRegex(ValueError, "image-backed"):
            scroll_canvas_document(runtime_state, 1, 3)

    def test_search_canvas_document_defaults_to_active_document(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "a.py",
                    "path": "src/a.py",
                    "format": "code",
                    "content": "alpha\nbeta\ngamma",
                },
                {
                    "id": "doc-2",
                    "title": "b.py",
                    "path": "src/b.py",
                    "format": "code",
                    "content": "beta only",
                },
            ],
            active_document_id="doc-1",
        )

        result = search_canvas_document(runtime_state, "beta")

        self.assertEqual(result["match_count"], 1)
        self.assertEqual(result["matches"][0]["document_id"], "doc-1")
        self.assertEqual(result["matches"][0]["line"], 2)

    def test_search_canvas_document_can_search_all_documents(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "a.py",
                    "path": "src/a.py",
                    "format": "code",
                    "content": "alpha\nbeta",
                },
                {
                    "id": "doc-2",
                    "title": "b.py",
                    "path": "src/b.py",
                    "format": "code",
                    "content": "beta\ngamma",
                },
            ],
            active_document_id="doc-1",
        )

        result = search_canvas_document(runtime_state, "beta", all_documents=True)

        self.assertEqual(result["match_count"], 2)
        self.assertEqual([match["document_id"] for match in result["matches"]], ["doc-1", "doc-2"])

    def test_search_canvas_document_supports_context_lines_and_offset(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "a.py",
                    "path": "src/a.py",
                    "format": "code",
                    "content": "zero\nalpha\nbeta\ngamma\nbeta again\ndelta",
                }
            ],
            active_document_id="doc-1",
        )

        result = search_canvas_document(runtime_state, "beta", context_lines=1, offset=1, max_results=1)

        self.assertEqual(result["match_count"], 2)
        self.assertEqual(result["returned_count"], 1)
        self.assertFalse(result["has_more"])
        self.assertEqual(result["matches"][0]["line"], 5)
        self.assertEqual(result["matches"][0]["context_before"], ["4: gamma"])
        self.assertEqual(result["matches"][0]["context_after"], ["6: delta"])

    def test_batch_read_canvas_documents_combines_expand_and_scroll_requests(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "a.py",
                    "path": "src/a.py",
                    "format": "code",
                    "content": "one\ntwo\nthree\nfour",
                },
                {
                    "id": "doc-2",
                    "title": "README.md",
                    "path": "README.md",
                    "format": "markdown",
                    "content": "# Title\n\nHello",
                },
            ],
            active_document_id="doc-1",
        )

        result = batch_read_canvas_documents(
            runtime_state,
            [
                {"document_path": "src/a.py", "start_line": 2, "end_line": 3},
                {"document_path": "README.md"},
                {"document_path": "missing.py"},
            ],
        )

        self.assertEqual(result["requested_count"], 3)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["results"][0]["action"], "scrolled")
        self.assertEqual(result["results"][0]["visible_lines"], ["2: two", "3: three"])
        self.assertEqual(result["results"][1]["action"], "expanded")
        self.assertEqual(result["results"][2]["status"], "error")

    def test_set_canvas_viewport_permanent_disables_auto_unpin(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "content": "line 1\nline 2\nline 3",
                }
            ]
        )

        result = set_canvas_viewport(
            runtime_state,
            document_path="src/app.py",
            start_line=2,
            end_line=3,
            permanent=True,
            auto_unpin_on_edit=True,
        )

        self.assertTrue(result["pinned"]["permanent"])
        self.assertFalse(result["pinned"]["auto_unpin_on_edit"])
        self.assertEqual(result["pinned"]["ttl_turns"], 0)

    def test_set_canvas_viewport_ttl_zero_is_treated_as_permanent(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "content": "line 1\nline 2\nline 3",
                }
            ]
        )

        result = set_canvas_viewport(
            runtime_state,
            document_path="src/app.py",
            start_line=1,
            end_line=2,
            ttl_turns=0,
            auto_unpin_on_edit=True,
        )

        self.assertTrue(result["pinned"]["permanent"])
        self.assertFalse(result["pinned"]["auto_unpin_on_edit"])
        self.assertEqual(result["pinned"]["ttl_turns"], 0)
        self.assertEqual(result["pinned"]["remaining_turns"], 0)

    def test_set_canvas_viewport_rejects_visual_canvas_documents(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-visual",
                    "title": "scan.pdf",
                    "path": "docs/scan.pdf",
                    "format": "markdown",
                    "content": "# scan.pdf",
                    "content_mode": "visual",
                    "canvas_mode": "preview_only",
                    "page_count": 2,
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "text-addressable lines"):
            set_canvas_viewport(runtime_state, document_path="docs/scan.pdf", start_line=1, end_line=2)

    def test_validate_canvas_document_detects_python_and_markdown_issues(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "broken.py",
                    "path": "broken.py",
                    "format": "code",
                    "language": "python",
                    "content": "def broken(:\n    pass\n",
                },
                {
                    "id": "doc-2",
                    "title": "README.md",
                    "path": "README.md",
                    "format": "markdown",
                    "content": "# Title\n### Skipped\n```python\nprint('x')\n",
                },
            ],
            active_document_id="doc-1",
        )

        python_result = validate_canvas_document(runtime_state, document_path="broken.py")
        markdown_result = validate_canvas_document(runtime_state, document_path="README.md")

        self.assertFalse(python_result["is_valid"])
        self.assertEqual(python_result["validator_used"], "python")
        self.assertEqual(python_result["issues"][0]["severity"], "error")
        self.assertEqual(markdown_result["validator_used"], "markdown")
        self.assertTrue(any(issue["message"] == "Unclosed fenced code block." for issue in markdown_result["issues"]))

    def test_validate_canvas_document_marks_visual_canvas_documents_invalid_for_text_validation(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-visual",
                    "title": "scan.pdf",
                    "path": "docs/scan.pdf",
                    "format": "markdown",
                    "content": "# scan.pdf",
                    "content_mode": "visual",
                    "canvas_mode": "preview_only",
                    "page_count": 2,
                }
            ]
        )

        result = validate_canvas_document(runtime_state, document_path="docs/scan.pdf")

        self.assertFalse(result["is_valid"])
        self.assertEqual(result["validator_used"], "none")
        self.assertIn("image-backed previews", result["issues"][0]["message"])

    def test_focus_canvas_page_pins_detected_page_range(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "report.pdf",
                    "path": "docs/report.pdf",
                    "format": "markdown",
                    "content": "## Page 1\n\nAlpha\n\n---\n\n## Page 2\n\nBeta",
                }
            ]
        )

        result = focus_canvas_page(runtime_state, document_path="docs/report.pdf", page_number=2, ttl_turns=2)
        payloads = get_canvas_viewport_payloads(runtime_state)

        self.assertEqual(result["action"], "page_focused")
        self.assertEqual(result["page_number"], 2)
        self.assertEqual(result["start_line"], 7)
        self.assertEqual(result["end_line"], 9)
        self.assertEqual(payloads[0]["page_number"], 2)
        self.assertEqual(payloads[0]["start_line"], 7)
        self.assertEqual(payloads[0]["end_line"], 9)

    def test_execute_tool_scroll_canvas_document_uses_runtime_window_limit(self):
        content = "\n".join(f"line {index}" for index in range(1, 101))
        runtime_state = {
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "doc-1",
                        "title": "Large file",
                        "format": "code",
                        "language": "python",
                        "content": content,
                    }
                ]
            ),
            "canvas_limits": {"scroll_window_lines": 12},
        }

        result, summary = _execute_tool(
            "scroll_canvas_document",
            {"start_line": 5, "end_line": 99},
            runtime_state=runtime_state,
        )

        self.assertEqual(result["action"], "scrolled")
        self.assertEqual(result["start_line"], 5)
        self.assertEqual(result["end_line_actual"], 16)
        self.assertIn("Canvas scrolled", summary)

    def test_execute_tool_search_canvas_document_supports_all_documents(self):
        runtime_state = {
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "doc-1",
                        "title": "a.py",
                        "path": "src/a.py",
                        "format": "code",
                        "content": "alpha\nbeta",
                    },
                    {
                        "id": "doc-2",
                        "title": "b.py",
                        "path": "src/b.py",
                        "format": "code",
                        "content": "beta\ngamma",
                    },
                ],
                active_document_id="doc-1",
            )
        }

        result, summary = _execute_tool(
            "search_canvas_document",
            {"query": "beta", "all_documents": True},
            runtime_state=runtime_state,
        )

        self.assertEqual(result["action"], "searched")
        self.assertEqual(result["match_count"], 2)
        self.assertIn("canvas matches found", summary)

    def test_runtime_system_message_mentions_canvas_scroll_for_truncated_excerpt(self):
        content = "\n".join(f"line {index}" for index in range(1, 51))
        document = normalize_canvas_document(
            {
                "id": "doc-1",
                "title": "Large file",
                "format": "code",
                "language": "python",
                "content": content,
            }
        )

        message = build_runtime_system_message(
            canvas_documents=[document],
            canvas_prompt_max_lines=10,
        )

        self.assertIn("This canvas excerpt is truncated", message["content"])
        self.assertIn("when no canvas read tool is enabled", message["content"])
        self.assertNotIn("scroll_canvas_document", message["content"])
        self.assertNotIn("expand_canvas_document", message["content"])

    def test_runtime_system_message_does_not_ask_expand_scroll_for_full_canvas(self):
        content = "\n".join(f"line {index}" for index in range(1, 11))
        document = normalize_canvas_document(
            {
                "id": "doc-1",
                "title": "Small file",
                "format": "code",
                "language": "python",
                "content": content,
            }
        )

        message = build_runtime_system_message(
            canvas_documents=[document],
            canvas_prompt_max_lines=20,
        )

        self.assertIn("fully visible in the current excerpt", message["content"])
        self.assertIn("Canvas is already fully visible", message["content"])
        self.assertNotIn("If this excerpt is truncated", message["content"])

    def test_extract_partial_json_string_value_handles_partial_escapes(self):
        arguments_text = "{\"title\":\"Plan\",\"content\":\"Line 1\\nLine 2\\u00e7 ve \\\"quote\\\""

        extracted = _extract_partial_json_string_value(arguments_text, "content")

        self.assertEqual(extracted, 'Line 1\nLine 2ç ve "quote"')

    def test_parse_tool_call_arguments_accepts_markdown_fenced_json(self):
        tool_args, parse_error = _parse_tool_call_arguments(
            "```json\n{\"start_line\": 12, \"end_line\": 14, \"lines\": [\"socket_client = None\"]}\n```",
            "replace_canvas_lines",
        )

        self.assertIsNone(parse_error)
        self.assertEqual(
            tool_args,
            {
                "start_line": 12,
                "end_line": 14,
                "lines": ["socket_client = None"],
            },
        )

    def test_parse_tool_call_arguments_repairs_truncated_json_object(self):
        tool_args, parse_error = _parse_tool_call_arguments(
            '{"start_line": 12, "end_line": 14, "lines": ["socket_client = None"]',
            "replace_canvas_lines",
        )

        self.assertIsNone(parse_error)
        self.assertEqual(
            tool_args,
            {
                "start_line": 12,
                "end_line": 14,
                "lines": ["socket_client = None"],
            },
        )

    def test_build_streaming_canvas_tool_preview_reads_partial_canvas_args(self):
        tool_call_parts = [
            {
                "name": "create_canvas_document",
                "arguments_parts": [
                    '{"title":"Spec","format":"code","language":"python","content":"print(1)\\nprint(2)"',
                ],
            }
        ]

        preview = _build_streaming_canvas_tool_preview(tool_call_parts)

        self.assertEqual(preview["tool"], "create_canvas_document")
        self.assertEqual(preview["preview_key"], "canvas-call-0")
        self.assertEqual(preview["snapshot"]["title"], "Spec")
        self.assertEqual(preview["snapshot"]["format"], "code")
        self.assertEqual(preview["snapshot"]["language"], "python")
        self.assertEqual(preview["content"], "print(1)\nprint(2)")

    def test_build_streaming_canvas_tool_preview_uses_latest_canvas_call(self):
        tool_call_parts = [
            {
                "name": "create_canvas_document",
                "arguments_parts": [
                    '{"title":"first.py","format":"code","language":"python","content":"print(1)"',
                ],
            },
            {
                "name": "create_canvas_document",
                "arguments_parts": [
                    '{"title":"second.py","format":"code","language":"python","content":"print(2)"',
                ],
            },
        ]

        preview = _build_streaming_canvas_tool_preview(tool_call_parts)

        self.assertEqual(preview["tool"], "create_canvas_document")
        self.assertEqual(preview["preview_key"], "canvas-call-1")
        self.assertEqual(preview["snapshot"]["title"], "second.py")
        self.assertEqual(preview["content"], "print(2)")

    def test_build_streaming_canvas_tool_preview_synthesizes_replace_canvas_preview_content(self):
        canvas_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "notes.md",
                    "path": "docs/notes.md",
                    "format": "markdown",
                    "content": "alpha\nbeta\ngamma",
                }
            ],
            active_document_id="doc-1",
        )
        tool_call_parts = [
            {
                "name": "replace_canvas_lines",
                "arguments_parts": [
                    '{"document_id":"doc-1","start_line":2,"end_line":2,"lines":["beta updated"]',
                ],
            }
        ]

        preview = _build_streaming_canvas_tool_preview(tool_call_parts, canvas_state)

        self.assertEqual(preview["tool"], "replace_canvas_lines")
        self.assertEqual(preview["snapshot"]["document_id"], "doc-1")
        self.assertEqual(preview["snapshot"]["path"], "docs/notes.md")
        self.assertEqual(preview["content_mode"], "replace")
        self.assertEqual(preview["content"], "alpha\nbeta updated\ngamma")

    def test_build_streaming_canvas_tool_preview_synthesizes_insert_canvas_preview_content(self):
        canvas_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "script.py",
                    "path": "src/script.py",
                    "format": "code",
                    "language": "python",
                    "content": "print(1)\nprint(3)",
                }
            ],
            active_document_id="doc-1",
        )
        tool_call_parts = [
            {
                "name": "insert_canvas_lines",
                "arguments_parts": [
                    '{"document_path":"src/script.py","after_line":1,"lines":["print(2)"]',
                ],
            }
        ]

        preview = _build_streaming_canvas_tool_preview(tool_call_parts, canvas_state)

        self.assertEqual(preview["tool"], "insert_canvas_lines")
        self.assertEqual(preview["snapshot"]["document_path"], "src/script.py")
        self.assertEqual(preview["snapshot"]["language"], "python")
        self.assertEqual(preview["content_mode"], "replace")
        self.assertEqual(preview["content"], "print(1)\nprint(2)\nprint(3)")

    def test_build_streaming_canvas_tool_preview_synthesizes_batch_canvas_preview_content(self):
        canvas_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "notes.md",
                    "path": "docs/notes.md",
                    "format": "markdown",
                    "content": "alpha\nbeta\ngamma",
                }
            ],
            active_document_id="doc-1",
        )
        tool_call_parts = [
            {
                "name": "batch_canvas_edits",
                "arguments_parts": [
                    '{"document_path":"docs/notes.md","operations":[{"action":"replace","start_line":2,"end_line":2,"lines":["beta updated"]}]',
                ],
            }
        ]

        preview = _build_streaming_canvas_tool_preview(tool_call_parts, canvas_state)

        self.assertEqual(preview["tool"], "batch_canvas_edits")
        self.assertEqual(preview["content_mode"], "replace")
        self.assertEqual(preview["content"], "alpha\nbeta updated\ngamma")

    def test_build_streaming_canvas_tool_preview_synthesizes_transform_canvas_preview_content(self):
        canvas_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "config.py",
                    "path": "config.py",
                    "format": "code",
                    "language": "python",
                    "content": "DEBUG = False\nprint('done')",
                }
            ],
            active_document_id="doc-1",
        )
        tool_call_parts = [
            {
                "name": "transform_canvas_lines",
                "arguments_parts": [
                    '{"document_path":"config.py","pattern":"DEBUG = False","replacement":"DEBUG = True"}',
                ],
            }
        ]

        preview = _build_streaming_canvas_tool_preview(tool_call_parts, canvas_state)

        self.assertEqual(preview["tool"], "transform_canvas_lines")
        self.assertEqual(preview["content_mode"], "replace")
        self.assertEqual(preview["content"], "DEBUG = True\nprint('done')")

    def test_canvas_self_read_guard_skips_path_target_after_same_turn_mutation(self):
        canvas_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "language": "python",
                    "content": "print('x')",
                }
            ],
            active_document_id="doc-1",
        )

        should_skip, guard_message = _should_skip_canvas_read_after_same_turn_mutation(
            "scroll_canvas_document",
            {"document_path": "src/app.py", "start_line": 1, "end_line": 1},
            canvas_state,
            mutated_doc_ids=set(),
            mutated_doc_paths={"src/app.py"},
        )

        self.assertTrue(should_skip)
        self.assertIn("src/app.py", guard_message)

    def test_canvas_self_read_guard_skips_default_active_document_after_mutation(self):
        canvas_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "README.md",
                    "path": "README.md",
                    "format": "markdown",
                    "content": "# hi",
                }
            ],
            active_document_id="doc-1",
        )

        should_skip, guard_message = _should_skip_canvas_read_after_same_turn_mutation(
            "expand_canvas_document",
            {},
            canvas_state,
            mutated_doc_ids={"doc-1"},
            mutated_doc_paths=set(),
        )

        self.assertTrue(should_skip)
        self.assertIn("README.md", guard_message)

    def test_canvas_self_read_guard_does_not_skip_all_documents_search(self):
        canvas_state = create_canvas_runtime_state(
            [
                {
                    "id": "doc-1",
                    "title": "a.py",
                    "path": "src/a.py",
                    "format": "code",
                    "content": "alpha",
                },
                {
                    "id": "doc-2",
                    "title": "b.py",
                    "path": "src/b.py",
                    "format": "code",
                    "content": "beta",
                },
            ],
            active_document_id="doc-1",
        )

        should_skip, guard_message = _should_skip_canvas_read_after_same_turn_mutation(
            "search_canvas_document",
            {"query": "a", "all_documents": True},
            canvas_state,
            mutated_doc_ids={"doc-1"},
            mutated_doc_paths={"src/a.py"},
        )

        self.assertFalse(should_skip)
        self.assertEqual(guard_message, "")

    def test_collect_canvas_mutation_locators_includes_paths_from_targets_and_result(self):
        tracked_ids, tracked_paths = _collect_canvas_mutation_locators(
            "batch_canvas_edits",
            {
                "targets": [
                    {
                        "document_path": "src/app.py",
                        "operations": [{"action": "replace", "start_line": 1, "end_line": 1, "lines": ["print('ok')"]}],
                    }
                ]
            },
            {
                "documents": [
                    {"document_id": "doc-1", "document_path": "src/app.py"},
                    {"document_id": "doc-2", "document_path": "src/lib/util.py"},
                ]
            },
        )

        self.assertIn("doc-1", tracked_ids)
        self.assertIn("doc-2", tracked_ids)
        self.assertIn("src/app.py", tracked_paths)
        self.assertIn("src/lib/util.py", tracked_paths)
