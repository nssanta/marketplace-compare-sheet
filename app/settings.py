"""
Конфигурация приложения через переменные окружения.
Все параметры читаются из .env файла.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Режим приложения: development / production
    app_env: str = Field(default="development", env="APP_ENV")

    # Хост и порт для uvicorn
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")

    # Режим по умолчанию, если не указан в запросе
    default_mode: str = Field(default="demo", env="DEFAULT_MODE")

    # Таймаут в секундах для HTTP-запросов к маркетплейсам
    http_timeout: float = Field(default=10.0, env="HTTP_TIMEOUT")

    # Максимальное количество результатов на запрос
    max_top_n: int = Field(default=50, env="MAX_TOP_N")

    # Секретный ключ для опциональной простой auth (пока не используется)
    api_key: str = Field(default="", env="API_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Синглтон настроек — импортировать из других модулей
settings = Settings()
