"""
Live-провайдер Wildberries через headless Chromium (Playwright).
Обходит 403 на прямых HTTP запросах к search.wb.ru:
браузер несёт cookies/fingerprint, которые антибот пропускает.

Стратегии (в порядке приоритета):
  1. Перехват XHR-ответа search.wb.ru — браузер сам получает JSON
  2. HTML-парсинг карточек как fallback

ENV переменные:
  BROWSER_HEADLESS   — "true"/"false" (default: true)
  BROWSER_USER_AGENT — строка user-agent
  BROWSER_DEBUG_DIR  — куда сохранять скриншоты/HTML при ошибке
"""

import asyncio
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.providers.base import BaseProvider
from app.logger import get_logger

logger = get_logger(__name__)

WB_SEARCH_PAGE = "https://www.wildberries.ru/catalog/0/search.aspx"

DEBUG_DIR = Path(os.getenv("BROWSER_DEBUG_DIR", "/tmp/browser_debug"))
HEADLESS = os.getenv("BROWSER_HEADLESS", "true").lower() not in ("false", "0", "no")
USER_AGENT = os.getenv(
    "BROWSER_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--window-size=1440,900",
]

# Таймауты (мс)
PAGE_TIMEOUT = 35_000
WAIT_AFTER_LOAD = 4_000


