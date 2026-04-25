from __future__ import annotations

import csv
import io
import logging
import os
import re
import unicodedata

import pdfplumber
from docx import Document
from docx.table import Table as _DocxTable
from docx.text.paragraph import Paragraph as _DocxParagraph

from config import (
    DOCUMENT_ALLOWED_MIME_TYPES,
    DOCUMENT_MAX_BYTES,
    DOCUMENT_MAX_TEXT_CHARS,
    OCR_ENABLED,
)

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_PDF = "application/pdf"
MIME_PLAIN = "text/plain"
MIME_CSV = "text/csv"
MIME_MARKDOWN = "text/markdown"

_EXTENSION_TO_MIME: dict[str, str] = {
    ".docx": MIME_DOCX,
    ".pdf": MIME_PDF,
    ".txt": MIME_PLAIN,
    ".csv": MIME_CSV,
    ".md": MIME_MARKDOWN,
    ".py": MIME_PLAIN,
    ".js": MIME_PLAIN,
    ".ts": MIME_PLAIN,
    ".tsx": MIME_PLAIN,
    ".jsx": MIME_PLAIN,
    ".json": MIME_PLAIN,
    ".html": MIME_PLAIN,
    ".css": MIME_PLAIN,
    ".scss": MIME_PLAIN,
    ".sh": MIME_PLAIN,
    ".sql": MIME_PLAIN,
    ".yaml": MIME_PLAIN,
    ".yml": MIME_PLAIN,
}

_CODE_LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".json": "json",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sh": "bash",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
}

LOGGER = logging.getLogger(__name__)


def guess_document_mime_type(filename: str, declared_mime: str) -> str:
    declared = (declared_mime or "").strip().lower()
    if declared in DOCUMENT_ALLOWED_MIME_TYPES:
        return declared
    ext = os.path.splitext(filename or "")[-1].lower()
    return _EXTENSION_TO_MIME.get(ext, declared)


def read_uploaded_document(uploaded_file) -> tuple[str, str, bytes]:
    filename = os.path.basename((uploaded_file.filename or "").strip())
    declared_mime = (uploaded_file.mimetype or "").lower().strip()
    mime_type = guess_document_mime_type(filename, declared_mime)
    if mime_type not in DOCUMENT_ALLOWED_MIME_TYPES:
        raise ValueError("Unsupported document type. Upload DOCX, PDF, TXT, CSV or MD.")
    doc_bytes = uploaded_file.read()
    if not doc_bytes:
        raise ValueError("Uploaded document is empty.")
    if len(doc_bytes) > DOCUMENT_MAX_BYTES:
        raise ValueError(f"Document is too large. Upload a maximum of {DOCUMENT_MAX_BYTES // (1024 * 1024)} MB.")
    return filename, mime_type, doc_bytes


def _format_table_as_markdown(table: list[list]) -> str:
    """Convert a list-of-rows (each row is a list of cell strings) to a markdown table."""
    if not table:
        return ""
    rows = [[str(cell or "").replace("|", "\\|").replace("\n", " ").strip() for cell in row] for row in table]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return ""
    col_count = max(len(row) for row in rows)
    rows = [row + [""] * (col_count - len(row)) for row in rows]
    header = "| " + " | ".join(rows[0]) + " |"
    separator = "| " + " | ".join(["---"] * col_count) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join([header, separator] + body_lines)


def _extract_text_from_docx(doc_bytes: bytes) -> str:
    document = Document(io.BytesIO(doc_bytes))
    parts: list[str] = []
    for element in document.element.body:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        if tag == "p":
            para = _DocxParagraph(element, document)
            text = para.text.strip()
            if text:
                parts.append(text)
        elif tag == "tbl":
            table = _DocxTable(element, document)
            rows = [
                [cell.text.replace("\n", " ").strip() for cell in row.cells]
                for row in table.rows
            ]
            md = _format_table_as_markdown(rows)
            if md:
                parts.append(md)
    return "\n\n".join(parts)


_PDF_OCR_MIN_TEXT_CHARS = 20
_PDF_OCR_RENDER_DPI = 200

# Non-convertible content markers for PDF pages
_NON_CONVERTIBLE_IMAGE = "[non-convertible content: image]"
_NON_CONVERTIBLE_DRAWING = "[non-convertible content: drawing]"


def _build_pdf_ocr_unavailable_notice(status: str) -> str:
    normalized_status = str(status or "").strip().lower()
    if normalized_status == "disabled":
        return "[OCR fallback unavailable: OCR is disabled, so image-only PDF content may be incomplete.]"
    if normalized_status == "unavailable":
        return "[OCR fallback unavailable: OCR dependencies are missing, so image-only PDF content may be incomplete.]"
    if normalized_status == "failed":
        return "[OCR fallback failed on this page; image-only PDF content may be incomplete.]"
    return ""


def _extract_text_from_pdf_ocr(page) -> tuple[str, str]:
    try:
        from ocr_service import extract_image_text
    except ImportError:
        return "", "unavailable"

    try:
        page_image = page.to_image(
            resolution=_PDF_OCR_RENDER_DPI,
            antialias=True,
            force_mediabox=True,
        )
        image_buffer = io.BytesIO()
        page_image.original.save(image_buffer, format="PNG")
        extracted_text = extract_image_text(image_buffer.getvalue(), "image/png").strip()
        return extracted_text, ("ok" if extracted_text else "empty")
    except RuntimeError as exc:
        LOGGER.warning("PDF OCR fallback runtime failure: %s", exc)
        if not OCR_ENABLED or "disabled" in str(exc).lower():
            return "", "disabled"
        return "", "failed"
    except Exception as exc:
        LOGGER.warning("PDF OCR fallback failed: %s", exc)
        return "", "failed"


