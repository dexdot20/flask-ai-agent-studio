from __future__ import annotations

from io import BytesIO
import os
from pathlib import PurePosixPath
import posixpath
import re
from urllib.parse import unquote, urlparse
import zipfile

import requests

from canvas_service import create_canvas_document, rewrite_canvas_document

GITHUB_IMPORT_MAX_ARCHIVE_BYTES = 8_000_000
GITHUB_IMPORT_MAX_FILES = 50
GITHUB_IMPORT_MAX_FILE_BYTES = 120_000
GITHUB_IMPORT_REQUEST_TIMEOUT_SECONDS = 30
GITHUB_IMPORT_DEFAULT_USER_AGENT = "flask-rag-vision-chatbot-github-import"

_TEXT_FILE_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".mdx",
    ".rst",
    ".adoc",
    ".org",
    ".py",
    ".pyw",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".mts",
    ".tsx",
    ".jsx",
    ".json",
    ".jsonc",
    ".yaml",
    ".yml",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".sh",
    ".bash",
    ".zsh",
    ".sql",
    ".xml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".example",
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".cxx",
    ".hpp",
    ".hh",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".kts",
    ".scala",
    ".dart",
    ".lua",
    ".r",
    ".vue",
    ".svelte",
    ".proto",
}

_TEXT_FILE_NAMES = {
    "dockerfile",
    "makefile",
    "gemfile",
    "rakefile",
    "vagrantfile",
    "jenkinsfile",
    "readme",
    "readme.md",
    "license",
    "license.md",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "cargo.toml",
    "go.mod",
    "go.sum",
}

_IGNORED_PATH_SEGMENTS = {
    ".git",
    ".github",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".next",
    ".nuxt",
    "vendor",
    "target",
}


def _github_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": GITHUB_IMPORT_DEFAULT_USER_AGENT,
    }


def _normalize_repo_slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", str(text or "").strip().lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned[:80] or "github-repo"


