"""
Нормализация сырых данных от провайдеров в единый формат NormalizedItem.
Каждый маркетплейс может давать разную структуру — здесь всё приводится к одному виду.
"""

from datetime import datetime
from typing import Any

from app.schemas.compare import NormalizedItem
from app.logger import get_logger

logger = get_logger(__name__)


def normalize_item(
    raw: dict[str, Any],
    marketplace: str,
    source_mode_used: str = "demo",
) -> NormalizedItem | None:
    """
    Преобразует сырой словарь в NormalizedItem.
    Возвращает None если данные невалидны (например, нет цены).
    """
    try:
        current_price = float(raw.get("current_price", 0) or 0)

        # Пропускаем товары без цены — они не полезны для сравнения
        if current_price <= 0:
            logger.debug("Пропускаем товар без цены: %s", raw.get("title", ""))
            return None

        old_price = raw.get("old_price")
        discount_pct = raw.get("discount_pct")

        # Если есть старая цена, но нет процента — вычислим сами
        if old_price and old_price > current_price and discount_pct is None:
            discount_pct = round((1 - current_price / old_price) * 100, 1)

        return NormalizedItem(
            marketplace=marketplace,
            query=raw.get("query", ""),
            title=raw.get("title", "Без названия"),
            current_price=current_price,
            old_price=float(old_price) if old_price else None,
            discount_pct=float(discount_pct) if discount_pct else None,
            rating=float(raw["rating"]) if raw.get("rating") is not None else None,
            reviews_count=int(raw["reviews_count"]) if raw.get("reviews_count") is not None else None,
            seller_name=raw.get("seller_name"),
            brand=raw.get("brand"),
            category_guess=raw.get("category_guess"),
            url=raw.get("url"),
            scraped_at=datetime.utcnow(),
            source_mode_used=source_mode_used,
        )

    except (TypeError, ValueError) as e:
        logger.warning("Ошибка нормализации товара: %s | данные: %s", e, raw)
        return None


def normalize_batch(
    items: list[dict[str, Any]],
    marketplace: str,
    source_mode_used: str = "demo",
) -> list[NormalizedItem]:
    """Нормализует список товаров, отфильтровывает None."""
    normalized = [normalize_item(raw, marketplace, source_mode_used) for raw in items]
    valid = [item for item in normalized if item is not None]
    logger.info(
        "%s: нормализовано %d/%d товаров",
        marketplace.upper(), len(valid), len(items)
    )
    return valid
