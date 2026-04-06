from __future__ import annotations

from html import escape
from io import BytesIO
import re
from typing import Iterable
from uuid import uuid4

try:
    import markdown as markdown_lib
except ImportError:  # pragma: no cover - optional dependency fallback
    markdown_lib = None

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer

from markdown_rendering import append_markdown_pdf_story

# Unicode font registration for Turkish / non-Latin character support.
_FONT_PATHS = {
    "DejaVuSans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSansMono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
}

def _try_register_fonts() -> bool:
    import os
    if not all(os.path.exists(p) for p in _FONT_PATHS.values()):
        return False
    try:
        for name, path in _FONT_PATHS.items():
            pdfmetrics.registerFont(TTFont(name, path))
        return True
    except Exception:
        return False

_UNICODE_FONTS = _try_register_fonts()
_BODY_FONT = "DejaVuSans" if _UNICODE_FONTS else "Helvetica"
_BOLD_FONT = "DejaVuSans-Bold" if _UNICODE_FONTS else "Helvetica-Bold"
_MONO_FONT = "DejaVuSansMono" if _UNICODE_FONTS else "Courier"

CANVAS_MAX_DOCUMENTS = 12
CANVAS_MAX_TITLE_LENGTH = 160
CANVAS_MAX_CONTENT_LENGTH = 120_000
CANVAS_MAX_LANGUAGE_LENGTH = 48
CANVAS_MAX_PATH_LENGTH = 240
CANVAS_MAX_SUMMARY_LENGTH = 280
CANVAS_MAX_SCOPE_ID_LENGTH = 80
CANVAS_MAX_RELATION_COUNT = 24
CANVAS_MAX_RELATION_ITEM_LENGTH = 120
CANVAS_CONTEXT_MAX_CHARS = 20_000
CANVAS_CONTEXT_MAX_LINES = 800
CANVAS_ALLOWED_FORMATS = {"markdown", "code"}
CANVAS_ALLOWED_ROLES = {"source", "config", "dependency", "docs", "test", "script", "note"}
CANVAS_MODE_DOCUMENT = "document"
CANVAS_MODE_PROJECT = "project"
CANVAS_PAGE_HEADING_RE = re.compile(r"^\s{0,3}##\s+Page\s+(\d+)\s*$", re.IGNORECASE)
CANVAS_FILE_PRIORITY = {
    "source": 10,
    "config": 20,
    "dependency": 30,
    "test": 40,
    "script": 50,
    "docs": 60,
    "note": 70,
}


def _normalize_line_endings(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def _clip_text(text: str, max_length: int) -> str:
    normalized = _normalize_line_endings(text)
    if len(normalized) <= max_length:
        return normalized
    return normalized[:max_length]


def _line_count(text: str) -> int:
    if not text:
        return 0
    return len(text.split("\n"))


def _extract_canvas_page_sections(content: str) -> list[dict]:
    lines = list_canvas_lines(content)
    if not lines:
        return []

    sections: list[dict] = []
    for line_number, line in enumerate(lines, start=1):
        match = CANVAS_PAGE_HEADING_RE.match(line)
        if not match:
            continue
        sections.append(
            {
                "page_number": int(match.group(1)),
                "start_line": line_number,
            }
        )

    if not sections:
        return []

    for index, section in enumerate(sections):
        next_start_line = sections[index + 1]["start_line"] if index + 1 < len(sections) else len(lines) + 1
        end_line = next_start_line - 1
        while end_line >= section["start_line"] and not lines[end_line - 1].strip():
            end_line -= 1
        if end_line >= section["start_line"] and lines[end_line - 1].strip() == "---":
            end_line -= 1
        while end_line >= section["start_line"] and not lines[end_line - 1].strip():
            end_line -= 1
        section["end_line"] = max(section["start_line"], end_line)

    return sections


def _get_canvas_page_range(content: str, page_number: int) -> tuple[int, int] | None:
    for section in _extract_canvas_page_sections(content):
        if int(section.get("page_number") or 0) == int(page_number):
            return int(section["start_line"]), int(section["end_line"])
    return None


def _normalize_canvas_language(value) -> str | None:
    language = re.sub(r"[^a-z0-9_+.#-]", "", str(value or "").strip().lower())[:CANVAS_MAX_LANGUAGE_LENGTH]
    return language or None


_EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".mts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".ino": "cpp",  # Arduino
    ".cs": "csharp",
    ".java": "java",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin", ".kts": "kotlin",
    ".scala": "scala",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".ps1": "powershell", ".psm1": "powershell",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    ".sql": "sql",
    ".json": "json", ".jsonc": "json",
    ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini", ".cfg": "ini",
    ".xml": "xml",
    ".md": "markdown", ".mdx": "markdown",
    ".r": "r",
    ".lua": "lua",
    ".dart": "dart",
    ".ex": "elixir", ".exs": "elixir",
    ".hs": "haskell",
    ".tf": "terraform", ".tfvars": "terraform",
    ".proto": "protobuf",
    ".vue": "vue",
    ".svelte": "svelte",
}
_NAME_LANGUAGE_MAP: dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "vagrantfile": "ruby",
    "jenkinsfile": "groovy",
}

_SHEBANG_LANGUAGE_MAP: dict[str, str] = {
    "python": "python", "python3": "python", "python2": "python",
    "node": "javascript", "nodejs": "javascript",
    "ruby": "ruby",
    "perl": "perl", "perl5": "perl",
    "bash": "bash", "sh": "bash", "zsh": "bash", "dash": "bash",
    "php": "php",
    "lua": "lua",
    "rscript": "r",
    "groovy": "groovy",
    "tclsh": "tcl", "expect": "tcl",
    "awk": "awk", "gawk": "awk",
}


def _infer_canvas_language_from_content(content: str) -> str | None:
    """Infer language from a shebang line (#!) at the top of the content."""
    first_line = content.split("\n", 1)[0].strip() if content else ""
    if not first_line.startswith("#!"):
        return None
    # e.g. "#!/usr/bin/env python3" or "#!/usr/bin/python3"
    parts = first_line[2:].strip().split()
    if not parts:
        return None
    interpreter = parts[-1].rsplit("/", 1)[-1].lower()
    return _SHEBANG_LANGUAGE_MAP.get(interpreter)


def _infer_canvas_language(path_or_name: str | None) -> str | None:
    if not path_or_name:
        return None
    name = str(path_or_name).rsplit("/", 1)[-1].lower().strip()
    if not name:
        return None
    stem_lang = _NAME_LANGUAGE_MAP.get(name)
    if stem_lang:
        return stem_lang
    dot_idx = name.rfind(".")
    if dot_idx < 0:
        return None
    return _EXTENSION_LANGUAGE_MAP.get(name[dot_idx:])


def _normalize_canvas_short_text(value, max_length: int) -> str | None:
    text = re.sub(r"\s+", " ", _normalize_line_endings(str(value or "")).strip())[:max_length]
    return text or None


def _normalize_canvas_identifier(value) -> str | None:
    identifier = re.sub(r"[^a-z0-9_.:-]", "", str(value or "").strip().lower())[:CANVAS_MAX_SCOPE_ID_LENGTH]
    return identifier or None


def _normalize_canvas_path(value) -> str | None:
    raw_path = _normalize_line_endings(str(value or "")).strip().replace("\\", "/")
    if not raw_path:
        return None
    raw_path = re.sub(r"/{2,}", "/", raw_path)
    while raw_path.startswith("./"):
        raw_path = raw_path[2:]
    raw_path = raw_path.lstrip("/")

    normalized_parts = []
    for part in raw_path.split("/"):
        cleaned_part = part.strip()
        if not cleaned_part or cleaned_part == ".":
            continue
        if cleaned_part == "..":
            if normalized_parts:
                normalized_parts.pop()
            continue
        normalized_parts.append(cleaned_part)

    normalized_path = "/".join(normalized_parts)[:CANVAS_MAX_PATH_LENGTH]
    return normalized_path or None


def _normalize_canvas_role(value) -> str | None:
    role = re.sub(r"[^a-z]", "", str(value or "").strip().lower())
    if role in CANVAS_ALLOWED_ROLES:
        return role
    return None


def _normalize_canvas_string_list(values) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []

    normalized = []
    seen = set()
    for raw_value in values:
        item = _normalize_canvas_short_text(raw_value, CANVAS_MAX_RELATION_ITEM_LENGTH)
        if not item:
            continue
        dedupe_key = item.lower()
        if dedupe_key in seen:
            continue
        normalized.append(item)
        seen.add(dedupe_key)
        if len(normalized) >= CANVAS_MAX_RELATION_COUNT:
            break
    return normalized


def _infer_canvas_role(path: str | None, title: str, format_name: str) -> str | None:
    candidate = (path or title or "").strip().lower()
    if not candidate:
        return None
    filename = candidate.rsplit("/", 1)[-1]
    if filename.startswith("test_") or "/tests/" in f"/{candidate}" or candidate.endswith("_test.py"):
        return "test"
    if filename in {"readme", "readme.md", "readme.txt"} or candidate.startswith("docs/"):
        return "docs"
    if filename in {"requirements.txt", "requirements-dev.txt", "package.json", "pyproject.toml", ".env", ".env.example"}:
        return "dependency" if "requirements" in filename or filename == "package.json" else "config"
    if filename.endswith((".ini", ".cfg", ".toml", ".yaml", ".yml", ".json", ".env")):
        return "config"
    if filename.endswith((".sh", ".bash")):
        return "script"
    if format_name == "code":
        return "source"
    return "note"


def _build_canvas_summary(title: str, path: str | None, role: str | None, content: str) -> str:
    label = path or title or "Canvas"
    first_meaningful_line = ""
    for line in _normalize_line_endings(content).split("\n"):
        stripped = re.sub(r"\s+", " ", line.strip())
        if not stripped:
            continue
        first_meaningful_line = stripped.lstrip("#*- ").strip()
        if first_meaningful_line:
            break

    role_label = (role or "document").replace("_", " ")
    if first_meaningful_line:
        return f"{role_label.capitalize()} {label}: {first_meaningful_line}"[:CANVAS_MAX_SUMMARY_LENGTH]
    return f"{role_label.capitalize()} {label}"[:CANVAS_MAX_SUMMARY_LENGTH]


def scale_canvas_char_limit(max_lines: int | None, *, default_lines: int, default_chars: int) -> int:
    try:
        normalized_max_lines = int(max_lines or 0)
    except (TypeError, ValueError):
        return default_chars
    if normalized_max_lines <= 0 or default_lines <= 0 or default_chars <= 0:
        return default_chars
    return max(1, int(round(default_chars * (normalized_max_lines / default_lines))))


