# Reddit Meme Bot

Telegram-бот, постящий лучшие мемы с Reddit раз в час.

## Запуск

```bash
pip install -r requirements.txt
TG_BOT_TOKEN=xxx TG_CHANNEL=@your_channel python render_bot.py
```

## Архитектура

```
Reddit API (r/memes, r/ProgrammerHumor, ...) 
  → SQLite очередь (data/bot.db) — дедупликация по reddit_id
  → APScheduler (sourcing каждые 30 мин, publishing каждый час)
  → Telegram Bot API sendPhoto
```

## Развёртывание

1. Telegram: @BotFather → `/newbot` → токен
2. Создать канал, добавить бота админом
3. GitHub: `Gan4ik13/reddit-meme-bot`
4. Render: Python 3, Free, env vars:
   - `TG_BOT_TOKEN` — токен от BotFather
   - `TG_CHANNEL` — @username канала

## Конфигурация

Все настройки в `render_bot.py`:
- `REDDIT_SUBREDDITS` — список сабреддитов
- `MIN_SCORE` — минимальный рейтинг поста (100)
- `REDDIT_SORT` — сортировка Reddit (hot/top)
- Расписание: sourcing `*/30 * * * *`, publishing `0 * * * *`

## Конвенции

- Python 3.12+, без type checker
- Reddit API без авторизации (публичные посты)
- SQLite для очереди, дедупликация по reddit_id
- aiohttp для health check + self-ping (Render free tier)
- Картинки отправляются как sendPhoto, fallback на sendDocument
