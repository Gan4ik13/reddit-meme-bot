#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборщик свежих мемов из множества источников.

Запускать локально: python update_memes.py
Или через cron раз в сутки.
"""

import os
import json
import random
import time
import re
from pathlib import Path
from datetime import datetime

import requests

logging_enabled = True
def log(msg):
    if logging_enabled:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

MEMES_PATH = Path(__file__).parent / "memes.json"

# ============================================================
#  Источники мемов (без авторизации Reddit)
# ============================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TelegramMemeBot/2.0",
    "Accept": "application/json",
}


def fetch_with_retry(url, headers=None, timeout=15, retries=3):
    """GET с retry при таймаутах."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers or HEADERS, timeout=timeout)
            return resp
        except requests.exceptions.Timeout:
            log(f"  Таймаут {attempt+1}/{retries}: {url[:60]}...")
            time.sleep(2 ** attempt)  # exponential backoff
        except Exception as e:
            log(f"  Ошибка {attempt+1}/{retries}: {e}")
            time.sleep(1)
    return None


# -----------------------------------------------------------
#  Источник 1: Meme-API (meme-api.com) — без авторизации
# -----------------------------------------------------------

def fetch_meme_api(count: int = 50) -> list[dict]:
    """meme-api.com — публичный API, без auth."""
    memes = []
    subs = [
        "memes", "dankmemes", "me_irl", "ProgrammerHumor",
        "gaming", "wholesomememes", "PrequelMemes", "funny",
        "AnimalsBeingDerps", "sciencememes", "pcmasterrace",
    ]

    for _ in range(count):
        sub = random.choice(subs)
        url = f"https://meme-api.com/gimme/{sub}"
        resp = fetch_with_retry(url, timeout=12)
        if not resp or resp.status_code != 200:
            continue
        try:
            d = resp.json()
            if d.get("nsfw") or not d.get("url"):
                continue
            # Проверяем что URL — картинка
            img_url = d["url"]
            if not any(img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                continue

            title = d.get("title", "Мем").strip()
            title = re.sub(r"\[.*?\]", "", title).strip()
            if len(title) > 150:
                title = title[:147] + "..."

            memes.append({
                "url": img_url,
                "title": title,
                "source": "memeapi",
                "subreddit": d.get("subreddit", sub),
                "tags": [],
                "score": d.get("ups", 50),
                "fetched_at": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            log(f"  MemeAPI parse error: {e}")
        time.sleep(0.7)

    log(f"MemeAPI: собрано {len(memes)} мемов")
    return memes


# -----------------------------------------------------------
#  Источник 2: Imgflip (популярные шаблоны + кастомные)
# -----------------------------------------------------------

def fetch_imgflip() -> list[dict]:
    """Imgflip API — популярные мем-шаблоны."""
    url = "https://api.imgflip.com/get_memes"
    resp = fetch_with_retry(url, timeout=15)
    if not resp or resp.status_code != 200:
        log("Imgflip: недоступен")
        return []

    try:
        data = resp.json()
        if not data.get("success"):
            log("Imgflip: API вернул ошибку")
            return []

        memes = []
        templates = data["data"]["memes"][:30]  # топ-30 популярных

        # Фильтруем только те, что выглядят как мемы (не просто картинки)
        meme_keywords = ["drake", "distracted", "change my mind", "roll safe",
                        "mocking", "always has been", "is this a pigeon",
                        "two buttons", "uno", "panik", "sad pablo",
                        "waiting", "hiding", "sleeping", "work", "office",
                        "cat", "dog", "grumpy", "woman", "guy", "man",
                        "brain", " expanding", "galaxy", "stonks", "skeleton"]

        for t in templates:
            name = t.get("name", "").lower()
            # Берём шаблоны с ключевыми словами мемов
            if any(kw in name for kw in meme_keywords) or t.get("box_count", 0) >= 2:
                img_url = t.get("url", "")
                if not img_url:
                    continue
                memes.append({
                    "url": img_url,
                    "title": t.get("name", "Мем")[:80],
                    "source": "imgflip",
                    "subreddit": "imgflip",
                    "tags": [],
                    "score": 100,  # популярные = высокий score
                    "fetched_at": datetime.utcnow().isoformat(),
                })

        log(f"Imgflip: собрано {len(memes)} шаблонов")
        return memes
    except Exception as e:
        log(f"Imgflip error: {e}")
        return []


# -----------------------------------------------------------
#  Источник 3: Reddit через pushshift.io (альтернатива)
# -----------------------------------------------------------

def fetch_pushshift(sub: str, limit: int = 15) -> list[dict]:
    """Pushshift — зеркало Reddit, меньше банов."""
    url = f"https://api.pullpush.io/reddit/search/submission/?subreddit={sub}&size={limit}&sort=score&order=desc&is_video=false&over_18=false"
    resp = fetch_with_retry(url, timeout=20)
    if not resp or resp.status_code != 200:
        return []

    try:
        data = resp.json()
        posts = data.get("data", [])
        memes = []
        for p in posts:
            img_url = p.get("url", "")
            if not img_url:
                continue
            if not any(img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                # Пробуем preview
                if "reddit" in img_url and "/comments/" in img_url:
                    continue  # self-post
                continue

            title = p.get("title", "Мем").strip()
            title = re.sub(r"\[.*?\]", "", title).strip()
            if len(title) > 150:
                title = title[:147] + "..."

            memes.append({
                "url": img_url,
                "title": title,
                "source": "pushshift",
                "subreddit": sub,
                "tags": [],
                "score": p.get("score", 0),
                "fetched_at": datetime.utcnow().isoformat(),
            })
        log(f"Pushshift r/{sub}: {len(memes)} мемов")
        return memes
    except Exception as e:
        log(f"Pushshift r/{sub} error: {e}")
        return []


# -----------------------------------------------------------
#  Источник 4: Reddit JSON с прокси/задержкой (fallback)
# -----------------------------------------------------------

def fetch_reddit_json(sub: str, limit: int = 15) -> list[dict]:
    """Прямой Reddit JSON — с большими таймаутами и задержками."""
    url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
    # Большой таймаут и задержка чтобы не забанили
    time.sleep(2)
    resp = fetch_with_retry(url, timeout=25, retries=2)
    if not resp or resp.status_code != 200:
        return []

    try:
        data = resp.json()
        posts = data.get("data", {}).get("children", [])
        memes = []
        for post in posts:
            p = post.get("data", {})
            if p.get("stickied") or p.get("is_video") or p.get("selftext"):
                continue
            img_url = p.get("url_overridden_by_dest") or p.get("url")
            if not img_url:
                continue
            if not any(img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                preview = p.get("preview", {}).get("images", [{}])[0].get("source", {}).get("url")
                if preview:
                    img_url = preview.replace("&amp;", "&")
                else:
                    continue

            title = p.get("title", "Мем").strip()
            title = re.sub(r"\[.*?\]", "", title).strip()
            if len(title) > 150:
                title = title[:147] + "..."

            memes.append({
                "url": img_url,
                "title": title,
                "source": "reddit",
                "subreddit": sub,
                "tags": [],
                "score": p.get("score", 0),
                "fetched_at": datetime.utcnow().isoformat(),
            })
        log(f"Reddit r/{sub}: {len(memes)} мемов")
        return memes
    except Exception as e:
        log(f"Reddit r/{sub} error: {e}")
        return []


# ============================================================
#  Обработка и теги
# ============================================================

TAG_MAP = {
    # IT
    "ProgrammerHumor": ["it", "programming"],
    "coding": ["it", "programming"],
    "linuxmemes": ["it", "linux"],
    "techsupportgore": ["it", "tech"],
    "pcmasterrace": ["gaming", "pc"],
    # Жизнь / Общие
    "memes": ["life", "general"],
    "dankmemes": ["life", "general"],
    "me_irl": ["life", "relatable"],
    "funny": ["life", "general"],
    "wholesomememes": ["life", "wholesome"],
    # Игры
    "gaming": ["gaming"],
    "apexlegends": ["gaming"],
    "MinecraftMemes": ["gaming"],
    # Кино
    "PrequelMemes": ["movies", "starwars"],
    "marvelmemes": ["movies", "marvel"],
    "lotrmemes": ["movies", "lotr"],
    # Наука / Абсурд
    "sciencememes": ["science"],
    "space": ["science", "space"],
    "surrealmemes": ["absurd"],
    "boneachingjuice": ["absurd"],
    # Животные
    "AnimalsBeingDerps": ["animals"],
    "cats": ["animals", "cats"],
    "dogs": ["animals", "dogs"],
    "aww": ["animals"],
    # Imgflip
    "imgflip": ["general", "classic"],
}


def deduplicate(memes: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for m in memes:
        url = m["url"].split("?")[0]
        if url not in seen:
            seen.add(url)
            unique.append(m)
    return unique


def assign_tags(memes: list[dict]) -> list[dict]:
    for m in memes:
        sub = m.get("subreddit", "")
        m["tags"] = TAG_MAP.get(sub, ["general"])
    return memes


def filter_quality(memes: list[dict]) -> list[dict]:
    """Фильтр: минимум 20 upvotes, не слишком старые."""
    return [m for m in memes if m.get("score", 0) >= 20]


WITTY_TEMPLATES = {
    "it": [
        "Когда код работает с первого раза",
        "IT-шникам посвящается",
        "Дебаггинг — моя жизнь",
        "Stack Overflow в шоке",
        "Компилируется? Не, не слышал",
        "Hello World, но больно",
        "Рефакторинг пошёл не по плану",
        "Git push — force of nature",
        "Программисты поймут",
        "Это не баг, это фича",
    ],
    "programming": [
        "Код ревью be like",
        "Когда junior пушит в master",
        "Пятница, 18:00, продакшн",
        "Работает — не трогай",
    ],
    "gaming": [
        "GG WP",
        "Лаги? Не, не слышал",
        "Когда босс на 1% хп",
        "Геймерский момент",
        "Just one more turn",
        "Rage quit incoming",
    ],
    "movies": [
        "Киноманская классика",
        "Сценаристы в шоке",
        "Оскар за лучший мем",
        "Приквел лучше оригинала?",
    ],
    "science": [
        "Наука — это весело",
        "Эйнштейн одобряет",
        "Физика не обманывает",
        "Big brain time",
    ],
    "animals": [
        "Животный мем",
        "Пушистик дня",
        "Милота атакует",
        "Кот делает котячьи дела",
    ],
    "general": [
        "Релатбл контент",
        "Жиза",
        "Понедельник начинается",
        "Это я в 3 часа ночи",
        "Муд на сегодня",
        "Свежачок",
        "Ситуация на миллион",
        "Каждый раз одно и то же",
    ],
    "absurd": [
        "Абсурд чистой воды",
        "Что я только что увидел",
        "Сюрреализм интенсифайс",
        "WTF level: over 9000",
    ],
    "life": [
        "Жизненно",
        "Взросление be like",
        "Офисная жиза",
        "Когда выключили будильник",
        "План на выходные",
    ],
    "wholesome": [
        "Доброта спасёт мир",
        "Wholesome момент",
        "Тепло на душе",
        "Верю в человечество",
    ],
    "classic": [
        "Классика жанра",
        "Легендарный мем",
        "Ностальгия по 2010-м",
        "Old but gold",
    ],
}


def generate_witty_caption(base_title: str, tags: list[str]) -> str:
    """Генерирует короткую остроумную подпись."""
    # Если заголовок короткий и не generic — оставляем
    if len(base_title) <= 60 and base_title not in ["Мем", "", " ", "Meme"]:
        # Проверяем что это не просто название сабреддита
        if not base_title.lower().startswith(("r/", "me_irl")):
            return base_title

    candidates = []
    for tag in tags:
        candidates.extend(WITTY_TEMPLATES.get(tag, WITTY_TEMPLATES["general"]))
    if not candidates:
        candidates = WITTY_TEMPLATES["general"]

    return random.choice(candidates)


def enrich_captions(memes: list[dict]) -> list[dict]:
    for m in memes:
        title = m.get("title", "")
        tags = m.get("tags", ["general"])
        if len(title) > 80 or title in ["", " ", "Мем", "Meme"] or title.lower().startswith("me_irl"):
            m["title"] = generate_witty_caption(title, tags)
        else:
            if len(title) > 100:
                m["title"] = title[:97] + "..."
    return memes


# ============================================================
#  Главный цикл
# ============================================================

def main():
    log("=== Начинаем сбор мемов ===")
    all_memes = []

    # 1. Meme-API — основной источник (50 штук)
    log("Источник 1: Meme-API...")
    all_memes.extend(fetch_meme_api(count=50))

    # 2. Imgflip — популярные шаблоны
    log("Источник 2: Imgflip...")
    all_memes.extend(fetch_imgflip())

    # 3. Pushshift — Reddit через зеркало
    log("Источник 3: Pushshift...")
    pushshift_subs = ["memes", "ProgrammerHumor", "gaming", "wholesomememes", "funny"]
    for sub in pushshift_subs:
        all_memes.extend(fetch_pushshift(sub, limit=10))
        time.sleep(1.5)

    # 4. Reddit JSON — fallback (с задержками)
    log("Источник 4: Reddit JSON (fallback)...")
    reddit_subs = ["dankmemes", "me_irl", "PrequelMemes", "AnimalsBeingDerps"]
    for sub in reddit_subs:
        all_memes.extend(fetch_reddit_json(sub, limit=10))
        time.sleep(3)  # Большая задержка чтобы не забанили

    log(f"Всего собрано: {len(all_memes)}")

    # Обработка
    all_memes = deduplicate(all_memes)
    log(f"После дедупликации: {len(all_memes)}")

    all_memes = assign_tags(all_memes)
    all_memes = filter_quality(all_memes)
    log(f"После фильтра качества: {len(all_memes)}")

    if len(all_memes) < 50:
        log("⚠️ Мало мемов после фильтра! Снижаем порог...")
        all_memes = [m for m in all_memes if m.get("score", 0) >= 10]
        log(f"После снижения порога: {len(all_memes)}")

    all_memes = enrich_captions(all_memes)
    random.shuffle(all_memes)

    # Сохраняем
    with open(MEMES_PATH, "w", encoding="utf-8") as f:
        json.dump(all_memes, f, ensure_ascii=False, indent=2)

    log(f"✅ Сохранено {len(all_memes)} мемов в {MEMES_PATH}")

    # Статистика
    tag_stats = {}
    for m in all_memes:
        for t in m.get("tags", ["general"]):
            tag_stats[t] = tag_stats.get(t, 0) + 1
    log("Распределение по тегам:")
    for tag, count in sorted(tag_stats.items(), key=lambda x: -x[1]):
        log(f"  {tag}: {count}")

    if len(all_memes) < 20:
        log("❌ КРИТИЧЕСКИ МАЛО МЕМОВ! Проверь интернет/блокировки.")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
