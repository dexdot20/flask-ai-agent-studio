from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import struct
import threading
import time

from config import RAG_EMBED_CACHE_ENABLED, RAG_EMBED_CACHE_MAX_ENTRIES

_cache_lock = threading.Lock()
_cache_db: sqlite3.Connection | None = None
_cache_db_path: str | None = None

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS embedding_cache (
    query_hash TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    embedding  BLOB NOT NULL,
    created_at INTEGER NOT NULL
)
"""
_CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_embedding_cache_created ON embedding_cache(created_at)"
)


def _get_cache_db_path() -> str:
    from .store import get_chroma_path

    return os.path.join(get_chroma_path(), "embed_cache.sqlite")


def _get_db() -> sqlite3.Connection:
    global _cache_db, _cache_db_path
    target_path = _get_cache_db_path()
    if _cache_db is not None and _cache_db_path == target_path:
        return _cache_db
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    conn = sqlite3.connect(target_path, check_same_thread=False, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_INDEX_SQL)
    conn.commit()
    _cache_db = conn
    _cache_db_path = target_path
    return conn


def _make_hash(text: str, model_name: str) -> str:
    key = f"{model_name}::{text}"
    return hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()


def _pack_embedding(embedding: list[float]) -> bytes:
    return struct.pack(f"{len(embedding)}f", *embedding)


def _unpack_embedding(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


def get_cached_embedding(text: str, model_name: str) -> list[float] | None:
    if not RAG_EMBED_CACHE_ENABLED:
        return None
    query_hash = _make_hash(text, model_name)
    with _cache_lock:
        try:
            db = _get_db()
            row = db.execute(
                "SELECT embedding FROM embedding_cache WHERE query_hash = ?",
                (query_hash,),
            ).fetchone()
            if row is None:
                return None
            return _unpack_embedding(row[0])
        except Exception:
            logging.debug("Embed cache read error", exc_info=True)
            return None


def set_cached_embedding(text: str, model_name: str, embedding: list[float]) -> None:
    if not RAG_EMBED_CACHE_ENABLED:
        return
    query_hash = _make_hash(text, model_name)
    blob = _pack_embedding(embedding)
    now = int(time.time())
    with _cache_lock:
        try:
            db = _get_db()
            db.execute(
                "INSERT OR REPLACE INTO embedding_cache (query_hash, model_name, embedding, created_at) "
                "VALUES (?, ?, ?, ?)",
                (query_hash, model_name, blob, now),
            )
            # LRU eviction: keep only the most recent RAG_EMBED_CACHE_MAX_ENTRIES entries
            db.execute(
                "DELETE FROM embedding_cache WHERE query_hash NOT IN ("
                "  SELECT query_hash FROM embedding_cache ORDER BY created_at DESC LIMIT ?"
                ")",
                (RAG_EMBED_CACHE_MAX_ENTRIES,),
            )
            db.commit()
        except Exception:
            logging.debug("Embed cache write error", exc_info=True)
