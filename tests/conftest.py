from __future__ import annotations

import os
import socket
import sys
import warnings
from pathlib import Path

import pytest
import requests

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)

# Force a deterministic, non-billable test environment before project modules import
# config.py and model_registry.py read these at import time.
os.environ.setdefault("RAG_ENABLED", "true")
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

PROJECT_ROOT = Path(__file__).resolve().parent.parent
project_root_str = str(PROJECT_ROOT)

if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)


class _FakeChromaCollection:
    def __init__(self):
        self._rows: dict[str, dict] = {}
        self._ordered_ids: list[str] = []

    def upsert(self, ids, documents, embeddings, metadatas):
        for item_id, document, embedding, metadata in zip(ids, documents, embeddings, metadatas, strict=False):
            normalized_id = str(item_id)
            if normalized_id not in self._rows:
                self._ordered_ids.append(normalized_id)
            self._rows[normalized_id] = {
                "id": normalized_id,
                "document": document,
                "embedding": list(embedding or []),
                "metadata": dict(metadata or {}),
            }

    def get(self, where=None, include=None):
        rows = [row for row in self._rows.values() if _matches_where(row["metadata"], where)]
        return {
            "ids": [row["id"] for row in rows],
            "documents": [row["document"] for row in rows],
            "metadatas": [row["metadata"] for row in rows],
        }

    def delete(self, ids=None):
        for item_id in ids or []:
            normalized_id = str(item_id)
            self._rows.pop(normalized_id, None)
            self._ordered_ids = [existing_id for existing_id in self._ordered_ids if existing_id != normalized_id]

    def query(self, query_embeddings, n_results, where=None, include=None):
        del query_embeddings, include
        rows = [self._rows[item_id] for item_id in self._ordered_ids if _matches_where(self._rows[item_id]["metadata"], where)]
        limited = rows[: max(1, int(n_results or 1))]
        return {
            "ids": [[row["id"] for row in limited]],
            "documents": [[row["document"] for row in limited]],
            "metadatas": [[row["metadata"] for row in limited]],
            "distances": [[0.0 for _row in limited]],
        }


class _FakeChromaClient:
    def __init__(self):
        self._collections: dict[str, _FakeChromaCollection] = {}

    def get_or_create_collection(self, name, metadata=None):
        del metadata
        if name not in self._collections:
            self._collections[name] = _FakeChromaCollection()
        return self._collections[name]


def _matches_where(metadata: dict | None, where: dict | None) -> bool:
    if not where:
        return True
    source = metadata if isinstance(metadata, dict) else {}
    for key, value in where.items():
        if source.get(key) != value:
            return False
    return True


def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
    return [[float(index + 1)] for index, _text in enumerate(texts)]


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    def _blocked_requests(*args, **kwargs):
        raise AssertionError("External network access is disabled in tests.")

    def _blocked_socket_connect(*args, **kwargs):
        raise AssertionError("External network access is disabled in tests.")

    monkeypatch.setattr(requests.sessions.Session, "request", _blocked_requests)
    monkeypatch.setattr(socket.socket, "connect", _blocked_socket_connect)


@pytest.fixture(autouse=True)
def isolate_test_state(monkeypatch):
    import agent
    import model_registry
    import prune_service
    import rag.store as rag_store
    import routes.conversations

    fake_client = _FakeChromaClient()
    rag_store._client = None
    rag_store._collection_cache = {}
    monkeypatch.setattr(rag_store, "get_client", lambda: fake_client)
    monkeypatch.setattr(rag_store, "embed_texts", _fake_embed_texts)
    model_registry.get_provider_client.cache_clear()
    deepseek_client = model_registry.get_provider_client(model_registry.DEEPSEEK_PROVIDER)
    monkeypatch.setattr(agent, "client", deepseek_client)
    monkeypatch.setattr(prune_service, "client", deepseek_client)
    monkeypatch.setattr(routes.conversations, "client", deepseek_client)
    yield
    rag_store._client = None
    rag_store._collection_cache = {}
    model_registry.get_provider_client.cache_clear()