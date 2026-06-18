#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_memes.py — скрипт для наполнения базы мемов.
Запускай: python update_memes.py
Результат — memes.json
"""

import json
import time
import random
import requests
from pathlib import Path

MEMES_PATH = Path(__file__).parent / "memes.json"

TITLES = [
    "Кот делает котячьи дела",
    "Пушистый модератор",
    "Кот на патруле",
    "Лапки в деле",
    "Мурлыка-машинка",
    "Котик одобряет",
    "Хвостатый хакер",
    "Сонный программист",
    "Кот в деле",
    "Пушистый алерт",
    "Пёсик на связи",
    "Добрая морда",
    "Хвост восторга",
    "Пёс-программист",
    "Утка дня",
    "Жёлтый мудрец",
    "Дак-хакер",
    "Случайный кадр",
    "Визуальный контент",
]


def fetch_cats(count=1500):
    memes = []
    for _ in range(count // 10):
        try:
            resp = requests.get("https://api.thecatapi.com/v1/images/search?limit=10", timeout=10)
            for item in resp.json():
                memes.append({"url": item["url"], "title": random.choice(TITLES), "source": "cat"})
            time.sleep(0.3)
        except Exception:
            continue
    return memes


def fetch_dogs(count=1500):
    memes = []
    for _ in range(count // 10):
        try:
            resp = requests.get("https://dog.ceo/api/breeds/image/random/10", timeout=10)
            for url in resp.json().get("message", []):
                memes.append({"url": url, "title": random.choice(TITLES), "source": "dog"})
            time.sleep(0.3)
        except Exception:
            continue
    return memes


def fetch_cataas(count=1000):
    memes = []
    for i in range(count):
        memes.append({
            "url": f"https://cataas.com/cat?t={random.randint(1, 999999)}",
            "title": random.choice(TITLES),
            "source": "cataas",
        })
    return memes


def fetch_ducks(count=500):
    memes = []
    for i in range(1, count + 1):
        memes.append({
            "url": f"https://random-d.uk/api/{random.randint(1, 3000)}.jpg",
            "title": random.choice(TITLES),
            "source": "duck",
        })
    return memes


def fetch_picsum(count=500):
    memes = []
    for i in range(count):
        memes.append({
            "url": f"https://picsum.photos/seed/{random.randint(1, 99999)}/800/600",
            "title": random.choice(TITLES),
            "source": "picsum",
        })
    return memes


def main():
    print("Собираем мемы...")
    all_memes = []

    for name, fn in [("cats", fetch_cats), ("dogs", fetch_dogs), ("cataas", fetch_cataas), ("ducks", fetch_ducks), ("picsum", fetch_picsum)]:
        print(f"  {name}...", end=" ", flush=True)
        try:
            memes = fn(500)
            all_memes.extend(memes)
            print(f"+{len(memes)}")
        except Exception as e:
            print(f"ошибка: {e}")
        time.sleep(0.5)

    random.shuffle(all_memes)
    all_memes = all_memes[:5000]

    with open(MEMES_PATH, "w", encoding="utf-8") as f:
        json.dump(all_memes, f, ensure_ascii=False, indent=1)

    print(f"\nГотово! {len(all_memes)} мемов -> {MEMES_PATH}")
    print("Теперь запуши в GitHub")


if __name__ == "__main__":
    main()
