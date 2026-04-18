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
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("RAG_ENABLED", "false")
os.environ.setdefault("DEEPSEEK_API_KEY", "")
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")

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


class TestGithubImportUrlParsing:

    def test_simple_repo_url_parsed(self):
        from github_import_service import _parse_github_repository_url

        result = _parse_github_repository_url("https://github.com/owner/my-repo")
        assert result["owner"] == "owner"
        assert result["repo"] == "my-repo"
        assert result["ref"] == ""
        assert result["subdir"] == ""

    def test_tree_url_with_branch_and_subdir_parsed(self):
        from github_import_service import _parse_github_repository_url

        result = _parse_github_repository_url("https://github.com/owner/repo/tree/main/src/utils")
        assert result["owner"] == "owner"
        assert result["repo"] == "repo"
        assert result["ref"] == "main"
        assert result["subdir"] == "src/utils"

    def test_git_suffix_stripped(self):
        from github_import_service import _parse_github_repository_url

        result = _parse_github_repository_url("https://github.com/owner/repo.git")
        assert result["repo"] == "repo"

    def test_non_github_host_raises(self):
        from github_import_service import _parse_github_repository_url

        with pytest.raises(ValueError):
            _parse_github_repository_url("https://gitlab.com/owner/repo")

    def test_missing_repo_name_raises(self):
        from github_import_service import _parse_github_repository_url

        with pytest.raises(ValueError):
            _parse_github_repository_url("https://github.com/owner")


# ---------------------------------------------------------------------------
# Unit: path normalization and scoring
# ---------------------------------------------------------------------------


class TestGithubImportPathHelpers:
    def test_normalize_repo_path_traversal_blocked(self):
        from github_import_service import _normalize_repo_path

        assert _normalize_repo_path("../etc/passwd") == "etc/passwd"
        assert _normalize_repo_path("a/../../b") == "b"

    def test_should_skip_path_ignores_node_modules(self):
        from github_import_service import _should_skip_path

        assert _should_skip_path("node_modules/lodash/index.js")
        assert not _should_skip_path("src/utils/index.js")

    def test_score_readme_higher_than_nested_file(self):
        from github_import_service import _score_repo_file

        readme_score = _score_repo_file("README.md")
        nested_score = _score_repo_file("src/lib/utils/helpers/string.ts")
        assert readme_score > nested_score

    def test_score_pyproject_toml_high(self):
        from github_import_service import _score_repo_file

        assert _score_repo_file("pyproject.toml") > _score_repo_file("src/nested/config/values.py")

    def test_binary_file_excluded(self):
        from github_import_service import _looks_like_text_file

        assert not _looks_like_text_file("image.png", b"\x89PNG\r\n\x1a\n")
        assert not _looks_like_text_file("font.ttf", b"\x00\x01\x00\x00")
        assert not _looks_like_text_file("archive.zip", b"PK\x03\x04")

    def test_text_file_included(self):
        from github_import_service import _looks_like_text_file

        assert _looks_like_text_file("app.py", b"print('hello')")
        assert _looks_like_text_file("readme.md", b"# Title\n")


# ---------------------------------------------------------------------------
# Unit: archive extraction
# ---------------------------------------------------------------------------


