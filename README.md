<div align="center">

# fast_telegram_srm

Telegram‑бот для фиксации вступлений пользователей в канал / супергруппу и записи событий в Google Sheets.

</div>

---

## Раздел для клиента (быстрый старт)

Этот блок — для владельца канала/проекта. Здесь только то, что нужно, чтобы запустить бота и получить строки в таблице.

### Что делает бот
Записывает в Google Таблицу каждое вступление (и заявки на вступление, если включены запросы на одобрение): время, ID пользователя, имя, юзернейм, ссылку приглашения (если доступно) и её название.

### Что подготовить заранее
1. Telegram Bot Token — получить у @BotFather (команда /newbot).  
2. Google Spreadsheet (пустая таблица или существующая). Скопируйте её ID из URL: `https://docs.google.com/spreadsheets/d/<ID>/edit`.  
3. Service Account в Google Cloud (JSON ключ) — выдать доступ (Editor) к таблице на e‑mail service account'а.

### Файл .env (минимум)
Создайте файл `.env` в корне проекта:
```
BOT_TOKEN=123456:ABC-DEF...
GOOGLE_SPREADSHEET_ID=1AbcDefGhIjKlMNopQRstuVWxyz...
GOOGLE_SERVICE_ACCOUNT_JSON=./gcloud-key.json   # или сам JSON, или base64
```
Дополнительно (необязательно):
```
TIMEZONE=Europe/Moscow          # Часовой пояс для отметок времени
LOG_LEVEL=INFO                  # DEBUG для подробного логирования
LOG_JOINS_WITHOUT_INVITE=true   # Логировать вступления без пригласительной ссылки
GSHEETS_SELF_CHECK=true         # Проверка доступа к таблице при старте
SENTRY_DSN=                     # Если используете Sentry
```

### Варианты значения GOOGLE_SERVICE_ACCOUNT_JSON
1. Путь к файлу: `C:\secret\key.json`
2. Сырой JSON одной строкой: `{"type":"service_account", ...}`
3. Base64 строка от того же JSON.

### Установка и запуск (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

### Проверка работы
1. Добавьте бота администратором в канал / супергруппу (нужны права: приглашать пользователей, просматривать участников, одобрять заявки — если используете join requests).  
2. Создайте пригласительную ссылку в интерфейсе Telegram и (по возможности) создайте её от имени бота.  
3. Зайдите тестовым аккаунтом через эту ссылку.  
4. В таблице появится новая строка. Если нет — смотрите логи (см. ниже).  

### Где смотреть ошибки
Терминал, где запущен бот. Типичные сообщения:
- `BOT_TOKEN is not set` — проверьте `.env`
- `Skipping chat_member: no invite_link` — включите `LOG_JOINS_WITHOUT_INVITE=true` или заходите по ссылке-приглашению
- Ошибки Google Sheets — проверьте права доступа таблицы для service account.

### Частые вопросы
Q: Почему иногда нет ссылки приглашения?  
A: Telegram API не всегда возвращает объект `invite_link` (например, публичный вход через @username, общий папочный инвайт, ссылка создана не ботом). В таком случае можно видеть пометку `(no invite)` или `(folder invite)`.

---

## Раздел для разработчика

Этот блок описывает архитектуру, настройки и внутренние механизмы расширения.

### Архитектура
- Aiogram 3.x (`Dispatcher`, роутеры) — обработчики: `my_chat_member`, `chat_member`, `chat_join_request`.
- Сервисный контейнер (`services.container`) предоставляет доступ к:
  - `Database` (SQLite через `aiosqlite`) — сопоставление: ID канала → имя листа.
  - `GoogleSheetsService` — асинхронная запись строк с backoff.
- Конфигурация через `pydantic_settings` (`app/config.py`).
- Логирование стандартным `logging`, уровни управляются `LOG_LEVEL`.
- (Опционно) Sentry для ошибок.

### Поток данных
1. Пользователь вступает или создаёт join request.
2. Соответствующий апдейт (`ChatJoinRequest` или `ChatMemberUpdated`) попадает в обработчик.
3. Определяется лист в Google Sheets (кэшируется в локальной БД; создаётся при первой необходимости).
4. Формируется строка: `[Timestamp, User ID, Full Name, Username, Invite Link, Link Name]`.
5. Отправляется append через сервис Google Sheets (повтор при временных ошибках).

### Особенности invite link логики
- Поле `invite_link` в `ChatMemberUpdated` может отсутствовать.
- Для join request сначала логируется заявка, затем после одобрения — результат вступления.
- Временный кэш (`app/utils/join_cache.py`) связывает заявку и итоговое вступление, чтобы восстановить ссылку, если её нет во втором апдейте.
- Флаги: `via_join_request`, `via_chat_folder_invite_link` используются для классификации.

### Переменные окружения (.env)
| Переменная | Обязательно | Назначение |
|-----------|-------------|-----------|
| BOT_TOKEN | да | Токен Telegram бота |
| GOOGLE_SERVICE_ACCOUNT_JSON | да | Ключ сервисного аккаунта (путь / JSON / base64) |
| GOOGLE_SPREADSHEET_ID | да | ID таблицы для записи |
| DB_PATH | нет (default ./data/app.db) | Путь к локальной SQLite БД |
| LOG_LEVEL | нет | Уровень логирования (INFO/DEBUG/...) |
| SENTRY_DSN | нет | DSN для отправки ошибок в Sentry |
| TIMEZONE | нет | Часовой пояс для меток времени |
| LOG_JOINS_WITHOUT_INVITE | нет | Логировать вступления без ссылки (true/false) |
| GSHEETS_SELF_CHECK | нет | Проверять доступ к таблице при старте |

### Зависимости (основные)
- aiogram — Telegram Bot API
- aiosqlite — асинхронная SQLite
- gspread / gspread-asyncio / google-auth — доступ к Google Sheets
- backoff — повтор при временных ошибках сети/API
- pydantic-settings — управление конфигурацией
- sentry-sdk — отчёт об ошибках (опционально)

### Локальный запуск
```bash
python -m app.main
```
Следите за тем, чтобы команда запускалась из корня проекта (иначе сломаются относительные импорты и `.env`).

### Структура данных в Google Sheets
Первая строка листа: `Timestamp | User ID | Full Name | Username | Invite Link | Link Name`.
Каждое событие — отдельная строка. Несколько каналов → несколько листов (создаются автоматически). Название листа — нормализованный заголовок канала (sanitize + ensure unique).

### Локальная БД
SQLite таблица (см. `services/db.py`) хранит соответствие channel_id ↔ sheet_name. Это позволяет не искать лист по каждой операции.

### Обработка ошибок
- Все необработанные исключения в апдейтах фиксируются `errors_handler` и не ломают цикл поллинга.
- Ошибки Google Sheets логируются; при временных проблемах backoff повторит запрос.

### Как добавить новый столбец в таблицу
1. Изменить `HEADERS` в `services/google_sheets.py`.
2. Изменить формирование `row` в соответствующих хендлерах.
3. (Опционально) мигрировать уже созданные листы вручную или скриптом.

### Тестирование
`tests/` (добавьте/расширьте) — рекомендуется мокать `GoogleSheetsService` и использовать фабрики обновлений Aiogram.

### Завершение работы
Ctrl+C в терминале. Обработчик корректно завершит цикл.