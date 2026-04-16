"""
Live-провайдер Ozon через публичный API.
Статус: stub — реализован как точка расширения.
Ozon требует авторизации для большинства API-методов.
В случае ошибки возвращает пустой список, не падает.
"""

from typing import Any

import httpx

from app.providers.base import BaseProvider
from app.logger import get_logger

logger = get_logger(__name__)

# Заглушка URL — Ozon не имеет открытого публичного поиска без ключа
OZON_API_URL = "https://api-seller.ozon.ru/v2/product/list"


class OzonPublicProvider(BaseProvider):
    """
    Live-провайдер Ozon.
    Ozon не предоставляет полностью открытый поиск без API-ключа.
    Провайдер реализован как расширяемый stub:
    - Если в .env задан OZON_API_KEY — можно расширить до реального запроса
    - Сейчас возвращает [] с предупреждением
    """

    marketplace = "ozon"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    def is_available(self) -> bool:
        # Требует API ключ для реальной работы
        return bool(self.api_key)

    async def search(self, query: str, top_n: int) -> list[dict[str, Any]]:
        """
        Пытается получить данные из Ozon.
        Без API ключа возвращает пустой список — graceful degradation.
        """
        if not self.api_key:
            logger.warning(
                "Ozon live: API ключ не задан, live mode недоступен для Ozon. "
                "Задайте OZON_API_KEY в .env"
            )
            return []

        # Место для реализации реального запроса к Ozon Seller API
        # Требует: OZON_API_KEY + Client-Id
        logger.warning("Ozon live: полная реализация не завершена, возвращаем []")
        return []
