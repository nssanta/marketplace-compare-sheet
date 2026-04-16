"""
Оркестратор сравнения маркетплейсов.
Выбирает провайдеры по режиму, запускает поиск, нормализует, считает summary.
"""

import uuid
from datetime import datetime

from app.schemas.compare import CompareRequest, CompareResponse
from app.providers.fixtures import WBFixtureProvider, OzonFixtureProvider
from app.providers.wb_public import WBPublicProvider
from app.providers.ozon_public import OzonPublicProvider
from app.services.normalize import normalize_batch
from app.services.summary import build_summary
from app.settings import settings
from app.logger import get_logger

logger = get_logger(__name__)


async def run_comparison(request: CompareRequest) -> CompareResponse:
    """
    Главная функция сравнения.
    Принимает CompareRequest, возвращает CompareResponse.
    """
    run_id = str(uuid.uuid4())[:8]  # Короткий ID для удобства
    errors: list[str] = []
    source_mode_used = request.mode

    logger.info(
        "Запуск сравнения [%s]: query=%r mode=%s marketplaces=%s top_n=%d",
        run_id, request.query, request.mode, request.marketplaces, request.top_n,
    )

    wb_items = []
    ozon_items = []

    # Обрабатываем каждый маркетплейс отдельно
    if "wb" in request.marketplaces:
        wb_raw, wb_mode = await _fetch(
            marketplace="wb",
            query=request.query,
            top_n=request.top_n,
            requested_mode=request.mode,
            run_id=run_id,
            errors=errors,
        )
        wb_items = normalize_batch(wb_raw, "wb", wb_mode)
        # Если fallback в demo — обновляем source_mode_used
        if wb_mode == "demo" and request.mode != "demo":
            source_mode_used = "demo"

    if "ozon" in request.marketplaces:
        ozon_raw, ozon_mode = await _fetch(
            marketplace="ozon",
            query=request.query,
            top_n=request.top_n,
            requested_mode=request.mode,
            run_id=run_id,
            errors=errors,
        )
        ozon_items = normalize_batch(ozon_raw, "ozon", ozon_mode)
        if ozon_mode == "demo" and request.mode != "demo":
            source_mode_used = "demo"

    summary = build_summary(request.query, wb_items, ozon_items)

    logger.info("Сравнение [%s] завершено: WB %d, Ozon %d", run_id, len(wb_items), len(ozon_items))

    return CompareResponse(
        ok=True,
        run_id=run_id,
        requested_mode=request.mode,
        source_mode_used=source_mode_used,
        updated_at=datetime.utcnow(),
        summary=summary,
        wb_items=wb_items,
        ozon_items=ozon_items,
        errors=errors,
    )


async def _fetch(
    marketplace: str,
    query: str,
    top_n: int,
    requested_mode: str,
    run_id: str,
    errors: list[str],
) -> tuple[list[dict], str]:
    """
    Загружает данные из нужного провайдера.
    Если live_public недоступен или упал — делает fallback в demo.
    Возвращает (данные, реальный_режим).
    """
    # Выбираем провайдер
    if requested_mode == "demo":
        provider = _get_fixture_provider(marketplace)
        mode_used = "demo"
    else:
        # live_public: пробуем live, при ошибке — fallback в demo
        live_provider = _get_live_provider(marketplace)
        try:
            raw = await live_provider.search(query, top_n)
            if raw:
                logger.info("[%s] %s live: получено %d товаров", run_id, marketplace.upper(), len(raw))
                return raw, "live_public"
            else:
                # Live вернул пустой список — переходим в demo
                logger.warning(
                    "[%s] %s live вернул 0 товаров → fallback в demo",
                    run_id, marketplace.upper()
                )
                errors.append(f"{marketplace}: live_public вернул 0 результатов, использован demo")
        except Exception as e:
            logger.warning("[%s] %s live ошибка: %s → fallback в demo", run_id, marketplace.upper(), e)
            errors.append(f"{marketplace}: {str(e)}, использован demo")

        # Fallback в demo
        provider = _get_fixture_provider(marketplace)
        mode_used = "demo"

    raw = await provider.search(query, top_n)
    return raw, mode_used


def _get_fixture_provider(marketplace: str):
    """Возвращает fixture-провайдер по имени маркетплейса."""
    if marketplace == "wb":
        return WBFixtureProvider()
    elif marketplace == "ozon":
        return OzonFixtureProvider()
    raise ValueError(f"Неизвестный маркетплейс: {marketplace}")


def _get_live_provider(marketplace: str):
    """Возвращает live-провайдер по имени маркетплейса."""
    if marketplace == "wb":
        return WBPublicProvider()
    elif marketplace == "ozon":
        return OzonPublicProvider(api_key=settings.api_key)
    raise ValueError(f"Неизвестный маркетплейс: {marketplace}")
