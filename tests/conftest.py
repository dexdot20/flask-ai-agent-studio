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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
project_root_str = str(PROJECT_ROOT)

if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

import request_security

from tests.support.mocks import FakeChromaClient, fake_embed_texts


@pytest.fixture(autouse=True)
def test_environment(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")


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

    fake_client = FakeChromaClient()
    rag_store._client = None
    rag_store._collection_cache = {}
    monkeypatch.setattr(rag_store, "get_client", lambda: fake_client)
    monkeypatch.setattr(rag_store, "embed_texts", fake_embed_texts)
    model_registry.get_provider_client.cache_clear()
    deepseek_client = model_registry.get_provider_client(model_registry.DEEPSEEK_PROVIDER)
    monkeypatch.setattr(agent, "client", deepseek_client)
    monkeypatch.setattr(prune_service, "client", deepseek_client)
    monkeypatch.setattr(routes.conversations, "client", deepseek_client)
    yield
    rag_store._client = None
    rag_store._collection_cache = {}
    model_registry.get_provider_client.cache_clear()


@pytest.fixture
def app(tmp_path, monkeypatch):
    from app import create_app

    monkeypatch.setattr("config.LOGIN_PIN", "")
    app_instance = create_app(database_path=str(tmp_path / "test.db"))
    app_instance.config.update(TESTING=True)
    return app_instance


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def create_conversation(client):
    def _factory(title: str = "Test Chat") -> int:
        response = client.post(
            "/api/conversations",
            json={"title": title, "model": "deepseek-chat"},
        )
        assert response.status_code == 201
        payload = response.get_json()
        assert isinstance(payload, dict)
        return int(payload["id"])

    return _factory


@pytest.fixture
def session_csrf_token(client) -> str:
    client.get("/")
    with client.session_transaction() as session_data:
        return str(session_data.get(request_security.CSRF_TOKEN_SESSION_KEY) or "")