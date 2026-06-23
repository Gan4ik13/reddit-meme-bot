#!/usr/bin/env python3
import re, json, requests, time, random, sys
from pathlib import Path
from datetime import datetime, timezone

MEMES_PATH = Path(__file__).parent / "memes.json"

WITTY_TEMPLATES = {
    "it": [
        "Когда код работает с первого раза", "IT-шникам посвящается",
        "Дебаггинг — моя жизнь", "Stack Overflow в шоке",
        "Компилируется? Не, не слышал", "Рефакторинг пошёл не по плану",
        "Git push — force of nature", "Программисты поймут",
        "Это не баг, это фича", "Джуниор детектед",
        "Прод в пятницу вечером", "Деплой без кофе не обходится",
        "Когда нашёл баг 3-летней давности", "Code review be like",
        "Сеньоры в шоке", "Микросервисы на коленке",
        "Документация? Не, не слышали", "Тестирование в продакшне",
        "Hotfix в прод без ревью", "Тёмная тема спасёт глаза",
        "Когда линупс обновился и всё сломал", "Терминал вместо психолога",
        "Docker clean up — удалил всё и молишься",
    ],
    "gaming": [
        "GG WP", "Лаги? Не, не слышал", "Когда босс на 1% хп",
        "Геймерский момент", "Just one more turn", "Rage quit incoming",
        "Рандом в чистую", "Skill issue", "Хитбоксы подвели",
        "Пауза для перекуса", "Нерф имбу", "Баланс? Разработчики?",
        "Фармим лут", "Тиммейты подвели", "Когда сервер упал в рейде",
        "Читер? Или скилл?", "Aim тренировки не прошли даром",
        "Лагнуло — не считается", "Билд собран, можно в рейд",
    ],
    "movies": [
        "Киноманская классика", "Сценаристы в шоке",
        "Оскар за лучший мем", "Сюжетный поворот века",
        "Спилберг одобряет", "Монтаж на высоте",
        "Озвучка — огонь", "Лучше, чем сиквел",
        "Кино на вечер", "Почему я не пошёл в киношколу",
        "Гарри Поттер отдыхает", "Marvel нервно курит",
    ],
    "science": [
        "Наука — это весело", "Эйнштейн одобряет", "Big brain time",
        "Мозг кипит", "Эксперимент удался", "Теория подтверждена",
        "Профессор в восторге", "Законы физики нарушены",
        "Когда наука побеждает", "Диссертация дня",
        "Гравитация? Не, не слышал",
    ],
    "animals": [
        "Животный мем", "Пушистик дня", "Милота атакует",
        "Хвостатый позитив", "Усы, лапы и хвост",
        "Зверский релакс", "Лапки на месте",
        "Мохнатый антидепрессант", "Зоопарк в телефоне",
        "Умиление 100 уровня", "Кто тут хороший мальчик",
    ],
    "general": [
        "Релатбл контент", "Жиза", "Понедельник начинается",
        "Это я в 3 часа ночи", "Свежачок", "Каждый раз одно и то же",
        "Настроение на сегодня", "Утро начинается не с кофе",
        "Ситуация на миллион", "Будни идиота",
        "Муд на сегодня", "Атмосфера заряжена",
        "Типичный день", "Почувствуй себя гением",
        "Реальность: включила", "Когда осознал",
        "Состояние потока", "Проснулся и сразу",
        "Вечер в хату", "План выполнен на 100%",
        "Ничто не предвещало", "История из жизни",
        "Будни фрилансера", "Рабочиебудни",
        "Уровень комфорта зашкаливает", "Friday vibes",
    ],
    "absurd": [
        "Абсурд чистой воды", "Что я только что увидел",
        "WTF level: over 9000", "Мой мозг: error",
        "Сюр какой-то", "Реальность перегруз",
        "Дичь дня", "Как это вообще существует",
        "Потрачено", "Логика покинула чат",
    ],
    "life": [
        "Жизненно", "Взросление be like", "Офисная жиза",
        "Взрослая жизнь наступила", "Кредитка плачет",
        "Ипотека или Париж", "Зарплата пришла и ушла",
        "Счастье в мелочах", "Бытовуха заела",
        "Вечные вопросы бытия", "Старость не радость",
    ],
    "wholesome": [
        "Доброта спасёт мир", "Wholesome момент", "Тепло на душе",
        "Лучшее что я видел сегодня", "Сердце растаяло",
        "Люди хорошие", "Вера в человечество восстановлена",
        "Милота дня", "Позитивчик",
    ],
    "relatable": [
        "Все мы такие", "Это про меня", "Кто узнал себя?",
        "Моё фото", "Я в реальной жизни",
        "Личный опыт", "История повторяется",
        "Как же это знакомо", "Абсолютный релейт",
    ],
    "classic": [
        "Классика жанра", "Легендарный мем", "Old but gold",
        "Проверено временем", "Мем из прошлого",
        "Вековая классика", "Наше всё",
        "Золотая коллекция",
    ],
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
