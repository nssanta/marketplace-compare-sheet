# Marketplace Compare Sheet

Система мониторинга товаров через Google Sheets.

**Google Sheets** → интерфейс пользователя  
**Apps Script** → слой запуска (HTTP к VPS)  
**Python backend на VPS** → сбор данных, нормализация, сравнение

---

## Быстрый старт

```bash
git clone https://github.com/<user>/marketplace-compare-sheet.git
cd marketplace-compare-sheet

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --reload
```

Сервер: http://localhost:8000  
Swagger UI: http://localhost:8000/docs

---

## Проверка

```bash
# Health check
curl http://localhost:8000/health

# Demo сравнение
curl -X POST http://localhost:8000/api/v1/compare \
  -H "Content-Type: application/json" \
  -d '{"query": "iphone 15 case", "marketplaces": ["wb","ozon"], "top_n": 5, "mode": "demo"}'
```

---

## Структура проекта

```
marketplace-compare-sheet/
├── app/
│   ├── main.py                  # FastAPI приложение
│   ├── settings.py              # ENV-конфигурация
│   ├── logger.py                # Настройка логов
│   ├── schemas/
│   │   └── compare.py           # Pydantic схемы
│   ├── api/
│   │   └── routes_compare.py    # Роутеры /health и /api/v1/compare
│   ├── providers/
│   │   ├── base.py              # Абстрактный провайдер
│   │   ├── fixtures.py          # Demo-провайдер (JSON)
│   │   ├── wb_public.py         # Live WB провайдер
│   │   └── ozon_public.py       # Live Ozon провайдер (stub)
│   ├── services/
│   │   ├── compare_service.py   # Оркестрация запросов
│   │   ├── normalize.py         # Нормализация данных
│   │   └── summary.py           # Подсчёт метрик
│   └── mock_data/
│       ├── wb_demo.json         # Демо-данные WB
│       └── ozon_demo.json       # Демо-данные Ozon
├── apps_script/
│   └── Code.gs                  # Google Apps Script
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SHEET_SETUP.md
│   └── DEMO.md
├── tests/
├── .env.example
├── requirements.txt
├── PLAN.md                      # План разработки
└── README.md
```

---

## Режимы работы

| Mode | Поведение |
|------|-----------|
| `demo` | Читает fixture JSON, работает всегда |
| `live_public` | Пробует реальные данные, при неудаче → demo + errors[] |

---

## Листы Google Sheets

| Лист | Назначение |
|------|-----------|
| `control` | Ввод параметров, статус, кнопка через меню |
| `raw_wb` | Результаты Wildberries |
| `raw_ozon` | Результаты Ozon |
| `summary` | Метрики и сравнение |
| `service` | Служебная информация |

**Настройка таблицы** → [docs/SHEET_SETUP.md](docs/SHEET_SETUP.md)

---

## Деплой на VPS

Подробная инструкция → [docs/DEMO.md](docs/DEMO.md)

Краткая версия:
```bash
# На VPS (Ubuntu)
git clone <repo> && cd marketplace-compare-sheet
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- Pydantic v2
- httpx
- Google Apps Script (JS)

---

## Архитектура

Подробно → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
