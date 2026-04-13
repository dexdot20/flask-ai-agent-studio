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


# Table-detection settings for borderless PDFs (no explicit border lines).
_PDF_TEXT_TABLE_SETTINGS: dict = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 5,
    "join_tolerance": 3,
    "min_words_vertical": 3,
    "min_words_horizontal": 1,
    "intersection_tolerance": 5,
}

_PDF_OCR_MIN_TEXT_CHARS = 20
_PDF_OCR_RENDER_DPI = 200
_PDF_OCR_MIN_IMAGE_COVERAGE = 0.35
PDF_VISION_PAGE_LIMIT = 3
_PDF_VISION_RENDER_DPI = 144
_PDF_VISION_MAX_DIMENSION = 1600
_PDF_HEADER_FOOTER_EDGE_RATIO = 0.08
_PDF_REPEATED_EDGE_MIN_PAGES = 3
_PDF_MULTI_COLUMN_MIN_WORDS = 40
_PDF_MULTI_COLUMN_MIN_SHARE = 0.15
_PDF_MULTI_COLUMN_MIN_GAP = 24


def _looks_like_real_table(data: list[list]) -> bool:
    """Guard text-strategy detections against false positives.

    pdfplumber's text strategy can misidentify word-wrapped paragraph text as a
    multi-column table when character X-positions happen to align.  Two checks:

    1. Header row must have ≥50% non-trivial cells (≥2 chars) — rejects headings
         like "RESULT: | | |" where only the first cell is populated.
    2. Fill-rate variance (CV) of all rows must be low — real tables have
       consistent cell density across rows; flowing paragraph text produces
       alternating fully-packed rows and near-empty rows (high CV).
    """
    if not data or len(data) < 2:
        return False
    header = [str(cell or "").strip() for cell in data[0]]
    n_cols = len(header)
    # Header must have ≥50% non-empty cells with at least 2 characters each.
    filled = sum(1 for c in header if len(c) >= 2)
    if filled < max(2, n_cols * 0.5):
        return False
    if len(data) == 2:
        data_row = [str(cell or "").strip() for cell in data[1]]
        data_fill = sum(1 for c in data_row if c) / max(1, len(data_row))
        return data_fill >= 0.50
    # Compute fill rate per row.
    fills = [
        sum(1 for c in row if (c or "").strip()) / max(1, len(row))
        for row in data
        if row
    ]
    if not fills:
        return False
    avg_fill = sum(fills) / len(fills)
    if avg_fill < 0.40:
        return False
    # High fill-rate variance signals word-wrapped paragraph text split into
    # fake columns (body text rows at 80-100% followed by blank/short rows at
    # 0-10% → CV typically > 0.5).  Real tables have consistent row density.
    if len(fills) > 1:
        stdev = (sum((f - avg_fill) ** 2 for f in fills) / len(fills)) ** 0.5
        cv = stdev / avg_fill if avg_fill > 0 else 1.0
        if cv > 0.50:
            return False
    return True


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


def _score_pdf_text_quality(text: str) -> float:
    normalized = str(text or "").strip()
    if not normalized:
        return float("-inf")

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if not lines:
        return float("-inf")

    avg_line_length = sum(len(line) for line in lines) / len(lines)
    very_short_lines = sum(1 for line in lines if len(line) <= 3)
    single_letter_lines = sum(1 for line in lines if len(line) == 1 and line.isalpha())
    fragmented_word_lines = sum(1 for line in lines if re.fullmatch(r"[a-zçğıöşü]{2,6}", line, flags=re.IGNORECASE))
    balanced_lines = sum(1 for line in lines if 12 <= len(line) <= 140)
    punctuation_lines = sum(1 for line in lines if re.search(r"[.!?:;)]", line))
    question_lines = sum(1 for line in lines if re.match(r"^\d{1,3}[.)-]?\s+", line))
    option_lines = sum(1 for line in lines if re.match(r"^[A-E][.)]\s+\S", line))
    noise_lines = sum(1 for index, line in enumerate(lines) if _is_probably_pdf_noise_line(line, index, len(lines)))

    return (
        len(normalized)
        + (avg_line_length * 6)
        + (balanced_lines * 24)
        + (punctuation_lines * 10)
        + (question_lines * 16)
        + (option_lines * 10)
        - (very_short_lines * 18)
        - (single_letter_lines * 90)
        - (fragmented_word_lines * 20)
        - (noise_lines * 60)
    )