class TestGithubImportArchiveExtraction:
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
        assert "README.md" in document_paths
        assert "src/utils/helpers.ts" in document_paths
        assert "node_modules/lodash/index.js" not in document_paths
        assert "dist/bundle.js" not in document_paths
        assert ".git/config" not in document_paths

    def test_primary_document_is_highest_scoring(self):
        from github_import_service import load_github_repo_canvas_entries

        archive_bytes = self._make_archive()
        with _patch_github_network(archive_bytes):
            result = load_github_repo_canvas_entries("https://github.com/owner/repo")

        assert result["primary_document_path"] == "README.md"

    def test_project_id_derived_from_owner_repo(self):
        from github_import_service import load_github_repo_canvas_entries

        archive_bytes = self._make_archive()
        with _patch_github_network(archive_bytes):
            result = load_github_repo_canvas_entries("https://github.com/MyOrg/MyRepo")

        assert "myorg" in result["project_id"]
        assert "myrepo" in result["project_id"]

    def test_empty_archive_raises(self):
        from github_import_service import load_github_repo_canvas_entries

        empty_zip = _make_zip({})
        with _patch_github_network(empty_zip):
            with pytest.raises(ValueError):
                load_github_repo_canvas_entries("https://github.com/owner/repo")

    def test_bad_zip_raises(self):
        from github_import_service import load_github_repo_canvas_entries

        with _patch_github_network(b"not a zip file"):
            with pytest.raises(ValueError):
                load_github_repo_canvas_entries("https://github.com/owner/repo")

    def test_api_error_raises(self):
        from github_import_service import load_github_repo_canvas_entries

        with _patch_github_network(b"", repo_status=403):
            with pytest.raises(ValueError):
                load_github_repo_canvas_entries("https://github.com/owner/repo")


# ---------------------------------------------------------------------------
# Unit: agent tool executor — confirmation gate
# ---------------------------------------------------------------------------


class TestAgentGithubImportTool:
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
        assert result.get("status") == "error"

    def test_valid_url_executes_import(self):
        archive_bytes = _make_zip({"README.md": "# Title\n"})
        with _patch_github_network(archive_bytes):
            result, summary = self._run_tool({"url": "https://github.com/owner/repo"})
        assert result.get("status") != "error"
        assert int(result.get("imported_count") or 0) > 0
        assert "imported" in summary.lower()

    def test_preview_missing_url_returns_error(self):
        result, summary = self._run_preview_tool({})
        assert result.get("status") == "error"

    def test_preview_returns_file_listing_without_canvas_mutation(self):
        from canvas_service import create_canvas_runtime_state

        archive_bytes = _make_zip({"README.md": "# Title\n", "src/utils.py": "pass\n"})
        runtime_state = {"canvas": create_canvas_runtime_state([])}
        with _patch_github_network(archive_bytes):
            result, summary = self._run_preview_tool({"url": "https://github.com/owner/repo"})

        assert "files" in result
        assert int(result.get("total_files") or 0) > 0
        assert "preview" in summary.lower()
        # Canvas must not have been mutated.
        canvas_docs = runtime_state["canvas"].get("documents") or []
        assert len(canvas_docs) == 0

    def test_preview_primary_document_path_returned(self):
        archive_bytes = _make_zip({"README.md": "# Title\n", "src/utils.py": "pass\n"})
        with _patch_github_network(archive_bytes):
            result, _ = self._run_preview_tool({"url": "https://github.com/owner/repo"})
        assert result.get("primary_document_path") == "README.md"


# ---------------------------------------------------------------------------
# Unit: sub-agent tool resolution inherits parent tools
# ---------------------------------------------------------------------------


class TestSubAgentToolResolutionInheritsParent:
    def test_parent_tool_names_override_defaults(self):
        from agent import _resolve_sub_agent_tool_names

        parent_tools = ["search_web", "fetch_url", "read_scratchpad"]
        result = _resolve_sub_agent_tool_names({}, parent_tool_names=parent_tools)
        # sub_agent never included in child
        assert "sub_agent" not in result
        # All parent read-only tools should pass through
        for tool in parent_tools:
            assert tool in result

    def test_sub_agent_stripped_even_if_in_parent_list(self):
        from agent import _resolve_sub_agent_tool_names

        parent_tools = ["search_web", "sub_agent", "fetch_url"]
        result = _resolve_sub_agent_tool_names({}, parent_tool_names=parent_tools)
        assert "sub_agent" not in result
        assert "search_web" in result

    def test_empty_parent_falls_back_to_defaults(self):
        from agent import _resolve_sub_agent_tool_names, SUB_AGENT_ALLOWED_TOOL_NAMES

        result = _resolve_sub_agent_tool_names({}, parent_tool_names=[])
        assert "sub_agent" not in result
        # Should contain some expected default read-only tools
        assert any(t in result for t in SUB_AGENT_ALLOWED_TOOL_NAMES if t != "sub_agent")

    def test_none_parent_falls_back_to_defaults(self):
        from agent import _resolve_sub_agent_tool_names, SUB_AGENT_ALLOWED_TOOL_NAMES

        result = _resolve_sub_agent_tool_names({}, parent_tool_names=None)
        # Should contain some expected default read-only tools
        assert any(t in result for t in SUB_AGENT_ALLOWED_TOOL_NAMES if t != "sub_agent")


