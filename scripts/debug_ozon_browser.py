#!/usr/bin/env python3
"""
Debug script: Ozon browser live provider.
Запуск: python scripts/debug_ozon_browser.py "наушники"

Печатает:
  final_url, page_title, items_found (per strategy), first_item_preview,
  screenshot_path, html_dump_path, elapsed_seconds

Честный вывод — без fallback, без маскировки.
"""

import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

QUERY = sys.argv[1] if len(sys.argv) > 1 else "наушники"
TOP_N = 5
DEBUG_DIR = Path("/tmp/browser_debug")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

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

RESULT_CONTAINER_SELECTORS = [
    "div[data-widget='searchResultsV2']",
    "div[data-widget='tile-catalog']",
    "div[data-widget='searchResultsError']",
    "div.widget-search-result-container",
    "div[class*='tileGrid']",
    "div[class*='searchResults']",
]


async def main():
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("FAIL: playwright not installed")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"OZON BROWSER DEBUG | query={QUERY!r} | top_n={TOP_N}")
    print(f"{'='*60}\n")

    t_start = time.monotonic()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = DEBUG_DIR / f"ozon_{ts}.png"
    html_dump_path = DEBUG_DIR / f"ozon_{ts}.html"

    console_errors: list[str] = []
    failed_requests: list[str] = []
    intercepted_api: list[dict] = []

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

        # Перехватываем Ozon entrypoint API и другие JSON-ответы
        async def on_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            if "ozon.ru" in url and "json" in ct:
                try:
                    body = await response.body()
                    body_len = len(body)
                    preview = body[:300].decode("utf-8", errors="replace")
                    intercepted_api.append({
                        "url": url[:120],
                        "status": response.status,
                        "body_len": body_len,
                        "preview": preview,
                    })
                except Exception:
                    pass

        def on_console(msg):
            if msg.type in ("error", "warning"):
                console_errors.append(f"[{msg.type}] {msg.text[:200]}")

        def on_request_failed(req):
            failed_requests.append(f"{req.failure} | {req.url[:100]}")

        page.on("response", on_response)
        page.on("console", on_console)
        page.on("requestfailed", on_request_failed)

        url = f"https://www.ozon.ru/search/?text={QUERY}&from_global=true"
        print(f"[1] Navigate to: {url}")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
        except Exception as e:
            print(f"[!] goto error: {e}")

        # Ждём появления любого из известных контейнеров
        container_found = None
        for sel in RESULT_CONTAINER_SELECTORS:
            try:
                await page.wait_for_selector(sel, timeout=8000)
                container_found = sel
                break
            except Exception:
                pass

        await asyncio.sleep(2.0)
        # Скроллим для lazy-load
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.4)")
        await asyncio.sleep(1.5)

        final_url = page.url
        page_title = await page.title()
        elapsed = time.monotonic() - t_start

        # Артефакты
        await page.screenshot(path=str(screenshot_path), full_page=True)
        html_content = await page.content()
        html_dump_path.write_text(html_content, encoding="utf-8")

        # Карточки по каждому селектору
        card_selectors = {
            "div[data-widget='searchResultsV2']": None,
            "div[data-widget='tile-catalog']": None,
            "a[href*='/product/']": None,
            "div[class*='tileRoot']": None,
            "div[class*='tile-root']": None,
            "div[class*='tileGrid'] > div": None,
            "[class*='searchResults'] a": None,
        }
        for sel in card_selectors:
            count = len(await page.query_selector_all(sel))
            card_selectors[sel] = count

        # Стратегия 1: script[type="application/json"]
        strat1_items = 0
        scripts = await page.evaluate("""() => {
            const tags = document.querySelectorAll('script[type="application/json"]');
            const res = [];
            for (const t of tags) {
                const txt = t.textContent || '';
                if (txt.length > 300 && (txt.includes('finalPrice') || txt.includes('cardPrice') || txt.includes('itemName'))) {
                    res.push(txt.substring(0, 2000));
                }
            }
            return res;
        }""")
        strat1_items = len(scripts)

        # Стратегия 2: window state
        window_state = await page.evaluate("""() => {
            const candidates = [window.__NEXT_DATA__, window.__ozon_state__, window.__initialState__];
            for (const c of candidates) {
                if (c) return JSON.stringify(c).substring(0, 500);
            }
            return null;
        }""")

        # Стратегия 3: ссылки /product/ в DOM
        product_links = await page.evaluate("""(top_n) => {
            const links = Array.from(document.querySelectorAll('a[href*="/product/"]'));
            const seen = new Set();
            const results = [];
            for (const link of links) {
                const href = link.getAttribute('href') || '';
                const key = href.split('?')[0];
                if (!key || seen.has(key)) continue;
                seen.add(key);

                // Ищем контейнер с ценой
                let container = link;
                for (let i = 0; i < 6; i++) {
                    container = container.parentElement;
                    if (!container) break;
                    const text = container.innerText || '';
                    if (/[1-9]\d{2,}/.test(text)) break;
                }

                const text = container ? (container.innerText || '') : '';
                const priceNums = [];
                for (const m of (text.matchAll(/(\d[\d\s]{1,5}\d)(?:\s*₽)?/g) || [])) {
                    const n = parseInt(m[1].replace(/\s/g, ''));
                    if (n >= 50 && n <= 9999999) priceNums.push(n);
                }

                let currentPrice = 0, oldPrice = null;
                if (priceNums.length >= 1) {
                    currentPrice = Math.min(...priceNums);
                    const bigger = Math.max(...priceNums);
                    if (bigger > currentPrice * 1.05) oldPrice = bigger;
                }

                // Заголовок: самый длинный span/div без цифр в начале
                let title = link.getAttribute('title') || link.innerText.trim().split('\\n')[0] || '';
                if (container) {
                    for (const el of container.querySelectorAll('span, a, h2, h3')) {
                        const t = (el.innerText || '').trim();
                        if (t.length > title.length && t.length > 15 && !/^[\\d₽]/.test(t)) {
                            title = t;
                        }
                    }
                }

                results.push({
                    url: href.startsWith('http') ? href : 'https://www.ozon.ru' + href,
                    title: title.substring(0, 180),
                    current_price: currentPrice,
                    old_price: oldPrice,
                });
                if (results.length >= top_n) break;
            }
            return results;
        }""", TOP_N)

        items_dom = [i for i in product_links if i.get("current_price", 0) > 0]

        await browser.close()

    # ---------- ВЫВОД ----------
    print(f"\n[2]  final_url      = {final_url}")
    print(f"[3]  page_title     = {page_title!r}")
    print(f"[4]  elapsed        = {elapsed:.1f}s")
    print(f"[5]  container_found= {container_found!r}")

    print(f"\n[6]  Intercepted JSON API calls ({len(intercepted_api)}):")
    for r in intercepted_api[:8]:
        print(f"     status={r['status']} len={r['body_len']:6d} | {r['url']}")
    if len(intercepted_api) > 8:
        print(f"     ... and {len(intercepted_api)-8} more")

    print(f"\n[7]  Card selector counts:")
    for sel, count in card_selectors.items():
        print(f"     {sel!r:50s} → {count}")

    print(f"\n[8]  Strategy 1 (script[type=json] with prices): {strat1_items} blocks found")
    print(f"[9]  Strategy 2 (window state): {'FOUND' if window_state else 'NOT FOUND'}")
    if window_state:
        print(f"     preview: {window_state[:200]!r}")
    print(f"[10] Strategy 3 (DOM /product/ links): {len(product_links)} links | {len(items_dom)} with price")
    if items_dom:
        print(f"     first_item_preview = {items_dom[0]}")

    print(f"\n[11] console_errors ({len(console_errors)}):")
    for e in console_errors[:5]:
        print(f"     {e}")

    print(f"\n[12] failed_requests ({len(failed_requests)}):")
    for r in failed_requests[:5]:
        print(f"     {r}")

    print(f"\n[13] screenshot_path = {screenshot_path}")
    print(f"[14] html_dump_path  = {html_dump_path}")
    print(f"[15] html_size       = {len(html_content)} chars")

    total_items = len(items_dom)
    print(f"\n{'='*60}")
    print(f"Ozon browser live = {'PASS' if total_items > 0 else 'FAIL'}")
    print(f"Ozon items found  = {total_items}")
    if total_items == 0:
        if not container_found:
            print("Ozon root cause   = anti-bot / page blocked (no result container loaded)")
        elif card_selectors.get("a[href*='/product/']", 0) == 0:
            print("Ozon root cause   = empty DOM (container loaded but no product links)")
        else:
            print("Ozon root cause   = parser bug (links found but price extraction failed)")
    print(f"{'='*60}\n")


asyncio.run(main())
