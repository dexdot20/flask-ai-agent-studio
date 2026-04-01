from __future__ import annotations

import csv
import io
import os
import re

import pdfplumber
from docx import Document
from docx.table import Table as _DocxTable
from docx.text.paragraph import Paragraph as _DocxParagraph

from config import (
    DOCUMENT_ALLOWED_MIME_TYPES,
    DOCUMENT_MAX_BYTES,
    DOCUMENT_MAX_TEXT_CHARS,
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


def _looks_like_real_table(data: list[list]) -> bool:
    """Guard text-strategy detections against false positives.

    pdfplumber's text strategy can misidentify word-wrapped paragraph text as a
    multi-column table when character X-positions happen to align.  Two checks:

    1. Header row must have ≥50% non-trivial cells (≥2 chars) — rejects headings
       like "SONUÇ: | | |" where only the first cell is populated.
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


def _extract_text_from_pdf_ocr(page) -> str:
    try:
        from ocr_service import extract_image_text
    except ImportError:
        return ""

    try:
        page_image = page.to_image(
            resolution=_PDF_OCR_RENDER_DPI,
            antialias=True,
            force_mediabox=True,
        )
        image_buffer = io.BytesIO()
        page_image.original.save(image_buffer, format="PNG")
        return extract_image_text(image_buffer.getvalue(), "image/png").strip()
    except Exception:
        return ""


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
        for page_num, page in enumerate(pdf.pages, start=1):
            page_parts: list[str] = []
            table_bboxes: list = []
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
            # When no structured table was found, attempt character-position
            # based extraction before falling back to plain text.
            if not table_bboxes:
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
            should_try_ocr = not table_bboxes and bool(getattr(page, "images", None))
            # When the page has no detected tables, use layout=True to preserve
            # spatial column ordering instead of the default linear read order.
            text_kwargs: dict = {} if table_bboxes else {"layout": True}
            text = (remaining.extract_text(**text_kwargs) or "").strip()
            if text:
                if not table_bboxes:
                    # Collapse runs of 3+ spaces produced by layout=True into 2
                    # spaces so the output stays readable without being noisy.
                    text = re.sub(r"[ \t]{3,}", "  ", text)
                page_parts.insert(0, text)
                if should_try_ocr and len(text) < _PDF_OCR_MIN_TEXT_CHARS:
                    # Very short text on an image-heavy page usually means the
                    # visible content is a scan or rasterized table.
                    ocr_text = _extract_text_from_pdf_ocr(page)
                    if ocr_text:
                        page_parts = [ocr_text]
            elif should_try_ocr:
                # Image-only or nearly empty pages are often scans; render the
                # page and run OCR as a fallback instead of dropping them.
                ocr_text = _extract_text_from_pdf_ocr(page)
                if ocr_text:
                    page_parts.append(ocr_text)
            if not page_parts:
                continue
            page_content = "\n\n".join(page_parts)
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
    rendered_text = build_canvas_markdown(name, text) if infer_canvas_format(name) == "markdown" else text
    truncated = len(rendered_text) > DOCUMENT_MAX_TEXT_CHARS
    clipped = rendered_text[:DOCUMENT_MAX_TEXT_CHARS] if truncated else rendered_text
    header = f"[Uploaded document: {name}]"
    if truncated:
        header += " (truncated to first 50,000 characters)"
    return f"{header}\n{clipped}", truncated