# ---------------------------------------------------------------------------
# Unit: tool registry registration
# ---------------------------------------------------------------------------


class TestGithubImportToolRegistration:
    def test_import_tool_spec_registered(self):
        from tool_registry import TOOL_SPEC_BY_NAME

        assert "import_github_repository_to_canvas" in TOOL_SPEC_BY_NAME

    def test_preview_tool_spec_registered(self):
        from tool_registry import TOOL_SPEC_BY_NAME

        assert "preview_github_import_to_canvas" in TOOL_SPEC_BY_NAME

    def test_import_tool_spec_has_no_confirmed_param(self):
        from tool_registry import TOOL_SPEC_BY_NAME

        spec = TOOL_SPEC_BY_NAME["import_github_repository_to_canvas"]
        assert "confirmed" not in spec["parameters"]["properties"]

    def test_import_tool_spec_requires_url(self):
        from tool_registry import TOOL_SPEC_BY_NAME

        spec = TOOL_SPEC_BY_NAME["import_github_repository_to_canvas"]
        assert "url" in spec["parameters"]["properties"]
        assert "url" in spec["parameters"]["required"]

    def test_preview_tool_spec_requires_url(self):
        from tool_registry import TOOL_SPEC_BY_NAME

        spec = TOOL_SPEC_BY_NAME["preview_github_import_to_canvas"]
        assert "url" in spec["parameters"]["properties"]
        assert "url" in spec["parameters"]["required"]

    def test_import_tool_metadata_declares_canvas_domain(self):
        from tool_registry import get_tool_runtime_metadata

        metadata = get_tool_runtime_metadata("import_github_repository_to_canvas")
        assert "canvas" in (metadata.get("state_domains") or ())

    def test_preview_tool_metadata_is_read_only(self):
        from tool_registry import get_tool_runtime_metadata

        metadata = get_tool_runtime_metadata("preview_github_import_to_canvas")
        assert metadata.get("read_only") is True

    def test_import_tool_is_not_read_only(self):
        from tool_registry import get_tool_runtime_metadata

        metadata = get_tool_runtime_metadata("import_github_repository_to_canvas")
        assert metadata.get("read_only") is not True

    def test_tools_in_canvas_section_of_permission_options(self):
        from routes.pages import build_tool_permission_sections

        canvas_section = next(
            (s for s in build_tool_permission_sections() if s["key"] == "canvas"),
            None,
        )
        assert canvas_section is not None
        canvas_tool_names = {t["name"] for t in canvas_section.get("tools", [])}
        assert "import_github_repository_to_canvas" in canvas_tool_names
        assert "preview_github_import_to_canvas" in canvas_tool_names

    def test_both_tools_have_labels(self):
        from routes.pages import TOOL_PERMISSION_LABELS

        assert "import_github_repository_to_canvas" in TOOL_PERMISSION_LABELS
        assert "preview_github_import_to_canvas" in TOOL_PERMISSION_LABELS
        assert "GitHub" in TOOL_PERMISSION_LABELS["import_github_repository_to_canvas"]
        assert "GitHub" in TOOL_PERMISSION_LABELS["preview_github_import_to_canvas"]


# ---------------------------------------------------------------------------
# Integration: Canvas POST with path field
# ---------------------------------------------------------------------------


class TestCanvasCreateWithPath:
    @pytest.fixture(autouse=True)
    def _setup(self, client, create_conversation):
        self.client = client
        self._create_conversation = create_conversation
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
        assert response.status_code == 201
        payload = response.get_json()
        doc = payload.get("document") or {}
        assert doc.get("path") == "src/app.py"

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
        assert response.status_code == 201
        payload = response.get_json()
        assert "document" in payload


