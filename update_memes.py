#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_memes.py — собирает ~5000 уникальных мемов из бесплатных API.
Запускай: python update_memes.py
"""

import json
import time
import random
import hashlib
import requests
from pathlib import Path

MEMES_PATH = Path(__file__).parent / "memes.json"

TITLES = [
    "Когда деплоишь в пятницу",
    "Код работает, не трогай",
    "Git blame показывает на тебя",
    "Кот одобряет",
    "Баг или фича?",
    "Stack overflow спасает",
    "Когда клиент видит сайт",
    "DevOps в 3 часа ночи",
    "CI/CD прошёл зелёный",
    "Когда найдёшь баг в проде",
    "Код на проде vs код в голове",
    "Рефакторинг за 5 минут",
    "Тык-тык-тык, деплой",
    "Когда всё сломалось",
    "Мем дня",
    "Когда всё работает",
    "Тесты прошли",
    "Когда понял что",
    "Нормальная ситуация",
    "Это точно работает",
    "Лучший день",
    "Когда всё по плану",
    "Жизненное",
    "Совет дня",
    "Знакомо?",
    "Когда клиент доволен",
    "Когда код компилируется",
    "Понедельник после выходных",
    "Когда нашёл решение",
    "Когда всё наконец работает",
]

seen_hashes = set()


def _hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _add_unique(memes: list, url: str, title: str, source: str) -> bool:
    h = _hash(url)
    if h in seen_hashes:
        return False
    seen_hashes.add(h)
    memes.append({"url": url, "title": title, "source": source})
    return True


def fetch_cats(target=800):
    memes = []
    for _ in range(target // 10 + 1):
        try:
            resp = requests.get("https://api.thecatapi.com/v1/images/search?limit=10", timeout=10)
            for item in resp.json():
                if _add_unique(memes, item["url"], random.choice(TITLES), "cat"):
                    pass
            time.sleep(0.3)
        except Exception:
            continue
        if len(memes) >= target:
            break
    return memes[:target]


def fetch_dogs(target=800):
    memes = []
    for _ in range(target // 10 + 1):
        try:
            resp = requests.get("https://dog.ceo/api/breeds/image/random/10", timeout=10)
            for url in resp.json().get("message", []):
                if _add_unique(memes, url, random.choice(TITLES), "dog"):
                    pass
            time.sleep(0.3)
        except Exception:
            continue
        if len(memes) >= target:
            break
    return memes[:target]


def fetch_foxes(target=300):
    memes = []
    for _ in range(target // 3 + 1):
        try:
            resp = requests.get("https://randomfox.ca/floof/", timeout=10)
            url = resp.json().get("image", "")
            if url:
                _add_unique(memes, url, random.choice(TITLES), "fox")
            time.sleep(0.3)
        except Exception:
            continue
        if len(memes) >= target:
            break
    return memes[:target]


def fetch_ducks(target=300):
    memes = []
    for i in range(1, target + 50):
        url = f"https://random-d.uk/api/{random.randint(1, 3463)}.jpg"
        if _add_unique(memes, url, random.choice(TITLES), "duck"):
            pass
        if len(memes) >= target:
            break
    return memes[:target]


def fetch_bears(target=200):
    memes = []
    for _ in range(target // 5 + 1):
        try:
            resp = requests.get("https://api.bearizz.fun/bears?count=5", timeout=10)
            if resp.status_code == 200:
                for item in resp.json():
                    url = item.get("image", "")
                    if url:
                        _add_unique(memes, url, random.choice(TITLES), "bear")
        except Exception:
            pass
        time.sleep(0.3)
        if len(memes) >= target:
            break
    return memes[:target]


def fetch_lorem_picsum(target=800):
    memes = []
    for i in range(1, target + 100):
        seed = random.randint(1, 10000)
        url = f"https://picsum.photos/seed/{seed}/800/600"
        if _add_unique(memes, url, random.choice(TITLES), "picsum"):
            pass
        if len(memes) >= target:
            break
    return memes[:target]


def fetch_nekos(target=200):
    memes = []
    for _ in range(target // 5 + 1):
        try:
            resp = requests.get("https://nekos.best/api/v2/neko?count=5", timeout=10)
            if resp.status_code == 200:
                for item in resp.json().get("results", []):
                    url = item.get("url", "")
                    if url:
                        _add_unique(memes, url, random.choice(TITLES), "neko")
            time.sleep(0.3)
        except Exception:
            continue
        if len(memes) >= target:
            break
    return memes[:target]


def fetch_shibe(target=200):
    memes = []
    for _ in range(target // 5 + 1):
        try:
            resp = requests.get("https://shibe.online/api/shibes?count=5&urls=true", timeout=10)
            if resp.status_code == 200:
                for url in resp.json():
                    if url:
                        _add_unique(memes, url, random.choice(TITLES), "shibe")
            time.sleep(0.3)
        except Exception:
            continue
        if len(memes) >= target:
            break
    return memes[:target]


def fetch_cataas(target=500):
    memes = []
    for i in range(target + 200):
        url = f"https://cataas.com/cat?_={random.randint(1, 999999)}"
        if _add_unique(memes, url, random.choice(TITLES), "cataas"):
            pass
        if len(memes) >= target:
            break
    return memes[:target]


def main():
    print("Собираем мемы...")
    all_memes = []

    sources = [
        ("cats", fetch_cats, 800),
        ("dogs", fetch_dogs, 800),
        ("foxes", fetch_foxes, 300),
        ("ducks", fetch_ducks, 300),
        ("bears", fetch_bears, 200),
        ("picsum", fetch_lorem_picsum, 800),
        ("neko", fetch_nekos, 200),
        ("shibe", fetch_shibe, 200),
        ("cataas", fetch_cataas, 500),
    ]

    for name, fn, count in sources:
        print(f"  {name}...", end=" ", flush=True)
        try:
            memes = fn(count)
            all_memes.extend(memes)
            print(f"+{len(memes)}")
        except Exception as e:
            print(f"ошибка: {e}")
        time.sleep(0.5)

    random.shuffle(all_memes)

    with open(MEMES_PATH, "w", encoding="utf-8") as f:
        json.dump(all_memes, f, ensure_ascii=False, indent=1)

    print(f"\nГотово! {len(all_memes)} уникальных мемов -> {MEMES_PATH}")
    print("Запуши: git add memes.json && git commit -m 'update memes' && git push")


if __name__ == "__main__":
    main()
