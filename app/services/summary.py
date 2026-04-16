"""
Подсчёт агрегированных метрик по результатам сравнения.
Всё что нужно бизнесу — min/avg цена, рейтинг, кто дешевле.
"""

from datetime import datetime

from app.schemas.compare import NormalizedItem, SummaryResult
from app.logger import get_logger

logger = get_logger(__name__)


def _avg(values: list[float]) -> float:
    """Безопасное среднее: возвращает 0.0 для пустого списка."""
    return round(sum(values) / len(values), 2) if values else 0.0


def build_summary(
    query: str,
    wb_items: list[NormalizedItem],
    ozon_items: list[NormalizedItem],
) -> SummaryResult:
    """
    Строит SummaryResult из нормализованных списков товаров.
    Считает: count, min/avg цену, avg рейтинг, winner по цене.
    """
    wb_prices = [i.current_price for i in wb_items if i.current_price > 0]
    ozon_prices = [i.current_price for i in ozon_items if i.current_price > 0]
    wb_ratings = [i.rating for i in wb_items if i.rating is not None]
    ozon_ratings = [i.rating for i in ozon_items if i.rating is not None]

    wb_min = min(wb_prices) if wb_prices else 0.0
    ozon_min = min(ozon_prices) if ozon_prices else 0.0

    # Определяем победителя по минимальной цене
    if wb_min > 0 and ozon_min > 0:
        diff = abs(wb_min - ozon_min)
        if diff < 1.0:
            # Цены почти одинаковые — считаем ничьей
            price_winner = "tie"
        elif wb_min < ozon_min:
            price_winner = "wb"
        else:
            price_winner = "ozon"
    elif wb_min > 0:
        price_winner = "wb"
    elif ozon_min > 0:
        price_winner = "ozon"
    else:
        price_winner = "n/a"

    # Спред = разница между лучшими ценами
    price_spread = abs(wb_min - ozon_min) if wb_min > 0 and ozon_min > 0 else 0.0

    summary = SummaryResult(
        query=query,
        wb_count=len(wb_items),
        ozon_count=len(ozon_items),
        wb_min_price=wb_min,
        ozon_min_price=ozon_min,
        wb_avg_price=_avg(wb_prices),
        ozon_avg_price=_avg(ozon_prices),
        wb_avg_rating=_avg(wb_ratings),
        ozon_avg_rating=_avg(ozon_ratings),
        price_winner=price_winner,
        price_spread=round(price_spread, 2),
        updated_at=datetime.utcnow(),
    )

    logger.info(
        "Summary: WB %d товаров (min %.0f₽), Ozon %d товаров (min %.0f₽), winner=%s",
        summary.wb_count, summary.wb_min_price,
        summary.ozon_count, summary.ozon_min_price,
        summary.price_winner,
    )
    return summary
