#!/usr/bin/env python3
"""
Smoke-test script для верификации backend на VPS.

Запуск:
    python scripts/smoke_test.py [BASE_URL]

По умолчанию BASE_URL = http://localhost:8000

Тесты:
    1. GET /health
    2. POST /api/v1/compare  mode=demo  (WB + Ozon)
    3. POST /api/v1/compare  mode=live_public  marketplaces=[wb]
    4. POST /api/v1/compare  mode=live_public  marketplaces=[ozon]  (Playwright)

Для каждого теста:
    - показывает ожидаемый shape
    - показывает реальный ответ (ключевые поля)
    - явно помечает PASS / FAIL / FALLBACK
"""

import sys
import time
import json
import urllib.request
import urllib.error
from typing import Any


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"

# ANSI цвета
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def _post(path: str, payload: dict, timeout: int = 120) -> tuple[int, dict]:
    url = BASE_URL + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def _get(path: str, timeout: int = 10) -> tuple[int, dict]:
    url = BASE_URL + path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def _fmt_item(item: dict) -> str:
    return (
        f"  title={item.get('title','')[:40]!r}  "
        f"price={item.get('current_price')}  "
        f"rating={item.get('rating')}  "
        f"source={item.get('source_mode_used')}"
    )


def _print_result(label: str, status: str, detail: str = ""):
    colors = {"PASS": GREEN, "FAIL": RED, "FALLBACK": YELLOW, "INFO": CYAN}
    color = colors.get(status, RESET)
    print(f"  {color}{BOLD}[{status}]{RESET} {label}")
    if detail:
        for line in detail.strip().splitlines():
            print(f"         {line}")


def _section(title: str):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{CYAN}{'─'*60}{RESET}")


# ─────────────────────────────────────────────────────────────
# TEST 1: Health check
# ─────────────────────────────────────────────────────────────

def test_health():
    _section("TEST 1 — GET /health")
    print("  Expected shape:")
    print('  {"status": "ok", "version": "1.0.0", "env": "..."}')
    print()

    t0 = time.monotonic()
    code, body = _get("/health")
    elapsed = time.monotonic() - t0

    if code == 200 and body.get("status") == "ok":
        _print_result(
            f"HTTP {code}  status={body.get('status')}  version={body.get('version')}  env={body.get('env')}  ({elapsed:.2f}s)",
            "PASS",
        )
        return True
    else:
        _print_result(f"HTTP {code}  body={body}  ({elapsed:.2f}s)", "FAIL")
        return False


# ─────────────────────────────────────────────────────────────
# TEST 2: Demo compare (WB + Ozon)
# ─────────────────────────────────────────────────────────────

def test_demo():
    _section("TEST 2 — POST /api/v1/compare  mode=demo  (WB + Ozon)")
    payload = {"query": "наушники bluetooth", "marketplaces": ["wb", "ozon"], "top_n": 3, "mode": "demo"}
    print(f"  Payload: {json.dumps(payload)}")
    print()
    print("  Expected shape:")
    print('  {"ok": true, "source_mode_used": "demo", "wb_items": [...3], "ozon_items": [...3],')
    print('   "summary": {"wb_count": 3, "ozon_count": 3, "price_winner": "wb|ozon|tie"}, "errors": []}')
    print()

    t0 = time.monotonic()
    code, body = _post("/api/v1/compare", payload, timeout=30)
    elapsed = time.monotonic() - t0

    if code != 200 or not body.get("ok"):
        _print_result(f"HTTP {code}  ({elapsed:.2f}s)  body={str(body)[:200]}", "FAIL")
        return False

    wb_n   = len(body.get("wb_items", []))
    ozon_n = len(body.get("ozon_items", []))
    summ   = body.get("summary", {})
    errs   = body.get("errors", [])
    src    = body.get("source_mode_used")

    ok = wb_n > 0 and ozon_n > 0 and src == "demo"
    status = "PASS" if ok else "FAIL"

    detail = (
        f"source_mode_used={src}  wb_items={wb_n}  ozon_items={ozon_n}  "
        f"winner={summ.get('price_winner')}  errors={errs}  ({elapsed:.2f}s)\n"
        f"wb[0]:   {_fmt_item(body['wb_items'][0]) if wb_n else 'EMPTY'}\n"
        f"ozon[0]: {_fmt_item(body['ozon_items'][0]) if ozon_n else 'EMPTY'}"
    )
    _print_result("demo WB+Ozon", status, detail)
    return ok


# ─────────────────────────────────────────────────────────────
# TEST 3: WB live
# ─────────────────────────────────────────────────────────────

