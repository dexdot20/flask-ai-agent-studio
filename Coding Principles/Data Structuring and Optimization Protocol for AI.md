**Purpose and Scope**
The primary objective is to define a data structure that enables the model to analyze event flows, historical actions, current states, and active requirements with maximum precision.

**Core Principles**
To optimize AI processing, data must not be presented as a raw text dump. It should be organized according to the following principles:
* **Chronological Integrity:** The sequence of events must remain intact.
* **Contextual Separation:** Historical data must be clearly distinguished from current information.
* **Single Source of Truth (SSoT):** Redundant information should be eliminated to prevent data noise.
* **Validity Filtering:** Deprecated or rejected requests must not be presented as active requirements.
* **Metadata Preservation:** Critical metadata that influences decision-making (timestamps, user roles, error codes, etc.) must be preserved.

**Formatting and Syntax Standards**
The following rules are mandatory for accurate data parsing by the model:
* **Markdown Headers:** Use `#` and `##` to define section hierarchies.
* **Concise Bullet Points:** Avoid dense paragraphs; present one core idea per line.
* **Tabular Structures:** Use tables for complex event flows (Time, Action, Result).
* **Role Isolation:** Keep system commands, tool outputs, and user requests in separate code blocks.
* **Data Sanitization:** Remove duplicate tokens, excessive whitespace, and obsolete intermediate text.
* **JSON vs. Markdown:** Use JSON for precise machine-readable payloads; use Markdown for human-AI readability.

**Data Layers (Relational Schema)**
Data organization should be structured into three isolated layers:
1. **Source Layer:** Raw transcripts, log records, and database outputs.
2. **Interpretation Layer:** Reordered events, extracted user intent, and historical decisions.
3. **Action Layer:** Commands, expected outcomes, and validation plans.