def _choose_best_pdf_text_candidate(*candidates: str) -> str:
    best_text = ""
    best_score = float("-inf")
    for candidate in candidates:
        text = _clean_pdf_page_text(candidate)
        if not text:
            continue
        score = _score_pdf_text_quality(text)
        if score > best_score:
            best_text = text
            best_score = score
    return best_text


def _normalize_pdf_page_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\u00ad", "")
    normalized = normalized.replace("\xa0", " ")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip()


def _is_probably_pdf_noise_line(line: str, index: int, total_lines: int) -> bool:
    stripped = re.sub(r"\s+", " ", str(line or "")).strip()
    if not stripped:
        return False

    near_edge = index < 2 or index >= max(0, total_lines - 2)
    if re.fullmatch(r"[-_=|~•·*.◦○●□■▪▫]{3,}", stripped):
        return True
    if re.fullmatch(r"(?i)(?:page|sayfa)\s*\d{1,3}(?:\s*/\s*\d{1,3})?", stripped):
        return True
    if re.fullmatch(r"[-–—]\s*\d{1,3}\s*[-–—]", stripped):
        return True
    if near_edge and re.fullmatch(r"\d{1,3}", stripped):
        return True
    if near_edge and re.fullmatch(r"[ivxlcdm]{1,6}", stripped, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"(?:[A-E]\s+){3,}[A-E]", stripped):
        return True
    if len(stripped) <= 18:
        symbol_count = sum(1 for char in stripped if not char.isalnum() and not char.isspace())
        if symbol_count >= max(4, int(len(stripped) * 0.6)):
            return True
    return False


def _should_concat_pdf_word_fragments(previous_line: str, next_line: str) -> bool:
    prev = previous_line.strip()
    nxt = next_line.strip()
    if not prev or not nxt:
        return False
    if prev.endswith("-") and re.match(r"^[A-Za-zÇĞİÖŞÜçğıöşü]", nxt):
        return True
    return bool(
        re.fullmatch(r"[A-Za-zÇĞİÖŞÜçğıöşü]{1,4}", prev)
        and re.match(r"^[a-zçğıöşü]", nxt)
    )


def _should_merge_pdf_lines(previous_line: str, next_line: str) -> bool:
    prev = previous_line.strip()
    nxt = next_line.strip()
    if not prev or not nxt:
        return False
    if prev.startswith("|") or nxt.startswith("|"):
        return False
    if re.match(r"^(?:[-*•]|\d{1,3}[.)]|[A-E][.)])\s+", nxt):
        return False
    if prev.endswith((".", "!", "?", ":", ";", ")", "]")):
        return False
    if _should_concat_pdf_word_fragments(prev, nxt):
        return True
    return bool(re.match(r"^[a-zçğıöşü(]", nxt) and len(prev) >= 2)


def _merge_pdf_lines(previous_line: str, next_line: str) -> str:
    prev = previous_line.rstrip()
    nxt = next_line.lstrip()
    if prev.endswith("-"):
        return f"{prev[:-1]}{nxt}"
    if _should_concat_pdf_word_fragments(prev, nxt):
        return f"{prev}{nxt}"
    return f"{prev} {nxt}"


