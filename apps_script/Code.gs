/**
 * Marketplace Compare Sheet — Google Apps Script
 *
 * Тонкий слой между Google Sheets и backend на VPS.
 * Читает параметры из листа control, отправляет запрос, записывает результат.
 *
 * Как использовать:
 *   1. Открой Google Sheets
 *   2. Tools → Script editor → вставь этот код
 *   3. Сохрани, перезагрузи таблицу
 *   4. Появится меню "Compare"
 */


// ─────────────────────────────────────────────
// Меню
// ─────────────────────────────────────────────

/**
 * Создаёт кастомное меню при открытии таблицы.
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🛒 Compare')
    .addItem('▶ Запустить сравнение (WB + Ozon)', 'runComparison')
    .addSeparator()
    .addItem('Только WB', 'runWBOnly')
    .addItem('Только Ozon', 'runOzonOnly')
    .addSeparator()
    .addItem('🗑 Очистить результаты', 'clearResults')
    .addToUi();
}


// ─────────────────────────────────────────────
// Основные функции запуска
// ─────────────────────────────────────────────

/**
 * Запускает сравнение WB + Ozon.
 * Читает параметры из листа control.
 */
function runComparison() {
  _runWithMarketplaces(['wb', 'ozon']);
}

/**
 * Запускает сравнение только WB.
 */
function runWBOnly() {
  _runWithMarketplaces(['wb']);
}

/**
 * Запускает сравнение только Ozon.
 */
function runOzonOnly() {
  _runWithMarketplaces(['ozon']);
}

/**
 * Внутренняя функция запуска — вызывает backend и обновляет листы.
 * @param {string[]} marketplaces - список маркетплейсов
 */
function _runWithMarketplaces(marketplaces) {
  var control = getControlValues();

  if (!control.query) {
    SpreadsheetApp.getUi().alert('Заполни поле Query на листе control!');
    return;
  }

  if (!control.backendUrl) {
    SpreadsheetApp.getUi().alert('Заполни поле Backend URL на листе control!');
    return;
  }

  setStatus('⏳ Выполняется...');

  var payload = {
    query: control.query,
    marketplaces: marketplaces,
    top_n: control.topN,
    mode: control.mode
  };

  Logger.log('Запрос к backend: ' + JSON.stringify(payload));

  try {
    var response = _callBackend(control.backendUrl, payload);

    if (!response.ok) {
      setStatus('❌ Backend вернул ошибку');
      updateServiceSheet(control, response, 'ERROR: backend ok=false');
      return;
    }

    // Записываем данные в листы
    writeRawSheet('raw_wb', response.wb_items || []);
    writeRawSheet('raw_ozon', response.ozon_items || []);
    writeSummary(response.summary, response);
    updateServiceSheet(control, response, '');

    var winner = response.summary.price_winner || 'n/a';
    setStatus('✅ Готово · winner: ' + winner + ' · run_id: ' + response.run_id);

  } catch (e) {
    Logger.log('Ошибка: ' + e.toString());
    setStatus('❌ Ошибка: ' + e.message);
    _writeServiceError(e.message);
  }
}


// ─────────────────────────────────────────────
// HTTP запрос к backend
// ─────────────────────────────────────────────

/**
 * Отправляет POST запрос к backend.
 * @param {string} url - полный URL эндпоинта
 * @param {Object} payload - тело запроса
 * @returns {Object} распарсенный JSON ответ
 */
function _callBackend(url, payload) {
  var options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true  // обрабатываем HTTP ошибки сами
  };

  var response = UrlFetchApp.fetch(url, options);
  var code = response.getResponseCode();
  var body = response.getContentText();

  Logger.log('Backend ответ: HTTP ' + code);

  if (code !== 200) {
    throw new Error('HTTP ' + code + ': ' + body.substring(0, 200));
  }

  return JSON.parse(body);
}


// ─────────────────────────────────────────────
// Чтение листа control
// ─────────────────────────────────────────────

/**
 * Читает значения управляющих параметров с листа control.
 *
 * Ожидаемая структура листа:
 *   B3 - query
 *   B4 - marketplaces (игнорируем, берём из параметра функции)
 *   B5 - top_n
 *   B6 - mode
 *   B7 - backend_url
 *
 * @returns {Object} объект с параметрами
 */
function getControlValues() {
  var sheet = _getSheet('control');
  return {
    query:      sheet.getRange('B3').getValue().toString().trim(),
    topN:       parseInt(sheet.getRange('B5').getValue()) || 10,
    mode:       sheet.getRange('B6').getValue().toString().trim() || 'demo',
    backendUrl: sheet.getRange('B7').getValue().toString().trim()
  };
}


// ─────────────────────────────────────────────
// Запись в листы
// ─────────────────────────────────────────────

/**
 * Записывает массив товаров в указанный лист (raw_wb или raw_ozon).
 * Первая строка — заголовки, дальше данные.
 *
 * @param {string} sheetName - имя листа
 * @param {Object[]} rows - массив нормализованных товаров
 */
function writeRawSheet(sheetName, rows) {
  var sheet = _getSheet(sheetName);
  sheet.clearContents();

  if (!rows || rows.length === 0) {
    sheet.getRange('A1').setValue('Нет данных');
    return;
  }

  // Заголовки
  var headers = [
    'marketplace', 'title', 'current_price', 'old_price', 'discount_pct',
    'rating', 'reviews_count', 'seller_name', 'brand', 'category_guess',
    'url', 'source_mode_used', 'scraped_at'
  ];

  // Данные
  var data = rows.map(function(item) {
    return [
      item.marketplace || '',
      item.title || '',
      item.current_price || 0,
      item.old_price || '',
      item.discount_pct || '',
      item.rating || '',
      item.reviews_count || '',
      item.seller_name || '',
      item.brand || '',
      item.category_guess || '',
      item.url || '',
      item.source_mode_used || '',
      item.scraped_at || ''
    ];
  });

  // Записываем заголовки и данные одним вызовом
  var allRows = [headers].concat(data);
  sheet.getRange(1, 1, allRows.length, headers.length).setValues(allRows);

  // Форматируем заголовки жирным
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');

  Logger.log(sheetName + ': записано ' + rows.length + ' строк');
}

