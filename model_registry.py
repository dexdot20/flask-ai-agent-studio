from __future__ import annotations

import json
import re
import weakref
from functools import lru_cache
from typing import Any

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from proxy_settings import PROXY_OPERATION_OPENROUTER
from token_utils import estimate_text_tokens

load_dotenv()

DEEPSEEK_PROVIDER = "deepseek"
OPENROUTER_PROVIDER = "openrouter"
MINIMAX_PROVIDER = "minimax"
OPENROUTER_MODEL_PREFIX = "openrouter:"
OPENROUTER_REASONING_MODE_DEFAULT = "default"
OPENROUTER_REASONING_MODE_ENABLED = "enabled"
OPENROUTER_REASONING_MODE_DISABLED = "disabled"
OPENROUTER_REASONING_MODES = {
    OPENROUTER_REASONING_MODE_DEFAULT,
    OPENROUTER_REASONING_MODE_ENABLED,
    OPENROUTER_REASONING_MODE_DISABLED,
}
OPENROUTER_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
OPENROUTER_MODEL_VARIANT_SEPARATOR = "@@"
OPENROUTER_MODEL_VARIANT_PART_SEPARATOR = ";"
OPENROUTER_MODEL_VARIANT_KEY_VALUE_SEPARATOR = "="
DEFAULT_CHAT_MODEL = "deepseek-chat"
DEFAULT_IMAGE_PROCESSING_METHOD = "auto"
IMAGE_PROCESSING_METHODS = {"auto", "llm_helper", "llm_direct", "local_ocr"}
MODEL_OPERATION_KEYS = (
    "summarize",
    "fetch_summarize",
    "fix_text",
    "generate_title",
    "upload_metadata",
    "sub_agent",
)
DEFAULT_OPERATION_MODEL_PREFERENCES = {key: "" for key in MODEL_OPERATION_KEYS}
DEFAULT_OPERATION_MODEL_FALLBACK_PREFERENCES = {key: [] for key in MODEL_OPERATION_KEYS}
CHAT_PARAMETER_OVERRIDE_SPECS = {
    "temperature": {
        "type": "float",
        "min": 0.0,
        "max": 2.0,
        "label": "Temperature",
        "description": "Controls creativity. Lower values are steadier, higher values are more varied.",
        "default": 1.0,
    },
    "top_p": {
        "type": "float",
        "min": 0.0,
        "max": 1.0,
        "label": "Top P",
        "description": "Limits sampling to the most likely probability mass.",
        "default": 1.0,
    },
    "max_tokens": {
        "type": "int",
        "min": 1,
        "max": 131_072,
        "label": "Max Tokens",
        "description": "Upper bound for how many tokens the next reply may generate.",
        "default": None,
    },
}
CHAT_PARAMETER_OVERRIDE_KEYS = tuple(CHAT_PARAMETER_OVERRIDE_SPECS.keys())
_OPENROUTER_PROVIDER_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,199}$")
_OPENROUTER_GEMINI_CACHE_BREAKPOINT_MIN_TOKENS_DEFAULT = 1028
_OPENROUTER_GEMINI_CACHE_BREAKPOINT_MIN_TOKENS_PRO = 2048
_OPENROUTER_IMPLICIT_PROMPT_CACHE_MODEL_PREFIXES = (
    "deepseek/",
    "openai/",
    "x-ai/",
    "grok/",
    "moonshotai/",
    "groq/",
)
_OPENROUTER_ANTHROPIC_CACHE_MAX_BREAKPOINTS = 2
_OPENROUTER_ANTHROPIC_VOLATILE_RUNTIME_MARKERS = (
    "## current date and time",
    "authoritative current time",
    "## tool execution history",
    "## active tools this turn",
)
_MINIMAX_REQUIRED_MAX_TOKENS_DEFAULT = 4_096


def _openrouter_anthropic_cache_min_tokens(api_model: str) -> int:
    """Return the minimum token threshold for Anthropic cache breakpoints.

    Thresholds per model family (per OpenRouter/Anthropic documentation):
    - 4096 tokens: claude-opus-4-5, claude-opus-4-6, claude-haiku-4-5
    - 2048 tokens: claude-sonnet-4-6, claude-haiku-3-5
    - 1024 tokens: all other Anthropic models
    """
    model_lower = api_model.lower()
    if any(s in model_lower for s in ("claude-opus-4-5", "claude-opus-4-6", "claude-haiku-4-5")):
        return 4096
    if any(s in model_lower for s in ("claude-sonnet-4-6", "claude-haiku-3-5")):
        return 2048
    return 1024


def _is_openrouter_prompt_cache_enabled(settings: dict[str, Any] | None) -> bool:
    if not isinstance(settings, dict):
        return True
    raw_value = settings.get("openrouter_prompt_cache_enabled")
    if raw_value is None:
        return True
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


class _OpenRouterChatCompletionsProxy:
    def __init__(self, owner: "_OpenRouterClientProxy"):
        self._owner = owner

    def create(self, *args, **kwargs):
        return self._owner._create_chat_completion(*args, **kwargs)


class _OpenRouterChatProxy:
    def __init__(self, owner: "_OpenRouterClientProxy"):
        self.completions = _OpenRouterChatCompletionsProxy(owner)


class _ManagedChatCompletionResponse:
    def __init__(self, response, iterator=None, prefetched_chunks=None, retained_resources=None):
        self._response = response
        self._iterator = iterator
        self._prefetched_chunks = list(prefetched_chunks or [])
        self._closed = False
        self._retained_resources = tuple(retained_resources or ())
        if len(self._retained_resources) >= 2:
            self._resource_finalizer = weakref.finalize(
                self,
                _close_openrouter_client_resources,
                self._retained_resources[0],
                self._retained_resources[1],
            )
        else:
            self._resource_finalizer = None

    def __iter__(self):
        try:
            if self._iterator is None:
                self._iterator = iter(self._response)
            while self._prefetched_chunks:
                yield self._prefetched_chunks.pop(0)
            for chunk in self._iterator:
                yield chunk
        finally:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        close_response = getattr(self._response, "close", None)
        if callable(close_response):
            try:
                close_response()
            except Exception:
                pass
            return

    def __getattr__(self, name: str):
        return getattr(self._response, name)


def _close_openrouter_client_resources(client: OpenAI | None, http_client: httpx.Client | None) -> None:
    try:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    finally:
        if http_client is not None:
            try:
                http_client.close()
            except Exception:
                pass


def _close_chat_completion_response(response) -> None:
    if response is None:
        return
    close_response = getattr(response, "close", None)
    if callable(close_response):
        try:
            close_response()
        except Exception:
            pass


class _OpenRouterClientProxy:
    def __init__(self, base_kwargs: dict[str, Any]):
        self._base_kwargs = dict(base_kwargs)
        self.chat = _OpenRouterChatProxy(self)

    def _build_client(self, proxy: str | None) -> tuple[OpenAI, httpx.Client]:
        http_client = httpx.Client(proxy=proxy, trust_env=False) if proxy else httpx.Client(trust_env=False)
        client_kwargs = dict(self._base_kwargs)
        client_kwargs["http_client"] = http_client
        client = OpenAI(**client_kwargs)
        return client, http_client

    def _create_chat_completion(self, *args, **kwargs):
        from web_tools import get_proxy_candidates_for_operation

        last_error: Exception | None = None
        for proxy in get_proxy_candidates_for_operation(PROXY_OPERATION_OPENROUTER, include_direct_fallback=True):
            client = None
            http_client = None
            response = None
            try:
                client, http_client = self._build_client(proxy)
                response = client.chat.completions.create(*args, **kwargs)
                if kwargs.get("stream") is True:
                    iterator = iter(response)
                    prefetched_chunks = []
                    try:
                        first_chunk = next(iterator)
                    except StopIteration:
                        pass
                    else:
                        prefetched_chunks.append(first_chunk)
                    managed_response = _ManagedChatCompletionResponse(
                        response,
                        iterator=iterator,
                        prefetched_chunks=prefetched_chunks,
                        retained_resources=(client, http_client),
                    )
                    client = None
                    http_client = None
                    response = None
                    return managed_response
                return response
            except Exception as error:
                last_error = error
                _close_chat_completion_response(response)
            finally:
                if client is not None:
                    client.close()
                if http_client is not None:
                    http_client.close()

        if last_error is not None:
            raise last_error
        raise RuntimeError("OpenRouter request failed without a recorded error.")


