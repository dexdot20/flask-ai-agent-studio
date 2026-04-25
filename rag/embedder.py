from __future__ import annotations

import os
import threading
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from config import RAG_EMBED_BATCH_SIZE, RAG_EMBED_MODEL
from logging_config import get_logger

LOGGER = get_logger(__name__)

_embedder = None
_embedder_lock = threading.Lock()


def _parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value in (None, ""):
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_device() -> str:
    requested = (os.getenv("BGE_M3_DEVICE") or "").strip().lower()
    if requested in {"cpu", "cpu:0"}:
        return "cpu"
    if requested and requested not in {"cuda", "cuda:0"}:
        raise RuntimeError("BGE_M3_DEVICE must be set to cpu or cuda for this application.")

    try:
        import torch
    except Exception:
        if requested:
            LOGGER.warning(
                "BGE_M3_DEVICE=%s was requested, but torch could not be imported; falling back to CPU.",
                requested,
            )
        return "cpu"

    if not torch.cuda.is_available():
        if requested:
            LOGGER.warning(
                "BGE_M3_DEVICE=%s was requested, but no CUDA-capable GPU was detected; falling back to CPU.",
                requested,
            )
        return "cpu"

    return requested or "cuda"


def _is_missing_dependency_error(exc: Exception) -> bool:
    if isinstance(exc, ImportError):
        return True
    if isinstance(exc.__cause__, ImportError):
        return True
    message = str(exc).strip().lower()
    return "dependencies are missing" in message


def get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder

    with _embedder_lock:
        if _embedder is not None:
            return _embedder

        model_name = RAG_EMBED_MODEL
        trust_remote_code = _parse_bool_env("BGE_M3_TRUST_REMOTE_CODE", False)
        local_files_only = _parse_bool_env("BGE_M3_LOCAL_FILES_ONLY", False) or os.path.isdir(model_name)
        device = _resolve_device()

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "BGE-M3 dependencies are missing. Install sentence-transformers and torch before using RAG."
            ) from exc

        # sentence_transformers logger is silenced globally in logging_config.py
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            model = SentenceTransformer(
                model_name,
                trust_remote_code=trust_remote_code,
                device=device,
                local_files_only=local_files_only,
            )
        _embedder = {
            "model": model,
            "device": device,
            "batch_size": RAG_EMBED_BATCH_SIZE,
            "model_name": model_name,
            "local_files_only": local_files_only,
        }
        return _embedder


def preload_embedder() -> None:
    if not _parse_bool_env("BGE_M3_PRELOAD", True):
        return
    try:
        get_embedder()
    except RuntimeError as exc:
        if not _is_missing_dependency_error(exc):
            raise
        LOGGER.warning("BGE-M3 preload skipped: %s", exc)


def embed_texts(texts: list[str]) -> list[list[float]]:
    prepared = [str(text or "").strip() for text in texts if str(text or "").strip()]
    if not prepared:
        return []

    engine = get_embedder()

    # For single-text queries: try cache first to avoid redundant inference
    if len(prepared) == 1:
        from .embed_cache import get_cached_embedding, set_cached_embedding

        cached = get_cached_embedding(prepared[0], engine["model_name"])
        if cached is not None:
            return [cached]

        vectors = engine["model"].encode(
            prepared,
            batch_size=engine["batch_size"],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        result = vectors.tolist()
        set_cached_embedding(prepared[0], engine["model_name"], result[0])
        return result

    # Batch ingest path — bypass cache
    vectors = engine["model"].encode(
        prepared,
        batch_size=engine["batch_size"],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.tolist()
