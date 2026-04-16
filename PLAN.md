# Marketplace Compare Sheet — План реализации

## Суть проекта

Система мониторинга товаров через Google Sheets:
- Google Sheets = интерфейс пользователя (лист control)
- Google Apps Script = тонкий слой запуска (HTTP → VPS)
- Python backend на VPS = worker, нормализация, сравнение, логика

---

## Шаги реализации

### Шаг 1 — Структура репозитория ✅
Создать все директории и пустые файлы согласно архитектуре.

### Шаг 2 — Backend: конфигурация и точка входа
- `app/settings.py` — ENV-переменные через pydantic-settings
- `app/logger.py` — настройка logging
- `app/main.py` — FastAPI приложение, подключение роутеров

### Шаг 3 — Schemas
- `app/schemas/compare.py` — Pydantic модели:
  - `CompareRequest`
  - `NormalizedItem`
  - `SummaryResult`
  - `CompareResponse`

### Шаг 4 — Mock data (fixtures)
- `app/mock_data/wb_demo.json` — реалистичные данные WB
- `app/mock_data/ozon_demo.json` — реалистичные данные Ozon

### Шаг 5 — Providers
- `app/providers/base.py` — абстрактный базовый провайдер
- `app/providers/fixtures.py` — демо-провайдер, читает fixture JSON
- `app/providers/wb_public.py` — стаб для live WB (graceful fallback)
- `app/providers/ozon_public.py` — стаб для live Ozon (graceful fallback)

### Шаг 6 — Services
- `app/services/normalize.py` — нормализация сырых данных → NormalizedItem
- `app/services/summary.py` — подсчёт метрик: min/avg цена, рейтинг, winner
- `app/services/compare_service.py` — оркестрация: вызов провайдеров, нормализация, summary

### Шаг 7 — API routes
- `app/api/routes_compare.py` — POST /api/v1/compare, GET /health

### Шаг 8 — Apps Script
- `apps_script/Code.gs` — весь JS для Google Sheets:
  - onOpen(), custom menu
  - runComparison(), runWBOnly(), runOzonOnly()
  - clearResults()
  - writeRawSheet(), writeSummary(), setStatus()
  - getControlValues()

### Шаг 9 — Документация
- `docs/ARCHITECTURE.md` — архитектура системы
- `docs/SHEET_SETUP.md` — как настроить Google Sheets
- `docs/DEMO.md` — как запустить demo end-to-end

### Шаг 10 — Конфиг и README
- `.env.example`
- `requirements.txt`
- `README.md` — быстрый старт, команды запуска

### Шаг 11 — Tests
- `tests/test_compare_service.py` — unit тесты на demo mode
- `tests/test_health.py` — smoke test /health endpoint

---

## Режимы работы

| mode | поведение |
|------|-----------|
| `demo` | backend читает fixtures, всё работает стабильно |
| `live_public` | backend пытается запросить реальные данные, при ошибке → fallback в demo |

Ответ всегда содержит `source_mode_used` — что реально было использовано.

---

## Технический стек

- Python 3.11+
- FastAPI + Uvicorn
- Pydantic v2
- httpx (для live провайдеров)
- python-dotenv / pydantic-settings
- Google Apps Script (JavaScript)

---

## Деплой на VPS

```bash
git clone https://github.com/<user>/marketplace-compare-sheet.git
cd marketplace-compare-sheet
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Или через systemd / supervisor (описано в ARCHITECTURE.md).

---

## Чеклист финальной проверки

- [ ] `GET /health` возвращает 200
- [ ] `POST /api/v1/compare` demo mode возвращает корректный JSON
- [ ] Apps Script читает control лист и отправляет запрос
- [ ] Листы raw_wb, raw_ozon, summary, service обновляются
- [ ] clearResults() очищает все листы
- [ ] live_public mode не падает, если источник недоступен