class _MiniMaxDelta:
    """Mimics OpenAI chat.completion.delta for MiniMax streaming responses."""

    def __init__(
        self,
        content: str = "",
        reasoning_content: str = "",
        tool_calls: list | None = None,
    ):
        self.content = content
        self.reasoning_content = reasoning_content
        self.tool_calls = tool_calls or []


class _MiniMaxChoiceDelta:
    """Mimics OpenAI chat.completion.chunk.choice[0].delta for MiniMax."""

    def __init__(
        self,
        content: str = "",
        reasoning_content: str = "",
        tool_calls: list | None = None,
    ):
        self.delta = _MiniMaxDelta(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
        )


class _MiniMaxChunk:
    """Mimics OpenAI chat.completion.chunk for MiniMax streaming responses.

    Translates Anthropic SDK streaming events to OpenAI-compatible format.
    """

    def __init__(
        self,
        content: str = "",
        reasoning_content: str = "",
        index: int = 0,
        tool_calls: list | None = None,
    ):
        self.choices = [
            _MiniMaxChoiceDelta(
                content=content,
                reasoning_content=reasoning_content,
                tool_calls=tool_calls,
            )
        ]
        self.index = index

    @property
    def usage(self) -> None:
        """Per-chunk usage is not available; usage is captured at stream end."""
        return None


class _MiniMaxStreamIterator:
    """Iterator that translates Anthropic streaming events to OpenAI-compatible chunks."""

    def __init__(self, anthropic_stream):
        self._anthropic_stream = anthropic_stream
        self._closed = False
        # Track tool use state across streaming events
        self._tool_use_state: dict[int, dict] = {}
        # Capture usage from message_delta events
        self._usage: dict | None = None

    def __iter__(self):
        return self

    def __next__(self):
        while True:
            chunk = next(self._anthropic_stream)
            self._closed = False  # will be set to True on close

            if chunk.type == "content_block_start":
                content_block = getattr(chunk, "content_block", None) or {}
                block_type = (
                    content_block.get("type", "")
                    if isinstance(content_block, dict)
                    else getattr(content_block, "type", "")
                )
                index = chunk.index or 0
                if block_type == "text":
                    # Initial text block - yield empty delta to set up the structure
                    return _MiniMaxChunk(content="", reasoning_content="", index=index)
                elif block_type == "thinking":
                    # Initial thinking block - yield empty reasoning_content
                    return _MiniMaxChunk(content="", reasoning_content="", index=index)
                elif block_type == "tool_use":
                    # Tool use block - extract tool id and name
                    tool_name = ""
                    tool_id = ""
                    if isinstance(content_block, dict):
                        tool_name = content_block.get("name", "")
                        tool_id = content_block.get("id", "")
                    else:
                        tool_name = getattr(content_block, "name", "")
                        tool_id = getattr(content_block, "id", "")
                    self._tool_use_state[index] = {"name": tool_name, "id": tool_id, "arguments": ""}
                    # Emit initial tool_use structure
                    return _MiniMaxChunk(
                        content="",
                        reasoning_content="",
                        index=index,
                        tool_calls=[
                            {
                                "index": index,
                                "id": tool_id,
                                "function": {
                                    "name": tool_name,
                                    "arguments": "",
                                },
                            }
                        ],
                    )

            elif chunk.type == "content_block_delta":
                delta = getattr(chunk, "delta", None)
                if delta is None:
                    continue
                delta_type = getattr(delta, "type", "")
                index = chunk.index or 0

                if delta_type == "thinking_delta":
                    thinking_text = getattr(delta, "thinking", "") or ""
                    return _MiniMaxChunk(content="", reasoning_content=thinking_text, index=index)
                elif delta_type == "text_delta":
                    text = getattr(delta, "text", "") or ""
                    return _MiniMaxChunk(content=text, reasoning_content="", index=index)
                elif delta_type == "input_json_delta":
                    # Tool use JSON delta - accumulate partial JSON
                    partial_json = getattr(delta, "partial_json", "") or ""
                    if index in self._tool_use_state:
                        self._tool_use_state[index]["arguments"] += partial_json
                    # Emit tool_calls with accumulated arguments
                    tool_call = {
                        "index": index,
                        "function": {
                            "name": "",
                            "arguments": partial_json,
                        },
                    }
                    if index in self._tool_use_state:
                        tool_call["id"] = self._tool_use_state[index].get("id", "")
                        tool_call["function"]["name"] = self._tool_use_state[index].get("name", "")
                    return _MiniMaxChunk(
                        content="",
                        reasoning_content="",
                        index=index,
                        tool_calls=[tool_call],
                    )

            elif chunk.type == "message_delta":
                # Capture usage from final message metadata
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "input_tokens", 0) or 0
                    output_tokens = getattr(usage, "output_tokens", 0) or 0
                    self._usage = {
                        "prompt_tokens": int(prompt_tokens),
                        "completion_tokens": int(output_tokens),
                        "total_tokens": int(prompt_tokens + output_tokens),
                    }
                continue

            elif chunk.type == "message_stop":
                raise StopIteration

        raise StopIteration

    @property
    def usage(self) -> _MiniMaxUsage | None:
        """Return captured usage after iteration completes."""
        if self._usage is None:
            return None
        return _MiniMaxUsage(
            prompt_tokens=self._usage["prompt_tokens"],
            completion_tokens=self._usage["completion_tokens"],
            total_tokens=self._usage["total_tokens"],
        )

    def close(self):
        self._closed = True
        close_method = getattr(self._anthropic_stream, "close", None)
        if callable(close_method):
            try:
                close_method()
            except Exception:
                pass


class _MiniMaxChatCompletionsProxy:
    """Exposes OpenAI-style chat.completions.create() interface for MiniMax."""

    def __init__(self, owner: "_MiniMaxClientProxy"):
        self._owner = owner

    def create(self, *args, **kwargs):
        return self._owner._create_chat_completion(*args, **kwargs)


class _MiniMaxChatProxy:
    def __init__(self, owner: "_MiniMaxClientProxy"):
        self.completions = _MiniMaxChatCompletionsProxy(owner)


