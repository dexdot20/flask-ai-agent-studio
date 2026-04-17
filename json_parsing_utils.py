from __future__ import annotations

import ast
import json
from typing import Callable


RepairJsonCallable = Callable[..., object]


def parse_json_like_text(
    text: str,
    *,
    repair_json_func: RepairJsonCallable | None = None,
    repair_objects_only: bool = True,
):
    raw_text = str(text or "").strip()
    if not raw_text:
        return None

    try:
        return json.loads(raw_text)
    except Exception:
        pass

    try:
        return ast.literal_eval(raw_text)
    except Exception:
        pass

    if not callable(repair_json_func):
        return None
    if repair_objects_only and not raw_text.lstrip().startswith("{"):
        return None

    try:
        repaired = repair_json_func(raw_text, return_objects=True, ensure_ascii=False)
    except TypeError:
        try:
            repaired = repair_json_func(raw_text)
        except Exception:
            return None
    except Exception:
        return None

    if isinstance(repaired, (dict, list)):
        return repaired
    return None


def extract_first_balanced_json_like_fragment(
    text: str,
    *,
    allowed_openers: str = "{[",
) -> str | None:
    raw_text = str(text or "")
    if not raw_text:
        return None

    start_indexes = [raw_text.find(opener) for opener in allowed_openers]
    start_indexes = [index for index in start_indexes if index >= 0]
    if not start_indexes:
        return None
    start_index = min(start_indexes)

    stack: list[str] = [raw_text[start_index]]
    in_string: str | None = None
    escape_next = False

    for index in range(start_index + 1, len(raw_text)):
        char = raw_text[index]

        if in_string:
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == in_string:
                in_string = None
            continue

        if char in {'"', "'"}:
            in_string = char
            continue

        if char in "[{":
            stack.append(char)
            continue

        if char in "]}":
            if not stack:
                return None
            top = stack[-1]
            if top == "{" and char == "}":
                stack.pop()
            elif top == "[" and char == "]":
                stack.pop()
            else:
                return None
            if not stack:
                return raw_text[start_index : index + 1]

    return None


def close_unbalanced_json_like_fragment(
    text: str,
    *,
    allowed_openers: str = "{[",
) -> str | None:
    raw_text = str(text or "").strip()
    if not raw_text:
        return None

    first_fragment = extract_first_balanced_json_like_fragment(raw_text, allowed_openers=allowed_openers)
    if first_fragment:
        return first_fragment

    opener_indexes = [raw_text.find(opener) for opener in allowed_openers]
    opener_indexes = [index for index in opener_indexes if index >= 0]
    if not opener_indexes:
        return None

    start_index = min(opener_indexes)
    fragment = raw_text[start_index:]

    stack: list[str] = []
    in_string: str | None = None
    escape_next = False

    for char in fragment:
        if in_string:
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == in_string:
                in_string = None
            continue

        if char in {'"', "'"}:
            in_string = char
            continue
        if char in "[{":
            stack.append(char)
            continue
        if char == "]":
            if not stack or stack[-1] != "[":
                return None
            stack.pop()
            continue
        if char == "}":
            if not stack or stack[-1] != "{":
                return None
            stack.pop()

    if in_string or escape_next or not stack:
        return None

    closing_suffix = "".join("}" if opener == "{" else "]" for opener in reversed(stack))
    return f"{fragment}{closing_suffix}"
