from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import random
import re
import socket
import unicodedata
import warnings
import xml.etree.ElementTree as ET
from io import BytesIO
from urllib.parse import quote as url_quote
from urllib.parse import urljoin
from urllib.parse import urlparse

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)

import requests as http_requests
from bs4 import BeautifulSoup, NavigableString, Tag
from ddgs import DDGS
from urllib3.exceptions import InsecureRequestWarning

from config import (
    CONTENT_MAX_CHARS,
    FETCH_MAX_REDIRECTS,
    FETCH_MAX_SIZE,
    FETCH_TIMEOUT,
    PRIVATE_NETWORKS,
    PROXIES_PATH,
    SEARCH_MAX_RESULTS,
)
from db import cache_get, cache_set, get_proxy_enabled_operations
from proxy_settings import (
    PROXY_OPERATION_FETCH_URL,
    PROXY_OPERATION_SEARCH_NEWS_DDGS,
    PROXY_OPERATION_SEARCH_NEWS_GOOGLE,
    PROXY_OPERATION_SEARCH_WEB,
)

_BROWSER_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
]
_CHROME_SEC_UA = [
    '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="99"',
    '"Microsoft Edge";v="124", "Chromium";v="124", "Not-A.Brand";v="99"',
]
_ACCEPT_LANGS = [
    "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "en-US,en;q=0.9,tr;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "tr,en;q=0.8",
]
_GN_LANG = {
    "tr": {"hl": "tr", "gl": "TR", "ceid": "TR:tr"},
    "en": {"hl": "en", "gl": "US", "ceid": "US:en"},
}
_GN_WHEN = {
    "d": "when:1d",
    "w": "when:7d",
    "m": "when:30d",
    "y": "when:1y",
}
_DDGS_TIMELIMIT = {"d": "d", "w": "w", "m": "m", "y": "y"}
_DDGS_REGION = {"tr": "tr-tr", "en": "us-en"}
_proxy_index = 0
_proxy_cache: list[str] | None = None
_proxy_cache_mtime: float | None = None
_FETCH_RETRYABLE_STATUS_CODES = {401, 403, 408, 425, 429, 500, 502, 503, 504}
_THIN_CONTENT_MIN_CHARS = 80
_LOW_PRIORITY_BLOCK_MIN_CHARS = 30
_HTML_HARD_NOISE_TAGS = (
    "script",
    "style",
    "iframe",
    "form",
    "button",
    "input",
    "select",
    "textarea",
    "svg",
    "canvas",
)
_HTML_LOW_PRIORITY_TAGS = (
    "nav",
    "footer",
    "aside",
    "header",
)
_HTML_NOISE_TAGS = _HTML_HARD_NOISE_TAGS + _HTML_LOW_PRIORITY_TAGS
_HTML_CONTENT_ROOT_SELECTORS = (
    "main",
    "article",
    "[role='main']",
    ".main-content",
    ".page-content",
    ".content",
    ".article-content",
    ".article-body",
    ".entry-content",
    ".post-content",
    ".post-body",
    ".markdown-body",
    ".doc-content",
    ".documentation-content",
)
_HTML_NOISE_HINTS = (
    "nav",
    "menu",
    "footer",
    "header",
    "cookie",
    "consent",
    "banner",
    "popup",
    "modal",
    "dialog",
    "share",
    "social",
    "subscribe",
    "newsletter",
    "promo",
    "advert",
    "ads",
    "breadcrumb",
    "comment",
    "related",
    "recommend",
    "sidebar",
    "toolbar",
    "pagination",
    "search",
    "login",
    "signup",
    "register",
)
_HTML_NOISE_ROLES = {
    "navigation",
    "banner",
    "contentinfo",
    "complementary",
    "search",
    "dialog",
    "alert",
    "menu",
}
_HTML_CONTAINER_TAGS = {
    "body",
    "main",
    "article",
    "section",
    "div",
    "figure",
    "details",
}
_HTML_PARAGRAPH_TAGS = {
    "p",
    "summary",
    "figcaption",
    "caption",
    "legend",
    "dd",
    "dt",
    "address",
}
_ZERO_WIDTH_TRANSLATION = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)


def _build_browser_headers(
    accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    url: str | None = None,
    relaxed: bool = False,
) -> dict:
    ua = random.choice(_BROWSER_UAS)
    is_firefox = "Firefox" in ua
    headers: dict = {
        "User-Agent": ua,
        "Accept": accept,
        "Accept-Language": random.choice(_ACCEPT_LANGS),
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }
    if url:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    if not is_firefox:
        headers["Sec-CH-UA"] = random.choice(_CHROME_SEC_UA)
        headers["Sec-CH-UA-Mobile"] = "?1" if "Mobile" in ua else "?0"
        headers["Sec-CH-UA-Platform"] = (
            '"Android"'
            if "Android" in ua
            else '"macOS"'
            if "Macintosh" in ua
            else '"Linux"'
            if "Linux" in ua
            else '"Windows"'
        )
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none"
        headers["Sec-Fetch-User"] = "?1"
    if relaxed:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        headers["Cache-Control"] = "no-cache"
        headers.pop("Upgrade-Insecure-Requests", None)
    return headers


def _iter_fetch_header_variants(url: str):
    yield _build_browser_headers(url=url)
    yield _build_browser_headers(url=url, relaxed=True)


