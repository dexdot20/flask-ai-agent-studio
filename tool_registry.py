from __future__ import annotations

import copy
import json

from config import (
    CLARIFICATION_DEFAULT_MAX_QUESTIONS,
    CLARIFICATION_QUESTION_LIMIT_MAX,
    CLARIFICATION_QUESTION_LIMIT_MIN,
    CONVERSATION_MEMORY_ENABLED,
    DEFAULT_SEARCH_TOOL_QUERY_LIMIT,
    RAG_ENABLED,
    SEARCH_TOOL_QUERY_LIMIT_MAX,
    SEARCH_TOOL_QUERY_LIMIT_MIN,
    SCRATCHPAD_SECTION_METADATA,
    SCRATCHPAD_SECTION_ORDER,
)
from canvas_service import get_canvas_document_capabilities

CANVAS_DOCUMENT_TOOL_NAMES = {
    "expand_canvas_document",
    "batch_read_canvas_documents",
    "scroll_canvas_document",
    "search_canvas_document",
    "validate_canvas_document",
    "rewrite_canvas_document",
    "preview_canvas_changes",
    "batch_canvas_edits",
    "transform_canvas_lines",
    "update_canvas_metadata",
    "set_canvas_viewport",
    "focus_canvas_page",
    "clear_canvas_viewport",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
    "delete_canvas_document",
    "clear_canvas",
}

CANVAS_TEXT_ADDRESSABLE_TOOL_NAMES = {
    "expand_canvas_document",
    "batch_read_canvas_documents",
    "scroll_canvas_document",
    "search_canvas_document",
    "validate_canvas_document",
    "rewrite_canvas_document",
    "preview_canvas_changes",
    "batch_canvas_edits",
    "transform_canvas_lines",
    "set_canvas_viewport",
    "focus_canvas_page",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
}

