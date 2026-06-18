# Meme Bot

Telegram-бот, постящий мемы из локальной JSON-базы раз в час.

## Запуск

```bash
pip install -r requirements.txt
TG_BOT_TOKEN=xxx TG_CHANNEL=@your_channel python render_bot.py
```

## Обновление базы мемов

```bash
python update_memes.py   # собирает ~2500 мемов из бесплатных API
git add memes.json && git commit -m "update memes" && git push
```

## Архитектура

```
memes.json (2500 мемов: коты, псы, утки, картинки)
  → SQLite (data/bot.db) — трекинг отправленных
  → APScheduler (каждый час)
  → Telegram Bot API sendPhoto
```

## Развёртывание

1. Telegram: @BotFather → `/newbot` → токен
2. Создать канал, добавить бота админом
3. GitHub: `Gan4ik13/reddit-meme-bot`
4. Render: Python 3, Free, env vars: `TG_BOT_TOKEN`, `TG_CHANNEL`

## Расписание

- Каждый час: публикация мема
- После отправки всех: сброс истории, повтор
- Обновление базы: `python update_memes.py` раз в неделю
