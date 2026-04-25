"""Merkezi loglama konfigürasyonu.

Bu modül, uygulama genelinde tutarlı loglama sağlar.
Kullanım:
    from logging_config import get_logger
    LOGGER = get_logger(__name__)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any


_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_CONFIGURED = False
_CONFIGURE_LOCK = object()

# Environment variable names for logging config
_ENV_APP_LOG_ENABLED = "APP_LOG_ENABLED"
_ENV_APP_LOG_LEVEL = "APP_LOG_LEVEL"
_ENV_APP_LOG_PATH = "APP_LOG_PATH"
_ENV_APP_LOG_MAX_BYTES = "APP_LOG_MAX_BYTES"
_ENV_APP_LOG_BACKUP_COUNT = "APP_LOG_BACKUP_COUNT"
_ENV_APP_LOG_CONSOLE_ENABLED = "APP_LOG_CONSOLE_ENABLED"


def _coerce_bool(value, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _get_log_level() -> int:
    """Log seviyesini environment variable'dan döndürür."""
    level = os.getenv(_ENV_APP_LOG_LEVEL, "INFO").strip().upper()
    return _LOG_LEVELS.get(level, logging.INFO)


def _is_log_enabled() -> bool:
    """Log etkin mi environment variable'dan kontrol eder."""
    return _coerce_bool(os.getenv(_ENV_APP_LOG_ENABLED), True)


def _get_log_path() -> str:
    """Log dosya yolunu environment variable'dan alır veya default değer döndürür."""
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent
    return os.getenv(_ENV_APP_LOG_PATH, str(base_dir / "logs" / "app.log")).strip()


def _get_log_max_bytes() -> int:
    """Max bytes environment variable'dan alır veya default döndürür."""
    try:
        return max(1024, int(os.getenv(_ENV_APP_LOG_MAX_BYTES, "2000000")))
    except (TypeError, ValueError):
        return 2_000_000


def _get_log_backup_count() -> int:
    """Backup count environment variable'dan alır veya default döndürür."""
    try:
        return max(1, int(os.getenv(_ENV_APP_LOG_BACKUP_COUNT, "5")))
    except (TypeError, ValueError):
        return 5


def _is_console_enabled() -> bool:
    """Console log etkin mi environment variable'dan kontrol eder."""
    return _coerce_bool(os.getenv(_ENV_APP_LOG_CONSOLE_ENABLED), False)


def configure_logging() -> None:
    """Merkezi loglama konfigürasyonunu uygular."""
    global _CONFIGURED

    if _CONFIGURED:
        return

    if not _is_log_enabled():
        logging.disable(logging.CRITICAL)
        _CONFIGURED = True
        return

    log_path = os.path.abspath(_get_log_path())
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(_get_log_level())

    # Mevcut handler'ları temizle (sadece uygulama logları için)
    for handler in root_logger.handlers[:]:
        if isinstance(handler, RotatingFileHandler):
            continue
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
            if getattr(handler, "baseFilename", "") == "":
                root_logger.removeHandler(handler)

    # Dosya handler'ı ekle (zaten varsa ekleme)
    has_target_handler = any(
        isinstance(h, RotatingFileHandler) and os.path.abspath(str(getattr(h, "baseFilename", ""))) == log_path
        for h in root_logger.handlers
    )
    if not has_target_handler:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=_get_log_max_bytes(),
            backupCount=_get_log_backup_count(),
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(_get_log_level())
        root_logger.addHandler(file_handler)

    # Konsol handler (opsiyonel)
    if _is_console_enabled():
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(_get_log_level())
        root_logger.addHandler(console_handler)

    # Gürültülü kütüphaneleri sustur
    for logger_name in ("werkzeug", "urllib3", "requests", "sentence_transformers"):
        noisy_logger = logging.getLogger(logger_name)
        noisy_logger.setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Modül adı ile logger döndürür.

    Args:
        name: logger adı (genellikle __name__)

    Returns:
        yapılandırılmış Logger instance
    """
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, msg: str, *args, **kwargs) -> None:
    """Bir exception ile birlikte ERROR seviyesinde loglar.

    Args:
        logger: Logger instance
        msg: Log mesajı
        *args: format args
        **kwargs: ek keyword argümanları (exc_info=True otomatik eklenir)
    """
    kwargs.setdefault("exc_info", True)
    logger.error(msg, *args, **kwargs)


def log_critical_event(logger: logging.Logger, event: str, **details: Any) -> None:
    """Kritik bir olayı loglar.

    Args:
        logger: Logger instance
        event: Olay adı
        **details: Ek detaylar (key=value formatında)
    """
    if details:
        detail_str = " | ".join(f"{k}={v!r}" for k, v in details.items())
        logger.critical("%s | %s", event, detail_str)
    else:
        logger.critical("%s", event)


def log_trace_event(logger: logging.Logger, event: str, **details: Any) -> None:
    """Agent trace olaylarını yapılandırılmış JSON formatında loglar.

    Bu fonksiyon, agent trace olaylarını merkezi log dosyasına JSON formatında yazar.
    Tüm alanlar tek bir JSON nesnesi içinde toplanır ve timestamp otomatik eklenir.

    Args:
        logger: Logger instance
        event: Olay adı (örn: 'agent_start', 'tool_call', 'agent_end')
        **details: Ek detaylar (key=value formatında, JSON-serializable olmalı)
    """
    trace_data: dict[str, Any] = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    trace_data.update(details)
    logger.info("TRACE %s", json.dumps(trace_data, default=str))


# Uygulama başlatıldığında otomatik konfigure et
configure_logging()