def _number_canvas_lines(
    content: str,
    *,
    max_lines: int = CANVAS_CONTEXT_MAX_LINES,
    max_chars: int | None = None,
) -> tuple[list[str], bool]:
    if max_chars is None:
        max_chars = scale_canvas_char_limit(
            max_lines,
            default_lines=CANVAS_CONTEXT_MAX_LINES,
            default_chars=CANVAS_CONTEXT_MAX_CHARS,
        )
    normalized = _normalize_line_endings(content)
    all_lines = normalized.split("\n") if normalized else []
    visible_lines = []
    visible_char_count = 0

    for index, line in enumerate(all_lines, start=1):
        numbered_line = f"{index}: {line}"
        extra_chars = len(numbered_line) + (1 if visible_lines else 0)
        if visible_lines and (len(visible_lines) >= max_lines or visible_char_count + extra_chars > max_chars):
            return visible_lines, True
        if not visible_lines and extra_chars > max_chars:
            visible_lines.append(numbered_line[:max_chars])
            return visible_lines, True
        visible_lines.append(numbered_line)
        visible_char_count += extra_chars

    return visible_lines, False


def build_canvas_relationship_map(documents: list[dict] | None) -> dict | None:
    normalized_documents = extract_canvas_documents({"canvas_documents": documents or []})
    if not normalized_documents:
        return None

    files = []
    aggregate_imports = []
    aggregate_exports = []
    aggregate_symbols = []
    aggregate_dependencies = []
    seen_buckets = {
        "imports": set(),
        "exports": set(),
        "symbols": set(),
        "dependencies": set(),
    }

    for document in sorted(normalized_documents, key=_document_sort_key):
        entry = {
            "file": document.get("path") or document.get("title") or document.get("id"),
            "role": document.get("role") or "note",
        }
        for key in ("imports", "exports", "symbols", "dependencies"):
            values = document.get(key) if isinstance(document.get(key), list) else []
            if values:
                entry[key] = values[:8]
            for value in values:
                normalized_value = str(value).strip()
                dedupe_key = normalized_value.lower()
                if not normalized_value or dedupe_key in seen_buckets[key]:
                    continue
                seen_buckets[key].add(dedupe_key)
                if key == "imports":
                    aggregate_imports.append(normalized_value)
                elif key == "exports":
                    aggregate_exports.append(normalized_value)
                elif key == "symbols":
                    aggregate_symbols.append(normalized_value)
                elif key == "dependencies":
                    aggregate_dependencies.append(normalized_value)
        files.append(entry)

    return {
        "files": files,
        "imports": aggregate_imports[:24],
        "exports": aggregate_exports[:24],
        "symbols": aggregate_symbols[:24],
        "dependencies": aggregate_dependencies[:24],
    }


def _resolve_active_canvas_document(documents: list[dict], active_document_id: str | None = None) -> dict | None:
    target_id = str(active_document_id or "").strip()
    if target_id:
        for document in documents:
            if str(document.get("id") or "") == target_id:
                return document
    return documents[-1] if documents else None


def _document_sort_key(document: dict) -> tuple[int, str, str, str]:
    role = str(document.get("role") or "note")
    priority = CANVAS_FILE_PRIORITY.get(role, 999)
    path = str(document.get("path") or "").strip().lower()
    title = str(document.get("title") or "").strip().lower()
    document_id = str(document.get("id") or "").strip()
    return priority, path, title, document_id


def _normalize_document_path_for_lookup(document_path: str | None) -> str | None:
    normalized_path = _normalize_canvas_path(document_path)
    return normalized_path or None


def _normalize_canvas_lookup_key(value) -> str | None:
    normalized_value = _normalize_document_path_for_lookup(value)
    if not normalized_value:
        return None
    return normalized_value.casefold()


def _normalize_canvas_lookup_basename(value) -> str | None:
    lookup_key = _normalize_canvas_lookup_key(value)
    if not lookup_key:
        return None
    return lookup_key.rsplit("/", 1)[-1]


def _collect_canvas_document_path_matches(documents: list[dict], document_path: str | None) -> dict[str, list[tuple[int, dict]]]:
    lookup_key = _normalize_canvas_lookup_key(document_path)
    match_groups: dict[str, list[tuple[int, dict]]] = {
        "exact_path": [],
        "exact_title": [],
        "suffix": [],
        "basename": [],
    }
    if not lookup_key:
        return match_groups

    lookup_basename = _normalize_canvas_lookup_basename(document_path)
    has_path_segments = "/" in lookup_key
    seen_ids_by_group = {key: set() for key in match_groups}

    def add_match(group_key: str, index: int, document: dict) -> None:
        document_id = str(document.get("id") or "").strip() or f"index:{index}"
        if document_id in seen_ids_by_group[group_key]:
            return
        seen_ids_by_group[group_key].add(document_id)
        match_groups[group_key].append((index, document))

    for index, document in enumerate(documents):
        path_key = _normalize_canvas_lookup_key(document.get("path"))
        if path_key == lookup_key:
            add_match("exact_path", index, document)
            continue

        title_key = _normalize_canvas_lookup_key(document.get("title"))
        if title_key == lookup_key:
            add_match("exact_title", index, document)
            continue

        if has_path_segments:
            suffix = f"/{lookup_key}"
            if path_key and path_key.endswith(suffix):
                add_match("suffix", index, document)
                continue
            if title_key and title_key.endswith(suffix):
                add_match("suffix", index, document)
                continue

        if not lookup_basename:
            continue
        if path_key and path_key.rsplit("/", 1)[-1] == lookup_basename:
            add_match("basename", index, document)
            continue
        if title_key and title_key.rsplit("/", 1)[-1] == lookup_basename:
            add_match("basename", index, document)

    return match_groups


def _find_canvas_document_by_path_locator(documents: list[dict], document_path: str | None) -> tuple[int, dict] | None:
    matches = _collect_canvas_document_path_matches(documents, document_path)
    if matches["exact_path"]:
        return matches["exact_path"][0]
    if len(matches["exact_title"]) == 1:
        return matches["exact_title"][0]
    if len(matches["suffix"]) == 1:
        return matches["suffix"][0]
    if len(matches["basename"]) == 1:
        return matches["basename"][0]
    return None


def _describe_canvas_path_matches(documents: list[dict], document_path: str | None) -> str:
    matches = _collect_canvas_document_path_matches(documents, document_path)
    candidate_matches = matches["exact_title"] or matches["suffix"] or matches["basename"]
    if len(candidate_matches) <= 1:
        return ""

    candidates = []
    for _, document in candidate_matches[:5]:
        label = str(document.get("path") or document.get("title") or document.get("id") or "Canvas").strip()
        if label:
            candidates.append(label)
    if not candidates:
        return ""
    return ", ".join(candidates)


def extract_canvas_primary_locator(document: dict | None) -> dict | None:
    if not isinstance(document, dict):
        return None
    path = _normalize_document_path_for_lookup(document.get("path"))
    if path:
        return {"type": "path", "value": path}
    document_id = str(document.get("id") or "").strip()
    if document_id:
        return {"type": "id", "value": document_id}
    return None


def extract_canvas_active_document_id(metadata: dict | None, documents: list[dict] | None = None) -> str | None:
    source = metadata if isinstance(metadata, dict) else {}
    normalized_documents = documents if isinstance(documents, list) else extract_canvas_documents(source)
    active_document_id = str(source.get("active_document_id") or "").strip()[:80]
    if active_document_id and any(str(document.get("id") or "") == active_document_id for document in normalized_documents):
        return active_document_id
    active_document = _resolve_active_canvas_document(normalized_documents)
    if not active_document:
        return None
    return str(active_document.get("id") or "").strip() or None


def determine_canvas_mode(documents: list[dict] | None) -> str:
    normalized_documents = documents if isinstance(documents, list) else []
    scope_ids = {
        str(document.get("project_id") or document.get("workspace_id") or "").strip()
        for document in normalized_documents
        if str(document.get("project_id") or document.get("workspace_id") or "").strip()
    }
    paths = {str(document.get("path") or "").strip() for document in normalized_documents if str(document.get("path") or "").strip()}
    if len(normalized_documents) > 1 or scope_ids or len(paths) > 1:
        return CANVAS_MODE_PROJECT
    return CANVAS_MODE_DOCUMENT


def _infer_canvas_target_type(documents: list[dict], active_document: dict | None) -> str:
    active_path = str((active_document or {}).get("path") or "").lower()
    dependency_paths = {
        str(document.get("path") or "").lower()
        for document in documents
        if str(document.get("role") or "") == "dependency"
    }
    if active_path.endswith(".py") or "pyproject.toml" in dependency_paths or "requirements.txt" in dependency_paths:
        return "python-project"
    if any(str(document.get("role") or "") == "source" for document in documents):
        return "multi-file-project"
    return "document-set"


def _infer_manifest_name(documents: list[dict], active_document: dict | None) -> str:
    active_document = active_document or {}
    for key in ("project_id", "workspace_id"):
        value = str(active_document.get(key) or "").strip()
        if value:
            return value
    for document in documents:
        for key in ("project_id", "workspace_id"):
            value = str(document.get(key) or "").strip()
            if value:
                return value
    active_path = str(active_document.get("path") or "").strip()
    if active_path:
        top_level = active_path.split("/", 1)[0].strip()
        if top_level:
            return top_level
    return str(active_document.get("title") or "Canvas").strip() or "Canvas"


