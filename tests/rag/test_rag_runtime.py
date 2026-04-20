from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
import rag_service
from db import get_app_settings, get_user_profile_entries, save_app_settings
from rag.chunker import Chunk, chunk_text_document
from rag.ingestor import chunks_from_records
from rag.store import _build_metadata_filter_where, query_chunks, upsert_chunks
from rag_service import (
    build_rag_auto_context,
    ensure_supported_rag_sources,
    get_exact_tool_memory_match,
    search_knowledge_base_tool,
    sync_conversations_to_rag_background,
    upsert_tool_memory_result,
)
from routes.chat import (
    _schedule_rag_conversation_sync,
    _trim_rag_context_to_token_budget,
    maybe_create_conversation_summary,
)


def test_build_metadata_filter_where_defaults_to_and_across_fields_and_or_within_field():
    where = _build_metadata_filter_where(
        {
            "workspace_id": ["conversation:12", "conversation:13"],
            "section_id": ["intro", "details"],
        },
        filter_mode="and",
        base_where={"category": "conversation"},
    )

    assert where == {
        "$and": [
            {"category": "conversation"},
            {
                "$and": [
                    {"$or": [{"workspace_id": "conversation:12"}, {"workspace_id": "conversation:13"}]},
                    {"$or": [{"section_id": "intro"}, {"section_id": "details"}]},
                ]
            },
        ]
    }


def test_build_metadata_filter_where_supports_or_across_fields():
    where = _build_metadata_filter_where(
        {
            "workspace_id": ["conversation:12", "conversation:13"],
            "section_id": ["intro"],
        },
        filter_mode="or",
        base_where={"category": "conversation"},
    )

    assert where == {
        "$and": [
            {"category": "conversation"},
            {
                "$or": [
                    {"$or": [{"workspace_id": "conversation:12"}, {"workspace_id": "conversation:13"}]},
                    {"section_id": "intro"},
                ]
            },
        ]
    }