class _MiniMaxClientProxy:
    """Wraps Anthropic SDK to expose OpenAI-compatible chat.completions interface.

    Translates OpenAI-format requests to Anthropic API calls and converts
    streaming responses back to OpenAI-compatible format.
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self.chat = _MiniMaxChatProxy(self)
        self._anthropic_client = None

    def _get_anthropic_client(self):
        if self._anthropic_client is None:
            import anthropic

            self._anthropic_client = anthropic.Anthropic(
                api_key=self._api_key,
                base_url="https://api.minimax.io/anthropic",
            )
        return self._anthropic_client

    def _translate_openai_to_anthropic(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Translate OpenAI-style kwargs to Anthropic API format."""
        import logging
        _logger = logging.getLogger(__name__)
        _logger.warning(f"[MiniMax Debug] Input kwargs keys: {list(kwargs.keys())}")

        translated: dict[str, Any] = {}

        def _coerce_positive_int(value, default: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return default
            return parsed if parsed > 0 else default

        # Model - direct mapping
        translated["model"] = kwargs.get("model", "")

        # Max tokens (required by Anthropic messages.create)
        translated["max_tokens"] = _coerce_positive_int(
            kwargs.get("max_tokens"), _MINIMAX_REQUIRED_MAX_TOKENS_DEFAULT
        )

        # Temperature - MiniMax requires (0.0, 1.0]
        if "temperature" in kwargs:
            temp = float(kwargs["temperature"])
            # Clamp to MiniMax's valid range (0.0, 1.0]
            temp = max(0.001, min(1.0, temp))
            translated["temperature"] = temp

        # Top p - not supported by Anthropic API, strip it
        # (Anthropic uses temperature only for randomness control)

        # System prompt - collect ALL system messages and merge into one
        # MiniMax requires exactly one system message; multiple are combined
        system_parts = []
        messages = kwargs.get("messages", [])
        if messages and isinstance(messages, list):
            non_system_messages = []
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                role = str(msg.get("role") or "").strip().lower()
                if role == "system":
                    content = msg.get("content", "")
                    if content:
                        system_parts.append(str(content))
                else:
                    non_system_messages.append(msg)
            messages = non_system_messages

        if system_parts:
            translated["system"] = "\n\n".join(system_parts)

        # Translate messages
        translated_messages = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue

            role = str(msg.get("role") or "").strip().lower()
            content = msg.get("content", "")
            tool_call_id = str(msg.get("tool_call_id") or "").strip()

            def _normalize_text_blocks(raw_content) -> list[dict[str, Any]]:
                if isinstance(raw_content, list):
                    blocks = []
                    for block in raw_content:
                        if not isinstance(block, dict):
                            continue
                        block_type = str(block.get("type") or "").strip()
                        if block_type == "text":
                            text = str(block.get("text") or "")
                            if text:
                                blocks.append({"type": "text", "text": text})
                    return blocks
                if isinstance(raw_content, str) and raw_content:
                    return [{"type": "text", "text": raw_content}]
                return []

            if role == "tool":
                tool_result_blocks = []
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if str(block.get("type") or "").strip() == "tool_result":
                            copied_block = dict(block)
                            if tool_call_id and not copied_block.get("tool_use_id"):
                                copied_block["tool_use_id"] = tool_call_id
                            tool_result_blocks.append(copied_block)

                if not tool_result_blocks:
                    result_content = content if content not in (None, "") else ""
                    tool_result_block: dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": tool_call_id or "tool_call",
                        "content": result_content,
                    }
                    tool_result_blocks.append(tool_result_block)

                translated_messages.append(
                    {
                        "role": "user",
                        "content": tool_result_blocks,
                    }
                )
                continue

            if role == "assistant":
                translated_content = _normalize_text_blocks(content)
                tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
                    tool_name = str(function.get("name") or tool_call.get("name") or "").strip()
                    if not tool_name:
                        continue
                    raw_arguments = function.get("arguments")
                    if isinstance(raw_arguments, str):
                        try:
                            input_payload = json.loads(raw_arguments)
                        except Exception:
                            input_payload = {}
                    elif isinstance(raw_arguments, dict):
                        input_payload = raw_arguments
                    else:
                        input_payload = {}
                    translated_content.append(
                        {
                            "type": "tool_use",
                            "id": str(tool_call.get("id") or "").strip() or f"tool_{tool_name}",
                            "name": tool_name,
                            "input": input_payload,
                        }
                    )

                if translated_content:
                    translated_messages.append(
                        {
                            "role": "assistant",
                            "content": translated_content,
                        }
                    )
                continue

            translated_content = _normalize_text_blocks(content)
            if not translated_content and role in ("user", "assistant"):
                translated_content = [{"type": "text", "text": ""}]

            if translated_content or role in ("user", "assistant"):
                translated_messages.append(
                    {
                        "role": role,
                        "content": translated_content,
                    }
                )

        translated["messages"] = translated_messages

        # Tools
        if "tools" in kwargs:
            tools = kwargs["tools"]
            if isinstance(tools, list):
                anthropic_tools = []
                for tool in tools:
                    if not isinstance(tool, dict):
                        continue
                    tool_type = str(tool.get("type") or "").strip()
                    if tool_type == "function":
                        func = tool.get("function", {})
                        anthropic_tools.append(
                            {
                                "name": func.get("name", ""),
                                "description": func.get("description", ""),
                                "input_schema": func.get("parameters", {}),
                            }
                        )
                    elif tool_type == "code":
                        # Code tool - skip for now
                        pass
                if anthropic_tools:
                    translated["tools"] = anthropic_tools

        # Tool choice
        tool_choice = kwargs.get("tool_choice")
        if isinstance(tool_choice, dict):
            function = tool_choice.get("function") if isinstance(tool_choice.get("function"), dict) else {}
            tool_name = str(function.get("name") or "").strip()
            if tool_name:
                translated["tool_choice"] = {"type": "tool", "name": tool_name}
        elif isinstance(tool_choice, str):
            normalized_tool_choice = tool_choice.strip().lower()
            if normalized_tool_choice == "auto":
                translated["tool_choice"] = {"type": "auto"}
            elif normalized_tool_choice in {"required", "any"}:
                translated["tool_choice"] = {"type": "any"}

        # Stream
        translated["stream"] = kwargs.get("stream", False)

        # Whitelist: only pass parameters that MiniMax's Anthropic endpoint supports
        allowed_params = {
            "model", "max_tokens", "system", "messages",
            "temperature", "stream", "tools", "tool_choice",
        }
        translated_copy = {k: v for k, v in translated.items() if k in allowed_params}

        import logging
        _logger = logging.getLogger(__name__)
        _logger.warning(f"[MiniMax Debug] After whitelist - translated keys: {list(translated_copy.keys())}")
        filtered = set(translated.keys()) - set(translated_copy.keys())
        if filtered:
            _logger.warning(f"[MiniMax Debug] Filtered out params: {filtered}")

        return translated_copy

    def _create_chat_completion(self, *args, **kwargs):
        """Handle chat.completions.create() call, translating to Anthropic API."""
        # Merge args and kwargs
        if args:
            # positional arg for model (uncommon but handle it)
            if len(args) >= 1:
                kwargs["model"] = args[0]
            if len(args) >= 2:
                kwargs["messages"] = args[1]

        # Translate to Anthropic format
        anthropic_kwargs = self._translate_openai_to_anthropic(kwargs)

        import logging
        _logger = logging.getLogger(__name__)
        _logger.warning(f"[MiniMax Debug] Final anthropic_kwargs keys: {list(anthropic_kwargs.keys())}")
        _logger.warning(f"[MiniMax Debug] anthropic_kwargs: {anthropic_kwargs}")

        # Get the client
        client = self._get_anthropic_client()

        # Check if streaming
        is_streaming = anthropic_kwargs.get("stream", False)

        if is_streaming:
            # Streaming call
            stream = client.messages.create(**anthropic_kwargs)
            return _MiniMaxStreamIterator(stream)
        else:
            # Non-streaming call
            response = client.messages.create(**anthropic_kwargs)
            return _MiniMaxNonStreamResponse(response, anthropic_kwargs.get("model", ""))


class _MiniMaxNonStreamResponse:
    """Wraps a non-streaming Anthropic response to look like OpenAI non-streaming response."""

    def __init__(self, message, model: str):
        self.message = message
        self.model = model
        self.choices = [_MiniMaxNonStreamChoice(message)]
        # Anthropic Usage uses attributes directly, not dict-like .get()
        usage = getattr(message, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
        else:
            prompt_tokens = 0
            output_tokens = 0
        self.usage = _MiniMaxUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=output_tokens,
            total_tokens=prompt_tokens + output_tokens,
        )

    def __iter__(self):
        return iter([self])


class _MiniMaxNonStreamChoice:
    def __init__(self, message):
        self.message = message
        self.finish_reason = getattr(message, "stop_reason", None) or "stop"


class _MiniMaxUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