def _clean_pdf_text(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", str(text or ""))
    cleaned = cleaned.replace("\u00ad", "").replace("\xa0", " ")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_markdown_tables_from_page(page) -> list[str]:
    table_chunks: list[str] = []
    try:
        tables = page.find_tables() or []
    except Exception:
        tables = []
    for table in tables:
        try:
            markdown = _format_table_as_markdown(table.extract())
        except Exception:
            markdown = ""
        if markdown:
            table_chunks.append(markdown)
    return table_chunks


def _extract_text_from_pdf(doc_bytes: bytes) -> str:
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(doc_bytes)) as pdf:
        multi_page = len(pdf.pages) > 1
        for page_num, page in enumerate(pdf.pages, start=1):
            page_parts: list[str] = []
            page_images = list(getattr(page, "images", None) or [])
            has_drawings = bool(getattr(page, "drawings", None))

            table_chunks = _extract_markdown_tables_from_page(page)
            if table_chunks:
                page_parts.extend(table_chunks)

            plain_text = _clean_pdf_text(page.extract_text() or "")
            if plain_text:
                page_parts.insert(0, plain_text)

            # Handle image-only pages with OCR fallback
            if not plain_text and page_images:
                ocr_text, ocr_status = _extract_text_from_pdf_ocr(page)
                cleaned_ocr_text = _clean_pdf_text(ocr_text)
                if cleaned_ocr_text:
                    page_parts.insert(0, cleaned_ocr_text)
                else:
                    ocr_notice = _build_pdf_ocr_unavailable_notice(ocr_status)
                    if ocr_notice:
                        page_parts.append(ocr_notice)
                    page_parts.append(_NON_CONVERTIBLE_IMAGE)

            # If extracted text is too short but page has images, try OCR
            if page_parts and len(_clean_pdf_text("\n\n".join(page_parts))) < _PDF_OCR_MIN_TEXT_CHARS and page_images:
                ocr_text, _ocr_status = _extract_text_from_pdf_ocr(page)
                cleaned_ocr_text = _clean_pdf_text(ocr_text)
                if cleaned_ocr_text:
                    page_parts.insert(0, cleaned_ocr_text)
                elif _NON_CONVERTIBLE_IMAGE not in page_parts:
                    page_parts.append(_NON_CONVERTIBLE_IMAGE)

            # Report drawings if present (regardless of images)
            if has_drawings:
                page_parts.append(_NON_CONVERTIBLE_DRAWING)

            if not page_parts:
                # Page with no extractable content at all
                page_parts.append(_NON_CONVERTIBLE_IMAGE)
                continue

            page_content = "\n\n".join(part for part in page_parts if part)
            if not page_content:
                continue
            if multi_page:
                parts.append(f"## Page {page_num}\n\n{page_content}")
            else:
                parts.append(page_content)

    return ("\n\n---\n\n" if len(parts) > 1 else "\n\n").join(parts)


def _extract_text_plain(doc_bytes: bytes) -> str:
    return doc_bytes.decode("utf-8-sig", errors="replace").strip()


def _extract_text_csv(doc_bytes: bytes) -> str:
    text = doc_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows: list[list[str]] = []
    for row in reader:
        stripped = [cell.strip() for cell in row]
        if any(stripped):
            rows.append(stripped)
    return _format_table_as_markdown(rows) if rows else ""


def extract_document_text(doc_bytes: bytes, mime_type: str) -> str:
    mime = (mime_type or "").strip().lower()
    if mime == MIME_DOCX:
        return _extract_text_from_docx(doc_bytes)
    if mime == MIME_PDF:
        try:
            return _extract_text_from_pdf(doc_bytes)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Could not read the PDF document: {exc}") from exc
    if mime == MIME_CSV:
        return _extract_text_csv(doc_bytes)
    if mime in (MIME_PLAIN, MIME_MARKDOWN):
        return _extract_text_plain(doc_bytes)
    raise ValueError(f"No text extractor for MIME type: {mime}")


def infer_canvas_language(filename: str) -> str | None:
    ext = os.path.splitext(filename or "")[-1].lower()
    return _CODE_LANGUAGE_BY_EXTENSION.get(ext)


def infer_canvas_format(filename: str) -> str:
    return "code" if infer_canvas_language(filename) else "markdown"


def build_canvas_markdown(filename: str, text: str) -> str:
    name = os.path.basename(filename or "document")
    if infer_canvas_format(name) == "code":
        return text.rstrip("\n")
    if os.path.splitext(name)[-1].lower() == ".md":
        return text
    return f"# {name}\n\n{text}"


def build_document_context_block(filename: str, text: str) -> tuple[str, bool]:
    name = os.path.basename(filename or "document")
    source_text = str(text or "")
    truncated = len(source_text) > DOCUMENT_MAX_TEXT_CHARS
    clipped_source_text = source_text[:DOCUMENT_MAX_TEXT_CHARS] if truncated else source_text
    rendered_text = (
        build_canvas_markdown(name, clipped_source_text)
        if infer_canvas_format(name) == "markdown"
        else clipped_source_text
    )
    header = f"[Uploaded document: {name}]"
    if truncated:
        header += " (truncated to first 50,000 characters)"
    return f"{header}\n{rendered_text}", truncated
