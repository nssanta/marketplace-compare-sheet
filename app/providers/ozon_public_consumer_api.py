"""
Enrichment layer: обогащает товарные карточки Ozon данными
из публичного consumer page endpoint.

URL формат:
    https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/name-id/

Не требует авторизации для большинства страниц, но может вернуть пустой
ответ при rate-limiting или изменении структуры. Все ошибки обрабатываются
gracefully — items возвращаются как есть.
"""

import json
from typing import Any

import httpx

from app.logger import get_logger

logger = get_logger(__name__)

OZON_PAGE_API = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://www.ozon.ru/",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}


async def enrich_with_consumer_api(
    items: list[dict[str, Any]],
    timeout: float = 8.0,
    max_enrich: int = 5,
) -> list[dict[str, Any]]:
    """
    Пробует обогатить первые max_enrich items данными из consumer page API.
    Заполняет seller_name, brand, category_guess если они отсутствуют.
    Возвращает список items независимо от успеха — не бросает исключений.

    Args:
        items: сырые товарные карточки от Playwright provider
        timeout: таймаут на один HTTP запрос (сек)
        max_enrich: максимум карточек для обогащения (экономим время)
    """
    if not items:
        return items

    enriched_count = 0

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=_HEADERS,
            follow_redirects=True,
        ) as client:
            for i, item in enumerate(items):
                if enriched_count >= max_enrich:
                    break
                url = item.get("url") or ""
                product_path = _extract_product_path(url)
                if not product_path:
                    continue

                try:
                    extra = await _fetch_product_page(client, product_path)
                    if extra:
                        items[i] = _merge(item, extra)
                        enriched_count += 1
                        logger.debug(
                            "Ozon enrich OK: %s", item.get("title", "")[:50]
                        )
                except Exception as e:
                    logger.debug("Ozon enrich skip (%s): %s", product_path, e)

    except Exception as e:
        logger.warning("Ozon consumer API общая ошибка: %s", e)

    logger.info(
        "Ozon consumer API: обогащено %d/%d товаров",
        enriched_count,
        min(len(items), max_enrich),
    )
    return items


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_product_path(url: str) -> str | None:
    """Извлекает путь /product/... из полного URL."""
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path
        if "/product/" in path:
            # Убираем trailing slash для чистоты
            return path.rstrip("/") + "/"
    except Exception:
        pass
    return None


async def _fetch_product_page(
    client: httpx.AsyncClient,
    product_path: str,
) -> dict[str, Any] | None:
    """
    Запрашивает consumer page API и возвращает распарсенные данные.
    Возвращает None если ответ невалидный или endpoint не ответил.
    """
    resp = await client.get(OZON_PAGE_API, params={"url": product_path})

    if resp.status_code != 200:
        logger.debug("Ozon page API: HTTP %d для %s", resp.status_code, product_path)
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    return _parse_page_response(data)


def _parse_page_response(data: dict) -> dict[str, Any]:
    """
    Разбирает ответ consumer page API.
    Структура: {"widgetStates": {"key": "<json_string>", ...}, ...}
    Ищет seller, brand, breadcrumbs в widgetStates.
    """
    result: dict[str, Any] = {}
    widget_states = data.get("widgetStates") or {}

    for raw_value in widget_states.values():
        if not isinstance(raw_value, str) or len(raw_value) < 10:
            continue
        try:
            widget = json.loads(raw_value)
            if not isinstance(widget, dict):
                continue
            _extract_from_widget(widget, result)
        except Exception:
            continue

        # Если уже нашли все поля — прекращаем
        if result.get("seller_name") and result.get("brand") and result.get("category_guess"):
            break

    return result


def _extract_from_widget(widget: dict, result: dict) -> None:
    """Извлекает seller, brand, category из одного widget-объекта."""
    # Seller
    if not result.get("seller_name"):
        seller = widget.get("seller") or widget.get("brandInfo") or {}
        if isinstance(seller, dict):
            name = seller.get("name") or seller.get("companyName") or seller.get("title")
            if name:
                result["seller_name"] = str(name).strip()
        elif isinstance(seller, str) and seller:
            result["seller_name"] = seller.strip()

    # Brand
    if not result.get("brand"):
        brand = widget.get("brand") or {}
        if isinstance(brand, dict):
            name = brand.get("name") or brand.get("title")
            if name:
                result["brand"] = str(name).strip()
        elif isinstance(brand, str) and brand:
            result["brand"] = brand.strip()
        # Иногда brand прямо в плоском поле
        if not result.get("brand"):
            flat_brand = widget.get("brandName") or widget.get("manufacturerName")
            if flat_brand:
                result["brand"] = str(flat_brand).strip()

    # Category из breadcrumbs
    if not result.get("category_guess"):
        breadcrumbs = widget.get("breadcrumbs") or widget.get("breadCrumbs") or []
        if isinstance(breadcrumbs, list) and len(breadcrumbs) >= 2:
            # Берём предпоследний элемент (категория, не сам товар)
            crumb = breadcrumbs[-2]
            if isinstance(crumb, dict):
                name = crumb.get("text") or crumb.get("title") or crumb.get("name")
                if name:
                    result["category_guess"] = str(name).strip()


def _merge(item: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """
    Мержит extra в item: заполняет только пустые поля, не перезаписывает.
    """
    for key in ("seller_name", "brand", "category_guess"):
        if not item.get(key) and extra.get(key):
            item[key] = extra[key]
    return item
