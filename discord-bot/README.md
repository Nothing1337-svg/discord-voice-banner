# Discord Voice Activity Bot

Бот отслеживает пользователей в голосовых и stage-каналах Discord-сервера, сохраняет статистику в SQLite и автоматически генерирует PNG-баннер с текущим количеством участников и самым активным пользователем за выбранный период.

## Возможности

- отслеживание входа, выхода и переходов между голосовыми каналами в реальном времени;
- подсчет текущих участников в голосе без Discord-ботов;
- сохранение истории голосовых сессий в SQLite;
- определение лидера за `day`, `week`, `month` или `all`;
- генерация изображения `data/current_banner.png` через Pillow;
- опциональная установка этого изображения как баннера сервера;
- slash-команды `/voice_top` и `/voice_banner`;
- логирование и аккуратная обработка ошибок.

## Установка

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Заполните:

- `.env`: `DISCORD_TOKEN`;
- `config.toml`: `discord.guild_id`.

Если `config.toml` случайно удален, восстановите его так:

```bash
cp config.example.toml config.toml
```

В Discord Developer Portal включите для бота:

- Server Members Intent;
- Voice States Intent.

Для режима `banner.mode = "guild"` боту нужно право `Manage Server`, а у сервера должна быть доступна функция баннера. Если это невозможно, оставьте `mode = "file"` и используйте `/voice_banner`.

## Запуск

```bash
source .venv/bin/activate
voice-activity-bot
```

Или:

```bash
python -m voice_activity_bot
```

## Конфигурация

Основной файл: `config.toml`.

```toml
[banner]
mode = "file"
period = "week"
output_path = "data/current_banner.png"
background_path = ""
font_path = ""
```

`background_path` можно указать на свою картинку 16:9. Если путь пустой, бот нарисует спокойный фон сам.

## Команды

- `/voice_top period:week` - показывает самого активного пользователя за период.
- `/voice_banner` - отправляет актуальное изображение баннера в канал.

## Важное про перезапуски

Бот хранит активные сессии в SQLite. После рестарта он сверяет сохраненные активные сессии с реальным состоянием голосовых каналов: тех, кто все еще в голосе, продолжает считать; устаревшие сессии закрывает временем запуска. Если бот был выключен долго, Discord не отдаст точные события, произошедшие во время простоя.
