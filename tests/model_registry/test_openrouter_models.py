from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import model_registry
from app import create_app
from db import save_app_settings
from model_registry import get_operation_model, get_operation_model_candidates, resolve_model_target
from proxy_settings import PROXY_OPERATION_FETCH_URL
from tests.support.app_harness import BaseAppRoutesTestCase


class TestOpenRouterModelRegistry(BaseAppRoutesTestCase):
    def test_normalize_chat_parameter_overrides_accepts_known_fields(self):
        overrides = model_registry.normalize_chat_parameter_overrides(
            {"temperature": 0.6, "top_p": 0.9, "max_tokens": 300}
        )

        self.assertEqual(
            overrides,
            {"temperature": 0.6, "top_p": 0.9, "max_tokens": 300},
        )

    def test_normalize_chat_parameter_overrides_rejects_unknown_fields(self):
        with self.assertRaises(ValueError):
            model_registry.normalize_chat_parameter_overrides({"temperature": 0.6, "foo": 1})

    def test_apply_chat_parameter_overrides_merges_whitelisted_values(self):
        request_kwargs = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.7,
        }

        merged = model_registry.apply_chat_parameter_overrides(
            request_kwargs,
            {"temperature": 0.4, "top_p": 0.8, "max_tokens": 512},
        )

        self.assertEqual(merged["temperature"], 0.4)
        self.assertEqual(merged["top_p"], 0.8)
        self.assertEqual(merged["max_tokens"], 512)
        self.assertEqual(merged["messages"], request_kwargs["messages"])

    def test_build_model_provider_policy_marks_deepseek_as_cache_friendly(self):
        policy = model_registry.build_model_provider_policy(
            {
                "provider": model_registry.DEEPSEEK_PROVIDER,
                "api_model": "deepseek-chat",
            }
        )

        self.assertTrue(policy["supports_prompt_cache"])
        self.assertTrue(policy["prefers_cache_friendly_prefix"])
        self.assertEqual(policy["cache_context"], {"supports_prompt_cache": True, "strategy": "implicit"})

    def test_openrouter_tool_choice_auto_fallback_policy_is_centralized(self):
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

        self.assertTrue(
            model_registry.should_retry_model_target_tool_choice_with_auto(
                error_text,
                request_kwargs,
                openrouter_target,
            )
        )
        self.assertFalse(
            model_registry.should_retry_model_target_tool_choice_with_auto(
                error_text,
                request_kwargs,
                deepseek_target,
            )
        )

        openrouter_fallback = model_registry.build_model_target_tool_choice_fallback_request(
            request_kwargs,
            openrouter_target,
        )
        deepseek_fallback = model_registry.build_model_target_tool_choice_fallback_request(
            request_kwargs,
            deepseek_target,
        )

        self.assertEqual(openrouter_fallback["tool_choice"], "auto")
        self.assertNotIn("parallel_tool_calls", openrouter_fallback)
        self.assertIsNone(deepseek_fallback)

    def test_create_app_refreshes_openrouter_headers_from_persisted_settings(self):
        save_app_settings(
            {
                "openrouter_http_referer": "https://example.com/runtime",
                "openrouter_app_title": "Runtime Header Test",
            }
        )

        create_app(database_path=self.db_path)
        client = model_registry.get_provider_client(model_registry.OPENROUTER_PROVIDER)

        self.assertEqual(
            client._base_kwargs.get("default_headers"),
            {
                "HTTP-Referer": "https://example.com/runtime",
                "X-Title": "Runtime Header Test",
            },
        )

    def test_settings_patch_rejects_invalid_openrouter_provider_slug(self):
        response = self.client.patch(
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

        self.assertEqual(response.status_code, 400)
        self.assertIn("provider_slug", response.get_json()["error"])

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

        self.assertEqual(
            target["extra_body"],
            {
                "provider": {"sort": "throughput", "only": ["deepinfra/turbo"], "allow_fallbacks": False},
                "reasoning": {"effort": "none"},
            },
        )

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

        self.assertEqual(
            target["extra_body"],
            {
                "provider": {"sort": "throughput"},
            },
        )

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

        self.assertEqual(target["extra_body"], {"provider": {"sort": "throughput"}})

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

        self.assertEqual(merged["extra_body"], {"provider": {"sort": "throughput"}})
        self.assertIsInstance(merged["messages"][0]["content"], list)
        self.assertEqual(
            merged["messages"][0]["content"][0]["cache_control"],
            {"type": "ephemeral"},
        )
        self.assertEqual(merged["messages"][1]["content"], "Summarize the stable prefix.")

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

        self.assertIsInstance(merged["messages"][0]["content"], list)
        self.assertEqual(
            merged["messages"][0]["content"][0]["cache_control"],
            {"type": "ephemeral"},
        )
        self.assertEqual(merged["messages"][3]["content"], request_kwargs["messages"][3]["content"])

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

        self.assertEqual(merged["messages"][0]["content"], request_kwargs["messages"][0]["content"])
        self.assertEqual(merged["messages"][3]["content"], request_kwargs["messages"][3]["content"])

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

        self.assertEqual(merged["messages"][0]["content"], request_kwargs["messages"][0]["content"])
        self.assertEqual(merged["extra_body"], {"provider": {"sort": "throughput"}})

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

        self.assertIsInstance(merged["messages"][0]["content"], list)
        self.assertEqual(merged["messages"][0]["content"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(merged["extra_body"], {"provider": {"sort": "throughput"}})

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

        self.assertIsInstance(merged["messages"][0]["content"], list)
        self.assertEqual(
            merged["messages"][0]["content"][0]["cache_control"],
            {"type": "ephemeral", "ttl": "1h"},
        )

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

        self.assertEqual(merged["messages"][0]["content"], request_kwargs["messages"][0]["content"])
        self.assertEqual(merged["messages"][1]["content"], request_kwargs["messages"][1]["content"])

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

        self.assertIsInstance(merged["messages"][0]["content"], list)
        self.assertEqual(merged["messages"][0]["content"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(merged["messages"][1]["content"], request_kwargs["messages"][1]["content"])

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

        self.assertEqual(merged["messages"][0]["content"], request_kwargs["messages"][0]["content"])

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

        self.assertEqual(merged["messages"][0]["content"], request_kwargs["messages"][0]["content"])
        self.assertEqual(merged["extra_body"], {"provider": {"sort": "throughput"}})

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

        self.assertEqual(merged["messages"][0]["content"], request_kwargs["messages"][0]["content"])
        self.assertEqual(merged["extra_body"], {"provider": {"sort": "throughput"}})

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

        self.assertTrue(cache_context["supports_prompt_cache"])
        self.assertEqual(cache_context["strategy"], "implicit")
        self.assertIn('"role":"system"', cache_context["cacheable_text"])

    def test_openrouter_client_uses_proxy_candidates_before_direct_fallback(self):
        attempts = []

        class FakeHttpClient:
            def __init__(self, *args, **kwargs):
                self.proxy = kwargs.get("proxy")
                self.trust_env = kwargs.get("trust_env")

            def close(self):
                return None

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.http_client = kwargs.get("http_client")
                self.chat = SimpleNamespace(completions=self)

            def create(self, *args, **kwargs):
                proxy = self.http_client.proxy if self.http_client else None
                attempts.append(proxy)
                if proxy:
                    raise RuntimeError("proxy failed")
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

            def close(self):
                return None

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
                side_effect=lambda *args, **kwargs: FakeHttpClient(*args, **kwargs),
            ), patch("model_registry.OpenAI", side_effect=lambda **kwargs: FakeOpenAI(**kwargs)):
                target = resolve_model_target("openrouter:anthropic/claude-sonnet-4.5", settings)
                response = target["client"].chat.completions.create(model=target["api_model"], messages=[])
        finally:
            model_registry.get_provider_client.cache_clear()

        self.assertEqual(attempts, ["http://proxy.example:8080", None])
        self.assertEqual(response.choices[0].message.content, "ok")

    def test_openrouter_stream_wrapper_defers_client_close_until_stream_close(self):
        import gc

        close_events = []

        class FakeHttpClient:
            def __init__(self, *args, **kwargs):
                self.proxy = kwargs.get("proxy")

            def close(self):
                close_events.append("http")

        class FakeStream:
            def __iter__(self):
                yield SimpleNamespace(choices=[])

            def close(self):
                close_events.append("stream")

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.http_client = kwargs.get("http_client")
                self.chat = SimpleNamespace(completions=self)

            def create(self, *args, **kwargs):
                return FakeStream()

            def close(self):
                close_events.append("client")

        model_registry.get_provider_client.cache_clear()
        try:
            with patch("web_tools.get_proxy_candidates_for_operation", return_value=[None]), patch(
                "model_registry.httpx.Client",
                side_effect=lambda *args, **kwargs: FakeHttpClient(*args, **kwargs),
            ), patch("model_registry.OpenAI", side_effect=lambda **kwargs: FakeOpenAI(**kwargs)):
                client = model_registry.get_provider_client(model_registry.OPENROUTER_PROVIDER)
                response = client.chat.completions.create(model="anthropic/claude-sonnet-4.5", messages=[], stream=True)
                self.assertEqual(close_events, [])
                list(response)
                self.assertEqual(close_events, ["stream"])
                del response
                gc.collect()
                self.assertEqual(close_events, ["stream", "client", "http"])
        finally:
            model_registry.get_provider_client.cache_clear()

    def test_openrouter_stream_retries_next_proxy_when_first_chunk_read_fails(self):
        import gc

        attempts = []
        close_events = []

        class FakeHttpClient:
            def __init__(self, *args, **kwargs):
                self.proxy = kwargs.get("proxy")

            def close(self):
                close_events.append(f"http:{self.proxy or 'direct'}")

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

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.http_client = kwargs.get("http_client")
                self.chat = SimpleNamespace(completions=self)

            def create(self, *args, **kwargs):
                proxy = self.http_client.proxy if self.http_client else None
                attempts.append(proxy)
                if proxy:
                    return BrokenStream("proxy")
                return WorkingStream()

            def close(self):
                label = self.http_client.proxy if self.http_client and self.http_client.proxy else "direct"
                close_events.append(f"client:{label}")

        model_registry.get_provider_client.cache_clear()
        try:
            with patch("web_tools.get_proxy_candidates_for_operation", return_value=["http://proxy.example:8080", None]), patch(
                "model_registry.httpx.Client",
                side_effect=lambda *args, **kwargs: FakeHttpClient(*args, **kwargs),
            ), patch("model_registry.OpenAI", side_effect=lambda **kwargs: FakeOpenAI(**kwargs)):
                client = model_registry.get_provider_client(model_registry.OPENROUTER_PROVIDER)
                response = client.chat.completions.create(model="anthropic/claude-sonnet-4.5", messages=[], stream=True)
                chunks = list(response)
                self.assertEqual(attempts, ["http://proxy.example:8080", None])
                self.assertEqual(len(chunks), 1)
                self.assertEqual(close_events[:3], ["stream:proxy", "client:http://proxy.example:8080", "http:http://proxy.example:8080"])
                del response
                gc.collect()
                self.assertEqual(
                    close_events,
                    [
                        "stream:proxy",
                        "client:http://proxy.example:8080",
                        "http:http://proxy.example:8080",
                        "stream:direct",
                        "client:direct",
                        "http:direct",
                    ],
                )
        finally:
            model_registry.get_provider_client.cache_clear()

    def test_openrouter_proxy_scope_disabled_forces_direct_connection(self):
        attempts = []

        class FakeHttpClient:
            def __init__(self, *args, **kwargs):
                self.proxy = kwargs.get("proxy")

            def close(self):
                return None

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.http_client = kwargs.get("http_client")
                self.chat = SimpleNamespace(completions=self)

            def create(self, *args, **kwargs):
                attempts.append(self.http_client.proxy if self.http_client else None)
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

            def close(self):
                return None

        save_app_settings({"proxy_enabled_operations": json.dumps([PROXY_OPERATION_FETCH_URL], ensure_ascii=False)})
        model_registry.get_provider_client.cache_clear()
        try:
            with patch("web_tools.get_proxy_candidates", return_value=["http://proxy.example:8080", None]), patch(
                "model_registry.httpx.Client",
                side_effect=lambda *args, **kwargs: FakeHttpClient(*args, **kwargs),
            ), patch("model_registry.OpenAI", side_effect=lambda **kwargs: FakeOpenAI(**kwargs)):
                client = model_registry.get_provider_client(model_registry.OPENROUTER_PROVIDER)
                response = client.chat.completions.create(model="anthropic/claude-sonnet-4.5", messages=[])

            self.assertEqual(response.choices[0].message.content, "ok")
            self.assertEqual(attempts, [None])
        finally:
            model_registry.get_provider_client.cache_clear()

    def test_openrouter_stream_wrapper_swallows_close_errors(self):
        import gc

        close_events = []

        class FakeHttpClient:
            def __init__(self, *args, **kwargs):
                self.proxy = kwargs.get("proxy")

            def close(self):
                close_events.append("http")
                raise OSError(9, "Bad file descriptor")

        class FakeStream:
            def __iter__(self):
                yield SimpleNamespace(choices=[])

            def close(self):
                close_events.append("stream")
                raise OSError(9, "Bad file descriptor")

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.http_client = kwargs.get("http_client")
                self.chat = SimpleNamespace(completions=self)

            def create(self, *args, **kwargs):
                return FakeStream()

            def close(self):
                close_events.append("client")
                raise OSError(9, "Bad file descriptor")

        model_registry.get_provider_client.cache_clear()
        try:
            with patch("web_tools.get_proxy_candidates_for_operation", return_value=[None]), patch(
                "model_registry.httpx.Client",
                side_effect=lambda *args, **kwargs: FakeHttpClient(*args, **kwargs),
            ), patch("model_registry.OpenAI", side_effect=lambda **kwargs: FakeOpenAI(**kwargs)):
                client = model_registry.get_provider_client(model_registry.OPENROUTER_PROVIDER)
                response = client.chat.completions.create(model="anthropic/claude-sonnet-4.5", messages=[], stream=True)
                list(response)
                self.assertEqual(close_events, ["stream"])
                del response
                gc.collect()
                self.assertEqual(close_events, ["stream", "client", "http"])
        finally:
            model_registry.get_provider_client.cache_clear()

    def test_operation_model_uses_configured_fallback_model(self):
        settings = {
            "operation_model_preferences": {"summarize": ""},
            "operation_model_fallback_preferences": {"summarize": ["deepseek-chat", "deepseek-reasoner"]},
        }

        self.assertEqual(get_operation_model("summarize", settings, fallback_model_id="deepseek-reasoner"), "deepseek-chat")

    def test_operation_model_candidates_preserve_configured_fallback_order(self):
        settings = {
            "operation_model_preferences": {"sub_agent": ""},
            "operation_model_fallback_preferences": {"sub_agent": ["deepseek-reasoner", "deepseek-chat"]},
            "sub_agent_retry_attempts": 0,
            "sub_agent_timeout_seconds": 20,
        }

        self.assertEqual(
            get_operation_model_candidates("sub_agent", settings, fallback_model_id="deepseek-chat"),
            ["deepseek-reasoner", "deepseek-chat"],
        )

    def test_settings_fall_back_to_builtin_visible_models_when_stale_custom_order_breaks(self):
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
                "visible_model_order": ["openrouter:anthropic/claude-sonnet-4.5"],
            },
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.patch(
            "/api/settings",
            json={"custom_models": []},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload["custom_models"], [])
        self.assertEqual(payload["visible_model_order"], ["deepseek-chat", "deepseek-reasoner"])
