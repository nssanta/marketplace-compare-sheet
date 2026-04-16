# Архитектура Marketplace Compare Sheet

## Обзор

```
┌─────────────────────────────────────────────────────┐
│                    Google Sheets                     │
│                                                      │
│  Лист control  →  Apps Script  →  POST /api/v1/compare │
│                                          │           │
│  ← writeSummary()                        │           │
│  ← writeRawSheet(raw_wb)                 │           │
│  ← writeRawSheet(raw_ozon)               │           │
└─────────────────────────────────────────────────────┘
                                           │
                              HTTPS (UrlFetchApp)
                                           │
┌─────────────────────────────────────────▼───────────┐
│                    VPS — Python Backend              │
│                                                      │
│  FastAPI                                             │
│    └─ POST /api/v1/compare                           │
│         └─ CompareService                            │
│              ├─ WB Provider (demo/live)              │
│              ├─ Ozon Provider (demo/live)            │
│              ├─ Normalize                            │
│              └─ Summary                              │
└──────────────────────────────────────────────────────┘
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
- **FastAPI** — HTTP фреймворк
- **settings.py** — конфигурация через .env
- **providers/** — адаптеры для источников данных
  - `fixtures.py` — демо-данные из JSON (всегда работает)
  - `wb_public.py` — публичный поиск WB (без авторизации)
  - `ozon_public.py` — Ozon API (требует ключ)
- **services/**
  - `compare_service.py` — оркестрация: выбор провайдера, fallback
  - `normalize.py` — приведение к единому формату NormalizedItem
  - `summary.py` — подсчёт метрик

## Поток данных

```
1. Пользователь → лист control: query="iphone 15 case", mode="demo"
2. Apps Script → POST /api/v1/compare
   {query, marketplaces, top_n, mode}
3. CompareService:
   - mode=demo → FixtureProvider → читает JSON файл
   - mode=live_public → LiveProvider → HTTP → если [] → fallback → FixtureProvider
4. NormalizeService → list[NormalizedItem]
5. SummaryService → SummaryResult (min/avg/winner)
6. CompareResponse → Apps Script
7. Apps Script → записывает в raw_wb, raw_ozon, summary, service
```

## Режимы работы

| Режим | Поведение |
|-------|-----------|
| `demo` | Читает fixture JSON, всегда работает |
| `live_public` | Пробует реальные данные, при неудаче → demo + ошибка в `errors[]` |

Ответ всегда содержит `source_mode_used` — что реально использовалось.

## Деплой на VPS

```bash
# 1. Клонируем
git clone https://github.com/<user>/marketplace-compare-sheet.git
cd marketplace-compare-sheet

# 2. Конфигурируем
cp .env.example .env
# редактируем .env если нужно

# 3. Ставим зависимости
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Запускаем
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5. Или через systemd (рекомендуется для продакшена)
# см. пример в docs/DEMO.md
```

## Масштабирование (будущее)

- Добавить кэш Redis для повторяющихся запросов
- Добавить очередь задач (Celery/RQ) для async парсинга
- Добавить базу данных для истории запросов
- Расширить Ozon provider через Ozon Seller API
