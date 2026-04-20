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
from tool_registry import (
    PARALLEL_SAFE_READ_ONLY_TOOL_NAMES,
    TOOL_SPEC_BY_NAME,
    get_openai_tool_specs,
    get_parallel_safe_tool_names,
)


class TestRuntimeSystemMessage:
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

        assert message["role"] == "system"
        content = message["content"]
        assert "## Current Date and Time" in content
        assert "2026-03-15T21:40:00+03:00" in content
        assert "- Time: 21:40" in content
        assert "## Core Directives" in content
        assert "## Active Tools This Turn" in content
        assert "Scratchpad (AI Persistent Memory)" in content
        assert "### User Profile & Mindset" in content
        assert "The user is 22 years old." in content
        assert "Only minimal durable general facts" in content
        assert "Default away from scratchpad" in content
        assert "Web findings" in content
        assert "important enough to deserve long-term storage" in content
        assert "Never save them just because they were requested." in content
        assert "Err on the side of saving if in doubt." not in content
        assert "Clarification**: If a good answer depends" in content
        assert "Image Follow-up**: Use for follow-up questions" in content
        assert "Tool Memory" in content
        assert "Remembered web result" in content
        assert "Knowledge Base" in content
        assert "Context block" in content
        assert "You are an advanced, capable, and helpful AI assistant." not in content

    def test_build_effective_user_preferences_combines_general_and_personality(self):
        combined = build_effective_user_preferences(
            {
                "general_instructions": "Keep answers short.",
                "ai_personality": "Sound calm, direct, and rigorous.",
            }
        )

        assert (
            combined
            == "General instructions:\nKeep answers short.\n\nAI personality:\nSound calm, direct, and rigorous."
        )

    def test_runtime_system_message_places_volatile_context_after_tool_calling(self):
        message = build_runtime_system_message(
            active_tool_names=["search_web", "search_knowledge_base", "search_tool_memory"],
            retrieved_context="Context block",
            tool_trace_context="- search_web [done]: prior result",
            tool_memory_context="Remembered web result",
        )

        content = message["content"]
        assert content.index("## Tool Calling") < content.index("## Tool Execution History")
        assert content.index("## Tool Calling") < content.index("## Active Tools This Turn")
        assert content.index("## Tool Calling") < content.index("## Tool Memory")
        assert content.index("## Tool Calling") < content.index("## Knowledge Base")

    def test_runtime_system_message_discourages_unnecessary_web_search(self):
        message = build_runtime_system_message(active_tool_names=["search_web", "fetch_url"])

        content = message["content"]
        assert (
            "Call a tool only when strictly required. If you can answer from the current context without current/external/source-specific verification, do not call a tool."
            in content
        )
        assert (
            "Use web-research tools only when the task genuinely needs current facts, external verification, or exact source text."
            in content
        )
        assert (
            "If the answer is already available from the current context, do not search or fetch anything." in content
        )

    def test_runtime_system_message_uses_canonical_role_heading_without_excess_blank_lines(self):
        message = build_runtime_system_message(
            user_preferences="Keep answers short.",
            scratchpad_sections={"notes": "One durable note."},
            active_tool_names=["search_web"],
        )

        content = message["content"]
        assert "## Assistant Role" in content
        assert "- You are a tool-using assistant." in content
        assert "\n\n\n" not in content

    def test_runtime_system_message_includes_user_profile_context(self):
        upsert_user_profile_entry("pref:concise", "The user prefers concise answers.", confidence=0.95, source="manual")

        message = build_runtime_system_message(
            user_profile_context=build_user_profile_system_context(),
            active_tool_names=[],
        )

        content = message["content"]
        assert "## User Profile" in content
        assert "The user prefers concise answers." in content

    def test_runtime_system_message_omits_instructional_user_profile_entries(self):
        upsert_user_profile_entry(
            "fact:bad-template",
            "Task completion reports must use exact format: Yapılan işlemler, Neden yaptı, Kalan işlemler, Önerilen sıradaki adım",
            confidence=0.95,
            source="summary_extraction",
        )
        upsert_user_profile_entry("pref:concise", "The user prefers concise answers.", confidence=0.95, source="manual")

        message = build_runtime_system_message(
            user_profile_context=build_user_profile_system_context(),
            active_tool_names=[],
        )

        content = message["content"]
        assert "The user prefers concise answers." in content
        assert "Task completion reports must use exact format" not in content
        assert "Yapılan işlemler" not in content

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

        assert "Auto-injected query: release notes" in message["content"]
        assert "Source: Product changelog" in message["content"]
        assert "The April release adds export support" in message["content"]
        assert "secret-source-key" not in message["content"]
        assert '"source_name"' not in message["content"]

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
        assert "## Clarification Response" in content
        assert "do NOT save them with save_to_conversation_memory" in content
        assert "## Knowledge Base" in content
        assert content.index("## Clarification Response") < content.index("## Knowledge Base")

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
        assert "## Clarification Response" in content
        assert "do NOT save them with save_to_conversation_memory" in content
        assert "Round 1" in content
        assert "- Reklam butceniz ne kadar? → Gunluk 200-300 TL" in content
        assert "Round 2" in content
        assert "- Urunun fiyat araligi nedir? → 199 TL - 3990 TL" in content

    def test_build_runtime_system_message_includes_double_check_protocol(self):
        message = build_runtime_system_message(
            active_tool_names=["search_web", "fetch_url"],
            double_check=True,
            double_check_query="Verify whether the deployment command is still correct.",
        )

        content = message["content"]
        assert "## Double-Check Protocol" in content
        assert "Treat this turn as a verification pass" in content
        assert (
            "verify this specific claim or request first: Verify whether the deployment command is still correct."
            in content
        )
        assert "strongest counterargument" in content
        assert "Do not present uncertain claims as certain" in content
        assert content.index("## Current Date and Time") < content.index("## Double-Check Protocol")

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
        assert "## Canvas Editing Guidance" in content
        assert "Prefer replace/insert/delete_canvas_lines over rewrite when only a part needs to change" in content
        assert "delete obsolete documents with delete_canvas_document" in content
        assert "If the whole canvas is obsolete, use clear_canvas" in content
        assert "## Tool Calling" in content
        assert "## Active Tools This Turn" in content
        assert "Native function calling is enabled for this turn." in content
        active_tools_start = content.index("## Active Tools This Turn")
        active_tools_block = content[active_tools_start:]
        assert "Callable tools: `create_canvas_document`" in active_tools_block
        assert "replace_canvas_lines" not in active_tools_block
        assert "rewrite_canvas_document" not in active_tools_block
        assert "## Active Canvas Document" not in content
        assert "Available Tools" not in content

    def test_canvas_cleanup_tool_guidance_mentions_obsolete_documents(self):
        delete_guidance = TOOL_SPEC_BY_NAME["delete_canvas_document"]["prompt"]["guidance"]
        clear_guidance = TOOL_SPEC_BY_NAME["clear_canvas"]["prompt"]["guidance"]

        assert "obsolete" in delete_guidance
        assert "superseded" in delete_guidance
        assert "obsolete" in clear_guidance
        assert "reset" in clear_guidance

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
        assert "## Active Canvas Document" in content
        assert "- Language: python" in content
        assert "- Total tokens (estimated): ~" in content
        assert "- Visible excerpt tokens (estimated): ~" in content
        assert "1: print('hello')" in content
        assert "2: print('world')" in content
        assert "## Canvas Editing Guidance" in content
        assert "batch independent inspections in one answer, then batch all known edits in one answer" in content
        assert "## Active Tools This Turn" in content
        assert "## Canvas File Set Summary" not in content
        assert "## Canvas Decision Matrix" not in content
        assert "create_canvas_document" in content
        assert "## Canvas Workflow" not in content
        assert "## Tool Calling" in content
        assert "Use only the tools listed in the Active Tools section" in content

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
        assert "- Ignored in prompt: true" in content
        assert "- Ignore reason: Superseded by src/app.py" in content
        assert "## Ignored Canvas Documents" in content
        assert "- src/legacy.py" in content
        assert "  - Symbols: legacy_main" in content
        assert "ignored=false" in content
        assert "SECRET_VALUE = 'hidden'" not in content
        assert "print(SECRET_VALUE)" not in content

    def test_build_tool_call_contract_mentions_parallel_and_dependent_tools(self):
        contract = build_tool_call_contract(
            [
                "search_web",
                "fetch_url",
                "image_explain",
                "search_canvas_document",
                "search_tool_memory",
            ]
        )

        rules_text = "\n".join(contract["rules"])
        batching_guidance = contract["batching_guidance"]
        assert "Use only the tools listed in the Active Tools section" in rules_text
        assert "search_web accepts only the queries array" in rules_text
        assert "Batch independent tool calls into one assistant turn" in batching_guidance
        assert "GATHER" in batching_guidance
        assert "search_knowledge_base and search_tool_memory can be batched" in batching_guidance

    def test_build_tool_call_contract_mentions_parallel_limit(self):
        contract = build_tool_call_contract(
            [
                "search_web",
                "fetch_url",
                "read_file",
            ],
            max_parallel_tools=2,
        )

        batching_guidance = contract["batching_guidance"]
        assert "cap is 2 per turn" in batching_guidance

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

        assert set(PARALLEL_SAFE_READ_ONLY_TOOL_NAMES) == runtime_parallel_safe
        assert expected_recent_tools.issubset(runtime_parallel_safe)

    def test_build_tool_call_contract_mentions_clarification_limit(self):
        contract = build_tool_call_contract(["ask_clarifying_question"], clarification_max_questions=3)

        rules_text = "\n".join(contract["rules"])
        assert "Ask at most 3 question(s) per call" in rules_text
        assert "Put the actual questions only in the tool arguments" in rules_text
        assert "Do not say that you prepared questions" in rules_text
        assert "plain UI text only" in rules_text
        assert "assistant-visible reply short and brief" in rules_text

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
        assert "## Canvas File Set Summary" in content
        assert "- Working mode: project" in content
        assert "- Project label: demo-app" in content
        assert "- Active file: src/app.py" in content
        assert "- Active file size: src/app.py — 3 lines" in content
        assert "- Other files: src/config.py" in content
        assert "- Other file sizes: src/config.py — 1 line" in content
        assert "- Path: src/app.py" not in content
        assert "- Role: source" in content
        assert "- Active document id: canvas-1" in content
        assert "- Canvas view status: full document visible (3/3 lines)" in content
        assert "- Total lines: 3" in content
        assert "Canvas is already fully visible" in content
        assert "In project mode, prefer document_path for targeting" in content
        assert "## Active Tools This Turn" in content
        assert "document_path" in content
        assert "- Validation status:" not in content
        assert "- Files in scope:" not in content
        assert "- Shared imports:" not in content
        assert "## Canvas Decision Matrix" not in content
        assert "## Canvas Project Manifest" not in content
        assert "## Canvas Relationship Map" not in content
        assert "## Other Canvas Documents" not in content

    def test_runtime_system_message_includes_remaining_context_budget_status(self):
        message = build_runtime_system_message(
            active_tool_names=["search_web"],
            runtime_budget_stats={"remaining_context_budget": 3210},
        )

        content = message["content"]
        assert "## Prompt Budget Status" in content
        assert "Remaining context budget ≈ 3210 tokens" in content

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
        assert "- Active document: Research Notes" in content
        assert "- Other canvas documents: Ricky - Career Profile and Preferences" in content
        assert "Use document_path only when an explicit project path is shown" in content
        assert "target the active document or use document_id" in content

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
        assert "## Pinned Canvas Viewports" in content
        assert "src/app.py lines 2-3" in content
        assert "2: line 2" in content
        assert "3: line 3" in content

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

        assert "## Current Date and Time" in refreshed
        assert "## Conversation Summaries" in refreshed
        assert "## Active Canvas Document" not in refreshed
        assert "## Pinned Canvas Viewports" not in refreshed
        assert "old line" not in refreshed
        assert refreshed.index("## Current Date and Time") < refreshed.index("## Conversation Summaries")

    def test_refresh_canvas_sections_in_context_injection_inserts_new_canvas_sections_before_summaries(self):
        context_injection = "## Current Date and Time\n- Time: 21:40\n\n## Conversation Summaries\n- Earlier summary"

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

        assert "## Active Canvas Document" in refreshed
        assert "1: alpha" in refreshed
        assert "2: beta" in refreshed
        assert refreshed.index("## Active Canvas Document") < refreshed.index("## Conversation Summaries")

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
        assert "Preview compaction: 1 long line(s) were clipped for token efficiency" in content
        assert "scroll_canvas_document or expand_canvas_document" in content

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
        assert "Preview compaction:" not in content
        assert f"1: {'A' * 220}" in content

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
        assert "This canvas excerpt is truncated" in content
        assert "The Canvas UI may show more content than the model currently has in context" in content
        assert "only the excerpt below and any pinned viewports are visible to you right now" in content
        assert "expand_canvas_document" in content
        assert "scroll_canvas_document" in content

    def test_canvas_tool_specs_prefer_smallest_valid_edit(self):
        batch_guidance = TOOL_SPEC_BY_NAME["batch_canvas_edits"]["prompt"]["guidance"]
        create_guidance = TOOL_SPEC_BY_NAME["create_canvas_document"]["prompt"]["guidance"]
        rewrite_guidance = TOOL_SPEC_BY_NAME["rewrite_canvas_document"]["prompt"]["guidance"]
        replace_guidance = TOOL_SPEC_BY_NAME["replace_canvas_lines"]["prompt"]["guidance"]
        expand_description = TOOL_SPEC_BY_NAME["expand_canvas_document"]["description"]
        expand_guidance = TOOL_SPEC_BY_NAME["expand_canvas_document"]["prompt"]["guidance"]
        scroll_description = TOOL_SPEC_BY_NAME["scroll_canvas_document"]["description"]
        search_guidance = TOOL_SPEC_BY_NAME["search_canvas_document"]["prompt"]["guidance"]

        assert "Prefer one batch_canvas_edits call" in batch_guidance
        assert "plain JSON object with an action field" in batch_guidance
        assert "For replace use start_line, end_line, and lines" in batch_guidance
        assert "Always include title" in create_guidance
        assert "src/app.py -> app.py" in create_guidance
        assert "Do not default to this when only part of the file needs to change" in rewrite_guidance
        assert "Multiple localized replace_canvas_lines calls are fine" in replace_guidance
        assert "document_id is optional" in expand_description
        assert "call-time snapshot" in expand_description
        assert "use document_path from the workspace summary or manifest" in expand_guidance
        assert "call expand_canvas_document again" in expand_guidance
        assert "before line-level edits" in scroll_description
        assert "Use this first when the user asks you to find something inside a large canvas" in search_guidance

    def test_update_canvas_metadata_tool_spec_supports_ignored_documents(self):
        metadata_spec = TOOL_SPEC_BY_NAME["update_canvas_metadata"]
        metadata_properties = metadata_spec["parameters"]["properties"]
        guidance = metadata_spec["prompt"]["guidance"]

        assert "ignored" in metadata_properties
        assert "ignored_reason" in metadata_properties
        assert "ignored=true" in guidance
        assert "ignored=false" in guidance

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
        assert "Snapshot rule" in content
        assert "expand_canvas_document returns a call-time snapshot" in content
        assert "call it again before relying on that older view" in content

    def test_runtime_system_message_mentions_title_requirement_for_create_canvas_document(self):
        message = build_runtime_system_message(active_tool_names=["create_canvas_document"])

        content = message["content"]
        assert "create_canvas_document always needs BOTH title and content" in content
        assert "never omit title" in content

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
        assert "prefer batch_canvas_edits over serial calls" in content
        assert "replace needs start_line+end_line+lines" in content

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
        assert "expand_canvas_document" in content
        assert "scroll_canvas_document" not in content

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
        assert tool_names == [
            "expand_canvas_document",
            "create_canvas_document",
            "rewrite_canvas_document",
            "batch_canvas_edits",
        ]

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
        assert tool_names == ["create_canvas_document"]

    def test_prepend_runtime_context_places_datetime_system_message_first(self):
        messages = prepend_runtime_context(
            [{"role": "user", "content": "Hello"}],
            user_preferences="",
            active_tool_names=[],
            scratchpad_sections={"notes": "Persistent note"},
        )

        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "system"
        assert "id" not in messages[0]
        assert messages[2]["role"] == "user"

        static_content = messages[0]["content"]
        dynamic_content = messages[1]["content"]
        assert "## Assistant Role" in static_content
        assert "## Scratchpad (AI Persistent Memory)" in dynamic_content
        assert "Persistent note" in dynamic_content
        assert "## Current Date and Time" in dynamic_content
        assert dynamic_content.index("## Scratchpad (AI Persistent Memory)") < dynamic_content.index(
            "## Current Date and Time"
        )

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

        assert len(messages) == 3
        static_content = messages[0]["content"]
        dynamic_content = messages[1]["content"]
        assert "## Assistant Role" in static_content
        assert "## Conversation Memory Write Policy" in static_content
        assert "## User Profile" in dynamic_content
        assert "The user prefers concise answers." in dynamic_content
        assert "## Scratchpad (AI Persistent Memory)" in dynamic_content
        assert "Persistent note" in dynamic_content
        assert "## Conversation Memory" in dynamic_content
        assert "Goal: Keep stable rules cached." in dynamic_content
        assert "## Current Date and Time" in dynamic_content
        assert dynamic_content.index("## User Profile") < dynamic_content.index("## Current Date and Time")
        assert dynamic_content.index("## Scratchpad (AI Persistent Memory)") < dynamic_content.index(
            "## Current Date and Time"
        )
        assert dynamic_content.index("## Conversation Memory") < dynamic_content.index("## Current Date and Time")
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "Hello"

    def test_prepend_runtime_context_places_datetime_before_conversation_summaries(self):
        messages = prepend_runtime_context(
            [
                {"role": "summary", "content": "Earlier summary"},
                {"role": "user", "content": "Hello"},
            ],
            user_preferences="",
            active_tool_names=[],
        )

        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "system"
        assert messages[2]["role"] == "summary"
        assert messages[3]["role"] == "user"
        content = messages[1]["content"]
        assert "## Current Date and Time" in content
        assert "## Conversation Summaries" in content
        assert content.index("## Current Date and Time") < content.index("## Conversation Summaries")
        assert "id" not in messages[0]

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
        assert "## Tool Memory" in content
        assert "## Active Canvas Document" in content
        assert "## Tool Execution History" in content
        assert "## Current Date and Time" in content
        assert content.index("## Current Date and Time") < content.index("## Tool Memory")
        assert content.index("## Tool Memory") < content.index("## Tool Execution History")
        assert content.index("## Active Canvas Document") < content.index("## Tool Execution History")
        assert content.index("## Current Date and Time") < content.index("## Tool Execution History")

    def test_runtime_system_message_includes_workspace_sandbox(self):
        message = build_runtime_system_message(
            active_tool_names=["create_file", "list_dir"],
            workspace_root="/tmp/workspace-root",
        )

        content = message["content"]
        assert "## Workspace Sandbox" in content
        assert "- Root: /tmp/workspace-root" in content
        assert "needs_confirmation" in content

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
            assert str(prompt.get("guidance") or "").strip()

        assert "current information, external verification" in TOOL_SPEC_BY_NAME["search_web"]["description"]
        assert (
            "If the answer is already available from the current context"
            in TOOL_SPEC_BY_NAME["search_web"]["prompt"]["guidance"]
        )
        assert not TOOL_SPEC_BY_NAME["search_web"]["parameters"].get("additionalProperties", True)
        assert "Do not pass max_results" in TOOL_SPEC_BY_NAME["search_web"]["prompt"]["guidance"]
        assert "current news coverage" in TOOL_SPEC_BY_NAME["search_news_ddgs"]["description"]
        assert "current news verification" in TOOL_SPEC_BY_NAME["search_news_google"]["description"]
        assert TOOL_SPEC_BY_NAME["read_scratchpad"]["parameters"]["required"] == []

    def test_memory_tool_specs_separate_scratchpad_and_conversation_memory(self):
        scratchpad_guidance = TOOL_SPEC_BY_NAME["append_scratchpad"]["prompt"]["guidance"]
        conversation_guidance = TOOL_SPEC_BY_NAME["save_to_conversation_memory"]["prompt"]["guidance"]
        persona_guidance = TOOL_SPEC_BY_NAME["save_to_persona_memory"]["prompt"]["guidance"]

        assert "conversation memory instead" in scratchpad_guidance
        assert "future responses or behavior across conversations" in scratchpad_guidance
        assert "default to conversation memory" in conversation_guidance
        assert "When you need to save multiple facts" in conversation_guidance
        assert "current chat" in persona_guidance
        assert "global scratchpad" in persona_guidance

    def test_search_tool_specs_allow_optional_conversation_memory_promotion(self):
        knowledge_base_spec = TOOL_SPEC_BY_NAME["search_knowledge_base"]
        tool_memory_spec = TOOL_SPEC_BY_NAME["search_tool_memory"]

        assert "save_to_conversation_memory" in knowledge_base_spec["parameters"]["properties"]
        assert "memory_key" in knowledge_base_spec["parameters"]["properties"]
        assert "save_to_conversation_memory" in tool_memory_spec["parameters"]["properties"]
        assert "memory_key" in tool_memory_spec["parameters"]["properties"]
        assert "survive later turns in this chat" in knowledge_base_spec["prompt"]["guidance"]
        assert "survive later turns in this chat" in tool_memory_spec["prompt"]["guidance"]

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
        assert "## Persona Memory" in content
        assert "#5 09:15 - Repo style: Prefer concise progress updates." in content
        assert "Shared durable memory for the currently active persona" in content
        assert "## Persona Memory Write Policy" in content
        assert "save_to_persona_memory" in content
        assert "conversation memory instead" in content
