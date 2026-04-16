"""
Точка входа FastAPI приложения.
Здесь настраиваем логирование, подключаем роутеры, добавляем middleware.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_compare import router
from app.logger import setup_logging, get_logger
from app.settings import settings

# Настраиваем логи до создания app
setup_logging(level="DEBUG" if settings.app_env == "development" else "INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Хуки старта и остановки приложения."""
    logger.info("Marketplace Compare Sheet backend запущен (env=%s)", settings.app_env)
    yield
    logger.info("Сервер останавливается")


app = FastAPI(
    title="Marketplace Compare Sheet",
    description="Backend для сравнения товаров WB и Ozon через Google Sheets",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — разрешаем запросы от Google Apps Script
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В проде можно ограничить до конкретных доменов
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Подключаем роутеры
app.include_router(router)

logger.info("Роутеры подключены")
