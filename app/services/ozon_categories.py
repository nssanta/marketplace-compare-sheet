"""
Helper: получение дерева категорий Ozon через публичный consumer endpoint.

Endpoint:
    https://www.ozon.ru/api/composer-api.bx/_action/v2/categoryChildV3
    ?menuId=185&categoryId=<id>

categoryId=0 — корень каталога (все топ-уровневые категории).
Вызов вернёт дочерние категории для указанного узла.

Использование:
    from app.services.ozon_categories import fetch_category_tree
    cats = await fetch_category_tree(category_id=0)
    # [{"id": 7500, "name": "Электроника", "url": "/electronics/", ...}, ...]
"""

from typing import Any

import httpx

from app.logger import get_logger

logger = get_logger(__name__)

OZON_CATEGORY_URL = (
    "https://www.ozon.ru/api/composer-api.bx/_action/v2/categoryChildV3"
    "?menuId=185&categoryId={category_id}"
)

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


async def fetch_category_tree(
    category_id: int = 0,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """
    Возвращает дочерние категории для categoryId.
    category_id=0 → корень каталога.
    При любой ошибке возвращает [] без исключений.

    Args:
        category_id: ID родительской категории (0 = корень)
        timeout: таймаут HTTP запроса в секундах
    """
    url = OZON_CATEGORY_URL.format(category_id=category_id)
    logger.info("Ozon categories: categoryId=%d", category_id)

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=_HEADERS,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        categories = _parse_response(data)
        logger.info("Ozon categories: получено %d категорий", len(categories))
        return categories

    except httpx.HTTPStatusError as e:
        logger.warning("Ozon categories HTTP %d: %s", e.response.status_code, e)
        return []
    except httpx.RequestError as e:
        logger.warning("Ozon categories сетевая ошибка: %s", e)
        return []
    except Exception as e:
        logger.warning("Ozon categories неожиданная ошибка: %s", e)
        return []


async def fetch_full_tree(
    root_id: int = 0,
    depth: int = 1,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """
    Рекурсивно загружает дерево категорий до указанной глубины.
    depth=1 — только прямые потомки (один уровень).
    depth=2 — потомки и их потомки.

    Используй осторожно: глубокое дерево = много запросов.

    Args:
        root_id: ID корневой категории
        depth: максимальная глубина рекурсии
        timeout: таймаут на каждый запрос
    """
    categories = await fetch_category_tree(category_id=root_id, timeout=timeout)
    if depth <= 1:
        return categories

    for cat in categories:
        if cat.get("id") and cat.get("children_count", 0) > 0:
            cat["children"] = await fetch_full_tree(
                root_id=cat["id"],
                depth=depth - 1,
                timeout=timeout,
            )

    return categories


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_response(data: Any) -> list[dict[str, Any]]:
    """Нормализует ответ endpoint в плоский список категорий."""
    if not isinstance(data, dict):
        return []

    # Endpoint может оборачивать результат в разные ключи
    raw_items: list = (
        data.get("categories")
        or data.get("items")
        or data.get("children")
        or data.get("catalog")
        or []
    )

    # Если ничего не нашли — ищем первый список словарей
    if not raw_items:
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                raw_items = v
                break

    return [_normalize_category(item) for item in raw_items if isinstance(item, dict)]


def _normalize_category(item: dict) -> dict[str, Any]:
    """Приводит одну категорию к единому формату."""
    cat_id = item.get("id") or item.get("categoryId") or item.get("ID")
    name = (
        item.get("title")
        or item.get("name")
        or item.get("categoryName")
        or item.get("Name")
        or ""
    )
    url = item.get("url") or item.get("link") or item.get("URL") or ""

    # children_count: берём явное значение или считаем вложенный список
    children_count = (
        item.get("childrenCount")
        or item.get("children_count")
        or item.get("childCount")
        or len(item.get("children") or [])
    )

    return {
        "id": int(cat_id) if cat_id else None,
        "name": str(name).strip(),
        "url": str(url).strip() or None,
        "children_count": int(children_count) if children_count else 0,
    }