CANVAS_EDITABLE_TOOL_NAMES = {
    "rewrite_canvas_document",
    "preview_canvas_changes",
    "batch_canvas_edits",
    "transform_canvas_lines",
    "update_canvas_metadata",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
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

SCRATCHPAD_SECTION_ENUM = list(SCRATCHPAD_SECTION_ORDER)
SCRATCHPAD_SECTION_DESCRIPTION = "Section to update: " + "; ".join(
    f"{section_id} = {SCRATCHPAD_SECTION_METADATA[section_id]['title']} ({SCRATCHPAD_SECTION_METADATA[section_id]['description']})"
    for section_id in SCRATCHPAD_SECTION_ORDER
)
CANVAS_LINE_ARRAY_DESCRIPTION = (
    "Each element is one line of text as a properly quoted JSON string with no trailing newline characters. "
    "Code content, including quotes, backslashes, and semicolons, must appear inside these strings and be properly escaped. "
    'Example: ["const char* ssid = \\\"MyNet\\\";", "const char* pass = \\\"abc\\\";"] . '
    "Never place code outside this array or as an argument key."
)


def _build_canvas_edit_operation_variants() -> list[dict]:
    return [
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["replace"], "description": "Replace an inclusive 1-based line range."},
                "start_line": {"type": "integer", "minimum": 1, "description": "1-based first line to replace."},
                "end_line": {"type": "integer", "minimum": 1, "description": "1-based last line to replace."},
                "lines": {"type": "array", "items": {"type": "string"}, "description": CANVAS_LINE_ARRAY_DESCRIPTION},
                "expected_start_line": {"type": "integer", "minimum": 1, "description": "Optional first line of the current snippet that must still match before applying the edit."},
                "expected_lines": {"type": "array", "items": {"type": "string"}, "description": "Optional current lines that must still match before applying the edit."},
            },
            "required": ["action", "start_line", "end_line", "lines"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["insert"], "description": "Insert new lines after a specific anchor line."},
                "after_line": {"type": "integer", "minimum": 0, "description": "Insert after this line number. Use 0 to insert before line 1 at the top of the file."},
                "lines": {"type": "array", "items": {"type": "string"}, "description": CANVAS_LINE_ARRAY_DESCRIPTION},
                "expected_start_line": {"type": "integer", "minimum": 1, "description": "Optional first line of the current snippet that must still match before applying the insert."},
                "expected_lines": {"type": "array", "items": {"type": "string"}, "description": "Optional nearby current lines that must still match before applying the insert."},
            },
            "required": ["action", "after_line", "lines"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["delete"], "description": "Delete an inclusive 1-based line range."},
                "start_line": {"type": "integer", "minimum": 1, "description": "1-based first line to delete."},
                "end_line": {"type": "integer", "minimum": 1, "description": "1-based last line to delete."},
                "expected_start_line": {"type": "integer", "minimum": 1, "description": "Optional first line of the current snippet that must still match before applying the delete."},
                "expected_lines": {"type": "array", "items": {"type": "string"}, "description": "Optional current lines that must still match before applying the delete."},
            },
            "required": ["action", "start_line", "end_line"],
            "additionalProperties": False,
        },
    ]


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
    if enabled("fetch_url") and enabled("scroll_fetched_content", "grep_fetched_content"):
        rows.append(
            {
                "situation": "A fetched web page is long enough that you want to inspect it across later turns without turning it into a Canvas draft.",
                "tool": "fetch_url + scroll_fetched_content / grep_fetched_content",
                "notes": "Fetch once, then browse the cached page by line window with scroll_fetched_content or jump to exact passages with grep_fetched_content.",
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
    if enabled("batch_canvas_edits"):
        rows.append(
            {
                "situation": "You already know several edits for multiple disjoint regions in one or more canvas documents.",
                "tool": "batch_canvas_edits",
                "notes": "Prefer one batch tool call over serial line edits when several non-overlapping changes are already known, especially if they span multiple files.",
            }
        )
    if enabled("preview_canvas_changes"):
        rows.append(
            {
                "situation": "You want to inspect the exact effect of a planned batch before mutating the canvas.",
                "tool": "preview_canvas_changes",
                "notes": "Use this for non-mutating diff previews of planned batch edits.",
            }
        )
    if enabled("transform_canvas_lines"):
        rows.append(
            {
                "situation": "A bulk find-replace or regex transform should be applied across one scope.",
                "tool": "transform_canvas_lines",
                "notes": "Use count_only first if the replacement scope is uncertain.",
            }
        )
    if enabled("update_canvas_metadata"):
        rows.append(
            {
                "situation": "Only document metadata should change, not the content lines.",
                "tool": "update_canvas_metadata",
                "notes": "Use this for summary, role, dependency, symbol, or title updates without rewriting content.",
            }
        )
    if enabled("set_canvas_viewport", "clear_canvas_viewport"):
        rows.append(
            {
                "situation": "You will keep working in the same region for several turns or want to stop injecting a pinned region.",
                "tool": "set_canvas_viewport / clear_canvas_viewport",
                "notes": "Use set_canvas_viewport only on text-addressable documents with known line ranges. Pinned viewport lines are auto-injected in later prompts until they expire or are cleared.",
            }
        )
    if enabled("focus_canvas_page"):
        rows.append(
            {
                "situation": "The active canvas document is multi-page and you need one specific page pinned into future prompts.",
                "tool": "focus_canvas_page",
                "notes": "Prefer this over manual page-range estimates only when the document exposes explicit '## Page N' markers in text content.",
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
    if enabled("batch_read_canvas_documents"):
        rows.append(
            {
                "situation": "You need content from several canvas documents or ranges at once.",
                "tool": "batch_read_canvas_documents",
                "notes": "Prefer this over multiple expand or scroll calls when reasoning depends on several files together.",
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
    if enabled("validate_canvas_document"):
        rows.append(
            {
                "situation": "You want a syntax or structure check after editing a canvas document.",
                "tool": "validate_canvas_document",
                "notes": "Use this after code or config edits to catch syntax issues before running anything.",
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
            "Append one or more rare durable general facts to one section of the persistent scratchpad. "
            "Reserve this for cross-conversation memory only. If the detail is mainly about the current chat or task, save it to conversation memory instead. "
            "Do not store temporary task details, sensitive secrets, one-off requests, or speculative inferences."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": SCRATCHPAD_SECTION_ENUM,
                    "description": SCRATCHPAD_SECTION_DESCRIPTION,
                },
                "notes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of short durable facts to append. Each item must be a single standalone fact — do not bundle multiple facts into one item. Minimum 1 item.",
                    "minItems": 1,
                }
            },
            "required": ["section", "notes"],
        },
        "prompt": {
            "purpose": "Saves one or more short durable cross-conversation memory lines into a specific scratchpad section only when they are likely to matter later.",
            "inputs": {
                "section": "target section id such as preferences, profile, lessons, tasks, problems, notes, or domain",
                "notes": "list of single short durable memory lines — one fact per item",
            },
            "guidance": (
                "Use very sparingly. Save only durable user-specific facts, recurring constraints, or stable preferences that are likely to matter in future conversations. "
                "If the information mainly belongs to the current chat, task, investigation, or tool run, save it to conversation memory instead. "
                "Do not save temporary requests, current-task details, large summaries, tool outputs, web/search results, speculative guesses, or sensitive data. "
                "If the information would not change future responses or behavior across conversations, do not store it. "
                "Choose the section deliberately: preferences for stable style/language instructions, profile for reasoning patterns, lessons for takeaways, problems for recurring unresolved issues, tasks for long-running cross-conversation work, domain for durable technical facts, and notes for anything durable that does not fit elsewhere. "
                "Each item in `notes` must be a single short standalone fact. Never combine multiple facts into one item."
            ),
        },
    },
    {
        "name": "replace_scratchpad",
        "description": (
            "Completely replace one section of the persistent scratchpad. "
            "Use this to rewrite, reorganize, or remove outdated durable general facts in a single section. "
            "Reserve scratchpad edits for cross-conversation memory, not current-chat state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": SCRATCHPAD_SECTION_ENUM,
                    "description": SCRATCHPAD_SECTION_DESCRIPTION,
                },
                "new_content": {
                    "type": "string",
                    "description": "The new content that will fully replace the selected scratchpad section.",
                }
            },
            "required": ["section", "new_content"],
        },
        "prompt": {
            "purpose": "Completely rewrites one structured scratchpad section.",
            "inputs": {
                "section": "target section id",
                "new_content": "the new complete content for that one section",
            },
            "guidance": (
                "Use carefully to prune or reorganize existing facts in one section. Ensure you do not accidentally delete important existing preferences or lessons from that section. "
                "Keep the final text compact and only include durable, general, high-signal facts that should matter across future conversations. "
                "If the content is mainly about the current chat or task, keep it out of the scratchpad and use conversation memory instead. Prefer a short bulleted list over paragraphs."
            ),
        },
    },
    {
        "name": "read_scratchpad",
        "description": (
            "Read the current persistent scratchpad content across all sections exactly as stored. "
            "Use this when you need to inspect the live structured scratchpad before editing it."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "prompt": {
            "purpose": "Reads the current structured scratchpad memory for inspection before editing.",
            "inputs": {},
            "guidance": (
                "Use this when you need to verify or quote the current durable memory before appending or replacing it. "
                "Prefer this before replace_scratchpad when you want to preserve existing facts."
            ),
        },
    },
        {
            "name": "save_to_conversation_memory",
            "description": (
                "Save one compact conversation-scoped memory entry for this chat only. "
                "Use this as the default place to store important chat-specific details, active constraints, decisions, discovered repo or environment facts, or critical tool outcomes that should not be lost later in the same conversation. "
                "If the same key already exists, the entry is refreshed instead of duplicated."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entry_type": {
                        "type": "string",
                        "enum": ["user_info", "task_context", "tool_result", "decision"],
                        "description": "Classification for the memory entry.",
                    },
                    "key": {
                        "type": "string",
                        "description": "Short label for the fact or result. Keep it compact and specific.",
                    },
                    "value": {
                        "type": "string",
                        "description": "Single-line micro-summary of the information to remember for later turns in this same chat.",
                    },
                },
                "required": ["entry_type", "key", "value"],
            },
            "prompt": {
                "purpose": "Writes one short conversation-specific memory entry that will be auto-injected in later turns of this same chat.",
                "inputs": {
                    "entry_type": "user_info, task_context, tool_result, or decision",
                    "key": "short label",
                    "value": "one compact factual line",
                },
                "guidance": (
                    "Use this whenever the information is important within this conversation but not clearly durable general memory for the cross-conversation scratchpad. "
                    "When choosing between scratchpad and conversation memory, default to conversation memory unless the fact is durable, general, and likely useful across future chats. "
                    "Prefer concise micro-summaries over raw outputs. Save incrementally after important clarifications, tool results, decisions, and constraints instead of waiting for a later summary. "
                    "Multiple compact entries are better than one overloaded summary. Be proactive in long or tool-heavy conversations, especially before details may be summarized, pruned, or pushed out of the visible context window. "
                    "Reuse the same key when updating the same fact so memory stays compact. "
                    "Do NOT save raw clarification question answers here — the clarification system already persists and injects them automatically. "
                    "Saving clarification answers to memory creates confusion in later turns."
                ),
            },
        },
        {
            "name": "delete_conversation_memory_entry",
            "description": (
                "Delete one outdated or incorrect conversation memory entry by id. "
                "Use this to clean up stale memory inside the current chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Conversation memory entry id to remove.",
                    },
                },
                "required": ["entry_id"],
            },
            "prompt": {
                "purpose": "Removes one obsolete conversation-scoped memory entry.",
                "inputs": {
                    "entry_id": "id shown in the Conversation Memory prompt section",
                },
                "guidance": "Use this when an earlier conversation-memory entry is no longer valid, was superseded, or should not keep influencing later turns.",
            },
        },
        {
            "name": "save_to_persona_memory",
            "description": (
                "Save one compact persona-scoped memory entry for the currently active persona. "
                "This memory is shared across conversations that use the same persona. "
                "If the same key already exists, the entry is refreshed instead of duplicated."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Short label for the stable persona-scoped fact. Keep it compact and specific.",
                    },
                    "value": {
                        "type": "string",
                        "description": "Single-line micro-summary of the information to remember across future conversations that use this persona.",
                    },
                },
                "required": ["key", "value"],
            },
            "prompt": {
                "purpose": "Writes one short persona-scoped memory entry that will be auto-injected in later conversations using this same persona.",
                "inputs": {
                    "key": "short label",
                    "value": "one compact factual line",
                },
                "guidance": (
                    "Use this for stable persona-scoped facts that should survive beyond the current chat, but are not broad enough for the global scratchpad. "
                    "Prefer this for recurring conventions, reusable repo or domain facts tied to this persona's work, and other durable persona-level context. "
                    "If the detail only matters for this current chat, save it to conversation memory instead. "
                    "Do NOT save raw tool outputs, temporary plans, or one-off task state here. "
                    "Reuse the same key when updating the same fact so persona memory stays compact."
                ),
            },
        },
        {
            "name": "delete_persona_memory_entry",
            "description": (
                "Delete one outdated or incorrect persona memory entry by id. "
                "Use this to clean up stale persona-scoped memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Persona memory entry id to remove.",
                    },
                },
                "required": ["entry_id"],
            },
            "prompt": {
                "purpose": "Removes one obsolete persona-scoped memory entry.",
                "inputs": {
                    "entry_id": "id shown in the Persona Memory prompt section",
                },
                "guidance": "Use this when an earlier persona-memory entry is no longer valid, was superseded, or should stop influencing future conversations for this persona.",
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
                            },
                            "depends_on": {
                                "type": "object",
                                "description": "Optional dependency rule that makes this question appear only after a prior question has one of the expected values.",
                                "properties": {
                                    "question_id": {
                                        "type": "string",
                                        "description": "The id of the earlier question this one depends on."
                                    },
                                    "value": {
                                        "type": "string",
                                        "description": "One required value from the parent question that should reveal this question."
                                    },
                                    "values": {
                                        "type": "array",
                                        "description": "Allowed parent-question values that should reveal this question.",
                                        "items": {"type": "string"},
                                        "minItems": 1,
                                        "maxItems": 10
                                    }
                                }
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
                "Use depends_on only for short follow-up branches that should stay hidden until a previous answer makes them relevant. "
                "Each questions item must be an object with id, label, and input_type; example: {\"id\":\"scope\",\"label\":\"Which scope?\",\"input_type\":\"text\"}. "
                "Use plain UI text only for intro, labels, placeholders, and options. Do not include Q:/A: prefixes, markdown bullets, XML/tag wrappers, code fences, or markers like <| and |>."
            ),
        },
    },
    {
        "name": "set_conversation_title",
        "description": (
            "Set a concise conversation title for the current chat. "
            "Use this on the first turn to replace the default title when the topic is clear."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short topic title, typically 2-5 words.",
                }
            },
            "required": ["title"],
        },
        "prompt": {
            "purpose": "Sets the conversation title shown in chat history.",
            "inputs": {
                "title": "short conversation topic title",
            },
            "guidance": (
                "Use this only when the conversation topic is clear. "
                "Prefer 2-5 words, avoid generic labels, and match the user's language when clear."
            ),
        },
    },
    {
        "name": "sub_agent",
        "description": (
            "Delegate a bounded research or inspection task to a helper sub-agent that can use only read-only tools, including exposed web search and URL fetch tools. "
            "Use it proactively when the task is genuinely multi-step, multi-tool, or context-heavy and would otherwise force a long inline tool chain — such as broad repo/web analysis, cross-file synthesis, or evidence gathering that needs a compact summary. "
            "Prefer direct answering or a single tool call when that is enough. "
            "Do not use it for file mutations, user clarification, or recursive delegation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The delegated task for the helper agent. Rewrite the user's request into clear English instructions unless the task is explicitly language-specific, and include only research-relevant details in that instruction text.",
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Legacy optional helper-agent tool budget (1-12). The runtime uses the user-configured Settings value instead, so this field is ignored when present.",
                    "minimum": 1,
                    "maximum": 12,
                },
            },
            "required": ["task"],
        },
        "prompt": {
            "purpose": "Delegates a scoped research or inspection task to a bounded helper agent and returns a compact summary with artifacts.",
            "inputs": {
                "task": "the delegated task and desired output",
                "max_steps": "optional helper-agent tool budget",
            },
            "guidance": (
                "Use this when the investigation genuinely benefits from a separate bounded pass and would otherwise require several tool steps or repeated context stitching in the parent agent. "
                "If the request can already be answered from the current conversation or stable knowledge, do not delegate it to web research. "
                "Do not let the token cost warning block delegation when the task is complex; the sub-agent exists for exactly those multi-tool cases. "
                "Give the helper a concrete task, expected deliverable, and any important constraints. "
                "Remember that the helper only receives fixed web-research tools when you are thinking in the older web-only model. "
                "Remember that classic web-research helpers such as search_web, fetch_url, fetch_url_summarized, scroll_fetched_content, and grep_fetched_content remain available when enabled. "
                "Remember that the helper receives only read-only tools selected in Settings (for example web research, canvas inspection, and workspace readers). "
                "The user controls both the helper's web-tool allowlist and its maximum step budget from Settings. "
                "The user controls both the helper's read-only tool allowlist and its maximum step budget from Settings, so do not try to manage that budget yourself. "
                "Before calling this tool, rewrite the delegated task into concise English instructions for the helper, even if the user spoke Turkish or another language. "
                "Use the user's original language only when the delegated task itself depends on that language, and otherwise expect the helper to work in English by default. "
                "Do not pass separate user-profile, background, conversation-summary, or canvas context; put only the research instruction text itself in the task. "
                "Keep it scoped: prefer one helper call over many, and do not delegate writes, clarifications, or recursive agent orchestration. "
                "The helper may still stop before reaching its configured budget when it already has enough evidence. "
                "If the helper uses web search, each search_web/search_news call must stay within the 1-5 query limit; split larger batches into separate calls."
            ),
        },
    },
    {
        "name": "image_explain",
        "description": (
            "Answer a follow-up question about a previously uploaded image saved in the current conversation. "
            "Use this when the user refers back to an earlier image or screenshot and the stored visual context may matter. "
            "Always send the follow-up question in English."
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
            "purpose": "Asks the configured helper image model a new question about a stored image from this conversation.",
            "inputs": {
                "image_id": "stored image id",
                "conversation_id": "current conversation id",
                "question": "follow-up question written in English",
            },
            "guidance": (
                "Use this when the user asks about a previously uploaded image instead of relying only on the cached summary. "
                "Always send the question in English. The tool response will be in English and uses the helper image model configured in Settings. "
                "If the referenced image is ambiguous, ask the user to clarify which image they mean before calling the tool."
            ),
        },
    },
    {
        "name": "transcribe_youtube_video",
        "description": (
            "Normalize a YouTube URL, transcribe the video's speech locally, and return a prompt-ready transcript context block. "
            "Use this only when the user explicitly asks for a YouTube transcription or video-summary workflow and a URL is provided."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "YouTube URL to transcribe (watch, short, embed, or youtu.be format).",
                }
            },
            "required": ["url"],
        },
        "prompt": {
            "purpose": "Transcribes a YouTube video and returns transcript text plus a context block ready for prompt injection.",
            "inputs": {
                "url": "full YouTube URL",
            },
            "guidance": (
                "Call this when the user wants transcript-driven analysis from a YouTube link and no transcript is already available in the current turn. "
                "Do not call it for non-YouTube URLs. "
                "If the runtime reports missing dependencies or disabled feature flags, surface that error clearly and continue with alternatives."
            ),
        },
    },
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the internal knowledge base indexed with RAG. "
            "Use this when the answer may exist in synced conversation history, stored tool outputs, or uploaded documents and you cannot answer reliably from the current context. "
            "Optionally filter by category. Use this for conversation, tool_result, or uploaded_document content. For cross-conversation web research memory, use search_tool_memory instead. "
            "Avoid repeating semantically overlapping searches when one good result set already answers the question; unnecessary searches waste tokens."
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
                    "description": "Optional category filter: conversation, tool_result, or uploaded_document. Do not pass tool_memory here; use search_tool_memory for web research memory.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of chunks to retrieve (1-12).",
                    "minimum": 1,
                    "maximum": 12,
                },
                "min_similarity": {
                    "type": "number",
                    "description": "Optional minimum similarity threshold between 0.0 and 1.0. Higher values trade recall for precision.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "save_to_conversation_memory": {
                    "type": "boolean",
                    "description": "If true, save a compact summary of the strongest search findings to conversation memory for this chat.",
                },
                "memory_key": {
                    "type": "string",
                    "description": "Optional short conversation-memory key to use when save_to_conversation_memory is true. Reuse the same key to refresh an existing finding.",
                },
            },
            "required": ["query"],
        },
        "prompt": {
            "purpose": "Searches the internal RAG knowledge base built from files, URLs, notes, and conversations.",
            "inputs": {"query": "semantic search query", "category": "optional category", "top_k": "1-12 results", "min_similarity": "optional threshold 0.0-1.0", "save_to_conversation_memory": "optional boolean", "memory_key": "optional short memory label"},
            "guidance": "Use category when the likely source type is clear, and use at most a few focused searches. Synthesize from returned chunks instead of retrying near-duplicate queries. If the current context is already sufficient, do not search again; unnecessary searches waste tokens. If the finding should survive later turns in this chat, set save_to_conversation_memory=true and provide a short memory_key.",
        },
    },
    {
        "name": "search_tool_memory",
        "description": (
            "Search past web tool results stored from previous conversations. "
            "Use this before making a new web request when you suspect the topic was already researched and the current context is not enough. "
            "This searches remembered results from fetch_url, search_web, and news tools across conversations. "
            "Use search_knowledge_base instead for uploaded documents or conversation content. Unnecessary lookups waste tokens."
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
                "min_similarity": {
                    "type": "number",
                    "description": "Optional minimum similarity threshold between 0.0 and 1.0. Higher values trade recall for precision.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "save_to_conversation_memory": {
                    "type": "boolean",
                    "description": "If true, save a compact summary of the strongest remembered findings to conversation memory for this chat.",
                },
                "memory_key": {
                    "type": "string",
                    "description": "Optional short conversation-memory key to use when save_to_conversation_memory is true. Reuse the same key to refresh an existing finding.",
                },
            },
            "required": ["query"],
        },
        "prompt": {
            "purpose": "Searches memory of past web searches, URL fetches, and news lookups.",
            "inputs": {"query": "semantic search query", "top_k": "1-10 results", "min_similarity": "optional threshold 0.0-1.0", "save_to_conversation_memory": "optional boolean", "memory_key": "optional short memory label"},
            "guidance": (
                "Use before making a new web request if similar research may already exist and you cannot answer from the current context. "
                "If high-similarity results already answer the question, reuse them instead of repeating the search. "
                "When the response includes expires_at_utc, treat older or near-expiry results more cautiously. Unnecessary lookups waste tokens. "
                "If the finding should survive later turns in this chat, set save_to_conversation_memory=true and provide a short memory_key."
            ),
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the web using DuckDuckGo. Use this only when you need current information, external verification, or facts that are not already answerable from the current conversation. "
            "Provide one or more search queries. Do not pass max_results or other result-limit controls; the runtime already applies the search result cap."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"List of search queries to run (1–{DEFAULT_SEARCH_TOOL_QUERY_LIMIT} queries).",
                    "minItems": 1,
                    "maxItems": DEFAULT_SEARCH_TOOL_QUERY_LIMIT,
                }
            },
            "additionalProperties": False,
            "required": ["queries"],
        },
        "prompt": {
            "purpose": "Runs a general web search and returns recent results.",
            "inputs": {"queries": f"1-{DEFAULT_SEARCH_TOOL_QUERY_LIMIT} search queries"},
            "guidance": (
                "search_web accepts only the queries array. Do not pass max_results, top_k, limit, or any other control arguments; the runtime already caps results. "
                f"Never pass more than {DEFAULT_SEARCH_TOOL_QUERY_LIMIT} queries in a single call. If you need more search terms, split them across multiple search_web calls. "
                "If the answer is already available from the current context or does not require external verification, do not search."
            ),
        },
    },
    {
        "name": "fetch_url",
        "description": (
            "Fetch and read the content of a specific web page. Returns cleaned text, metadata, and a page outline. "
            "Use after search_web when you actually need the page's exact content or source wording. "
            "For very large pages the content may be clipped to fit the token budget; "
            "when that happens the result includes an outline of the page sections plus preserved leading, middle, and trailing excerpts when space allows. "
            "If you need omitted sections or an exact passage from a clipped page, use scroll_fetched_content or grep_fetched_content after this tool."
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
            "guidance": (
                "Large pages are automatically clipped to stay within the token budget. "
                "When content is clipped the result shows a Page Outline of the section headings. "
                "The tool also tries to preserve a middle excerpt so important details are not biased toward only the start or end of the page. "
                "Do not fetch a page unless you actually need its exact content or source wording. "
                "Do not repeat the same URL in the same turn. "
                "If a long page will remain useful across later turns, fetch_url keeps the raw page text available for later scroll_fetched_content and grep_fetched_content calls without importing it into Canvas. "
                "Use scroll_fetched_content to browse omitted sections and grep_fetched_content to locate exact text in a clipped page. "
                "To recall content from a previously fetched URL across turns use search_tool_memory."
            ),
        },
    },
    {
        "name": "fetch_url_summarized",
        "description": (
            "Fetch a specific web page, send the cleaned page text to a dedicated summarizer model, and return only the resulting clean summary. "
            "Use this when the parent assistant needs a concise distilled page summary instead of raw page text. "
            "The returned tool result intentionally hides the full fetched content from the parent assistant and favors dense sectioned summaries over raw excerpts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL of the page (must start with http:// or https://).",
                },
                "focus": {
                    "type": "string",
                    "description": "Optional question, angle, or topic to focus the summary on.",
                }
            },
            "required": ["url"],
        },
        "prompt": {
            "purpose": "Reads a URL and returns only an AI-generated summary of the page.",
            "inputs": {"url": "full http/https URL", "focus": "optional focus or question"},
            "guidance": (
                "Use this when you want the page distilled before it reaches you, such as long articles where only the key points matter. "
                "If focus is given, the summary should prioritize that question or angle. "
                "Expect short labeled sections with key facts, constraints, and any unresolved uncertainty the source still leaves open. "
                "Use fetch_url instead when you need raw extracted text, metadata, page outline details, exact wording from the source page, or later browsing via scroll_fetched_content / grep_fetched_content."
            ),
        },
    },
    {
        "name": "scroll_fetched_content",
        "description": (
            "Read a window of lines from the content of a previously fetched URL. "
            "Prefers already-fetched raw page text, but can also re-fetch the page live when cached content is unavailable. "
            "Use this to browse omitted sections of a long or clipped page without importing it into Canvas."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL whose fetched content should be browsed; cached content is preferred and live refetch can be used when needed.",
                },
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional 1-based first line to show (default 1).",
                },
                "window_lines": {
                    "type": "integer",
                    "minimum": 20,
                    "maximum": 400,
                    "description": "Number of lines to return (20–400, default 120).",
                },
                "refresh_if_missing": {
                    "type": "boolean",
                    "description": "When true, automatically re-fetch the URL live if cached raw content is unavailable (default true).",
                },
            },
            "required": ["url"],
        },
        "prompt": {
            "purpose": "Browses a previously fetched page by returning a specific line window from its cached content.",
            "inputs": {
                "url": "URL to browse; cached content is preferred and live refetch can be used when needed",
                "start_line": "optional 1-based first line to show",
                "window_lines": "optional 20-400 line window size",
                "refresh_if_missing": "whether to re-fetch the page live when cached raw content is missing",
            },
            "guidance": (
                "Use this after fetch_url when the returned page text was clipped or when you want to inspect a large fetched source incrementally across later turns. "
                "Start with start_line=1 when you need the top of the page, then continue with the next window when the result reports more content below. "
                "Use grep_fetched_content first when you need to jump directly to a keyword, heading, code snippet, or exact passage instead of browsing sequentially. "
                "Use refresh_if_missing=false only when you explicitly need cache-only behavior."
            ),
        },
    },
    {
        "name": "grep_fetched_content",
        "description": (
            "Search for a keyword, phrase, or regex pattern inside the content of a previously fetched URL. "
            "Prefers already-fetched raw page text, but can also re-fetch the page live when cached content is unavailable. "
            "Returns matching lines with surrounding context. "
            "Use this instead of re-fetching the same URL when you need to find a specific value, code snippet, heading, or term."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL whose content to search; the tool can use cached content or re-fetch the page live when needed.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Keyword, phrase, or Python regex pattern to search for (case-insensitive).",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Number of lines of context to include before and after each match (0–5, default 2).",
                    "minimum": 0,
                    "maximum": 5,
                },
                "max_matches": {
                    "type": "integer",
                    "description": "Maximum number of matches to return (1–30, default 20).",
                    "minimum": 1,
                    "maximum": 30,
                },
                "refresh_if_missing": {
                    "type": "boolean",
                    "description": "When true, automatically re-fetch the URL live if cached raw content is unavailable (default true).",
                },
            },
            "required": ["url", "pattern"],
        },
        "prompt": {
            "purpose": "Searches cached fetch_url content for a keyword, phrase, or regex.",
            "inputs": {
                "url": "URL to search; cached content is preferred and live refetch can be used when needed",
                "pattern": "keyword or regex",
                "context_lines": "0-5 lines of context (default 2)",
                "max_matches": "1-30 max results (default 20)",
                "refresh_if_missing": "whether to re-fetch the page live when cached raw content is missing",
            },
            "guidance": (
                "Prefer this over repeating fetch_url when you need exact wording from a page you already inspected. "
                "If raw cached content is missing, the tool can refresh the page live unless you explicitly disable refresh_if_missing. "
                "Use simple keywords for broad matches or anchored regex (e.g. r'price:\\s*\\d+') for precise values. "
                "Use refresh_if_missing=false only when you explicitly need cache-only behavior."
            ),
        },
    },
    {
        "name": "search_news_ddgs",
        "description": (
            "Search recent news articles using DuckDuckGo News. Returns title, link, publication time and source for each article. "
            "Use this only when the request needs current news coverage, external verification, or broad news discovery. "
            "Optionally filter by time range and language. If you need the full article text, follow up with fetch_url on the returned links."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"List of news search queries (1–{DEFAULT_SEARCH_TOOL_QUERY_LIMIT}).",
                    "minItems": 1,
                    "maxItems": DEFAULT_SEARCH_TOOL_QUERY_LIMIT,
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
            "inputs": {"queries": f"1-{DEFAULT_SEARCH_TOOL_QUERY_LIMIT} news queries", "lang": "tr|en", "when": "d|w|m|y"},
            "guidance": (
                "Use this for broad recent-news discovery when you actually need headlines, sources, and timestamps before reading full articles. "
                "Prefer this over search_news_google for generic international topics or the first pass on a topic. "
                f"Never pass more than {DEFAULT_SEARCH_TOOL_QUERY_LIMIT} queries in one call. If you need article details, follow up with fetch_url on the most relevant links instead of widening the same news query repeatedly. "
                "If the answer is already known or does not require current news verification, do not search."
            ),
        },
    },
    {
        "name": "search_news_google",
        "description": (
            "Search Google News via RSS feed. Returns title, link, publication time and source for each article. "
            "Use this only when the request needs current news coverage or current news verification and Google News coverage is specifically preferred, especially for Turkish financial news, local outlets, or when DuckDuckGo News yields weak coverage. "
            "Optionally filter by time range and language. If you need the full article text, follow up with fetch_url on the returned links."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"List of news search queries (1–{DEFAULT_SEARCH_TOOL_QUERY_LIMIT}).",
                    "minItems": 1,
                    "maxItems": DEFAULT_SEARCH_TOOL_QUERY_LIMIT,
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
            "inputs": {"queries": f"1-{DEFAULT_SEARCH_TOOL_QUERY_LIMIT} news queries", "lang": "tr|en", "when": "d|w|m|y"},
            "guidance": (
                "Use this when Google News coverage is likely stronger than DuckDuckGo News for the topic or locale and the request genuinely needs current news verification. "
                f"Never pass more than {DEFAULT_SEARCH_TOOL_QUERY_LIMIT} queries in one call. After scanning the feed, fetch only the few links that are actually needed."
            ),
        },
    },
    {
        "name": "expand_canvas_document",
        "description": (
            "Load one canvas document beyond the active excerpt when you need more context. "
            "The result is a call-time snapshot, so re-run after later edits if you need a refreshed view. "
            "Use this before broader reasoning or editing; document_id is optional, and when document_id and document_path are omitted it defaults to the active document."
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
                "Treat the result as a call-time snapshot of the canvas state; if later edits may have happened, call expand_canvas_document again instead of assuming the older expansion is still current. "
                "After expanding, prefer the smallest valid edit that solves the request. "
                "If you do not know the document_id, use document_path from the workspace summary or manifest instead of getting stuck. "
                "In project mode, prefer document_path over document_id so file targeting stays stable."
            ),
        },
    },
    {
        "name": "batch_read_canvas_documents",
        "description": (
            "Read multiple canvas documents or line ranges in one call. "
            "Use this instead of multiple expand_canvas_document or scroll_canvas_document calls when you need context from several files together."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "documents": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 12,
                    "description": "List of canvas documents or line ranges to read.",
                    "items": {
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
                                "description": "Optional 1-based start line. Provide with end_line to read only a range."
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "Optional 1-based end line. Provide with start_line to read only a range."
                            },
                            "max_lines": {
                                "type": "integer",
                                "description": "Optional max line budget for this request."
                            }
                        }
                    }
                }
            },
            "required": ["documents"]
        },
        "prompt": {
            "purpose": "Loads several canvas documents or targeted ranges in a single tool call.",
            "inputs": {"documents": "array of document selectors with optional start_line/end_line/max_lines"},
            "guidance": (
                "Use this when reasoning depends on several open files at once. "
                "For each entry, omit start_line and end_line to expand the document excerpt, or provide both to read only a focused range. "
                "In project mode, prefer document_path over document_id when possible."
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
                "If you do not know the document_id, use the document_path from the workspace summary or manifest instead of stopping to search for the id. "
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
                "context_lines": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": "Optional number of context lines to include above and below each match. Defaults to 0."
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Optional match offset for pagination. Defaults to 0."
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
        "name": "validate_canvas_document",
        "description": (
            "Validate one canvas document without modifying it. "
            "Checks Python syntax, JSON validity, or Markdown structure depending on validator or file type."
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
                "validator": {
                    "type": "string",
                    "enum": ["python", "json", "markdown", "auto"],
                    "description": "Validator to use. Defaults to auto based on document language or format."
                }
            }
        },
        "prompt": {
            "purpose": "Runs a non-mutating syntax or structure check on one canvas document.",
            "inputs": {"document_id": "optional target id", "document_path": "optional target project-relative path", "validator": "python, json, markdown, or auto"},
            "guidance": (
                "Use this after editing code or config in the canvas when you want a fast correctness check before running anything. "
                "Prefer validator='auto' unless you specifically need to override the inferred format."
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
            "guidance": (
                "Use this when you need exact source text from a known file. Prefer narrow line ranges for large files, and use search_files or list_dir first when the path or target region is still unknown."
            ),
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
            "guidance": (
                "Use this to discover the workspace structure before reading or writing files. Prefer a focused subdirectory path when possible instead of repeatedly listing the workspace root."
            ),
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
            "guidance": "Use this when you know a filename fragment, directory prefix, or exact text to look for. Prefer path-only search first, then enable search_content when you need matching file contents too.",
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
            "guidance": (
                "Use this after scaffolding or batch file writes to catch structural issues early. Prefer validating the smallest relevant project subdirectory when you do not need a full-workspace check."
            ),
        },
    },
    {
        "name": "preview_github_import_to_canvas",
        "description": (
            "Fetch metadata for a GitHub repository and return a structured preview of which files would be imported into Canvas. "
            "Does NOT modify Canvas. Use this before importing to show the user what will change."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "GitHub repository URL, such as https://github.com/owner/repo or https://github.com/owner/repo/tree/branch/subdir."
                }
            },
            "required": ["url"]
        },
        "prompt": {
            "purpose": "Returns a file listing preview for a GitHub repository without mutating Canvas.",
            "inputs": {"url": "GitHub repository URL"},
            "guidance": (
                "ALWAYS call this tool first when the user wants to import a GitHub repository into Canvas. "
                "After receiving the preview, present the file list and total count to the user, then call ask_clarifying_question "
                "to obtain explicit approval BEFORE proceeding. "
                "Do NOT call import_github_repository_to_canvas in the same turn as this tool. "
                "Only call import_github_repository_to_canvas in a subsequent turn after the user has confirmed."
            ),
        },
    },
    {
        "name": "import_github_repository_to_canvas",
        "description": (
            "Download a GitHub repository archive, extract supported text files, and add them into the current conversation Canvas as path-aware project files. "
            "This mutates Canvas and may update existing files with matching paths. "
            "REQUIRED: You MUST have called preview_github_import_to_canvas and obtained explicit user approval via ask_clarifying_question in a PREVIOUS turn before calling this."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "GitHub repository URL to import, such as https://github.com/owner/repo or https://github.com/owner/repo/tree/branch/subdir."
                }
            },
            "required": ["url"]
        },
        "prompt": {
            "purpose": "Imports a GitHub repository into Canvas as path-aware project files and chooses one high-signal file as the active document.",
            "inputs": {"url": "GitHub repository URL"},
            "guidance": (
                "ONLY call this tool after all of the following conditions are met: "
                "(1) you called preview_github_import_to_canvas in a previous turn, "
                "(2) you presented the file listing to the user, "
                "(3) you called ask_clarifying_question and the user explicitly confirmed in their most recent message. "
                "Never call this tool speculatively or in the same turn as the preview tool. "
                "The import keeps project-relative paths so Canvas tree and path-based targeting work immediately."
            ),
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
                    "description": "Required document title shown in the canvas panel. Never omit it. If path is set, this should usually match the filename or basename."
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
                "title": "required document title; if path is known, usually reuse its basename or filename label",
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
                "Always include title. Never omit it. "
                "If path is provided, set title from that path's basename or user-facing file label (for example src/app.py -> app.py). "
                "If there is no path yet, still provide a concise artifact name such as README.md, Release Plan, or Draft Notes. "
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
                "If the user needs an additional file, create a separate canvas document instead of rewriting the current one into a different file. "
                "When the user's request results in content that naturally replaces the active canvas document, call this tool proactively as part of delivering the response — do not ask the user whether they want it saved."
            ),
        },
    },
    {
        "name": "preview_canvas_changes",
        "description": "Preview the effect of multiple non-overlapping line edits against one canvas document without mutating it.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Optional target canvas document id."},
                "document_path": {"type": "string", "description": "Optional target project-relative path. Prefer this over document_id in project mode."},
                "operations": {
                    "type": "array",
                    "minItems": 1,
                    "description": "Ordered list of non-overlapping replace, insert, or delete operations to preview.",
                    "items": {"oneOf": _build_canvas_edit_operation_variants()}
                }
            },
            "required": ["operations"]
        },
        "prompt": {
            "purpose": "Shows a non-mutating preview of planned batch canvas edits.",
            "inputs": {"document_id": "optional target id", "document_path": "optional target project-relative path", "operations": "ordered edit operations"},
            "guidance": (
                "Use this when you want to inspect the exact before/after effect of planned canvas changes before applying them. "
                "Each operation must be a plain JSON object with an action field set to replace, insert, or delete. "
                "Do not wrap one operation in a string, array, or nested object shell. "
                "Use the same schema as batch_canvas_edits: replace needs start_line, end_line, and lines; insert needs after_line and lines; delete needs start_line and end_line. "
                "Prefer this over speculative prose descriptions when the user needs a concrete diff preview."
            ),
        },
    },
    {
        "name": "batch_canvas_edits",
        "description": "Apply multiple non-overlapping line edit operations to one canvas document in a single call.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "Optional target canvas document id. Defaults to the active document when document_path is omitted."
                },
                "document_path": {
                    "type": "string",
                    "description": "Optional target project-relative path. Prefer this over document_id in project mode."
                },
                "operations": {
                    "type": "array",
                    "description": "Ordered list of non-overlapping replace, insert, or delete operations to apply against the same document snapshot.",
                    "minItems": 1,
                    "items": {"oneOf": _build_canvas_edit_operation_variants()}
                },
                "targets": {
                    "type": "array",
                    "minItems": 1,
                    "description": "Optional multi-document mode. Each target must include operations and may include document_id or document_path.",
                    "items": {
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
                            "operations": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"oneOf": _build_canvas_edit_operation_variants()},
                                "description": "Ordered list of non-overlapping replace, insert, or delete operations for this target."
                            }
                        },
                        "required": ["operations"]
                    }
                },
                "atomic": {
                    "type": "boolean",
                    "description": "When true, restore the original document or documents if any operation in the batch fails."
                }
            },
            "anyOf": [
                {"required": ["operations"]},
                {"required": ["targets"]}
            ]
        },
        "prompt": {
            "purpose": "Applies multiple disjoint line edits to one or more canvas documents in a single call.",
            "inputs": {"document_id": "optional target id", "document_path": "optional target project-relative path", "operations": "ordered edit operations for one document", "targets": "optional multi-document target array", "atomic": "optional rollback flag"},
            "guidance": (
                "Use this when you already know several non-overlapping edits for one document or multiple documents. "
                "Prefer one batch_canvas_edits call over serial replace_canvas_lines, insert_canvas_lines, or delete_canvas_lines calls when the targets are already known. "
                "Every operation must target a disjoint region or insertion anchor. "
                "Every operation must be a plain JSON object with an action field set to replace, insert, or delete. "
                "Do not nest a single operation inside an extra array or wrapper object. "
                "For replace use start_line, end_line, and lines. For insert use after_line and lines. For delete use start_line and end_line. "
                "Line numbers are interpreted against the pre-batch document and adjusted automatically for earlier operations in the same batch. "
                "When you are editing from a previously seen snippet, include expected_lines and expected_start_line on each operation so stale edits are rejected safely. "
                "Use targets when multiple files should change together. In project mode, prefer document_path when possible."
            ),
        },
    },
    {
        "name": "transform_canvas_lines",
        "description": "Apply a plain-text or regex find-replace across a full canvas document or a specific line scope.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Optional target canvas document id."},
                "document_path": {"type": "string", "description": "Optional target project-relative path. Prefer this over document_id in project mode."},
                "pattern": {"type": "string", "description": "Search text or regex pattern."},
                "replacement": {"type": "string", "description": "Replacement text. Regex capture groups may use $1, $2, and so on."},
                "scope": {"type": "string", "description": "Use 'all' or 'lines_<start>_<end>'."},
                "is_regex": {"type": "boolean"},
                "case_sensitive": {"type": "boolean"},
                "count_only": {"type": "boolean", "description": "When true, report matches without mutating the document."}
            },
            "required": ["pattern", "replacement"]
        },
        "prompt": {
            "purpose": "Performs a scoped plain-text or regex transformation across one canvas document.",
            "inputs": {"document_id": "optional target id", "document_path": "optional target project-relative path", "pattern": "search text or regex", "replacement": "replacement text", "scope": "all or lines range", "is_regex": "regex toggle", "case_sensitive": "case sensitivity toggle", "count_only": "preview-only toggle"},
            "guidance": (
                "Use this for bulk find-replace work across a document or a bounded line range. "
                "If the exact impact is uncertain, run with count_only=true first, then apply the real replacement."
            ),
        },
    },
    {
        "name": "update_canvas_metadata",
        "description": "Update canvas document metadata such as title, summary, role, ignored state, ignore reason, imports, exports, dependencies, or important symbols without changing content lines.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Optional target canvas document id."},
                "document_path": {"type": "string", "description": "Optional target project-relative path. Prefer this over document_id in project mode."},
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "role": {"type": "string", "enum": ["source", "config", "dependency", "docs", "test", "script", "note"]},
                "ignored": {"type": "boolean", "description": "Set true to hide this document's content from future automatic prompt excerpts without deleting it. Set false to re-enable the document later."},
                "ignored_reason": {"type": "string", "description": "Short reason explaining why the document is being ignored. Required when turning ignored on for a document that does not already have a reason."},
                "add_imports": {"type": "array", "items": {"type": "string"}},
                "remove_imports": {"type": "array", "items": {"type": "string"}},
                "add_exports": {"type": "array", "items": {"type": "string"}},
                "remove_exports": {"type": "array", "items": {"type": "string"}},
                "add_dependencies": {"type": "array", "items": {"type": "string"}},
                "remove_dependencies": {"type": "array", "items": {"type": "string"}},
                "add_symbols": {"type": "array", "items": {"type": "string"}}
            }
        },
        "prompt": {
            "purpose": "Updates canvas metadata without touching document content.",
            "inputs": {"document_id": "optional target id", "document_path": "optional target project-relative path", "title": "new title", "summary": "new summary", "role": "new role", "ignored": "set true to suppress future prompt content or false to re-enable it", "ignored_reason": "short reason for ignoring the document", "add_imports": "imports to append", "remove_imports": "imports to remove", "add_exports": "exports to append", "remove_exports": "exports to remove", "add_dependencies": "dependencies to append", "remove_dependencies": "dependencies to remove", "add_symbols": "symbols to append"},
            "guidance": "Use this when only metadata should change and the document body must remain untouched. Set ignored=true with ignored_reason to hide a document's content from future prompt excerpts without deleting it, and set ignored=false later when that document should become visible again.",
        },
    },
    {
        "name": "set_canvas_viewport",
        "description": "Pin a text line range from a text-addressable canvas document so it is automatically injected into later prompts for a limited number of turns.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Optional target canvas document id."},
                "document_path": {"type": "string", "description": "Optional target project-relative path. Prefer this over document_id in project mode."},
                "start_line": {"type": "integer", "minimum": 1, "description": "1-based first line to pin."},
                "end_line": {"type": "integer", "minimum": 1, "description": "1-based last line to pin."},
                "ttl_turns": {"type": "integer", "minimum": 0, "description": "How many future turns to keep the viewport pinned. Use 0 to keep it pinned until explicitly cleared. Ignored when permanent=true."},
                "permanent": {"type": "boolean", "description": "When true, pin the viewport until explicitly cleared and ignore ttl_turns."},
                "auto_unpin_on_edit": {"type": "boolean", "description": "When true, automatically clear the viewport if an overlapping edit changes that region."}
            },
            "required": ["start_line", "end_line"]
        },
        "prompt": {
            "purpose": "Pins a canvas range for automatic reuse in subsequent prompts.",
            "inputs": {"document_id": "optional target id", "document_path": "optional target project-relative path", "start_line": "viewport start", "end_line": "viewport end", "ttl_turns": "number of future turns to keep it pinned", "permanent": "pin until explicitly cleared", "auto_unpin_on_edit": "whether overlapping edits clear it automatically"},
            "guidance": "Use this only for text-addressable canvas documents when you expect to keep working in the same known line range for multiple turns and want to avoid repeated scroll or expand calls. Use permanent=true when the range should stay pinned until you explicitly clear it.",
        },
    },
    {
        "name": "focus_canvas_page",
        "description": "Pin one specific page from a page-marker-aware canvas document so it is automatically injected into later prompts.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Optional target canvas document id."},
                "document_path": {"type": "string", "description": "Optional target project-relative path. Prefer this over document_id in project mode."},
                "page_number": {"type": "integer", "minimum": 1, "description": "1-based page number to pin."},
                "ttl_turns": {"type": "integer", "minimum": 0, "description": "How many future turns to keep the page pinned. Use 0 to keep it pinned until explicitly cleared."},
                "auto_unpin_on_edit": {"type": "boolean", "description": "When true, automatically clear the pinned page if an overlapping edit changes that region."}
            },
            "required": ["page_number"]
        },
        "prompt": {
            "purpose": "Pins one full page from a multi-page canvas document for automatic reuse in subsequent prompts.",
            "inputs": {"document_id": "optional target id", "document_path": "optional target project-relative path", "page_number": "page to focus", "ttl_turns": "number of future turns to keep it pinned", "auto_unpin_on_edit": "whether overlapping edits clear it automatically"},
            "guidance": "Use this only when the canvas content exposes explicit page markers such as '## Page N'. Prefer it over set_canvas_viewport when the user refers to a specific page and those markers already exist in the text content.",
        },
    },
    {
        "name": "clear_canvas_viewport",
        "description": "Clear one pinned canvas viewport or all pinned viewports.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Optional target canvas document id."},
                "document_path": {"type": "string", "description": "Optional target project-relative path. When omitted with document_id, clears all viewports."}
            }
        },
        "prompt": {
            "purpose": "Removes one or all pinned canvas viewports.",
            "inputs": {"document_id": "optional target id", "document_path": "optional target project-relative path"},
            "guidance": "Use this when a pinned viewport is no longer useful or should stop consuming prompt space. If both document_id and document_path are omitted, the tool clears all pinned viewports.",
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
                },
                "expected_start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional first line of the current document context you expect to still match before the edit is applied."
                },
                "expected_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional current lines that must still match before replacing. Use this to guard against line drift after earlier edits or stale previews."
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
                "If the previous tool result includes expected_lines, reuse those values on the next related edit instead of guessing a fresh snippet. "
                "When you are editing based on a previously seen snippet and line numbers may have shifted, include expected_lines (and expected_start_line when needed) so the tool can reject stale edits safely. "
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
                },
                "expected_start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional first line of the current document context you expect to still match before inserting."
                },
                "expected_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional nearby current lines that must still match before inserting. Use this to guard against stale insertion anchors."
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
                "If the previous tool result includes expected_lines, reuse those values on the next related edit instead of guessing a fresh snippet. "
                "When the insertion point comes from an earlier view, include expected_lines (and expected_start_line when needed) so the tool can catch drift before inserting. "
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
                },
                "expected_start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional first line of the current document context you expect to still match before deleting."
                },
                "expected_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional current lines that must still match before deleting. Use this to guard against stale ranges."
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
                "If the previous tool result includes expected_lines, reuse those values on the next related edit instead of guessing a fresh snippet. "
                "When the target range came from an earlier snippet, include expected_lines (and expected_start_line when needed) so stale deletions are rejected safely. "
                "If the target region is not visible, inspect it first. In project mode, prefer document_path when possible."
            ),
        },
    },
    {
        "name": "delete_canvas_document",
        "description": "Delete a canvas document, including obsolete or superseded ones. Defaults to the active document when document_id is omitted.",
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
            "guidance": "Use this when a canvas document is obsolete, superseded, or a throwaway scratch draft, or when the user explicitly wants to remove a single canvas document. Deletion is irreversible for the current conversation state.",
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
            "guidance": "Use this when the whole canvas is obsolete, should be reset, or the user explicitly requests deleting all canvas documents. This is irreversible for the current conversation state, so do not use it as a shortcut for deleting a single file.",
        },
    },
]

