from __future__ import annotations

import copy
import json
import re

from config import CLARIFICATION_DEFAULT_MAX_QUESTIONS, CLARIFICATION_QUESTION_LIMIT_MAX, CLARIFICATION_QUESTION_LIMIT_MIN, RAG_ENABLED

CANVAS_DOCUMENT_TOOL_NAMES = {
    "expand_canvas_document",
    "scroll_canvas_document",
    "search_canvas_document",
    "rewrite_canvas_document",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
    "delete_canvas_document",
    "clear_canvas",
}

WEB_SEARCH_TOOL_NAMES = {
    "search_web",
    "fetch_url",
    "search_news_ddgs",
    "search_news_google",
}

NEWS_TOOL_NAMES = {
    "search_news_ddgs",
    "search_news_google",
}

WORKSPACE_TOOL_NAMES = {
    "create_directory",
    "create_file",
    "update_file",
    "read_file",
    "list_dir",
    "search_files",
    "write_project_tree",
    "validate_project_workspace",
}

FILE_REFERENCE_RE = re.compile(
    r"\b[\w./-]+\.(?:py|js|ts|tsx|jsx|json|md|txt|html|css|scss|yaml|yml|toml|ini|cfg|sh|sql|csv)\b",
    re.IGNORECASE,
)
URL_REFERENCE_RE = re.compile(r"https?://|www\.", re.IGNORECASE)

WORKSPACE_INTENT_HINTS = (
    "code",
    "repo",
    "repository",
    "project",
    "workspace",
    "file",
    "files",
    "folder",
    "directory",
    "path",
    "implement",
    "implementation",
    "fix",
    "debug",
    "refactor",
    "edit",
    "update",
    "create",
    "write",
    "read",
    "test",
    "tests",
    "module",
    "class",
    "function",
    "bug",
    "patch",
    "readme",
    "stacktrace",
    "kod",
    "repo",
    "proje",
    "dosya",
    "dosyalar",
    "klas",
    "dizin",
    "yol",
    "uygula",
    "incele",
    "duzelt",
    "düzelt",
    "duzenle",
    "düzenle",
    "guncelle",
    "güncelle",
    "olustur",
    "oluştur",
    "yaz",
    "oku",
    "test",
    "fonksiyon",
    "sinif",
    "sınıf",
    "modul",
    "modül",
)

WEB_INTENT_HINTS = (
    "http://",
    "https://",
    "www.",
    "web",
    "internet",
    "browser",
    "site",
    "website",
    "url",
    "link",
    "search web",
    "search the web",
    "browse",
    "google",
    "bing",
    "duckduckgo",
    "ddg",
    "webde",
    "internette",
)

NEWS_INTENT_HINTS = (
    "news",
    "headline",
    "headlines",
    "latest",
    "current events",
    "today",
    "breaking",
    "guncel",
    "güncel",
    "haber",
    "son durum",
    "son haber",
)

CANVAS_CREATION_INTENT_HINTS = (
    "canvas",
    "draft",
    "artifact",
    "document",
    "doc",
    "outline",
    "report",
    "spec",
    "notes",
    "taslak",
    "dokuman",
    "doküman",
    "belge",
    "rapor",
    "not",
)


def _normalize_intent_text(text: str | None) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _contains_intent_hint(text: str, hints: tuple[str, ...]) -> bool:
    tokens = set(re.findall(r"[a-z0-9_]+", text))
    for hint in hints:
        normalized_hint = str(hint or "").strip().lower()
        if not normalized_hint:
            continue
        if " " in normalized_hint or "://" in normalized_hint or "." in normalized_hint or "/" in normalized_hint:
            if normalized_hint in text:
                return True
            continue
        if normalized_hint in tokens:
            return True
        if len(normalized_hint) >= 5 and any(token.startswith(normalized_hint) for token in tokens):
            return True
    return False


def _should_enable_workspace_tools(
    normalized_text: str,
    *,
    workspace_root: str | None = None,
    has_canvas_documents: bool = False,
) -> bool:
    if has_canvas_documents:
        return True
    if not workspace_root:
        return False
    if not normalized_text:
        return False
    if FILE_REFERENCE_RE.search(normalized_text):
        return True
    if "/" in normalized_text or "\\" in normalized_text:
        return True
    return _contains_intent_hint(normalized_text, WORKSPACE_INTENT_HINTS)


def _should_enable_web_tools(normalized_text: str) -> bool:
    if not normalized_text:
        return False
    if URL_REFERENCE_RE.search(normalized_text):
        return True
    return _contains_intent_hint(normalized_text, WEB_INTENT_HINTS)


def _should_enable_news_tools(normalized_text: str) -> bool:
    if not normalized_text:
        return False
    return _contains_intent_hint(normalized_text, NEWS_INTENT_HINTS)


def _should_enable_canvas_creation(normalized_text: str, *, has_canvas_documents: bool = False) -> bool:
    if has_canvas_documents:
        return True
    if not normalized_text:
        return False
    return _contains_intent_hint(normalized_text, CANVAS_CREATION_INTENT_HINTS)


