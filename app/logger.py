"""
Настройка логирования для всего приложения.
Используем стандартный logging с читаемым форматом.
"""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Настраивает root logger с читаемым форматом вывода."""

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
        datefmt=date_format,
        stream=sys.stdout,
    )

    # Отключаем слишком подробные логи от uvicorn access
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Возвращает именованный логгер для модуля."""
    return logging.getLogger(name)