class TestRagRuntime:
    @pytest.fixture(autouse=True)
    def _setup(self, app, client, create_conversation):
        self.app = app
        self.client = client
        self._create_conversation = create_conversation

    def test_structured_summary_persists_user_profile_facts(self):
        conversation_id = self._create_conversation()
        with self.app.app_context():
            from db import get_db, insert_message

            with get_db() as conn:
                insert_message(
                    conn, conversation_id, "user", "Please keep answers short and concise in future replies."
                )
                insert_message(conn, conversation_id, "assistant", "Understood. I will keep future answers concise.")

        summary_payload = {
            "content": json.dumps(
                {
                    "facts": [
                        "The user prefers concise answers in future replies and wants the assistant to keep responses short unless more detail is explicitly requested.",
                        "The user is actively working on an os-chatbot codebase and expects continuity across iterations so the assistant should preserve implementation context when responding.",
                    ],
                    "decisions": [
                        "Future replies should stay concise while still preserving implementation-critical details and current repository context."
                    ],
                    "open_issues": [
                        "Need to keep tracking codebase-specific preferences across future maintenance tasks."
                    ],
                    "entities": ["os-chatbot"],
                    "tool_outcomes": [
                        "No external tool results were required for this summary; the key persistent preference is concise reply style."
                    ],
                }
            )
        }
        settings = get_app_settings()
        settings.update(
            {
                "chat_summary_mode": "auto",
                "chat_summary_detail_level": "detailed",
                "summary_skip_first": 0,
                "summary_skip_last": 0,
            }
        )

        with patch("routes.chat.collect_agent_response", return_value=summary_payload) as mocked_collect:
            outcome = maybe_create_conversation_summary(
                conversation_id,
                "deepseek-chat",
                settings,
                fetch_url_token_threshold=4_000,
                fetch_url_clip_aggressiveness=0,
                force=True,
                bypass_mode=True,
            )

        assert outcome["applied"]
        prompt_messages = mocked_collect.call_args.args[0]
        prompt_text = "\n".join(str(message.get("content") or "") for message in prompt_messages)
        assert "Write a detailed summary" in prompt_text
        stored_entries = get_user_profile_entries()
        assert any("concise answers" in entry["value"].lower() for entry in stored_entries)
        assert outcome.get("stored_profile_fact_count", 0) >= 1

    def test_query_chunks_skips_expired_metadata(self):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        future_ts = now_ts + 3600
        past_ts = now_ts - 3600

        fake_collection = Mock()
        fake_collection.query.return_value = {
            "documents": [["expired result", "fresh result"]],
            "metadatas": [
                [
                    {
                        "source_key": "expired",
                        "source_type": "tool_memory",
                        "category": "tool_memory",
                        "expires_at_ts": past_ts,
                    },
                    {
                        "source_key": "fresh",
                        "source_type": "tool_memory",
                        "category": "tool_memory",
                        "expires_at_ts": future_ts,
                    },
                ]
            ],
            "distances": [[0.1, 0.05]],
            "ids": [["old-id", "fresh-id"]],
        }

        with (
            patch("rag.store._iter_query_collections", return_value=[(fake_collection, {"category": "tool_memory"})]),
            patch("rag.store.embed_texts", return_value=[[0.1, 0.2]]),
        ):
            rows = query_chunks("latest result", top_k=5, category="tool_memory")

        assert len(rows) == 1
        assert rows[0]["id"] == "fresh-id"
        assert rows[0]["metadata"]["source_key"] == "fresh"

    def test_upsert_chunks_writes_to_category_collections(self):
        collection_conversation = Mock()
        collection_tool_memory = Mock()

        chunks = [
            Chunk(
                id="chunk-1",
                text="conversation text",
                source_name="conversation-doc",
                source_type="conversation",
                category="conversation",
                chunk_index=0,
                metadata={"source_key": "src-1"},
            ),
            Chunk(
                id="chunk-2",
                text="tool memory text",
                source_name="tool-memory-doc",
                source_type="tool_memory",
                category="tool_memory",
                chunk_index=0,
                metadata={"source_key": "src-2"},
            ),
        ]

        def fake_get_collection(name="knowledge_base"):
            if name == "knowledge_base__conversation":
                return collection_conversation
            if name == "knowledge_base__tool_memory":
                return collection_tool_memory
            return Mock()

        with (
            patch("rag.store.get_collection", side_effect=fake_get_collection),
            patch("rag.store.embed_texts", return_value=[[0.1, 0.2], [0.3, 0.4]]),
        ):
            inserted = upsert_chunks(chunks)

        assert inserted == 2
        collection_conversation.upsert.assert_called_once()
        collection_tool_memory.upsert.assert_called_once()

    def test_get_exact_tool_memory_match_returns_joined_chunk_content(self):
        with (
            patch("rag_service.ensure_supported_rag_sources"),
            patch(
                "rag_service.get_rag_document_record",
                return_value={
                    "source_key": "src-1",
                    "source_name": "fetch_url: https://example.com/page",
                    "metadata": json.dumps({"summary": "Page content extracted: Example"}),
                    "expires_at": None,
                },
            ),
            patch(
                "rag_service.rag_get_source_chunks",
                return_value=[
                    {"id": "chunk-1", "text": "Title: Example", "metadata": {"chunk_index": 0}},
                    {"id": "chunk-2", "text": "Body: Retrieved content", "metadata": {"chunk_index": 1}},
                ],
            ),
        ):
            match = get_exact_tool_memory_match("fetch_url", "https://example.com/page")

        assert match is not None
        assert match["summary"] == "Page content extracted: Example"
        assert "Title: Example" in match["content"]
        assert "Body: Retrieved content" in match["content"]

    def test_upsert_tool_memory_result_assigns_ttl_metadata(self):
        with (
            patch("rag_service.time.time", return_value=1_000),
            patch("rag_service.ingest_rag_chunks") as mocked_ingest,
        ):
            mocked_ingest.return_value = {"ok": True}
            upsert_tool_memory_result(
                "search_news_ddgs",
                "economy headlines",
                "headline body",
                "brief summary",
            )

        _, kwargs = mocked_ingest.call_args
        assert kwargs["expires_at"] == "1970-01-01 02:16:40"
        assert kwargs["metadata"]["expires_at_ts"] == 8_200
        assert kwargs["metadata"]["workspace_id"] == "tool-memory"
        assert kwargs["metadata"]["project_id"] == "search_news_ddgs"
        assert kwargs["metadata"]["document_id"] == kwargs["source_key"]
        assert str(kwargs["metadata"]["document_path"]).startswith("tool_memory/")

    def test_upsert_tool_memory_result_sanitizes_html_entities(self):
        with (
            patch("rag_service.time.time", return_value=1_000),
            patch("rag_service.ingest_rag_chunks") as mocked_ingest,
        ):
            mocked_ingest.return_value = {"ok": True}
            upsert_tool_memory_result(
                "fetch_url",
                "https://example.com",
                "Title &amp; Summary\u200b",
                "brief summary",
            )

        _, kwargs = mocked_ingest.call_args
        assert "Title & Summary" in kwargs["chunks"][0].text

    def test_search_knowledge_base_tool_adds_context_metadata(self):
        fake_hits = [
            {
                "id": "chunk-1",
                "text": "sort docs",
                "metadata": {
                    "source_key": "src-1",
                    "source_name": "doc-1",
                    "source_type": "conversation",
                    "category": "conversation",
                    "chunk_index": 0,
                    "indexed_at_ts": 2_000,
                },
                "similarity": 0.52,
            },
            {
                "id": "chunk-2",
                "text": "sort docs tail",
                "metadata": {
                    "source_key": "src-1",
                    "source_name": "doc-1",
                    "source_type": "conversation",
                    "category": "conversation",
                    "chunk_index": 2,
                    "indexed_at_ts": 2_000,
                },
                "similarity": 0.51,
            },
        ]

        with (
            patch("rag_service.ensure_supported_rag_sources"),
            patch("rag_service.rag_query_chunks", return_value=fake_hits),
            patch("rag_service.get_db") as mocked_db,
            patch("rag_service.time.time", return_value=2_000),
        ):
            mocked_db.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = [
                {"source_key": "src-1", "chunk_count": 3}
            ]
            result = search_knowledge_base_tool("python sort", top_k=5)

        assert result["matches"][0]["total_chunks"] == 3
        assert result["matches"][0]["has_more_context"]
        assert not result["matches"][1]["has_more_context"]

    def test_search_knowledge_base_tool_uses_query_expansion_and_dedupes_hits(self):
        original_query = "python liste sıralama nasıl yapılır"

        def fake_query(
            query,
            top_k=5,
            category=None,
            source_type_hint=None,
            metadata_filters=None,
            metadata_filter_mode="and",
        ):
            del source_type_hint
            del metadata_filters
            del metadata_filter_mode
            if query == original_query:
                return [
                    {
                        "id": "chunk-1",
                        "text": "sort docs",
                        "metadata": {
                            "source_key": "src-1",
                            "source_name": "doc-1",
                            "source_type": "conversation",
                            "category": "conversation",
                            "chunk_index": 0,
                            "indexed_at_ts": 2_000,
                        },
                        "similarity": 0.40,
                    }
                ]
            return [
                {
                    "id": "chunk-1",
                    "text": "sort docs",
                    "metadata": {
                        "source_key": "src-1",
                        "source_name": "doc-1",
                        "source_type": "conversation",
                        "category": "conversation",
                        "chunk_index": 0,
                        "indexed_at_ts": 2_000,
                    },
                    "similarity": 0.52,
                },
                {
                    "id": "chunk-2",
                    "text": "list order",
                    "metadata": {
                        "source_key": "src-2",
                        "source_name": "doc-2",
                        "source_type": "conversation",
                        "category": "conversation",
                        "chunk_index": 1,
                        "indexed_at_ts": 2_000,
                    },
                    "similarity": 0.45,
                },
            ]

        with (
            patch("rag_service.ensure_supported_rag_sources"),
            patch("rag_service.rag_query_chunks", side_effect=fake_query) as mocked_query,
            patch("rag_service.time.time", return_value=2_000),
        ):
            result = search_knowledge_base_tool(original_query, top_k=5)

        assert mocked_query.call_count >= 2
        assert result["count"] == 2

    def test_ensure_supported_rag_sources_uses_cooldown(self):
        fake_conn = Mock()
        fake_conn.execute.return_value.fetchall.return_value = []

        with (
            patch("rag_service._rag_sources_verified", True),
            patch("rag_service._rag_sources_last_verified_at", 100.0),
            patch("rag_service.time.time", return_value=120.0),
            patch(
                "rag_service.get_db",
                return_value=Mock(__enter__=Mock(return_value=fake_conn), __exit__=Mock(return_value=False)),
            ),
            patch("rag_service.get_expired_rag_document_source_keys") as mocked_expired,
        ):
            removed = ensure_supported_rag_sources()

        assert removed == 0
        mocked_expired.assert_called_once()

    def test_chunk_text_document_normalizes_unicode_and_stable_ids(self):
        first = chunk_text_document("Cafe\u0301\u200b", "doc", "conversation", "conversation")
        second = chunk_text_document("Café", "doc", "conversation", "conversation")

        assert first[0].text == "Café"
        assert first[0].id == second[0].id

    def test_chunk_text_document_assigns_page_number_metadata(self):
        text = "## Page 1\n\n" + ("Alpha " * 80) + "\n\n## Page 2\n\n" + ("Beta " * 80)

        chunks = chunk_text_document(text, "doc", "uploaded-document", "general", chunk_size=160, overlap=40)

        page_numbers = [chunk.metadata.get("page_number") for chunk in chunks]
        assert 1 in page_numbers
        assert 2 in page_numbers
        assert page_numbers[0] == 1

    def test_chunk_text_document_assigns_section_metadata(self):
        text = "# Intro\n\nAlpha content\n\n## Details\n\nBeta content"

        chunks = chunk_text_document(text, "doc", "uploaded-document", "general", chunk_size=120, overlap=0)

        section_ids = [str(chunk.metadata.get("section_id") or "") for chunk in chunks]
        section_titles = [str(chunk.metadata.get("section_title") or "") for chunk in chunks]
        assert "intro" in section_ids
        assert "details" in section_ids
        assert "Intro" in section_titles
        assert "Details" in section_titles
        assert all("chunk_id_in_document" in chunk.metadata for chunk in chunks)

    def test_chunks_from_records_skips_short_noise_messages(self):
        chunks = chunks_from_records(
            [
                {"role": "user", "content": "Tamam"},
                {"role": "assistant", "content": "Bu yanıt indekslenmesi gereken kadar uzun ve anlamlıdır."},
            ],
            source_name="conversation:1:Test",
            source_type="conversation",
            category="conversation",
        )

        assert len(chunks) == 1
        assert "Tamam" not in chunks[0].text

    def test_build_rag_auto_context_respects_allowed_source_types(self):
        fake_hits = [
            {
                "id": "upload-disabled",
                "text": "manual memory disabled",
                "metadata": {
                    "source_key": "upload-1",
                    "source_name": "Manual disabled",
                    "source_type": "uploaded_document",
                    "category": "uploaded_document",
                    "chunk_index": 0,
                    "auto_inject_enabled": False,
                },
                "similarity": 0.93,
            },
            {
                "id": "tool-hit",
                "text": "tool memory",
                "metadata": {
                    "source_key": "tool-1",
                    "source_name": "Tool memory",
                    "source_type": "tool_memory",
                    "category": "tool_memory",
                    "chunk_index": 0,
                },
                "similarity": 0.92,
            },
            {
                "id": "upload-enabled",
                "text": "manual memory enabled",
                "metadata": {
                    "source_key": "upload-2",
                    "source_name": "Manual enabled",
                    "source_type": "uploaded_document",
                    "category": "uploaded_document",
                    "chunk_index": 0,
                    "auto_inject_enabled": True,
                },
                "similarity": 0.91,
            },
        ]

        with (
            patch("rag_service.ensure_supported_rag_sources"),
            patch("rag_service.rag_query_chunks", return_value=fake_hits),
        ):
            result = build_rag_auto_context(
                "manual memory",
                True,
                threshold=0.1,
                top_k=5,
                allowed_source_types={"uploaded_document"},
            )

        assert result is not None
        assert [match["source_name"] for match in result["matches"]] == ["Manual enabled"]

    def test_build_rag_auto_context_prefers_recent_hits_with_temporal_decay(self):
        old_timestamp = int((datetime.now(timezone.utc) - timedelta(days=60)).timestamp())
        new_timestamp = int(datetime.now(timezone.utc).timestamp())
        fake_hits = [
            {
                "id": "old-hit",
                "text": "older memory",
                "metadata": {
                    "source_key": "old",
                    "source_name": "Old",
                    "source_type": "tool_memory",
                    "category": "tool_memory",
                    "chunk_index": 0,
                    "indexed_at_ts": old_timestamp,
                },
                "similarity": 0.50,
            },
            {
                "id": "new-hit",
                "text": "newer memory",
                "metadata": {
                    "source_key": "new",
                    "source_name": "New",
                    "source_type": "tool_memory",
                    "category": "tool_memory",
                    "chunk_index": 0,
                    "indexed_at_ts": new_timestamp,
                },
                "similarity": 0.50,
            },
        ]

        with (
            patch("rag_service.ensure_supported_rag_sources"),
            patch("rag_service.rag_query_chunks", return_value=fake_hits),
            patch("rag_service.time.time", return_value=new_timestamp),
        ):
            result = build_rag_auto_context("recent memory", True, threshold=0.1, top_k=5)

        assert result is not None
        assert result["matches"][0]["source_name"] == "New"
        assert result["matches"][0]["similarity"] > result["matches"][1]["similarity"]
        assert "id" not in result["matches"][0]
        assert "source_key" not in result["matches"][0]

    def test_build_rag_auto_context_excludes_current_conversation_sources(self):
        fake_hits = [
            {
                "id": "conversation-hit",
                "text": "conversation memory",
                "metadata": {
                    "source_key": "conversation-1",
                    "source_name": "Conversation",
                    "source_type": "conversation",
                    "category": "conversation",
                    "chunk_index": 0,
                },
                "similarity": 0.98,
            },
            {
                "id": "tool-hit",
                "text": "tool memory",
                "metadata": {
                    "source_key": "tool-1",
                    "source_name": "Tool result",
                    "source_type": "tool_result",
                    "category": "tool_result",
                    "chunk_index": 0,
                },
                "similarity": 0.95,
            },
            {
                "id": "archived-hit",
                "text": "archived conversation memory",
                "metadata": {
                    "source_key": "conversation-1-archived",
                    "source_name": "Conversation archive",
                    "source_type": "conversation",
                    "category": "conversation",
                    "chunk_index": 0,
                    "archived_conversation": True,
                    "archived_message_count": 12,
                },
                "similarity": 0.93,
            },
            {
                "id": "other-hit",
                "text": "other memory",
                "metadata": {
                    "source_key": "other-1",
                    "source_name": "Other",
                    "source_type": "tool_memory",
                    "category": "tool_memory",
                    "chunk_index": 0,
                },
                "similarity": 0.90,
            },
        ]

        with (
            patch("rag_service.ensure_supported_rag_sources"),
            patch("rag_service.rag_query_chunks", return_value=fake_hits),
        ):
            result = build_rag_auto_context(
                "recent memory",
                True,
                threshold=0.1,
                top_k=5,
                exclude_source_keys={"conversation-1", "tool-1"},
            )

        assert result is not None
        # Archived conversation chunks are now excluded from auto-inject
        # (exclude_archived_conversations=True), so only non-archived
        # non-excluded sources remain.
        assert [match["source_name"] for match in result["matches"]] == ["Other"]

    def test_build_rag_auto_context_limits_chunks_per_source(self):
        fake_hits = [
            {
                "id": "same-1",
                "text": "same source chunk 1",
                "metadata": {
                    "source_key": "same",
                    "source_name": "Same Source",
                    "source_type": "uploaded_document",
                    "category": "uploaded_document",
                    "chunk_index": 0,
                    "auto_inject_enabled": True,
                },
                "similarity": 0.99,
            },
            {
                "id": "same-2",
                "text": "same source chunk 2",
                "metadata": {
                    "source_key": "same",
                    "source_name": "Same Source",
                    "source_type": "uploaded_document",
                    "category": "uploaded_document",
                    "chunk_index": 1,
                    "auto_inject_enabled": True,
                },
                "similarity": 0.98,
            },
            {
                "id": "same-3",
                "text": "same source chunk 3",
                "metadata": {
                    "source_key": "same",
                    "source_name": "Same Source",
                    "source_type": "uploaded_document",
                    "category": "uploaded_document",
                    "chunk_index": 2,
                    "auto_inject_enabled": True,
                },
                "similarity": 0.97,
            },
            {
                "id": "other-1",
                "text": "other source chunk",
                "metadata": {
                    "source_key": "other",
                    "source_name": "Other Source",
                    "source_type": "uploaded_document",
                    "category": "uploaded_document",
                    "chunk_index": 0,
                    "auto_inject_enabled": True,
                },
                "similarity": 0.96,
            },
        ]

        with (
            patch("rag_service.ensure_supported_rag_sources"),
            patch("rag_service.rag_query_chunks", return_value=fake_hits),
            patch(
                "rag_service.RAG_MAX_CHUNKS_PER_SOURCE",
                2,
            ),
        ):
            result = build_rag_auto_context("memory", True, threshold=0.1, top_k=4)

        assert result is not None
        assert [match["source_name"] for match in result["matches"]] == ["Same Source", "Same Source", "Other Source"]

    def test_build_rag_auto_context_overfetches_candidates_for_source_diversity(self):
        with (
            patch("rag_service.ensure_supported_rag_sources"),
            patch("rag_service.rag_query_chunks", return_value=[]) as mocked_query,
            patch(
                "rag_service.RAG_MAX_CHUNKS_PER_SOURCE",
                2,
            ),
        ):
            build_rag_auto_context("memory", True, threshold=0.1, top_k=3)

        assert mocked_query.call_count >= 1
        assert mocked_query.call_args.kwargs["top_k"] == 6

    def test_search_knowledge_base_tool_stops_query_expansion_after_sufficient_first_variant_hits(self):
        first_variant_hits = [
            {
                "id": f"hit-{index}",
                "text": f"hit {index}",
                "metadata": {
                    "source_key": f"source-{index}",
                    "source_name": f"Source {index}",
                    "source_type": "uploaded_document",
                    "category": "uploaded_document",
                    "chunk_index": 0,
                },
                "similarity": 0.9 - (index * 0.01),
            }
            for index in range(4)
        ]

        with (
            patch("rag_service.ensure_supported_rag_sources"),
            patch(
                "rag_service._expand_query_variants",
                return_value=["memory", "memory variant"],
            ),
            patch(
                "rag_service.rag_query_chunks",
                side_effect=[first_variant_hits, RuntimeError("Second variant should not run")],
            ) as mocked_query,
            patch("rag_service.RAG_MAX_CHUNKS_PER_SOURCE", 2),
        ):
            result = search_knowledge_base_tool("memory", top_k=2)

        assert mocked_query.call_count == 1
        assert result["count"] == 2

    def test_trim_rag_context_skips_oversized_high_score_match_and_keeps_smaller_relevant_matches(self):
        retrieved_context = {
            "query": "memory",
            "matches": [
                {"source_name": "Large", "text": "large", "similarity": 0.99},
                {"source_name": "Small A", "text": "small-a", "similarity": 0.95},
                {"source_name": "Small B", "text": "small-b", "similarity": 0.94},
            ],
        }

        def fake_format(context):
            return "|".join(match.get("source_name") or "" for match in context.get("matches") or [])

        token_map = {
            "Large": 150,
            "Small A": 40,
            "Small B": 45,
            "Small A|Small B": 85,
            "Large|Small A": 190,
            "Large|Small B": 195,
        }

        with (
            patch("routes.chat.format_knowledge_base_auto_context", side_effect=fake_format),
            patch(
                "routes.chat.estimate_text_tokens",
                side_effect=lambda text: token_map.get(text, 999),
            ),
        ):
            trimmed = _trim_rag_context_to_token_budget(retrieved_context, max_tokens=100)

        assert trimmed is not None
        assert [match["source_name"] for match in trimmed["matches"]] == ["Small A", "Small B"]

    def test_rag_search_route_uses_saved_source_type_settings(self):
        settings = get_app_settings()
        settings["rag_source_types"] = json.dumps(["uploaded_document"], ensure_ascii=False)
        save_app_settings(settings)

        with patch(
            "routes.conversations.search_knowledge_base_tool",
            return_value={"query": "memory", "count": 0, "matches": []},
        ) as mocked_search:
            response = self.client.get("/api/rag/search?q=memory")

        assert response.status_code == 200
        assert mocked_search.call_args.kwargs["allowed_source_types"] == ["uploaded_document"]

        with patch(
            "routes.conversations.search_knowledge_base_tool",
            return_value={"query": "memory", "count": 0, "matches": []},
        ) as mocked_search:
            response = self.client.get("/api/rag/search?q=memory&source_types=conversation,tool_memory")

        assert response.status_code == 200
        assert mocked_search.call_args.kwargs["allowed_source_types"] == ["conversation", "tool_memory"]

        with patch(
            "routes.conversations.search_knowledge_base_tool",
            return_value={"query": "memory", "count": 0, "matches": []},
        ) as mocked_search:
            response = self.client.get("/api/rag/search?q=memory&source_type=conversation,tool_memory")

        assert response.status_code == 200
        assert mocked_search.call_args.kwargs["allowed_source_types"] == ["conversation", "tool_memory"]

    def test_rag_search_route_passes_min_similarity(self):
        with patch(
            "routes.conversations.search_knowledge_base_tool",
            return_value={"query": "memory", "count": 0, "matches": []},
        ) as mocked_search:
            response = self.client.get("/api/rag/search?q=memory&min_similarity=0.75")

        assert response.status_code == 200
        assert mocked_search.call_args.kwargs["min_similarity"] == 0.75

    def test_rag_search_route_passes_hierarchical_metadata_filters(self):
        with patch(
            "routes.conversations.search_knowledge_base_tool",
            return_value={"query": "memory", "count": 0, "matches": []},
        ) as mocked_search:
            response = self.client.get(
                "/api/rag/search?q=memory&workspace_id=conversation:12&project_id=chat-history&document_path=conversations/12&section_id=intro"
            )

        assert response.status_code == 200
        assert mocked_search.call_args.kwargs["metadata_filters"] == {
            "workspace_id": ["conversation:12"],
            "project_id": ["chat-history"],
            "document_path": ["conversations/12"],
            "section_id": ["intro"],
        }
        assert mocked_search.call_args.kwargs["metadata_filter_mode"] == "and"

    def test_rag_search_route_passes_multi_value_filters_with_or_mode(self):
        with patch(
            "routes.conversations.search_knowledge_base_tool",
            return_value={"query": "memory", "count": 0, "matches": []},
        ) as mocked_search:
            response = self.client.get(
                "/api/rag/search?q=memory&workspace_id=conversation:12&workspace_id=conversation:13&section_id=intro,details&metadata_filter_mode=or"
            )

        assert response.status_code == 200
        assert mocked_search.call_args.kwargs["metadata_filters"] == {
            "workspace_id": ["conversation:12", "conversation:13"],
            "section_id": ["intro", "details"],
        }
        assert mocked_search.call_args.kwargs["metadata_filter_mode"] == "or"

    def test_rag_search_route_rejects_invalid_metadata_filter_mode(self):
        response = self.client.get("/api/rag/search?q=memory&metadata_filter_mode=xor")

        assert response.status_code == 400
        assert "metadata_filter_mode" in response.get_json()["error"]

    def test_rag_search_route_rejects_invalid_min_similarity(self):
        response = self.client.get("/api/rag/search?q=memory&min_similarity=abc")

        assert response.status_code == 400
        assert "min_similarity" in response.get_json()["error"]

    def test_rag_search_route_rejects_out_of_range_min_similarity(self):
        for value in ("-0.1", "1.1"):
            response = self.client.get(f"/api/rag/search?q=memory&min_similarity={value}")

            assert response.status_code == 400
            assert "min_similarity" in response.get_json()["error"]

    def test_schedule_rag_conversation_sync_runs_inline_in_testing(self):
        with self.app.app_context():
            with (
                patch("routes.chat.sync_conversations_to_rag_safe") as mocked_safe,
                patch("routes.chat.sync_conversations_to_rag_background") as mocked_background,
            ):
                _schedule_rag_conversation_sync(321)

        mocked_safe.assert_called_once_with(conversation_id=321, force=False)
        mocked_background.assert_not_called()

    def test_schedule_rag_conversation_sync_uses_background_executor_outside_testing(self):
        previous_testing = self.app.config.get("TESTING", False)
        self.app.config["TESTING"] = False

        try:
            with self.app.app_context():
                with (
                    patch("routes.chat.sync_conversations_to_rag_safe") as mocked_safe,
                    patch("routes.chat.sync_conversations_to_rag_background") as mocked_background,
                ):
                    _schedule_rag_conversation_sync(321, force=True)

            mocked_safe.assert_not_called()
            mocked_background.assert_called_once()
            assert mocked_background.call_args.kwargs["conversation_id"] == 321
            assert mocked_background.call_args.kwargs["force"]
        finally:
            self.app.config["TESTING"] = previous_testing

    def test_sync_conversations_to_rag_background_coalesces_duplicate_jobs(self):
        class FakeExecutor:
            def __init__(self):
                self.calls = []

            def submit(self, fn):
                future = object()
                self.calls.append((fn, future))
                return future

        executor = FakeExecutor()
        rag_service._rag_background_sync_jobs.clear()
        try:
            with patch("rag_service._get_rag_background_executor", return_value=executor):
                first_future = sync_conversations_to_rag_background(self.app, conversation_id=321, force=False)
                second_future = sync_conversations_to_rag_background(self.app, conversation_id=321, force=True)

            assert first_future is second_future
            assert len(executor.calls) == 1
            assert rag_service._rag_background_sync_jobs["conversation:321"]["force"]
        finally:
            rag_service._rag_background_sync_jobs.clear()