def load_proxies() -> list[str]:
    global _proxy_cache, _proxy_cache_mtime

    try:
        current_mtime = os.path.getmtime(PROXIES_PATH)
    except OSError:
        _proxy_cache = []
        _proxy_cache_mtime = None
        return []

    if _proxy_cache is not None and _proxy_cache_mtime == current_mtime:
        return list(_proxy_cache)

    proxies = []
    with open(PROXIES_PATH, "r", encoding="utf-8") as handle:
        for line in handle:
            proxy = line.strip()
            if not proxy or proxy.startswith("#"):
                continue
            parsed = urlparse(proxy)
            if parsed.scheme in {"http", "https", "socks5", "socks5h"} and parsed.hostname and parsed.port:
                proxies.append(proxy)

    _proxy_cache = proxies
    _proxy_cache_mtime = current_mtime
    return list(proxies)


def get_proxy_candidates(include_direct_fallback: bool = False) -> list[str | None]:
    global _proxy_index
    proxies = load_proxies()
    if not proxies:
        return [None]

    start = _proxy_index % len(proxies)
    _proxy_index = (_proxy_index + 1) % len(proxies)
    ordered = proxies[start:] + proxies[:start]
    if include_direct_fallback:
        ordered.append(None)
    return ordered


def get_proxy_candidates_for_operation(
    operation: str,
    *,
    include_direct_fallback: bool = False,
    settings: dict | None = None,
) -> list[str | None]:
    enabled_operations = set(get_proxy_enabled_operations(settings))
    normalized_operation = str(operation or "").strip().lower()
    if normalized_operation not in enabled_operations:
        return [None]
    return get_proxy_candidates(include_direct_fallback=include_direct_fallback)


def _requests_proxy_dict(proxy: str | None):
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def _is_safe_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"
    if parsed.scheme not in ("http", "https"):
        return False, "Only http and https are supported"
    hostname = parsed.hostname or ""
    if not hostname:
        return False, "Hostname not found"
    if hostname.lower() in ("localhost", "localhost."):
        return False, "Local addresses are prohibited"
    try:
        for info in socket.getaddrinfo(hostname, None):
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            for net in PRIVATE_NETWORKS:
                if ip in net:
                    return False, f"Private/local network address prohibited: {addr}"
    except socket.gaierror:
        return False, f"DNS resolution failed: {hostname}"
    return True, ""


