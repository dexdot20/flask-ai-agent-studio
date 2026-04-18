from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import model_registry
from app import create_app
from db import save_app_settings
from model_registry import get_operation_model, get_operation_model_candidates, resolve_model_target
from proxy_settings import PROXY_OPERATION_FETCH_URL
from tests.support.mocks import CallbackHttpClient, CallbackOpenAI, StaticStream


def test_normalize_chat_parameter_overrides_accepts_known_fields():
    overrides = model_registry.normalize_chat_parameter_overrides(
        {"temperature": 0.6, "top_p": 0.9, "max_tokens": 300}
    )

    assert overrides == {"temperature": 0.6, "top_p": 0.9, "max_tokens": 300}


def test_normalize_chat_parameter_overrides_rejects_unknown_fields():
    with pytest.raises(ValueError):
        model_registry.normalize_chat_parameter_overrides({"temperature": 0.6, "foo": 1})


def test_apply_chat_parameter_overrides_merges_whitelisted_values():
    request_kwargs = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.7,
    }

    merged = model_registry.apply_chat_parameter_overrides(
        request_kwargs,
        {"temperature": 0.4, "top_p": 0.8, "max_tokens": 512},
    )

    assert merged["temperature"] == 0.4
    assert merged["top_p"] == 0.8
    assert merged["max_tokens"] == 512
    assert merged["messages"] == request_kwargs["messages"]


