"""
Провайдер фикстур — читает демо-данные из JSON файлов.
Используется в режиме demo, всегда доступен.
"""

import json
import random
from pathlib import Path
from typing import Any

from app.providers.base import BaseProvider
from app.logger import get_logger

logger = get_logger(__name__)

# Путь к папке с демо-данными
MOCK_DATA_DIR = Path(__file__).parent.parent / "mock_data"


class WBFixtureProvider(BaseProvider):
    """Демо-провайдер Wildberries: читает wb_demo.json."""

    marketplace = "wb"

    def __init__(self) -> None:
        self._data: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Загружает фикстуру при инициализации."""
        path = MOCK_DATA_DIR / "wb_demo.json"
        try:
            with open(path, encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info("WB fixtures загружены: %d товаров", len(self._data))
        except FileNotFoundError:
            logger.error("Файл фикстуры не найден: %s", path)
            self._data = []

    def is_available(self) -> bool:
        return len(self._data) > 0

    async def search(self, query: str, top_n: int) -> list[dict[str, Any]]:
        """
        Возвращает демо-данные WB.
        Добавляем query в каждый элемент для трассируемости.
        """
        logger.debug("WB fixture search: query=%r top_n=%d", query, top_n)
        # Небольшое рандомное перемешивание, чтобы каждый запрос выглядел "живым"
        sample = random.sample(self._data, min(top_n, len(self._data)))
        return [{"query": query, **item} for item in sample]


class OzonFixtureProvider(BaseProvider):
    """Демо-провайдер Ozon: читает ozon_demo.json."""

    marketplace = "ozon"

    def __init__(self) -> None:
        self._data: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Загружает фикстуру при инициализации."""
        path = MOCK_DATA_DIR / "ozon_demo.json"
        try:
            with open(path, encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info("Ozon fixtures загружены: %d товаров", len(self._data))
        except FileNotFoundError:
            logger.error("Файл фикстуры не найден: %s", path)
            self._data = []

    def is_available(self) -> bool:
        return len(self._data) > 0

    async def search(self, query: str, top_n: int) -> list[dict[str, Any]]:
        """Возвращает демо-данные Ozon."""
        logger.debug("Ozon fixture search: query=%r top_n=%d", query, top_n)
        sample = random.sample(self._data, min(top_n, len(self._data)))
        return [{"query": query, **item} for item in sample]