TOOL_SPEC_BY_NAME = {tool["name"]: tool for tool in TOOL_SPECS}
SEARCH_QUERY_LIMITED_TOOL_NAMES = {"search_web", "search_news_ddgs", "search_news_google"}

_TOOL_RUNTIME_DEFAULTS = {
    "read_only": False,
    "parallel_safe": False,
    "exclusive_turn": False,
    "session_cacheable": False,
    "prompt_visible": True,
    "ui_hidden": False,
    "depends_on_tool_outputs": False,
    "state_domains": (),
}

_TOOL_RUNTIME_METADATA_OVERRIDES = {
    "ask_clarifying_question": {
        "exclusive_turn": True,
        "state_domains": ("clarification",),
    },
    "set_conversation_title": {
        "ui_hidden": True,
        "prompt_visible": True,
        "state_domains": ("conversation",),
    },
    "sub_agent": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("delegation", "web"),
    },
    "image_explain": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("image",),
    },
    "transcribe_youtube_video": {
        "state_domains": ("video",),
    },
    "search_knowledge_base": {
        "read_only": True,
        "parallel_safe": True,
        "depends_on_tool_outputs": True,
        "state_domains": ("memory", "rag"),
    },
    "search_tool_memory": {
        "read_only": True,
        "parallel_safe": True,
        "depends_on_tool_outputs": True,
        "state_domains": ("memory", "web"),
    },
    "search_web": {
        "read_only": True,
        "parallel_safe": True,
        "session_cacheable": True,
        "state_domains": ("web",),
        "prompt_visible": False,
    },
    "fetch_url": {
        "read_only": True,
        "parallel_safe": True,
        "session_cacheable": True,
        "state_domains": ("web",),
    },
    "fetch_url_summarized": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("web",),
    },
    "scroll_fetched_content": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("web",),
    },
    "grep_fetched_content": {
        "read_only": True,
        "parallel_safe": True,
        "session_cacheable": True,
        "state_domains": ("web",),
    },
    "search_news_ddgs": {
        "read_only": True,
        "parallel_safe": True,
        "session_cacheable": True,
        "state_domains": ("web",),
    },
    "search_news_google": {
        "read_only": True,
        "parallel_safe": True,
        "session_cacheable": True,
        "state_domains": ("web",),
    },
    "expand_canvas_document": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("canvas",),
    },
    "batch_read_canvas_documents": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("canvas",),
    },
    "scroll_canvas_document": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("canvas",),
    },
    "search_canvas_document": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("canvas",),
    },
    "validate_canvas_document": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("canvas",),
    },
    "preview_canvas_changes": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("canvas",),
    },
    "read_scratchpad": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("memory",),
    },
    "read_file": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("workspace",),
    },
    "list_dir": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("workspace",),
    },
    "search_files": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("workspace",),
    },
    "validate_project_workspace": {
        "read_only": True,
        "parallel_safe": True,
        "state_domains": ("workspace",),
    },
    "import_github_repository_to_canvas": {
        "state_domains": ("canvas", "web"),
    },
    "preview_github_import_to_canvas": {
        "read_only": True,
        "parallel_safe": False,
        "state_domains": ("web",),
    },
}