def build_canvas_decision_matrix(
    active_tool_names: list[str] | None = None,
    *,
    has_canvas_documents: bool = False,
    canvas_mode: str | None = None,
) -> list[dict[str, str]]:
    active_set = set(active_tool_names or [])

    def enabled(*tool_names: str) -> bool:
        if not active_set:
            return True
        return any(tool_name in active_set for tool_name in tool_names)

    rows: list[dict[str, str]] = []
    if enabled("create_canvas_document"):
        rows.append(
            {
                "situation": (
                    "No canvas document exists yet and the user wants a draft, file, or editable artifact."
                    if not has_canvas_documents
                    else "You need a brand-new file, draft, or artifact."
                ),
                "tool": "create_canvas_document",
                "notes": "Create one file per document. For source code, use format='code'. Prefer line edits for later partial changes.",
            }
        )
    if enabled("rewrite_canvas_document"):
        rows.append(
            {
                "situation": "Most or all of the document should change and you already know the intended final content.",
                "tool": "rewrite_canvas_document",
                "notes": "Use this for near-full replacement. For targeted changes, use line-level tools instead.",
            }
        )
    if enabled("replace_canvas_lines", "insert_canvas_lines", "delete_canvas_lines"):
        rows.append(
            {
                "situation": "Only a localized region should change and the exact visible 1-based lines are known.",
                "tool": "replace_canvas_lines / insert_canvas_lines / delete_canvas_lines",
                "notes": "Use only visible or recently inspected lines. Never guess hidden line numbers.",
            }
        )
    if enabled("scroll_canvas_document"):
        rows.append(
            {
                "situation": "You need a specific hidden range outside the visible excerpt.",
                "tool": "scroll_canvas_document",
                "notes": "Read the smallest relevant hidden window before editing.",
            }
        )
    if enabled("search_canvas_document"):
        rows.append(
            {
                "situation": "You need to locate text, symbols, or a pattern inside a large canvas before deciding what to inspect or edit.",
                "tool": "search_canvas_document",
                "notes": "Use this before scrolling or expanding when you are still trying to find the right region.",
            }
        )
    if enabled("expand_canvas_document"):
        rows.append(
            {
                "situation": "You need a wider full-file view before reasoning or editing.",
                "tool": "expand_canvas_document",
                "notes": "Use this when the excerpt or targeted scroll is still insufficient.",
            }
        )
    if canvas_mode == "project" and rows:
        rows.append(
            {
                "situation": "Project mode targeting and file identity.",
                "tool": "Prefer document_path",
                "notes": "Use document_path over document_id when possible.",
            }
        )
    return rows