def _clean_pdf_page_text(text: str) -> str:
    normalized = _normalize_pdf_page_text(text)
    if not normalized:
        return ""

    raw_lines = [re.sub(r"\s+", " ", line).strip() for line in normalized.splitlines()]
    filtered_lines = [
        line
        for index, line in enumerate(raw_lines)
        if line and not _is_probably_pdf_noise_line(line, index, len(raw_lines))
    ]
    if not filtered_lines:
        return ""

    merged_lines: list[str] = []
    for line in filtered_lines:
        if merged_lines and _should_merge_pdf_lines(merged_lines[-1], line):
            merged_lines[-1] = _merge_pdf_lines(merged_lines[-1], line)
        else:
            merged_lines.append(line)

    cleaned = "\n".join(merged_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _estimate_pdf_page_image_coverage(page) -> float:
    page_width = float(getattr(page, "width", 0) or 0)
    page_height = float(getattr(page, "height", 0) or 0)
    if page_width <= 0 or page_height <= 0:
        return 0.0
    images = list(getattr(page, "images", None) or [])
    if not images:
        return 0.0

    total_area = page_width * page_height
    covered_area = 0.0
    for image in images:
        try:
            x0 = float(image.get("x0", 0) or 0)
            x1 = float(image.get("x1", 0) or 0)
            top = float(image.get("top", 0) or 0)
            bottom = float(image.get("bottom", 0) or 0)
        except Exception:
            continue
        covered_area += max(0.0, x1 - x0) * max(0.0, bottom - top)
    if covered_area <= 0:
        return 0.0
    return min(1.0, covered_area / total_area)


def _normalize_pdf_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _collect_page_edge_lines(page) -> tuple[set[str], set[str]]:
    page_height = float(getattr(page, "height", 0) or 0)
    page_width = float(getattr(page, "width", 0) or 0)
    if page_height <= 0 or page_width <= 0:
        return set(), set()

    edge_height = max(24.0, page_height * _PDF_HEADER_FOOTER_EDGE_RATIO)
    regions = [
        (0, (0, 0, page_width, edge_height)),
        (1, (0, max(0.0, page_height - edge_height), page_width, page_height)),
    ]
    edge_lines: list[set[str]] = [set(), set()]
    for index, bbox in regions:
        try:
            snippet = page.crop(bbox).extract_text(layout=True) or ""
        except Exception:
            snippet = ""
        for line in snippet.splitlines():
            normalized = _normalize_pdf_line(line)
            if len(normalized) >= 4:
                edge_lines[index].add(normalized)
    return edge_lines[0], edge_lines[1]


def _detect_repeating_page_edge_lines(pdf) -> set[str]:
    counts: dict[str, int] = {}
    for page in pdf.pages:
        top_lines, bottom_lines = _collect_page_edge_lines(page)
        for line in top_lines | bottom_lines:
            counts[line] = counts.get(line, 0) + 1
    return {
        line
        for line, count in counts.items()
        if count >= _PDF_REPEATED_EDGE_MIN_PAGES
    }


def _filter_repeating_page_edge_lines(text: str, repeated_lines: set[str]) -> str:
    if not text or not repeated_lines:
        return text
    filtered_lines = [
        line
        for line in text.splitlines()
        if not _normalize_pdf_line(line) or _normalize_pdf_line(line) not in repeated_lines
    ]
    filtered = "\n".join(filtered_lines)
    filtered = re.sub(r"\n{3,}", "\n\n", filtered)
    return filtered.strip()


# ---------------------------------------------------------------------------
# Character-position based borderless-table extractor
# ---------------------------------------------------------------------------
# pdfplumber's text-strategy table finder sometimes mis-splits or misses
# borderless tables.  This extractor works from raw word positions: it finds
# vertical gutters (x-ranges with very few words), uses them as column
# boundaries, groups words into physical lines, assigns words to columns, and
# merges wrapped rows that belong to the same logical record.
# ---------------------------------------------------------------------------

_BORDERLESS_MIN_COLS = 3
_BORDERLESS_MIN_WORDS = 20
_BORDERLESS_MIN_GUTTER_PX = 8
_BORDERLESS_COV_PCT = 0.05
_BORDERLESS_Y_SNAP = 3


def _detect_borderless_col_edges(words: list[dict], page_width: float) -> list[int]:
    """Detect column left-edges by finding vertical gutters in word coverage."""
    bins = int(page_width) + 1
    coverage = [0] * bins
    for w in words:
        x0 = max(0, int(w["x0"]))
        x1 = min(bins - 1, int(w["x1"]))
        for x in range(x0, x1 + 1):
            coverage[x] += 1
    threshold = max(2, int(len(words) * _BORDERLESS_COV_PCT))
    gutters: list[tuple[int, int]] = []
    in_g, gs = False, 0
    for x in range(bins):
        if coverage[x] <= threshold:
            if not in_g:
                gs = x
                in_g = True
        else:
            if in_g:
                if x - gs >= _BORDERLESS_MIN_GUTTER_PX:
                    gutters.append((gs, x))
                in_g = False
    first_content = min((int(w["x0"]) for w in words), default=0)
    edges = [ge for _, ge in gutters if ge > first_content]
    if not edges or edges[0] != first_content:
        edges.insert(0, first_content)
    return edges


def _extract_column_ordered_text(page) -> str:
    try:
        words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    except Exception:
        return ""
    if len(words) < _PDF_MULTI_COLUMN_MIN_WORDS:
        return ""

    col_edges = _detect_borderless_col_edges(words, page.width)
    if len(col_edges) != 2:
        return ""

    def _assign(x0: float) -> int:
        best = 0
        for index, edge in enumerate(col_edges):
            if edge <= x0 + 5:
                best = index
        return best

    columns: list[list[dict]] = [[] for _ in range(len(col_edges))]
    for word in words:
        columns[_assign(word["x0"])] .append(word)

    min_words_per_col = max(12, int(len(words) * _PDF_MULTI_COLUMN_MIN_SHARE))
    significant_columns: list[tuple[float, float, list[dict]]] = []
    for column_words in columns:
        if len(column_words) < min_words_per_col:
            continue
        x0 = min(float(word["x0"]) for word in column_words)
        x1 = max(float(word["x1"]) for word in column_words)
        significant_columns.append((x0, x1, column_words))
    if len(significant_columns) != 2:
        return ""

    significant_columns.sort(key=lambda item: item[0])
    gap = significant_columns[1][0] - significant_columns[0][1]
    if gap < max(_PDF_MULTI_COLUMN_MIN_GAP, float(page.width) * 0.03):
        return ""

    from collections import defaultdict

    blocks: list[str] = []
    for _, __, column_words in significant_columns:
        lines_map: dict[int, list[dict]] = defaultdict(list)
        for word in column_words:
            y_key = round(float(word["top"]) / _BORDERLESS_Y_SNAP) * _BORDERLESS_Y_SNAP
            lines_map[y_key].append(word)
        lines: list[str] = []
        for y_key in sorted(lines_map):
            ordered_words = sorted(lines_map[y_key], key=lambda item: (item["x0"], item["x1"]))
            line = " ".join(str(word["text"] or "").strip() for word in ordered_words if str(word["text"] or "").strip()).strip()
            if line:
                lines.append(line)
        block = "\n".join(lines).strip()
        if block:
            blocks.append(block)
    if len(blocks) != 2:
        return ""
    return re.sub(r"[ \t]{3,}", "  ", "\n\n".join(blocks)).strip()


def _try_extract_borderless_table(page) -> str:
    """Extract a borderless table from word positions; return markdown or ''."""
    try:
        words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    except Exception:
        return ""
    if len(words) < _BORDERLESS_MIN_WORDS:
        return ""
    col_edges = _detect_borderless_col_edges(words, page.width)
    n_cols = len(col_edges)
    if n_cols < _BORDERLESS_MIN_COLS:
        return ""

    # Assign words to a (line, column) grid.
    from collections import defaultdict

    lines_map: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        y_key = round(w["top"] / _BORDERLESS_Y_SNAP) * _BORDERLESS_Y_SNAP
        lines_map[y_key].append(w)

    def _assign(x0: float) -> int:
        best = 0
        for i, edge in enumerate(col_edges):
            if edge <= x0 + 5:
                best = i
        return best

    grid: list[list[str]] = []
    for y in sorted(lines_map):
        row = [""] * n_cols
        for w in sorted(lines_map[y], key=lambda w: w["x0"]):
            ci = _assign(w["x0"])
            row[ci] = (row[ci] + " " + w["text"]).strip() if row[ci] else w["text"]
        grid.append(row)
    if not grid:
        return ""

    # Merge wrapped physical rows into logical rows.
    def _is_new_row(row: list[str]) -> bool:
        c0 = row[0].strip()
        if not c0 or c0.startswith("("):
            return False
        if ":" in c0:
            return True
        return sum(1 for i in range(1, n_cols) if row[i].strip()) >= 1

    def _is_last_col_only(row: list[str]) -> bool:
        """True when only the last 1-2 columns carry content (date fragment)."""
        return (
            not row[0].strip()
            and any(row[j].strip() for j in range(n_cols - 2, n_cols))
            and not any(row[j].strip() for j in range(1, max(1, n_cols - 2)))
        )

    def _merge_row(target: list[str], source: list[str]) -> None:
        for i in range(n_cols):
            cell = source[i].strip()
            if cell:
                target[i] = (target[i] + " " + cell).strip() if target[i] else cell

    merged: list[list[str]] = []
    pending_leading: list[str] | None = None
    current: list[str] | None = list(grid[0])

    for idx in range(1, len(grid)):
        row = grid[idx]
        next_row = grid[idx + 1] if idx + 1 < len(grid) else None

        if _is_last_col_only(row):
            # A date fragment that sits at a Y position *before* the model row
            # (leading) must be attached to the *next* new row, not the current
            # one.  Detect this by: next physical row is a new logical row AND
            # has no date in its last column yet.
            is_leading = (
                next_row is not None
                and _is_new_row(next_row)
                and not next_row[n_cols - 1].strip()
            )
            if is_leading:
                if current is not None:
                    merged.append(current)
                pending_leading = list(row)
                current = None
            else:
                # Trailing fragment — append to current row.
                if current is not None:
                    _merge_row(current, row)
        elif _is_new_row(row):
            if current is not None:
                merged.append(current)
            current = list(row)
            if pending_leading is not None:
                _merge_row(current, pending_leading)
                pending_leading = None
        else:
            if current is None:
                current = list(row)
                if pending_leading is not None:
                    _merge_row(current, pending_leading)
                    pending_leading = None
            else:
                _merge_row(current, row)

    if current is not None:
        merged.append(current)

    # Try to merge the first two rows into a combined header when they are
    # complementary non-numeric rows (like a two-line column header).
    if len(merged) >= 2:
        r0, r1 = merged[0], merged[1]
        all_text = all(
            not s.strip().replace(",", "").replace(".", "").lstrip("$").isdigit()
            for s in r0 + r1
            if s.strip()
        )
        has_complement = any(
            (not a.strip() and b.strip()) or (a.strip() and not b.strip())
            for a, b in zip(r0, r1)
        )
        if all_text and has_complement:
            header = [
                (f"{a.strip()} {b.strip()}").strip() for a, b in zip(r0, r1)
            ]
            merged = [header] + merged[2:]

    if not _looks_like_real_table(merged):
        return ""
    # Reject when any column's average cell length exceeds a threshold — real
    # table cells are short (numbers, names, dates); paragraph text forced into
    # a column produces cells with hundreds of characters.
    _MAX_AVG_CELL_LEN = 80
    for ci in range(n_cols):
        lengths = [len(str(row[ci] or "").strip()) for row in merged[1:] if row[ci]]
        if lengths and sum(lengths) / len(lengths) > _MAX_AVG_CELL_LEN:
            return ""
    return _format_table_as_markdown(merged)


def _extract_text_from_pdf(doc_bytes: bytes) -> str:
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(doc_bytes)) as pdf:
        multi_page = len(pdf.pages) > 1
        repeated_edge_lines = _detect_repeating_page_edge_lines(pdf)
        for page_num, page in enumerate(pdf.pages, start=1):
            page_parts: list[str] = []
            table_bboxes: list = []
            column_ordered_text = ""
            # Try line-based detection first (explicit borders), then text-based
            # (implicit/borderless tables like whitespace-separated columns).
            for settings in (None, _PDF_TEXT_TABLE_SETTINGS):
                if table_bboxes:
                    break
                try:
                    kwargs = {} if settings is None else {"table_settings": settings}
                    for tbl in (page.find_tables(**kwargs) or []):
                        try:
                            data = tbl.extract()
                            # Reject text-strategy false positives (e.g. flowing
                            # paragraph text misidentified as a table).
                            if settings is not None and not _looks_like_real_table(data):
                                continue
                            md = _format_table_as_markdown(data)
                        except Exception:
                            continue
                        if md:
                            page_parts.append(md)
                            table_bboxes.append(tbl.bbox)
                except Exception:
                    pass
            remaining = page
            for bbox in table_bboxes:
                try:
                    remaining = remaining.outside_bbox(bbox)
                except Exception:
                    pass
            if not table_bboxes:
                # Prefer column reconstruction for prose-like two-column pages
                # before trying the borderless-table path.
                column_ordered_text = _extract_column_ordered_text(remaining)
            # When no structured table was found, attempt character-position
            # based extraction before falling back to plain text.
            if not table_bboxes and not column_ordered_text:
                borderless_md = _try_extract_borderless_table(page)
                if borderless_md:
                    page_parts.append(borderless_md)
                    if not page_parts:
                        continue
                    page_content = "\n\n".join(page_parts)
                    if multi_page:
                        parts.append(f"## Page {page_num}\n\n{page_content}")
                    else:
                        parts.append(page_content)
                    continue
            has_page_images = bool(getattr(page, "images", None))
            image_coverage = _estimate_pdf_page_image_coverage(page)
            should_compare_ocr = has_page_images and image_coverage >= _PDF_OCR_MIN_IMAGE_COVERAGE
            layout_text = ""
            linear_text = ""
            if table_bboxes:
                linear_text = (remaining.extract_text() or "").strip()
            else:
                layout_text = (remaining.extract_text(layout=True) or "").strip()
                linear_text = (remaining.extract_text() or "").strip()
            text = _choose_best_pdf_text_candidate(column_ordered_text, layout_text, linear_text)
            ocr_text = ""
            ocr_status = "not_attempted"
            if should_compare_ocr:
                ocr_text, ocr_status = _extract_text_from_pdf_ocr(page)
                text = _choose_best_pdf_text_candidate(text, ocr_text)
            if text:
                if text == _clean_pdf_page_text(layout_text) and not table_bboxes:
                    # Collapse runs of 3+ spaces produced by layout=True into 2
                    # spaces so the output stays readable without being noisy.
                    text = re.sub(r"[ \t]{3,}", "  ", text)
                text = _filter_repeating_page_edge_lines(text, repeated_edge_lines)
                page_parts.insert(0, text)
                if has_page_images and len(text) < _PDF_OCR_MIN_TEXT_CHARS:
                    # Very short text on an image-heavy page usually means the
                    # visible content is a scan or rasterized table.
                    if not ocr_text:
                        ocr_text, ocr_status = _extract_text_from_pdf_ocr(page)
                    ocr_text = _clean_pdf_page_text(ocr_text)
                    if ocr_text:
                        page_parts = [_filter_repeating_page_edge_lines(ocr_text, repeated_edge_lines)]
                    else:
                        ocr_notice = _build_pdf_ocr_unavailable_notice(ocr_status)
                        if ocr_notice:
                            page_parts.append(ocr_notice)
            elif has_page_images:
                # Image-only or nearly empty pages are often scans; render the
                # page and run OCR as a fallback instead of dropping them.
                if not ocr_text:
                    ocr_text, ocr_status = _extract_text_from_pdf_ocr(page)
                ocr_text = _clean_pdf_page_text(ocr_text)
                if ocr_text:
                    page_parts.append(_filter_repeating_page_edge_lines(ocr_text, repeated_edge_lines))
                else:
                    ocr_notice = _build_pdf_ocr_unavailable_notice(ocr_status)
                    if ocr_notice:
                        page_parts.append(ocr_notice)
            if not page_parts:
                continue
            page_content = "\n\n".join(page_parts)
            if multi_page:
                parts.append(f"## Page {page_num}\n\n{page_content}")
            else:
                parts.append(page_content)
    return ("\n\n---\n\n" if len(parts) > 1 else "\n\n").join(parts)


