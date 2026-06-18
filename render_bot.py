#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reddit Meme Telegram Bot — Render.com deployment.

Берёт лучшие посты с Reddit (юмор, мемы, программисты)
и постит в Telegram канал раз в час.
"""

import os
import sys
import json
import time
import random
import re
import hashlib
import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta
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

# ============================================================
#  Конфигурация из env
# ============================================================

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHANNEL = os.environ.get("TG_CHANNEL", "")
PORT = int(os.environ.get("PORT", 8080))

REDDIT_SUBREDDITS = [
    "ProgrammerHumor",
    "memes",
    "dankmemes",
    "funny",
    "me_irl",
    "techhumor",
    "SoftwareGore",
    "Bossfight",
    "tifu",
    "whitepeoplegifs",
]

REDDIT_SORT = "hot"
REDDIT_TIMEFRAME = "day"
MIN_SCORE = 100

# ============================================================
#  SQLite
# ============================================================

DB_PATH = Path(os.environ.get("DATA_DIR", "data")) / "bot.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
_conn.row_factory = sqlite3.Row


def _init_db():
    _conn.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            reddit_id     TEXT UNIQUE,
            title         TEXT NOT NULL,
            image_url     TEXT,
            source_url    TEXT,
            score         INTEGER DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'pending',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at  TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_posts_reddit ON posts(reddit_id);
    """)


def _add_reddit_post(reddit_id: str, title: str, image_url: str, source_url: str, score: int) -> bool:
    try:
        _conn.execute(
            "INSERT OR IGNORE INTO posts (reddit_id, title, image_url, source_url, score, status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (reddit_id, title, image_url, source_url, score),
        )
        _conn.commit()
        return _conn.total_changes > 0
    except Exception:
        return False


def _get_pending():
    cur = _conn.execute(
        "SELECT id, title, image_url, source_url FROM posts WHERE status='pending' ORDER BY score DESC LIMIT 1"
    )
    row = cur.fetchone()
    return (row["id"], row["title"], row["image_url"], row["source_url"]) if row else None


def _mark_published(post_id: int):
    _conn.execute(
        "UPDATE posts SET status='published', published_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), post_id),
    )
    _conn.commit()


def _mark_failed(post_id: int):
    _conn.execute("UPDATE posts SET status='failed' WHERE id=?", (post_id,))
    _conn.commit()


def _pending_count() -> int:
    return _conn.execute("SELECT COUNT(*) FROM posts WHERE status='pending'").fetchone()[0]


# ============================================================
#  Reddit API (без авторизации — публичные посты)
# ============================================================

