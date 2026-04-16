# Demo — запуск и проверка end-to-end

## Быстрый старт локально

```bash
# Клонируем и входим
git clone https://github.com/<user>/marketplace-compare-sheet.git
cd marketplace-compare-sheet

# Виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate    # Windows

# Зависимости + Playwright (официальный путь, всё одной командой)
pip install -r requirements.txt && playwright install --with-deps chromium

# Конфиг
cp .env.example .env

# Запуск
uvicorn app.main:app --reload
```

Сервер стартует на http://localhost:8000

---

## Проверка API руками

### 1. Health check
```bash
curl http://localhost:8000/health
```
Ожидаем:
```json
{"status": "ok", "version": "1.0.0", "env": "development"}
```

### 2. Demo сравнение (WB + Ozon, без браузера)
```bash
curl -X POST http://localhost:8000/api/v1/compare \
  -H "Content-Type: application/json" \
  -d '{
    "query": "iphone 15 case",
    "marketplaces": ["wb", "ozon"],
    "top_n": 5,
    "mode": "demo"
  }'
```
Ожидаем:
```json
{
  "ok": true,
  "run_id": "a1b2c3d4",
  "requested_mode": "demo",
  "source_mode_used": "demo",
  "summary": { "wb_count": 5, "ozon_count": 5, "price_winner": "wb|ozon|tie" },
  "wb_items": [...],
  "ozon_items": [...],
  "errors": []
}
```

### 3. Live mode — только WB (быстро, без Playwright)
```bash
curl -X POST http://localhost:8000/api/v1/compare \
  -H "Content-Type: application/json" \
  -d '{
    "query": "наушники bluetooth",
    "marketplaces": ["wb"],
    "top_n": 5,
    "mode": "live_public"
  }'
```
Если WB ответил → `source_mode_used: "live_public"`.  
Если нет → `source_mode_used: "demo"`, в `errors[]` причина.

### 4. Live mode — Ozon (Playwright, ~10-15 сек)
```bash
curl -X POST http://localhost:8000/api/v1/compare \
  -H "Content-Type: application/json" \
  -d '{
    "query": "наушники bluetooth",
    "marketplaces": ["ozon"],
    "top_n": 5,
    "mode": "live_public"
  }'
```
Запускает headless Chromium, парсит выдачу, enrichment через consumer API.  
Если Playwright не установлен или Ozon заблокировал → `source_mode_used: "demo"`.

### 5. Live mode — WB + Ozon вместе
```bash
curl -X POST http://localhost:8000/api/v1/compare \
  -H "Content-Type: application/json" \
  -d '{
    "query": "кофемашина",
    "marketplaces": ["wb", "ozon"],
    "top_n": 10,
    "mode": "live_public"
  }'
```

---

## Swagger UI

Открой в браузере: http://localhost:8000/docs

---

## Деплой на VPS (Ubuntu/Debian)

### 1. Ставим Python и git

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip git
```

### 2. Клонируем и настраиваем

```bash
cd /opt
sudo git clone https://github.com/<user>/marketplace-compare-sheet.git
sudo chown -R $USER:$USER /opt/marketplace-compare-sheet
cd marketplace-compare-sheet

python3.12 -m venv venv
source venv/bin/activate

# Одна команда: зависимости + Chromium + системные пакеты
pip install -r requirements.txt && playwright install --with-deps chromium

cp .env.example .env
nano .env  # при необходимости правим
```

### 3. Тестовый запуск

```bash
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Smoke-test (в другом терминале):
```bash
# Запускает все 4 теста: health + demo + wb live + ozon live
python scripts/smoke_test.py http://localhost:8000

# Или если сервер на другом хосте/порту
python scripts/smoke_test.py http://YOUR-VPS-IP:8000
```

Ожидаемый вывод при полностью рабочем стеке:
```
[PASS] health
[PASS] demo
[PASS] wb_live        ← если WB search.wb.ru доступен
[PASS] ozon_live      ← если Playwright + Ozon не заблокировал

# Если Ozon live не прошёл — это честный результат:
[FALLBACK] ozon_live  ← fallback to demo, errors[] непустой
  Ozon Playwright: NOT VERIFIED — requires further investigation
```

