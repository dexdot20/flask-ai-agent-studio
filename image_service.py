from __future__ import annotations

import base64

from config import IMAGE_UPLOADS_DISABLED_FEATURE_ERROR, IMAGE_UPLOADS_ENABLED, OCR_ENABLED, VISION_ENABLED
from model_registry import (
    apply_model_target_request_options,
    can_model_process_images,
    can_model_use_structured_outputs,
    normalize_image_processing_method,
    resolve_model_target,
)
from ocr_service import extract_image_text
from vision import (
    build_image_analysis_prompt,
    extract_json_object,
    extract_text_from_response_content,
    normalize_image_analysis,
    optimize_image_for_processing,
    run_image_vision_analysis,
)


def _build_llm_vision_request(image_url: str, user_text: str = "") -> list[dict]:
    analysis_prompt = build_image_analysis_prompt(user_text=user_text)

    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": analysis_prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
    ]


def _run_llm_image_analysis(
    image_bytes: bytes,
    mime_type: str,
    *,
    user_text: str = "",
    model_id: str,
    settings: dict | None = None,
) -> dict:
    if not model_id or not can_model_process_images(model_id, settings):
        raise RuntimeError("The selected chat model does not support visual analysis.")

    optimized_bytes, optimized_mime_type = optimize_image_for_processing(image_bytes, mime_type, purpose="vision")
    image_b64 = base64.b64encode(optimized_bytes).decode("utf-8")
    image_url = f"data:{optimized_mime_type};base64,{image_b64}"
    target = resolve_model_target(model_id, settings)

    request_kwargs = {
        "model": target["api_model"],
        "messages": _build_llm_vision_request(image_url, user_text=user_text),
        "temperature": 0.2,
    }
    if can_model_use_structured_outputs(model_id, settings):
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
    normalized["analysis_method"] = "llm"
    return normalized


def _run_local_ocr_analysis(image_bytes: bytes, mime_type: str) -> dict:
    if not OCR_ENABLED:
        raise RuntimeError("Local OCR is disabled.")
    return {
        "ocr_text": extract_image_text(image_bytes, mime_type),
        "analysis_method": "local_ocr",
    }


def _run_local_vision_analysis(image_bytes: bytes, mime_type: str, user_text: str = "", *, ocr_hint: str = "") -> dict:
    if not VISION_ENABLED:
        raise RuntimeError("Local vision is disabled.")
    analysis = run_image_vision_analysis(image_bytes, mime_type, user_text=user_text, ocr_hint=ocr_hint)
    analysis["analysis_method"] = "local_vl"
    return analysis


def _resolve_processing_plan(processing_method: str, model_id: str, settings: dict | None = None) -> list[str]:
    llm_available = bool(model_id and can_model_process_images(model_id, settings))
    if processing_method == "llm":
        return ["llm", "local_both", "local_vl", "local_ocr"] if llm_available else ["local_both", "local_vl", "local_ocr"]
    if processing_method == "local_both":
        return ["local_both", "local_vl", "local_ocr"]
    if processing_method == "local_vl":
        return ["local_vl", "local_ocr"]
    if processing_method == "local_ocr":
        return ["local_ocr", "local_vl"]
    if llm_available:
        return ["llm", "local_both", "local_vl", "local_ocr"]
    return ["local_both", "local_vl", "local_ocr"]


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
            if step == "llm":
                return _run_llm_image_analysis(
                    image_bytes,
                    mime_type,
                    user_text=user_text,
                    model_id=model_id,
                    settings=settings,
                )
            if step == "local_ocr":
                return normalize_image_analysis(_run_local_ocr_analysis(image_bytes, mime_type))
            if step == "local_vl":
                return normalize_image_analysis(_run_local_vision_analysis(image_bytes, mime_type, user_text=user_text))
            if step == "local_both":
                combined_analysis = {}
                completed_methods = []
                ocr_hint = ""
                if OCR_ENABLED:
                    ocr_analysis = _run_local_ocr_analysis(image_bytes, mime_type)
                    combined_analysis.update(ocr_analysis)
                    ocr_hint = str(ocr_analysis.get("ocr_text") or "").strip()
                    completed_methods.append("ocr")
                if VISION_ENABLED:
                    combined_analysis.update(
                        _run_local_vision_analysis(
                            image_bytes,
                            mime_type,
                            user_text=user_text,
                            ocr_hint=ocr_hint,
                        )
                    )
                    completed_methods.append("vision")

                if completed_methods == ["ocr", "vision"]:
                    combined_analysis["analysis_method"] = "local_both"
                elif completed_methods == ["vision"]:
                    combined_analysis["analysis_method"] = "local_vl"
                elif completed_methods == ["ocr"]:
                    combined_analysis["analysis_method"] = "local_ocr"
                else:
                    raise RuntimeError("No local image processors are enabled.")
                return normalize_image_analysis(combined_analysis)
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("No image processing method is currently available.")