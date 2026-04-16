# ruff: noqa: I001
"""Tests for GitHub repository import into Canvas.

Covers:
- github_import_service: URL parsing, path scoring, archive extraction, path filtering
- agent-side _run_import_github_repository_to_canvas: confirmation gate
- Canvas POST path field propagation
- /api/conversations/<id>/canvas/import-github endpoint
- Sub-agent tool inheritance from parent runtime context
- Tool registry: new tool spec and metadata registration
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("RAG_ENABLED", "false")
os.environ.setdefault("DEEPSEEK_API_KEY", "")
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")

from tests.support.app_harness import BaseAppRoutesTestCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zip(files: dict[str, str], root_prefix: str = "owner-repo-abc123") -> bytes:
    """Build an in-memory ZIP archive resembling a GitHub zipball."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.mkdir(f"{root_prefix}/")
        for path, content in files.items():
            zf.writestr(f"{root_prefix}/{path}", content)
    return buf.getvalue()


def _patch_github_network(
    archive_bytes: bytes,
    *,
    default_branch: str = "main",
    repo_status: int = 200,
    archive_status: int = 200,
):
    """Return a requests.get mock that satisfies both GitHub API and archive calls."""
    repo_payload = json.dumps({"default_branch": default_branch}).encode()

    def _get(url, **kwargs):
        mock_resp = MagicMock()
        if "api.github.com" in url:
            mock_resp.status_code = repo_status
            mock_resp.json.return_value = {"default_branch": default_branch}
        elif "codeload.github.com" in url:
            mock_resp.status_code = archive_status
            chunks = [archive_bytes[i : i + 32768] for i in range(0, len(archive_bytes), 32768)]
            mock_resp.iter_content.return_value = chunks or [b""]
        else:
            mock_resp.status_code = 404
            mock_resp.iter_content.return_value = []
        return mock_resp

    return patch("github_import_service.requests.get", side_effect=_get)


# ---------------------------------------------------------------------------
# Unit: URL parsing
# ---------------------------------------------------------------------------


class TestGithubImportUrlParsing(unittest.TestCase):
    def setUp(self):
        from github_import_service import _parse_github_repository_url

        self._parse = _parse_github_repository_url

    def test_simple_repo_url_parsed(self):
        result = self._parse("https://github.com/owner/my-repo")
        self.assertEqual(result["owner"], "owner")
        self.assertEqual(result["repo"], "my-repo")
        self.assertEqual(result["ref"], "")
        self.assertEqual(result["subdir"], "")

    def test_tree_url_with_branch_and_subdir_parsed(self):
        result = self._parse("https://github.com/owner/repo/tree/main/src/utils")
        self.assertEqual(result["owner"], "owner")
        self.assertEqual(result["repo"], "repo")
        self.assertEqual(result["ref"], "main")
        self.assertEqual(result["subdir"], "src/utils")

    def test_git_suffix_stripped(self):
        result = self._parse("https://github.com/owner/repo.git")
        self.assertEqual(result["repo"], "repo")

    def test_non_github_host_raises(self):
        from github_import_service import _parse_github_repository_url

        with self.assertRaises(ValueError):
            _parse_github_repository_url("https://gitlab.com/owner/repo")

    def test_missing_repo_name_raises(self):
        from github_import_service import _parse_github_repository_url

        with self.assertRaises(ValueError):
            _parse_github_repository_url("https://github.com/owner")


# ---------------------------------------------------------------------------
# Unit: path normalization and scoring
# ---------------------------------------------------------------------------


