# discord-voice-banner

`discord-voice-banner` - Discord-бот для отслеживания активности в голосовых каналах и генерации динамического баннера сервера.

Бот считает реальных пользователей в голосе, не учитывает Discord-ботов, сохраняет статистику в SQLite и рисует PNG-баннер с текущей активностью, самым активным участником и топом голосовых каналов.

## Возможности

- отслеживает все voice и stage-каналы одного сервера;
- считает количество пользователей, которые прямо сейчас находятся в голосе;
- считает количество активных голосовых каналов;
- сохраняет завершенные и активные голосовые сессии в SQLite;
- восстанавливает активные сессии после перезапуска;
- определяет самого активного пользователя за `day`, `week`, `month` или `all`;
- генерирует баннер с названием `discord-voice-banner`, аватаром, ником и временем топ-пользователя;
- корректно переживает отсутствие аватарки, недоступный Discord CDN, длинные ники и Unicode;
- обновляет баннер с cooldown, чтобы не создавать лишнюю нагрузку на Discord API;
- пишет понятные логи и корректно закрывает базу при остановке.

## Структура проекта

```text
.
├── src/
│   └── discord_voice_banner/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── voice_tracker.py
│       ├── banner.py
│       ├── tasks.py
│       ├── logging_setup.py
│       └── utils.py
├── tests/
│   └── smoke_test.py
├── assets/
├── data/
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
└── README.md
```

## Требования

- Python 3.11 или новее;
- токен Discord-бота;
- бот должен быть приглашен на нужный сервер;
- в Discord Developer Portal должны быть включены intents:
  - Server Members Intent;
  - Voice States Intent;
- право `Manage Server` нужно только для режима `APPLY_GUILD_BANNER=true`;
- сервер Discord должен поддерживать баннер, если нужно автообновление серверного баннера.

## Установка

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
```

Заполни `.env`:

```env
DISCORD_TOKEN=your-discord-bot-token
GUILD_ID=123456789012345678
APPLY_GUILD_BANNER=false
BANNER_PERIOD=all
```

Настоящий `.env` нельзя коммитить. Он уже добавлен в `.gitignore`.

## Запуск

```bash
source .venv/bin/activate
python run.py
```

Или после `pip install -e .`:

```bash
discord-voice-banner
```

Проверка конфигурации и базы без подключения к Discord:

```bash
python run.py --check
```

Генерация тестового баннера без подключения к Discord:

```bash
python run.py --render-sample
```

Smoke-тест:

```bash
python tests/smoke_test.py
```

## Переменные окружения

| Переменная | Обязательна | Значение по умолчанию | Назначение |
| --- | --- | --- | --- |
| `DISCORD_TOKEN` | да | пусто | Токен Discord-бота. |
| `GUILD_ID` | да | `0` | ID сервера Discord. |
| `APPLY_GUILD_BANNER` | нет | `false` | Если `true`, бот обновляет серверный баннер через Discord API. |
| `BANNER_PERIOD` | нет | `all` | Период статистики: `day`, `week`, `month`, `all`. |
| `UPDATE_INTERVAL_SECONDS` | нет | `300` | Интервал фонового обновления баннера. Минимум `30`. |
| `BANNER_UPDATE_COOLDOWN_SECONDS` | нет | `20` | Задержка после voice-событий. Минимум `2`. |
| `DATABASE_PATH` | нет | `data/voice_banner.sqlite3` | Путь к SQLite-базе. |
| `BANNER_OUTPUT_PATH` | нет | `data/current-banner.png` | Путь к PNG-баннеру. |
| `LOG_LEVEL` | нет | `INFO` | Уровень логирования. |
| `LOG_FILE` | нет | `logs/bot.log` | Файл логов. Пустое значение отключает запись в файл. |

## Диагностика

- `Missing required environment variable(s): DISCORD_TOKEN, GUILD_ID` - создай `.env` из `.env.example` и заполни значения.
- `Discord rejected the token` - токен неверный или был пересоздан.
- `PrivilegedIntentsRequired` - включи нужные intents в Discord Developer Portal.
- `Configured guild ... is not visible` - бот не приглашен на сервер или указан неправильный `GUILD_ID`.
- `Discord Forbidden while updating guild banner` - нет права `Manage Server` или сервер не поддерживает баннеры.
- `database locked` - запущено несколько копий бота с одной SQLite-базой.

Логи пишутся в консоль и по умолчанию в `logs/bot.log`.
