"""Merkezi loglama konfigürasyonu.

Bu modül, uygulama genelinde tutarlı loglama sağlar.
Kullanım:
    from logging_config import get_logger
    logger = get_logger(__name__)
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

import config


_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_CONFIGURED = False
_CONFIGURE_LOCK = object()


def _get_log_level() -> int:
    """Log seviyesini config'ten döndürür."""
    level = _LOG_LEVELS.get(config.APP_LOG_LEVEL.upper(), logging.INFO)
    return level


def configure_logging() -> None:
    """Merkezi loglama konfigürasyonunu uygular."""
    global _CONFIGURED

    if _CONFIGURED:
        return

    if not getattr(config, "APP_LOG_ENABLED", True):
        logging.disable(logging.CRITICAL)
        _CONFIGURED = True
        return

    log_path = os.path.abspath(config.APP_LOG_PATH)
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
            if handler.baseFilename == "":
                root_logger.removeHandler(handler)

    # Dosya handler'ı ekle (zaten varsa ekleme)
    has_target_handler = any(
        isinstance(h, RotatingFileHandler)
        and os.path.abspath(str(getattr(h, "baseFilename", ""))) == log_path
        for h in root_logger.handlers
    )
    if not has_target_handler:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=config.APP_LOG_MAX_BYTES,
            backupCount=config.APP_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(_get_log_level())
        root_logger.addHandler(file_handler)

    # Konsol handler (opsiyonel)
    if getattr(config, "APP_LOG_CONSOLE_ENABLED", False):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(_get_log_level())
        root_logger.addHandler(console_handler)

    # Gürültülü kütüphaneleri sustur
    for logger_name in ("werkzeug", "urllib3", "requests"):
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


def log_critical_event(logger: logging.Logger, event: str, **details) -> None:
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


# Uygulama başlatıldığında otomatik konfigure et
configure_logging()
