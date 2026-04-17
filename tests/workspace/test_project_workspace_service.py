from __future__ import annotations

from pathlib import Path

import pytest

from project_workspace_service import (
    WORKSPACE_HISTORY_DIRNAME,
    WORKSPACE_MAX_READ_LINES,
    capture_temporary_workspace_snapshot,
    clear_workspace,
    create_workspace_runtime_state,
    delete_temporary_workspace_snapshot,
    preview_workspace_changes,
    read_file,
    restore_temporary_workspace_snapshot,
    validate_project_workspace,
    _normalize_workspace_relative_path,
)


@pytest.fixture
def runtime_state(tmp_path):
    root = tmp_path / "workspace"
    return create_workspace_runtime_state(root_path=str(root))


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        ("src/app.py", "src/app.py"),
        (r"src\\nested\\main.py", "src/nested/main.py"),
        ("./src/./pkg/__init__.py", "src/pkg/__init__.py"),
    ],
)
def test_normalize_workspace_relative_path_normalizes_safe_inputs(raw_path, expected):
    assert _normalize_workspace_relative_path(raw_path) == expected


@pytest.mark.parametrize("raw_path", ["../escape.py", "/absolute/path.py", ".workspace-history/secret.txt"])
def test_normalize_workspace_relative_path_rejects_unsafe_inputs(raw_path):
    with pytest.raises(ValueError):
        _normalize_workspace_relative_path(raw_path)



def test_read_file_applies_default_line_window(runtime_state):
    root = Path(runtime_state["root_path"])
    target = root / "demo.txt"
    root.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(f"line-{index}" for index in range(1, 901)), encoding="utf-8")

    result = read_file(runtime_state, "demo.txt", start_line=10)

    assert result["start_line"] == 10
    assert result["end_line"] == 10 + WORKSPACE_MAX_READ_LINES - 1
    assert result["is_truncated"] is True
    assert result["content"].startswith("10: line-10")
    assert f"{result['end_line']}: line-{result['end_line']}" in result["content"]



def test_read_file_rejects_non_utf8_text(runtime_state):
    root = Path(runtime_state["root_path"])
    root.mkdir(parents=True, exist_ok=True)
    (root / "binary.dat").write_bytes(b"\xff\xfe\x00bad")

    with pytest.raises(ValueError, match="UTF-8"):
        read_file(runtime_state, "binary.dat")



def test_temporary_workspace_snapshot_restores_user_files_without_touching_history(runtime_state):
    root = Path(runtime_state["root_path"])
    history_root = root / WORKSPACE_HISTORY_DIRNAME
    user_file = root / "src" / "app.py"
    history_file = history_root / "events.log"
    root.mkdir(parents=True, exist_ok=True)
    history_root.mkdir(parents=True, exist_ok=True)
    user_file.parent.mkdir(parents=True, exist_ok=True)
    user_file.write_text("print('v1')\n", encoding="utf-8")
    history_file.write_text("history-v1\n", encoding="utf-8")

    snapshot = capture_temporary_workspace_snapshot(runtime_state)
    user_file.write_text("print('v2')\n", encoding="utf-8")
    (root / "src" / "extra.py").write_text("print('extra')\n", encoding="utf-8")
    history_file.write_text("history-v2\n", encoding="utf-8")

    restore_result = restore_temporary_workspace_snapshot(snapshot)
    delete_result = delete_temporary_workspace_snapshot(snapshot)

    assert restore_result["status"] == "ok"
    assert user_file.read_text(encoding="utf-8") == "print('v1')\n"
    assert not (root / "src" / "extra.py").exists()
    assert history_file.read_text(encoding="utf-8") == "history-v2\n"
    assert delete_result["status"] == "ok"



def test_clear_workspace_preserve_history_only_removes_user_contents(runtime_state):
    root = Path(runtime_state["root_path"])
    history_file = root / WORKSPACE_HISTORY_DIRNAME / "events.log"
    user_file = root / "notes.txt"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    user_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text("keep\n", encoding="utf-8")
    user_file.write_text("remove\n", encoding="utf-8")

    result = clear_workspace(runtime_state, preserve_history=True)

    assert result == {"status": "ok", "action": "workspace_cleared", "preserve_history": True}
    assert root.exists()
    assert history_file.exists()
    assert not user_file.exists()



def test_preview_workspace_changes_truncates_large_diff(runtime_state):
    root = Path(runtime_state["root_path"])
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("a\n" * 6000, encoding="utf-8")

    preview = preview_workspace_changes(runtime_state, [{"path": "app.py", "content": "b\n" * 6000}])

    assert preview["status"] == "ok"
    assert preview["diffs"][0]["diff"].endswith("\n...[diff truncated]")



def test_validate_project_workspace_reports_syntax_errors(runtime_state):
    root = Path(runtime_state["root_path"])
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("def broken(:\n", encoding="utf-8")

    result = validate_project_workspace(runtime_state)

    assert result["status"] == "needs_attention"
    assert result["summary"]["issue_count"] == 1
    assert "Python syntax error in app.py" in result["issues"][0]



def test_validate_project_workspace_accepts_stdlib_requirements_and_local_imports(runtime_state):
    root = Path(runtime_state["root_path"])
    root.mkdir(parents=True, exist_ok=True)
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "requirements.txt").write_text("requests>=2\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    (root / "app.py").write_text("import json\nimport requests\nfrom pkg import util\n", encoding="utf-8")
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "util.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
    (root / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")

    result = validate_project_workspace(runtime_state)

    assert result["status"] == "ok"
    assert result["summary"]["looks_like_python_project"] is True
    assert result["issues"] == []
    assert not any("Import may be unresolved" in warning for warning in result["warnings"])