TOOL_SPECS = [
    {
        "name": "append_scratchpad",
        "description": (
            "Append one or more durable user-specific facts or preferences to the persistent scratchpad. "
            "Use this only for long-lived, high-signal information that will likely change future answers or actions. "
            "Do not store temporary task details, sensitive secrets, one-off requests, or speculative inferences."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "notes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of short durable facts to append. Each item must be a single standalone fact — do not bundle multiple facts into one item. Minimum 1 item.",
                    "minItems": 1,
                }
            },
            "required": ["notes"],
        },
        "prompt": {
            "purpose": "Saves one or more short durable user facts or preferences into persistent scratchpad memory only when they are likely to matter later.",
            "inputs": {"notes": "list of single short durable memory lines — one fact per item"},
            "guidance": (
                "Use very sparingly. Save only durable user-specific facts, recurring constraints, or stable preferences that are likely to matter in future conversations. "
                "Do not save temporary requests, current-task details, large summaries, tool outputs, web/search results, speculative guesses, or sensitive data. "
                "If the information would not change future responses or behavior, do not store it. "
                "Each item in `notes` must be a single short standalone fact. Never combine multiple facts into one item."
            ),
        },
    },
    {
        "name": "replace_scratchpad",
        "description": (
            "Completely replace the persistent scratchpad content. "
            "Use this to rewrite, reorganize, or remove outdated durable user-specific facts. "
            "Do not store temporary task details or speculative inferences."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "new_content": {
                    "type": "string",
                    "description": "The new content that will fully replace the existing scratchpad.",
                }
            },
            "required": ["new_content"],
        },
        "prompt": {
            "purpose": "Completely rewrites the persistent scratchpad memory.",
            "inputs": {"new_content": "the new complete scratchpad content"},
            "guidance": (
                "Use carefully to prune or reorganize existing facts. Ensure you do not accidentally delete important existing preferences. "
                "Keep the final text compact and only include durable, high-signal facts. Prefer a short bulleted list over paragraphs."
            ),
        },
    },
    {
        "name": "ask_clarifying_question",
        "description": (
            "Ask the user one or more structured clarification questions and stop answering until they reply. "
            "Use this when key requirements are missing, ambiguous, or mutually dependent and you should not guess. "
            "If the user explicitly asks you to ask questions first before answering, use this tool instead of asking inline."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "intro": {
                    "type": "string",
                    "description": "Short lead-in shown before the questions."
                },
                "questions": {
                    "type": "array",
                    "description": "List of clarification questions.",
                    "minItems": 1,
                    "maxItems": CLARIFICATION_QUESTION_LIMIT_MAX,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Stable identifier for mapping the answer later."
                            },
                            "label": {
                                "type": "string",
                                "description": "The question shown to the user."
                            },
                            "input_type": {
                                "type": "string",
                                "enum": ["text", "single_select", "multi_select"],
                                "description": "How the user should answer this question."
                            },
                            "required": {
                                "type": "boolean",
                                "description": "Whether the user must answer this question."
                            },
                            "placeholder": {
                                "type": "string",
                                "description": "Optional placeholder for free-text answers."
                            },
                            "options": {
                                "type": "array",
                                "description": "Selectable options for single_select or multi_select questions.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "value": {"type": "string"},
                                        "description": {"type": "string"}
                                    },
                                    "required": ["label", "value"]
                                }
                            },
                            "allow_free_text": {
                                "type": "boolean",
                                "description": "Whether the user may add custom text alongside the predefined options."
                            }
                        },
                        "required": ["id", "label", "input_type"]
                    }
                },
                "submit_label": {
                    "type": "string",
                    "description": "Optional button label shown in the UI."
                }
            },
            "required": ["questions"],
        },
        "prompt": {
            "purpose": "Collects missing user requirements before continuing the answer.",
            "inputs": {
                "intro": "optional short lead-in",
                "questions": "structured questions",
                "submit_label": "optional button label"
            },
            "guidance": (
                "Use this instead of guessing when important requirements are missing. "
                "Ask only the smallest set of questions needed to continue. "
                "When the user asks you to ask questions first, this is the required tool. "
                "Put the actual question text only in the tool arguments, not in the assistant text. "
                "Keep the assistant-visible reply short and brief, and let the UI render the questions. "
                "When you call this tool, it must be the only tool call in that assistant message and you must wait for the user's reply before answering. "
                "Prefer single_select or multi_select when the likely answers are known, keep question ids short and unique, and use required=false for optional follow-ups. "
                "Each questions item must be an object with id, label, and input_type; example: {\"id\":\"scope\",\"label\":\"Which scope?\",\"input_type\":\"text\"}."
            ),
        },
    },
    {
        "name": "sub_agent",
        "description": (
            "Delegate a bounded research or inspection task to a helper sub-agent that can use only read-only tools. "
            "Use it proactively when the task is genuinely multi-step, multi-tool, or context-heavy and would otherwise force a long inline tool chain — such as broad repo/web analysis, cross-file synthesis, or evidence gathering that needs a compact summary. "
            "Avoid it only when you can answer directly or with a single tool call; otherwise, prefer delegation over stretching the parent agent context. "
            "Do not use it for file mutations, user clarification, or recursive delegation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The delegated task for the helper agent. Rewrite the user's request into clear English instructions unless the task is explicitly language-specific.",
                },
                "allowed_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional exact tool-name allowlist to narrow the helper's read-only tool set further.",
                    "minItems": 1,
                    "maxItems": 12,
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Maximum helper-agent tool steps (1-8).",
                    "minimum": 1,
                    "maximum": 8,
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Total soft timeout budget for the helper-agent run across fallback attempts in seconds (5-900).",
                    "minimum": 5,
                    "maximum": 900,
                },
            },
            "required": ["task"],
        },
        "prompt": {
            "purpose": "Delegates a scoped research or inspection task to a bounded helper agent and returns a compact summary with artifacts.",
            "inputs": {
                "task": "the delegated task and desired output",
                "allowed_tools": "optional tool-name allowlist",
                "max_steps": "optional helper-agent tool budget",
                "timeout_seconds": "optional soft timeout",
            },
            "guidance": (
                "Use this when the investigation genuinely benefits from a separate bounded pass and would otherwise require several tool steps or repeated context stitching in the parent agent. "
                "Do not let the token cost warning block delegation when the task is complex; the sub-agent exists for exactly those multi-tool cases. "
                "Give the helper a concrete task, expected deliverable, and any important constraints. "
                "Before calling this tool, rewrite the delegated task into concise English instructions for the helper, even if the user spoke Turkish or another language. "
                "Use the user's original language only when the delegated task itself depends on that language, and otherwise expect the helper to work in English by default. "
                "Keep it scoped: prefer one helper call over many, and do not delegate writes, clarifications, or recursive agent orchestration. "
                "If the helper uses web search, each search_web/search_news call must stay within the 1-5 query limit; split larger batches into separate calls."
            ),
        },
    },
    {
        "name": "image_explain",
        "description": (
            "Answer a follow-up question about a previously uploaded image saved in the current conversation. "
            "Use this when the user refers back to an earlier image or screenshot and the stored visual context may matter."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_id": {
                    "type": "string",
                    "description": "The globally unique stored image_id for the referenced uploaded image.",
                },
                "conversation_id": {
                    "type": "integer",
                    "description": "The current conversation id used to verify that the image belongs to this chat.",
                },
                "question": {
                    "type": "string",
                    "description": "A focused follow-up question about the image. Write this question in English.",
                },
            },
            "required": ["image_id", "conversation_id", "question"],
        },
        "prompt": {
            "purpose": "Asks the vision model a new question about a stored image from this conversation.",
            "inputs": {
                "image_id": "stored image id",
                "conversation_id": "current conversation id",
                "question": "follow-up question written in English",
            },
            "guidance": (
                "Use this when the user asks about a previously uploaded image instead of relying only on the cached summary. "
                "Always send the question in English. The tool response will be in English. "
                "If the referenced image is ambiguous, ask the user to clarify which image they mean before calling the tool."
            ),
        },
    },
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the internal knowledge base indexed with RAG. "
            "Use this when the answer may exist in synced conversation history or stored tool outputs and you cannot answer reliably from the current context. "
            "Optionally filter by category. Avoid repeating semantically overlapping searches when one good result set already answers the question; unnecessary searches waste tokens."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Semantic search query for the knowledge base.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter: conversation or tool_result.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of chunks to retrieve (1-12).",
                    "minimum": 1,
                    "maximum": 12,
                },
            },
            "required": ["query"],
        },
        "prompt": {
            "purpose": "Searches the internal RAG knowledge base built from files, URLs, notes, and conversations.",
            "inputs": {"query": "semantic search query", "category": "optional category", "top_k": "1-12 results"},
            "guidance": "Use at most a few focused searches and synthesize from returned chunks instead of retrying near-duplicate queries. If the current context is already sufficient, do not search again; unnecessary searches waste tokens.",
        },
    },
    {
        "name": "search_tool_memory",
        "description": (
            "Search past web tool results stored from previous conversations. "
            "Use this before making a new web request when you suspect the topic was already researched and the current context is not enough. "
            "This searches remembered results from fetch_url, search_web, and news tools; unnecessary lookups waste tokens."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Semantic search query for past web tool results.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of remembered results to retrieve (1-10).",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        },
        "prompt": {
            "purpose": "Searches memory of past web searches, URL fetches, and news lookups.",
            "inputs": {"query": "semantic search query", "top_k": "1-10 results"},
            "guidance": (
                "Use before making a new web request if similar research may already exist and you cannot answer from the current context. "
                "If high-similarity results already answer the question, reuse them instead of repeating the search. Unnecessary lookups waste tokens."
            ),
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the web using DuckDuckGo. Use this to find current information, facts, prices, news, or any topic requiring up-to-date data. "
            "Provide one or more search queries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of search queries to run (1–5 queries).",
                    "minItems": 1,
                    "maxItems": 5,
                }
            },
            "required": ["queries"],
        },
        "prompt": {
            "purpose": "Runs a general web search and returns recent results.",
            "inputs": {"queries": "1-5 search queries"},
            "guidance": "Never pass more than 5 queries in a single call. If you need more search terms, split them across multiple search_web calls.",
        },
    },
    {
        "name": "fetch_url",
        "description": (
            "Fetch and read the content of a specific web page. Returns cleaned text and metadata. "
            "Use after search_web to read the full content of a relevant page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL of the page (must start with http:// or https://).",
                }
            },
            "required": ["url"],
        },
        "prompt": {
            "purpose": "Reads the cleaned content of a specific URL.",
            "inputs": {"url": "full http/https URL"},
        },
    },
    {
        "name": "search_news_ddgs",
        "description": (
            "Search recent news articles using DuckDuckGo News. Returns title, link, publication time and source for each article. "
            "Use this for general news, trending topics or when a broad news index is appropriate. "
            "Optionally filter by time range and language. If you need the full article text, follow up with fetch_url on the returned links."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of news search queries (1–5).",
                    "minItems": 1,
                    "maxItems": 5,
                },
                "lang": {
                    "type": "string",
                    "enum": ["tr", "en"],
                    "description": "Search language/region. 'tr' for Turkish results, 'en' for English.",
                },
                "when": {
                    "type": "string",
                    "enum": ["d", "w", "m", "y"],
                    "description": "Optional time filter: 'd'=last day, 'w'=last week, 'm'=last month, 'y'=last year.",
                },
            },
            "required": ["queries"],
        },
        "prompt": {
            "purpose": "Searches news headlines/links/dates/sources with DuckDuckGo News.",
            "inputs": {"queries": "1-5 news queries", "lang": "tr|en", "when": "d|w|m|y"},
        },
    },
    {
        "name": "search_news_google",
        "description": (
            "Search Google News via RSS feed. Returns title, link, publication time and source for each article. "
            "Use this when Google News coverage is preferred (e.g. Turkish financial news, local outlets, or when DuckDuckGo News yields poor results). "
            "Optionally filter by time range and language. If you need the full article text, follow up with fetch_url on the returned links."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of news search queries (1–5).",
                    "minItems": 1,
                    "maxItems": 5,
                },
                "lang": {
                    "type": "string",
                    "enum": ["tr", "en"],
                    "description": "Search language/region. 'tr' for Turkish results, 'en' for English.",
                },
                "when": {
                    "type": "string",
                    "enum": ["d", "w", "m", "y"],
                    "description": "Optional time filter: 'd'=last day, 'w'=last week, 'm'=last month, 'y'=last year.",
                },
            },
            "required": ["queries"],
        },
        "prompt": {
            "purpose": "Searches news headlines/links/dates/sources with Google News RSS.",
            "inputs": {"queries": "1-5 news queries", "lang": "tr|en", "when": "d|w|m|y"},
        },
    },
    {
        "name": "expand_canvas_document",
        "description": (
            "Load one canvas document beyond the active excerpt when you need more context. "
            "Use this before broader reasoning or editing; document_id is optional."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "Optional target canvas document id."
                },
                "document_path": {
                    "type": "string",
                    "description": "Optional target project-relative path. Prefer this in project mode."
                }
            }
        },
        "prompt": {
            "purpose": "Expands one canvas document into full line-numbered context for focused reasoning or editing.",
            "inputs": {"document_id": "optional target id", "document_path": "optional target project-relative path"},
            "guidance": (
                "Use this when the manifest and active-document excerpt are insufficient and you need another canvas file in full detail. "
                "After expanding, prefer the smallest valid edit that solves the request. "
                "If you do not know the document_id, use document_path from the workspace summary or manifest instead of getting stuck. "
                "In project mode, prefer document_path over document_id so file targeting stays stable."
            ),
        },
    },
    {
        "name": "scroll_canvas_document",
        "description": (
            "Read a targeted line range when you need lines outside the visible excerpt. "
            "Use this before line-level edits when the target region is not visible yet; document_id is optional."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "Optional target canvas document id."
                },
                "document_path": {
                    "type": "string",
                    "description": "Optional target project-relative path. Prefer this in project mode."
                },
                "start_line": {
                    "type": "integer",
                    "description": "1-based starting line number to read."
                },
                "end_line": {
                    "type": "integer",
                    "description": "1-based ending line number to read."
                }
            },
            "required": ["start_line", "end_line"]
        },
        "prompt": {
            "purpose": "Reads a focused line window from one canvas document without loading the entire file into the prompt.",
            "inputs": {
                "document_id": "optional target id",
                "document_path": "optional target project-relative path",
                "start_line": "1-based starting line",
                "end_line": "1-based ending line"
            },
            "guidance": (
                "Use this when you know which region you need and the active excerpt is truncated. "
                "After inspecting the right window, prefer line-level edit tools for localized changes instead of rewriting the whole file. "
                "If you do not know the document_id, use document_path from the workspace summary or manifest instead of stopping to search for the id. "
                "In project mode, prefer document_path over document_id so file targeting stays stable."
            ),
        },
    },
    {
        "name": "search_canvas_document",
        "description": (
            "Search the active canvas document, or all open canvas documents, for literal text or a regex pattern. "
            "Use this before scroll_canvas_document or expand_canvas_document when you first need to locate the relevant region."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Literal text or regex pattern to search for."
                },
                "document_id": {
                    "type": "string",
                    "description": "Optional target canvas document id. Defaults to the active document when all_documents is false."
                },
                "document_path": {
                    "type": "string",
                    "description": "Optional target project-relative path. Prefer this in project mode."
                },
                "all_documents": {
                    "type": "boolean",
                    "description": "Search across all open canvas documents instead of only the active or explicitly targeted one."
                },
                "is_regex": {
                    "type": "boolean",
                    "description": "Treat query as a regex pattern instead of plain text."
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether the search should be case-sensitive."
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "description": "Maximum number of matches to return. Defaults to 10."
                }
            },
            "required": ["query"]
        },
        "prompt": {
            "purpose": "Finds where text or patterns appear inside canvas documents without loading more lines than necessary.",
            "inputs": {
                "query": "literal text or regex pattern",
                "document_id": "optional target id",
                "document_path": "optional target project-relative path",
                "all_documents": "optional boolean to search all open canvas documents",
                "is_regex": "optional boolean",
                "case_sensitive": "optional boolean",
                "max_results": "optional result limit"
            },
            "guidance": (
                "Use this first when the user asks you to find something inside a large canvas or when you do not yet know which lines matter. "
                "After locating the right lines, use scroll_canvas_document for the smallest relevant window or expand_canvas_document for a wider view. "
                "In project mode, prefer document_path over document_id when you know the file path."
            ),
        },
    },
    {
        "name": "create_directory",
        "description": "Create a directory inside the conversation workspace sandbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative directory path to create."
                }
            },
            "required": ["path"]
        },
        "prompt": {
            "purpose": "Creates one or more directories inside the workspace sandbox.",
            "inputs": {"path": "workspace-relative directory path"},
            "guidance": "Use only workspace-relative paths. The sandbox rejects paths outside the conversation workspace.",
        },
    },
    {
        "name": "create_file",
        "description": "Create a new UTF-8 text file inside the conversation workspace sandbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative file path to create."
                },
                "content": {
                    "type": "string",
                    "description": "Full text content for the new file."
                }
            },
            "required": ["path", "content"]
        },
        "prompt": {
            "purpose": "Creates a new file in the workspace sandbox.",
            "inputs": {"path": "workspace-relative file path", "content": "full file content"},
            "guidance": "Fails if the file already exists. Use update_file for existing files.",
        },
    },
    {
        "name": "update_file",
        "description": "Replace the full content of an existing UTF-8 text file inside the workspace sandbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative file path to update."
                },
                "content": {
                    "type": "string",
                    "description": "Full replacement text content."
                }
            },
            "required": ["path", "content"]
        },
        "prompt": {
            "purpose": "Updates an existing file in the workspace sandbox.",
            "inputs": {"path": "workspace-relative file path", "content": "full replacement content"},
            "guidance": "Use this only for files that already exist.",
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the conversation workspace sandbox with optional line limits.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative file path to read."
                },
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional first line to include. Defaults to 1."
                },
                "end_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional last line to include."
                }
            },
            "required": ["path"]
        },
        "prompt": {
            "purpose": "Reads a file from the workspace sandbox.",
            "inputs": {"path": "workspace-relative file path", "start_line": "optional first line", "end_line": "optional last line"},
        },
    },
    {
        "name": "list_dir",
        "description": "List files and directories inside the conversation workspace sandbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Optional workspace-relative directory path. Defaults to the workspace root."
                }
            }
        },
        "prompt": {
            "purpose": "Lists workspace files and directories.",
            "inputs": {"path": "optional workspace-relative directory path"},
        },
    },
    {
        "name": "search_files",
        "description": "Search workspace file paths and optionally file contents inside the conversation sandbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Case-insensitive search text."
                },
                "path_prefix": {
                    "type": "string",
                    "description": "Optional workspace-relative directory to search under."
                },
                "search_content": {
                    "type": "boolean",
                    "description": "Whether to search inside file contents in addition to file paths."
                }
            },
            "required": ["query"]
        },
        "prompt": {
            "purpose": "Searches file paths or contents inside the workspace sandbox.",
            "inputs": {"query": "case-insensitive search text", "path_prefix": "optional subdirectory", "search_content": "optional boolean"},
        },
    },
    {
        "name": "write_project_tree",
        "description": "Create or overwrite many directories and files inside the workspace sandbox in one operation.",
        "parameters": {
            "type": "object",
            "properties": {
                "directories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Workspace-relative directories to create."
                },
                "files": {
                    "type": "array",
                    "description": "Files to write with path and content.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"}
                        },
                        "required": ["path", "content"]
                    }
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Set true only after the user approves overwriting existing files."
                }
            }
        },
        "prompt": {
            "purpose": "Writes a batch of project directories and files into the workspace sandbox.",
            "inputs": {"directories": "optional directories", "files": "optional file entries", "confirm": "optional overwrite confirmation"},
            "guidance": "If the tool reports needs_confirmation, review the returned diffs with the user and do not re-run with confirm=true until the overwrite set is approved.",
        },
    },
    {
        "name": "validate_project_workspace",
        "description": "Run lightweight validation checks against the workspace sandbox or one project subdirectory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Optional workspace-relative directory path. Defaults to the workspace root."
                }
            }
        },
        "prompt": {
            "purpose": "Validates project files in the workspace sandbox.",
            "inputs": {"path": "optional workspace-relative directory path"},
        },
    },
    {
        "name": "create_canvas_document",
        "description": (
            "Create a canvas document for the current conversation. "
            "Use one document per file or editable artifact."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Document title shown in the canvas panel."
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Full document content. "
                        "For format='code' documents this is raw source code without any markdown wrapper — no triple-backtick fences. "
                        "For format='markdown' documents this is the markdown body."
                    )
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "code"],
                    "description": "Canvas document format. Use code for a raw code document without markdown wrappers."
                },
                "language": {
                    "type": "string",
                    "description": "Optional dominant code language for the document, such as python, javascript, or sql."
                },
                "path": {
                    "type": "string",
                    "description": "Optional project-relative path such as src/app.py, README.md, or tests/test_app.py."
                },
                "role": {
                    "type": "string",
                    "enum": ["source", "config", "dependency", "docs", "test", "script", "note"],
                    "description": "Optional semantic role for the document inside a project workspace."
                },
                "summary": {
                    "type": "string",
                    "description": "Optional short semantic summary of the document's responsibility."
                },
                "imports": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional imported modules, files, or config keys referenced by this document."
                },
                "exports": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional exported entry points, functions, classes, or files produced by this document."
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional important symbols defined in this document."
                },
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional package or file dependencies associated with this document."
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional stable project identifier grouping related canvas documents."
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional stable workspace identifier grouping related canvas documents."
                }
            },
            "required": ["title", "content"]
        },
        "prompt": {
            "purpose": "Creates an editable canvas document attached to the conversation, optionally as part of a project workspace.",
            "inputs": {
                "title": "document title",
                "content": "full document body (raw source code for code format; markdown body for markdown format — no fences around code)",
                "format": "markdown or code — set code for source files, scripts, configs, and any file with a code extension",
                "language": "dominant code language e.g. python, cpp, javascript, bash, sql; auto-inferred from path extension if omitted",
                "path": "optional project-relative file path e.g. src/app.py, sketch.ino, config.yaml",
                "role": "optional semantic document role",
                "summary": "optional short responsibility summary",
                "imports": "optional referenced modules, files, or config keys",
                "exports": "optional exported entry points or files",
                "symbols": "optional key symbols defined in the document",
                "dependencies": "optional package or file dependencies",
                "project_id": "optional project identifier",
                "workspace_id": "optional workspace identifier"
            },
            "guidance": (
                "For source code files, always set format='code' and language so the document renders with syntax highlighting. "
                "If path is provided (e.g. sketch.ino, src/main.py), format and language are inferred automatically — you can omit them. "
                "The content field must contain raw code — do NOT wrap it in triple-backtick fences. "
                "Prefer creating the document before line-level edits. "
                "Keep one file or artifact per canvas document instead of bundling multiple files together. "
                "Once the document exists, prefer localized line edits for partial changes. "
                "In project mode, set path, role, and ideally summary so the workspace manifest stays coherent."
            ),
        },
    },
    {
        "name": "rewrite_canvas_document",
        "description": "Rewrite one existing canvas document in full while keeping the same document id. Use this for near-full replacement, not small localized edits.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "The full replacement content. "
                        "For code documents this is raw source code without any markdown wrapper — no triple-backtick fences. "
                        "For markdown documents this is the markdown body."
                    )
                },
                "title": {
                    "type": "string",
                    "description": "Optional replacement title."
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "code"],
                    "description": "Optional replacement format for the document."
                },
                "language": {
                    "type": "string",
                    "description": "Optional dominant code language for the updated document."
                },
                "path": {
                    "type": "string",
                    "description": "Optional replacement project-relative path for the document."
                },
                "role": {
                    "type": "string",
                    "enum": ["source", "config", "dependency", "docs", "test", "script", "note"],
                    "description": "Optional replacement semantic role for the document."
                },
                "summary": {
                    "type": "string",
                    "description": "Optional replacement short semantic summary."
                },
                "imports": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional replacement import list."
                },
                "exports": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional replacement export list."
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional replacement symbol list."
                },
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional replacement dependency list."
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional replacement project identifier."
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional replacement workspace identifier."
                },
                "document_id": {
                    "type": "string",
                    "description": "Optional target canvas document id. Defaults to the active document."
                },
                "document_path": {
                    "type": "string",
                    "description": "Optional target project-relative path. Prefer this over document_id in project mode."
                }
            },
            "required": ["content"]
        },
        "prompt": {
            "purpose": "Replaces the full content of an existing canvas document.",
            "inputs": {"content": "full document body", "title": "optional title", "format": "optional markdown or code", "language": "optional dominant code language", "path": "optional project-relative file path", "role": "optional semantic role", "summary": "optional short responsibility summary", "imports": "optional import list", "exports": "optional export list", "symbols": "optional symbol list", "dependencies": "optional dependency list", "project_id": "optional project identifier", "workspace_id": "optional workspace identifier", "document_id": "optional target id", "document_path": "optional target project-relative path"},
            "guidance": (
                "Use this for full-document replacement once you know the intended final content. "
                "Do not default to this when only part of the file needs to change; use replace_canvas_lines, insert_canvas_lines, or delete_canvas_lines for targeted edits. "
                "If you do not know the document_id, use document_path from the workspace summary or manifest. "
                "In project mode prefer document_path when possible. "
                "If the user needs an additional file, create a separate canvas document instead of rewriting the current one into a different file."
            ),
        },
    },
    {
        "name": "replace_canvas_lines",
        "description": "Replace a 1-based inclusive visible line range inside the active canvas document.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_line": {"type": "integer", "minimum": 1, "description": "1-based first line to replace."},
                "end_line": {"type": "integer", "minimum": 1, "description": "1-based last line to replace."},
                "lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Replacement lines. Each element is one line of text as a properly quoted JSON string — "
                        "no trailing newline characters. Code content (including quotes, backslashes, semicolons) "
                        "must appear INSIDE these strings, properly escaped. "
                        'Example: ["const char* ssid = \\"MyNet\\";", "const char* pass = \\"abc\\";"]. '
                        "Never place code outside this array or as an argument key."
                    )
                },
                "document_id": {
                    "type": "string",
                    "description": "Optional target canvas document id. Defaults to the active document."
                },
                "document_path": {
                    "type": "string",
                    "description": "Optional target project-relative path. Prefer this over document_id in project mode."
                }
            },
            "required": ["start_line", "end_line", "lines"]
        },
        "prompt": {
            "purpose": "Replaces specific lines in the canvas document.",
            "inputs": {"start_line": "first line", "end_line": "last line", "lines": "replacement lines as JSON string array", "document_id": "optional target id", "document_path": "optional target project-relative path"},
            "guidance": (
                "Use only when the exact 1-based line range is known from the visible excerpt or a recent scroll/expand result. "
                "Put ALL code content inside the lines array as properly escaped JSON strings. "
                'Example: {"start_line": 3, "end_line": 5, "lines": ["  int x = 1;", "  return x;"]}. '
                "Multiple localized replace_canvas_lines calls are fine when the changes are separated. "
                "If you do not know the document_id, use document_path from the workspace summary or manifest. "
                "For broad rewrites, prefer rewrite_canvas_document. In project mode, prefer document_path when possible."
            ),
        },
    },
    {
        "name": "insert_canvas_lines",
        "description": "Insert one or more lines into the active canvas document after a given visible line number.",
        "parameters": {
            "type": "object",
            "properties": {
                "after_line": {"type": "integer", "minimum": 0, "description": "Insert after this 1-based line. Use 0 to insert at the top."},
                "lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "New lines to insert. Each element is one line of text as a properly quoted JSON string — "
                        "no trailing newline characters. Code content must appear INSIDE these strings, properly escaped. "
                        "Never place code outside this array or as an argument key."
                    )
                },
                "document_id": {
                    "type": "string",
                    "description": "Optional target canvas document id. Defaults to the active document."
                },
                "document_path": {
                    "type": "string",
                    "description": "Optional target project-relative path. Prefer this over document_id in project mode."
                }
            },
            "required": ["after_line", "lines"]
        },
        "prompt": {
            "purpose": "Inserts lines into the canvas document.",
            "inputs": {"after_line": "insertion point", "lines": "new lines", "document_id": "optional target id", "document_path": "optional target project-relative path"},
            "guidance": (
                "Use only when the insertion point is known from the visible excerpt or a recent scroll/expand result. "
                "Use this for partial additions instead of rewriting the whole document when the rest should stay intact. "
                "If the target region is not visible, inspect it first. In project mode, prefer document_path when possible."
            ),
        },
    },
    {
        "name": "delete_canvas_lines",
        "description": "Delete a 1-based inclusive visible line range from the active canvas document.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_line": {"type": "integer", "minimum": 1, "description": "1-based first line to delete."},
                "end_line": {"type": "integer", "minimum": 1, "description": "1-based last line to delete."},
                "document_id": {
                    "type": "string",
                    "description": "Optional target canvas document id. Defaults to the active document."
                },
                "document_path": {
                    "type": "string",
                    "description": "Optional target project-relative path. Prefer this over document_id in project mode."
                }
            },
            "required": ["start_line", "end_line"]
        },
        "prompt": {
            "purpose": "Deletes specific lines from the canvas document.",
            "inputs": {"start_line": "first line", "end_line": "last line", "document_id": "optional target id", "document_path": "optional target project-relative path"},
            "guidance": (
                "Use only when the exact 1-based line range is visible in the current excerpt or in a recent scroll/expand result. "
                "Use this for partial removals instead of rewriting the whole document when the rest should stay intact. "
                "If the target region is not visible, inspect it first. In project mode, prefer document_path when possible."
            ),
        },
    },
    {
        "name": "delete_canvas_document",
        "description": "Delete a canvas document. Defaults to the active document when document_id is omitted.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "Optional target canvas document id. Defaults to the active document."
                },
                "document_path": {
                    "type": "string",
                    "description": "Optional target project-relative path. Prefer this over document_id in project mode."
                }
            }
        },
        "prompt": {
            "purpose": "Deletes one canvas document from the current conversation.",
            "inputs": {"document_id": "optional target id", "document_path": "optional target project-relative path"},
        },
    },
    {
        "name": "clear_canvas",
        "description": "Delete all canvas documents for the current conversation.",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "prompt": {
            "purpose": "Clears all canvas documents from the current conversation.",
            "inputs": {},
        },
    },
]