class TestGithubImportPathHelpers(unittest.TestCase):
    def test_normalize_repo_path_traversal_blocked(self):
        from github_import_service import _normalize_repo_path

        self.assertEqual(_normalize_repo_path("../etc/passwd"), "etc/passwd")
        self.assertEqual(_normalize_repo_path("a/../../b"), "b")

    def test_should_skip_path_ignores_node_modules(self):
        from github_import_service import _should_skip_path

        self.assertTrue(_should_skip_path("node_modules/lodash/index.js"))
        self.assertFalse(_should_skip_path("src/utils/index.js"))

    def test_score_readme_higher_than_nested_file(self):
        from github_import_service import _score_repo_file

        readme_score = _score_repo_file("README.md")
        nested_score = _score_repo_file("src/lib/utils/helpers/string.ts")
        self.assertGreater(readme_score, nested_score)

    def test_score_pyproject_toml_high(self):
        from github_import_service import _score_repo_file

        self.assertGreater(_score_repo_file("pyproject.toml"), _score_repo_file("src/nested/config/values.py"))

    def test_binary_file_excluded(self):
        from github_import_service import _looks_like_text_file

        self.assertFalse(_looks_like_text_file("image.png", b"\x89PNG\r\n\x1a\n"))
        self.assertFalse(_looks_like_text_file("font.ttf", b"\x00\x01\x00\x00"))
        self.assertFalse(_looks_like_text_file("archive.zip", b"PK\x03\x04"))

    def test_text_file_included(self):
        from github_import_service import _looks_like_text_file

        self.assertTrue(_looks_like_text_file("app.py", b"print('hello')"))
        self.assertTrue(_looks_like_text_file("readme.md", b"# Title\n"))


# ---------------------------------------------------------------------------
# Unit: archive extraction
# ---------------------------------------------------------------------------


class TestGithubImportArchiveExtraction(unittest.TestCase):
    def _make_archive(self):
        return _make_zip(
            {
                "README.md": "# Hello\n",
                "src/utils/helpers.ts": "export const noop = () => {};\n",
                "src/lib/config/settings.json": '{"debug": false}\n',
                "node_modules/lodash/index.js": "// lodash",
                "dist/bundle.js": "// bundle",
                ".git/config": "[core]",
            }
        )

    def test_ignored_directories_excluded(self):
        from github_import_service import load_github_repo_canvas_entries

        archive_bytes = self._make_archive()
        with _patch_github_network(archive_bytes):
            result = load_github_repo_canvas_entries("https://github.com/owner/repo")

        document_paths = {doc["path"] for doc in result["documents"]}
        self.assertIn("README.md", document_paths)
        self.assertIn("src/utils/helpers.ts", document_paths)
        self.assertNotIn("node_modules/lodash/index.js", document_paths)
        self.assertNotIn("dist/bundle.js", document_paths)
        self.assertNotIn(".git/config", document_paths)

    def test_primary_document_is_highest_scoring(self):
        from github_import_service import load_github_repo_canvas_entries

        archive_bytes = self._make_archive()
        with _patch_github_network(archive_bytes):
            result = load_github_repo_canvas_entries("https://github.com/owner/repo")

        self.assertEqual(result["primary_document_path"], "README.md")

    def test_project_id_derived_from_owner_repo(self):
        from github_import_service import load_github_repo_canvas_entries

        archive_bytes = self._make_archive()
        with _patch_github_network(archive_bytes):
            result = load_github_repo_canvas_entries("https://github.com/MyOrg/MyRepo")

        self.assertIn("myorg", result["project_id"])
        self.assertIn("myrepo", result["project_id"])

    def test_empty_archive_raises(self):
        from github_import_service import load_github_repo_canvas_entries

        empty_zip = _make_zip({})
        with _patch_github_network(empty_zip):
            with self.assertRaises(ValueError):
                load_github_repo_canvas_entries("https://github.com/owner/repo")

    def test_bad_zip_raises(self):
        from github_import_service import load_github_repo_canvas_entries

        with _patch_github_network(b"not a zip file"):
            with self.assertRaises(ValueError):
                load_github_repo_canvas_entries("https://github.com/owner/repo")

    def test_api_error_raises(self):
        from github_import_service import load_github_repo_canvas_entries

        with _patch_github_network(b"", repo_status=403):
            with self.assertRaises(ValueError):
                load_github_repo_canvas_entries("https://github.com/owner/repo")


# ---------------------------------------------------------------------------
# Unit: agent tool executor — confirmation gate
# ---------------------------------------------------------------------------