def _normalize_runtime_tool_name_list(values) -> list[str]:
    normalized: list[str] = []
    for raw_value in values or []:
        tool_name = str(raw_value or "").strip()
        if tool_name and tool_name not in normalized:
            normalized.append(tool_name)
    return normalized


def _coerce_runtime_tool_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _build_tool_runtime_metadata() -> dict[str, dict]:
    metadata: dict[str, dict] = {}
    for tool in TOOL_SPECS:
        tool_name = str(tool.get("name") or "").strip()
        if not tool_name:
            continue
        entry = dict(_TOOL_RUNTIME_DEFAULTS)
        entry.update(_TOOL_RUNTIME_METADATA_OVERRIDES.get(tool_name, {}))
        entry["state_domains"] = tuple(dict.fromkeys(entry.get("state_domains") or ()))
        metadata[tool_name] = entry
    return metadata


TOOL_RUNTIME_METADATA = _build_tool_runtime_metadata()
WEB_TOOL_NAMES = frozenset(
    tool_name
    for tool_name, metadata in TOOL_RUNTIME_METADATA.items()
    if "web" in metadata.get("state_domains", ())
)
PARALLEL_SAFE_TOOL_NAMES = frozenset(
    tool_name
    for tool_name, metadata in TOOL_RUNTIME_METADATA.items()
    if metadata.get("parallel_safe") is True
)
PARALLEL_SAFE_READ_ONLY_TOOL_NAMES = tuple(
    tool_name
    for tool_name, metadata in TOOL_RUNTIME_METADATA.items()
    if metadata.get("parallel_safe") is True and metadata.get("read_only") is True
)
SESSION_CACHEABLE_TOOL_NAMES = frozenset(
    tool_name
    for tool_name, metadata in TOOL_RUNTIME_METADATA.items()
    if metadata.get("session_cacheable") is True
)
CANVAS_READ_BARRIER_TOOL_NAMES = frozenset(
    tool_name
    for tool_name, metadata in TOOL_RUNTIME_METADATA.items()
    if metadata.get("read_only") is True and "canvas" in metadata.get("state_domains", ())
)


