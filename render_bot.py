#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Meme Telegram Bot — Render.com deployment.

Постит мемы каждые 35-50 минут (рандом).
Подписи короткие, остроумные.
Внизу: хештеги + кнопка "Подписаться".
"""

import os
import sys
import json
import time
import random
import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp.web
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# ============================================================
#  Логирование
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")

# ============================================================
#  Конфигурация — ТОЛЬКО из env vars
# ============================================================

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHANNEL = os.environ.get("TG_CHANNEL", "").strip()
PORT = int(os.environ.get("PORT", 8080))

if not TG_BOT_TOKEN:
    log.error("TG_BOT_TOKEN не задан!")
    sys.exit(1)

if not TG_CHANNEL:
    log.error("TG_CHANNEL не задан!")
    sys.exit(1)

# Нормализуем канал
if TG_CHANNEL.startswith("t.me/"):
    TG_CHANNEL = "@" + TG_CHANNEL[5:]
elif not TG_CHANNEL.startswith("@") and not TG_CHANNEL.startswith("-"):
    TG_CHANNEL = "@" + TG_CHANNEL

CHANNEL_NAME = TG_CHANNEL.lstrip("@")

# Проверка токена
def _validate_token():
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getMe"
    try:
        resp = requests.get(url, timeout=15)
        data = resp.json()
        if data.get("ok"):
            bot_info = data["result"]
            log.info("Токен валиден. Бот: @%s (id=%s)", bot_info["username"], bot_info["id"])
            return True
        else:
            log.error("Токен НЕВАЛИДЕН! %s", data.get("description"))
            return False
    except Exception as e:
        log.error("Ошибка проверки токена: %s", e)
        return False

if not _validate_token():
    sys.exit(1)

log.info("Канал для публикации: %s", TG_CHANNEL)

MEMES_PATH = Path(__file__).parent / "memes.json"

# ============================================================
#  SQLite
# ============================================================

DB_PATH = Path(os.environ.get("DATA_DIR", "data")) / "bot.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
_conn.row_factory = sqlite3.Row


def _init_db():
    _conn.executescript("""
        CREATE TABLE IF NOT EXISTS sent_memes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meme_url TEXT NOT NULL UNIQUE,
            meme_tags TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_sent_url ON sent_memes(meme_url);
        CREATE INDEX IF NOT EXISTS idx_sent_at ON sent_memes(sent_at);

        CREATE TABLE IF NOT EXISTS tag_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_tag_hist ON tag_history(tag, sent_at);
    """)


def _is_sent(url: str) -> bool:
    cur = _conn.execute("SELECT 1 FROM sent_memes WHERE meme_url = ? LIMIT 1", (url,))
    return cur.fetchone() is not None


def _mark_sent(url: str, tags: str = ""):
    try:
        _conn.execute("INSERT OR IGNORE INTO sent_memes (meme_url, meme_tags) VALUES (?, ?)", (url, tags))
        _conn.commit()
    except Exception as e:
        log.error("DB mark_sent error: %s", e)


def _sent_count() -> int:
    return _conn.execute("SELECT COUNT(*) FROM sent_memes").fetchone()[0]


def _get_recent_tags(hours: int = 6) -> list[str]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    cur = _conn.execute(
        "SELECT tag FROM tag_history WHERE sent_at > ? ORDER BY sent_at DESC",
        (since,)
    )
    return [row[0] for row in cur.fetchall()]


def _log_tag(tag: str):
    _conn.execute("INSERT INTO tag_history (tag) VALUES (?)", (tag,))
    _conn.commit()


def _cleanup_old():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _conn.execute("DELETE FROM sent_memes WHERE sent_at < ?", (cutoff,))
    _conn.execute("DELETE FROM tag_history WHERE sent_at < ?", (cutoff,))
    _conn.commit()


# ============================================================
#  Мемы из JSON (с перезагрузкой)
# ============================================================

_memes_cache: list[dict] = []
_cache_mtime: float = 0


def _load_memes() -> list[dict]:
    global _memes_cache, _cache_mtime

    if not MEMES_PATH.exists():
        log.error("memes.json не найден!")
        return []

    current_mtime = MEMES_PATH.stat().st_mtime
    if _memes_cache and _cache_mtime == current_mtime:
        return _memes_cache

    try:
        with open(MEMES_PATH, "r", encoding="utf-8") as f:
            _memes_cache = json.load(f)
        _cache_mtime = current_mtime
        log.info("Загружено %d мемов из базы", len(_memes_cache))
    except Exception as e:
        log.error("Ошибка загрузки memes.json: %s", e)
        if not _memes_cache:
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

    recent_tags = _get_recent_tags(hours=6)

    def score_meme(meme):
        tags = meme.get("tags", ["general"])
        overlap = sum(1 for t in tags if t in recent_tags)
        return overlap * 100 + random.randint(0, 50)

    unsent.sort(key=score_meme)
    top_pool = unsent[:min(10, len(unsent))]
    chosen = random.choice(top_pool)

    primary_tag = chosen.get("tags", ["general"])[0]
    _log_tag(primary_tag)

    return chosen


# ============================================================
#  Подписи и хештеги
# ============================================================

HASHTAG_MAP = {
    "it": "#it #программирование #технологии",
    "programming": "#код #программист #it",
    "gaming": "#игры #гейминг #gamers",
    "movies": "#кино #фильмы #попкультура",
    "science": "#наука #космос #умно",
    "animals": "#животные #милота #пушистики",
    "life": "#жиза #жизнь #relatable",
    "general": "#мемы #юмор #свежачок",
    "absurd": "#абсурд #сюрреализм #wtf",
    "wholesome": "#доброта #wholesome #тепло",
    "classic": "#классика #мемы #oldbutgold",
    "relatable": "#жиза #все_мы #relatable",
    "pc": "#пк #гейминг #техника",
    "starwars": "#звездныевойны #кино #мемы",
    "marvel": "#марвел #кино #мемы",
    "linux": "#linux #opensource #it",
    "tech": "#технологии #it #гаджеты",
    "space": "#космос #наука #вселенная",
    "cats": "#коты #животные #милота",
    "dogs": "#собаки #животные #милота",
}


def _build_caption(meme: dict) -> str:
    """Формирует подпись: текст + хештеги + название канала."""
    title = meme.get("title", "Мем").strip()
    tags = meme.get("tags", ["general"])

    primary_tag = tags[0] if tags else "general"
    hashtag_line = HASHTAG_MAP.get(primary_tag, HASHTAG_MAP["general"])

    # Собираем caption
    caption = f"{title}\n\n{hashtag_line} #{CHANNEL_NAME}"

    # Telegram limit: 1024 chars for caption
    if len(caption) > 1024:
        title = title[:900] + "..."
        caption = f"{title}\n\n{hashtag_line} #{CHANNEL_NAME}"

    return caption


# ============================================================
#  Telegram API
# ============================================================

def _send_photo(image_url: str, caption: str) -> bool:
    """Отправляет фото с inline-кнопкой Подписаться."""
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Подписаться", "url": f"https://t.me/{CHANNEL_NAME}"}
        ]]
    }

    payload = {
        "chat_id": TG_CHANNEL,
        "photo": image_url,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(keyboard),
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            log.info("Фото отправлено успешно")
            return True
        error = data.get("description", "")
        log.error("Telegram API error: %s", error[:200])
        if "wrong file" in error.lower() or "failed to get" in error.lower():
            return _send_as_document(image_url, caption)
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        text = e.response.text[:200]
        log.error("HTTP %s: %s", status, text)
        if status == 429:
            log.warning("Rate limit! Ждём 60 сек...")
            time.sleep(60)
    except Exception as e:
        log.error("Send error: %s", e)
    return False


def _send_as_document(image_url: str, caption: str) -> bool:
    """Fallback: отправка как документ."""
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendDocument"
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Подписаться", "url": f"https://t.me/{CHANNEL_NAME}"}
        ]]
    }
    payload = {
        "chat_id": TG_CHANNEL,
        "document": image_url,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(keyboard),
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        return resp.json().get("ok", False)
    except Exception as e:
        log.error("Send document error: %s", e)
        return False


# ============================================================
#  Публикация
# ============================================================

_last_post_time: datetime | None = None


def job_publishing():
    global _last_post_time
    log.info("=== PUBLISHING ===")

    meme = _get_next_meme()
    if not meme:
        log.warning("Нет мемов в базе! Запусти update_memes.py")
        return

    url = meme["url"]
    caption = _build_caption(meme)
    log.info("Публикуем: %s", caption[:60].replace("\n", " "))
    log.info("URL: %s", url[:80])

    if _send_photo(url, caption):
        _mark_sent(url, ",".join(meme.get("tags", [])))
        _last_post_time = datetime.now(timezone.utc)
        total = len(_load_memes())
        sent = _sent_count()
        log.info("✅ Опубликовано! Отправлено: %d/%d", sent, total)
        _cleanup_old()
    else:
        log.error("❌ Не удалось отправить")


# ============================================================
#  Рандомный интервал 35-50 минут
# ============================================================

def get_random_interval() -> int:
    return random.randint(35 * 60, 50 * 60)


# ============================================================
#  HTTP сервер
# ============================================================

start_time = datetime.now(timezone.utc)


async def handle_health(request):
    memes = _load_memes()
    next_post = "N/A"
    if _last_post_time:
        next_est = _last_post_time + timedelta(minutes=42)
        next_post = next_est.strftime("%H:%M:%S")

    return aiohttp.web.json_response({
        "status": "ok",
        "bot": "meme-bot",
        "version": "2.1",
        "total_memes": len(memes),
        "sent": _sent_count(),
        "last_post": _last_post_time.isoformat() if _last_post_time else None,
        "next_post_est": next_post,
        "uptime_hours": round((datetime.now(timezone.utc) - start_time).total_seconds() / 3600, 1),
    })


async def handle_root(request):
    return aiohttp.web.json_response({
        "status": "ok",
        "bot": "meme-bot",
        "message": "Бот работает. Постит мемы каждые 35-50 минут.",
    })


async def self_ping():
    while True:
        await asyncio.sleep(300)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{PORT}/health") as resp:
                    pass
        except Exception:
            pass


# ============================================================
#  Главный цикл
# ============================================================

def main():
    _init_db()
    _load_memes()

    total = len(_load_memes())
    sent = _sent_count()
    log.info("🚀 Бот запущен")
    log.info("📊 Мемов в базе: %d | Отправлено: %d | Канал: %s", total, sent, TG_CHANNEL)

    app = aiohttp.web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)

    runner = aiohttp.web.AppRunner(app)

    async def start():
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        log.info("🌐 HTTP сервер на порту %d", PORT)

        scheduler = AsyncIOScheduler(timezone="UTC")

        # Первый пост через 2-5 минут
        first_delay = random.randint(2 * 60, 5 * 60)

        def random_job():
            job_publishing()
            next_interval = get_random_interval()
            scheduler.reschedule_job("random_post", trigger="interval", seconds=next_interval)
            log.info("⏭ Следующий пост через %d мин", next_interval // 60)

        scheduler.add_job(
            random_job,
            "interval",
            seconds=first_delay,
            id="random_post",
            max_instances=1,
            coalesce=True,
        )

        scheduler.start()
        log.info("⏰ Планировщик запущен. Первый пост через %d мин", first_delay // 60)

        asyncio.ensure_future(self_ping())

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
        log.info("🛑 Остановлен")


if __name__ == "__main__":
    main()