def build_canvas_project_manifest(documents: list[dict] | None, active_document_id: str | None = None) -> dict | None:
    raw_documents = documents or []
    normalized_documents = extract_canvas_documents({"canvas_documents": raw_documents})
    if not normalized_documents:
        return None

    raw_normalized_documents = [
        cleaned
        for cleaned in (normalize_canvas_document(entry) for entry in raw_documents[:CANVAS_MAX_DOCUMENTS])
        if cleaned
    ]

    active_document = _resolve_active_canvas_document(normalized_documents, active_document_id)
    mode = determine_canvas_mode(raw_normalized_documents or normalized_documents)
    dependency_summaries = []
    seen_dependency_summaries = set()
    open_issues = []
    file_list = []

    missing_paths = 0
    missing_roles = 0
    for document in normalized_documents:
        summary = str(document.get("summary") or "").strip() or _build_canvas_summary(
            str(document.get("title") or "Canvas"),
            document.get("path"),
            document.get("role"),
            str(document.get("content") or ""),
        )
        role = str(document.get("role") or "note")
        entry = {
            "id": document["id"],
            "title": document["title"],
            "format": document["format"],
            "summary": summary,
            "line_count": int(document.get("line_count") or 0),
            "active": active_document is not None and document["id"] == active_document["id"],
            "priority": CANVAS_FILE_PRIORITY.get(role, 999),
        }
        for key in ("path", "role", "language", "project_id", "workspace_id"):
            if document.get(key):
                entry[key] = document[key]
        for key in ("imports", "exports", "symbols", "dependencies"):
            values = document.get(key) if isinstance(document.get(key), list) else []
            if values:
                entry[key] = values[:8]
        file_list.append(entry)

        if mode == CANVAS_MODE_PROJECT and not document.get("path"):
            missing_paths += 1
        if mode == CANVAS_MODE_PROJECT and not document.get("role"):
            missing_roles += 1

        dependency_values = document.get("dependencies") if isinstance(document.get("dependencies"), list) else []
        for value in dependency_values:
            normalized_value = str(value).strip()
            dedupe_key = normalized_value.lower()
            if not normalized_value or dedupe_key in seen_dependency_summaries:
                continue
            dependency_summaries.append(normalized_value)
            seen_dependency_summaries.add(dedupe_key)

    if mode == CANVAS_MODE_PROJECT and missing_paths:
        open_issues.append("Some project canvas documents are missing a path.")
    if mode == CANVAS_MODE_PROJECT and missing_roles:
        open_issues.append("Some project canvas documents are missing a role.")

    file_list.sort(key=_document_sort_key)

    validation_issues = []
    if mode == CANVAS_MODE_PROJECT:
        raw_normalized_paths = []
        for entry in raw_documents[:CANVAS_MAX_DOCUMENTS]:
            if not isinstance(entry, dict):
                continue
            path = _normalize_document_path_for_lookup(entry.get("path"))
            if path:
                raw_normalized_paths.append(path.lower())
        if len(raw_normalized_paths) != len(set(raw_normalized_paths)):
            validation_issues.append("Duplicate project paths detected.")
        active_paths = [entry.get("path") for entry in file_list if entry.get("path")]
        if not any((entry.get("role") == "source") for entry in file_list):
            validation_issues.append("No source file is marked in the project manifest.")

    manifest = {
        "mode": mode,
        "project_name": _infer_manifest_name(normalized_documents, active_document),
        "target_type": _infer_canvas_target_type(normalized_documents, active_document),
        "document_count": len(normalized_documents),
        "active_document_id": active_document["id"] if active_document else None,
        "active_path": active_document.get("path") if active_document else None,
        "active_file": active_document.get("path") or active_document.get("title") if active_document else None,
        "file_list": file_list,
        "open_issues": [*open_issues, *validation_issues],
        "last_validation_status": "ok" if not validation_issues else "needs_attention",
        "dependency_summaries": dependency_summaries[:16],
        "relationship_map": build_canvas_relationship_map(normalized_documents),
    }
    if active_document and active_document.get("project_id"):
        manifest["project_id"] = active_document["project_id"]
    if active_document and active_document.get("workspace_id"):
        manifest["workspace_id"] = active_document["workspace_id"]
    return manifest


def normalize_canvas_document(value, *, fallback_title: str = "Canvas") -> dict | None:
    if not isinstance(value, dict):
        return None

    document_id = str(value.get("id") or "").strip()[:80] or uuid4().hex
    title = str(value.get("title") or fallback_title).strip()[:CANVAS_MAX_TITLE_LENGTH] or fallback_title
    content = _clip_text(value.get("content") or "", CANVAS_MAX_CONTENT_LENGTH)

    # Resolve path and language early so we can auto-infer format.
    path = _normalize_canvas_path(value.get("path"))
    language = (
        _normalize_canvas_language(value.get("language"))
        or _infer_canvas_language(path)
        or _infer_canvas_language(str(value.get("title") or "").strip())
        or _infer_canvas_language_from_content(str(value.get("content") or "").lstrip())
    )

    # Promote format to "code" when path/title extension indicates source code and
    # no explicit format was given by the caller.
    explicit_format = str(value.get("format") or "").strip().lower()
    if explicit_format in CANVAS_ALLOWED_FORMATS:
        format_name = explicit_format
    elif language and language != "markdown":
        format_name = "code"
    else:
        format_name = "markdown"
    created_at = str(value.get("created_at") or "").strip()[:80]
    updated_at = str(value.get("updated_at") or "").strip()[:80]
    role = _normalize_canvas_role(value.get("role")) or _infer_canvas_role(path, title, format_name)
    summary = _normalize_canvas_short_text(value.get("summary"), CANVAS_MAX_SUMMARY_LENGTH)
    imports = _normalize_canvas_string_list(value.get("imports"))
    exports = _normalize_canvas_string_list(value.get("exports"))
    symbols = _normalize_canvas_string_list(value.get("symbols"))
    dependencies = _normalize_canvas_string_list(value.get("dependencies"))
    project_id = _normalize_canvas_identifier(value.get("project_id"))
    workspace_id = _normalize_canvas_identifier(value.get("workspace_id"))

    cleaned = {
        "id": document_id,
        "title": title,
        "format": format_name,
        "content": content,
        "line_count": _line_count(content),
    }
    raw_page_count = value.get("page_count")
    if format_name != "code":
        detected_page_count = len(_extract_canvas_page_sections(content))
        if detected_page_count > 0:
            page_count = detected_page_count
        else:
            try:
                page_count = max(0, int(raw_page_count or 0))
            except (TypeError, ValueError):
                page_count = 0
        if page_count > 0:
            cleaned["page_count"] = page_count

    if path:
        cleaned["path"] = path
    if role:
        cleaned["role"] = role
    cleaned["summary"] = summary or _build_canvas_summary(title, path, role, content)

    if language:
        cleaned["language"] = language
    if imports:
        cleaned["imports"] = imports
    if exports:
        cleaned["exports"] = exports
    if symbols:
        cleaned["symbols"] = symbols
    if dependencies:
        cleaned["dependencies"] = dependencies
    if project_id:
        cleaned["project_id"] = project_id
    if workspace_id:
        cleaned["workspace_id"] = workspace_id

    if created_at:
        cleaned["created_at"] = created_at
    if updated_at:
        cleaned["updated_at"] = updated_at

    source_message_id = value.get("source_message_id")
    if isinstance(source_message_id, int) and source_message_id > 0:
        cleaned["source_message_id"] = source_message_id

    return cleaned


def extract_canvas_documents(metadata: dict | None) -> list[dict]:
    source = metadata if isinstance(metadata, dict) else {}
    raw_documents = source.get("canvas_documents")
    if not isinstance(raw_documents, list):
        return []

    normalized = []
    seen_ids = set()
    seen_paths = set()
    for entry in raw_documents[:CANVAS_MAX_DOCUMENTS]:
        cleaned = normalize_canvas_document(entry)
        if not cleaned:
            continue
        if cleaned["id"] in seen_ids:
            continue
        normalized_path = str(cleaned.get("path") or "").strip().lower()
        if normalized_path and normalized_path in seen_paths:
            continue
        normalized.append(cleaned)
        seen_ids.add(cleaned["id"])
        if normalized_path:
            seen_paths.add(normalized_path)
    return normalized


def list_canvas_lines(content: str) -> list[str]:
    normalized = _normalize_line_endings(content)
    if normalized == "":
        return []
    return normalized.split("\n")


def join_canvas_lines(lines: Iterable[str]) -> str:
    return "\n".join(str(line) for line in lines)


def _normalize_canvas_expected_line(line: str) -> str:
    return _normalize_line_endings(str(line)).rstrip()


def _validate_canvas_expected_lines(
    existing_lines: list[str],
    *,
    expected_lines: list[str] | None,
    expected_start_line: int | None,
    default_start_line: int,
) -> None:
    if expected_lines is None:
        return

    normalized_expected = [_normalize_canvas_expected_line(line) for line in expected_lines]
    if not normalized_expected:
        return

    compare_start = expected_start_line if expected_start_line is not None else default_start_line
    if compare_start < 1:
        raise ValueError("expected_start_line must be at least 1 when expected_lines are provided.")

    compare_end = compare_start + len(normalized_expected) - 1
    if compare_end > len(existing_lines):
        raise ValueError(
            "Canvas context drift detected: the expected lines no longer fit at the current location. Reinspect the document before editing."
        )

    current_slice = [
        _normalize_canvas_expected_line(line)
        for line in existing_lines[compare_start - 1:compare_end]
    ]
    if current_slice != normalized_expected:
        raise ValueError(
            f"Canvas context drift detected around lines {compare_start}-{compare_end}. Reinspect the document before editing."
        )


def extract_canvas_viewports(metadata: dict | None, documents: list[dict] | None = None) -> dict[str, dict]:
    source = metadata if isinstance(metadata, dict) else {}
    raw_viewports = source.get("canvas_viewports")
    if not isinstance(raw_viewports, dict):
        return {}

    normalized_documents = documents if isinstance(documents, list) else extract_canvas_documents(source)
    valid_document_ids = {str(document.get("id") or "") for document in normalized_documents}
    normalized_viewports: dict[str, dict] = {}
    for key, viewport in raw_viewports.items():
        if not isinstance(viewport, dict):
            continue
        document_id = str(viewport.get("document_id") or "").strip()
        if not document_id or document_id not in valid_document_ids:
            continue
        start_line = int(viewport.get("start_line") or 0)
        end_line = int(viewport.get("end_line") or 0)
        if start_line < 1 or end_line < start_line:
            continue
        normalized_key = str(key or viewport.get("document_path") or document_id).strip()
        if not normalized_key:
            continue
        normalized_viewports[normalized_key] = {
            "document_id": document_id,
            "document_path": _normalize_canvas_path(viewport.get("document_path")),
            "start_line": start_line,
            "end_line": end_line,
            "ttl_turns": max(0, int(viewport.get("ttl_turns") or 0)),
            "remaining_turns": max(0, int(viewport.get("remaining_turns") or 0)),
            "auto_unpin_on_edit": viewport.get("auto_unpin_on_edit") is True,
        }
        try:
            page_number = int(viewport.get("page_number") or 0)
        except (TypeError, ValueError):
            page_number = 0
        if page_number > 0:
            normalized_viewports[normalized_key]["page_number"] = page_number
    return normalized_viewports