def test_wb_live():
    _section("TEST 3 — POST /api/v1/compare  mode=live_public  marketplaces=[wb]")
    payload = {"query": "наушники bluetooth", "marketplaces": ["wb"], "top_n": 3, "mode": "live_public"}
    print(f"  Payload: {json.dumps(payload)}")
    print()
    print("  Expected shape (live):")
    print('  {"ok": true, "source_mode_used": "live_public", "wb_items": [...], "errors": []}')
    print("  Expected shape (fallback):")
    print('  {"ok": true, "source_mode_used": "demo", "wb_items": [...], "errors": ["wb: ..."]}')
    print()

    t0 = time.monotonic()
    code, body = _post("/api/v1/compare", payload, timeout=30)
    elapsed = time.monotonic() - t0

    if code != 200 or not body.get("ok"):
        _print_result(f"HTTP {code}  ({elapsed:.2f}s)", "FAIL")
        return False

    wb_n  = len(body.get("wb_items", []))
    src   = body.get("source_mode_used")
    errs  = body.get("errors", [])

    if src == "live_public" and wb_n > 0:
        status = "PASS"
        label = f"LIVE data confirmed  wb_items={wb_n}  ({elapsed:.2f}s)"
    elif wb_n > 0:
        status = "FALLBACK"
        label = f"fallback to demo  wb_items={wb_n}  errors={errs}  ({elapsed:.2f}s)"
    else:
        status = "FAIL"
        label = f"no items returned  src={src}  errors={errs}  ({elapsed:.2f}s)"

    detail = (
        f"source_mode_used={src}  wb_items={wb_n}  errors={errs}\n"
        f"wb[0]: {_fmt_item(body['wb_items'][0]) if wb_n else 'EMPTY'}"
    )
    _print_result(label, status, detail)
    return wb_n > 0


# ─────────────────────────────────────────────────────────────
# TEST 4: Ozon live (Playwright)
# ─────────────────────────────────────────────────────────────

def test_ozon_live():
    _section("TEST 4 — POST /api/v1/compare  mode=live_public  marketplaces=[ozon]  (Playwright)")
    payload = {"query": "наушники bluetooth", "marketplaces": ["ozon"], "top_n": 5, "mode": "live_public"}
    print(f"  Payload: {json.dumps(payload)}")
    print()
    print("  Expected shape (live — Playwright succeeded):")
    print('  {"ok": true, "source_mode_used": "live_public",')
    print('   "ozon_items": [{"marketplace":"ozon","title":"...","current_price":1234,...}],')
    print('   "errors": []}')
    print()
    print("  Expected shape (fallback — Playwright failed or Ozon blocked):")
    print('  {"ok": true, "source_mode_used": "demo",')
    print('   "ozon_items": [...fixture data...],')
    print('   "errors": ["ozon: ... использован demo"]}')
    print()
    print(f"  {YELLOW}NOTE: Playwright запросы занимают 10-30 сек. Ожидаем...{RESET}")
    print()

    t0 = time.monotonic()
    code, body = _post("/api/v1/compare", payload, timeout=120)
    elapsed = time.monotonic() - t0

    if code != 200 or not body.get("ok"):
        _print_result(f"HTTP {code}  ({elapsed:.2f}s)", "FAIL")
        return False

    ozon_n = len(body.get("ozon_items", []))
    src    = body.get("source_mode_used")
    errs   = body.get("errors", [])

    if src == "live_public" and ozon_n > 0:
        status = "PASS"
        label = f"LIVE data confirmed  ozon_items={ozon_n}  ({elapsed:.2f}s)"
        verdict = "Ozon Playwright: VERIFIED on this VPS"
    elif ozon_n > 0:
        status = "FALLBACK"
        label = f"fallback to demo  ozon_items={ozon_n}  errors={errs}  ({elapsed:.2f}s)"
        verdict = "Ozon Playwright: NOT VERIFIED — requires further investigation"
    else:
        status = "FAIL"
        label = f"no items returned  src={src}  ({elapsed:.2f}s)"
        verdict = "Ozon Playwright: FAILED — check logs"

    items_preview = ""
    if ozon_n > 0:
        for i, item in enumerate(body["ozon_items"][:3]):
            items_preview += f"\nozon[{i}]: {_fmt_item(item)}"

    detail = (
        f"source_mode_used={src}  ozon_items={ozon_n}  errors={errs}\n"
        f"{BOLD}{verdict}{RESET}"
        + items_preview
    )
    _print_result(label, status, detail)
    return ozon_n > 0


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}Marketplace Compare Sheet — Smoke Test{RESET}")
    print(f"Target: {CYAN}{BASE_URL}{RESET}")
    print(f"Time:   {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results: dict[str, bool] = {}

    results["health"] = test_health()

    if not results["health"]:
        print(f"\n{RED}{BOLD}Health check failed — сервер не отвечает. Дальше бессмысленно.{RESET}\n")
        sys.exit(1)

    results["demo"]     = test_demo()
    results["wb_live"]  = test_wb_live()
    results["ozon_live"] = test_ozon_live()

    # Summary
    _section("ИТОГ")
    all_ok = True
    for name, passed in results.items():
        if passed:
            _print_result(name, "PASS")
        else:
            _print_result(name, "FAIL")
            if name != "ozon_live":  # ozon fallback не критичен
                all_ok = False

    ozon_live_passed = results.get("ozon_live", False)
    if not ozon_live_passed:
        print(f"\n  {YELLOW}Ozon live_public: implemented, requires runtime verification on VPS.{RESET}")
        print(f"  {YELLOW}Если fallback — проверь логи uvicorn и убедись что playwright install chromium выполнен.{RESET}")

    if all_ok:
        print(f"\n{GREEN}{BOLD}Backend готов к подключению Google Sheets.{RESET}\n")
    else:
        print(f"\n{RED}{BOLD}Есть критические ошибки — исправь перед подключением Google Sheets.{RESET}\n")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
