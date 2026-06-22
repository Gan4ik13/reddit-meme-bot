#!/usr/bin/env python3
import re, json, requests, time, random, sys
from pathlib import Path
from datetime import datetime, timezone

MEMES_PATH = Path(__file__).parent / "memes.json"

WITTY_TEMPLATES = {
    "it": ["Когда код работает с первого раза", "IT-шникам посвящается", "Дебаггинг — моя жизнь", "Stack Overflow в шоке", "Компилируется? Не, не слышал", "Рефакторинг пошёл не по плану", "Git push — force of nature", "Программисты поймут", "Это не баг, это фича"],
    "gaming": ["GG WP", "Лаги? Не, не слышал", "Когда босс на 1% хп", "Геймерский момент", "Just one more turn", "Rage quit incoming"],
    "movies": ["Киноманская классика", "Сценаристы в шоке", "Оскар за лучший мем"],
    "science": ["Наука — это весело", "Эйнштейн одобряет", "Big brain time"],
    "animals": ["Животный мем", "Пушистик дня", "Милота атакует"],
    "general": ["Релатбл контент", "Жиза", "Понедельник начинается", "Это я в 3 часа ночи", "Свежачок", "Каждый раз одно и то же"],
    "absurd": ["Абсурд чистой воды", "Что я только что увидел", "WTF level: over 9000"],
    "life": ["Жизненно", "Взросление be like", "Офисная жиза"],
    "wholesome": ["Доброта спасёт мир", "Wholesome момент", "Тепло на душе"],
    "relatable": ["Все мы такие", "Это про меня", "Кто узнал себя?"],
    "classic": ["Классика жанра", "Легендарный мем", "Old but gold"],
}

TAG_MAP = {
    "ProgrammerHumor": ["it", "programming"], "coding": ["it"], "linuxmemes": ["it"],
    "techsupportgore": ["it", "tech"], "pcmasterrace": ["gaming", "pc"],
    "memes": ["general"], "dankmemes": ["general"], "me_irl": ["relatable"],
    "funny": ["general"], "wholesomememes": ["wholesome"], "gaming": ["gaming"],
    "PrequelMemes": ["movies"], "marvelmemes": ["movies"],
    "lotrmemes": ["movies"], "sciencememes": ["science"],
    "space": ["science"], "surrealmemes": ["absurd"],
    "boneachingjuice": ["absurd"], "AnimalsBeingDerps": ["animals"],
    "cats": ["animals"], "dogs": ["animals"], "aww": ["animals"],
    "imgflip": ["general"],
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def gen_caption(tags):
    pool = []
    for t in tags:
        pool.extend(WITTY_TEMPLATES.get(t, WITTY_TEMPLATES["general"]))
    return random.choice(pool) if pool else "Мем дня"

def is_readable(t):
    if not t or len(t) < 3: return False
    words = t.split()
    if len(words) < 2: return False
    letters = [c for c in t if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.7: return False
    return True

log("=== Сбор свежих мемов ===")
all_memes = []

# Source 1: Meme-API (with fresh session per call to avoid hangs)
log("Meme-API...")
subs = ["memes", "dankmemes", "ProgrammerHumor", "me_irl", "gaming", "wholesomememes", "funny", "cats", "AnimalsBeingDerps", "sciencememes", "PrequelMemes", "pcmasterrace"]
success = 0
for i in range(50):
    sub = random.choice(subs)
    try:
        r = requests.get(f"https://meme-api.com/gimme/{sub}", timeout=5)
        if r.status_code == 200:
            d = r.json()
            if not d.get("nsfw") and d.get("url") and d.get("ups", 0) >= 30:
                all_memes.append({"url": d["url"], "title": d.get("title", ""), "source": "memeapi", "subreddit": d.get("subreddit", sub), "tags": [], "score": d["ups"], "fetched_at": datetime.now(timezone.utc).isoformat()})
                success += 1
    except Exception as e:
        log(f"  err: {e}")
    time.sleep(0.3)
    if success >= 30:
        break
log(f"  got {len(all_memes)}")

# Source 2: Imgflip
log("Imgflip...")
try:
    r = requests.get("https://api.imgflip.com/get_memes", timeout=8)
    if r.status_code == 200:
        data = r.json()
        if data.get("success"):
            for t in data["data"]["memes"][:30]:
                all_memes.append({"url": t["url"], "title": t["name"][:80], "source": "imgflip", "subreddit": "imgflip", "tags": [], "score": 100, "fetched_at": datetime.now(timezone.utc).isoformat()})
    log(f"  imgflip: OK")
except Exception as e:
    log(f"  imgflip: {e}")

# Dedup
seen = set()
unique = []
for m in all_memes:
    u = m["url"].split("?")[0]
    if u not in seen:
        seen.add(u)
        unique.append(m)
log(f"After dedup: {len(unique)}")

# Filter quality & readability
unique = [m for m in unique if m.get("score", 0) >= 30]
unique = [m for m in unique if is_readable(m.get("title", ""))]
log(f"After filter: {len(unique)}")

# Tags
for m in unique:
    m["tags"] = TAG_MAP.get(m.get("subreddit", ""), ["general"])

# Enrich captions with witty Russian phrases
for m in unique:
    m["title"] = gen_caption(m["tags"])

random.shuffle(unique)
unique = unique[:100]

with open(MEMES_PATH, "w", encoding="utf-8") as f:
    json.dump(unique, f, ensure_ascii=False, indent=2)

log(f"SAVED {len(unique)} memes to memes.json")