class TestAgentGithubImportTool(unittest.TestCase):
    def _run_tool(self, args: dict, canvas_documents: list | None = None):
        from agent import _run_import_github_repository_to_canvas
        from canvas_service import create_canvas_runtime_state

        canvas_docs = canvas_documents or []
        runtime_state = {"canvas": create_canvas_runtime_state(canvas_docs)}
        return _run_import_github_repository_to_canvas(args, runtime_state)

    def _run_preview_tool(self, args: dict):
        from agent import _run_preview_github_import_to_canvas

        return _run_preview_github_import_to_canvas(args, {})

    def test_missing_url_returns_error(self):
        result, summary = self._run_tool({})
        self.assertEqual(result.get("status"), "error")

    def test_valid_url_executes_import(self):
        archive_bytes = _make_zip({"README.md": "# Title\n"})
        with _patch_github_network(archive_bytes):
            result, summary = self._run_tool({"url": "https://github.com/owner/repo"})
        self.assertNotEqual(result.get("status"), "error")
        self.assertGreater(int(result.get("imported_count") or 0), 0)
        self.assertIn("imported", summary.lower())

    def test_preview_missing_url_returns_error(self):
        result, summary = self._run_preview_tool({})
        self.assertEqual(result.get("status"), "error")

    def test_preview_returns_file_listing_without_canvas_mutation(self):
        from canvas_service import create_canvas_runtime_state

        archive_bytes = _make_zip({"README.md": "# Title\n", "src/utils.py": "pass\n"})
        runtime_state = {"canvas": create_canvas_runtime_state([])}
        with _patch_github_network(archive_bytes):
            result, summary = self._run_preview_tool({"url": "https://github.com/owner/repo"})

        self.assertIn("files", result)
        self.assertGreater(int(result.get("total_files") or 0), 0)
        self.assertIn("preview", summary.lower())
        # Canvas must not have been mutated.
        canvas_docs = runtime_state["canvas"].get("documents") or []
        self.assertEqual(len(canvas_docs), 0)

    def test_preview_primary_document_path_returned(self):
        archive_bytes = _make_zip({"README.md": "# Title\n", "src/utils.py": "pass\n"})
        with _patch_github_network(archive_bytes):
            result, _ = self._run_preview_tool({"url": "https://github.com/owner/repo"})
        self.assertEqual(result.get("primary_document_path"), "README.md")


# ---------------------------------------------------------------------------
# Unit: sub-agent tool resolution inherits parent tools
# ---------------------------------------------------------------------------


class TestSubAgentToolResolutionInheritsParent(unittest.TestCase):
    def test_parent_tool_names_override_defaults(self):
        from agent import _resolve_sub_agent_tool_names

        parent_tools = ["search_web", "fetch_url", "read_scratchpad"]
        result = _resolve_sub_agent_tool_names({}, parent_tool_names=parent_tools)
        # sub_agent never included in child
        self.assertNotIn("sub_agent", result)
        # All parent read-only tools should pass through
        for tool in parent_tools:
            self.assertIn(tool, result)

    def test_sub_agent_stripped_even_if_in_parent_list(self):
        from agent import _resolve_sub_agent_tool_names

        parent_tools = ["search_web", "sub_agent", "fetch_url"]
        result = _resolve_sub_agent_tool_names({}, parent_tool_names=parent_tools)
        self.assertNotIn("sub_agent", result)
        self.assertIn("search_web", result)

    def test_empty_parent_falls_back_to_defaults(self):
        from agent import _resolve_sub_agent_tool_names, SUB_AGENT_ALLOWED_TOOL_NAMES

        result = _resolve_sub_agent_tool_names({}, parent_tool_names=[])
        self.assertNotIn("sub_agent", result)
        # Should contain some expected default read-only tools
        self.assertTrue(any(t in result for t in SUB_AGENT_ALLOWED_TOOL_NAMES if t != "sub_agent"))

    def test_none_parent_falls_back_to_defaults(self):
        from agent import _resolve_sub_agent_tool_names, SUB_AGENT_ALLOWED_TOOL_NAMES

        result = _resolve_sub_agent_tool_names({}, parent_tool_names=None)
        # Should contain some expected default read-only tools
        self.assertTrue(any(t in result for t in SUB_AGENT_ALLOWED_TOOL_NAMES if t != "sub_agent"))


