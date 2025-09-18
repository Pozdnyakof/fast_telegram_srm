# Развертывание на Ubuntu 24.04 (systemd)

Ниже инструкция для сервера, к которому есть доступ по SSH (IP + ключ). Предполагается чистая Ubuntu 24.04.

## 1) Подготовка сервера

Подключитесь к серверу по SSH с локальной машины:

```bash
ssh -i ~/.ssh/your_key ubuntu@YOUR_SERVER_IP
```

Обновите пакеты и установите зависимости:

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git python3 python3-venv python3-pip
```

(Опционально) Создайте отдельного пользователя для бота:
```bash
sudo adduser --system --group --home /opt/fast_telegram_srm bot
sudo usermod -aG bot $USER
```

## 2) Размещение кода

```bash
sudo mkdir -p /opt/fast_telegram_srm
sudo chown -R $USER:bot /opt/fast_telegram_srm
cd /opt/fast_telegram_srm

# Клонирование репозитория или копирование артефактов
# Вариант A: клонировать напрямую
sudo -u $USER git clone https://github.com/Pozdnyakof/fast_telegram_srm .

# Вариант B: загрузить архив релиза и распаковать (если используется GitHub Releases)
```

Создайте виртуальное окружение и установите зависимости:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3) Настройка конфигурации

Создайте файл окружения:
```bash
cp .env.example .env
nano .env
```
Заполните переменные:
- BOT_TOKEN — токен бота
- GOOGLE_SPREADSHEET_ID — ID таблицы
- GOOGLE_SERVICE_ACCOUNT_JSON — путь к JSON ключу или сам JSON (рекомендуем путь к файлу)

Разместите ключ сервисного аккаунта:
```bash
mkdir -p keys
nano keys/service_account.json
# Вставьте JSON ключ сюда, сохраните
```
Убедитесь, что путь в .env соответствует `./keys/service_account.json`.

Создайте каталоги для данных при необходимости:
```bash
mkdir -p data
```

Проверьте, что бот запускается вручную:
```bash
python -m app.main
# Остановить: Ctrl+C
```

## 4) Настройка systemd

Скопируйте unit-файл:
```bash
sudo cp deploy/systemd/fast-telegram-srm.service /etc/systemd/system/
```

Отредактируйте при необходимости пользователя/группу в юните (по умолчанию `bot:bot`) и директорию WorkingDirectory, если путь отличается.

Перезагрузите демона и запустите сервис:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fast-telegram-srm
sudo systemctl start fast-telegram-srm
```

Проверка статуса и логов:
```bash
systemctl status fast-telegram-srm
journalctl -u fast-telegram-srm -f
```

## 5) Обновления релизов

Для обновления кода:
```bash
cd /opt/fast_telegram_srm
sudo -u $USER git pull --rebase
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart fast-telegram-srm
```

## 6) Частые проблемы

- Нет доступа к Google Sheets: убедитесь, что e-mail сервисного аккаунта добавлен в доступы (Editor) к таблице.
- `BOT_TOKEN is not set`: проверьте `.env` и права файла (`EnvironmentFile` в unit-файле).
- Путь `GOOGLE_SERVICE_ACCOUNT_JSON`: если это путь, он должен быть доступен процессу сервиса (рекомендуется относительный `./keys/service_account.json` из каталога `/opt/fast_telegram_srm`).
- Прав доступа: убедитесь, что пользователь, от которого запускается сервис, владеет файлами/каталогами или имеет нужные права.