TOOL_SPEC_BY_NAME = {tool["name"]: tool for tool in TOOL_SPECS}


def _normalize_clarification_max_questions(value: int | None) -> int:
    try:
        normalized = int(value) if value is not None else CLARIFICATION_DEFAULT_MAX_QUESTIONS
    except (TypeError, ValueError):
        normalized = CLARIFICATION_DEFAULT_MAX_QUESTIONS
    return max(CLARIFICATION_QUESTION_LIMIT_MIN, min(CLARIFICATION_QUESTION_LIMIT_MAX, normalized))


def _build_clarification_spec(tool: dict, clarification_max_questions: int | None = None) -> dict:
    spec = copy.deepcopy(tool)
    if spec.get("name") != "ask_clarifying_question":
        return spec

    limit = _normalize_clarification_max_questions(clarification_max_questions)
    parameters = spec.get("parameters") if isinstance(spec.get("parameters"), dict) else {}
    properties = parameters.get("properties") if isinstance(parameters.get("properties"), dict) else {}
    questions_schema = properties.get("questions") if isinstance(properties.get("questions"), dict) else {}
    questions_schema["maxItems"] = limit
    questions_schema["description"] = f"List of 1-{limit} clarification questions."
    properties["questions"] = questions_schema
    parameters["properties"] = properties
    spec["parameters"] = parameters

    prompt = spec.get("prompt") if isinstance(spec.get("prompt"), dict) else {}
    prompt_inputs = prompt.get("inputs") if isinstance(prompt.get("inputs"), dict) else {}
    prompt_inputs["questions"] = f"1-{limit} structured questions"
    prompt["inputs"] = prompt_inputs

    guidance = str(prompt.get("guidance") or "").strip()
    limit_note = f" Ask at most {limit} question(s) in a single call."
    if limit_note.strip() not in guidance:
        guidance = f"{guidance}{limit_note}".strip()
    prompt["guidance"] = guidance
    spec["prompt"] = prompt
    return spec


