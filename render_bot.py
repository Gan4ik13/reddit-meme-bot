#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VK Meme Telegram Bot — Render.com deployment.

Берёт лучшие мемы из VK пабликов и постит в Telegram канал.
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

VK_ACCESS_TOKEN = os.environ.get("VK_ACCESS_TOKEN", "")

VK_GROUPS = [
    -23811351,
    -178542337,
    -127517820,
    -36458093,
    -38131646,
    -151052765,
    -217498432,
    -171520934,
    -19985991,
    -30496112,
]

MIN_LIKES = 50
POSTS_PER_GROUP = 30

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
            vk_post_id    TEXT UNIQUE,
            title         TEXT NOT NULL,
            image_url     TEXT,
            source_url    TEXT,
            likes         INTEGER DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'pending',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at  TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_posts_vk ON posts(vk_post_id);
    """)


def _add_vk_post(vk_post_id: str, title: str, image_url: str, source_url: str, likes: int) -> bool:
    try:
        _conn.execute(
            "INSERT OR IGNORE INTO posts (vk_post_id, title, image_url, source_url, likes, status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (vk_post_id, title, image_url, source_url, likes),
        )
        _conn.commit()
        return _conn.total_changes > 0
    except Exception:
        return False


def _get_pending():
    cur = _conn.execute(
        "SELECT id, title, image_url, source_url FROM posts WHERE status='pending' ORDER BY likes DESC LIMIT 1"
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
#  VK API
# ============================================================

def _fetch_vk_posts(owner_id: int, count: int = POSTS_PER_GROUP) -> list[dict]:
    url = "https://api.vk.com/method/wall.get"
    params = {
        "owner_id": owner_id,
        "count": count,
        "filter": "owner",
        "access_token": VK_ACCESS_TOKEN,
        "v": "5.199",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            log.warning("VK API error for %s: %s", owner_id, data["error"].get("error_msg", ""))
            return []
        items = data.get("response", {}).get("items", [])
        posts = []
        for item in items:
            if item.get("is_pinned"):
                continue
            if item.get("marked_as_ads"):
                continue
            text = item.get("text", "")
            attachments = item.get("attachments", [])
            image_url = _extract_vk_image(attachments)
            if not image_url:
                continue
            likes = item.get("likes", {}).get("count", 0)
            if likes < MIN_LIKES:
                continue
            post_url = f"https://vk.com/wall{owner_id}_{item['id']}"
            title = _clean_vk_text(text)
            if not title:
                title = "Мем из VK"
            posts.append({
                "vk_post_id": f"{owner_id}_{item['id']}",
                "title": title,
                "image_url": image_url,
                "source_url": post_url,
                "likes": likes,
            })
        return posts
    except Exception as e:
        log.warning("VK fetch error (%s): %s", owner_id, e)
        return []


def _extract_vk_image(attachments: list) -> str | None:
    for att in attachments:
        att_type = att.get("type", "")
        if att_type == "photo":
            sizes = att.get("photo", {}).get("sizes", [])
            best = None
            for s in sizes:
                if s.get("type") in ("w", "z", "y", "x"):
                    best = s.get("url")
            if best:
                return best
            if sizes:
                return sizes[-1].get("url")
        elif att_type == "doc" and att.get("doc", {}).get("type") == 6:
            return att["doc"].get("url")
    return None


def _clean_vk_text(text: str) -> str:
    text = re.sub(r"\[.*?\|.*?\]", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"#\S+", "", text)
    text = text.strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return lines[0][:200] if lines else ""


def _fetch_all_vk() -> int:
    added = 0
    for group_id in VK_GROUPS:
        posts = _fetch_vk_posts(group_id, POSTS_PER_GROUP)
        for p in posts:
            if _add_vk_post(p["vk_post_id"], p["title"], p["image_url"], p["source_url"], p["likes"]):
                added += 1
        time.sleep(0.5)
    return added


# ============================================================
#  Публикация в Telegram
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
        if "wrong type" in str(error).lower() or "failed to get" in str(error).lower():
            log.warning("Photo failed, trying document: %s", error[:100])
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
        return resp.json().get("ok", False)
    except Exception as e:
        log.error("Document send error: %s", e)
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
    added = _fetch_all_vk()
    log.info("=== SOURCING: добавлено %d (всего: %d) ===", added, _pending_count())


def job_publishing():
    log.info("=== PUBLISHING ===")
    result = _get_pending()
    if not result:
        log.info("Очередь пуста, sourcing...")
        job_sourcing()
        result = _get_pending()
        if not result:
            log.warning("Всё равно пусто")
            return

    post_id, title, image_url, source_url = result
    log.info("Публикуем: %s", title[:60])

    if _send_photo(image_url, title):
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
    return aiohttp.web.json_response({"status": "ok", "bot": "vk-meme-bot"})


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
    if not VK_ACCESS_TOKEN:
        log.error("VK_ACCESS_TOKEN не задан!")
        sys.exit(1)

    _init_db()
    log.info("Бот запущен. Канал: %s", TG_CHANNEL)
    log.info("VK пабликов: %d", len(VK_GROUPS))
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