### 4. Systemd сервис (для продакшена)

Создаём файл сервиса:
```bash
sudo nano /etc/systemd/system/marketplace-compare.service
```

Содержимое:
```ini
[Unit]
Description=Marketplace Compare Sheet Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/marketplace-compare-sheet
ExecStart=/opt/marketplace-compare-sheet/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
Environment=APP_ENV=production
# Playwright ищет браузер относительно HOME пользователя
Environment=HOME=/var/www

[Install]
WantedBy=multi-user.target
```

> **Важно про Playwright и systemd:** Playwright хранит браузер в `~/.cache/ms-playwright`.  
> Если сервис запускается от `www-data`, нужно установить браузер от того же пользователя:
> ```bash
> sudo -u www-data HOME=/var/www playwright install chromium
> ```

Запускаем:
```bash
sudo systemctl daemon-reload
sudo systemctl enable marketplace-compare
sudo systemctl start marketplace-compare
sudo systemctl status marketplace-compare
```

Логи:
```bash
sudo journalctl -u marketplace-compare -f
```

### 5. Nginx reverse proxy (опционально, для HTTPS)

```bash
sudo apt install nginx certbot python3-certbot-nginx
```

Конфиг `/etc/nginx/sites-available/marketplace-compare`:
```nginx
server {
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # Playwright запускает headless браузер — может занять до 30+ сек
        # 360s даёт запас даже при медленном Ozon или нагруженном VPS
        proxy_read_timeout 360s;
        proxy_send_timeout 360s;
        proxy_connect_timeout 10s;
    }
}
```

Активируем:
```bash
sudo ln -s /etc/nginx/sites-available/marketplace-compare /etc/nginx/sites-enabled/
sudo certbot --nginx -d your-domain.com
sudo nginx -t && sudo systemctl reload nginx
```

---

## Troubleshooting Playwright

### Playwright не установлен
```
ERROR: Playwright не установлен. Запусти: pip install playwright && playwright install chromium
```
Решение:
```bash
source venv/bin/activate
pip install playwright
playwright install chromium
playwright install-deps
```

### Chromium не запускается на VPS
```
Error: Failed to launch chromium because executable doesn't exist
```
Решение:
```bash
# Убедись что браузер установлен для текущего пользователя
playwright install chromium
# Проверь наличие
ls ~/.cache/ms-playwright/
```

### Timeout при загрузке страницы Ozon
Ozon мог заблокировать или медленно отвечает.  
В ответе будет: `source_mode_used: "demo"`, `errors: ["ozon: ... использован demo"]`.  
Это ожидаемое поведение — fallback в demo работает корректно.

> **Статус Ozon live_public:** `implemented, requires runtime verification on VPS`  
> Архитектура fallback рабочая. Успех Playwright-парсинга зависит от того,
> блокирует ли Ozon headless запросы в конкретный момент с конкретного IP.
> Проверь через `python scripts/smoke_test.py` — результат скажет правду.

### Playwright под root (некоторые VPS)
Если сервер запускается от root, добавь в `.env`:
```
PLAYWRIGHT_EXTRA_ARGS=--no-sandbox
```
(флаги `--no-sandbox` уже включены в провайдере по умолчанию)

---

## Чеклист финальной проверки

- [ ] `GET /health` возвращает `{"status": "ok"}`
- [ ] `POST /compare` demo mode возвращает `wb_items` и `ozon_items`
- [ ] `summary.price_winner` корректно определяет победителя
- [ ] `POST /compare` live_public WB возвращает реальные данные
- [ ] `POST /compare` live_public Ozon возвращает реальные данные (Playwright)
- [ ] При недоступности источника: `source_mode_used: "demo"`, `errors[]` непустой
- [ ] Apps Script в Google Sheets видит меню "🛒 Compare"
- [ ] После нажатия "Запустить" обновляются листы raw_wb, raw_ozon, summary, service
- [ ] `clearResults()` очищает все листы
- [ ] Логи в journalctl читаемые и информативные
- [ ] Nginx timeout ≥ 60s (для Playwright запросов)