# ---------------------------------------------------------------------------
# Unit: tool registry registration
# ---------------------------------------------------------------------------


class TestGithubImportToolRegistration(unittest.TestCase):
    def test_import_tool_spec_registered(self):
        from tool_registry import TOOL_SPEC_BY_NAME

        self.assertIn("import_github_repository_to_canvas", TOOL_SPEC_BY_NAME)

    def test_preview_tool_spec_registered(self):
        from tool_registry import TOOL_SPEC_BY_NAME

        self.assertIn("preview_github_import_to_canvas", TOOL_SPEC_BY_NAME)

    def test_import_tool_spec_has_no_confirmed_param(self):
        from tool_registry import TOOL_SPEC_BY_NAME

        spec = TOOL_SPEC_BY_NAME["import_github_repository_to_canvas"]
        self.assertNotIn("confirmed", spec["parameters"]["properties"])

    def test_import_tool_spec_requires_url(self):
        from tool_registry import TOOL_SPEC_BY_NAME

        spec = TOOL_SPEC_BY_NAME["import_github_repository_to_canvas"]
        self.assertIn("url", spec["parameters"]["properties"])
        self.assertIn("url", spec["parameters"]["required"])

    def test_preview_tool_spec_requires_url(self):
        from tool_registry import TOOL_SPEC_BY_NAME

        spec = TOOL_SPEC_BY_NAME["preview_github_import_to_canvas"]
        self.assertIn("url", spec["parameters"]["properties"])
        self.assertIn("url", spec["parameters"]["required"])

    def test_import_tool_metadata_declares_canvas_domain(self):
        from tool_registry import get_tool_runtime_metadata

        metadata = get_tool_runtime_metadata("import_github_repository_to_canvas")
        self.assertIn("canvas", metadata.get("state_domains") or ())

    def test_preview_tool_metadata_is_read_only(self):
        from tool_registry import get_tool_runtime_metadata

        metadata = get_tool_runtime_metadata("preview_github_import_to_canvas")
        self.assertTrue(metadata.get("read_only") is True)

    def test_import_tool_is_not_read_only(self):
        from tool_registry import get_tool_runtime_metadata

        metadata = get_tool_runtime_metadata("import_github_repository_to_canvas")
        self.assertNotEqual(metadata.get("read_only"), True)

    def test_tools_in_canvas_section_of_permission_options(self):
        from routes.pages import build_tool_permission_sections

        canvas_section = next(
            (s for s in build_tool_permission_sections() if s["key"] == "canvas"),
            None,
        )
        self.assertIsNotNone(canvas_section)
        canvas_tool_names = {t["name"] for t in canvas_section.get("tools", [])}
        self.assertIn("import_github_repository_to_canvas", canvas_tool_names)
        self.assertIn("preview_github_import_to_canvas", canvas_tool_names)

    def test_both_tools_have_labels(self):
        from routes.pages import TOOL_PERMISSION_LABELS

        self.assertIn("import_github_repository_to_canvas", TOOL_PERMISSION_LABELS)
        self.assertIn("preview_github_import_to_canvas", TOOL_PERMISSION_LABELS)
        self.assertIn("GitHub", TOOL_PERMISSION_LABELS["import_github_repository_to_canvas"])
        self.assertIn("GitHub", TOOL_PERMISSION_LABELS["preview_github_import_to_canvas"])


# ---------------------------------------------------------------------------
# Integration: Canvas POST with path field
# ---------------------------------------------------------------------------