def get_tool_runtime_metadata(tool_name: str) -> dict:
    normalized_tool_name = str(tool_name or "").strip()
    metadata = TOOL_RUNTIME_METADATA.get(normalized_tool_name)
    if metadata is None:
        return dict(_TOOL_RUNTIME_DEFAULTS)
    return dict(metadata)


def is_tool_parallel_safe(tool_name: str, tool_args: dict | None = None) -> bool:
    normalized_tool_name = str(tool_name or "").strip()
    metadata = TOOL_RUNTIME_METADATA.get(normalized_tool_name)
    if not metadata or metadata.get("parallel_safe") is not True:
        return False
    normalized_tool_args = tool_args if isinstance(tool_args, dict) else {}
    if normalized_tool_name in {"search_knowledge_base", "search_tool_memory"} and _coerce_runtime_tool_bool(
        normalized_tool_args.get("save_to_conversation_memory")
    ):
        return False
    return True


def is_tool_session_cacheable(tool_name: str) -> bool:
    return get_tool_runtime_metadata(tool_name).get("session_cacheable") is True


def get_parallel_safe_tool_names(tool_names=None, *, read_only_only: bool = False) -> list[str]:
    normalized_tool_names = _normalize_runtime_tool_name_list(tool_names)
    if not normalized_tool_names:
        normalized_tool_names = list(TOOL_RUNTIME_METADATA.keys())
    return [
        tool_name
        for tool_name in normalized_tool_names
        if is_tool_parallel_safe(tool_name)
        and (not read_only_only or get_tool_runtime_metadata(tool_name).get("read_only") is True)
    ]


