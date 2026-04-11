from __future__ import annotations

import json
from types import SimpleNamespace


def build_stream_chunk(reasoning: str = "", content: str = "", tool_calls=None, usage=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    reasoning_content=reasoning,
                    content=content,
                    tool_calls=tool_calls or [],
                )
            )
        ]
        if (reasoning or content or tool_calls)
        else [],
        usage=usage,
    )


def build_stream_chunk_openrouter(
    reasoning: str = "",
    content: str = "",
    reasoning_details=None,
    tool_calls=None,
    usage=None,
):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    reasoning=reasoning,
                    reasoning_details=reasoning_details or [],
                    content=content,
                    tool_calls=tool_calls or [],
                )
            )
        ]
        if (reasoning or content or tool_calls or reasoning_details)
        else [],
        usage=usage,
    )


def build_tool_call_chunk(name: str, arguments: dict, call_id: str = "tool-call-1", index: int = 0):
    return build_stream_chunk(
        tool_calls=[
            {
                "index": index,
                "id": call_id,
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        ]
    )
