import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN") or ""
DB_PATH: str = os.getenv("DB_PATH", "bot.db")
TZ: str = os.getenv("TZ", "Europe/Moscow")

# ---- Пути к ассетам ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
GIFTS_DIR = os.path.join(ASSETS_DIR, "gifts")
AVATARS_DIR = os.path.join(ASSETS_DIR, "avatars")

# ---- Экономика ----
HEARTS_QUESTION_MATCH = 5
HEARTS_QUESTION_MISS = 2
HEARTS_MOVIE_RATED = 10
HEARTS_FRIDAY_DONE = 30
HEARTS_REFERRAL = 300

CANCEL_WISH_COST = 300
REPLACE_WISH_COST = 100
MOVIE_CHOICE_COST = 300
SURPRISE_COST = 500
COMPLIMENT_COST = 10

# ---- Главный статус (от total_earned) ----
STATUSES = [
    (0, "🌱 Первопроходцы"),
    (100, "🌙 Мечтатели"),
    (500, "🥈 Серебряные"),
    (1000, "🥇 Золотые"),
    (3000, "💎 Бриллиантовые"),
    (10000, "👑 Королевские"),
]


def get_status(total_earned: int) -> str:
    status = STATUSES[0][1]
    for threshold, name in STATUSES:
        if total_earned >= threshold:
            status = name
    return status


# ---- Статус «Вместе N дней» ----
LOVE_STATUSES = [
    (0, "🌸 Первые искры"),
    (31, "💗 Пара"),
    (91, "💕 Влюблённые"),
    (181, "💞 Родные"),
    (1096, "💝 Навсегда"),
    (3651, "👑 Легендарные"),
]


def get_love_status(days: int) -> str:
    status = LOVE_STATUSES[0][1]
    for threshold, name in LOVE_STATUSES:
        if days >= threshold:
            status = name
    return status

# ---- Пакеты сердечек ----
PACKAGES = [
    {"hearts": 300,  "price": 1, "bonus_percent": 10},
    {"hearts": 1000, "price": 2, "bonus_percent": 20},
    {"hearts": 3000, "price": 3, "bonus_percent": 30},
]

FIRST_PURCHASE_BONUS = 30   # +30% на первую покупку


def get_package(hearts: int) -> dict | None:
    for p in PACKAGES:
        if p["hearts"] == hearts:
            return p
    return None


def calc_bonus(hearts: int, is_first: bool) -> tuple[int, int]:
    """
    Возвращает (bonus_percent, total_hearts).
    Первая покупка — 30%, обычная — прогрессия по пакету.
    НЕ суммируются.
    """
    pkg = get_package(hearts)
    if pkg is None:
        return 0, hearts

    bonus_percent = FIRST_PURCHASE_BONUS if is_first else pkg["bonus_percent"]
    total = int(hearts * (1 + bonus_percent / 100))
    return bonus_percent, total

# ---- Ю-Касcа ----
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "")
YOOKASSA_WEBHOOK_URL = os.getenv("YOOKASSA_WEBHOOK_URL", "")

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8000"))