def get_prompt_visible_tool_names(tool_names=None) -> list[str]:
    normalized_tool_names = _normalize_runtime_tool_name_list(tool_names)
    return [
        tool_name
        for tool_name in normalized_tool_names
        if get_tool_runtime_metadata(tool_name).get("prompt_visible") is not False
    ]


def get_ui_hidden_tool_names(tool_names=None) -> list[str]:
    normalized_tool_names = _normalize_runtime_tool_name_list(tool_names)
    return [
        tool_name
        for tool_name in normalized_tool_names
        if get_tool_runtime_metadata(tool_name).get("ui_hidden") is True
    ]


def _normalize_clarification_max_questions(value: int | None) -> int:
    try:
        normalized = int(value) if value is not None else CLARIFICATION_DEFAULT_MAX_QUESTIONS
    except (TypeError, ValueError):
        normalized = CLARIFICATION_DEFAULT_MAX_QUESTIONS
    return max(CLARIFICATION_QUESTION_LIMIT_MIN, min(CLARIFICATION_QUESTION_LIMIT_MAX, normalized))


def _normalize_search_tool_query_limit(value: int | None) -> int:
    try:
        normalized = int(value) if value is not None else DEFAULT_SEARCH_TOOL_QUERY_LIMIT
    except (TypeError, ValueError):
        normalized = DEFAULT_SEARCH_TOOL_QUERY_LIMIT
    return max(SEARCH_TOOL_QUERY_LIMIT_MIN, min(SEARCH_TOOL_QUERY_LIMIT_MAX, normalized))


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


