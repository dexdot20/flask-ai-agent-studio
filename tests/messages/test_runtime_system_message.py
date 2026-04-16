from __future__ import annotations

from datetime import datetime, timedelta, timezone

from canvas_service import (
    create_canvas_runtime_state,
    get_canvas_runtime_active_document_id,
    get_canvas_runtime_documents,
    get_canvas_viewport_payloads,
    set_canvas_viewport,
)
from db import (
    build_effective_user_preferences,
    build_user_profile_system_context,
    upsert_user_profile_entry,
)
from messages import (
    build_runtime_system_message,
    build_tool_call_contract,
    prepend_runtime_context,
    refresh_canvas_sections_in_context_injection,
)
from tests.support.app_harness import BaseAppRoutesTestCase
from tool_registry import PARALLEL_SAFE_READ_ONLY_TOOL_NAMES, TOOL_SPEC_BY_NAME, get_openai_tool_specs, get_parallel_safe_tool_names


class TestRuntimeSystemMessage(BaseAppRoutesTestCase):
    def test_runtime_system_message_includes_explicit_current_date_and_time(self):
        now = datetime(2026, 3, 15, 21, 42, 5, tzinfo=timezone(timedelta(hours=3)))

        message = build_runtime_system_message(
            user_preferences="Keep answers short.",
            scratchpad_sections={"profile": "The user is 22 years old."},
            active_tool_names=[
                "append_scratchpad",
                "ask_clarifying_question",
                "image_explain",
                "search_knowledge_base",
                "search_tool_memory",
            ],
            retrieved_context="Context block",
            tool_memory_context="Remembered web result",
            now=now,
        )

        self.assertEqual(message["role"], "system")
        content = message["content"]
        self.assertIn("## Current Date and Time", content)
        self.assertIn("AUTHORITATIVE CURRENT TIME", content)
        self.assertIn("2026-03-15T21:40:00+03:00", content)
        self.assertIn("- Time: 21:40", content)
        self.assertIn("## Core Directives", content)
        self.assertIn("Keep answers short.", content)
        self.assertIn("Scratchpad (AI Persistent Memory)", content)
        self.assertIn("### User Profile & Mindset", content)
        self.assertIn("The user is 22 years old.", content)
        self.assertIn("Only minimal durable general facts", content)
        self.assertIn("Default away from scratchpad", content)
        self.assertIn("Web findings", content)
        self.assertIn("important enough to deserve long-term storage", content)
        self.assertIn("Never save them just because they were requested.", content)
        self.assertNotIn("Err on the side of saving if in doubt.", content)
        self.assertIn("Clarification**: If a good answer depends", content)
        self.assertIn("Image Follow-up**: Use for follow-up questions", content)
        self.assertIn("Tool Memory", content)
        self.assertIn("Remembered web result", content)
        self.assertIn("Knowledge Base", content)
        self.assertIn("Context block", content)
        self.assertNotIn("You are an advanced, capable, and helpful AI assistant.", content)

    def test_build_effective_user_preferences_combines_general_and_personality(self):
        combined = build_effective_user_preferences(
            {
                "general_instructions": "Keep answers short.",
                "ai_personality": "Sound calm, direct, and rigorous.",
            }
        )

        self.assertEqual(
            combined,
            "General instructions:\nKeep answers short.\n\nAI personality:\nSound calm, direct, and rigorous.",
        )

    def test_runtime_system_message_places_volatile_context_after_tool_calling(self):
        message = build_runtime_system_message(
            active_tool_names=["search_web", "search_knowledge_base", "search_tool_memory"],
            retrieved_context="Context block",
            tool_trace_context="- search_web [done]: prior result",
            tool_memory_context="Remembered web result",
        )

        content = message["content"]
        self.assertLess(content.index("## Tool Calling"), content.index("## Tool Execution History"))
        self.assertLess(content.index("## Tool Calling"), content.index("## Active Tools This Turn"))
        self.assertLess(content.index("## Tool Calling"), content.index("## Tool Memory"))
        self.assertLess(content.index("## Tool Calling"), content.index("## Knowledge Base"))

    def test_runtime_system_message_discourages_unnecessary_web_search(self):
        message = build_runtime_system_message(active_tool_names=["search_web", "fetch_url"])

        content = message["content"]
        self.assertIn("If you can answer definitively from the current context and the task does not require current, external, or source-specific verification, do not call a tool.", content)
        self.assertIn("Use web-research tools only when the task genuinely needs current facts, external verification, or exact source text.", content)
        self.assertIn("If the answer is already available from the current context, do not search or fetch anything.", content)

    def test_runtime_system_message_uses_canonical_role_heading_without_excess_blank_lines(self):
        message = build_runtime_system_message(
            user_preferences="Keep answers short.",
            scratchpad_sections={"notes": "One durable note."},
            active_tool_names=["search_web"],
        )

        content = message["content"]
        self.assertIn("## Assistant Role", content)
        self.assertIn("- You are a tool-using assistant.", content)
        self.assertNotIn("\n\n\n", content)

    def test_runtime_system_message_includes_user_profile_context(self):
        upsert_user_profile_entry("pref:concise", "The user prefers concise answers.", confidence=0.95, source="manual")

        message = build_runtime_system_message(
            user_profile_context=build_user_profile_system_context(),
            active_tool_names=[],
        )

        content = message["content"]
        self.assertIn("## User Profile", content)
        self.assertIn("The user prefers concise answers.", content)

    def test_build_runtime_system_message_formats_compact_auto_injected_rag_context(self):
        message = build_runtime_system_message(
            active_tool_names=["search_knowledge_base"],
            retrieved_context={
                "query": "release notes",
                "count": 1,
                "matches": [
                    {
                        "source_name": "Product changelog",
                        "similarity": 0.87,
                        "text": "The April release adds export support and fixes sync drift.",
                        "source_key": "secret-source-key",
                    }
                ],
            },
        )

        self.assertIn("Auto-injected query: release notes", message["content"])
        self.assertIn("Source: Product changelog", message["content"])
        self.assertIn("The April release adds export support", message["content"])
        self.assertNotIn("secret-source-key", message["content"])
        self.assertNotIn('"source_name"', message["content"])

    def test_build_runtime_system_message_marks_clarification_responses_before_knowledge_base(self):
        message = build_runtime_system_message(
            active_tool_names=["search_knowledge_base"],
            clarification_response={
                "assistant_message_id": 42,
                "answers": {
                    "group_size": {"display": "2 kişi"},
                    "age_range": {"display": "15-18"},
                },
            },
            retrieved_context={
                "query": "2 kişi 15-18",
                "count": 1,
                "matches": [
                    {
                        "source_name": "Social anxiety notes",
                        "similarity": 0.83,
                        "text": "Structured exposure tasks work better when matched to age and group size.",
                    }
                ],
            },
        )

        content = message["content"]
        self.assertIn("## Clarification Response", content)
        self.assertIn("direct response to your earlier clarification questions", content)
        self.assertIn("## Knowledge Base", content)
        self.assertLess(content.index("## Clarification Response"), content.index("## Knowledge Base"))

    def test_build_runtime_system_message_includes_all_clarification_rounds(self):
        message = build_runtime_system_message(
            active_tool_names=["search_knowledge_base"],
            clarification_response={
                "assistant_message_id": "99",
                "answers": {
                    "price": {"display": "199 TL - 3990 TL"},
                    "competition": {"display": "Bolca var"},
                },
            },
            all_clarification_rounds=[
                {
                    "questions": [
                        {"id": "budget", "label": "Reklam butceniz ne kadar?"},
                        {"id": "goal", "label": "Ana hedefiniz nedir?"},
                    ],
                    "answers": {
                        "budget": {"display": "Gunluk 200-300 TL"},
                        "goal": {"display": "Satin alma"},
                    },
                },
                {
                    "questions": [
                        {"id": "price", "label": "Urunun fiyat araligi nedir?"},
                        {"id": "competition", "label": "Rakipleriniz kim?"},
                    ],
                    "answers": {
                        "price": {"display": "199 TL - 3990 TL"},
                        "competition": {"display": "Bolca var"},
                    },
                },
            ],
        )

        content = message["content"]
        self.assertIn("## Clarification Response", content)
        self.assertIn("The clarification answers below capture the answered rounds", content)
        self.assertIn("Accept these answers at face value", content)
        self.assertIn("Round 1", content)
        self.assertIn("- Reklam butceniz ne kadar? → Gunluk 200-300 TL", content)
        self.assertIn("Round 2", content)
        self.assertIn("- Urunun fiyat araligi nedir? → 199 TL - 3990 TL", content)

    def test_build_runtime_system_message_includes_double_check_protocol(self):
        message = build_runtime_system_message(
            active_tool_names=["search_web", "fetch_url"],
            double_check=True,
            double_check_query="Verify whether the deployment command is still correct.",
        )

        content = message["content"]
        self.assertIn("## Double-Check Protocol", content)
        self.assertIn("Treat this turn as a verification pass", content)
        self.assertIn(
            "verify this specific claim or request first: Verify whether the deployment command is still correct.",
            content,
        )
        self.assertIn("strongest counterargument", content)
        self.assertIn("Do not present uncertain claims as certain", content)
        self.assertLess(content.index("## Current Date and Time"), content.index("## Double-Check Protocol"))

    def test_runtime_system_message_hides_canvas_edit_tools_without_canvas_document(self):
        message = build_runtime_system_message(
            active_tool_names=[
                "expand_canvas_document",
                "create_canvas_document",
                "rewrite_canvas_document",
                "preview_canvas_changes",
                "batch_canvas_edits",
                "transform_canvas_lines",
                "update_canvas_metadata",
                "set_canvas_viewport",
                "clear_canvas_viewport",
                "replace_canvas_lines",
                "insert_canvas_lines",
                "delete_canvas_lines",
                "delete_canvas_document",
                "clear_canvas",
            ],
        )

        content = message["content"]
        self.assertIn("## Canvas Editing Guidance", content)
        self.assertIn("Do not rewrite the whole document when only part needs to change", content)
        self.assertIn("obsolete, superseded, or just a scratch draft", content)
        self.assertIn("use clear_canvas instead of leaving dead documents behind", content)
        self.assertIn("If you do not know the document_id, use the document_path", content)
        self.assertIn("## Tool Calling", content)
        self.assertIn("## Active Tools This Turn", content)
        self.assertIn("Native function calling is enabled for this turn.", content)
        active_tools_start = content.index("## Active Tools This Turn")
        active_tools_block = content[active_tools_start:]
        self.assertIn("Callable tools: `create_canvas_document`", active_tools_block)
        self.assertNotIn("replace_canvas_lines", active_tools_block)
        self.assertNotIn("rewrite_canvas_document", active_tools_block)
        self.assertNotIn("## Active Canvas Document", content)
        self.assertNotIn("Available Tools", content)

    def test_canvas_cleanup_tool_guidance_mentions_obsolete_documents(self):
        delete_guidance = TOOL_SPEC_BY_NAME["delete_canvas_document"]["prompt"]["guidance"]
        clear_guidance = TOOL_SPEC_BY_NAME["clear_canvas"]["prompt"]["guidance"]

        self.assertIn("obsolete", delete_guidance)
        self.assertIn("superseded", delete_guidance)
        self.assertIn("obsolete", clear_guidance)
        self.assertIn("reset", clear_guidance)

    def test_runtime_system_message_includes_active_canvas_document_context(self):
        message = build_runtime_system_message(
            active_tool_names=[
                "create_canvas_document",
                "rewrite_canvas_document",
                "replace_canvas_lines",
                "expand_canvas_document",
                "scroll_canvas_document",
            ],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "main.py",
                    "format": "markdown",
                    "language": "python",
                    "content": "print('hello')\nprint('world')",
                }
            ],
        )

        content = message["content"]
        self.assertIn("## Active Canvas Document", content)
        self.assertIn("- Language: python", content)
        self.assertIn("- Total tokens (estimated): ~", content)
        self.assertIn("- Visible excerpt tokens (estimated): ~", content)
        self.assertIn("1: print('hello')", content)
        self.assertIn("2: print('world')", content)
        self.assertIn("## Canvas Editing Guidance", content)
        self.assertIn("Multiple canvas tool calls in one answer are fine", content)
        self.assertIn("If you do not know the document_id, use the document_path", content)
        self.assertIn("## Active Tools This Turn", content)
        self.assertNotIn("## Canvas File Set Summary", content)
        self.assertNotIn("## Canvas Decision Matrix", content)
        self.assertIn("create_canvas_document", content)
        self.assertNotIn("## Canvas Workflow", content)
        self.assertIn("## Tool Calling", content)
        self.assertIn("Use only the tools listed in the Active Tools section for this turn", content)

    def test_runtime_system_message_represents_ignored_canvas_documents_as_metadata_only(self):
        message = build_runtime_system_message(
            active_tool_names=[
                "update_canvas_metadata",
                "expand_canvas_document",
                "search_canvas_document",
            ],
            canvas_documents=[
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
            canvas_active_document_id="canvas-1",
        )

        content = message["content"]
        self.assertIn("- Ignored in prompt: true", content)
        self.assertIn("- Ignore reason: Superseded by src/app.py", content)
        self.assertIn("## Ignored Canvas Documents", content)
        self.assertIn("- src/legacy.py", content)
        self.assertIn("  - Symbols: legacy_main", content)
        self.assertIn("ignored=false", content)
        self.assertNotIn("SECRET_VALUE = 'hidden'", content)
        self.assertNotIn("print(SECRET_VALUE)", content)

    def test_build_tool_call_contract_mentions_parallel_and_dependent_tools(self):
        contract = build_tool_call_contract([
            "search_web",
            "fetch_url",
            "image_explain",
            "search_canvas_document",
            "search_tool_memory",
        ])

        rules_text = "\n".join(contract["rules"])
        batching_guidance = contract["batching_guidance"]
        self.assertIn("Use only the tools listed in the Active Tools section", rules_text)
        self.assertIn("search_web accepts only the queries array", rules_text)
        self.assertIn("Batch independent tool calls into one assistant turn", batching_guidance)
        self.assertIn("GATHER", batching_guidance)
        self.assertIn("search_knowledge_base and search_tool_memory can be batched", batching_guidance)

    def test_build_tool_call_contract_mentions_parallel_limit(self):
        contract = build_tool_call_contract([
            "search_web",
            "fetch_url",
            "read_file",
        ], max_parallel_tools=2)

        batching_guidance = contract["batching_guidance"]
        self.assertIn("cap is 2 per turn", batching_guidance)

    def test_parallel_safe_read_only_tool_metadata_stays_in_sync(self):
        expected_recent_tools = {
            "fetch_url_summarized",
            "scroll_fetched_content",
            "batch_read_canvas_documents",
            "validate_canvas_document",
            "preview_canvas_changes",
            "sub_agent",
        }

        runtime_parallel_safe = set(get_parallel_safe_tool_names(read_only_only=True))

        self.assertEqual(set(PARALLEL_SAFE_READ_ONLY_TOOL_NAMES), runtime_parallel_safe)
        self.assertTrue(expected_recent_tools.issubset(runtime_parallel_safe))

    def test_build_tool_call_contract_mentions_clarification_limit(self):
        contract = build_tool_call_contract(["ask_clarifying_question"], clarification_max_questions=3)

        rules_text = "\n".join(contract["rules"])
        self.assertIn("Ask at most 3 question(s) per call", rules_text)
        self.assertIn("Put the actual questions only in the tool arguments", rules_text)
        self.assertIn("Do not say that you prepared questions", rules_text)
        self.assertIn("plain UI text only", rules_text)
        self.assertIn("assistant-visible reply short and brief", rules_text)

    def test_runtime_system_message_includes_canvas_workspace_summary(self):
        message = build_runtime_system_message(
            active_tool_names=[
                "create_canvas_document",
                "rewrite_canvas_document",
                "replace_canvas_lines",
            ],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "role": "source",
                    "project_id": "demo-app",
                    "workspace_id": "demo-workspace",
                    "format": "code",
                    "language": "python",
                    "content": "from config import settings\n\nprint(settings)",
                    "imports": ["config"],
                    "symbols": ["main"],
                },
                {
                    "id": "canvas-2",
                    "title": "config.py",
                    "path": "src/config.py",
                    "role": "config",
                    "project_id": "demo-app",
                    "workspace_id": "demo-workspace",
                    "format": "code",
                    "language": "python",
                    "content": "settings = {'debug': True}",
                    "exports": ["settings"],
                },
            ],
            canvas_active_document_id="canvas-1",
        )

        content = message["content"]
        self.assertIn("## Canvas File Set Summary", content)
        self.assertIn("- Working mode: project", content)
        self.assertIn("- Project label: demo-app", content)
        self.assertIn("- Active file: src/app.py", content)
        self.assertIn("- Active file size: src/app.py — 3 lines", content)
        self.assertIn("- Other files: src/config.py", content)
        self.assertIn("- Other file sizes: src/config.py — 1 line", content)
        self.assertNotIn("- Path: src/app.py", content)
        self.assertIn("- Role: source", content)
        self.assertIn("- Active document id: canvas-1", content)
        self.assertIn("- Canvas view status: full document visible (3/3 lines)", content)
        self.assertIn("- Total lines: 3", content)
        self.assertIn("Canvas is already fully visible", content)
        self.assertIn("In project mode, prefer document_path for targeting", content)
        self.assertIn("## Active Tools This Turn", content)
        self.assertIn("document_path", content)
        self.assertNotIn("- Validation status:", content)
        self.assertNotIn("- Files in scope:", content)
        self.assertNotIn("- Shared imports:", content)
        self.assertNotIn("## Canvas Decision Matrix", content)
        self.assertNotIn("## Canvas Project Manifest", content)
        self.assertNotIn("## Canvas Relationship Map", content)
        self.assertNotIn("## Other Canvas Documents", content)

    def test_runtime_system_message_includes_remaining_context_budget_status(self):
        message = build_runtime_system_message(
            active_tool_names=["search_web"],
            runtime_budget_stats={"remaining_context_budget": 3210},
        )

        content = message["content"]
        self.assertIn("## Prompt Budget Status", content)
        self.assertIn("Remaining context budget ≈ 3210 tokens", content)

    def test_runtime_system_message_uses_document_titles_when_canvas_paths_are_missing(self):
        message = build_runtime_system_message(
            active_tool_names=[
                "create_canvas_document",
                "rewrite_canvas_document",
                "replace_canvas_lines",
            ],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "Research Notes",
                    "format": "markdown",
                    "content": "One\nTwo",
                },
                {
                    "id": "canvas-2",
                    "title": "Ricky - Career Profile and Preferences",
                    "format": "markdown",
                    "content": "Profile",
                },
            ],
            canvas_active_document_id="canvas-1",
        )

        content = message["content"]
        self.assertIn("- Active document: Research Notes", content)
        self.assertIn("- Other canvas documents: Ricky - Career Profile and Preferences", content)
        self.assertIn("use document_path only when an explicit project path is shown", content)
        self.assertIn("otherwise do not invent a path", content)

    def test_runtime_system_message_includes_pinned_canvas_viewports(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "language": "python",
                    "content": "line 1\nline 2\nline 3\nline 4",
                }
            ]
        )
        set_canvas_viewport(runtime_state, document_path="src/app.py", start_line=2, end_line=3, ttl_turns=2)

        message = build_runtime_system_message(
            active_tool_names=["set_canvas_viewport", "clear_canvas_viewport", "replace_canvas_lines"],
            canvas_documents=get_canvas_runtime_documents(runtime_state),
            canvas_active_document_id=get_canvas_runtime_active_document_id(runtime_state),
            canvas_viewports=get_canvas_viewport_payloads(runtime_state),
        )

        content = message["content"]
        self.assertIn("## Pinned Canvas Viewports", content)
        self.assertIn("src/app.py lines 2-3", content)
        self.assertIn("2: line 2", content)
        self.assertIn("3: line 3", content)

    def test_refresh_canvas_sections_in_context_injection_removes_deleted_canvas_sections(self):
        context_injection = (
            "## Current Date and Time\n"
            "- Time: 21:40\n\n"
            "## Active Canvas Document\n"
            "- Active document id: canvas-1\n"
            "```text\n"
            "1: old line\n"
            "```\n\n"
            "## Pinned Canvas Viewports\n"
            "- src/app.py lines 2-3\n\n"
            "## Conversation Summaries\n"
            "- Earlier summary"
        )

        refreshed = refresh_canvas_sections_in_context_injection(
            context_injection,
            active_tool_names=["delete_canvas_document"],
            canvas_documents=[],
        )

        self.assertIn("## Current Date and Time", refreshed)
        self.assertIn("## Conversation Summaries", refreshed)
        self.assertNotIn("## Active Canvas Document", refreshed)
        self.assertNotIn("## Pinned Canvas Viewports", refreshed)
        self.assertNotIn("old line", refreshed)
        self.assertLess(refreshed.index("## Current Date and Time"), refreshed.index("## Conversation Summaries"))

    def test_refresh_canvas_sections_in_context_injection_inserts_new_canvas_sections_before_summaries(self):
        context_injection = (
            "## Current Date and Time\n"
            "- Time: 21:40\n\n"
            "## Conversation Summaries\n"
            "- Earlier summary"
        )

        refreshed = refresh_canvas_sections_in_context_injection(
            context_injection,
            active_tool_names=["create_canvas_document", "rewrite_canvas_document"],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "notes.md",
                    "format": "markdown",
                    "language": "markdown",
                    "content": "alpha\nbeta",
                }
            ],
            canvas_active_document_id="canvas-1",
        )

        self.assertIn("## Active Canvas Document", refreshed)
        self.assertIn("1: alpha", refreshed)
        self.assertIn("2: beta", refreshed)
        self.assertLess(refreshed.index("## Active Canvas Document"), refreshed.index("## Conversation Summaries"))

    def test_runtime_system_message_mentions_canvas_preview_compaction(self):
        message = build_runtime_system_message(
            active_tool_names=[
                "create_canvas_document",
                "rewrite_canvas_document",
                "replace_canvas_lines",
                "expand_canvas_document",
                "scroll_canvas_document",
            ],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "report.md",
                    "format": "markdown",
                    "language": "markdown",
                    "content": ("A" * 260) + "\nshort line",
                }
            ],
            canvas_prompt_max_tokens=120,
        )

        content = message["content"]
        self.assertIn("Preview compaction: 1 long line(s) were clipped for token efficiency", content)
        self.assertIn("scroll_canvas_document or expand_canvas_document", content)

    def test_runtime_system_message_does_not_compact_small_canvas_document_that_fits_budget(self):
        message = build_runtime_system_message(
            active_tool_names=[
                "rewrite_canvas_document",
                "replace_canvas_lines",
                "expand_canvas_document",
                "scroll_canvas_document",
            ],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "notes.md",
                    "format": "markdown",
                    "language": "markdown",
                    "content": ("A" * 220) + "\nshort line",
                }
            ],
            canvas_prompt_max_tokens=10_000,
        )

        content = message["content"]
        self.assertNotIn("Preview compaction:", content)
        self.assertIn(f"1: {'A' * 220}", content)

    def test_runtime_system_message_explains_canvas_ui_vs_prompt_excerpt_when_truncated(self):
        message = build_runtime_system_message(
            active_tool_names=[
                "rewrite_canvas_document",
                "replace_canvas_lines",
                "expand_canvas_document",
                "scroll_canvas_document",
            ],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "notes.md",
                    "path": "notes.md",
                    "format": "markdown",
                    "language": "markdown",
                    "content": "\n".join(f"line {index} - {'A' * 180}" for index in range(1, 40)),
                }
            ],
            canvas_prompt_max_tokens=120,
        )

        content = message["content"]
        self.assertIn("This canvas excerpt is truncated", content)
        self.assertIn("The Canvas UI may show more content than the model currently has in context", content)
        self.assertIn("only the excerpt below and any pinned viewports are visible to you right now", content)
        self.assertIn("expand_canvas_document", content)
        self.assertIn("scroll_canvas_document", content)

    def test_canvas_tool_specs_prefer_smallest_valid_edit(self):
        batch_guidance = TOOL_SPEC_BY_NAME["batch_canvas_edits"]["prompt"]["guidance"]
        create_guidance = TOOL_SPEC_BY_NAME["create_canvas_document"]["prompt"]["guidance"]
        rewrite_guidance = TOOL_SPEC_BY_NAME["rewrite_canvas_document"]["prompt"]["guidance"]
        replace_guidance = TOOL_SPEC_BY_NAME["replace_canvas_lines"]["prompt"]["guidance"]
        expand_description = TOOL_SPEC_BY_NAME["expand_canvas_document"]["description"]
        expand_guidance = TOOL_SPEC_BY_NAME["expand_canvas_document"]["prompt"]["guidance"]
        scroll_description = TOOL_SPEC_BY_NAME["scroll_canvas_document"]["description"]
        search_guidance = TOOL_SPEC_BY_NAME["search_canvas_document"]["prompt"]["guidance"]

        self.assertIn("Prefer one batch_canvas_edits call", batch_guidance)
        self.assertIn("plain JSON object with an action field", batch_guidance)
        self.assertIn("For replace use start_line, end_line, and lines", batch_guidance)
        self.assertIn("Always include title", create_guidance)
        self.assertIn("src/app.py -> app.py", create_guidance)
        self.assertIn("Do not default to this when only part of the file needs to change", rewrite_guidance)
        self.assertIn("Multiple localized replace_canvas_lines calls are fine", replace_guidance)
        self.assertIn("document_id is optional", expand_description)
        self.assertIn("call-time snapshot", expand_description)
        self.assertIn("use document_path from the workspace summary or manifest", expand_guidance)
        self.assertIn("call expand_canvas_document again", expand_guidance)
        self.assertIn("before line-level edits", scroll_description)
        self.assertIn("Use this first when the user asks you to find something inside a large canvas", search_guidance)

    def test_update_canvas_metadata_tool_spec_supports_ignored_documents(self):
        metadata_spec = TOOL_SPEC_BY_NAME["update_canvas_metadata"]
        metadata_properties = metadata_spec["parameters"]["properties"]
        guidance = metadata_spec["prompt"]["guidance"]

        self.assertIn("ignored", metadata_properties)
        self.assertIn("ignored_reason", metadata_properties)
        self.assertIn("ignored=true", guidance)
        self.assertIn("ignored=false", guidance)

    def test_runtime_system_message_mentions_expand_snapshot_rule(self):
        message = build_runtime_system_message(
            active_tool_names=[
                "create_canvas_document",
                "rewrite_canvas_document",
                "replace_canvas_lines",
                "expand_canvas_document",
            ],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "report.md",
                    "format": "markdown",
                    "language": "markdown",
                    "content": "line 1\nline 2",
                }
            ],
        )

        content = message["content"]
        self.assertIn("Snapshot rule", content)
        self.assertIn("expand_canvas_document returns a call-time snapshot", content)
        self.assertIn("call it again before relying on that older view", content)

    def test_runtime_system_message_mentions_title_requirement_for_create_canvas_document(self):
        message = build_runtime_system_message(active_tool_names=["create_canvas_document"])

        content = message["content"]
        self.assertIn("create_canvas_document always needs BOTH title and content", content)
        self.assertIn("never omit title", content)

    def test_runtime_system_message_mentions_batch_operation_shape(self):
        message = build_runtime_system_message(
            active_tool_names=["batch_canvas_edits"],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "Draft",
                    "format": "markdown",
                    "content": "line 1\nline 2",
                }
            ],
        )

        content = message["content"]
        self.assertIn("Every batch_canvas_edits operation must be a plain object", content)
        self.assertIn("For batch_canvas_edits, replace needs start_line, end_line, and lines", content)

    def test_runtime_system_message_omits_disabled_scroll_guidance(self):
        message = build_runtime_system_message(
            active_tool_names=[
                "rewrite_canvas_document",
                "replace_canvas_lines",
                "expand_canvas_document",
            ],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "report.md",
                    "format": "markdown",
                    "language": "markdown",
                    "content": "\n".join(f"line {index}" for index in range(1, 80)),
                }
            ],
            canvas_prompt_max_lines=10,
        )

        content = message["content"]
        self.assertIn("expand_canvas_document", content)
        self.assertNotIn("scroll_canvas_document", content)

    def test_openai_tool_specs_include_expand_canvas_document_with_canvas_documents(self):
        tools = get_openai_tool_specs(
            [
                "batch_canvas_edits",
                "expand_canvas_document",
                "create_canvas_document",
                "rewrite_canvas_document",
            ],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "content": "print('hello')",
                }
            ],
        )

        tool_names = [entry["function"]["name"] for entry in tools]
        self.assertEqual(tool_names, ["expand_canvas_document", "create_canvas_document", "rewrite_canvas_document", "batch_canvas_edits"])

    def test_openai_tool_specs_hide_canvas_edit_tools_without_canvas_document(self):
        tools = get_openai_tool_specs(
            [
                "create_canvas_document",
                "rewrite_canvas_document",
                "batch_canvas_edits",
                "replace_canvas_lines",
                "clear_canvas",
            ]
        )

        tool_names = [entry["function"]["name"] for entry in tools]
        self.assertEqual(tool_names, ["create_canvas_document"])

    def test_prepend_runtime_context_places_datetime_system_message_first(self):
        messages = prepend_runtime_context(
            [{"role": "user", "content": "Hello"}],
            user_preferences="",
            active_tool_names=[],
            scratchpad_sections={"notes": "Persistent note"},
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertNotIn("id", messages[0])
        self.assertEqual(messages[2]["role"], "system")
        self.assertNotIn("id", messages[2])

        stable_content = messages[0]["content"]
        content = messages[2]["content"]
        self.assertNotIn("Current Date and Time", stable_content)
        self.assertNotIn("Persistent note", stable_content)
        self.assertIn("## Assistant Role", stable_content)
        self.assertIn("Persistent note", content)
        self.assertIn("Current Date and Time", content)
        self.assertLess(content.index("## Scratchpad (AI Persistent Memory)"), content.index("## Current Date and Time"))
        self.assertIn("> **AUTHORITATIVE CURRENT TIME:**", content)
        self.assertNotIn("User Preferences", content)
        self.assertIn("Date: ", content)
        self.assertIn("Time: ", content)
        self.assertEqual(messages[1]["role"], "user")

    def test_prepend_runtime_context_moves_dynamic_state_into_bottom_system_message(self):
        messages = prepend_runtime_context(
            [{"role": "user", "content": "Hello"}],
            user_preferences="Keep answers short.",
            active_tool_names=["save_to_conversation_memory"],
            user_profile_context="The user prefers concise answers.",
            conversation_memory=[
                {
                    "id": 7,
                    "entry_type": "task_context",
                    "key": "Goal",
                    "value": "Keep stable rules cached.",
                    "created_at": "2026-04-08 10:23:00",
                }
            ],
            scratchpad_sections={"notes": "Persistent note"},
        )

        static_content = messages[0]["content"]
        dynamic_content = messages[2]["content"]
        self.assertIn("## Assistant Role", static_content)
        self.assertIn("## Conversation Memory Write Policy", static_content)
        self.assertNotIn("## User Profile", static_content)
        self.assertNotIn("## Scratchpad (AI Persistent Memory)", static_content)
        self.assertNotIn("## Conversation Memory\n", static_content)

        self.assertIn("## User Profile", dynamic_content)
        self.assertIn("The user prefers concise answers.", dynamic_content)
        self.assertIn("## Scratchpad (AI Persistent Memory)", dynamic_content)
        self.assertIn("Persistent note", dynamic_content)
        self.assertIn("## Conversation Memory", dynamic_content)
        self.assertIn("Goal: Keep stable rules cached.", dynamic_content)
        self.assertIn("## Current Date and Time", dynamic_content)
        self.assertLess(dynamic_content.index("## User Profile"), dynamic_content.index("## Current Date and Time"))
        self.assertLess(dynamic_content.index("## Scratchpad (AI Persistent Memory)"), dynamic_content.index("## Current Date and Time"))
        self.assertLess(dynamic_content.index("## Conversation Memory"), dynamic_content.index("## Current Date and Time"))

    def test_prepend_runtime_context_places_datetime_before_conversation_summaries(self):
        messages = prepend_runtime_context(
            [
                {"role": "summary", "content": "Earlier summary"},
                {"role": "user", "content": "Hello"},
            ],
            user_preferences="",
            active_tool_names=[],
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[3]["role"], "system")
        content = messages[3]["content"]
        self.assertIn("## Conversation Summaries", content)
        self.assertIn("authoritative compressed history for earlier deleted turns", content)
        self.assertIn("## Current Date and Time", content)
        self.assertTrue(content.startswith("## Current Date and Time"))
        self.assertLess(content.index("## Current Date and Time"), content.index("## Conversation Summaries"))
        self.assertNotIn("id", messages[3])

    def test_runtime_system_message_places_datetime_before_tool_history(self):
        message = build_runtime_system_message(
            active_tool_names=["search_knowledge_base", "search_tool_memory"],
            tool_memory_context="Remembered result context.",
            tool_trace_context="- fetch_url https://example.com -> cached result",
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "notes.md",
                    "path": "notes.md",
                    "format": "markdown",
                    "content": "Reference block.\nStable canvas excerpt.",
                }
            ],
            now=datetime(2026, 4, 2, 21, 43, tzinfo=timezone.utc),
        )

        content = message["content"]
        self.assertIn("## Tool Memory", content)
        self.assertIn("## Active Canvas Document", content)
        self.assertIn("## Tool Execution History", content)
        self.assertIn("## Current Date and Time", content)
        self.assertIn("> **AUTHORITATIVE CURRENT TIME:**", content)
        self.assertLess(content.index("## Current Date and Time"), content.index("## Tool Memory"))
        self.assertLess(content.index("## Tool Memory"), content.index("## Tool Execution History"))
        self.assertLess(content.index("## Active Canvas Document"), content.index("## Tool Execution History"))
        self.assertLess(content.index("## Current Date and Time"), content.index("## Tool Execution History"))

    def test_runtime_system_message_includes_workspace_sandbox(self):
        message = build_runtime_system_message(
            active_tool_names=["create_file", "list_dir"],
            workspace_root="/tmp/workspace-root",
        )

        content = message["content"]
        self.assertIn("## Workspace Sandbox", content)
        self.assertIn("- Root: /tmp/workspace-root", content)
        self.assertIn("needs_confirmation", content)

    def test_tool_specs_include_guidance_for_workspace_and_news_tools(self):
        for tool_name in [
            "search_web",
            "search_news_ddgs",
            "search_news_google",
            "read_file",
            "list_dir",
            "validate_project_workspace",
        ]:
            prompt = TOOL_SPEC_BY_NAME[tool_name]["prompt"]
            self.assertTrue(str(prompt.get("guidance") or "").strip())

        self.assertIn("current information, external verification", TOOL_SPEC_BY_NAME["search_web"]["description"])
        self.assertIn("If the answer is already available from the current context", TOOL_SPEC_BY_NAME["search_web"]["prompt"]["guidance"])
        self.assertFalse(TOOL_SPEC_BY_NAME["search_web"]["parameters"].get("additionalProperties", True))
        self.assertIn("Do not pass max_results", TOOL_SPEC_BY_NAME["search_web"]["prompt"]["guidance"])
        self.assertIn("current news coverage", TOOL_SPEC_BY_NAME["search_news_ddgs"]["description"])
        self.assertIn("current news verification", TOOL_SPEC_BY_NAME["search_news_google"]["description"])
        self.assertEqual(TOOL_SPEC_BY_NAME["read_scratchpad"]["parameters"]["required"], [])

    def test_memory_tool_specs_separate_scratchpad_and_conversation_memory(self):
        scratchpad_guidance = TOOL_SPEC_BY_NAME["append_scratchpad"]["prompt"]["guidance"]
        conversation_guidance = TOOL_SPEC_BY_NAME["save_to_conversation_memory"]["prompt"]["guidance"]
        persona_guidance = TOOL_SPEC_BY_NAME["save_to_persona_memory"]["prompt"]["guidance"]

        self.assertIn("conversation memory instead", scratchpad_guidance)
        self.assertIn("future responses or behavior across conversations", scratchpad_guidance)
        self.assertIn("default to conversation memory", conversation_guidance)
        self.assertIn("Multiple compact entries are better than one overloaded summary", conversation_guidance)
        self.assertIn("current chat", persona_guidance)
        self.assertIn("global scratchpad", persona_guidance)

    def test_search_tool_specs_allow_optional_conversation_memory_promotion(self):
        knowledge_base_spec = TOOL_SPEC_BY_NAME["search_knowledge_base"]
        tool_memory_spec = TOOL_SPEC_BY_NAME["search_tool_memory"]

        self.assertIn("save_to_conversation_memory", knowledge_base_spec["parameters"]["properties"])
        self.assertIn("memory_key", knowledge_base_spec["parameters"]["properties"])
        self.assertIn("save_to_conversation_memory", tool_memory_spec["parameters"]["properties"])
        self.assertIn("memory_key", tool_memory_spec["parameters"]["properties"])
        self.assertIn("survive later turns in this chat", knowledge_base_spec["prompt"]["guidance"])
        self.assertIn("survive later turns in this chat", tool_memory_spec["prompt"]["guidance"])

    def test_runtime_system_message_renders_persona_memory_and_policy(self):
        message = build_runtime_system_message(
            active_tool_names=["save_to_persona_memory", "delete_persona_memory_entry"],
            persona_memory=[
                {
                    "id": 5,
                    "key": "Repo style",
                    "value": "Prefer concise progress updates.",
                    "created_at": "2026-04-08 09:15:00",
                }
            ],
        )

        content = message["content"]
        self.assertIn("## Persona Memory", content)
        self.assertIn("#5 09:15 - Repo style: Prefer concise progress updates.", content)
        self.assertIn("Shared durable memory for the currently active persona", content)
        self.assertIn("## Persona Memory Write Policy", content)
        self.assertIn("save_to_persona_memory", content)
        self.assertIn("conversation memory instead", content)
