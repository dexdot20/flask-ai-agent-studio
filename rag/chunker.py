from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

from config import RAG_CHUNK_OVERLAP, RAG_CHUNK_SIZE

DEFAULT_CHUNK_SIZE = RAG_CHUNK_SIZE
DEFAULT_CHUNK_OVERLAP = RAG_CHUNK_OVERLAP
MAX_METADATA_VALUE_LENGTH = 500
_INVISIBLE_TEXT_RE = re.compile(r"[\u00ad\u200b-\u200f\u2028\u2029\ufeff]")
_PAGE_MARKER_RE = re.compile(r"^##\s+Page\s+(\d+)\s*$", re.IGNORECASE)
_SECTION_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")


@dataclass(slots=True)
class Chunk:
    id: str
    text: str
    source_name: str
    source_type: str
    category: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)

    def to_metadata(self) -> dict:
        metadata = {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "category": normalize_category(self.category),
            "chunk_index": self.chunk_index,
        }
        for key, value in (self.metadata or {}).items():
            if value in (None, ""):
                continue
            metadata[str(key)] = _normalize_metadata_value(value)
        return metadata


def normalize_category(category: str | None) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", str(category or "general").strip().lower()).strip("-")
    return cleaned or "general"


def _normalize_whitespace(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = _INVISIBLE_TEXT_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_metadata_value(value):
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())[:MAX_METADATA_VALUE_LENGTH]
    return str(value).strip()[:MAX_METADATA_VALUE_LENGTH]


def _paragraphs_from_text(text: str) -> list[str]:
    normalized = _normalize_whitespace(text)
    if not normalized:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    if paragraphs:
        return paragraphs
    return [normalized]


def _slice_long_paragraph(paragraph: str, chunk_size: int, overlap: int) -> Iterable[str]:
    if len(paragraph) <= chunk_size:
        yield paragraph
        return

    start = 0
    step = max(1, chunk_size - max(0, overlap))
    while start < len(paragraph):
        end = min(len(paragraph), start + chunk_size)
        yield paragraph[start:end].strip()
        if end >= len(paragraph):
            break
        start += step


def _paragraph_page_number(paragraph: str, fallback_page_number: int | None) -> int | None:
    first_line = str(paragraph or "").split("\n", 1)[0].strip()
    match = _PAGE_MARKER_RE.match(first_line)
    if match:
        return int(match.group(1))
    return fallback_page_number


def _normalize_section_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", str(value or "").strip().lower()).strip("-")
    return cleaned or "section"


def _extract_section_title(paragraph: str) -> str | None:
    first_line = str(paragraph or "").split("\n", 1)[0].strip()
    match = _SECTION_HEADING_RE.match(first_line)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or None