def get_enabled_tool_specs(active_tool_names: list[str], clarification_max_questions: int | None = None) -> list[dict]:
    active_set = set(active_tool_names or [])
    specs = [tool for tool in TOOL_SPECS if tool["name"] in active_set]
    if not RAG_ENABLED:
        specs = [tool for tool in specs if tool["name"] != "search_knowledge_base"]
    return [_build_clarification_spec(tool, clarification_max_questions) for tool in specs]


def resolve_runtime_tool_names(
    active_tool_names: list[str],
    canvas_documents: list[dict] | None = None,
    *,
    user_message: str | None = None,
    workspace_root: str | None = None,
) -> list[str]:
    names = list(active_tool_names or [])
    if not names:
        return []

    if user_message is None and workspace_root is None:
        if canvas_documents:
            return names
        return [name for name in names if name not in CANVAS_DOCUMENT_TOOL_NAMES]

    normalized_text = _normalize_intent_text(user_message)
    has_canvas_documents = bool(canvas_documents)
    enable_workspace_tools = _should_enable_workspace_tools(
        normalized_text,
        workspace_root=workspace_root,
        has_canvas_documents=has_canvas_documents,
    )
    enable_web_tools = _should_enable_web_tools(normalized_text)
    enable_news_tools = _should_enable_news_tools(normalized_text)
    enable_canvas_creation = _should_enable_canvas_creation(
        normalized_text,
        has_canvas_documents=has_canvas_documents,
    )

    runtime_names: list[str] = []
    for name in names:
        if name in CANVAS_DOCUMENT_TOOL_NAMES and not has_canvas_documents:
            continue
        if name == "create_canvas_document" and not enable_canvas_creation:
            continue
        if name in WORKSPACE_TOOL_NAMES and not enable_workspace_tools:
            continue
        if name in NEWS_TOOL_NAMES and not enable_news_tools:
            continue
        if name in WEB_SEARCH_TOOL_NAMES and name not in NEWS_TOOL_NAMES and not enable_web_tools:
            continue
        runtime_names.append(name)
    return runtime_names


