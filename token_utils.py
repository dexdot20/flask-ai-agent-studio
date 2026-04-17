from __future__ import annotations

import logging
import re
from functools import lru_cache

import tiktoken


LOGGER = logging.getLogger(__name__)
TOKEN_ESTIMATION_FALLBACK_MARGIN = 0.90
_FALLBACK_WARNING_EMITTED = False


@lru_cache(maxsize=1)
def get_token_encoder():
    global _FALLBACK_WARNING_EMITTED
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        if not _FALLBACK_WARNING_EMITTED:
            LOGGER.warning("Failed to initialize tiktoken encoder; falling back to heuristic token estimation.")
            _FALLBACK_WARNING_EMITTED = True
        return None


def estimate_text_tokens(text: str) -> int:
    normalized = str(text or "").strip()
    if not normalized:
        return 0

    encoder = get_token_encoder()
    if encoder is not None:
        try:
            return max(1, len(encoder.encode(normalized, disallowed_special=())))
        except Exception:
            LOGGER.exception("Token estimation failed while encoding text; using heuristic fallback.")

    byte_estimate = (len(normalized.encode("utf-8")) + 3) // 4
    piece_estimate = len(re.findall(r"\w+|[^\w\s]", normalized, re.UNICODE))
    heuristic_estimate = max(1, byte_estimate, piece_estimate)
    return max(1, int(heuristic_estimate / TOKEN_ESTIMATION_FALLBACK_MARGIN))