def _normalize_repo_path(value: str | None) -> str:
    normalized = str(value or "").strip().replace("\\", "/")
    if not normalized:
        return ""
    normalized = re.sub(r"/{2,}", "/", normalized).strip("/")
    if not normalized:
        return ""
    parts: list[str] = []
    for part in PurePosixPath(normalized).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _parse_github_repository_url(url: str) -> dict:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise ValueError("Only github.com repository URLs are supported.")

    path_parts = [unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
    if len(path_parts) < 2:
        raise ValueError("GitHub repository URL must include both owner and repository name.")

    owner = path_parts[0]
    repo = path_parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        raise ValueError("GitHub repository URL is incomplete.")

    ref = ""
    subdir = ""
    if len(path_parts) >= 4 and path_parts[2] == "tree":
        ref = path_parts[3]
        if len(path_parts) > 4:
            subdir = _normalize_repo_path("/".join(path_parts[4:]))

    return {
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "subdir": subdir,
        "source_url": f"https://github.com/{owner}/{repo}",
        "display_url": parsed.geturl(),
    }


def _resolve_default_branch(owner: str, repo: str) -> str:
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=_github_headers(),
        timeout=GITHUB_IMPORT_REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code >= 400:
        raise ValueError(f"GitHub repository metadata could not be loaded ({response.status_code}).")
    payload = response.json() if callable(getattr(response, "json", None)) else {}
    default_branch = str((payload or {}).get("default_branch") or "").strip()
    if not default_branch:
        raise ValueError("GitHub repository metadata did not include a default branch.")
    return default_branch


def _download_archive_bytes(owner: str, repo: str, ref: str) -> bytes:
    archive_urls = [
        f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{ref}",
        f"https://codeload.github.com/{owner}/{repo}/zip/refs/tags/{ref}",
    ]
    last_status_code = 0
    for archive_url in archive_urls:
        response = requests.get(
            archive_url,
            headers=_github_headers(),
            timeout=GITHUB_IMPORT_REQUEST_TIMEOUT_SECONDS,
            stream=True,
        )
        last_status_code = int(getattr(response, "status_code", 0) or 0)
        if response.status_code == 404:
            continue
        if response.status_code >= 400:
            raise ValueError(f"GitHub archive download failed ({response.status_code}).")
        chunks: list[bytes] = []
        byte_count = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            chunks.append(chunk)
            byte_count += len(chunk)
            if byte_count > GITHUB_IMPORT_MAX_ARCHIVE_BYTES:
                raise ValueError(
                    f"GitHub archive is too large. Limit is {GITHUB_IMPORT_MAX_ARCHIVE_BYTES:,} bytes."
                )
        return b"".join(chunks)
    raise ValueError(f"GitHub archive could not be downloaded ({last_status_code or 404}).")


def _looks_like_text_file(path: str, raw_bytes: bytes) -> bool:
    basename = posixpath.basename(path).lower()
    suffix = posixpath.splitext(basename)[1].lower()
    if not raw_bytes:
        return False
    # Reject by extension first — reliable regardless of encoding quirks.
    _BINARY_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".tiff", ".webp",
        ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
        ".exe", ".dll", ".so", ".dylib", ".wasm",
        ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".flac", ".ogg",
        ".ttf", ".otf", ".woff", ".woff2", ".eot",
        ".pyc", ".pyd", ".class", ".o", ".a",
        ".db", ".sqlite", ".sqlite3",
    }
    if suffix in _BINARY_EXTENSIONS:
        return False
    if basename in _TEXT_FILE_NAMES or suffix in _TEXT_FILE_EXTENSIONS:
        sample = raw_bytes[:4096]
        if b"\x00" in sample:
            return False
        return True
    # Unknown extension — probe bytes.
    sample = raw_bytes[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _decode_text_file(raw_bytes: bytes) -> str:
    truncated = raw_bytes[:GITHUB_IMPORT_MAX_FILE_BYTES]
    try:
        return truncated.decode("utf-8")
    except UnicodeDecodeError:
        return truncated.decode("utf-8", errors="ignore")


def _should_skip_path(relative_path: str) -> bool:
    lowered_parts = [part.lower() for part in relative_path.split("/") if part]
    return any(part in _IGNORED_PATH_SEGMENTS for part in lowered_parts)


def _score_repo_file(path: str) -> int:
    normalized = str(path or "").strip().lower()
    basename = posixpath.basename(normalized)
    depth = len([part for part in normalized.split("/") if part])
    score = 0

    if basename in {"readme.md", "readme", "readme.txt"}:
        score += 1200
    if basename in {"pyproject.toml", "package.json", "requirements.txt", "cargo.toml", "go.mod"}:
        score += 1200
    if basename in {"app.py", "main.py", "manage.py", "index.js", "main.ts", "main.jsx", "main.tsx"}:
        score += 980
    if normalized.startswith("src/"):
        score += 940
    if normalized.startswith("app/"):
        score += 900
    if normalized.startswith("lib/"):
        score += 860
    if normalized.startswith("docs/"):
        score += 780
    if normalized.startswith("tests/"):
        score += 700
    if basename.endswith((".md", ".rst", ".txt")):
        score += 120
    if basename.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java")):
        score += 260

    score -= depth * 6
    score -= len(normalized) // 24
    return score


def load_github_repo_canvas_entries(url: str) -> dict:
    repo_info = _parse_github_repository_url(url)
    owner = repo_info["owner"]
    repo = repo_info["repo"]
    ref = repo_info["ref"] or _resolve_default_branch(owner, repo)
    subdir = repo_info["subdir"]
    archive_bytes = _download_archive_bytes(owner, repo, ref)

    try:
        archive = zipfile.ZipFile(BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("GitHub archive is not a valid ZIP file.") from exc

    entries: list[dict] = []
    skipped_binary = 0
    skipped_filtered = 0
    skipped_limit = 0

    with archive:
        all_infos = [info for info in archive.infolist() if not info.is_dir()]
        if not all_infos:
            raise ValueError("GitHub archive did not contain any files.")
        root_prefix = str(all_infos[0].filename or "").split("/", 1)[0]
        if not root_prefix:
            raise ValueError("GitHub archive root could not be determined.")

        candidate_files: list[dict] = []
        for info in all_infos:
            filename = str(info.filename or "")
            if not filename.startswith(f"{root_prefix}/"):
                continue
            relative_path = _normalize_repo_path(filename[len(root_prefix) + 1 :])
            if not relative_path:
                continue
            if subdir:
                if relative_path == subdir:
                    continue
                if not (relative_path == subdir or relative_path.startswith(f"{subdir}/")):
                    continue
                relative_path = _normalize_repo_path(relative_path[len(subdir) :])
            if not relative_path or _should_skip_path(relative_path):
                skipped_filtered += 1
                continue
            raw_bytes = archive.read(info)
            if not _looks_like_text_file(relative_path, raw_bytes):
                skipped_binary += 1
                continue
            candidate_files.append(
                {
                    "path": relative_path,
                    "content": _decode_text_file(raw_bytes),
                    "score": _score_repo_file(relative_path),
                    "size": len(raw_bytes),
                }
            )

    if not candidate_files:
        raise ValueError("No supported text files were found in that GitHub repository.")

    candidate_files.sort(key=lambda item: (-int(item["score"]), str(item["path"])))
    selected_files = candidate_files[:GITHUB_IMPORT_MAX_FILES]
    skipped_limit = max(0, len(candidate_files) - len(selected_files))
    if not selected_files:
        raise ValueError("No supported files fit within the Canvas import limit.")

    project_slug = _normalize_repo_slug(f"{owner}-{repo}")
    workspace_slug = _normalize_repo_slug(f"{project_slug}-{ref}")
    import_group_id = _normalize_repo_slug(f"{workspace_slug}-github-import")

    for item in selected_files:
        relative_path = str(item["path"])
        entries.append(
            {
                "title": os.path.basename(relative_path) or relative_path,
                "path": relative_path,
                "content": item["content"],
                "project_id": project_slug,
                "workspace_id": workspace_slug,
                "source_url": repo_info["display_url"],
                "source_title": f"{owner}/{repo}@{ref}",
                "source_kind": "github_repo",
                "import_group_id": import_group_id,
                "score": int(item["score"]),
            }
        )

    primary_document = max(entries, key=lambda entry: (int(entry.get("score") or 0), -len(str(entry.get("path") or ""))))
    return {
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "project_id": project_slug,
        "workspace_id": workspace_slug,
        "source_url": repo_info["display_url"],
        "source_title": f"{owner}/{repo}@{ref}",
        "import_group_id": import_group_id,
        "documents": entries,
        "primary_document_path": str(primary_document.get("path") or "").strip(),
        "imported_count": len(entries),
        "skipped_binary_count": skipped_binary,
        "skipped_filtered_count": skipped_filtered,
        "skipped_limit_count": skipped_limit,
    }


def import_github_repository_into_canvas(runtime_state: dict, url: str) -> dict:
    repo_payload = load_github_repo_canvas_entries(url)
    created_count = 0
    updated_count = 0
    imported_documents: list[dict] = []
    primary_document_path = str(repo_payload.get("primary_document_path") or "").strip()

    ordered_documents = sorted(
        repo_payload.get("documents") or [],
        key=lambda entry: (str(entry.get("path") or "") == primary_document_path, -int(entry.get("score") or 0), str(entry.get("path") or "")),
    )

    for entry in ordered_documents:
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        try:
            document = rewrite_canvas_document(
                runtime_state,
                content=str(entry.get("content") or ""),
                document_path=path,
                title=str(entry.get("title") or os.path.basename(path) or path),
                format_name="",
                language_name=None,
                path=path,
                project_id=repo_payload.get("project_id"),
                workspace_id=repo_payload.get("workspace_id"),
            )
            updated_count += 1
        except ValueError:
            document = create_canvas_document(
                runtime_state,
                title=str(entry.get("title") or os.path.basename(path) or path),
                content=str(entry.get("content") or ""),
                format_name="",
                language_name=None,
                path=path,
                project_id=repo_payload.get("project_id"),
                workspace_id=repo_payload.get("workspace_id"),
                source_url=repo_payload.get("source_url"),
                source_title=repo_payload.get("source_title"),
                source_kind="github_repo",
                import_group_id=repo_payload.get("import_group_id"),
            )
            created_count += 1
        imported_documents.append(document)

    primary_document = next(
        (document for document in imported_documents if str(document.get("path") or "").strip() == primary_document_path),
        imported_documents[-1] if imported_documents else None,
    )
    if primary_document is not None:
        runtime_state["active_document_id"] = str(primary_document.get("id") or "").strip() or runtime_state.get("active_document_id")

    return {
        **repo_payload,
        "created_count": created_count,
        "updated_count": updated_count,
        "documents": imported_documents,
        "active_document_id": str((primary_document or {}).get("id") or "").strip() or None,
    }
