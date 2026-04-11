from __future__ import annotations

import math
import os
import re
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

    def upsert(self, ids, documents, embeddings, metadatas):
        for item_id, document, embedding, metadata in zip(ids, documents, embeddings, metadatas, strict=False):
            self._rows[str(item_id)] = {
                "id": str(item_id),
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
            self._rows.pop(str(item_id), None)

    def query(self, query_embeddings, n_results, where=None, include=None):
        query_vector = list((query_embeddings or [[[]]])[0] or [])
        rows = [row for row in self._rows.values() if _matches_where(row["metadata"], where)]
        scored = []
        for row in rows:
            similarity = _dot_product(query_vector, row["embedding"])
            scored.append((1.0 - similarity, row))
        scored.sort(key=lambda item: item[0])
        limited = scored[: max(1, int(n_results or 1))]
        return {
            "ids": [[row["id"] for _distance, row in limited]],
            "documents": [[row["document"] for _distance, row in limited]],
            "metadatas": [[row["metadata"] for _distance, row in limited]],
            "distances": [[distance for distance, _row in limited]],
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


def _dot_product(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return float(sum(float(left[index]) * float(right[index]) for index in range(size)))


def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        tokens = re.findall(r"[a-z0-9_]+", str(text or "").lower())
        values = [0.0] * 16
        for token in tokens:
            bucket = sum(token.encode("utf-8")) % len(values)
            values[bucket] += 1.0
        if not any(values):
            values[0] = 1.0
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        vectors.append([value / norm for value in values])
    return vectors


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