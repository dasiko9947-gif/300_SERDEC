"""Единый модуль наград, ачивок и начислений."""
import logging

from database import _fetchall, _execute, add_hearts

logger = logging.getLogger(__name__)


# =========================================================
#  Тексты ачивок
# =========================================================

ACHIEVEMENT_TITLES = {
    "first_movie": "🎬 Первый фильм",
    "movies_10": "🎬 10 фильмов",
    "movies_30": "🎬 30 фильмов",
    "movies_100": "🎬 100 фильмов",
    "movies_300": "🎬 300 фильмов",
    "first_friday": "🖤 Первая Пятница",
    "friday_streak_4": "🖤 4 Пятницы подряд",
    "friday_streak_15": "🖤 15 Пятниц подряд",
    "friday_streak_30": "🖤 30 Пятниц подряд",
    "friday_streak_100": "🖤 100 Пятниц подряд",
    "hearts_collector": "❤️ 3 сердца",
    "roses_collector": "🌹 3 розы",
    "bears_collector": "🧸 3 мишки",
    "collection_master": "🎨 9 подарков",
    "couple_avatar": "💞 Пара",
}


def title_of(code: str) -> str:
    return ACHIEVEMENT_TITLES.get(code, code)


# =========================================================
#  Награды за действия
# =========================================================

async def reward_movie_rated(user_a_id: int, user_b_id: int) -> None:
    """+10 ❤️ каждому за оценку фильма."""
    await add_hearts(user_a_id, 10)
    await add_hearts(user_b_id, 10)


async def reward_friday_done(user_a_id: int, user_b_id: int) -> None:
    """+30 ❤️ обоим за выполнение Пятницы."""
    await add_hearts(user_a_id, 30)
    await add_hearts(user_b_id, 30)


# =========================================================
#  Базовые операции с ачивками
# =========================================================

async def has_achievement(couple_id: int, code: str) -> bool:
    rows = await _fetchall(
        "SELECT 1 FROM achievements WHERE couple_id=? AND code=? LIMIT 1",
        (couple_id, code),
    )
    return bool(rows)


async def unlock_achievement(couple_id: int, code: str) -> bool:
    """Выдаёт ачивку, если её ещё нет. True — если выдали впервые."""
    if await has_achievement(couple_id, code):
        return False
    await _execute(
        "INSERT INTO achievements (couple_id, code) VALUES (?, ?)",
        (couple_id, code),
    )
    logger.info(f"achievement unlocked: {code} for couple {couple_id}")
    return True


async def get_unlocked(couple_id: int) -> list[str]:
    rows = await _fetchall(
        "SELECT code FROM achievements WHERE couple_id=?", (couple_id,)
    )
    return [r["code"] for r in rows]


# =========================================================
#  Проверки после действий
# =========================================================
async def check_movie_milestones(
    couple_id: int, user_a_id: int, user_b_id: int
) -> list[str]:
    """
    Считает ТОЛЬКО просмотренные фильмы (оба поставили оценку).
    """
    movies = await _fetchall(
        "SELECT id FROM movies WHERE couple_id=? "
        "AND rating_a IS NOT NULL AND rating_b IS NOT NULL",
        (couple_id,),
    )
    total = len(movies)
    unlocked: list[str] = []

    # Первый просмотренный фильм — без награды
    if total >= 1:
        if await unlock_achievement(couple_id, "first_movie"):
            unlocked.append("🎬 <b>Первый фильм просмотрен!</b>\nТак держать ❤️")

    # 10 фильмов — +100
    if total >= 10 and await unlock_achievement(couple_id, "movies_10"):
        await add_hearts(user_a_id, 100)
        await add_hearts(user_b_id, 100)
        unlocked.append("🎬 <b>10 фильмов вместе!</b>\n+100 ❤️ каждому")

    # 30 фильмов — +200
    if total >= 30 and await unlock_achievement(couple_id, "movies_30"):
        await add_hearts(user_a_id, 200)
        await add_hearts(user_b_id, 200)
        unlocked.append("🎬 <b>30 фильмов вместе!</b>\n+200 ❤️ каждому")

    # 100 фильмов — +300
    if total >= 100 and await unlock_achievement(couple_id, "movies_100"):
        await add_hearts(user_a_id, 300)
        await add_hearts(user_b_id, 300)
        unlocked.append("🎬 <b>100 фильмов вместе!</b>\n+300 ❤️ каждому")

    # 300 фильмов — +1000
    if total >= 300 and await unlock_achievement(couple_id, "movies_300"):
        await add_hearts(user_a_id, 1000)
        await add_hearts(user_b_id, 1000)
        unlocked.append("🎬 <b>300 фильмов вместе!</b>\n+1000 ❤️ каждому")

    return unlocked


