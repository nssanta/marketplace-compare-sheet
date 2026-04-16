"""
Pydantic-схемы для запросов и ответов API сравнения маркетплейсов.
Все поля типизированы, дефолты расставлены явно.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Запрос
# ---------------------------------------------------------------------------

class CompareRequest(BaseModel):
    """Тело POST /api/v1/compare."""

    query: str = Field(..., min_length=1, max_length=255, description="Поисковый запрос товара")
    marketplaces: list[Literal["wb", "ozon"]] = Field(
        default=["wb", "ozon"],
        description="Список маркетплейсов для сравнения",
    )
    top_n: int = Field(default=10, ge=1, le=50, description="Количество результатов")
    mode: Literal["demo", "live_public"] = Field(
        default="demo",
        description="Режим работы: demo = фикстуры, live_public = реальные данные",
    )


# ---------------------------------------------------------------------------
# Нормализованный товар
# ---------------------------------------------------------------------------

class NormalizedItem(BaseModel):
    """Нормализованный товар из любого маркетплейса."""

    marketplace: str                      # wb | ozon
    query: str                            # исходный запрос
    title: str                            # название товара
    current_price: float                  # текущая цена в рублях
    old_price: Optional[float] = None     # цена до скидки
    discount_pct: Optional[float] = None  # процент скидки
    rating: Optional[float] = None        # рейтинг 0-5
    reviews_count: Optional[int] = None   # количество отзывов
    seller_name: Optional[str] = None     # название продавца
    brand: Optional[str] = None           # бренд
    category_guess: Optional[str] = None  # категория (best-effort)
    url: Optional[str] = None             # ссылка на товар
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    source_mode_used: str = "demo"        # demo | live_public


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class SummaryResult(BaseModel):
    """Агрегированные метрики сравнения по запросу."""

    query: str
    wb_count: int = 0
    ozon_count: int = 0
    wb_min_price: float = 0.0
    ozon_min_price: float = 0.0
    wb_avg_price: float = 0.0
    ozon_avg_price: float = 0.0
    wb_avg_rating: float = 0.0
    ozon_avg_rating: float = 0.0
    # Кто дешевле по минимальной цене
    price_winner: Literal["wb", "ozon", "tie", "n/a"] = "n/a"
    # Разница между лучшими ценами в рублях
    price_spread: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Финальный ответ
# ---------------------------------------------------------------------------

class CompareResponse(BaseModel):
    """Ответ POST /api/v1/compare."""

    ok: bool = True
    run_id: str                              # UUID запуска
    requested_mode: str                      # что просил пользователь
    source_mode_used: str                    # что реально использовалось
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    summary: SummaryResult
    wb_items: list[NormalizedItem] = []
    ozon_items: list[NormalizedItem] = []
    errors: list[str] = []                   # некритичные ошибки, если были


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Ответ GET /health."""

    status: str = "ok"
    version: str = "1.0.0"
    env: str = "development"