def create_canvas_runtime_state(
    initial_documents: list[dict] | None = None,
    active_document_id: str | None = None,
    viewports: dict[str, dict] | None = None,
) -> dict:
    documents = extract_canvas_documents({"canvas_documents": initial_documents or []})
    resolved_active_document_id = extract_canvas_active_document_id({"active_document_id": active_document_id}, documents)
    runtime_state = {
        "documents": documents,
        "active_document_id": resolved_active_document_id,
        "viewports": extract_canvas_viewports({"canvas_viewports": viewports or {}}, documents),
    }
    runtime_state["mode"] = determine_canvas_mode(documents)
    return runtime_state


def get_canvas_runtime_active_document_id(runtime_state: dict | None) -> str | None:
    if not isinstance(runtime_state, dict):
        return None
    return extract_canvas_active_document_id(
        {"active_document_id": runtime_state.get("active_document_id")},
        runtime_state.get("documents") if isinstance(runtime_state.get("documents"), list) else [],
    )


def get_canvas_runtime_snapshot(runtime_state: dict | None) -> dict:
    documents = get_canvas_runtime_documents(runtime_state)
    active_document_id = get_canvas_runtime_active_document_id(runtime_state)
    return {
        "documents": documents,
        "active_document_id": active_document_id,
        "viewports": extract_canvas_viewports({"canvas_viewports": (runtime_state or {}).get("viewports")}, documents),
        "mode": determine_canvas_mode(documents),
        "manifest": build_canvas_project_manifest(documents, active_document_id=active_document_id),
    }


def get_canvas_runtime_documents(runtime_state: dict | None) -> list[dict]:
    if not isinstance(runtime_state, dict):
        return []
    return extract_canvas_documents({"canvas_documents": runtime_state.get("documents") or []})


def _refresh_canvas_runtime_state(runtime_state: dict) -> None:
    documents = get_canvas_runtime_documents(runtime_state)
    runtime_state["documents"] = documents
    runtime_state["active_document_id"] = extract_canvas_active_document_id(
        {"active_document_id": runtime_state.get("active_document_id")},
        documents,
    )
    runtime_state["mode"] = determine_canvas_mode(documents)
    runtime_state["viewports"] = extract_canvas_viewports({"canvas_viewports": runtime_state.get("viewports")}, documents)


def _find_canvas_document(
    runtime_state: dict,
    document_id: str | None = None,
    document_path: str | None = None,
) -> tuple[int, dict]:
    documents = runtime_state.get("documents") if isinstance(runtime_state, dict) else None
    if not isinstance(documents, list) or not documents:
        raise ValueError("No canvas document is available yet.")

    normalized_path = _normalize_document_path_for_lookup(document_path)
    if normalized_path:
        match = _find_canvas_document_by_path_locator(documents, normalized_path)
        if match:
            return match
        candidate_text = _describe_canvas_path_matches(documents, normalized_path)
        if candidate_text:
            raise ValueError(f"Canvas document path is ambiguous for {normalized_path}. Matches: {candidate_text}")
        raise ValueError(f"Canvas document not found for path: {normalized_path}")

    target_id = str(document_id or runtime_state.get("active_document_id") or "").strip()
    if target_id:
        for index, document in enumerate(documents):
            if str(document.get("id") or "") == target_id:
                return index, document
        raise ValueError(f"Canvas document not found for id: {target_id}")

    return len(documents) - 1, documents[-1]


def _store_canvas_document(runtime_state: dict, document: dict) -> dict:
    normalized = normalize_canvas_document(document)
    if not normalized:
        raise ValueError("Canvas document is invalid.")

    documents = runtime_state.setdefault("documents", [])
    updated = False
    for index, existing in enumerate(documents):
        if existing.get("id") == normalized["id"]:
            documents[index] = normalized
            updated = True
            break
    if not updated:
        documents.append(normalized)
        if len(documents) > CANVAS_MAX_DOCUMENTS:
            documents[:] = documents[-CANVAS_MAX_DOCUMENTS:]
    runtime_state["active_document_id"] = normalized["id"]
    _refresh_canvas_runtime_state(runtime_state)
    return normalized


def _update_canvas_document_in_place(runtime_state: dict, document_id: str, content: str) -> dict:
    documents = runtime_state.setdefault("documents", [])
    for index, existing in enumerate(documents):
        if str(existing.get("id") or "") != document_id:
            continue
        next_document = dict(existing)
        next_document["content"] = _clip_text(content, CANVAS_MAX_CONTENT_LENGTH)
        normalized = normalize_canvas_document(next_document)
        documents[index] = normalized
        runtime_state["active_document_id"] = normalized["id"]
        _refresh_canvas_runtime_state(runtime_state)
        return normalized
    raise ValueError(f"Canvas document not found for id: {document_id}")


def create_canvas_document(
    runtime_state: dict,
    title: str,
    content: str,
    format_name: str = "markdown",
    language_name: str | None = None,
    path: str | None = None,
    role: str | None = None,
    summary: str | None = None,
    imports: list[str] | None = None,
    exports: list[str] | None = None,
    symbols: list[str] | None = None,
    dependencies: list[str] | None = None,
    project_id: str | None = None,
    workspace_id: str | None = None,
) -> dict:
    normalized = normalize_canvas_document(
        {
            "id": uuid4().hex,
            "title": title or "Canvas",
            "format": format_name,
            "content": content,
            "language": language_name,
            "path": path,
            "role": role,
            "summary": summary,
            "imports": imports,
            "exports": exports,
            "symbols": symbols,
            "dependencies": dependencies,
            "project_id": project_id,
            "workspace_id": workspace_id,
        }
    )
    return _store_canvas_document(runtime_state, normalized)


def rewrite_canvas_document(
    runtime_state: dict,
    content: str,
    document_id: str | None = None,
    document_path: str | None = None,
    title: str | None = None,
    format_name: str | None = None,
    language_name: str | None = None,
    path: str | None = None,
    role: str | None = None,
    summary: str | None = None,
    imports: list[str] | None = None,
    exports: list[str] | None = None,
    symbols: list[str] | None = None,
    dependencies: list[str] | None = None,
    project_id: str | None = None,
    workspace_id: str | None = None,
) -> dict:
    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    next_document = dict(document)
    next_document["content"] = _clip_text(content, CANVAS_MAX_CONTENT_LENGTH)
    if title is not None:
        next_document["title"] = str(title or "Canvas").strip()[:CANVAS_MAX_TITLE_LENGTH] or "Canvas"
    if format_name is not None:
        next_document["format"] = format_name
    if language_name is not None:
        next_document["language"] = language_name
    if path is not None:
        next_document["path"] = path
    if role is not None:
        next_document["role"] = role
    if summary is not None:
        next_document["summary"] = summary
    if imports is not None:
        next_document["imports"] = imports
    if exports is not None:
        next_document["exports"] = exports
    if symbols is not None:
        next_document["symbols"] = symbols
    if dependencies is not None:
        next_document["dependencies"] = dependencies
    if project_id is not None:
        next_document["project_id"] = project_id
    if workspace_id is not None:
        next_document["workspace_id"] = workspace_id
    return _store_canvas_document(runtime_state, next_document)


def replace_canvas_lines(
    runtime_state: dict,
    start_line: int,
    end_line: int,
    lines: list[str],
    document_id: str | None = None,
    document_path: str | None = None,
    expected_lines: list[str] | None = None,
    expected_start_line: int | None = None,
) -> dict:
    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    existing_lines = list_canvas_lines(document.get("content") or "")
    if start_line < 1 or end_line < start_line:
        raise ValueError("start_line and end_line must define a valid 1-based inclusive range.")
    if start_line > len(existing_lines):
        raise ValueError("Line range exceeds the current canvas document.")
    if end_line > len(existing_lines):
        raise ValueError("Line range exceeds the current canvas document.")

    _validate_canvas_expected_lines(
        existing_lines,
        expected_lines=expected_lines,
        expected_start_line=expected_start_line,
        default_start_line=start_line,
    )

    replacement = [str(line) for line in (lines or [])]
    next_lines = [*existing_lines[: start_line - 1], *replacement, *existing_lines[end_line:]]
    next_document = dict(document)
    next_document["content"] = join_canvas_lines(next_lines)
    return _store_canvas_document(runtime_state, next_document)


def insert_canvas_lines(
    runtime_state: dict,
    after_line: int,
    lines: list[str],
    document_id: str | None = None,
    document_path: str | None = None,
    expected_lines: list[str] | None = None,
    expected_start_line: int | None = None,
) -> dict:
    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    existing_lines = list_canvas_lines(document.get("content") or "")
    if after_line < 0 or after_line > len(existing_lines):
        raise ValueError("after_line must be between 0 and the current line count.")

    expected_count = len(expected_lines or [])
    default_start_line = 1 if after_line <= 0 else max(1, after_line - max(0, expected_count - 1))
    _validate_canvas_expected_lines(
        existing_lines,
        expected_lines=expected_lines,
        expected_start_line=expected_start_line,
        default_start_line=default_start_line,
    )

    additions = [str(line) for line in (lines or [])]
    next_lines = [*existing_lines[:after_line], *additions, *existing_lines[after_line:]]
    next_document = dict(document)
    next_document["content"] = join_canvas_lines(next_lines)
    return _store_canvas_document(runtime_state, next_document)


def delete_canvas_lines(
    runtime_state: dict,
    start_line: int,
    end_line: int,
    document_id: str | None = None,
    document_path: str | None = None,
    expected_lines: list[str] | None = None,
    expected_start_line: int | None = None,
) -> dict:
    return replace_canvas_lines(
        runtime_state,
        start_line,
        end_line,
        [],
        document_id=document_id,
        document_path=document_path,
        expected_lines=expected_lines,
        expected_start_line=expected_start_line,
    )