/**
 * Записывает summary-данные на лист summary.
 *
 * @param {Object} summary - объект SummaryResult
 * @param {Object} response - полный ответ от backend
 */
function writeSummary(summary, response) {
  var sheet = _getSheet('summary');
  sheet.clearContents();

  var now = new Date().toLocaleString('ru-RU');

  var rows = [
    ['Параметр', 'Значение'],
    ['Запрос', summary.query || ''],
    ['', ''],
    ['📦 WB', ''],
    ['Товаров найдено', summary.wb_count || 0],
    ['Мин. цена', summary.wb_min_price ? summary.wb_min_price + ' ₽' : '—'],
    ['Avg цена', summary.wb_avg_price ? summary.wb_avg_price + ' ₽' : '—'],
    ['Avg рейтинг', summary.wb_avg_rating || '—'],
    ['', ''],
    ['🛍 Ozon', ''],
    ['Товаров найдено', summary.ozon_count || 0],
    ['Мин. цена', summary.ozon_min_price ? summary.ozon_min_price + ' ₽' : '—'],
    ['Avg цена', summary.ozon_avg_price ? summary.ozon_avg_price + ' ₽' : '—'],
    ['Avg рейтинг', summary.ozon_avg_rating || '—'],
    ['', ''],
    ['🏆 Победитель по цене', (summary.price_winner || 'n/a').toUpperCase()],
    ['Спред цен', summary.price_spread ? summary.price_spread + ' ₽' : '—'],
    ['', ''],
    ['Режим источника', response.source_mode_used || ''],
    ['Запрошенный режим', response.requested_mode || ''],
    ['Run ID', response.run_id || ''],
    ['Обновлено', now]
  ];

  sheet.getRange(1, 1, rows.length, 2).setValues(rows);

  // Форматирование заголовков
  sheet.getRange('A1:B1').setFontWeight('bold');
  sheet.getRange('A4').setFontWeight('bold');
  sheet.getRange('A10').setFontWeight('bold');
  sheet.getRange('A16').setFontWeight('bold');

  // Выравниваем колонку A
  sheet.getRange('A1:A' + rows.length).setHorizontalAlignment('left');

  Logger.log('Лист summary обновлён');
}

/**
 * Обновляет служебный лист service.
 *
 * @param {Object} control - значения из control листа
 * @param {Object} response - ответ от backend
 * @param {string} errorMsg - сообщение об ошибке (пустое если всё ок)
 */
function updateServiceSheet(control, response, errorMsg) {
  var sheet = _getSheet('service');
  sheet.clearContents();

  var now = new Date().toLocaleString('ru-RU');
  var errors = (response.errors || []).join('; ') || errorMsg || '—';

  var rows = [
    ['Параметр', 'Значение'],
    ['backend_url', control.backendUrl || ''],
    ['last_status', errorMsg ? 'ERROR' : 'OK'],
    ['last_error', errors],
    ['last_run_id', response.run_id || '—'],
    ['updated_at', now],
    ['requested_mode', response.requested_mode || ''],
    ['source_mode_used', response.source_mode_used || '']
  ];

  sheet.getRange(1, 1, rows.length, 2).setValues(rows);
  sheet.getRange('A1:B1').setFontWeight('bold');
}


// ─────────────────────────────────────────────
// Статус и утилиты
// ─────────────────────────────────────────────

/**
 * Обновляет статус на листе control.
 * @param {string} message - текст статуса
 */
function setStatus(message) {
  var sheet = _getSheet('control');
  sheet.getRange('B9').setValue(message);
  sheet.getRange('B10').setValue(new Date().toLocaleString('ru-RU'));
  SpreadsheetApp.flush();  // Принудительно перерисовываем UI
  Logger.log('Status: ' + message);
}

/**
 * Очищает листы raw_wb, raw_ozon, summary и сбрасывает статус.
 */
function clearResults() {
  ['raw_wb', 'raw_ozon', 'summary'].forEach(function(name) {
    _getSheet(name).clearContents();
  });
  setStatus('READY');
  Logger.log('Результаты очищены');
}

/**
 * Пишет сообщение об ошибке на лист service без полного ответа.
 * @param {string} errorMsg
 */
function _writeServiceError(errorMsg) {
  var sheet = _getSheet('service');
  var control = getControlValues();
  var now = new Date().toLocaleString('ru-RU');

  var rows = [
    ['Параметр', 'Значение'],
    ['backend_url', control.backendUrl || ''],
    ['last_status', 'ERROR'],
    ['last_error', errorMsg],
    ['last_run_id', '—'],
    ['updated_at', now],
    ['requested_mode', control.mode || ''],
    ['source_mode_used', '—']
  ];

  sheet.clearContents();
  sheet.getRange(1, 1, rows.length, 2).setValues(rows);
  sheet.getRange('A1:B1').setFontWeight('bold');
}

/**
 * Возвращает лист по имени. Если не существует — создаёт.
 * @param {string} name - имя листа
 * @returns {GoogleAppsScript.Spreadsheet.Sheet}
 */
function _getSheet(name) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    Logger.log('Создан новый лист: ' + name);
  }
  return sheet;
}