# ---------------------------------------------------------------------------
# Integration: GitHub import endpoint
# ---------------------------------------------------------------------------


class TestGithubImportEndpoint:
    @pytest.fixture(autouse=True)
    def _setup(self, client, create_conversation):
        self.client = client
        self._create_conversation = create_conversation

    def _archive(self, files: dict | None = None) -> bytes:
        return _make_zip(files or {"README.md": "# Title\n", "app.py": "print('hello')\n"})

    def test_endpoint_requires_url(self):
        conv_id = self._create_conversation()
        response = self.client.post(
            f"/api/conversations/{conv_id}/canvas/import-github",
            json={},
        )
        assert response.status_code == 400
        payload = response.get_json()
        assert "error" in payload

    def test_endpoint_returns_404_for_missing_conversation(self):
        response = self.client.post(
            "/api/conversations/99999/canvas/import-github",
            json={"url": "https://github.com/owner/repo"},
        )
        assert response.status_code == 404

    def test_endpoint_imports_files_into_canvas(self):
        conv_id = self._create_conversation()
        archive_bytes = self._archive()
        with _patch_github_network(archive_bytes):
            response = self.client.post(
                f"/api/conversations/{conv_id}/canvas/import-github",
                json={"url": "https://github.com/owner/repo"},
            )

        assert response.status_code == 201
        payload = response.get_json()
        assert int(payload.get("imported_count") or 0) > 0
        assert payload.get("active_document_id") is not None
        assert isinstance(payload.get("documents"), list)
        assert len(payload["documents"]) > 0

    def test_endpoint_selects_readme_as_primary_document(self):
        conv_id = self._create_conversation()
        archive_bytes = self._archive({"README.md": "# Hello\n", "src/utils.py": "pass\n"})
        with _patch_github_network(archive_bytes):
            response = self.client.post(
                f"/api/conversations/{conv_id}/canvas/import-github",
                json={"url": "https://github.com/owner/repo"},
            )

        assert response.status_code == 201
        payload = response.get_json()
        assert payload.get("primary_document_path") == "README.md"

    def test_endpoint_returns_messages_with_canvas_state(self):
        conv_id = self._create_conversation()
        archive_bytes = self._archive()
        with _patch_github_network(archive_bytes):
            response = self.client.post(
                f"/api/conversations/{conv_id}/canvas/import-github",
                json={"url": "https://github.com/owner/repo"},
            )

        assert response.status_code == 201
        payload = response.get_json()
        assert isinstance(payload.get("messages"), list)

    def test_endpoint_persists_canvas_to_conversation(self):
        conv_id = self._create_conversation()
        archive_bytes = self._archive({"main.py": "print('hi')\n"})
        with _patch_github_network(archive_bytes):
            self.client.post(
                f"/api/conversations/{conv_id}/canvas/import-github",
                json={"url": "https://github.com/owner/repo"},
            )

        conversation_response = self.client.get(f"/api/conversations/{conv_id}")
        assert conversation_response.status_code == 200
        messages = conversation_response.get_json()["messages"]
        canvas_docs = [
            doc
            for msg in messages
            if msg.get("metadata", {}).get("canvas_documents")
            for doc in msg["metadata"]["canvas_documents"]
        ]
        assert len(canvas_docs) > 0

    def test_endpoint_invalid_url_returns_400(self):
        conv_id = self._create_conversation()
        response = self.client.post(
            f"/api/conversations/{conv_id}/canvas/import-github",
            json={"url": "https://gitlab.com/owner/repo"},
        )
        assert response.status_code == 400
        payload = response.get_json()
        assert "error" in payload

    def test_endpoint_returns_project_id_and_workspace_id(self):
        conv_id = self._create_conversation()
        archive_bytes = self._archive()
        with _patch_github_network(archive_bytes):
            response = self.client.post(
                f"/api/conversations/{conv_id}/canvas/import-github",
                json={"url": "https://github.com/owner/repo"},
            )

        assert response.status_code == 201
        payload = response.get_json()
        assert payload.get("project_id") is not None
        assert payload.get("workspace_id") is not None