def get_openai_tool_specs(
    active_tool_names: list[str],
    canvas_documents: list[dict] | None = None,
    clarification_max_questions: int | None = None,
) -> list[dict]:
    specs = []
    runtime_tool_names = resolve_runtime_tool_names(active_tool_names, canvas_documents=canvas_documents)
    for tool in get_enabled_tool_specs(runtime_tool_names, clarification_max_questions=clarification_max_questions):
        parameters = copy.deepcopy(tool.get("parameters") or {})
        if parameters.get("type") == "object":
            parameters.setdefault("additionalProperties", False)
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description") or "",
                    "parameters": parameters,
                },
            }
        )
    return specs



def _compact_arg_type(arg_props: dict) -> str:
    arg_type = arg_props.get("type", "string")
    if arg_type == "array":
        item_type = (arg_props.get("items") or {}).get("type", "")
        if item_type:
            return f"array[{item_type}]"
    return arg_type


def get_prompt_tool_context(
    active_tool_names: list[str],
    canvas_documents: list[dict] | None = None,
    clarification_max_questions: int | None = None,
) -> list[dict] | None:
    tools = []
    runtime_tool_names = resolve_runtime_tool_names(active_tool_names, canvas_documents=canvas_documents)
    for tool in get_enabled_tool_specs(runtime_tool_names, clarification_max_questions=clarification_max_questions):
        parameters = tool.get("parameters") if isinstance(tool.get("parameters"), dict) else {}
        properties = parameters.get("properties") if isinstance(parameters.get("properties"), dict) else {}
        required = parameters.get("required") if isinstance(parameters.get("required"), list) else []
        prompt = tool.get("prompt") if isinstance(tool.get("prompt"), dict) else {}
        use_for = str(prompt.get("purpose") or "").strip()
        if not use_for:
            use_for = str(tool.get("description") or "").strip().split(". ")[0].strip()

        entry = {"name": tool["name"]}
        if use_for:
            entry["use_for"] = use_for
        if properties:
            args = {}
            for arg_name, arg_props in properties.items():
                parts = [_compact_arg_type(arg_props)]
                if arg_name in required:
                    parts.append("required")
                enum_values = arg_props.get("enum")
                if enum_values:
                    parts.append("one of " + json.dumps(enum_values, ensure_ascii=False))
                desc = str(arg_props.get("description") or "").strip()
                compact = ", ".join(parts)
                if desc:
                    compact += f" — {desc}"
                args[arg_name] = compact
            entry["arguments"] = args
        guidance = str(prompt.get("guidance") or "").strip()
        if guidance:
            entry["guidance"] = guidance
        tools.append(entry)
    return tools or None