def split_text_into_chunks(
    text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP
) -> list[str]:
    chunk_size = max(300, int(chunk_size or DEFAULT_CHUNK_SIZE))
    overlap = max(0, min(int(overlap or DEFAULT_CHUNK_OVERLAP), chunk_size // 2))
    paragraphs = _paragraphs_from_text(text)
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        pieces = list(_slice_long_paragraph(paragraph, chunk_size, overlap))
        for piece in pieces:
            if not current:
                current = piece
                continue
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) <= chunk_size:
                current = candidate
                continue
            chunks.append(current.strip())
            carry = current[-overlap:].strip() if overlap and len(current) > overlap else ""
            current = f"{carry}\n\n{piece}".strip() if carry else piece
            if len(current) > chunk_size:
                overflow_parts = list(_slice_long_paragraph(current, chunk_size, overlap))
                chunks.extend(overflow_parts[:-1])
                current = overflow_parts[-1]

    if current.strip():
        chunks.append(current.strip())

    deduped: list[str] = []
    for chunk in chunks:
        cleaned = _normalize_whitespace(chunk)
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _build_chunk_id(source_name: str, source_type: str, category: str, text: str) -> str:
    digest = hashlib.sha1(f"{source_name}|{source_type}|{category}|{text}".encode("utf-8")).hexdigest()
    return f"chunk-{digest}"


def chunk_text_document(
    text: str,
    source_name: str,
    source_type: str,
    category: str,
    metadata: dict | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    normalized_category = normalize_category(category)
    normalized_text = _normalize_whitespace(text)
    if not normalized_text:
        return []

    chunk_size = max(300, int(chunk_size or DEFAULT_CHUNK_SIZE))
    overlap = max(0, min(int(overlap or DEFAULT_CHUNK_OVERLAP), chunk_size // 2))
    paragraphs = _paragraphs_from_text(normalized_text)
    if not paragraphs:
        return []

    base_metadata = dict(metadata or {})
    chunk_entries: list[tuple[str, int | None, str | None, str | None]] = []
    current_chunk = ""
    current_chunk_page: int | None = None
    current_page: int | None = None
    current_section_title: str | None = None
    current_section_id: str | None = None

    def flush_current_chunk() -> None:
        nonlocal current_chunk, current_chunk_page
        cleaned = _normalize_whitespace(current_chunk)
        if cleaned:
            chunk_entries.append((cleaned, current_chunk_page, current_section_id, current_section_title))
        current_chunk = ""
        current_chunk_page = None

    for paragraph in paragraphs:
        next_section_title = _extract_section_title(paragraph)
        if next_section_title:
            next_section_id = _normalize_section_id(next_section_title)
            if current_chunk and current_section_id and next_section_id != current_section_id:
                flush_current_chunk()
            current_section_title = next_section_title
            current_section_id = next_section_id
        paragraph_page = _paragraph_page_number(paragraph, current_page)
        if paragraph_page is not None:
            current_page = paragraph_page
        pieces = list(_slice_long_paragraph(paragraph, chunk_size, overlap))
        for piece in pieces:
            piece_page = _paragraph_page_number(piece, current_page)
            if piece_page is not None:
                current_page = piece_page
            if current_chunk and piece_page is not None and current_chunk_page is not None and piece_page != current_chunk_page:
                flush_current_chunk()

            if not current_chunk:
                current_chunk = piece
                current_chunk_page = piece_page
                continue

            candidate = f"{current_chunk}\n\n{piece}" if current_chunk else piece
            if len(candidate) <= chunk_size:
                current_chunk = candidate
                continue

            previous_chunk = current_chunk
            previous_page = current_chunk_page
            flush_current_chunk()
            carry = ""
            if (
                overlap
                and previous_chunk
                and previous_page is not None
                and piece_page is not None
                and previous_page == piece_page
                and len(previous_chunk) > overlap
            ):
                carry = previous_chunk[-overlap:].strip()
            candidate_with_overlap = f"{carry}\n\n{piece}".strip() if carry else piece
            current_chunk = candidate_with_overlap if len(candidate_with_overlap) <= chunk_size else piece
            current_chunk_page = piece_page

    flush_current_chunk()

    items: list[Chunk] = []
    seen_texts: set[str] = set()
    for index, (chunk_text, page_number, section_id, section_title) in enumerate(chunk_entries):
        if chunk_text in seen_texts:
            continue
        seen_texts.add(chunk_text)
        chunk_metadata = dict(base_metadata)
        if page_number is not None:
            chunk_metadata["page_number"] = int(page_number)
        if section_id:
            chunk_metadata["section_id"] = section_id
        if section_title:
            chunk_metadata["section_title"] = section_title
        chunk_metadata["chunk_id_in_document"] = len(items)
        chunk_id = _build_chunk_id(source_name, source_type, normalized_category, chunk_text)
        items.append(
            Chunk(
                id=chunk_id,
                text=chunk_text,
                source_name=source_name,
                source_type=source_type,
                category=normalized_category,
                chunk_index=len(items),
                metadata=chunk_metadata,
            )
        )
    return items