def _build_search_query_limit_spec(tool: dict, search_tool_query_limit: int | None = None) -> dict:
    spec = copy.deepcopy(tool)
    tool_name = str(spec.get("name") or "").strip()
    if tool_name not in SEARCH_QUERY_LIMITED_TOOL_NAMES:
        return spec

    limit = _normalize_search_tool_query_limit(search_tool_query_limit)
    limit_range = f"1-{limit}"
    parameters = spec.get("parameters") if isinstance(spec.get("parameters"), dict) else {}
    properties = parameters.get("properties") if isinstance(parameters.get("properties"), dict) else {}
    queries_schema = properties.get("queries") if isinstance(properties.get("queries"), dict) else {}
    queries_schema["maxItems"] = limit

    if tool_name == "search_web":
        queries_schema["description"] = f"List of search queries to run ({limit_range} queries)."
    else:
        queries_schema["description"] = f"List of news search queries ({limit_range})."

    properties["queries"] = queries_schema
    parameters["properties"] = properties
    spec["parameters"] = parameters

    prompt = spec.get("prompt") if isinstance(spec.get("prompt"), dict) else {}
    prompt_inputs = prompt.get("inputs") if isinstance(prompt.get("inputs"), dict) else {}
    if tool_name == "search_web":
        prompt_inputs["queries"] = f"{limit_range} search queries"
    elif tool_name in {"search_news_ddgs", "search_news_google"}:
        prompt_inputs["queries"] = f"{limit_range} news queries"
    prompt["inputs"] = prompt_inputs

    guidance = str(prompt.get("guidance") or "").strip()
    replacements = {
        "search_web": (
            "Never pass more than 5 queries in a single call. If you need more search terms, split them across multiple search_web calls. ",
            f"Never pass more than {limit} queries in a single call. If you need more search terms, split them across multiple search_web calls. ",
        ),
        "search_news_ddgs": (
            "Never pass more than 5 queries in one call. If you need article details, follow up with fetch_url on the most relevant links instead of widening the same news query repeatedly. ",
            f"Never pass more than {limit} queries in one call. If you need article details, follow up with fetch_url on the most relevant links instead of widening the same news query repeatedly. ",
        ),
        "search_news_google": (
            "Never pass more than 5 queries in one call. After scanning the feed, fetch only the few links that are actually needed.",
            f"Never pass more than {limit} queries in one call. After scanning the feed, fetch only the few links that are actually needed.",
        ),
    }
    old_text, new_text = replacements.get(tool_name, ("", ""))
    if old_text and old_text in guidance:
        guidance = guidance.replace(old_text, new_text)
    else:
        limit_note = f" Stay within the configured {limit_range} query limit for a single call."
        if limit_note.strip() not in guidance:
            guidance = f"{guidance}{limit_note}".strip()
    prompt["guidance"] = guidance
    spec["prompt"] = prompt
    return spec


