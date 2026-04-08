from __future__ import annotations

import base64

from config import IMAGE_UPLOADS_DISABLED_FEATURE_ERROR, IMAGE_UPLOADS_ENABLED, OCR_ENABLED
from image_utils import (
    build_image_analysis_prompt,
    extract_json_object,
    extract_text_from_response_content,
    normalize_freeform_answer_text,
    normalize_image_analysis,
    optimize_image_for_processing,
)
from model_registry import (
    apply_model_target_request_options,
    can_model_process_images,
    can_model_use_structured_outputs,
    get_image_helper_model_id,
    normalize_image_processing_method,
    resolve_model_target,
)
from ocr_service import extract_image_text


def _build_multimodal_request(image_url: str, prompt_text: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
    ]


def _resolve_helper_model_id(settings: dict | None = None, *, fallback_model_id: str = "") -> str:
    candidate = get_image_helper_model_id(settings)
    if candidate and can_model_process_images(candidate, settings):
        return candidate

    fallback_candidate = str(fallback_model_id or "").strip()
    if fallback_candidate and can_model_process_images(fallback_candidate, settings):
        return fallback_candidate

    return ""


def can_answer_image_questions(settings: dict | None = None, *, fallback_model_id: str = "") -> bool:
    return bool(_resolve_helper_model_id(settings, fallback_model_id=fallback_model_id))


def _run_helper_llm_image_analysis(
    image_bytes: bytes,
    mime_type: str,
    *,
    user_text: str = "",
    model_id: str,
    settings: dict | None = None,
) -> dict:
    helper_model_id = _resolve_helper_model_id(settings, fallback_model_id=model_id)
    if not helper_model_id:
        raise RuntimeError("No helper image model is available for visual analysis.")

    optimized_bytes, optimized_mime_type = optimize_image_for_processing(image_bytes, mime_type, purpose="vision")
    image_b64 = base64.b64encode(optimized_bytes).decode("utf-8")
    image_url = f"data:{optimized_mime_type};base64,{image_b64}"
    target = resolve_model_target(helper_model_id, settings)

    request_kwargs = {
        "model": target["api_model"],
        "messages": _build_multimodal_request(image_url, build_image_analysis_prompt(user_text=user_text)),
        "temperature": 0.2,
    }
    if can_model_use_structured_outputs(helper_model_id, settings):
        request_kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "image_analysis",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "vision_summary": {
                            "type": "string",
                            "description": "Concise non-text visual summary in English.",
                        },
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Short English bullets with relevant visual observations.",
                        },
                        "assistant_guidance": {
                            "type": "string",
                            "description": "One short English sentence telling a downstream LLM how to use the analysis.",
                        },
                    },
                    "required": ["vision_summary", "key_points", "assistant_guidance"],
                    "additionalProperties": False,
                },
            },
        }

    request_kwargs = apply_model_target_request_options(request_kwargs, target)
    response = target["client"].chat.completions.create(**request_kwargs)
    choice = response.choices[0] if getattr(response, "choices", None) else None
    message = getattr(choice, "message", None) if choice else None
    raw_output = extract_text_from_response_content(getattr(message, "content", "")).strip()
    parsed_output = extract_json_object(raw_output)
    normalized = normalize_image_analysis(parsed_output, fallback_text=raw_output)
    normalized["analysis_method"] = "llm_helper"
    return normalized


def _prepare_direct_multimodal_analysis(model_id: str, settings: dict | None = None) -> dict:
    if not model_id or not can_model_process_images(model_id, settings):
        raise RuntimeError("The selected chat model does not support direct image input.")
    return normalize_image_analysis(
        {
            "analysis_method": "llm_direct",
            "assistant_guidance": "The original image will be attached directly to the active multimodal chat model.",
        }
    )


def _run_local_ocr_analysis(image_bytes: bytes, mime_type: str) -> dict:
    if not OCR_ENABLED:
        raise RuntimeError("Local OCR is disabled.")
    return {
        "ocr_text": extract_image_text(image_bytes, mime_type),
        "analysis_method": "local_ocr",
    }