def test_minimax_translation_preserves_tool_result_turn_chain():
    proxy = model_registry._MiniMaxClientProxy(api_key="test-key")
    translated = proxy._translate_openai_to_anthropic(
        {
            "model": "MiniMax-M2.7",
            "messages": [
                {"role": "user", "content": "Solve the task."},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "search_web", "arguments": '{"query":"x"}'},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": "{\"ok\":true,\"summary\":\"done\"}",
                },
            ],
        }
    )

    converted_messages = translated["messages"]
    assert converted_messages[1]["role"] == "assistant"
    assistant_blocks = converted_messages[1]["content"]
    assert any(block.get("type") == "tool_use" and block.get("id") == "call_1" for block in assistant_blocks)

    assert converted_messages[2]["role"] == "user"
    tool_result_block = converted_messages[2]["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["tool_use_id"] == "call_1"


def test_minimax_translation_maps_tool_choice_to_anthropic_shape():
    proxy = model_registry._MiniMaxClientProxy(api_key="test-key")

    translated_auto = proxy._translate_openai_to_anthropic(
        {
            "model": "MiniMax-M2.7",
            "tool_choice": "auto",
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    assert translated_auto["tool_choice"] == {"type": "auto"}

    translated_specific = proxy._translate_openai_to_anthropic(
        {
            "model": "MiniMax-M2.7",
            "tool_choice": {"type": "function", "function": {"name": "search_web"}},
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    assert translated_specific["tool_choice"] == {"type": "tool", "name": "search_web"}


def test_minimax_translation_sets_required_max_tokens_when_missing():
    proxy = model_registry._MiniMaxClientProxy(api_key="test-key")
    translated = proxy._translate_openai_to_anthropic(
        {
            "model": "MiniMax-M2.7",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        }
    )

    assert translated["max_tokens"] == 4096


def test_minimax_translation_preserves_explicit_max_tokens():
    proxy = model_registry._MiniMaxClientProxy(api_key="test-key")
    translated = proxy._translate_openai_to_anthropic(
        {
            "model": "MiniMax-M2.7",
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": "hello"}],
        }
    )

    assert translated["max_tokens"] == 1200


def test_build_model_provider_policy_marks_deepseek_as_cache_friendly():
    policy = model_registry.build_model_provider_policy(
        {
            "provider": model_registry.DEEPSEEK_PROVIDER,
            "api_model": "deepseek-chat",
        }
    )

    assert policy["supports_prompt_cache"]
    assert policy["prefers_cache_friendly_prefix"]
    assert policy["cache_context"] == {"supports_prompt_cache": True, "strategy": "implicit"}


def test_openrouter_tool_choice_auto_fallback_policy_is_centralized():
    request_kwargs = {
        "tool_choice": {"type": "function", "function": {"name": "ask_clarifying_question"}},
        "parallel_tool_calls": False,
    }
    error_text = "Error code: 404 - {'error': {'message': 'No endpoints found that support the provided tool_choice value.', 'code': 404}}"
    openrouter_target = {
        "policy": model_registry.build_model_provider_policy(
            {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "anthropic/claude-sonnet-4.5",
            }
        )
    }
    deepseek_target = {
        "policy": model_registry.build_model_provider_policy(
            {
                "provider": model_registry.DEEPSEEK_PROVIDER,
                "api_model": "deepseek-chat",
            }
        )
    }

    assert model_registry.should_retry_model_target_tool_choice_with_auto(
        error_text,
        request_kwargs,
        openrouter_target,
    )
    assert not model_registry.should_retry_model_target_tool_choice_with_auto(
        error_text,
        request_kwargs,
        deepseek_target,
    )

    openrouter_fallback = model_registry.build_model_target_tool_choice_fallback_request(
        request_kwargs,
        openrouter_target,
    )
    deepseek_fallback = model_registry.build_model_target_tool_choice_fallback_request(
        request_kwargs,
        deepseek_target,
    )

    assert openrouter_fallback["tool_choice"] == "auto"
    assert "parallel_tool_calls" not in openrouter_fallback
    assert deepseek_fallback is None


class TestOpenRouterModelRegistry:
    def test_create_app_refreshes_openrouter_headers_from_persisted_settings(self, app):
        save_app_settings(
            {
                "openrouter_http_referer": "https://example.com/runtime",
                "openrouter_app_title": "Runtime Header Test",
            }
        )

        create_app(database_path=app.config["DATABASE_PATH"])
        client = model_registry.get_provider_client(model_registry.OPENROUTER_PROVIDER)

        assert client._base_kwargs.get("default_headers") == {
            "HTTP-Referer": "https://example.com/runtime",
            "X-Title": "Runtime Header Test",
        }

    def test_settings_patch_rejects_invalid_openrouter_provider_slug(self, client):
        response = client.patch(
            "/api/settings",
            json={
                "custom_models": [
                    {
                        "name": "Claude Sonnet 4.5",
                        "api_model": "anthropic/claude-sonnet-4.5",
                        "provider_slug": "Invalid Provider!",
                        "supports_tools": True,
                    }
                ]
            },
        )

        assert response.status_code == 400
        assert "provider_slug" in response.get_json()["error"]

    def test_resolve_model_target_builds_openrouter_provider_and_reasoning_overrides(self):
        settings = {
            "custom_models": [
                {
                    "name": "Claude Sonnet 4.5",
                    "api_model": "anthropic/claude-sonnet-4.5",
                    "provider_slug": "deepinfra/turbo",
                    "reasoning_mode": "disabled",
                    "reasoning_effort": "high",
                    "supports_tools": True,
                    "supports_vision": True,
                    "supports_structured_outputs": True,
                }
            ]
        }

        with patch("model_registry.get_provider_client", return_value=SimpleNamespace()):
            target = resolve_model_target("openrouter:anthropic/claude-sonnet-4.5", settings)

        assert target["extra_body"] == {
            "provider": {"sort": "throughput", "only": ["deepinfra/turbo"], "allow_fallbacks": False},
            "reasoning": {"effort": "none"},
        }

    def test_resolve_model_target_defaults_openrouter_requests_to_throughput_sorting(self):
        settings = {
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

        with patch("model_registry.get_provider_client", return_value=SimpleNamespace()):
            target = resolve_model_target("openrouter:anthropic/claude-sonnet-4.5", settings)

        assert target["extra_body"] == {"provider": {"sort": "throughput"}}

    def test_resolve_model_target_disables_openrouter_prompt_cache_when_setting_is_off(self):
        settings = {
            "openrouter_prompt_cache_enabled": False,
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

        with patch("model_registry.get_provider_client", return_value=SimpleNamespace()):
            target = resolve_model_target("openrouter:anthropic/claude-sonnet-4.5", settings)

        assert target["extra_body"] == {"provider": {"sort": "throughput"}}

    def test_apply_model_target_request_options_adds_gemini_cache_breakpoint(self):
        request_kwargs = {
            "messages": [
                {"role": "system", "content": "Reference context. " * 1000},
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "google/gemini-2.5-pro",
            },
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        assert merged["extra_body"] == {"provider": {"sort": "throughput"}}
        assert isinstance(merged["messages"][0]["content"], list)
        assert merged["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert merged["messages"][1]["content"] == "Summarize the stable prefix."

    def test_apply_model_target_request_options_prefers_leading_stable_gemini_system_message(self):
        request_kwargs = {
            "messages": [
                {"role": "system", "content": "Stable prefix. " * 1000},
                {"role": "user", "content": "Earlier question."},
                {"role": "assistant", "content": "Earlier answer."},
                {"role": "system", "content": "Dynamic current-turn injection. " * 1000},
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "google/gemini-2.5-pro",
            },
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        assert isinstance(merged["messages"][0]["content"], list)
        assert merged["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert merged["messages"][3]["content"] == request_kwargs["messages"][3]["content"]

    def test_apply_model_target_request_options_does_not_fallback_to_later_gemini_system_message(self):
        request_kwargs = {
            "messages": [
                {"role": "system", "content": "Short stable prefix."},
                {"role": "user", "content": "Earlier question."},
                {"role": "assistant", "content": "Earlier answer."},
                {"role": "system", "content": "Later stable prefix. " * 1000},
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "google/gemini-2.5-pro",
            },
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        assert merged["messages"][0]["content"] == request_kwargs["messages"][0]["content"]
        assert merged["messages"][3]["content"] == request_kwargs["messages"][3]["content"]

    def test_apply_model_target_request_options_skips_small_anthropic_prefix(self):
        request_kwargs = {
            "messages": [
                {"role": "system", "content": "Reference context. " * 300},
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "anthropic/claude-sonnet-4.5",
            },
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        first_content = merged["messages"][0]["content"]
        if isinstance(first_content, list):
            assert first_content[0].get("type") == "text"
            assert "Reference context." in first_content[0].get("text", "")
        else:
            assert first_content == request_kwargs["messages"][0]["content"]
        assert merged["extra_body"] == {"provider": {"sort": "throughput"}}

    def test_apply_model_target_request_options_adds_anthropic_cache_breakpoint_for_long_prefix(self):
        request_kwargs = {
            "messages": [
                {"role": "system", "content": "Reference context. " * 1000},
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "anthropic/claude-sonnet-4.5",
            },
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        assert isinstance(merged["messages"][0]["content"], list)
        assert merged["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert merged["extra_body"] == {"provider": {"sort": "throughput"}}

    def test_apply_model_target_request_options_adds_anthropic_cache_breakpoint_with_1h_ttl(self):
        request_kwargs = {
            "messages": [
                {"role": "system", "content": "Reference context. " * 1000},
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "anthropic/claude-sonnet-4.5",
            },
            "settings": {"openrouter_anthropic_cache_ttl": "1h"},
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        assert isinstance(merged["messages"][0]["content"], list)
        assert merged["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    def test_apply_model_target_request_options_skips_anthropic_breakpoint_for_volatile_runtime_block(self):
        request_kwargs = {
            "messages": [
                {"role": "system", "content": "Short stable prefix."},
                {"role": "system", "content": "## Current Date and Time\n- Time: 21:40\n\n" + ("Dynamic runtime context. " * 1200)},
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "anthropic/claude-sonnet-4.5",
            },
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        assert merged["messages"][0]["content"] == request_kwargs["messages"][0]["content"]
        assert merged["messages"][1]["content"] == request_kwargs["messages"][1]["content"]

    def test_apply_model_target_request_options_avoids_second_anthropic_breakpoint_on_volatile_runtime_block(self):
        request_kwargs = {
            "messages": [
                {"role": "system", "content": "Stable prefix. " * 1000},
                {"role": "system", "content": "## Tool Execution History\n- search_web [done]: old query\n\n" + ("Dynamic runtime context. " * 1000)},
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "anthropic/claude-sonnet-4.5",
            },
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        assert isinstance(merged["messages"][0]["content"], list)
        assert merged["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert merged["messages"][1]["content"] == request_kwargs["messages"][1]["content"]

    def test_apply_model_target_request_options_skips_small_block_form_gemini_prefix(self):
        request_kwargs = {
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "Short stable prefix."}],
                },
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "google/gemini-2.5-pro",
            },
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        assert merged["messages"][0]["content"] == request_kwargs["messages"][0]["content"]

    def test_apply_model_target_request_options_leaves_non_gemini_google_models_unchanged(self):
        request_kwargs = {
            "messages": [
                {"role": "system", "content": "Reference context. " * 1000},
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "google/gemma-3-27b-it",
            },
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        assert merged["messages"][0]["content"] == request_kwargs["messages"][0]["content"]
        assert merged["extra_body"] == {"provider": {"sort": "throughput"}}

    def test_apply_model_target_request_options_skips_gemini_cache_breakpoint_when_setting_is_off(self):
        request_kwargs = {
            "messages": [
                {"role": "system", "content": "Reference context. " * 1000},
                {"role": "user", "content": "Summarize the stable prefix."},
            ]
        }
        target = {
            "record": {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "google/gemini-2.5-pro",
            },
            "settings": {"openrouter_prompt_cache_enabled": False},
            "extra_body": {"provider": {"sort": "throughput"}},
        }

        merged = model_registry.apply_model_target_request_options(request_kwargs, target)

        assert merged["messages"][0]["content"] == request_kwargs["messages"][0]["content"]
        assert merged["extra_body"] == {"provider": {"sort": "throughput"}}

    def test_build_openrouter_cache_estimate_context_supports_implicit_deepseek_caching(self):
        messages = [
            {"role": "system", "content": "Stable instructions."},
            {"role": "user", "content": "Question about the same document."},
        ]

        cache_context = model_registry.build_openrouter_cache_estimate_context(
            messages,
            {
                "provider": model_registry.OPENROUTER_PROVIDER,
                "api_model": "deepseek/deepseek-chat",
            },
            {"openrouter_prompt_cache_enabled": True},
        )

        assert cache_context["supports_prompt_cache"]
        assert cache_context["strategy"] == "implicit"
        assert '"role":"system"' in cache_context["cacheable_text"]

    def test_openrouter_client_uses_proxy_candidates_before_direct_fallback(self):
        attempts = []

        def openai_factory(**kwargs):
            http_client = kwargs.get("http_client")

            def on_create(*args, **inner_kwargs):
                del args, inner_kwargs
                proxy = http_client.proxy if http_client else None
                attempts.append(proxy)
                if proxy:
                    raise RuntimeError("proxy failed")
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

            return CallbackOpenAI(http_client=http_client, on_create=on_create)

        settings = {
            "custom_models": [
                {
                    "name": "Claude Sonnet 4.5",
                    "api_model": "anthropic/claude-sonnet-4.5",
                    "provider_slug": "deepinfra/turbo",
                    "reasoning_mode": "disabled",
                    "reasoning_effort": "high",
                    "supports_tools": True,
                    "supports_vision": True,
                    "supports_structured_outputs": True,
                }
            ]
        }

        model_registry.get_provider_client.cache_clear()
        try:
            with patch("web_tools.get_proxy_candidates_for_operation", return_value=["http://proxy.example:8080", None]), patch(
                "model_registry.httpx.Client",
                side_effect=lambda *args, **kwargs: CallbackHttpClient(*args, **kwargs),
            ), patch("model_registry.OpenAI", side_effect=openai_factory):
                target = resolve_model_target("openrouter:anthropic/claude-sonnet-4.5", settings)
                response = target["client"].chat.completions.create(model=target["api_model"], messages=[])
        finally:
            model_registry.get_provider_client.cache_clear()

        assert attempts == ["http://proxy.example:8080", None]
        assert response.choices[0].message.content == "ok"

    def test_openrouter_stream_wrapper_defers_client_close_until_stream_close(self):
        import gc

        close_events = []

        def http_client_factory(*args, **kwargs):
            del args
            return CallbackHttpClient(**kwargs, on_close=lambda: close_events.append("http"))

        def openai_factory(**kwargs):
            return CallbackOpenAI(
                http_client=kwargs.get("http_client"),
                on_create=lambda *args, **inner_kwargs: StaticStream(
                    [SimpleNamespace(choices=[])],
                    on_close=lambda: close_events.append("stream"),
                ),
                on_close=lambda: close_events.append("client"),
            )

        model_registry.get_provider_client.cache_clear()
        try:
            with patch("web_tools.get_proxy_candidates_for_operation", return_value=[None]), patch(
                "model_registry.httpx.Client",
                side_effect=http_client_factory,
            ), patch("model_registry.OpenAI", side_effect=openai_factory):
                client = model_registry.get_provider_client(model_registry.OPENROUTER_PROVIDER)
                response = client.chat.completions.create(model="anthropic/claude-sonnet-4.5", messages=[], stream=True)
                assert close_events == []
                list(response)
                assert close_events == ["stream"]
                del response
                gc.collect()
                assert close_events == ["stream", "client", "http"]
        finally:
            model_registry.get_provider_client.cache_clear()

    def test_openrouter_stream_retries_next_proxy_when_first_chunk_read_fails(self):
        import gc

        attempts = []
        close_events = []

        class BrokenStream:
            def __init__(self, label):
                self.label = label

            def __iter__(self):
                raise OSError(9, "Bad file descriptor")
                yield

            def close(self):
                close_events.append(f"stream:{self.label}")

        class WorkingStream:
            def __iter__(self):
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))])

            def close(self):
                close_events.append("stream:direct")


        def http_client_factory(*args, **kwargs):
            del args
            client = CallbackHttpClient(**kwargs)

            def on_close():
                close_events.append(f"http:{client.proxy or 'direct'}")

            client._on_close = on_close
            return client

        def openai_factory(**kwargs):
            http_client = kwargs.get("http_client")

            def on_create(*args, **inner_kwargs):
                del args, inner_kwargs
                proxy = http_client.proxy if http_client else None
                attempts.append(proxy)
                if proxy:
                    return BrokenStream("proxy")
                return WorkingStream()

            def on_close():
                label = http_client.proxy if http_client and http_client.proxy else "direct"
                close_events.append(f"client:{label}")

            return CallbackOpenAI(http_client=http_client, on_create=on_create, on_close=on_close)

        model_registry.get_provider_client.cache_clear()
        try:
            with patch("web_tools.get_proxy_candidates_for_operation", return_value=["http://proxy.example:8080", None]), patch(
                "model_registry.httpx.Client",
                side_effect=http_client_factory,
            ), patch("model_registry.OpenAI", side_effect=openai_factory):
                client = model_registry.get_provider_client(model_registry.OPENROUTER_PROVIDER)
                response = client.chat.completions.create(model="anthropic/claude-sonnet-4.5", messages=[], stream=True)
                chunks = list(response)
                assert attempts == ["http://proxy.example:8080", None]
                assert len(chunks) == 1
                assert close_events[:3] == ["stream:proxy", "client:http://proxy.example:8080", "http:http://proxy.example:8080"]
                del response
                gc.collect()
                assert close_events == [
                    "stream:proxy",
                    "client:http://proxy.example:8080",
                    "http:http://proxy.example:8080",
                    "stream:direct",
                    "client:direct",
                    "http:direct",
                ]
        finally:
            model_registry.get_provider_client.cache_clear()

    def test_openrouter_proxy_scope_disabled_forces_direct_connection(self):
        attempts = []

        def openai_factory(**kwargs):
            http_client = kwargs.get("http_client")
            return CallbackOpenAI(
                http_client=http_client,
                on_create=lambda *args, **inner_kwargs: (
                    attempts.append(http_client.proxy if http_client else None)
                    or SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
                ),
            )

        save_app_settings({"proxy_enabled_operations": json.dumps([PROXY_OPERATION_FETCH_URL], ensure_ascii=False)})
        model_registry.get_provider_client.cache_clear()
        try:
            with patch("web_tools.get_proxy_candidates", return_value=["http://proxy.example:8080", None]), patch(
                "model_registry.httpx.Client",
                side_effect=lambda *args, **kwargs: CallbackHttpClient(*args, **kwargs),
            ), patch("model_registry.OpenAI", side_effect=openai_factory):
                client = model_registry.get_provider_client(model_registry.OPENROUTER_PROVIDER)
                response = client.chat.completions.create(model="anthropic/claude-sonnet-4.5", messages=[])

            assert response.choices[0].message.content == "ok"
            assert attempts == [None]
        finally:
            model_registry.get_provider_client.cache_clear()

    def test_openrouter_stream_wrapper_swallows_close_errors(self):
        import gc

        close_events = []

        def http_client_factory(*args, **kwargs):
            del args

            def on_close():
                close_events.append("http")
                raise OSError(9, "Bad file descriptor")

            return CallbackHttpClient(**kwargs, on_close=on_close)

        def openai_factory(**kwargs):
            def stream_close():
                close_events.append("stream")
                raise OSError(9, "Bad file descriptor")

            def client_close():
                close_events.append("client")
                raise OSError(9, "Bad file descriptor")

            return CallbackOpenAI(
                http_client=kwargs.get("http_client"),
                on_create=lambda *args, **inner_kwargs: StaticStream([SimpleNamespace(choices=[])], on_close=stream_close),
                on_close=client_close,
            )

        model_registry.get_provider_client.cache_clear()
        try:
            with patch("web_tools.get_proxy_candidates_for_operation", return_value=[None]), patch(
                "model_registry.httpx.Client",
                side_effect=http_client_factory,
            ), patch("model_registry.OpenAI", side_effect=openai_factory):
                client = model_registry.get_provider_client(model_registry.OPENROUTER_PROVIDER)
                response = client.chat.completions.create(model="anthropic/claude-sonnet-4.5", messages=[], stream=True)
                list(response)
                assert close_events == ["stream"]
                del response
                gc.collect()
                assert close_events == ["stream", "client", "http"]
        finally:
            model_registry.get_provider_client.cache_clear()

    def test_operation_model_uses_configured_fallback_model(self):
        settings = {
            "operation_model_preferences": {"summarize": ""},
            "operation_model_fallback_preferences": {"summarize": ["deepseek-chat", "deepseek-reasoner"]},
        }

        assert get_operation_model("summarize", settings, fallback_model_id="deepseek-reasoner") == "deepseek-chat"

    def test_operation_model_candidates_preserve_configured_fallback_order(self):
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": ["deepseek-reasoner", "deepseek-chat"]},
            "sub_agent_retry_attempts": 0,
            "sub_agent_timeout_seconds": 20,
        }

        assert get_operation_model_candidates("sub_agent", settings, fallback_model_id="deepseek-chat") == [
            "deepseek-reasoner",
            "deepseek-chat",
        ]

    def test_settings_fall_back_to_builtin_visible_models_when_stale_custom_order_breaks(self, client):
        response = client.patch(
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
                "visible_model_order": ["openrouter:anthropic/claude-sonnet-4.5"],
            },
        )
        assert response.status_code == 200

        response = client.patch(
            "/api/settings",
            json={"custom_models": []},
        )
        assert response.status_code == 200
        payload = response.get_json()

        assert payload["custom_models"] == []
        visible_model_order = payload["visible_model_order"]
        assert visible_model_order[:2] == ["deepseek-chat", "deepseek-reasoner"]
        assert "openrouter:anthropic/claude-sonnet-4.5" not in visible_model_order
