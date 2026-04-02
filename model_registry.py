from __future__ import annotations

import json
import os
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
IMAGE_PROCESSING_METHODS = {"auto", "llm", "local_ocr", "local_vl", "local_both"}
MODEL_OPERATION_KEYS = (
    "summarize",
    "prune",
    "fix_text",
    "generate_title",
    "upload_metadata",
    "sub_agent",
)
DEFAULT_OPERATION_MODEL_PREFERENCES = {key: "" for key in MODEL_OPERATION_KEYS}
DEFAULT_OPERATION_MODEL_FALLBACK_PREFERENCES = {key: [] for key in MODEL_OPERATION_KEYS}
_EMPTY_PRICING = {"input": 0.0, "input_cache_hit": 0.0, "output": 0.0}
_OPENROUTER_PROVIDER_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,199}$")
_OPENROUTER_GEMINI_CACHE_BREAKPOINT_MIN_TOKENS_DEFAULT = 1028
_OPENROUTER_GEMINI_CACHE_BREAKPOINT_MIN_TOKENS_PRO = 2048


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
        try:
            close_response = getattr(self._response, "close", None)
            if callable(close_response):
                try:
                    close_response()
                except Exception:
                    pass
        finally:
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
        "pricing": {"input": 0.28, "input_cache_hit": 0.028, "output": 0.42},
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
        "pricing": {"input": 0.28, "input_cache_hit": 0.028, "output": 0.42},
    },
]
BUILTIN_MODEL_IDS = {model["id"] for model in BUILTIN_MODELS}
DEFAULT_VISIBLE_CHAT_MODEL_ORDER = [
    model["id"] for model in BUILTIN_MODELS if model.get("supports_tools")
]


def _copy_model_record(record: dict[str, Any]) -> dict[str, Any]:
    copied = dict(record)
    pricing = copied.get("pricing")
    if isinstance(pricing, dict):
        copied["pricing"] = dict(pricing)
    return copied


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


def _openrouter_gemini_cache_min_tokens(api_model: Any) -> int:
    normalized_api_model = str(api_model or "").strip().lower()
    if "flash" in normalized_api_model:
        return _OPENROUTER_GEMINI_CACHE_BREAKPOINT_MIN_TOKENS_DEFAULT
    if "pro" in normalized_api_model:
        return _OPENROUTER_GEMINI_CACHE_BREAKPOINT_MIN_TOKENS_PRO
    return _OPENROUTER_GEMINI_CACHE_BREAKPOINT_MIN_TOKENS_DEFAULT


def _with_openrouter_cache_breakpoint(content: Any, *, min_tokens: int) -> tuple[Any, bool]:
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
        normalized_blocks[last_text_index]["cache_control"] = {"type": "ephemeral"}
        return normalized_blocks, True

    text = str(content or "").strip()
    if not text or estimate_text_tokens(text) < min_tokens:
        return content, False
    return ([{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}], True)


def _prepare_model_request_messages(messages: Any, record: dict[str, Any] | None) -> Any:
    if not isinstance(messages, list) or not isinstance(record, dict):
        return messages
    if str(record.get("provider") or "").strip() != OPENROUTER_PROVIDER:
        return messages

    api_model = str(record.get("api_model") or "").strip()
    if not _openrouter_requires_explicit_cache_breakpoints(api_model):
        return messages

    prepared_messages = list(messages)
    cache_min_tokens = _openrouter_gemini_cache_min_tokens(api_model)
    fallback_index: int | None = None
    for index, message in enumerate(prepared_messages):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        if fallback_index is None and role not in {"system", "developer"}:
            fallback_index = index
        if role not in {"system", "developer"}:
            continue
        updated_content, applied = _with_openrouter_cache_breakpoint(message.get("content"), min_tokens=cache_min_tokens)
        if not applied:
            continue
        prepared_messages[index] = {**message, "content": updated_content}
        return prepared_messages

    if fallback_index is None or fallback_index >= len(prepared_messages):
        return prepared_messages

    fallback_message = prepared_messages[fallback_index]
    if not isinstance(fallback_message, dict):
        return prepared_messages
    updated_content, applied = _with_openrouter_cache_breakpoint(fallback_message.get("content"), min_tokens=cache_min_tokens)
    if not applied:
        return prepared_messages
    prepared_messages[fallback_index] = {**fallback_message, "content": updated_content}
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
        "pricing": dict(_EMPTY_PRICING),
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


