# Настройка Google Sheets

## 1. Создай новую таблицу

Открой https://sheets.google.com → создай новый документ.

---

## 2. Создай листы

Нужно создать 5 листов (вкладки внизу):
- `control`
- `raw_wb`
- `raw_ozon`
- `summary`
- `service`

---

## 3. Заполни лист control

Скопируй эту структуру в лист **control**:

| Ячейка | Значение | Описание |
|--------|----------|----------|
| A1 | `Marketplace Compare Sheet` | Заголовок |
| A3 | `Query` | Метка |
| B3 | `iphone 15 case` | **Твой поисковый запрос** |
| A4 | `Marketplaces` | Метка |
| B4 | `both` | Информационно (управляется через меню) |
| A5 | `Top N` | Метка |
| B5 | `10` | **Количество результатов** |
| A6 | `Mode` | Метка |
| B6 | `demo` | **demo** или **live_public** |
| A7 | `Backend URL` | Метка |
| B7 | `http://YOUR-VPS-IP:8000/api/v1/compare` | **URL твоего backend** |
| A9 | `Status` | Метка |
| B9 | `READY` | Статус (обновляется автоматически) |
| A10 | `Updated at` | Метка |
| B10 | `-` | Время последнего запроса |
| A11 | `Last run id` | Метка |
| B11 | `-` | ID последнего запуска |

---

## 4. Добавь Apps Script

1. В таблице: **Extensions → Apps Script**
2. Удали весь код в редакторе
3. Вставь содержимое файла `apps_script/Code.gs`
4. Нажми **Save** (Ctrl+S)
5. Закрой вкладку со Script editor
6. **Перезагрузи** Google Sheets

---

## 5. Разреши скрипту доступ

При первом запуске Apps Script попросит разрешения:
1. Нажми **Review permissions**
2. Выбери свой аккаунт
3. Нажми **Advanced** → **Go to Marketplace Compare Sheet (unsafe)**
4. Нажми **Allow**

Это нормально — скрипт твой, запускается в твоём аккаунте.

---

## 6. Проверь что работает

1. В таблице появится меню **🛒 Compare**
2. Убедись что в B7 стоит правильный URL backend
3. Нажми **🛒 Compare → ▶ Запустить сравнение (WB + Ozon)**
4. Через несколько секунд обновятся листы raw_wb, raw_ozon, summary

---

## Структура листов после запуска

### raw_wb / raw_ozon
Таблица с товарами:
- marketplace, title, current_price, old_price, discount_pct
- rating, reviews_count, seller_name, brand, category_guess
- url, source_mode_used, scraped_at

### summary
Компактные метрики:
- Количество товаров WB/Ozon
- Min и avg цены
- Avg рейтинги
- Победитель по цене
- Спред цен

### service
Служебная информация:
- backend_url, last_status, last_error
- last_run_id, updated_at, requested_mode, source_mode_used