BUILTIN_MODELS = [
    {
        "id": "deepseek-chat",
        "name": "DeepSeek Chat",
        "provider": DEEPSEEK_PROVIDER,
        "api_model": "deepseek-chat",
        "supports_tools": True,
        "supports_vision": False,
        "supports_structured_outputs": False,
        "is_custom": False,
    },
    {
        "id": "deepseek-reasoner",
        "name": "DeepSeek Reasoner",
        "provider": DEEPSEEK_PROVIDER,
        "api_model": "deepseek-reasoner",
        "supports_tools": True,
        "supports_vision": False,
        "supports_structured_outputs": False,
        "is_custom": False,
    },
    {
        "id": "MiniMax-M2.7",
        "name": "MiniMax M2.7",
        "provider": MINIMAX_PROVIDER,
        "api_model": "MiniMax-M2.7",
        "supports_tools": True,
        "supports_vision": False,
        "supports_structured_outputs": False,
        "is_custom": False,
    },
    {
        "id": "MiniMax-M2.7-highspeed",
        "name": "MiniMax M2.7 HighSpeed",
        "provider": MINIMAX_PROVIDER,
        "api_model": "MiniMax-M2.7-highspeed",
        "supports_tools": True,
        "supports_vision": False,
        "supports_structured_outputs": False,
        "is_custom": False,
    },
    {
        "id": "MiniMax-M2.5",
        "name": "MiniMax M2.5",
        "provider": MINIMAX_PROVIDER,
        "api_model": "MiniMax-M2.5",
        "supports_tools": True,
        "supports_vision": False,
        "supports_structured_outputs": False,
        "is_custom": False,
    },
    {
        "id": "MiniMax-M2.5-highspeed",
        "name": "MiniMax M2.5 HighSpeed",
        "provider": MINIMAX_PROVIDER,
        "api_model": "MiniMax-M2.5-highspeed",
        "supports_tools": True,
        "supports_vision": False,
        "supports_structured_outputs": False,
        "is_custom": False,
    },
    {
        "id": "MiniMax-M2.1",
        "name": "MiniMax M2.1",
        "provider": MINIMAX_PROVIDER,
        "api_model": "MiniMax-M2.1",
        "supports_tools": True,
        "supports_vision": False,
        "supports_structured_outputs": False,
        "is_custom": False,
    },
    {
        "id": "MiniMax-M2.1-highspeed",
        "name": "MiniMax M2.1 HighSpeed",
        "provider": MINIMAX_PROVIDER,
        "api_model": "MiniMax-M2.1-highspeed",
        "supports_tools": True,
        "supports_vision": False,
        "supports_structured_outputs": False,
        "is_custom": False,
    },
    {
        "id": "MiniMax-M2",
        "name": "MiniMax M2",
        "provider": MINIMAX_PROVIDER,
        "api_model": "MiniMax-M2",
        "supports_tools": True,
        "supports_vision": False,
        "supports_structured_outputs": False,
        "is_custom": False,
    },
]
BUILTIN_MODEL_IDS = {model["id"] for model in BUILTIN_MODELS}
DEFAULT_VISIBLE_CHAT_MODEL_ORDER = [model["id"] for model in BUILTIN_MODELS if model.get("supports_tools")]


def _copy_model_record(record: dict[str, Any]) -> dict[str, Any]:
    return dict(record)


def normalize_chat_parameter_overrides(raw_value: Any) -> dict[str, Any] | None:
    if raw_value in (None, ""):
        return None
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except Exception as exc:
            raise ValueError("parameter_overrides must be a JSON object.") from exc
    else:
        parsed = raw_value
    if parsed in (None, {}):
        return None
    if not isinstance(parsed, dict):
        raise ValueError("parameter_overrides must be an object or null.")

    normalized: dict[str, Any] = {}
    unknown_keys = [key for key in parsed.keys() if key not in CHAT_PARAMETER_OVERRIDE_SPECS]
    if unknown_keys:
        unknown_key_list = ", ".join(sorted(str(key) for key in unknown_keys)[:8])
        raise ValueError(f"Unsupported parameter override keys: {unknown_key_list}.")

    for key, spec in CHAT_PARAMETER_OVERRIDE_SPECS.items():
        if key not in parsed:
            continue
        raw_entry = parsed.get(key)
        if raw_entry in (None, ""):
            continue
        if spec.get("type") == "int":
            try:
                value = int(raw_entry)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be an integer.") from exc
        else:
            try:
                value = float(raw_entry)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be a number.") from exc
        minimum = spec.get("min")
        maximum = spec.get("max")
        if minimum is not None and value < minimum:
            raise ValueError(f"{key} must be >= {minimum}.")
        if maximum is not None and value > maximum:
            raise ValueError(f"{key} must be <= {maximum}.")
        normalized[key] = value

    return normalized or None


