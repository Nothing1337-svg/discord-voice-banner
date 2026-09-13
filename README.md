# discord-voice-banner

`discord-voice-banner` - Discord-бот для отслеживания активности в голосовых каналах и генерации динамического баннера сервера.

Бот считает реальных пользователей в голосе, не учитывает Discord-ботов, сохраняет статистику в SQLite и рисует PNG/JPG-баннер с текущей активностью, самым активным участником, аватаром, временем в голосе, топом каналов и временем последнего обновления.

## Возможности

- отслеживает все voice и stage-каналы одного сервера;
- считает количество пользователей, которые прямо сейчас находятся в голосе;
- считает количество активных голосовых каналов;
- сохраняет завершенные и активные голосовые сессии в SQLite;
- восстанавливает активные сессии после перезапуска;
- определяет самого активного пользователя за `day`, `week`, `month` или `all`;
- генерирует аккуратный баннер 1280×640;
- поддерживает пользовательский фон `PNG`, `JPG`, `JPEG`;
- корректно обрезает фон по cover/crop без кривого растягивания;
- добавляет затемнение поверх фона, чтобы текст читался;
- поддерживает русский и английский язык;
- поддерживает кириллицу, Unicode, длинные ники и fallback-аватар;
- обновляет баннер с cooldown, чтобы не создавать лишнюю нагрузку на Discord API;
- пишет понятные логи и корректно закрывает базу при остановке.

## Структура проекта

```text
.
├── src/
│   └── discord_voice_banner/
│       ├── __init__.py
│       ├── __main__.py
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── voice_tracker.py
│       ├── tasks.py
│       ├── logging_setup.py
│       ├── utils.py
│       ├── banner/
│       │   ├── __init__.py
│       │   ├── generator.py
│       │   ├── fonts.py
│       │   ├── layout.py
│       │   ├── localization.py
│       │   └── utils.py
│       └── locales/
│           ├── ru.json
│           └── en.json
├── tests/
│   └── smoke_test.py
├── assets/
│   └── fonts/
├── data/
├── .env.example
├── .gitignore
├── pyproject.toml
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

## Пример `.env`

```env
DISCORD_TOKEN=your-discord-bot-token
GUILD_ID=123456789012345678
APPLY_GUILD_BANNER=false

BANNER_PERIOD=all
UPDATE_INTERVAL_SECONDS=300
BANNER_UPDATE_COOLDOWN_SECONDS=20

DATABASE_PATH=data/voice_banner.sqlite3
BANNER_OUTPUT_PATH=data/banner.png
BANNER_WIDTH=1280
BANNER_HEIGHT=640

LANGUAGE=ru
CUSTOM_BANNER_PATH=assets/custom_banner.png
FONT_PATH=assets/fonts/DejaVuSans.ttf
FONT_BOLD_PATH=assets/fonts/DejaVuSans-Bold.ttf

LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
```

Настоящий `.env` нельзя коммитить. Он уже добавлен в `.gitignore`.

## Как использовать свой баннер

1. Положи изображение в папку `assets`, например:

```text
assets/custom_banner.png
```

2. Укажи путь в `.env`:

```env
CUSTOM_BANNER_PATH=assets/custom_banner.png
```

3. Запусти бота:

```bash
python run.py
```

Поддерживаются форматы:

```text
PNG
JPG
JPEG
```

Если файл отсутствует, поврежден или имеет неподходящий формат, бот не упадет. Он запишет предупреждение в лог и использует стандартный сгенерированный фон.

Если изображение другого размера, оно будет приведено к размеру баннера через cover/crop: пропорции сохраняются, изображение центрируется и аккуратно обрезается.

## Как переключить язык

Русский:

```env
LANGUAGE=ru
```

Английский:

```env
LANGUAGE=en
```

Все строки баннера лежат в:

```text
src/discord_voice_banner/locales/ru.json
src/discord_voice_banner/locales/en.json
```

## Где менять шрифты

По умолчанию бот ищет системные шрифты с поддержкой кириллицы: DejaVu Sans, Arial, Arial Unicode, Segoe UI Emoji.

Если хочешь использовать свои шрифты, положи их сюда:

```text
assets/fonts/
```

И укажи в `.env`:

```env
FONT_PATH=assets/fonts/DejaVuSans.ttf
FONT_BOLD_PATH=assets/fonts/DejaVuSans-Bold.ttf
```

Для русского языка нужен TrueType-шрифт с поддержкой кириллицы. Если подходящий шрифт не найден, генератор остановится с понятной ошибкой в логах.

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
| `BANNER_OUTPUT_PATH` | нет | `data/banner.png` | Путь к итоговому баннеру. Можно использовать `.png`, `.jpg`, `.jpeg`. |
| `BANNER_WIDTH` | нет | `1280` | Ширина баннера. |
| `BANNER_HEIGHT` | нет | `640` | Высота баннера. |
| `LANGUAGE` | нет | `ru` | Язык баннера: `ru` или `en`. |
| `CUSTOM_BANNER_PATH` | нет | `assets/custom_banner.png` | Путь к пользовательскому фону. |
| `FONT_PATH` | нет | `assets/fonts/DejaVuSans.ttf` | Путь к обычному шрифту. |
| `FONT_BOLD_PATH` | нет | `assets/fonts/DejaVuSans-Bold.ttf` | Путь к жирному шрифту. |
| `LOG_LEVEL` | нет | `INFO` | Уровень логирования. |
| `LOG_FILE` | нет | `logs/bot.log` | Файл логов. Пустое значение отключает запись в файл. |

## Диагностика

- `Missing required environment variable(s): DISCORD_TOKEN, GUILD_ID` - создай `.env` из `.env.example` и заполни значения.
- `Discord rejected the token` - токен неверный или был пересоздан.
- `PrivilegedIntentsRequired` - включи нужные intents в Discord Developer Portal.
- `Configured guild ... is not visible` - бот не приглашен на сервер или указан неправильный `GUILD_ID`.
- `Discord Forbidden while updating guild banner` - нет права `Manage Server` или сервер не поддерживает баннеры.
- `Custom banner could not be loaded` - файл фона поврежден или не является изображением.
- `Unsupported custom banner format` - фон должен быть `PNG`, `JPG` или `JPEG`.
- `No TrueType font with Unicode/Cyrillic support was found` - укажи `FONT_PATH` и `FONT_BOLD_PATH`.
- `database locked` - запущено несколько копий бота с одной SQLite-базой.

Логи пишутся в консоль и по умолчанию в `logs/bot.log`.