def get_enabled_tool_specs(
    active_tool_names: list[str],
    clarification_max_questions: int | None = None,
    search_tool_query_limit: int | None = None,
) -> list[dict]:
    active_set = set(active_tool_names or [])
    specs = [tool for tool in TOOL_SPECS if tool["name"] in active_set]
    if not RAG_ENABLED:
        specs = [tool for tool in specs if tool["name"] != "search_knowledge_base"]
    if not CONVERSATION_MEMORY_ENABLED:
        specs = [
            tool
            for tool in specs
            if tool["name"] not in {"save_to_conversation_memory", "delete_conversation_memory_entry"}
        ]
    return [
        _build_search_query_limit_spec(
            _build_clarification_spec(tool, clarification_max_questions),
            search_tool_query_limit,
        )
        for tool in specs
    ]


def resolve_runtime_tool_names(
    active_tool_names: list[str],
    canvas_documents: list[dict] | None = None,
    *,
    workspace_root: str | None = None,
) -> list[str]:
    """Return the subset of active_tool_names that are available given current runtime state.

    Only hard precondition gates apply:
    - Canvas document editing tools require an existing canvas document.
    - Text-addressable canvas tools are hidden when every canvas document is visual-only.
    - Editable canvas tools are hidden when no canvas document is editable.
    - Workspace file tools require a configured workspace_root.
    Everything else (web search, canvas creation, etc.) is always included.
    """
    names = list(active_tool_names or [])
    if not names:
        return []

    has_canvas_documents = bool(canvas_documents)
    has_text_addressable_canvas_documents = any(
        get_canvas_document_capabilities(document)["line_addressable"]
        for document in (canvas_documents or [])
        if isinstance(document, dict)
    )
    has_editable_canvas_documents = any(
        get_canvas_document_capabilities(document)["editable"]
        for document in (canvas_documents or [])
        if isinstance(document, dict)
    )
    runtime_names: list[str] = []
    for name in names:
        if name in CANVAS_DOCUMENT_TOOL_NAMES and not has_canvas_documents:
            continue
        if name in CANVAS_TEXT_ADDRESSABLE_TOOL_NAMES and not has_text_addressable_canvas_documents:
            continue
        if name in CANVAS_EDITABLE_TOOL_NAMES and not has_editable_canvas_documents:
            continue
        if name in WORKSPACE_TOOL_NAMES and not workspace_root:
            continue
        runtime_names.append(name)
    return runtime_names


def get_openai_tool_specs(
    active_tool_names: list[str],
    canvas_documents: list[dict] | None = None,
    clarification_max_questions: int | None = None,
    search_tool_query_limit: int | None = None,
    *,
    workspace_root: str | None = None,
) -> list[dict]:
    specs = []
    runtime_tool_names = resolve_runtime_tool_names(
        active_tool_names,
        canvas_documents=canvas_documents,
        workspace_root=workspace_root,
    )
    for tool in get_enabled_tool_specs(
        runtime_tool_names,
        clarification_max_questions=clarification_max_questions,
        search_tool_query_limit=search_tool_query_limit,
    ):
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
    search_tool_query_limit: int | None = None,
    *,
    workspace_root: str | None = None,
) -> list[dict] | None:
    tools = []
    runtime_tool_names = resolve_runtime_tool_names(
        active_tool_names,
        canvas_documents=canvas_documents,
        workspace_root=workspace_root,
    )
    for tool in get_enabled_tool_specs(
        runtime_tool_names,
        clarification_max_questions=clarification_max_questions,
        search_tool_query_limit=search_tool_query_limit,
    ):
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