def _render_pdf_page_image_bytes(page, *, dpi: int = _PDF_VISION_RENDER_DPI, max_dimension: int = _PDF_VISION_MAX_DIMENSION) -> tuple[bytes, str]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow is an indirect runtime dependency here
        raise ValueError("PDF page rendering requires Pillow.") from exc

    try:
        page_image = page.to_image(
            resolution=dpi,
            antialias=True,
            force_mediabox=True,
        )
        pil_image = page_image.original.convert("RGB")
    except Exception as exc:
        raise ValueError(f"Could not render PDF page as an image: {exc}") from exc

    if max_dimension > 0:
        pil_image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    image_buffer = io.BytesIO()
    pil_image.save(image_buffer, format="JPEG", quality=82, optimize=True)
    return image_buffer.getvalue(), "image/jpeg"


def render_pdf_pages_for_vision(doc_bytes: bytes, *, max_pages: int = PDF_VISION_PAGE_LIMIT) -> list[dict]:
    page_limit = max(1, int(max_pages or 1))
    rendered_pages: list[dict] = []
    failed_page_numbers: list[int] = []

    try:
        with pdfplumber.open(io.BytesIO(doc_bytes)) as pdf:
            total_pages = len(pdf.pages)
            if total_pages <= 0:
                raise ValueError("The uploaded PDF does not contain any pages.")

            is_truncated = total_pages > page_limit
            for page_number, page in enumerate(pdf.pages[:page_limit], start=1):
                try:
                    image_bytes, mime_type = _render_pdf_page_image_bytes(page)
                except ValueError as exc:
                    LOGGER.warning(
                        "Visual PDF rendering failed on page %s/%s: %s",
                        page_number,
                        total_pages,
                        exc,
                    )
                    failed_page_numbers.append(page_number)
                    continue
                rendered_pages.append(
                    {
                        "page_number": page_number,
                        "image_bytes": image_bytes,
                        "mime_type": mime_type,
                        "total_pages": total_pages,
                        "truncated": is_truncated,
                    }
                )
    except ValueError:
        raise
    except Exception as exc:
        LOGGER.warning("Could not open PDF for visual rendering: %s", exc)
        raise ValueError(f"Could not render the uploaded PDF as page images: {exc}") from exc

    if not rendered_pages:
        if failed_page_numbers:
            failed_label = ", ".join(str(page_number) for page_number in failed_page_numbers)
            raise ValueError(f"Could not render the uploaded PDF as page images. Failed pages: {failed_label}")
        raise ValueError("Could not render the uploaded PDF as page images.")

    if failed_page_numbers:
        for page in rendered_pages:
            page["failed_page_numbers"] = list(failed_page_numbers)
            page["partial_failure"] = True

    return rendered_pages


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


def build_visual_canvas_markdown(filename: str, page_count: int, *, total_pages: int | None = None) -> str:
    name = os.path.basename(filename or "document")
    normalized_page_count = max(1, int(page_count or 1))
    normalized_total_pages = max(normalized_page_count, int(total_pages or normalized_page_count))
    lines = [
        f"# {name}",
        "",
        "> This is a visual, read-only canvas preview backed by rendered page images.",
        "> Use page navigation to inspect each page in the Canvas panel.",
        "",
    ]
    if normalized_total_pages > normalized_page_count:
        lines.extend(
            [
                f"> This PDF contains {normalized_total_pages} pages. Only the first {normalized_page_count} are available in visual preview.",
                "",
            ]
        )
    for page_number in range(1, normalized_page_count + 1):
        lines.extend(
            [
                f"## Page {page_number}",
                "",
                f"[Visual page {page_number} preview is available in the Canvas panel.]",
                "",
            ]
        )
        if page_number < normalized_page_count:
            lines.extend(["---", ""])
    return "\n".join(lines).strip()


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
