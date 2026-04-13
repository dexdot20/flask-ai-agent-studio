# ruff: noqa: I001
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pdfplumber
import requests as http_requests
from docx import Document
from werkzeug.datastructures import MultiDict

import model_registry
import ocr_service
import prune_service
import rag_service
import request_security
import web_tools
from agent import (
    CANVAS_MUTATION_TOOL_NAMES,
    CANVAS_TOOL_NAMES,
    CONTEXT_OVERFLOW_RECOVERY_ERROR_TEXT,
    FINAL_ANSWER_ERROR_TEXT,
    FINAL_ANSWER_MISSING_TEXT,
    SUB_AGENT_ALLOWED_TOOL_NAMES,
    _apply_tool_output_budget,
    _build_compact_tool_message_content,
    _build_final_answer_instruction,
    _build_reasoning_replay_instruction,
    _build_sub_agent_messages,
    _build_tool_execution_result_message,
    _conversation_has_clarification_tool_call,
    _estimate_input_breakdown,
    _estimate_message_breakdown,
    _execute_tool,
    _extract_usage_metrics,
    _format_tool_execution_error,
    _is_context_overflow_error,
    _iter_agent_exchange_blocks,
    _lookup_cross_turn_tool_memory,
    _prepare_tool_result_for_transcript,
    _run_fetch_url_summarized,
    _run_fetch_url_to_canvas,
    _run_sub_agent_stream,
    _summarize_model_call_usage,
    _tool_result_has_error,
    _truncate_preview_text,
    _try_compact_messages,
    collect_agent_response,
    run_agent_stream,
)
from app import create_app
from conversation_cleanup_service import capture_workspace_snapshot_for_assistant_message
from canvas_service import (
    batch_canvas_edits,
    build_canvas_project_manifest,
    build_canvas_tool_result,
    create_canvas_runtime_state,
    find_latest_canvas_documents,
    find_latest_canvas_state,
    get_canvas_runtime_active_document_id,
    get_canvas_runtime_documents,
    get_canvas_viewport_payloads,
    normalize_canvas_document,
    preview_canvas_changes,
    replace_canvas_lines,
    search_canvas_document,
    set_canvas_viewport,
    transform_canvas_lines,
    update_canvas_metadata,
    validate_canvas_document,
)
from config import (
    AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS,
    AGENT_CONTEXT_COMPACTION_THRESHOLD,
    PROMPT_MAX_INPUT_TOKENS,
    PROMPT_RAG_MAX_TOKENS,
    PROMPT_RECENT_HISTORY_MAX_TOKENS,
    PROMPT_RESPONSE_TOKEN_RESERVE,
    PROMPT_SUMMARY_MAX_TOKENS,
    PROMPT_TOOL_MEMORY_MAX_TOKENS,
    PROMPT_TOOL_TRACE_MAX_TOKENS,
    PRUNING_MIN_TARGET_TOKENS,
    PRUNING_TARGET_REDUCTION_RATIO,
)
from db import (
    append_to_scratchpad,
    build_conversation_assistant_behavior,
    build_persona_preferences,
    count_visible_message_tokens,
    create_file_asset,
    create_image_asset,
    create_video_asset,
    extract_message_usage,
    extract_pending_clarification,
    get_active_tool_names,
    get_all_scratchpad_sections,
    get_app_settings,
    get_conversation_memory,
    get_conversation_messages,
    get_db,
    get_file_asset,
    get_image_asset,
    get_user_profile_entries,
    get_video_asset,
    insert_conversation_memory_entry,
    insert_message,
    insert_model_invocation,
    normalize_active_tool_names,
    parse_message_metadata,
    parse_message_tool_calls,
    read_image_asset_bytes,
    save_app_settings,
    serialize_message_metadata,
    upsert_user_profile_entry,
)
from doc_service import (
    _extract_text_csv,
    _extract_text_from_pdf,
    _format_table_as_markdown,
    _looks_like_real_table,
    _try_extract_borderless_table,
    build_canvas_markdown,
    build_document_context_block,
    build_visual_canvas_markdown,
    extract_document_text,
    infer_canvas_format,
    infer_canvas_language,
    render_pdf_pages_for_vision,
)
from markdown_rendering import _iter_markdown_blocks
from messages import (
    SUMMARY_LABEL,
    build_api_messages,
    build_runtime_context_injection,
    build_runtime_system_message,
    build_tool_call_contract,
    build_user_message_for_model,
    normalize_chat_messages,
    prepend_runtime_context,
)
from project_workspace_service import create_workspace_runtime_state
from proxy_settings import DEFAULT_PROXY_ENABLED_OPERATIONS, PROXY_OPERATION_FETCH_URL
from prune_service import _build_pruning_messages, _estimate_pruning_target_tokens
from rag_service import (
    get_conversation_records_for_rag,
    sync_conversations_to_rag,
)
from routes.auth import AUTH_LAST_SEEN_KEY, AUTH_REMEMBER_KEY, AUTH_SESSION_KEY
from routes.chat import (
    OMITTED_TOOL_OUTPUT_TEXT,
    _cancel_chat_run,
    _build_budgeted_prompt_messages,
    _enrich_rag_query_with_context,
    _build_tool_trace_context,
    _collect_answered_clarification_rounds,
    _count_prunable_message_tokens,
    _estimate_prompt_tokens,
    _get_effective_summary_trigger_token_count,
    _is_failed_tool_summary,
    _persist_streaming_assistant_message,
    _register_chat_run,
    _select_recent_prompt_window,
    _select_summary_source_messages_by_token_budget,
    _unregister_chat_run,
    _validate_clarification_response_against_messages,
    build_summary_prompt_messages,
    preload_dependencies,
)
from routes.pages import build_tool_permission_options, build_tool_permission_sections
from tests.support.app_harness import BaseAppRoutesTestCase
from tests.support.stream_events import build_stream_chunk, build_stream_chunk_openrouter, build_tool_call_chunk
from token_utils import estimate_text_tokens
from tool_registry import TOOL_SPEC_BY_NAME, get_enabled_tool_specs, get_openai_tool_specs, resolve_runtime_tool_names
from web_tools import (
    _extract_html,
    fetch_url_tool,
    get_proxy_candidates_for_operation,
    load_proxies,
    search_news_ddgs_tool,
    search_news_google_tool,
    search_web_tool,
)


class AppRoutesTestCase(BaseAppRoutesTestCase):
    _stream_chunk = staticmethod(build_stream_chunk)
    _stream_chunk_openrouter = staticmethod(build_stream_chunk_openrouter)
    _tool_call_chunk = staticmethod(build_tool_call_chunk)

    def _get_session_csrf_token(self) -> str:
        with self.client.session_transaction() as session_data:
            return str(session_data.get(request_security.CSRF_TOKEN_SESSION_KEY) or "")

    def test_settings_roundtrip(self):
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["general_instructions"], "")
        self.assertEqual(payload["ai_personality"], "")
        self.assertEqual(payload["effective_user_preferences"], "")
        self.assertEqual(payload["personas"], [])
        self.assertIsNone(payload["default_persona_id"])
        self.assertEqual(payload["scratchpad"], "")
        self.assertEqual(payload["max_steps"], 5)
        self.assertEqual(payload["max_parallel_tools"], 4)
        self.assertEqual(payload["clarification_max_questions"], 5)
        self.assertAlmostEqual(payload["temperature"], 0.7)
        self.assertEqual(payload["canvas_prompt_max_lines"], 250)
        self.assertEqual(payload["canvas_prompt_max_tokens"], 4000)
        self.assertEqual(payload["canvas_prompt_max_chars"], 20000)
        self.assertEqual(payload["canvas_prompt_code_line_max_chars"], 180)
        self.assertEqual(payload["canvas_prompt_text_line_max_chars"], 100)
        self.assertEqual(payload["canvas_expand_max_lines"], 1600)
        self.assertEqual(payload["canvas_scroll_window_lines"], 200)
        self.assertEqual(payload["sub_agent_max_steps"], 6)
        self.assertEqual(payload["sub_agent_timeout_seconds"], 240)
        self.assertEqual(payload["sub_agent_retry_attempts"], 2)
        self.assertEqual(payload["sub_agent_retry_delay_seconds"], 5)
        self.assertEqual(payload["sub_agent_max_parallel_tools"], 4)
        self.assertEqual(payload["sub_agent_allowed_tool_names"], SUB_AGENT_ALLOWED_TOOL_NAMES)
        self.assertEqual(payload["web_cache_ttl_hours"], 24)
        self.assertTrue(payload["openrouter_prompt_cache_enabled"])
        self.assertIn("openrouter_http_referer", payload)
        self.assertIn("openrouter_app_title", payload)
        self.assertIn("login_session_timeout_minutes", payload)
        self.assertIn("login_max_failed_attempts", payload)
        self.assertIn("login_lockout_seconds", payload)
        self.assertIn("login_remember_session_days", payload)
        self.assertIn("conversation_memory_enabled", payload)
        self.assertIn("ocr_enabled", payload)
        self.assertIn("ocr_provider", payload)
        self.assertIn("rag_enabled", payload)
        self.assertIn("youtube_transcripts_enabled", payload)
        self.assertIn("youtube_transcript_language", payload)
        self.assertIn("youtube_transcript_model_size", payload)
        self.assertIn("chat_summary_model", payload)
        self.assertIn("rag_chunk_size", payload)
        self.assertIn("rag_chunk_overlap", payload)
        self.assertIn("rag_max_chunks_per_source", payload)
        self.assertIn("rag_search_top_k", payload)
        self.assertIn("rag_search_min_similarity", payload)
        self.assertIn("rag_query_expansion_enabled", payload)
        self.assertIn("rag_query_expansion_max_variants", payload)
        self.assertIn("tool_memory_ttl_default_seconds", payload)
        self.assertIn("tool_memory_ttl_web_seconds", payload)
        self.assertIn("tool_memory_ttl_news_seconds", payload)
        self.assertIn("fetch_raw_max_text_chars", payload)
        self.assertIn("fetch_summary_max_chars", payload)
        self.assertEqual(payload["chat_summary_detail_level"], "balanced")
        self.assertEqual(payload["rag_auto_inject"], bool(payload["features"]["rag_enabled"]))
        self.assertEqual(payload["chat_summary_mode"], "auto")
        self.assertEqual(payload["chat_summary_trigger_token_count"], 80000)
        self.assertEqual(payload["prompt_max_input_tokens"], PROMPT_MAX_INPUT_TOKENS)
        self.assertEqual(payload["prompt_response_token_reserve"], PROMPT_RESPONSE_TOKEN_RESERVE)
        self.assertEqual(payload["prompt_recent_history_max_tokens"], PROMPT_RECENT_HISTORY_MAX_TOKENS)
        self.assertEqual(payload["prompt_summary_max_tokens"], PROMPT_SUMMARY_MAX_TOKENS)
        self.assertEqual(payload["prompt_rag_max_tokens"], PROMPT_RAG_MAX_TOKENS)
        self.assertEqual(payload["prompt_tool_memory_max_tokens"], PROMPT_TOOL_MEMORY_MAX_TOKENS)
        self.assertEqual(payload["prompt_tool_trace_max_tokens"], PROMPT_TOOL_TRACE_MAX_TOKENS)
        self.assertAlmostEqual(payload["context_compaction_threshold"], AGENT_CONTEXT_COMPACTION_THRESHOLD)
        self.assertEqual(payload["context_compaction_keep_recent_rounds"], AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS)
        self.assertEqual(payload["context_selection_strategy"], "classic")
        self.assertEqual(payload["entropy_profile"], "balanced")
        self.assertEqual(payload["entropy_rag_budget_ratio"], 35)
        self.assertTrue(payload["entropy_protect_code_blocks"])
        self.assertTrue(payload["entropy_protect_tool_results"])
        self.assertTrue(payload["entropy_reference_boost"])
        self.assertFalse(payload["reasoning_auto_collapse"])
        self.assertFalse(payload["pruning_enabled"])
        self.assertEqual(payload["pruning_token_threshold"], 80000)
        self.assertEqual(payload["pruning_batch_size"], 10)
        self.assertAlmostEqual(payload["pruning_target_reduction_ratio"], PRUNING_TARGET_REDUCTION_RATIO)
        self.assertEqual(payload["pruning_min_target_tokens"], PRUNING_MIN_TARGET_TOKENS)
        self.assertEqual(payload["fetch_url_token_threshold"], 3500)
        self.assertEqual(payload["fetch_url_clip_aggressiveness"], 50)
        self.assertEqual(payload["fetch_url_summarized_max_input_chars"], 80000)
        self.assertEqual(payload["fetch_url_summarized_max_output_tokens"], 2400)
        self.assertEqual(payload["fetch_url_to_canvas_chunk_threshold"], 20000)
        self.assertEqual(payload["fetch_url_to_canvas_chunk_chars"], 30000)
        self.assertEqual(payload["fetch_url_to_canvas_max_chunks"], 10)
        self.assertEqual(payload["custom_models"], [])
        self.assertEqual(payload["visible_model_order"], ["deepseek-chat", "deepseek-reasoner"])
        self.assertEqual(payload["proxy_enabled_operations"], DEFAULT_PROXY_ENABLED_OPERATIONS)
        self.assertEqual(
            payload["operation_model_preferences"],
            {
                "summarize": "",
                "fetch_summarize": "",
                "prune": "",
                "fix_text": "",
                "generate_title": "",
                "upload_metadata": "",
                "sub_agent": "",
            },
        )
        self.assertEqual(
            payload["operation_model_fallback_preferences"],
            {
                "summarize": [],
                "fetch_summarize": [],
                "prune": [],
                "fix_text": [],
                "generate_title": [],
                "upload_metadata": [],
                "sub_agent": [],
            },
        )
        self.assertEqual(payload["image_processing_method"], "auto")
        self.assertEqual(payload["rag_sensitivity"], "strict")
        self.assertEqual(payload["rag_context_size"], "small")
        self.assertEqual(
            payload["rag_source_types"],
            ["conversation", "tool_result", "tool_memory", "uploaded_document"] if payload["features"]["rag_enabled"] else [],
        )
        self.assertEqual(
            payload["rag_auto_inject_source_types"],
            ["conversation", "tool_result", "tool_memory", "uploaded_document"] if payload["features"]["rag_enabled"] else [],
        )
        self.assertFalse(payload["tool_memory_auto_inject"])

    def test_settings_patch_roundtrips_runtime_managed_fields(self):
        response = self.client.patch(
            "/api/settings",
            json={
                "openrouter_http_referer": "https://example.com/runtime",
                "openrouter_app_title": "Runtime Settings Test",
                "login_session_timeout_minutes": 45,
                "login_max_failed_attempts": 7,
                "login_lockout_seconds": 900,
                "login_remember_session_days": 120,
                "conversation_memory_enabled": False,
                "ocr_enabled": False,
                "ocr_provider": "easyocr",
                "rag_enabled": True,
                "youtube_transcripts_enabled": True,
                "youtube_transcript_language": "tr",
                "youtube_transcript_model_size": "medium",
                "chat_summary_model": "deepseek-reasoner",
                "rag_chunk_size": 2200,
                "rag_chunk_overlap": 300,
                "rag_max_chunks_per_source": 3,
                "rag_search_top_k": 6,
                "rag_search_min_similarity": 0.42,
                "rag_query_expansion_enabled": False,
                "rag_query_expansion_max_variants": 4,
                "tool_memory_ttl_default_seconds": 650000,
                "tool_memory_ttl_web_seconds": 50000,
                "tool_memory_ttl_news_seconds": 9000,
                "fetch_raw_max_text_chars": 26000,
                "fetch_summary_max_chars": 8500,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["openrouter_http_referer"], "https://example.com/runtime")
        self.assertEqual(payload["openrouter_app_title"], "Runtime Settings Test")
        self.assertEqual(payload["login_session_timeout_minutes"], 45)
        self.assertEqual(payload["login_max_failed_attempts"], 7)
        self.assertEqual(payload["login_lockout_seconds"], 900)
        self.assertEqual(payload["login_remember_session_days"], 120)
        self.assertFalse(payload["conversation_memory_enabled"])
        self.assertFalse(payload["ocr_enabled"])
        self.assertEqual(payload["ocr_provider"], "easyocr")
        self.assertTrue(payload["rag_enabled"])
        self.assertTrue(payload["youtube_transcripts_enabled"])
        self.assertEqual(payload["youtube_transcript_language"], "tr")
        self.assertEqual(payload["youtube_transcript_model_size"], "medium")
        self.assertEqual(payload["chat_summary_model"], "deepseek-reasoner")
        self.assertEqual(payload["rag_chunk_size"], 2200)
        self.assertEqual(payload["rag_chunk_overlap"], 300)
        self.assertEqual(payload["rag_max_chunks_per_source"], 3)
        self.assertEqual(payload["rag_search_top_k"], 6)
        self.assertAlmostEqual(payload["rag_search_min_similarity"], 0.42)
        self.assertFalse(payload["rag_query_expansion_enabled"])
        self.assertEqual(payload["rag_query_expansion_max_variants"], 4)
        self.assertEqual(payload["tool_memory_ttl_default_seconds"], 650000)
        self.assertEqual(payload["tool_memory_ttl_web_seconds"], 50000)
        self.assertEqual(payload["tool_memory_ttl_news_seconds"], 9000)
        self.assertEqual(payload["fetch_raw_max_text_chars"], 26000)
        self.assertEqual(payload["fetch_summary_max_chars"], 8500)
        self.assertEqual(payload["image_helper_model"], "")
        self.assertIn("features", payload)
        self.assertIn("rag_enabled", payload["features"])
        self.assertIn("ocr_enabled", payload["features"])
        self.assertIn("image_uploads_enabled", payload["features"])
        self.assertIsInstance(payload["features"]["rag_enabled"], bool)
        self.assertIsInstance(payload["features"]["ocr_enabled"], bool)
        self.assertIsInstance(payload["features"]["image_uploads_enabled"], bool)

        response = self.client.patch(
            "/api/settings",
            json={
                "general_instructions": "Keep answers short.",
                "ai_personality": "Sound like a pragmatic senior engineer.",
                "max_steps": 3,
                "max_parallel_tools": 6,
                "temperature": 1.1,
                "clarification_max_questions": 4,
                "chat_summary_mode": "aggressive",
                "chat_summary_detail_level": "detailed",
                "chat_summary_trigger_token_count": 9000,
                "prompt_max_input_tokens": 90000,
                "prompt_response_token_reserve": 10000,
                "prompt_recent_history_max_tokens": 28000,
                "prompt_summary_max_tokens": 14000,
                "prompt_rag_max_tokens": 16000,
                "prompt_tool_memory_max_tokens": 8000,
                "prompt_tool_trace_max_tokens": 7000,
                "context_compaction_threshold": 0.9,
                "context_compaction_keep_recent_rounds": 3,
                "context_selection_strategy": "entropy_rag_hybrid",
                "entropy_profile": "aggressive",
                "entropy_rag_budget_ratio": 55,
                "entropy_protect_code_blocks": True,
                "entropy_protect_tool_results": False,
                "entropy_reference_boost": True,
                "reasoning_auto_collapse": True,
                "pruning_enabled": True,
                "pruning_token_threshold": 12000,
                "pruning_batch_size": 4,
                "pruning_target_reduction_ratio": 0.5,
                "pruning_min_target_tokens": 220,
                "fetch_url_token_threshold": 4200,
                "fetch_url_clip_aggressiveness": 70,
                "fetch_url_summarized_max_input_chars": 62000,
                "fetch_url_summarized_max_output_tokens": 3100,
                "fetch_url_to_canvas_chunk_threshold": 18000,
                "fetch_url_to_canvas_chunk_chars": 24000,
                "fetch_url_to_canvas_max_chunks": 7,
                "canvas_prompt_max_lines": 1200,
                "canvas_prompt_max_tokens": 3200,
                "canvas_prompt_max_chars": 36000,
                "canvas_prompt_code_line_max_chars": 240,
                "canvas_prompt_text_line_max_chars": 140,
                "canvas_expand_max_lines": 2200,
                "canvas_scroll_window_lines": 150,
                "sub_agent_max_steps": 9,
                "sub_agent_timeout_seconds": 300,
                "sub_agent_retry_attempts": 3,
                "sub_agent_retry_delay_seconds": 7,
                "sub_agent_max_parallel_tools": 5,
                "sub_agent_allowed_tool_names": ["search_web", "fetch_url_summarized"],
                "web_cache_ttl_hours": 12,
                "openrouter_prompt_cache_enabled": False,
                "custom_models": [
                    {
                        "name": "Claude Sonnet 4.5",
                        "api_model": "anthropic/claude-sonnet-4.5",
                        "provider_slug": "deepinfra/turbo",
                        "reasoning_mode": "enabled",
                        "reasoning_effort": "high",
                        "supports_tools": True,
                        "supports_vision": True,
                        "supports_structured_outputs": True,
                    }
                ],
                "visible_model_order": ["openrouter:anthropic/claude-sonnet-4.5", "deepseek-chat"],
                "operation_model_preferences": {
                    "summarize": "openrouter:anthropic/claude-sonnet-4.5",
                    "fetch_summarize": "deepseek-chat",
                    "prune": "deepseek-chat",
                    "fix_text": "deepseek-chat",
                    "generate_title": "openrouter:anthropic/claude-sonnet-4.5",
                    "upload_metadata": "openrouter:anthropic/claude-sonnet-4.5",
                    "sub_agent": "deepseek-reasoner",
                },
                "operation_model_fallback_preferences": {
                    "summarize": ["deepseek-reasoner", "deepseek-chat"],
                    "fetch_summarize": ["deepseek-reasoner"],
                    "prune": ["deepseek-reasoner"],
                    "fix_text": ["deepseek-reasoner"],
                    "generate_title": ["deepseek-reasoner"],
                    "upload_metadata": ["deepseek-reasoner"],
                    "sub_agent": ["deepseek-chat", "deepseek-reasoner"],
                },
                "image_processing_method": "llm_helper",
                "image_helper_model": "openrouter:anthropic/claude-sonnet-4.5",
                "active_tools": ["fetch_url", "search_web"],
                "proxy_enabled_operations": ["openrouter", "fetch_url"],
                "rag_auto_inject": False,
                "rag_sensitivity": "strict",
                "rag_context_size": "large",
                "rag_source_types": ["tool_memory", "uploaded_document"],
                "rag_auto_inject_source_types": ["uploaded_document"],
                "tool_memory_auto_inject": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["user_preferences"], "Keep answers short.")
        self.assertEqual(payload["general_instructions"], "Keep answers short.")
        self.assertEqual(payload["ai_personality"], "Sound like a pragmatic senior engineer.")
        self.assertEqual(len(payload["personas"]), 1)
        self.assertEqual(payload["personas"][0]["name"], "Default")
        self.assertIsInstance(payload["default_persona_id"], int)
        self.assertEqual(payload["personas"][0]["id"], payload["default_persona_id"])
        self.assertEqual(payload["personas"][0]["general_instructions"], "Keep answers short.")
        self.assertEqual(payload["personas"][0]["ai_personality"], "Sound like a pragmatic senior engineer.")
        self.assertIn("General instructions:\nKeep answers short.", payload["effective_user_preferences"])
        self.assertIn("AI personality:\nSound like a pragmatic senior engineer.", payload["effective_user_preferences"])
        self.assertEqual(payload["scratchpad"], "")
        self.assertEqual(payload["max_steps"], 3)
        self.assertEqual(payload["max_parallel_tools"], 6)
        self.assertEqual(payload["clarification_max_questions"], 4)
        self.assertAlmostEqual(payload["temperature"], 1.1)
        self.assertEqual(payload["chat_summary_mode"], "aggressive")
        self.assertEqual(payload["chat_summary_detail_level"], "detailed")
        self.assertEqual(payload["chat_summary_trigger_token_count"], 9000)
        self.assertEqual(payload["prompt_max_input_tokens"], 90000)
        self.assertEqual(payload["prompt_response_token_reserve"], 10000)
        self.assertEqual(payload["prompt_recent_history_max_tokens"], 28000)
        self.assertEqual(payload["prompt_summary_max_tokens"], 14000)
        self.assertEqual(payload["prompt_rag_max_tokens"], 16000)
        self.assertEqual(payload["prompt_tool_memory_max_tokens"], 8000)
        self.assertEqual(payload["prompt_tool_trace_max_tokens"], 7000)
        self.assertAlmostEqual(payload["context_compaction_threshold"], 0.9)
        self.assertEqual(payload["context_compaction_keep_recent_rounds"], 3)
        self.assertEqual(payload["context_selection_strategy"], "entropy_rag_hybrid")
        self.assertEqual(payload["entropy_profile"], "aggressive")
        self.assertEqual(payload["entropy_rag_budget_ratio"], 55)
        self.assertTrue(payload["entropy_protect_code_blocks"])
        self.assertFalse(payload["entropy_protect_tool_results"])
        self.assertTrue(payload["entropy_reference_boost"])
        self.assertTrue(payload["reasoning_auto_collapse"])
        self.assertTrue(payload["pruning_enabled"])
        self.assertEqual(payload["pruning_token_threshold"], 12000)
        self.assertEqual(payload["pruning_batch_size"], 4)
        self.assertAlmostEqual(payload["pruning_target_reduction_ratio"], 0.5)
        self.assertEqual(payload["pruning_min_target_tokens"], 220)
        self.assertEqual(payload["fetch_url_token_threshold"], 4200)
        self.assertEqual(payload["fetch_url_clip_aggressiveness"], 70)
        self.assertEqual(payload["fetch_url_summarized_max_input_chars"], 62000)
        self.assertEqual(payload["fetch_url_summarized_max_output_tokens"], 3100)
        self.assertEqual(payload["fetch_url_to_canvas_chunk_threshold"], 18000)
        self.assertEqual(payload["fetch_url_to_canvas_chunk_chars"], 24000)
        self.assertEqual(payload["fetch_url_to_canvas_max_chunks"], 7)
        self.assertEqual(payload["canvas_prompt_max_lines"], 1200)
        self.assertEqual(payload["canvas_prompt_max_tokens"], 3200)
        self.assertEqual(payload["canvas_prompt_max_chars"], 36000)
        self.assertEqual(payload["canvas_prompt_code_line_max_chars"], 240)
        self.assertEqual(payload["canvas_prompt_text_line_max_chars"], 140)
        self.assertEqual(payload["canvas_expand_max_lines"], 2200)
        self.assertEqual(payload["canvas_scroll_window_lines"], 150)
        self.assertEqual(payload["sub_agent_max_steps"], 9)
        self.assertEqual(payload["sub_agent_timeout_seconds"], 300)
        self.assertEqual(payload["sub_agent_retry_attempts"], 3)
        self.assertEqual(payload["sub_agent_retry_delay_seconds"], 7)
        self.assertEqual(payload["sub_agent_max_parallel_tools"], 5)
        self.assertEqual(payload["sub_agent_allowed_tool_names"], ["search_web", "fetch_url_summarized"])
        self.assertEqual(payload["web_cache_ttl_hours"], 12)
        self.assertFalse(payload["openrouter_prompt_cache_enabled"])
        self.assertEqual(
            payload["custom_models"][0]["id"],
            "openrouter:anthropic/claude-sonnet-4.5@@r=enabled:high;p=deepinfra/turbo;v=1;s=1",
        )
        self.assertEqual(payload["custom_models"][0]["provider_slug"], "deepinfra/turbo")
        self.assertEqual(payload["custom_models"][0]["reasoning_mode"], "enabled")
        self.assertEqual(payload["custom_models"][0]["reasoning_effort"], "high")
        self.assertEqual(
            payload["visible_model_order"],
            ["openrouter:anthropic/claude-sonnet-4.5@@r=enabled:high;p=deepinfra/turbo;v=1;s=1", "deepseek-chat"],
        )
        self.assertEqual(
            payload["operation_model_preferences"]["summarize"],
            "openrouter:anthropic/claude-sonnet-4.5@@r=enabled:high;p=deepinfra/turbo;v=1;s=1",
        )
        self.assertEqual(payload["operation_model_preferences"]["fetch_summarize"], "deepseek-chat")
        self.assertEqual(payload["operation_model_preferences"]["sub_agent"], "deepseek-reasoner")
        self.assertEqual(payload["operation_model_fallback_preferences"]["summarize"], ["deepseek-reasoner", "deepseek-chat"])
        self.assertEqual(payload["operation_model_fallback_preferences"]["fetch_summarize"], ["deepseek-reasoner"])
        self.assertEqual(payload["operation_model_fallback_preferences"]["sub_agent"], ["deepseek-chat", "deepseek-reasoner"])
        self.assertEqual(payload["image_processing_method"], "llm_helper")
        self.assertEqual(payload["image_helper_model"], "openrouter:anthropic/claude-sonnet-4.5")
        self.assertTrue(
            any(
                model["id"] == "openrouter:anthropic/claude-sonnet-4.5@@r=enabled:high;p=deepinfra/turbo;v=1;s=1"
                for model in payload["available_models"]
            )
        )
        self.assertEqual(payload["active_tools"], ["fetch_url", "search_web"])
        self.assertEqual(payload["proxy_enabled_operations"], ["openrouter", "fetch_url"])
        self.assertFalse(payload["rag_auto_inject"])
        self.assertEqual(payload["rag_sensitivity"], "strict")
        self.assertEqual(payload["rag_context_size"], "large")
        self.assertEqual(
            payload["rag_source_types"],
            ["tool_memory", "uploaded_document"] if payload["features"]["rag_enabled"] else [],
        )
        self.assertEqual(
            payload["rag_auto_inject_source_types"],
            ["uploaded_document"] if payload["features"]["rag_enabled"] else [],
        )
        self.assertFalse(payload["tool_memory_auto_inject"])

    def test_settings_page_mentions_ignored_canvas_documents(self):
        response = self.client.get("/settings")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Ignored Canvas documents stay available for later reuse",
            response.get_data(as_text=True),
        )

    def test_settings_accepts_extended_summary_options(self):
        response = self.client.patch(
            "/api/settings",
            json={
                "chat_summary_mode": "conservative",
                "chat_summary_detail_level": "comprehensive",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["chat_summary_mode"], "conservative")
        self.assertEqual(payload["chat_summary_detail_level"], "comprehensive")

    def test_settings_reject_invalid_context_selection_strategy(self):
        response = self.client.patch(
            "/api/settings",
            json={"context_selection_strategy": "quantum"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("context_selection_strategy", response.get_json()["error"])

    def test_conservative_summary_mode_uses_rounded_up_threshold(self):
        self.assertEqual(
            _get_effective_summary_trigger_token_count(
                {
                    "chat_summary_mode": "conservative",
                    "chat_summary_trigger_token_count": "1001",
                }
            ),
            1502,
        )

    def test_settings_patch_rejects_invalid_proxy_operations(self):
        response = self.client.patch(
            "/api/settings",
            json={"proxy_enabled_operations": ["openrouter", "invalid_proxy_scope"]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("proxy_enabled_operations", response.get_json()["error"])

    def test_settings_patch_ignores_unknown_operation_model_keys(self):
        response = self.client.patch(
            "/api/settings",
            json={
                "operation_model_preferences": {
                    "summarize": "deepseek-chat",
                    "legacy_unused": "deepseek-reasoner",
                },
                "operation_model_fallback_preferences": {
                    "sub_agent": ["deepseek-chat"],
                    "legacy_unused": ["deepseek-reasoner"],
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["operation_model_preferences"]["summarize"], "deepseek-chat")
        self.assertNotIn("legacy_unused", payload["operation_model_preferences"])
        self.assertEqual(payload["operation_model_fallback_preferences"]["sub_agent"], ["deepseek-chat"])
        self.assertNotIn("legacy_unused", payload["operation_model_fallback_preferences"])

    def test_persona_crud_and_conversation_persona_override(self):
        response = self.client.post(
            "/api/personas",
            json={
                "name": "Analyst",
                "general_instructions": "Focus on evidence.",
                "ai_personality": "Sound analytical.",
            },
        )
        self.assertEqual(response.status_code, 201)
        analyst_persona = response.get_json()["persona"]

        response = self.client.post(
            "/api/personas",
            json={
                "name": "Teacher",
                "general_instructions": "Explain step by step.",
                "ai_personality": "Sound patient.",
            },
        )
        self.assertEqual(response.status_code, 201)
        teacher_persona = response.get_json()["persona"]

        response = self.client.patch(
            "/api/settings",
            json={"default_persona_id": analyst_persona["id"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["default_persona_id"], analyst_persona["id"])

        response = self.client.post(
            "/api/conversations",
            json={"title": "Persona Chat", "model": "deepseek-chat"},
        )
        self.assertEqual(response.status_code, 201)
        conversation_payload = response.get_json()
        conversation_id = conversation_payload["id"]
        self.assertIsNone(conversation_payload["persona_id"])

        self.assertEqual(
            build_conversation_assistant_behavior(conversation_id, get_app_settings()),
            build_persona_preferences(analyst_persona),
        )

        response = self.client.patch(
            f"/api/conversations/{conversation_id}",
            json={"persona_id": teacher_persona["id"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["persona_id"], teacher_persona["id"])

        response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["conversation"]["persona"]["id"], teacher_persona["id"])

        self.assertEqual(
            build_conversation_assistant_behavior(conversation_id, get_app_settings()),
            build_persona_preferences(teacher_persona),
        )

        response = self.client.delete(f"/api/personas/{teacher_persona['id']}")
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["conversation"]["persona"])

        self.assertEqual(
            build_conversation_assistant_behavior(conversation_id, get_app_settings()),
            build_persona_preferences(analyst_persona),
        )

    def test_delete_conversation_message_soft_deletes_it_and_returns_filtered_history(self):
        conversation_id = self._create_conversation()
        with get_db() as conn:
            user_message_id = insert_message(conn, conversation_id, "user", "Delete me")
            assistant_message_id = insert_message(conn, conversation_id, "assistant", "Keep me")

        with patch("routes.conversations.sync_conversations_to_rag_safe") as mocked_sync:
            response = self.client.delete(
                f"/api/messages/{user_message_id}",
                json={"conversation_id": conversation_id},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["deleted"])
        self.assertEqual(payload["message_id"], user_message_id)
        self.assertEqual(payload["conversation_id"], conversation_id)
        self.assertEqual(payload["deleted_message_ids"], [user_message_id, assistant_message_id])
        self.assertEqual(payload["messages"], [])
        self.assertEqual(get_conversation_messages(conversation_id), [])
        mocked_sync.assert_called_once_with(conversation_id=conversation_id, force=True)

    def test_delete_conversation_message_rolls_back_branch_mutations_and_workspace(self):
        conversation_id = self._create_conversation()
        workspace_root = os.path.join(self.temp_dir.name, "delete-branch-workspace")
        os.makedirs(workspace_root, exist_ok=True)
        workspace_file = os.path.join(workspace_root, "state.txt")

        with get_db() as conn:
            first_user_id = insert_message(conn, conversation_id, "user", "First prompt")
            first_assistant_id = insert_message(conn, conversation_id, "assistant", "First answer")
            deleted_user_id = insert_message(conn, conversation_id, "user", "Delete this branch")
            later_assistant_id = insert_message(conn, conversation_id, "assistant", "Later branch answer")

        with patch(
            "conversation_cleanup_service.create_workspace_runtime_state",
            side_effect=lambda conversation_id=None, root_path=None: create_workspace_runtime_state(root_path=workspace_root),
        ), patch("routes.conversations.sync_conversations_to_rag_safe") as mocked_sync:
            with open(workspace_file, "w", encoding="utf-8") as fh:
                fh.write("baseline workspace")
            capture_workspace_snapshot_for_assistant_message(
                conversation_id,
                first_assistant_id,
                source_message_id=first_user_id,
            )

            with open(workspace_file, "w", encoding="utf-8") as fh:
                fh.write("later workspace")

            append_to_scratchpad(
                "Later branch scratchpad",
                conversation_id=conversation_id,
                source_message_id=later_assistant_id,
            )
            upsert_user_profile_entry(
                "fact:branch-delete",
                "later profile",
                confidence=0.7,
                source="test",
                conversation_id=conversation_id,
                source_message_id=later_assistant_id,
            )
            insert_conversation_memory_entry(
                conversation_id,
                "task_context",
                "branch-memory",
                "later memory",
                message_id=later_assistant_id,
                mutation_context={"source_message_id": later_assistant_id},
            )

            response = self.client.delete(
                f"/api/messages/{deleted_user_id}",
                json={"conversation_id": conversation_id},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["deleted_message_ids"], [deleted_user_id, later_assistant_id])
        self.assertEqual([message["id"] for message in payload["messages"]], [first_user_id, first_assistant_id])
        self.assertEqual([message["id"] for message in get_conversation_messages(conversation_id)], [first_user_id, first_assistant_id])

        scratchpad_sections = get_all_scratchpad_sections(get_app_settings())
        self.assertNotIn("Later branch scratchpad", scratchpad_sections.get("notes", ""))
        self.assertNotIn("fact:branch-delete", {entry["key"] for entry in get_user_profile_entries()})
        self.assertEqual(get_conversation_memory(conversation_id), [])

        with open(workspace_file, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "baseline workspace")

        mocked_sync.assert_called_once_with(conversation_id=conversation_id, force=True)

    def test_create_conversation_accepts_custom_openrouter_model(self):
        response = self.client.patch(
            "/api/settings",
            json={
                "custom_models": [
                    {
                        "name": "Claude Sonnet 4.5",
                        "api_model": "anthropic/claude-sonnet-4.5",
                        "supports_tools": True,
                        "supports_vision": True,
                        "supports_structured_outputs": True,
                    }
                ],
                "visible_model_order": ["openrouter:anthropic/claude-sonnet-4.5", "deepseek-chat"],
            },
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/api/conversations",
            json={"title": "OR Chat", "model": "openrouter:anthropic/claude-sonnet-4.5"},
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["title"], "OR Chat")
        self.assertEqual(payload["model"], "openrouter:anthropic/claude-sonnet-4.5")
        self.assertEqual(payload["model_label"], "Claude Sonnet 4.5")

        conversation_response = self.client.get(f"/api/conversations/{payload['id']}")
        self.assertEqual(conversation_response.status_code, 200)
        self.assertEqual(
            conversation_response.get_json()["conversation"]["model_label"],
            "Claude Sonnet 4.5",
        )

    def test_conversation_payload_includes_memory_entries(self):
        conversation_id = self._create_conversation()
        insert_conversation_memory_entry(
            conversation_id,
            "decision",
            "API",
            "Flask will be used.",
        )

        response = self.client.get(f"/api/conversations/{conversation_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["conversation_memory_enabled"])
        self.assertEqual(payload["memory_count"], 1)
        self.assertEqual(payload["memory"][0]["entry_type"], "decision")
        self.assertEqual(payload["memory"][0]["key"], "API")

    def test_conversation_memory_crud_routes_update_list(self):
        conversation_id = self._create_conversation()

        create_response = self.client.post(
            f"/api/conversations/{conversation_id}/memory",
            json={
                "entry_type": "user_info",
                "key": "Preferred language",
                "value": "Turkish",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        create_payload = create_response.get_json()
        entry = create_payload["entry"]
        self.assertEqual(create_payload["memory_count"], 1)
        self.assertEqual(create_payload["memory"][0]["key"], "Preferred language")

        update_response = self.client.patch(
            f"/api/conversations/{conversation_id}/memory/{entry['id']}",
            json={
                "entry_type": "decision",
                "key": "Preferred locale",
                "value": "Turkish",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        update_payload = update_response.get_json()
        self.assertEqual(update_payload["entry"]["entry_type"], "decision")
        self.assertEqual(update_payload["entry"]["key"], "Preferred locale")
        self.assertEqual(update_payload["memory"][0]["key"], "Preferred locale")

        delete_response = self.client.delete(f"/api/conversations/{conversation_id}/memory/{entry['id']}")
        self.assertEqual(delete_response.status_code, 200)
        delete_payload = delete_response.get_json()
        self.assertEqual(delete_payload["memory_count"], 0)
        self.assertEqual(get_conversation_memory(conversation_id), [])

    def test_get_conversation_memory_returns_latest_window_in_chronological_order(self):
        conversation_id = self._create_conversation()

        for index in range(45):
            insert_conversation_memory_entry(
                conversation_id,
                "task_context",
                f"Entry {index:02d}",
                f"Value {index:02d}",
            )

        entries = get_conversation_memory(conversation_id)

        self.assertEqual(len(entries), 40)
        self.assertEqual(entries[0]["key"], "Entry 05")
        self.assertEqual(entries[-1]["key"], "Entry 44")
        self.assertEqual(
            [entry["key"] for entry in entries[:3]],
            ["Entry 05", "Entry 06", "Entry 07"],
        )

    def test_rag_query_enrichment_uses_task_context_and_decision_entries(self):
        enriched = _enrich_rag_query_with_context(
            "Fix the bug",
            [
                {
                    "entry_type": "user_info",
                    "key": "Locale",
                    "value": "Turkish",
                    "created_at": "2026-04-08 10:00:00",
                },
                {
                    "entry_type": "task_context",
                    "key": "Goal",
                    "value": "Repair the RAG memory flow",
                    "created_at": "2026-04-08 10:01:00",
                },
                {
                    "entry_type": "decision",
                    "key": "Constraint",
                    "value": "Keep the schema unchanged",
                    "created_at": "2026-04-08 10:02:00",
                },
            ],
            [],
        )

        self.assertIn("Goal: Repair the RAG memory flow", enriched)
        self.assertIn("Constraint: Keep the schema unchanged", enriched)
        self.assertNotIn("Locale: Turkish", enriched)
        self.assertTrue(enriched.endswith("Fix the bug"))

    def test_custom_openrouter_models_can_share_the_same_base_model_id_with_different_profiles(self):
        response = self.client.patch(
            "/api/settings",
            json={
                "custom_models": [
                    {
                        "name": "Gemini Flash",
                        "api_model": "google/gemini-3-flash-preview",
                        "reasoning_mode": "disabled",
                        "supports_tools": True,
                        "supports_vision": False,
                        "supports_structured_outputs": False,
                    },
                    {
                        "name": "Gemini Flash Thinking",
                        "api_model": "google/gemini-3-flash-preview",
                        "reasoning_mode": "enabled",
                        "reasoning_effort": "xhigh",
                        "supports_tools": True,
                        "supports_vision": False,
                        "supports_structured_outputs": False,
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        custom_models = payload["custom_models"]
        self.assertEqual(len(custom_models), 2)
        self.assertNotEqual(custom_models[0]["id"], custom_models[1]["id"])
        self.assertTrue(custom_models[0]["id"].startswith("openrouter:google/gemini-3-flash-preview"))
        self.assertTrue(custom_models[1]["id"].startswith("openrouter:google/gemini-3-flash-preview"))
        self.assertIn("@@r=disabled", custom_models[0]["id"])
        self.assertIn("@@r=enabled:xhigh", custom_models[1]["id"])

    def test_settings_patch_rejects_invalid_rag_presets(self):
        response = self.client.patch(
            "/api/settings",
            json={"rag_sensitivity": "aggressive"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rag_sensitivity", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"rag_context_size": "huge"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rag_context_size", response.get_json()["error"])

    def test_settings_patch_rejects_invalid_rag_source_types(self):
        response = self.client.patch(
            "/api/settings",
            json={"rag_source_types": "conversation"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rag_source_types", response.get_json()["error"])

    def test_settings_patch_rejects_invalid_rag_auto_inject_source_types(self):
        response = self.client.patch(
            "/api/settings",
            json={"rag_auto_inject_source_types": "conversation"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rag_auto_inject_source_types", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"rag_auto_inject_source_types": ["conversation", "invalid_source"]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rag_auto_inject_source_types", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"rag_source_types": ["conversation", "invalid_source"]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rag_source_types", response.get_json()["error"])

    def test_settings_patch_keeps_auto_inject_sources_independent_of_searchable_sources(self):
        response = self.client.patch(
            "/api/settings",
            json={
                "rag_source_types": ["conversation"],
                "rag_auto_inject_source_types": ["uploaded_document"],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["rag_source_types"], ["conversation"])
        self.assertEqual(payload["rag_auto_inject_source_types"], ["uploaded_document"])

    def test_settings_patch_rejects_invalid_pruning_values(self):
        response = self.client.patch(
            "/api/settings",
            json={"pruning_token_threshold": 999},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("pruning_token_threshold", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"pruning_batch_size": 0},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("pruning_batch_size", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"pruning_target_reduction_ratio": 0.05},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("pruning_target_reduction_ratio", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"pruning_min_target_tokens": 10},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("pruning_min_target_tokens", response.get_json()["error"])

    def test_settings_patch_rejects_invalid_prompt_budget_relationships(self):
        response = self.client.patch(
            "/api/settings",
            json={
                "prompt_max_input_tokens": 10000,
                "prompt_response_token_reserve": 8500,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("prompt_response_token_reserve", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={
                "prompt_max_input_tokens": 12000,
                "prompt_recent_history_max_tokens": 13000,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("prompt_recent_history_max_tokens", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"context_compaction_threshold": 0.49},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("context_compaction_threshold", response.get_json()["error"])

    def test_settings_patch_rejects_invalid_canvas_values(self):
        response = self.client.patch(
            "/api/settings",
            json={"canvas_prompt_max_lines": 99},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("canvas_prompt_max_lines", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"canvas_expand_max_lines": 5000},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("canvas_expand_max_lines", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"canvas_scroll_window_lines": 49},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("canvas_scroll_window_lines", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"canvas_prompt_max_chars": 999},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("canvas_prompt_max_chars", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"canvas_prompt_code_line_max_chars": 39},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("canvas_prompt_code_line_max_chars", response.get_json()["error"])

        response = self.client.patch(
            "/api/settings",
            json={"canvas_prompt_text_line_max_chars": 1001},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("canvas_prompt_text_line_max_chars", response.get_json()["error"])

    def test_login_pin_protects_page_and_api_routes(self):
        with patch("config.LOGIN_PIN", "2468"):
            response = self.client.get("/login")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Enter PIN", response.get_data(as_text=True))

            response = self.client.get("/")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])

            response = self.client.get("/api/settings")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.get_json()["error"], "Login PIN required.")

            response = self.client.post("/login", data={"pin": "0000"})
            self.assertEqual(response.status_code, 401)
            self.assertIn("Invalid PIN.", response.get_data(as_text=True))

            response = self.client.post("/login", data={"pin": "2468"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], "/")

            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)

    def test_api_mutations_require_csrf_token_outside_testing_even_with_werkzeug_user_agent(self):
        previous_testing = self.app.config.get("TESTING", False)
        self.app.config["TESTING"] = False
        try:
            self.client.get("/")
            csrf_token = self._get_session_csrf_token()
            self.assertTrue(csrf_token)

            response = self.client.post(
                "/api/conversations",
                json={"title": "Blocked", "model": "deepseek-chat"},
                headers={"User-Agent": "Werkzeug/3.1.0"},
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.get_json()["error"], "Security check failed. Refresh the page and try again.")

            response = self.client.post(
                "/api/conversations",
                json={"title": "Allowed", "model": "deepseek-chat"},
                headers={
                    "User-Agent": "Werkzeug/3.1.0",
                    "X-CSRF-Token": csrf_token,
                },
            )
            self.assertEqual(response.status_code, 201)
        finally:
            self.app.config["TESTING"] = previous_testing

    def test_login_requires_csrf_token_outside_testing(self):
        with patch("config.LOGIN_PIN", "2468"):
            previous_testing = self.app.config.get("TESTING", False)
            self.app.config["TESTING"] = False
            try:
                response = self.client.get("/login")
                self.assertEqual(response.status_code, 200)
                self.assertIn('name="csrf_token"', response.get_data(as_text=True))

                csrf_token = self._get_session_csrf_token()
                self.assertTrue(csrf_token)

                response = self.client.post("/login", data={"pin": "2468"})
                self.assertEqual(response.status_code, 403)

                response = self.client.post(
                    "/login",
                    data={"pin": "2468", "csrf_token": csrf_token},
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], "/")
            finally:
                self.app.config["TESTING"] = previous_testing

    def test_logout_requires_csrf_token_outside_testing(self):
        previous_testing = self.app.config.get("TESTING", False)
        self.app.config["TESTING"] = False
        try:
            self.client.get("/")
            csrf_token = self._get_session_csrf_token()
            self.assertTrue(csrf_token)

            response = self.client.post("/logout")
            self.assertEqual(response.status_code, 403)

            response = self.client.post("/logout", data={"csrf_token": csrf_token})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], "/")
        finally:
            self.app.config["TESTING"] = previous_testing

    def test_rate_limit_ignores_spoofed_x_forwarded_for_header(self):
        previous_testing = self.app.config.get("TESTING", False)
        previous_request_count = request_security._RATE_LIMIT_REQUEST_COUNT
        self.app.config["TESTING"] = False
        request_security._RATE_LIMIT_STATE.clear()
        request_security._RATE_LIMIT_REQUEST_COUNT = 0
        try:
            self.client.get("/")
            csrf_token = self._get_session_csrf_token()
            self.assertTrue(csrf_token)

            with patch("request_security._get_rate_limit_rule", return_value=("api-write", 1, 60)):
                response = self.client.post(
                    "/api/conversations",
                    json={"title": "First", "model": "deepseek-chat"},
                    headers={
                        "X-CSRF-Token": csrf_token,
                        "X-Forwarded-For": "1.1.1.1",
                    },
                )
                self.assertEqual(response.status_code, 201)

                response = self.client.post(
                    "/api/conversations",
                    json={"title": "Second", "model": "deepseek-chat"},
                    headers={
                        "X-CSRF-Token": csrf_token,
                        "X-Forwarded-For": "2.2.2.2",
                    },
                )
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.get_json()["error"], "Too many requests. Please try again shortly.")
                self.assertGreaterEqual(int(response.headers["Retry-After"]), 1)
                self.assertLessEqual(int(response.headers["Retry-After"]), 60)
        finally:
            request_security._RATE_LIMIT_STATE.clear()
            request_security._RATE_LIMIT_REQUEST_COUNT = previous_request_count
            self.app.config["TESTING"] = previous_testing

    def test_pages_render_html_lang_from_accept_language(self):
        headers = {"Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"}

        response = self.client.get("/", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn('<html lang="tr">', response.get_data(as_text=True))

        response = self.client.get("/settings", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn('<html lang="tr">', response.get_data(as_text=True))

    def test_login_page_renders_html_lang_from_accept_language(self):
        with patch("config.LOGIN_PIN", "2468"):
            response = self.client.get(
                "/login",
                headers={"Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('<html lang="tr">', response.get_data(as_text=True))

    def test_login_pin_times_out_without_remember(self):
        with patch("config.LOGIN_PIN", "2468"), patch("config.LOGIN_SESSION_TIMEOUT_MINUTES", 1):
            response = self.client.post("/login", data={"pin": "2468"})
            self.assertEqual(response.status_code, 302)

            with self.client.session_transaction() as session_data:
                session_data[AUTH_SESSION_KEY] = True
                session_data[AUTH_REMEMBER_KEY] = False
                session_data[AUTH_LAST_SEEN_KEY] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

            response = self.client.get("/settings")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])

    def test_login_pin_remember_me_skips_timeout(self):
        with patch("config.LOGIN_PIN", "2468"), patch("config.LOGIN_SESSION_TIMEOUT_MINUTES", 1):
            response = self.client.post("/login", data={"pin": "2468", "remember": "on"})
            self.assertEqual(response.status_code, 302)

            with self.client.session_transaction() as session_data:
                session_data[AUTH_SESSION_KEY] = True
                session_data[AUTH_REMEMBER_KEY] = True
                session_data[AUTH_LAST_SEEN_KEY] = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

            response = self.client.get("/settings")
            self.assertEqual(response.status_code, 200)

    def test_login_pin_locks_out_after_failed_attempts(self):
        with patch("config.LOGIN_PIN", "2468"), patch("config.LOGIN_MAX_FAILED_ATTEMPTS", 2), patch(
            "config.LOGIN_LOCKOUT_SECONDS", 60
        ):
            response = self.client.post("/login", data={"pin": "0000"})
            self.assertEqual(response.status_code, 401)

            response = self.client.post("/login", data={"pin": "1111"})
            self.assertEqual(response.status_code, 429)
            self.assertIn("Too many failed attempts.", response.get_data(as_text=True))

            response = self.client.post("/login", data={"pin": "2468"})
            self.assertEqual(response.status_code, 429)

    def test_create_conversation_rejects_invalid_model(self):
        response = self.client.post(
            "/api/conversations",
            json={"title": "Test Chat", "model": "invalid-model"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid model.")

    def test_create_app_registers_bootstrap_rag_sync(self):
        with patch("rag_service.sync_conversations_to_rag_safe") as mocked_sync:
            bootstrap_app = create_app(database_path=f"{self.temp_dir.name}/bootstrap.db")
            mocked_sync.assert_not_called()
            bootstrap_client = bootstrap_app.test_client()
            bootstrap_client.get("/")

            mocked_sync.assert_called_once_with()

    def test_create_app_applies_persisted_login_lifetime_setting(self):
        save_app_settings({"login_remember_session_days": "14"})

        second_app = create_app(database_path=self.db_path)

        self.assertEqual(second_app.config["PERMANENT_SESSION_LIFETIME"], timedelta(days=14))

    def test_database_initialization_adds_rag_document_expiration_column(self):
        with get_db() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(rag_documents)").fetchall()}

        self.assertIn("expires_at", columns)

    def test_create_conversation_triggers_auto_rag_sync(self):
        with patch("routes.conversations.sync_conversations_to_rag_safe") as mocked_sync:
            response = self.client.post(
                "/api/conversations",
                json={"title": "Test Chat", "model": "deepseek-chat"},
            )

        self.assertEqual(response.status_code, 201)
        mocked_sync.assert_called_once_with(conversation_id=response.get_json()["id"])

    def test_update_conversation_title_triggers_auto_rag_sync(self):
        with patch("routes.conversations.sync_conversations_to_rag_safe") as mocked_sync:
            conversation_id = self._create_conversation()
            mocked_sync.reset_mock()

            response = self.client.patch(
                f"/api/conversations/{conversation_id}",
                json={"title": "Renamed Chat"},
            )

        self.assertEqual(response.status_code, 200)
        mocked_sync.assert_called_once_with(conversation_id=conversation_id)

    def test_chat_route_triggers_auto_rag_sync_after_persist(self):
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": [], "canvas_documents": []},
                {"type": "done"},
            ]
        )

        with patch("routes.conversations.sync_conversations_to_rag_safe") as conversation_sync:
            conversation_id = self._create_conversation()
            conversation_sync.reset_mock()

        with patch("routes.chat.run_agent_stream", return_value=fake_events), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ) as chat_sync:
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Hello",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        chat_sync.assert_called_once_with(conversation_id=conversation_id, force=False)

    def test_get_conversation_records_for_rag_separates_soft_deleted_messages_into_archive(self):
        conversation_id = self._create_conversation()
        assistant_metadata = serialize_message_metadata(
            {
                "tool_results": [
                    {
                        "tool_name": "fetch_url",
                        "content": "Stale tool result",
                    }
                ]
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "Original prompt")
            deleted_assistant_id = insert_message(
                conn,
                conversation_id,
                "assistant",
                "Outdated answer",
                metadata=assistant_metadata,
            )
            insert_message(conn, conversation_id, "assistant", "Current answer")
            conn.execute(
                "UPDATE messages SET deleted_at = datetime('now') WHERE id = ?",
                (deleted_assistant_id,),
            )

        records = get_conversation_records_for_rag(conversation_id)

        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["messages"],
            [
                {"role": "user", "content": "Original prompt"},
                {"role": "assistant", "content": "Current answer"},
            ],
        )
        self.assertEqual(records[0]["tool_results"], [])
        self.assertEqual(len(records[0]["archived_messages"]), 1)
        self.assertIn("Hidden transcript message from this conversation.", records[0]["archived_messages"][0]["content"])
        self.assertIn("Outdated answer", records[0]["archived_messages"][0]["content"])

    def test_get_conversation_records_for_rag_compacts_clarification_response_messages(self):
        conversation_id = self._create_conversation()

        with get_db() as conn:
            insert_message(
                conn,
                conversation_id,
                "user",
                "Q: Bütçe nedir?\nA: 200-300 TL\nQ: Hedef ülke nedir?\nA: Türkiye",
                metadata=serialize_message_metadata(
                    {
                        "clarification_response": {
                            "assistant_message_id": 5,
                            "answers": {
                                "budget": {"display": "200-300 TL"},
                                "country": {"display": "Türkiye"},
                            },
                        }
                    }
                ),
            )
            insert_message(conn, conversation_id, "assistant", "Plan hazır.")

        records = get_conversation_records_for_rag(conversation_id)

        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["messages"],
            [
                {"role": "user", "content": "200-300 TL Türkiye"},
                {"role": "assistant", "content": "Plan hazır."},
            ],
        )

    def test_sync_conversations_to_rag_skips_unchanged_conversations_without_loading_records(self):
        conversation_id = self._create_conversation()
        user_text = "Original prompt " * 40
        assistant_text = "Current answer " * 60
        assistant_metadata = serialize_message_metadata(
            {
                "tool_results": [
                    {
                        "tool_name": "fetch_url",
                        "content": "Indexed tool result " * 40,
                    }
                ]
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", user_text)
            insert_message(conn, conversation_id, "assistant", assistant_text, metadata=assistant_metadata)
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                ("2026-04-08 10:00:00", conversation_id),
            )

        first_sync = sync_conversations_to_rag(conversation_id)

        self.assertTrue(first_sync)

        with patch("rag_service.get_conversation_records_for_rag") as mocked_records:
            second_sync = sync_conversations_to_rag(conversation_id)

        self.assertEqual(second_sync, [])
        mocked_records.assert_not_called()

    def test_sync_conversations_to_rag_skips_reindex_for_unchanged_tool_results(self):
        conversation_id = self._create_conversation()
        assistant_metadata = serialize_message_metadata(
            {
                "tool_results": [
                    {
                        "tool_name": "fetch_url",
                        "content": "Indexed tool result " * 40,
                    }
                ]
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "First prompt " * 30)
            insert_message(conn, conversation_id, "assistant", "First answer " * 40, metadata=assistant_metadata)
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                ("2026-04-08 10:00:00", conversation_id),
            )

        first_sync = sync_conversations_to_rag(conversation_id)
        self.assertTrue(first_sync)

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "Follow-up without tool change " * 20)
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                ("2026-04-08 10:01:00", conversation_id),
            )

        ingested_source_keys: list[str] = []

        def fake_ingest(*args, **kwargs):
            ingested_source_keys.append(str(kwargs.get("source_key") or ""))
            return {"source_key": kwargs.get("source_key")}

        with patch("rag_service.ingest_rag_chunks", side_effect=fake_ingest):
            sync_conversations_to_rag(conversation_id)

        self.assertIn(rag_service.conversation_rag_source_key(rag_service.RAG_SOURCE_CONVERSATION, conversation_id), ingested_source_keys)
        self.assertNotIn(rag_service.conversation_rag_source_key(rag_service.RAG_SOURCE_TOOL_RESULT, conversation_id), ingested_source_keys)

    def test_chat_edit_resyncs_rag_before_retrieval(self):
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Updated answer."},
                {"type": "tool_capture", "tool_results": [], "canvas_documents": []},
                {"type": "done"},
            ]
        )

        with patch("routes.conversations.sync_conversations_to_rag_safe"):
            conversation_id = self._create_conversation()

        with get_db() as conn:
            edited_message_id = insert_message(conn, conversation_id, "user", "Original prompt")
            insert_message(conn, conversation_id, "assistant", "Original answer")

        def check_rag_context(*args, **kwargs):
            self.assertTrue(chat_sync.called)
            self.assertEqual(chat_sync.call_args.kwargs, {"conversation_id": conversation_id, "force": True})
            return None

        with patch("routes.chat.run_agent_stream", return_value=fake_events), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ) as chat_sync, patch("routes.chat.build_rag_auto_context", side_effect=check_rag_context):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "edited_message_id": edited_message_id,
                    "user_content": "Edited prompt",
                    "messages": [{"role": "user", "content": "Edited prompt"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)

    def test_chat_route_updates_conversation_model_to_last_used_model(self):
        conversation_id = self._create_conversation()

        settings_response = self.client.patch(
            "/api/settings",
            json={
                "custom_models": [
                    {
                        "name": "Claude Sonnet 4.5",
                        "api_model": "anthropic/claude-sonnet-4.5",
                        "supports_tools": True,
                        "supports_vision": True,
                        "supports_structured_outputs": True,
                    }
                ],
                "visible_model_order": ["openrouter:anthropic/claude-sonnet-4.5", "deepseek-chat"],
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": [],
                "rag_auto_inject": False,
            },
        )
        self.assertEqual(settings_response.status_code, 200)

        def fake_run_agent_stream(*args, **kwargs):
            return iter(
                [
                    {"type": "answer_start"},
                    {"type": "answer_delta", "text": "Tamam."},
                    {"type": "tool_capture", "tool_results": [], "canvas_documents": []},
                    {"type": "done"},
                ]
            )

        with patch("routes.chat.run_agent_stream", side_effect=fake_run_agent_stream), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "openrouter:anthropic/claude-sonnet-4.5",
                    "user_content": "Yeni modeli kullan.",
                    "messages": [{"role": "user", "content": "Yeni modeli kullan."}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        conversation = conversation_response.get_json()["conversation"]
        self.assertEqual(conversation["model"], "openrouter:anthropic/claude-sonnet-4.5")
        self.assertEqual(conversation["model_label"], "Claude Sonnet 4.5")

    def test_chat_edit_restores_canvas_state_from_that_point(self):
        captured = {}
        conversation_id = self._create_conversation()

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "First prompt")
            insert_message(
                conn,
                conversation_id,
                "assistant",
                "Initial canvas",
                metadata=serialize_message_metadata(
                    {
                        "canvas_documents": [
                            {
                                "id": "canvas-a",
                                "title": "draft-a.md",
                                "format": "markdown",
                                "content": "# Draft A",
                            }
                        ],
                        "active_document_id": "canvas-a",
                    }
                ),
            )
            edited_message_id = insert_message(conn, conversation_id, "user", "Second prompt")
            insert_message(
                conn,
                conversation_id,
                "assistant",
                "Updated canvas",
                metadata=serialize_message_metadata(
                    {
                        "canvas_documents": [
                            {
                                "id": "canvas-b",
                                "title": "draft-b.md",
                                "format": "markdown",
                                "content": "# Draft B",
                            }
                        ],
                        "active_document_id": "canvas-b",
                    }
                ),
            )

        def fake_run_agent_stream(*args, **kwargs):
            captured["initial_canvas_documents"] = kwargs.get("initial_canvas_documents") or []
            captured["initial_canvas_active_document_id"] = kwargs.get("initial_canvas_active_document_id")
            return iter([{"type": "done"}])

        with patch("routes.chat.run_agent_stream", side_effect=fake_run_agent_stream), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "edited_message_id": edited_message_id,
                    "user_content": "Second prompt revised",
                    "messages": [{"role": "user", "content": "Second prompt revised"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([doc["title"] for doc in captured["initial_canvas_documents"]], ["draft-a.md"])
        self.assertEqual(captured["initial_canvas_active_document_id"], "canvas-a")

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        runtime_state = find_latest_canvas_state(messages)
        self.assertEqual([doc["title"] for doc in runtime_state["documents"]], ["draft-a.md"])

    def test_chat_edit_does_not_replay_stale_context_injection(self):
        captured = {}
        conversation_id = self._create_conversation()
        stale_context = "## Knowledge Base\nStale branch excerpt: Old message / Old answer"

        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "First question")
            insert_message(conn, conversation_id, "assistant", "First answer")
            edited_message_id = insert_message(
                conn,
                conversation_id,
                "user",
                "Old message",
                metadata=serialize_message_metadata({"context_injection": stale_context}),
            )
            insert_message(conn, conversation_id, "assistant", "Old answer")

        def fake_run_agent_stream(api_messages, *args, **kwargs):
            captured["api_messages"] = api_messages
            return iter(
                [
                    {"type": "answer_start"},
                    {"type": "answer_delta", "text": "New answer"},
                    {"type": "tool_capture", "tool_results": []},
                    {"type": "done"},
                ]
            )

        with patch("routes.chat.run_agent_stream", side_effect=fake_run_agent_stream), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "edited_message_id": edited_message_id,
                    "model": "deepseek-chat",
                    "user_content": "New message",
                    "messages": [
                        {"role": "user", "content": "First question"},
                        {"role": "assistant", "content": "First answer"},
                        {
                            "role": "user",
                            "content": "New message",
                            "metadata": {"context_injection": stale_context},
                        },
                    ],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("api_messages", captured)
        system_text = "\n\n".join(
            str(message.get("content") or "")
            for message in captured["api_messages"]
            if message.get("role") == "system"
        )
        self.assertNotIn("Stale branch excerpt", system_text)
        self.assertIn("New message", "\n".join(str(message.get("content") or "") for message in captured["api_messages"]))

        with get_db() as conn:
            row = conn.execute("SELECT metadata FROM messages WHERE id = ?", (edited_message_id,)).fetchone()
        persisted_metadata = parse_message_metadata(row["metadata"])
        self.assertNotIn("Stale branch excerpt", str(persisted_metadata.get("context_injection") or ""))

    def test_chat_edit_reverts_later_branch_state_before_replay_prompt(self):
        captured = {}
        conversation_id = self._create_conversation()
        workspace_root = os.path.join(self.temp_dir.name, "edit-replay-prompt-workspace")

        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
            }
        )
        append_to_scratchpad("Baseline scratchpad")
        upsert_user_profile_entry("fact:edit-replay", "baseline profile", confidence=0.9, source="test")

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "First question")
            insert_message(conn, conversation_id, "assistant", "First answer")
            edited_message_id = insert_message(conn, conversation_id, "user", "Old message")
            later_assistant_id = insert_message(conn, conversation_id, "assistant", "Old answer")

        append_to_scratchpad(
            "Stale scratchpad",
            conversation_id=conversation_id,
            source_message_id=later_assistant_id,
        )
        upsert_user_profile_entry(
            "fact:edit-replay",
            "stale profile",
            confidence=0.3,
            source="test",
            conversation_id=conversation_id,
            source_message_id=later_assistant_id,
        )
        insert_conversation_memory_entry(
            conversation_id,
            "task_context",
            "stale-memory",
            "stale memory",
            message_id=later_assistant_id,
            mutation_context={"source_message_id": later_assistant_id},
        )

        def fake_run_agent_stream(api_messages, *args, **kwargs):
            captured["api_messages"] = api_messages
            return iter(
                [
                    {"type": "answer_start"},
                    {"type": "answer_delta", "text": "Replay completed."},
                    {"type": "tool_capture", "tool_results": []},
                    {"type": "done"},
                ]
            )

        with patch(
            "conversation_cleanup_service.create_workspace_runtime_state",
            side_effect=lambda conversation_id=None, root_path=None: create_workspace_runtime_state(root_path=workspace_root),
        ), patch("routes.chat.run_agent_stream", side_effect=fake_run_agent_stream), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "edited_message_id": edited_message_id,
                    "model": "deepseek-chat",
                    "user_content": "New message",
                    "messages": [{"role": "user", "content": "New message"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        system_text = "\n\n".join(
            str(message.get("content") or "")
            for message in captured["api_messages"]
            if message.get("role") == "system"
        )
        self.assertIn("Baseline scratchpad", system_text)
        self.assertNotIn("Stale scratchpad", system_text)
        self.assertIn("baseline profile", system_text)
        self.assertNotIn("stale profile", system_text)
        self.assertNotIn("stale memory", system_text)
        self.assertEqual(get_conversation_memory(conversation_id), [])

    def test_chat_edit_rolls_back_mutable_state_when_replay_stream_fails(self):
        conversation_id = self._create_conversation()
        workspace_root = os.path.join(self.temp_dir.name, "edit-replay-workspace")
        os.makedirs(workspace_root, exist_ok=True)
        workspace_file = os.path.join(workspace_root, "notes.txt")
        with open(workspace_file, "w", encoding="utf-8") as fh:
            fh.write("baseline workspace")

        append_to_scratchpad("Baseline scratchpad")
        upsert_user_profile_entry("fact:preferred-tone", "baseline profile", confidence=0.9, source="test")

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "First prompt")
            insert_message(conn, conversation_id, "assistant", "First answer")
            edited_message_id = insert_message(conn, conversation_id, "user", "Original editable prompt")
            insert_message(conn, conversation_id, "assistant", "Later assistant answer")
            max_before = conn.execute(
                "SELECT COALESCE(MAX(id), 0) AS max_id FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()["max_id"]

        insert_conversation_memory_entry(
            conversation_id,
            "task_context",
            "critical-plan",
            "baseline memory",
            message_id=edited_message_id,
        )

        def failing_events():
            append_to_scratchpad("Mutated scratchpad")
            upsert_user_profile_entry("fact:preferred-tone", "mutated profile", confidence=0.2, source="test")
            insert_conversation_memory_entry(
                conversation_id,
                "task_context",
                "critical-plan",
                "mutated memory",
                message_id=edited_message_id,
            )
            with open(workspace_file, "w", encoding="utf-8") as fh:
                fh.write("mutated workspace")
            yield {"type": "answer_delta", "text": "Partial output"}
            raise RuntimeError("forced replay failure")

        with patch(
            "routes.chat.create_workspace_runtime_state",
            side_effect=lambda _conversation_id=None, _root_path=None: create_workspace_runtime_state(root_path=workspace_root),
        ), patch("routes.chat.run_agent_stream", return_value=failing_events()), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "edited_message_id": edited_message_id,
                    "user_content": "Edited prompt that should rollback",
                    "messages": [{"role": "user", "content": "Edited prompt that should rollback"}],
                },
            )
            payload_text = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Previous state restored", payload_text)

        with get_db() as conn:
            edited_row = conn.execute(
                "SELECT content, deleted_at FROM messages WHERE id = ? AND conversation_id = ?",
                (edited_message_id, conversation_id),
            ).fetchone()
            later_row = conn.execute(
                """SELECT deleted_at
                   FROM messages
                   WHERE conversation_id = ? AND role = 'assistant' AND content = ?
                   ORDER BY id DESC
                   LIMIT 1""",
                (conversation_id, "Later assistant answer"),
            ).fetchone()
            max_after = conn.execute(
                "SELECT COALESCE(MAX(id), 0) AS max_id FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()["max_id"]

        self.assertEqual(edited_row["content"], "Original editable prompt")
        self.assertIsNone(edited_row["deleted_at"])
        self.assertIsNotNone(later_row)
        self.assertIsNone(later_row["deleted_at"])
        self.assertEqual(max_after, max_before)

        with get_db() as conn:
            mutation_rows = conn.execute(
                """SELECT source_message_id, before_value, after_value
                   FROM conversation_state_mutations
                   WHERE conversation_id = ? AND target_kind = ? AND target_key = ?
                   ORDER BY id ASC""",
                (conversation_id, "conversation_memory", "critical-plan"),
            ).fetchall()

        self.assertGreaterEqual(len(mutation_rows), 3)
        latest_mutation = mutation_rows[-1]
        self.assertIsNone(latest_mutation["source_message_id"])
        self.assertEqual(json.loads(latest_mutation["before_value"])["value"], "mutated memory")
        self.assertEqual(json.loads(latest_mutation["after_value"])["value"], "baseline memory")

        scratchpad_sections = get_all_scratchpad_sections(get_app_settings())
        self.assertIn("Baseline scratchpad", scratchpad_sections.get("notes", ""))
        self.assertNotIn("Mutated scratchpad", scratchpad_sections.get("notes", ""))

        profile_entries = {entry["key"]: entry for entry in get_user_profile_entries()}
        self.assertEqual(profile_entries["fact:preferred-tone"]["value"], "baseline profile")

        memory_entries = get_conversation_memory(conversation_id)
        baseline_entry = next((entry for entry in memory_entries if entry.get("key") == "critical-plan"), None)
        self.assertIsNotNone(baseline_entry)
        self.assertEqual(baseline_entry["value"], "baseline memory")

        with open(workspace_file, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "baseline workspace")

    def test_chat_edit_commits_mutable_state_on_successful_replay(self):
        conversation_id = self._create_conversation()
        workspace_root = os.path.join(self.temp_dir.name, "edit-replay-workspace-success")
        os.makedirs(workspace_root, exist_ok=True)
        workspace_file = os.path.join(workspace_root, "state.txt")
        with open(workspace_file, "w", encoding="utf-8") as fh:
            fh.write("before")

        append_to_scratchpad("Before success")
        upsert_user_profile_entry("fact:success-path", "before", confidence=0.6, source="test")

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "First prompt")
            insert_message(conn, conversation_id, "assistant", "First answer")
            edited_message_id = insert_message(conn, conversation_id, "user", "Original editable prompt")
            later_message_id = insert_message(conn, conversation_id, "assistant", "Later assistant answer")

        insert_conversation_memory_entry(
            conversation_id,
            "task_context",
            "success-memory",
            "before",
            message_id=edited_message_id,
        )

        def successful_events():
            append_to_scratchpad("Committed scratchpad")
            upsert_user_profile_entry("fact:success-path", "after", confidence=0.9, source="test")
            insert_conversation_memory_entry(
                conversation_id,
                "task_context",
                "success-memory",
                "after",
                message_id=edited_message_id,
            )
            with open(workspace_file, "w", encoding="utf-8") as fh:
                fh.write("after")
            yield {"type": "answer_start"}
            yield {"type": "answer_delta", "text": "Replay completed."}
            yield {"type": "tool_capture", "tool_results": [], "canvas_documents": []}
            yield {"type": "done"}

        with patch(
            "routes.chat.create_workspace_runtime_state",
            side_effect=lambda _conversation_id=None, _root_path=None: create_workspace_runtime_state(root_path=workspace_root),
        ), patch("routes.chat.run_agent_stream", return_value=successful_events()), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "edited_message_id": edited_message_id,
                    "user_content": "Edited prompt that should commit",
                    "messages": [{"role": "user", "content": "Edited prompt that should commit"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)

        with get_db() as conn:
            edited_row = conn.execute(
                "SELECT content FROM messages WHERE id = ? AND conversation_id = ?",
                (edited_message_id, conversation_id),
            ).fetchone()
            later_row = conn.execute(
                "SELECT deleted_at FROM messages WHERE id = ? AND conversation_id = ?",
                (later_message_id, conversation_id),
            ).fetchone()

        self.assertEqual(edited_row["content"], "Edited prompt that should commit")
        self.assertIsNotNone(later_row["deleted_at"])

        scratchpad_sections = get_all_scratchpad_sections(get_app_settings())
        self.assertIn("Committed scratchpad", scratchpad_sections.get("notes", ""))

        profile_entries = {entry["key"]: entry for entry in get_user_profile_entries()}
        self.assertEqual(profile_entries["fact:success-path"]["value"], "after")

        memory_entries = get_conversation_memory(conversation_id)
        committed_entry = next((entry for entry in memory_entries if entry.get("key") == "success-memory"), None)
        self.assertIsNotNone(committed_entry)
        self.assertEqual(committed_entry["value"], "after")

        with open(workspace_file, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "after")

    def test_chat_route_separates_prompt_tools_from_execution_whitelist(self):
        captured = {}
        conversation_id = self._create_conversation()

        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": json.dumps(["append_scratchpad", "search_web", "rewrite_canvas_document"], ensure_ascii=False),
                "rag_auto_inject": "false",
            }
        )

        def fake_run_agent_stream(api_messages, *args, **kwargs):
            captured["api_messages"] = api_messages
            captured["args"] = args
            captured["enabled_tool_names"] = kwargs.get("enabled_tool_names")
            captured["prompt_tool_names"] = kwargs.get("prompt_tool_names")
            return iter(
                [
                    {"type": "answer_start"},
                    {"type": "answer_delta", "text": "OK"},
                    {"type": "tool_capture", "tool_results": []},
                    {"type": "done"},
                ]
            )

        with patch("routes.chat.run_agent_stream", side_effect=fake_run_agent_stream), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": "Merhaba"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["args"][0], "deepseek-chat")
        self.assertEqual(captured["args"][1], 1)
        self.assertEqual(captured["args"][2][:2], ["append_scratchpad", "search_web"])
        self.assertIn("replace_scratchpad", captured["args"][2])
        self.assertIn("append_scratchpad", captured["prompt_tool_names"])
        self.assertIn("replace_scratchpad", captured["prompt_tool_names"])
        self.assertNotIn("search_web", captured["prompt_tool_names"])
        system_text = "\n\n".join(
            str(message.get("content") or "")
            for message in captured["api_messages"]
            if message.get("role") == "system"
        )
        self.assertIn("Callable tools:", system_text)
        self.assertIn("`append_scratchpad`", system_text)
        self.assertIn("`search_web`", system_text)
        self.assertNotIn("`rewrite_canvas_document`", system_text)

    def test_chat_route_injects_conversation_memory_and_passes_agent_context(self):
        captured = {}
        conversation_id = self._create_conversation()
        insert_conversation_memory_entry(
            conversation_id,
            "user_info",
            "Preferred name",
            "Kullanıcının adı Ahmet.",
        )

        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": json.dumps(["save_to_conversation_memory", "delete_conversation_memory_entry"], ensure_ascii=False),
                "rag_auto_inject": "false",
            }
        )

        def fake_run_agent_stream(api_messages, *args, **kwargs):
            captured["api_messages"] = api_messages
            captured["agent_context"] = kwargs.get("agent_context")
            return iter(
                [
                    {"type": "answer_start"},
                    {"type": "answer_delta", "text": "OK"},
                    {"type": "tool_capture", "tool_results": []},
                    {"type": "done"},
                ]
            )

        with patch("routes.chat.run_agent_stream", side_effect=fake_run_agent_stream), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": "Bunu hatırla"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["agent_context"]["conversation_id"], conversation_id)
        self.assertIn("source_message_id", captured["agent_context"])
        system_text = "\n\n".join(
            str(message.get("content") or "")
            for message in captured["api_messages"]
            if message.get("role") == "system"
        )
        self.assertIn("## Conversation Memory", system_text)
        self.assertIn("Preferred name", system_text)
        self.assertIn("Kullanıcının adı Ahmet.", system_text)

    def test_chat_route_defers_postprocess_outside_testing(self):
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": [], "canvas_documents": []},
                {"type": "done"},
            ]
        )

        conversation_id = self._create_conversation()
        previous_testing = self.app.config.get("TESTING", False)
        self.app.config["TESTING"] = False

        try:
            self.client.get("/")
            csrf_token = self._get_session_csrf_token()
            self.assertTrue(csrf_token)

            with patch("routes.chat.run_agent_stream", return_value=fake_events), patch(
                "routes.chat.POST_RESPONSE_EXECUTOR.submit"
            ) as mocked_submit, patch("routes.chat.SUMMARY_EXECUTOR.submit") as mocked_summary_submit:
                response = self.client.post(
                    "/chat",
                    json={
                        "conversation_id": conversation_id,
                        "model": "deepseek-chat",
                        "user_content": "Hello",
                        "messages": [{"role": "user", "content": "Hello"}],
                    },
                    headers={"X-CSRF-Token": csrf_token},
                )
                response.get_data(as_text=True)
        finally:
            self.app.config["TESTING"] = previous_testing

        self.assertEqual(response.status_code, 200)
        mocked_submit.assert_called_once()
        mocked_summary_submit.assert_not_called()

    def test_generate_title_triggers_auto_rag_sync(self):
        with patch("routes.conversations.sync_conversations_to_rag_safe"):
            conversation_id = self._create_conversation()

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "Need a title")
            insert_message(conn, conversation_id, "assistant", "Sure, here is the answer")
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )

        with patch(
            "routes.chat.collect_agent_response",
            return_value={"content": "Better Title", "errors": []},
        ), patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(f"/api/conversations/{conversation_id}/generate-title")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["title"], "Better Title")

    def test_manual_prune_endpoint_updates_message_and_preserves_original(self):
        conversation_id = self._create_conversation()
        with get_db() as conn:
            message_id = insert_message(conn, conversation_id, "assistant", "Bu mesaj gereksiz ayrıntılar içeriyor ve budanmalı.")

        mock_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Bu mesaj budanmış halidir."))]
        )
        with patch("prune_service.client.chat.completions.create", return_value=mock_response), patch(
            "routes.conversations.sync_conversations_to_rag_safe"
        ) as mocked_sync:
            response = self.client.post(
                f"/api/messages/{message_id}/prune",
                json={"conversation_id": conversation_id},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["pruned"])
        self.assertEqual(payload["message"]["content"], "Bu mesaj budanmış halidir.")
        self.assertTrue(payload["message"]["metadata"]["is_pruned"])
        self.assertEqual(
            payload["message"]["metadata"]["pruned_original"],
            "Bu mesaj gereksiz ayrıntılar içeriyor ve budanmalı.",
        )
        mocked_sync.assert_called_once_with(conversation_id=conversation_id)

    def test_pruning_prompt_requires_preserving_critical_and_code_content(self):
        prompt_messages = _build_pruning_messages(
            """Bunu kısalt ama şu kodu bozma:\n\n```python\ndef add(a, b):\n    return a + b\n```\n\nAPI key: sk-test-12345\nURL: https://example.com/docs\nSayi: 4096"""
        )

        system_prompt = prompt_messages[0]["content"]
        user_prompt = prompt_messages[1]["content"]

        self.assertIn("all critical facts", system_prompt)
        self.assertIn("code blocks", system_prompt)
        self.assertIn("keep those sections verbatim", system_prompt)
        self.assertIn("Preserve the message's core idea", user_prompt)
        self.assertIn("Code blocks", user_prompt)
        self.assertIn("JSON", user_prompt)
        self.assertIn("URLs", user_prompt)
        self.assertIn("must be kept verbatim", user_prompt)

    def test_pruning_prompt_includes_target_token_hint(self):
        prompt_messages = _build_pruning_messages("Tekrarlı ayrıntı " * 80, target_tokens=123)

        self.assertIn("roughly 123 tokens", prompt_messages[1]["content"])

    def test_pruning_prompt_includes_role_and_retry_instruction(self):
        prompt_messages = _build_pruning_messages(
            "Detaylı teknik açıklama",
            role="assistant",
            retry_instruction="Empty response returned previously.",
        )

        self.assertIn("Target message role: assistant.", prompt_messages[1]["content"])
        self.assertIn("Empty response returned previously.", prompt_messages[1]["content"])

    def test_pruning_target_tokens_do_not_expand_short_messages(self):
        short_message = "Kısa not"
        target_tokens = _estimate_pruning_target_tokens(short_message)

        self.assertGreaterEqual(target_tokens, 1)
        self.assertLessEqual(target_tokens, estimate_text_tokens(short_message))

    def test_prune_score_weights_redistribute_rag_weight_when_disabled(self):
        weights = prune_service._resolve_prune_score_weights(rag_enabled=False)

        self.assertEqual(weights["rag_coverage"], 0.0)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertGreater(weights["entropy_prunability"], prune_service.PRUNE_SCORE_WEIGHTS["entropy_prunability"])
        self.assertGreater(weights["recency"], prune_service.PRUNE_SCORE_WEIGHTS["recency"])

    def test_prune_conversation_batch_uses_scored_candidate_order(self):
        conversation_id = self._create_conversation()
        with get_db() as conn:
            small_id = insert_message(conn, conversation_id, "user", "Kısa mesaj")
            large_id = insert_message(conn, conversation_id, "assistant", "Büyük mesaj " * 120)
            medium_id = insert_message(conn, conversation_id, "user", "Orta mesaj " * 40)

        pruned_ids = []

        def fake_prune_message(message_id):
            pruned_ids.append(message_id)
            return {"id": message_id}

        with patch(
            "prune_service.score_conversation_messages_for_prune",
            return_value=[
                {"id": medium_id, "prune_score": 0.91},
                {"id": small_id, "prune_score": 0.88},
                {"id": large_id, "prune_score": 0.33},
            ],
        ), patch("prune_service.prune_message", side_effect=fake_prune_message):
            pruned_count = prune_service.prune_conversation_batch(conversation_id, 2)

        self.assertEqual(pruned_count, 2)
        self.assertEqual(pruned_ids, [medium_id, small_id])
        self.assertNotIn(large_id, pruned_ids)

    def test_prune_conversation_batch_skips_failed_messages(self):
        conversation_id = self._create_conversation()
        with get_db() as conn:
            first_id = insert_message(conn, conversation_id, "assistant", "İlk büyük mesaj " * 60)
            second_id = insert_message(conn, conversation_id, "user", "İkinci büyük mesaj " * 55)

        seen_ids = []

        def fake_prune_message(message_id):
            seen_ids.append(message_id)
            if message_id == first_id:
                raise RuntimeError("temporary failure")
            return {"id": message_id}

        with patch(
            "prune_service.score_conversation_messages_for_prune",
            return_value=[
                {"id": first_id, "prune_score": 0.95},
                {"id": second_id, "prune_score": 0.81},
            ],
        ), patch("prune_service.prune_message", side_effect=fake_prune_message):
            pruned_count = prune_service.prune_conversation_batch(conversation_id, 2)

        self.assertEqual(pruned_count, 1)
        self.assertEqual(set(seen_ids), {first_id, second_id})

    def test_prune_scores_endpoint_returns_scored_candidates(self):
        conversation_id = self._create_conversation()

        with patch(
            "routes.conversations.score_conversation_messages_for_prune",
            return_value=[
                {
                    "id": 11,
                    "position": 2,
                    "role": "assistant",
                    "content_preview": "Örnek içerik",
                    "estimated_tokens": 42,
                    "entropy_score": 0.21,
                    "rag_coverage_score": 0.66,
                    "recency_score": 0.75,
                    "token_weight": 0.8,
                    "prune_score": 0.79,
                }
            ],
        ):
            response = self.client.post(f"/api/conversations/{conversation_id}/prune-scores", json={})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["prunable_message_count"], 1)
        self.assertEqual(payload["prunable_token_count"], 42)
        self.assertEqual(payload["scores"][0]["id"], 11)
        self.assertIn("batch_size", payload)
        self.assertIn("threshold", payload)

    def test_prune_selected_endpoint_prunes_selected_messages_in_position_order(self):
        conversation_id = self._create_conversation()
        with get_db() as conn:
            first_id = insert_message(conn, conversation_id, "user", "İlk mesaj")
            insert_message(conn, conversation_id, "assistant", "İkinci mesaj")
            third_id = insert_message(conn, conversation_id, "user", "Üçüncü mesaj")

        seen_ids = []

        def fake_prune_message(message_id):
            seen_ids.append(message_id)
            return {"id": message_id, "content": f"pruned-{message_id}"}

        with patch(
            "routes.conversations.score_conversation_messages_for_prune",
            return_value=[
                {"id": third_id, "position": 3, "prune_score": 0.92},
                {"id": first_id, "position": 1, "prune_score": 0.89},
            ],
        ), patch("routes.conversations.prune_message", side_effect=fake_prune_message), patch(
            "routes.conversations.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/prune-selected",
                json={"message_ids": [third_id, first_id]},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["pruned_count"], 2)
        self.assertEqual(seen_ids, [first_id, third_id])
        self.assertEqual([result["id"] for result in payload["results"]], [first_id, third_id])

    def test_is_prunable_message_allows_plain_assistant_messages(self):
        self.assertTrue(prune_service.is_prunable_message({"role": "assistant", "content": "Detaylı ama araçsız yanıt"}))
        self.assertFalse(
            prune_service.is_prunable_message(
                {
                    "role": "assistant",
                    "content": "Araç çağrısı içerir",
                    "tool_calls": [{"id": "call-1"}],
                }
            )
        )

    def test_background_post_response_pruning_runs_when_threshold_exceeded(self):
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Kısa cevap."},
                {"type": "tool_capture", "tool_results": [], "canvas_documents": []},
                {"type": "done"},
            ]
        )

        conversation_id = self._create_conversation()

        with patch("routes.chat.run_agent_stream", return_value=fake_events), patch(
            "routes.chat.maybe_create_conversation_summary",
            return_value={"applied": False},
        ), patch("routes.chat._count_prunable_message_tokens", return_value=90_000), patch(
            "routes.chat.prune_conversation_batch"
        ) as mocked_prune, patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.patch(
                "/api/settings",
                json={
                    "pruning_enabled": True,
                    "pruning_token_threshold": 80000,
                    "pruning_batch_size": 3,
                },
            )
            self.assertEqual(response.status_code, 200)

            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Merhaba",
                    "messages": [{"role": "user", "content": "Merhaba"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        mocked_prune.assert_called_once_with(conversation_id, 3)

    def test_update_message_endpoint_updates_user_and_assistant_messages(self):
        conversation_id = self._create_conversation()
        with get_db() as conn:
            user_id = insert_message(conn, conversation_id, "user", "İlk sürüm")
            assistant_id = insert_message(conn, conversation_id, "assistant", "İlk yanıt")

        with patch("routes.conversations.sync_conversations_to_rag_safe") as mocked_sync:
            user_response = self.client.patch(
                f"/api/messages/{user_id}",
                json={
                    "conversation_id": conversation_id,
                    "content": "Düzeltilmiş kullanıcı mesajı",
                },
            )
            assistant_response = self.client.patch(
                f"/api/messages/{assistant_id}",
                json={
                    "conversation_id": conversation_id,
                    "content": "Düzeltilmiş asistan yanıtı",
                },
            )

        self.assertEqual(user_response.status_code, 200)
        self.assertEqual(assistant_response.status_code, 200)
        self.assertEqual(user_response.get_json()["message"]["content"], "Düzeltilmiş kullanıcı mesajı")
        self.assertEqual(assistant_response.get_json()["message"]["content"], "Düzeltilmiş asistan yanıtı")
        self.assertEqual(mocked_sync.call_count, 2)

    def test_chat_uses_updated_history_messages_after_manual_edit(self):
        captured = {}
        conversation_id = self._create_conversation()

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "İlk soru")
            assistant_id = insert_message(conn, conversation_id, "assistant", "Eski yanıt")

        with patch("routes.conversations.sync_conversations_to_rag_safe"):
            update_response = self.client.patch(
                f"/api/messages/{assistant_id}",
                json={
                    "conversation_id": conversation_id,
                    "content": "Güncel yanıt",
                },
            )

        self.assertEqual(update_response.status_code, 200)

        def fake_run_agent_stream(*args, **kwargs):
            captured["api_messages"] = args[0]
            return iter([{"type": "done"}])

        with patch("routes.chat.run_agent_stream", side_effect=fake_run_agent_stream), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": "Yeni soru"}],
                    "user_content": "Yeni soru",
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        assistant_messages = [
            message for message in captured["api_messages"]
            if isinstance(message, dict) and message.get("role") == "assistant"
        ]
        self.assertTrue(any(message.get("content") == "Güncel yanıt" for message in assistant_messages))

    def test_count_prunable_message_tokens_ignores_tool_and_summary_messages(self):
        messages = [
            {"role": "user", "content": "Visible user text"},
            {"role": "assistant", "content": "Visible assistant text"},
            {
                "role": "assistant",
                "content": "Tool call envelope",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search_web", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "content": "Very large tool result" * 1000},
            {"role": "summary", "content": "Conversation summary"},
            {"role": "assistant", "content": "", "metadata": {"is_pruned": True}},
        ]

        expected = _count_prunable_message_tokens(
            [
                {"role": "user", "content": "Visible user text"},
                {"role": "assistant", "content": "Visible assistant text"},
            ]
        )

        self.assertEqual(_count_prunable_message_tokens(messages), expected)

    def test_active_tools_include_replace_scratchpad_for_existing_scratchpad_mode(self):
        settings = {"active_tools": json.dumps(["append_scratchpad", "search_web"]) }
        active_tools = get_active_tool_names(settings)
        self.assertIn("replace_scratchpad", active_tools)
        self.assertIn("read_scratchpad", active_tools)

    def test_active_tools_do_not_backfill_disabled_canvas_inspection_tools(self):
        settings = {"active_tools": json.dumps(["rewrite_canvas_document", "replace_canvas_lines"])}

        active_tool_names = get_active_tool_names(settings)

        self.assertIn("rewrite_canvas_document", active_tool_names)
        self.assertIn("replace_canvas_lines", active_tool_names)
        self.assertNotIn("expand_canvas_document", active_tool_names)
        self.assertNotIn("scroll_canvas_document", active_tool_names)

    def test_db_connections_enable_busy_timeout_and_wal_mode(self):
        with get_db() as conn:
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

        self.assertEqual(busy_timeout, 30000)
        self.assertEqual(str(journal_mode).lower(), "wal")

    def test_disabled_features_reflect_in_settings_and_routes(self):
        with patch("config.RAG_ENABLED", False), patch("config.OCR_ENABLED", False), patch(
            "config.IMAGE_UPLOADS_ENABLED", False
        ), patch("db.RAG_ENABLED", False), patch("db.IMAGE_UPLOADS_ENABLED", False), patch(
            "routes.pages.RAG_ENABLED", False
        ), patch("routes.conversations.RAG_ENABLED", False):
            response = self.client.get("/api/settings")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertFalse(payload["rag_auto_inject"])
            self.assertFalse(payload["features"]["rag_enabled"])
            self.assertFalse(payload["features"]["ocr_enabled"])
            self.assertFalse(payload["features"]["image_uploads_enabled"])

            response = self.client.patch(
                "/api/settings",
                json={"rag_auto_inject": True},
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.get_json()["rag_auto_inject"])

            response = self.client.get("/api/rag/documents")
            self.assertEqual(response.status_code, 410)

            conversation_id = self._create_conversation()
            response = self.client.delete(f"/api/conversations/{conversation_id}")
            self.assertEqual(response.status_code, 204)

        with patch("routes.chat.IMAGE_UPLOADS_ENABLED", False):
            response = self.client.post(
                "/chat",
                data={
                    "messages": json.dumps([{"role": "user", "content": "Test"}]),
                    "model": "deepseek-chat",
                    "conversation_id": "",
                    "user_content": "Test",
                    "image": (io.BytesIO(b"fake image bytes"), "test.png"),
                },
            )
            self.assertEqual(response.status_code, 410)

    def test_chat_allows_image_upload_in_ocr_only_mode(self):
        conversation_id = self._create_conversation()
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("db.IMAGE_STORAGE_DIR", self.image_storage_dir), patch("routes.chat.IMAGE_UPLOADS_ENABLED", True), patch(
            "routes.chat.analyze_uploaded_image",
            return_value={
                "ocr_text": "invoice total 42",
                "vision_summary": "Readable text was detected in the image and added to the context.",
                "assistant_guidance": "Use the extracted OCR text as the primary image context when answering the user.",
                "key_points": [],
            },
        ), patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                data={
                    "messages": json.dumps([{"role": "user", "content": "Bu görselde ne yazıyor?"}]),
                    "model": "deepseek-chat",
                    "conversation_id": str(conversation_id),
                    "user_content": "Bu görselde ne yazıyor?",
                    "image": (io.BytesIO(b"fake image bytes"), "receipt.png", "image/png"),
                },
            )

        self.assertEqual(response.status_code, 200)
        response.get_data(as_text=True)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        user_messages = [message for message in messages if message["role"] == "user"]
        self.assertEqual(len(user_messages), 1)
        metadata = user_messages[0]["metadata"]
        self.assertEqual(metadata["ocr_text"], "invoice total 42")
        self.assertEqual(
            metadata["assistant_guidance"],
            "Use the extracted OCR text as the primary image context when answering the user.",
        )

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
        self.assertIn("- Other files: src/config.py", content)
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
        self.assertEqual(messages[1]["role"], "system")
        self.assertNotIn("id", messages[1])

        stable_content = messages[0]["content"]
        content = messages[1]["content"]
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
        self.assertEqual(messages[2]["role"], "user")

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
        self.assertEqual(messages[2]["role"], "system")
        content = messages[2]["content"]
        self.assertIn("## Conversation Summaries", content)
        self.assertIn("authoritative compressed history for earlier deleted turns", content)
        self.assertIn("## Current Date and Time", content)
        self.assertTrue(content.startswith("## Current Date and Time"))
        self.assertLess(content.index("## Current Date and Time"), content.index("## Conversation Summaries"))
        self.assertNotIn("id", messages[2])

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

        self.assertIn("conversation memory instead", scratchpad_guidance)
        self.assertIn("future responses or behavior across conversations", scratchpad_guidance)
        self.assertIn("default to conversation memory", conversation_guidance)
        self.assertIn("Multiple compact entries are better than one overloaded summary", conversation_guidance)

    def test_search_tool_specs_allow_optional_conversation_memory_promotion(self):
        knowledge_base_spec = TOOL_SPEC_BY_NAME["search_knowledge_base"]
        tool_memory_spec = TOOL_SPEC_BY_NAME["search_tool_memory"]

        self.assertIn("save_to_conversation_memory", knowledge_base_spec["parameters"]["properties"])
        self.assertIn("memory_key", knowledge_base_spec["parameters"]["properties"])
        self.assertIn("save_to_conversation_memory", tool_memory_spec["parameters"]["properties"])
        self.assertIn("memory_key", tool_memory_spec["parameters"]["properties"])
        self.assertIn("survive later turns in this chat", knowledge_base_spec["prompt"]["guidance"])
        self.assertIn("survive later turns in this chat", tool_memory_spec["prompt"]["guidance"])

    def test_settings_patch_allows_manual_scratchpad_updates(self):
        response = self.client.patch(
            "/api/settings",
            json={"scratchpad": "The user likes concise answers.\nThe user likes concise answers.\n"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["scratchpad"], "The user likes concise answers.")
        self.assertEqual(payload["scratchpad_sections"]["notes"]["content"], "The user likes concise answers.")
        self.assertFalse(payload["features"]["scratchpad_admin_editing"])

    def test_settings_get_reports_scratchpad_admin_feature_flag(self):
        with patch("config.SCRATCHPAD_ADMIN_EDITING_ENABLED", True):
            response = self.client.get("/api/settings")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["features"]["scratchpad_admin_editing"])

    def test_append_to_scratchpad_deduplicates_and_persists(self):
        result, summary = append_to_scratchpad("The user is 22 years old.")
        self.assertEqual(summary, "Scratchpad updated")
        self.assertEqual(result["status"], "appended")

        duplicate_result, duplicate_summary = append_to_scratchpad("The   user is 22 years old.   ")
        self.assertEqual(duplicate_summary, "Scratchpad notes already exist")
        self.assertEqual(duplicate_result["status"], "skipped")

        settings = get_app_settings()
        self.assertEqual(settings["scratchpad"], "The user is 22 years old.")

    def test_chat_runtime_context_injects_saved_scratchpad(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "scratchpad": "The user prefers concise answers.",
                "max_steps": "2",
                "active_tools": "[]",
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events) as mocked_stream:
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Hello",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        first_call_messages = mocked_stream.call_args.args[0]
        injected_context = next(
            (
                message["content"]
                for message in first_call_messages[1:]
                if message.get("role") == "system" and "The user prefers concise answers." in str(message.get("content") or "")
            ),
            None,
        )
        self.assertIsNotNone(injected_context)

    def test_chat_uses_saved_rag_sensitivity_and_context_size(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "scratchpad": "",
                "max_steps": "2",
                "active_tools": "[]",
                "rag_auto_inject": "true",
                "rag_sensitivity": "strict",
                "rag_context_size": "large",
                "rag_source_types": json.dumps(["conversation"], ensure_ascii=False),
                "rag_auto_inject_source_types": json.dumps(["uploaded_document"], ensure_ascii=False),
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.build_rag_auto_context", return_value=None) as mocked_rag, patch(
            "routes.chat.run_agent_stream", return_value=fake_events
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Hello",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mocked_rag.call_args.args[0], "Hello")
        self.assertTrue(mocked_rag.call_args.args[1])
        self.assertEqual(mocked_rag.call_args.kwargs["threshold"], 0.55)
        self.assertEqual(mocked_rag.call_args.kwargs["top_k"], 8)
        self.assertEqual(mocked_rag.call_args.kwargs["allowed_source_types"], {"uploaded_document"})

    def test_chat_excludes_tool_memory_from_generic_rag_when_dedicated_tool_memory_auto_inject_is_enabled(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "scratchpad": "",
                "max_steps": "2",
                "active_tools": "[]",
                "rag_auto_inject": "true",
                "rag_sensitivity": "strict",
                "rag_context_size": "large",
                "rag_source_types": json.dumps(["conversation", "tool_memory", "uploaded_document"], ensure_ascii=False),
                "rag_auto_inject_source_types": json.dumps(["conversation", "tool_memory", "uploaded_document"], ensure_ascii=False),
                "tool_memory_auto_inject": "true",
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.build_rag_auto_context", return_value=None) as mocked_rag, patch(
            "routes.chat.run_agent_stream", return_value=fake_events
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Hello",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mocked_rag.call_args.kwargs["allowed_source_types"], {"conversation", "uploaded_document"})

    def test_chat_disables_clarification_tool_for_clarification_response_turn(self):
        conversation_id = self._create_conversation()
        assistant_message_id = self._insert_pending_clarification_assistant(conversation_id)
        save_app_settings(
            {
                "user_preferences": "",
                "scratchpad": "",
                "max_steps": "2",
                "active_tools": json.dumps(["ask_clarifying_question"], ensure_ascii=False),
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events) as mocked_stream:
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Q: Budget?\nA: 200-300 TL",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Q: Budget?\nA: 200-300 TL",
                            "metadata": {
                                "clarification_response": {
                                    "assistant_message_id": assistant_message_id,
                                    "answers": {
                                        "budget": {"display": "200-300 TL"},
                                    },
                                }
                            },
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("ask_clarifying_question", mocked_stream.call_args.args[3])

    def test_chat_keeps_clarification_tool_when_response_turn_also_has_new_user_request(self):
        conversation_id = self._create_conversation()
        assistant_message_id = self._insert_pending_clarification_assistant(conversation_id)
        save_app_settings(
            {
                "user_preferences": "",
                "scratchpad": "",
                "max_steps": "2",
                "active_tools": json.dumps(["ask_clarifying_question"], ensure_ascii=False),
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events) as mocked_stream:
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Q: Budget?\nA: 200-300 TL\n\nİlk olarak bana sorular sor.",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Q: Budget?\nA: 200-300 TL\n\nİlk olarak bana sorular sor.",
                            "metadata": {
                                "clarification_response": {
                                    "assistant_message_id": assistant_message_id,
                                    "answers": {
                                        "budget": {"display": "200-300 TL"},
                                    },
                                }
                            },
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("ask_clarifying_question", mocked_stream.call_args.args[3])

    def test_validate_clarification_response_against_messages_enriches_questions(self):
        conversation_id = self._create_conversation()
        assistant_message_id = self._insert_pending_clarification_assistant(
            conversation_id,
            questions=[
                {
                    "id": "budget",
                    "label": "Budget?",
                    "input_type": "text",
                    "required": True,
                },
                {
                    "id": "goal",
                    "label": "Goal?",
                    "input_type": "text",
                    "required": False,
                },
            ],
        )

        with self.app.app_context():
            validated, error = _validate_clarification_response_against_messages(
                {
                    "assistant_message_id": assistant_message_id,
                    "answers": {
                        "budget": {"display": "200-300 TL"},
                        "unexpected": {"display": "ignore me"},
                    },
                },
                get_conversation_messages(conversation_id),
            )

        self.assertIsNone(error)
        self.assertEqual(validated["assistant_message_id"], assistant_message_id)
        self.assertEqual(validated["questions"][0]["id"], "budget")
        self.assertEqual(validated["answers"], {"budget": {"display": "200-300 TL"}})

    def test_collect_answered_clarification_rounds_skips_orphaned_responses(self):
        conversation_id = self._create_conversation()

        with self.app.app_context():
            with get_db() as conn:
                insert_message(
                    conn,
                    conversation_id,
                    "user",
                    "Q: Budget?\nA: 200-300 TL",
                    metadata=serialize_message_metadata(
                        {
                            "clarification_response": {
                                "assistant_message_id": 999999,
                                "answers": {"budget": {"display": "200-300 TL"}},
                            }
                        }
                    ),
                )
            rounds = _collect_answered_clarification_rounds(get_conversation_messages(conversation_id))

        self.assertEqual(rounds, [])

    def test_chat_rejects_stale_clarification_response_turn(self):
        conversation_id = self._create_conversation()
        stale_assistant_message_id = self._insert_pending_clarification_assistant(conversation_id)

        with self.app.app_context():
            with get_db() as conn:
                insert_message(
                    conn,
                    conversation_id,
                    "user",
                    "Q: Budget?\nA: 100 TL",
                    metadata=serialize_message_metadata(
                        {
                            "clarification_response": {
                                "assistant_message_id": stale_assistant_message_id,
                                "answers": {"budget": {"display": "100 TL"}},
                            }
                        }
                    ),
                )

        self._insert_pending_clarification_assistant(
            conversation_id,
            text="I need one more update.",
            questions=[
                {
                    "id": "goal",
                    "label": "Goal?",
                    "input_type": "text",
                    "required": True,
                }
            ],
        )

        with patch("routes.chat.run_agent_stream") as mocked_stream:
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Q: Budget?\nA: 200-300 TL",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Q: Budget?\nA: 200-300 TL",
                            "metadata": {
                                "clarification_response": {
                                    "assistant_message_id": stale_assistant_message_id,
                                    "answers": {
                                        "budget": {"display": "200-300 TL"},
                                    },
                                }
                            },
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "stale_clarification_response")
        mocked_stream.assert_not_called()

    def test_index_uses_external_app_script(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("marked/marked.min.js", html)
        self.assertIn("dompurify/dist/purify.min.js", html)
        self.assertIn('id="app-bootstrap"', html)
        self.assertIn('href="/settings"', html)
        self.assertNotIn('id="scratchpad-list"', html)
        self.assertNotIn('id="settings-panel"', html)

    def test_settings_page_renders_dedicated_layout(self):
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Minimal, grouped settings", html)
        self.assertIn('data-settings-tab="general"', html)
        self.assertIn('data-settings-tab="models"', html)
        self.assertIn('data-settings-tab="context"', html)
        self.assertIn('data-settings-tab="tools"', html)
        self.assertIn('data-settings-tab="knowledge"', html)
        self.assertIn("Manual knowledge", html)
        self.assertIn("Upload document", html)
        self.assertIn('src="/static/settings.js?v=', html)
        self.assertIn('id="kb-sync-btn"', html)
        self.assertIn("Proxy scope", html)
        self.assertIn("proxy-enabled-operation", html)
        self.assertIn("settings-subsection-grid", html)
        self.assertIn("settings-callout", html)
        self.assertIn("settings-collapsible", html)
        self.assertIn("Fallback order per operation", html)
        self.assertIn('id="tool-memory-lane-panel"', html)
        self.assertIn("Persona fallback", html)
        self.assertIn("Model identity", html)
        self.assertIn("Research boundaries", html)
        self.assertIn("Publishing controls", html)
        self.assertIn('id="settings-restart-banner"', html)
        self.assertIn('id="upload-metadata-model-preference-select"', html)
        self.assertIn('id="upload-metadata-model-fallback-list"', html)
        self.assertIn('id="chat-summary-model-select"', html)
        self.assertIn('id="openrouter-http-referer-input"', html)
        self.assertIn('id="openrouter-app-title-input"', html)
        self.assertIn('id="login-session-timeout-minutes-input"', html)
        self.assertIn('id="conversation-memory-enabled-toggle"', html)
        self.assertIn('id="ocr-enabled-toggle"', html)
        self.assertIn('id="rag-enabled-toggle"', html)
        self.assertIn('id="youtube-transcript-model-size-select"', html)
        self.assertIn('id="tool-memory-ttl-default-seconds-input"', html)
        self.assertIn('id="fetch-summary-max-chars-input"', html)
        self.assertNotIn('id="reasoning-auto-collapse-toggle"', html)
        self.assertNotIn('style="', html)

    def test_settings_tools_cover_all_defined_tool_specs(self):
        option_names = [option["name"] for option in build_tool_permission_options()]

        self.assertIn("replace_scratchpad", option_names)
        self.assertIn("delete_canvas_document", option_names)
        self.assertIn("clear_canvas", option_names)

    def test_settings_tools_group_access_surfaces(self):
        sections = build_tool_permission_sections()
        section_titles = [section["title"] for section in sections]

        self.assertEqual(
            section_titles,
            ["Assistant & Memory", "Web Research", "Draft Files (Canvas)", "Real Files (Workspace)"],
        )

        assistant_tools = next(section for section in sections if section["key"] == "assistant")["tools"]
        workspace_tools = next(section for section in sections if section["key"] == "workspace")["tools"]
        canvas_tools = next(section for section in sections if section["key"] == "canvas")["tools"]
        research_section = next(section for section in sections if section["key"] == "research")

        self.assertIn("save_to_conversation_memory", [tool["name"] for tool in assistant_tools])
        self.assertIn("delete_conversation_memory_entry", [tool["name"] for tool in assistant_tools])

        self.assertIn("read_file", [tool["name"] for tool in workspace_tools])
        self.assertIn("validate_project_workspace", [tool["name"] for tool in workspace_tools])
        self.assertIn("search_canvas_document", [tool["name"] for tool in canvas_tools])
        self.assertIn("batch_read_canvas_documents", [tool["name"] for tool in canvas_tools])
        self.assertIn("validate_canvas_document", [tool["name"] for tool in canvas_tools])
        self.assertIn("focus_canvas_page", [tool["name"] for tool in canvas_tools])
        self.assertEqual(
            research_section["note"],
            "When enabled, these tools stay available at runtime, but the prompt still tells the assistant to avoid unnecessary external lookups.",
        )

        assistant_labels = {tool["name"]: tool["label"] for tool in assistant_tools}
        research_labels = {tool["name"]: tool["label"] for tool in research_section["tools"]}
        canvas_labels = {tool["name"]: tool["label"] for tool in canvas_tools}

        self.assertEqual(assistant_labels["save_to_conversation_memory"], "Save chat memory")
        self.assertEqual(assistant_labels["delete_conversation_memory_entry"], "Delete chat memory")
        self.assertEqual(assistant_labels["sub_agent"], "Web research helper")
        self.assertEqual(assistant_labels["search_tool_memory"], "Search remembered research")
        self.assertEqual(research_labels["fetch_url_summarized"], "Summarize URL")
        self.assertEqual(research_labels["fetch_url_to_canvas"], "Import URL into Canvas")
        self.assertEqual(canvas_labels["batch_read_canvas_documents"], "Read multiple canvas documents")
        self.assertEqual(canvas_labels["validate_canvas_document"], "Validate canvas document")

    def test_sub_agent_allowed_tools_are_web_only(self):
        self.assertEqual(
            SUB_AGENT_ALLOWED_TOOL_NAMES,
            [
                "search_web",
                "fetch_url",
                "fetch_url_summarized",
                "grep_fetched_content",
                "search_news_ddgs",
                "search_news_google",
            ],
        )

    def test_settings_api_roundtrip_preserves_configured_tool_permissions(self):
        response = self.client.patch(
            "/api/settings",
            json={
                "active_tools": [
                    "append_scratchpad",
                    "replace_scratchpad",
                    "delete_canvas_document",
                    "clear_canvas",
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        active_tools = response.get_json()["active_tools"]
        self.assertEqual(
            active_tools,
            ["append_scratchpad", "replace_scratchpad", "delete_canvas_document", "clear_canvas"],
        )

    def test_proxy_candidates_for_operation_respect_saved_scope(self):
        save_app_settings({"proxy_enabled_operations": json.dumps([PROXY_OPERATION_FETCH_URL], ensure_ascii=False)})

        with patch("web_tools.get_proxy_candidates", return_value=["http://proxy.example:8080", None]):
            self.assertEqual(
                get_proxy_candidates_for_operation("openrouter", include_direct_fallback=True),
                [None],
            )
            self.assertEqual(
                get_proxy_candidates_for_operation("fetch_url", include_direct_fallback=True),
                ["http://proxy.example:8080", None],
            )

    def test_build_user_message_for_model_includes_stored_image_reference(self):
        content = build_user_message_for_model(
            "What does this mean?",
            {
                "image_id": "img_123",
                "image_name": "screen.png",
                "vision_summary": "A pricing table is visible.",
            },
        )

        self.assertIn("Stored image reference: image_id=img_123, file=screen.png", content)
        self.assertIn("Visual summary: A pricing table is visible.", content)

    def test_build_user_message_for_model_includes_multiple_attachments(self):
        content = build_user_message_for_model(
            "Compare these assets.",
            {
                "attachments": [
                    {
                        "kind": "image",
                        "image_id": "img_123",
                        "image_name": "screen-a.png",
                        "vision_summary": "A dashboard is visible.",
                    },
                    {
                        "kind": "image",
                        "image_id": "img_456",
                        "image_name": "screen-b.png",
                        "vision_summary": "A settings page is visible.",
                    },
                    {
                        "kind": "document",
                        "file_id": "file_123",
                        "file_name": "notes.txt",
                        "file_context_block": "[Uploaded document: notes.txt]\n\nProject notes",
                    },
                ]
            },
        )

        self.assertIn("Stored image reference: image_id=img_123, file=screen-a.png", content)
        self.assertIn("Stored image reference: image_id=img_456, file=screen-b.png", content)
        self.assertIn("[Image attachment context] Attachment 1", content)
        self.assertIn("[Image attachment context] Attachment 2", content)
        self.assertIn("[Uploaded document: notes.txt]", content)
        self.assertIn("Visual summary: A dashboard is visible.", content)
        self.assertIn("Visual summary: A settings page is visible.", content)

    def test_build_user_message_for_model_clarifies_visual_pdf_page_limit(self):
        content = build_user_message_for_model(
            "Analyze this PDF.",
            {
                "attachments": [
                    {
                        "kind": "document",
                        "file_name": "exam.pdf",
                        "submission_mode": "visual",
                        "visual_page_count": 3,
                        "visual_total_page_count": 6,
                        "visual_page_image_ids": ["img-1", "img-2", "img-3"],
                    }
                ]
            },
        )

        self.assertIn("PDF has 6 pages; only the first 3 pages are attached", content)

    def test_build_user_message_for_model_warns_when_visual_pdf_has_no_rendered_pages(self):
        content = build_user_message_for_model(
            "Analyze this PDF.",
            {
                "attachments": [
                    {
                        "kind": "document",
                        "file_name": "scan.pdf",
                        "submission_mode": "visual",
                        "visual_page_count": 0,
                        "visual_total_page_count": 4,
                        "visual_page_image_ids": [],
                    }
                ]
            },
        )

        self.assertIn("PDF has 4 pages, but no rendered page images are currently attached", content)
        self.assertNotIn("1 page is attached", content)

    def test_build_user_message_for_model_omits_document_context_already_in_canvas(self):
        content = build_user_message_for_model(
            "Use the document in canvas.",
            {
                "attachments": [
                    {
                        "kind": "document",
                        "file_id": "file_123",
                        "file_name": "notes.txt",
                        "file_context_block": "[Uploaded document: notes.txt]\n\nProject notes\nLine two",
                    }
                ]
            },
            canvas_documents=[
                {
                    "id": "doc-1",
                    "title": "notes.txt",
                    "content": "# notes.txt\n\nProject notes\nLine two",
                    "format": "markdown",
                    "language": "markdown",
                }
            ],
        )

        self.assertIn("Use the document in canvas.", content)
        self.assertNotIn("[Uploaded document: notes.txt]", content)
        self.assertNotIn("Project notes", content)

    def test_build_user_message_for_model_omits_document_context_for_extensionless_canvas_title(self):
        content = build_user_message_for_model(
            "Use the document in canvas.",
            {
                "attachments": [
                    {
                        "kind": "document",
                        "file_id": "file_123",
                        "file_name": "notes.txt",
                        "file_context_block": "[Uploaded document: notes.txt]\n\nProject notes\nLine two",
                    }
                ]
            },
            canvas_documents=[
                {
                    "id": "doc-1",
                    "title": "notes",
                    "content": "# notes.txt\n\nProject notes\nLine two",
                    "format": "markdown",
                    "language": "markdown",
                }
            ],
        )

        self.assertEqual(content, "Use the document in canvas.")

    def test_build_user_message_for_model_preserves_clarification_transcript(self):
        content = build_user_message_for_model(
            "Q: Budget?\nA: 200-300 TL\nQ: Goal?\nA: Sales",
            {
                "clarification_response": {
                    "assistant_message_id": 12,
                    "answers": {
                        "budget": {"display": "200-300 TL"},
                        "goal": {"display": "Sales"},
                    },
                }
            },
        )

        self.assertEqual(content, "- budget \u2192 200-300 TL\n- goal \u2192 Sales")

    def test_build_user_message_for_model_reconstructs_clarification_transcript_when_content_is_empty(self):
        content = build_user_message_for_model(
            "",
            {
                "clarification_response": {
                    "assistant_message_id": 12,
                    "answers": {
                        "budget": {"display": "200-300 TL"},
                    },
                }
            },
            clarification_questions=[
                {
                    "id": "budget",
                    "label": "Budget?",
                    "input_type": "text",
                }
            ],
        )

        self.assertEqual(content, "- Budget? \u2192 200-300 TL")

    def test_build_user_message_for_model_preserves_freeform_request_beside_clarification_answers(self):
        content = build_user_message_for_model(
            "Q: Budget?\nA: 200-300 TL\n\nİlk olarak bana sorular sor.",
            {
                "clarification_response": {
                    "assistant_message_id": 12,
                    "answers": {
                        "budget": {"display": "200-300 TL"},
                    },
                }
            },
        )

        self.assertEqual(content, "İlk olarak bana sorular sor.\n\n- budget \u2192 200-300 TL")

    def test_image_explain_tool_spec_requires_image_and_conversation_ids(self):
        spec = TOOL_SPEC_BY_NAME["image_explain"]

        self.assertEqual(spec["parameters"]["required"], ["image_id", "conversation_id", "question"])
        self.assertIn("Write this question in English", spec["parameters"]["properties"]["question"]["description"])
        self.assertIn("Always send the question in English", spec["prompt"]["guidance"])

    def test_clarification_tool_spec_supports_structured_questions(self):
        spec = TOOL_SPEC_BY_NAME["ask_clarifying_question"]

        self.assertEqual(spec["parameters"]["required"], ["questions"])
        self.assertEqual(spec["parameters"]["properties"]["questions"]["minItems"], 1)
        self.assertEqual(spec["parameters"]["properties"]["questions"]["maxItems"], 25)
        self.assertEqual(
            spec["parameters"]["properties"]["questions"]["items"]["properties"]["depends_on"]["type"],
            "object",
        )
        self.assertIn("explicitly asks you to ask questions first", spec["description"])
        self.assertIn("only tool call", spec["prompt"]["guidance"])
        self.assertIn("ids short and unique", spec["prompt"]["guidance"])
        self.assertIn("depends_on", spec["prompt"]["guidance"])

    def test_openai_tool_specs_resize_clarification_question_limit(self):
        tools = get_openai_tool_specs(["ask_clarifying_question"], clarification_max_questions=7)

        questions_schema = tools[0]["function"]["parameters"]["properties"]["questions"]
        self.assertEqual(questions_schema["maxItems"], 7)
        self.assertEqual(questions_schema["description"], "List of 1-7 clarification questions.")

    def test_sub_agent_tool_spec_requires_english_delegation(self):
        spec = TOOL_SPEC_BY_NAME["sub_agent"]

        self.assertIn("clear English instructions", spec["parameters"]["properties"]["task"]["description"])
        self.assertIn("rewrite the delegated task into concise English instructions", spec["prompt"]["guidance"])
        self.assertNotIn("timeout_seconds", spec["parameters"]["properties"])
        self.assertNotIn("allowed_tools", spec["parameters"]["properties"])
        self.assertIn("The user controls both the helper's web-tool allowlist and its maximum step budget from Settings", spec["prompt"]["guidance"])
        self.assertIn("Legacy optional helper-agent tool budget", spec["parameters"]["properties"]["max_steps"]["description"])

    def test_clarification_tool_validator_accepts_stringified_question_objects(self):
        from agent import _validate_tool_arguments

        tool_args = {
            "questions": [
                '{"id":"scope","label":"Which scope?","input_type":"single_select","options":[{"label":"Only this repo","value":"repo"}]}',
                '{"id":"notes","label":"Anything else?","input_type":"text"}',
            ]
        }

        self.assertIsNone(_validate_tool_arguments("ask_clarifying_question", tool_args))
        self.assertIsInstance(tool_args["questions"][0], dict)
        self.assertEqual(tool_args["questions"][0]["id"], "scope")

    def test_clarification_tool_validator_accepts_plain_string_questions(self):
        from agent import _validate_tool_arguments

        tool_args = {
            "questions": [
                "Which operating system should I target?",
                "Any hard constraints?",
            ]
        }

        self.assertIsNone(_validate_tool_arguments("ask_clarifying_question", tool_args))
        self.assertEqual(tool_args["questions"][0]["label"], "Which operating system should I target?")
        self.assertEqual(tool_args["questions"][0]["input_type"], "text")

    def test_clarification_tool_validator_uses_configured_max_questions(self):
        from agent import _validate_tool_arguments

        tool_args = {
            "questions": [
                {"id": "one", "label": "One?", "input_type": "text"},
                {"id": "two", "label": "Two?", "input_type": "text"},
                {"id": "three", "label": "Three?", "input_type": "text"},
            ]
        }

        with patch("agent.get_clarification_max_questions", return_value=2):
            error = _validate_tool_arguments("ask_clarifying_question", tool_args)

        self.assertIsNone(error)
        self.assertEqual(len(tool_args["questions"]), 2)

    def test_search_web_validator_allows_more_than_five_queries_for_runtime_batching(self):
        from agent import _validate_tool_arguments

        tool_args = {"queries": [f"query {index}" for index in range(1, 8)]}

        self.assertIsNone(_validate_tool_arguments("search_web", tool_args))

    def test_search_web_validator_normalizes_legacy_query_aliases(self):
        from agent import _validate_tool_arguments

        tool_args = {"search_query": "repo overview"}

        self.assertIsNone(_validate_tool_arguments("search_web", tool_args))
        self.assertEqual(tool_args["queries"], ["repo overview"])

    def test_create_canvas_document_validator_infers_missing_title_from_path(self):
        from agent import _validate_tool_arguments

        tool_args = {
            "path": "src/app.py",
            "content": "print('hello')",
            "format": "code",
        }

        self.assertIsNone(_validate_tool_arguments("create_canvas_document", tool_args))
        self.assertEqual(tool_args["title"], "app.py")

    def test_grep_fetched_content_validator_clamps_runtime_coercible_limits(self):
        from agent import _validate_tool_arguments

        tool_args = {
            "url": "https://example.com",
            "pattern": "Sağlık Yönetimi",
            "context_lines": 10,
            "max_matches": 99,
        }

        self.assertIsNone(_validate_tool_arguments("grep_fetched_content", tool_args))
        self.assertEqual(tool_args["context_lines"], 5)
        self.assertEqual(tool_args["max_matches"], 30)

    def test_batch_canvas_edits_validator_drops_optional_null_selectors(self):
        from agent import _validate_tool_arguments

        tool_args = {
            "document_path": None,
            "targets": [
                {
                    "document_id": "doc-1",
                    "document_path": None,
                    "operations": [
                        {"action": "insert", "after_line": 1, "lines": ["Yeni satir"]},
                    ],
                }
            ],
        }

        self.assertIsNone(_validate_tool_arguments("batch_canvas_edits", tool_args))
        self.assertNotIn("document_path", tool_args)
        self.assertNotIn("document_path", tool_args["targets"][0])

    def test_validator_treats_required_null_field_as_missing(self):
        from agent import _validate_tool_arguments

        tool_args = {"url": None}

        self.assertEqual(
            _validate_tool_arguments("fetch_url", tool_args),
            "Missing required argument 'url' for fetch_url",
        )

    def test_execute_tool_batches_search_web_queries_above_schema_limit(self):
        queries = [f"query {index}" for index in range(1, 8)]

        with patch(
            "agent.search_web_tool",
            side_effect=[
                [{"title": "A", "url": "https://example.com/a", "snippet": "alpha"}],
                [{"title": "B", "url": "https://example.com/b", "snippet": "beta"}],
            ],
        ) as mocked_search:
            result, summary = _execute_tool("search_web", {"queries": queries})

        self.assertEqual(mocked_search.call_count, 2)
        self.assertEqual(mocked_search.call_args_list[0].args[0], queries[:5])
        self.assertEqual(mocked_search.call_args_list[1].args[0], queries[5:])
        self.assertEqual(len(result), 2)
        self.assertEqual(summary, "2 web results found")

    def test_execute_clarification_tool_normalizes_question_aliases(self):
        result, summary = _execute_tool(
            "ask_clarifying_question",
            {
                "questions": [
                    {
                        "key": "software",
                        "question": "Hangi sanallaştırma yazılımını kullanacaksın?",
                        "type": "single",
                        "options": [
                            {"label": "VMware", "value": "vmware"},
                            {"label": "VirtualBox", "value": "virtualbox"},
                        ],
                    }
                ]
            },
        )

        self.assertEqual(summary, "Awaiting user clarification")
        self.assertEqual(result["status"], "needs_user_input")
        self.assertEqual(result["clarification"]["questions"][0]["id"], "software")
        self.assertEqual(result["clarification"]["questions"][0]["label"], "Hangi sanallaştırma yazılımını kullanacaksın?")
        self.assertEqual(result["clarification"]["questions"][0]["input_type"], "single_select")

    def test_execute_clarification_tool_normalizes_question_dependencies(self):
        result, summary = _execute_tool(
            "ask_clarifying_question",
            {
                "questions": [
                    {
                        "id": "platform",
                        "label": "Which platform?",
                        "input_type": "single_select",
                        "options": [
                            {"label": "Web", "value": "web"},
                            {"label": "Mobile", "value": "mobile"},
                        ],
                    },
                    {
                        "id": "framework",
                        "label": "Which web framework?",
                        "input_type": "single_select",
                        "options": [
                            {"label": "Flask", "value": "flask"},
                            {"label": "FastAPI", "value": "fastapi"},
                        ],
                        "depends_on": {"question_id": "platform", "value": "web"},
                    },
                ],
            },
        )

        self.assertEqual(summary, "Awaiting user clarification")
        self.assertEqual(
            result["clarification"]["questions"][1]["depends_on"],
            {"question_id": "platform", "values": ["web"]},
        )

    def test_execute_clarification_tool_rejects_select_questions_without_options(self):
        with self.assertRaises(ValueError):
            _execute_tool(
                "ask_clarifying_question",
                {
                    "questions": [
                        {"id": "scope", "label": "Which scope?", "input_type": "single_select"},
                    ]
                },
            )

    def test_execute_clarification_tool_respects_max_question_setting(self):
        with patch("agent.get_clarification_max_questions", return_value=2):
            result, summary = _execute_tool(
                "ask_clarifying_question",
                {
                    "intro": "Before I answer, I need a few details.",
                    "questions": [
                        {"id": "scope", "label": "Which scope?", "input_type": "text"},
                        {"id": "style", "label": "What style?", "input_type": "text"},
                        {"id": "deadline", "label": "Any deadline?", "input_type": "text"},
                    ],
                },
            )

        self.assertEqual(summary, "Awaiting user clarification")
        self.assertEqual(result["status"], "needs_user_input")
        self.assertEqual(len(result["clarification"]["questions"]), 2)
        self.assertEqual(
            result["text"],
            "Before I answer, I need a few details.\n"
            "Please answer these questions:\n"
            "1. Which scope?\n"
            "2. What style?",
        )
        self.assertEqual(result["clarification"]["intro"], "Before I answer, I need a few details.")
        self.assertEqual(result["clarification"]["questions"][0]["label"], "Which scope?")

    def test_execute_clarification_tool_sanitizes_wrapped_labels_and_options(self):
        result, summary = _execute_tool(
            "ask_clarifying_question",
            {
                "intro": '<|"Önce bunu netleştirelim:"|>',
                "submit_label": '```Devam```',
                "questions": [
                    {
                        "id": '<|career-focus|>',
                        "label": '* Q: <|"Önerdiğim 3 yoldan hangileri sana daha cazip geliyor?"|>',
                        "input_type": "multi_select",
                        "options": [
                            {'label': '<|"Akademik Nörobilim Araştırmacısı"|>', 'value': '<|academic_track|>'},
                            '* <|"Klinik Araştırma + Akademik Hibrit"|>',
                        ],
                    }
                ],
            },
        )

        self.assertEqual(summary, "Awaiting user clarification")
        clarification = result["clarification"]
        self.assertEqual(clarification["intro"], "Önce bunu netleştirelim:")
        self.assertEqual(clarification["submit_label"], "Devam")
        self.assertEqual(clarification["questions"][0]["id"], "career_focus")
        self.assertEqual(
            clarification["questions"][0]["label"],
            "Önerdiğim 3 yoldan hangileri sana daha cazip geliyor?",
        )
        self.assertEqual(clarification["questions"][0]["options"][0]["label"], "Akademik Nörobilim Araştırmacısı")
        self.assertEqual(clarification["questions"][0]["options"][0]["value"], "academic_track")
        self.assertEqual(clarification["questions"][0]["options"][1]["label"], "Klinik Araştırma + Akademik Hibrit")
        self.assertEqual(clarification["questions"][0]["options"][1]["value"], "Klinik Araştırma + Akademik Hibrit")

    def test_execute_clarification_tool_preserves_numbered_financial_option_labels(self):
        result, summary = _execute_tool(
            "ask_clarifying_question",
            {
                "questions": [
                    {
                        "id": "income",
                        "label": "Yüksek finansal getiri ile kastettiğin net aylık nedir?",
                        "input_type": "single_select",
                        "options": [
                            {"label": "1.000+ TL", "value": "1000_plus"},
                            {"label": "2.000+ TL", "value": "2000_plus"},
                            {"label": "3.000+ TL", "value": "3000_plus"},
                        ],
                    }
                ]
            },
        )

        clarification = result["clarification"]
        self.assertEqual(summary, "Awaiting user clarification")
        self.assertEqual(clarification["questions"][0]["options"][0]["label"], "1.000+ TL")
        self.assertEqual(clarification["questions"][0]["options"][1]["label"], "2.000+ TL")
        self.assertEqual(clarification["questions"][0]["options"][2]["label"], "3.000+ TL")

    def test_execute_clarification_tool_preserves_grade_level_option_labels(self):
        result, summary = _execute_tool(
            "ask_clarifying_question",
            {
                "questions": [
                    {
                        "id": "kpss_start_time",
                        "label": "KPSS hazırlığına ne zaman başlamayı planlıyorsun?",
                        "input_type": "single_select",
                        "options": [
                            {"label": "5. sınıftan itibaren yavaş yavaş", "value": "5. sınıftan itibaren yavaş yavaş"},
                            {"label": "sınıfın başında", "value": "sınıfın başında"},
                            {"label": "Henüz düşünmedim", "value": "Henüz düşünmedim"},
                        ],
                    }
                ]
            },
        )

        clarification = result["clarification"]
        self.assertEqual(summary, "Awaiting user clarification")
        self.assertEqual(
            clarification["questions"][0]["options"][0]["label"],
            "5. sınıftan itibaren yavaş yavaş",
        )
        self.assertEqual(
            clarification["questions"][0]["options"][0]["value"],
            "5. sınıftan itibaren yavaş yavaş",
        )

    def test_clarification_prompt_guidance_avoids_inline_qa_format(self):
        message = build_runtime_system_message(
            active_tool_names=["ask_clarifying_question"],
        )

        self.assertIn("plain UI text only", message["content"])
        self.assertIn("avoid Q:/A: prefixes", message["content"])
        self.assertNotIn("use a simple Q:/A: format", message["content"])

        spec = TOOL_SPEC_BY_NAME["ask_clarifying_question"]
        self.assertIn("plain UI text only", spec["prompt"]["guidance"])
        self.assertIn("<| and |>", spec["prompt"]["guidance"])

    def test_execute_clarification_tool_dedupes_question_ids(self):
        result, summary = _execute_tool(
            "ask_clarifying_question",
            {
                "questions": [
                    {"id": "scope", "label": "Which scope?", "input_type": "text"},
                    {"id": "scope", "label": "What style?", "input_type": "text"},
                    {"label": "Any deadline?", "input_type": "text"},
                ]
            },
        )

        self.assertEqual(summary, "Awaiting user clarification")
        self.assertEqual(
            [question["id"] for question in result["clarification"]["questions"]],
            ["scope", "scope_2", "question_3"],
        )

    def test_run_agent_stream_allows_clarification_with_other_tool_calls(self):
        responses = [
            iter(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    reasoning_content="I should clarify scope and gather one quick result first.",
                                    content="",
                                    tool_calls=[
                                        {
                                            "index": 0,
                                            "id": "call-1",
                                            "function": {
                                                "name": "search_web",
                                                "arguments": json.dumps({"queries": ["clarification context"]}, ensure_ascii=False),
                                            },
                                        },
                                        {
                                            "index": 1,
                                            "id": "call-2",
                                            "function": {
                                                "name": "ask_clarifying_question",
                                                "arguments": json.dumps(
                                                    {
                                                        "questions": [
                                                            {"id": "scope", "label": "Which scope?", "input_type": "text"},
                                                        ]
                                                    },
                                                    ensure_ascii=False,
                                                ),
                                            },
                                        },
                                    ],
                                )
                            )
                        ]
                    ),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=3, total_tokens=6)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Stub", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Need help deciding scope"}],
                    "deepseek-chat",
                    2,
                    ["search_web", "ask_clarifying_question"],
                )
            )

        self.assertNotIn(
            "ask_clarifying_question must be the only tool call in a single assistant turn.",
            [event.get("error") for event in events if event["type"] == "tool_error"],
        )
        self.assertTrue(
            any(
                event["type"] == "tool_result"
                and event["tool"] == "search_web"
                and event["call_id"] == "call-1"
                and event["summary"] == "1 web results found"
                for event in events
            )
        )
        self.assertTrue(
            any(
                event["type"] == "tool_result"
                and event["tool"] == "ask_clarifying_question"
                and event["call_id"] == "call-2"
                and event["summary"] == "Awaiting user clarification"
                for event in events
            )
        )
        self.assertTrue(any(event["type"] == "clarification_request" for event in events))
        self.assertFalse(any(event["type"] == "tool_error" for event in events))

    def test_extract_pending_clarification_uses_configured_question_limit(self):
        metadata = {
            "pending_clarification": {
                "questions": [
                    {"id": f"q{index}", "label": f"Question {index}?", "input_type": "text"}
                    for index in range(1, 8)
                ]
            }
        }

        with patch("db.get_clarification_max_questions", return_value=7):
            payload = extract_pending_clarification(metadata)

        self.assertIsNotNone(payload)
        self.assertEqual(len(payload["questions"]), 7)
        self.assertEqual(payload["questions"][-1]["id"], "q7")

    def test_load_proxies_uses_cached_file_contents(self):
        proxies_path = Path(self.temp_dir.name) / "proxies.txt"
        proxies_path.write_text("http://127.0.0.1:8080\n", encoding="utf-8")
        web_tools._proxy_cache = None
        web_tools._proxy_cache_mtime = None

        with patch("web_tools.PROXIES_PATH", str(proxies_path)):
            first = load_proxies()
            self.assertEqual(first, ["http://127.0.0.1:8080"])

            mocked_open = Mock(side_effect=AssertionError("Proxy file should not be reopened when unchanged"))
            with patch("builtins.open", mocked_open):
                second = load_proxies()

        self.assertEqual(second, first)

    def test_image_explain_returns_reupload_instruction_when_asset_is_missing(self):
        result, summary = _execute_tool(
            "image_explain",
            {
                "image_id": "missing-image",
                "conversation_id": 99,
                "question": "What does the chart show?",
            },
        )

        self.assertEqual(summary, "Stored image not found")
        self.assertEqual(result["status"], "missing_image")
        self.assertIn("re-upload", result["error"])

    def test_get_ocr_engine_falls_back_to_easyocr_when_paddle_dependencies_are_missing(self):
        with patch.object(ocr_service, "OCR_ENABLED", True), patch.object(
            ocr_service, "OCR_PROVIDER", "paddleocr"
        ), patch.object(ocr_service, "_ocr_engine", None), patch.object(
            ocr_service,
            "_build_paddleocr_engine",
            side_effect=RuntimeError(
                "PaddleOCR dependencies are missing. Ensure paddleocr and a compatible paddlepaddle runtime are installed."
            ),
        ) as mocked_paddle, patch.object(
            ocr_service,
            "_build_easyocr_engine",
            return_value={"provider": "easyocr", "reader": object()},
        ) as mocked_easy:
            engine = ocr_service.get_ocr_engine()

        self.assertEqual(engine["provider"], "easyocr")
        self.assertEqual(engine["configured_provider"], "paddleocr")
        mocked_paddle.assert_called_once_with()
        mocked_easy.assert_called_once_with()

    def test_configure_paddle_runtime_disables_pir_and_onednn(self):
        fake_paddle = Mock()
        with patch.dict(sys.modules, {"paddle": fake_paddle}):
            ocr_service._configure_paddle_runtime()

        fake_paddle.set_flags.assert_called_once_with(
            {
                "FLAGS_enable_pir_api": False,
                "FLAGS_enable_pir_in_executor": False,
                "FLAGS_use_mkldnn": False,
                "FLAGS_use_onednn": False,
            }
        )

    def test_preload_ocr_engine_skips_missing_dependencies_without_raising(self):
        with patch.object(ocr_service, "OCR_ENABLED", True), patch.object(
            ocr_service, "OCR_PRELOAD_ON_STARTUP", True
        ), patch.object(
            ocr_service,
            "get_ocr_engine",
            side_effect=RuntimeError(
                "PaddleOCR dependencies are missing. Ensure paddleocr and a compatible paddlepaddle runtime are installed."
            ),
        ):
            ocr_service.preload_ocr_engine(SimpleNamespace(debug=False))

    def test_preload_dependencies_preloads_ocr_for_local_ocr_setting(self):
        with patch("routes.chat.get_app_settings", return_value={"image_processing_method": "local_ocr"}), patch(
            "routes.chat.OCR_ENABLED", True
        ), patch("routes.chat.RAG_ENABLED", False), patch("routes.chat.preload_ocr_engine") as mocked_preload_ocr:
            preload_dependencies(SimpleNamespace(debug=False))

        mocked_preload_ocr.assert_called_once()

    def test_preload_dependencies_preloads_ocr_for_llm_direct_setting(self):
        with patch("routes.chat.get_app_settings", return_value={"image_processing_method": "llm_direct"}), patch(
            "routes.chat.OCR_ENABLED", True
        ), patch("routes.chat.RAG_ENABLED", False), patch("routes.chat.preload_ocr_engine") as mocked_preload_ocr:
            preload_dependencies(SimpleNamespace(debug=False))

        mocked_preload_ocr.assert_called_once()

    def test_resolve_device_uses_cpu_without_importing_torch(self):
        from rag import embedder

        original_import = __import__

        def guarded_import(name, *args, **kwargs):
            if name == "torch":
                raise AssertionError("torch should not be imported for cpu device selection")
            return original_import(name, *args, **kwargs)

        with patch.dict(os.environ, {"BGE_M3_DEVICE": "cpu"}, clear=False), patch(
            "builtins.__import__", side_effect=guarded_import
        ):
            self.assertEqual(embedder._resolve_device(), "cpu")

    def test_resolve_device_falls_back_to_cpu_when_cuda_is_requested_without_torch(self):
        from rag import embedder

        original_import = __import__

        def guarded_import(name, *args, **kwargs):
            if name == "torch":
                raise ModuleNotFoundError("No module named 'torch'")
            return original_import(name, *args, **kwargs)

        with patch.dict(os.environ, {"BGE_M3_DEVICE": "cuda"}, clear=False), patch(
            "builtins.__import__", side_effect=guarded_import
        ), patch.object(embedder.logging, "warning") as mock_warning:
            self.assertEqual(embedder._resolve_device(), "cpu")
            mock_warning.assert_called_once()
            self.assertIn("falling back to CPU", mock_warning.call_args.args[0])

    def test_preload_embedder_skips_missing_dependencies_without_raising(self):
        from rag import embedder

        with patch.object(
            embedder,
            "get_embedder",
            side_effect=RuntimeError(
                "BGE-M3 dependencies are missing. Install sentence-transformers and torch before using RAG."
            ),
        ), patch.object(embedder.logging, "warning") as mock_warning:
            embedder.preload_embedder()
            mock_warning.assert_called_once()
            self.assertIn("BGE-M3 preload skipped", mock_warning.call_args.args[0])

    def test_canvas_tools_create_and_edit_document_in_runtime_state(self):
        runtime_state = {}

        created, create_summary = _execute_tool(
            "create_canvas_document",
            {
                "title": "Release Plan",
                "content": "# Release Plan\n\n- Draft\n- Review",
            },
            runtime_state=runtime_state,
        )
        self.assertEqual(create_summary, "Canvas created: Release Plan")
        self.assertEqual(created["action"], "created")
        document_id = created["document_id"]

        inserted, insert_summary = _execute_tool(
            "insert_canvas_lines",
            {
                "document_id": document_id,
                "after_line": 2,
                "lines": ["", "## Notes", "- Ship after QA"],
            },
            runtime_state=runtime_state,
        )
        self.assertEqual(insert_summary, "Canvas lines inserted in Release Plan")
        self.assertIn("## Notes", inserted["content"])
        self.assertIn("expected_lines", inserted)
        self.assertEqual(inserted["expected_start_line"], 1)
        self.assertEqual(inserted["expected_lines"][0], "# Release Plan")

        deleted, delete_summary = _execute_tool(
            "delete_canvas_lines",
            {
                "document_id": document_id,
                "start_line": 2,
                "end_line": 2,
            },
            runtime_state=runtime_state,
        )
        self.assertEqual(delete_summary, "Canvas lines deleted in Release Plan")
        self.assertNotIn("", deleted["content"].splitlines()[:1])
        self.assertIn("expected_lines", deleted)
        self.assertEqual(deleted["expected_start_line"], 2)

    def test_canvas_tools_support_code_format(self):
        runtime_state = {}

        created, _ = _execute_tool(
            "create_canvas_document",
            {
                "title": "main.py",
                "content": "print('hello')",
                "format": "code",
                "language": "python",
            },
            runtime_state=runtime_state,
        )

        self.assertEqual(created["format"], "code")
        self.assertEqual(created["language"], "python")

        updated, _ = _execute_tool(
            "rewrite_canvas_document",
            {
                "document_id": created["document_id"],
                "content": "console.log('hello');",
                "format": "code",
                "language": "javascript",
            },
            runtime_state=runtime_state,
        )

        self.assertEqual(updated["format"], "code")
        self.assertEqual(updated["language"], "javascript")

    def test_canvas_tools_delete_and_clear_documents_in_runtime_state(self):
        runtime_state = {}

        created_first, _ = _execute_tool(
            "create_canvas_document",
            {
                "title": "Draft One",
                "content": "# Draft One",
            },
            runtime_state=runtime_state,
        )
        created_second, _ = _execute_tool(
            "create_canvas_document",
            {
                "title": "Draft Two",
                "content": "# Draft Two",
            },
            runtime_state=runtime_state,
        )

        deleted, delete_summary = _execute_tool(
            "delete_canvas_document",
            {"document_id": created_first["document_id"]},
            runtime_state=runtime_state,
        )

        self.assertEqual(delete_summary, "Canvas deleted: Draft One")
        self.assertEqual(deleted["action"], "deleted")
        self.assertEqual(deleted["remaining_count"], 1)

        cleared, clear_summary = _execute_tool(
            "clear_canvas",
            {},
            runtime_state=runtime_state,
        )

        self.assertEqual(clear_summary, "Canvas cleared (1 documents removed)")
        self.assertEqual(cleared["action"], "cleared")
        self.assertEqual(cleared["cleared_count"], 1)
        self.assertEqual(runtime_state["canvas"]["documents"], [])
        self.assertIsNone(runtime_state["canvas"]["active_document_id"])
        self.assertEqual(created_second["title"], "Draft Two")

    def test_workspace_tools_create_read_list_search_update_and_validate(self):
        workspace_root = os.path.join(self.temp_dir.name, "workspace-tools")
        runtime_state = {"workspace": create_workspace_runtime_state(root_path=workspace_root)}

        created_dir, _ = _execute_tool("create_directory", {"path": "demo/tests"}, runtime_state=runtime_state)
        self.assertEqual(created_dir["path"], "demo/tests")

        created_file, _ = _execute_tool(
            "create_file",
            {"path": "demo/app.py", "content": "def main():\n    return 'ok'\n"},
            runtime_state=runtime_state,
        )
        self.assertEqual(created_file["action"], "file_created")

        updated_file, _ = _execute_tool(
            "update_file",
            {"path": "demo/app.py", "content": "def main():\n    return 'updated'\n"},
            runtime_state=runtime_state,
        )
        self.assertEqual(updated_file["action"], "file_updated")

        read_result, _ = _execute_tool(
            "read_file",
            {"path": "demo/app.py", "start_line": 1, "end_line": 2},
            runtime_state=runtime_state,
        )
        self.assertIn("1: def main():", read_result["content"])
        self.assertIn("2:     return 'updated'", read_result["content"])

        list_result, _ = _execute_tool("list_dir", {"path": "demo"}, runtime_state=runtime_state)
        self.assertEqual([entry["path"] for entry in list_result["entries"]], ["demo/tests", "demo/app.py"])

        search_result, _ = _execute_tool(
            "search_files",
            {"query": "updated", "path_prefix": "demo", "search_content": True},
            runtime_state=runtime_state,
        )
        self.assertEqual(search_result["matches"][0]["path"], "demo/app.py")

        validate_result, _ = _execute_tool(
            "validate_project_workspace",
            {"path": "demo"},
            runtime_state=runtime_state,
        )
        self.assertEqual(validate_result["status"], "ok")

    def test_validate_project_workspace_reports_python_project_rule_warnings(self):
        workspace_root = os.path.join(self.temp_dir.name, "validation-rules")
        runtime_state = {"workspace": create_workspace_runtime_state(root_path=workspace_root)}

        written, _ = _execute_tool(
            "write_project_tree",
            {
                "directories": ["demo/src/demo_pkg", "demo/tests"],
                "files": [
                    {"path": "demo/README.md", "content": "# Demo\n"},
                    {"path": "demo/requirements.txt", "content": "requests\n"},
                    {"path": "demo/pyproject.toml", "content": "[project]\nname = 'demo'\nversion = '0.1.0'\n"},
                    {"path": "demo/config.py", "content": "\n"},
                    {"path": "demo/src/demo_pkg/__init__.py", "content": ""},
                    {"path": "demo/src/demo_pkg/main.py", "content": "from .missing import run\n"},
                ],
            },
            runtime_state=runtime_state,
        )
        self.assertEqual(written["status"], "ok")

        validation, _ = _execute_tool(
            "validate_project_workspace",
            {"path": "demo"},
            runtime_state=runtime_state,
        )
        self.assertEqual(validation["status"], "ok")
        self.assertTrue(validation["summary"]["looks_like_python_project"])
        self.assertGreaterEqual(validation["summary"]["warning_count"], 4)
        self.assertIn("Missing expected file: app.py", validation["warnings"])
        self.assertIn("Missing tests directory or test files.", validation["warnings"])
        self.assertIn("config.py is empty.", validation["warnings"])
        self.assertIn("No obvious Python entry point found. Add app.py, main.py, __main__.py, or declare scripts in pyproject.toml.", validation["warnings"])
        self.assertIn("Relative import target is missing in src/demo_pkg/main.py: .missing", validation["warnings"])

    def test_write_project_tree_requires_confirmation_for_overwrites(self):
        workspace_root = os.path.join(self.temp_dir.name, "workspace-project")
        runtime_state = {"workspace": create_workspace_runtime_state(root_path=workspace_root)}

        initial, _ = _execute_tool(
            "write_project_tree",
            {
                "files": [
                    {"path": "demo-app/app.py", "content": "print('v1')\n"},
                    {"path": "demo-app/config.py", "content": "DEBUG = True\n"},
                ]
            },
            runtime_state=runtime_state,
        )
        self.assertEqual(initial["status"], "ok")

        overwrite_preview, _ = _execute_tool(
            "write_project_tree",
            {
                "files": [
                    {"path": "demo-app/app.py", "content": "print('rewrite')\n"},
                    {"path": "demo-app/config.py", "content": "SETTINGS = {'debug': True}\n"},
                ]
            },
            runtime_state=runtime_state,
        )
        self.assertEqual(overwrite_preview["status"], "needs_confirmation")
        self.assertIn("demo-app/app.py", overwrite_preview["overwrites"])
        self.assertIn("--- a/demo-app/app.py", overwrite_preview["diffs"][0]["diff"])

        applied, _ = _execute_tool(
            "write_project_tree",
            {
                "files": [
                    {"path": "demo-app/app.py", "content": "print('rewrite')\n"},
                    {"path": "demo-app/config.py", "content": "SETTINGS = {'debug': True}\n"},
                ],
                "confirm": True,
            },
            runtime_state=runtime_state,
        )
        self.assertEqual(applied["status"], "ok")

    def test_hidden_workspace_history_is_not_listed_or_searched(self):
        workspace_root = os.path.join(self.temp_dir.name, "workspace-hidden-history")
        runtime_state = {"workspace": create_workspace_runtime_state(root_path=workspace_root)}

        _execute_tool(
            "create_file",
            {"path": "demo/app.py", "content": "print('v1')\n"},
            runtime_state=runtime_state,
        )
        _execute_tool(
            "update_file",
            {"path": "demo/app.py", "content": "print('v2')\n"},
            runtime_state=runtime_state,
        )

        listed, _ = _execute_tool("list_dir", {}, runtime_state=runtime_state)
        self.assertEqual([entry["path"] for entry in listed["entries"]], ["demo"])

        searched, _ = _execute_tool(
            "search_files",
            {"query": ".workspace-history", "search_content": True},
            runtime_state=runtime_state,
        )
        self.assertEqual(searched["matches"], [])

    def test_expand_canvas_document_tool_returns_line_numbered_context(self):
        runtime_state = {"canvas": create_canvas_runtime_state([
            {
                "id": "canvas-1",
                "title": "app.py",
                "path": "src/app.py",
                "role": "source",
                "format": "code",
                "language": "python",
                "content": "import os\n\nprint('hello')",
                "imports": ["os"],
                "symbols": ["main"],
            },
            {
                "id": "canvas-2",
                "title": "config.py",
                "path": "src/config.py",
                "role": "config",
                "format": "code",
                "language": "python",
                "content": "DEBUG = True",
                "exports": ["DEBUG"],
            },
        ], active_document_id="canvas-2")}

        expanded, summary = _execute_tool(
            "expand_canvas_document",
            {"document_path": "src/app.py"},
            runtime_state=runtime_state,
        )

        self.assertEqual(summary, "Canvas expanded: src/app.py")
        self.assertEqual(expanded["action"], "expanded")
        self.assertEqual(expanded["document_path"], "src/app.py")
        self.assertEqual(expanded["visible_lines"][0], "1: import os")
        self.assertEqual(expanded["visible_lines"][2], "3: print('hello')")
        self.assertEqual(expanded["snapshot_semantics"], "call_time")
        self.assertIn("call-time snapshot", expanded["snapshot_notice"])
        self.assertIn("re-run expand_canvas_document", expanded["snapshot_notice"])
        self.assertEqual(expanded["manifest_excerpt"]["active_file"], "src/config.py")
        self.assertIn("os", expanded["relationship_map"]["imports"])

    def test_expand_canvas_document_accepts_title_as_document_path(self):
        runtime_state = {"canvas": create_canvas_runtime_state([
            {
                "id": "canvas-arduino",
                "title": "Arduino Kodu - RobotBeyni.ino",
                "role": "source",
                "format": "code",
                "language": "cpp",
                "content": "int led = 13;\nvoid setup() {}",
            }
        ])}

        expanded, summary = _execute_tool(
            "expand_canvas_document",
            {"document_path": "Arduino Kodu - RobotBeyni.ino"},
            runtime_state=runtime_state,
        )

        self.assertEqual(summary, "Canvas expanded: Arduino Kodu - RobotBeyni.ino")
        self.assertEqual(expanded["title"], "Arduino Kodu - RobotBeyni.ino")
        self.assertEqual(expanded["visible_lines"], ["1: int led = 13;", "2: void setup() {}"])

    def test_expand_canvas_document_accepts_unique_basename_as_document_path(self):
        runtime_state = {"canvas": create_canvas_runtime_state([
            {
                "id": "canvas-arduino",
                "title": "Arduino Kodu - RobotBeyni.ino",
                "path": "projects/robot/Arduino Kodu - RobotBeyni.ino",
                "role": "source",
                "format": "code",
                "language": "cpp",
                "content": "int led = 13;\nvoid loop() {}",
            }
        ])}

        expanded, summary = _execute_tool(
            "expand_canvas_document",
            {"document_path": "Arduino Kodu - RobotBeyni.ino"},
            runtime_state=runtime_state,
        )

        self.assertEqual(summary, "Canvas expanded: projects/robot/Arduino Kodu - RobotBeyni.ino")
        self.assertEqual(expanded["document_path"], "projects/robot/Arduino Kodu - RobotBeyni.ino")
        self.assertEqual(expanded["visible_lines"], ["1: int led = 13;", "2: void loop() {}"])

    def test_chat_image_upload_persists_image_asset_and_metadata(self):
        conversation_id = self._create_conversation()
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("db.IMAGE_STORAGE_DIR", self.image_storage_dir), patch("routes.chat.IMAGE_UPLOADS_ENABLED", True), patch(
            "routes.chat.analyze_uploaded_image",
            return_value={
                "analysis_method": "llm_helper",
                "ocr_text": "hello",
                "vision_summary": "A login screen is shown.",
                "assistant_guidance": "Use the labels and values when answering.",
                "key_points": ["Email field", "Password field"],
            },
        ), patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                data={
                    "messages": json.dumps([{"role": "user", "content": "Bu görsel ne anlatıyor?"}]),
                    "model": "deepseek-chat",
                    "conversation_id": str(conversation_id),
                    "user_content": "Bu görsel ne anlatıyor?",
                    "image": (io.BytesIO(b"fake image bytes"), "screen.png", "image/png"),
                },
            )

        self.assertEqual(response.status_code, 200)
        response.get_data(as_text=True)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        user_messages = [message for message in messages if message["role"] == "user"]
        self.assertEqual(len(user_messages), 1)

        metadata = user_messages[0]["metadata"]
        self.assertIn("image_id", metadata)
        self.assertEqual(metadata["image_name"], "screen.png")
        self.assertEqual(metadata["analysis_method"], "llm_helper")
        self.assertEqual(metadata["vision_summary"], "A login screen is shown.")

        asset = get_image_asset(metadata["image_id"], conversation_id=conversation_id)
        self.assertIsNotNone(asset)
        self.assertEqual(asset["filename"], "screen.png")
        self.assertEqual(asset["message_id"], user_messages[0]["id"])
        self.assertEqual(asset["initial_analysis"]["analysis_method"], "llm_helper")
        self.assertTrue(Path(asset["storage_path"]).is_file())

    def test_chat_mixed_multi_attachment_upload_persists_assets_and_canvas_documents(self):
        conversation_id = self._create_conversation()
        captured = {}

        def fake_run_agent_stream(*args, **kwargs):
            captured["initial_canvas_documents"] = kwargs.get("initial_canvas_documents") or []
            return iter([{"type": "done"}])

        with patch("db.IMAGE_STORAGE_DIR", self.image_storage_dir), patch("routes.chat.IMAGE_UPLOADS_ENABLED", True), patch(
            "routes.chat.analyze_uploaded_image",
            side_effect=[
                {
                    "ocr_text": "alpha",
                    "vision_summary": "First screen.",
                    "assistant_guidance": "Use alpha.",
                    "key_points": ["A"],
                },
                {
                    "ocr_text": "beta",
                    "vision_summary": "Second screen.",
                    "assistant_guidance": "Use beta.",
                    "key_points": ["B"],
                },
            ],
        ), patch("routes.chat.run_agent_stream", side_effect=fake_run_agent_stream):
            response = self.client.post(
                "/chat",
                data=MultiDict(
                    [
                        ("messages", json.dumps([{"role": "user", "content": "Review everything"}])),
                        ("model", "deepseek-chat"),
                        ("conversation_id", str(conversation_id)),
                        ("user_content", "Review everything"),
                        ("image", (io.BytesIO(b"image-a"), "screen-a.png", "image/png")),
                        ("image", (io.BytesIO(b"image-b"), "screen-b.png", "image/png")),
                        ("document", (io.BytesIO(b"Doc A"), "notes-a.txt", "text/plain")),
                        ("document", (io.BytesIO(b"Doc B"), "notes-b.txt", "text/plain")),
                    ]
                ),
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        self.assertEqual(len([event for event in events if event["type"] == "vision_complete"]), 2)
        self.assertEqual(len([event for event in events if event["type"] == "document_processed"]), 2)
        canvas_event = next((event for event in events if event["type"] == "canvas_sync"), None)
        self.assertIsNotNone(canvas_event)
        self.assertEqual(len(canvas_event["documents"]), 2)
        self.assertEqual([doc["title"] for doc in canvas_event["documents"]], ["notes-a.txt", "notes-b.txt"])

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        user_messages = [message for message in messages if message["role"] == "user"]
        self.assertEqual(len(user_messages), 1)

        metadata = user_messages[0]["metadata"]
        attachments = metadata.get("attachments") or []
        self.assertEqual(len(attachments), 4)
        self.assertEqual(len([entry for entry in attachments if entry["kind"] == "image"]), 2)
        self.assertEqual(len([entry for entry in attachments if entry["kind"] == "document"]), 2)

        for attachment in attachments:
            if attachment["kind"] == "image":
                asset = get_image_asset(attachment["image_id"], conversation_id=conversation_id)
                self.assertIsNotNone(asset)
                self.assertEqual(asset["message_id"], user_messages[0]["id"])
                continue
            asset = get_file_asset(attachment["file_id"], conversation_id=conversation_id)
            self.assertIsNotNone(asset)
            self.assertEqual(asset["message_id"], user_messages[0]["id"])

    def test_chat_youtube_transcript_attachment_persists_and_reaches_prompt(self):
        conversation_id = self._create_conversation()
        captured = {}

        def fake_run_agent_stream(api_messages, *args, **kwargs):
            captured["api_messages"] = api_messages
            return iter([{"type": "done"}])

        with patch("routes.chat.YOUTUBE_TRANSCRIPTS_ENABLED", True), patch(
            "routes.chat.read_youtube_video_reference",
            return_value=("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ), patch(
            "routes.chat.transcribe_youtube_video",
            return_value={
                "platform": "youtube",
                "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "source_video_id": "dQw4w9WgXcQ",
                "title": "Demo Video",
                "duration_seconds": 93,
                "transcript_text": "Hello from the transcript. This is the main point.",
                "transcript_language": "en",
            },
        ), patch("routes.chat.run_agent_stream", side_effect=fake_run_agent_stream):
            response = self.client.post(
                "/chat",
                json={
                    "messages": [{"role": "user", "content": "Summarize this video"}],
                    "model": "deepseek-chat",
                    "conversation_id": conversation_id,
                    "user_content": "Summarize this video",
                    "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        video_event = next((event for event in events if event["type"] == "video_transcript_ready"), None)
        self.assertIsNotNone(video_event)
        self.assertEqual(video_event["video_title"], "Demo Video")

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        user_messages = [message for message in messages if message["role"] == "user"]
        self.assertEqual(len(user_messages), 1)

        metadata = user_messages[0]["metadata"]
        attachments = metadata.get("attachments") or []
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["kind"], "video")
        self.assertEqual(attachments[0]["video_title"], "Demo Video")
        self.assertIn("Hello from the transcript", attachments[0]["transcript_context_block"])

        asset = get_video_asset(attachments[0]["video_id"], conversation_id=conversation_id)
        self.assertIsNotNone(asset)
        self.assertEqual(asset["message_id"], user_messages[0]["id"])
        self.assertEqual(asset["title"], "Demo Video")

        user_prompt_messages = [message for message in captured.get("api_messages", []) if message.get("role") == "user"]
        self.assertTrue(any("[YouTube video transcript: Demo Video]" in str(message.get("content") or "") for message in user_prompt_messages))

    def test_chat_rejects_invalid_youtube_url(self):
        conversation_id = self._create_conversation()

        with patch("routes.chat.YOUTUBE_TRANSCRIPTS_ENABLED", True), patch(
            "routes.chat.read_youtube_video_reference",
            side_effect=ValueError("Enter a valid YouTube URL."),
        ):
            response = self.client.post(
                "/chat",
                json={
                    "messages": [{"role": "user", "content": "Check this"}],
                    "model": "deepseek-chat",
                    "conversation_id": conversation_id,
                    "user_content": "Check this",
                    "youtube_url": "https://example.com/not-youtube",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("YouTube", response.get_json()["error"])

    def test_extract_youtube_video_id_rejects_lookalike_host(self):
        from video_transcript_service import extract_youtube_video_id

        self.assertIsNone(extract_youtube_video_id("https://notyoutube.com/watch?v=dQw4w9WgXcQ"))

    def test_delete_conversation_removes_persisted_video_assets(self):
        conversation_id = self._create_conversation()
        asset = create_video_asset(
            conversation_id,
            source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            source_video_id="dQw4w9WgXcQ",
            title="Demo Video",
            transcript_text="Transcript body",
            transcript_language="en",
            duration_seconds=93,
        )

        response = self.client.delete(f"/api/conversations/{conversation_id}")

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(get_video_asset(asset["video_id"], conversation_id=conversation_id))

    def test_delete_conversation_reverts_global_state_and_deletes_workspace(self):
        conversation_id = self._create_conversation()
        workspace_root = os.path.join(self.temp_dir.name, "conversation-delete-workspace")
        os.makedirs(workspace_root, exist_ok=True)
        workspace_file = os.path.join(workspace_root, "state.txt")
        with open(workspace_file, "w", encoding="utf-8") as fh:
            fh.write("workspace state")

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "Conversation prompt")
            assistant_message_id = insert_message(conn, conversation_id, "assistant", "Conversation answer")

        append_to_scratchpad(
            "Conversation scoped scratchpad",
            conversation_id=conversation_id,
            source_message_id=assistant_message_id,
        )
        upsert_user_profile_entry(
            "fact:conversation-delete",
            "delete me",
            confidence=0.8,
            source="test",
            conversation_id=conversation_id,
            source_message_id=assistant_message_id,
        )

        with patch(
            "conversation_cleanup_service.get_workspace_root_for_conversation",
            return_value=workspace_root,
        ), patch("routes.conversations.purge_conversation_rag_sources") as mocked_purge:
            response = self.client.delete(f"/api/conversations/{conversation_id}")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(os.path.exists(workspace_root))
        self.assertNotIn("Conversation scoped scratchpad", get_all_scratchpad_sections(get_app_settings()).get("notes", ""))
        self.assertNotIn("fact:conversation-delete", {entry["key"] for entry in get_user_profile_entries()})
        self.assertEqual(self.client.get(f"/api/conversations/{conversation_id}").status_code, 404)
        mocked_purge.assert_called_once_with(conversation_id, include_archived=True)

    def test_delete_conversation_purges_rag_sources_even_when_rag_is_disabled(self):
        conversation_id = self._create_conversation()

        with patch("routes.conversations.RAG_ENABLED", False), patch(
            "routes.conversations.purge_conversation_rag_sources"
        ) as mocked_purge:
            response = self.client.delete(f"/api/conversations/{conversation_id}")

        self.assertEqual(response.status_code, 204)
        mocked_purge.assert_called_once_with(conversation_id, include_archived=True)

    def test_delete_conversation_continues_when_rag_cleanup_fails(self):
        conversation_id = self._create_conversation()

        with patch(
            "routes.conversations.purge_conversation_rag_sources",
            side_effect=RuntimeError("cleanup failed"),
        ):
            response = self.client.delete(f"/api/conversations/{conversation_id}")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get(f"/api/conversations/{conversation_id}").status_code, 404)

    def test_delete_conversation_removes_persisted_image_files(self):
        conversation_id = self._create_conversation()

        with patch("db.IMAGE_STORAGE_DIR", self.image_storage_dir):
            asset = create_image_asset(conversation_id, "screen.png", "image/png", b"raw bytes")
            self.assertTrue(Path(asset["storage_path"]).is_file())

            response = self.client.delete(f"/api/conversations/{conversation_id}")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Path(asset["storage_path"]).exists())

    def test_external_app_script_exists_and_contains_bootstrap_reader(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        self.assertTrue(script_path.exists())
        script_text = script_path.read_text(encoding="utf-8")
        self.assertIn('document.getElementById("app-bootstrap")', script_text)
        self.assertIn("globalThis.marked", script_text)
        self.assertIn("function renderMarkdown", script_text)
        self.assertIn("INPUT_BREAKDOWN_ORDER", script_text)
        self.assertIn("loadSidebar()", script_text)
        self.assertIn('const editBanner = document.getElementById("edit-banner")', script_text)
        self.assertIn('const editedMessageId = isEditing ? Number(editingEntry.id) : null;', script_text)
        self.assertIn('edited_message_id: editedMessageId', script_text)
        self.assertIn('formData.append("edited_message_id", String(editedMessageId));', script_text)
        self.assertIn('document_canvas_action: documentCanvasAction,', script_text)
        self.assertIn("clearEditTarget();", script_text)
        self.assertIn("function isEditableHistoryMessage(message)", script_text)
        self.assertIn("function createInlineMessageEditor(message)", script_text)
        self.assertIn("function getExistingDocumentAttachmentsForCanvasPrompt(message)", script_text)
        self.assertIn("function saveEditedHistoryMessage(messageId, nextContent, options = {})", script_text)
        self.assertIn("function createMessageActions(message, options = {})", script_text)
        self.assertIn("Save and Send", script_text)
        self.assertIn("Copy message", script_text)
        self.assertIn("Copy as Markdown", script_text)
        self.assertIn('editable: message.role === "user" || message.role === "assistant"', script_text)
        self.assertIn('method: "PATCH"', script_text)
        self.assertIn('body: JSON.stringify({', script_text)
        self.assertIn('`/api/messages/${messageId}`', script_text)
        self.assertIn("const fragment = document.createDocumentFragment();", script_text)
        self.assertIn("messagesEl.replaceChildren(fragment);", script_text)
        self.assertIn("function isPersistedMessageId(messageId)", script_text)
        self.assertIn("function isCanvasStreamingPreviewTool(toolName)", script_text)
        self.assertIn("isCanvasStreamingPreviewTool(event.tool)", script_text)

        style_path = Path(__file__).resolve().parent.parent / "static" / "style.css"
        style_text = style_path.read_text(encoding="utf-8")
        self.assertIn(".message-inline-editor", style_text)
        self.assertIn(".message-inline-editor__input", style_text)
        self.assertIn(".message-inline-editor__actions", style_text)

    def test_external_settings_script_exists_and_contains_tabbed_settings_logic(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "settings.js"
        self.assertTrue(script_path.exists())
        script_text = script_path.read_text(encoding="utf-8")
        self.assertIn('document.getElementById("app-bootstrap")', script_text)
        self.assertIn("function activateTab", script_text)
        self.assertIn("function applyConditionalSectionState", script_text)
        self.assertIn("void loadKnowledgeBaseDocuments();", script_text)
        self.assertIn("void refreshSettings();", script_text)
        self.assertIn("window.addEventListener(\"beforeunload\"", script_text)

    def test_reasoning_panel_uses_markdown_rendering(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        self.assertIn('body.innerHTML = renderReasoning(text);', script_text)

    def test_reasoning_panel_stays_open_when_stream_finishes(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        self.assertIn('updateReasoningPanel(asstGroup, getReasoningText(metadata), { forceOpen: true });', script_text)
        self.assertNotIn('updateReasoningPanel(asstGroup, getReasoningText(metadata), { autoCollapse: true });', script_text)

    def test_reasoning_is_restored_from_session_cache_after_refresh(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        self.assertIn("assistant-reasoning:", script_text)
        self.assertIn("saveAssistantReasoning(currentConvId, persistedMessageIds?.assistant_message_id || assistantEntry.id, rawReasoning);", script_text)
        self.assertIn("updateReasoningPanel(group, getReasoningText(metadata, options.messageId));", script_text)

    def test_conversation_export_posts_cached_reasoning_from_frontend(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        self.assertIn("function collectConversationReasoningExportMap(entries = history, conversationId = currentConvId)", script_text)
        self.assertIn('body: JSON.stringify({ reasoning_by_message_id: reasoningByMessageId })', script_text)
        self.assertIn('method: "POST"', script_text)

    def test_raw_json_conversation_export_button_is_wired_from_frontend(self):
        template_path = Path(__file__).resolve().parent.parent / "templates" / "index.html"
        template_text = template_path.read_text(encoding="utf-8")
        self.assertIn('id="conversation-export-json-btn"', template_text)
        self.assertIn("Download raw .json", template_text)

        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        self.assertIn('const conversationExportJsonBtn = document.getElementById("conversation-export-json-btn");', script_text)
        self.assertIn('conversationExportJsonBtn.addEventListener("click", () => downloadConversation("json"));', script_text)

    def test_reasoning_css_includes_markdown_styles(self):
        style_path = Path(__file__).resolve().parent.parent / "static" / "style.css"
        style_text = style_path.read_text(encoding="utf-8")
        self.assertIn(".reasoning-body code", style_text)
        self.assertIn(".reasoning-body ul", style_text)

    def test_sub_agent_css_includes_markdown_styles(self):
        style_path = Path(__file__).resolve().parent.parent / "static" / "style.css"
        style_text = style_path.read_text(encoding="utf-8")
        self.assertIn(".sub-agent-markdown table", style_text)
        self.assertIn(".sub-agent-run__instructions", style_text)

    def test_truncate_preview_text_marks_continuation_with_ascii_ellipsis(self):
        self.assertEqual(_truncate_preview_text("abcdef", limit=4), "abcd...")
        self.assertEqual(_truncate_preview_text("abc", limit=4), "abc")

    def test_estimate_message_breakdown_splits_runtime_system_sections(self):
        message = build_runtime_system_message(
            active_tool_names=["search_web", "search_knowledge_base", "search_tool_memory", "append_scratchpad"],
            retrieved_context={
                "query": "alpha",
                "count": 1,
                "matches": [
                    {
                        "source_name": "Alpha notes",
                        "similarity": 0.91,
                        "text": "Alpha knowledge block",
                    }
                ],
            },
            tool_trace_context="search_web -> returned 3 results",
            tool_memory_context="Stored page snapshot",
            scratchpad="Remember the preferred deployment region.",
            canvas_documents=[
                {
                    "id": "doc-1",
                    "title": "spec.md",
                    "content": "line one\nline two",
                    "format": "markdown",
                    "language": "markdown",
                }
            ],
        )

        breakdown = _estimate_message_breakdown(message)
        self.assertGreater(breakdown["core_instructions"], 0)
        self.assertGreater(breakdown["canvas"], 0)
        self.assertGreater(breakdown["scratchpad"], 0)
        self.assertGreater(breakdown["tool_trace"], 0)
        self.assertGreater(breakdown["tool_memory"], 0)
        self.assertNotIn("tool_specs", breakdown)
        self.assertNotIn("Available Tools", message["content"])
        self.assertGreater(sum(breakdown.values()), estimate_text_tokens(message["content"]))

    def test_estimate_input_breakdown_counts_native_tool_schemas(self):
        message = build_runtime_system_message(active_tool_names=["search_web"])
        request_tools = get_openai_tool_specs(["search_web"])

        breakdown, _total_tokens, tool_schema_tokens = _estimate_input_breakdown(
            [message, {"role": "user", "content": "Find the release notes."}],
            request_tools=request_tools,
        )

        self.assertNotIn("Available Tools", message["content"])
        self.assertGreater(tool_schema_tokens, 0)
        self.assertEqual(breakdown["tool_specs"], tool_schema_tokens)

    def test_estimate_input_breakdown_includes_message_wrapper_overhead(self):
        message = {"role": "user", "content": "Find the release notes."}

        breakdown, _total_tokens, _tool_schema_tokens = _estimate_input_breakdown([message])

        self.assertGreater(breakdown["user_messages"], estimate_text_tokens(message["content"]))

    def test_estimate_message_breakdown_classifies_canvas_workspace_sections_as_canvas(self):
        content = "\n".join(
            [
                "## Canvas File Set Summary",
                "- Active file: src/app.py",
                "",
                "## Canvas Editing Guidance",
                "- Prefer the smallest valid edit.",
                "",
                "## Canvas Decision Matrix",
                "| Situation | Preferred tool | Notes |",
                "| --- | --- | --- |",
                "| Need a draft | create_canvas_document | Create an artifact. |",
            ]
        )

        breakdown = _estimate_message_breakdown({"role": "system", "content": content})

        self.assertIn("canvas", breakdown)
        self.assertGreater(breakdown["canvas"], estimate_text_tokens(content))
        self.assertLessEqual(breakdown.get("core_instructions", 0), 2)

    def test_resolve_runtime_tool_names_without_user_message_always_includes_web_tools(self):
        # When user_message is not provided (the main chat path), intent filtering is
        # skipped and all active tools except canvas-document tools (no canvas present)
        # are always sent to the model.
        runtime_names = resolve_runtime_tool_names(
            [
                "append_scratchpad",
                "search_web",
                "fetch_url",
                "fetch_url_to_canvas",
                "search_news_ddgs",
                "read_file",
                "create_canvas_document",
            ],
            workspace_root="/tmp/workspace",
        )

        self.assertEqual(
            runtime_names,
            ["append_scratchpad", "search_web", "fetch_url", "fetch_url_to_canvas", "search_news_ddgs", "read_file", "create_canvas_document"],
        )

    def test_resolve_runtime_tool_names_without_user_message_excludes_workspace_tools_when_no_root(self):
        # Workspace tools are excluded when workspace_root is not set, regardless of message.
        runtime_names = resolve_runtime_tool_names(
            [
                "read_file",
                "list_dir",
                "create_file",
                "search_web",
                "create_canvas_document",
            ],
        )

        self.assertEqual(runtime_names, ["search_web", "create_canvas_document"])

    def test_get_openai_tool_specs_include_workspace_tools_only_with_workspace_root(self):
        tools_with_workspace = get_openai_tool_specs(
            ["read_file", "list_dir", "search_web"],
            workspace_root="/tmp/workspace-root",
        )
        tools_without_workspace = get_openai_tool_specs(["read_file", "list_dir", "search_web"])

        self.assertEqual(
            [entry["function"]["name"] for entry in tools_with_workspace],
            ["search_web", "read_file", "list_dir"],
        )
        self.assertEqual(
            [entry["function"]["name"] for entry in tools_without_workspace],
            ["search_web"],
        )

    def test_run_agent_stream_exposes_workspace_tools_to_model_only_when_workspace_root_exists(self):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        reasoning_content="",
                        content="Done.",
                        tool_calls=[],
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=2, total_tokens=4),
        )

        workspace_runtime_state = create_workspace_runtime_state(
            root_path=os.path.join(self.temp_dir.name, "agent-workspace"),
        )

        with patch("agent.client.chat.completions.create", return_value=response) as mocked_create:
            list(
                run_agent_stream(
                    [{"role": "user", "content": "Inspect the workspace."}],
                    "deepseek-chat",
                    1,
                    ["read_file", "search_web"],
                    workspace_runtime_state=workspace_runtime_state,
                )
            )

        self.assertIn("tools", mocked_create.call_args.kwargs)
        self.assertEqual(
            [entry["function"]["name"] for entry in mocked_create.call_args.kwargs["tools"]],
            ["search_web", "read_file"],
        )

        with patch("agent.client.chat.completions.create", return_value=response) as mocked_create_without_workspace:
            list(
                run_agent_stream(
                    [{"role": "user", "content": "Inspect the workspace."}],
                    "deepseek-chat",
                    1,
                    ["read_file", "search_web"],
                    workspace_runtime_state=create_workspace_runtime_state(),
                )
            )

        self.assertEqual(
            [entry["function"]["name"] for entry in mocked_create_without_workspace.call_args.kwargs["tools"]],
            ["search_web"],
        )

    def test_resolve_runtime_tool_names_keeps_canvas_tools_when_canvas_documents_exist(self):
        runtime_names = resolve_runtime_tool_names(
            [
                "create_canvas_document",
                "search_canvas_document",
                "preview_canvas_changes",
                "set_canvas_viewport",
                "rewrite_canvas_document",
                "replace_canvas_lines",
            ],
            canvas_documents=[
                {
                    "id": "canvas-1",
                    "title": "draft.md",
                    "format": "markdown",
                    "content": "hello",
                }
            ],
        )

        self.assertEqual(
            runtime_names,
            ["create_canvas_document", "search_canvas_document", "preview_canvas_changes", "set_canvas_viewport", "rewrite_canvas_document", "replace_canvas_lines"],
        )

    def test_resolve_runtime_tool_names_hides_text_canvas_tools_for_visual_only_documents(self):
        runtime_names = resolve_runtime_tool_names(
            [
                "create_canvas_document",
                "expand_canvas_document",
                "search_canvas_document",
                "set_canvas_viewport",
                "update_canvas_metadata",
                "focus_canvas_page",
                "delete_canvas_document",
            ],
            canvas_documents=[
                {
                    "id": "canvas-visual",
                    "title": "scan.pdf",
                    "format": "markdown",
                    "content": "# scan.pdf",
                    "content_mode": "visual",
                    "canvas_mode": "preview_only",
                    "page_count": 3,
                }
            ],
        )

        self.assertEqual(
            runtime_names,
            ["create_canvas_document", "delete_canvas_document"],
        )

    def test_extract_message_usage_maps_legacy_system_prompt_breakdown(self):
        usage = extract_message_usage(
            {
                "usage": {
                    "estimated_input_tokens": 4,
                    "input_breakdown": {
                        "system_prompt": 4,
                    },
                }
            }
        )

        self.assertEqual(usage["input_breakdown"]["core_instructions"], 4)
        self.assertNotIn("system_prompt", usage["input_breakdown"])

    def test_extract_message_usage_adds_unknown_overhead_to_match_prompt_tokens(self):
        usage = extract_message_usage(
            {
                "usage": {
                    "prompt_tokens": 12,
                    "estimated_input_tokens": 6,
                    "input_breakdown": {
                        "system_prompt": 4,
                        "user_messages": 2,
                    },
                }
            }
        )

        self.assertEqual(usage["estimated_input_tokens"], 12)
        self.assertEqual(usage["input_breakdown"]["core_instructions"], 4)
        self.assertEqual(usage["input_breakdown"]["user_messages"], 2)
        self.assertEqual(usage["input_breakdown"]["unknown_provider_overhead"], 6)

    def test_extract_message_usage_preserves_peak_input_and_prompt_cap(self):
        usage = extract_message_usage(
            {
                "usage": {
                    "prompt_tokens": 12,
                    "max_input_tokens_per_call": 7,
                    "configured_prompt_max_input_tokens": 100000,
                }
            }
        )

        self.assertEqual(usage["prompt_tokens"], 12)
        self.assertEqual(usage["max_input_tokens_per_call"], 7)
        self.assertEqual(usage["configured_prompt_max_input_tokens"], 100000)

    def test_extract_message_usage_preserves_deepseek_cache_token_counts(self):
        usage = extract_message_usage(
            {
                "usage": {
                    "prompt_tokens": 12,
                    "prompt_cache_hit_tokens": 5,
                    "prompt_cache_miss_tokens": 7,
                }
            }
        )

        self.assertEqual(usage["prompt_tokens"], 12)
        self.assertEqual(usage["prompt_cache_hit_tokens"], 5)
        self.assertEqual(usage["prompt_cache_miss_tokens"], 7)

    def test_extract_message_usage_preserves_cache_estimation_flags(self):
        usage = extract_message_usage(
            {
                "usage": {
                    "prompt_tokens": 12,
                    "prompt_cache_hit_tokens": 5,
                    "prompt_cache_miss_tokens": 7,
                    "cache_metrics_estimated": True,
                    "model_calls": [
                        {
                            "index": 1,
                            "estimated_input_tokens": 12,
                            "prompt_cache_hit_tokens": 5,
                            "prompt_cache_miss_tokens": 7,
                            "cache_metrics_estimated": True,
                        }
                    ],
                }
            }
        )

        self.assertTrue(usage["cache_metrics_estimated"])
        self.assertTrue(usage["model_calls"][0]["cache_metrics_estimated"])

    def test_extract_message_usage_preserves_provider_and_pricing_availability(self):
        usage = extract_message_usage(
            {
                "usage": {
                    "prompt_tokens": 12,
                    "cost_available": False,
                    "currency": "USD",
                    "provider": "openrouter",
                    "model": "openrouter:anthropic/claude-sonnet-4.5",
                }
            }
        )

        self.assertEqual(usage["prompt_tokens"], 12)
        self.assertFalse(usage["cost_available"])
        self.assertEqual(usage["currency"], "USD")
        self.assertEqual(usage["provider"], "openrouter")
        self.assertEqual(usage["model"], "openrouter:anthropic/claude-sonnet-4.5")

    def test_extract_message_usage_preserves_partial_provider_usage_flag(self):
        usage = extract_message_usage(
            {
                "usage": {
                    "estimated_input_tokens": 18,
                    "provider_usage_partial": True,
                    "model_calls": [
                        {
                            "index": 1,
                            "estimated_input_tokens": 18,
                            "missing_provider_usage": True,
                        }
                    ],
                }
            }
        )

        self.assertTrue(usage["provider_usage_partial"])
        self.assertTrue(usage["model_calls"][0]["missing_provider_usage"])

    def test_extract_usage_metrics_normalizes_openrouter_prompt_tokens_details(self):
        # OpenRouter returns cached_tokens inside prompt_tokens_details
        usage = SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=50,
            total_tokens=1050,
            prompt_cache_hit_tokens=None,
            prompt_cache_miss_tokens=None,
            model_extra={
                "prompt_tokens_details": {"cached_tokens": 800, "cache_write_tokens": 0}
            },
        )
        metrics = _extract_usage_metrics(usage)
        self.assertEqual(metrics["prompt_tokens"], 1000)
        self.assertEqual(metrics["prompt_cache_hit_tokens"], 800)

    def test_extract_usage_metrics_normalizes_openrouter_cache_write_tokens(self):
        usage = SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=50,
            total_tokens=1050,
            prompt_cache_hit_tokens=None,
            prompt_cache_miss_tokens=None,
            model_extra={
                "prompt_tokens_details": {"cached_tokens": 800, "cache_write_tokens": 120}
            },
        )

        metrics = _extract_usage_metrics(usage)

        self.assertEqual(metrics["prompt_cache_write_tokens"], 120)
        self.assertTrue(metrics["cache_write_present"])

    def test_extract_usage_metrics_prefers_deepseek_field_over_prompt_tokens_details(self):
        # When DeepSeek's native field is already present, it takes priority
        usage = SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=50,
            total_tokens=1050,
            prompt_cache_hit_tokens=600,
            prompt_cache_miss_tokens=400,
            model_extra={
                "prompt_tokens_details": {"cached_tokens": 999}
            },
        )
        metrics = _extract_usage_metrics(usage)
        self.assertEqual(metrics["prompt_cache_hit_tokens"], 600)

    def test_extract_usage_metrics_marks_openrouter_cache_field_presence(self):
        usage = SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=50,
            total_tokens=1050,
            prompt_cache_hit_tokens=None,
            prompt_cache_miss_tokens=None,
            model_extra={
                "prompt_tokens_details": {"cached_tokens": 800}
            },
        )

        metrics = _extract_usage_metrics(usage)

        self.assertTrue(metrics["cache_hit_present"])
        self.assertFalse(metrics["cache_miss_present"])

    def test_summarize_model_call_usage_reports_peak_single_call_input(self):
        summary = _summarize_model_call_usage(
            [
                {"prompt_tokens": 48000, "estimated_input_tokens": 48000},
                {"estimated_input_tokens": 61000},
                {"prompt_tokens": 52000, "estimated_input_tokens": 52000},
            ]
        )

        self.assertEqual(summary["max_input_tokens_per_call"], 61000)

    def test_frontend_restores_persistent_tool_trace_panel(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        style_path = Path(__file__).resolve().parent.parent / "static" / "style.css"
        style_text = style_path.read_text(encoding="utf-8")
        self.assertIn("function updateAssistantToolTrace(group, metadata)", script_text)
        self.assertIn("tool_trace: assistantToolTrace", script_text)
        self.assertIn("function updateAssistantSubAgentTrace(group, metadata)", script_text)
        self.assertIn("sub_agent_traces: assistantSubAgentTraces", script_text)
        self.assertIn('assistant_sub_agent_trace_update', script_text)
        self.assertIn('fallback_note', script_text)
        self.assertIn('task_full: String(entry.task_full || "").trim()', script_text)
        self.assertIn('sub-agent-run__note', script_text)
        self.assertIn('sub-agent-run__instructions-body', script_text)
        self.assertIn('Should the research be saved to the Canvas?', script_text)
        self.assertIn('summaryText !== fallbackNote', script_text)
        self.assertIn("function createAssistantMessageActions(message)", script_text)
        self.assertIn("Edit message", script_text)
        self.assertIn("Regenerate reply", script_text)
        self.assertIn("msg-action-btn--icon", style_text)
        self.assertIn("msg-actions--footer", style_text)
        self.assertIn("msg-group.user .msg-actions--footer", style_text)
        self.assertNotIn('openBtn.textContent = "Open canvas";', script_text)

    def test_usage_panel_exposes_cache_hit_and_miss_metrics(self):
        html_text = self.client.get("/").get_data(as_text=True)
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn("Token Usage", html_text)
        self.assertIn('id="stat-cache-hit"', html_text)
        self.assertIn('id="stat-cache-miss"', html_text)
        self.assertIn('id="stat-last-cache-hit"', html_text)
        self.assertIn('id="stat-last-cache-miss"', html_text)
        self.assertIn('id="stat-cost"', html_text)
        self.assertIn('id="stat-last-cost"', html_text)
        self.assertIn("prompt_cache_hit_tokens", script_text)
        self.assertIn("prompt_cache_miss_tokens", script_text)
        self.assertIn("cache_metrics_estimated", script_text)
        self.assertIn("cost_available", script_text)
        self.assertIn("formatUsageCost", script_text)

    def test_frontend_exposes_delete_and_clipboard_fallback_hooks(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        style_path = Path(__file__).resolve().parent.parent / "static" / "style.css"
        style_text = style_path.read_text(encoding="utf-8")

        self.assertIn("async function deleteConversationMessage(messageId)", script_text)
        self.assertIn("Delete this message?", script_text)
        self.assertIn("function fallbackCopyText(text)", script_text)
        self.assertIn("async function copyTextToClipboard(text)", script_text)
        self.assertIn("msg-delete-confirm", style_text)
        self.assertIn("msg-action-btn--danger", style_text)

    def test_frontend_includes_clarification_ui_hooks(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        self.assertIn("function appendClarificationPanel(group, metadata, options = {})", script_text)
        self.assertIn("function updateClarificationFieldVisibility(form, clarification)", script_text)
        self.assertIn("pending_clarification: pendingClarification", script_text)
        self.assertIn('clarification_response', script_text)
        self.assertIn("A: Type your answer", script_text)
        self.assertIn("Your draft answers stay in this browser until you send them.", script_text)
        self.assertIn("clarification-card__intro", script_text)
        self.assertIn("clarification-card__summary", script_text)
        self.assertIn("clarification-options__search", script_text)
        self.assertIn("function renderBubbleWithCursor(bubbleEl, text)", script_text)
        self.assertIn('bubbleEl.classList.add("streaming-text")', script_text)
        self.assertIn("function renderBubbleMarkdown(bubbleEl, text)", script_text)

        style_path = Path(__file__).resolve().parent.parent / "static" / "style.css"
        style_text = style_path.read_text(encoding="utf-8")
        self.assertIn(".clarification-card", style_text)
        self.assertIn(".clarification-card__intro", style_text)
        self.assertIn(".clarification-card__helper", style_text)
        self.assertIn(".clarification-form", style_text)
        self.assertIn(".clarification-options__search", style_text)
        self.assertIn(".bubble.streaming-text", style_text)

    def test_frontend_streaming_render_uses_frame_buffered_markdown_rendering(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        style_path = Path(__file__).resolve().parent.parent / "static" / "style.css"
        style_text = style_path.read_text(encoding="utf-8")

        self.assertIn("let visibleAnswer = \"\";", script_text)
        self.assertIn("visibleAnswer = fullAnswer;", script_text)
        self.assertIn("if (!String(fullAnswer || \"\").trim()) {", script_text)
        self.assertIn("renderBubbleWithCursor(asstBubble, visibleAnswer);", script_text)
        self.assertIn("window.requestAnimationFrame(flushStreamingAnswerFrame)", script_text)
        self.assertIn("asstBubble.hidden = true;", script_text)
        self.assertIn("findStreamingCursorContainer", script_text)
        self.assertIn("bubbleEl.hidden = false;", script_text)
        self.assertIn(".stream-cursor", style_text)
        self.assertIn("line-height: 1;", style_text)
        self.assertIn("vertical-align: text-bottom;", style_text)
        self.assertIn("@keyframes streamCursorBlink", style_text)

    def test_frontend_streaming_render_includes_loading_shell_and_server_cancel_hook(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        style_path = Path(__file__).resolve().parent.parent / "static" / "style.css"
        style_text = style_path.read_text(encoding="utf-8")

        self.assertIn("function renderAssistantLoadingBubble(bubbleEl, label = \"Preparing response…\", detail = \"\")", script_text)
        self.assertIn("const streamRequestId = createStreamRequestId();", script_text)
        self.assertIn("stream_request_id: streamRequestId", script_text)
        self.assertIn('fetch(`/api/chat-runs/${encodeURIComponent(runId)}/cancel`', script_text)
        self.assertIn("STREAM_ANSWER_RENDER_INTERVAL_MS = 42", script_text)
        self.assertIn(".assistant-loading", style_text)
        self.assertIn(".bubble.bubble--loading", style_text)
        self.assertIn("@keyframes assistantLoadingBounce", style_text)

    def test_frontend_canvas_streaming_defers_panel_and_preview_renders(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn("let activeAnswerRenderPending = false;", script_text)
        self.assertIn("const CANVAS_STREAMING_PREVIEW_THROTTLE_MS = 96;", script_text)
        self.assertIn("function requestCanvasPanelRender({ deferForStreaming = false } = {})", script_text)
        self.assertIn("function flushDeferredCanvasRenderWork()", script_text)
        self.assertIn("activeAnswerRenderPending = true;", script_text)
        self.assertIn("flushDeferredCanvasRenderWork();", script_text)
        self.assertIn('requestCanvasPanelRender({ deferForStreaming: options.deferPanelRender !== false });', script_text)
        self.assertIn('messagesEl.style.scrollBehavior = active ? "auto" : "";', script_text)

    def test_frontend_canvas_mobile_viewport_controls_are_wired(self):
        html = self.client.get("/").get_data(as_text=True)
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        style_path = Path(__file__).resolve().parent.parent / "static" / "style.css"
        style_text = style_path.read_text(encoding="utf-8")

        self.assertIn('id="canvas-zoom-out-btn"', html)
        self.assertIn('id="canvas-zoom-in-btn"', html)
        self.assertIn('id="canvas-fullscreen-toggle"', html)
        self.assertIn("const CANVAS_ZOOM_LEVELS = Object.freeze([1, 1.12, 1.25, 1.4, 1.55]);", script_text)
        self.assertIn("function syncCanvasViewportControls()", script_text)
        self.assertIn("function toggleCanvasFullscreen(force = null)", script_text)
        self.assertIn(".canvas-viewport-toggle", style_text)
        self.assertIn(".canvas-panel.canvas-panel--fullscreen", style_text)

    def test_settings_ui_exposes_fetch_threshold_input(self):
        html = self.client.get("/settings").get_data(as_text=True)
        self.assertIn("Tool budgets", html)
        self.assertIn("Tool step limit (1-50)", html)
        self.assertIn("Parent model max parallel tools (1-12)", html)
        self.assertIn('id="max-parallel-tools-input"', html)
        self.assertIn('id="sub-agent-max-parallel-tools-input"', html)
        self.assertIn("Max clarification questions (1-25)", html)
        self.assertIn('id="clarification-max-questions-input"', html)
        self.assertIn('value="append_scratchpad"', html)
        self.assertIn('value="read_scratchpad"', html)
        self.assertIn('value="ask_clarifying_question"', html)
        self.assertIn('value="sub_agent"', html)
        self.assertIn('id="scratchpad-list"', html)
        self.assertIn('id="scratchpad-add-btn"', html)
        self.assertIn('Reserve the scratchpad for durable cross-conversation lessons, profile clues, recurring problems, long-running workstreams, preferences, domain facts, and a few general notes.', html)
        self.assertIn('id="summary-mode-select"', html)
        self.assertIn('id="summary-trigger-input"', html)
        self.assertIn('id="prompt-max-input-tokens-input"', html)
        self.assertIn('id="prompt-response-token-reserve-input"', html)
        self.assertIn('id="prompt-recent-history-max-tokens-input"', html)
        self.assertIn('id="prompt-summary-max-tokens-input"', html)
        self.assertIn('id="prompt-rag-max-tokens-input"', html)
        self.assertIn('id="prompt-tool-memory-max-tokens-input"', html)
        self.assertIn('id="prompt-tool-trace-max-tokens-input"', html)
        self.assertIn('id="context-compaction-threshold-input"', html)
        self.assertIn('id="context-compaction-keep-recent-rounds-input"', html)
        self.assertIn('id="tool-memory-auto-inject-toggle"', html)
        self.assertIn('id="pruning-target-reduction-ratio-input"', html)
        self.assertIn('id="pruning-min-target-tokens-input"', html)
        self.assertIn('id="fetch-threshold-input"', html)
        self.assertIn('id="fetch-aggressiveness-input"', html)
        self.assertIn('id="rag-sensitivity-select"', html)
        self.assertIn('id="rag-context-size-select"', html)
        self.assertIn('id="rag-sensitivity-hint"', html)
        self.assertIn('id="summary-detail-level-select"', html)
        self.assertIn('id="sub-agent-model-preference-select"', html)
        self.assertIn('id="sub-agent-model-fallback-list"', html)
        self.assertNotIn('id="sub-agent-include-conversation-context-toggle"', html)
        self.assertNotIn('id="sub-agent-include-canvas-context-toggle"', html)
        self.assertIn('id="sub-agent-max-steps-input"', html)
        self.assertIn('id="sub-agent-tool-toggles"', html)
        self.assertIn('name="sub-agent-allowed-tool"', html)
        self.assertIn("Choose which web-only tools the delegated helper may use during research.", html)
        self.assertIn('id="web-cache-ttl-hours-input"', html)
        self.assertIn('id="openrouter-prompt-cache-enabled-toggle"', html)
        self.assertIn('id="custom-model-routing-mode-select"', html)
        self.assertIn("Pin a specific provider", html)
        self.assertIn('id="custom-model-provider-slug-input"', html)
        self.assertIn('id="custom-model-reasoning-mode-select"', html)
        self.assertIn('id="custom-model-reasoning-effort-select"', html)

        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")
        self.assertIn("const RAG_SENSITIVITY_HINTS = {", script_text)

    def test_run_agent_stream_executes_append_scratchpad_tool(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("append_scratchpad", {"section": "preferences", "notes": ["The user is 22 years old."]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=3, total_tokens=6)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Saved."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=2, total_tokens=4)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.append_to_scratchpad",
            return_value=({"status": "appended", "scratchpad": "The user is 22 years old."}, "Scratchpad updated"),
        ) as mocked_append:
            events = list(run_agent_stream([{"role": "user", "content": "Remember this"}], "deepseek-chat", 2, ["append_scratchpad"]))

        mocked_append.assert_called_once_with(
            ["The user is 22 years old."],
            section="preferences",
            conversation_id=None,
            source_message_id=None,
        )
        tool_result_event = next(event for event in events if event["type"] == "tool_result")
        self.assertEqual(tool_result_event["tool"], "append_scratchpad")
        self.assertEqual(tool_result_event["summary"], "Scratchpad updated")

    def test_execute_tool_reads_current_scratchpad(self):
        save_app_settings({"scratchpad_preferences": "Stable preference\nAnother note"})

        result, summary = _execute_tool("read_scratchpad", {}, runtime_state={})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scratchpad_sections"]["preferences"], "Stable preference\nAnother note")
        self.assertEqual(result["sections"][5]["title"], "User Preferences")
        self.assertEqual(result["note_count"], 2)
        self.assertEqual(summary, "Scratchpad read")

    def test_execute_tool_saves_conversation_memory_entry(self):
        conversation_id = self._create_conversation()

        result, summary = _execute_tool(
            "save_to_conversation_memory",
            {
                "entry_type": "user_info",
                "key": "Preferred language",
                "value": "Kullanıcı bu konuşmada Türkçe istiyor.",
            },
            runtime_state={"agent_context": {"conversation_id": conversation_id}},
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(summary, "Conversation memory saved: Preferred language")
        entries = get_conversation_memory(conversation_id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["entry_type"], "user_info")
        self.assertEqual(entries[0]["key"], "Preferred language")

    def test_execute_tool_updates_existing_conversation_memory_entry_by_key(self):
        conversation_id = self._create_conversation()
        original_entry = insert_conversation_memory_entry(
            conversation_id,
            "user_info",
            "Preferred language",
            "Kullanıcı bu konuşmada Türkçe istiyor.",
        )

        result, summary = _execute_tool(
            "save_to_conversation_memory",
            {
                "entry_type": "task_context",
                "key": "Preferred language",
                "value": "Kullanıcı bu konuşmada kısa ve net Türkçe yanıt istiyor.",
            },
            runtime_state={"agent_context": {"conversation_id": conversation_id}},
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(summary, "Conversation memory updated: Preferred language")
        self.assertTrue(result.get("updated_existing"))
        entries = get_conversation_memory(conversation_id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], original_entry["id"])
        self.assertEqual(entries[0]["entry_type"], "task_context")
        self.assertEqual(entries[0]["value"], "Kullanıcı bu konuşmada kısa ve net Türkçe yanıt istiyor.")

    def test_execute_tool_search_knowledge_base_can_save_compact_result_to_conversation_memory(self):
        conversation_id = self._create_conversation()
        search_result = {
            "query": "python sort",
            "count": 2,
            "matches": [
                {
                    "source_name": "doc-1",
                    "source_type": "uploaded_document",
                    "similarity": 0.82,
                    "text": "Python listeleri siralamak icin sorted kullanilir.",
                },
                {
                    "source_name": "conversation-12",
                    "source_type": "conversation",
                    "similarity": 0.64,
                    "text": "Onceki sohbette reverse sort ornegi verildi.",
                },
            ],
        }

        with patch("agent.search_knowledge_base_tool", return_value=search_result):
            result, summary = _execute_tool(
                "search_knowledge_base",
                {
                    "query": "python sort",
                    "save_to_conversation_memory": True,
                    "memory_key": "Sorting findings",
                },
                runtime_state={"agent_context": {"conversation_id": conversation_id}},
            )

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["conversation_memory"]["status"], "ok")
        self.assertEqual(result["conversation_memory"]["key"], "Sorting findings")
        self.assertFalse(result["conversation_memory"]["updated_existing"])
        self.assertEqual(summary, "2 knowledge chunks found; conversation memory saved: Sorting findings")
        entries = get_conversation_memory(conversation_id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["entry_type"], "tool_result")
        self.assertEqual(entries[0]["key"], "Sorting findings")
        self.assertIn("Knowledge base search for \"python sort\"", entries[0]["value"])
        self.assertIn("doc-1 [uploaded_document] sim 0.82", entries[0]["value"])

    def test_execute_tool_search_tool_memory_can_refresh_saved_finding(self):
        conversation_id = self._create_conversation()
        insert_conversation_memory_entry(
            conversation_id,
            "tool_result",
            "Policy cache",
            "Eski arama ozeti.",
        )
        search_result = {
            "query": "example.com policy",
            "count": 1,
            "matches": [
                {
                    "source_name": "fetch_url: example.com/policy",
                    "source_type": "tool_memory",
                    "similarity": 0.91,
                    "text": "Cached policy text.",
                    "expiry_warning": "Expires within 1 hour",
                }
            ],
        }

        with patch("agent.search_tool_memory", return_value=search_result):
            result, summary = _execute_tool(
                "search_tool_memory",
                {
                    "query": "example.com policy",
                    "save_to_conversation_memory": True,
                    "memory_key": "Policy cache",
                },
                runtime_state={"agent_context": {"conversation_id": conversation_id}},
            )

        self.assertEqual(result["conversation_memory"]["status"], "ok")
        self.assertTrue(result["conversation_memory"]["updated_existing"])
        self.assertEqual(summary, "1 tool memory matches found; conversation memory updated: Policy cache")
        entries = get_conversation_memory(conversation_id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["key"], "Policy cache")
        self.assertIn("Tool memory search for \"example.com policy\"", entries[0]["value"])
        self.assertIn("Expires within 1 hour", entries[0]["value"])

    def test_execute_tool_search_knowledge_base_ignores_falsey_string_save_flag(self):
        conversation_id = self._create_conversation()
        search_result = {
            "query": "python sort",
            "count": 1,
            "matches": [
                {
                    "source_name": "doc-1",
                    "source_type": "uploaded_document",
                    "similarity": 0.82,
                    "text": "Python listeleri siralamak icin sorted kullanilir.",
                }
            ],
        }

        with patch("agent.search_knowledge_base_tool", return_value=search_result):
            result, summary = _execute_tool(
                "search_knowledge_base",
                {
                    "query": "python sort",
                    "save_to_conversation_memory": "false",
                },
                runtime_state={"agent_context": {"conversation_id": conversation_id}},
            )

        self.assertNotIn("conversation_memory", result)
        self.assertEqual(summary, "1 knowledge chunks found")
        self.assertEqual(get_conversation_memory(conversation_id), [])

    def test_execute_tool_does_not_delete_other_conversation_memory_entry(self):
        source_conversation_id = self._create_conversation("Source")
        other_conversation_id = self._create_conversation("Other")
        entry = insert_conversation_memory_entry(
            source_conversation_id,
            "decision",
            "API",
            "Flask kullanılacak.",
        )

        result, summary = _execute_tool(
            "delete_conversation_memory_entry",
            {"entry_id": entry["id"]},
            runtime_state={"agent_context": {"conversation_id": other_conversation_id}},
        )

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(summary, f"Conversation memory not found: {entry['id']}")
        remaining_entries = get_conversation_memory(source_conversation_id)
        self.assertEqual(len(remaining_entries), 1)
        self.assertEqual(remaining_entries[0]["id"], entry["id"])

    def test_runtime_system_message_omits_empty_scratchpad_section_when_only_read_tool_is_active(self):
        message = build_runtime_system_message(active_tool_names=["read_scratchpad"], scratchpad="")

        content = message["content"]
        self.assertNotIn("## Scratchpad (AI Persistent Memory)", content)
        self.assertIn("read_scratchpad", content)
        self.assertNotIn("(All sections empty)", content)
        self.assertNotIn("### Memory Write Policy", content)

    def test_runtime_system_message_renders_conversation_memory_and_policy(self):
        message = build_runtime_system_message(
            active_tool_names=["save_to_conversation_memory", "delete_conversation_memory_entry"],
            conversation_memory=[
                {
                    "id": 7,
                    "entry_type": "tool_result",
                    "key": "Latest fetch",
                    "value": "Belgelerde Python 3.12 hedefleniyor.",
                    "created_at": "2026-04-08 10:23:00",
                }
            ],
            summary_count=2,
        )

        content = message["content"]
        self.assertIn("## Conversation Memory", content)
        self.assertIn("#7 [tool_result] 10:23 - Latest fetch: Belgelerde Python 3.12 hedefleniyor.", content)
        self.assertIn("primary durable working memory for this chat", content)
        self.assertIn("## Conversation Memory Priority", content)
        self.assertIn("## Conversation Memory Write Policy", content)
        self.assertIn("Default choice", content)
        self.assertIn("Save incrementally", content)
        self.assertIn("Especially save before context loss", content)
        self.assertIn("Prefer multiple small entries", content)
        self.assertIn("Prefer update over duplication", content)
        self.assertIn("save_to_conversation_memory", content)

    def test_run_agent_stream_caps_parallel_safe_tool_workers(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("search_web", {"queries": ["repo overview"]}, call_id="call-1", index=0),
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com"}, call_id="call-2", index=1),
                    self._tool_call_chunk("read_file", {"path": "README.md"}, call_id="call-3", index=2),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=3, total_tokens=6)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Done."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3)),
                ]
            ),
        ]
        executor_limits = []

        class FakeFuture:
            def __init__(self, value):
                self._value = value

            def result(self):
                return self._value

        class FakeExecutor:
            def __init__(self, max_workers):
                executor_limits.append(max_workers)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn, slot):
                return FakeFuture(fn(slot))

        def fake_execute(tool_name, tool_args, runtime_state=None):
            del tool_args, runtime_state
            return {"status": "ok", "tool": tool_name}, f"{tool_name} ok"

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.ThreadPoolExecutor",
            side_effect=lambda max_workers: FakeExecutor(max_workers),
        ), patch("agent._validate_tool_arguments", return_value=None), patch(
            "agent._execute_tool",
            side_effect=fake_execute,
        ):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Inspect the repo."}],
                    "deepseek-chat",
                    2,
                    ["search_web", "fetch_url", "read_file"],
                    max_parallel_tools=2,
                )
            )

        self.assertEqual(executor_limits, [2])
        tool_results = [event for event in events if event["type"] == "tool_result"]
        self.assertEqual([event["tool"] for event in tool_results], ["search_web", "fetch_url", "read_file"])

    def test_run_agent_stream_does_not_session_cache_workspace_reads_after_workspace_mutation(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("read_file", {"path": "demo/app.py"}, call_id="call-1"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._tool_call_chunk(
                        "update_file",
                        {"path": "demo/app.py", "content": "print('v2')\n"},
                        call_id="call-2",
                    ),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._tool_call_chunk("read_file", {"path": "demo/app.py"}, call_id="call-3"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Done."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3)),
                ]
            ),
        ]
        executed_calls = []

        def fake_execute(tool_name, tool_args, runtime_state=None):
            del runtime_state
            executed_calls.append((tool_name, dict(tool_args)))
            if tool_name == "read_file":
                read_count = len([name for name, _args in executed_calls if name == "read_file"])
                rendered_content = "1: print('v1')" if read_count == 1 else "1: print('v2')"
                return (
                    {
                        "status": "ok",
                        "action": "file_read",
                        "path": str(tool_args.get("path") or ""),
                        "content": rendered_content,
                    },
                    f"File read: {tool_args.get('path')}",
                )
            if tool_name == "update_file":
                return (
                    {
                        "status": "ok",
                        "action": "file_updated",
                        "path": str(tool_args.get("path") or ""),
                    },
                    f"File updated: {tool_args.get('path')}",
                )
            raise AssertionError(f"Unexpected tool: {tool_name}")

        workspace_runtime_state = create_workspace_runtime_state(
            root_path=os.path.join(self.temp_dir.name, "workspace-cache"),
        )

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent._execute_tool",
            side_effect=fake_execute,
        ):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Inspect, edit, then inspect again."}],
                    "deepseek-chat",
                    4,
                    ["read_file", "update_file"],
                    workspace_runtime_state=workspace_runtime_state,
                )
            )

        read_calls = [entry for entry in executed_calls if entry[0] == "read_file"]
        self.assertEqual(len(read_calls), 2)
        read_results = [event for event in events if event["type"] == "tool_result" and event["tool"] == "read_file"]
        self.assertEqual(len(read_results), 2)
        self.assertTrue(all(event.get("cached") is False for event in read_results))

    def test_execute_tool_runs_sub_agent_with_user_selected_web_tools(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "search_web", "read_file", "create_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }

        fake_child_events = iter(
            [
                {"type": "step_update", "step": 1, "tool": "search_web", "preview": "repo setup", "call_id": "c1"},
                {
                    "type": "tool_history",
                    "step": 1,
                    "messages": [
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_web",
                                        "arguments": '{"queries":["repo setup"]}',
                                    },
                                }
                            ],
                        },
                        {"role": "tool", "tool_call_id": "c1", "content": '[{"title":"Setup","url":"https://example.com/setup"}]'},
                    ],
                },
                {"type": "tool_result", "step": 1, "tool": "search_web", "summary": "1 web results found", "call_id": "c1"},
                {"type": "tool_capture", "tool_results": []},
                {"type": "answer_delta", "text": "Found the relevant setup guidance."},
                {"type": "done"},
            ]
        )

        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": []},
            "sub_agent_allowed_tool_names": ["search_web", "fetch_url_summarized"],
            "sub_agent_max_steps": 5,
        }

        with patch("agent.get_app_settings", return_value=settings), patch("agent.run_agent_stream", return_value=fake_child_events) as mocked_run:
            result, summary = _execute_tool(
                "sub_agent",
                {
                    "task": "Inspect the README and summarize the setup steps.",
                    "max_steps": 2,
                },
                runtime_state,
            )

        self.assertEqual(mocked_run.call_args.args[2], 5)
        self.assertEqual(mocked_run.call_args.args[3], ["search_web", "fetch_url_summarized"])
        self.assertEqual(mocked_run.call_args.kwargs["prompt_tool_names"], ["search_web", "fetch_url_summarized"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("setup", result["summary"].lower())
        self.assertEqual(result["tool_trace"][0]["tool_name"], "search_web")
        self.assertTrue(runtime_state["sub_agent_traces"])
        self.assertEqual(runtime_state["sub_agent_traces"][0]["messages"][-1]["role"], "assistant")
        self.assertIn("Sub-agent completed", summary)

    def test_execute_tool_scopes_sub_agent_to_user_selected_web_tools(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "search_web", "read_file"],
                "prompt_tool_names": ["sub_agent", "read_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }

        fake_child_events = iter(
            [
                {"type": "answer_delta", "text": "Scoped correctly."},
                {"type": "done"},
            ]
        )

        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": []},
            "sub_agent_allowed_tool_names": ["fetch_url", "search_news_google"],
            "sub_agent_max_steps": 4,
        }

        with patch("agent.get_app_settings", return_value=settings), patch("agent.run_agent_stream", return_value=fake_child_events) as mocked_run:
            result, _ = _execute_tool(
                "sub_agent",
                {
                    "task": "Inspect the README and summarize the setup steps.",
                },
                runtime_state,
            )

        self.assertEqual(mocked_run.call_args.args[2], 4)
        self.assertEqual(mocked_run.call_args.args[3], ["fetch_url", "search_news_google"])
        self.assertEqual(mocked_run.call_args.kwargs["prompt_tool_names"], ["fetch_url", "search_news_google"])
        self.assertEqual(result["status"], "ok")

    def test_execute_tool_accepts_google_search_alias(self):
        with patch(
            "agent.search_web_tool",
            return_value=[{"title": "A", "url": "https://example.com", "snippet": "alpha"}],
        ) as mocked_search:
            result, summary = _execute_tool("google_search", {"queries": ["repo overview"]})

        self.assertEqual(mocked_search.call_count, 1)
        self.assertEqual(mocked_search.call_args.args[0], ["repo overview"])
        self.assertEqual(summary, "1 web results found")
        self.assertEqual(result[0]["title"], "A")

    def test_execute_tool_accepts_search_web_query_alias(self):
        with patch(
            "agent.search_web_tool",
            return_value=[{"title": "A", "url": "https://example.com", "snippet": "alpha"}],
        ) as mocked_search:
            result, summary = _execute_tool("search_web", {"query": "repo overview"})

        self.assertEqual(mocked_search.call_count, 1)
        self.assertEqual(mocked_search.call_args.args[0], ["repo overview"])
        self.assertEqual(summary, "1 web results found")
        self.assertEqual(result[0]["title"], "A")

    def test_execute_tool_skips_empty_search_web_calls(self):
        with patch("agent.search_web_tool") as mocked_search:
            result, summary = _execute_tool("search_web", {})

        mocked_search.assert_not_called()
        self.assertEqual(result, [])
        self.assertEqual(summary, "search_web skipped: no queries provided")

    def test_execute_tool_blocks_recursive_sub_agent_calls(self):
        result, summary = _execute_tool(
            "sub_agent",
            {"task": "Investigate this recursively."},
            {"agent_context": {"sub_agent_depth": 1, "enabled_tool_names": ["sub_agent"]}},
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("Recursive sub-agent delegation is disabled", result["error"])
        self.assertTrue(summary.startswith("Failed:"))

    def test_execute_tool_marks_sub_agent_tool_errors_as_failures(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }

        fake_child_events = iter(
            [
                {"type": "step_update", "step": 1, "tool": "read_file", "preview": "missing.txt", "call_id": "c1"},
                {"type": "tool_error", "step": 1, "tool": "read_file", "error": "File not found.", "call_id": "c1"},
                {"type": "done"},
            ]
        )

        with patch("agent.run_agent_stream", return_value=fake_child_events):
            result, summary = _execute_tool(
                "sub_agent",
                {"task": "Try to read a missing file."},
                runtime_state,
            )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["error"], "File not found.")
        self.assertTrue(summary.startswith("Sub-agent partial:"))
        self.assertTrue(runtime_state["sub_agent_traces"])
        self.assertEqual(runtime_state["sub_agent_traces"][0]["status"], "partial")

    def test_run_sub_agent_stream_emits_live_progress_updates(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }

        fake_child_events = iter(
            [
                {"type": "step_update", "step": 1, "tool": "read_file", "preview": "README.md", "call_id": "c1"},
                {"type": "tool_result", "step": 1, "tool": "read_file", "summary": "File read: README.md", "call_id": "c1"},
                {"type": "answer_delta", "text": "Summary ready."},
                {"type": "done"},
            ]
        )

        with patch("agent.run_agent_stream", return_value=fake_child_events):
            events = list(_run_sub_agent_stream({"task": "Inspect README.md"}, runtime_state))

        live_updates = [event for event in events if event["type"] == "sub_agent_trace_update"]
        self.assertGreaterEqual(len(live_updates), 3)
        self.assertEqual(live_updates[0]["entry"]["status"], "running")
        self.assertNotIn("task_full", live_updates[0]["entry"])
        self.assertEqual(live_updates[1]["entry"]["tool_trace"][0]["state"], "running")
        self.assertEqual(live_updates[-1]["entry"]["status"], "ok")
        self.assertEqual(live_updates[-1]["entry"]["tool_trace"][0]["state"], "done")

    def test_run_sub_agent_stream_uses_configured_parallel_limit(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": []},
            "sub_agent_max_parallel_tools": 1,
            "sub_agent_allowed_tool_names": ["fetch_url"],
        }
        fake_child_events = iter(
            [
                {"type": "answer_delta", "text": "Summary ready."},
                {"type": "done"},
            ]
        )

        with patch("agent.get_app_settings", return_value=settings), patch(
            "agent.run_agent_stream",
            return_value=fake_child_events,
        ) as mocked_run:
            events = list(_run_sub_agent_stream({"task": "Inspect README.md"}, runtime_state))

        self.assertEqual(mocked_run.call_args.kwargs["max_parallel_tools"], 1)
        self.assertEqual(mocked_run.call_args.kwargs["prompt_tool_names"], ["fetch_url"])
        self.assertEqual(events[-1]["entry"]["status"], "ok")

    def test_run_sub_agent_stream_inherits_parent_parallel_limit_when_child_limit_unset(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": []},
            "max_parallel_tools": 4,
            "sub_agent_allowed_tool_names": ["fetch_url"],
        }
        fake_child_events = iter(
            [
                {"type": "answer_delta", "text": "Summary ready."},
                {"type": "done"},
            ]
        )

        with patch("agent.get_app_settings", return_value=settings), patch(
            "agent.run_agent_stream",
            return_value=fake_child_events,
        ) as mocked_run:
            list(_run_sub_agent_stream({"task": "Inspect README.md"}, runtime_state))

        self.assertEqual(mocked_run.call_args.kwargs["max_parallel_tools"], 4)

    def test_run_sub_agent_stream_uses_configured_max_steps(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file", "list_dir", "search_files", "search_web", "fetch_url"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "canvas-1",
                        "title": "main.py",
                        "path": "src/main.py",
                        "format": "code",
                        "content": "print('hello')",
                    }
                ]
            ),
        }
        fake_child_events = iter(
            [
                {"type": "answer_delta", "text": "Summary ready."},
                {"type": "done"},
            ]
        )

        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": []},
            "sub_agent_max_steps": 11,
            "sub_agent_allowed_tool_names": ["search_web", "fetch_url", "search_news_google"],
        }

        with patch("agent.get_app_settings", return_value=settings), patch("agent.run_agent_stream", return_value=fake_child_events) as mocked_run:
            list(
                _run_sub_agent_stream(
                    {
                        "task": "Analyze the repo codebase across multiple files, compare implementations, inspect sources, gather evidence, and synthesize a thorough report.",
                    },
                    runtime_state,
                )
            )

        self.assertEqual(mocked_run.call_args.args[2], 11)

    def test_run_sub_agent_stream_preserves_full_task_when_short_label_is_truncated(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }
        long_task = "# Investigate\n\n" + ("A" * 500)
        fake_child_events = iter(
            [
                {"type": "answer_delta", "text": "Summary ready."},
                {"type": "done"},
            ]
        )

        with patch("agent.run_agent_stream", return_value=fake_child_events):
            events = list(_run_sub_agent_stream({"task": long_task}, runtime_state))

        final_entry = [event for event in events if event["type"] == "sub_agent_trace_update"][-1]["entry"]
        self.assertIn("task", final_entry)
        self.assertIn("task_full", final_entry)
        self.assertTrue(final_entry["task"].endswith("…"))
        self.assertEqual(final_entry["task_full"], long_task)

    def test_run_sub_agent_stream_retries_retryable_model_errors_with_fallback_models(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": ["deepseek-reasoner", "deepseek-chat"]},
            "sub_agent_retry_attempts": 0,
            "sub_agent_timeout_seconds": 20,
        }

        attempts = [
            iter(
                [
                    {"type": "tool_error", "step": 1, "tool": "api", "error": "RateLimitError: 429 Too Many Requests"},
                ]
            ),
            iter(
                [
                    {"type": "answer_delta", "text": "Recovered on fallback model."},
                    {"type": "done"},
                ]
            ),
        ]

        with patch("agent.get_app_settings", return_value=settings), patch(
            "agent.run_agent_stream", side_effect=attempts
        ) as mocked_run:
            events = list(_run_sub_agent_stream({"task": "Inspect README.md"}, runtime_state))

        self.assertEqual(mocked_run.call_args_list[0].args[1], "deepseek-reasoner")
        self.assertEqual(mocked_run.call_args_list[1].args[1], "deepseek-chat")
        final_update = events[-1]
        self.assertEqual(final_update["type"], "sub_agent_trace_update")
        self.assertEqual(final_update["entry"]["model"], "deepseek-chat")
        self.assertEqual(final_update["entry"]["summary"], "Recovered on fallback model.")
        self.assertTrue(runtime_state["sub_agent_traces"])
        self.assertEqual(len(runtime_state["sub_agent_traces"]), 1)
        self.assertEqual(runtime_state["sub_agent_traces"][-1]["model"], "deepseek-chat")
        self.assertEqual(runtime_state["sub_agent_traces"][-1]["fallback_note"], "Continued on deepseek-chat after model error.")

    def test_run_sub_agent_stream_retries_timed_out_attempts_with_fallback_models(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": ["deepseek-reasoner", "deepseek-chat"]},
            "sub_agent_retry_attempts": 0,
            "sub_agent_timeout_seconds": 20,
        }

        attempts = [
            iter(
                [
                    {"type": "step_update", "step": 1, "tool": "read_file", "preview": "README.md", "call_id": "c1"},
                    {"type": "answer_delta", "text": "This arrives too late."},
                    {
                        "type": "tool_history",
                        "step": 1,
                        "messages": [
                            {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "type": "function",
                                        "function": {
                                            "name": "read_file",
                                            "arguments": '{"path":"README.md"}',
                                        },
                                    }
                                ],
                            },
                            {"role": "tool", "tool_call_id": "c1", "content": '{"path":"README.md","content":"hello"}'},
                        ],
                    },
                    {"type": "done"},
                ]
            ),
            iter(
                [
                    {"type": "answer_delta", "text": "Recovered after timeout."},
                    {"type": "done"},
                ]
            ),
        ]

        with patch("agent.get_app_settings", return_value=settings), patch(
            "agent.run_agent_stream", side_effect=attempts
        ) as mocked_run, patch(
            "agent.time.monotonic",
            side_effect=[0, 0, 2, 4, 6, 16] + [16] * 20,
        ):
            events = list(_run_sub_agent_stream({"task": "Inspect README.md"}, runtime_state))

        self.assertEqual(mocked_run.call_args_list[0].args[1], "deepseek-reasoner")
        self.assertEqual(mocked_run.call_args_list[1].args[1], "deepseek-chat")
        second_messages = mocked_run.call_args_list[1].args[0]
        self.assertTrue(
            any(
                message.get("role") == "system"
                and "Continue from the latest transcript" in str(message.get("content") or "")
                for message in second_messages
            )
        )
        self.assertTrue(
            any(
                message.get("role") == "assistant"
                and "This arrives too late." in str(message.get("content") or "")
                for message in second_messages
            )
        )
        for message in second_messages:
            if message.get("role") != "assistant":
                continue
            for tool_call in message.get("tool_calls") or []:
                self.assertIn("function", tool_call)
                self.assertNotIn("preview", tool_call)
                self.assertNotIn("arguments", tool_call)
        self.assertEqual(events[-1]["entry"]["model"], "deepseek-chat")
        self.assertEqual(events[-1]["entry"]["summary"], "Recovered after timeout.")
        self.assertEqual(len(runtime_state["sub_agent_traces"]), 1)
        self.assertEqual(runtime_state["sub_agent_traces"][0]["status"], "ok")
        self.assertTrue(runtime_state["sub_agent_traces"][0]["timed_out"])
        self.assertIn("Continued on deepseek-chat after timeout.", runtime_state["sub_agent_traces"][0]["fallback_note"])
        self.assertEqual(runtime_state["sub_agent_traces"][0]["model"], "deepseek-chat")
        self.assertTrue(
            any(
                message.get("role") == "assistant"
                and "This arrives too late." in str(message.get("content") or "")
                for message in runtime_state["sub_agent_traces"][0].get("messages") or []
            )
        )

    def test_run_sub_agent_stream_retries_same_model_before_fallback(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": ["deepseek-reasoner", "deepseek-chat"]},
            "sub_agent_retry_attempts": 1,
            "sub_agent_retry_delay_seconds": 1,
            "sub_agent_timeout_seconds": 60,
        }

        attempts = [
            iter([
                {"type": "tool_error", "step": 1, "tool": "api", "error": "Request timeout while generating."},
            ]),
            iter([
                {"type": "answer_delta", "text": "Recovered on the retry."},
                {"type": "done"},
            ]),
        ]

        with patch("agent.get_app_settings", return_value=settings), patch(
            "agent.run_agent_stream", side_effect=attempts
        ) as mocked_run, patch("agent.time.sleep", return_value=None) as mocked_sleep, patch(
            "agent.time.monotonic",
            side_effect=iter(range(100)),
        ):
            events = list(_run_sub_agent_stream({"task": "Inspect README.md"}, runtime_state))

        self.assertEqual(mocked_run.call_count, 2)
        self.assertEqual(mocked_run.call_args_list[0].args[1], "deepseek-reasoner")
        self.assertEqual(mocked_run.call_args_list[1].args[1], "deepseek-reasoner")
        self.assertTrue(mocked_sleep.called)
        self.assertEqual(events[-1]["entry"]["model"], "deepseek-reasoner")
        self.assertEqual(events[-1]["entry"]["summary"], "Recovered on the retry.")
        self.assertEqual(len(runtime_state["sub_agent_traces"]), 1)
        self.assertEqual(runtime_state["sub_agent_traces"][-1]["model"], "deepseek-reasoner")
        self.assertNotIn("fallback_note", runtime_state["sub_agent_traces"][-1])

    def test_run_sub_agent_stream_falls_back_after_missing_final_answer(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "search_web"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": ["deepseek-reasoner", "deepseek-chat"]},
            "sub_agent_retry_attempts": 0,
            "sub_agent_timeout_seconds": 20,
        }

        attempts = [
            iter(
                [
                    {"type": "step_update", "step": 1, "tool": "search_web", "preview": "undiagnosed syndrome", "call_id": "s1"},
                    {"type": "tool_result", "step": 1, "tool": "search_web", "summary": "25 web results found", "call_id": "s1"},
                    {
                        "type": "tool_error",
                        "step": 1,
                        "tool": "agent",
                        "error": "The model returned no final answer content. Retrying and waiting for a final answer.",
                    },
                    {"type": "answer_delta", "text": FINAL_ANSWER_MISSING_TEXT},
                    {"type": "done"},
                ]
            ),
            iter(
                [
                    {"type": "answer_delta", "text": "Recovered on fallback model."},
                    {"type": "done"},
                ]
            ),
        ]

        with patch("agent.get_app_settings", return_value=settings), patch(
            "agent.run_agent_stream", side_effect=attempts
        ) as mocked_run:
            events = list(_run_sub_agent_stream({"task": "Investigate unusual syndromes"}, runtime_state))

        self.assertEqual(mocked_run.call_args_list[0].args[1], "deepseek-reasoner")
        self.assertEqual(mocked_run.call_args_list[1].args[1], "deepseek-chat")
        self.assertEqual(events[-1]["entry"]["model"], "deepseek-chat")
        self.assertEqual(events[-1]["entry"]["summary"], "Recovered on fallback model.")
        self.assertEqual(events[-1]["entry"]["fallback_note"], "Continued on deepseek-chat after missing final answer.")
        self.assertTrue(all(item["tool_name"] != "agent" for item in events[-1]["entry"]["tool_trace"]))
        self.assertEqual(runtime_state["sub_agent_traces"][-1]["fallback_note"], "Continued on deepseek-chat after missing final answer.")

    def test_execute_tool_summarizes_partial_sub_agent_evidence_when_final_answer_missing(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "search_web"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": []},
            "sub_agent_retry_attempts": 0,
            "sub_agent_timeout_seconds": 20,
        }

        fake_child_events = iter(
            [
                {"type": "step_update", "step": 1, "tool": "search_web", "preview": "rare disease review", "call_id": "s1"},
                {"type": "tool_result", "step": 1, "tool": "search_web", "summary": "25 web results found", "call_id": "s1"},
                {
                    "type": "tool_error",
                    "step": 1,
                    "tool": "agent",
                    "error": "The model still did not provide a final answer in assistant content.",
                },
                {"type": "answer_delta", "text": FINAL_ANSWER_MISSING_TEXT},
                {"type": "done"},
            ]
        )

        with patch("agent.get_app_settings", return_value=settings), patch(
            "agent.run_agent_stream", return_value=fake_child_events
        ):
            result, summary = _execute_tool(
                "sub_agent",
                {"task": "Investigate unusual syndromes"},
                runtime_state,
            )

        self.assertEqual(result["status"], "partial")
        self.assertNotIn("error", result)
        self.assertIn("usable final conclusion", result["summary"])
        self.assertIn("25 web results found", result["summary"])
        self.assertTrue(summary.startswith("Sub-agent partial:"))
        self.assertTrue(all(item["tool_name"] != "agent" for item in result["tool_trace"]))
        self.assertEqual(runtime_state["sub_agent_traces"][-1]["status"], "partial")
        self.assertNotIn(FINAL_ANSWER_MISSING_TEXT, runtime_state["sub_agent_traces"][-1]["summary"])

    def test_run_sub_agent_stream_tries_all_fallback_models_in_order(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file"],
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {
                "sub_agent": ["deepseek-reasoner", "openrouter:anthropic/claude-sonnet-4.5", "deepseek-chat"],
            },
            "sub_agent_retry_attempts": 0,
            "custom_models": [
                {
                    "name": "Claude Sonnet 4.5",
                    "api_model": "anthropic/claude-sonnet-4.5",
                    "supports_tools": True,
                    "supports_vision": True,
                    "supports_structured_outputs": True,
                }
            ],
        }

        attempts = [
            iter(
                [
                    {"type": "tool_error", "step": 1, "tool": "read_file", "error": "File not found.", "call_id": "c1"},
                    {"type": "done"},
                ]
            ),
            iter(
                [
                    {"type": "tool_error", "step": 1, "tool": "read_file", "error": "Read failed.", "call_id": "c2"},
                    {"type": "done"},
                ]
            ),
            iter(
                [
                    {"type": "answer_delta", "text": "Recovered on the third model."},
                    {"type": "done"},
                ]
            ),
        ]

        with patch("agent.get_app_settings", return_value=settings), patch(
            "agent.run_agent_stream", side_effect=attempts
        ) as mocked_run:
            events = list(_run_sub_agent_stream({"task": "Inspect README.md"}, runtime_state))

        self.assertEqual([call.args[1] for call in mocked_run.call_args_list[:3]], [
            "deepseek-reasoner",
            "openrouter:anthropic/claude-sonnet-4.5@@v=1;s=1",
            "deepseek-chat",
        ])
        self.assertEqual(mocked_run.call_count, 3)
        self.assertEqual(events[-1]["entry"]["model"], "deepseek-chat")
        self.assertEqual(events[-1]["entry"]["summary"], "Recovered on the third model.")
        self.assertEqual(len(runtime_state["sub_agent_traces"]), 1)
        self.assertEqual(runtime_state["sub_agent_traces"][-1]["model"], "deepseek-chat")
        self.assertEqual(
            runtime_state["sub_agent_traces"][0]["fallback_note"],
            "Continued on deepseek-chat after model error.",
        )

    def test_build_sub_agent_messages_mentions_web_query_limit(self):
        messages = _build_sub_agent_messages("Inspect the web", ["search_web"])

        self.assertIn("Use English for tool planning", messages[0]["content"])
        self.assertIn("rewrite it into clear English working notes", messages[0]["content"])
        self.assertIn("Read-only still includes web search and URL fetch tools", messages[0]["content"])
        self.assertIn("1 and 5 items", messages[0]["content"])
        self.assertIn("split broader searches into multiple calls", messages[0]["content"])
        self.assertIn("## Current Date and Time", messages[0]["content"])

    def test_build_sub_agent_messages_includes_fixed_current_time_context(self):
        now = datetime(2026, 4, 7, 14, 23, 45, tzinfo=timezone(timedelta(hours=3)))
        messages = _build_sub_agent_messages("Inspect the web", ["search_web"], now=now)

        self.assertIn("## Current Date and Time", messages[0]["content"])
        self.assertIn("2026-04-07T14:20:00+03:00", messages[0]["content"])
        self.assertIn("- Date: 2026-04-07", messages[0]["content"])
        self.assertIn("- Time: 14:20", messages[0]["content"])

    def test_build_sub_agent_messages_only_includes_task_text(self):
        messages = _build_sub_agent_messages("Inspect the web", ["search_web"])

        self.assertIn("Delegated task from the parent assistant:", messages[1]["content"])
        self.assertIn("Inspect the web", messages[1]["content"])
        self.assertNotIn("Current conversation summary:", messages[1]["content"])

    def test_lookup_cross_turn_tool_memory_does_not_exact_match_sub_agent(self):
        with patch("agent.get_exact_tool_memory_match") as mocked_lookup:
            result = _lookup_cross_turn_tool_memory(
                "sub_agent",
                {"task": "Inspect README", "max_steps": 4},
            )

        self.assertIsNone(result)
        mocked_lookup.assert_not_called()

    def test_run_sub_agent_stream_ignores_conversation_handoff(self):
        runtime_state = {
            "agent_context": {
                "model": "deepseek-chat",
                "enabled_tool_names": ["sub_agent", "read_file"],
                "conversation_handoff": "User: this contains profile details.",
                "sub_agent_depth": 0,
            },
            "canvas": create_canvas_runtime_state(),
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
            "workspace": {"root_path": None},
        }
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": []},
        }
        fake_child_events = iter(
            [
                {"type": "answer_delta", "text": "Summary ready."},
                {"type": "done"},
            ]
        )

        with patch("agent.get_app_settings", return_value=settings), patch(
            "agent.run_agent_stream",
            return_value=fake_child_events,
        ) as mocked_run:
            list(_run_sub_agent_stream({"task": "Inspect README.md"}, runtime_state))

        child_messages = mocked_run.call_args.args[0]
        self.assertTrue(any(message.get("role") == "user" and "Inspect README.md" in str(message.get("content") or "") for message in child_messages))
        self.assertFalse(
            any(
                "profile details" in str(message.get("content") or "")
                or "Current conversation summary:" in str(message.get("content") or "")
                for message in child_messages
            )
        )

    def test_build_final_answer_instruction_forbids_claiming_unconfirmed_actions(self):
        instruction = _build_final_answer_instruction()

        self.assertEqual(instruction["role"], "system")
        self.assertIn("Do not claim that an action was completed", instruction["content"])
        self.assertIn("If work remains unfinished, say so explicitly", instruction["content"])
        self.assertIn("Do not include stray JSON objects", instruction["content"])

    def test_run_agent_stream_does_not_force_canvas_write_retry_when_no_tool_is_called(self):
        # Even if the user asks for a canvas write, the orchestrator should no longer
        # hard-force a retry. Tool choice is left to the model.
        hallucinated_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        reasoning_content="",
                        content="Canvas'ı İngilizceye çevirdim.",
                        tool_calls=[],
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

        with patch("agent.client.chat.completions.create", return_value=hallucinated_response) as mocked_create:
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Promptu İngilizceye çevirip Canvas'a yaz."}],
                    "deepseek-chat",
                    3,
                    ["create_canvas_document"],
                )
            )

        self.assertEqual(mocked_create.call_count, 1)
        answer_deltas = [e["text"] for e in events if e["type"] == "answer_delta"]
        self.assertIn("Canvas'ı İngilizceye çevirdim.", answer_deltas)
        self.assertFalse(any(event["type"] == "clarification_request" for event in events))
        usage_event = next(event for event in events if event["type"] == "usage")
        self.assertEqual(usage_event["model_call_count"], 1)
        self.assertFalse(any(call["is_retry"] for call in usage_event["model_calls"]))

    def test_build_reasoning_replay_instruction_marks_reasoning_as_non_execution_evidence(self):
        instruction = _build_reasoning_replay_instruction(
            {
                "entries": [
                    {
                        "step": 1,
                        "reasoning": "I should verify the latest figures and then update the canvas.",
                        "tool_names": ["search_web"],
                    }
                ]
            },
            "Verify and update",
        )

        self.assertIsNotNone(instruction)
        self.assertIn("Only actual tool results confirm", instruction["content"])
        self.assertIn("planned tools = search_web", instruction["content"])

    def test_run_fetch_url_summarized_uses_fetch_summarize_operation_model(self):
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Focused summary output."))]
        )
        fake_create = Mock(return_value=fake_response)
        fake_target = {
            "api_model": "openrouter:summary-model",
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
        }

        with patch(
            "agent.fetch_url_tool",
            return_value={
                "url": "https://example.com/page",
                "title": "Example Page",
                "content": "Pricing details and limitations.",
                "meta_description": "Example metadata",
                "content_source_element": "main",
                "outline": ["Pricing", "Limits"],
            },
        ), patch(
            "agent.get_app_settings",
            return_value={
                "fetch_url_summarized_max_input_chars": "6000",
                "fetch_url_summarized_max_output_tokens": "3100",
            },
        ), patch(
            "agent.get_operation_model",
            return_value="openrouter:summary-model",
        ), patch("agent.resolve_model_target", return_value=fake_target), patch(
            "agent.apply_model_target_request_options",
            side_effect=lambda kwargs, target: kwargs,
        ):
            result, summary = _run_fetch_url_summarized(
                {"url": "https://example.com/page", "focus": "pricing limits"},
                {"agent_context": {"model": "deepseek-chat"}},
            )

        self.assertEqual(result["summary"], "Focused summary output.")
        self.assertEqual(result["focus"], "pricing limits")
        self.assertEqual(result["model"], "openrouter:summary-model")
        self.assertEqual(result["summary_profile"], "general_web_page")
        self.assertIn("Page summarized:", summary)
        request_kwargs = fake_create.call_args.kwargs
        self.assertEqual(request_kwargs["max_tokens"], 3100)
        self.assertIn("Focus:\npricing limits", request_kwargs["messages"][1]["content"])
        self.assertIn("Focus answer:", request_kwargs["messages"][0]["content"])
        self.assertIn("section headers and flat bullet lists", request_kwargs["messages"][0]["content"])

    def test_run_fetch_url_to_canvas_imports_chunked_documents(self):
        fetched_content = "alpha " * 2700

        with patch(
            "agent.fetch_url_tool",
            return_value={
                "url": "https://example.com/guide",
                "title": "Example Guide",
                "content": fetched_content,
                "meta_description": "Reference guide",
                "content_format": "html",
            },
        ) as mocked_fetch, patch(
            "agent.get_app_settings",
            return_value={
                "fetch_url_to_canvas_chunk_threshold": "2000",
                "fetch_url_to_canvas_chunk_chars": "6000",
                "fetch_url_to_canvas_max_chunks": "5",
            },
        ):
            runtime_state = {}
            result, summary = _run_fetch_url_to_canvas({"url": "https://example.com/guide"}, runtime_state)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "url_imported_to_canvas")
        self.assertEqual(result["url"], "https://example.com/guide")
        self.assertEqual(result["title"], "Example Guide")
        self.assertGreater(result["document_count"], 1)
        self.assertTrue(result["chunked"])
        self.assertEqual(len(result["documents"]), result["document_count"])
        self.assertEqual(result["documents"][0]["source_url"], "https://example.com/guide")
        self.assertEqual(result["documents"][0]["source_kind"], "fetched_url")
        self.assertEqual(result["documents"][0]["chunk_index"], 1)
        self.assertEqual(result["documents"][0]["chunk_count"], result["document_count"])
        self.assertIn("Fetched URL imported to Canvas", summary)
        self.assertEqual(result["document_id"], get_canvas_runtime_active_document_id(runtime_state["canvas"]))
        self.assertEqual(len(get_canvas_runtime_documents(runtime_state["canvas"])), result["document_count"])
        self.assertEqual(mocked_fetch.call_args.kwargs["cache_namespace"], "fetch_canvas:6000:5")
        self.assertGreaterEqual(mocked_fetch.call_args.kwargs["content_max_chars"], 38000)

    def test_sub_agent_tool_spec_mentions_exposed_web_search_tools(self):
        spec = TOOL_SPEC_BY_NAME["sub_agent"]

        self.assertIn("web search and URL fetch tools", spec["description"])
        self.assertIn("search_web", spec["prompt"]["guidance"])
        self.assertIn("Remember that the helper only receives fixed web-research tools", spec["prompt"]["guidance"])

    def test_run_agent_stream_emits_clarification_request_and_stops(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk(
                        "ask_clarifying_question",
                        {
                            "intro": "Before I answer, I need two details.",
                            "questions": [
                                {
                                    "id": "scope",
                                    "label": "Which scope?",
                                    "input_type": "single_select",
                                    "options": [
                                        {"label": "Only this repo", "value": "repo"},
                                        {"label": "General tool", "value": "general"},
                                    ],
                                },
                                {"id": "notes", "label": "Anything else?", "input_type": "text", "required": False},
                            ],
                        },
                    ),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4, total_tokens=7)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Build this for me"}],
                    "deepseek-chat",
                    2,
                    ["ask_clarifying_question"],
                )
            )

        clarification_event = next(event for event in events if event["type"] == "clarification_request")
        self.assertEqual(
            clarification_event["text"],
            "Before I answer, I need two details.\n"
            "Please answer these questions:\n"
            "1. Which scope? Options: Only this repo | General tool.\n"
            "2. Anything else? (optional)",
        )
        self.assertEqual(clarification_event["clarification"]["intro"], "Before I answer, I need two details.")
        self.assertEqual(clarification_event["clarification"]["questions"][0]["id"], "scope")
        self.assertFalse(any(event["type"] == "answer_delta" for event in events))
        self.assertEqual(events[-1]["type"], "done")

    def test_run_agent_stream_does_not_retry_skipped_clarification_plain_text(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="Önce birkaç soru sormalıyım."),
                    self._stream_chunk(content="Soruları hazırladım."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=8)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create:
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Önce sorular sor, sonra cevaba geç."}],
                    "deepseek-chat",
                    2,
                    ["ask_clarifying_question"],
                )
            )

        usage_event = next(event for event in events if event["type"] == "usage")
        self.assertEqual(mocked_create.call_count, 1)
        self.assertIn({"type": "answer_delta", "text": "Soruları hazırladım."}, events)
        self.assertFalse(any(event["type"] == "clarification_request" for event in events))
        self.assertEqual(usage_event["model_call_count"], 1)
        self.assertEqual(mocked_create.call_args_list[0].kwargs["tool_choice"], "auto")
        self.assertEqual(events[-1]["type"], "done")

    def test_run_agent_stream_repairs_invalid_clarification_tool_payload_once(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk(
                        "ask_clarifying_question",
                        {
                            "questions": [
                                {"id": "scope", "label": "Which scope?", "input_type": "single_select"},
                            ],
                        },
                    ),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=8)),
                ]
            ),
            iter(
                [
                    self._tool_call_chunk(
                        "ask_clarifying_question",
                        {
                            "intro": "Before I answer, I need one detail.",
                            "questions": [
                                {
                                    "id": "scope",
                                    "label": "Which scope?",
                                    "input_type": "single_select",
                                    "options": [
                                        {"label": "Only this repo", "value": "repo"},
                                        {"label": "General guidance", "value": "general"},
                                    ],
                                }
                            ],
                        },
                    ),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=4, total_tokens=8)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create:
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Ask me questions first."}],
                    "deepseek-chat",
                    2,
                    ["ask_clarifying_question"],
                )
            )

        clarification_event = next(event for event in events if event["type"] == "clarification_request")
        usage_event = next(event for event in events if event["type"] == "usage")
        tool_errors = [event for event in events if event["type"] == "tool_error" and event["tool"] == "ask_clarifying_question"]
        self.assertTrue(tool_errors)
        self.assertEqual(clarification_event["clarification"]["questions"][0]["options"][0]["value"], "repo")
        self.assertEqual(usage_event["model_call_count"], 2)
        self.assertEqual(usage_event["model_calls"][1]["retry_reason"], "clarification_tool_repair")
        self.assertEqual(
            mocked_create.call_args_list[1].kwargs["tool_choice"],
            {"type": "function", "function": {"name": "ask_clarifying_question"}},
        )
        self.assertFalse(mocked_create.call_args_list[1].kwargs["parallel_tool_calls"])
        self.assertEqual(events[-1]["type"], "done")

    def test_run_agent_stream_falls_back_when_openrouter_provider_rejects_clarification_repair_tool_choice(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk(
                        "ask_clarifying_question",
                        {
                            "questions": [
                                {"id": "scope", "label": "Which scope?", "input_type": "single_select"},
                            ],
                        },
                    ),
                    self._stream_chunk_openrouter(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=8)),
                ]
            ),
            RuntimeError(
                "Error code: 404 - {'error': {'message': 'No endpoints found that support the provided tool_choice value.', 'code': 404}}"
            ),
            iter(
                [
                    self._tool_call_chunk(
                        "ask_clarifying_question",
                        {
                            "intro": "Before I answer, I need two details.",
                            "questions": [
                                {"id": "goal", "label": "What is the main goal?", "input_type": "text"},
                                {"id": "constraints", "label": "Any constraints I should respect?", "input_type": "text", "required": False},
                            ],
                        },
                    ),
                    self._stream_chunk_openrouter(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=4, total_tokens=8)),
                ]
            ),
        ]

        mock_create = Mock(side_effect=responses)
        mock_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=mock_create
                )
            )
        )

        with patch("agent.get_app_settings", return_value={}), patch(
            "agent.resolve_model_target",
            return_value={
                "record": {"provider": model_registry.OPENROUTER_PROVIDER},
                "client": mock_client,
                "api_model": "anthropic/claude-sonnet-4.5",
                "extra_body": {"provider": {"only": ["deepinfra/turbo"], "allow_fallbacks": False}},
            },
        ):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Önce sorular sor, sonra cevaba geç."}],
                    "openrouter:anthropic/claude-sonnet-4.5",
                    2,
                    ["ask_clarifying_question"],
                )
            )

        clarification_event = next(event for event in events if event["type"] == "clarification_request")
        tool_errors = [event for event in events if event["type"] == "tool_error" and event["tool"] == "ask_clarifying_question"]
        self.assertTrue(tool_errors)
        self.assertEqual(clarification_event["clarification"]["questions"][0]["id"], "goal")
        self.assertEqual(mock_create.call_args_list[1].kwargs["tool_choice"], {"type": "function", "function": {"name": "ask_clarifying_question"}})
        self.assertFalse(mock_create.call_args_list[1].kwargs["parallel_tool_calls"])
        self.assertEqual(mock_create.call_args_list[2].kwargs["tool_choice"], "auto")
        self.assertNotIn("parallel_tool_calls", mock_create.call_args_list[2].kwargs)
        self.assertEqual(
            mock_create.call_args_list[2].kwargs["extra_body"],
            {"provider": {"only": ["deepinfra/turbo"], "allow_fallbacks": False}},
        )
        self.assertEqual(events[-1]["type"], "done")

    def test_active_tool_normalization_filters_invalid_entries(self):
        normalized = normalize_active_tool_names(
            [
                "fetch_url",
                "search_web",
                "fetch_url",
                "invalid_tool",
                123,
            ]
        )
        self.assertEqual(normalized, ["fetch_url", "search_web"])

    def test_multiple_app_instances_use_separate_databases(self):
        second_dir = tempfile.TemporaryDirectory()
        self.addCleanup(second_dir.cleanup)
        second_db_path = f"{second_dir.name}/second.db"
        second_app = create_app(database_path=second_db_path)
        second_app.config.update(TESTING=True)
        second_client = second_app.test_client()

        first_response = self.client.post(
            "/api/conversations",
            json={"title": "First App", "model": "deepseek-chat"},
        )
        second_response = second_client.post(
            "/api/conversations",
            json={"title": "Second App", "model": "deepseek-chat"},
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)

        first_id = first_response.get_json()["id"]
        second_id = second_response.get_json()["id"]

        first_get = self.client.get(f"/api/conversations/{first_id}")
        second_get = second_client.get(f"/api/conversations/{second_id}")
        self.assertEqual(first_get.status_code, 200)
        self.assertEqual(second_get.status_code, 200)
        self.assertEqual(first_get.get_json()["conversation"]["title"], "First App")
        self.assertEqual(second_get.get_json()["conversation"]["title"], "Second App")

        with self.app.app_context():
            first_count = get_db().execute("SELECT COUNT(*) AS count FROM conversations").fetchone()["count"]
        with second_app.app_context():
            second_count = get_db().execute("SELECT COUNT(*) AS count FROM conversations").fetchone()["count"]

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)

    def test_settings_page_lists_canvas_inspection_tool_toggles(self):
        response = self.client.get("/settings")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('value="expand_canvas_document"', html)
        self.assertIn('value="scroll_canvas_document"', html)
        self.assertIn('value="focus_canvas_page"', html)

    def test_conversation_crud_flow(self):
        conversation_id = self._create_conversation()

        response = self.client.get("/api/conversations")
        self.assertEqual(response.status_code, 200)
        rows = response.get_json()
        self.assertTrue(any(row["id"] == conversation_id for row in rows))

        response = self.client.patch(
            f"/api/conversations/{conversation_id}",
            json={"title": "Updated Title"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["title"], "Updated Title")

        response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["conversation"]["id"], conversation_id)
        self.assertEqual(payload["messages"], [])

        response = self.client.delete(f"/api/conversations/{conversation_id}")
        self.assertEqual(response.status_code, 204)

        response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(response.status_code, 404)

    def test_update_conversation_title_rejects_blank_values(self):
        conversation_id = self._create_conversation()

        response = self.client.patch(
            f"/api/conversations/{conversation_id}",
            json={"title": "   "},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Title required.")

    def test_rag_endpoints_support_manual_document_ingest(self):
        response = self.client.get("/api/rag/documents")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

        response = self.client.post(
            "/api/rag/ingest",
            data={
                "document": (io.BytesIO(b"Alpha\nBeta\nGamma"), "ops-notes.txt", "text/plain"),
                "source_name": "Ops Notes",
                "description": "Use when answering operations questions.",
                "auto_inject_enabled": "false",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["file_name"], "ops-notes.txt")
        self.assertEqual(payload["document"]["source_type"], "uploaded_document")
        self.assertEqual(payload["document"]["source_name"], "Ops Notes")
        self.assertGreater(payload["document"]["chunk_count"], 0)

        response = self.client.get("/api/rag/documents")
        self.assertEqual(response.status_code, 200)
        documents = response.get_json()
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["source_type"], "uploaded_document")
        self.assertEqual(documents[0]["metadata"]["description"], "Use when answering operations questions.")
        self.assertFalse(documents[0]["metadata"]["auto_inject_enabled"])

    def test_rag_upload_metadata_generation_uses_deepseek_chat(self):
        fake_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"title":"Ops Notes","description":"Use this document for operations questions and process checks."}',
                    )
                )
            ]
        )

        with patch("routes.conversations.client.chat.completions.create", return_value=fake_response) as mocked_create:
            response = self.client.post(
                "/api/rag/upload-metadata",
                data={
                    "document": (io.BytesIO(b"Alpha\nBeta\nGamma"), "ops-notes.txt", "text/plain"),
                    "source_name": "Ops Notes Draft",
                    "description": "Operations reference",
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["title"], "Ops Notes")
        self.assertEqual(payload["description"], "Use this document for operations questions and process checks.")
        self.assertTrue(payload["used_ai"])
        mocked_create.assert_called_once()
        call_kwargs = mocked_create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "deepseek-chat")
        prompt_text = "\n".join(message.get("content", "") for message in call_kwargs["messages"])
        self.assertIn("ops-notes.txt", prompt_text)
        self.assertIn("Alpha", prompt_text)

    def test_fix_text_endpoint(self):
        fake_result = {
            "content": "Improved text",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        with patch("routes.chat.collect_agent_response", return_value=fake_result) as mocked_collect:
            response = self.client.post(
                "/api/fix-text",
                json={"text": "improved text", "model": "deepseek-chat"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["text"], "Improved text")
        self.assertTrue(mocked_collect.called)

    def test_collect_agent_response_keeps_reasoning_separate_from_content(self):
        fake_events = iter(
            [
                {"type": "reasoning_start"},
                {"type": "reasoning_delta", "text": "Internal chain"},
                {"type": "done"},
            ]
        )

        with patch("agent.run_agent_stream", return_value=fake_events):
            result = collect_agent_response([{"role": "user", "content": "Test"}], "deepseek-reasoner", 1, [])

        self.assertEqual(result["content"], "")
        self.assertEqual(result["reasoning_content"], "Internal chain")

    def test_fix_text_reasoner_requires_final_content(self):
        fake_result = {
            "content": "",
            "reasoning_content": "Improved via reasoning",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        with patch("routes.chat.collect_agent_response", return_value=fake_result):
            response = self.client.post(
                "/api/fix-text",
                json={"text": "improved text", "model": "deepseek-reasoner"},
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"], "No text returned.")

    def test_fix_text_uses_operation_model_preference(self):
        response = self.client.patch(
            "/api/settings",
            json={
                "custom_models": [
                    {
                        "name": "Claude Sonnet 4.5",
                        "api_model": "anthropic/claude-sonnet-4.5",
                        "supports_tools": False,
                        "supports_vision": False,
                        "supports_structured_outputs": False,
                    }
                ],
                "operation_model_preferences": {
                    "fix_text": "openrouter:anthropic/claude-sonnet-4.5",
                },
            },
        )
        self.assertEqual(response.status_code, 200)

        fake_result = {
            "content": "Improved text",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        with patch("routes.chat.collect_agent_response", return_value=fake_result) as mocked_collect:
            response = self.client.post(
                "/api/fix-text",
                json={"text": "improved text"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mocked_collect.call_args.args[1].startswith("openrouter:anthropic/claude-sonnet-4.5"))

    def test_chat_stream_persists_messages(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "2",
                "temperature": "0.3",
                "active_tools": "[]",
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {"type": "step_started", "step": 1, "max_steps": 2},
                {"type": "step_update", "step": 1, "tool": "search_web", "preview": "hello", "call_id": "c1"},
                {"type": "tool_result", "step": 1, "tool": "search_web", "summary": "1 web result found", "call_id": "c1"},
                {"type": "reasoning_start"},
                {"type": "reasoning_delta", "text": "Analyzing request"},
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Hello "},
                {"type": "answer_delta", "text": "world"},
                {
                    "type": "usage",
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                    "estimated_input_tokens": 14,
                    "input_breakdown": {
                        "core_instructions": 4,
                        "user_messages": 6,
                        "assistant_history": 0,
                        "tool_results": 0,
                        "rag_context": 3,
                        "final_instruction": 1,
                    },
                    "cost": 0.0,
                    "currency": "USD",
                    "model": "deepseek-chat",
                },
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events) as mocked_stream:
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Hello",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True).strip().splitlines()
        self.assertAlmostEqual(mocked_stream.call_args.kwargs["temperature"], 0.3)
        events = [json.loads(line) for line in body]
        event_types = [event["type"] for event in events]
        self.assertIn("answer_start", event_types)
        self.assertIn("answer_delta", event_types)
        self.assertIn("usage", event_types)
        self.assertIn("done", event_types)
        self.assertLess(event_types.index("done"), event_types.index("message_ids"))

        with get_db() as conn:
            rows = conn.execute(
                "SELECT role, content, metadata, prompt_tokens, completion_tokens, total_tokens FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["role"], "user")
        self.assertEqual(rows[0]["content"], "Hello")
        self.assertEqual(rows[1]["role"], "assistant")
        self.assertEqual(rows[1]["content"], "Hello world")
        assistant_metadata = json.loads(rows[1]["metadata"])
        self.assertEqual(assistant_metadata["reasoning_content"], "Analyzing request")
        self.assertEqual(assistant_metadata["tool_trace"][0]["tool_name"], "search_web")
        self.assertEqual(assistant_metadata["tool_trace"][0]["state"], "done")
        self.assertEqual(assistant_metadata["usage"]["estimated_input_tokens"], 11)
        self.assertEqual(assistant_metadata["usage"]["input_breakdown"]["user_messages"], 6)
        self.assertEqual(assistant_metadata["usage"]["input_breakdown"]["core_instructions"], 5)
        self.assertEqual(rows[1]["prompt_tokens"], 11)
        self.assertEqual(rows[1]["completion_tokens"], 7)
        self.assertEqual(rows[1]["total_tokens"], 18)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        assistant_message = conversation_response.get_json()["messages"][1]
        self.assertEqual(assistant_message["usage"]["estimated_input_tokens"], 11)
        self.assertEqual(assistant_message["usage"]["input_breakdown"]["core_instructions"], 5)
        self.assertNotIn("reasoning_content", assistant_message["metadata"])
        self.assertEqual(assistant_message["metadata"]["tool_trace"][0]["tool_name"], "search_web")

    def test_chat_stream_persists_exact_model_invocations_for_raw_export(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "temperature": "0.3",
                "active_tools": "[]",
                "rag_auto_inject": "false",
            }
        )

        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="Thinking. "),
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Test",
                    "messages": [{"role": "user", "content": "Test"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)

        with get_db() as conn:
            assistant_row = conn.execute(
                "SELECT id FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY id DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
            invocation_rows = conn.execute(
                """SELECT assistant_message_id, source_message_id, call_type, provider, api_model,
                          request_payload, response_summary
                   FROM model_invocations
                   WHERE conversation_id = ?
                   ORDER BY id""",
                (conversation_id,),
            ).fetchall()

        self.assertIsNotNone(assistant_row)
        self.assertEqual(len(invocation_rows), 1)
        self.assertEqual(invocation_rows[0]["assistant_message_id"], assistant_row["id"])
        self.assertEqual(invocation_rows[0]["call_type"], "agent_step")
        self.assertEqual(invocation_rows[0]["provider"], "deepseek")
        self.assertEqual(invocation_rows[0]["api_model"], "deepseek-chat")

        request_payload = json.loads(invocation_rows[0]["request_payload"])
        response_summary = json.loads(invocation_rows[0]["response_summary"])
        self.assertIn(
            {"role": "user", "content": "Test"},
            [
                {"role": message.get("role"), "content": message.get("content")}
                for message in request_payload["messages"]
                if isinstance(message, dict)
            ],
        )
        self.assertTrue(request_payload["stream"])
        self.assertEqual(response_summary["content_text"], "Final answer.")
        self.assertEqual(response_summary["usage"]["prompt_tokens"], 2)

    def test_failed_tool_summary_detection_marks_fetch_failures(self):
        self.assertTrue(_is_failed_tool_summary("Fetch failed: HTTP 403"))
        self.assertTrue(_is_failed_tool_summary("failed: timeout while reading response"))
        self.assertFalse(_is_failed_tool_summary("Page content extracted: Example"))

    def test_chat_stream_persists_pending_clarification(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "2",
                "active_tools": '["ask_clarifying_question"]',
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {
                    "type": "clarification_request",
                    "text": (
                        "Before I answer, I need two details.\n"
                        "Please answer these questions:\n"
                        "1. Which scope? Options: Only this repo | General tool.\n"
                        "2. Anything else? (optional)"
                    ),
                    "clarification": {
                        "intro": "Before I answer, I need two details.",
                        "submit_label": "Continue",
                        "questions": [
                            {
                                "id": "scope",
                                "label": "Which scope?",
                                "input_type": "single_select",
                                "options": [
                                    {"label": "Only this repo", "value": "repo"},
                                    {"label": "General tool", "value": "general"},
                                ],
                            },
                            {
                                "id": "notes",
                                "label": "Anything else?",
                                "input_type": "text",
                                "required": False,
                            },
                        ],
                    },
                },
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Build this for me",
                    "messages": [{"role": "user", "content": "Build this for me"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        streamed_events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines() if line.strip()]
        clarification_event = next((event for event in streamed_events if event["type"] == "clarification_request"), None)
        self.assertIsNotNone(clarification_event)
        self.assertEqual(clarification_event["clarification"]["submit_label"], "Continue")

        with get_db() as conn:
            rows = conn.execute(
                "SELECT role, content, metadata FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()

        self.assertEqual([row["role"] for row in rows], ["user", "assistant"])
        assistant_metadata = json.loads(rows[1]["metadata"])
        self.assertEqual(rows[1]["content"], clarification_event["text"])
        self.assertIn("Which scope?", rows[1]["content"])
        self.assertEqual(assistant_metadata["pending_clarification"]["questions"][0]["id"], "scope")

    def test_chat_passes_clarification_history_as_transcript_with_runtime_injection(self):
        """Clarification answers must be injected into the runtime context (Clarification Response section).

        Regression test: previously clarification_response was always passed as None to
        _build_budgeted_prompt_messages, so the Clarification Response section was never
        injected. This caused the model to ignore the answers and re-ask the questions.
        """
        conversation_id = self._create_conversation()
        pending_questions = [
            {
                "id": "budget",
                "label": "Budget?",
                "input_type": "text",
                "required": True,
            }
        ]
        assistant_message_id = self._insert_pending_clarification_assistant(
            conversation_id,
            text="",
            questions=pending_questions,
        )
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "2",
                "active_tools": '[]',
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events) as mocked_stream:
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Q: Budget?\nA: 200-300 TL",
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "",
                            "metadata": {
                                "pending_clarification": {
                                    "questions": pending_questions,
                                }
                            },
                        },
                        {
                            "role": "user",
                            "content": "Q: Budget?\nA: 200-300 TL",
                            "metadata": {
                                "clarification_response": {
                                    "assistant_message_id": assistant_message_id,
                                    "answers": {
                                        "budget": {"display": "200-300 TL"},
                                    },
                                }
                            },
                        },
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        request_api_messages = mocked_stream.call_args.args[0]
        assistant_messages = [message for message in request_api_messages if message["role"] == "assistant"]
        user_messages = [message for message in request_api_messages if message["role"] == "user"]
        system_messages = [message for message in request_api_messages if message["role"] == "system"]

        # The clarification questions are still visible in the assistant's rendered message
        self.assertTrue(any("Please answer this question:" in (message.get("content") or "") for message in assistant_messages))
        self.assertTrue(any("1. Budget?" in (message.get("content") or "") for message in assistant_messages))
        self.assertEqual(user_messages[-1]["content"], "- Budget? \u2192 200-300 TL")
        # The Clarification Response section MUST be injected so the model sees the answers
        self.assertTrue(
            any("## Clarification Response" in (message.get("content") or "") for message in system_messages),
            "Clarification Response section must be injected when answers are provided — model needs this to proceed with the task",
        )
        # The answers must appear in the injected system context
        self.assertTrue(
            any("200-300 TL" in (message.get("content") or "") for message in system_messages),
            "Clarification answers must be visible in the system context injection",
        )

    def test_chat_stream_persists_tool_history_rows(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "2",
                "active_tools": '["search_web"]',
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {"type": "step_started", "step": 1, "max_steps": 2},
                {
                    "type": "tool_history",
                    "step": 1,
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "I will search first.",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_web",
                                        "arguments": '{"queries":["istanbul"]}',
                                    },
                                }
                            ],
                        },
                        {
                            "role": "tool",
                            "tool_call_id": "call-1",
                            "content": '{"ok":true,"results":[{"title":"Istanbul"}]}',
                        },
                    ],
                },
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Results are ready."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "What is Istanbul?",
                    "messages": [{"role": "user", "content": "What is Istanbul?"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        tool_history_event = next((event for event in events if event["type"] == "assistant_tool_history"), None)
        self.assertIsNotNone(tool_history_event)
        self.assertEqual(len(tool_history_event["messages"]), 2)

        with get_db() as conn:
            rows = conn.execute(
                "SELECT role, content, tool_calls, tool_call_id FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()

        self.assertEqual([row["role"] for row in rows], ["user", "assistant", "tool", "assistant"])
        self.assertIn("search_web", rows[1]["tool_calls"])
        self.assertEqual(rows[1]["content"], "")
        self.assertEqual(rows[2]["tool_call_id"], "call-1")
        self.assertEqual(rows[3]["content"], "Results are ready.")

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant", "tool", "assistant"])

    def test_chat_stream_strips_buffered_tool_preamble_from_final_assistant_message(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "2",
                "active_tools": '["search_web"]',
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Önce arama yapacağım."},
                {
                    "type": "tool_history",
                    "step": 1,
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "Önce arama yapacağım.",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_web",
                                        "arguments": '{"queries":["istanbul"]}',
                                    },
                                }
                            ],
                        },
                        {
                            "role": "tool",
                            "tool_call_id": "call-1",
                            "content": '{"ok":true}',
                        },
                    ],
                },
                {"type": "answer_delta", "text": "Sonucu buldum."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Araştır ve söyle",
                    "messages": [{"role": "user", "content": "Araştır ve söyle"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        response.get_data(as_text=True)
        with get_db() as conn:
            rows = conn.execute(
                "SELECT role, content, tool_calls, tool_call_id FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()

        self.assertEqual([row["role"] for row in rows], ["user", "assistant", "tool", "assistant"])
        self.assertEqual(rows[1]["content"], "")
        self.assertEqual(rows[3]["content"], "Sonucu buldum.")
        self.assertIn("search_web", rows[1]["tool_calls"])
        self.assertEqual(rows[2]["tool_call_id"], "call-1")

    def test_parse_message_tool_calls_compacts_large_canvas_payloads(self):
        large_content = "\n".join(f"print({index})" for index in range(200))
        raw_tool_calls = [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "create_canvas_document",
                    "arguments": json.dumps(
                        {
                            "title": "draft.py",
                            "content": large_content,
                            "symbols": [f"symbol_{index}" for index in range(40)],
                        },
                        ensure_ascii=False,
                    ),
                },
            }
        ]

        normalized = parse_message_tool_calls(raw_tool_calls)

        self.assertEqual(len(normalized), 1)
        arguments = json.loads(normalized[0]["function"]["arguments"])
        self.assertIn("[TRIMMED canvas content:", arguments["content"])
        self.assertLess(len(arguments["content"]), len(large_content))
        self.assertIn("[TRIMMED symbols:", arguments["symbols"][-1])

    def test_serialize_message_metadata_keeps_tool_trace(self):
        payload = serialize_message_metadata(
            {
                "tool_trace": [
                    {
                        "tool_name": "search_web",
                        "step": 1,
                        "preview": "query",
                        "summary": "2 web results found",
                        "state": "done",
                        "cached": True,
                    }
                ]
            }
        )

        metadata = parse_message_metadata(payload)
        self.assertEqual(metadata["tool_trace"][0]["tool_name"], "search_web")
        self.assertEqual(metadata["tool_trace"][0]["state"], "done")
        self.assertTrue(metadata["tool_trace"][0]["cached"])

    def test_serialize_message_metadata_keeps_sub_agent_traces(self):
        payload = serialize_message_metadata(
            {
                "sub_agent_traces": [
                    {
                        "task": "Inspect README",
                        "task_full": "# Inspect README\n\nLook for the setup section and summarize it.",
                        "status": "partial",
                        "summary": "Found the setup section.",
                        "fallback_note": "Continued on deepseek-chat after timeout.",
                        "error": "Timed out while reading a second file.",
                        "tool_trace": [
                            {
                                "tool_name": "read_file",
                                "step": 1,
                                "preview": "README.md",
                                "summary": "File read: README.md",
                                "state": "done",
                            }
                        ],
                        "artifacts": [
                            {"kind": "tool_input", "label": "Read File", "value": "README.md"}
                        ],
                        "messages": [
                            {
                                "role": "assistant",
                                "tool_calls": [
                                    {"name": "read_file", "preview": "README.md", "arguments": '{"path":"README.md"}'}
                                ],
                            },
                            {
                                "role": "tool",
                                "tool_call_id": "call-1",
                                "content": '{"path":"README.md","content":"hello"}',
                            },
                        ],
                        "canvas_saved": True,
                        "canvas_document_id": "canvas-research-1",
                        "canvas_document_title": "Research - Inspect README",
                    }
                ]
            }
        )

        metadata = parse_message_metadata(payload)
        self.assertEqual(metadata["sub_agent_traces"][0]["task"], "Inspect README")
        self.assertEqual(
            metadata["sub_agent_traces"][0]["task_full"],
            "# Inspect README\n\nLook for the setup section and summarize it.",
        )
        self.assertEqual(metadata["sub_agent_traces"][0]["status"], "partial")
        self.assertEqual(metadata["sub_agent_traces"][0]["tool_trace"][0]["tool_name"], "read_file")
        self.assertEqual(metadata["sub_agent_traces"][0]["messages"][0]["tool_calls"][0]["name"], "read_file")
        self.assertEqual(metadata["sub_agent_traces"][0]["fallback_note"], "Continued on deepseek-chat after timeout.")
        self.assertTrue(metadata["sub_agent_traces"][0]["canvas_saved"])
        self.assertEqual(metadata["sub_agent_traces"][0]["canvas_document_id"], "canvas-research-1")
        self.assertEqual(metadata["sub_agent_traces"][0]["canvas_document_title"], "Research - Inspect README")

    def test_serialize_message_metadata_keeps_canvas_documents(self):
        payload = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-1",
                        "title": "Draft",
                        "format": "markdown",
                        "content": "# Draft\n\nHello",
                    },
                    {
                        "id": "canvas-2",
                        "title": "Notes",
                        "format": "markdown",
                        "content": "# Notes\n\nExtra",
                    }
                ]
            }
        )

        metadata = parse_message_metadata(payload)
        self.assertEqual(metadata["canvas_documents"][0]["id"], "canvas-1")
        self.assertEqual(metadata["canvas_documents"][0]["title"], "Draft")
        self.assertEqual(metadata["canvas_documents"][1]["id"], "canvas-2")

    def test_serialize_message_metadata_keeps_active_canvas_document_id(self):
        payload = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-1",
                        "title": "Draft",
                        "format": "markdown",
                        "content": "# Draft",
                    },
                    {
                        "id": "canvas-2",
                        "title": "Notes",
                        "format": "markdown",
                        "content": "# Notes",
                    },
                ],
                "active_document_id": "canvas-1",
            }
        )

        metadata = parse_message_metadata(payload)
        self.assertEqual(metadata["active_document_id"], "canvas-1")

    def test_serialize_message_metadata_keeps_canvas_cleared_flag(self):
        payload = serialize_message_metadata(
            {
                "canvas_documents": [],
                "canvas_cleared": True,
            }
        )

        metadata = parse_message_metadata(payload)
        self.assertEqual(metadata["canvas_documents"], [])
        self.assertTrue(metadata["canvas_cleared"])

    def test_find_latest_canvas_documents_stops_at_cleared_marker(self):
        messages = [
            {
                "id": 1,
                "metadata": {
                    "canvas_documents": [
                        {
                            "id": "canvas-1",
                            "title": "Draft",
                            "format": "markdown",
                            "content": "# Draft",
                        }
                    ]
                },
            },
            {
                "id": 2,
                "metadata": {
                    "canvas_documents": [],
                    "canvas_cleared": True,
                },
            },
        ]

        self.assertEqual(find_latest_canvas_documents(messages), [])

    def test_find_latest_canvas_state_restores_active_document_id(self):
        messages = [
            {
                "id": 1,
                "metadata": {
                    "canvas_documents": [
                        {
                            "id": "canvas-1",
                            "title": "app.py",
                            "path": "src/app.py",
                            "format": "code",
                            "content": "print('hello')",
                        },
                        {
                            "id": "canvas-2",
                            "title": "README.md",
                            "path": "README.md",
                            "format": "markdown",
                            "content": "# Demo",
                        },
                    ],
                    "active_document_id": "canvas-1",
                },
            }
        ]

        runtime_state = find_latest_canvas_state(messages)
        self.assertEqual(get_canvas_runtime_active_document_id(runtime_state), "canvas-1")
        self.assertEqual(runtime_state["mode"], "project")

    def test_canvas_project_manifest_prioritizes_source_and_config_files(self):
        manifest = build_canvas_project_manifest(
            [
                {
                    "id": "canvas-1",
                    "title": "README.md",
                    "path": "README.md",
                    "role": "docs",
                    "format": "markdown",
                    "content": "# Demo",
                },
                {
                    "id": "canvas-2",
                    "title": "config.py",
                    "path": "src/config.py",
                    "role": "config",
                    "format": "code",
                    "content": "settings = {}",
                },
                {
                    "id": "canvas-3",
                    "title": "app.py",
                    "path": "src/app.py",
                    "role": "source",
                    "format": "code",
                    "content": "print('hello')",
                },
            ],
            active_document_id="canvas-3",
        )

        self.assertEqual(manifest["active_file"], "src/app.py")
        self.assertEqual(manifest["last_validation_status"], "ok")
        self.assertEqual([entry["path"] for entry in manifest["file_list"]], ["src/app.py", "src/config.py", "README.md"])
        self.assertEqual([entry["priority"] for entry in manifest["file_list"]], [10, 20, 60])

    def test_canvas_project_manifest_flags_duplicate_paths(self):
        manifest = build_canvas_project_manifest(
            [
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "role": "source",
                    "format": "code",
                    "content": "print('one')",
                },
                {
                    "id": "canvas-2",
                    "title": "app copy.py",
                    "path": "src/app.py",
                    "role": "source",
                    "format": "code",
                    "content": "print('two')",
                },
            ],
            active_document_id="canvas-1",
        )

        self.assertEqual(manifest["last_validation_status"], "needs_attention")
        self.assertIn("Duplicate project paths detected.", manifest["open_issues"])

    def test_normalize_canvas_document_accepts_code_format(self):
        document = normalize_canvas_document(
            {
                "id": "canvas-code",
                "title": "Script",
                "format": "code",
                "language": "python",
                "content": "print('ok')",
            }
        )

        self.assertEqual(document["format"], "code")
        self.assertEqual(document["language"], "python")

    def test_create_canvas_runtime_state_preserves_multiple_documents(self):
        runtime_state = create_canvas_runtime_state(
            [
                {"id": "canvas-1", "title": "Draft", "format": "markdown", "content": "one"},
                {"id": "canvas-2", "title": "Notes", "format": "markdown", "content": "two"},
            ]
        )

        self.assertEqual(len(runtime_state["documents"]), 2)
        self.assertEqual(runtime_state["active_document_id"], "canvas-2")

    def test_chat_persists_canvas_documents_from_tool_capture(self):
        conversation_id = self._create_conversation()
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "I prepared a draft."},
                {
                    "type": "tool_capture",
                    "tool_results": [],
                    "canvas_modified": True,
                    "canvas_documents": [
                        {
                            "id": "canvas-1",
                            "title": "Draft",
                            "format": "markdown",
                            "content": "# Draft\n\nInitial version",
                        }
                    ],
                },
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Create a draft",
                    "messages": [{"role": "user", "content": "Create a draft"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        canvas_event = next((event for event in events if event["type"] == "canvas_sync"), None)
        self.assertIsNotNone(canvas_event)
        self.assertTrue(canvas_event["auto_open"])
        self.assertEqual(canvas_event["documents"][0]["title"], "Draft")

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        messages = conversation_response.get_json()["messages"]
        assistant_messages = [message for message in messages if message["role"] == "assistant"]
        self.assertEqual(assistant_messages[-1]["metadata"]["canvas_documents"][0]["id"], "canvas-1")

    def test_chat_forwards_replace_mode_canvas_preview_updates(self):
        conversation_id = self._create_conversation()
        fake_events = iter(
            [
                {
                    "type": "canvas_tool_starting",
                    "tool": "replace_canvas_lines",
                    "preview_key": "canvas-call-0",
                    "snapshot": {"document_id": "canvas-1", "path": "docs/draft.md"},
                },
                {
                    "type": "canvas_content_delta",
                    "tool": "replace_canvas_lines",
                    "preview_key": "canvas-call-0",
                    "delta": "# Draft\n\nUpdated",
                    "snapshot": {"document_id": "canvas-1", "path": "docs/draft.md"},
                    "replace_content": True,
                },
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Update the draft",
                    "messages": [{"role": "user", "content": "Update the draft"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        preview_event = next((event for event in events if event["type"] == "canvas_content_delta"), None)
        self.assertIsNotNone(preview_event)
        self.assertTrue(preview_event["replace_content"])
        self.assertEqual(preview_event["delta"], "# Draft\n\nUpdated")

    def test_chat_forwards_committed_canvas_sync_before_trailing_answer_text(self):
        conversation_id = self._create_conversation()
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Preparing the committed draft..."},
                {
                    "type": "tool_capture",
                    "tool_results": [],
                    "canvas_modified": True,
                    "successful_canvas_mutation": True,
                    "canvas_documents": [
                        {
                            "id": "canvas-1",
                            "title": "Draft",
                            "format": "markdown",
                            "content": "# Draft\n\nCommitted body",
                        }
                    ],
                    "active_document_id": "canvas-1",
                },
                {"type": "answer_delta", "text": " The summary is ready now."},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Update the draft",
                    "messages": [{"role": "user", "content": "Update the draft"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        canvas_index = next(index for index, event in enumerate(events) if event["type"] == "canvas_sync")
        trailing_answer_index = next(
            index
            for index, event in enumerate(events)
            if event["type"] == "answer_delta" and event["text"] == " The summary is ready now."
        )
        self.assertLess(canvas_index, trailing_answer_index)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        messages = conversation_response.get_json()["messages"]
        assistant_messages = [message for message in messages if message["role"] == "assistant"]
        self.assertEqual(assistant_messages[-1]["metadata"]["canvas_documents"][0]["content"], "# Draft\n\nCommitted body")

    def test_chat_does_not_auto_open_canvas_when_state_is_unchanged(self):
        conversation_id = self._create_conversation()
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Answer without changing the canvas."},
                {
                    "type": "tool_capture",
                    "tool_results": [],
                    "canvas_modified": False,
                    "canvas_documents": [
                        {
                            "id": "canvas-existing",
                            "title": "Existing Draft",
                            "format": "markdown",
                            "content": "# Draft\n\nUnchanged",
                        }
                    ],
                },
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Answer the question",
                    "messages": [{"role": "user", "content": "Answer the question"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        canvas_event = next((event for event in events if event["type"] == "canvas_sync"), None)
        self.assertIsNotNone(canvas_event)
        self.assertFalse(canvas_event["auto_open"])

    def test_chat_persists_canvas_documents_without_text_response(self):
        conversation_id = self._create_conversation()
        fake_events = iter(
            [
                {
                    "type": "tool_capture",
                    "tool_results": [],
                    "canvas_documents": [
                        {
                            "id": "canvas-empty-answer",
                            "title": "Draft",
                            "format": "markdown",
                            "content": "# Draft\n\nInitial version",
                        }
                    ],
                },
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Create a draft",
                    "messages": [{"role": "user", "content": "Create a draft"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        canvas_event = next((event for event in events if event["type"] == "canvas_sync"), None)
        self.assertIsNotNone(canvas_event)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        messages = conversation_response.get_json()["messages"]
        assistant_messages = [message for message in messages if message["role"] == "assistant"]
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(assistant_messages[0]["content"], "")
        self.assertEqual(
            assistant_messages[0]["metadata"]["canvas_documents"][0]["id"],
            "canvas-empty-answer",
        )

    def test_chat_persists_cleared_canvas_without_documents(self):
        conversation_id = self._create_conversation()
        fake_events = iter(
            [
                {
                    "type": "tool_capture",
                    "tool_results": [],
                    "canvas_modified": True,
                    "canvas_documents": [],
                    "canvas_cleared": True,
                },
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Clear the canvas",
                    "messages": [{"role": "user", "content": "Clear the canvas"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        canvas_event = next((event for event in events if event["type"] == "canvas_sync"), None)
        self.assertIsNotNone(canvas_event)
        self.assertEqual(canvas_event["documents"], [])
        self.assertTrue(canvas_event["cleared"])

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        messages = conversation_response.get_json()["messages"]
        assistant_messages = [message for message in messages if message["role"] == "assistant"]
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(assistant_messages[0]["metadata"]["canvas_documents"], [])
        self.assertTrue(assistant_messages[0]["metadata"]["canvas_cleared"])

    def test_persist_streaming_assistant_message_upserts_partial_output(self):
        conversation_id = self._create_conversation()

        assistant_message_id = _persist_streaming_assistant_message(
            conversation_id,
            None,
            content="Partial answer.",
            reasoning="Reasoning in progress.",
            usage_data={"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
            tool_results=[{"tool_name": "fetch_url", "status": "ok"}],
            canvas_documents=[],
            active_document_id=None,
            canvas_cleared=False,
            tool_trace_entries=[{"tool_name": "fetch_url", "state": "done", "step": 1}],
            pending_clarification=None,
        )

        self.assertIsInstance(assistant_message_id, int)

        updated_message_id = _persist_streaming_assistant_message(
            conversation_id,
            assistant_message_id,
            content="Partial answer. Continued.",
            reasoning="Reasoning completed.",
            usage_data={"prompt_tokens": 4, "completion_tokens": 7, "total_tokens": 11},
            tool_results=[{"tool_name": "fetch_url", "status": "ok"}],
            canvas_documents=[],
            active_document_id=None,
            canvas_cleared=False,
            tool_trace_entries=[{"tool_name": "fetch_url", "state": "done", "step": 1}],
            pending_clarification=None,
        )

        self.assertEqual(updated_message_id, assistant_message_id)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        messages = conversation_response.get_json()["messages"]
        assistant_messages = [message for message in messages if message["role"] == "assistant"]
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(assistant_messages[0]["content"], "Partial answer. Continued.")
        self.assertEqual(assistant_messages[0]["usage"]["total_tokens"], 11)
        self.assertNotIn("reasoning_content", assistant_messages[0]["metadata"])

    def test_persist_streaming_assistant_message_ignores_reasoning_only_partial_output(self):
        conversation_id = self._create_conversation()

        assistant_message_id = _persist_streaming_assistant_message(
            conversation_id,
            None,
            content="",
            reasoning="Reasoning only.",
            usage_data=None,
            tool_results=[],
            canvas_documents=[],
            active_document_id=None,
            canvas_cleared=False,
            tool_trace_entries=[],
            pending_clarification=None,
        )

        self.assertIsNone(assistant_message_id)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        messages = conversation_response.get_json()["messages"]
        assistant_messages = [message for message in messages if message["role"] == "assistant"]
        self.assertEqual(assistant_messages, [])

    def test_persist_streaming_assistant_message_keeps_tool_only_partial_output(self):
        conversation_id = self._create_conversation()

        assistant_message_id = _persist_streaming_assistant_message(
            conversation_id,
            None,
            content="",
            reasoning="",
            usage_data=None,
            tool_results=[],
            sub_agent_traces=[{"status": "running", "task": "Inspect README.md"}],
            canvas_documents=[],
            active_document_id=None,
            canvas_cleared=False,
            tool_trace_entries=[{"tool_name": "sub_agent", "state": "running", "step": 1}],
            pending_clarification=None,
        )

        self.assertIsInstance(assistant_message_id, int)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        messages = conversation_response.get_json()["messages"]
        assistant_messages = [message for message in messages if message["role"] == "assistant"]
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(assistant_messages[0]["content"], "")
        self.assertTrue(assistant_messages[0]["metadata"]["tool_trace"])
        self.assertTrue(assistant_messages[0]["metadata"]["sub_agent_traces"])

    def test_cancel_chat_run_endpoint_sets_registered_run_state(self):
        run_id = "test-chat-run-cancel"
        run_state = _register_chat_run(run_id, conversation_id=123)
        self.addCleanup(lambda: _unregister_chat_run(run_id))

        response = self.client.post(f"/api/chat-runs/{run_id}/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"cancelled": True, "active": True})
        self.assertTrue(run_state["cancel_event"].is_set())
        self.assertTrue(_cancel_chat_run(run_id))

    def test_uploaded_document_prompts_before_opening_canvas(self):
        conversation_id = self._create_conversation()

        fake_events = iter([
            {"type": "done"},
        ])

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                data={
                    "conversation_id": str(conversation_id),
                    "model": "deepseek-chat",
                    "user_content": "Please review this file",
                    "messages": json.dumps([
                        {"role": "user", "content": "Please review this file"},
                    ]),
                    "document": (io.BytesIO(b"Project notes\n\nDetails"), "notes.txt", "text/plain"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        document_event = next((event for event in events if event["type"] == "document_processed"), None)
        self.assertIsNotNone(document_event)
        self.assertIn("canvas_document", document_event)

        canvas_event = next((event for event in events if event["type"] == "canvas_sync"), None)
        self.assertIsNotNone(canvas_event)
        self.assertFalse(canvas_event.get("auto_open"))

    def test_uploaded_document_can_skip_canvas_creation(self):
        conversation_id = self._create_conversation()

        with patch("routes.chat.run_agent_stream", return_value=iter([{"type": "done"}])):
            response = self.client.post(
                "/chat",
                data={
                    "conversation_id": str(conversation_id),
                    "model": "deepseek-chat",
                    "user_content": "Please review this file",
                    "messages": json.dumps([
                        {"role": "user", "content": "Please review this file"},
                    ]),
                    "document_canvas_action": "skip",
                    "document": (io.BytesIO(b"Project notes\n\nDetails"), "notes.txt", "text/plain"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        document_event = next((event for event in events if event["type"] == "document_processed"), None)
        self.assertIsNotNone(document_event)
        self.assertIsNone(document_event.get("canvas_document"))

        canvas_event = next((event for event in events if event["type"] == "canvas_sync"), None)
        self.assertIsNone(canvas_event)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        latest_canvas_state = find_latest_canvas_state(messages)
        self.assertEqual(latest_canvas_state["documents"], [])

    def test_uploaded_document_can_auto_open_canvas_when_requested(self):
        conversation_id = self._create_conversation()

        with patch("routes.chat.run_agent_stream", return_value=iter([{"type": "done"}])):
            response = self.client.post(
                "/chat",
                data={
                    "conversation_id": str(conversation_id),
                    "model": "deepseek-chat",
                    "user_content": "Please review this file",
                    "messages": json.dumps([
                        {"role": "user", "content": "Please review this file"},
                    ]),
                    "document_canvas_action": "open",
                    "document": (io.BytesIO(b"Project notes\n\nDetails"), "notes.txt", "text/plain"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        canvas_event = next((event for event in events if event["type"] == "canvas_sync"), None)
        self.assertIsNotNone(canvas_event)
        self.assertTrue(canvas_event.get("auto_open"))

    def test_edit_replay_with_existing_document_attachment_can_reopen_canvas(self):
        conversation_id = self._create_conversation()
        extracted_text = "Project notes\n\nDetails"
        context_block, text_truncated = build_document_context_block("notes.txt", extracted_text)
        file_asset = create_file_asset(
            conversation_id,
            "notes.txt",
            "text/plain",
            extracted_text.encode("utf-8"),
            extracted_text,
        )
        attachment = {
            "kind": "document",
            "file_id": file_asset["file_id"],
            "file_name": "notes.txt",
            "file_mime_type": "text/plain",
            "submission_mode": "text",
            "canvas_mode": "editable",
            "file_text_truncated": text_truncated,
            "file_context_block": context_block,
        }

        with get_db() as conn:
            edited_user_id = insert_message(
                conn,
                conversation_id,
                "user",
                "Please review this file",
                metadata=serialize_message_metadata({"attachments": [attachment]}),
            )
            insert_message(conn, conversation_id, "assistant", "Original answer")

        with patch("routes.chat.run_agent_stream", return_value=iter([{"type": "done"}])):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "edited_message_id": edited_user_id,
                    "document_canvas_action": "open",
                    "model": "deepseek-chat",
                    "user_content": "Please review this file again",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Please review this file again",
                            "metadata": {"attachments": [attachment]},
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        document_event = next((event for event in events if event["type"] == "document_processed"), None)
        self.assertIsNotNone(document_event)
        self.assertEqual(document_event["file_id"], file_asset["file_id"])
        self.assertEqual(document_event["attachment"]["file_id"], file_asset["file_id"])
        self.assertEqual(document_event["canvas_document"]["content"], "# notes.txt\n\nProject notes\n\nDetails")

        canvas_event = next((event for event in events if event["type"] == "canvas_sync"), None)
        self.assertIsNotNone(canvas_event)
        self.assertTrue(canvas_event.get("auto_open"))
        self.assertEqual(canvas_event["documents"][0]["source_file_id"], file_asset["file_id"])
        self.assertEqual(canvas_event["documents"][0]["content"], "# notes.txt\n\nProject notes\n\nDetails")

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        latest_canvas_state = find_latest_canvas_state(conversation_response.get_json()["messages"])
        self.assertEqual(len(latest_canvas_state["documents"]), 1)
        self.assertEqual(latest_canvas_state["documents"][0]["source_file_id"], file_asset["file_id"])
        self.assertEqual(latest_canvas_state["documents"][0]["content"], "# notes.txt\n\nProject notes\n\nDetails")

    def test_render_pdf_pages_for_vision_limits_output_to_first_pages(self):
        fake_pdf = SimpleNamespace(pages=[object(), object(), object(), object()])

        class _FakePdfContext:
            def __enter__(self_inner):
                return fake_pdf

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        rendered_payloads = [
            (b"page-1", "image/jpeg"),
            (b"page-2", "image/jpeg"),
            (b"page-3", "image/jpeg"),
            (b"page-4", "image/jpeg"),
        ]

        with patch("doc_service.pdfplumber.open", return_value=_FakePdfContext()), patch(
            "doc_service._render_pdf_page_image_bytes",
            side_effect=rendered_payloads,
        ) as render_page:
            pages = render_pdf_pages_for_vision(b"%PDF-1.4", max_pages=3)

        self.assertEqual(len(pages), 3)
        self.assertEqual([page["page_number"] for page in pages], [1, 2, 3])
        self.assertEqual([page["image_bytes"] for page in pages], [b"page-1", b"page-2", b"page-3"])
        self.assertEqual([page["mime_type"] for page in pages], ["image/jpeg", "image/jpeg", "image/jpeg"])
        self.assertTrue(all(page["truncated"] is True for page in pages))
        self.assertTrue(all(page["total_pages"] == 4 for page in pages))
        self.assertEqual(render_page.call_count, 3)

    def test_render_pdf_pages_for_vision_skips_failed_pages_and_returns_partial_result(self):
        fake_pdf = SimpleNamespace(pages=[object(), object()])

        class _FakePdfContext:
            def __enter__(self_inner):
                return fake_pdf

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        with patch("doc_service.pdfplumber.open", return_value=_FakePdfContext()), patch(
            "doc_service._render_pdf_page_image_bytes",
            side_effect=[(b"page-1", "image/jpeg"), ValueError("bad page bitmap")],
        ):
            pages = render_pdf_pages_for_vision(b"%PDF-1.4", max_pages=2)

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["page_number"], 1)
        self.assertEqual(pages[0]["image_bytes"], b"page-1")
        self.assertEqual(pages[0]["failed_page_numbers"], [2])
        self.assertTrue(pages[0]["partial_failure"])

    def test_render_pdf_pages_for_vision_raises_when_all_pages_fail(self):
        fake_pdf = SimpleNamespace(pages=[object(), object()])

        class _FakePdfContext:
            def __enter__(self_inner):
                return fake_pdf

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        with patch("doc_service.pdfplumber.open", return_value=_FakePdfContext()), patch(
            "doc_service._render_pdf_page_image_bytes",
            side_effect=[ValueError("bad page bitmap"), ValueError("bad page bitmap")],
        ):
            with self.assertRaisesRegex(ValueError, "Failed pages: 1, 2"):
                render_pdf_pages_for_vision(b"%PDF-1.4", max_pages=2)

    def test_build_visual_canvas_markdown_reports_truncated_preview(self):
        content = build_visual_canvas_markdown("exam.pdf", 3, total_pages=7)

        self.assertIn("This PDF contains 7 pages.", content)
        self.assertIn("Only the first 3 are available in visual preview.", content)

    def test_build_api_messages_embeds_visual_pdf_pages(self):
        normalized = [
            {
                "role": "user",
                "content": "Please analyze this exam PDF.",
                "metadata": {
                    "attachments": [
                        {
                            "kind": "document",
                            "file_name": "exam.pdf",
                            "file_mime_type": "application/pdf",
                            "submission_mode": "visual",
                            "visual_page_count": 2,
                            "visual_page_image_ids": ["img-1", "img-2"],
                        }
                    ]
                },
            }
        ]

        with patch(
            "messages.read_image_asset_bytes",
            side_effect=[
                ({"mime_type": "image/jpeg"}, b"image-one"),
                ({"mime_type": "image/jpeg"}, b"image-two"),
            ],
        ):
            api_messages = build_api_messages(normalized, embed_visual_documents=True)

        self.assertEqual(len(api_messages), 1)
        self.assertIsInstance(api_messages[0]["content"], list)
        text_blocks = [block for block in api_messages[0]["content"] if block.get("type") == "text"]
        image_blocks = [block for block in api_messages[0]["content"] if block.get("type") == "image_url"]
        self.assertTrue(any("exam.pdf" in str(block.get("text") or "") for block in text_blocks))
        self.assertEqual(len(image_blocks), 2)
        self.assertTrue(all(str(block["image_url"]["url"]).startswith("data:image/jpeg;base64,") for block in image_blocks))

    def test_build_api_messages_warns_when_visual_pdf_image_asset_is_missing(self):
        normalized = [
            {
                "role": "user",
                "content": "Please analyze this exam PDF.",
                "metadata": {
                    "attachments": [
                        {
                            "kind": "document",
                            "file_name": "exam.pdf",
                            "file_mime_type": "application/pdf",
                            "submission_mode": "visual",
                            "visual_page_count": 3,
                            "visual_page_numbers": [1, 2, 3],
                            "visual_page_image_ids": ["img-1", "img-2", "img-3"],
                        }
                    ]
                },
            }
        ]

        with patch(
            "messages.read_image_asset_bytes",
            side_effect=[
                ({"mime_type": "image/jpeg"}, b"image-one"),
                (None, None),
                ({"mime_type": "image/jpeg"}, b"image-three"),
            ],
        ):
            api_messages = build_api_messages(normalized, embed_visual_documents=True)

        self.assertEqual(len(api_messages), 1)
        self.assertIsInstance(api_messages[0]["content"], list)
        text_blocks = [block for block in api_messages[0]["content"] if block.get("type") == "text"]
        image_blocks = [block for block in api_messages[0]["content"] if block.get("type") == "image_url"]
        self.assertEqual(len(image_blocks), 2)
        self.assertTrue(any("visual PDF preview images" in str(block.get("text") or "") for block in text_blocks))
        self.assertTrue(any("page(s): 2" in str(block.get("text") or "") for block in text_blocks))

    def test_build_api_messages_preserves_visual_pdf_warning_when_all_pages_are_missing(self):
        normalized = [
            {
                "role": "user",
                "content": "Please analyze this exam PDF.",
                "metadata": {
                    "attachments": [
                        {
                            "kind": "document",
                            "file_name": "exam.pdf",
                            "file_mime_type": "application/pdf",
                            "submission_mode": "visual",
                            "visual_page_count": 2,
                            "visual_page_numbers": [1, 2],
                            "visual_page_image_ids": ["img-1", "img-2"],
                        }
                    ]
                },
            }
        ]

        with patch("messages.read_image_asset_bytes", return_value=(None, None)):
            api_messages = build_api_messages(normalized, embed_visual_documents=True)

        self.assertEqual(len(api_messages), 1)
        self.assertIsInstance(api_messages[0]["content"], str)
        self.assertIn("Please analyze this exam PDF.", api_messages[0]["content"])
        self.assertIn("visual PDF preview images", api_messages[0]["content"])

    def test_chat_accepts_visual_pdf_mode_and_emits_preview_only_document_event(self):
        captured = {}
        conversation_id = self._create_conversation()

        def fake_run_agent_stream(api_messages, *args, **kwargs):
            captured["api_messages"] = api_messages
            return iter([
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Analyzed visually."},
                {"type": "done"},
            ])

        rendered_pages = [
            {"page_number": 1, "mime_type": "image/jpeg", "image_bytes": b"page-one"},
            {"page_number": 2, "mime_type": "image/jpeg", "image_bytes": b"page-two"},
        ]

        with patch("routes.chat.can_model_process_images", return_value=True), patch(
            "routes.chat.render_pdf_pages_for_vision",
            return_value=rendered_pages,
        ), patch("routes.chat.run_agent_stream", side_effect=fake_run_agent_stream):
            response = self.client.post(
                "/chat",
                data=MultiDict(
                    [
                        ("messages", json.dumps([{"role": "user", "content": "Analyze visually"}])),
                        ("model", "deepseek-chat"),
                        ("conversation_id", str(conversation_id)),
                        ("user_content", "Analyze visually"),
                        ("document_modes", json.dumps([{"file_name": "exam.pdf", "submission_mode": "visual"}])),
                        ("document", (io.BytesIO(b"%PDF-1.4 fake pdf bytes"), "exam.pdf", "application/pdf")),
                    ]
                ),
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        document_event = next((event for event in events if event["type"] == "document_processed"), None)
        self.assertIsNotNone(document_event)
        self.assertTrue(document_event.get("visual_only"))
        self.assertIn("canvas_document", document_event)

        canvas_event = next((event for event in events if event["type"] == "canvas_sync"), None)
        self.assertIsNotNone(canvas_event)
        self.assertEqual(len(canvas_event.get("documents") or []), 1)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        user_message = next(message for message in messages if message["role"] == "user")
        attachments = user_message["metadata"].get("attachments") or []
        document_attachment = next(entry for entry in attachments if entry["kind"] == "document")
        self.assertEqual(document_attachment["submission_mode"], "visual")
        self.assertEqual(document_attachment["canvas_mode"], "preview_only")
        self.assertEqual(document_attachment["visual_page_count"], 2)
        self.assertEqual(len(document_attachment["visual_page_image_ids"]), 2)
        stored_page_bytes = [read_image_asset_bytes(image_id)[1] for image_id in document_attachment["visual_page_image_ids"]]
        self.assertEqual(stored_page_bytes, [b"page-one", b"page-two"])

        latest_canvas_state = find_latest_canvas_state(messages)
        self.assertEqual(len(latest_canvas_state["documents"]), 1)
        visual_document = latest_canvas_state["documents"][0]
        self.assertEqual(visual_document["content_mode"], "visual")
        self.assertEqual(visual_document["canvas_mode"], "preview_only")
        self.assertEqual(visual_document["source_file_id"], document_attachment["file_id"])
        self.assertEqual(visual_document["source_mime_type"], "application/pdf")
        self.assertEqual(visual_document["visual_page_image_ids"], document_attachment["visual_page_image_ids"])
        self.assertEqual(visual_document["page_count"], 2)

        image_response = self.client.get(
            f"/api/conversations/{conversation_id}/images/{document_attachment['visual_page_image_ids'][0]}"
        )
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.mimetype, "image/jpeg")
        self.assertEqual(image_response.data, b"page-one")

        api_messages = captured["api_messages"]
        user_api_message = next(message for message in api_messages if message.get("role") == "user")
        self.assertIsInstance(user_api_message.get("content"), list)
        self.assertEqual(len([block for block in user_api_message["content"] if block.get("type") == "image_url"]), 2)

    def test_chat_visual_pdf_marks_truncation_metadata_when_preview_is_limited(self):
        conversation_id = self._create_conversation()

        rendered_pages = [
            {"page_number": 1, "mime_type": "image/jpeg", "image_bytes": b"page-one", "total_pages": 6, "truncated": True},
            {"page_number": 2, "mime_type": "image/jpeg", "image_bytes": b"page-two", "total_pages": 6, "truncated": True},
            {"page_number": 3, "mime_type": "image/jpeg", "image_bytes": b"page-three", "total_pages": 6, "truncated": True},
        ]

        with patch("routes.chat.can_model_process_images", return_value=True), patch(
            "routes.chat.render_pdf_pages_for_vision",
            return_value=rendered_pages,
        ), patch("routes.chat.run_agent_stream", return_value=iter([{"type": "done"}])):
            response = self.client.post(
                "/chat",
                data=MultiDict(
                    [
                        ("messages", json.dumps([{"role": "user", "content": "Analyze visually"}])),
                        ("model", "deepseek-chat"),
                        ("conversation_id", str(conversation_id)),
                        ("user_content", "Analyze visually"),
                        ("document_modes", json.dumps([{"file_name": "exam.pdf", "submission_mode": "visual"}])),
                        ("document", (io.BytesIO(b"%PDF-1.4 fake pdf bytes"), "exam.pdf", "application/pdf")),
                    ]
                ),
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        document_event = next((event for event in events if event["type"] == "document_processed"), None)
        self.assertIsNotNone(document_event)
        self.assertIn("Only the first 3 are available in visual preview.", document_event["canvas_document"]["content"])

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        user_message = next(message for message in messages if message["role"] == "user")
        attachments = user_message["metadata"].get("attachments") or []
        document_attachment = next(entry for entry in attachments if entry["kind"] == "document")
        self.assertEqual(document_attachment["visual_page_count"], 3)
        self.assertEqual(document_attachment["visual_total_page_count"], 6)
        self.assertTrue(document_attachment["visual_pages_truncated"])
        self.assertEqual(document_attachment["visual_page_limit"], 3)

        latest_canvas_state = find_latest_canvas_state(messages)
        self.assertEqual(len(latest_canvas_state["documents"]), 1)
        visual_document = latest_canvas_state["documents"][0]
        self.assertEqual(visual_document["content_mode"], "visual")
        self.assertEqual(visual_document["canvas_mode"], "preview_only")
        self.assertEqual(visual_document["source_file_id"], document_attachment["file_id"])
        self.assertEqual(visual_document["source_mime_type"], "application/pdf")
        self.assertEqual(visual_document["visual_page_image_ids"], document_attachment["visual_page_image_ids"])
        self.assertEqual(visual_document["page_count"], 3)

        image_response = self.client.get(
            f"/api/conversations/{conversation_id}/images/{document_attachment['visual_page_image_ids'][0]}"
        )
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.mimetype, "image/jpeg")
        self.assertEqual(image_response.data, b"page-one")

    def test_chat_visual_pdf_records_failed_render_pages_in_metadata(self):
        conversation_id = self._create_conversation()

        rendered_pages = [
            {"page_number": 1, "mime_type": "image/jpeg", "image_bytes": b"page-one", "total_pages": 3, "truncated": False},
            {"page_number": 3, "mime_type": "image/jpeg", "image_bytes": b"page-three", "total_pages": 3, "truncated": False},
        ]

        with patch("routes.chat.can_model_process_images", return_value=True), patch(
            "routes.chat.render_pdf_pages_for_vision",
            return_value=rendered_pages,
        ), patch("routes.chat.run_agent_stream", return_value=iter([{"type": "done"}])):
            response = self.client.post(
                "/chat",
                data=MultiDict(
                    [
                        ("messages", json.dumps([{"role": "user", "content": "Analyze visually"}])),
                        ("model", "deepseek-chat"),
                        ("conversation_id", str(conversation_id)),
                        ("user_content", "Analyze visually"),
                        ("document_modes", json.dumps([{"file_name": "exam.pdf", "submission_mode": "visual"}])),
                        ("document", (io.BytesIO(b"%PDF-1.4 fake pdf bytes"), "exam.pdf", "application/pdf")),
                    ]
                ),
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        user_message = next(message for message in messages if message["role"] == "user")
        attachments = user_message["metadata"].get("attachments") or []
        document_attachment = next(entry for entry in attachments if entry["kind"] == "document")
        self.assertEqual(document_attachment["visual_page_numbers"], [1, 3])
        self.assertEqual(document_attachment["visual_failed_pages"], [2])
        self.assertTrue(document_attachment["visual_pages_partial"])
        self.assertEqual(document_attachment["visual_page_count"], 2)

    def test_markdown_block_parser_preserves_ordered_list_start_numbers(self):
        blocks = _iter_markdown_blocks(
            "1. First phase\n\n- One\n\n2. Second phase\n\n- Two\n\n3. Third phase",
            preserve_inline_formatting=True,
        )

        ordered_starts = [
            block.get("start")
            for block in blocks
            if block.get("type") == "list" and block.get("kind") == "ordered"
        ]

        self.assertEqual(ordered_starts, [1, 2, 3])

    def test_canvas_export_endpoint_returns_markdown_and_pdf(self):
        conversation_id = self._create_conversation()
        metadata = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-export",
                        "title": "Draft Export",
                        "format": "markdown",
                        "content": "# Export\n\n1. First phase\n\n- One\n- Two\n\n2. Second phase\n\n- Three\n\n3. Third phase\n\n- Four",
                    }
                ]
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "assistant", "Here is the draft.", metadata=metadata)

        markdown_response = self.client.get(
            f"/api/conversations/{conversation_id}/canvas/export?format=md&document_id=canvas-export"
        )
        self.assertEqual(markdown_response.status_code, 200)
        self.assertEqual(markdown_response.mimetype, "text/markdown")
        self.assertIn("attachment; filename=\"Draft-Export.md\"", markdown_response.headers["Content-Disposition"])
        self.assertEqual(markdown_response.headers.get("Cache-Control"), "no-store, max-age=0")
        self.assertEqual(markdown_response.headers.get("Pragma"), "no-cache")
        self.assertEqual(markdown_response.headers.get("Expires"), "0")
        self.assertIn("# Export", markdown_response.get_data(as_text=True))

        pdf_response = self.client.get(
            f"/api/conversations/{conversation_id}/canvas/export?format=pdf&document_id=canvas-export"
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        self.assertEqual(pdf_response.headers.get("Cache-Control"), "no-store, max-age=0")
        self.assertEqual(pdf_response.headers.get("Pragma"), "no-cache")
        self.assertEqual(pdf_response.headers.get("Expires"), "0")
        self.assertTrue(pdf_response.data.startswith(b"%PDF"))

        with pdfplumber.open(io.BytesIO(pdf_response.data)) as pdf:
            pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        self.assertIn("Export", pdf_text)
        self.assertIn("One", pdf_text)
        self.assertIn("Four", pdf_text)
        self.assertRegex(pdf_text, r"1[.\s]+First phase")
        self.assertRegex(pdf_text, r"2[.\s]+Second phase")
        self.assertRegex(pdf_text, r"3[.\s]+Third phase")
        self.assertNotRegex(pdf_text, r"1[.\s]+Second phase")
        self.assertNotRegex(pdf_text, r"1[.\s]+Third phase")
        self.assertNotIn("# Export", pdf_text)
        self.assertNotIn("- One", pdf_text)
        self.assertIn("Lines:", pdf_text)
        self.assertIn("Pages:", pdf_text)
        self.assertNotIn("Role:", pdf_text)
        self.assertNotIn("Format:", pdf_text)
        self.assertNotIn("Page 1", pdf_text)

        html_response = self.client.get(
            f"/api/conversations/{conversation_id}/canvas/export?format=html&document_id=canvas-export"
        )
        self.assertEqual(html_response.status_code, 200)
        self.assertEqual(html_response.mimetype, "text/html")
        self.assertIn("attachment; filename=\"Draft-Export.html\"", html_response.headers["Content-Disposition"])
        self.assertEqual(html_response.headers.get("Cache-Control"), "no-store, max-age=0")
        self.assertEqual(html_response.headers.get("Pragma"), "no-cache")
        self.assertEqual(html_response.headers.get("Expires"), "0")
        self.assertIn("<ol>", html_response.get_data(as_text=True))
        self.assertIn("<ul>", html_response.get_data(as_text=True))

    def test_canvas_export_endpoint_renders_code_format(self):
        conversation_id = self._create_conversation()
        metadata = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-code-export",
                        "title": "main.py",
                        "format": "code",
                        "language": "python",
                        "content": "print('hello')",
                    }
                ]
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "assistant", "Here is the code.", metadata=metadata)

        markdown_response = self.client.get(
            f"/api/conversations/{conversation_id}/canvas/export?format=md&document_id=canvas-code-export"
        )
        self.assertEqual(markdown_response.status_code, 200)
        self.assertIn("```python", markdown_response.get_data(as_text=True))

        html_response = self.client.get(
            f"/api/conversations/{conversation_id}/canvas/export?format=html&document_id=canvas-code-export"
        )
        self.assertEqual(html_response.status_code, 200)
        self.assertIn("language-python", html_response.get_data(as_text=True))

    def test_canvas_export_endpoint_embeds_katex_for_math_documents(self):
        conversation_id = self._create_conversation()
        metadata = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-math-export",
                        "title": "Math Notes",
                        "format": "markdown",
                        "content": "# Math\n\nThe identity is $A = {0, 1, 2}$ and $$x^2 + y^2 = z^2$$.",
                    }
                ]
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "assistant", "Math ready.", metadata=metadata)

        html_response = self.client.get(
            f"/api/conversations/{conversation_id}/canvas/export?format=html&document_id=canvas-math-export"
        )
        self.assertEqual(html_response.status_code, 200)
        html_text = html_response.get_data(as_text=True)
        self.assertIn("katex.min.js", html_text)
        self.assertIn("auto-render.min.js", html_text)
        self.assertIn("renderMathInElement", html_text)

    def test_canvas_delete_endpoint_updates_canvas_state(self):
        conversation_id = self._create_conversation()
        metadata = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-one",
                        "title": "Draft One",
                        "format": "markdown",
                        "content": "# One",
                    },
                    {
                        "id": "canvas-two",
                        "title": "Draft Two",
                        "format": "markdown",
                        "content": "# Two",
                    },
                    {
                        "id": "canvas-three",
                        "title": "Draft Three",
                        "format": "markdown",
                        "content": "# Three",
                    },
                ]
                ,
                "active_document_id": "canvas-one",
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "assistant", "Canvas ready.", metadata=metadata)

        delete_response = self.client.delete(
            f"/api/conversations/{conversation_id}/canvas?document_id=canvas-three"
        )
        self.assertEqual(delete_response.status_code, 200)
        delete_payload = delete_response.get_json()
        self.assertFalse(delete_payload["cleared"])
        self.assertEqual(delete_payload["remaining_count"], 2)
        self.assertEqual(delete_payload["deleted_document_id"], "canvas-three")
        self.assertEqual(delete_payload["active_document_id"], "canvas-one")
        self.assertEqual(delete_payload["documents"][0]["id"], "canvas-one")
        self.assertEqual(delete_payload["documents"][1]["id"], "canvas-two")

        clear_response = self.client.delete(
            f"/api/conversations/{conversation_id}/canvas?clear_all=true"
        )
        self.assertEqual(clear_response.status_code, 200)
        clear_payload = clear_response.get_json()
        self.assertTrue(clear_payload["cleared"])
        self.assertEqual(clear_payload["remaining_count"], 0)
        self.assertEqual(clear_payload["documents"], [])

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        self.assertEqual(messages[-1]["role"], "tool")
        self.assertEqual(messages[-1]["metadata"]["canvas_documents"], [])
        self.assertTrue(messages[-1]["metadata"]["canvas_cleared"])

    def test_canvas_delete_endpoint_accepts_document_path(self):
        conversation_id = self._create_conversation()
        metadata = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-one",
                        "title": "app.py",
                        "path": "src/app.py",
                        "format": "code",
                        "content": "print('one')",
                    },
                    {
                        "id": "canvas-two",
                        "title": "config.py",
                        "path": "src/config.py",
                        "format": "code",
                        "content": "settings = {}",
                    },
                ],
                "active_document_id": "canvas-two",
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "assistant", "Canvas ready.", metadata=metadata)

        with patch("routes.conversations.sync_conversations_to_rag_safe") as mocked_sync_safe, patch(
            "routes.conversations.sync_conversations_to_rag_background"
        ) as mocked_sync_background:
            delete_response = self.client.delete(
                f"/api/conversations/{conversation_id}/canvas?document_path=src/config.py"
            )

        self.assertEqual(delete_response.status_code, 200)
        mocked_sync_safe.assert_called_once_with(conversation_id=conversation_id)
        mocked_sync_background.assert_not_called()
        delete_payload = delete_response.get_json()
        self.assertEqual(delete_payload["remaining_count"], 1)
        self.assertEqual(delete_payload["documents"][0]["path"], "src/app.py")

    def test_canvas_delete_endpoint_reassigns_active_document_when_active_deleted(self):
        conversation_id = self._create_conversation()
        metadata = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-one",
                        "title": "Draft One",
                        "format": "markdown",
                        "content": "# One",
                    },
                    {
                        "id": "canvas-two",
                        "title": "Draft Two",
                        "format": "markdown",
                        "content": "# Two",
                    },
                    {
                        "id": "canvas-three",
                        "title": "Draft Three",
                        "format": "markdown",
                        "content": "# Three",
                    },
                ],
                "active_document_id": "canvas-two",
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "assistant", "Canvas ready.", metadata=metadata)

        delete_response = self.client.delete(
            f"/api/conversations/{conversation_id}/canvas?document_id=canvas-two"
        )
        self.assertEqual(delete_response.status_code, 200)
        delete_payload = delete_response.get_json()
        self.assertFalse(delete_payload["cleared"])
        self.assertEqual(delete_payload["remaining_count"], 2)
        self.assertEqual(delete_payload["deleted_document_id"], "canvas-two")
        self.assertEqual(delete_payload["active_document_id"], "canvas-three")
        self.assertEqual(delete_payload["documents"][0]["id"], "canvas-one")
        self.assertEqual(delete_payload["documents"][1]["id"], "canvas-three")

    def test_canvas_patch_endpoint_updates_document_content_and_format(self):
        conversation_id = self._create_conversation()
        metadata = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-edit",
                        "title": "Draft",
                        "format": "markdown",
                        "content": "# Draft\n\nInitial",
                    }
                ]
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "assistant", "Here is the draft.", metadata=metadata)

        response = self.client.patch(
            f"/api/conversations/{conversation_id}/canvas",
            json={
                "document_id": "canvas-edit",
                "content": "print('saved')",
                "format": "code",
                "language": "python",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["document"]["format"], "code")
        self.assertEqual(payload["document"]["language"], "python")
        self.assertEqual(payload["document"]["content"], "print('saved')")

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        messages = conversation_response.get_json()["messages"]
        latest_canvas = find_latest_canvas_documents(messages)
        self.assertEqual(latest_canvas[0]["format"], "code")
        self.assertEqual(latest_canvas[0]["content"], "print('saved')")

    def test_canvas_patch_endpoint_accepts_document_path(self):
        conversation_id = self._create_conversation()
        metadata = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-edit",
                        "title": "app.py",
                        "path": "src/app.py",
                        "format": "code",
                        "content": "print('old')",
                    }
                ]
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "assistant", "Here is the draft.", metadata=metadata)

        response = self.client.patch(
            f"/api/conversations/{conversation_id}/canvas",
            json={
                "document_path": "src/app.py",
                "content": "print('new')",
                "format": "code",
                "language": "python",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["document"]["path"], "src/app.py")
        self.assertEqual(payload["document"]["content"], "print('new')")

    def test_canvas_patch_endpoint_accepts_title_label_as_document_path(self):
        conversation_id = self._create_conversation()
        metadata = serialize_message_metadata(
            {
                "canvas_documents": [
                    {
                        "id": "canvas-edit",
                        "title": "Arduino Kodu - RobotBeyni.ino",
                        "format": "code",
                        "language": "cpp",
                        "content": "int led = 13;",
                    }
                ]
            }
        )

        with get_db() as conn:
            insert_message(conn, conversation_id, "assistant", "Here is the sketch.", metadata=metadata)

        response = self.client.patch(
            f"/api/conversations/{conversation_id}/canvas",
            json={
                "document_path": "Arduino Kodu - RobotBeyni.ino",
                "content": "int led = 12;",
                "format": "code",
                "language": "cpp",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["document"]["title"], "Arduino Kodu - RobotBeyni.ino")
        self.assertEqual(payload["document"]["content"], "int led = 12;")

    def test_canvas_post_endpoint_saves_sub_agent_research_and_marks_trace(self):
        conversation_id = self._create_conversation()
        assistant_metadata = serialize_message_metadata(
            {
                "sub_agent_traces": [
                    {
                        "task": "Inspect the README setup section",
                        "status": "ok",
                        "summary": "Found the setup commands and dependency notes.",
                        "tool_trace": [
                            {
                                "tool_name": "read_file",
                                "step": 1,
                                "preview": "README.md",
                                "summary": "Read the setup section.",
                                "state": "done",
                            }
                        ],
                    }
                ]
            }
        )

        with get_db() as conn:
            assistant_message_id = insert_message(
                conn,
                conversation_id,
                "assistant",
                "Here is the research summary.",
                metadata=assistant_metadata,
            )

        response = self.client.post(
            f"/api/conversations/{conversation_id}/canvas",
            json={
                "title": "Research - README setup",
                "content": "# README setup\n\n## Task\n\nInspect the README setup section.\n\n## Research Steps\n\n- Read README.md (done): Setup section reviewed.\n- Checked install notes (done): Dependencies noted.",
                "format": "markdown",
                "source_assistant_message_id": assistant_message_id,
                "source_sub_agent_trace_index": 0,
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertTrue(payload["saved_sub_agent_trace"])
        self.assertEqual(payload["document"]["title"], "Research - README setup")
        self.assertEqual(payload["document"]["format"], "markdown")
        self.assertEqual(
            payload["document"]["content"],
            "# Research - README setup\n\n## Summary\n\nFound the setup commands and dependency notes.",
        )
        self.assertNotIn("## Task", payload["document"]["content"])
        self.assertNotIn("## Research Steps", payload["document"]["content"])

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        latest_canvas = find_latest_canvas_documents(messages)
        self.assertEqual(len(latest_canvas), 1)
        self.assertEqual(latest_canvas[0]["title"], "Research - README setup")

        updated_assistant = next(message for message in messages if message["id"] == assistant_message_id)
        trace_entry = updated_assistant["metadata"]["sub_agent_traces"][0]
        self.assertTrue(trace_entry["canvas_saved"])
        self.assertEqual(trace_entry["canvas_document_title"], "Research - README setup")
        self.assertEqual(trace_entry["canvas_document_id"], payload["document"]["id"])

    def test_canvas_post_endpoint_allows_blank_new_file_creation(self):
        conversation_id = self._create_conversation()

        response = self.client.post(
            f"/api/conversations/{conversation_id}/canvas",
            json={
                "title": "notes.md",
                "content": "",
                "format": "markdown",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["document"]["title"], "notes.md")
        self.assertEqual(payload["document"]["content"], "")
        self.assertEqual(payload["documents"][0]["title"], "notes.md")
        self.assertEqual(payload["documents"][0]["content"], "")
        self.assertEqual(payload["active_document_id"], payload["document"]["id"])

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        latest_canvas = find_latest_canvas_documents(messages)
        self.assertEqual(len(latest_canvas), 1)
        self.assertEqual(latest_canvas[0]["title"], "notes.md")
        self.assertEqual(latest_canvas[0]["content"], "")

    def test_canvas_post_endpoint_accepts_pdf_uploads_via_multipart(self):
        conversation_id = self._create_conversation()

        with patch("routes.conversations.extract_document_text", return_value="Question 1\nA) One\nB) Two"):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/canvas",
                data={
                    "file": (io.BytesIO(b"%PDF-1.4 fake pdf bytes"), "exam.pdf"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["document"]["title"], "exam.pdf")
        self.assertEqual(payload["document"]["format"], "markdown")
        self.assertIsNone(payload["document"].get("language"))
        self.assertEqual(payload["document"]["content"], "Question 1\nA) One\nB) Two")

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        latest_canvas = find_latest_canvas_documents(messages)
        self.assertEqual(len(latest_canvas), 1)
        self.assertEqual(latest_canvas[0]["title"], "exam.pdf")
        self.assertEqual(latest_canvas[0]["content"], "Question 1\nA) One\nB) Two")

    def test_document_canvas_inference_for_code_files(self):
        self.assertEqual(infer_canvas_format("main.py"), "code")
        self.assertEqual(infer_canvas_language("main.py"), "python")
        self.assertEqual(build_canvas_markdown("main.py", "print('hello')"), "print('hello')")
        self.assertEqual(infer_canvas_format("notes.md"), "markdown")

    def test_document_context_block_uses_markdown_for_pdf_uploads(self):
        context_block, truncated = build_document_context_block("openrouter.pdf", "A\nB\nC")

        self.assertFalse(truncated)
        self.assertIn("[Uploaded document: openrouter.pdf]", context_block)
        self.assertIn("# openrouter.pdf", context_block)
        self.assertIn("A\nB\nC", context_block)

    def test_document_context_block_uses_markdown_for_text_uploads(self):
        context_block, truncated = build_document_context_block("notes.txt", "first line\nsecond line")

        self.assertFalse(truncated)
        self.assertIn("[Uploaded document: notes.txt]", context_block)
        self.assertIn("# notes.txt", context_block)
        self.assertIn("first line\nsecond line", context_block)

    def test_document_context_block_truncates_source_before_markdown_rendering(self):
        with patch("doc_service.DOCUMENT_MAX_TEXT_CHARS", 5):
            context_block, truncated = build_document_context_block("notes.txt", "abcdef")

        self.assertTrue(truncated)
        self.assertIn("[Uploaded document: notes.txt]", context_block)
        self.assertIn("# notes.txt", context_block)
        self.assertIn("abcde", context_block)
        self.assertNotIn("abcdef", context_block)

    def test_format_table_as_markdown_produces_valid_markdown_table(self):
        table = [["Model", "Price", "Context"], ["GPT-4o", "$0.01", "128k"], ["Claude", "$0.015", "200k"]]
        result = _format_table_as_markdown(table)

        lines = result.splitlines()
        self.assertEqual(lines[0], "| Model | Price | Context |")
        self.assertEqual(lines[1], "| --- | --- | --- |")
        self.assertEqual(lines[2], "| GPT-4o | $0.01 | 128k |")
        self.assertEqual(lines[3], "| Claude | $0.015 | 200k |")

    def test_format_table_as_markdown_escapes_pipe_characters(self):
        table = [["A|B", "C"], ["1|2", "3"]]
        result = _format_table_as_markdown(table)

        self.assertIn("A\\|B", result)
        self.assertIn("1\\|2", result)

    def test_extract_text_csv_produces_markdown_table(self):
        csv_bytes = b"Name,Age,City\nAlice,30,Istanbul\nBob,25,Ankara"
        result = _extract_text_csv(csv_bytes)

        lines = result.splitlines()
        self.assertEqual(lines[0], "| Name | Age | City |")
        self.assertEqual(lines[1], "| --- | --- | --- |")
        self.assertIn("Alice", result)
        self.assertIn("Istanbul", result)

    def test_extract_text_csv_strips_utf8_bom(self):
        csv_bytes = b"\xef\xbb\xbfName,Age\nAlice,30"
        result = _extract_text_csv(csv_bytes)

        self.assertNotIn("\ufeff", result)
        self.assertIn("| Name | Age |", result)

    def test_extract_text_from_pdf_uses_ocr_for_image_only_pages(self):
        from PIL import Image

        class FakePage:
            def __init__(self):
                self.images = [{"x0": 0, "top": 0, "x1": 100, "bottom": 100}]

            def find_tables(self, **kwargs):
                return []

            def outside_bbox(self, bbox):
                return self

            def extract_text(self, **kwargs):
                return ""

            def to_image(self, **kwargs):
                return SimpleNamespace(original=Image.new("RGB", (40, 40), "white"))

        class FakePDF:
            def __init__(self):
                self.pages = [FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("doc_service.pdfplumber.open", return_value=FakePDF()):
            with patch("ocr_service.extract_image_text", return_value="SCANNED PAGE TEXT") as ocr_mock:
                result = _extract_text_from_pdf(b"%PDF-FAKE")

        self.assertEqual(result, "SCANNED PAGE TEXT")
        ocr_mock.assert_called_once()

    def test_extract_text_from_pdf_orders_two_column_pages_by_column(self):
        class FakeCrop:
            def extract_text(self, **kwargs):
                return ""

        class FakePage:
            width = 600
            height = 800
            images = []

            def find_tables(self, **kwargs):
                return []

            def outside_bbox(self, bbox):
                return self

            def crop(self, bbox):
                return FakeCrop()

            def extract_words(self, **kwargs):
                words = []
                for line_index in range(1, 13):
                    top = 40 + (line_index * 18)
                    words.extend(
                        [
                            {"text": f"Left{line_index}", "x0": 20, "x1": 70, "top": top, "bottom": top + 10},
                            {"text": "alpha", "x0": 78, "x1": 120, "top": top, "bottom": top + 10},
                            {"text": f"Right{line_index}", "x0": 340, "x1": 405, "top": top, "bottom": top + 10},
                            {"text": "beta", "x0": 408, "x1": 442, "top": top, "bottom": top + 10},
                        ]
                    )
                return words

            def extract_text(self, **kwargs):
                return "INTERLEAVED LAYOUT TEXT"

        class FakePDF:
            def __init__(self):
                self.pages = [FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("doc_service.pdfplumber.open", return_value=FakePDF()):
            result = _extract_text_from_pdf(b"%PDF-FAKE")

        self.assertIn("Left1 alpha\nLeft2 alpha", result)
        self.assertIn("Right1 beta\nRight2 beta", result)
        self.assertLess(result.index("Left12 alpha"), result.index("Right1 beta"))
        self.assertNotIn("INTERLEAVED LAYOUT TEXT", result)

    def test_extract_text_from_pdf_filters_repeated_headers_and_footers(self):
        class FakeCrop:
            def __init__(self, text):
                self._text = text

            def extract_text(self, **kwargs):
                return self._text

        class FakePage:
            width = 600
            height = 800
            images = []

            def __init__(self, page_num):
                self.page_num = page_num

            def find_tables(self, **kwargs):
                return []

            def outside_bbox(self, bbox):
                return self

            def crop(self, bbox):
                if bbox[1] == 0:
                    return FakeCrop("Company Confidential")
                return FakeCrop("Internal Use Only")

            def extract_words(self, **kwargs):
                return []

            def extract_text(self, **kwargs):
                return f"Company Confidential\nBody {self.page_num}\nInternal Use Only"

        class FakePDF:
            def __init__(self):
                self.pages = [FakePage(1), FakePage(2), FakePage(3)]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("doc_service.pdfplumber.open", return_value=FakePDF()):
            result = _extract_text_from_pdf(b"%PDF-FAKE")

        self.assertIn("Body 1", result)
        self.assertIn("Body 2", result)
        self.assertIn("Body 3", result)
        self.assertNotIn("Company Confidential", result)
        self.assertNotIn("Internal Use Only", result)

    def test_extract_text_from_pdf_prefers_cleaner_linear_text_over_fragmented_layout(self):
        class FakeCrop:
            def extract_text(self, **kwargs):
                return ""

        class FakePage:
            width = 600
            height = 800
            images = []

            def find_tables(self, **kwargs):
                return []

            def outside_bbox(self, bbox):
                return self

            def crop(self, bbox):
                return FakeCrop()

            def extract_words(self, **kwargs):
                return []

            def extract_text(self, **kwargs):
                if kwargs.get("layout"):
                    return "M\nksızın\nAÇIKLAMA\nDİKKATİ"
                return "Maksızın AÇIKLAMA DİKKATİ"

        class FakePDF:
            def __init__(self):
                self.pages = [FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("doc_service.pdfplumber.open", return_value=FakePDF()):
            result = _extract_text_from_pdf(b"%PDF-FAKE")

        self.assertIn("Maksızın AÇIKLAMA DİKKATİ", result)
        self.assertNotIn("M\nksızın", result)

    def test_extract_text_from_pdf_prunes_edge_page_noise(self):
        class FakeCrop:
            def extract_text(self, **kwargs):
                return ""

        class FakePage:
            width = 600
            height = 800
            images = []

            def find_tables(self, **kwargs):
                return []

            def outside_bbox(self, bbox):
                return self

            def crop(self, bbox):
                return FakeCrop()

            def extract_words(self, **kwargs):
                return []

            def extract_text(self, **kwargs):
                return "- 12 -\n••••\n1. Soru metni burada başlar\nA) Bir\nB) İki\n3"

        class FakePDF:
            def __init__(self):
                self.pages = [FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("doc_service.pdfplumber.open", return_value=FakePDF()):
            result = _extract_text_from_pdf(b"%PDF-FAKE")

        self.assertIn("1. Soru metni burada başlar", result)
        self.assertIn("A) Bir", result)
        self.assertIn("B) İki", result)
        self.assertNotIn("- 12 -", result)
        self.assertNotIn("••••", result)
        self.assertNotIn("\n3\n", f"\n{result}\n")

    def test_extract_text_from_pdf_prefers_ocr_for_image_heavy_noisy_pages(self):
        from PIL import Image

        class FakeCrop:
            def extract_text(self, **kwargs):
                return ""

        class FakePage:
            width = 600
            height = 800

            def __init__(self):
                self.images = [{"x0": 0, "top": 0, "x1": 600, "bottom": 800}]

            def find_tables(self, **kwargs):
                return []

            def outside_bbox(self, bbox):
                return self

            def crop(self, bbox):
                return FakeCrop()

            def extract_words(self, **kwargs):
                return []

            def extract_text(self, **kwargs):
                if kwargs.get("layout"):
                    return "- 8 -\nA B C D E\nM\netin"
                return "- 8 -\nA B C D E\nM\netin"

            def to_image(self, **kwargs):
                return SimpleNamespace(original=Image.new("RGB", (40, 40), "white"))

        class FakePDF:
            def __init__(self):
                self.pages = [FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("doc_service.pdfplumber.open", return_value=FakePDF()):
            with patch("ocr_service.extract_image_text", return_value="Metin sorusu temiz olarak okundu.") as ocr_mock:
                result = _extract_text_from_pdf(b"%PDF-FAKE")

        self.assertEqual(result, "Metin sorusu temiz olarak okundu.")
        ocr_mock.assert_called_once()

    def test_extract_document_text_raises_clear_error_for_pdf_parser_failures(self):
        with patch("doc_service.pdfplumber.open", side_effect=RuntimeError("broken PDF parser")):
            with self.assertRaisesRegex(ValueError, "Could not read the PDF document: broken PDF parser"):
                extract_document_text(b"%PDF-FAKE", "application/pdf")

    def test_looks_like_real_table_accepts_small_borderless_tables(self):
        table = [["Model", "Price", "Context"], ["GPT-4o", "$0.01", "128k"]]

        self.assertTrue(_looks_like_real_table(table))

    def test_borderless_table_parser_extracts_columns_from_word_positions(self):
        """Simulates a borderless tabular PDF page with 4 columns of aligned words."""

        class FakeWord(dict):
            pass

        def word(text, x0, x1, top):
            return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": top + 10}

        words = [
            # Header (line Y=10)
            word("Name", 10, 45, 10),
            word("Price", 100, 130, 10),
            word("Context", 200, 250, 10),
            word("Date", 320, 350, 10),
            # Data row 1 (Y=25)
            word("ModelA", 10, 60, 25),
            word("$0.10", 100, 130, 25),
            word("128k", 200, 230, 25),
            word("Jan", 320, 340, 25),
            word("2025", 345, 370, 25),
            # Data row 2 (Y=40)
            word("ModelB", 10, 60, 40),
            word("$0.05", 100, 130, 40),
            word("256k", 200, 230, 40),
            word("Feb", 320, 340, 40),
            word("2025", 345, 370, 40),
            # Data row 3 (Y=55)
            word("ModelC:", 10, 65, 55),
            word("X", 70, 80, 55),
            word("$0.20", 100, 130, 55),
            word("64k", 200, 220, 55),
            word("Mar", 320, 340, 55),
            word("2025", 345, 370, 55),
        ]

        class FakePage:
            width = 400

            def find_tables(self, **kwargs):
                return []

            def extract_words(self, **kwargs):
                return words

        result = _try_extract_borderless_table(FakePage())

        self.assertIn("| Name |", result)
        self.assertIn("| --- |", result)
        self.assertIn("ModelA", result)
        self.assertIn("$0.10", result)
        self.assertIn("128k", result)
        self.assertIn("Jan 2025", result)

    def test_borderless_table_parser_handles_leading_date_fragment(self):
        """Date fragment appearing *before* the model row in Y-space must be
        attached to that model row, not to the preceding row."""

        def word(text, x0, x1, top):
            return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": top + 10}

        words = [
            # Header row (Y=10)
            word("Model", 10, 55, 10),
            word("Price", 100, 135, 10),
            word("Ctx", 200, 230, 10),
            word("Date", 320, 350, 10),
            # Row1 — full date on same line (Y=25)
            word("Model: A", 10, 70, 25),
            word("$0.10", 100, 130, 25),
            word("128k", 200, 228, 25),
            word("Jan 2025", 320, 385, 25),
            # Leading date fragment for Row2 (Y=38) — appears BEFORE row2 data
            word("26", 320, 336, 38),
            word("Feb", 338, 360, 38),
            # Row2 — data without date (Y=43)
            word("Model: B", 10, 70, 43),
            word("$0.05", 100, 130, 43),
            word("256k", 200, 228, 43),
            # Trailing year for Row2 (Y=50)
            word("2025", 320, 356, 50),
            # Row3 — full date on same line (Y=60)
            word("Model: C", 10, 70, 60),
            word("$0.20", 100, 130, 60),
            word("64k", 200, 228, 60),
            word("Mar 2025", 320, 388, 60),
            # Row4 (Y=75) — needed to reach _BORDERLESS_MIN_WORDS threshold
            word("Model: D", 10, 70, 75),
            word("$0.30", 100, 130, 75),
            word("512k", 200, 228, 75),
            word("Apr 2025", 320, 388, 75),
        ]

        class FakePage:
            width = 400

            def find_tables(self, **kwargs):
                return []

            def extract_words(self, **kwargs):
                return words

        result = _try_extract_borderless_table(FakePage())
        rows = [l for l in result.split("\n") if l.startswith("| ") and "---" not in l]
        dates = [r.split(" | ")[-1].strip().rstrip("|").strip() for r in rows]

        # Header row
        self.assertIn("Date", dates[0])
        # Row1 date must be clean
        self.assertEqual(dates[1], "Jan 2025")
        # Row2 date must be "26 Feb 2025" (leading + trailing merged)
        self.assertIn("26", dates[2])
        self.assertIn("Feb", dates[2])
        self.assertIn("2025", dates[2])
        # Row3 date must be clean
        self.assertEqual(dates[3], "Mar 2025")

    def test_borderless_table_parser_rejects_paragraph_text(self):
        """A single wide column of long text should not be detected as a table."""

        def word(text, x0, x1, top):
            return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": top + 10}

        words = [word(f"word{i}", 10, 50, i * 15) for i in range(25)]

        class FakePage:
            width = 400

            def find_tables(self, **kwargs):
                return []

            def extract_words(self, **kwargs):
                return words

        result = _try_extract_borderless_table(FakePage())

        self.assertEqual(result, "")

    def test_conversation_export_endpoint_returns_markdown_docx_and_pdf(self):
        conversation_id = self._create_conversation("Exportable Chat")

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "Hello")
            insert_message(
                conn,
                conversation_id,
                "assistant",
                "",
                metadata=serialize_message_metadata(
                    {
                        "reasoning_content": "This stale reasoning should never be exported.",
                    },
                    include_private_fields=True,
                ),
            )
            insert_message(
                conn,
                conversation_id,
                "assistant",
                "Here is the answer.\n\n1. First step\n\n- Inspect\n\n2. Second step\n\n- Fix\n\n3. Third step\n\n- Verify\n\n$A = {0, 1, 2}$ and $$x^2 + y^2 = z^2$$.",
                metadata=serialize_message_metadata(
                    {
                        "reasoning_content": "Reasoned through the request.",
                        "tool_trace": [
                            {
                                "tool_name": "search_web",
                                "step": 1,
                                "preview": "hello",
                                "summary": "1 web result found",
                                "state": "done",
                            }
                        ],
                    },
                    include_private_fields=True,
                ),
            )

        markdown_response = self.client.get(f"/api/conversations/{conversation_id}/export?format=md")
        self.assertEqual(markdown_response.status_code, 200)
        self.assertEqual(markdown_response.mimetype, "text/markdown")
        self.assertIn("attachment; filename=\"Exportable-Chat.md\"", markdown_response.headers["Content-Disposition"])
        self.assertIn("Message count: 2", markdown_response.get_data(as_text=True))
        self.assertIn("## 1. User", markdown_response.get_data(as_text=True))
        self.assertIn("## 2. Assistant", markdown_response.get_data(as_text=True))
        self.assertNotIn("_(empty)_", markdown_response.get_data(as_text=True))
        self.assertIn("### Reasoning", markdown_response.get_data(as_text=True))
        self.assertIn("Reasoned through the request.", markdown_response.get_data(as_text=True))
        self.assertNotIn("This stale reasoning should never be exported.", markdown_response.get_data(as_text=True))
        self.assertIn("### Tool Trace", markdown_response.get_data(as_text=True))
        self.assertIn("2. Second step", markdown_response.get_data(as_text=True))

        docx_response = self.client.get(f"/api/conversations/{conversation_id}/export?format=docx")
        self.assertEqual(docx_response.status_code, 200)
        self.assertEqual(
            docx_response.mimetype,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertTrue(docx_response.data.startswith(b"PK"))

        docx_document = Document(io.BytesIO(docx_response.data))
        docx_text = "\n".join(paragraph.text for paragraph in docx_document.paragraphs)
        self.assertIn("Reasoned through the request.", docx_text)
        self.assertNotIn("This stale reasoning should never be exported.", docx_text)
        self.assertIn("1. First step", docx_text)
        self.assertIn("2. Second step", docx_text)
        self.assertIn("3. Third step", docx_text)
        self.assertIn("A = {0, 1, 2}", docx_text)
        self.assertIn("x^2 + y^2 = z^2", docx_text)
        self.assertNotIn("$A = {0, 1, 2}$", docx_text)
        self.assertNotIn("```markdown", docx_text)
        self.assertNotIn("### Canvas", docx_text)

        pdf_response = self.client.get(f"/api/conversations/{conversation_id}/export?format=pdf")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        self.assertTrue(pdf_response.data.startswith(b"%PDF"))

        with pdfplumber.open(io.BytesIO(pdf_response.data)) as pdf:
            pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        self.assertIn("Reasoned through the request.", pdf_text)
        self.assertNotIn("This stale reasoning should never be exported.", pdf_text)
        self.assertRegex(pdf_text, r"1[.\s]+First step")
        self.assertRegex(pdf_text, r"2[.\s]+Second step")
        self.assertRegex(pdf_text, r"3[.\s]+Third step")
        self.assertNotRegex(pdf_text, r"1[.\s]+Second step")
        self.assertIn("A = {0, 1, 2}", pdf_text)
        self.assertIn("x^2 + y^2 = z^2", pdf_text)
        self.assertNotIn("$A = {0, 1, 2}$", pdf_text)
        self.assertNotIn("```markdown", pdf_text)
        self.assertNotIn("### Canvas", pdf_text)

    def test_conversation_export_endpoint_returns_raw_json_with_model_invocations(self):
        conversation_id = self._create_conversation("Raw Export Chat")

        with get_db() as conn:
            user_message_id = insert_message(conn, conversation_id, "user", "Hello")
            assistant_message_id = insert_message(
                conn,
                conversation_id,
                "assistant",
                "Here is the answer.",
                metadata=serialize_message_metadata(
                    {
                        "reasoning_content": "Reasoned through the request.",
                    },
                    include_private_fields=True,
                ),
            )
            insert_model_invocation(
                conn,
                conversation_id,
                assistant_message_id=assistant_message_id,
                source_message_id=user_message_id,
                step=1,
                call_index=1,
                call_type="agent_step",
                provider="deepseek",
                api_model="deepseek-chat",
                request_payload={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
                response_summary={
                    "status": "ok",
                    "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
                    "reasoning_text": "Reasoned through the request.",
                    "content_text": "Let me think.",
                },
            )
            insert_model_invocation(
                conn,
                conversation_id,
                assistant_message_id=assistant_message_id,
                source_message_id=user_message_id,
                step=1,
                call_index=2,
                call_type="final_answer",
                provider="deepseek",
                api_model="deepseek-chat",
                request_payload={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Let me think."},
                    ],
                    "stream": True,
                },
                response_summary={
                    "status": "ok",
                    "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
                    "content_text": "Here is the answer.",
                },
            )

        response = self.client.get(f"/api/conversations/{conversation_id}/export?format=json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertIn("attachment; filename=\"Raw-Export-Chat.json\"", response.headers["Content-Disposition"])

        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(payload["export_type"], "conversation_raw_model_invocations")
        self.assertEqual(payload["capture_status"]["status"], "available")
        self.assertEqual(payload["capture_status"]["invocation_count"], 2)
        self.assertEqual(payload["invocations"][0]["request"]["messages"][0]["content"], "Hello")
        self.assertEqual(payload["invocations"][1]["call_type"], "final_answer")
        self.assertTrue(payload["transcript"][1]["has_reasoning"])
        self.assertTrue(payload["transcript"][0]["created_at"])
        self.assertTrue(payload["transcript"][1]["created_at"])
        self.assertIn("metadata", payload["transcript"][1])
        self.assertEqual(
            payload["transcript"][1]["metadata"]["reasoning_content"],
            "Reasoned through the request.",
        )

    def test_conversation_export_endpoint_marks_legacy_json_export_when_no_exact_snapshots(self):
        conversation_id = self._create_conversation("Legacy Raw Export")

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "Hello")
            insert_message(conn, conversation_id, "assistant", "Legacy answer")

        response = self.client.get(f"/api/conversations/{conversation_id}/export?format=json")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(payload["capture_status"]["status"], "unavailable_for_legacy_conversation")
        self.assertEqual(payload["invocations"], [])
        self.assertIn("Exact snapshots are only available", payload["limitations"][0])

    def test_conversation_export_endpoint_includes_attachments_and_sub_agent_traces(self):
        conversation_id = self._create_conversation("Detailed Export")

        with get_db() as conn:
            insert_message(
                conn,
                conversation_id,
                "user",
                "Please review the attachment.",
                metadata=serialize_message_metadata(
                    {
                        "attachments": [
                            {
                                "kind": "document",
                                "file_id": "file-123",
                                "file_name": "report.pdf",
                                "file_mime_type": "application/pdf",
                                "file_context_block": "# Report\n\nThe monthly report content.",
                                "submission_mode": "text",
                            }
                        ]
                    }
                ),
            )
            insert_message(
                conn,
                conversation_id,
                "assistant",
                "I inspected the file.",
                metadata=serialize_message_metadata(
                    {
                        "sub_agent_traces": [
                            {
                                "task": "Inspect report",
                                "status": "done",
                                "model": "deepseek-chat",
                                "summary": "Reviewed the attachment and found the main points.",
                                "fallback_note": "Continued on deepseek-chat after timeout.",
                                "canvas_saved": True,
                                "canvas_document_id": "canvas-report-1",
                                "canvas_document_title": "Report Notes",
                                "tool_trace": [
                                    {
                                        "tool_name": "read_file",
                                        "step": 1,
                                        "summary": "Read report.pdf",
                                        "state": "done",
                                    }
                                ],
                                "artifacts": [
                                    {"kind": "tool_output", "label": "Extracted text", "value": "Monthly report summary"}
                                ],
                                "messages": [
                                    {"role": "assistant", "content": "Starting review."},
                                ],
                            }
                        ]
                    }
                ),
            )

        response = self.client.get(f"/api/conversations/{conversation_id}/export?format=md")
        self.assertEqual(response.status_code, 200)

        exported_text = response.get_data(as_text=True)
        self.assertIn("Conversation ID:", exported_text)
        self.assertIn("Message count: 2", exported_text)
        self.assertIn("### Attachments", exported_text)
        self.assertIn("report.pdf", exported_text)
        self.assertIn("### Sub-Agent Traces", exported_text)
        self.assertIn("Inspect report", exported_text)
        self.assertIn("Canvas saved: Yes", exported_text)

    def test_conversation_export_endpoint_uses_client_reasoning_fallback_for_old_messages(self):
        conversation_id = self._create_conversation("Legacy Reasoning Export")

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "Hello")
            assistant_message_id = insert_message(
                conn,
                conversation_id,
                "assistant",
                "Legacy answer.",
                metadata=serialize_message_metadata(
                    {
                        "tool_trace": [
                            {
                                "tool_name": "search_web",
                                "step": 1,
                                "preview": "legacy",
                                "summary": "Legacy lookup",
                                "state": "done",
                            }
                        ],
                    }
                ),
            )

        get_response = self.client.get(f"/api/conversations/{conversation_id}/export?format=md")
        self.assertEqual(get_response.status_code, 200)
        self.assertNotIn("Recovered cached reasoning.", get_response.get_data(as_text=True))

        post_response = self.client.post(
            f"/api/conversations/{conversation_id}/export?format=md",
            json={"reasoning_by_message_id": {str(assistant_message_id): "Recovered cached reasoning."}},
        )
        self.assertEqual(post_response.status_code, 200)

        exported_text = post_response.get_data(as_text=True)
        self.assertIn("### Reasoning", exported_text)
        self.assertIn("Recovered cached reasoning.", exported_text)
        self.assertIn("Legacy answer.", exported_text)

    def test_conversation_payload_includes_message_created_at(self):
        conversation_id = self._create_conversation("Created At Chat")

        with get_db() as conn:
            insert_message(conn, conversation_id, "user", "Timestamp me")

        response = self.client.get(f"/api/conversations/{conversation_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["messages"][0]["content"], "Timestamp me")
        self.assertTrue(payload["messages"][0]["created_at"])

    def test_serialize_message_metadata_preserves_rich_tool_result_and_trace_fields(self):
        metadata = parse_message_metadata(
            serialize_message_metadata(
                {
                    "tool_results": [
                        {
                            "tool_name": "fetch_url",
                            "content": "Short fetched content.",
                            "summary": "Fetched page summary.",
                            "recovery_hint": "Use grep_fetched_content for an exact quote.",
                            "fetch_diagnostic": "HTTP 200 · cleaned HTML",
                            "meta_description": "Page description.",
                            "structured_data": '{"headline": "Demo"}',
                            "fetch_outcome": "success",
                            "content_mode": "clipped_text",
                            "raw_content_available": True,
                            "content_token_estimate": 12,
                            "content_char_count": 24,
                        }
                    ],
                    "tool_trace": [
                        {
                            "tool_name": "fetch_url",
                            "step": 1,
                            "state": "done",
                            "executed_at": "10:15:00",
                            "summary": "Fetched the page.",
                        }
                    ],
                },
                include_private_fields=True,
            ),
            include_private_fields=True,
        )

        self.assertEqual(metadata["tool_results"][0]["recovery_hint"], "Use grep_fetched_content for an exact quote.")
        self.assertEqual(metadata["tool_results"][0]["fetch_diagnostic"], "HTTP 200 · cleaned HTML")
        self.assertEqual(metadata["tool_results"][0]["meta_description"], "Page description.")
        self.assertEqual(metadata["tool_results"][0]["structured_data"], '{"headline": "Demo"}')
        self.assertEqual(metadata["tool_results"][0]["fetch_outcome"], "success")
        self.assertTrue(metadata["tool_results"][0]["raw_content_available"])
        self.assertEqual(metadata["tool_results"][0]["content_char_count"], 24)
        self.assertEqual(metadata["tool_trace"][0]["executed_at"], "10:15:00")

    def test_raw_json_conversation_export_preserves_message_metadata(self):
        conversation_id = self._create_conversation("Metadata Export Chat")

        with get_db() as conn:
            insert_message(
                conn,
                conversation_id,
                "user",
                "Please inspect the fetched page.",
                metadata=serialize_message_metadata(
                    {
                        "attachments": [
                            {
                                "kind": "document",
                                "file_id": "file-123",
                                "file_name": "report.pdf",
                                "file_mime_type": "application/pdf",
                                "file_context_block": "# Report\n\nBody",
                            }
                        ]
                    }
                ),
            )
            insert_message(
                conn,
                conversation_id,
                "assistant",
                "I inspected it.",
                metadata=serialize_message_metadata(
                    {
                        "tool_trace": [
                            {
                                "tool_name": "fetch_url",
                                "step": 1,
                                "state": "done",
                                "executed_at": "10:15:00",
                                "summary": "Fetched page",
                            }
                        ],
                        "tool_results": [
                            {
                                "tool_name": "fetch_url",
                                "content": "Short fetched content.",
                                "summary": "Fetched page summary.",
                                "fetch_diagnostic": "HTTP 200 · cleaned HTML",
                                "recovery_hint": "Use grep_fetched_content for an exact quote.",
                            }
                        ],
                        "canvas_documents": [
                            {
                                "id": "canvas-1",
                                "title": "Notes",
                                "format": "markdown",
                                "content": "# Notes",
                            }
                        ],
                        "active_document_id": "canvas-1",
                    },
                    include_private_fields=True,
                ),
            )

        response = self.client.get(f"/api/conversations/{conversation_id}/export?format=json")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.get_data(as_text=True))
        user_entry = payload["transcript"][0]
        assistant_entry = payload["transcript"][1]

        self.assertEqual(user_entry["metadata"]["attachments"][0]["file_name"], "report.pdf")
        self.assertEqual(assistant_entry["metadata"]["tool_trace"][0]["executed_at"], "10:15:00")
        self.assertEqual(
            assistant_entry["metadata"]["tool_results"][0]["fetch_diagnostic"],
            "HTTP 200 · cleaned HTML",
        )
        self.assertEqual(assistant_entry["metadata"]["active_document_id"], "canvas-1")
        self.assertEqual(assistant_entry["metadata"]["canvas_documents"][0]["title"], "Notes")

    def test_frontend_normalize_history_entry_preserves_message_timestamps(self):
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn('created_at: String(source.created_at || "").trim()', script_text)
        self.assertIn('deleted_at: String(source.deleted_at || "").trim()', script_text)

    def test_conversation_export_endpoint_rejects_invalid_format(self):
        conversation_id = self._create_conversation("Exportable Chat")

        response = self.client.get(f"/api/conversations/{conversation_id}/export?format=txt")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "format must be md, json, docx, or pdf.")

    def test_canvas_line_replace_rejects_out_of_bounds_start_line(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "Draft",
                    "content": "line 1\nline 2",
                    "format": "markdown",
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "Line range exceeds"):
            replace_canvas_lines(runtime_state, 3, 3, ["replacement"], document_id="canvas-1")

    def test_canvas_line_replace_rejects_stale_expected_lines(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "Draft",
                    "content": "line 1\nline 2\nline 3",
                    "format": "markdown",
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "Canvas context drift detected"):
            replace_canvas_lines(
                runtime_state,
                2,
                2,
                ["replacement"],
                document_id="canvas-1",
                expected_lines=["old line 2"],
                expected_start_line=2,
            )

    def test_batch_canvas_edits_applies_mixed_operations_with_offsets(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "content": "alpha\nbeta\ngamma\ndelta\nepsilon\nzeta",
                }
            ]
        )

        result = batch_canvas_edits(
            runtime_state,
            [
                {"action": "replace", "start_line": 2, "end_line": 2, "lines": ["beta updated", "beta extra"]},
                {"action": "insert", "after_line": 5, "lines": ["inserted after epsilon"]},
                {"action": "delete", "start_line": 6, "end_line": 6},
            ],
            document_path="src/app.py",
            atomic=True,
        )

        self.assertEqual(result["applied_count"], 3)
        self.assertEqual(
            result["document"]["content"],
            "alpha\nbeta updated\nbeta extra\ngamma\ndelta\nepsilon\ninserted after epsilon",
        )
        self.assertEqual(result["changed_ranges"][1]["applied_after_line"], 6)
        self.assertEqual(result["changed_ranges"][2]["applied_start_line"], 8)

    def test_batch_canvas_edits_rejects_overlapping_operations(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "Draft",
                    "format": "markdown",
                    "content": "line 1\nline 2\nline 3",
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "overlap"):
            batch_canvas_edits(
                runtime_state,
                [
                    {"action": "replace", "start_line": 2, "end_line": 2, "lines": ["changed"]},
                    {"action": "insert", "after_line": 2, "lines": ["inserted"]},
                ],
                document_id="canvas-1",
            )

    def test_batch_canvas_edits_atomic_rolls_back_on_failure(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "Draft",
                    "format": "markdown",
                    "content": "line 1\nline 2\nline 3",
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "Line range exceeds"):
            batch_canvas_edits(
                runtime_state,
                [
                    {"action": "replace", "start_line": 2, "end_line": 2, "lines": ["changed"]},
                    {"action": "delete", "start_line": 99, "end_line": 99},
                ],
                document_id="canvas-1",
                atomic=True,
            )

        self.assertEqual(get_canvas_runtime_documents(runtime_state)[0]["content"], "line 1\nline 2\nline 3")

    def test_batch_canvas_edits_supports_multi_target_atomic_updates(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "a.py",
                    "path": "src/a.py",
                    "format": "code",
                    "content": "alpha\nbeta",
                },
                {
                    "id": "canvas-2",
                    "title": "b.py",
                    "path": "src/b.py",
                    "format": "code",
                    "content": "one\ntwo",
                },
            ]
        )

        result = batch_canvas_edits(
            runtime_state,
            [],
            atomic=True,
            targets=[
                {"document_path": "src/a.py", "operations": [{"action": "replace", "start_line": 2, "end_line": 2, "lines": ["beta updated"]}]},
                {"document_path": "src/b.py", "operations": [{"action": "insert", "after_line": 2, "lines": ["three"]}]},
            ],
        )

        self.assertEqual(result["action"], "batch_multi_edited")
        self.assertEqual(result["target_count"], 2)
        documents = {document["path"]: document for document in get_canvas_runtime_documents(runtime_state)}
        self.assertEqual(documents["src/a.py"]["content"], "alpha\nbeta updated")
        self.assertEqual(documents["src/b.py"]["content"], "one\ntwo\nthree")

    def test_batch_canvas_edits_multi_target_atomic_rolls_back_all_documents(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "a.py",
                    "path": "src/a.py",
                    "format": "code",
                    "content": "alpha\nbeta",
                },
                {
                    "id": "canvas-2",
                    "title": "b.py",
                    "path": "src/b.py",
                    "format": "code",
                    "content": "one\ntwo",
                },
            ]
        )

        with self.assertRaisesRegex(ValueError, "Line range exceeds"):
            batch_canvas_edits(
                runtime_state,
                [],
                atomic=True,
                targets=[
                    {"document_path": "src/a.py", "operations": [{"action": "replace", "start_line": 2, "end_line": 2, "lines": ["beta updated"]}]},
                    {"document_path": "src/b.py", "operations": [{"action": "delete", "start_line": 99, "end_line": 99}]},
                ],
            )

        documents = {document["path"]: document for document in get_canvas_runtime_documents(runtime_state)}
        self.assertEqual(documents["src/a.py"]["content"], "alpha\nbeta")
        self.assertEqual(documents["src/b.py"]["content"], "one\ntwo")

    def test_batch_canvas_edits_clears_auto_unpin_viewport_for_multi_line_delete(self):
        runtime_state = {"canvas": create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "content": "line 1\nline 2\nline 3\nline 4\nline 5",
                }
            ]
        )}
        set_canvas_viewport(runtime_state["canvas"], document_path="src/app.py", start_line=3, end_line=5, ttl_turns=3, auto_unpin_on_edit=True)

        _execute_tool(
            "batch_canvas_edits",
            {
                "document_path": "src/app.py",
                "operations": [
                    {"action": "delete", "start_line": 3, "end_line": 5},
                ],
            },
            runtime_state,
        )

        self.assertEqual(runtime_state["canvas"]["viewports"], {})

    def test_preview_canvas_changes_does_not_mutate_runtime_state(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "Draft",
                    "format": "markdown",
                    "content": "line 1\nline 2\nline 3",
                }
            ]
        )

        result = preview_canvas_changes(
            runtime_state,
            [{"action": "replace", "start_line": 2, "end_line": 2, "lines": ["updated line 2"]}],
            document_id="canvas-1",
        )

        self.assertEqual(result["preview"]["changes"][0]["before"], "line 2")
        self.assertEqual(result["preview"]["changes"][0]["after"], "updated line 2")
        self.assertEqual(get_canvas_runtime_documents(runtime_state)[0]["content"], "line 1\nline 2\nline 3")

    def test_transform_canvas_lines_supports_count_only_and_replace(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "config.py",
                    "path": "config.py",
                    "format": "code",
                    "content": "DEBUG = False\nDEBUG = False\nprint('done')",
                }
            ]
        )

        count_result = transform_canvas_lines(
            runtime_state,
            "DEBUG = False",
            "DEBUG = True",
            document_path="config.py",
            count_only=True,
        )
        self.assertEqual(count_result["matches_found"], 2)
        self.assertEqual(get_canvas_runtime_documents(runtime_state)[0]["content"], "DEBUG = False\nDEBUG = False\nprint('done')")

        apply_result = transform_canvas_lines(
            runtime_state,
            "DEBUG = False",
            "DEBUG = True",
            document_path="config.py",
        )
        self.assertEqual(apply_result["matches_replaced"], 2)
        self.assertEqual(get_canvas_runtime_documents(runtime_state)[0]["content"], "DEBUG = True\nDEBUG = True\nprint('done')")

    def test_execute_tool_count_only_transform_does_not_mutate_or_clear_viewport(self):
        runtime_state = {"canvas": create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "config.py",
                    "path": "config.py",
                    "format": "code",
                    "content": "DEBUG = False\nDEBUG = False\nprint('done')",
                }
            ]
        )}
        set_canvas_viewport(runtime_state["canvas"], document_path="config.py", start_line=1, end_line=2, ttl_turns=3, auto_unpin_on_edit=True)

        result, summary = _execute_tool(
            "transform_canvas_lines",
            {
                "document_path": "config.py",
                "pattern": "DEBUG = False",
                "replacement": "DEBUG = True",
                "count_only": True,
            },
            runtime_state,
        )

        self.assertEqual(result["action"], "transformed")
        self.assertEqual(result["matches_found"], 2)
        self.assertIn("Canvas transform matched", summary)
        self.assertEqual(get_canvas_runtime_documents(runtime_state["canvas"])[0]["content"], "DEBUG = False\nDEBUG = False\nprint('done')")
        self.assertNotEqual(runtime_state["canvas"]["viewports"], {})

    def test_execute_tool_transform_defaults_to_case_sensitive_and_reports_no_match(self):
        runtime_state = {"canvas": create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "config.py",
                    "path": "config.py",
                    "format": "code",
                    "content": "DEBUG = False\nprint('done')",
                }
            ]
        )}

        result, summary = _execute_tool(
            "transform_canvas_lines",
            {
                "document_path": "config.py",
                "pattern": "debug = false",
                "replacement": "DEBUG = True",
            },
            runtime_state,
        )

        self.assertEqual(result["action"], "transformed")
        self.assertEqual(result["matches_found"], 0)
        self.assertEqual(result["matches_replaced"], 0)
        self.assertIn("matched 0 line(s)", summary)
        self.assertEqual(get_canvas_runtime_documents(runtime_state["canvas"])[0]["content"], "DEBUG = False\nprint('done')")

    def test_transform_canvas_lines_rejects_empty_pattern(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "config.py",
                    "path": "config.py",
                    "format": "code",
                    "content": "DEBUG = False",
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "must not be empty"):
            transform_canvas_lines(
                runtime_state,
                "",
                "DEBUG = True",
                document_path="config.py",
            )

    def test_update_canvas_metadata_updates_summary_dependencies_and_symbols(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "README.md",
                    "path": "README.md",
                    "format": "markdown",
                    "content": "# Demo",
                    "dependencies": ["config.py"],
                    "symbols": ["create_app"],
                }
            ]
        )

        result = update_canvas_metadata(
            runtime_state,
            document_path="README.md",
            summary="Main documentation",
            role="docs",
            add_dependencies=["app.py"],
            remove_dependencies=["config.py"],
            add_symbols=["init_db"],
        )

        self.assertIn("summary", result["updated_fields"])
        self.assertIn("dependencies", result["updated_fields"])
        self.assertEqual(result["document"]["role"], "docs")
        self.assertEqual(result["document"]["dependencies"], ["app.py"])
        self.assertEqual(result["document"]["symbols"], ["create_app", "init_db"])

    def test_update_canvas_metadata_updates_imports_and_exports(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "content": "print('ok')",
                    "imports": ["flask"],
                    "exports": ["create_app"],
                }
            ]
        )

        result = update_canvas_metadata(
            runtime_state,
            document_path="src/app.py",
            add_imports=["sqlite3"],
            remove_imports=["flask"],
            add_exports=["main"],
            remove_exports=["create_app"],
        )

        self.assertIn("imports", result["updated_fields"])
        self.assertIn("exports", result["updated_fields"])
        self.assertEqual(result["document"]["imports"], ["sqlite3"])
        self.assertEqual(result["document"]["exports"], ["main"])

    def test_update_canvas_metadata_can_ignore_and_restore_document(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "legacy.py",
                    "path": "src/legacy.py",
                    "format": "code",
                    "language": "python",
                    "content": "print('legacy')",
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "ignored_reason"):
            update_canvas_metadata(
                runtime_state,
                document_path="src/legacy.py",
                ignored=True,
            )

        ignored_result = update_canvas_metadata(
            runtime_state,
            document_path="src/legacy.py",
            ignored=True,
            ignored_reason="Superseded by src/app.py",
        )

        self.assertTrue(ignored_result["document"]["ignored"])
        self.assertEqual(ignored_result["document"]["ignored_reason"], "Superseded by src/app.py")
        self.assertIn("ignored", ignored_result["updated_fields"])
        self.assertIn("ignored_reason", ignored_result["updated_fields"])

        ignored_tool_result = build_canvas_tool_result(ignored_result["document"], action="metadata_updated")
        self.assertEqual(ignored_tool_result["content"], "")
        self.assertFalse(ignored_tool_result["content_truncated"])

        validation_result = validate_canvas_document(runtime_state, document_path="src/legacy.py")
        self.assertEqual(validation_result["validator_used"], "none")
        self.assertIn("ignored canvas documents", validation_result["issues"][0]["message"])

        with self.assertRaisesRegex(ValueError, "ignored canvas document"):
            search_canvas_document(runtime_state, "legacy", document_path="src/legacy.py")

        restored_result = update_canvas_metadata(
            runtime_state,
            document_path="src/legacy.py",
            ignored=False,
        )

        self.assertNotIn("ignored", restored_result["document"])
        self.assertNotIn("ignored_reason", restored_result["document"])
        self.assertIn("ignored", restored_result["updated_fields"])
        self.assertIn("ignored_reason", restored_result["updated_fields"])

        restored_search = search_canvas_document(runtime_state, "legacy", document_path="src/legacy.py")
        self.assertGreater(restored_search["match_count"], 0)
        self.assertEqual(restored_search["matches"][0]["document_id"], "canvas-1")

    def test_overlapping_edit_clears_auto_unpin_canvas_viewport(self):
        runtime_state = {"canvas": create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "content": "line 1\nline 2\nline 3",
                }
            ]
        )}
        set_canvas_viewport(runtime_state["canvas"], document_path="src/app.py", start_line=2, end_line=3, ttl_turns=3, auto_unpin_on_edit=True)

        _execute_tool(
            "replace_canvas_lines",
            {
                "document_path": "src/app.py",
                "start_line": 2,
                "end_line": 2,
                "lines": ["line 2 updated"],
            },
            runtime_state,
        )

        self.assertEqual(runtime_state["canvas"]["viewports"], {})

    def test_execute_tool_set_canvas_viewport_defaults_auto_unpin_on_edit(self):
        runtime_state = {"canvas": create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "content": "line 1\nline 2\nline 3",
                }
            ]
        )}

        _execute_tool(
            "set_canvas_viewport",
            {
                "document_path": "src/app.py",
                "start_line": 2,
                "end_line": 3,
                "ttl_turns": 3,
            },
            runtime_state,
        )

        _execute_tool(
            "replace_canvas_lines",
            {
                "document_path": "src/app.py",
                "start_line": 2,
                "end_line": 2,
                "lines": ["line 2 updated"],
            },
            runtime_state,
        )

        self.assertEqual(runtime_state["canvas"]["viewports"], {})

    def test_canvas_tool_sets_include_new_canvas_tools(self):
        self.assertTrue(
            {
                "batch_read_canvas_documents",
                "preview_canvas_changes",
                "batch_canvas_edits",
                "transform_canvas_lines",
                "update_canvas_metadata",
                "validate_canvas_document",
                "set_canvas_viewport",
                "focus_canvas_page",
                "clear_canvas_viewport",
            }.issubset(CANVAS_TOOL_NAMES)
        )
        self.assertTrue(
            {
                "batch_canvas_edits",
                "transform_canvas_lines",
                "update_canvas_metadata",
                "set_canvas_viewport",
                "focus_canvas_page",
                "clear_canvas_viewport",
            }.issubset(CANVAS_MUTATION_TOOL_NAMES)
        )

    def test_execute_tool_runs_transform_metadata_and_viewport_tools(self):
        runtime_state = {"canvas": create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "content": "alpha\nbeta",
                }
            ]
        )}

        preview_result, _ = _execute_tool(
            "preview_canvas_changes",
            {
                "document_path": "src/app.py",
                "operations": [{"action": "insert", "after_line": 2, "lines": ["gamma"]}],
            },
            runtime_state,
        )
        self.assertEqual(preview_result["action"], "previewed")

        transform_result, _ = _execute_tool(
            "transform_canvas_lines",
            {
                "document_path": "src/app.py",
                "pattern": "beta",
                "replacement": "beta updated",
            },
            runtime_state,
        )
        self.assertEqual(transform_result["action"], "lines_transformed")

        metadata_result, _ = _execute_tool(
            "update_canvas_metadata",
            {
                "document_path": "src/app.py",
                "summary": "Main app file",
                "add_symbols": ["main"],
            },
            runtime_state,
        )
        self.assertEqual(metadata_result["action"], "metadata_updated")

        viewport_result, _ = _execute_tool(
            "set_canvas_viewport",
            {
                "document_path": "src/app.py",
                "start_line": 1,
                "end_line": 2,
                "ttl_turns": 2,
            },
            runtime_state,
        )
        self.assertEqual(viewport_result["action"], "viewport_set")

        focus_runtime_state = {
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "pdf-1",
                        "title": "report.pdf",
                        "path": "docs/report.pdf",
                        "format": "markdown",
                        "content": "## Page 1\n\nAlpha\n\n---\n\n## Page 2\n\nBeta",
                    }
                ]
            )
        }
        focus_result, focus_summary = _execute_tool(
            "focus_canvas_page",
            {
                "document_path": "docs/report.pdf",
                "page_number": 2,
                "ttl_turns": 2,
            },
            focus_runtime_state,
        )
        self.assertEqual(focus_result["action"], "page_focused")
        self.assertIn("page 2", focus_summary)

        clear_result, _ = _execute_tool(
            "clear_canvas_viewport",
            {"document_path": "src/app.py"},
            runtime_state,
        )
        self.assertEqual(clear_result["action"], "viewport_cleared")

    def test_execute_tool_runs_batch_read_and_validate_canvas_tools(self):
        runtime_state = {
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "canvas-1",
                        "title": "app.py",
                        "path": "src/app.py",
                        "format": "code",
                        "language": "python",
                        "content": "def broken(:\n    pass\n",
                    },
                    {
                        "id": "canvas-2",
                        "title": "README.md",
                        "path": "README.md",
                        "format": "markdown",
                        "content": "# Title\n\nBody",
                    },
                ]
            )
        }

        read_result, read_summary = _execute_tool(
            "batch_read_canvas_documents",
            {"documents": [{"document_path": "README.md"}, {"document_path": "src/app.py", "start_line": 1, "end_line": 2}]},
            runtime_state,
        )
        validate_result, validate_summary = _execute_tool(
            "validate_canvas_document",
            {"document_path": "src/app.py"},
            runtime_state,
        )

        self.assertEqual(read_result["action"], "batch_read")
        self.assertEqual(read_result["success_count"], 2)
        self.assertIn("Canvas batch read returned", read_summary)
        self.assertEqual(validate_result["action"], "validated")
        self.assertFalse(validate_result["is_valid"])
        self.assertIn("Canvas validation found", validate_summary)

    def test_execute_tool_runs_batch_canvas_edits(self):
        runtime_state = {
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "canvas-1",
                        "title": "app.py",
                        "path": "src/app.py",
                        "format": "code",
                        "content": "alpha\nbeta\ngamma",
                    }
                ]
            )
        }

        result, summary = _execute_tool(
            "batch_canvas_edits",
            {
                "document_path": "src/app.py",
                "operations": [
                    {"action": "replace", "start_line": 2, "end_line": 2, "lines": ["beta updated"]},
                    {"action": "insert", "after_line": 3, "lines": ["delta"]},
                ],
            },
            runtime_state,
        )

        self.assertEqual(result["action"], "lines_batch_edited")
        self.assertEqual(result["applied_count"], 2)
        self.assertIn("Canvas batch edit applied", summary)
        self.assertEqual(
            get_canvas_runtime_documents(runtime_state["canvas"])[0]["content"],
            "alpha\nbeta updated\ngamma\ndelta",
        )

    def test_execute_tool_batch_canvas_edits_infers_missing_action_from_range_fields(self):
        runtime_state = {
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "canvas-1",
                        "title": "app.py",
                        "path": "src/app.py",
                        "format": "code",
                        "content": "alpha\nbeta\ngamma",
                    }
                ]
            )
        }

        result, summary = _execute_tool(
            "batch_canvas_edits",
            {
                "document_path": "src/app.py",
                "operations": [
                    {"start_line": 2, "end_line": 2, "lines": ["beta updated"]},
                ],
            },
            runtime_state,
        )

        self.assertEqual(result["action"], "lines_batch_edited")
        self.assertEqual(result["applied_count"], 1)
        self.assertIn("Canvas batch edit applied", summary)
        self.assertEqual(
            get_canvas_runtime_documents(runtime_state["canvas"])[0]["content"],
            "alpha\nbeta updated\ngamma",
        )

    def test_execute_tool_batch_canvas_edits_repairs_nested_operation_shapes(self):
        runtime_state = {
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "canvas-1",
                        "title": "app.py",
                        "path": "src/app.py",
                        "format": "code",
                        "content": "alpha\nbeta\ngamma",
                    }
                ]
            )
        }

        result, summary = _execute_tool(
            "batch_canvas_edits",
            {
                "document_path": "src/app.py",
                "operations": [[{"replace": {"start_line": 2, "end_line": 2, "lines": "beta updated"}}]],
            },
            runtime_state,
        )

        self.assertEqual(result["action"], "lines_batch_edited")
        self.assertEqual(result["applied_count"], 1)
        self.assertIn("Canvas batch edit applied", summary)
        self.assertEqual(
            get_canvas_runtime_documents(runtime_state["canvas"])[0]["content"],
            "alpha\nbeta updated\ngamma",
        )

    def test_execute_tool_batch_canvas_edits_repairs_prose_wrapped_json_payloads(self):
        runtime_state = {
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "canvas-1",
                        "title": "app.py",
                        "path": "src/app.py",
                        "format": "code",
                        "content": "alpha\nbeta\ngamma",
                    }
                ]
            )
        }

        result, summary = _execute_tool(
            "batch_canvas_edits",
            {
                "document_path": "src/app.py",
                "operations": "Please apply these edits: [{\"start_line\": 2, \"end_line\": 2, \"lines\": [\"beta updated\"]}]",
            },
            runtime_state,
        )

        self.assertEqual(result["action"], "lines_batch_edited")
        self.assertEqual(result["applied_count"], 1)
        self.assertIn("Canvas batch edit applied", summary)
        self.assertEqual(
            get_canvas_runtime_documents(runtime_state["canvas"])[0]["content"],
            "alpha\nbeta updated\ngamma",
        )

    def test_execute_tool_batch_canvas_edits_repairs_stringified_wrapper_payloads(self):
        runtime_state = {
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "canvas-1",
                        "title": "app.py",
                        "path": "src/app.py",
                        "format": "code",
                        "content": "alpha\nbeta\ngamma",
                    }
                ]
            )
        }

        result, summary = _execute_tool(
            "batch_canvas_edits",
            {
                "document_path": "src/app.py",
                "operations": "```json\n{\"operations\": [{\"operation\": \"{'replace': {'start_line': 2, 'end_line': 2, 'lines': ['beta updated']}}\"}]}\n```",
            },
            runtime_state,
        )

        self.assertEqual(result["action"], "lines_batch_edited")
        self.assertEqual(result["applied_count"], 1)
        self.assertIn("Canvas batch edit applied", summary)
        self.assertEqual(
            get_canvas_runtime_documents(runtime_state["canvas"])[0]["content"],
            "alpha\nbeta updated\ngamma",
        )

    def test_execute_tool_skips_expand_when_active_canvas_is_already_fully_visible(self):
        runtime_state = {
            "canvas": create_canvas_runtime_state(
                [
                    {
                        "id": "canvas-1",
                        "title": "app.py",
                        "path": "src/app.py",
                        "format": "code",
                        "content": "alpha\nbeta\ngamma",
                    }
                ],
                active_document_id="canvas-1",
            ),
            "canvas_prompt": {"max_lines": 20, "max_tokens": 4000},
            "canvas_limits": {"expand_max_lines": 800, "scroll_window_lines": 200},
        }

        result, summary = _execute_tool(
            "expand_canvas_document",
            {"document_path": "src/app.py"},
            runtime_state,
        )

        self.assertEqual(result["action"], "already_visible")
        self.assertFalse(result["is_truncated"])
        self.assertEqual(result["visible_line_end"], 3)
        self.assertIn("already fully visible", result["reason"])
        self.assertIn("Canvas already fully visible", summary)

    def test_normalize_canvas_document_falls_back_to_default_title(self):
        normalized = normalize_canvas_document(
            {
                "id": "canvas-blank-title",
                "title": "   ",
                "format": "markdown",
                "content": "content",
            }
        )

        self.assertEqual(normalized["title"], "Canvas")

    def test_normalize_canvas_document_preserves_language_metadata(self):
        normalized = normalize_canvas_document(
            {
                "id": "canvas-python",
                "title": "script.py",
                "format": "markdown",
                "language": " Python ",
                "content": "print('hello')",
            }
        )

        self.assertEqual(normalized["language"], "python")

    def test_normalize_canvas_document_preserves_project_metadata(self):
        normalized = normalize_canvas_document(
            {
                "id": "canvas-project",
                "title": "app.py",
                "path": "./src/app.py",
                "role": "source",
                "summary": " Main application entry point ",
                "imports": ["config", "config", "os"],
                "exports": ["create_app"],
                "symbols": ["create_app", "main"],
                "dependencies": ["flask", "python-dotenv"],
                "project_id": "Demo App",
                "workspace_id": "Workspace-1",
                "format": "code",
                "language": "python",
                "content": "print('hello')",
            }
        )

        self.assertEqual(normalized["path"], "src/app.py")
        self.assertEqual(normalized["role"], "source")
        self.assertEqual(normalized["summary"], "Main application entry point")
        self.assertEqual(normalized["imports"], ["config", "os"])
        self.assertEqual(normalized["dependencies"], ["flask", "python-dotenv"])
        self.assertEqual(normalized["project_id"], "demoapp")
        self.assertEqual(normalized["workspace_id"], "workspace-1")

    def test_canvas_line_tools_accept_document_path(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-1",
                    "title": "app.py",
                    "path": "src/app.py",
                    "format": "code",
                    "content": "line 1\nline 2",
                }
            ]
        )

        updated = replace_canvas_lines(runtime_state, 2, 2, ["line changed"], document_path="src/app.py")
        self.assertEqual(updated["path"], "src/app.py")
        self.assertEqual(updated["content"], "line 1\nline changed")

    def test_canvas_line_tools_accept_unique_suffix_document_path(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-src",
                    "title": "main.py",
                    "path": "apps/demo/src/main.py",
                    "format": "code",
                    "content": "line 1\nline 2",
                },
                {
                    "id": "canvas-test",
                    "title": "main.py",
                    "path": "apps/demo/tests/main.py",
                    "format": "code",
                    "content": "test 1\ntest 2",
                },
            ]
        )

        updated = replace_canvas_lines(runtime_state, 2, 2, ["line changed"], document_path="src/main.py")

        self.assertEqual(updated["path"], "apps/demo/src/main.py")
        self.assertEqual(updated["content"], "line 1\nline changed")

    def test_canvas_line_tools_report_ambiguous_basename_document_path(self):
        runtime_state = create_canvas_runtime_state(
            [
                {
                    "id": "canvas-src",
                    "title": "main.py",
                    "path": "apps/demo/src/main.py",
                    "format": "code",
                    "content": "line 1\nline 2",
                },
                {
                    "id": "canvas-test",
                    "title": "main.py",
                    "path": "apps/demo/tests/main.py",
                    "format": "code",
                    "content": "test 1\ntest 2",
                },
            ]
        )

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            replace_canvas_lines(runtime_state, 1, 1, ["line changed"], document_path="main.py")

    def test_run_agent_stream_executes_native_tool_calls(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="Need current info. "),
                    self._stream_chunk(
                        tool_calls=[
                            {
                                "index": 0,
                                "id": "tool-call-1",
                                "function": {
                                    "name": "search_web",
                                    "arguments": '{"queries":["test query"]}',
                                },
                            }
                        ]
                    ),
                    self._stream_chunk(
                        usage=SimpleNamespace(
                            prompt_tokens=4,
                            prompt_cache_hit_tokens=1,
                            prompt_cache_miss_tokens=3,
                            completion_tokens=6,
                            total_tokens=10,
                        )
                    ),
                ]
            ),
            iter(
                [
                    self._stream_chunk(reasoning="Using fetched context. "),
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(
                        usage=SimpleNamespace(
                            prompt_tokens=3,
                            prompt_cache_hit_tokens=2,
                            prompt_cache_miss_tokens=1,
                            completion_tokens=5,
                            total_tokens=8,
                        )
                    ),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create, patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 3, ["search_web"]))

        event_types = [event["type"] for event in events]
        self.assertIn("step_started", event_types)
        self.assertIn("reasoning_start", event_types)
        self.assertIn({"type": "reasoning_delta", "text": "Need current info. "}, events)
        self.assertIn("step_update", event_types)
        self.assertIn("tool_result", event_types)
        self.assertIn("answer_start", event_types)
        self.assertIn({"type": "answer_delta", "text": "Final answer."}, events)

        for call in mocked_create.call_args_list:
            _, kwargs = call
            self.assertTrue(kwargs.get("stream"))

        first_call_kwargs = mocked_create.call_args_list[0].kwargs
        self.assertIn("tools", first_call_kwargs)
        self.assertEqual(first_call_kwargs["tool_choice"], "auto")

        second_call_kwargs = mocked_create.call_args_list[1].kwargs
        self.assertIn("tools", second_call_kwargs)
        self.assertEqual(second_call_kwargs["tool_choice"], "auto")

        usage_events = [event for event in events if event["type"] == "usage"]
        self.assertEqual(len(usage_events), 1)
        usage_event = usage_events[0]
        self.assertEqual(usage_event["prompt_tokens"], 7)
        self.assertEqual(usage_event["prompt_cache_hit_tokens"], 3)
        self.assertEqual(usage_event["prompt_cache_miss_tokens"], 4)
        self.assertEqual(usage_event["completion_tokens"], 11)
        self.assertEqual(usage_event["total_tokens"], 18)
        self.assertEqual(usage_event["cost"], 0.000006)
        self.assertGreater(usage_event["estimated_input_tokens"], 0)
        self.assertEqual(usage_event["max_input_tokens_per_call"], 4)
        self.assertGreater(usage_event["configured_prompt_max_input_tokens"], 0)
        self.assertGreater(usage_event["input_breakdown"]["user_messages"], 0)
        self.assertGreater(usage_event["input_breakdown"]["tool_results"], 0)
        self.assertEqual(usage_event["input_breakdown"].get("assistant_history", 0), 0)
        self.assertEqual(usage_event["model_call_count"], 2)
        self.assertEqual(len(usage_event["model_calls"]), 2)
        self.assertEqual(usage_event["model_calls"][0]["call_type"], "agent_step")
        self.assertEqual(usage_event["model_calls"][0]["step"], 1)
        self.assertFalse(usage_event["model_calls"][0]["missing_provider_usage"])
        self.assertEqual(usage_event["model_calls"][0]["prompt_cache_hit_tokens"], 1)
        self.assertEqual(usage_event["model_calls"][0]["prompt_cache_miss_tokens"], 3)
        self.assertEqual(usage_event["model_calls"][1]["call_type"], "agent_step")
        self.assertEqual(usage_event["model_calls"][1]["prompt_tokens"], 3)
        self.assertEqual(usage_event["model_calls"][1]["prompt_cache_hit_tokens"], 2)
        self.assertEqual(usage_event["model_calls"][1]["prompt_cache_miss_tokens"], 1)
        self.assertEqual(
            usage_event["model_calls"][1]["estimated_input_tokens"],
            usage_event["model_calls"][1]["prompt_tokens"],
        )

        second_call_messages = mocked_create.call_args_list[1].kwargs["messages"]
        self.assertEqual([message["role"] for message in second_call_messages], ["user", "assistant", "tool", "system"])
        self.assertEqual(second_call_messages[1]["tool_calls"][0]["function"]["name"], "search_web")
        self.assertEqual(second_call_messages[2]["tool_call_id"], "tool-call-1")
        self.assertIn("[AGENT REASONING CONTEXT]", second_call_messages[3]["content"])

        tool_history_event = next((event for event in events if event["type"] == "tool_history"), None)
        self.assertIsNotNone(tool_history_event)
        self.assertEqual(tool_history_event["messages"][0]["role"], "assistant")
        self.assertEqual(tool_history_event["messages"][1]["role"], "tool")

    def test_run_agent_stream_records_exact_invocation_snapshots(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="Thinking. "),
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
        ]
        invocation_log = []

        with patch("agent.client.chat.completions.create", side_effect=responses):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Test"}],
                    "deepseek-chat",
                    1,
                    [],
                    invocation_log_sink=invocation_log,
                )
            )

        self.assertIn({"type": "answer_delta", "text": "Final answer."}, events)
        self.assertEqual(len(invocation_log), 1)
        self.assertEqual(invocation_log[0]["call_type"], "agent_step")
        self.assertEqual(invocation_log[0]["provider"], "deepseek")
        self.assertEqual(invocation_log[0]["api_model"], "deepseek-chat")
        self.assertEqual(invocation_log[0]["request_payload"]["messages"][0]["content"], "Test")
        self.assertTrue(invocation_log[0]["request_payload"]["stream"])
        self.assertEqual(invocation_log[0]["response_summary"]["status"], "ok")
        self.assertEqual(invocation_log[0]["response_summary"]["content_text"], "Final answer.")
        self.assertEqual(invocation_log[0]["response_summary"]["usage"]["prompt_tokens"], 2)

    def test_run_agent_stream_marks_unknown_pricing_as_unavailable(self):
        responses = [
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(
                        usage=SimpleNamespace(
                            prompt_tokens=4,
                            completion_tokens=6,
                            total_tokens=10,
                        )
                    ),
                ]
            )
        ]
        mock_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=Mock(side_effect=responses)
                )
            )
        )
        custom_settings = {
            "custom_models": [
                {
                    "name": "Claude Sonnet 4.5",
                    "api_model": "anthropic/claude-sonnet-4.5",
                    "supports_tools": True,
                    "supports_vision": True,
                    "supports_structured_outputs": True,
                }
            ]
        }

        with patch("agent.get_app_settings", return_value=custom_settings), patch(
            "agent.resolve_model_target",
            return_value={
                "record": {"provider": "openrouter"},
                "client": mock_client,
                "api_model": "anthropic/claude-sonnet-4.5",
            },
        ):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Test"}],
                    "openrouter:anthropic/claude-sonnet-4.5",
                    1,
                    [],
                )
            )

        usage_event = next(event for event in events if event["type"] == "usage")
        self.assertIsNone(usage_event["cost"])
        self.assertFalse(usage_event["cost_available"])

    def test_run_agent_stream_estimates_openrouter_cache_miss_from_cached_tokens(self):
        responses = [
            iter(
                [
                    self._stream_chunk_openrouter(content="Final answer."),
                    self._stream_chunk_openrouter(
                        usage=SimpleNamespace(
                            prompt_tokens=1000,
                            completion_tokens=50,
                            total_tokens=1050,
                            model_extra={
                                "prompt_tokens_details": {"cached_tokens": 800}
                            },
                        )
                    ),
                ]
            )
        ]
        mock_create = Mock(side_effect=responses)
        fake_target = {
            "record": {"provider": model_registry.OPENROUTER_PROVIDER, "api_model": "anthropic/claude-sonnet-4.5"},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))),
            "api_model": "anthropic/claude-sonnet-4.5",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Test"}],
                    "openrouter:anthropic/claude-sonnet-4.5",
                    1,
                    [],
                )
            )

        usage_event = next(event for event in events if event["type"] == "usage")
        self.assertEqual(usage_event["prompt_cache_hit_tokens"], 800)
        self.assertEqual(usage_event["prompt_cache_miss_tokens"], 200)
        self.assertTrue(usage_event["cache_metrics_estimated"])
        self.assertTrue(usage_event["model_calls"][0]["cache_metrics_estimated"])

    def test_run_agent_stream_keeps_openrouter_cache_write_tokens(self):
        responses = [
            iter(
                [
                    self._stream_chunk_openrouter(content="Final answer."),
                    self._stream_chunk_openrouter(
                        usage=SimpleNamespace(
                            prompt_tokens=1000,
                            completion_tokens=50,
                            total_tokens=1050,
                            model_extra={
                                "prompt_tokens_details": {"cached_tokens": 800, "cache_write_tokens": 120}
                            },
                        )
                    ),
                ]
            )
        ]
        mock_create = Mock(side_effect=responses)
        fake_target = {
            "record": {"provider": model_registry.OPENROUTER_PROVIDER, "api_model": "anthropic/claude-sonnet-4.5"},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))),
            "api_model": "anthropic/claude-sonnet-4.5",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Test"}],
                    "openrouter:anthropic/claude-sonnet-4.5",
                    1,
                    [],
                )
            )

        usage_event = next(event for event in events if event["type"] == "usage")
        self.assertEqual(usage_event["prompt_cache_write_tokens"], 120)
        self.assertEqual(usage_event["model_calls"][0]["prompt_cache_write_tokens"], 120)

    def test_chat_route_persists_only_cache_friendly_context_injection(self):
        conversation_id = self._create_conversation()

        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
            }
        )

        injected_context = (
            "## Current Date and Time\n"
            "- Time: 21:40\n\n"
            "## Tool Execution History\n"
            "- search_web [done]: cached summary\n\n"
            "## Active Tools This Turn\n"
            "- Callable tools: search_web"
        )

        def fake_build_budgeted_prompt_messages(*args, **kwargs):
            return (
                [{"role": "system", "content": "Stable system"}, {"role": "user", "content": "Hello"}],
                [{"role": "system", "content": "Stable system"}, {"role": "user", "content": "Hello"}],
                {"estimated_total_tokens": 2},
                injected_context,
            )

        def fake_run_agent_stream(*args, **kwargs):
            return iter(
                [
                    {"type": "answer_start"},
                    {"type": "answer_delta", "text": "Done"},
                    {"type": "tool_capture", "tool_results": []},
                    {"type": "done"},
                ]
            )

        with patch("routes.chat._build_budgeted_prompt_messages", side_effect=fake_build_budgeted_prompt_messages), patch(
            "routes.chat.run_agent_stream",
            side_effect=fake_run_agent_stream,
        ), patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Hello",
                    "messages": [
                        {"role": "user", "content": "Hello"},
                    ],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        persisted_messages = conversation_response.get_json()["messages"]
        persisted_user_message = next(message for message in persisted_messages if message["role"] == "user")
        persisted_metadata = parse_message_metadata(persisted_user_message.get("metadata"))
        self.assertNotIn("context_injection", persisted_metadata)

    def test_run_agent_stream_estimates_openrouter_cache_hits_when_provider_omits_cache_usage(self):
        responses = [
            iter(
                [
                    self._stream_chunk_openrouter(
                        tool_calls=[
                            {
                                "index": 0,
                                "id": "tool-call-1",
                                "function": {
                                    "name": "search_web",
                                    "arguments": json.dumps({"queries": ["latest update"]}, ensure_ascii=False),
                                },
                            }
                        ]
                    ),
                    self._stream_chunk_openrouter(
                        usage=SimpleNamespace(
                            prompt_tokens=12,
                            completion_tokens=3,
                            total_tokens=15,
                        )
                    ),
                ]
            ),
            iter(
                [
                    self._stream_chunk_openrouter(content="Final answer."),
                    self._stream_chunk_openrouter(
                        usage=SimpleNamespace(
                            prompt_tokens=14,
                            completion_tokens=4,
                            total_tokens=18,
                        )
                    ),
                ]
            ),
        ]
        mock_create = Mock(side_effect=responses)
        fake_target = {
            "record": {"provider": model_registry.OPENROUTER_PROVIDER, "api_model": "anthropic/claude-sonnet-4.5"},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))),
            "api_model": "anthropic/claude-sonnet-4.5",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Test"}],
                    "openrouter:anthropic/claude-sonnet-4.5",
                    3,
                    ["search_web"],
                )
            )

        usage_event = next(event for event in events if event["type"] == "usage")
        self.assertTrue(usage_event["cache_metrics_estimated"])
        self.assertEqual(usage_event["model_calls"][0]["prompt_cache_hit_tokens"], 0)
        self.assertEqual(usage_event["model_calls"][0]["prompt_cache_miss_tokens"], 12)
        self.assertGreater(usage_event["model_calls"][1]["prompt_cache_hit_tokens"], 0)
        self.assertLess(usage_event["model_calls"][1]["prompt_cache_miss_tokens"], 14)

    def test_run_agent_stream_keeps_estimated_breakdown_when_provider_usage_is_missing(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="Need current info. "),
                    self._stream_chunk(
                        tool_calls=[
                            {
                                "index": 0,
                                "id": "tool-call-1",
                                "function": {
                                    "name": "search_web",
                                    "arguments": '{"queries":["test query"]}',
                                },
                            }
                        ]
                    ),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(
                        usage=SimpleNamespace(
                            prompt_tokens=3,
                            completion_tokens=5,
                            total_tokens=8,
                        )
                    ),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 3, ["search_web"]))

        usage_event = next(event for event in events if event["type"] == "usage")
        self.assertEqual(usage_event["prompt_tokens"], 3)
        self.assertEqual(usage_event["completion_tokens"], 5)
        self.assertEqual(usage_event["total_tokens"], 8)
        self.assertTrue(usage_event["provider_usage_partial"])
        self.assertGreater(usage_event["estimated_input_tokens"], usage_event["prompt_tokens"])
        self.assertGreater(usage_event["input_breakdown"]["tool_results"], 0)
        self.assertEqual(len(usage_event["model_calls"]), 2)
        self.assertTrue(usage_event["model_calls"][0]["missing_provider_usage"])
        self.assertEqual(usage_event["model_calls"][0]["prompt_tokens"], None)
        self.assertGreater(usage_event["model_calls"][0]["estimated_input_tokens"], 0)
        self.assertEqual(usage_event["model_calls"][1]["prompt_tokens"], 3)

    def test_run_agent_stream_passes_openrouter_extra_body_preferences(self):
        responses = [
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(
                        usage=SimpleNamespace(
                            prompt_tokens=1,
                            completion_tokens=1,
                            total_tokens=2,
                        )
                    ),
                ]
            )
        ]
        mock_create = Mock(side_effect=responses)
        mock_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=mock_create
                )
            )
        )

        with patch("agent.get_app_settings", return_value={}), patch(
            "agent.resolve_model_target",
            return_value={
                "record": {"provider": "openrouter"},
                "client": mock_client,
                "api_model": "anthropic/claude-sonnet-4.5",
                "extra_body": {
                    "provider": {"only": ["deepinfra/turbo"], "allow_fallbacks": False},
                    "reasoning": {"effort": "high"},
                },
            },
        ):
            list(
                run_agent_stream(
                    [{"role": "user", "content": "Test"}],
                    "openrouter:anthropic/claude-sonnet-4.5",
                    1,
                    [],
                )
            )

        self.assertEqual(
            mock_create.call_args.kwargs["extra_body"],
            {
                "provider": {"only": ["deepinfra/turbo"], "allow_fallbacks": False},
                "reasoning": {"effort": "high"},
            },
        )

    def test_run_agent_stream_adds_gemini_cache_breakpoint_to_request_messages(self):
        responses = [
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(
                        usage=SimpleNamespace(
                            prompt_tokens=1,
                            completion_tokens=1,
                            total_tokens=2,
                        )
                    ),
                ]
            )
        ]
        mock_create = Mock(side_effect=responses)
        mock_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=mock_create
                )
            )
        )

        with patch("agent.get_app_settings", return_value={}), patch(
            "agent.resolve_model_target",
            return_value={
                "record": {
                    "provider": model_registry.OPENROUTER_PROVIDER,
                    "api_model": "google/gemini-2.5-pro",
                },
                "client": mock_client,
                "api_model": "google/gemini-2.5-pro",
                "extra_body": {"provider": {"sort": "throughput"}},
            },
        ):
            list(
                run_agent_stream(
                    [
                        {"role": "system", "content": "Reference context. " * 1000},
                        {"role": "user", "content": "Test"},
                    ],
                    "openrouter:google/gemini-2.5-pro",
                    1,
                    [],
                )
            )

        first_message = mock_create.call_args.kwargs["messages"][0]
        self.assertEqual(first_message["role"], "system")
        self.assertIsInstance(first_message["content"], list)
        self.assertEqual(first_message["content"][0]["cache_control"], {"type": "ephemeral"})

    def test_run_agent_stream_compacts_canvas_tool_call_history(self):
        large_content = "\n".join(f"value_{index} = {index}" for index in range(400))
        original_arguments = {
            "title": "draft.py",
            "content": large_content,
            "format": "code",
            "language": "python",
        }
        responses = [
            iter(
                [
                    self._stream_chunk(
                        tool_calls=[
                            {
                                "index": 0,
                                "id": "tool-call-1",
                                "function": {
                                    "name": "create_canvas_document",
                                    "arguments": json.dumps(original_arguments, ensure_ascii=False),
                                },
                            }
                        ]
                    ),
                    self._stream_chunk(
                        usage=SimpleNamespace(
                            prompt_tokens=5,
                            prompt_cache_hit_tokens=0,
                            prompt_cache_miss_tokens=5,
                            completion_tokens=4,
                            total_tokens=9,
                        )
                    ),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Canvas hazır."),
                    self._stream_chunk(
                        usage=SimpleNamespace(
                            prompt_tokens=4,
                            prompt_cache_hit_tokens=0,
                            prompt_cache_miss_tokens=4,
                            completion_tokens=3,
                            total_tokens=7,
                        )
                    ),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create:
            list(run_agent_stream([{"role": "user", "content": "Bir canvas taslağı oluştur."}], "deepseek-chat", 2, ["create_canvas_document"]))

        second_call_messages = mocked_create.call_args_list[1].kwargs["messages"]
        assistant_tool_call = second_call_messages[1]["tool_calls"][0]
        self.assertEqual(assistant_tool_call["function"]["name"], "create_canvas_document")
        compacted_arguments_text = assistant_tool_call["function"]["arguments"]
        compacted_arguments = json.loads(compacted_arguments_text)
        self.assertIn("[TRIMMED canvas content:", compacted_arguments["content"])
        self.assertLess(
            len(compacted_arguments_text),
            len(json.dumps(original_arguments, ensure_ascii=False)),
        )

    def test_execute_create_canvas_document_returns_lightweight_document_snapshot(self):
        runtime_state = {"canvas": create_canvas_runtime_state([])}
        result, summary = _execute_tool(
            "create_canvas_document",
            {
                "title": "draft.py",
                "content": "\n".join(f"print({index})" for index in range(400)),
                "format": "code",
                "language": "python",
            },
            runtime_state=runtime_state,
        )

        self.assertEqual(summary, "Canvas created: draft.py")
        self.assertEqual(result["document"]["title"], "draft.py")
        self.assertEqual(result["document"]["format"], "code")
        self.assertNotIn("content", result["document"])
        self.assertTrue(result["content_truncated"])

    def test_build_api_messages_preserves_tool_history_fields(self):
        normalized = normalize_chat_messages(
            [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "I am searching.",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "search_web",
                                "arguments": '{"queries":["hello"]}',
                            },
                        }
                    ],
                },
                {"role": "tool", "content": "{}", "tool_call_id": "call-1"},
            ]
        )

        api_messages = build_api_messages(normalized)

        self.assertEqual(api_messages[1]["tool_calls"][0]["function"]["name"], "search_web")
        self.assertEqual(api_messages[2]["tool_call_id"], "call-1")

    def test_build_api_messages_adds_tool_name_when_tool_call_id_is_missing(self):
        normalized = normalize_chat_messages(
            [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "I am searching.",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "search_web",
                                "arguments": '{"queries":["hello"]}',
                            },
                        }
                    ],
                },
                {"role": "tool", "content": "{}"},
            ]
        )

        api_messages = build_api_messages(normalized)

        self.assertEqual(
            api_messages,
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "I am searching."},
            ],
        )

    def test_build_api_messages_drops_outbound_message_ids_for_provider(self):
        normalized = normalize_chat_messages(
            [
                {"role": "user", "content": "Hello", "id": 318},
                {
                    "role": "assistant",
                    "content": "I am searching.",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "search_web",
                                "arguments": '{"queries":["hello"]}',
                            },
                        }
                    ],
                    "id": 319,
                },
                {"role": "tool", "content": "{}", "tool_call_id": "call-1", "id": 320},
            ]
        )

        api_messages = build_api_messages(normalized)

        self.assertNotIn("id", api_messages[0])
        self.assertNotIn("id", api_messages[1])
        self.assertNotIn("id", api_messages[2])
        self.assertEqual(api_messages[2]["tool_call_id"], "call-1")

    def test_build_api_messages_adds_ids_for_tool_protocol_messages(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "I am searching.",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "search_web",
                            "arguments": '{"queries":["hello"]}',
                        },
                    }
                ],
            },
            {"role": "tool", "content": "{}", "tool_call_id": "call-1"},
        ]

        api_messages = build_api_messages(messages)

        self.assertNotIn("id", api_messages[1])
        self.assertNotIn("id", api_messages[2])
        self.assertEqual(api_messages[2]["tool_call_id"], "call-1")

    def test_build_api_messages_maps_summary_role_to_assistant_context(self):
        normalized = normalize_chat_messages(
            [
                {"role": "summary", "content": "The user asked for a short answer."},
            ]
        )

        api_messages = build_api_messages(normalized)

        self.assertEqual(api_messages[0]["role"], "assistant")
        self.assertTrue(api_messages[0]["content"].startswith("Conversation summary:"))
        self.assertNotIn("generated from deleted messages", api_messages[0]["content"])
        self.assertIn("The user asked for a short answer.", api_messages[0]["content"])

    def test_build_api_messages_maps_hierarchical_summary_to_clean_assistant_context(self):
        normalized = normalize_chat_messages(
            [
                {
                    "role": "summary",
                    "content": f"{SUMMARY_LABEL}\n\nMerged summary details.",
                    "metadata": parse_message_metadata(
                        serialize_message_metadata(
                            {"is_summary": True, "summary_source": "summary_history", "summary_level": 2}
                        )
                    ),
                },
            ]
        )

        api_messages = build_api_messages(normalized)

        self.assertEqual(api_messages[0]["role"], "assistant")
        self.assertTrue(api_messages[0]["content"].startswith("Conversation summary of earlier summaries:"))
        self.assertIn("Merged summary details.", api_messages[0]["content"])

    def test_build_api_messages_injects_persisted_context_before_user_message(self):
        normalized = normalize_chat_messages(
            [
                {
                    "role": "user",
                    "content": "Hello",
                    "metadata": parse_message_metadata(
                        serialize_message_metadata(
                            {
                                "context_injection": "## Current Date and Time\n- Time: 21:40",
                            }
                        )
                    ),
                },
            ]
        )

        api_messages = build_api_messages(normalized)

        self.assertEqual(api_messages[0]["role"], "system")
        self.assertNotIn("id", api_messages[0])
        self.assertIn("## Current Date and Time", api_messages[0]["content"])
        self.assertEqual(api_messages[1]["role"], "user")
        self.assertNotIn("id", api_messages[1])
        self.assertEqual(api_messages[1]["content"], "Hello")

    def test_build_api_messages_keeps_only_latest_runtime_context_injection(self):
        normalized = normalize_chat_messages(
            [
                {
                    "role": "user",
                    "content": "First",
                    "metadata": parse_message_metadata(
                        serialize_message_metadata(
                            {
                                "context_injection": "## Current Date and Time\n- Time: 21:35",
                            }
                        )
                    ),
                },
                {
                    "role": "assistant",
                    "content": "Reply",
                },
                {
                    "role": "user",
                    "content": "Second",
                    "metadata": parse_message_metadata(
                        serialize_message_metadata(
                            {
                                "context_injection": "## Current Date and Time\n- Time: 21:40",
                            }
                        )
                    ),
                },
            ]
        )

        api_messages = build_api_messages(normalized)

        system_messages = [message for message in api_messages if message["role"] == "system"]
        self.assertEqual(len(system_messages), 1)
        self.assertEqual(api_messages[0]["role"], "user")
        self.assertNotIn("id", api_messages[0])
        self.assertEqual(api_messages[1]["role"], "assistant")
        self.assertNotIn("id", api_messages[1])
        self.assertEqual(api_messages[2]["role"], "system")
        self.assertNotIn("id", api_messages[2])
        self.assertIn("21:40", api_messages[2]["content"])
        self.assertEqual(api_messages[3]["role"], "user")
        self.assertNotIn("id", api_messages[3])

    def test_build_api_messages_strips_historical_runtime_context_injections(self):
        historical_context = (
            "## Clarification Response\n"
            "Earlier clarification guidance\n\n"
            "## Tool Memory\n"
            "Earlier search result\n\n"
            "## Knowledge Base\n"
            "Earlier KB excerpt\n\n"
            "## Current Date and Time\n"
            "- Time: 21:35\n\n"
            "## Tool Execution History\n"
            "- search_web [done]: old query\n\n"
            "## Active Tools This Turn\n"
            "- Callable tools: search_web\n\n"
            "## Active Canvas Document\n"
            "```text\n"
            "1: old line\n"
            "```\n\n"
            "## Pinned Canvas Viewports\n"
            "- src/app.py lines 20-24\n"
        )
        latest_context = (
            "## Current Date and Time\n"
            "- Time: 21:40\n\n"
            "## Active Canvas Document\n"
            "```text\n"
            "1: latest line\n"
            "```"
        )
        normalized = normalize_chat_messages(
            [
                {
                    "role": "user",
                    "content": "First",
                    "metadata": parse_message_metadata(
                        serialize_message_metadata({"context_injection": historical_context})
                    ),
                },
                {"role": "assistant", "content": "Reply"},
                {
                    "role": "user",
                    "content": "Second",
                    "metadata": parse_message_metadata(
                        serialize_message_metadata({"context_injection": latest_context})
                    ),
                },
            ]
        )

        api_messages = build_api_messages(normalized)

        system_messages = [message for message in api_messages if message["role"] == "system"]
        self.assertEqual(len(system_messages), 1)
        self.assertIn("21:40", system_messages[0]["content"])
        self.assertIn("## Active Canvas Document", system_messages[0]["content"])
        self.assertNotIn("Earlier clarification guidance", system_messages[0]["content"])
        self.assertNotIn("Earlier search result", system_messages[0]["content"])
        self.assertNotIn("Earlier KB excerpt", system_messages[0]["content"])

    def test_build_api_messages_strips_historical_dynamic_runtime_state_injections(self):
        historical_context = (
            "## User Profile\n"
            "The user prefers concise answers.\n\n"
            "## Scratchpad (AI Persistent Memory)\n"
            "### General Notes\n"
            "Persistent note\n\n"
            "## Conversation Memory\n"
            "- #7 [task_context] 10:23 - Goal: Keep stable rules cached.\n\n"
            "## Conversation Memory Priority\n"
            "- Save chat-specific facts before more context is lost.\n"
        )
        latest_context = "## Current Date and Time\n- Time: 21:40"
        normalized = normalize_chat_messages(
            [
                {
                    "role": "user",
                    "content": "First",
                    "metadata": parse_message_metadata(
                        serialize_message_metadata({"context_injection": historical_context})
                    ),
                },
                {"role": "assistant", "content": "Reply"},
                {
                    "role": "user",
                    "content": "Second",
                    "metadata": parse_message_metadata(
                        serialize_message_metadata({"context_injection": latest_context})
                    ),
                },
            ]
        )

        api_messages = build_api_messages(normalized)

        system_messages = [message for message in api_messages if message["role"] == "system"]
        self.assertEqual(len(system_messages), 1)
        self.assertIn("21:40", system_messages[0]["content"])
        self.assertNotIn("The user prefers concise answers.", system_messages[0]["content"])
        self.assertNotIn("Persistent note", system_messages[0]["content"])
        self.assertNotIn("Goal: Keep stable rules cached.", system_messages[0]["content"])
        self.assertNotIn("## Conversation Memory Priority", system_messages[0]["content"])

    def test_build_api_messages_strips_answered_clarification_tool_blocks(self):
        normalized = normalize_chat_messages(
            [
                {
                    "id": 10,
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "ask_clarifying_question",
                                "arguments": '{"questions":[{"id":"budget","label":"Budget?","input_type":"text"}]}'
                            },
                        }
                    ],
                },
                {
                    "id": 11,
                    "role": "tool",
                    "content": '{"status":"needs_user_input","clarification":{"questions":[{"id":"budget","label":"Budget?","input_type":"text"}]}}',
                    "tool_call_id": "call-1",
                },
                {
                    "id": 12,
                    "role": "assistant",
                    "content": "",
                    "metadata": {
                        "pending_clarification": {
                            "questions": [{"id": "budget", "label": "Budget?", "input_type": "text"}]
                        }
                    },
                },
                {
                    "id": 13,
                    "role": "user",
                    "content": "Q: Budget?\nA: 200-300 TL",
                    "metadata": {
                        "clarification_response": {
                            "assistant_message_id": 12,
                            "answers": {"budget": {"display": "200-300 TL"}},
                        }
                    },
                },
            ]
        )

        api_messages = build_api_messages(normalized)

        self.assertEqual(
            api_messages,
            [
                {
                    "role": "assistant",
                    "content": "Before I answer, I need a few details.\nPlease answer this question:\n1. Budget?",
                },
                {
                    "role": "user",
                    "content": "- Budget? \u2192 200-300 TL",
                },
            ],
        )

    def test_build_api_messages_strips_saved_sub_agent_tool_blocks(self):
        normalized = normalize_chat_messages(
            [
                {"id": 1, "role": "user", "content": "Research the setup steps."},
                {
                    "id": 2,
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-sub-agent-1",
                            "type": "function",
                            "function": {
                                "name": "sub_agent",
                                "arguments": '{"task":"Inspect README setup"}',
                            },
                        }
                    ],
                },
                {
                    "id": 3,
                    "role": "tool",
                    "content": '{"summary":"Install requirements.txt first."}',
                    "tool_call_id": "call-sub-agent-1",
                },
                {
                    "id": 4,
                    "role": "assistant",
                    "content": "I found the setup steps and saved them to Canvas.",
                    "metadata": {
                        "sub_agent_traces": [
                            {
                                "task": "Inspect README setup",
                                "status": "ok",
                                "summary": "Install requirements.txt first.",
                                "canvas_saved": True,
                                "canvas_document_id": "canvas-1",
                                "canvas_document_title": "Research - README setup",
                            }
                        ]
                    },
                },
                {"id": 5, "role": "user", "content": "What should I install first?"},
            ]
        )

        api_messages = build_api_messages(normalized)

        self.assertEqual(
            api_messages,
            [
                {"role": "user", "content": "Research the setup steps."},
                {"role": "assistant", "content": "I found the setup steps and saved them to Canvas."},
                {"role": "user", "content": "What should I install first?"},
            ],
        )

    def test_build_api_messages_strips_old_clarification_response_user_turns(self):
        normalized = normalize_chat_messages(
            [
                {
                    "id": 10,
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "ask_clarifying_question",
                                "arguments": '{"questions":[{"id":"budget","label":"Budget?","input_type":"text"}]}'
                            },
                        }
                    ],
                },
                {
                    "id": 11,
                    "role": "tool",
                    "content": '{"status":"needs_user_input"}',
                    "tool_call_id": "call-1",
                },
                {
                    "id": 12,
                    "role": "assistant",
                    "content": "",
                    "metadata": {
                        "pending_clarification": {
                            "questions": [{"id": "budget", "label": "Budget?", "input_type": "text"}]
                        }
                    },
                },
                {
                    "id": 13,
                    "role": "user",
                    "content": "Q: Budget?\nA: 200-300 TL",
                    "metadata": {
                        "clarification_response": {
                            "assistant_message_id": 12,
                            "answers": {"budget": {"display": "200-300 TL"}},
                        }
                    },
                },
                {
                    "id": 20,
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-2",
                            "type": "function",
                            "function": {
                                "name": "ask_clarifying_question",
                                "arguments": '{"questions":[{"id":"price","label":"Price?","input_type":"text"}]}'
                            },
                        }
                    ],
                },
                {
                    "id": 21,
                    "role": "tool",
                    "content": '{"status":"needs_user_input"}',
                    "tool_call_id": "call-2",
                },
                {
                    "id": 22,
                    "role": "assistant",
                    "content": "",
                    "metadata": {
                        "pending_clarification": {
                            "questions": [{"id": "price", "label": "Price?", "input_type": "text"}]
                        }
                    },
                },
                {
                    "id": 23,
                    "role": "user",
                    "content": "Q: Price?\nA: 199 TL",
                    "metadata": {
                        "clarification_response": {
                            "assistant_message_id": 22,
                            "answers": {"price": {"display": "199 TL"}},
                        }
                    },
                },
            ]
        )

        api_messages = build_api_messages(normalized)

        self.assertEqual(
            api_messages,
            [
                {
                    "role": "assistant",
                    "content": "Before I answer, I need a few details.\nPlease answer this question:\n1. Budget?",
                },
                {
                    "role": "user",
                    "content": "- Budget? \u2192 200-300 TL",
                },
                {
                    "role": "assistant",
                    "content": "Before I answer, I need a few details.\nPlease answer this question:\n1. Price?",
                },
                {
                    "role": "user",
                    "content": "- Price? \u2192 199 TL",
                },
            ],
        )

    def test_build_tool_trace_context_ignores_clarification_entries(self):
        canonical_messages = normalize_chat_messages(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "metadata": {
                        "tool_trace": [
                            {"tool_name": "ask_clarifying_question", "state": "done", "summary": "asked 3 questions"},
                            {"tool_name": "search_web", "state": "done", "summary": "found pricing page"},
                        ]
                    },
                }
            ]
        )

        context = _build_tool_trace_context(canonical_messages)

        self.assertIn("search_web", context)
        # clarification is replaced by a single controlled sentinel row, not the original trace data
        self.assertIn("ask_clarifying_question", context)
        self.assertIn("answered", context)
        self.assertNotIn("asked 3 questions", context)
        # table format verification
        self.assertIn("| # | Time | Tool | State | Detail |", context)

    def test_build_api_messages_uses_null_content_for_tool_only_assistant_turns(self):
        api_messages = build_api_messages(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "search_web", "arguments": "{}"},
                        }
                    ],
                }
            ]
        )

        self.assertEqual(api_messages, [])

    def test_runtime_system_message_avoids_duplicate_active_canvas_identity_when_workspace_summary_is_present(self):
        message = build_runtime_system_message(
            active_tool_names=["replace_canvas_lines"],
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
                    "content": "print('a')\nprint('b')\n",
                },
                {
                    "id": "canvas-2",
                    "title": "utils.py",
                    "path": "src/utils.py",
                    "role": "source",
                    "project_id": "demo-app",
                    "workspace_id": "demo-workspace",
                    "format": "code",
                    "language": "python",
                    "content": "pass\n",
                },
            ],
            canvas_active_document_id="canvas-1",
        )

        content = message["content"]
        self.assertIn("- Active file: src/app.py", content)
        self.assertEqual(content.count("- Path: src/app.py"), 0)

    def test_build_runtime_system_message_skips_canvas_editing_guidance_for_read_only_canvas_tools(self):
        message = build_runtime_system_message(
            active_tool_names=["search_canvas_document", "expand_canvas_document", "set_canvas_viewport"],
            canvas_documents=[
                {
                    "id": "doc-1",
                    "title": "notes.txt",
                    "content": "alpha\nbeta\n",
                    "format": "markdown",
                }
            ],
            include_volatile_context=False,
        )

        self.assertNotIn("## Canvas Editing Guidance", message["content"])

    def test_chat_uses_compact_clarification_answers_for_rag_query(self):
        conversation_id = self._create_conversation()
        assistant_message_id = self._insert_pending_clarification_assistant(
            conversation_id,
            questions=[
                {"id": "group_size", "label": "Kaç kişisiniz?", "input_type": "text", "required": True},
                {"id": "age_range", "label": "Yaş grubunuz nedir?", "input_type": "text", "required": True},
                {"id": "city", "label": "Nerede yaşıyorsunuz?", "input_type": "text", "required": True},
            ],
        )
        save_app_settings(
            {
                "user_preferences": "",
                "scratchpad": "",
                "max_steps": "2",
                "active_tools": "[]",
                "rag_auto_inject": "true",
                "rag_sensitivity": "strict",
                "rag_context_size": "large",
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        message_text = "Q: Kaç kişisiniz?\nA: 2 kişi\nQ: Yaş grubunuz nedir?\nA: 15-18\nQ: Nerede yaşıyorsunuz?\nA: İstanbul"
        with patch("routes.chat.build_rag_auto_context", return_value=None) as mocked_rag, patch(
            "routes.chat.run_agent_stream", return_value=fake_events
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": message_text,
                    "messages": [
                        {
                            "role": "user",
                            "content": message_text,
                            "metadata": {
                                "clarification_response": {
                                    "assistant_message_id": assistant_message_id,
                                    "answers": {
                                        "group_size": {"display": "2 kişi"},
                                        "age_range": {"display": "15-18"},
                                        "city": {"display": "İstanbul"},
                                    },
                                }
                            },
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mocked_rag.call_args.args[0], "2 kişi 15-18 İstanbul")

    def test_chat_does_not_compact_plain_messages_that_only_look_like_qna(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "scratchpad": "",
                "max_steps": "2",
                "active_tools": "[]",
                "rag_auto_inject": "true",
                "rag_sensitivity": "strict",
                "rag_context_size": "large",
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Done."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        message_text = "Q: Bu bir başlık mı?\nA: Evet\nEk açıklama: A: burada normal bir metin"
        with patch("routes.chat.build_rag_auto_context", return_value=None) as mocked_rag, patch(
            "routes.chat.run_agent_stream", return_value=fake_events
        ):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": message_text,
                    "messages": [{"role": "user", "content": message_text}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mocked_rag.call_args.args[0], message_text)

    def test_patch_user_message_clears_stale_context_injection_but_keeps_attachments(self):
        conversation_id = self._create_conversation()

        with get_db() as conn:
            message_id = insert_message(
                conn,
                conversation_id,
                "user",
                "Old prompt",
                metadata=serialize_message_metadata(
                    {
                        "context_injection": "## Knowledge Base\nStale branch excerpt",
                        "attachments": [
                            {
                                "kind": "document",
                                "file_id": "doc-1",
                                "file_name": "notes.txt",
                                "file_mime_type": "text/plain",
                                "file_context_block": "Original attachment context",
                            }
                        ],
                    }
                ),
            )

        with patch("routes.conversations.sync_conversations_to_rag_safe"):
            response = self.client.patch(
                f"/api/messages/{message_id}",
                json={
                    "conversation_id": conversation_id,
                    "content": "Edited prompt",
                },
            )

        self.assertEqual(response.status_code, 200)
        response_metadata = response.get_json()["message"]["metadata"]
        self.assertNotIn("context_injection", response_metadata)
        self.assertEqual(response_metadata["attachments"][0]["file_id"], "doc-1")
        self.assertEqual(response_metadata["attachments"][0]["file_name"], "notes.txt")

        with get_db() as conn:
            row = conn.execute("SELECT metadata FROM messages WHERE id = ?", (message_id,)).fetchone()
        persisted_metadata = parse_message_metadata(row["metadata"])
        self.assertNotIn("context_injection", persisted_metadata)
        self.assertEqual(persisted_metadata["attachments"][0]["file_id"], "doc-1")

    def test_run_agent_stream_retries_until_content_final_answer_arrives(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="Thinking step by step."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create:
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-reasoner", 2, []))

        self.assertIn({"type": "reasoning_delta", "text": "Thinking step by step."}, events)
        self.assertIn(
            {
                "type": "tool_error",
                "step": 1,
                "tool": "agent",
                "error": "The model returned no final answer content. Retrying and waiting for a final answer.",
            },
            events,
        )
        self.assertIn({"type": "answer_delta", "text": "Final answer."}, events)
        leaked_reasoning = [event for event in events if event["type"] == "answer_delta" and "Thinking" in event["text"]]
        self.assertEqual(leaked_reasoning, [])

        usage_event = next(event for event in events if event["type"] == "usage")
        self.assertEqual(usage_event["model_call_count"], 2)
        self.assertTrue(usage_event["model_calls"][1]["is_retry"])
        self.assertEqual(usage_event["model_calls"][1]["retry_reason"], "missing_final_answer")

        second_call_messages = mocked_create.call_args_list[1].kwargs["messages"]
        retry_content = second_call_messages[-1]["content"]
        self.assertIn("MISSING FINAL ANSWER", retry_content)
        self.assertIn("assistant content only", retry_content)

    def test_run_agent_stream_does_not_force_canvas_retry_when_answer_mentions_canvas_context(self):
        responses = [
            iter(
                [
                    self._stream_chunk(content="Tamam, şimdilik Canvas'a dokunmuyorum. Shoulder press için 12.5-15 kg ile başla."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        prior_turn_messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc1",
                        "type": "function",
                        "function": {
                            "name": "batch_canvas_edits",
                            "arguments": '{"document_id":"canvas-1","operations":[]}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tc1", "content": '{"status":"ok"}'},
            {"role": "user", "content": "Şimdilik Canvas'ı elleme, sadece ağırlık önerisi ver."},
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create:
            events = list(
                run_agent_stream(
                    prior_turn_messages,
                    "deepseek-chat",
                    3,
                    ["rewrite_canvas_document"],
                )
            )

        answer_deltas = [event["text"] for event in events if event["type"] == "answer_delta"]
        self.assertEqual(answer_deltas, ["Tamam, şimdilik Canvas'a dokunmuyorum. Shoulder press için 12.5-15 kg ile başla."])
        self.assertFalse(any(event["type"] == "tool_result" for event in events))

        usage_event = next(event for event in events if event["type"] == "usage")
        self.assertEqual(usage_event["model_call_count"], 1)
        self.assertFalse(any(call["is_retry"] for call in usage_event["model_calls"]))
        self.assertEqual(mocked_create.call_count, 1)

    def test_run_agent_stream_accepts_python_literal_tool_call_arguments(self):
        responses = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            reasoning_content="",
                            content="",
                            tool_calls=[
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "create_canvas_document",
                                        "arguments": "{'title': 'Robot Plan', 'content': '# Notes'}",
                                    },
                                }
                            ],
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            ),
            iter(
                [
                    self._stream_chunk(content="Tamam."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses):
            events = list(run_agent_stream([{"role": "user", "content": "Canvas oluştur"}], "deepseek-chat", 2, ["create_canvas_document"]))

        self.assertIn({"type": "answer_delta", "text": "Tamam."}, events)
        parser_errors = [event for event in events if event["type"] == "tool_error" and event["tool"] == "parser"]
        self.assertEqual(parser_errors, [])
        tool_capture_event = next(event for event in events if event["type"] == "tool_capture")
        self.assertEqual([doc["title"] for doc in tool_capture_event["canvas_documents"]], ["Robot Plan"])
        self.assertEqual(tool_capture_event["canvas_documents"][0]["content"], "# Notes")

    def test_run_agent_stream_extracts_dsml_tool_calls_from_content(self):
        dsml_content = (
            "<｜DSML｜function_calls>\n"
            "<｜DSML｜invoke name=\"create_canvas_document\">\n"
            "<｜DSML｜parameter name=\"title\" string=\"true\">Arduino Kodu - RobotBeyni.ino</｜DSML｜parameter>\n"
            "<｜DSML｜parameter name=\"content\" string=\"true\">// test\nint led = 13;</｜DSML｜parameter>\n"
            "</｜DSML｜invoke>\n"
            "</｜DSML｜function_calls>"
        )
        responses = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            reasoning_content="",
                            content=dsml_content,
                            tool_calls=[],
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            ),
            iter(
                [
                    self._stream_chunk(content="Bitti."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses):
            events = list(run_agent_stream([{"role": "user", "content": "Canvas oluştur"}], "deepseek-reasoner", 2, ["create_canvas_document"]))

        self.assertIn({"type": "answer_delta", "text": "Bitti."}, events)
        leaked_dsml = [event for event in events if event["type"] == "answer_delta" and "function_calls" in event["text"]]
        self.assertEqual(leaked_dsml, [])
        parser_errors = [event for event in events if event["type"] == "tool_error" and event["tool"] == "parser"]
        self.assertEqual(parser_errors, [])
        tool_capture_event = next(event for event in events if event["type"] == "tool_capture")
        self.assertEqual([doc["title"] for doc in tool_capture_event["canvas_documents"]], ["Arduino Kodu - RobotBeyni.ino"])
        self.assertEqual(tool_capture_event["canvas_documents"][0]["content"], "// test\nint led = 13;")

    def test_run_agent_stream_prefers_content_dsml_when_native_tool_args_are_invalid(self):
        dsml_content = (
            "<｜DSML｜function_calls>\n"
            "<｜DSML｜invoke name=\"create_canvas_document\">\n"
            "<｜DSML｜parameter name=\"title\" string=\"true\">Robot Plan</｜DSML｜parameter>\n"
            "<｜DSML｜parameter name=\"content\" string=\"true\"># Notes</｜DSML｜parameter>\n"
            "</｜DSML｜invoke>\n"
            "</｜DSML｜function_calls>"
        )
        responses = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            reasoning_content="",
                            content=dsml_content,
                            tool_calls=[
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "replace_canvas_lines",
                                        "arguments": "not valid json at all",
                                    },
                                }
                            ],
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            ),
            iter(
                [
                    self._stream_chunk(content="Bitti."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Canvas oluştur"}],
                    "deepseek-reasoner",
                    2,
                    ["create_canvas_document", "replace_canvas_lines"],
                )
            )

        self.assertIn({"type": "answer_delta", "text": "Bitti."}, events)
        parser_errors = [event for event in events if event["type"] == "tool_error" and event["tool"] == "parser"]
        self.assertEqual(parser_errors, [])
        tool_capture_event = next(event for event in events if event["type"] == "tool_capture")
        self.assertEqual([doc["title"] for doc in tool_capture_event["canvas_documents"]], ["Robot Plan"])
        self.assertEqual(tool_capture_event["canvas_documents"][0]["content"], "# Notes")

    def test_context_overflow_error_detection(self):
        self.assertTrue(_is_context_overflow_error("context_length_exceeded: requested 200000 tokens"))
        self.assertTrue(_is_context_overflow_error("This model's maximum context length is 128000 tokens."))
        self.assertFalse(_is_context_overflow_error("rate_limit_exceeded"))
        self.assertFalse(_is_context_overflow_error("429 Too Many Requests"))

    def test_usage_ui_copy_explains_multi_call_prompt_totals(self):
        template_path = Path(__file__).resolve().parent.parent / "templates" / "index.html"
        template_text = template_path.read_text(encoding="utf-8")

        self.assertIn("Peak prompt in one model call", template_text)
        self.assertIn("can exceed a model's single-call context window", template_text)

        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn("prompt (all calls)", script_text)
        self.assertIn("peak call prompt", script_text)

    def test_iter_agent_exchange_blocks_keeps_assistant_and_tool_together(self):
        blocks = _iter_agent_exchange_blocks(
            [
                {"role": "system", "content": "sys"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "search_web", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "tool result"},
                {"role": "user", "content": "next"},
            ]
        )

        self.assertEqual(blocks[1]["type"], "exchange")
        self.assertEqual([message["role"] for message in blocks[1]["messages"]], ["assistant", "tool"])

    def test_try_compact_messages_preserves_recent_exchanges(self):
        messages = [
            {"role": "system", "content": "sys"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "search_web", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "A" * 1200},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-2", "type": "function", "function": {"name": "fetch_url", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "call-2", "content": "B" * 1200},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-3", "type": "function", "function": {"name": "search_news_ddgs", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "call-3", "content": "C" * 1200},
        ]

        compacted = _try_compact_messages(messages, budget=200, keep_recent=2)

        self.assertIsNotNone(compacted)
        self.assertEqual(compacted[0]["role"], "system")
        self.assertEqual(compacted[1]["role"], "user")
        self.assertIn("compacted tool step 1", compacted[1]["content"])
        self.assertEqual(compacted[-2]["role"], "assistant")
        self.assertEqual(compacted[-1]["role"], "tool")

    def test_try_compact_messages_builds_semantic_summary(self):
        messages = [
            {"role": "system", "content": "sys"},
            {
                "role": "assistant",
                "content": "I should search for current release notes before answering.",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search_web", "arguments": '{"queries": ["python release notes"]}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": "Web results\n\n1. Python 3.13 notes\nURL: https://example.com\nSnippet: Latest changes overview",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-2", "type": "function", "function": {"name": "fetch_url", "arguments": '{"url": "https://example.com"}'}}],
            },
            {"role": "tool", "tool_call_id": "call-2", "content": "Title: Python 3.13\n\nKey highlights and changes."},
        ]

        compacted = _try_compact_messages(messages, budget=120, keep_recent=1)

        self.assertIsNotNone(compacted)
        compacted_summary = compacted[1]["content"]
        self.assertIn("Assistant intent:", compacted_summary)
        self.assertIn("search_web: python release notes", compacted_summary)
        self.assertIn("Outcomes:", compacted_summary)
        self.assertIn("Web results", compacted_summary)

    def test_try_compact_messages_includes_recovery_hints(self):
        messages = [
            {"role": "system", "content": "sys"},
            {
                "role": "assistant",
                "content": "I should fetch the page before answering.",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "fetch_url", "arguments": '{"url": "https://example.com/docs"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": "Title: Docs\n\nLarge response body",
            },
        ]

        compacted = _try_compact_messages(messages, budget=80, keep_recent=0)

        self.assertIsNotNone(compacted)
        self.assertIn("Recovery:", compacted[1]["content"])
        self.assertIn("grep_fetched_content", compacted[1]["content"])

    def test_prepare_tool_result_for_transcript_clips_large_non_fetch_payloads(self):
        result = _prepare_tool_result_for_transcript("search_web", {"items": ["x" * 30000]})
        rendered = _build_compact_tool_message_content("search_web", {}, {"ignored": True}, "summary", transcript_result=result)

        self.assertIsInstance(result, str)
        self.assertIn("[CLIPPED: original", result)
        self.assertIn("[CLIPPED: original", rendered)

    def test_build_compact_tool_message_content_clips_large_structured_transcript_payloads(self):
        transcript_result = {"items": ["x" * 30000]}
        raw_serialized = json.dumps(transcript_result, ensure_ascii=False)

        rendered = _build_compact_tool_message_content(
            "search_web",
            {},
            {"ignored": True},
            "summary",
            transcript_result=transcript_result,
        )

        self.assertLess(len(rendered), len(raw_serialized))
        self.assertTrue(rendered.startswith('{"items":'))

    def test_prepare_tool_result_for_transcript_compacts_canvas_mutation_payloads(self):
        result = _prepare_tool_result_for_transcript(
            "rewrite_canvas_document",
            {
                "status": "ok",
                "action": "rewritten",
                "document": {
                    "id": "canvas-1",
                    "title": "main.py",
                    "format": "code",
                    "language": "python",
                    "line_count": 40,
                },
                "document_id": "canvas-1",
                "title": "main.py",
                "format": "code",
                "language": "python",
                "line_count": 40,
                "expected_start_line": 18,
                "expected_lines": ["def main():", "    return 1"],
                "content": "print('x')\n" * 500,
                "content_truncated": True,
            },
        )

        self.assertIsInstance(result, dict)
        self.assertNotIn("content", result)
        self.assertIn("content_preview", result)
        self.assertLess(len(result["content_preview"]), 450)
        self.assertTrue(result["content_truncated"])
        self.assertEqual(result["document_id"], "canvas-1")
        self.assertEqual(result["expected_start_line"], 18)
        self.assertEqual(result["expected_lines"], ["def main():", "    return 1"])

    def test_prepare_tool_result_for_transcript_preserves_fetch_url_to_canvas_document_list(self):
        result = _prepare_tool_result_for_transcript(
            "fetch_url_to_canvas",
            {
                "status": "ok",
                "action": "url_imported_to_canvas",
                "url": "https://example.com/guide",
                "document_id": "canvas-1",
                "document_path": "web/example/part-01.md",
                "document_count": 2,
                "import_group_id": "fetch-abc123",
                "chunked": True,
                "truncated": False,
                "content_format": "html",
                "fetch_summary": "Page content extracted: Example Guide",
                "documents": [
                    {
                        "document_id": "canvas-1",
                        "document_path": "web/example/part-01.md",
                        "title": "Example Guide (Part 1/2)",
                        "line_count": 120,
                        "source_url": "https://example.com/guide",
                        "source_title": "Example Guide",
                        "source_kind": "fetched_url",
                        "import_group_id": "fetch-abc123",
                        "chunk_index": 1,
                        "chunk_count": 2,
                    },
                    {
                        "document_id": "canvas-2",
                        "document_path": "web/example/part-02.md",
                        "title": "Example Guide (Part 2/2)",
                        "line_count": 80,
                        "source_url": "https://example.com/guide",
                        "source_title": "Example Guide",
                        "source_kind": "fetched_url",
                        "import_group_id": "fetch-abc123",
                        "chunk_index": 2,
                        "chunk_count": 2,
                    },
                ],
            },
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["document_count"], 2)
        self.assertEqual(result["import_group_id"], "fetch-abc123")
        self.assertEqual(len(result["documents"]), 2)
        self.assertEqual(result["documents"][0]["chunk_index"], 1)
        self.assertEqual(result["documents"][1]["chunk_count"], 2)
        self.assertEqual(result["fetch_summary"], "Page content extracted: Example Guide")

    def test_prepare_tool_result_for_transcript_preserves_canvas_expand_payloads(self):
        visible_lines = [f"{index}: {'x' * 80}" for index in range(1, 700)]

        result = _prepare_tool_result_for_transcript(
            "expand_canvas_document",
            {
                "status": "ok",
                "action": "expanded",
                "document_id": "canvas-1",
                "title": "large.txt",
                "format": "text",
                "line_count": len(visible_lines),
                "visible_lines": visible_lines,
                "visible_line_end": len(visible_lines),
                "is_truncated": False,
            },
        )

        self.assertIsInstance(result, str)
        self.assertIn("large.txt", result)
        self.assertIn("699 lines", result)
        # all visible lines should be present in the formatted output
        self.assertIn("1: " + "x" * 80, result)

    def test_apply_tool_output_budget_compacts_large_results_before_next_turn(self):
        base_messages = [{"role": "user", "content": "Summarize the fetched docs."}]
        long_fetch_result = {
            "url": "https://example.com/docs",
            "title": "Docs",
            "content": "Important documentation details. " * 200,
            "meta_description": "Short docs description.",
            "structured_data": "headline: Docs headline\ntext: Important structured summary",
            "status": 200,
            "content_format": "html",
            "cleanup_applied": True,
        }
        fetch_transcript = _prepare_tool_result_for_transcript(
            "fetch_url",
            long_fetch_result,
            fetch_url_token_threshold=10_000,
        )
        entries = [
            {
                "tool_name": "fetch_url",
                "tool_args": {"url": "https://example.com/docs"},
                "call_id": "call-1",
                "result": long_fetch_result,
                "summary": "Page content extracted: Docs",
                "transcript_result": fetch_transcript,
                "ok": True,
            },
            {
                "tool_name": "read_file",
                "tool_args": {"path": "README.md"},
                "call_id": "call-2",
                "result": "A" * 4000,
                "summary": "File read: README.md",
                "transcript_result": "A" * 4000,
                "ok": True,
            },
        ]

        with patch("agent.PROMPT_MAX_INPUT_TOKENS", 400), patch("agent.AGENT_CONTEXT_COMPACTION_THRESHOLD", 0.5):
            tool_messages, transcript_results, tool_execution_result_message, compacted = _apply_tool_output_budget(
                base_messages,
                entries,
                fetch_url_token_threshold=10_000,
                fetch_url_clip_aggressiveness=20,
            )

        self.assertTrue(compacted)
        self.assertEqual(len(tool_messages), 2)
        self.assertEqual(len(transcript_results), 2)
        self.assertIn("Budget note:", tool_messages[0]["content"])
        self.assertIn("Prompt-budget compacted result.", tool_messages[1]["content"])
        self.assertIsNotNone(tool_execution_result_message)
        self.assertIn("Recovery:", tool_execution_result_message["content"])

    def test_apply_tool_output_budget_compacts_error_results_without_successes(self):
        base_messages = [{"role": "user", "content": "Summarize the failure."}]
        long_error = "Traceback: " + ("failed step; " * 300)
        entries = [
            {
                "tool_name": "read_file",
                "tool_args": {"path": "README.md"},
                "call_id": "call-1",
                "execution_error": long_error,
                "ok": False,
            }
        ]

        with patch("agent.PROMPT_MAX_INPUT_TOKENS", 120), patch("agent.AGENT_CONTEXT_COMPACTION_THRESHOLD", 0.5):
            tool_messages, transcript_results, tool_execution_result_message, compacted = _apply_tool_output_budget(
                base_messages,
                entries,
            )

        self.assertTrue(compacted)
        self.assertEqual(len(tool_messages), 1)
        self.assertLess(len(tool_messages[0]["content"]), len(long_error))
        self.assertIn("Recovery:", tool_messages[0]["content"])
        self.assertEqual(transcript_results[0]["tool_name"], "read_file")
        self.assertIn("summary", transcript_results[0])
        self.assertIsNone(tool_execution_result_message)

    def test_build_tool_execution_result_message_surfaces_fetch_recovery_for_clipped_results(self):
        message = _build_tool_execution_result_message(
            [
                {
                    "tool_name": "fetch_url",
                    "arguments": {"url": "https://example.com/docs"},
                    "ok": True,
                    "summary": "Page content extracted: Docs",
                    "result": {
                        "content_mode": "clipped_text",
                        "summary_notice": "Content was clipped and grep_fetched_content should be used for exact text.",
                    },
                }
            ]
        )

        self.assertIsNotNone(message)
        self.assertIn("This guidance is step-local", message["content"])
        self.assertIn("later asks you to verify or refresh", message["content"])
        self.assertIn("Recovery:", message["content"])
        self.assertIn("grep_fetched_content", message["content"])

    def test_tool_specs_include_preview_operation_schema_and_new_guidance(self):
        preview_specs = get_openai_tool_specs(
            ["preview_canvas_changes", "validate_canvas_document", "batch_read_canvas_documents"],
            canvas_documents=[{"id": "doc-1", "title": "draft.py", "content": "print('x')\n"}],
        )
        preview_spec_map = {spec["function"]["name"]: spec for spec in preview_specs}
        operations_items = preview_spec_map["preview_canvas_changes"]["function"]["parameters"]["properties"]["operations"]["items"]
        enabled_specs = {
            spec["name"]: spec
            for spec in get_enabled_tool_specs(["search_files", "set_canvas_viewport", "clear_canvas", "batch_canvas_edits", "search_canvas_document", "validate_canvas_document", "batch_read_canvas_documents"])
        }

        self.assertIn("oneOf", operations_items)
        self.assertEqual(
            {variant["properties"]["action"]["enum"][0] for variant in operations_items["oneOf"]},
            {"replace", "insert", "delete"},
        )
        self.assertIn("Prefer path-only search first", enabled_specs["search_files"]["prompt"]["guidance"])
        self.assertIn("Use 0 to keep it pinned", enabled_specs["set_canvas_viewport"]["parameters"]["properties"]["ttl_turns"]["description"])
        self.assertIn("permanent", enabled_specs["set_canvas_viewport"]["parameters"]["properties"])
        self.assertIn("targets", enabled_specs["batch_canvas_edits"]["parameters"]["properties"])
        self.assertIn("context_lines", enabled_specs["search_canvas_document"]["parameters"]["properties"])
        self.assertIn("offset", enabled_specs["search_canvas_document"]["parameters"]["properties"])
        self.assertIn("validator", enabled_specs["validate_canvas_document"]["parameters"]["properties"])
        self.assertIn("documents", enabled_specs["batch_read_canvas_documents"]["parameters"]["properties"])
        self.assertIn("explicitly requests deleting all canvas documents", enabled_specs["clear_canvas"]["prompt"]["guidance"])

    def test_format_tool_execution_error_hides_internal_exception_class_names(self):
        error_text = _format_tool_execution_error(ValueError("Canvas document not found for path: src/app.py"))
        custom_error = type("CanvasDocumentLookupError", (Exception,), {})("Canvas document not found for path: src/app.py")

        self.assertEqual(error_text, "Canvas document not found for path: src/app.py")
        self.assertEqual(_format_tool_execution_error(custom_error), "Canvas document not found for path: src/app.py")

    def test_tool_result_has_error_detects_status_error_payloads(self):
        self.assertTrue(_tool_result_has_error("sub_agent", {"status": "error", "error": "failed"}))
        self.assertTrue(_tool_result_has_error("image_explain", {"status": "missing_image", "error": "missing"}))
        self.assertFalse(_tool_result_has_error("ask_clarifying_question", {"status": "needs_user_input"}))

    def test_apply_tool_output_budget_omits_nonstandard_tool_message_id(self):
        base_messages = [{"role": "user", "content": "Read the file."}]
        entries = [
            {
                "tool_name": "read_file",
                "tool_args": {"path": "README.md"},
                "call_id": "call-1",
                "result": {"status": "ok", "path": "README.md", "content": "hello"},
                "summary": "File read: README.md",
                "transcript_result": {"status": "ok", "path": "README.md", "content": "hello"},
                "ok": True,
            }
        ]

        tool_messages, _, _, _ = _apply_tool_output_budget(base_messages, entries)

        self.assertEqual(tool_messages[0]["role"], "tool")
        self.assertEqual(tool_messages[0]["tool_call_id"], "call-1")
        self.assertNotIn("id", tool_messages[0])

    def test_run_agent_stream_deduplicates_fetch_guidance_system_message(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/1"}, call_id="call-1", index=0),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=3, total_tokens=6)),
                ]
            ),
            iter(
                [
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/2"}, call_id="call-2", index=0),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=3, total_tokens=6)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Done."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3)),
                ]
            ),
        ]
        fetch_results = [
            ({"url": "https://example.com/1", "title": "One", "content": "content", "content_mode": "full_text"}, "Fetched first"),
            ({"url": "https://example.com/2", "title": "Two", "content": "content", "content_mode": "full_text"}, "Fetched second"),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create, patch(
            "agent._execute_tool",
            side_effect=fetch_results,
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Check two pages"}], "deepseek-chat", 4, ["fetch_url"]))

        self.assertIn({"type": "answer_delta", "text": "Done."}, events)
        third_call_messages = mocked_create.call_args_list[2].kwargs["messages"]
        fetch_guidance_messages = [
            message
            for message in third_call_messages
            if str(message.get("role") or "") == "system"
            and "[TOOL EXECUTION RESULTS]" in str(message.get("content") or "")
        ]
        self.assertEqual(len(fetch_guidance_messages), 1)

    def test_run_agent_stream_deduplicates_missing_final_answer_instruction(self):
        responses = [
            iter([self._stream_chunk(reasoning="One."), self._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))]),
            iter([self._stream_chunk(reasoning="Two."), self._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))]),
            iter([self._stream_chunk(content="Final."), self._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))]),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create:
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-reasoner", 3, []))

        self.assertIn({"type": "answer_delta", "text": "Final."}, events)
        third_call_messages = mocked_create.call_args_list[2].kwargs["messages"]
        retry_markers = [message for message in third_call_messages if "MISSING FINAL ANSWER" in str(message.get("content") or "")]
        self.assertEqual(len(retry_markers), 1)

    def test_run_agent_stream_recovers_from_context_overflow_before_model_turn(self):
        api_messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Need answer"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "search_web", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "A" * 2500},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-2", "type": "function", "function": {"name": "fetch_url", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "call-2", "content": "B" * 2500},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-3", "type": "function", "function": {"name": "search_news_ddgs", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "call-3", "content": "C" * 2500},
        ]
        responses = [
            Exception("context_length_exceeded"),
            iter([self._stream_chunk(content="Recovered."), self._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))]),
        ]

        with patch("agent.PROMPT_MAX_INPUT_TOKENS", 300), patch(
            "agent.client.chat.completions.create",
            side_effect=responses,
        ) as mocked_create:
            events = list(run_agent_stream(api_messages, "deepseek-chat", 2, []))

        self.assertIn({"type": "answer_delta", "text": "Recovered."}, events)
        self.assertEqual(mocked_create.call_count, 2)
        retried_messages = mocked_create.call_args_list[1].kwargs["messages"]
        self.assertTrue(any(message["role"] == "user" and "compacted tool step" in message["content"] for message in retried_messages))

    def test_run_agent_stream_traces_overflow_recovery_telemetry(self):
        api_messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Need answer"},
            {
                "role": "assistant",
                "content": "I should inspect older search results.",
                "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "search_web", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "A" * 2500},
            {
                "role": "assistant",
                "content": "Now inspect fetched details.",
                "tool_calls": [{"id": "call-2", "type": "function", "function": {"name": "fetch_url", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "call-2", "content": "B" * 2500},
        ]
        responses = [
            Exception("context_length_exceeded"),
            iter([self._stream_chunk(content="Recovered."), self._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))]),
        ]

        with patch("agent.PROMPT_MAX_INPUT_TOKENS", 250), patch(
            "agent.client.chat.completions.create",
            side_effect=responses,
        ), patch("agent._trace_agent_event") as mocked_trace:
            events = list(run_agent_stream(api_messages, "deepseek-chat", 2, []))

        self.assertIn({"type": "answer_delta", "text": "Recovered."}, events)
        compacted_calls = [call for call in mocked_trace.call_args_list if call.args and call.args[0] == "context_compacted"]
        self.assertTrue(compacted_calls)
        self.assertTrue(any(call.kwargs.get("force") is True for call in compacted_calls))
        self.assertTrue(any((call.kwargs.get("compacted_exchange_count") or 0) >= 1 for call in compacted_calls))
        recovered_calls = [call for call in mocked_trace.call_args_list if call.args and call.args[0] == "context_overflow_recovered"]
        self.assertTrue(recovered_calls)
        self.assertEqual(recovered_calls[-1].kwargs.get("phase"), "main_loop")

    def test_run_agent_stream_reports_unrecoverable_context_overflow(self):
        with patch("agent.client.chat.completions.create", side_effect=Exception("maximum context length exceeded")):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 1, []))

        self.assertIn(
            {
                "type": "tool_error",
                "step": 1,
                "tool": "api",
                "error": CONTEXT_OVERFLOW_RECOVERY_ERROR_TEXT,
            },
            events,
        )
        self.assertIn({"type": "answer_delta", "text": FINAL_ANSWER_ERROR_TEXT}, events)

    def test_final_answer_phase_recovers_from_context_overflow(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("search_web", {"queries": ["x"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)),
                ]
            ),
            Exception("context_length_exceeded"),
            iter([self._stream_chunk(content="Final after compaction."), self._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))]),
        ]

        with patch("agent.PROMPT_MAX_INPUT_TOKENS", 200), patch(
            "agent.AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS",
            0,
        ), patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet" * 200}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 1, ["search_web"]))

        self.assertIn({"type": "answer_delta", "text": "Final after compaction."}, events)

    def test_run_agent_stream_streams_final_answer_deltas_after_tool_calls(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("search_web", {"queries": ["latest"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=2, total_tokens=4)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Hello "),
                    self._stream_chunk(content="world"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 2, ["search_web"]))

        answer_deltas = [event["text"] for event in events if event["type"] == "answer_delta"]
        self.assertEqual(answer_deltas, ["Hello ", "world"])

        tool_result_index = next(
            index
            for index, event in enumerate(events)
            if event["type"] == "tool_result" and event.get("tool") == "search_web"
        )
        answer_start_index = next(index for index, event in enumerate(events) if event["type"] == "answer_start")
        self.assertLess(tool_result_index, answer_start_index)

    def test_run_agent_stream_does_not_buffer_openrouter_answer_on_placeholder_tool_call_delta(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("search_web", {"queries": ["latest"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=2, total_tokens=4)),
                ]
            ),
            iter(
                [
                    self._stream_chunk_openrouter(
                        tool_calls=[
                            {
                                "index": 0,
                                "id": "placeholder-call",
                                "function": {"name": "", "arguments": ""},
                            }
                        ]
                    ),
                    self._stream_chunk_openrouter(content="Hello "),
                    self._stream_chunk_openrouter(content="world"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
        ]

        fake_create = Mock(side_effect=responses)
        fake_target = {
            "record": {"provider": model_registry.OPENROUTER_PROVIDER},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
            "api_model": "deepseek/deepseek-chat",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Test"}],
                    "openrouter:deepseek/deepseek-chat",
                    2,
                    ["search_web"],
                )
            )

        answer_deltas = [event["text"] for event in events if event["type"] == "answer_delta"]
        self.assertEqual(answer_deltas, ["Hello ", "world"])

    def test_run_agent_stream_skips_empty_search_web_tool_calls_without_error(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("search_web", {}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch("agent.search_web_tool") as mocked_search:
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 2, ["search_web"]))

        mocked_search.assert_not_called()
        self.assertFalse(any(event["type"] == "tool_error" and event.get("tool") == "search_web" for event in events))
        tool_result = next(
            event for event in events if event["type"] == "tool_result" and event.get("tool") == "search_web"
        )
        self.assertEqual(tool_result["step"], 1)
        self.assertEqual(tool_result["call_id"], "tool-call-1")
        self.assertEqual(tool_result["summary"], "search_web skipped: no queries provided")

    def test_run_agent_stream_allows_active_tool_calls_even_when_prompt_tools_are_pruned(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("search_web", {"queries": ["x"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create, patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Test"}],
                    "deepseek-chat",
                    2,
                    ["search_web"],
                    prompt_tool_names=[],
                )
            )

        first_call_kwargs = mocked_create.call_args_list[0].kwargs
        self.assertNotIn("tools", first_call_kwargs)
        self.assertFalse(any(event["type"] == "tool_error" and event.get("error") == "Tool disabled: search_web" for event in events))
        self.assertTrue(any(event["type"] == "tool_result" and event.get("tool") == "search_web" for event in events))

    def test_run_agent_stream_separates_reasoning_turns_with_blank_line(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="First reasoning block."),
                    self._tool_call_chunk("search_web", {"queries": ["x"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(reasoning="Second reasoning block."),
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        fake_create = Mock(side_effect=responses)
        fake_target = {
            "record": {"provider": model_registry.DEEPSEEK_PROVIDER},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
            "api_model": "deepseek-reasoner",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-reasoner", 2, ["search_web"]))

        reasoning_deltas = [event["text"] for event in events if event["type"] == "reasoning_delta"]
        self.assertEqual(reasoning_deltas, ["First reasoning block.", "\n\n", "Second reasoning block."])

    def test_run_agent_stream_closes_provider_stream_when_generator_closes(self):
        class FakeResponse:
            def __init__(self):
                self.closed = False

            def __iter__(self):
                yield AppRoutesTestCase._stream_chunk(content="Partial answer.")
                yield AppRoutesTestCase._stream_chunk(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))

            def close(self):
                self.closed = True

        fake_response = FakeResponse()
        fake_create = Mock(return_value=fake_response)
        fake_target = {
            "record": {"provider": model_registry.DEEPSEEK_PROVIDER},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
            "api_model": "deepseek-chat",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target):
            stream = run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 1, [])
            self.assertEqual(next(stream)["type"], "step_started")
            self.assertEqual(next(stream)["type"], "answer_start")
            stream.close()

        self.assertTrue(fake_response.closed)

    def test_run_agent_stream_replays_reasoning_into_next_tool_step(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="Need current info before I answer."),
                    self._tool_call_chunk("search_web", {"queries": ["latest update"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        fake_create = Mock(side_effect=responses)
        fake_target = {
            "record": {"provider": model_registry.DEEPSEEK_PROVIDER},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
            "api_model": "deepseek-reasoner",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-reasoner", 2, ["search_web"]))

        self.assertIn({"type": "answer_delta", "text": "Final answer."}, events)
        second_call_messages = fake_create.call_args_list[1].kwargs["messages"]
        replay_message = next(
            (
                message
                for message in second_call_messages
                if message.get("role") == "system" and "[AGENT REASONING CONTEXT]" in message.get("content", "")
            ),
            None,
        )
        self.assertIsNotNone(replay_message)
        self.assertIn("Need current info before I answer.", replay_message["content"])
        self.assertIn("planned tools = search_web", replay_message["content"])

    def test_run_agent_stream_preserves_openrouter_reasoning_details_across_tool_calls(self):
        responses = [
            iter(
                [
                    self._stream_chunk_openrouter(
                        reasoning_details=[
                            {
                                "type": "reasoning.text",
                                "text": "Need current info. ",
                                "id": "reasoning-text-1",
                                "format": "anthropic-claude-v1",
                                "index": 0,
                            }
                        ]
                    ),
                    self._stream_chunk_openrouter(
                        reasoning_details=[
                            {
                                "type": "reasoning.text",
                                "text": "Search first.",
                                "id": "reasoning-text-1",
                                "format": "anthropic-claude-v1",
                                "index": 0,
                            }
                        ],
                        tool_calls=[
                            {
                                "index": 0,
                                "id": "tool-call-1",
                                "function": {
                                    "name": "search_web",
                                    "arguments": json.dumps({"queries": ["latest update"]}, ensure_ascii=False),
                                },
                            }
                        ],
                    ),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]
        fake_create = Mock(side_effect=responses)
        fake_target = {
            "record": {"provider": model_registry.OPENROUTER_PROVIDER},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
            "api_model": "anthropic/claude-3.7-sonnet",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Test"}],
                    "openrouter:anthropic/claude-3.7-sonnet",
                    2,
                    ["search_web"],
                )
            )

        self.assertIn({"type": "reasoning_delta", "text": "Need current info. "}, events)
        self.assertIn({"type": "reasoning_delta", "text": "Search first."}, events)
        self.assertIn({"type": "answer_delta", "text": "Final answer."}, events)

        second_call_messages = fake_create.call_args_list[1].kwargs["messages"]
        replay_messages = [
            message
            for message in second_call_messages
            if message.get("role") == "system" and "[AGENT REASONING CONTEXT]" in message.get("content", "")
        ]
        self.assertEqual(replay_messages, [])

        assistant_tool_message = next(
            (
                message
                for message in second_call_messages
                if message.get("role") == "assistant" and message.get("tool_calls")
            ),
            None,
        )
        self.assertIsNotNone(assistant_tool_message)
        self.assertEqual(
            assistant_tool_message["reasoning_details"],
            [
                {
                    "type": "reasoning.text",
                    "text": "Need current info. Search first.",
                    "id": "reasoning-text-1",
                    "format": "anthropic-claude-v1",
                    "index": 0,
                }
            ],
        )

    def test_run_agent_stream_skips_reasoning_replay_when_reasoning_empty(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("search_web", {"queries": ["latest update"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        fake_create = Mock(side_effect=responses)
        fake_target = {
            "record": {"provider": model_registry.DEEPSEEK_PROVIDER},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
            "api_model": "deepseek-chat",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 2, ["search_web"]))

        self.assertIn({"type": "answer_delta", "text": "Final answer."}, events)
        second_call_messages = fake_create.call_args_list[1].kwargs["messages"]
        replay_messages = [
            message
            for message in second_call_messages
            if message.get("role") == "system" and "[AGENT REASONING CONTEXT]" in message.get("content", "")
        ]
        self.assertEqual(replay_messages, [])

    def test_run_agent_stream_replays_reasoning_alongside_blocker_memory(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="I should search first, then summarize whatever I find."),
                    self._tool_call_chunk("search_web", {"queries": ["latest update"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Fallback answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        fake_create = Mock(side_effect=responses)
        fake_target = {
            "record": {"provider": model_registry.DEEPSEEK_PROVIDER},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
            "api_model": "deepseek-reasoner",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target), patch(
            "agent.search_web_tool",
            side_effect=RuntimeError("search backend unavailable"),
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Find current info"}], "deepseek-reasoner", 2, ["search_web"]))

        self.assertIn({"type": "answer_delta", "text": "Fallback answer."}, events)
        second_call_messages = fake_create.call_args_list[1].kwargs["messages"]
        replay_message = next(
            (
                message
                for message in second_call_messages
                if message.get("role") == "system" and "[AGENT REASONING CONTEXT]" in message.get("content", "")
            ),
            None,
        )
        blocker_message = next(
            (
                message
                for message in second_call_messages
                if message.get("role") == "system" and "AGENT WORKING MEMORY" in message.get("content", "")
            ),
            None,
        )
        self.assertIsNotNone(replay_message)
        self.assertIsNotNone(blocker_message)
        self.assertIn("I should search first", replay_message["content"])
        self.assertIn("search backend unavailable", blocker_message["content"])

    def test_run_agent_stream_keeps_initial_reasoning_plan_across_long_tool_loop(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="Plan: first search broad context, then verify details, then draft the answer."),
                    self._tool_call_chunk("search_web", {"queries": ["broad context"]}, call_id="tool-call-1"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(reasoning="The broad search is done. I should verify one detail before drafting."),
                    self._tool_call_chunk("search_web", {"queries": ["verify detail"]}, call_id="tool-call-2"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(reasoning="I have enough evidence. I will do one final targeted search, then answer."),
                    self._tool_call_chunk("search_web", {"queries": ["final confirmation"]}, call_id="tool-call-3"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        fake_create = Mock(side_effect=responses)
        fake_target = {
            "record": {"provider": model_registry.DEEPSEEK_PROVIDER},
            "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
            "api_model": "deepseek-reasoner",
            "extra_body": {},
        }

        with patch("agent.resolve_model_target", return_value=fake_target), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Find current info"}], "deepseek-reasoner", 4, ["search_web"]))

        self.assertIn({"type": "answer_delta", "text": "Final answer."}, events)
        fourth_call_messages = fake_create.call_args_list[3].kwargs["messages"]
        replay_message = next(
            (
                message
                for message in fourth_call_messages
                if message.get("role") == "system" and "[AGENT REASONING CONTEXT]" in message.get("content", "")
            ),
            None,
        )
        self.assertIsNotNone(replay_message)
        self.assertIn("Plan: first search broad context, then verify details, then draft the answer.", replay_message["content"])
        self.assertIn("I should verify one detail before drafting.", replay_message["content"])
        self.assertIn("I will do one final targeted search, then answer.", replay_message["content"])

    def test_estimate_message_breakdown_counts_reasoning_replay_as_internal_state(self):
        content = "[AGENT REASONING CONTEXT]\n\nPrior reasoning"
        breakdown = _estimate_message_breakdown({"role": "system", "content": content})

        self.assertEqual(breakdown, {"internal_state": estimate_text_tokens(content)})

    def test_run_agent_stream_reports_missing_final_content_after_retry_budget(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="First reasoning pass."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(reasoning="Second reasoning pass."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-reasoner", 1, []))

        self.assertIn({"type": "reasoning_delta", "text": "First reasoning pass."}, events)
        self.assertIn({"type": "reasoning_delta", "text": "Second reasoning pass."}, events)
        self.assertIn(
            {
                "type": "tool_error",
                "step": 1,
                "tool": "agent",
                "error": "The model still did not provide a final answer in assistant content.",
            },
            events,
        )
        self.assertIn({"type": "answer_delta", "text": FINAL_ANSWER_MISSING_TEXT}, events)
        leaked_reasoning = [event for event in events if event["type"] == "answer_delta" and "reasoning pass" in event["text"]]
        self.assertEqual(leaked_reasoning, [])

    def test_run_agent_stream_injects_blocker_memory_after_tool_failure(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("search_web", {"queries": ["bad query"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Fallback answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create, patch(
            "agent.search_web_tool",
            side_effect=RuntimeError("search backend unavailable"),
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Find current info"}], "deepseek-chat", 2, ["search_web"]))

        self.assertIn({"type": "answer_delta", "text": "Fallback answer."}, events)
        second_call_messages = mocked_create.call_args_list[1].kwargs["messages"]
        blocker_message = next((message for message in second_call_messages if message["role"] == "system" and "AGENT WORKING MEMORY" in message["content"]), None)
        self.assertIsNotNone(blocker_message)
        self.assertIn("search backend unavailable", blocker_message["content"])
        self.assertIn("Failed paths to avoid repeating", blocker_message["content"])

    def test_run_agent_stream_enforces_per_tool_step_limit(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/1"}, call_id="tool-call-1", index=0),
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/2"}, call_id="tool-call-2", index=1),
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/3"}, call_id="tool-call-3", index=2),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.fetch_url_tool",
            return_value={"url": "https://example.com", "title": "Example", "content": "Body"},
        ) as mocked_fetch:
            events = list(run_agent_stream([{"role": "user", "content": "Fetch several pages"}], "deepseek-chat", 2, ["fetch_url"]))

        self.assertEqual(mocked_fetch.call_count, 2)
        per_tool_errors = [
            event for event in events
            if event["type"] == "tool_error" and event["tool"] == "fetch_url" and "Per-tool step limit reached" in event["error"]
        ]
        self.assertEqual(len(per_tool_errors), 1)
        self.assertIn({"type": "answer_delta", "text": "Final answer."}, events)

    def test_run_agent_stream_uses_max_steps_as_default_per_tool_budget(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("append_scratchpad", {"notes": ["note 1"]}, call_id="tool-call-1"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._tool_call_chunk("append_scratchpad", {"notes": ["note 2"]}, call_id="tool-call-2"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._tool_call_chunk("append_scratchpad", {"notes": ["note 3"]}, call_id="tool-call-3"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._tool_call_chunk("append_scratchpad", {"notes": ["note 4"]}, call_id="tool-call-4"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._tool_call_chunk("append_scratchpad", {"notes": ["note 5"]}, call_id="tool-call-5"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._tool_call_chunk("append_scratchpad", {"notes": ["note 6"]}, call_id="tool-call-6"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.append_to_scratchpad",
            side_effect=[
                ({"status": "appended", "scratchpad": "note 1"}, "Scratchpad updated"),
                ({"status": "appended", "scratchpad": "note 1\nnote 2"}, "Scratchpad updated"),
                ({"status": "appended", "scratchpad": "note 1\nnote 2\nnote 3"}, "Scratchpad updated"),
                ({"status": "appended", "scratchpad": "note 1\nnote 2\nnote 3\nnote 4"}, "Scratchpad updated"),
                ({"status": "appended", "scratchpad": "note 1\nnote 2\nnote 3\nnote 4\nnote 5"}, "Scratchpad updated"),
                ({"status": "appended", "scratchpad": "note 1\nnote 2\nnote 3\nnote 4\nnote 5\nnote 6"}, "Scratchpad updated"),
            ],
        ) as mocked_append:
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Remember these notes"}],
                    "deepseek-chat",
                    6,
                    ["append_scratchpad"],
                )
            )

        self.assertEqual(mocked_append.call_count, 6)
        per_tool_errors = [
            event
            for event in events
            if event["type"] == "tool_error" and event["tool"] == "append_scratchpad" and "Per-tool step limit reached" in event["error"]
        ]
        self.assertEqual(per_tool_errors, [])
        self.assertIn({"type": "answer_delta", "text": "Final answer."}, events)

    def test_run_agent_stream_stops_after_api_error_without_duplicate_retry(self):
        responses = [RuntimeError("Error code: 400 - {'error': {'message': 'Invalid consecutive assistant message at message index 2', 'type': 'invalid_request_error'}}")]

        with patch("agent.client.chat.completions.create", side_effect=responses):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-reasoner", 2, []))

        api_errors = [event for event in events if event["type"] == "tool_error" and event["tool"] == "api"]
        self.assertEqual(len(api_errors), 1)
        self.assertIn({"type": "answer_delta", "text": FINAL_ANSWER_ERROR_TEXT}, events)

    def test_run_agent_stream_ignores_truncated_stream_after_content(self):
        class TruncatedStreamResponse:
            def __iter__(self):
                yield AppRoutesTestCase._stream_chunk(content="Final answer.")
                raise http_requests.exceptions.ChunkedEncodingError("incomplete chunked read")

            def close(self):
                return None

        with patch("agent.client.chat.completions.create", return_value=TruncatedStreamResponse()):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 1, []))

        self.assertIn({"type": "answer_delta", "text": "Final answer."}, events)
        self.assertFalse(any(event["type"] == "tool_error" for event in events))
        self.assertIn({"type": "done"}, events)

    def test_extract_html_cleans_noise_and_whitespace(self):
        html = """
        <html>
            <head>
                <title>Example Title</title>
                <style>.hidden { display: none; }</style>
                <script>console.log('ignore')</script>
            </head>
            <body>
                <nav>Navigation</nav>
                <main>
                    <h1>  Heading\u200b </h1>
                    <h1>  Heading\u200b </h1>
                    <p>First line&nbsp;&nbsp; here.</p>
                    <div>\n\nSecond   line\t\tcontinues.\n</div>
                    <div>-----</div>
                </main>
            </body>
        </html>
        """

        result = _extract_html(html, "https://example.com/page")

        self.assertEqual(result["title"], "Example Title")
        self.assertEqual(result["content_format"], "html")
        self.assertTrue(result["content"].startswith("# Heading"))
        self.assertIn("First line here.", result["content"])
        self.assertIn("Second line continues.", result["content"])
        self.assertIn("Heading", result["raw_content"])
        self.assertNotIn("Navigation", result["content"])
        self.assertNotIn("console.log", result["content"])
        self.assertNotIn("-----", result["content"])
        self.assertNotIn("\u200b", result["content"])

    def test_extract_html_converts_core_structure_to_markdown(self):
        html = """
        <html>
            <body>
                <main>
                    <h1>API Docs</h1>
                    <p>Read the <a href="/reference">reference</a> before calling <code>fetch_url</code>.</p>
                    <ul>
                        <li>Install dependencies</li>
                        <li>Configure the API key</li>
                    </ul>
                    <pre><code class="language-bash">pip install -r requirements.txt</code></pre>
                </main>
            </body>
        </html>
        """

        result = _extract_html(html, "https://example.com/docs")

        self.assertIn("# API Docs", result["content"])
        self.assertIn("[reference](https://example.com/reference)", result["content"])
        self.assertIn("`fetch_url`", result["content"])
        self.assertIn("- Install dependencies", result["content"])
        self.assertIn("- Configure the API key", result["content"])
        self.assertIn("```bash\npip install -r requirements.txt\n```", result["content"])
        self.assertIn("Install dependencies", result["raw_content"])
        self.assertIn("pip install -r requirements.txt", result["raw_content"])

    def test_extract_html_preserves_definition_lists_and_spanned_tables(self):
        html = """
        <html>
            <body>
                <main>
                    <dl>
                        <dt>Timeout</dt>
                        <dd>20 seconds</dd>
                        <dt>Output</dt>
                        <dd>Markdown with preserved structure</dd>
                    </dl>
                    <table>
                        <tr>
                            <th rowspan="2">Plan</th>
                            <th colspan="2">Limits</th>
                        </tr>
                        <tr>
                            <th>Tokens</th>
                            <th>Tools</th>
                        </tr>
                        <tr>
                            <td>Pro</td>
                            <td>128k</td>
                            <td>12</td>
                        </tr>
                    </table>
                </main>
            </body>
        </html>
        """

        result = _extract_html(html, "https://example.com/reference")

        self.assertIn("**Timeout**: 20 seconds", result["content"])
        self.assertIn("**Output**: Markdown with preserved structure", result["content"])
        self.assertIn("| Plan | Limits | Limits |", result["content"])
        self.assertIn("| Plan | Tokens | Tools |", result["content"])
        self.assertIn("| Pro | 128k | 12 |", result["content"])

    def test_extract_html_outline_ignores_noise_regions(self):
        html = """
        <html>
            <body>
                <nav><h2>Site Nav</h2></nav>
                <main>
                    <h1>Main Title</h1>
                    <h2>Section A</h2>
                    <p>Body copy.</p>
                </main>
                <footer><h3>Footer Head</h3></footer>
            </body>
        </html>
        """

        result = _extract_html(html, "https://example.com/outline")

        self.assertEqual(result["outline"], ["[h1] Main Title", "[h2] Section A"])
        self.assertEqual(result["content_source_element"], "main")

    def test_extract_html_falls_back_to_meta_noscript_and_json_ld_when_body_is_thin(self):
        html = """
        <html>
            <head>
                <title>Rates Page</title>
                <title>Rates Page</title>
                <meta name="description" content="Current market summary for dollars and euros.">
                <script type="application/ld+json">
                    {
                        "headline": "Live USD/TRY and EUR/TRY data",
                        "description": "Current exchange-rate information on the open market."
                    }
                </script>
            </head>
            <body>
                <aside>Supplemental rate notes from the sidebar.</aside>
                <main><div></div></main>
                <noscript>Fallback rate summary shown without JavaScript.</noscript>
            </body>
        </html>
        """

        result = _extract_html(html, "https://example.com/rates")

        self.assertEqual(result["title"], "Rates Page")
        self.assertEqual(result["title"], "Rates Page")
        self.assertIn("Current market summary for dollars and euros.", result["content"])
        self.assertIn("Supplemental rate notes from the sidebar.", result["content"])
        self.assertIn("Fallback rate summary shown without JavaScript.", result["content"])
        self.assertIn("Live USD/TRY and EUR/TRY data", result["content"])
        self.assertIn("Live USD/TRY and EUR/TRY data", result["content"])

    def test_combine_distinct_text_blocks_removes_contained_longer_duplicates(self):
        combined = web_tools._combine_distinct_text_blocks(
            [
                "This API requires authentication and explicit version headers for every request.",
                "This API requires authentication and explicit version headers for every request. Extra rollout details are also included.",
            ]
        )

        self.assertIn("Extra rollout details are also included.", combined)
        self.assertEqual(combined.count("This API requires authentication and explicit version headers for every request."), 1)

    def test_infer_fetch_summary_profile_detects_technical_docs(self):
        from agent import _infer_fetch_summary_profile

        profile = _infer_fetch_summary_profile(
            {
                "url": "https://docs.example.com/api/reference",
                "title": "API Reference",
                "content_format": "html",
                "content_source_element": "main",
                "outline": ["[h1] Authentication", "[h2] Configuration"],
            }
        )

        self.assertEqual(profile["name"], "technical_documentation")
        self.assertIn("Key APIs or configuration", profile["section_labels"])

    def test_extract_html_surfaces_structured_metadata_even_when_body_is_long(self):
        html = """
        <html>
            <head>
                <title>Reference Docs</title>
                <meta name="description" content="High-level explanation of the API surface.">
                <script type="application/ld+json">
                    {
                        "headline": "Reference Docs headline",
                        "description": "Structured API summary for search engines."
                    }
                </script>
            </head>
            <body>
                <main>
                    <h1>Reference Docs</h1>
                    <p>""" + ("Detailed implementation text. " * 30) + """</p>
                </main>
            </body>
        </html>
        """

        result = _extract_html(html, "https://example.com/reference")

        self.assertEqual(result["meta_description"], "High-level explanation of the API surface.")
        self.assertIn("Reference Docs headline", result["structured_data"])
        self.assertIn("High-level explanation of the API surface.", result["content"])

    def test_grep_fetched_content_tool_handles_invalid_window_args_and_skips_tool_memory_headers(self):
        with patch("web_tools.cache_get", return_value=None), patch(
            "rag_service.get_exact_tool_memory_match",
            return_value={
                "content": (
                    "tool:fetch_url\n"
                    "Input: https://example.com/page\n"
                    "Summary: Example page\n"
                    "needle in page body"
                )
            },
        ):
            result = web_tools.grep_fetched_content_tool(
                "https://example.com/page",
                "needle",
                context_lines="oops",
                max_matches="bad",
            )

        self.assertEqual(result["match_count"], 1)
        self.assertEqual(result["matches"][0]["line_number"], 1)
        self.assertEqual(result["matches"][0]["line"], "needle in page body")

    def test_grep_fetched_content_tool_uses_summarized_fetch_tool_memory_when_available(self):
        with patch("web_tools.cache_get", return_value=None), patch(
            "rag_service.get_exact_tool_memory_match",
            side_effect=lambda tool_name, args_preview: {
                "content": "Summary: distilled page notes\nneedle in summary"
            }
            if tool_name == "fetch_url_summarized"
            else None,
        ), patch(
            "rag_service.search_tool_memory",
            return_value={
                "matches": [
                    {
                        "source_name": "fetch_url_summarized: https://example.com/page | pricing",
                        "text": "Summary: distilled page notes\nneedle in summary",
                    }
                ]
            },
        ):
            result = web_tools.grep_fetched_content_tool(
                "https://example.com/page",
                "needle",
            )

        self.assertEqual(result["match_count"], 1)
        self.assertIn("needle in summary", result["matches"][0]["line"])
        self.assertEqual(result["searched_source"], "tool_memory_summary")

    def test_grep_fetched_content_tool_refetches_when_cache_is_missing(self):
        with patch("web_tools.cache_get", return_value=None), patch(
            "rag_service.get_exact_tool_memory_match",
            return_value=None,
        ), patch(
            "web_tools.fetch_url_tool",
            return_value={
                "url": "https://example.com/page",
                "content": "alpha\nneedle\nomega",
                "status": 200,
            },
        ):
            result = web_tools.grep_fetched_content_tool(
                "https://example.com/page",
                "needle",
            )

        self.assertEqual(result["match_count"], 1)
        self.assertEqual(result["searched_source"], "live_refetch")
        self.assertTrue(result["refetched"])

    def test_grep_fetched_content_tool_prefers_raw_content_from_fetch_cache(self):
        with patch(
            "web_tools.cache_get",
            return_value={
                "url": "https://example.com/page",
                "content": "# Example\n\n- needle hidden inside markdown noise",
                "raw_content": "Example\nalpha\nneedle\nomega",
            },
        ), patch("rag_service.get_exact_tool_memory_match", return_value=None):
            result = web_tools.grep_fetched_content_tool(
                "https://example.com/page",
                "needle",
            )

        self.assertEqual(result["match_count"], 1)
        self.assertEqual(result["matches"][0]["line"], "needle")
        self.assertEqual(result["searched_source"], "fetch_cache")

    def test_fetch_url_tool_recovers_partial_chunked_content(self):
        class FakeResponse:
            def __init__(self):
                self.headers = {"Content-Type": "text/html; charset=utf-8"}
                self.url = "https://example.com/page"
                self.encoding = "utf-8"
                self.status_code = 200

            def iter_content(self, chunk_size=8192):
                yield b"<html><head><title>Example</title></head><body><main>"
                yield b"Recovered partial content"
                raise http_requests.exceptions.ChunkedEncodingError("incomplete chunked read")

        class FakeSession:
            def __init__(self):
                self.max_redirects = 0
                self.trust_env = False
                self.proxies = {}

            def get(self, *args, **kwargs):
                return FakeResponse()

            def close(self):
                return None

        with patch("web_tools._is_safe_url", return_value=(True, "")), patch(
            "web_tools.cache_get",
            return_value=None,
        ), patch("web_tools.cache_set") as mocked_cache_set, patch(
            "web_tools.get_proxy_candidates",
            return_value=[None],
        ), patch("web_tools.http_requests.Session", return_value=FakeSession()):
            result = fetch_url_tool("https://example.com/page")

        self.assertEqual(result["title"], "Example")
        self.assertIn("Recovered partial content", result["content"])
        self.assertTrue(result["partial_content"])
        self.assertIn("partial page content was recovered", result["fetch_warning"])
        self.assertTrue(mocked_cache_set.called)

    def test_fetch_pdf_uses_document_pdf_extractor_output(self):
        class FakePDF:
            def __init__(self):
                self.pages = [object(), object()]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("doc_service._extract_text_from_pdf", return_value="## Page 1\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"), patch(
            "pdfplumber.open",
            return_value=FakePDF(),
        ):
            result = web_tools._extract_pdf(b"%PDF-FAKE", "https://example.com/report.pdf")

        self.assertEqual(result["content_format"], "pdf")
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["pages_extracted"], 2)
        self.assertIn("| A | B |", result["content"])

    def test_fetch_url_tool_uses_proxies_before_direct_fallback(self):
        attempts = []

        class FakeResponse:
            def __init__(self):
                self.headers = {"Content-Type": "text/plain; charset=utf-8"}
                self.url = "https://example.com/page"
                self.encoding = "utf-8"
                self.status_code = 200

            def iter_content(self, chunk_size=8192):
                yield b"Recovered without proxy"

        class FakeSession:
            def __init__(self):
                self.max_redirects = 0
                self.trust_env = False
                self.proxies = {}

            def get(self, *args, **kwargs):
                proxy = self.proxies.get("https") if self.proxies else None
                attempts.append(proxy)
                if proxy:
                    raise http_requests.exceptions.Timeout("proxy failed")
                return FakeResponse()

            def close(self):
                return None

        with patch("web_tools._is_safe_url", return_value=(True, "")), patch(
            "web_tools.cache_get",
            return_value=None,
        ), patch("web_tools.cache_set"), patch(
            "web_tools.get_proxy_candidates",
            return_value=["http://proxy.example:8080", None],
        ) as mocked_candidates, patch("web_tools.http_requests.Session", side_effect=FakeSession):
            result = fetch_url_tool("https://example.com/page")

        mocked_candidates.assert_called_once_with(include_direct_fallback=True)
        self.assertEqual(attempts, ["http://proxy.example:8080", None])
        self.assertEqual(result["content"], "Recovered without proxy")

    def test_fetch_url_tool_retries_with_alternate_headers_when_first_response_is_thin(self):
        header_attempts = []

        class FakeResponse:
            def __init__(self, html):
                self.headers = {"Content-Type": "text/html; charset=utf-8"}
                self.url = "https://example.com/page"
                self.encoding = "utf-8"
                self.status_code = 200
                self._html = html

            def iter_content(self, chunk_size=8192):
                yield self._html.encode("utf-8")

        class FakeSession:
            def __init__(self):
                self.max_redirects = 0
                self.trust_env = False
                self.proxies = {}

            def get(self, *args, **kwargs):
                headers = kwargs.get("headers") or {}
                header_attempts.append(headers.get("Cache-Control"))
                if len(header_attempts) == 1:
                    return FakeResponse("<html><body><main>ok</main></body></html>")
                return FakeResponse(
                    """
                    <html><head><title>Rates</title><meta name=\"description\" content=\"Current USD and EUR rates are listed here.\"></head>
                    <body><main><div>Sufficient fallback content and current market summary are included here.</div></main></body></html>
                    """
                )

            def close(self):
                return None

        with patch("web_tools._is_safe_url", return_value=(True, "")), patch(
            "web_tools.cache_get",
            return_value=None,
        ), patch("web_tools.cache_set") as mocked_cache_set, patch(
            "web_tools.get_proxy_candidates",
            return_value=[None],
        ), patch("web_tools.http_requests.Session", side_effect=FakeSession):
            result = fetch_url_tool("https://example.com/page")

        self.assertEqual(header_attempts[:2], ["max-age=0", "no-cache"])
        self.assertIn("Current USD and EUR rates are listed here.", result["content"])
        self.assertTrue(mocked_cache_set.called)

    def test_fetch_url_tool_retries_without_ssl_verification_on_cert_failure(self):
        verify_values = []

        class FakeResponse:
            def __init__(self):
                self.headers = {"Content-Type": "text/html; charset=utf-8"}
                self.url = "https://example.com/page"
                self.encoding = "utf-8"
                self.status_code = 200

            def iter_content(self, chunk_size=8192):
                yield b"<html><head><title>Example</title></head><body><main>Trusted content</main></body></html>"

        class FakeSession:
            def __init__(self):
                self.max_redirects = 0
                self.trust_env = False
                self.proxies = {}

            def get(self, *args, **kwargs):
                verify_values.append(kwargs.get("verify", True))
                if kwargs.get("verify", True):
                    raise http_requests.exceptions.SSLError(
                        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
                    )
                return FakeResponse()

            def close(self):
                return None

        with patch("web_tools._is_safe_url", return_value=(True, "")), patch(
            "web_tools.cache_get",
            return_value=None,
        ), patch("web_tools.cache_set") as mocked_cache_set, patch(
            "web_tools.get_proxy_candidates",
            return_value=[None],
        ), patch("web_tools.http_requests.Session", side_effect=FakeSession):
            result = fetch_url_tool("https://example.com/page")

        self.assertGreaterEqual(len(verify_values), 2)
        self.assertEqual(verify_values[:2], [True, False])
        self.assertEqual(verify_values[::2], [True] * (len(verify_values) // 2))
        self.assertEqual(verify_values[1::2], [False] * (len(verify_values) // 2))
        self.assertEqual(result["title"], "Example")
        self.assertTrue(result["ssl_verification_bypassed"])
        self.assertIn("without certificate verification", result["fetch_warning"])
        self.assertTrue(mocked_cache_set.called)

    def test_fetch_url_tool_does_not_cache_empty_blocked_page(self):
        class FakeResponse:
            def __init__(self):
                self.headers = {"Content-Type": "text/html; charset=utf-8"}
                self.url = "https://example.com/blocked"
                self.encoding = "utf-8"
                self.status_code = 403

            def iter_content(self, chunk_size=8192):
                yield b"<html><head><title>Forbidden</title></head><body><main></main></body></html>"

        class FakeSession:
            def __init__(self):
                self.max_redirects = 0
                self.trust_env = False
                self.proxies = {}

            def get(self, *args, **kwargs):
                return FakeResponse()

            def close(self):
                return None

        with patch("web_tools._is_safe_url", return_value=(True, "")), patch(
            "web_tools.cache_get",
            return_value=None,
        ), patch("web_tools.cache_set") as mocked_cache_set, patch(
            "web_tools.get_proxy_candidates",
            return_value=[None],
        ), patch("web_tools.http_requests.Session", side_effect=FakeSession):
            result = fetch_url_tool("https://example.com/blocked")

        self.assertFalse(mocked_cache_set.called)
        self.assertEqual(result["error"], "HTTP 403")
        self.assertEqual(result["content"], "")

    def test_search_web_uses_proxies_before_direct_fallback(self):
        attempts = []

        class FakeDDGS:
            def __init__(self, proxy=None):
                self.proxy = proxy

            def __enter__(self):
                attempts.append(self.proxy)
                if self.proxy:
                    raise RuntimeError("proxy failed")
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, max_results=5):
                return [{"title": "Result", "href": "https://example.com", "body": "Snippet"}]

        with patch("web_tools.cache_get", return_value=None), patch("web_tools.cache_set"), patch(
            "web_tools.get_proxy_candidates",
            return_value=["http://proxy.example:8080", None],
        ) as mocked_candidates, patch("web_tools.DDGS", FakeDDGS):
            result = search_web_tool(["example"])

        mocked_candidates.assert_called_once_with(include_direct_fallback=True)
        self.assertEqual(attempts, ["http://proxy.example:8080", None])
        self.assertEqual(result[0]["url"], "https://example.com")

    def test_search_news_ddgs_uses_proxies_before_direct_fallback(self):
        attempts = []

        class FakeDDGS:
            def __init__(self, proxy=None):
                self.proxy = proxy

            def __enter__(self):
                attempts.append(self.proxy)
                if self.proxy:
                    raise RuntimeError("proxy failed")
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def news(self, query, region=None, safesearch=None, timelimit=None, max_results=5):
                return [{"title": "News", "url": "https://example.com/news", "date": "today", "source": "Example"}]

        with patch("web_tools.cache_get", return_value=None), patch("web_tools.cache_set"), patch(
            "web_tools.get_proxy_candidates",
            return_value=["http://proxy.example:8080", None],
        ) as mocked_candidates, patch("web_tools.DDGS", FakeDDGS):
            result = search_news_ddgs_tool(["example"])

        mocked_candidates.assert_called_once_with(include_direct_fallback=True)
        self.assertEqual(attempts, ["http://proxy.example:8080", None])
        self.assertEqual(result[0]["link"], "https://example.com/news")

    def test_search_news_google_uses_proxies_before_direct_fallback(self):
        attempts = []

        class FakeResponse:
            content = b"""<?xml version=\"1.0\"?><rss><channel><item><title>News - Example</title><link>https://example.com/news</link><pubDate>today</pubDate><source>Example</source></item></channel></rss>"""

            def raise_for_status(self):
                return None

        def fake_get(url, headers=None, timeout=None, proxies=None):
            proxy = (proxies or {}).get("https") if proxies else None
            attempts.append(proxy)
            if proxy:
                raise RuntimeError("proxy failed")
            return FakeResponse()

        with patch("web_tools.cache_get", return_value=None), patch("web_tools.cache_set"), patch(
            "web_tools.get_proxy_candidates",
            return_value=["http://proxy.example:8080", None],
        ) as mocked_candidates, patch("web_tools.http_requests.get", side_effect=fake_get):
            result = search_news_google_tool(["example"])

        mocked_candidates.assert_called_once_with(include_direct_fallback=True)
        self.assertEqual(attempts, ["http://proxy.example:8080", None])
        self.assertEqual(result[0]["link"], "https://example.com/news")

    def test_run_agent_stream_clips_long_fetch_results_before_transcript(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/long"}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=6, total_tokens=10)),
                ]
            ),
        ]
        long_content = "\n\n".join(
            [
                "Overview block with broad context and repeated details. " * 12,
                "Focus block about integration strategy and cleanup pipeline. " * 12,
                "Another block covering token threshold handling and retrieval summaries. " * 12,
                "Final block with implementation notes and metadata persistence. " * 12,
            ]
        )

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create, patch(
            "agent.fetch_url_tool",
            return_value={
                "url": "https://example.com/long",
                "title": "Long Example",
                "content": long_content,
                "status": 200,
                "content_format": "html",
                "cleanup_applied": True,
            },
        ), patch("agent.FETCH_SUMMARY_MAX_CHARS", 5000):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Focus on cleanup and token handling"}],
                    "deepseek-chat",
                    2,
                    ["fetch_url"],
                    fetch_url_token_threshold=50,
                )
            )

        tool_capture_event = next(event for event in events if event["type"] == "tool_capture")
        stored_result = tool_capture_event["tool_results"][0]
        self.assertEqual(stored_result["tool_name"], "fetch_url")
        self.assertEqual(stored_result["content_mode"], "clipped_text")
        self.assertIn("clipped", stored_result["summary_notice"])
        self.assertIn("grep_fetched_content", stored_result["summary_notice"])
        self.assertIn("raw_content", stored_result)
        self.assertEqual(stored_result["raw_content"], long_content.strip())

        self.assertIn("recovery_hint", stored_result)
        self.assertIn("grep_fetched_content", stored_result["recovery_hint"])

        second_call_messages = mocked_create.call_args_list[1].kwargs["messages"]
        transcript_content = second_call_messages[-1]["content"]
        self.assertIn("TOOL EXECUTION RESULTS", transcript_content)
        self.assertIn("fetch_url", transcript_content)
        self.assertIn("OK", transcript_content)

    def test_select_summary_source_messages_prioritizes_continuation_focus(self):
        canonical_messages = [
            {"id": 1, "position": 1, "role": "user", "content": "Gardening soil tips and irrigation details. " * 8},
            {"id": 2, "position": 2, "role": "assistant", "content": "More gardening notes and fertilizer reminders. " * 8},
            {"id": 3, "position": 3, "role": "user", "content": "Gemini cache breakpoints and prompt caching constraints. " * 8},
            {"id": 4, "position": 4, "role": "assistant", "content": "Use explicit cache breakpoints for Gemini requests. " * 8},
        ]

        selected = _select_summary_source_messages_by_token_budget(
            canonical_messages,
            canonical_messages,
            target_tokens=120,
            user_preferences="",
            continuation_focus="Need help with Gemini cache breakpoints and prompt caching.",
        )

        self.assertTrue(selected)
        self.assertTrue(any("Gemini cache breakpoints" in message["content"] for message in selected))

    def test_build_summary_prompt_messages_includes_continuation_focus(self):
        prompt_messages = build_summary_prompt_messages(
            [{"role": "user", "content": "Earlier context"}],
            "",
            continuation_focus="Current task is prompt caching for Gemini.",
        )

        self.assertIn("Current continuation focus", prompt_messages[0]["content"])
        self.assertIn("prompt caching for Gemini", prompt_messages[0]["content"])

    def test_run_agent_stream_marks_fetch_failures_clearly_in_transcript(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/blocked"}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Blocked answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=6, total_tokens=10)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create, patch(
            "agent.fetch_url_tool",
            return_value={
                "url": "https://example.com/blocked",
                "content": "",
                "error": "HTTP 403",
                "status": 403,
            },
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Fetch it"}], "deepseek-chat", 2, ["fetch_url"]))

        tool_result_event = next(event for event in events if event["type"] == "tool_result")
        self.assertIn("Fetch failed", tool_result_event["summary"])

        tool_capture_event = next(event for event in events if event["type"] == "tool_capture")
        stored_result = tool_capture_event["tool_results"][0]
        self.assertEqual(stored_result["fetch_outcome"], "error")
        self.assertIn("fetch_url already attempted this URL", stored_result["fetch_diagnostic"])

        second_call_messages = mocked_create.call_args_list[1].kwargs["messages"]
        transcript_content = second_call_messages[-1]["content"]
        self.assertIn("TOOL EXECUTION RESULTS", transcript_content)
        self.assertIn("source of truth", transcript_content)
        self.assertIn("fetch_url", transcript_content)
        self.assertIn("FAILED", transcript_content)

    def test_run_agent_stream_marks_partial_fetch_as_already_attempted(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/page"}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Partial answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=6, total_tokens=10)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create, patch(
            "agent.fetch_url_tool",
            return_value={
                "url": "https://example.com/page",
                "title": "Example",
                "content": "Recovered partial content from the page body for analysis.",
                "status": 200,
                "partial_content": True,
                "fetch_warning": "Connection ended early; partial page content was recovered",
                "content_format": "html",
            },
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Fetch it"}], "deepseek-chat", 2, ["fetch_url"]))

        tool_result_event = next(event for event in events if event["type"] == "tool_result")
        self.assertIn("Partial page content extracted", tool_result_event["summary"])

        tool_capture_event = next(event for event in events if event["type"] == "tool_capture")
        stored_result = tool_capture_event["tool_results"][0]
        self.assertEqual(stored_result["fetch_outcome"], "partial_content")
        self.assertIn("Do not call fetch_url again for the same URL in this turn", stored_result["fetch_diagnostic"])
        self.assertIn("grep_fetched_content", stored_result["fetch_diagnostic"])

        second_call_messages = mocked_create.call_args_list[1].kwargs["messages"]
        transcript_content = second_call_messages[-1]["content"]
        self.assertIn("TOOL EXECUTION RESULTS", transcript_content)
        self.assertIn("fetch_url", transcript_content)
        self.assertIn("OK", transcript_content)

    def test_run_agent_stream_logs_duplicate_fetch_url_calls(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/page"}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8)),
                ]
            ),
            iter(
                [
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/page"}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=6, total_tokens=10)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create, patch(
            "agent.fetch_url_tool",
            return_value={
                "url": "https://example.com/page",
                "title": "Example",
                "content": "Fetched page body with enough detail to reuse without fetching again.",
                "status": 200,
                "content_format": "html",
            },
        ) as mocked_fetch, patch("agent._trace_agent_event") as mocked_trace:
            events = list(run_agent_stream([{"role": "user", "content": "Fetch it"}], "deepseek-chat", 3, ["fetch_url"]))

        mocked_fetch.assert_called_with("https://example.com/page")
        self.assertEqual(mocked_fetch.call_count, 1)
        tool_result_summaries = [event["summary"] for event in events if event["type"] == "tool_result"]
        self.assertIn("Page content extracted", tool_result_summaries[0])
        self.assertIn("Page content extracted", tool_result_summaries[1])

        third_call_messages = mocked_create.call_args_list[2].kwargs["messages"]
        transcript_content = third_call_messages[-1]["content"]
        self.assertIn("TOOL EXECUTION RESULTS", transcript_content)
        self.assertIn("fetch_url", transcript_content)
        duplicate_logs = [call for call in mocked_trace.call_args_list if call.args and call.args[0] == "duplicate_fetch_attempt"]
        self.assertEqual(len(duplicate_logs), 1)
        self.assertEqual(duplicate_logs[0].kwargs["url"], "https://example.com/page")

    def test_higher_clip_aggressiveness_keeps_less_fetch_content(self):
        result = {
            "url": "https://example.com/long",
            "title": "Long Example",
            "content": "A" * 12000,
            "status": 200,
            "content_format": "html",
            "cleanup_applied": True,
        }

        from agent import _prepare_fetch_result_for_model

        less_aggressive = _prepare_fetch_result_for_model(
            result,
            fetch_url_token_threshold=1000,
            fetch_url_clip_aggressiveness=10,
        )
        more_aggressive = _prepare_fetch_result_for_model(
            result,
            fetch_url_token_threshold=1000,
            fetch_url_clip_aggressiveness=90,
        )

        self.assertGreater(len(less_aggressive["content"]), len(more_aggressive["content"]))

    def test_prepare_fetch_result_for_model_preserves_middle_excerpt_when_clipped(self):
        from agent import _prepare_fetch_result_for_model

        result = {
            "url": "https://example.com/long",
            "title": "Long Example",
            "meta_description": "Implementation guidance for the long example page.",
            "content_source_element": "main",
            "outline": ["[h1] Header", "[h2] Middle", "[h2] Footer"],
            "content": (
                ("HEADER section. " * 120)
                + ("MIDDLE UNIQUE MARKER with implementation details. " * 60)
                + ("FOOTER section. " * 120)
            ),
            "status": 200,
            "content_format": "html",
            "cleanup_applied": True,
        }

        prepared = _prepare_fetch_result_for_model(
            result,
            fetch_url_token_threshold=300,
            fetch_url_clip_aggressiveness=50,
        )

        self.assertEqual(prepared["content_mode"], "clipped_text")
        self.assertEqual(prepared["clip_strategy"], "head_middle_tail_excerpt")
        self.assertIn("MIDDLE UNIQUE MARKER", prepared["content"])
        self.assertIn("leading, middle, and trailing excerpts", prepared["summary_notice"].lower())
        self.assertIn("Context anchors:", prepared["summary_notice"])
        self.assertIn("Primary container: main.", prepared["context_summary"])
        self.assertIn("Outline anchors:", prepared["context_summary"])

    def test_build_fetch_tool_message_content_keeps_full_clipped_excerpt(self):
        from agent import _build_fetch_tool_message_content

        clipped_content = ("HEAD " * 900) + "TAIL-MARKER"
        with patch("agent.FETCH_SUMMARY_MAX_CHARS", 1000):
            message = _build_fetch_tool_message_content(
                {"url": "https://example.com/clipped"},
                "Page content extracted",
                {
                    "url": "https://example.com/clipped",
                    "title": "Clipped Example",
                    "content": clipped_content,
                    "content_mode": "clipped_text",
                    "clip_strategy": "head_middle_tail_excerpt",
                },
            )

        self.assertIn("TAIL-MARKER", message)

    def test_run_agent_stream_executes_native_tool_call_without_content_fallback(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("search_web", {"queries": ["x"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Recovered answer"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=4, total_tokens=6)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 2, ["search_web"]))

        self.assertIn("step_update", [event["type"] for event in events])
        self.assertIn("tool_result", [event["type"] for event in events])
        self.assertIn({"type": "answer_delta", "text": "Recovered answer"}, events)

    def test_run_agent_stream_streams_native_pre_tool_text_live_and_strips_intermediate_history(self):
        captured_calls = []

        def fake_create(model, messages, stream, stream_options=None, tools=None, tool_choice=None, temperature=None):
            captured_calls.append(list(messages))
            call_index = len(captured_calls)
            if call_index == 1:
                return iter(
                    [
                        self._stream_chunk(content="Okay, I will check now."),
                        self._tool_call_chunk("search_web", {"queries": ["test"]}),
                        self._stream_chunk(
                            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=20, total_tokens=25)
                        ),
                    ]
                )
            else:
                return iter(
                    [
                        self._stream_chunk(content="Here is the result."),
                        self._stream_chunk(
                            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
                        ),
                    ]
                )

        with patch("agent.client.chat.completions.create", side_effect=fake_create), patch(
            "agent.search_web_tool",
            return_value=[{"title": "R", "url": "https://example.com", "snippet": "S"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 2, ["search_web"]))

        answer_texts = [event["text"] for event in events if event["type"] == "answer_delta"]
        combined_answer = "".join(answer_texts)
        self.assertIn("Okay, I will check now.", combined_answer)
        self.assertIn("Here is the result.", combined_answer)

        self.assertGreaterEqual(len(captured_calls), 2, "Expected at least 2 model calls")
        second_call_messages = captured_calls[1]
        assistant_messages = [m for m in second_call_messages if m.get("role") == "assistant"]
        pre_tool_contents = [m["content"] for m in assistant_messages if "Okay, I will check now" in (m.get("content") or "")]
        self.assertEqual(
            pre_tool_contents,
            [],
            "Pre-tool narrative text should stream live but be stripped from intermediate tool-call history to prevent self-echoing.",
        )

    def test_run_agent_stream_emits_short_pre_tool_text_without_waiting_for_threshold(self):
        responses = [
            iter(
                [
                    self._stream_chunk(content="Hi"),
                    self._tool_call_chunk("search_web", {"queries": ["test"]}),
                    self._stream_chunk(
                        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=20, total_tokens=25)
                    ),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer."),
                    self._stream_chunk(
                        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
                    ),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.search_web_tool",
            return_value=[{"title": "R", "url": "https://example.com", "snippet": "S"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 2, ["search_web"]))

        answer_deltas = [event["text"] for event in events if event["type"] == "answer_delta"]
        self.assertEqual(answer_deltas[0], "Hi")
        self.assertIn("Final answer.", answer_deltas)

    def test_run_agent_stream_streams_plain_answer_chunks_live(self):
        responses = [
            iter(
                [
                    self._stream_chunk(content="Hello "),
                    self._stream_chunk(content="world"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            )
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses):
            events = list(run_agent_stream([{"role": "user", "content": "Selam"}], "deepseek-chat", 1, []))

        answer_deltas = [event["text"] for event in events if event["type"] == "answer_delta"]
        self.assertEqual(answer_deltas, ["Hello ", "world"])

        answer_start_index = next(index for index, event in enumerate(events) if event["type"] == "answer_start")
        first_delta_index = next(
            index for index, event in enumerate(events) if event["type"] == "answer_delta" and event["text"] == "Hello "
        )
        second_delta_index = next(
            index for index, event in enumerate(events) if event["type"] == "answer_delta" and event["text"] == "world"
        )
        usage_index = next(index for index, event in enumerate(events) if event["type"] == "usage")

        self.assertLess(answer_start_index, first_delta_index)
        self.assertLess(first_delta_index, second_delta_index)
        self.assertLess(second_delta_index, usage_index)

    def test_run_agent_stream_can_disable_clarification_answer_buffering_for_live_chat(self):
        responses = [
            iter(
                [
                    self._stream_chunk(content="Hello "),
                    self._stream_chunk(content="world"),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            )
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.get_app_settings",
            return_value={},
        ):
            events = list(
                run_agent_stream(
                    [{"role": "user", "content": "Selam"}],
                    "deepseek-chat",
                    1,
                    ["ask_clarifying_question"],
                    buffer_clarification_answers=False,
                )
            )

        answer_deltas = [event["text"] for event in events if event["type"] == "answer_delta"]
        self.assertEqual(answer_deltas, ["Hello ", "world"])

    def test_chat_stream_response_disables_buffering(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Live output"},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events) as mocked_stream:
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Hello",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-cache")
        self.assertEqual(response.headers.get("X-Accel-Buffering"), "no")
        self.assertFalse(mocked_stream.call_args.kwargs["buffer_clarification_answers"])

    def test_chat_edit_resend_replaces_future_messages(self):
        conversation_id = self._create_conversation()
        with get_db() as conn:
            user_one_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                (conversation_id, "First question", None),
            ).lastrowid
            first_assistant_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'assistant', ?, ?)",
                (conversation_id, "First answer", None),
            ).lastrowid
            edited_user_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                (conversation_id, "Old message", None),
            ).lastrowid
            stale_assistant_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'assistant', ?, ?)",
                (conversation_id, "Old answer", None),
            ).lastrowid

        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "New answer"},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "edited_message_id": edited_user_id,
                    "model": "deepseek-chat",
                    "user_content": "New message",
                    "messages": [
                        {"role": "user", "content": "First question"},
                        {"role": "assistant", "content": "First answer"},
                        {"role": "user", "content": "New message"},
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        message_ids_event = next((event for event in events if event["type"] == "message_ids"), None)
        self.assertIsNotNone(message_ids_event)
        self.assertEqual(message_ids_event["user_message_id"], edited_user_id)
        self.assertIsInstance(message_ids_event["assistant_message_id"], int)

        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, role, content FROM messages WHERE conversation_id = ? AND deleted_at IS NULL ORDER BY id",
                (conversation_id,),
            ).fetchall()
            deleted_row = conn.execute(
                "SELECT deleted_at FROM messages WHERE id = ?",
                (stale_assistant_id,),
            ).fetchone()

        self.assertEqual(
            [(row["id"], row["role"], row["content"]) for row in rows],
            [
                (user_one_id, "user", "First question"),
                (first_assistant_id, "assistant", "First answer"),
                (edited_user_id, "user", "New message"),
                (message_ids_event["assistant_message_id"], "assistant", "New answer"),
            ],
        )
        self.assertIsNotNone(deleted_row)
        self.assertIsNotNone(deleted_row["deleted_at"])

    def test_chat_stream_emits_history_sync_with_canonical_messages(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
            }
        )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Senkron cevap"},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.run_agent_stream", return_value=fake_events):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Hello",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        history_sync_event = next((event for event in events if event["type"] == "history_sync"), None)
        self.assertIsNotNone(history_sync_event)
        self.assertEqual([message["role"] for message in history_sync_event["messages"]], ["user", "assistant"])

    def test_chat_summarizes_oldest_unsummarized_visible_messages(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["context"] * 120)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "auto",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(39):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Message {index + 1} {dense_message}", None),
                )

        fake_summary = {
            "content": "Summary of the first 20 messages with enough retained detail to meet the minimum length validation threshold for summaries.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Live answer"},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.get_prompt_preflight_summary_token_count", return_value=1000), patch(
            "routes.chat.collect_agent_response", return_value=fake_summary
        ), patch("routes.chat.run_agent_stream", return_value=fake_events), patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": f"Message 40 {dense_message}",
                    "messages": [{"role": "user", "content": f"Message 40 {dense_message}"}],
                },
            )
            streamed_events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]

        self.assertEqual(response.status_code, 200)
        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        conversation_messages = conversation_response.get_json()["messages"]
        self.assertEqual(conversation_messages[0]["role"], "summary")
        self.assertTrue(conversation_messages[0]["metadata"]["is_summary"])
        self.assertEqual(conversation_messages[0]["metadata"]["covered_message_count"], 39)
        self.assertEqual(conversation_messages[0]["metadata"]["summary_mode"], "auto")
        self.assertEqual(conversation_messages[0]["metadata"]["trigger_token_count"], 1000)
        self.assertEqual(
            conversation_messages[0]["content"],
            "Conversation summary (generated from deleted messages):\n\nSummary of the first 20 messages with enough retained detail to meet the minimum length validation threshold for summaries.",
        )
        self.assertEqual(len(conversation_messages), 3)
        self.assertEqual(conversation_messages[-1]["role"], "assistant")

        summary_event = next((event for event in streamed_events if event["type"] == "conversation_summary_applied"), None)
        self.assertIsNotNone(summary_event)
        self.assertEqual(summary_event["covered_message_count"], 39)
        self.assertEqual(summary_event["mode"], "auto")

        history_sync_events = [event for event in streamed_events if event["type"] == "history_sync"]
        self.assertEqual(len(history_sync_events), 2)
        self.assertEqual(history_sync_events[-1]["messages"][0]["role"], "summary")

        with get_db() as conn:
            deleted_count = conn.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ? AND deleted_at IS NOT NULL",
                (conversation_id,),
            ).fetchone()["count"]
        self.assertEqual(deleted_count, 39)

    def test_chat_rejects_edit_for_message_removed_by_summary(self):
        conversation_id = self._create_conversation()
        summary_metadata = serialize_message_metadata(
            {
                "is_summary": True,
                "summary_source": "conversation_history",
                "covered_message_ids": [999],
                "covered_message_count": 20,
            }
        )

        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'summary', ?, ?)",
                (conversation_id, "Conversation summary (generated from deleted messages):\n\nSummary", summary_metadata),
            )

        response = self.client.post(
            "/chat",
            json={
                "conversation_id": conversation_id,
                "edited_message_id": 999,
                "model": "deepseek-chat",
                "user_content": "New content",
                "messages": [{"role": "user", "content": "New content"}],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "This message can no longer be edited because it was summarized.")

    def test_chat_summary_covers_interleaved_tool_messages(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["history"] * 120)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "auto",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                (conversation_id, f"First user message {dense_message}", None),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'assistant', ?, ?)",
                (conversation_id, f"First answer {dense_message}", None),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, tool_call_id) VALUES (?, 'tool', ?, ?)",
                (conversation_id, '{"ok":true}', "call-1"),
            )
            for index in range(7):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Follow-up user message {index + 1} {dense_message}", None),
                )

        fake_summary = {
            "content": "Summary of the first five visible messages with enough retained detail to meet the minimum length validation threshold for summaries.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "New live answer"},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.get_prompt_preflight_summary_token_count", return_value=1000), patch(
            "routes.chat.collect_agent_response", return_value=fake_summary
        ), patch("routes.chat.run_agent_stream", return_value=fake_events), patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": f"Third user message {dense_message}",
                    "messages": [{"role": "user", "content": f"Third user message {dense_message}"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)

        with get_db() as conn:
            visible_rows = conn.execute(
                "SELECT role, content, tool_call_id FROM messages WHERE conversation_id = ? AND deleted_at IS NULL ORDER BY position, id",
                (conversation_id,),
            ).fetchall()
            deleted_count = conn.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ? AND deleted_at IS NOT NULL",
                (conversation_id,),
            ).fetchone()["count"]

        self.assertEqual(
            [(row["role"], row["tool_call_id"]) for row in visible_rows],
            [("summary", None), ("user", None), ("assistant", None)],
        )
        self.assertGreaterEqual(deleted_count, 6)

    def test_chat_summary_can_trigger_from_large_tool_history(self):
        conversation_id = self._create_conversation()
        dense_tool_payload = json.dumps(
            {
                "results": [
                    {
                        "title": f"Result {index}",
                        "content": " ".join(["tool-context"] * 120),
                    }
                    for index in range(12)
                ]
            },
            ensure_ascii=False,
        )
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "auto",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                (conversation_id, "Short user message", None),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'assistant', ?, ?)",
                (conversation_id, "Short assistant reply", None),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, tool_call_id) VALUES (?, 'tool', ?, ?)",
                (conversation_id, dense_tool_payload, "call-1"),
            )

        fake_summary = {
            "content": "Summary of the early visible conversation with enough retained detail to meet the minimum length validation threshold for summaries.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Fresh answer"},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.get_prompt_preflight_summary_token_count", return_value=1000), patch(
            "routes.chat.collect_agent_response", return_value=fake_summary
        ), patch("routes.chat.run_agent_stream", return_value=fake_events), patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": "Latest question",
                    "messages": [{"role": "user", "content": "Latest question"}],
                },
            )
            streamed_events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]

        self.assertEqual(response.status_code, 200)
        summary_event = next((event for event in streamed_events if event["type"] == "conversation_summary_applied"), None)
        self.assertIsNotNone(summary_event)
        self.assertEqual(summary_event["covered_message_count"], 2)
        self.assertEqual(summary_event["covered_tool_message_count"], 1)

        with get_db() as conn:
            visible_rows = conn.execute(
                "SELECT role, tool_call_id FROM messages WHERE conversation_id = ? AND deleted_at IS NULL ORDER BY position, id",
                (conversation_id,),
            ).fetchall()

        self.assertEqual(
            [(row["role"], row["tool_call_id"]) for row in visible_rows],
            [
                ("summary", None),
                ("user", None),
                ("assistant", None),
            ],
        )

    def test_build_summary_prompt_messages_filters_empty_and_merges_assistant_history(self):
        prompt_messages = build_summary_prompt_messages(
            [
                {"role": "user", "content": "First user request"},
                {"role": "assistant", "content": "   "},
                {"role": "assistant", "content": "First assistant note"},
                {"role": "assistant", "content": "Second assistant note"},
                {"role": "assistant", "content": FINAL_ANSWER_ERROR_TEXT},
                {"role": "user", "content": "   "},
                {"role": "user", "content": "Second user request"},
            ],
            "",
        )

        self.assertEqual([message["role"] for message in prompt_messages], ["system", "user"])
        self.assertIn("USER:\nFirst user request", prompt_messages[1]["content"])
        self.assertIn("ASSISTANT:\nFirst assistant note\n\nSecond assistant note", prompt_messages[1]["content"])
        self.assertIn("USER:\nSecond user request", prompt_messages[1]["content"])
        self.assertNotIn(FINAL_ANSWER_ERROR_TEXT, prompt_messages[1]["content"])

    def test_build_summary_prompt_messages_include_tool_findings_from_assistant_metadata(self):
        prompt_messages = build_summary_prompt_messages(
            [
                {"role": "user", "content": "Research the market"},
                {
                    "role": "assistant",
                    "content": "I reviewed the sources.",
                    "metadata": {
                        "tool_results": [
                            {
                                "tool_name": "fetch_url",
                                "summary": "Revenue grew 18 percent year over year.",
                                "content": "Very long tool payload that should not be needed when a summary is available.",
                            },
                            {
                                "tool_name": "search_web",
                                "content": "Analysts expect demand to remain strong through Q4 based on recent filings and channel checks.",
                            },
                        ]
                    },
                },
            ],
            "",
        )

        transcript = prompt_messages[1]["content"]
        self.assertIn("Tool findings:", transcript)
        self.assertIn("fetch_url: Revenue grew 18 percent year over year.", transcript)
        self.assertIn("search_web: Analysts expect demand to remain strong through Q4", transcript)

    def test_build_summary_prompt_messages_include_tool_role_messages(self):
        prompt_messages = build_summary_prompt_messages(
            [
                {"role": "user", "content": "Check the source"},
                {"role": "assistant", "content": "I will inspect the page."},
                {"role": "tool", "content": '{"ok": true, "headline": "Market expands"}', "tool_call_id": "call-9"},
            ],
            "",
        )

        transcript = prompt_messages[1]["content"]
        self.assertIn("TOOL RESULT:\ncall call-9: {\"ok\": true, \"headline\": \"Market expands\"}", transcript)

    def test_estimate_prompt_tokens_counts_tool_call_payload(self):
        plain_messages = [
            {
                "role": "assistant",
                "content": "Done.",
            }
        ]
        tool_call_messages = [
            {
                "role": "assistant",
                "content": "Done.",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "search_web",
                            "arguments": '{"queries":["token budgets"]}',
                        },
                    }
                ],
            }
        ]

        self.assertGreater(_estimate_prompt_tokens(tool_call_messages), _estimate_prompt_tokens(plain_messages))

    def test_select_recent_prompt_window_respects_token_budget(self):
        messages = [
            {"role": "user", "content": "alpha " * 120},
            {"role": "assistant", "content": "beta " * 120},
            {"role": "user", "content": "gamma " * 120},
        ]

        selected = _select_recent_prompt_window(messages, max_tokens=120, min_user_messages=2)

        self.assertLessEqual(_estimate_prompt_tokens(build_api_messages(selected)), 120)
        self.assertLessEqual(sum(1 for message in selected if message["role"] == "user"), 2)

    def test_select_recent_prompt_window_keeps_complete_tool_call_blocks(self):
        messages = [
            {"role": "user", "content": "older context " * 80, "position": 1, "id": 1},
            {
                "role": "assistant",
                "content": "Calling a tool now.",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search_web", "arguments": "{}"},
                    }
                ],
                "position": 2,
                "id": 2,
            },
            {"role": "tool", "content": '{"ok": true}', "tool_call_id": "call-1", "position": 3, "id": 3},
            {"role": "user", "content": "latest question", "position": 4, "id": 4},
        ]

        selected = _select_recent_prompt_window(messages, max_tokens=200)

        self.assertEqual([message["role"] for message in selected], ["assistant", "tool", "user"])
        self.assertEqual(selected[0]["tool_calls"][0]["id"], "call-1")
        self.assertEqual(selected[1]["tool_call_id"], "call-1")

    def test_select_recent_prompt_window_skips_incomplete_tool_call_blocks(self):
        messages = [
            {
                "role": "assistant",
                "content": "Calling a tool now.",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search_web", "arguments": "{}"},
                    }
                ],
                "position": 1,
                "id": 1,
            },
            {"role": "user", "content": "latest question", "position": 2, "id": 2},
        ]

        selected = _select_recent_prompt_window(messages, max_tokens=300)

        self.assertEqual([message["role"] for message in selected], ["user"])

    def test_select_recent_prompt_window_redacts_old_tool_output_but_keeps_current_turn_tool_output(self):
        messages = [
            {"role": "user", "content": "Older question", "position": 1, "id": 1},
            {
                "role": "assistant",
                "content": "Calling old tool.",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search_web", "arguments": "{}"},
                    }
                ],
                "position": 2,
                "id": 2,
            },
            {"role": "tool", "content": "A" * 2500, "tool_call_id": "call-1", "position": 3, "id": 3},
            {"role": "user", "content": "Latest question", "position": 4, "id": 4},
            {
                "role": "assistant",
                "content": "Calling current tool.",
                "tool_calls": [
                    {
                        "id": "call-2",
                        "type": "function",
                        "function": {"name": "fetch_url", "arguments": "{}"},
                    }
                ],
                "position": 5,
                "id": 5,
            },
            {"role": "tool", "content": "Current tool result", "tool_call_id": "call-2", "position": 6, "id": 6},
        ]

        selected = _select_recent_prompt_window(messages, max_tokens=500)

        redacted_old_tool = next(message for message in selected if message.get("tool_call_id") == "call-1")
        current_turn_tool = next(message for message in selected if message.get("tool_call_id") == "call-2")

        self.assertEqual(redacted_old_tool["role"], "tool")
        self.assertEqual(redacted_old_tool["content"], OMITTED_TOOL_OUTPUT_TEXT)
        self.assertEqual(current_turn_tool["role"], "tool")
        self.assertEqual(current_turn_tool["content"], "Current tool result")
        self.assertLessEqual(_estimate_prompt_tokens(build_api_messages(selected)), 500)

    def test_select_recent_prompt_window_skips_resolved_historical_tool_blocks(self):
        messages = [
            {"role": "user", "content": "Older question", "position": 1, "id": 1},
            {
                "role": "assistant",
                "content": "Calling old tool.",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search_web", "arguments": "{}"},
                    }
                ],
                "position": 2,
                "id": 2,
            },
            {"role": "tool", "content": "Old tool result", "tool_call_id": "call-1", "position": 3, "id": 3},
            {"role": "assistant", "content": "Resolved final answer", "position": 4, "id": 4},
            {"role": "user", "content": "Latest question", "position": 5, "id": 5},
        ]

        selected = _select_recent_prompt_window(messages, max_tokens=500)

        self.assertEqual([message["role"] for message in selected], ["user", "assistant", "user"])
        self.assertEqual(selected[1]["content"], "Resolved final answer")
        self.assertFalse(any(message.get("tool_call_id") == "call-1" for message in selected))

    def test_select_recent_prompt_window_entropy_prefers_code_dense_blocks(self):
        messages = [
            {"role": "user", "content": "Intro request", "position": 1, "id": 1},
            {"role": "assistant", "content": "filler " * 200, "position": 2, "id": 2},
            {
                "role": "assistant",
                "content": "```python\nvalue = load_config()\nprint(value)\n```",
                "position": 3,
                "id": 3,
            },
            {"role": "user", "content": "Please continue with the config issue", "position": 4, "id": 4},
        ]

        selected = _select_recent_prompt_window(
            messages,
            max_tokens=120,
            settings={
                "context_selection_strategy": "entropy",
                "entropy_profile": "balanced",
                "entropy_protect_code_blocks": "true",
                "entropy_protect_tool_results": "true",
                "entropy_reference_boost": "false",
            },
        )

        selected_contents = [message["content"] for message in selected]
        self.assertIn("```python\nvalue = load_config()\nprint(value)\n```", selected_contents)
        self.assertIn("Please continue with the config issue", selected_contents)
        self.assertNotIn("filler " * 200, selected_contents)

    def test_budgeted_prompt_messages_keep_numeric_short_follow_up_with_previous_assistant(self):
        canonical_messages = normalize_chat_messages(
            [
                {"id": 1, "position": 1, "role": "user", "content": "Older setup context " * 80},
                {"id": 2, "position": 2, "role": "assistant", "content": "Older answer " * 60},
                {"id": 3, "position": 3, "role": "user", "content": "Command output " * 140},
                {
                    "id": 4,
                    "position": 4,
                    "role": "assistant",
                    "content": "1. Mevcut tunnel'a hostname ekleyelim.\n2. Yeni bir tunnel oluşturalım.\nHangisini seçiyorsunuz?",
                },
                {"id": 5, "position": 5, "role": "user", "content": "1"},
            ]
        )
        settings = {"user_preferences": "", "scratchpad": ""}

        with patch("routes.chat._select_prefix_prompt_window", return_value=[]), patch(
            "routes.chat.get_prompt_max_input_tokens", return_value=6000
        ), patch("routes.chat.get_prompt_response_token_reserve", return_value=1000), patch(
            "routes.chat.get_prompt_recent_history_max_tokens", return_value=15
        ), patch("routes.chat.get_prompt_summary_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_rag_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_tool_trace_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_tool_memory_max_tokens", return_value=0
        ), patch("routes.chat.get_clarification_max_questions", return_value=5):
            api_messages, _, stats, _ = _build_budgeted_prompt_messages(
                canonical_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=None,
            )

        visible_history = [message for message in api_messages if message["role"] in {"assistant", "user"}]

        self.assertEqual([entry["id"] for entry in stats["recent_selection_trace"]], [5])
        self.assertEqual([entry["id"] for entry in stats["prompt_history_trace"]][-2:], [4, 5])
        self.assertEqual(stats["continuity_guard_status"], "applied")
        self.assertEqual(stats["continuity_guard_anchor"]["id"], 4)
        self.assertEqual(stats["continuity_guard_user"]["id"], 5)
        self.assertEqual([message["role"] for message in visible_history[-2:]], ["assistant", "user"])
        self.assertIn("Hangisini seçiyorsunuz?", visible_history[-2]["content"])
        self.assertEqual(visible_history[-1]["content"], "1")

    def test_budgeted_prompt_messages_keep_short_confirmation_with_previous_assistant(self):
        canonical_messages = normalize_chat_messages(
            [
                {"id": 1, "position": 1, "role": "user", "content": "Önceki uzun talep " * 90},
                {"id": 2, "position": 2, "role": "assistant", "content": "Önceki uzun cevap " * 70},
                {
                    "id": 3,
                    "position": 3,
                    "role": "assistant",
                    "content": "Mevcut tunnel yapılandırmasını güncelleyip servisi yeniden başlatayım mı?",
                },
                {"id": 4, "position": 4, "role": "user", "content": "Evet"},
            ]
        )
        settings = {"user_preferences": "", "scratchpad": ""}

        with patch("routes.chat._select_prefix_prompt_window", return_value=[]), patch(
            "routes.chat.get_prompt_max_input_tokens", return_value=6000
        ), patch("routes.chat.get_prompt_response_token_reserve", return_value=1000), patch(
            "routes.chat.get_prompt_recent_history_max_tokens", return_value=10
        ), patch("routes.chat.get_prompt_summary_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_rag_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_tool_trace_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_tool_memory_max_tokens", return_value=0
        ), patch("routes.chat.get_clarification_max_questions", return_value=5):
            api_messages, _, stats, _ = _build_budgeted_prompt_messages(
                canonical_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=None,
            )

        visible_history = [message for message in api_messages if message["role"] in {"assistant", "user"}]

        self.assertEqual([entry["id"] for entry in stats["recent_selection_trace"]], [4])
        self.assertEqual([entry["id"] for entry in stats["prompt_history_trace"]][-2:], [3, 4])
        self.assertEqual(stats["continuity_guard_status"], "applied")
        self.assertEqual(stats["continuity_guard_anchor"]["id"], 3)
        self.assertEqual(stats["continuity_guard_user"]["id"], 4)
        self.assertEqual([message["role"] for message in visible_history[-2:]], ["assistant", "user"])
        self.assertIn("yeniden başlatayım mı?", visible_history[-2]["content"])
        self.assertEqual(visible_history[-1]["content"], "Evet")

    def test_budgeted_prompt_messages_do_not_anchor_arbitrary_single_word_new_request(self):
        canonical_messages = normalize_chat_messages(
            [
                {"id": 1, "position": 1, "role": "user", "content": "Docker kurulumu nasıl yapılır?"},
                {"id": 2, "position": 2, "role": "assistant", "content": "Docker için apt üzerinden kurulum yapabilirsiniz."},
                {"id": 3, "position": 3, "role": "user", "content": "Python"},
            ]
        )
        settings = {"user_preferences": "", "scratchpad": ""}

        with patch("routes.chat._select_prefix_prompt_window", return_value=[]), patch(
            "routes.chat.get_prompt_max_input_tokens", return_value=6000
        ), patch("routes.chat.get_prompt_response_token_reserve", return_value=1000), patch(
            "routes.chat.get_prompt_recent_history_max_tokens", return_value=8
        ), patch("routes.chat.get_prompt_summary_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_rag_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_tool_trace_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_tool_memory_max_tokens", return_value=0
        ), patch("routes.chat.get_clarification_max_questions", return_value=5):
            api_messages, _, stats, _ = _build_budgeted_prompt_messages(
                canonical_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=None,
            )

        visible_history = [message for message in api_messages if message["role"] in {"assistant", "user"}]

        self.assertEqual([entry["id"] for entry in stats["recent_selection_trace"]], [3])
        self.assertEqual([entry["id"] for entry in stats["prompt_history_trace"]], [3])
        self.assertEqual(stats["continuity_guard_status"], "not_needed")
        self.assertIsNone(stats["continuity_guard_anchor"])
        self.assertEqual([message["content"] for message in visible_history], ["Python"])

    def test_budgeted_prompt_messages_reserve_rag_budget_for_entropy_hybrid(self):
        canonical_messages = normalize_chat_messages(
            [
                {"id": 1, "position": 1, "role": "user", "content": "Initial context"},
                {"id": 2, "position": 2, "role": "assistant", "content": "filler " * 120},
                {"id": 3, "position": 3, "role": "user", "content": "Need the exact API endpoint again"},
            ]
        )
        settings = {
            "user_preferences": "",
            "scratchpad": "",
            "context_selection_strategy": "entropy_rag_hybrid",
            "entropy_profile": "balanced",
            "entropy_rag_budget_ratio": "40",
            "entropy_protect_code_blocks": "true",
            "entropy_protect_tool_results": "true",
            "entropy_reference_boost": "true",
        }
        retrieved_context = {
            "query": "api endpoint",
            "count": 1,
            "matches": [{"source_name": "docs", "text": "POST /api/settings updates configuration.", "similarity": 0.92}],
        }

        with patch("routes.chat.get_prompt_max_input_tokens", return_value=6000), patch(
            "routes.chat.get_prompt_response_token_reserve", return_value=1000
        ), patch("routes.chat.get_prompt_recent_history_max_tokens", return_value=1200), patch(
            "routes.chat.get_prompt_summary_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_rag_max_tokens", return_value=800), patch(
            "routes.chat.get_prompt_tool_trace_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_tool_memory_max_tokens", return_value=0), patch(
            "routes.chat.get_clarification_max_questions", return_value=5
        ):
            _, _, stats, _ = _build_budgeted_prompt_messages(
                canonical_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=retrieved_context,
                tool_memory_context=None,
            )

        self.assertEqual(stats["context_selection_strategy"], "entropy_rag_hybrid")
        self.assertEqual(stats["entropy_profile"], "balanced")
        self.assertGreater(stats["rag_budget_reserve"], 0)
        self.assertGreater(stats["rag_tokens"], 0)

    def test_summary_source_selection_uses_expanded_prompt_budget(self):
        canonical_messages = [
            {"id": 1, "position": 1, "role": "user", "content": "Kickoff"},
            {
                "id": 2,
                "position": 2,
                "role": "assistant",
                "content": "Short reply",
                "metadata": {
                    "tool_results": [
                        {
                            "tool_name": "fetch_url",
                            "summary": "Important result " * 60,
                            "content": "Raw payload " * 300,
                        }
                    ]
                },
            },
        ]

        selected = _select_summary_source_messages_by_token_budget(
            canonical_messages,
            canonical_messages,
            target_tokens=240,
            user_preferences="",
        )

        self.assertEqual([message["role"] for message in selected], ["user"])
        prompt_messages = build_summary_prompt_messages(selected, "")
        self.assertLessEqual(_estimate_prompt_tokens(prompt_messages), 400)

    def test_chat_summary_status_reports_detailed_failure_stage(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["context"] * 120)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "auto",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(12):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Seed {index + 1} {dense_message}", None),
                )

        failing_summary = {
            "content": "",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": ["This model's maximum context length is 131072 tokens. However, you requested 132465 tokens."],
        }
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Live answer"},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.collect_agent_response", return_value=failing_summary), patch(
            "routes.chat.run_agent_stream", return_value=fake_events
        ), patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": f"Latest {dense_message}",
                    "messages": [{"role": "user", "content": f"Latest {dense_message}"}],
                },
            )
            events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]

        self.assertEqual(response.status_code, 200)
        status_event = next((event for event in events if event["type"] == "conversation_summary_status"), None)
        self.assertIsNotNone(status_event)
        self.assertEqual(status_event["reason"], "summary_generation_failed")
        self.assertEqual(status_event["failure_stage"], "context_too_large")
        self.assertIn("maximum context length", status_event["failure_detail"])
        self.assertEqual(status_event["returned_text_length"], 0)
        self.assertEqual(status_event["summary_error_count"], 1)
        self.assertGreaterEqual(status_event["candidate_message_count"], 1)

    def test_chat_summary_rejects_error_summary_without_deleting_messages(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["history"] * 120)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "auto",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(12):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Seed {index + 1} {dense_message}", None),
                )

        failing_summary = {
            "content": FINAL_ANSWER_ERROR_TEXT,
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [FINAL_ANSWER_ERROR_TEXT],
        }
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Live answer"},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.collect_agent_response", return_value=failing_summary), patch(
            "routes.chat.run_agent_stream", return_value=fake_events
        ), patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": f"Latest {dense_message}",
                    "messages": [{"role": "user", "content": f"Latest {dense_message}"}],
                },
            )
            events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]

        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(event["type"] == "conversation_summary_applied" for event in events))

        with get_db() as conn:
            visible_rows = conn.execute(
                "SELECT role FROM messages WHERE conversation_id = ? AND deleted_at IS NULL ORDER BY position, id",
                (conversation_id,),
            ).fetchall()
            deleted_count = conn.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ? AND deleted_at IS NOT NULL",
                (conversation_id,),
            ).fetchone()["count"]

        self.assertEqual(deleted_count, 0)
        self.assertEqual([row["role"] for row in visible_rows][-2:], ["user", "assistant"])

    def test_chat_can_create_multiple_summary_passes_without_resummarizing_old_ones(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["seed"] * 120)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "auto",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(13):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Seed {index + 1} {dense_message}", None),
                )

        first_summary = {
            "content": "First summary block with enough retained detail to satisfy the minimum length validation threshold for summary generation.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        second_summary = {
            "content": "Second summary block with enough retained detail to satisfy the minimum length validation threshold for summary generation.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }

        for user_text, summary_payload, answer_text in [
            ("Turn 14", first_summary, "Answer 1"),
            ("Turn 15", second_summary, "Answer 2"),
        ]:
            fake_events = iter(
                [
                    {"type": "answer_start"},
                    {"type": "answer_delta", "text": answer_text},
                    {"type": "tool_capture", "tool_results": []},
                    {"type": "done"},
                ]
            )
            with patch("routes.chat.collect_agent_response", return_value=summary_payload), patch(
                "routes.chat.run_agent_stream", return_value=fake_events
            ), patch("routes.chat.sync_conversations_to_rag_safe"):
                response = self.client.post(
                    "/chat",
                    json={
                        "conversation_id": conversation_id,
                        "model": "deepseek-chat",
                        "user_content": f"{user_text} {dense_message}",
                        "messages": [{"role": "user", "content": f"{user_text} {dense_message}"}],
                    },
                )
                response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        summary_messages = [message for message in messages if message["role"] == "summary"]

        self.assertEqual(len(summary_messages), 1)
        self.assertEqual(
            summary_messages[0]["content"],
            "Conversation summary (generated from deleted messages):\n\nFirst summary block with enough retained detail to satisfy the minimum length validation threshold for summary generation.",
        )
        self.assertEqual(summary_messages[0]["metadata"]["covered_message_count"], 13)
        self.assertEqual(
            [message["role"] for message in messages],
            ["summary", "user", "assistant", "user", "assistant"],
        )

    def test_chat_summary_covers_tool_call_assistant_messages(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["history"] * 120)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                (conversation_id, f"First user {dense_message}", None, 1),
            )
            assistant_tool_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, tool_calls, position) VALUES (?, 'assistant', ?, ?, ?)",
                (
                    conversation_id,
                    "I will use a tool.",
                    json.dumps(
                        [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "search_web", "arguments": "{}"},
                            }
                        ]
                    ),
                    2,
                ),
            ).lastrowid
            tool_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, tool_call_id, position) VALUES (?, 'tool', ?, ?, ?)",
                (conversation_id, '{"ok": true, "headline": "Important finding"}', "call-1", 3),
            ).lastrowid
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                (conversation_id, f"Second user {dense_message}", None, 4),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'assistant', ?, ?, ?)",
                (conversation_id, f"Plain answer {dense_message}", None, 5),
            )

        fake_summary = {
            "content": "Summary block with enough retained detail to satisfy the minimum length validation threshold and preserve tool-chain coverage in metadata.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }

        with patch("routes.chat.collect_agent_response", return_value=fake_summary), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ), patch("routes.chat.get_prompt_summary_max_tokens", return_value=300):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize",
                json={"force": True},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["applied"])

        summary_message = next(message for message in payload["messages"] if message["role"] == "summary")
        self.assertEqual(summary_message["metadata"]["covered_tool_call_message_count"], 1)
        self.assertEqual(summary_message["metadata"]["covered_tool_message_count"], 1)
        self.assertIn(assistant_tool_id, summary_message["metadata"]["covered_message_ids"])
        self.assertIn(tool_id, summary_message["metadata"]["covered_message_ids"])

        with get_db() as conn:
            visible_rows = conn.execute(
                "SELECT id, role FROM messages WHERE conversation_id = ? AND deleted_at IS NULL ORDER BY position, id",
                (conversation_id,),
            ).fetchall()

        visible_pairs = [(row["id"], row["role"]) for row in visible_rows]
        self.assertNotIn((assistant_tool_id, "assistant"), visible_pairs)
        self.assertNotIn((tool_id, "tool"), visible_pairs)

    def test_manual_summarize_can_create_hierarchical_summary_from_existing_summaries(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        long_summary = " ".join(["summary-detail"] * 250)
        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'summary', ?, ?, ?)",
                (
                    conversation_id,
                    f"Conversation summary (generated from deleted messages):\n\n{long_summary}",
                    serialize_message_metadata({"is_summary": True, "summary_source": "conversation_history", "summary_level": 1}),
                    1,
                ),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'summary', ?, ?, ?)",
                (
                    conversation_id,
                    f"Conversation summary (generated from deleted messages):\n\n{long_summary}",
                    serialize_message_metadata({"is_summary": True, "summary_source": "conversation_history", "summary_level": 1}),
                    2,
                ),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'summary', ?, ?, ?)",
                (
                    conversation_id,
                    "Conversation summary (generated from deleted messages):\n\nRecent compact summary.",
                    serialize_message_metadata({"is_summary": True, "summary_source": "conversation_history", "summary_level": 1}),
                    3,
                ),
            )

        fake_summary = {
            "content": json.dumps(
                {
                    "facts": ["Older summary facts were merged."],
                    "decisions": ["A hierarchical summary replaced older summaries."],
                    "open_issues": [],
                    "entities": [],
                    "tool_outcomes": [],
                },
                ensure_ascii=False,
            ),
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }

        with patch("routes.chat.collect_agent_response", return_value=fake_summary), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ), patch("routes.chat.get_prompt_summary_max_tokens", return_value=300):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize",
                json={"force": True},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["applied"])
        summary_messages = [message for message in payload["messages"] if message["role"] == "summary"]
        self.assertEqual(len(summary_messages), 2)
        hierarchical_summary = next(message for message in summary_messages if message["metadata"]["summary_level"] == 2)
        self.assertEqual(hierarchical_summary["metadata"]["summary_source"], "summary_history")

    def test_run_agent_stream_reuses_cross_turn_fetch_url_memory(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/page"}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Final answer from cached fetch."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=6, total_tokens=10)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.get_exact_tool_memory_match",
            return_value={
                "content": "URL: https://example.com/page\n\nTitle: Example\n\nReused page content.",
                "summary": "Page content extracted: Example",
            },
        ), patch("agent.fetch_url_tool") as mocked_fetch:
            events = list(run_agent_stream([{"role": "user", "content": "Fetch it again"}], "deepseek-chat", 2, ["fetch_url"]))

        mocked_fetch.assert_not_called()
        tool_result_event = next(event for event in events if event["type"] == "tool_result")
        self.assertTrue(tool_result_event["cached"])
        self.assertIn("Page content extracted", tool_result_event["summary"])

    def test_chat_summary_mode_never_skips_summary_even_above_token_threshold(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["never"] * 120)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(12):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Seed {index + 1} {dense_message}", None),
                )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Answer without summary"},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.collect_agent_response") as mocked_summary, patch(
            "routes.chat.run_agent_stream", return_value=fake_events
        ), patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": f"Latest {dense_message}",
                    "messages": [{"role": "user", "content": f"Latest {dense_message}"}],
                },
            )
            events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]

        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(event["type"] == "conversation_summary_applied" for event in events))
        mocked_summary.assert_not_called()

        conversation_response = self.client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(conversation_response.status_code, 200)
        visible_messages = conversation_response.get_json()["messages"]
        self.assertFalse(any(message["role"] == "summary" for message in visible_messages))

    def test_run_agent_stream_blocks_tool_json_after_max_steps(self):
        responses = [
            iter(
                [
                    self._stream_chunk(reasoning="Need web data."),
                    self._tool_call_chunk("search_web", {"queries": ["x"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(reasoning="Still trying to call a tool."),
                    self._tool_call_chunk("search_web", {"queries": ["y"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.search_web_tool",
            return_value=[{"title": "Test", "url": "https://example.com", "snippet": "Snippet"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 1, ["search_web"]))

        self.assertIn(
            {
                "type": "tool_error",
                "step": 1,
                "tool": "agent",
                "error": "Tool limit reached before the model produced a final answer.",
            },
            events,
        )
        self.assertIn({"type": "answer_delta", "text": FINAL_ANSWER_ERROR_TEXT}, events)
        leaked_json = [event for event in events if event["type"] == "answer_delta" and "tool_calls" in event["text"]]
        self.assertEqual(leaked_json, [])

    def test_final_answer_phase_dsml_tool_call_does_not_leak_to_user(self):
        dsml_in_final = (
            "Tamam.\n"
            "<｜DSML｜function_calls>\n"
            "<｜DSML｜invoke name=\"append_scratchpad\">\n"
            "<｜DSML｜parameter name=\"note\" string=\"true\">some note</｜DSML｜parameter>\n"
            "</｜DSML｜invoke>\n"
            "</｜DSML｜function_calls>"
        )
        responses = [
            iter(
                [
                    self._tool_call_chunk("search_web", {"queries": ["x"]}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content=dsml_in_final),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)),
                ]
            ),
        ]

        with patch("agent.client.chat.completions.create", side_effect=responses), patch(
            "agent.search_web_tool",
            return_value=[{"title": "T", "url": "https://example.com", "snippet": "S"}],
        ):
            events = list(run_agent_stream([{"role": "user", "content": "Test"}], "deepseek-chat", 1, ["search_web", "append_scratchpad"]))

        answer_deltas = [event["text"] for event in events if event["type"] == "answer_delta"]
        full_answer = "".join(answer_deltas)
        self.assertNotIn("DSML", full_answer)
        self.assertNotIn("function_calls", full_answer)
        self.assertNotIn("append_scratchpad", full_answer)
        self.assertIn("Tamam.", full_answer)
        tool_limit_errors = [
            event for event in events
            if event["type"] == "tool_error" and event["error"] == "Tool limit reached before the model produced a final answer."
        ]
        self.assertEqual(tool_limit_errors, [])

    def test_generate_title_updates_conversation(self):
        conversation_id = self._create_conversation(title="Untitled")
        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                (conversation_id, "Generate a title", None),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'assistant', ?, ?)",
                (conversation_id, "Certainly", None),
            )

        fake_result = {
            "content": "Updated Title",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        with patch("routes.chat.collect_agent_response", return_value=fake_result):
            response = self.client.post(f"/api/conversations/{conversation_id}/generate-title")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["title"], "Updated Title")

        with get_db() as conn:
            row = conn.execute("SELECT title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        self.assertEqual(row["title"], "Updated Title")

    def test_generate_title_falls_back_to_new_chat_for_noisy_output(self):
        conversation_id = self._create_conversation(title="Untitled")
        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                (conversation_id, "Need a short title", None),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'assistant', ?, ?)",
                (conversation_id, "Sure, here is the answer", None),
            )

        fake_result = {
            "content": "**Tamamlandı!** 🚀 Canvas'a bakıp detayları ekleyebilirim.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        with patch("routes.chat.collect_agent_response", return_value=fake_result):
            response = self.client.post(f"/api/conversations/{conversation_id}/generate-title")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["title"], "New Chat")

        with get_db() as conn:
            row = conn.execute("SELECT title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        self.assertEqual(row["title"], "New Chat")

    def test_generate_title_rejects_generic_announcement_and_uses_source_fallback(self):
        conversation_id = self._create_conversation(title="Untitled")
        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                (conversation_id, "python list sorting", None),
            )

        fake_result = {
            "content": "Sure, here is a better title",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        with patch("routes.chat.collect_agent_response", return_value=fake_result):
            response = self.client.post(f"/api/conversations/{conversation_id}/generate-title")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["title"], "Python List Sorting")

    def test_generate_title_uses_source_fallback_when_model_errors(self):
        conversation_id = self._create_conversation(title="Untitled")
        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                (conversation_id, "python list sorting", None),
            )

        with patch("routes.chat.collect_agent_response", side_effect=RuntimeError("model unavailable")):
            response = self.client.post(f"/api/conversations/{conversation_id}/generate-title")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["title"], "Python List Sorting")

        with get_db() as conn:
            row = conn.execute("SELECT title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        self.assertEqual(row["title"], "Python List Sorting")

    def test_generate_title_uses_minimal_prompt_without_runtime_context_or_tools(self):
        """Root-cause regression test: generate_title must NOT inject runtime context or tools."""
        conversation_id = self._create_conversation(title="Untitled")
        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                (conversation_id, "How do I sort a list?", None),
            )

        fake_result = {
            "content": "Sorting a List",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        with patch("routes.chat.collect_agent_response", return_value=fake_result) as mocked_collect:
            self.client.post(f"/api/conversations/{conversation_id}/generate-title")

        mocked_collect.assert_called_once()
        args, _kwargs = mocked_collect.call_args
        prompt_messages, _model, max_steps, enabled_tool_names = args

        # Exactly two messages: system directive + user content — no runtime system context
        self.assertEqual(len(prompt_messages), 2)
        self.assertEqual(prompt_messages[0]["role"], "system")
        self.assertEqual(prompt_messages[1]["role"], "user")

        system_content = prompt_messages[0]["content"]
        self.assertNotIn("helpful AI assistant", system_content)
        self.assertNotIn("Available Tools", system_content)
        self.assertIn("compact conversation title", system_content)
        self.assertIn("noun phrase or short topic label", system_content)

        # Must use exactly 1 step and zero tools — prevents multi-turn tool calls
        self.assertEqual(max_steps, 1)
        self.assertEqual(enabled_tool_names, [])

    def test_get_unsummarized_visible_messages_skip_first_and_last(self):
        from db import get_unsummarized_visible_messages

        messages = [
            {"id": 1, "position": 1, "role": "user", "content": "First"},
            {"id": 2, "position": 2, "role": "assistant", "content": "Second"},
            {"id": 3, "position": 3, "role": "user", "content": "Third"},
            {"id": 4, "position": 4, "role": "assistant", "content": "Fourth"},
            {"id": 5, "position": 5, "role": "user", "content": "Fifth"},
        ]
        result = get_unsummarized_visible_messages(messages, skip_first=1, skip_last=1)
        self.assertEqual([m["id"] for m in result], [2, 3, 4])

        result_all = get_unsummarized_visible_messages(messages, skip_first=0, skip_last=0)
        self.assertEqual([m["id"] for m in result_all], [1, 2, 3, 4, 5])

        result_over = get_unsummarized_visible_messages(messages, skip_first=3, skip_last=3)
        self.assertEqual(result_over, [])

        result_with_limit = get_unsummarized_visible_messages(messages, skip_first=1, skip_last=1, limit=2)
        self.assertEqual([m["id"] for m in result_with_limit], [2, 3])

    def test_get_unsummarized_visible_messages_ignores_hidden_tool_call_assistant_entries(self):
        from db import get_unsummarized_visible_messages

        messages = [
            {"id": 1, "position": 1, "role": "user", "content": "First", "tool_calls": []},
            {
                "id": 2,
                "position": 2,
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "function": {"name": "search_web", "arguments": "{}"}}],
            },
            {"id": 3, "position": 3, "role": "assistant", "content": "Visible assistant", "tool_calls": []},
            {"id": 4, "position": 4, "role": "user", "content": "Fourth", "tool_calls": []},
            {"id": 5, "position": 5, "role": "assistant", "content": "Fifth", "tool_calls": []},
        ]

        result = get_unsummarized_visible_messages(messages, skip_first=1, skip_last=1)
        self.assertEqual([message["id"] for message in result], [3, 4])

    def test_chat_preflight_summary_respects_mode_never(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["preflight"] * 900)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(8):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Seed {index + 1} {dense_message}", None),
                )

        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Main answer without preflight summary."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.collect_agent_response") as mocked_collect, patch(
            "routes.chat.run_agent_stream", return_value=fake_events
        ), patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": f"Latest {dense_message}",
                    "messages": [{"role": "user", "content": f"Latest {dense_message}"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        summary_status = next((event for event in events if event["type"] == "conversation_summary_status"), None)
        self.assertIsNotNone(summary_status)
        self.assertEqual(summary_status["reason"], "mode_never")
        mocked_collect.assert_not_called()

    def test_manual_summarize_endpoint_returns_404_for_missing_conversation(self):
        response = self.client.post(
            "/api/conversations/999999/summarize",
            json={"force": True},
        )
        self.assertEqual(response.status_code, 404)

    def test_manual_summarize_endpoint_can_force_summarize(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["manual"] * 120)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(12):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Seed {index + 1} {dense_message}", None),
                )

        fake_summary = {
            "content": "Manual summary with enough retained detail to satisfy the minimum length validation threshold for summary generation results.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        with patch("routes.chat.collect_agent_response", return_value=fake_summary), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize",
                json={"force": True},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["applied"])
        self.assertGreater(data["covered_message_count"], 0)

    def test_manual_summarize_endpoint_respects_requested_message_count(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "1",
                "summary_skip_last": "1",
            }
        )

        with get_db() as conn:
            for index in range(6):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                    (conversation_id, f"Message {index + 1}", None, index + 1),
                )

        fake_summary = {
            "content": "Manual summary with enough retained detail to satisfy the minimum length validation threshold and preserve the requested message window.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }

        with patch("routes.chat.collect_agent_response", return_value=fake_summary), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize",
                json={"force": True, "message_count": 2},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["applied"])
        self.assertEqual(data["requested_message_count"], 2)
        self.assertEqual(data["eligible_message_count"], 4)
        self.assertEqual(data["covered_message_count"], 2)

        summary_message = next(message for message in data["messages"] if message["role"] == "summary")
        self.assertEqual(summary_message["metadata"]["covered_message_ids"], [2, 3])

    def test_manual_summarize_endpoint_can_preserve_outer_messages_when_summarizing_all(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "2",
                "summary_skip_last": "2",
            }
        )

        with get_db() as conn:
            for index in range(72):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                    (conversation_id, f"Message {index + 1}", None, index + 1),
                )

        fake_summary = {
            "content": "All-message summary that still preserves the first and last conversation turns while compressing the middle.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }

        with patch(
            "routes.chat._select_summary_source_messages_by_token_budget",
            side_effect=AssertionError("all-messages mode should not use token-budgeted source selection"),
        ), patch("routes.chat.collect_agent_response", return_value=fake_summary), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize",
                json={"force": True, "summarize_all_messages": True},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["applied"])
        self.assertIsNone(data["requested_message_count"])
        self.assertEqual(data["eligible_message_count"], 68)
        self.assertEqual(data["covered_message_count"], 68)

        summary_message = next(message for message in data["messages"] if message["role"] == "summary")
        self.assertEqual(summary_message["metadata"]["covered_message_count"], 68)
        self.assertEqual(summary_message["metadata"]["covers_from_position"], 3)
        self.assertEqual(summary_message["metadata"]["covers_to_position"], 70)
        self.assertTrue(summary_message["metadata"].get("covered_ids_truncated"))

    def test_manual_summarize_preview_endpoint_returns_selected_candidates_without_writing(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "1",
                "summary_skip_last": "1",
            }
        )

        with get_db() as conn:
            for index in range(6):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                    (conversation_id, f"Message {index + 1}", None, index + 1),
                )

        with patch("routes.chat.collect_agent_response") as mocked_collect:
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize/preview",
                json={"force": True, "message_count": 2},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["preview"])
        self.assertFalse(data["applied"])
        self.assertEqual(data["reason"], "preview")
        self.assertEqual(data["candidate_message_count"], 2)
        self.assertEqual(data["eligible_message_count"], 4)
        self.assertEqual(data["requested_message_count"], 2)
        self.assertGreater(data["estimated_source_tokens"], 0)
        self.assertGreater(data["estimated_prompt_tokens"], 0)
        self.assertEqual(data["prompt_message_count"], 2)
        self.assertEqual([entry["id"] for entry in data["messages_preview"]], [2, 3])
        mocked_collect.assert_not_called()

    def test_manual_summarize_endpoint_honors_include_message_ids(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(6):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                    (conversation_id, f"Message {index + 1}", None, index + 1),
                )

        fake_summary = {
            "content": "Selected-message summary with enough retained detail to satisfy the summary validation threshold and preserve chronology.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }

        with patch("routes.chat.collect_agent_response", return_value=fake_summary), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize",
                json={"force": True, "include_message_ids": [2, 4]},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["applied"])
        self.assertEqual(data["requested_message_count"], 2)
        self.assertEqual(data["covered_message_count"], 2)

        summary_message = next(message for message in data["messages"] if message["role"] == "summary")
        self.assertEqual(summary_message["metadata"]["covered_message_ids"], [2, 4])

    def test_manual_summarize_endpoint_threads_summary_preferences_into_prompt(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["manual"] * 120)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(12):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Seed {index + 1} {dense_message}", None),
                )

        fake_summary = {
            "content": "Manual summary with enough retained detail to satisfy the minimum length validation threshold for summary generation results.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        with patch("routes.chat.collect_agent_response", return_value=fake_summary) as mocked_collect, patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize",
                json={
                    "force": True,
                    "summary_focus": "action items and decisions",
                    "summary_detail_level": "comprehensive",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["applied"])
        prompt_messages = mocked_collect.call_args.args[0]
        prompt_text = "\n".join(str(message.get("content") or "") for message in prompt_messages)
        self.assertIn("comprehensive summary", prompt_text)
        self.assertIn("Current continuation focus:", prompt_text)
        self.assertIn("action items and decisions", prompt_text)
        self.assertIn("Preserve continuity carefully", prompt_text)

    def test_manual_summarize_endpoint_honors_false_force_strings(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            conn.execute(

                "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                (conversation_id, "Seed message", None),
            )

        with patch("routes.chat.collect_agent_response") as mocked_collect:
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize",
                json={"force": "false"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["applied"])
        self.assertEqual(data["reason"], "mode_never")
        mocked_collect.assert_not_called()

    def test_manual_summarize_preserves_edges_and_inserts_summary_at_first_covered_slot(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "2",
                "summary_skip_last": "2",
            }
        )

        with get_db() as conn:
            for index in range(8):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Message {index + 1}", None),
                )

        fake_summary = {
            "content": "Summary block with enough retained detail to satisfy the minimum length validation threshold and preserve chronology across the covered messages.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }

        with patch("routes.chat.collect_agent_response", return_value=fake_summary), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize",
                json={"force": True},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["applied"])
        self.assertEqual(data["covered_message_count"], 4)

        messages = data["messages"]
        self.assertEqual([message["content"] for message in messages if message["role"] == "user"], ["Message 1", "Message 2", "Message 7", "Message 8"])
        self.assertEqual([message["role"] for message in messages], ["user", "user", "summary", "user", "user"])

        summary_message = next(message for message in messages if message["role"] == "summary")
        self.assertEqual(summary_message["metadata"]["covered_message_ids"], [3, 4, 5, 6])
        self.assertEqual(summary_message["metadata"]["summary_insert_strategy"], "replace_first_covered_message_preserve_positions")
        self.assertEqual(summary_message["position"], 3)

    def test_visible_token_count_ignores_hidden_tool_messages_and_tool_call_assistants(self):
        visible_messages = [
            {"role": "user", "content": "Visible user text"},
            {"role": "assistant", "content": "Visible assistant text"},
            {"role": "tool", "content": "Hidden tool result"},
            {"role": "summary", "content": "Visible summary text"},
        ]
        mixed_messages = [
            {"role": "user", "content": "Visible user text"},
            {"role": "assistant", "content": "Visible assistant text"},
            {
                "role": "assistant",
                "content": "Hidden assistant tool call",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search_web", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "content": "Hidden tool result"},
            {"role": "summary", "content": "Visible summary text"},
        ]

        self.assertEqual(count_visible_message_tokens(mixed_messages), count_visible_message_tokens(visible_messages))

    def test_visible_token_count_includes_context_injection_metadata(self):
        baseline_messages = [
            {"role": "user", "content": "Visible user text"},
            {"role": "assistant", "content": "Visible assistant text"},
        ]
        injected_messages = [
            {
                "role": "user",
                "content": "Visible user text",
                "metadata": {"context_injection": "## Tool Memory\nSaved result context for this turn."},
            },
            {"role": "assistant", "content": "Visible assistant text"},
        ]

        self.assertGreater(
            count_visible_message_tokens(injected_messages),
            count_visible_message_tokens(baseline_messages),
        )

    def test_visible_token_count_can_exclude_context_injection_metadata(self):
        baseline_messages = [
            {"role": "user", "content": "Visible user text"},
            {"role": "assistant", "content": "Visible assistant text"},
        ]
        injected_messages = [
            {
                "role": "user",
                "content": "Visible user text",
                "metadata": {"context_injection": "## Tool Memory\nSaved result context for this turn."},
            },
            {"role": "assistant", "content": "Visible assistant text"},
        ]

        self.assertEqual(
            count_visible_message_tokens(injected_messages, include_context_injections=False),
            count_visible_message_tokens(baseline_messages, include_context_injections=False),
        )

    def test_budgeted_prompt_messages_report_request_token_overhead_for_visual_documents(self):
        canonical_messages = normalize_chat_messages(
            [
                {
                    "id": 1,
                    "position": 1,
                    "role": "user",
                    "content": "Please inspect the uploaded PDF.",
                    "metadata": {
                        "attachments": [
                            {
                                "kind": "document",
                                "file_id": "file-1",
                                "file_name": "spec.pdf",
                                "submission_mode": "visual",
                                "visual_page_image_ids": ["img-1"],
                                "visual_page_count": 1,
                            }
                        ]
                    },
                }
            ]
        )
        settings = {"user_preferences": "", "scratchpad": ""}

        with patch("messages.read_image_asset_bytes", return_value=({"mime_type": "image/jpeg"}, b"x" * 4096)), patch(
            "routes.chat.get_prompt_max_input_tokens", return_value=6000
        ), patch("routes.chat.get_prompt_response_token_reserve", return_value=1000), patch(
            "routes.chat.get_prompt_recent_history_max_tokens", return_value=1200
        ), patch("routes.chat.get_prompt_summary_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_rag_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_tool_trace_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_tool_memory_max_tokens", return_value=0
        ), patch("routes.chat.get_clarification_max_questions", return_value=5):
            _api_messages, _request_api_messages, stats, _current_context_injection = _build_budgeted_prompt_messages(
                canonical_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=None,
            )

        self.assertIn("request_estimated_total_tokens", stats)
        self.assertIn("request_token_overhead", stats)
        self.assertGreater(stats["request_estimated_total_tokens"], stats["estimated_total_tokens"])
        self.assertGreater(stats["request_token_overhead"], 0)

    def test_budgeted_prompt_messages_use_separate_tool_trace_budget(self):
        canonical_messages = [
            {
                "id": 1,
                "position": 1,
                "role": "assistant",
                "content": "Finished the previous step.",
                "metadata": {
                    "tool_trace": [
                        {
                            "tool_name": "search_web",
                            "state": "done",
                            "preview": "query",
                            "summary": "trace detail " * 80,
                        }
                    ]
                },
            },
            {"id": 2, "position": 2, "role": "user", "content": "What changed?"},
        ]
        settings = {"user_preferences": "", "scratchpad": ""}
        tool_memory_context = "## Tool Memory\n" + ("memory detail " * 160)

        with patch("routes.chat.get_prompt_max_input_tokens", return_value=6000), patch(
            "routes.chat.get_prompt_response_token_reserve", return_value=1000
        ), patch("routes.chat.get_prompt_recent_history_max_tokens", return_value=1000), patch(
            "routes.chat.get_prompt_summary_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_rag_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_tool_trace_max_tokens", return_value=80
        ), patch("routes.chat.get_prompt_tool_memory_max_tokens", return_value=240), patch(
            "routes.chat.get_clarification_max_questions", return_value=5
        ):
            _, _, stats, _ = _build_budgeted_prompt_messages(
                canonical_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=tool_memory_context,
            )

        self.assertGreater(stats["tool_trace_tokens"], 0)
        self.assertLessEqual(stats["tool_trace_tokens"], 80)
        self.assertGreater(stats["tool_memory_tokens"], 0)
        self.assertLessEqual(stats["tool_memory_tokens"], 240)
        self.assertGreater(stats["tool_memory_tokens"], stats["tool_trace_tokens"])

    def test_budgeted_prompt_messages_base_system_tokens_ignore_tool_trace_payload(self):
        traced_messages = [
            {
                "id": 1,
                "position": 1,
                "role": "assistant",
                "content": "Finished the previous step.",
                "metadata": {
                    "tool_trace": [
                        {
                            "tool_name": "search_web",
                            "state": "done",
                            "preview": "query",
                            "summary": "trace detail " * 120,
                        }
                    ]
                },
            },
            {"id": 2, "position": 2, "role": "user", "content": "What changed?"},
        ]
        untraced_messages = [
            {"id": 1, "position": 1, "role": "assistant", "content": "Finished the previous step."},
            {"id": 2, "position": 2, "role": "user", "content": "What changed?"},
        ]
        settings = {"user_preferences": "", "scratchpad": ""}

        with patch("routes.chat.get_prompt_max_input_tokens", return_value=6000), patch(
            "routes.chat.get_prompt_response_token_reserve", return_value=1000
        ), patch("routes.chat.get_prompt_recent_history_max_tokens", return_value=1000), patch(
            "routes.chat.get_prompt_summary_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_rag_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_tool_trace_max_tokens", return_value=120
        ), patch("routes.chat.get_prompt_tool_memory_max_tokens", return_value=0), patch(
            "routes.chat.get_clarification_max_questions", return_value=5
        ):
            traced_result = _build_budgeted_prompt_messages(
                traced_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=None,
            )
            untraced_result = _build_budgeted_prompt_messages(
                untraced_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=None,
            )

        traced_stats = traced_result[2]
        untraced_stats = untraced_result[2]
        self.assertEqual(traced_stats["base_system_tokens"], untraced_stats["base_system_tokens"])
        self.assertGreater(traced_stats["tool_trace_tokens"], 0)

    def test_budgeted_prompt_messages_move_dynamic_state_to_bottom_injection(self):
        canonical_messages = normalize_chat_messages(
            [
                {"id": 1, "position": 1, "role": "user", "content": "Hello"},
            ]
        )
        settings = {"user_preferences": "", "scratchpad": ""}
        conversation_memory = [
            {
                "id": 7,
                "entry_type": "task_context",
                "key": "Goal",
                "value": "Keep stable rules cached.",
                "created_at": "2026-04-08 10:23:00",
            }
        ]

        with patch("routes.chat.build_user_profile_system_context", return_value="The user prefers concise answers."), patch(
            "routes.chat.get_all_scratchpad_sections", return_value={"notes": "Persistent note"}
        ), patch("routes.chat.get_prompt_max_input_tokens", return_value=6000), patch(
            "routes.chat.get_prompt_response_token_reserve", return_value=1000
        ), patch("routes.chat.get_prompt_recent_history_max_tokens", return_value=1000), patch(
            "routes.chat.get_prompt_summary_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_rag_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_tool_trace_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_tool_memory_max_tokens", return_value=0), patch(
            "routes.chat.get_clarification_max_questions", return_value=5
        ):
            api_messages, _, _, _ = _build_budgeted_prompt_messages(
                canonical_messages,
                settings,
                active_tool_names=["save_to_conversation_memory"],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=None,
                conversation_memory=conversation_memory,
            )

        self.assertEqual([message["role"] for message in api_messages], ["system", "system", "user"])
        static_content = api_messages[0]["content"]
        dynamic_content = api_messages[1]["content"]
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

    def test_budgeted_prompt_messages_keep_prefix_anchor_before_summaries(self):
        canonical_messages = normalize_chat_messages(
            [
                {
                    "id": 1,
                    "position": 1,
                    "role": "user",
                    "content": "First question about a long-lived topic.",
                    "metadata": parse_message_metadata(
                        serialize_message_metadata({"context_injection": "## Current Date and Time\n- Time: 21:35"})
                    ),
                },
                {"id": 2, "position": 2, "role": "assistant", "content": "First answer."},
                {"id": 3, "position": 3, "role": "summary", "content": "Earlier compressed context."},
                {"id": 4, "position": 4, "role": "user", "content": "Latest question that should stay near the end."},
            ]
        )
        settings = {"user_preferences": "", "scratchpad": ""}

        with patch("routes.chat.get_prompt_max_input_tokens", return_value=6000), patch(
            "routes.chat.get_prompt_response_token_reserve", return_value=1000
        ), patch("routes.chat.get_prompt_recent_history_max_tokens", return_value=1000), patch(
            "routes.chat.get_prompt_summary_max_tokens", return_value=400
        ), patch("routes.chat.get_prompt_rag_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_tool_trace_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_tool_memory_max_tokens", return_value=0), patch(
            "routes.chat.get_clarification_max_questions", return_value=5
        ):
            api_messages, _, stats, _ = _build_budgeted_prompt_messages(
                canonical_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=None,
            )

        first_user_index = next(index for index, message in enumerate(api_messages) if message["role"] == "user")
        first_summary_index = next(
            index
            for index, message in enumerate(api_messages)
            if message["role"] == "assistant" and "Conversation summary" in message["content"]
        )
        self.assertLess(first_user_index, first_summary_index)
        self.assertGreaterEqual(stats["prefix_message_count"], 1)

    def test_budgeted_prompt_messages_bias_prefix_for_cache_friendly_models(self):
        canonical_messages = normalize_chat_messages(
            [
                {"id": 1, "position": 1, "role": "user", "content": "Stable project brief. " * 160},
                {"id": 2, "position": 2, "role": "assistant", "content": "Acknowledged. " * 120},
                {"id": 3, "position": 3, "role": "user", "content": "Stable requirements list. " * 150},
                {"id": 4, "position": 4, "role": "assistant", "content": "Captured. " * 120},
                {"id": 5, "position": 5, "role": "user", "content": "Latest question with some new variation."},
            ]
        )
        settings = {"user_preferences": "", "scratchpad": ""}

        with patch("routes.chat.get_prompt_max_input_tokens", return_value=8000), patch(
            "routes.chat.get_prompt_response_token_reserve", return_value=1000
        ), patch("routes.chat.get_prompt_recent_history_max_tokens", return_value=900), patch(
            "routes.chat.get_prompt_summary_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_rag_max_tokens", return_value=0), patch(
            "routes.chat.get_prompt_tool_trace_max_tokens", return_value=0
        ), patch("routes.chat.get_prompt_tool_memory_max_tokens", return_value=0), patch(
            "routes.chat.get_clarification_max_questions", return_value=5
        ):
            _, _, uncached_stats, _ = _build_budgeted_prompt_messages(
                canonical_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=None,
            )
            _, _, cached_stats, _ = _build_budgeted_prompt_messages(
                canonical_messages,
                settings,
                active_tool_names=[],
                clarification_response=None,
                all_clarification_rounds=None,
                retrieved_context=None,
                tool_memory_context=None,
                model_id="deepseek-chat",
            )

        self.assertFalse(uncached_stats["cache_friendly_prefix"])
        self.assertTrue(cached_stats["cache_friendly_prefix"])
        self.assertGreaterEqual(cached_stats["prefix_tokens"], uncached_stats["prefix_tokens"])

    def test_undo_summary_restores_messages_in_original_order(self):
        conversation_id = self._create_conversation()
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "never",
                "chat_summary_trigger_token_count": "1000",
                "summary_skip_first": "2",
                "summary_skip_last": "2",
            }
        )

        with get_db() as conn:
            for index in range(8):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Message {index + 1}", None),
                )

        fake_summary = {
            "content": "Summary block with enough retained detail to satisfy the minimum length validation threshold and allow undo restoration.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }

        with patch("routes.chat.collect_agent_response", return_value=fake_summary), patch(
            "routes.chat.sync_conversations_to_rag_safe"
        ):
            summarize_response = self.client.post(
                f"/api/conversations/{conversation_id}/summarize",
                json={"force": True},
            )

        summary_message_id = summarize_response.get_json()["summary_message_id"]
        with patch("routes.chat.sync_conversations_to_rag_safe"):
            undo_response = self.client.post(
                f"/api/conversations/{conversation_id}/summaries/{summary_message_id}/undo"
            )

        self.assertEqual(undo_response.status_code, 200)
        data = undo_response.get_json()
        self.assertTrue(data["reverted"])
        self.assertEqual(data["restored_message_count"], 4)
        self.assertEqual([message["role"] for message in data["messages"]], ["user"] * 8)
        self.assertEqual([message["content"] for message in data["messages"]], [f"Message {index}" for index in range(1, 9)])
        self.assertEqual([message["position"] for message in data["messages"]], list(range(1, 9)))

    def test_undo_summary_restores_legacy_summary_layout(self):
        conversation_id = self._create_conversation()

        with get_db() as conn:
            inserted_ids = []
            for index in range(8):
                inserted_ids.append(
                    conn.execute(
                        "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                        (conversation_id, f"Message {index + 1}", None, index + 1),
                    ).lastrowid
                )

            deleted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            conn.execute(
                "UPDATE messages SET deleted_at = ? WHERE conversation_id = ? AND id IN (?, ?, ?, ?)",
                (deleted_at, conversation_id, inserted_ids[2], inserted_ids[3], inserted_ids[4], inserted_ids[5]),
            )
            conn.execute(
                "UPDATE messages SET position = 4 WHERE id = ?",
                (inserted_ids[6],),
            )
            conn.execute(
                "UPDATE messages SET position = 5 WHERE id = ?",
                (inserted_ids[7],),
            )
            summary_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'summary', ?, ?, 3)",
                (
                    conversation_id,
                    "Conversation summary (generated from deleted messages):\n\nLegacy summary block.",
                    serialize_message_metadata(
                        {
                            "is_summary": True,
                            "summary_source": "conversation_history",
                            "covers_from_position": 3,
                            "covers_to_position": 6,
                            "covered_message_count": 4,
                            "covered_message_ids": [inserted_ids[2], inserted_ids[3], inserted_ids[4], inserted_ids[5]],
                            "generated_at": deleted_at,
                        }
                    ),
                ),
            ).lastrowid

        with patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summaries/{summary_id}/undo"
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["reverted"])
        self.assertEqual([message["content"] for message in data["messages"]], [f"Message {index}" for index in range(1, 9)])
        self.assertEqual([message["position"] for message in data["messages"]], list(range(1, 9)))

    def test_undo_summary_restores_tool_chain_missing_from_metadata(self):
        conversation_id = self._create_conversation()

        with get_db() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                (conversation_id, "Message 1", None, 1),
            )
            assistant_tool_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, tool_calls, position) VALUES (?, 'assistant', ?, ?, ?)",
                (
                    conversation_id,
                    "Working on it.",
                    json.dumps(
                        [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "search_web", "arguments": "{}"},
                            }
                        ]
                    ),
                    2,
                ),
            ).lastrowid
            tool_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, tool_call_id, position) VALUES (?, 'tool', ?, ?, ?)",
                (conversation_id, '{"ok": true}', "call-1", 3),
            ).lastrowid
            user_two_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                (conversation_id, "Message 4", None, 4),
            ).lastrowid
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                (conversation_id, "Message 5", None, 5),
            )

            deleted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            conn.execute(
                "UPDATE messages SET deleted_at = ? WHERE conversation_id = ? AND id IN (?, ?, ?)",
                (deleted_at, conversation_id, assistant_tool_id, tool_id, user_two_id),
            )
            summary_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'summary', ?, ?, ?)",
                (
                    conversation_id,
                    "Conversation summary (generated from deleted messages):\n\nSummary block.",
                    serialize_message_metadata(
                        {
                            "is_summary": True,
                            "summary_source": "conversation_history",
                            "covers_from_position": 2,
                            "covers_to_position": 4,
                            "summary_insert_strategy": "replace_first_covered_message_preserve_positions",
                            "covered_message_count": 1,
                            "covered_message_ids": [user_two_id],
                            "generated_at": deleted_at,
                        }
                    ),
                    2,
                ),
            ).lastrowid

        with patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summaries/{summary_id}/undo"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["reverted"])
        self.assertEqual(payload["restored_message_count"], 3)
        self.assertEqual(
            [(message["role"], message.get("tool_call_id")) for message in payload["messages"]],
            [
                ("user", None),
                ("assistant", None),
                ("tool", "call-1"),
                ("user", None),
                ("user", None),
            ],
        )

    def test_undo_summary_does_not_count_older_deleted_messages_in_same_range(self):
        conversation_id = self._create_conversation()

        with get_db() as conn:
            inserted_ids = []
            for index in range(8):
                inserted_ids.append(
                    conn.execute(
                        "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'user', ?, ?, ?)",
                        (conversation_id, f"Message {index + 1}", None, index + 1),
                    ).lastrowid
                )

            older_deleted_at = "2026-04-08T10:00:00+00:00"
            current_deleted_at = "2026-04-08T11:00:00+00:00"
            conn.execute(
                "UPDATE messages SET deleted_at = ? WHERE conversation_id = ? AND id IN (?, ?)",
                (older_deleted_at, conversation_id, inserted_ids[2], inserted_ids[3]),
            )
            conn.execute(
                "UPDATE messages SET deleted_at = ? WHERE conversation_id = ? AND id IN (?, ?)",
                (current_deleted_at, conversation_id, inserted_ids[4], inserted_ids[5]),
            )
            summary_id = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, position) VALUES (?, 'summary', ?, ?, ?)",
                (
                    conversation_id,
                    "Conversation summary (generated from deleted messages):\n\nSummary block.",
                    serialize_message_metadata(
                        {
                            "is_summary": True,
                            "summary_source": "conversation_history",
                            "covers_from_position": 3,
                            "covers_to_position": 6,
                            "summary_insert_strategy": "replace_first_covered_message_preserve_positions",
                            "covered_message_count": 2,
                            "covered_message_ids": [inserted_ids[4], inserted_ids[5]],
                            "generated_at": current_deleted_at,
                        }
                    ),
                    5,
                ),
            ).lastrowid

        with patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/summaries/{summary_id}/undo"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["reverted"])
        self.assertEqual(payload["restored_message_count"], 2)
        self.assertEqual([message["position"] for message in payload["messages"]], [1, 2, 5, 6, 7, 8])

        with get_db() as conn:
            visible_ids = {
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM messages WHERE conversation_id = ? AND deleted_at IS NULL",
                    (conversation_id,),
                ).fetchall()
            }

        self.assertIn(inserted_ids[4], visible_ids)
        self.assertIn(inserted_ids[5], visible_ids)
        self.assertNotIn(inserted_ids[2], visible_ids)
        self.assertNotIn(inserted_ids[3], visible_ids)

    def test_settings_include_new_summary_params(self):
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "5",
                "active_tools": "[]",
                "summary_skip_first": "3",
                "summary_skip_last": "2",
            }
        )
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["summary_skip_first"], 3)
        self.assertEqual(data["summary_skip_last"], 2)

    def test_settings_patch_validates_new_summary_params(self):
        response = self.client.patch(
            "/api/settings",
            json={"summary_skip_first": 5, "summary_skip_last": 3},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["summary_skip_first"], 5)
        self.assertEqual(data["summary_skip_last"], 3)

    def test_settings_patch_rejects_invalid_skip_values(self):
        response = self.client.patch(
            "/api/settings",
            json={"summary_skip_first": 25},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_structured_summary_prompt_contains_sections(self):
        prompt_messages = build_summary_prompt_messages(
            [
                {"role": "user", "content": "Tell me about Python"},
                {"role": "assistant", "content": "Python is a programming language."},
            ],
            "",
        )
        system_content = prompt_messages[0]["content"]
        self.assertIn("User Goals & Intentions", system_content)
        self.assertIn("Key Facts & Information", system_content)
        self.assertIn("Decisions & Agreements", system_content)
        self.assertIn("Unresolved Questions", system_content)
        self.assertIn("Important Context", system_content)
        self.assertIn("sufficient detail", system_content)

    def test_chat_applies_preflight_summary_before_main_agent_run(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["preflight"] * 900)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "auto",
                "chat_summary_trigger_token_count": "80000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(20):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Seed {index + 1} {dense_message}", None),
                )

        fake_summary = {
            "content": "Preflight summary block with enough retained detail to satisfy the minimum length validation threshold and reduce prompt size before the main answer.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Main answer after preflight summary."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.get_prompt_preflight_summary_token_count", return_value=1000), patch(
            "routes.chat.collect_agent_response", return_value=fake_summary
        ), patch("routes.chat.run_agent_stream", return_value=fake_events), patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": f"Latest {dense_message}",
                    "messages": [{"role": "user", "content": f"Latest {dense_message}"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        summary_event = next((event for event in events if event["type"] == "conversation_summary_applied"), None)
        self.assertIsNotNone(summary_event)
        self.assertTrue(summary_event["preflight"])
        history_sync_event = next((event for event in events if event["type"] == "history_sync"), None)
        self.assertIsNotNone(history_sync_event)
        summary_messages = [message for message in history_sync_event["messages"] if message["role"] == "summary"]
        self.assertTrue(summary_messages)
        self.assertIn(SUMMARY_LABEL, summary_messages[0]["content"])

    def test_chat_preflight_summary_skips_second_summary_pass_in_same_request(self):
        conversation_id = self._create_conversation()
        dense_message = " ".join(["preflight"] * 900)
        save_app_settings(
            {
                "user_preferences": "",
                "max_steps": "1",
                "active_tools": "[]",
                "rag_auto_inject": "false",
                "chat_summary_mode": "auto",
                "chat_summary_trigger_token_count": "80000",
                "summary_skip_first": "0",
                "summary_skip_last": "0",
            }
        )

        with get_db() as conn:
            for index in range(20):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
                    (conversation_id, f"Seed {index + 1} {dense_message}", None),
                )

        fake_summary = {
            "content": "Preflight summary block with enough retained detail to satisfy the minimum length validation threshold and reduce prompt size before the main answer.",
            "reasoning_content": "",
            "usage": None,
            "tool_results": [],
            "errors": [],
        }
        fake_events = iter(
            [
                {"type": "answer_start"},
                {"type": "answer_delta", "text": "Main answer after preflight summary."},
                {"type": "tool_capture", "tool_results": []},
                {"type": "done"},
            ]
        )

        with patch("routes.chat.get_prompt_preflight_summary_token_count", return_value=1000), patch(
            "routes.chat.collect_agent_response", return_value=fake_summary
        ), patch("routes.chat.run_agent_stream", return_value=fake_events), patch(
            "routes.chat.SUMMARY_EXECUTOR.submit"
        ) as mocked_summary_submit, patch("routes.chat.sync_conversations_to_rag_safe"):
            response = self.client.post(
                "/chat",
                json={
                    "conversation_id": conversation_id,
                    "model": "deepseek-chat",
                    "user_content": f"Latest {dense_message}",
                    "messages": [{"role": "user", "content": f"Latest {dense_message}"}],
                },
            )
            response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        mocked_summary_submit.assert_not_called()

    def test_run_agent_stream_uses_compact_tool_message_content_for_followup_prompt(self):
        responses = [
            iter(
                [
                    self._tool_call_chunk("fetch_url", {"url": "https://example.com/compact"}),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8)),
                ]
            ),
            iter(
                [
                    self._stream_chunk(content="Compact answer."),
                    self._stream_chunk(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=6, total_tokens=10)),
                ]
            ),
        ]

        long_content = "\n\n".join(
            [
                "Overview block with broad context and repeated details. " * 12,
                "Evidence block with implementation details and caveats. " * 12,
                "Closing block with more raw detail that should stay out of the prompt-facing tool message. " * 12,
            ]
        )

        with patch("agent.client.chat.completions.create", side_effect=responses) as mocked_create, patch(
            "agent.fetch_url_tool",
            return_value={
                "url": "https://example.com/compact",
                "title": "Compact Example",
                "content": long_content,
                "status": 200,
                "content_format": "html",
                "cleanup_applied": True,
            },
        ):
            list(
                run_agent_stream(
                    [{"role": "user", "content": "Fetch and summarize compactly"}],
                    "deepseek-chat",
                    2,
                    ["fetch_url"],
                    fetch_url_token_threshold=50,
                )
            )

        second_call_messages = mocked_create.call_args_list[1].kwargs["messages"]
        tool_message = next(message for message in second_call_messages if message["role"] == "tool")
        self.assertIn("Title: Compact Example", tool_message["content"])
        self.assertIn("URL: https://example.com/compact", tool_message["content"])
        self.assertNotIn("raw_content", tool_message["content"])

    # ------------------------------------------------------------------
    # Clarification injection guard: stale rounds must not leak
    # ------------------------------------------------------------------

    def test_build_runtime_system_message_suppresses_clarification_rounds_on_non_clarification_turn(self):
        """When the current turn is NOT a clarification turn (clarification_response is None),
        historical all_clarification_rounds must not produce a ## Clarification Response section."""
        message = build_runtime_system_message(
            active_tool_names=["search_knowledge_base"],
            clarification_response=None,
            all_clarification_rounds=[
                {
                    "questions": [{"id": "q1", "label": "Which option?"}],
                    "answers": {"q1": {"display": "Option A"}},
                },
            ],
        )
        content = message["content"]
        self.assertNotIn("## Clarification Response", content)
        self.assertNotIn("Option A", content)

    def test_context_injection_suppresses_clarification_when_no_current_response(self):
        """build_runtime_context_injection must not include clarification data
        when clarification_response is None, even if all_clarification_rounds is populated."""
        injection = build_runtime_context_injection(
            active_tool_names=["search_web"],
            clarification_response=None,
            all_clarification_rounds=[
                {
                    "questions": [{"id": "q1", "label": "Budget?"}],
                    "answers": {"q1": {"display": "200 TL"}},
                },
            ],
        )
        self.assertNotIn("## Clarification Response", injection)
        self.assertNotIn("200 TL", injection)

    def test_context_injection_includes_clarification_when_current_response_present(self):
        """build_runtime_context_injection should include clarification data when
        the current turn carries a clarification response."""
        injection = build_runtime_context_injection(
            active_tool_names=["search_web"],
            clarification_response={
                "assistant_message_id": "5",
                "answers": {"q1": {"display": "200 TL"}},
            },
            all_clarification_rounds=[
                {
                    "questions": [{"id": "q1", "label": "Budget?"}],
                    "answers": {"q1": {"display": "200 TL"}},
                },
            ],
        )
        self.assertIn("## Clarification Response", injection)
        self.assertIn("200 TL", injection)

    # ------------------------------------------------------------------
    # save_to_conversation_memory result compactness
    # ------------------------------------------------------------------

    def test_save_to_conversation_memory_result_excludes_internal_fields(self):
        """The tool result for save_to_conversation_memory should not include
        verbose internal DB fields like id, conversation_id, message_id, or created_at."""
        from agent import _run_save_to_conversation_memory

        with self.app.app_context():
            conv_id = self._create_conversation()
            runtime_state = {
                "agent_context": {"conversation_id": conv_id, "source_message_id": None},
            }
            result, summary = _run_save_to_conversation_memory(
                {"entry_type": "tool_result", "key": "test_key", "value": "test_value"},
                runtime_state,
            )
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["key"], "test_key")
            self.assertFalse(result.get("updated_existing", False))
            # Internal DB fields must NOT be present
            self.assertNotIn("entry", result)
            self.assertNotIn("id", result)
            self.assertNotIn("conversation_id", result)
            self.assertNotIn("message_id", result)
            self.assertNotIn("created_at", result)
            self.assertIn("saved", summary)

class TestConversationHasClarificationToolCall(unittest.TestCase):
    """Tests for the fixed _conversation_has_clarification_tool_call.

    The function must only return True when ask_clarifying_question is called
    AFTER the latest user message (i.e., in the current turn), NOT for
    historical calls from previous turns.
    """

    def _make_clarification_assistant_message(self):
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "ask_clarifying_question",
                        "arguments": '{"questions":[{"id":"q1","label":"test","input_type":"text"}]}',
                    }
                }
            ],
        }

    def test_returns_true_when_clarification_called_after_latest_user(self):
        # Current turn: tool was called after latest user message → True
        messages = [
            {"role": "user", "content": "Önce soru sor"},
            self._make_clarification_assistant_message(),
        ]
        self.assertTrue(_conversation_has_clarification_tool_call(messages))

    def test_returns_false_when_clarification_only_in_historical_turn(self):
        # Historical turn has the call; current turn (after latest user) does not → False
        messages = [
            {"role": "user", "content": "İlaçlarımı anlat"},
            self._make_clarification_assistant_message(),
            {"role": "user", "content": "Atomoxetine kullanıyorum"},  # answered
            {"role": "assistant", "content": "Anladım, DEHB tedavi planı..."},
            # New turn — different question, no clarification tool call this time
            {"role": "user", "content": "Peki modafinil nasıl çalışır?"},
            {"role": "assistant", "content": "Modafinil bir uyarıcıdır..."},
        ]
        self.assertFalse(_conversation_has_clarification_tool_call(messages))

    def test_returns_false_when_no_messages(self):
        self.assertFalse(_conversation_has_clarification_tool_call([]))

    def test_returns_false_when_no_user_message(self):
        # No user message at all
        messages = [{"role": "assistant", "content": "Merhaba"}]
        self.assertFalse(_conversation_has_clarification_tool_call(messages))

    def test_returns_false_when_no_tool_calls_this_turn(self):
        # Previous clarification call exists but nothing after latest user
        messages = [
            {"role": "user", "content": "Soru sor"},
            self._make_clarification_assistant_message(),
            {"role": "user", "content": "Cevap verdim"},
            # No assistant message after this user message yet
        ]
        self.assertFalse(_conversation_has_clarification_tool_call(messages))

    def test_returns_false_when_other_tool_called_this_turn(self):
        # Different tool called after latest user — not ask_clarifying_question → False
        messages = [
            {"role": "user", "content": "Canvas'ı güncelle"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "replace_canvas_lines", "arguments": "{}"}}],
            },
        ]
        self.assertFalse(_conversation_has_clarification_tool_call(messages))

    def test_multiple_historical_turns_all_blocked_before(self):
        # Three prior clarification rounds, none in the current turn → False
        messages = []
        for _ in range(3):
            messages.append({"role": "user", "content": "Yeni soru"})
            messages.append(self._make_clarification_assistant_message())
            messages.append({"role": "user", "content": "Cevap"})
            messages.append({"role": "assistant", "content": "Devam edelim"})
        # Current turn: model answers directly
        messages.append({"role": "user", "content": "Başka bir şey sor lütfen"})
        messages.append({"role": "assistant", "content": "Belki başka bir şey sorardım ama biliyorum..."})
        self.assertFalse(_conversation_has_clarification_tool_call(messages))

    def test_historical_and_current_both_have_call(self):
        # Historical call + current turn also has a call → True
        messages = [
            {"role": "user", "content": "Soru sor"},
            self._make_clarification_assistant_message(),
            {"role": "user", "content": "Cevap verdim"},
            {"role": "assistant", "content": "Devam ediyorum"},
            {"role": "user", "content": "Ayrıca şunu da sor"},
            self._make_clarification_assistant_message(),  # current turn has call
        ]
        self.assertTrue(_conversation_has_clarification_tool_call(messages))


class TestClarificationResponseInjection(unittest.TestCase):
    """Regression tests for the bug where clarification_response was never passed
    to _build_budgeted_prompt_messages, causing the Clarification Response section
    to never appear in the model's prompt even when the user had answered all questions.

    Root cause: routes/chat.py called _build_budgeted_prompt_messages with
    clarification_response=None, all_clarification_rounds=None unconditionally.
    Fix: pass the actual clarification_response and collected rounds.
    """

    def _make_clarification_response(self):
        return {
            "assistant_message_id": "42",
            "questions": [
                {"id": "wallet_type", "text": "Hangi Bitcoin cüzdan yazılımını kullanıyorsunuz?"},
                {"id": "installation_method", "text": "Cüzdan nasıl kuruldu?"},
            ],
            "answers": {
                "wallet_type": {"display": "Diğer / Bilmiyorum"},
                "installation_method": {"display": "Bilmiyorum"},
            },
        }

    def test_build_runtime_context_injection_injects_clarification_response(self):
        """When clarification_response is provided, Clarification Response section appears."""
        clarification_response = self._make_clarification_response()
        injection = build_runtime_context_injection(
            active_tool_names=["ask_clarifying_question"],
            clarification_response=clarification_response,
            all_clarification_rounds=None,
        )
        self.assertIn("Clarification Response", injection)
        self.assertIn("Diğer / Bilmiyorum", injection)
        self.assertIn("Bilmiyorum", injection)

    def test_build_runtime_context_injection_no_clarification_when_none(self):
        """When clarification_response is None, no Clarification Response section."""
        injection = build_runtime_context_injection(
            active_tool_names=["ask_clarifying_question"],
            clarification_response=None,
            all_clarification_rounds=None,
        )
        self.assertNotIn("Clarification Response", injection)

    def test_build_runtime_context_injection_no_clarification_when_no_answers(self):
        """When clarification_response has no answers dict, no section is injected."""
        empty_response = {"assistant_message_id": "42", "questions": [], "answers": {}}
        injection = build_runtime_context_injection(
            active_tool_names=["ask_clarifying_question"],
            clarification_response=empty_response,
            all_clarification_rounds=None,
        )
        self.assertNotIn("Clarification Response", injection)

    def test_clarification_response_guidance_prohibits_re_rendering_questions(self):
        """Guidance text must explicitly prohibit re-displaying the questions in text."""
        clarification_response = self._make_clarification_response()
        injection = build_runtime_context_injection(
            active_tool_names=["ask_clarifying_question"],
            clarification_response=clarification_response,
            all_clarification_rounds=None,
        )
        # The guidance should explicitly forbid re-listing the questions
        self.assertIn("re-list", injection.lower().replace("-", " ") + " " + injection.lower())

    def test_clarification_response_shows_all_rounds_when_provided(self):
        """When all_clarification_rounds is provided, all rounds appear in the injection."""
        first_round = {
            "questions": [{"id": "scope", "text": "Hangi modül?"}],
            "answers": {"scope": {"display": "Backend modülü"}},
        }
        current_round = self._make_clarification_response()
        injection = build_runtime_context_injection(
            active_tool_names=["ask_clarifying_question"],
            clarification_response=current_round,
            all_clarification_rounds=[first_round, current_round],
        )
        self.assertIn("Clarification Response", injection)
        self.assertIn("Backend modülü", injection)
        self.assertIn("Diğer / Bilmiyorum", injection)

