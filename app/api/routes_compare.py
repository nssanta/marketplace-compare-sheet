"""
API роутер для эндпоинтов сравнения маркетплейсов.
GET /health — проверка работоспособности
POST /api/v1/compare — основная логика
"""

from fastapi import APIRouter, HTTPException

from app.schemas.compare import CompareRequest, CompareResponse, HealthResponse
from app.services.compare_service import run_comparison
from app.settings import settings
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    """Проверяет что сервер жив и отвечает."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        env=settings.app_env,
    )


@router.post("/api/v1/compare", response_model=CompareResponse, tags=["compare"])
async def compare_marketplaces(request: CompareRequest) -> CompareResponse:
    """
    Запускает сравнение товаров по маркетплейсам.

    - **query**: поисковый запрос
    - **marketplaces**: ["wb", "ozon"] или один из них
    - **top_n**: количество результатов (1-50)
    - **mode**: demo | live_public
    """
    logger.info("POST /api/v1/compare: query=%r mode=%s", request.query, request.mode)

    # Ограничиваем top_n максимальным значением из настроек
    if request.top_n > settings.max_top_n:
        request = request.model_copy(update={"top_n": settings.max_top_n})
        logger.debug("top_n обрезан до %d", settings.max_top_n)

    try:
        result = await run_comparison(request)
        return result
    except Exception as e:
        logger.exception("Ошибка при выполнении сравнения: %s", e)
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")
