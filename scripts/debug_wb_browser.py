#!/usr/bin/env python3
"""
Debug script: WB browser live provider.
Запуск: python scripts/debug_wb_browser.py "наушники"

Печатает:
  final_url, page_title, items_found, first_item_preview,
  screenshot_path, html_dump_path, elapsed_seconds

Честный вывод — без fallback, без маскировки.
"""

import asyncio
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

QUERY = sys.argv[1] if len(sys.argv) > 1 else "наушники"
TOP_N = 5
DEBUG_DIR = Path("/tmp/browser_debug")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("FAIL: playwright not installed")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"WB BROWSER DEBUG | query={QUERY!r} | top_n={TOP_N}")
    print(f"{'='*60}\n")

    t_start = time.monotonic()
    intercepted: dict = {}
    console_errors: list[str] = []
    failed_requests: list[str] = []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    screenshot_path = DEBUG_DIR / f"wb_{ts}.png"
    html_dump_path = DEBUG_DIR / f"wb_{ts}.html"

    CHROMIUM_ARGS = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
    ]
    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            user_agent=USER_AGENT,
            extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9"},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        # Перехватываем все XHR к search.wb.ru
        all_wb_responses: list[dict] = []

        async def on_response(response):
            url = response.url
            if "search.wb.ru" in url:
                status = response.status
                try:
                    body = await response.body()
                    body_len = len(body)
                    body_preview = body[:500].decode("utf-8", errors="replace")
                except Exception:
                    body_len = 0
                    body_preview = "<body unreadable>"
                entry = {
                    "url": url,
                    "status": status,
                    "body_len": body_len,
                    "body_preview": body_preview,
                }
                all_wb_responses.append(entry)
                if status == 200:
                    try:
                        import json
                        data = json.loads(body)
                        products = data.get("data", {}).get("products", [])
                        if products:
                            intercepted["json"] = data
                            intercepted["url"] = url
                            intercepted["products_count"] = len(products)
                    except Exception:
                        pass

        def on_console(msg):
            if msg.type in ("error", "warning"):
                console_errors.append(f"[{msg.type}] {msg.text}")

        def on_request_failed(req):
            failed_requests.append(f"{req.failure} | {req.url[:100]}")

        page.on("response", on_response)
        page.on("console", on_console)
        page.on("requestfailed", on_request_failed)

        url = f"https://www.wildberries.ru/catalog/0/search.aspx?sort=popular&search={QUERY}"
        print(f"[1] Navigate to: {url}")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
        except Exception as e:
            print(f"[!] goto error: {e}")

        await asyncio.sleep(3.5)

        try:
            await page.wait_for_selector("article.product-card, .j-card-item", timeout=5000)
        except Exception:
            pass

        final_url = page.url
        page_title = await page.title()
        elapsed = time.monotonic() - t_start

        # Сохраняем артефакты
        await page.screenshot(path=str(screenshot_path), full_page=True)
        html_dump_path.write_text(await page.content(), encoding="utf-8")

        # Считаем карточки по каждому селектору
        selectors_found = {}
        for sel in [
            "article.product-card",
            ".j-card-item",
            "[class*='product-card']",
            "a[href*='/catalog/']",
        ]:
            count = len(await page.query_selector_all(sel))
            selectors_found[sel] = count

        # Пробуем распарсить карточки
        items = []
        cards = await page.query_selector_all("article.product-card")
        if not cards:
            cards = await page.query_selector_all(".j-card-item")

        for card in cards[:TOP_N]:
            try:
                item = {}
                for sel in ["span.product-card__name", ".goods-name", "[class*='product-card__name']"]:
                    el = await card.query_selector(sel)
                    if el:
                        item["title"] = (await el.inner_text()).strip()
                        break
                for sel in ["ins.price-block__final-price", ".price-block__final-price", "[class*='final-price']"]:
                    el = await card.query_selector(sel)
                    if el:
                        txt = await el.inner_text()
                        digits = re.sub(r"[^\d]", "", txt)
                        item["price"] = int(digits) if digits else 0
                        break
                if item.get("title") or item.get("price"):
                    items.append(item)
            except Exception:
                pass

        await browser.close()

    # ---------- ВЫВОД ----------
    print(f"\n[2] final_url      = {final_url}")
    print(f"[3] page_title     = {page_title!r}")
    print(f"[4] elapsed        = {elapsed:.1f}s")
    print(f"\n[5] WB XHR responses intercepted: {len(all_wb_responses)}")
    for r in all_wb_responses:
        print(f"     status={r['status']} len={r['body_len']} url={r['url'][:100]}")
        print(f"     preview: {r['body_preview'][:200]!r}")

    print(f"\n[6] Intercepted JSON products: {intercepted.get('products_count', 0)}")
    if intercepted.get("url"):
        print(f"     from: {intercepted['url'][:100]}")

    print(f"\n[7] Cards by selector:")
    for sel, count in selectors_found.items():
        print(f"     {sel!r:45s} → {count}")

    print(f"\n[8] items_found (HTML parse) = {len(items)}")
    if items:
        print(f"     first_item_preview = {items[0]}")

    print(f"\n[9] console_errors ({len(console_errors)}):")
    for e in console_errors[:5]:
        print(f"     {e}")

    print(f"\n[10] failed_requests ({len(failed_requests)}):")
    for r in failed_requests[:5]:
        print(f"     {r}")

    print(f"\n[11] screenshot_path = {screenshot_path}")
    print(f"[12] html_dump_path  = {html_dump_path}")

    total = (intercepted.get("products_count") or 0) + len(items)
    print(f"\n{'='*60}")
    print(f"WB browser live = {'PASS' if total > 0 else 'FAIL'}")
    print(f"WB items found  = {total}")
    if total == 0:
        if all_wb_responses and all(r["status"] == 403 for r in all_wb_responses):
            print("WB root cause   = anti-bot (403 even from browser)")
        elif not all_wb_responses:
            print("WB root cause   = XHR not intercepted / page didn't trigger search API")
        elif sum(selectors_found.values()) == 0:
            print("WB root cause   = empty DOM (page loaded but no cards)")
        else:
            print("WB root cause   = parser bug (cards found but parse failed)")
    print(f"{'='*60}\n")


asyncio.run(main())
