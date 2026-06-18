#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Meme Telegram Bot — Render.com deployment.

Постит мемы из локальной JSON-базы memes.json.
Базу обновляешь скриптом update_memes.py раз в неделю.
"""

import os
import sys
import json
import random
import sqlite3
import logging
import asyncio
from datetime import datetime
from pathlib import Path

import aiohttp.web
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHANNEL = os.environ.get("TG_CHANNEL", "")
PORT = int(os.environ.get("PORT", 8080))

MEMES_PATH = Path(__file__).parent / "memes.json"

# ============================================================
#  SQLite — трекинг отправленных мемов
# ============================================================

DB_PATH = Path(os.environ.get("DATA_DIR", "data")) / "bot.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
_conn.row_factory = sqlite3.Row


def _init_db():
    _conn.executescript("""
        CREATE TABLE IF NOT EXISTS sent_memes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meme_url TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_sent_url ON sent_memes(meme_url);
    """)


def _is_sent(url: str) -> bool:
    cur = _conn.execute("SELECT 1 FROM sent_memes WHERE meme_url = ? LIMIT 1", (url,))
    return cur.fetchone() is not None


def _mark_sent(url: str):
    _conn.execute("INSERT INTO sent_memes (meme_url) VALUES (?)", (url,))
    _conn.commit()


def _sent_count() -> int:
    return _conn.execute("SELECT COUNT(*) FROM sent_memes").fetchone()[0]


# ============================================================
#  Мемы из JSON
# ============================================================

_memes_cache: list[dict] = []


def _load_memes() -> list[dict]:
    global _memes_cache
    if _memes_cache:
        return _memes_cache
    if MEMES_PATH.exists():
        with open(MEMES_PATH, "r", encoding="utf-8") as f:
            _memes_cache = json.load(f)
        log.info("Загружено %d мемов из базы", len(_memes_cache))
    else:
        log.error("memes.json не найден!")
        _memes_cache = []
    return _memes_cache


def _get_next_meme() -> dict | None:
    memes = _load_memes()
    if not memes:
        return None

    unsent = [m for m in memes if not _is_sent(m["url"])]
    if not unsent:
        log.info("Все мемы отправлены! Сбрасываем историю.")
        _conn.execute("DELETE FROM sent_memes")
        _conn.commit()
        unsent = memes

    return random.choice(unsent)


# ============================================================
#  Telegram
# ============================================================

def _send_photo(image_url: str, caption: str) -> bool:
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TG_CHANNEL,
        "photo": image_url,
        "caption": caption[:1024],
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            return True
        error = data.get("description", "")
        log.error("Telegram: %s", error[:200])
    except Exception as e:
        log.error("Send error: %s", e)
    return False


# ============================================================
#  Jobs
# ============================================================

def job_publishing():
    log.info("=== PUBLISHING ===")
    meme = _get_next_meme()
    if not meme:
        log.warning("Нет мемов в базе!")
        return

    url = meme["url"]
    title = meme.get("title", "Мем")
    log.info("Публикуем: %s", title[:60])

    if _send_photo(url, title):
        _mark_sent(url)
        log.info("Опубликовано! Отправлено: %d/%d", _sent_count(), len(_load_memes()))
    else:
        log.error("Не удалось отправить")


# ============================================================
#  aiohttp
# ============================================================

async def handle_health(request):
    return aiohttp.web.json_response({
        "status": "ok",
        "total_memes": len(_load_memes()),
        "sent": _sent_count(),
        "uptime": str(datetime.utcnow() - start_time),
    })


async def handle_root(request):
    return aiohttp.web.json_response({"status": "ok", "bot": "meme-bot"})


async def self_ping():
    while True:
        await asyncio.sleep(600)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{PORT}/health") as resp:
                    log.info("Self-ping: %s", resp.status)
        except Exception:
            pass


start_time = datetime.now()


def main():
    if not TG_BOT_TOKEN:
        log.error("TG_BOT_TOKEN не задан!")
        sys.exit(1)
    if not TG_CHANNEL:
        log.error("TG_CHANNEL не задан!")
        sys.exit(1)

    _init_db()
    _load_memes()
    log.info("Бот запущен. Канал: %s", TG_CHANNEL)
    log.info("Мемов в базе: %d, отправлено: %d", len(_load_memes()), _sent_count())

    app = aiohttp.web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)

    runner = aiohttp.web.AppRunner(app)

    async def start():
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        log.info("HTTP сервер на порту %d", PORT)

        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            job_publishing,
            CronTrigger.from_crontab("0 * * * *"),
            id="publishing",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        log.info("Планировщик запущен")

        asyncio.ensure_future(self_ping())

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, job_publishing)

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            scheduler.shutdown()
            await runner.cleanup()

    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        log.info("Остановлен")


if __name__ == "__main__":
    main()
