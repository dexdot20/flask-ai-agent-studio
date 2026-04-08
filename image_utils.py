from __future__ import annotations

import json
import os
import re
from io import BytesIO

from config import IMAGE_ALLOWED_MIME_TYPES, IMAGE_MAX_BYTES

REMOTE_IMAGE_MAX_SIDE = 1280


def extract_text_from_response_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part and part.strip())
    return ""


def extract_json_object(raw_text: str) -> dict:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return {}

    try:
        parsed = json.loads(raw_text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end > start:
        candidate = raw_text[start : end + 1]
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def normalize_freeform_answer_text(raw_text: str) -> str:
    cleaned = str(raw_text or "").strip()
    if not cleaned:
        return ""

    fenced = re.match(r"^```(?:text|markdown)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    cleaned = re.sub(r"^answer\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def build_image_analysis_prompt(*, user_text: str = "", ocr_hint: str = "") -> str:
    prompt = (
        "Analyze the image for a text-first chat assistant. Return strict JSON with exactly these keys: "
        "vision_summary, key_points, assistant_guidance. "
        "vision_summary: a dense 2-4 sentence explanation in English that states what the image is, "
        "what the main regions or components are, and which visible relationships, states, or values matter most. "
        "If the image is a UI or screenshot, explain the screen's likely purpose, major panels, active selections, "
        "warnings, prices, totals, statuses, or controls that stand out. "
        "If the image is a chart, table, or document, explain what is being compared or organized and the standout "
        "values, structure, or trends. "
        "key_points: an array of 4-6 short English bullets with the most relevant observations, labels, values, "
        "warnings, selections, or layout clues. "
        "assistant_guidance: one short English sentence telling another LLM which cues from this analysis should "
        "drive the final answer. "
        "Do not transcribe visible text verbatim into vision_summary unless it is essential for understanding the image, "
        "because OCR handles raw text separately. "
        "Be specific and concrete. Avoid vague phrases like 'some interface' or 'various items'. "
        "Return JSON only."
    )
    if ocr_hint:
        prompt += (
            f" OCR already extracted likely text cues: {ocr_hint[:1500]}. "
            "Use them to interpret structure, emphasis, and relationships, but do not simply repeat them."
        )
    if user_text:
        prompt += f" The user's current request is: {user_text.strip()}"
    return prompt


def normalize_analysis_list(values, limit: int = 8) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in normalized:
            normalized.append(text[:300])
    return normalized[:limit]


def normalize_image_analysis(raw_analysis: dict, fallback_text: str = "") -> dict:
    raw_analysis = raw_analysis if isinstance(raw_analysis, dict) else {}
    raw_summary = str(raw_analysis.get("vision_summary") or "").strip()
    normalized = {
        "analysis_method": str(raw_analysis.get("analysis_method") or "").strip(),
        "ocr_text": str(raw_analysis.get("ocr_text") or "").strip(),
        "vision_summary": raw_summary,
        "assistant_guidance": str(raw_analysis.get("assistant_guidance") or "").strip(),
        "key_points": normalize_analysis_list(raw_analysis.get("key_points")),
    }

    if not normalized["vision_summary"]:
        if fallback_text:
            normalized["vision_summary"] = fallback_text.strip()[:500]
        elif normalized["ocr_text"]:
            normalized["vision_summary"] = "Readable text was detected in the image and added to the context."

    has_visual_context = bool(raw_summary or normalized["key_points"] or fallback_text)
    if not normalized["assistant_guidance"]:
        if normalized["ocr_text"] and has_visual_context:
            normalized["assistant_guidance"] = (
                "Use the extracted OCR text as the primary image context and the visual summary for non-text cues when answering the user."
            )
        elif normalized["ocr_text"]:
            normalized["assistant_guidance"] = "Use the extracted OCR text as the primary image context when answering the user."
        elif normalized["vision_summary"]:
            normalized["assistant_guidance"] = "Use the visual summary as the primary image context when answering the user."

    return normalized


def read_uploaded_image(uploaded_file):
    filename = os.path.basename((uploaded_file.filename or "").strip())
    if not filename:
        raise ValueError("Image file name is missing.")

    mime_type = (uploaded_file.mimetype or "").lower().strip()
    if mime_type not in IMAGE_ALLOWED_MIME_TYPES:
        raise ValueError("Unsupported file type. Upload PNG, JPG or WEBP.")

    image_bytes = uploaded_file.read()
    if not image_bytes:
        raise ValueError("Uploaded image is empty.")
    if len(image_bytes) > IMAGE_MAX_BYTES:
        raise ValueError("Image is too large. Upload a maximum of 10 MB.")

    return filename, mime_type, image_bytes


def optimize_image_for_processing(image_bytes: bytes, mime_type: str, *, purpose: str = "vision") -> tuple[bytes, str]:
    try:
        from PIL import Image, ImageEnhance, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow is required for image optimization.") from exc

    with Image.open(BytesIO(image_bytes)) as image:
        image = ImageOps.exif_transpose(image)
        normalized_purpose = str(purpose or "vision").strip().lower()

        if normalized_purpose == "ocr":
            width, height = image.size
            longest_side = max(width, height)
            target_longest_side = min(2200, max(longest_side, 1400))
            if target_longest_side != longest_side:
                scale = target_longest_side / float(longest_side)
                resized_size = (
                    max(28, int(width * scale)),
                    max(28, int(height * scale)),
                )
                image = image.resize(resized_size, Image.Resampling.LANCZOS)

            image = ImageOps.autocontrast(image.convert("L"), cutoff=1)
            image = ImageEnhance.Contrast(image).enhance(1.15)
            image = ImageEnhance.Sharpness(image).enhance(1.2)
            image = image.convert("RGB")

            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            optimized_mime_type = "image/png"
        else:
            width, height = image.size
            longest_side = max(width, height)

            if longest_side > REMOTE_IMAGE_MAX_SIDE:
                scale = REMOTE_IMAGE_MAX_SIDE / float(longest_side)
                resized_size = (
                    max(28, int(width * scale)),
                    max(28, int(height * scale)),
                )
                image = image.resize(resized_size, Image.Resampling.LANCZOS)

            has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
            output = BytesIO()
            if has_alpha:
                image.save(output, format="PNG", optimize=True)
                optimized_mime_type = "image/png"
            else:
                image = image.convert("RGB")
                image.save(output, format="JPEG", quality=92, optimize=True)
                optimized_mime_type = "image/jpeg"

    optimized_bytes = output.getvalue()
    return optimized_bytes, optimized_mime_type