def _normalize_batch_canvas_lines(value, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Batch canvas edit field '{field_name}' must be an array of strings.")
    return [str(line) for line in value]


def _normalize_batch_canvas_operation(operation: dict, index: int) -> dict:
    if not isinstance(operation, dict):
        raise ValueError(f"Batch canvas operation #{index + 1} must be an object.")

    action = str(operation.get("action") or "").strip().lower()
    if action not in {"replace", "insert", "delete"}:
        raise ValueError(f"Batch canvas operation #{index + 1} has unsupported action: {action or '<empty>'}.")

    normalized = {"action": action, "index": index}
    expected_lines = operation.get("expected_lines")
    if expected_lines is not None:
        normalized["expected_lines"] = _normalize_batch_canvas_lines(expected_lines, field_name="expected_lines")

    expected_start_line = operation.get("expected_start_line")
    if expected_start_line is not None:
        try:
            normalized_expected_start_line = int(expected_start_line)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Batch canvas operation #{index + 1} has an invalid expected_start_line.") from exc
        if normalized_expected_start_line < 1:
            raise ValueError(f"Batch canvas operation #{index + 1} expected_start_line must be at least 1.")
        normalized["expected_start_line"] = normalized_expected_start_line

    if action == "insert":
        try:
            after_line = int(operation.get("after_line"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Batch canvas operation #{index + 1} is missing a valid after_line.") from exc
        if after_line < 0:
            raise ValueError(f"Batch canvas operation #{index + 1} after_line must be at least 0.")
        normalized["after_line"] = after_line
        normalized["lines"] = _normalize_batch_canvas_lines(operation.get("lines"), field_name="lines")
        return normalized

    try:
        start_line = int(operation.get("start_line"))
        end_line = int(operation.get("end_line"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Batch canvas operation #{index + 1} is missing a valid line range.") from exc

    if start_line < 1 or end_line < start_line:
        raise ValueError(f"Batch canvas operation #{index + 1} must define a valid 1-based inclusive range.")

    normalized["start_line"] = start_line
    normalized["end_line"] = end_line
    if action == "replace":
        normalized["lines"] = _normalize_batch_canvas_lines(operation.get("lines"), field_name="lines")
    return normalized


def _batch_canvas_operation_delta(operation: dict) -> int:
    action = operation["action"]
    if action == "insert":
        return len(operation.get("lines") or [])
    replaced_count = operation["end_line"] - operation["start_line"] + 1
    if action == "delete":
        return -replaced_count
    return len(operation.get("lines") or []) - replaced_count


def _calculate_batch_canvas_offset(reference_line: int, prior_operations: list[dict]) -> int:
    offset = 0
    for operation in prior_operations:
        if operation["action"] == "insert":
            if operation["after_line"] < reference_line:
                offset += len(operation.get("lines") or [])
            continue
        if operation["start_line"] < reference_line:
            offset += _batch_canvas_operation_delta(operation)
    return offset


def _batch_canvas_operations_overlap(left: dict, right: dict) -> bool:
    left_action = left["action"]
    right_action = right["action"]

    if left_action == "insert" and right_action == "insert":
        return left["after_line"] == right["after_line"]
    if left_action == "insert":
        return right["start_line"] <= left["after_line"] <= right["end_line"]
    if right_action == "insert":
        return left["start_line"] <= right["after_line"] <= left["end_line"]
    return max(left["start_line"], right["start_line"]) <= min(left["end_line"], right["end_line"])


def _validate_batch_canvas_operations(operations: list[dict]) -> list[dict]:
    normalized_operations = [_normalize_batch_canvas_operation(operation, index) for index, operation in enumerate(operations)]
    for index, left in enumerate(normalized_operations):
        for right in normalized_operations[index + 1:]:
            if _batch_canvas_operations_overlap(left, right):
                raise ValueError(
                    f"Batch canvas operations #{left['index'] + 1} and #{right['index'] + 1} overlap. Split them into separate non-overlapping edits."
                )
    return normalized_operations


def batch_canvas_edits(
    runtime_state: dict,
    operations: list[dict],
    *,
    document_id: str | None = None,
    document_path: str | None = None,
    atomic: bool = False,
) -> dict:
    if not isinstance(operations, list) or not operations:
        raise ValueError("batch_canvas_edits requires a non-empty operations array.")

    normalized_operations = _validate_batch_canvas_operations(operations)
    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    resolved_document_id = str(document.get("id") or "").strip() or document_id
    original_document = dict(document)

    applied_operations: list[dict] = []
    changed_ranges: list[dict] = []
    current_document = original_document
    try:
        for operation in normalized_operations:
            expected_start_line = operation.get("expected_start_line")
            adjusted_expected_start_line = None
            if expected_start_line is not None:
                adjusted_expected_start_line = expected_start_line + _calculate_batch_canvas_offset(
                    expected_start_line,
                    applied_operations,
                )

            if operation["action"] == "insert":
                original_after_line = operation["after_line"]
                adjusted_after_line = original_after_line + _calculate_batch_canvas_offset(original_after_line, applied_operations)
                current_document = insert_canvas_lines(
                    runtime_state,
                    after_line=adjusted_after_line,
                    lines=operation.get("lines") or [],
                    document_id=resolved_document_id,
                    expected_lines=operation.get("expected_lines"),
                    expected_start_line=adjusted_expected_start_line,
                )
                edit_start_line = adjusted_after_line + 1
                edit_end_line = adjusted_after_line + len(operation.get("lines") or [])
                changed_ranges.append(
                    {
                        "operation_index": operation["index"],
                        "action": "insert",
                        "requested_after_line": original_after_line,
                        "applied_after_line": adjusted_after_line,
                        "edit_start_line": edit_start_line,
                        "edit_end_line": max(edit_start_line, edit_end_line),
                    }
                )
            else:
                original_start_line = operation["start_line"]
                original_end_line = operation["end_line"]
                adjusted_start_line = original_start_line + _calculate_batch_canvas_offset(original_start_line, applied_operations)
                adjusted_end_line = original_end_line + _calculate_batch_canvas_offset(original_end_line, applied_operations)
                if operation["action"] == "replace":
                    current_document = replace_canvas_lines(
                        runtime_state,
                        start_line=adjusted_start_line,
                        end_line=adjusted_end_line,
                        lines=operation.get("lines") or [],
                        document_id=resolved_document_id,
                        expected_lines=operation.get("expected_lines"),
                        expected_start_line=adjusted_expected_start_line,
                    )
                    replacement_line_count = len(operation.get("lines") or [])
                    changed_ranges.append(
                        {
                            "operation_index": operation["index"],
                            "action": "replace",
                            "requested_start_line": original_start_line,
                            "requested_end_line": original_end_line,
                            "applied_start_line": adjusted_start_line,
                            "applied_end_line": adjusted_end_line,
                            "edit_start_line": adjusted_start_line,
                            "edit_end_line": max(adjusted_start_line, adjusted_start_line + replacement_line_count - 1),
                        }
                    )
                else:
                    current_document = delete_canvas_lines(
                        runtime_state,
                        start_line=adjusted_start_line,
                        end_line=adjusted_end_line,
                        document_id=resolved_document_id,
                        expected_lines=operation.get("expected_lines"),
                        expected_start_line=adjusted_expected_start_line,
                    )
                    changed_ranges.append(
                        {
                            "operation_index": operation["index"],
                            "action": "delete",
                            "requested_start_line": original_start_line,
                            "requested_end_line": original_end_line,
                            "applied_start_line": adjusted_start_line,
                            "applied_end_line": adjusted_end_line,
                            "edit_start_line": adjusted_start_line,
                            "edit_end_line": adjusted_end_line,
                        }
                    )
            applied_operations.append(operation)
    except Exception:
        if atomic:
            _store_canvas_document(runtime_state, original_document)
        raise

    return {
        "status": "ok",
        "action": "batch_edited",
        "document": current_document,
        "document_id": current_document.get("id"),
        "document_path": current_document.get("path"),
        "title": current_document.get("title"),
        "applied_count": len(applied_operations),
        "operation_count": len(normalized_operations),
        "changed_ranges": changed_ranges,
    }


def _parse_canvas_transform_scope(scope: str | None, total_lines: int) -> tuple[int, int]:
    normalized_scope = str(scope or "all").strip().lower()
    if not normalized_scope or normalized_scope == "all":
        return 1, total_lines

    match = re.fullmatch(r"lines_(\d+)_(\d+)", normalized_scope)
    if not match:
        raise ValueError("transform_canvas_lines scope must be 'all' or 'lines_<start>_<end>'.")

    start_line = int(match.group(1))
    end_line = int(match.group(2))
    if start_line < 1 or end_line < start_line:
        raise ValueError("transform_canvas_lines scope must define a valid 1-based inclusive range.")
    if total_lines == 0:
        return 1, 0
    if end_line > total_lines:
        raise ValueError("transform_canvas_lines scope exceeds the current canvas document.")
    return start_line, end_line


def _compile_canvas_transform_pattern(pattern: str, *, is_regex: bool, case_sensitive: bool):
    if pattern == "":
        raise ValueError("transform_canvas_lines pattern must not be empty.")
    if len(pattern) > 500:
        raise ValueError("transform_canvas_lines pattern is too long.")
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.compile(pattern if is_regex else re.escape(pattern), flags)
    except re.error as exc:
        raise ValueError(f"Invalid transform_canvas_lines pattern: {exc}") from exc


def _format_canvas_regex_replacement(replacement: str) -> str:
    return re.sub(r"\$(\d+)", r"\\g<\1>", str(replacement))


def _iter_canvas_transform_affected_lines(text: str, compiled_pattern) -> list[int]:
    line_offsets = [0]
    for index, char in enumerate(text):
        if char == "\n":
            line_offsets.append(index + 1)

    affected_lines: list[int] = []
    for match in compiled_pattern.finditer(text):
        start_offset = match.start()
        line_number = 1
        for candidate_index, offset in enumerate(line_offsets, start=1):
            if offset > start_offset:
                break
            line_number = candidate_index
        if line_number not in affected_lines:
            affected_lines.append(line_number)
    return affected_lines


def transform_canvas_lines(
    runtime_state: dict,
    pattern: str,
    replacement: str,
    *,
    document_id: str | None = None,
    document_path: str | None = None,
    scope: str = "all",
    is_regex: bool = False,
    case_sensitive: bool = True,
    count_only: bool = False,
) -> dict:
    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    document_id = str(document.get("id") or "")
    all_lines = list_canvas_lines(document.get("content") or "")
    scope_start, scope_end = _parse_canvas_transform_scope(scope, len(all_lines))
    scoped_lines = [] if scope_end <= 0 else all_lines[scope_start - 1:scope_end]
    scoped_text = join_canvas_lines(scoped_lines)

    compiled_pattern = _compile_canvas_transform_pattern(str(pattern), is_regex=is_regex, case_sensitive=case_sensitive)
    matches = list(compiled_pattern.finditer(scoped_text))
    affected_line_numbers = [scope_start + line_number - 1 for line_number in _iter_canvas_transform_affected_lines(scoped_text, compiled_pattern)]
    result = {
        "status": "ok",
        "action": "transformed",
        "document_id": document.get("id"),
        "document_path": document.get("path"),
        "title": document.get("title"),
        "matches_found": len(matches),
        "matches_replaced": 0 if count_only else len(matches),
        "affected_lines": affected_line_numbers,
        "scope": scope,
    }
    if count_only or not matches:
        result["document"] = document
        return result

    replacement_text = _format_canvas_regex_replacement(replacement) if is_regex else str(replacement)
    transformed_text = compiled_pattern.sub(replacement_text, scoped_text)
    next_lines = list(all_lines)
    replacement_lines = list_canvas_lines(transformed_text)
    next_lines[scope_start - 1:scope_end] = replacement_lines
    updated_document = _update_canvas_document_in_place(runtime_state, document_id, join_canvas_lines(next_lines))
    result["document"] = updated_document
    return result


def update_canvas_metadata(
    runtime_state: dict,
    *,
    document_id: str | None = None,
    document_path: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    role: str | None = None,
    add_dependencies: list[str] | None = None,
    remove_dependencies: list[str] | None = None,
    add_symbols: list[str] | None = None,
) -> dict:
    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    next_document = dict(document)
    updated_fields: list[str] = []

    if title is not None:
        next_document["title"] = str(title or "Canvas").strip()[:CANVAS_MAX_TITLE_LENGTH] or "Canvas"
        updated_fields.append("title")
    if summary is not None:
        next_document["summary"] = _normalize_canvas_short_text(summary, CANVAS_MAX_SUMMARY_LENGTH) or next_document.get("summary")
        updated_fields.append("summary")
    if role is not None:
        normalized_role = _normalize_canvas_role(role)
        if not normalized_role:
            raise ValueError(f"Unsupported canvas role: {role}")
        next_document["role"] = normalized_role
        updated_fields.append("role")

    if add_dependencies is not None or remove_dependencies is not None:
        dependency_values = list(next_document.get("dependencies") or [])
        dependency_lookup = {str(item).casefold(): str(item) for item in dependency_values}
        for value in _normalize_canvas_string_list(add_dependencies):
            if value.casefold() in dependency_lookup:
                continue
            dependency_values.append(value)
            dependency_lookup[value.casefold()] = value
        for value in _normalize_canvas_string_list(remove_dependencies):
            dependency_lookup.pop(value.casefold(), None)
            dependency_values = [item for item in dependency_values if item.casefold() != value.casefold()]
        next_document["dependencies"] = dependency_values
        updated_fields.append("dependencies")

    if add_symbols is not None:
        symbol_values = list(next_document.get("symbols") or [])
        symbol_lookup = {str(item).casefold() for item in symbol_values}
        for value in _normalize_canvas_string_list(add_symbols):
            if value.casefold() in symbol_lookup:
                continue
            symbol_values.append(value)
            symbol_lookup.add(value.casefold())
        next_document["symbols"] = symbol_values
        updated_fields.append("symbols")

    normalized_document = _store_canvas_document(runtime_state, next_document)
    return {
        "status": "ok",
        "action": "metadata_updated",
        "document": normalized_document,
        "updated_fields": updated_fields,
    }


def preview_canvas_changes(
    runtime_state: dict,
    operations: list[dict],
    *,
    document_id: str | None = None,
    document_path: str | None = None,
) -> dict:
    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    preview_state = create_canvas_runtime_state([document], active_document_id=document.get("id"))
    normalized_operations = _validate_batch_canvas_operations(operations)
    preview_entries: list[dict] = []
    applied_operations: list[dict] = []

    for operation in normalized_operations:
        preview_document = get_canvas_runtime_documents(preview_state)[0]
        preview_lines = list_canvas_lines(preview_document.get("content") or "")
        if operation["action"] == "insert":
            original_after_line = operation["after_line"]
            adjusted_after_line = original_after_line + _calculate_batch_canvas_offset(original_after_line, applied_operations)
            after_index = max(0, adjusted_after_line)
            before_text = ""
            after_text = join_canvas_lines(operation.get("lines") or [])
            edit_start_line = adjusted_after_line + 1
            edit_end_line = max(edit_start_line, adjusted_after_line + len(operation.get("lines") or []))
            preview_entries.append(
                {
                    "operation_index": operation["index"],
                    "action": "insert",
                    "affected_lines": f"{edit_start_line}-{edit_end_line}",
                    "before": before_text,
                    "after": after_text,
                }
            )
        else:
            original_start_line = operation["start_line"]
            original_end_line = operation["end_line"]
            adjusted_start_line = original_start_line + _calculate_batch_canvas_offset(original_start_line, applied_operations)
            adjusted_end_line = original_end_line + _calculate_batch_canvas_offset(original_end_line, applied_operations)
            before_text = join_canvas_lines(preview_lines[adjusted_start_line - 1:adjusted_end_line])
            after_text = "" if operation["action"] == "delete" else join_canvas_lines(operation.get("lines") or [])
            preview_entries.append(
                {
                    "operation_index": operation["index"],
                    "action": operation["action"],
                    "affected_lines": f"{adjusted_start_line}-{adjusted_end_line}",
                    "before": before_text,
                    "after": after_text,
                }
            )

        expected_start_line = operation.get("expected_start_line")
        adjusted_expected_start_line = None
        if expected_start_line is not None:
            adjusted_expected_start_line = expected_start_line + _calculate_batch_canvas_offset(expected_start_line, applied_operations)
        if operation["action"] == "insert":
            adjusted_after_line = operation["after_line"] + _calculate_batch_canvas_offset(operation["after_line"], applied_operations)
            insert_canvas_lines(
                preview_state,
                after_line=adjusted_after_line,
                lines=operation.get("lines") or [],
                document_id=document.get("id"),
                expected_lines=operation.get("expected_lines"),
                expected_start_line=adjusted_expected_start_line,
            )
        elif operation["action"] == "replace":
            adjusted_start_line = operation["start_line"] + _calculate_batch_canvas_offset(operation["start_line"], applied_operations)
            adjusted_end_line = operation["end_line"] + _calculate_batch_canvas_offset(operation["end_line"], applied_operations)
            replace_canvas_lines(
                preview_state,
                start_line=adjusted_start_line,
                end_line=adjusted_end_line,
                lines=operation.get("lines") or [],
                document_id=document.get("id"),
                expected_lines=operation.get("expected_lines"),
                expected_start_line=adjusted_expected_start_line,
            )
        else:
            adjusted_start_line = operation["start_line"] + _calculate_batch_canvas_offset(operation["start_line"], applied_operations)
            adjusted_end_line = operation["end_line"] + _calculate_batch_canvas_offset(operation["end_line"], applied_operations)
            delete_canvas_lines(
                preview_state,
                start_line=adjusted_start_line,
                end_line=adjusted_end_line,
                document_id=document.get("id"),
                expected_lines=operation.get("expected_lines"),
                expected_start_line=adjusted_expected_start_line,
            )
        applied_operations.append(operation)

    insertion_count = sum(1 for entry in preview_entries if entry["action"] == "insert")
    deletion_count = sum(1 for entry in preview_entries if entry["action"] == "delete")
    replace_count = sum(1 for entry in preview_entries if entry["action"] == "replace")
    summary_parts = []
    if insertion_count:
        summary_parts.append(f"{insertion_count} insertion(s)")
    if deletion_count:
        summary_parts.append(f"{deletion_count} deletion(s)")
    if replace_count:
        summary_parts.append(f"{replace_count} replacement(s)")
    summary = ", ".join(summary_parts) if summary_parts else "No changes"

    return {
        "status": "ok",
        "action": "previewed",
        "preview": {
            "document_path": document.get("path"),
            "document_id": document.get("id"),
            "title": document.get("title"),
            "changes": preview_entries,
            "summary": summary,
        },
    }


def _normalize_canvas_viewports(runtime_state: dict) -> dict[str, dict]:
    viewports = runtime_state.get("viewports") if isinstance(runtime_state, dict) else None
    if not isinstance(viewports, dict):
        viewports = {}
        runtime_state["viewports"] = viewports
    return viewports


def set_canvas_viewport(
    runtime_state: dict,
    *,
    start_line: int,
    end_line: int,
    ttl_turns: int = 3,
    auto_unpin_on_edit: bool = True,
    document_id: str | None = None,
    document_path: str | None = None,
    page_number: int | None = None,
) -> dict:
    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    total_lines = int(document.get("line_count") or 0)
    if start_line < 1 or end_line < start_line:
        raise ValueError("set_canvas_viewport requires a valid 1-based inclusive range.")
    if total_lines and end_line > total_lines:
        raise ValueError("set_canvas_viewport range exceeds the current canvas document.")
    viewport_key = str(document.get("path") or document.get("id") or "").strip()
    if not viewport_key:
        raise ValueError("Canvas viewport target is missing a stable document key.")
    normalized_ttl_turns = max(0, int(ttl_turns or 0))
    _normalize_canvas_viewports(runtime_state)[viewport_key] = {
        "document_id": document.get("id"),
        "document_path": document.get("path"),
        "start_line": int(start_line),
        "end_line": int(end_line),
        "ttl_turns": normalized_ttl_turns,
        "remaining_turns": normalized_ttl_turns,
        "auto_unpin_on_edit": auto_unpin_on_edit is True,
    }
    if isinstance(page_number, int) and page_number > 0:
        _normalize_canvas_viewports(runtime_state)[viewport_key]["page_number"] = page_number
    return {
        "status": "ok",
        "action": "viewport_set",
        "pinned": dict(_normalize_canvas_viewports(runtime_state)[viewport_key]),
    }


def focus_canvas_page(
    runtime_state: dict,
    *,
    page_number: int,
    ttl_turns: int = 3,
    auto_unpin_on_edit: bool = True,
    document_id: str | None = None,
    document_path: str | None = None,
) -> dict:
    if int(page_number or 0) < 1:
        raise ValueError("focus_canvas_page requires page_number >= 1.")

    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    page_sections = _extract_canvas_page_sections(document.get("content") or "")
    if not page_sections:
        raise ValueError(
            "This canvas document does not expose page markers yet. focus_canvas_page currently works with page-aware documents such as uploaded PDFs."
        )

    page_range = _get_canvas_page_range(document.get("content") or "", int(page_number))
    if not page_range:
        available_pages = ", ".join(str(section.get("page_number")) for section in page_sections[:12])
        raise ValueError(f"Canvas page {page_number} was not found. Available pages: {available_pages}")

    viewport_result = set_canvas_viewport(
        runtime_state,
        start_line=page_range[0],
        end_line=page_range[1],
        ttl_turns=ttl_turns,
        auto_unpin_on_edit=auto_unpin_on_edit,
        document_id=document.get("id"),
        document_path=document.get("path"),
        page_number=int(page_number),
    )
    pinned = viewport_result.get("pinned") if isinstance(viewport_result.get("pinned"), dict) else {}
    return {
        "status": "ok",
        "action": "page_focused",
        "document_id": document.get("id"),
        "document_path": document.get("path"),
        "title": document.get("title"),
        "page_number": int(page_number),
        "page_count": len(page_sections),
        "start_line": page_range[0],
        "end_line": page_range[1],
        "pinned": pinned,
    }


def clear_canvas_viewport(runtime_state: dict, *, document_path: str | None = None, document_id: str | None = None) -> dict:
    viewports = _normalize_canvas_viewports(runtime_state)
    if document_path is None and document_id is None:
        cleared_count = len(viewports)
        viewports.clear()
        return {"status": "ok", "action": "viewport_cleared", "cleared_count": cleared_count}

    cleared_count = 0
    target_document_id = str(document_id or "").strip()
    target_document_path = _normalize_canvas_path(document_path)
    for key in list(viewports.keys()):
        viewport = viewports.get(key) or {}
        if target_document_id and str(viewport.get("document_id") or "") == target_document_id:
            viewports.pop(key, None)
            cleared_count += 1
            continue
        if target_document_path and _normalize_canvas_path(viewport.get("document_path")) == target_document_path:
            viewports.pop(key, None)
            cleared_count += 1
    return {"status": "ok", "action": "viewport_cleared", "cleared_count": cleared_count}


def decrement_canvas_viewport_ttls(runtime_state: dict) -> None:
    viewports = _normalize_canvas_viewports(runtime_state)
    for key in list(viewports.keys()):
        remaining_turns = int(viewports[key].get("remaining_turns") or 0)
        ttl_turns = int(viewports[key].get("ttl_turns") or 0)
        if ttl_turns <= 0:
            continue
        remaining_turns -= 1
        if remaining_turns <= 0:
            viewports.pop(key, None)
            continue
        viewports[key]["remaining_turns"] = remaining_turns


def get_canvas_viewport_payloads(runtime_state: dict) -> list[dict]:
    documents = get_canvas_runtime_documents(runtime_state)
    document_by_id = {str(document.get("id") or ""): document for document in documents}
    payloads: list[dict] = []
    for viewport in _normalize_canvas_viewports(runtime_state).values():
        document = document_by_id.get(str(viewport.get("document_id") or ""))
        if not document:
            continue
        start_line = int(viewport.get("start_line") or 0)
        end_line = int(viewport.get("end_line") or 0)
        all_lines = list_canvas_lines(document.get("content") or "")
        if start_line < 1 or end_line < start_line or end_line > len(all_lines):
            continue
        payloads.append(
            {
                "document_id": document.get("id"),
                "document_path": document.get("path"),
                "title": document.get("title"),
                "start_line": start_line,
                "end_line": end_line,
                "page_number": int(viewport.get("page_number") or 0),
                "remaining_turns": int(viewport.get("remaining_turns") or 0),
                "auto_unpin_on_edit": viewport.get("auto_unpin_on_edit") is True,
                "visible_lines": [
                    f"{line_number}: {all_lines[line_number - 1]}"
                    for line_number in range(start_line, end_line + 1)
                ],
            }
        )
    return payloads


def clear_overlapping_canvas_viewports(
    runtime_state: dict,
    *,
    document_id: str | None = None,
    document_path: str | None = None,
    edit_start_line: int,
    edit_end_line: int,
) -> int:
    viewports = _normalize_canvas_viewports(runtime_state)
    cleared_count = 0
    normalized_path = _normalize_canvas_path(document_path)
    for key in list(viewports.keys()):
        viewport = viewports.get(key) or {}
        if viewport.get("auto_unpin_on_edit") is not True:
            continue
        same_document = False
        if document_id and str(viewport.get("document_id") or "") == str(document_id):
            same_document = True
        if normalized_path and _normalize_canvas_path(viewport.get("document_path")) == normalized_path:
            same_document = True
        if not same_document:
            continue
        viewport_start = int(viewport.get("start_line") or 0)
        viewport_end = int(viewport.get("end_line") or 0)
        if max(viewport_start, edit_start_line) <= min(viewport_end, edit_end_line):
            viewports.pop(key, None)
            cleared_count += 1
    return cleared_count


def scroll_canvas_document(
    runtime_state: dict,
    start_line: int,
    end_line: int,
    document_id: str | None = None,
    document_path: str | None = None,
    max_window_lines: int = 200,
    max_chars: int | None = None,
) -> dict:
    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    existing_lines = list_canvas_lines(document.get("content") or "")
    total_lines = len(existing_lines)
    if start_line < 1 or end_line < start_line:
        raise ValueError("start_line and end_line must define a valid 1-based inclusive range.")
    if total_lines == 0:
        return {
            "status": "ok",
            "action": "scrolled",
            "document_id": document.get("id"),
            "document_path": document.get("path"),
            "title": document.get("title"),
            "start_line": 1,
            "end_line_actual": 0,
            "total_lines": 0,
            "visible_lines": [],
            "has_more_above": False,
            "has_more_below": False,
        }

    window_limit = max(1, int(max_window_lines or 1))
    effective_start = min(start_line, total_lines)
    effective_end = min(total_lines, end_line, effective_start + window_limit - 1)
    if max_chars is None:
        max_chars = scale_canvas_char_limit(max_window_lines, default_lines=200, default_chars=8_000)

    visible_lines = []
    visible_char_count = 0
    for index in range(effective_start, effective_end + 1):
        numbered_line = f"{index}: {existing_lines[index - 1]}"
        extra_chars = len(numbered_line) + (1 if visible_lines else 0)
        if visible_lines and visible_char_count + extra_chars > max_chars:
            effective_end = index - 1
            break
        if not visible_lines and extra_chars > max_chars:
            visible_lines.append(numbered_line[:max_chars])
            effective_end = index
            break
        visible_lines.append(numbered_line)
        visible_char_count += extra_chars

    return {
        "status": "ok",
        "action": "scrolled",
        "document_id": document.get("id"),
        "document_path": document.get("path"),
        "title": document.get("title"),
        "start_line": effective_start,
        "end_line_actual": effective_end,
        "total_lines": total_lines,
        "visible_lines": visible_lines,
        "has_more_above": effective_start > 1,
        "has_more_below": effective_end < total_lines,
    }


def search_canvas_document(
    runtime_state: dict,
    query: str,
    *,
    document_id: str | None = None,
    document_path: str | None = None,
    all_documents: bool = False,
    is_regex: bool = False,
    case_sensitive: bool = False,
    max_results: int = 10,
) -> dict:
    documents = get_canvas_runtime_documents(runtime_state)
    if not documents:
        raise ValueError("No canvas document is available yet.")

    raw_query = str(query or "")
    if not raw_query.strip():
        raise ValueError("Search query is required.")

    result_limit = max(1, min(50, int(max_results or 10)))
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = None
    if is_regex:
        try:
            pattern = re.compile(raw_query, flags)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc
    else:
        raw_query = raw_query if case_sensitive else raw_query.casefold()

    target_documents = documents
    if not all_documents:
        _, target_document = _find_canvas_document(
            runtime_state,
            document_id=document_id,
            document_path=document_path,
        )
        target_documents = [target_document]

    matches: list[dict] = []
    for document in target_documents:
        for index, line in enumerate(list_canvas_lines(document.get("content") or ""), start=1):
            haystack = line if case_sensitive else line.casefold()
            found = bool(pattern.search(line)) if pattern is not None else raw_query in haystack
            if not found:
                continue
            matches.append(
                {
                    "document_id": document.get("id"),
                    "document_path": document.get("path"),
                    "title": document.get("title"),
                    "line": index,
                    "excerpt": line[:200],
                }
            )
            if len(matches) >= result_limit:
                break
        if len(matches) >= result_limit:
            break

    return {
        "status": "ok",
        "action": "searched",
        "query": query,
        "is_regex": is_regex,
        "case_sensitive": case_sensitive,
        "all_documents": all_documents,
        "match_count": len(matches),
        "matches": matches,
    }


def delete_canvas_document(
    runtime_state: dict,
    document_id: str | None = None,
    document_path: str | None = None,
) -> dict:
    index, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    documents = runtime_state.get("documents") if isinstance(runtime_state, dict) else None
    if not isinstance(documents, list):
        raise ValueError("No canvas document is available yet.")

    previous_active_document_id = get_canvas_runtime_active_document_id(runtime_state)
    removed = documents.pop(index)
    clear_canvas_viewport(runtime_state, document_id=str(removed.get("id") or "") or None, document_path=removed.get("path"))
    if documents:
        runtime_state["active_document_id"] = (
            documents[-1]["id"]
            if str(removed.get("id") or "") == str(previous_active_document_id or "")
            else previous_active_document_id
        )
    else:
        runtime_state["active_document_id"] = None
    _refresh_canvas_runtime_state(runtime_state)
    return {
        "status": "ok",
        "action": "deleted",
        "deleted_id": removed.get("id"),
        "deleted_title": removed.get("title"),
        "remaining_count": len(documents),
    }


def clear_canvas(runtime_state: dict) -> dict:
    documents = get_canvas_runtime_documents(runtime_state)
    cleared_count = len(documents)
    runtime_state["documents"] = []
    runtime_state["active_document_id"] = None
    runtime_state["viewports"] = {}
    runtime_state["mode"] = CANVAS_MODE_DOCUMENT
    return {
        "status": "ok",
        "action": "cleared",
        "cleared_count": cleared_count,
    }


def build_canvas_document_result_snapshot(document: dict | None) -> dict | None:
    normalized = normalize_canvas_document(document)
    if not normalized:
        return None

    snapshot = {
        "id": normalized["id"],
        "title": normalized["title"],
        "format": normalized["format"],
        "line_count": normalized["line_count"],
    }
    if int(normalized.get("page_count") or 0) > 0:
        snapshot["page_count"] = int(normalized["page_count"])
    if normalized.get("language"):
        snapshot["language"] = normalized["language"]
    for key in ("path", "role", "summary", "project_id", "workspace_id"):
        if normalized.get(key):
            snapshot[key] = normalized[key]
    for key in ("imports", "exports", "symbols", "dependencies"):
        values = normalized.get(key) if isinstance(normalized.get(key), list) else []
        if values:
            snapshot[key] = values
    return snapshot


def build_canvas_tool_result(
    document: dict,
    *,
    action: str,
    edit_start_line: int | None = None,
    edit_end_line: int | None = None,
    expected_start_line: int | None = None,
    expected_lines: list[str] | None = None,
) -> dict:
    normalized = normalize_canvas_document(document)
    if not normalized:
        raise ValueError("Canvas document is invalid.")
    content = normalized["content"]
    # For localized edits on code documents, show a context window around the
    # affected region rather than the first 2000 chars. This lets the model
    # verify its changes in place without having to scroll through the file.
    if (
        edit_start_line is not None
        and normalized.get("format") == "code"
        and action in ("lines_replaced", "lines_inserted", "lines_deleted", "lines_batch_edited")
    ):
        all_lines = list_canvas_lines(content)
        total = len(all_lines)
        end_ref = edit_end_line if edit_end_line is not None else edit_start_line
        context_start = max(1, edit_start_line - 4)
        context_end = min(total, end_ref + 4)
        preview = "\n".join(f"{i}: {all_lines[i - 1]}" for i in range(context_start, context_end + 1))
        content_truncated = total > (context_end - context_start + 1)
    else:
        preview = content[:2000]
        content_truncated = len(content) > len(preview)
    result = {
        "status": "ok",
        "action": action,
        "document": build_canvas_document_result_snapshot(normalized),
        "document_id": normalized["id"],
        "primary_locator": extract_canvas_primary_locator(normalized),
        "title": normalized["title"],
        "format": normalized["format"],
        "line_count": normalized["line_count"],
        "content": preview,
        "content_truncated": content_truncated,
    }
    if isinstance(expected_start_line, int) and expected_start_line >= 1:
        result["expected_start_line"] = expected_start_line
    if isinstance(expected_lines, list) and expected_lines:
        result["expected_lines"] = [str(line) for line in expected_lines]
    if normalized.get("language"):
        result["language"] = normalized["language"]
    if int(normalized.get("page_count") or 0) > 0:
        result["page_count"] = int(normalized["page_count"])
    for key in ("path", "role", "summary", "project_id", "workspace_id"):
        if normalized.get(key):
            result[key] = normalized[key]
    for key in ("imports", "exports", "symbols", "dependencies"):
        values = normalized.get(key) if isinstance(normalized.get(key), list) else []
        if values:
            result[key] = values
    return result


def build_canvas_document_context_result(
    runtime_state: dict,
    *,
    document_id: str | None = None,
    document_path: str | None = None,
    max_lines: int | None = None,
    max_chars: int | None = None,
) -> dict:
    _, document = _find_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
    normalized = normalize_canvas_document(document)
    if not normalized:
        raise ValueError("Canvas document is invalid.")

    numbered_lines, is_truncated = _number_canvas_lines(
        normalized.get("content") or "",
        max_lines=max_lines or CANVAS_CONTEXT_MAX_LINES,
        max_chars=max_chars,
    )
    if is_truncated:
        total = normalized.get("line_count") or 0
        shown = len(numbered_lines)
        numbered_lines = [f"[Excerpt: lines 1\u2013{shown} of {total}. Use scroll_canvas_document to view hidden lines.]", *numbered_lines]
    else:
        shown = len(numbered_lines)
    documents = get_canvas_runtime_documents(runtime_state)
    manifest = build_canvas_project_manifest(documents, active_document_id=get_canvas_runtime_active_document_id(runtime_state))
    relationship_map = build_canvas_relationship_map(documents)
    return {
        "status": "ok",
        "action": "expanded",
        "document": build_canvas_document_result_snapshot(normalized),
        "document_id": normalized["id"],
        "document_path": normalized.get("path"),
        "title": normalized["title"],
        "format": normalized["format"],
        "language": normalized.get("language"),
        "role": normalized.get("role"),
        "summary": normalized.get("summary"),
        "line_count": normalized.get("line_count"),
        "visible_lines": numbered_lines,
        "visible_line_end": shown,
        "is_truncated": is_truncated,
        "primary_locator": extract_canvas_primary_locator(normalized),
        "manifest_excerpt": {
            "project_name": (manifest or {}).get("project_name"),
            "target_type": (manifest or {}).get("target_type"),
            "active_file": (manifest or {}).get("active_file"),
        },
        "relationship_map": relationship_map,
    }


def find_latest_canvas_state(messages: list[dict]) -> dict:
    for message in reversed(messages or []):
        metadata = message.get("metadata") if isinstance(message, dict) else None
        if isinstance(metadata, dict) and metadata.get("canvas_cleared") is True:
            return create_canvas_runtime_state([], active_document_id=None)
        documents = extract_canvas_documents(metadata)
        if not documents:
            continue
        active_document_id = extract_canvas_active_document_id(metadata, documents)
        viewports = extract_canvas_viewports(metadata, documents)
        return create_canvas_runtime_state(documents, active_document_id=active_document_id, viewports=viewports)
    return create_canvas_runtime_state()


def find_latest_canvas_documents(messages: list[dict]) -> list[dict]:
    runtime_state = find_latest_canvas_state(messages)
    message_id = None
    for message in reversed(messages or []):
        metadata = message.get("metadata") if isinstance(message, dict) else None
        if isinstance(metadata, dict) and extract_canvas_documents(metadata):
            message_id = message.get("id") if isinstance(message.get("id"), int) else None
            break
    results = []
    for document in get_canvas_runtime_documents(runtime_state):
        result = dict(document)
        if message_id is not None:
            result["source_message_id"] = message_id
        results.append(result)
    return results


def find_latest_canvas_document(
    messages: list[dict],
    document_id: str | None = None,
    document_path: str | None = None,
) -> dict | None:
    target_id = str(document_id or "").strip()
    target_path = _normalize_document_path_for_lookup(document_path)
    documents = list(reversed(find_latest_canvas_documents(messages)))
    if target_path:
        match = _find_canvas_document_by_path_locator(documents, target_path)
        if match:
            _, document = match
            return dict(document)
        return None
    for document in documents:
        if not target_id or document.get("id") == target_id:
            return dict(document)
    return None


def build_markdown_download(document: dict) -> bytes:
    normalized = normalize_canvas_document(document)
    if not normalized:
        raise ValueError("Canvas document is invalid.")
    content = _normalize_line_endings(normalized["content"])
    if normalized.get("format") == "code":
        language = normalized.get("language") or "text"
        return f"```{language}\n{content}\n```\n".encode("utf-8")
    return content.encode("utf-8")


def build_html_download(document: dict) -> bytes:
    normalized = normalize_canvas_document(document)
    if not normalized:
        raise ValueError("Canvas document is invalid.")

    content = _normalize_line_endings(normalized["content"])
    if normalized.get("format") == "code":
        language = escape(normalized.get("language") or "text")
        rendered = f'<pre><code class="language-{language}">{escape(content)}</code></pre>'
    elif markdown_lib is not None:
        rendered = markdown_lib.markdown(
            content,
            extensions=["extra", "fenced_code", "tables", "sane_lists"],
        )
    else:
        rendered = f"<pre>{escape(content)}</pre>"

    title = escape(normalized["title"])
    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{title}</title>
    <style>
        :root {{
            color-scheme: light;
            --bg: #f6f7fb;
            --surface: #ffffff;
            --text: #162033;
            --muted: #52607a;
            --border: #d8dfeb;
            --accent: #3157d5;
            --code-bg: #eef2fb;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            background: linear-gradient(180deg, #eef2ff 0%, var(--bg) 220px);
            color: var(--text);
            font: 16px/1.7 \"Segoe UI\", Arial, sans-serif;
        }}
        main {{
            width: min(900px, calc(100vw - 32px));
            margin: 32px auto;
            padding: 32px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 20px;
            box-shadow: 0 24px 70px rgba(22, 32, 51, 0.08);
        }}
        h1, h2, h3, h4 {{ line-height: 1.25; color: #0f1728; }}
        p, li, blockquote {{ color: var(--text); }}
        blockquote {{ border-left: 4px solid var(--accent); margin: 1rem 0; padding: 0.1rem 0 0.1rem 1rem; color: var(--muted); }}
        pre {{ background: var(--code-bg); border: 1px solid var(--border); border-radius: 14px; padding: 14px; overflow-x: auto; }}
        code {{ background: var(--code-bg); border-radius: 6px; padding: 0.15em 0.35em; font-family: \"Cascadia Code\", Consolas, monospace; }}
        pre code {{ background: transparent; padding: 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ border: 1px solid var(--border); padding: 10px 12px; text-align: left; vertical-align: top; }}
        th {{ background: #f3f6fd; }}
        a {{ color: var(--accent); }}
    </style>
</head>
<body>
    <main>
        <article>
            {rendered}
        </article>
    </main>
</body>
</html>
"""
    return html.encode("utf-8")


def build_pdf_download(document: dict) -> bytes:
    normalized = normalize_canvas_document(document)
    if not normalized:
        raise ValueError("Canvas document is invalid.")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CanvasTitle",
        parent=styles["Title"],
        fontName=_BOLD_FONT,
    )
    body_style = ParagraphStyle(
        "CanvasBody",
        parent=styles["BodyText"],
        fontName=_BODY_FONT,
        fontSize=10,
        leading=14,
        spaceAfter=6,
    )
    heading1_style = ParagraphStyle(
        "CanvasH1",
        parent=styles["Heading1"],
        fontName=_BOLD_FONT,
        textColor=colors.HexColor("#1f2a44"),
        spaceAfter=8,
        spaceBefore=14,
    )
    heading_style = ParagraphStyle(
        "CanvasHeading",
        parent=styles["Heading2"],
        fontName=_BOLD_FONT,
        textColor=colors.HexColor("#1f2a44"),
        spaceAfter=8,
        spaceBefore=10,
    )
    code_style = ParagraphStyle(
        "CanvasCode",
        parent=styles["Code"],
        fontName=_MONO_FONT,
        fontSize=8.5,
        leading=11,
        leftIndent=10,
        rightIndent=10,
        backColor=colors.HexColor("#f3f5f9"),
        borderPadding=8,
    )

    story = [Paragraph(escape(normalized["title"]), title_style), Spacer(1, 6)]
    if normalized.get("format") == "code":
        story.append(Preformatted(_normalize_line_endings(normalized["content"]), code_style))
        output = BytesIO()
        doc = SimpleDocTemplate(output, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
        doc.build(story)
        return output.getvalue()

    append_markdown_pdf_story(
        story,
        normalized["content"],
        body_style=body_style,
        heading1_style=heading1_style,
        heading_style=heading_style,
        subheading_style=heading_style,
        code_style=code_style,
        heading_level_offset=0,
    )

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    doc.build(story)
    return output.getvalue()