"""
Live-провайдер Ozon: публичный поиск через headless Chromium (Playwright).
Не использует Seller API. Работает на VPS с установленным Playwright.

Установка:
    pip install playwright
    playwright install chromium
    playwright install-deps  # системные зависимости
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.providers.base import BaseProvider
from app.logger import get_logger

logger = get_logger(__name__)

OZON_SEARCH_URL = "https://www.ozon.ru/search/?text={query}&from_global=true"

# Сколько ждём загрузки страницы и карточек (мс)
PAGE_LOAD_TIMEOUT = 30_000
CARD_WAIT_TIMEOUT = 20_000

# Браузерные аргументы для VPS (headless, без sandbox)
CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Возможные селекторы контейнера результатов (Ozon периодически меняет)
RESULT_CONTAINER_SELECTORS = [
    "div[data-widget='searchResultsV2']",
    "div[data-widget='tile-catalog']",
    "div[data-widget='searchResultsError']",  # тоже значит страница загружена
    "div.widget-search-result-container",
]


class OzonPublicPlaywrightProvider(BaseProvider):
    """
    Парсит публичную поисковую выдачу Ozon через headless Chromium.
    Стратегии извлечения (от быстрой к медленной):
      1. SSR JSON из <script> тегов (самый надёжный)
      2. window.__NEXT_DATA__ / window.__ozon_state__
      3. DOM heuristics по ссылкам /product/
    """

    marketplace = "ozon"

    def is_available(self) -> bool:
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    async def search(self, query: str, top_n: int) -> list[dict[str, Any]]:
        """Запускает поиск, возвращает список сырых товаров или []."""
        try:
            from playwright.async_api import async_playwright, TimeoutError as PWTimeout
        except ImportError:
            logger.error(
                "Playwright не установлен. "
                "Запусти: pip install playwright && playwright install chromium"
            )
            return []

        logger.info("Ozon Playwright: поиск %r top_n=%d", query, top_n)

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True, args=CHROMIUM_ARGS)
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 900},
                    locale="ru-RU",
                    timezone_id="Europe/Moscow",
                    extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9"},
                )
                # Скрываем webdriver флаг
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = await context.new_page()

                url = OZON_SEARCH_URL.format(query=query.replace(" ", "+"))
                try:
                    await page.goto(url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
                    await _wait_for_any(page, RESULT_CONTAINER_SELECTORS, CARD_WAIT_TIMEOUT)
                except PWTimeout:
                    logger.warning("Ozon Playwright: timeout загрузки для %r", query)
                    await browser.close()
                    return []

                # Небольшая пауза для завершения рендеринга
                await asyncio.sleep(1.5)

                items = await self._extract_items(page, query, top_n)
                await browser.close()

                logger.info("Ozon Playwright: извлечено %d товаров для %r", len(items), query)
                return items

        except Exception as e:
            logger.warning("Ozon Playwright неожиданная ошибка: %s", e)
            return []

    async def _extract_items(self, page, query: str, top_n: int) -> list[dict[str, Any]]:
        """Пробует стратегии извлечения по убыванию надёжности."""
        # 1. SSR JSON в <script> тегах
        items = await _extract_from_script_tags(page, query, top_n)
        if items:
            logger.debug("Ozon: использована стратегия script-tags (%d)", len(items))
            return items

        # 2. window.__NEXT_DATA__ или аналог
        items = await _extract_from_window_state(page, query, top_n)
        if items:
            logger.debug("Ozon: использована стратегия window_state (%d)", len(items))
            return items

        # 3. DOM heuristics
        items = await _extract_from_dom(page, query, top_n)
        logger.debug("Ozon: использована стратегия dom (%d)", len(items))
        return items


# ---------------------------------------------------------------------------
# Стратегия 1: SSR JSON в <script> тегах
# ---------------------------------------------------------------------------

async def _extract_from_script_tags(page, query: str, top_n: int) -> list[dict[str, Any]]:
    """
    Ozon вставляет SSR-данные в <script type="application/json"> теги.
    Ищем крупные JSON-блоки с признаками товарных карточек.
    """
    scripts = await page.evaluate("""() => {
        const results = [];
        const tags = document.querySelectorAll('script[type="application/json"]');
        for (const tag of tags) {
            const text = tag.textContent || '';
            if (text.length > 500 && (text.includes('finalPrice') || text.includes('cardPrice'))) {
                results.push(text);
            }
        }
        return results;
    }""")

    if not scripts:
        return []

    items = []
    for raw_text in scripts:
        try:
            data = json.loads(raw_text)
            found = _walk_for_products(data, query, top_n - len(items))
            items.extend(found)
            if len(items) >= top_n:
                break
        except Exception:
            continue

    return items[:top_n]


# ---------------------------------------------------------------------------
# Стратегия 2: window state объекты
# ---------------------------------------------------------------------------

async def _extract_from_window_state(page, query: str, top_n: int) -> list[dict[str, Any]]:
    """Ищет товары в window.__NEXT_DATA__, window.__ozon_state__ и аналогах."""
    raw = await page.evaluate("""() => {
        const candidates = [
            window.__NEXT_DATA__,
            window.__ozon_state__,
            window.__initialState__,
        ];
        for (const c of candidates) {
            if (c) return JSON.stringify(c);
        }
        return null;
    }""")

    if not raw:
        return []

    try:
        data = json.loads(raw)
        return _walk_for_products(data, query, top_n)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Стратегия 3: DOM heuristics
# ---------------------------------------------------------------------------

async def _extract_from_dom(page, query: str, top_n: int) -> list[dict[str, Any]]:
    """
    Извлекает товары через DOM, опираясь на структуру ссылок /product/.
    Использует несколько CSS-стратегий и price-паттерны в тексте карточки.
    """
    # Скроллим для lazy-load
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
    await asyncio.sleep(0.8)

    raw_cards: list[dict] = await page.evaluate(r"""(top_n) => {
        const results = [];
        const seen = new Set();

        // Ищем все ссылки на продукты
        const links = Array.from(document.querySelectorAll('a[href*="/product/"]'));

        for (const link of links) {
            const href = link.getAttribute('href') || '';
            // Нормализуем href как ключ дедупликации
            const key = href.split('?')[0].replace(/\/$/, '');
            if (!href || seen.has(key) || !key.includes('/product/')) continue;
            seen.add(key);

            // Находим контейнер карточки: поднимаемся до элемента с ценой
            let container = link;
            for (let i = 0; i < 6; i++) {
                container = container.parentElement;
                if (!container) break;
                if (/\d{3,}/.test(container.innerText || '')) break;
            }
            if (!container) continue;

            const cardText = container.innerText || '';

            // Извлекаем цены из текста
            const priceNums = [];
            const priceMatches = cardText.matchAll(/(\d[\d\s]{2,6}\d)(?:\s*₽)?/g);
            for (const m of priceMatches) {
                const n = parseInt(m[1].replace(/\s/g, ''));
                if (n >= 50 && n <= 9999999) priceNums.push(n);
            }

            let currentPrice = 0, oldPrice = null;
            if (priceNums.length === 1) {
                currentPrice = priceNums[0];
            } else if (priceNums.length >= 2) {
                // Меньшая цена — текущая, большая — зачёркнутая
                currentPrice = Math.min(...priceNums);
                const bigger = Math.max(...priceNums);
                if (bigger > currentPrice * 1.05) oldPrice = bigger;
            }

            // Название: ищем самый длинный span/div/h без чисел
            let title = '';
            const textEls = container.querySelectorAll('span, div, h1, h2, h3');
            for (const el of textEls) {
                const t = (el.childNodes.length === 1 && el.childNodes[0].nodeType === 3)
                    ? el.innerText.trim()
                    : '';
                if (t.length > title.length && t.length > 10 && !/^\d/.test(t)) {
                    title = t;
                }
            }
            if (!title) title = link.getAttribute('title') || link.innerText.trim().split('\n')[0];

            // Рейтинг
            let rating = null;
            const ratingMatch = cardText.match(/(\d[.,]\d)\s*(?:из\s*5)?/);
            if (ratingMatch) {
                const r = parseFloat(ratingMatch[1].replace(',', '.'));
                if (r >= 1.0 && r <= 5.0) rating = r;
            }

            // Количество отзывов
            let reviewsCount = null;
            const reviewMatch = cardText.match(/(\d[\d\s]*)\s*(?:отзыв|оценк)/i);
            if (reviewMatch) {
                reviewsCount = parseInt(reviewMatch[1].replace(/\s/g, ''));
            }

            const fullUrl = href.startsWith('http') ? href : 'https://www.ozon.ru' + href;

            results.push({
                url: fullUrl,
                title: title.substring(0, 200),
                current_price: currentPrice,
                old_price: oldPrice,
                rating,
                reviews_count: reviewsCount,
            });

            if (results.length >= top_n) break;
        }
        return results;
    }""", top_n)

    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "query": query,
            "title": c.get("title", ""),
            "current_price": float(c.get("current_price") or 0),
            "old_price": float(c["old_price"]) if c.get("old_price") else None,
            "discount_pct": _calc_discount(c.get("current_price"), c.get("old_price")),
            "rating": c.get("rating"),
            "reviews_count": c.get("reviews_count"),
            "seller_name": None,
            "brand": None,
            "category_guess": None,
            "url": c.get("url"),
            "scraped_at": now,
            "source_mode_used": "live_public",
        }
        for c in raw_cards
        if c.get("current_price") and float(c["current_price"]) > 0
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _wait_for_any(page, selectors: list[str], timeout: int) -> None:
    """Ждёт появления любого из переданных селекторов."""
    from playwright.async_api import TimeoutError as PWTimeout

    tasks = [
        asyncio.create_task(page.wait_for_selector(sel, timeout=timeout))
        for sel in selectors
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    # Если ни один не выполнился — задачи кинут исключения, ловим их
    for t in done:
        try:
            t.result()
            return
        except PWTimeout:
            pass
    raise PWTimeout(f"Ни один из селекторов не найден: {selectors}")


def _walk_for_products(
    node: Any,
    query: str,
    limit: int,
    depth: int = 0,
    found: list | None = None,
) -> list[dict[str, Any]]:
    """
    Рекурсивно обходит JSON-дерево, ищет объекты с признаками товара:
    наличие ценового поля + названия.
    """
    if found is None:
        found = []
    if depth > 12 or len(found) >= limit:
        return found

    if isinstance(node, list):
        for item in node:
            if len(found) >= limit:
                break
            _walk_for_products(item, query, limit, depth + 1, found)
    elif isinstance(node, dict):
        price_keys = {"finalPrice", "cardPrice", "priceV2", "price", "salePrice"}
        name_keys = {"name", "title", "productName", "itemName"}

        has_price = bool(price_keys & node.keys())
        has_name = bool(name_keys & node.keys())

        if has_price and has_name:
            parsed = _parse_json_product(node, query)
            if parsed:
                found.append(parsed)
                return found  # не углубляемся внутрь этого объекта

        for v in node.values():
            if len(found) >= limit:
                break
            _walk_for_products(v, query, limit, depth + 1, found)

    return found


def _parse_json_product(node: dict, query: str) -> dict[str, Any] | None:
    """Извлекает поля из найденного товарного объекта в JSON."""
    try:
        raw_price = (
            node.get("finalPrice")
            or node.get("cardPrice")
            or node.get("priceV2")
            or node.get("price")
            or node.get("salePrice")
            or 0
        )
        price = _parse_price(raw_price)
        if not price:
            return None

        raw_old = (
            node.get("originalPrice")
            or node.get("strikethroughPrice")
            or node.get("crossPrice")
            or node.get("oldPrice")
        )
        old_price = _parse_price(raw_old) if raw_old else None
        if old_price and old_price <= price:
            old_price = None

        name = (
            node.get("name")
            or node.get("title")
            or node.get("productName")
            or node.get("itemName")
            or ""
        )

        url = node.get("url") or node.get("link") or node.get("webURL") or ""
        if url and not url.startswith("http"):
            url = "https://www.ozon.ru" + url

        rating_raw = node.get("rating") or node.get("reviewRating") or node.get("score")
        rating = float(rating_raw) if rating_raw else None
        if rating and not (1.0 <= rating <= 5.0):
            rating = None

        reviews = node.get("reviewsCount") or node.get("feedbacksCount") or node.get("reviews")
        reviews_count = int(reviews) if reviews else None

        return {
            "query": query,
            "title": str(name).strip()[:200],
            "current_price": price,
            "old_price": old_price,
            "discount_pct": _calc_discount(price, old_price),
            "rating": rating,
            "reviews_count": reviews_count,
            "seller_name": _get_nested_str(node, ["seller", "name"], ["brandName"], ["brand"]),
            "brand": _get_nested_str(node, ["brand", "name"], ["brandName"]),
            "category_guess": _get_nested_str(node, ["category", "name"], ["categoryName"]),
            "url": url,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "source_mode_used": "live_public",
        }
    except Exception:
        return None


def _parse_price(raw: Any) -> float:
    """Парсит цену из числа, строки или dict с полем 'value'."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("amount") or 0
    cleaned = re.sub(r"[^\d.]", "", str(raw).replace(",", "."))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _calc_discount(price: Any, old_price: Any) -> float | None:
    """Вычисляет процент скидки, если есть старая цена."""
    try:
        p, o = float(price or 0), float(old_price or 0)
        if o > p > 0:
            return round((1 - p / o) * 100, 1)
    except (TypeError, ValueError):
        pass
    return None


def _get_nested_str(node: dict, *key_paths: list[str]) -> str | None:
    """Пробует несколько путей к строковому значению в словаре."""
    for path in key_paths:
        try:
            val = node
            for k in path:
                val = val[k]
            if val and isinstance(val, str):
                return val.strip() or None
        except (KeyError, TypeError):
            continue
    return None