class WBBrowserProvider(BaseProvider):
    """
    Live WB провайдер на Playwright.
    Перехватывает XHR-вызов search.wb.ru, который делает сам браузер.
    """

    marketplace = "wb"

    def is_available(self) -> bool:
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    async def search(self, query: str, top_n: int) -> list[dict[str, Any]]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright не установлен")
            return []

        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        t_start = time.monotonic()
        intercepted: dict[str, Any] = {}

        logger.info("WB browser: поиск %r top_n=%d headless=%s", query, top_n, HEADLESS)

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=HEADLESS, args=CHROMIUM_ARGS)
                context = await browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    locale="ru-RU",
                    timezone_id="Europe/Moscow",
                    user_agent=USER_AGENT,
                    extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9"},
                )
                # Скрываем webdriver флаг
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = await context.new_page()

                # Перехватываем JSON-ответ поискового API WB
                async def on_response(response):
                    url = response.url
                    if "search.wb.ru" in url and "search" in url and response.status == 200:
                        try:
                            data = await response.json()
                            if data.get("data", {}).get("products"):
                                intercepted["json"] = data
                                intercepted["api_url"] = url
                                intercepted["status"] = response.status
                                logger.info(
                                    "WB browser: перехвачен ответ %s (статус %d)",
                                    url[:80], response.status,
                                )
                        except Exception as e:
                            logger.debug("WB: не удалось распарсить XHR: %s", e)

                page.on("response", on_response)

                url = f"{WB_SEARCH_PAGE}?sort=popular&search={query}"
                await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)

                # Ждём XHR или карточек
                await asyncio.sleep(random.uniform(2.5, 4.0))
                try:
                    await page.wait_for_selector(
                        "article.product-card, .j-card-item",
                        timeout=WAIT_AFTER_LOAD,
                    )
                except Exception:
                    pass

                final_url = page.url
                page_title = await page.title()
                elapsed = time.monotonic() - t_start

                logger.info(
                    "WB browser: страница загружена %.1fс | title=%r | intercepted=%s",
                    elapsed, page_title, bool(intercepted),
                )

                # Стратегия 1: перехваченный JSON
                if intercepted.get("json"):
                    products = (
                        intercepted["json"].get("data", {}).get("products", [])[:top_n]
                    )
                    if products:
                        logger.info(
                            "WB browser: %d товаров из XHR-перехвата", len(products)
                        )
                        await browser.close()
                        return self._normalize_json(query, products)

                # Стратегия 2: HTML-парсинг
                logger.info("WB browser: XHR не перехвачен, пробуем HTML парсинг")
                items = await self._parse_html(page, query, top_n)

                if not items:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    shot = DEBUG_DIR / f"wb_fail_{ts}.png"
                    dump = DEBUG_DIR / f"wb_fail_{ts}.html"
                    await page.screenshot(path=str(shot), full_page=True)
                    (dump).write_text(await page.content(), encoding="utf-8")
                    logger.warning(
                        "WB browser: 0 товаров | title=%r | url=%s | screenshot=%s",
                        page_title, final_url, shot,
                    )

                await browser.close()
                return items

        except Exception as e:
            elapsed = time.monotonic() - t_start
            logger.warning("WB browser exception (%.1fс): %s", elapsed, e)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            return []

    # ------------------------------------------------------------------
    # HTML-парсинг
    # ------------------------------------------------------------------

    async def _parse_html(self, page, query: str, top_n: int) -> list[dict[str, Any]]:
        """Парсит карточки из DOM WB. Несколько попыток с разными селекторами."""
        card_selectors = [
            "article.product-card",
            ".j-card-item",
            "[class*='product-card'][class*='j-card']",
        ]
        cards = []
        used_sel = ""
        for sel in card_selectors:
            cards = await page.query_selector_all(sel)
            if cards:
                used_sel = sel
                break

        logger.info("WB HTML: найдено %d карточек по %r", len(cards), used_sel)
        results = []

        for card in cards[:top_n]:
            try:
                item: dict[str, Any] = {"query": query}

                # Title
                for sel in [
                    "span.product-card__name",
                    ".goods-name",
                    "[class*='product-card__name']",
                    "span[class*='name']",
                ]:
                    el = await card.query_selector(sel)
                    if el:
                        item["title"] = (await el.inner_text()).strip()
                        break

                # Price
                for sel in [
                    "ins.price-block__final-price",
                    ".price-block__final-price",
                    "[class*='final-price']",
                    "[class*='price']",
                ]:
                    el = await card.query_selector(sel)
                    if el:
                        item["current_price"] = _parse_price(await el.inner_text())
                        if item["current_price"] > 0:
                            break

                # Old price
                for sel in [
                    "del.price-block__old-price",
                    ".price-block__old-price",
                    "[class*='old-price']",
                ]:
                    el = await card.query_selector(sel)
                    if el:
                        op = _parse_price(await el.inner_text())
                        if op > 0:
                            item["old_price"] = op
                        break

                # Rating
                for sel in [
                    "span.address-rate-mini",
                    ".product-card__rating",
                    "[class*='rate']",
                ]:
                    el = await card.query_selector(sel)
                    if el:
                        try:
                            item["rating"] = float(
                                (await el.inner_text()).strip().replace(",", ".")
                            )
                        except Exception:
                            pass
                        break

                # Reviews count
                for sel in ["span.product-card__count", "[class*='count']"]:
                    el = await card.query_selector(sel)
                    if el:
                        txt = await el.inner_text()
                        digits = "".join(filter(str.isdigit, txt))
                        if digits:
                            item["reviews_count"] = int(digits)
                        break

                # URL
                for sel in ["a.product-card__link", "a[href*='/catalog/']", "a"]:
                    el = await card.query_selector(sel)
                    if el:
                        href = await el.get_attribute("href")
                        if href:
                            item["url"] = (
                                href
                                if href.startswith("http")
                                else f"https://www.wildberries.ru{href}"
                            )
                            break

                if item.get("title") and item.get("current_price", 0) > 0:
                    results.append(item)
            except Exception as e:
                logger.debug("WB HTML: ошибка карточки: %s", e)

        return results

    # ------------------------------------------------------------------
    # Нормализация перехваченного JSON
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_json(query: str, products: list[dict]) -> list[dict[str, Any]]:
        result = []
        for p in products:
            price_raw = p.get("salePriceU", 0) or p.get("priceU", 0)
            old_price_raw = p.get("priceU", 0)
            current_price = price_raw / 100
            old_price = old_price_raw / 100 if old_price_raw != price_raw else None
            result.append({
                "query": query,
                "title": p.get("name", ""),
                "current_price": current_price,
                "old_price": old_price,
                "discount_pct": p.get("sale"),
                "rating": p.get("reviewRating"),
                "reviews_count": p.get("feedbacks"),
                "seller_name": p.get("brand"),
                "brand": p.get("brand"),
                "category_guess": None,
                "url": f"https://www.wildberries.ru/catalog/{p.get('id')}/detail.aspx",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "source_mode_used": "live_public",
            })
        return result


def _parse_price(text: str) -> float:
    digits = re.sub(r"[^\d]", "", str(text))
    return float(digits) if digits else 0.0