async def check_friday_milestones(
    couple_id: int, user_a_id: int, user_b_id: int
) -> list[str]:
    """Проверяет ачивки по Пятнице."""
    events = await _fetchall(
        "SELECT status FROM friday_events WHERE couple_id=? "
        "ORDER BY created_at DESC LIMIT 200",
        (couple_id,),
    )
    if not events:
        return []

    # Подряд done от свежих
    streak = 0
    for e in events:
        if e["status"] == "done":
            streak += 1
        else:
            break

    unlocked: list[str] = []

    # Первая Пятница — без награды
    done_count = sum(1 for e in events if e["status"] == "done")
    if done_count >= 1:
        if await unlock_achievement(couple_id, "first_friday"):
            unlocked.append("🖤 <b>Первая Пятница!</b>\nВы это сделали ❤️")

    # 4 подряд — +100
    if streak >= 4 and await unlock_achievement(couple_id, "friday_streak_4"):
        await add_hearts(user_a_id, 100)
        await add_hearts(user_b_id, 100)
        unlocked.append("🖤 <b>4 Пятницы подряд!</b>\n+100 ❤️ каждому")

    # 15 подряд — +200
    if streak >= 15 and await unlock_achievement(couple_id, "friday_streak_15"):
        await add_hearts(user_a_id, 200)
        await add_hearts(user_b_id, 200)
        unlocked.append("🖤 <b>15 Пятниц подряд!</b>\n+200 ❤️ каждому")

    # 30 подряд — +300
    if streak >= 30 and await unlock_achievement(couple_id, "friday_streak_30"):
        await add_hearts(user_a_id, 300)
        await add_hearts(user_b_id, 300)
        unlocked.append("🖤 <b>30 Пятниц подряд!</b>\n+300 ❤️ каждому")

    # 100 подряд — +1000
    if streak >= 100 and await unlock_achievement(couple_id, "friday_streak_100"):
        await add_hearts(user_a_id, 1000)
        await add_hearts(user_b_id, 1000)
        unlocked.append("🖤 <b>100 Пятниц подряд!</b>\n+1000 ❤️ каждому")

    return unlocked


async def check_gift_collection(
    couple_id: int, user_a_id: int, user_b_id: int
) -> list[str]:
    """Проверяет ачивки по коллекции подарков."""
    rows = await _fetchall(
        "SELECT gift_key FROM gifts WHERE couple_id=?", (couple_id,)
    )
    keys = {r["gift_key"] for r in rows}
    unlocked: list[str] = []

    hearts_keys = {"heart_wine", "heart_black", "heart_white"}
    roses_keys = {"rose_red", "rose_white", "rose_pink"}
    bears_keys = {"bear_brown", "bear_pink", "bear_white"}
    base_keys = hearts_keys | roses_keys | bears_keys

    # 3 сердца — без награды
    if hearts_keys.issubset(keys):
        if await unlock_achievement(couple_id, "hearts_collector"):
            unlocked.append("❤️ <b>3 сердца собраны!</b>")

    # 3 розы — без награды
    if roses_keys.issubset(keys):
        if await unlock_achievement(couple_id, "roses_collector"):
            unlocked.append("🌹 <b>3 розы собраны!</b>")

    # 3 мишки — без награды
    if bears_keys.issubset(keys):
        if await unlock_achievement(couple_id, "bears_collector"):
            unlocked.append("🧸 <b>3 мишки собраны!</b>")

    # 9 подарков — +100
    if base_keys.issubset(keys):
        if await unlock_achievement(couple_id, "collection_master"):
            await add_hearts(user_a_id, 100)
            await add_hearts(user_b_id, 100)
            unlocked.append("🎨 <b>Все 9 подарков собраны!</b>\n+100 ❤️ каждому")

    return unlocked