def apply_chat_parameter_overrides(
    request_kwargs: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    merged_request_kwargs = dict(request_kwargs)
    normalized_overrides = normalize_chat_parameter_overrides(overrides)
    if not normalized_overrides:
        return merged_request_kwargs

    for key in CHAT_PARAMETER_OVERRIDE_KEYS:
        if key not in normalized_overrides:
            continue
        merged_request_kwargs[key] = normalized_overrides[key]
    return merged_request_kwargs


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_json_list(raw_value: Any) -> list[Any]:
    if isinstance(raw_value, list):
        return raw_value
    if raw_value in (None, ""):
        return []
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _parse_json_dict(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if raw_value in (None, ""):
        return {}
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _merge_nested_dicts(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_nested_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def normalize_openrouter_api_model(value: Any) -> str:
    api_model = str(value or "").strip()
    if api_model.startswith(OPENROUTER_MODEL_PREFIX):
        api_model = api_model[len(OPENROUTER_MODEL_PREFIX) :]
    return api_model.strip().strip("/")[:200]


def _split_openrouter_model_identity(value: Any) -> tuple[str, str]:
    normalized_value = normalize_openrouter_api_model(value)
    if not normalized_value:
        return "", ""

    base_api_model, separator, variant_suffix = normalized_value.partition(OPENROUTER_MODEL_VARIANT_SEPARATOR)
    if not separator:
        return base_api_model, ""
    return base_api_model, variant_suffix


def _normalize_openrouter_model_variant_suffix(variant: dict[str, Any] | None) -> str:
    source = variant if isinstance(variant, dict) else {}
    parts: list[str] = []

    reasoning_mode, reasoning_effort = normalize_openrouter_reasoning_preferences(
        source.get("reasoning_mode", source.get("reasoning_enabled")),
        source.get("reasoning_effort"),
    )
    if reasoning_mode != OPENROUTER_REASONING_MODE_DEFAULT or reasoning_effort:
        reasoning_value = reasoning_mode
        if reasoning_effort:
            reasoning_value = f"{reasoning_value}:{reasoning_effort}"
        parts.append(f"r{OPENROUTER_MODEL_VARIANT_KEY_VALUE_SEPARATOR}{reasoning_value}")

    provider_slug = normalize_openrouter_provider_slug(source.get("provider_slug") or source.get("openrouter_provider"))
    if provider_slug:
        parts.append(f"p{OPENROUTER_MODEL_VARIANT_KEY_VALUE_SEPARATOR}{provider_slug}")

    if _coerce_bool(source.get("supports_tools", True)) is False:
        parts.append(f"t{OPENROUTER_MODEL_VARIANT_KEY_VALUE_SEPARATOR}0")
    if _coerce_bool(source.get("supports_vision", False)) is True:
        parts.append(f"v{OPENROUTER_MODEL_VARIANT_KEY_VALUE_SEPARATOR}1")
    if _coerce_bool(source.get("supports_structured_outputs", False)) is True:
        parts.append(f"s{OPENROUTER_MODEL_VARIANT_KEY_VALUE_SEPARATOR}1")

    if not parts:
        return ""
    return f"{OPENROUTER_MODEL_VARIANT_SEPARATOR}{OPENROUTER_MODEL_VARIANT_PART_SEPARATOR.join(parts)}"


def _parse_openrouter_model_variant_suffix(variant_suffix: str) -> dict[str, Any]:
    cleaned_suffix = str(variant_suffix or "").strip()
    if not cleaned_suffix:
        return {}

    parsed: dict[str, Any] = {}
    for part in cleaned_suffix.split(OPENROUTER_MODEL_VARIANT_PART_SEPARATOR):
        key, separator, value = part.partition(OPENROUTER_MODEL_VARIANT_KEY_VALUE_SEPARATOR)
        if not separator:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key == "r" and value:
            reasoning_mode, reasoning_effort = normalize_openrouter_reasoning_preferences(
                value.split(":", 1)[0],
                value.split(":", 1)[1] if ":" in value else "",
            )
            parsed["reasoning_mode"] = reasoning_mode
            if reasoning_effort:
                parsed["reasoning_effort"] = reasoning_effort
        elif key == "p" and value:
            parsed["provider_slug"] = normalize_openrouter_provider_slug(value)
        elif key == "t":
            parsed["supports_tools"] = value not in {"0", "false", "no", "off"}
        elif key == "v":
            parsed["supports_vision"] = value in {"1", "true", "yes", "on"}
        elif key == "s":
            parsed["supports_structured_outputs"] = value in {"1", "true", "yes", "on"}

    return parsed


def build_openrouter_model_id(api_model: str, variant: dict[str, Any] | None = None) -> str:
    normalized_api_model, encoded_variant_suffix = _split_openrouter_model_identity(api_model)
    if not normalized_api_model:
        return ""

    variant_suffix = _normalize_openrouter_model_variant_suffix(variant)
    if not variant_suffix and encoded_variant_suffix:
        variant_suffix = f"{OPENROUTER_MODEL_VARIANT_SEPARATOR}{encoded_variant_suffix}"
    return f"{OPENROUTER_MODEL_PREFIX}{normalized_api_model}{variant_suffix}"


def normalize_openrouter_provider_slug(value: Any) -> str:
    provider_slug = str(value or "").strip().strip("/").lower()
    if not provider_slug:
        return ""
    if not _OPENROUTER_PROVIDER_SLUG_RE.fullmatch(provider_slug):
        return ""
    return provider_slug


def normalize_openrouter_reasoning_preferences(mode_value: Any, effort_value: Any = None) -> tuple[str, str]:
    raw_effort = str(effort_value or "").strip().lower()
    if raw_effort == "none":
        return OPENROUTER_REASONING_MODE_DISABLED, ""

    if isinstance(mode_value, bool):
        mode = OPENROUTER_REASONING_MODE_ENABLED if mode_value else OPENROUTER_REASONING_MODE_DISABLED
    else:
        mode = str(mode_value or "").strip().lower()

    if mode in {"1", "true", "yes", "on"}:
        mode = OPENROUTER_REASONING_MODE_ENABLED
    elif mode in {"0", "false", "no", "off"}:
        mode = OPENROUTER_REASONING_MODE_DISABLED
    elif mode not in OPENROUTER_REASONING_MODES:
        mode = OPENROUTER_REASONING_MODE_DEFAULT

    effort = raw_effort if raw_effort in OPENROUTER_REASONING_EFFORTS else ""
    if mode == OPENROUTER_REASONING_MODE_DEFAULT and effort:
        mode = OPENROUTER_REASONING_MODE_ENABLED
    if mode != OPENROUTER_REASONING_MODE_ENABLED:
        effort = ""
    return mode, effort


def _openrouter_supports_top_level_prompt_cache(api_model: Any) -> bool:
    normalized_api_model = str(api_model or "").strip().lower()
    return normalized_api_model.startswith("anthropic/")


def _openrouter_requires_explicit_cache_breakpoints(api_model: Any) -> bool:
    normalized_api_model = str(api_model or "").strip().lower()
    return normalized_api_model.startswith("google/gemini")


def _openrouter_supports_implicit_prompt_cache(api_model: Any) -> bool:
    normalized_api_model = str(api_model or "").strip().lower()
    return normalized_api_model.startswith(_OPENROUTER_IMPLICIT_PROMPT_CACHE_MODEL_PREFIXES)


def _openrouter_gemini_cache_min_tokens(api_model: Any) -> int:
    normalized_api_model = str(api_model or "").strip().lower()
    if "flash" in normalized_api_model:
        return _OPENROUTER_GEMINI_CACHE_BREAKPOINT_MIN_TOKENS_DEFAULT
    if "pro" in normalized_api_model:
        return _OPENROUTER_GEMINI_CACHE_BREAKPOINT_MIN_TOKENS_PRO
    return _OPENROUTER_GEMINI_CACHE_BREAKPOINT_MIN_TOKENS_DEFAULT


def _build_cache_control(ttl: str) -> dict[str, Any]:
    """Build the cache_control dict. ttl: '5m' → ephemeral (5 min), '1h' → ephemeral with ttl=1h."""
    if ttl == "1h":
        return {"type": "ephemeral", "ttl": "1h"}
    return {"type": "ephemeral"}


def _with_openrouter_cache_breakpoint(content: Any, *, min_tokens: int, ttl: str = "5m") -> tuple[Any, bool]:
    cache_control = _build_cache_control(ttl)
    if isinstance(content, list):
        normalized_blocks: list[dict[str, Any]] = []
        last_text_index: int | None = None
        text_parts: list[str] = []
        for index, block in enumerate(content):
            if not isinstance(block, dict):
                return content, False
            copied_block = dict(block)
            if isinstance(copied_block.get("cache_control"), dict):
                return content, False
            text_value = str(copied_block.get("text") or "").strip()
            if str(copied_block.get("type") or "").strip() == "text" and text_value:
                last_text_index = index
                text_parts.append(text_value)
            normalized_blocks.append(copied_block)
        if last_text_index is None or estimate_text_tokens("\n\n".join(text_parts)) < min_tokens:
            return content, False
        normalized_blocks[last_text_index]["cache_control"] = cache_control
        return normalized_blocks, True

    text = str(content or "").strip()
    if not text or estimate_text_tokens(text) < min_tokens:
        return content, False
    return ([{"type": "text", "text": text, "cache_control": cache_control}], True)


def _is_openrouter_anthropic_volatile_runtime_content(content: Any) -> bool:
    text_chunks: list[str] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if str(block.get("type") or "").strip() != "text":
                continue
            block_text = str(block.get("text") or "").strip()
            if block_text:
                text_chunks.append(block_text)
    else:
        normalized_text = str(content or "").strip()
        if normalized_text:
            text_chunks.append(normalized_text)

    if not text_chunks:
        return False
    combined_text = "\n\n".join(text_chunks).lower()
    return any(marker in combined_text for marker in _OPENROUTER_ANTHROPIC_VOLATILE_RUNTIME_MARKERS)


def _serialize_openrouter_cache_payload(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _extract_openrouter_breakpoint_prefix(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""

    prefix_messages: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            return ""

        copied_message = dict(message)
        content = copied_message.get("content")
        if not isinstance(content, list):
            prefix_messages.append(copied_message)
            continue

        prefix_blocks: list[Any] = []
        for block in content:
            copied_block = dict(block) if isinstance(block, dict) else block
            prefix_blocks.append(copied_block)
            if isinstance(block, dict) and isinstance(block.get("cache_control"), dict):
                copied_message["content"] = prefix_blocks
                prefix_messages.append(copied_message)
                return _serialize_openrouter_cache_payload(prefix_messages)

        prefix_messages.append(copied_message)

    return ""


def build_openrouter_cache_estimate_context(
    messages: Any, record: dict[str, Any] | None, settings: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    if str(record.get("provider") or "").strip() != OPENROUTER_PROVIDER:
        return None
    if not _is_openrouter_prompt_cache_enabled(settings):
        return {
            "supports_prompt_cache": False,
            "strategy": "disabled",
            "cacheable_text": "",
        }

    api_model = str(record.get("api_model") or "").strip()
    if _openrouter_supports_top_level_prompt_cache(api_model):
        return {
            "supports_prompt_cache": True,
            "strategy": "top_level",
            "cacheable_text": _serialize_openrouter_cache_payload(messages),
        }

    if _openrouter_requires_explicit_cache_breakpoints(api_model):
        return {
            "supports_prompt_cache": True,
            "strategy": "explicit_breakpoint",
            "cacheable_text": _extract_openrouter_breakpoint_prefix(messages),
        }

    if _openrouter_supports_implicit_prompt_cache(api_model):
        return {
            "supports_prompt_cache": True,
            "strategy": "implicit",
            "cacheable_text": _serialize_openrouter_cache_payload(messages),
        }

    return {
        "supports_prompt_cache": False,
        "strategy": "none",
        "cacheable_text": "",
    }


def _summarize_model_cache_context(cache_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(cache_context, dict):
        return None
    return {
        "supports_prompt_cache": bool(cache_context.get("supports_prompt_cache") is True),
        "strategy": str(cache_context.get("strategy") or "").strip(),
    }


def build_model_provider_policy(
    record: dict[str, Any] | None, settings: dict[str, Any] | None = None
) -> dict[str, Any]:
    provider = str(record.get("provider") or "").strip() if isinstance(record, dict) else ""
    cache_context: dict[str, Any] | None = None
    tool_choice_fallback_value: str | None = None
    tool_choice_error_signatures: tuple[tuple[str, ...], ...] = ()
    supports_native_reasoning_continuation = False

    if provider == DEEPSEEK_PROVIDER:
        cache_context = {
            "supports_prompt_cache": True,
            "strategy": "implicit",
        }
    elif provider == OPENROUTER_PROVIDER and isinstance(record, dict):
        cache_context = _summarize_model_cache_context(build_openrouter_cache_estimate_context([], record, settings))
        supports_native_reasoning_continuation = True
        tool_choice_fallback_value = "auto"
        tool_choice_error_signatures = (
            (
                "tool_choice",
                "no endpoints found",
                "support the provided",
            ),
        )
    elif provider == MINIMAX_PROVIDER:
        # MiniMax uses Anthropic SDK format with thinking support
        supports_native_reasoning_continuation = True
        cache_context = {
            "supports_prompt_cache": False,
            "strategy": "none",
        }

    supports_prompt_cache = bool(isinstance(cache_context, dict) and cache_context.get("supports_prompt_cache") is True)
    return {
        "provider": provider,
        "cache_context": cache_context,
        "supports_prompt_cache": supports_prompt_cache,
        "prefers_cache_friendly_prefix": supports_prompt_cache,
        "supports_native_reasoning_continuation": supports_native_reasoning_continuation,
        "tool_choice_auto_fallback_enabled": bool(tool_choice_fallback_value),
        "tool_choice_fallback_value": tool_choice_fallback_value,
        "tool_choice_auto_fallback_error_signatures": tool_choice_error_signatures,
    }


def get_model_target_policy(target: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(target, dict):
        policy = target.get("policy")
        if isinstance(policy, dict):
            return dict(policy)
        return build_model_provider_policy(target.get("record"), target.get("settings"))
    return build_model_provider_policy(None)


def model_prefers_cache_friendly_prefix(model_id: str | None, settings: dict[str, Any] | None = None) -> bool:
    record = get_model_record(str(model_id or "").strip(), settings)
    if not isinstance(record, dict):
        return False
    policy = build_model_provider_policy(record, settings)
    return bool(policy.get("prefers_cache_friendly_prefix"))


def model_target_supports_native_reasoning_continuation(target: dict[str, Any] | None) -> bool:
    policy = get_model_target_policy(target)
    return bool(policy.get("supports_native_reasoning_continuation"))


def should_retry_model_target_tool_choice_with_auto(
    error: Exception | str,
    request_kwargs: dict[str, Any],
    target: dict[str, Any] | None,
) -> bool:
    if not isinstance(request_kwargs.get("tool_choice"), dict):
        return False

    policy = get_model_target_policy(target)
    if not bool(policy.get("tool_choice_auto_fallback_enabled")):
        return False

    normalized_error = str(error or "").strip().lower()
    if not normalized_error:
        return False

    error_signatures = policy.get("tool_choice_auto_fallback_error_signatures") or ()
    for signature in error_signatures:
        if all(str(marker or "").strip().lower() in normalized_error for marker in signature):
            return True
    return False


def build_model_target_tool_choice_fallback_request(
    request_kwargs: dict[str, Any],
    target: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(request_kwargs, dict):
        return None

    fallback_value = get_model_target_policy(target).get("tool_choice_fallback_value")
    if fallback_value in (None, ""):
        return None

    fallback_request_kwargs = dict(request_kwargs)
    fallback_request_kwargs["tool_choice"] = fallback_value
    if fallback_value == "auto":
        fallback_request_kwargs.pop("parallel_tool_calls", None)
    return fallback_request_kwargs


def _prepare_model_request_messages(
    messages: Any, record: dict[str, Any] | None, settings: dict[str, Any] | None = None
) -> Any:
    if not isinstance(messages, list) or not isinstance(record, dict):
        return messages
    if str(record.get("provider") or "").strip() != OPENROUTER_PROVIDER:
        return messages
    if not _is_openrouter_prompt_cache_enabled(settings):
        return messages

    api_model = str(record.get("api_model") or "").strip()
    supports_explicit_breakpoints = _openrouter_requires_explicit_cache_breakpoints(api_model)
    supports_top_level_cache = _openrouter_supports_top_level_prompt_cache(api_model)
    if not supports_explicit_breakpoints and not supports_top_level_cache:
        return messages

    prepared_messages = list(messages)
    cache_min_tokens = (
        _openrouter_gemini_cache_min_tokens(api_model)
        if supports_explicit_breakpoints
        else _openrouter_anthropic_cache_min_tokens(api_model)
    )
    # TTL only applies to Anthropic; Gemini uses ephemeral (5m) only
    if supports_top_level_cache and isinstance(settings, dict):
        raw_ttl = str(settings.get("openrouter_anthropic_cache_ttl") or "").strip().lower()
        cache_ttl = "1h" if raw_ttl == "1h" else "5m"
    else:
        cache_ttl = "5m"
    max_breakpoints = 1 if supports_explicit_breakpoints else _OPENROUTER_ANTHROPIC_CACHE_MAX_BREAKPOINTS
    breakpoints_placed = 0
    for index, message in enumerate(prepared_messages):
        if not isinstance(message, dict):
            break
        role = str(message.get("role") or "").strip().lower()
        if role not in {"system", "developer"}:
            break
        if breakpoints_placed >= max_breakpoints:
            break
        if supports_top_level_cache and _is_openrouter_anthropic_volatile_runtime_content(message.get("content")):
            continue
        updated_content, applied = _with_openrouter_cache_breakpoint(
            message.get("content"), min_tokens=cache_min_tokens, ttl=cache_ttl
        )
        if applied:
            prepared_messages[index] = {**prepared_messages[index], "content": updated_content}
            breakpoints_placed += 1
    return prepared_messages


def canonicalize_model_id(value: Any) -> str:
    model_id = str(value or "").strip()
    if not model_id:
        return ""
    if model_id in BUILTIN_MODEL_IDS:
        return model_id
    if model_id.startswith(OPENROUTER_MODEL_PREFIX):
        return build_openrouter_model_id(model_id)
    return model_id


def normalize_custom_model_definition(raw_value: Any) -> dict[str, Any] | None:
    if not isinstance(raw_value, dict):
        return None

    raw_identity = raw_value.get("api_model") or raw_value.get("model") or raw_value.get("id")
    parsed_api_model, parsed_variant_suffix = _split_openrouter_model_identity(raw_identity)
    parsed_variant = _parse_openrouter_model_variant_suffix(parsed_variant_suffix)

    api_model = normalize_openrouter_api_model(raw_value.get("api_model") or raw_value.get("model") or parsed_api_model)
    if not api_model:
        return None

    reasoning_mode_input = raw_value.get("reasoning_mode")
    if reasoning_mode_input is None:
        reasoning_mode_input = parsed_variant.get("reasoning_mode")
    reasoning_effort_input = raw_value.get("reasoning_effort")
    if reasoning_effort_input is None:
        reasoning_effort_input = parsed_variant.get("reasoning_effort")

    provider_slug_input = raw_value.get("provider_slug")
    if provider_slug_input is None:
        provider_slug_input = parsed_variant.get("provider_slug")

    supports_tools_input = raw_value.get("supports_tools")
    if supports_tools_input is None:
        supports_tools_input = parsed_variant.get("supports_tools", True)
    supports_vision_input = raw_value.get("supports_vision")
    if supports_vision_input is None:
        supports_vision_input = parsed_variant.get("supports_vision", False)
    supports_structured_outputs_input = raw_value.get("supports_structured_outputs")
    if supports_structured_outputs_input is None:
        supports_structured_outputs_input = parsed_variant.get("supports_structured_outputs", False)

    model_id = build_openrouter_model_id(
        api_model,
        {
            "reasoning_mode": reasoning_mode_input,
            "reasoning_effort": reasoning_effort_input,
            "provider_slug": provider_slug_input,
            "supports_tools": supports_tools_input,
            "supports_vision": supports_vision_input,
            "supports_structured_outputs": supports_structured_outputs_input,
        },
    )
    if not model_id or model_id in BUILTIN_MODEL_IDS:
        return None

    name = str(raw_value.get("name") or api_model).strip()[:120] or api_model
    provider_slug = normalize_openrouter_provider_slug(provider_slug_input or raw_value.get("openrouter_provider"))
    reasoning_mode, reasoning_effort = normalize_openrouter_reasoning_preferences(
        reasoning_mode_input,
        reasoning_effort_input,
    )
    return {
        "id": model_id,
        "name": name,
        "provider": OPENROUTER_PROVIDER,
        "api_model": api_model,
        "provider_slug": provider_slug,
        "reasoning_mode": reasoning_mode,
        "reasoning_effort": reasoning_effort,
        "supports_tools": _coerce_bool(supports_tools_input),
        "supports_vision": _coerce_bool(supports_vision_input),
        "supports_structured_outputs": _coerce_bool(supports_structured_outputs_input),
        "is_custom": True,
    }


def normalize_custom_models(raw_value: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in _parse_json_list(raw_value):
        definition = normalize_custom_model_definition(item)
        if not definition:
            continue
        model_id = definition["id"]
        if model_id in seen_ids:
            continue
        seen_ids.add(model_id)
        normalized.append(definition)
    return normalized


def get_custom_model_contract() -> dict[str, Any]:
    return {
        "provider": OPENROUTER_PROVIDER,
        "model_prefix": OPENROUTER_MODEL_PREFIX,
        "client_uid_prefix": "draft-custom-model:",
        "variant_separator": OPENROUTER_MODEL_VARIANT_SEPARATOR,
        "variant_part_separator": OPENROUTER_MODEL_VARIANT_PART_SEPARATOR,
        "variant_key_value_separator": OPENROUTER_MODEL_VARIANT_KEY_VALUE_SEPARATOR,
        "provider_slug_pattern": _OPENROUTER_PROVIDER_SLUG_RE.pattern,
        "reasoning_modes": [
            OPENROUTER_REASONING_MODE_DEFAULT,
            OPENROUTER_REASONING_MODE_ENABLED,
            OPENROUTER_REASONING_MODE_DISABLED,
        ],
        "reasoning_efforts": sorted(OPENROUTER_REASONING_EFFORTS),
    }


def get_all_models(settings: dict | None = None) -> list[dict[str, Any]]:
    records = [_copy_model_record(record) for record in BUILTIN_MODELS]
    if settings is None:
        return records
    records.extend(normalize_custom_models(settings.get("custom_models")))
    return records


def get_model_record(model_id: str, settings: dict | None = None) -> dict[str, Any] | None:
    normalized_model_id = canonicalize_model_id(model_id)
    if not normalized_model_id:
        return None
    for record in get_all_models(settings):
        if record["id"] == normalized_model_id:
            return record
    if normalized_model_id.startswith(OPENROUTER_MODEL_PREFIX):
        variant_prefix = f"{normalized_model_id}{OPENROUTER_MODEL_VARIANT_SEPARATOR}"
        for record in get_all_models(settings):
            if record["id"].startswith(variant_prefix):
                return record
    return None


def is_valid_model_id(model_id: str, settings: dict | None = None) -> bool:
    return get_model_record(model_id, settings) is not None


def get_model_label(model_id: str, settings: dict | None = None) -> str:
    record = get_model_record(model_id, settings)
    if record:
        return str(record.get("name") or record["id"])
    return canonicalize_model_id(model_id) or str(model_id or "").strip()


def get_chat_capable_models(settings: dict | None = None) -> list[dict[str, Any]]:
    return [record for record in get_all_models(settings) if record.get("supports_tools")]


def _get_default_visible_model_order(settings: dict | None = None) -> list[str]:
    candidate_ids = {record["id"] for record in get_chat_capable_models(settings)}
    default_order = [model_id for model_id in DEFAULT_VISIBLE_CHAT_MODEL_ORDER if model_id in candidate_ids]
    if default_order:
        return default_order
    return [record["id"] for record in get_chat_capable_models(settings)]


def normalize_visible_model_order(raw_value: Any, settings: dict | None = None) -> list[str]:
    if raw_value in (None, ""):
        return _get_default_visible_model_order(settings)

    normalized: list[str] = []
    for item in _parse_json_list(raw_value):
        model_id = canonicalize_model_id(item)
        record = get_model_record(model_id, settings)
        if record and record.get("supports_tools") and record["id"] not in normalized:
            normalized.append(record["id"])
    if normalized:
        return normalized
    return _get_default_visible_model_order(settings)


def get_visible_chat_models(settings: dict | None = None, include_model_id: str | None = None) -> list[dict[str, Any]]:
    catalog = {record["id"]: record for record in get_chat_capable_models(settings)}
    ordered_ids = normalize_visible_model_order(
        settings.get("visible_model_order") if isinstance(settings, dict) else None,
        settings,
    )
    records = [catalog[model_id] for model_id in ordered_ids if model_id in catalog]

    if include_model_id:
        included = get_model_record(include_model_id, settings)
        if included and included.get("supports_tools") and included["id"] not in {record["id"] for record in records}:
            records.append(included)

    if records:
        return records

    fallback = get_model_record(DEFAULT_CHAT_MODEL, settings)
    return [fallback] if fallback and fallback.get("supports_tools") else []


def get_default_chat_model_id(settings: dict | None = None) -> str:
    visible_models = get_visible_chat_models(settings)
    if visible_models:
        return visible_models[0]["id"]
    return DEFAULT_CHAT_MODEL


def _normalize_operation_model_mapping(raw_value: Any, settings: dict | None = None) -> dict[str, str]:
    raw_preferences = _parse_json_dict(raw_value)
    normalized = dict(DEFAULT_OPERATION_MODEL_PREFERENCES)
    for operation in MODEL_OPERATION_KEYS:
        candidate = canonicalize_model_id(raw_preferences.get(operation))
        record = get_model_record(candidate, settings)
        if record:
            normalized[operation] = record["id"]
    return normalized


def _copy_operation_model_fallback_preferences(preferences: dict[str, list[str]]) -> dict[str, list[str]]:
    return {operation: list(preferences.get(operation, [])) for operation in MODEL_OPERATION_KEYS}


def normalize_operation_model_preferences(raw_value: Any, settings: dict | None = None) -> dict[str, str]:
    return _normalize_operation_model_mapping(raw_value, settings)


def _normalize_operation_model_fallback_list(raw_value: Any, settings: dict | None = None) -> list[str]:
    if raw_value in (None, ""):
        return []
    if isinstance(raw_value, list):
        raw_items = raw_value
    elif isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except Exception:
            raw_items = [raw_value]
        else:
            raw_items = parsed if isinstance(parsed, list) else [raw_value]
    else:
        raw_items = [raw_value]

    normalized: list[str] = []
    for item in raw_items:
        candidate = canonicalize_model_id(item)
        record = get_model_record(candidate, settings)
        if record and record["id"] not in normalized:
            normalized.append(record["id"])
    return normalized


def normalize_operation_model_fallback_preferences(
    raw_value: Any, settings: dict | None = None
) -> dict[str, list[str]]:
    raw_preferences = _parse_json_dict(raw_value)
    normalized: dict[str, list[str]] = {key: [] for key in MODEL_OPERATION_KEYS}
    for operation in MODEL_OPERATION_KEYS:
        normalized[operation] = _normalize_operation_model_fallback_list(raw_preferences.get(operation), settings)
    return normalized


def get_operation_model_preferences(settings: dict | None = None) -> dict[str, str]:
    if not isinstance(settings, dict):
        return dict(DEFAULT_OPERATION_MODEL_PREFERENCES)
    return normalize_operation_model_preferences(settings.get("operation_model_preferences"), settings)


def get_operation_model_fallback_preferences(settings: dict | None = None) -> dict[str, list[str]]:
    if not isinstance(settings, dict):
        return _copy_operation_model_fallback_preferences(DEFAULT_OPERATION_MODEL_FALLBACK_PREFERENCES)
    return normalize_operation_model_fallback_preferences(
        settings.get("operation_model_fallback_preferences"), settings
    )


def get_operation_model(
    operation: str,
    settings: dict | None = None,
    fallback_model_id: str | None = None,
) -> str:
    candidates = get_operation_model_candidates(operation, settings, fallback_model_id=fallback_model_id)
    if candidates:
        return candidates[0]
    return get_default_chat_model_id(settings)


def get_operation_model_candidates(
    operation: str,
    settings: dict | None = None,
    fallback_model_id: str | None = None,
) -> list[str]:
    candidates: list[str] = []

    preferences = get_operation_model_preferences(settings)
    preferred_model = preferences.get(operation, "")
    if preferred_model and is_valid_model_id(preferred_model, settings):
        candidates.append(preferred_model)

    fallback_preferences = get_operation_model_fallback_preferences(settings)
    for configured_fallback_model in fallback_preferences.get(operation, []):
        if (
            configured_fallback_model
            and is_valid_model_id(configured_fallback_model, settings)
            and configured_fallback_model not in candidates
        ):
            candidates.append(configured_fallback_model)

    normalized_fallback = canonicalize_model_id(fallback_model_id)
    if (
        normalized_fallback
        and is_valid_model_id(normalized_fallback, settings)
        and normalized_fallback not in candidates
    ):
        candidates.append(normalized_fallback)

    default_chat_model = get_default_chat_model_id(settings)
    if default_chat_model and is_valid_model_id(default_chat_model, settings) and default_chat_model not in candidates:
        candidates.append(default_chat_model)

    return candidates


def normalize_image_processing_method(value: Any) -> str:
    method = str(value or DEFAULT_IMAGE_PROCESSING_METHOD).strip().lower()
    if method == "llm":
        return "llm_helper"
    if method in {"local_vl", "local_both"}:
        return "local_ocr"
    if method in IMAGE_PROCESSING_METHODS:
        return method
    return DEFAULT_IMAGE_PROCESSING_METHOD


def get_image_helper_model_id(settings: dict | None = None) -> str:
    source = settings if settings is not None else {}
    candidate = canonicalize_model_id(source.get("image_helper_model"))
    if candidate and get_model_record(candidate, settings):
        return candidate

    default_chat_model = get_default_chat_model_id(settings)
    if default_chat_model and can_model_process_images(default_chat_model, settings):
        return default_chat_model

    return ""


def can_model_use_tools(model_id: str, settings: dict | None = None) -> bool:
    record = get_model_record(model_id, settings)
    return bool(record and record.get("supports_tools"))


def can_model_process_images(model_id: str, settings: dict | None = None) -> bool:
    record = get_model_record(model_id, settings)
    return bool(record and record.get("supports_vision"))


def can_model_use_structured_outputs(model_id: str, settings: dict | None = None) -> bool:
    record = get_model_record(model_id, settings)
    return bool(record and record.get("supports_structured_outputs"))


@lru_cache(maxsize=3)
def get_provider_client(provider: str) -> OpenAI | _OpenRouterClientProxy | _MiniMaxClientProxy:
    import config

    if provider == DEEPSEEK_PROVIDER:
        return OpenAI(
            api_key=(config.DEEPSEEK_API_KEY or "").strip(),
            base_url="https://api.deepseek.com",
        )
    if provider == OPENROUTER_PROVIDER:
        default_headers: dict[str, str] = {}
        http_referer = str(config.OPENROUTER_HTTP_REFERER or "").strip()
        app_title = str(config.OPENROUTER_APP_TITLE or "").strip()
        if http_referer:
            default_headers["HTTP-Referer"] = http_referer
        if app_title:
            default_headers["X-Title"] = app_title

        kwargs: dict[str, Any] = {
            "api_key": (config.OPENROUTER_API_KEY or "").strip(),
            "base_url": "https://openrouter.ai/api/v1",
        }
        if default_headers:
            kwargs["default_headers"] = default_headers
        return _OpenRouterClientProxy(kwargs)
    if provider == MINIMAX_PROVIDER:
        return _MiniMaxClientProxy(api_key=(config.MINIMAX_API_KEY or "").strip())
    raise ValueError(f"Unsupported provider: {provider}")


def resolve_model_target(model_id: str, settings: dict | None = None) -> dict[str, Any]:
    record = get_model_record(model_id, settings)
    if not record:
        raise ValueError(f"Unsupported model: {model_id}")
    policy = build_model_provider_policy(record, settings)
    return {
        "record": record,
        "settings": settings,
        "policy": policy,
        "client": get_provider_client(str(record["provider"])),
        "api_model": str(record["api_model"]),
        "extra_body": build_model_request_extra_body(record, settings),
    }


def build_model_request_extra_body(
    record: dict[str, Any] | None, settings: dict[str, Any] | None = None
) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    if str(record.get("provider") or "").strip() != OPENROUTER_PROVIDER:
        return {}

    extra_body: dict[str, Any] = {}
    provider_options: dict[str, Any] = {"sort": "throughput"}
    provider_slug = normalize_openrouter_provider_slug(record.get("provider_slug"))
    if provider_slug:
        provider_options.update(
            {
                "only": [provider_slug],
                "allow_fallbacks": False,
            }
        )

    extra_body["provider"] = provider_options

    reasoning_mode, reasoning_effort = normalize_openrouter_reasoning_preferences(
        record.get("reasoning_mode"),
        record.get("reasoning_effort"),
    )
    if reasoning_mode == OPENROUTER_REASONING_MODE_DISABLED:
        extra_body["reasoning"] = {"effort": "none"}
    elif reasoning_mode == OPENROUTER_REASONING_MODE_ENABLED:
        extra_body["reasoning"] = {"effort": reasoning_effort} if reasoning_effort else {"enabled": True}

    return extra_body


def apply_model_target_request_options(request_kwargs: dict[str, Any], target: dict[str, Any] | None) -> dict[str, Any]:
    merged_request_kwargs = dict(request_kwargs)
    record = target.get("record") if isinstance(target, dict) else None
    settings = target.get("settings") if isinstance(target, dict) else None
    prepared_messages = _prepare_model_request_messages(merged_request_kwargs.get("messages"), record, settings)
    if prepared_messages is not merged_request_kwargs.get("messages"):
        merged_request_kwargs["messages"] = prepared_messages
    # Add top-level cache_control for Anthropic models (OpenRouter API format)
    if _should_add_openrouter_top_level_cache_control(record, settings):
        merged_request_kwargs["cache_control"] = _build_cache_control(
            _get_openrouter_anthropic_ttl(settings)
        )
    extra_body = target.get("extra_body") if isinstance(target, dict) else None
    if isinstance(extra_body, dict) and extra_body:
        existing_extra_body = merged_request_kwargs.get("extra_body")
        if not isinstance(existing_extra_body, dict):
            existing_extra_body = {}
        merged_request_kwargs["extra_body"] = _merge_nested_dicts(existing_extra_body, extra_body)
    return merged_request_kwargs


def _should_add_openrouter_top_level_cache_control(record: dict[str, Any] | None, settings: dict[str, Any] | None) -> bool:
    """Check if top-level cache_control should be added for the model."""
    if not isinstance(record, dict):
        return False
    if str(record.get("provider") or "").strip() != OPENROUTER_PROVIDER:
        return False
    if not _is_openrouter_prompt_cache_enabled(settings):
        return False
    api_model = str(record.get("api_model") or "").strip()
    return _openrouter_supports_top_level_prompt_cache(api_model)


def _get_openrouter_anthropic_ttl(settings: dict[str, Any] | None) -> str:
    """Get the cache TTL for Anthropic models from settings."""
    if not isinstance(settings, dict):
        return "5m"
    raw_ttl = str(settings.get("openrouter_anthropic_cache_ttl") or "").strip().lower()
    return "1h" if raw_ttl == "1h" else "5m"



