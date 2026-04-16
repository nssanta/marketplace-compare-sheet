"""
Live-провайдер Wildberries через публичный поиск.
Статус: stub — реализован как точка расширения.
В случае ошибки возвращает пустой список, не падает.
"""

from typing import Any

import httpx

from app.providers.base import BaseProvider
from app.logger import get_logger

logger = get_logger(__name__)

# Публичный поисковый URL WB (без авторизации, может меняться)
WB_SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v4/search"


class WBPublicProvider(BaseProvider):
    """
    Live-провайдер WB.
    Пытается забрать реальные данные через публичный поиск WB.
    Если не получается — возвращает [] и логирует ошибку.
    """

    marketplace = "wb"

    def is_available(self) -> bool:
        # Считаем провайдер доступным — он сам отловит ошибку при запросе
        return True

    async def search(self, query: str, top_n: int) -> list[dict[str, Any]]:
        """
        Запрашивает поисковую выдачу WB.
        При любой ошибке возвращает пустой список.
        """
        params = {
            "appType": 1,
            "curr": "rub",
            "dest": -1257786,
            "query": query,
            "resultset": "catalog",
            "sort": "popular",
            "suppressSpellcheck": "false",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(WB_SEARCH_URL, params=params)
                response.raise_for_status()
                data = response.json()

            products = data.get("data", {}).get("products", [])[:top_n]
            logger.info("WB live: получено %d товаров для %r", len(products), query)
            return self._normalize_raw(query, products)

        except httpx.HTTPError as e:
            logger.warning("WB live HTTP ошибка: %s", e)
            return []
        except Exception as e:
            logger.warning("WB live неожиданная ошибка: %s", e)
            return []

    def _normalize_raw(self, query: str, products: list[dict]) -> list[dict[str, Any]]:
        """Преобразует сырой ответ WB в унифицированный словарь."""
        result = []
        for p in products:
            # Цена в WB API хранится в копейках, делим на 100
            price_raw = p.get("salePriceU", 0) or p.get("priceU", 0)
            old_price_raw = p.get("priceU", 0)
            current_price = price_raw / 100
            old_price = old_price_raw / 100 if old_price_raw != price_raw else None

            result.append({
                "query": query,
                "title": p.get("name", ""),
                "current_price": current_price,
                "old_price": old_price,
                "discount_pct": p.get("sale"),
                "rating": p.get("reviewRating"),
                "reviews_count": p.get("feedbacks"),
                "seller_name": p.get("brand"),
                "brand": p.get("brand"),
                "category_guess": None,
                "url": f"https://www.wildberries.ru/catalog/{p.get('id')}/detail.aspx",
            })
        return result
