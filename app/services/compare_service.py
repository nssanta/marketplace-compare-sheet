"""
Оркестратор сравнения маркетплейсов.
Выбирает провайдеры по режиму, запускает поиск, нормализует, считает summary.
Логирует: provider, fallback, item count, время выполнения.
"""

import time
import uuid
from datetime import datetime

from app.schemas.compare import CompareRequest, CompareResponse
from app.providers.fixtures import WBFixtureProvider, OzonFixtureProvider
from app.providers.wb_public import WBPublicProvider
from app.providers.ozon_public_playwright import OzonPublicPlaywrightProvider
from app.providers.ozon_public_consumer_api import enrich_with_consumer_api
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
    run_id = str(uuid.uuid4())[:8]
    errors: list[str] = []
    source_mode_used = request.mode
    t_start = time.monotonic()

    logger.info(
        "[%s] START query=%r mode=%s marketplaces=%s top_n=%d",
        run_id, request.query, request.mode, request.marketplaces, request.top_n,
    )

    wb_items = []
    ozon_items = []

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
        # Enrichment только для live данных — demo-фикстуры уже полные
        if ozon_mode == "live_public" and ozon_raw:
            ozon_raw = await enrich_with_consumer_api(
                ozon_raw,
                timeout=settings.http_timeout,
                max_enrich=5,
            )
        ozon_items = normalize_batch(ozon_raw, "ozon", ozon_mode)
        if ozon_mode == "demo" and request.mode != "demo":
            source_mode_used = "demo"

    summary = build_summary(request.query, wb_items, ozon_items)

    elapsed = time.monotonic() - t_start
    logger.info(
        "[%s] DONE %.2fs | source=%s | WB=%d Ozon=%d | winner=%s | errors=%d",
        run_id, elapsed,
        source_mode_used,
        len(wb_items), len(ozon_items),
        summary.price_winner,
        len(errors),
    )
    if errors:
        for err in errors:
            logger.warning("[%s] fallback error: %s", run_id, err)

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
    Логирует: provider name, items count, elapsed time, fallback.
    """
    mp = marketplace.upper()

    if requested_mode == "demo":
        provider = _get_fixture_provider(marketplace)
        t0 = time.monotonic()
        raw = await provider.search(query, top_n)
        logger.info(
            "[%s] %s provider=fixture items=%d elapsed=%.2fs",
            run_id, mp, len(raw), time.monotonic() - t0,
        )
        return raw, "demo"

    # live_public: пробуем live, при ошибке — fallback в demo
    live_provider = _get_live_provider(marketplace)
    provider_name = type(live_provider).__name__
    t0 = time.monotonic()

    try:
        raw = await live_provider.search(query, top_n)
        elapsed = time.monotonic() - t0

        if raw:
            logger.info(
                "[%s] %s provider=%s items=%d elapsed=%.2fs source=live_public",
                run_id, mp, provider_name, len(raw), elapsed,
            )
            return raw, "live_public"

        # Live вернул пустой список
        logger.warning(
            "[%s] %s provider=%s returned 0 items elapsed=%.2fs → FALLBACK demo",
            run_id, mp, provider_name, elapsed,
        )
        errors.append(f"{marketplace}: live_public вернул 0 результатов, использован demo")

    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.warning(
            "[%s] %s provider=%s EXCEPTION elapsed=%.2fs → FALLBACK demo | %s",
            run_id, mp, provider_name, elapsed, e,
        )
        errors.append(f"{marketplace}: {str(e)}, использован demo")

    # Fallback в demo
    fixture = _get_fixture_provider(marketplace)
    t1 = time.monotonic()
    raw = await fixture.search(query, top_n)
    logger.info(
        "[%s] %s provider=fixture(fallback) items=%d elapsed=%.2fs",
        run_id, mp, len(raw), time.monotonic() - t1,
    )
    return raw, "demo"


def _get_fixture_provider(marketplace: str):
    if marketplace == "wb":
        return WBFixtureProvider()
    elif marketplace == "ozon":
        return OzonFixtureProvider()
    raise ValueError(f"Неизвестный маркетплейс: {marketplace}")


def _get_live_provider(marketplace: str):
    if marketplace == "wb":
        return WBPublicProvider()
    elif marketplace == "ozon":
        return OzonPublicPlaywrightProvider()
    raise ValueError(f"Неизвестный маркетплейс: {marketplace}")