def _clean_extracted_text(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", str(text or ""))
    cleaned = cleaned.translate(_ZERO_WIDTH_TRANSLATION)
    cleaned = cleaned.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)

    normalized_lines = []
    for line in cleaned.split("\n"):
        stripped = re.sub(r"\s+", " ", line).strip()
        if stripped and re.fullmatch(r"[-_=|~•·*.]{3,}", stripped):
            continue
        normalized_lines.append(stripped)

    cleaned = "\n".join(normalized_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _truncate_content(text: str) -> str:
    if len(text) <= CONTENT_MAX_CHARS:
        return text
    return text[:CONTENT_MAX_CHARS].rstrip() + "\n[Content truncated]"


def _extract_meta_content(soup: BeautifulSoup, *selectors: tuple[str, str]) -> str:
    for attr, value in selectors:
        tag = soup.find("meta", attrs={attr: value})
        content = (tag.get("content") or "").strip() if tag else ""
        if content:
            return content
    return ""


def _collect_structured_text(value, parts: list[str], limit: int = 6):
    if len(parts) >= limit or value is None:
        return
    if isinstance(value, str):
        cleaned = _clean_extracted_text(value)
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
        return
    if isinstance(value, list):
        for item in value:
            if len(parts) >= limit:
                break
            _collect_structured_text(item, parts, limit=limit)
        return
    if not isinstance(value, dict):
        return

    for key in ("headline", "name", "description", "articleBody", "text"):
        if len(parts) >= limit:
            break
        _collect_structured_text(value.get(key), parts, limit=limit)

    if len(parts) < limit:
        main_entity = value.get("mainEntity") or value.get("mainEntityOfPage")
        _collect_structured_text(main_entity, parts, limit=limit)


def _extract_json_ld_text(soup: BeautifulSoup) -> str:
    parts: list[str] = []
    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        _collect_structured_text(parsed, parts)
        if len(parts) >= 6:
            break
    return "\n\n".join(parts[:6])


def _combine_distinct_text_blocks(blocks: list[str]) -> str:
    combined: list[str] = []
    seen = set()
    for block in blocks:
        cleaned = _clean_extracted_text(block)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        skip_current = False
        replaced_indexes = []
        for index, existing in enumerate(combined):
            existing_key = existing.casefold()
            if len(key) >= 40 and key in existing_key:
                skip_current = True
                break
            if len(existing_key) >= 40 and existing_key in key:
                replaced_indexes.append(index)
        if skip_current:
            continue
        for index in reversed(replaced_indexes):
            seen.discard(combined[index].casefold())
            combined.pop(index)
        seen.add(key)
        combined.append(cleaned)
    return "\n\n".join(combined)


def _extract_tag_hints(tag: Tag) -> str:
    attrs = tag.attrs if isinstance(getattr(tag, "attrs", None), dict) else {}
    parts: list[str] = []
    if attrs.get("id"):
        parts.append(str(attrs.get("id") or ""))
    classes = attrs.get("class") if isinstance(attrs.get("class"), list) else []
    if classes:
        parts.extend(str(item or "") for item in classes)
    for attr_name in ("role", "aria-label", "data-testid"):
        value = attrs.get(attr_name)
        if value:
            parts.append(str(value))
    return " ".join(parts).strip().casefold()


def _is_probably_noise_block(tag: Tag) -> bool:
    attrs = tag.attrs if isinstance(getattr(tag, "attrs", None), dict) else {}
    if tag.name in _HTML_NOISE_TAGS:
        return True
    if "hidden" in attrs:
        return True
    if str(attrs.get("aria-hidden") or "").strip().lower() == "true":
        return True
    role = str(attrs.get("role") or "").strip().lower()
    if role in _HTML_NOISE_ROLES:
        return True

    hints = _extract_tag_hints(tag)
    if hints and any(token in hints for token in _HTML_NOISE_HINTS):
        text = _clean_extracted_text(tag.get_text(separator=" "))
        if len(text) < 1_500:
            return True

    links = tag.find_all("a")
    if links and tag.name in {"div", "section", "aside", "ul", "ol"}:
        text = _clean_extracted_text(tag.get_text(separator=" "))
        link_text = _clean_extracted_text(" ".join(link.get_text(separator=" ") for link in links))
        if text and len(link_text) >= max(40, int(len(text) * 0.6)) and len(text) < 500:
            return True
    return False


def _prune_html_noise(soup: BeautifulSoup) -> None:
    for tag in list(soup.find_all(True)):
        if _is_probably_noise_block(tag):
            tag.decompose()


def _pick_html_content_root(soup: BeautifulSoup):
    candidates: list[tuple[int, Tag, str]] = []
    seen_ids: set[int] = set()

    def add_candidate(node, label: str):
        if not isinstance(node, Tag):
            return
        identity = id(node)
        if identity in seen_ids:
            return
        seen_ids.add(identity)
        text = _clean_extracted_text(node.get_text(separator="\n"))
        if not text:
            return
        score = len(text)
        if label == "main":
            score += 1_000
        elif label == "article":
            score += 900
        elif label == "body":
            score += 100
        hints = _extract_tag_hints(node)
        if any(token in hints for token in ("content", "article", "post", "entry", "markdown", "doc")):
            score += 250
        link_count = len(node.find_all("a"))
        if link_count:
            score -= min(400, link_count * 8)
        candidates.append((score, node, label))

    add_candidate(soup.find("main"), "main")
    add_candidate(soup.find("article"), "article")
    for selector in _HTML_CONTENT_ROOT_SELECTORS:
        for node in soup.select(selector):
            add_candidate(node, node.name if node.name in {"main", "article", "body"} else "root")
    add_candidate(soup.body, "body")

    if not candidates:
        return soup, "root"

    _, root, label = max(candidates, key=lambda item: item[0])
    return root, label if label in {"main", "article", "body"} else "root"


def _clean_markdown_inline_text(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", str(text or ""))
    cleaned = cleaned.translate(_ZERO_WIDTH_TRANSLATION)
    cleaned = cleaned.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = "\n".join(part.strip() for part in cleaned.split("\n"))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned.strip()


def _render_inline_markdown(node, base_url: str) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    if _is_probably_noise_block(node):
        return ""
    if node.name == "br":
        return "\n"
    if node.name == "img":
        return _clean_markdown_inline_text(node.get("alt") or "")
    if node.name == "code" and isinstance(node.parent, Tag) and node.parent.name == "pre":
        return ""

    children_text = "".join(_render_inline_markdown(child, base_url) for child in node.children)
    cleaned_text = _clean_markdown_inline_text(children_text)
    if not cleaned_text:
        return ""

    if node.name in {"strong", "b"}:
        return f"**{cleaned_text}**"
    if node.name in {"em", "i"}:
        return f"*{cleaned_text}*"
    if node.name == "code":
        return f"`{cleaned_text.replace('`', '')}`"
    if node.name == "a":
        href = str(node.get("href") or "").strip()
        resolved = urljoin(base_url, href) if href else ""
        if resolved.startswith(("http://", "https://")):
            if cleaned_text == resolved:
                return cleaned_text
            return f"[{cleaned_text}]({resolved})"
        return cleaned_text
    if node.name == "sup":
        return f"^{cleaned_text}"
    if node.name == "sub":
        return f"~{cleaned_text}"
    return children_text


def _parse_span_value(raw_value) -> int:
    try:
        return max(1, int(str(raw_value or "1").strip()))
    except (TypeError, ValueError):
        return 1


def _render_table_markdown(table: Tag, base_url: str) -> str:
    row_tags = table.find_all("tr")
    if not row_tags:
        return ""

    grid: dict[int, dict[int, str]] = {}
    max_columns = 0
    for row_index, row in enumerate(row_tags):
        row_map = grid.setdefault(row_index, {})
        col_index = 0
        for cell in row.find_all(["th", "td"], recursive=False):
            while col_index in row_map:
                col_index += 1
            cell_text = _clean_markdown_inline_text(_render_inline_markdown(cell, base_url)) or _clean_extracted_text(
                cell.get_text(separator=" ")
            )
            normalized_text = cell_text.replace("|", "\\|")
            colspan = _parse_span_value(cell.get("colspan"))
            rowspan = _parse_span_value(cell.get("rowspan"))
            for row_offset in range(rowspan):
                target_row = grid.setdefault(row_index + row_offset, {})
                for col_offset in range(colspan):
                    target_row[col_index + col_offset] = normalized_text
            col_index += colspan
        max_columns = max(max_columns, len(row_map), col_index)

    rows: list[list[str]] = []
    for row_index in range(len(row_tags)):
        row_map = grid.get(row_index, {})
        normalized_row = [row_map.get(col_index, "") for col_index in range(max_columns)]
        if any(cell for cell in normalized_row):
            rows.append(normalized_row)
    if not rows:
        return ""
    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    if len(normalized_rows) == 1:
        return " | ".join(normalized_rows[0]).strip()
    header = normalized_rows[0]
    separator = ["---"] * column_count
    body = normalized_rows[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines).strip()


def _render_list_markdown(list_tag: Tag, base_url: str, depth: int = 0) -> str:
    lines: list[str] = []
    ordered = list_tag.name == "ol"
    for index, item in enumerate(list_tag.find_all("li", recursive=False), start=1):
        marker = f"{index}. " if ordered else "- "
        prefix = "  " * depth + marker
        lead_parts: list[str] = []
        nested_lines: list[str] = []
        for child in item.children:
            if isinstance(child, NavigableString):
                cleaned_child = _clean_markdown_inline_text(str(child))
                if cleaned_child:
                    lead_parts.append(cleaned_child)
                continue
            if not isinstance(child, Tag) or _is_probably_noise_block(child):
                continue
            if child.name in {"ul", "ol"}:
                nested_markdown = _render_list_markdown(child, base_url, depth + 1)
                if nested_markdown:
                    nested_lines.extend(nested_markdown.splitlines())
                continue
            if child.name in _HTML_CONTAINER_TAGS | _HTML_PARAGRAPH_TAGS:
                child_blocks = _render_markdown_blocks(child, base_url)
                if child_blocks:
                    if not lead_parts:
                        lead_parts.append(child_blocks[0])
                        extra_blocks = child_blocks[1:]
                    else:
                        extra_blocks = child_blocks
                    for block in extra_blocks:
                        nested_lines.extend(("  " * (depth + 1) + line) if line else "" for line in block.splitlines())
                continue
            rendered = _clean_markdown_inline_text(_render_inline_markdown(child, base_url))
            if rendered:
                lead_parts.append(rendered)
        lead_text = _clean_markdown_inline_text(" ".join(part for part in lead_parts if part)) or "Item"
        lines.append(prefix + lead_text)
        lines.extend(nested_lines)
    return "\n".join(line for line in lines if line is not None).strip()


def _render_definition_list_markdown(list_tag: Tag, base_url: str) -> str:
    lines: list[str] = []
    current_term = ""
    for child in list_tag.children:
        if isinstance(child, NavigableString):
            continue
        if not isinstance(child, Tag) or _is_probably_noise_block(child):
            continue
        if child.name == "dt":
            current_term = _clean_markdown_inline_text(_render_inline_markdown(child, base_url))
            continue
        if child.name != "dd":
            continue
        blocks = _render_markdown_blocks(child, base_url)
        definition = _clean_markdown_inline_text(" ".join(blocks)) if blocks else _clean_extracted_text(child.get_text(separator=" "))
        if not definition:
            continue
        if current_term:
            lines.append(f"**{current_term}**: {definition}")
        else:
            lines.append(definition)
    return "\n".join(lines).strip()


def _render_markdown_blocks(node, base_url: str) -> list[str]:
    if isinstance(node, NavigableString):
        cleaned = _clean_markdown_inline_text(str(node))
        return [cleaned] if cleaned else []
    if not isinstance(node, Tag) or _is_probably_noise_block(node):
        return []

    tag_name = node.name.lower()
    if tag_name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        text = _clean_markdown_inline_text(_render_inline_markdown(node, base_url))
        return [f"{'#' * int(tag_name[1])} {text}"] if text else []
    if tag_name in _HTML_PARAGRAPH_TAGS:
        text = _clean_markdown_inline_text(_render_inline_markdown(node, base_url))
        return [text] if text else []
    if tag_name in {"ul", "ol"}:
        rendered_list = _render_list_markdown(node, base_url)
        return [rendered_list] if rendered_list else []
    if tag_name == "dl":
        rendered_list = _render_definition_list_markdown(node, base_url)
        return [rendered_list] if rendered_list else []
    if tag_name == "pre":
        code_text = (node.get_text(separator="\n") or "").replace("\r\n", "\n").strip("\n")
        if not code_text.strip():
            return []
        class_names = node.get("class") if isinstance(node.get("class"), list) else []
        if not class_names:
            code_child = node.find("code")
            class_names = code_child.get("class") if isinstance(code_child, Tag) and isinstance(code_child.get("class"), list) else []
        language = ""
        for class_name in class_names or []:
            match = re.search(r"language-([A-Za-z0-9_+-]+)", str(class_name or ""))
            if match:
                language = match.group(1)
                break
        return [f"```{language}\n{code_text}\n```".strip()]
    if tag_name == "blockquote":
        child_blocks: list[str] = []
        for child in node.children:
            child_blocks.extend(_render_markdown_blocks(child, base_url))
        if not child_blocks:
            quoted = _clean_markdown_inline_text(_render_inline_markdown(node, base_url))
            child_blocks = [quoted] if quoted else []
        if not child_blocks:
            return []
        quoted_lines = []
        for block in child_blocks:
            for line in block.splitlines() or [""]:
                quoted_lines.append(f"> {line}" if line else ">")
        return ["\n".join(quoted_lines).strip()]
    if tag_name == "table":
        table_markdown = _render_table_markdown(node, base_url)
        return [table_markdown] if table_markdown else []
    if tag_name == "hr":
        return []
    if tag_name in _HTML_CONTAINER_TAGS:
        blocks: list[str] = []
        for child in node.children:
            blocks.extend(_render_markdown_blocks(child, base_url))
        if blocks:
            return blocks
        fallback = _clean_markdown_inline_text(_render_inline_markdown(node, base_url))
        return [fallback] if fallback else []

    fallback = _clean_markdown_inline_text(_render_inline_markdown(node, base_url))
    return [fallback] if fallback else []


def _combine_distinct_markdown_blocks(blocks: list[str]) -> str:
    combined: list[str] = []
    seen = set()
    for block in blocks:
        cleaned_block = str(block or "").strip()
        if not cleaned_block:
            continue
        dedupe_key = _clean_extracted_text(re.sub(r"[#>*`\[\]()_-]", " ", cleaned_block)).casefold()
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        combined.append(cleaned_block)
    markdown = "\n\n".join(combined).strip()
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown


def _build_html_markdown(
    *,
    content_root: Tag,
    url: str,
    meta_description: str,
    structured_text: str,
    low_priority_blocks: list[str],
    noscript_text: str,
    primary_text: str,
) -> str:
    markdown_blocks = _render_markdown_blocks(content_root, url)
    primary_markdown = _combine_distinct_markdown_blocks(markdown_blocks)
    supplemental_blocks: list[str] = []
    normalized_primary_text = _clean_extracted_text(primary_text).casefold()
    normalized_primary_markdown = _clean_extracted_text(primary_markdown).casefold()
    normalized_meta_description = _clean_extracted_text(meta_description).casefold()

    if meta_description and normalized_meta_description not in {
        normalized_primary_text,
        normalized_primary_markdown,
    }:
        if normalized_meta_description and normalized_meta_description not in normalized_primary_text:
            supplemental_blocks.append(meta_description)

    if len(primary_text) < _THIN_CONTENT_MIN_CHARS:
        if structured_text:
            supplemental_blocks.append("## Structured Data Highlights\n\n" + structured_text)
        supplemental_blocks.extend(low_priority_blocks)
        if noscript_text:
            supplemental_blocks.append(noscript_text)
    return _combine_distinct_markdown_blocks([*supplemental_blocks, primary_markdown])


def _extract_html_outline(root) -> list[str]:
    headings = []
    for tag in root.find_all(["h1", "h2", "h3", "h4"]):
        text = _clean_extracted_text(tag.get_text(separator=" "))
        if text and len(headings) < 50:
            headings.append(f"[{tag.name.lower()}] {text[:120]}")
    return headings


def _collect_low_priority_html_blocks(soup: BeautifulSoup) -> list[str]:
    blocks: list[str] = []
    for tag in soup.find_all(list(_HTML_LOW_PRIORITY_TAGS)):
        text = _clean_extracted_text(tag.get_text(separator="\n"))
        if text and len(text) >= _LOW_PRIORITY_BLOCK_MIN_CHARS:
            blocks.append(text)
    return blocks


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _extract_html(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("title") or ""
    title = title.get_text(strip=True) if title else ""
    if not title:
        title = _extract_meta_content(soup, ("property", "og:title"), ("name", "twitter:title"))

    noscript_text = _combine_distinct_text_blocks([tag.get_text(separator="\n") for tag in soup.find_all("noscript")])
    meta_description = _extract_meta_content(
        soup,
        ("name", "description"),
        ("property", "og:description"),
        ("name", "twitter:description"),
    )
    structured_text = _extract_json_ld_text(soup)
    low_priority_blocks = _collect_low_priority_html_blocks(soup)

    _prune_html_noise(soup)

    content_root, content_source_element = _pick_html_content_root(soup)
    outline = _extract_html_outline(content_root)
    primary_text = _clean_extracted_text(content_root.get_text(separator="\n"))
    reusable_summary = _combine_distinct_text_blocks([meta_description, structured_text])
    text = _combine_distinct_text_blocks([reusable_summary, primary_text]) if reusable_summary else primary_text
    if len(primary_text) < _THIN_CONTENT_MIN_CHARS:
        text = _combine_distinct_text_blocks([reusable_summary, primary_text, *low_priority_blocks, noscript_text])
    if not text:
        text = _combine_distinct_text_blocks([reusable_summary, *low_priority_blocks, noscript_text])
    markdown_content = _build_html_markdown(
        content_root=content_root,
        url=url,
        meta_description=meta_description,
        structured_text=structured_text,
        low_priority_blocks=low_priority_blocks,
        noscript_text=noscript_text,
        primary_text=primary_text,
    )
    result = {
        "url": url,
        "title": title,
        "content": _truncate_content(markdown_content or text),
        "raw_content": _truncate_content(text),
        "content_format": "html",
        "content_source_element": content_source_element,
    }
    if outline:
        result["outline"] = outline
    if meta_description:
        result["meta_description"] = meta_description
    if structured_text:
        result["structured_data"] = structured_text
    return result


def _extract_pdf(data: bytes, url: str) -> dict:
    try:
        from doc_service import _extract_text_from_pdf

        total_pages = None
        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(data)) as pdf:
                total_pages = len(pdf.pages)
        except Exception:
            total_pages = None

        text = _clean_extracted_text(_extract_text_from_pdf(data))
        result = {
            "url": url,
            "title": f"PDF: {url.rstrip('/').split('/')[-1]}",
            "content": _truncate_content(text),
            "content_format": "pdf",
        }
        if total_pages is not None:
            result["page_count"] = total_pages
            result["pages_extracted"] = total_pages
        return result
    except Exception as exc:
        return {"url": url, "title": "", "content": "", "error": f"Could not read PDF: {exc}"}


def _extract_json_text(resp, raw: bytes, url: str) -> dict:
    try:
        parsed = resp.json()
        text = json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        text = raw.decode("utf-8", errors="replace")
    return {"url": url, "title": "", "content": _truncate_content(_clean_extracted_text(text)), "content_format": "json"}


def _extract_xml_text(raw: bytes, url: str) -> dict:
    decoded = raw.decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(decoded)
    except Exception:
        text = decoded
    else:
        text_fragments = []
        for element in root.iter():
            value = (element.text or "").strip()
            if not value:
                continue
            label = re.sub(r"\s+", " ", str(element.tag or "")).strip()
            text_fragments.append(f"{label}: {value}" if label else value)
        text = "\n".join(text_fragments) or decoded
    return {"url": url, "title": "", "content": _truncate_content(_clean_extracted_text(text)), "content_format": "xml"}


def _extract_plain_text(raw: bytes, url: str, content_format: str = "text") -> dict:
    text = raw.decode("utf-8", errors="replace")
    return {
        "url": url,
        "title": "",
        "content": _truncate_content(_clean_extracted_text(text)),
        "content_format": content_format,
    }


def _build_fetch_result_from_response(resp, raw: bytes, url: str, partial_error: str | None = None) -> dict:
    ct = resp.headers.get("Content-Type", "").lower()
    final_url = resp.url

    if "pdf" in ct or url.lower().endswith(".pdf"):
        result = _extract_pdf(raw, final_url)
    elif "json" in ct:
        result = _extract_json_text(resp, raw, final_url)
    elif "xml" in ct and "html" not in ct:
        result = _extract_xml_text(raw, final_url)
    elif "text/plain" in ct:
        result = _extract_plain_text(raw, final_url)
    else:
        enc = resp.encoding or "utf-8"
        result = _extract_html(raw.decode(enc, errors="replace"), final_url)

    result["cleanup_applied"] = True
    result["status"] = resp.status_code
    if partial_error:
        result["fetch_warning"] = partial_error
        result["partial_content"] = True
    return result


def _has_useful_fetch_content(result: dict) -> bool:
    content = result.get("raw_content") or result.get("content") or ""
    return len(_clean_extracted_text(content)) >= _THIN_CONTENT_MIN_CHARS


def _append_fetch_warning(result: dict, warning: str):
    existing = (result.get("fetch_warning") or "").strip()
    if existing:
        if warning not in existing:
            result["fetch_warning"] = f"{existing}; {warning}"
        return
    result["fetch_warning"] = warning


def _should_retry_without_ssl_verification(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "certificate verify failed" in text or "sslcertverificationerror" in text


def fetch_url_tool(url: str) -> dict:
    safe, reason = _is_safe_url(url)
    if not safe:
        return {"url": url, "error": reason, "content": ""}

    cache_key = f"fetch:{hashlib.md5(url.encode()).hexdigest()}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    last_error = None
    best_result = None
    header_variants = list(_iter_fetch_header_variants(url))
    for proxy in get_proxy_candidates_for_operation(PROXY_OPERATION_FETCH_URL, include_direct_fallback=True):
        for index, headers in enumerate(header_variants):
            session = None
            try:
                session = http_requests.Session()
                session.max_redirects = FETCH_MAX_REDIRECTS
                session.trust_env = False
                proxy_map = _requests_proxy_dict(proxy)
                if proxy_map:
                    session.proxies.update(proxy_map)
                bypassed_ssl_verification = False
                try:
                    resp = session.get(
                        url,
                        timeout=FETCH_TIMEOUT,
                        headers=headers,
                        stream=True,
                        allow_redirects=True,
                    )
                except http_requests.exceptions.SSLError as exc:
                    if not _should_retry_without_ssl_verification(exc):
                        raise
                    bypassed_ssl_verification = True
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", InsecureRequestWarning)
                        resp = session.get(
                            url,
                            timeout=FETCH_TIMEOUT,
                            headers=headers,
                            stream=True,
                            allow_redirects=True,
                            verify=False,
                        )
                raw = b""
                partial_error = None
                try:
                    for chunk in resp.iter_content(chunk_size=8192):
                        raw += chunk
                        if len(raw) >= FETCH_MAX_SIZE:
                            raw = raw[:FETCH_MAX_SIZE]
                            break
                except (http_requests.exceptions.ChunkedEncodingError, http_requests.exceptions.ConnectionError) as exc:
                    if raw:
                        partial_error = f"Connection ended early; partial page content was recovered ({exc})"
                    else:
                        raise

                result = _build_fetch_result_from_response(resp, raw, url, partial_error=partial_error)
                if bypassed_ssl_verification:
                    result["ssl_verification_bypassed"] = True
                    _append_fetch_warning(
                        result,
                        "SSL certificate verification failed; retried without certificate verification",
                    )
                status_code = int(getattr(resp, "status_code", 0) or 0)
                if status_code >= 400:
                    _append_fetch_warning(result, f"HTTP {status_code} returned by origin")
                    if status_code in _FETCH_RETRYABLE_STATUS_CODES and not _has_useful_fetch_content(result):
                        best_result = best_result or result
                        last_error = f"HTTP {status_code}"
                        if index + 1 < len(header_variants):
                            continue
                        break

                if not result.get("content"):
                    best_result = best_result or result
                    if status_code >= 400:
                        last_error = last_error or f"HTTP {status_code}"
                    else:
                        last_error = last_error or "Fetched page returned no extractable content"
                    if status_code in _FETCH_RETRYABLE_STATUS_CODES and index + 1 < len(header_variants):
                        continue
                    break

                if result.get("partial_content"):
                    cache_set(cache_key, result)
                    return result

                if not _has_useful_fetch_content(result):
                    _append_fetch_warning(result, "Only limited extractable content was found on the page")
                    best_result = result
                    if result.get("content_format") == "html" and index + 1 < len(header_variants):
                        continue
                    cache_set(cache_key, result)
                    return result

                cache_set(cache_key, result)
                return result
            except http_requests.exceptions.TooManyRedirects:
                last_error = "Too many redirects"
                break
            except http_requests.exceptions.Timeout:
                last_error = "Request timed out (20s)"
                break
            except Exception as exc:
                last_error = str(exc)
                break
            finally:
                if session is not None:
                    session.close()

    if best_result is not None and best_result.get("content"):
        status_code = int(best_result.get("status", 0) or 0)
        if status_code >= 400 and not best_result.get("partial_content") and not _has_useful_fetch_content(best_result):
            return {"url": url, "error": f"HTTP {status_code}", "content": ""}
        return best_result

    return {"url": url, "error": last_error or "Could not fetch URL", "content": ""}


def search_web_tool(queries: list) -> list:
    if not queries:
        return []

    results = []
    seen_urls = set()

    for raw_query in queries[:5]:
        query = str(raw_query).strip()
        if not query:
            continue

        cache_key = f"search:{hashlib.md5(query.lower().encode()).hexdigest()}"
        cached = cache_get(cache_key)
        if cached is not None:
            for row in cached:
                if row.get("url") not in seen_urls:
                    seen_urls.add(row.get("url"))
                    results.append(row)
            continue

        try:
            hits = None
            last_error = None
            for proxy in get_proxy_candidates_for_operation(PROXY_OPERATION_SEARCH_WEB, include_direct_fallback=True):
                try:
                    with DDGS(proxy=proxy) as ddgs:
                        hits = list(ddgs.text(query, max_results=SEARCH_MAX_RESULTS))
                    break
                except Exception as exc:
                    last_error = exc
            if hits is None:
                raise last_error or RuntimeError("Search failed")
            normalized = [
                {
                    "title": hit.get("title", ""),
                    "url": hit.get("href", ""),
                    "snippet": hit.get("body", ""),
                }
                for hit in hits
            ]
            cache_set(cache_key, normalized)
            for row in normalized:
                if row["url"] not in seen_urls:
                    seen_urls.add(row["url"])
                    results.append(row)
        except Exception as exc:
            results.append({"error": str(exc), "query": query})

    return results


def search_news_ddgs_tool(queries: list, lang: str = "tr", when: str | None = None) -> list:
    if not queries:
        return []

    region = _DDGS_REGION.get(lang, "tr-tr")
    timelimit = _DDGS_TIMELIMIT.get(when) if when else None
    results = []
    seen_urls = set()

    for raw_query in queries[:5]:
        query = str(raw_query).strip()
        if not query:
            continue

        cache_key = f"news_ddgs:{hashlib.md5((query + lang + (when or '')).lower().encode()).hexdigest()}"
        cached = cache_get(cache_key)
        if cached is not None:
            for row in cached:
                if row.get("link") not in seen_urls:
                    seen_urls.add(row["link"])
                    results.append(row)
            continue

        try:
            hits = None
            last_error = None
            for proxy in get_proxy_candidates_for_operation(PROXY_OPERATION_SEARCH_NEWS_DDGS, include_direct_fallback=True):
                try:
                    with DDGS(proxy=proxy) as ddgs:
                        hits = list(
                            ddgs.news(
                                query,
                                region=region,
                                safesearch="off",
                                timelimit=timelimit,
                                max_results=SEARCH_MAX_RESULTS,
                            )
                        )
                    break
                except Exception as exc:
                    last_error = exc
            if hits is None:
                raise last_error or RuntimeError("News search failed")
            normalized = [
                {
                    "title": hit.get("title", ""),
                    "link": hit.get("url", ""),
                    "time": hit.get("date", ""),
                    "source": hit.get("source", ""),
                }
                for hit in hits
            ]
            cache_set(cache_key, normalized)
            for row in normalized:
                if row["link"] not in seen_urls:
                    seen_urls.add(row["link"])
                    results.append(row)
        except Exception as exc:
            results.append({"error": str(exc), "query": query})

    return results


def search_news_google_tool(queries: list, lang: str = "tr", when: str | None = None) -> list:
    if not queries:
        return []

    geo = _GN_LANG.get(lang, _GN_LANG["tr"])
    results = []
    seen_urls = set()

    for raw_query in queries[:5]:
        query = str(raw_query).strip()
        if not query:
            continue

        full_query = f"{query} {_GN_WHEN[when]}" if when and when in _GN_WHEN else query
        cache_key = f"news_google:{hashlib.md5((full_query + lang).lower().encode()).hexdigest()}"
        cached = cache_get(cache_key)
        if cached is not None:
            for row in cached:
                if row.get("link") not in seen_urls:
                    seen_urls.add(row["link"])
                    results.append(row)
            continue

        rss_url = (
            f"https://news.google.com/rss/search"
            f"?q={url_quote(full_query)}"
            f"&hl={geo['hl']}&gl={geo['gl']}&ceid={geo['ceid']}"
        )
        try:
            resp = None
            last_error = None
            for proxy in get_proxy_candidates_for_operation(PROXY_OPERATION_SEARCH_NEWS_GOOGLE, include_direct_fallback=True):
                try:
                    resp = http_requests.get(
                        rss_url,
                        headers=_build_browser_headers(
                            accept="application/rss+xml, application/xml, text/xml, */*;q=0.8"
                        ),
                        timeout=15,
                        proxies=_requests_proxy_dict(proxy),
                    )
                    resp.raise_for_status()
                    break
                except Exception as exc:
                    last_error = exc
                    resp = None
            if resp is None:
                raise last_error or RuntimeError("Could not fetch Google News RSS")
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")[:SEARCH_MAX_RESULTS]

            normalized = []
            for item in items:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                source = ""
                source_element = item.find("source")
                if source_element is not None:
                    source = (source_element.text or "").strip()
                if source and title.endswith(f" - {source}"):
                    title = title[: -(len(source) + 3)]
                if link:
                    normalized.append({"title": title, "link": link, "time": pub, "source": source})

            cache_set(cache_key, normalized)
            for row in normalized:
                if row["link"] not in seen_urls:
                    seen_urls.add(row["link"])
                    results.append(row)
        except Exception as exc:
            results.append({"error": str(exc), "query": raw_query})

    return results


_GREP_CONTEXT_MAX_LINES = 5
_GREP_MAX_MATCHES = 30


def _coerce_grep_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _strip_tool_memory_record_prefix(text: str) -> str:
    lines = str(text or "").splitlines()
    if not lines or not lines[0].startswith("tool:"):
        return str(text or "")

    start_index = 1
    while start_index < len(lines) and lines[start_index].startswith(("Input:", "Summary:")):
        start_index += 1

    stripped = "\n".join(lines[start_index:]).lstrip()
    return stripped or str(text or "")


def grep_fetched_content_tool(
    url: str,
    pattern: str,
    context_lines: int = 2,
    max_matches: int = 20,
    refresh_if_missing: bool = True,
) -> dict:
    """Search for a pattern in the cached content of a previously fetched URL.

    Looks up the raw page content from the fetch cache or tool memory, then
    performs a case-insensitive regex search line-by-line and returns matching
    lines with surrounding context.
    """
    url = str(url or "").strip()
    pattern = str(pattern or "").strip()
    if not url:
        return {"error": "url is required", "url": ""}
    if not pattern:
        return {"error": "pattern is required", "url": url}

    context_lines = _coerce_grep_int(context_lines, default=2, minimum=0, maximum=_GREP_CONTEXT_MAX_LINES)
    max_matches = _coerce_grep_int(max_matches, default=20, minimum=1, maximum=_GREP_MAX_MATCHES)
    refresh_if_missing = _coerce_bool(refresh_if_missing, default=True)
    searched_source = ""
    refetch_error = ""

    # 1. Try the in-process fetch cache first (fastest, same session)
    cache_key = f"fetch:{hashlib.md5(url.encode()).hexdigest()}"
    cached = cache_get(cache_key)
    if isinstance(cached, dict):
        raw_text = cached.get("raw_content") or cached.get("content") or ""
        if raw_text:
            searched_source = "fetch_cache"
    else:
        raw_text = ""

    # 2. Fall back to RAG tool memory (cross-turn, full raw_content preferred)
    if not raw_text:
        try:
            from rag_service import get_exact_tool_memory_match  # lazy import – avoids circular deps
            match = get_exact_tool_memory_match("fetch_url", url)
            if isinstance(match, dict):
                raw_text = _strip_tool_memory_record_prefix(match.get("content") or "")
                if raw_text:
                    searched_source = "tool_memory_raw"
        except Exception:
            raw_text = ""

    # 3. Re-fetch live when no raw page text is available.
    if not raw_text and refresh_if_missing:
        refreshed = fetch_url_tool(url)
        refreshed_text = _clean_extracted_text(refreshed.get("raw_content") or refreshed.get("content") or "")
        if refreshed_text and not refreshed.get("error"):
            raw_text = refreshed_text
            searched_source = "live_refetch"
        else:
            refetch_error = str(refreshed.get("error") or refreshed.get("fetch_warning") or "").strip()

    # 4. Fallback to summarized fetch tool memory when only the distilled summary exists.
    if not raw_text:
        try:
            from rag_service import get_exact_tool_memory_match, search_tool_memory  # lazy import – avoids circular deps

            summarized_match = get_exact_tool_memory_match("fetch_url_summarized", url)
            if isinstance(summarized_match, dict):
                raw_text = _strip_tool_memory_record_prefix(summarized_match.get("content") or "")
                if raw_text:
                    searched_source = "tool_memory_summary"

            if not raw_text:
                search_matches = (search_tool_memory(url, top_k=5).get("matches") or [])[:5]
                for match in search_matches:
                    source_name = str(match.get("source_name") or "").strip()
                    if not source_name.startswith("fetch_url_summarized:"):
                        continue
                    if url not in source_name:
                        continue
                    raw_text = _strip_tool_memory_record_prefix(match.get("text") or "")
                    if raw_text:
                        searched_source = "tool_memory_summary"
                        break
        except Exception:
            raw_text = ""

    if not raw_text:
        error_message = (
            "URL content not found in cache, live fetch, or tool memory. "
            "Call fetch_url for this URL first, then use grep_fetched_content."
        )
        if refetch_error:
            error_message += f" Live refetch also failed: {refetch_error}"
        return {
            "error": error_message,
            "url": url,
            "match_count": 0,
            "matches": [],
        }

    # Compile the pattern
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return {"error": f"Invalid regex pattern: {exc}", "url": url, "match_count": 0, "matches": []}

    lines = raw_text.splitlines()
    matches: list[dict] = []
    for line_index, line in enumerate(lines):
        if len(matches) >= max_matches:
            break
        if not compiled.search(line):
            continue
        before_start = max(0, line_index - context_lines)
        after_end = min(len(lines), line_index + context_lines + 1)
        matches.append(
            {
                "line_number": line_index + 1,
                "line": line,
                "context_before": lines[before_start:line_index],
                "context_after": lines[line_index + 1 : after_end],
            }
        )

    truncated = len(matches) >= max_matches and any(
        compiled.search(line) for line in lines[matches[-1]["line_number"] :]
    )
    result: dict = {
        "url": url,
        "pattern": pattern,
        "match_count": len(matches),
        "matches": matches,
        "searched_source": searched_source or "unknown",
    }
    if searched_source == "live_refetch":
        result["refetched"] = True
    if truncated:
        result["truncated"] = True
        result["note"] = f"Results limited to {max_matches} matches. Refine the pattern or increase max_matches to see more."
    if not matches:
        result["note"] = "No matches found. The pattern may not appear in the fetched content, or the content was not cached."
    if searched_source == "tool_memory_summary":
        summary_note = "Search ran against a summarized page snapshot because full raw page text was unavailable."
        existing_note = str(result.get("note") or "").strip()
        result["note"] = f"{existing_note} {summary_note}".strip() if existing_note else summary_note
    return result