def _resolve_processing_plan(processing_method: str, model_id: str, settings: dict | None = None) -> list[str]:
    helper_available = can_answer_image_questions(settings, fallback_model_id=model_id)
    direct_available = bool(model_id and can_model_process_images(model_id, settings))

    if processing_method == "llm_helper":
        plan = []
        if helper_available:
            plan.append("llm_helper")
        if direct_available:
            plan.append("llm_direct")
        return plan or ["local_ocr"]
    if processing_method == "llm_direct":
        plan = []
        if direct_available:
            plan.append("llm_direct")
        if helper_available:
            plan.append("llm_helper")
        return plan or ["local_ocr"]
    if processing_method == "local_ocr":
        return ["local_ocr"]

    if helper_available:
        plan = ["llm_helper"]
        if direct_available:
            plan.append("llm_direct")
        plan.append("local_ocr")
        return plan
    if direct_available:
        return ["llm_direct", "local_ocr"]
    return ["local_ocr"]


def analyze_uploaded_image(
    image_bytes: bytes,
    mime_type: str,
    user_text: str = "",
    *,
    model_id: str = "",
    settings: dict | None = None,
    processing_method: str = "auto",
) -> dict:
    if not IMAGE_UPLOADS_ENABLED:
        raise RuntimeError(IMAGE_UPLOADS_DISABLED_FEATURE_ERROR)

    normalized_method = normalize_image_processing_method(processing_method)
    last_error: Exception | None = None

    for step in _resolve_processing_plan(normalized_method, model_id, settings):
        try:
            if step == "llm_helper":
                return _run_helper_llm_image_analysis(
                    image_bytes,
                    mime_type,
                    user_text=user_text,
                    model_id=model_id,
                    settings=settings,
                )
            if step == "llm_direct":
                return _prepare_direct_multimodal_analysis(model_id, settings)
            if step == "local_ocr":
                return normalize_image_analysis(_run_local_ocr_analysis(image_bytes, mime_type))
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("No image processing method is currently available.")


def answer_image_question(
    image_bytes: bytes,
    mime_type: str,
    question: str,
    initial_analysis: dict | None = None,
    *,
    settings: dict | None = None,
    model_id: str = "",
) -> str:
    normalized_question = str(question or "").strip()
    if not normalized_question:
        raise ValueError("question is required.")

    helper_model_id = _resolve_helper_model_id(settings, fallback_model_id=model_id)
    if not helper_model_id:
        raise RuntimeError("No helper image model is available for follow-up image questions.")

    optimized_bytes, optimized_mime_type = optimize_image_for_processing(image_bytes, mime_type, purpose="vision")
    image_b64 = base64.b64encode(optimized_bytes).decode("utf-8")
    image_url = f"data:{optimized_mime_type};base64,{image_b64}"

    analysis = initial_analysis if isinstance(initial_analysis, dict) else {}
    analysis_method = str(analysis.get("analysis_method") or "").strip()
    summary = str(analysis.get("vision_summary") or "").strip()
    guidance = str(analysis.get("assistant_guidance") or "").strip()
    ocr_text = str(analysis.get("ocr_text") or "").strip()
    key_points = analysis.get("key_points") if isinstance(analysis.get("key_points"), list) else []

    prompt_parts = [
        "You are answering a follow-up question about a previously uploaded image.",
        "Use the image as the primary source of truth. Any stored OCR or summary is hint-only context.",
        "Always answer in English.",
        f"User question: {normalized_question}",
    ]
    if analysis_method:
        prompt_parts.append(f"Stored analysis source: {analysis_method}")
    if summary:
        prompt_parts.append(f"Stored summary hint: {summary}")
    if key_points:
        prompt_parts.append("Stored key observations:\n- " + "\n- ".join(str(point) for point in key_points if str(point or "").strip()))
    if guidance:
        prompt_parts.append(f"Stored guidance hint: {guidance}")
    if ocr_text:
        prompt_parts.append(f"Stored OCR hint: {ocr_text[:1500]}")
    prompt_parts.append(
        "Answer directly in English in 1-3 short paragraphs. If a detail is unreadable, say so briefly instead of guessing. Do not return JSON."
    )

    target = resolve_model_target(helper_model_id, settings)
    request_kwargs = {
        "model": target["api_model"],
        "messages": _build_multimodal_request(image_url, "\n".join(prompt_parts)),
        "temperature": 0.2,
    }
    request_kwargs = apply_model_target_request_options(request_kwargs, target)
    response = target["client"].chat.completions.create(**request_kwargs)
    choice = response.choices[0] if getattr(response, "choices", None) else None
    message = getattr(choice, "message", None) if choice else None
    raw_output = extract_text_from_response_content(getattr(message, "content", "")).strip()
    answer = normalize_freeform_answer_text(raw_output)
    if not answer:
        raise RuntimeError("Image follow-up model returned an empty answer.")
    return answer