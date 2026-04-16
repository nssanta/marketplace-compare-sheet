# Demo — запуск и проверка end-to-end

## Быстрый старт локально

```bash
# Клонируем и входим
git clone https://github.com/<user>/marketplace-compare-sheet.git
cd marketplace-compare-sheet

# Виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate    # Windows

# Зависимости
pip install -r requirements.txt

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

### 2. Demo сравнение (WB + Ozon)
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
  "summary": {
    "query": "iphone 15 case",
    "wb_count": 5,
    "ozon_count": 5,
    "price_winner": "wb|ozon|tie",
    ...
  },
  "wb_items": [...],
  "ozon_items": [...],
  "errors": []
}
```

### 3. Live mode (с fallback)
```bash
curl -X POST http://localhost:8000/api/v1/compare \
  -H "Content-Type: application/json" \
  -d '{
    "query": "наушники bluetooth",
    "marketplaces": ["wb"],
    "top_n": 3,
    "mode": "live_public"
  }'
```

Если WB публичный поиск сработал — `source_mode_used: "live_public"`.
Если нет — `source_mode_used: "demo"`, в `errors[]` будет причина.

---

## Swagger UI

Открой в браузере: http://localhost:8000/docs

Там можно интерактивно протестировать все эндпоинты.

---

## Деплой на VPS (Ubuntu/Debian)

### 1. Ставим Python и git
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip git
```

### 2. Клонируем и настраиваем
```bash
cd /opt
sudo git clone https://github.com/<user>/marketplace-compare-sheet.git
cd marketplace-compare-sheet
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Редактируем .env при необходимости
nano .env
```

### 3. Тестовый запуск
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Проверяем: `curl http://YOUR-VPS-IP:8000/health`

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

[Install]
WantedBy=multi-user.target
```

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

### 5. Nginx reverse proxy (опционально)

Если хочешь HTTPS и красивый URL:
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
    }
}
```

---

## Чеклист финальной проверки

- [ ] `GET /health` возвращает `{"status": "ok"}`
- [ ] `POST /api/v1/compare` demo mode возвращает `wb_items` и `ozon_items`
- [ ] `summary.price_winner` корректно определяет победителя
- [ ] Apps Script в Google Sheets видит меню "🛒 Compare"
- [ ] После нажатия "Запустить" обновляются листы raw_wb, raw_ozon, summary, service
- [ ] `clearResults()` очищает все листы
- [ ] live_public mode не падает если источник недоступен (возвращает demo + errors)
- [ ] Логи читаемые и информативные
