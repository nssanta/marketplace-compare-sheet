# Архитектура Marketplace Compare Sheet

## Обзор

```
┌─────────────────────────────────────────────────────────────────┐
│                        Google Sheets                             │
│                                                                  │
│  Лист control  →  Apps Script  →  POST /api/v1/compare          │
│                                            │                     │
│  ← writeSummary()                          │                     │
│  ← writeRawSheet(raw_wb)                   │                     │
│  ← writeRawSheet(raw_ozon)                 │                     │
└─────────────────────────────────────────────────────────────────┘
                                             │
                                HTTPS (UrlFetchApp)
                                             │
┌────────────────────────────────────────────▼────────────────────┐
│                      VPS — Python Backend                        │
│                                                                  │
│  FastAPI                                                         │
│    └─ POST /api/v1/compare                                       │
│         └─ CompareService                                        │
│              ├─ WB Provider (demo / live HTTP)                   │
│              ├─ Ozon Provider (demo / live Playwright)           │
│              │    └─ Consumer API enrichment (best-effort)       │
│              ├─ Normalize                                        │
│              └─ Summary                                          │
└──────────────────────────────────────────────────────────────────┘
```

## Компоненты

### Google Sheets (UI)
- Лист **control** — ввод параметров, статус, кнопка через меню
- Лист **raw_wb** — сырые результаты Wildberries
- Лист **raw_ozon** — сырые результаты Ozon
- Лист **summary** — агрегированные метрики и winner
- Лист **service** — служебная информация (run_id, ошибки, режим)

### Apps Script (слой запуска)
- Файл `Code.gs` содержит весь JS-код
- Читает параметры из листа control
- Делает HTTP POST на VPS через `UrlFetchApp`
- Записывает ответ в листы
- Не содержит никакой бизнес-логики

### Python Backend (VPS)

#### FastAPI
- `main.py` — приложение, CORS middleware, lifespan хуки
- `settings.py` — конфигурация через .env (pydantic-settings)
- `api/routes_compare.py` — эндпоинты `/health` и `/api/v1/compare`

#### Providers (адаптеры источников данных)

| Файл | Маркетплейс | Режим | Описание |
|------|-------------|-------|----------|
| `fixtures.py` | WB + Ozon | demo | Читает JSON фикстуры, всегда работает |
| `wb_public.py` | WB | live_public | Публичный поиск WB (без авторизации) |
| `ozon_public_playwright.py` | Ozon | live_public | Headless Chromium через Playwright |
| `ozon_public.py` | Ozon | — | Legacy stub (не используется в live) |

#### Enrichment layer
- `ozon_public_consumer_api.py` — необязательный шаг после Playwright-поиска
- Запрашивает `/api/composer-api.bx/page/json/v2?url=<product_path>`
- Заполняет `seller_name`, `brand`, `category_guess` из widgetStates
- Обогащает максимум 5 карточек за запрос (экономия времени)
- При любой ошибке возвращает items как есть — не ломает flow

#### Services
- `compare_service.py` — оркестрация: выбор провайдера, enrichment, fallback
- `normalize.py` — приведение к единому формату `NormalizedItem`
- `summary.py` — подсчёт метрик (min/avg цена, рейтинг, winner)
- `ozon_categories.py` — helper для дерева категорий Ozon

## Поток данных

```
1. Пользователь → лист control: query="наушники bluetooth", mode="live_public"
2. Apps Script → POST /api/v1/compare
   {query, marketplaces: ["wb","ozon"], top_n: 10, mode: "live_public"}

3. CompareService — WB:
   mode=live_public → WBPublicProvider.search() → HTTP GET search.wb.ru
   если [] → fallback → WBFixtureProvider → errors[]

4. CompareService — Ozon:
   mode=live_public → OzonPublicPlaywrightProvider.search()
     → headless Chromium → ozon.ru/search/?text=...
     → стратегии: script-tags JSON → window state → DOM heuristics
   если [] → fallback → OzonFixtureProvider → errors[]
   если успех → enrich_with_consumer_api() [best-effort, max 5 карточек]

5. normalize_batch() → list[NormalizedItem] для WB и Ozon

6. build_summary() → SummaryResult (min/avg/winner)

7. CompareResponse → Apps Script

8. Apps Script → записывает в raw_wb, raw_ozon, summary, service
```

## Режимы работы

| Режим | WB | Ozon |
|-------|----|------|
| `demo` | Fixture JSON | Fixture JSON |
| `live_public` | HTTP search.wb.ru | Playwright + Consumer API |

`source_mode_used` в ответе показывает что реально использовалось:
- `live_public` — данные получены с маркетплейса
- `demo` — использованы фикстуры (провайдер упал или вернул [])

Каждый маркетплейс может иметь свой `source_mode_used` в items.  
Итоговый `source_mode_used` в CompareResponse = `demo` если хоть один провайдер упал в fallback.

## Playwright на VPS

Playwright запускает headless Chromium в процессе Python. На VPS нужны:

```bash
# Установка браузера и системных зависимостей
playwright install chromium
playwright install-deps

# Chromium запускается с флагами:
#   --no-sandbox (для root/container окружения)
#   --disable-setuid-sandbox
#   --disable-dev-shm-usage (ограниченная /dev/shm на VPS)
```

Ресурсы: ~200-400MB RAM на один запрос (браузер запускается и закрывается).  
Время ответа: 5-15 секунд (зависит от скорости Ozon).

## Деплой на VPS

```bash
# 1. Клонируем
git clone https://github.com/<user>/marketplace-compare-sheet.git
cd marketplace-compare-sheet

# 2. Конфигурируем
cp .env.example .env

# 3. Ставим зависимости
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Устанавливаем Playwright браузер
playwright install chromium
playwright install-deps

# 5. Запускаем
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 6. Или через systemd (рекомендуется для продакшена)
# см. docs/DEMO.md
```

## Масштабирование (будущее)

- Кэш Redis для повторяющихся запросов (TTL 10-30 мин)
- Очередь задач (Celery/RQ) для async парсинга с timeout
- История запросов в PostgreSQL
- Расширить WB provider через официальный Affiliate API