class TestCanvasCreateWithPath(BaseAppRoutesTestCase):
    def test_canvas_post_stores_path_in_document(self):
        conv_id = self._create_conversation()
        response = self.client.post(
            f"/api/conversations/{conv_id}/canvas",
            json={
                "title": "app.py",
                "content": "print('hello')\n",
                "format": "code",
                "path": "src/app.py",
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        doc = payload.get("document") or {}
        self.assertEqual(doc.get("path"), "src/app.py")

    def test_canvas_post_without_path_still_works(self):
        conv_id = self._create_conversation()
        response = self.client.post(
            f"/api/conversations/{conv_id}/canvas",
            json={
                "title": "notes.md",
                "content": "",
                "format": "markdown",
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertIn("document", payload)


# ---------------------------------------------------------------------------
# Integration: GitHub import endpoint
# ---------------------------------------------------------------------------


class TestGithubImportEndpoint(BaseAppRoutesTestCase):
    def _archive(self, files: dict | None = None) -> bytes:
        return _make_zip(files or {"README.md": "# Title\n", "app.py": "print('hello')\n"})

    def test_endpoint_requires_url(self):
        conv_id = self._create_conversation()
        response = self.client.post(
            f"/api/conversations/{conv_id}/canvas/import-github",
            json={},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIn("error", payload)

    def test_endpoint_returns_404_for_missing_conversation(self):
        response = self.client.post(
            "/api/conversations/99999/canvas/import-github",
            json={"url": "https://github.com/owner/repo"},
        )
        self.assertEqual(response.status_code, 404)

    def test_endpoint_imports_files_into_canvas(self):
        conv_id = self._create_conversation()
        archive_bytes = self._archive()
        with _patch_github_network(archive_bytes):
            response = self.client.post(
                f"/api/conversations/{conv_id}/canvas/import-github",
                json={"url": "https://github.com/owner/repo"},
            )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertGreater(int(payload.get("imported_count") or 0), 0)
        self.assertIsNotNone(payload.get("active_document_id"))
        self.assertIsInstance(payload.get("documents"), list)
        self.assertGreater(len(payload["documents"]), 0)

    def test_endpoint_selects_readme_as_primary_document(self):
        conv_id = self._create_conversation()
        archive_bytes = self._archive({"README.md": "# Hello\n", "src/utils.py": "pass\n"})
        with _patch_github_network(archive_bytes):
            response = self.client.post(
                f"/api/conversations/{conv_id}/canvas/import-github",
                json={"url": "https://github.com/owner/repo"},
            )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload.get("primary_document_path"), "README.md")

    def test_endpoint_returns_messages_with_canvas_state(self):
        conv_id = self._create_conversation()
        archive_bytes = self._archive()
        with _patch_github_network(archive_bytes):
            response = self.client.post(
                f"/api/conversations/{conv_id}/canvas/import-github",
                json={"url": "https://github.com/owner/repo"},
            )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertIsInstance(payload.get("messages"), list)

    def test_endpoint_persists_canvas_to_conversation(self):
        conv_id = self._create_conversation()
        archive_bytes = self._archive({"main.py": "print('hi')\n"})
        with _patch_github_network(archive_bytes):
            self.client.post(
                f"/api/conversations/{conv_id}/canvas/import-github",
                json={"url": "https://github.com/owner/repo"},
            )

        conversation_response = self.client.get(f"/api/conversations/{conv_id}")
        self.assertEqual(conversation_response.status_code, 200)
        messages = conversation_response.get_json()["messages"]
        canvas_docs = [
            doc
            for msg in messages
            if msg.get("metadata", {}).get("canvas_documents")
            for doc in msg["metadata"]["canvas_documents"]
        ]
        self.assertGreater(len(canvas_docs), 0)

    def test_endpoint_invalid_url_returns_400(self):
        conv_id = self._create_conversation()
        response = self.client.post(
            f"/api/conversations/{conv_id}/canvas/import-github",
            json={"url": "https://gitlab.com/owner/repo"},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIn("error", payload)

    def test_endpoint_returns_project_id_and_workspace_id(self):
        conv_id = self._create_conversation()
        archive_bytes = self._archive()
        with _patch_github_network(archive_bytes):
            response = self.client.post(
                f"/api/conversations/{conv_id}/canvas/import-github",
                json={"url": "https://github.com/owner/repo"},
            )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertIsNotNone(payload.get("project_id"))
        self.assertIsNotNone(payload.get("workspace_id"))


if __name__ == "__main__":
    unittest.main()