def _fetch_reddit_posts(subreddit: str, sort: str = "hot", limit: int = 25) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t=day"
    headers = {"User-Agent": "TelegramMemeBot/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        posts = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if post.get("stickied"):
                continue
            if post.get("is_self") and not post.get("url_overridden_by_dest"):
                continue
            permalink = post.get("permalink", "")
            image_url = _extract_image_url(post)
            if not image_url:
                continue
            posts.append({
                "reddit_id": post.get("id", ""),
                "title": post.get("title", ""),
                "image_url": image_url,
                "source_url": f"https://reddit.com{permalink}",
                "score": post.get("score", 0),
            })
        return posts
    except Exception as e:
        log.warning("Reddit fetch error (%s): %s", subreddit, e)
        return []


def _extract_image_url(post: dict) -> str | None:
    url = post.get("url_overridden_by_dest") or post.get("url", "")
    if not url:
        return None
    if url.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return url
    if "i.redd.it" in url:
        return url
    if "imgur.com" in url:
        if "/a/" in url or "/gallery/" in url:
            return None
        if not url.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
            url = url + ".jpg"
        return url
    if post.get("preview", {}).get("images"):
        source = post["preview"]["images"][0].get("source", {})
        src_url = source.get("url", "").replace("&amp;", "&")
        if src_url:
            return src_url
    if post.get("thumbnail") in ("self", "default", "nsfw", "spoiler"):
        return None
    if post.get("thumbnail", "").startswith("http"):
        return post["thumbnail"]
    return None


def _fetch_all_reddit() -> int:
    added = 0
    for sub in REDDIT_SUBREDDITS:
        posts = _fetch_reddit_posts(sub, REDDIT_SORT, 25)
        for p in posts:
            if p["score"] >= MIN_SCORE:
                if _add_reddit_post(p["reddit_id"], p["title"], p["image_url"], p["source_url"], p["score"]):
                    added += 1
        time.sleep(1)
    return added


# ============================================================
#  Публикация в Telegram
# ============================================================

def _format_caption(title: str, source_url: str) -> str:
    return title


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
        if "wrong type of photo" in str(error).lower() or "failed to get http url content" in str(error).lower():
            log.warning("Photo failed, trying as document: %s", error[:100])
            return _send_document(image_url, caption)
        log.error("Telegram photo API: %s", error[:200])
    except Exception as e:
        log.error("Photo send error: %s", e)
    return False


def _send_document(file_url: str, caption: str) -> bool:
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendDocument"
    payload = {
        "chat_id": TG_CHANNEL,
        "document": file_url,
        "caption": caption[:1024],
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            return True
        log.error("Telegram document API: %s", data.get("description", "")[:200])
    except Exception as e:
        log.error("Document send error: %s", e)
    return False


def _send_text(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHANNEL,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json().get("ok", False)
    except Exception as e:
        log.error("Text send error: %s", e)
    return False


# ============================================================
#  APScheduler jobs
# ============================================================

MIN_QUEUE = 3


def job_sourcing():
    log.info("=== SOURCING: очередь=%d ===", _pending_count())
    if _pending_count() >= MIN_QUEUE:
        log.info("Очередь полная, пропускаем")
        return

    added = _fetch_all_reddit()
    log.info("=== SOURCING: добавлено %d (всего: %d) ===", added, _pending_count())


def job_publishing():
    log.info("=== PUBLISHING ===")
    result = _get_pending()
    if not result:
        log.info("Очередь пуста, запускаем sourcing...")
        job_sourcing()
        result = _get_pending()
        if not result:
            log.warning("Всё равно пусто")
            return

    post_id, title, image_url, source_url = result
    caption = _format_caption(title, source_url)
    log.info("Публикуем: %s", title[:60])

    if _send_photo(image_url, caption):
        _mark_published(post_id)
        log.info("Опубликовано! В очереди: %d", _pending_count())
    else:
        _mark_failed(post_id)
        log.error("Не удалось, помечено failed")


# ============================================================
#  aiohttp: health check + self-ping
# ============================================================

async def handle_health(request):
    return aiohttp.web.json_response({
        "status": "ok",
        "pending": _pending_count(),
        "uptime": str(datetime.utcnow() - start_time),
    })


async def handle_root(request):
    return aiohttp.web.json_response({"status": "ok", "bot": "reddit-meme-bot"})


async def self_ping():
    while True:
        await asyncio.sleep(600)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{PORT}/health") as resp:
                    log.info("Self-ping: %s", resp.status)
        except Exception as e:
            log.warning("Self-ping failed: %s", e)


start_time = datetime.now()


# ============================================================
#  Main
# ============================================================

def main():
    if not TG_BOT_TOKEN:
        log.error("TG_BOT_TOKEN не задан!")
        sys.exit(1)
    if not TG_CHANNEL:
        log.error("TG_CHANNEL не задан!")
        sys.exit(1)

    _init_db()
    log.info("Бот запущен. Канал: %s", TG_CHANNEL)
    log.info("Сабреддиты: %s", ", ".join(REDDIT_SUBREDDITS))
    log.info("Очередь: %d постов", _pending_count())

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
            job_sourcing,
            CronTrigger.from_crontab("*/30 * * * *"),
            id="sourcing",
            max_instances=1,
            coalesce=True,
        )
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

        def _initial_run():
            if _pending_count() < MIN_QUEUE:
                log.info("Стартовое наполнение очереди...")
                job_sourcing()
            if _pending_count() > 0:
                log.info("Стартовая публикация...")
                job_publishing()

        loop.run_in_executor(None, _initial_run)

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