def normalize_operation_model_fallback_preferences(raw_value: Any, settings: dict | None = None) -> dict[str, list[str]]:
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
    return normalize_operation_model_fallback_preferences(settings.get("operation_model_fallback_preferences"), settings)


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
        if configured_fallback_model and is_valid_model_id(configured_fallback_model, settings) and configured_fallback_model not in candidates:
            candidates.append(configured_fallback_model)

    normalized_fallback = canonicalize_model_id(fallback_model_id)
    if normalized_fallback and is_valid_model_id(normalized_fallback, settings) and normalized_fallback not in candidates:
        candidates.append(normalized_fallback)

    default_chat_model = get_default_chat_model_id(settings)
    if default_chat_model and is_valid_model_id(default_chat_model, settings) and default_chat_model not in candidates:
        candidates.append(default_chat_model)

    return candidates


def normalize_image_processing_method(value: Any) -> str:
    method = str(value or DEFAULT_IMAGE_PROCESSING_METHOD).strip().lower()
    if method in IMAGE_PROCESSING_METHODS:
        return method
    return DEFAULT_IMAGE_PROCESSING_METHOD


def can_model_use_tools(model_id: str, settings: dict | None = None) -> bool:
    record = get_model_record(model_id, settings)
    return bool(record and record.get("supports_tools"))


def can_model_process_images(model_id: str, settings: dict | None = None) -> bool:
    record = get_model_record(model_id, settings)
    return bool(record and record.get("supports_vision"))


def can_model_use_structured_outputs(model_id: str, settings: dict | None = None) -> bool:
    record = get_model_record(model_id, settings)
    return bool(record and record.get("supports_structured_outputs"))


@lru_cache(maxsize=2)
def get_provider_client(provider: str) -> OpenAI:
    if provider == DEEPSEEK_PROVIDER:
        return OpenAI(
            api_key=(os.getenv("DEEPSEEK_API_KEY") or "").strip(),
            base_url="https://api.deepseek.com",
        )
    if provider == OPENROUTER_PROVIDER:
        default_headers: dict[str, str] = {}
        http_referer = (os.getenv("OPENROUTER_HTTP_REFERER") or os.getenv("OPENROUTER_SITE_URL") or "").strip()
        app_title = (os.getenv("OPENROUTER_APP_TITLE") or os.getenv("OPENROUTER_X_TITLE") or "").strip()
        if http_referer:
            default_headers["HTTP-Referer"] = http_referer
        if app_title:
            default_headers["X-OpenRouter-Title"] = app_title

        kwargs: dict[str, Any] = {
            "api_key": (os.getenv("OPENROUTER_API_KEY") or "").strip(),
            "base_url": "https://openrouter.ai/api/v1",
        }
        if default_headers:
            kwargs["default_headers"] = default_headers
        return _OpenRouterClientProxy(kwargs)
    raise ValueError(f"Unsupported provider: {provider}")


def resolve_model_target(model_id: str, settings: dict | None = None) -> dict[str, Any]:
    record = get_model_record(model_id, settings)
    if not record:
        raise ValueError(f"Unsupported model: {model_id}")
    return {
        "record": record,
        "client": get_provider_client(str(record["provider"])),
        "api_model": str(record["api_model"]),
        "extra_body": build_model_request_extra_body(record),
    }


def build_model_request_extra_body(record: dict[str, Any] | None) -> dict[str, Any]:
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

    api_model = str(record.get("api_model") or "").strip()
    if _openrouter_supports_top_level_prompt_cache(api_model):
        extra_body["cache_control"] = {"type": "ephemeral"}

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
    prepared_messages = _prepare_model_request_messages(merged_request_kwargs.get("messages"), record)
    if prepared_messages is not merged_request_kwargs.get("messages"):
        merged_request_kwargs["messages"] = prepared_messages
    extra_body = target.get("extra_body") if isinstance(target, dict) else None
    if isinstance(extra_body, dict) and extra_body:
        existing_extra_body = merged_request_kwargs.get("extra_body")
        if not isinstance(existing_extra_body, dict):
            existing_extra_body = {}
        merged_request_kwargs["extra_body"] = _merge_nested_dicts(existing_extra_body, extra_body)
    return merged_request_kwargs


def get_model_pricing(model_id: str, settings: dict | None = None) -> dict[str, float]:
    record = get_model_record(model_id, settings)
    if not record:
        return dict(_EMPTY_PRICING)
    pricing = record.get("pricing")
    if isinstance(pricing, dict):
        return {
            "input": float(pricing.get("input") or 0.0),
            "input_cache_hit": float(pricing.get("input_cache_hit") or 0.0),
            "output": float(pricing.get("output") or 0.0),
        }
    return dict(_EMPTY_PRICING)


def has_known_model_pricing(model_id: str, settings: dict | None = None) -> bool:
    pricing = get_model_pricing(model_id, settings)
    return any(float(pricing.get(key) or 0.0) > 0.0 for key in ("input", "input_cache_hit", "output"))