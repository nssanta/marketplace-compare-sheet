"""
Абстрактный базовый провайдер для всех источников данных.
Каждый маркетплейс реализует этот интерфейс.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    """Базовый класс провайдера данных маркетплейса."""

    # Имя маркетплейса: wb | ozon
    marketplace: str = ""

    @abstractmethod
    async def search(self, query: str, top_n: int) -> list[dict[str, Any]]:
        """
        Выполняет поиск товаров по запросу.

        Args:
            query: Поисковый запрос
            top_n: Максимальное количество результатов

        Returns:
            Список сырых данных товаров (до нормализации)
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Возвращает True если провайдер готов к работе."""
        raise NotImplementedError
