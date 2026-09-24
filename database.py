import logging
import os
from typing import Any

import aiosqlite

from config import DB_PATH

logger = logging.getLogger(__name__)

# =========================================================
#  INIT + MIGRATIONS
# =========================================================

async def init_db() -> None:
    """
    1. Создаёт таблицу schema_version.
    2. Применяет миграции из migrations/.
    3. Сидит тесты и вопросы.
    """
    # 1. Таблица версий
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

    # 2. Миграции
    await run_migrations()

    # 3. Seed
    from utils.tests import seed_tests, seed_questions
    await seed_tests()
    await seed_movies_base()
    await seed_questions()


async def run_migrations() -> None:
    """Применяет неприменённые миграции из папки migrations/."""
    migrations_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "migrations",
    )

    if not os.path.isdir(migrations_dir):
        logger.error(f"❌ Папка migrations/ не найдена: {migrations_dir}")
        return

    # Текущая версия
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT MAX(version) AS v FROM schema_version"
        ) as cur:
            row = await cur.fetchone()
            current_version = row["v"] if row and row["v"] else 0

    logger.info(f"📂 Текущая версия БД: {current_version}")

    # Список миграций (сортировка по имени)
    files = sorted([
        f for f in os.listdir(migrations_dir)
        if f.endswith(".sql") and f[0].isdigit()
    ])

    applied_any = False

    for fname in files:
        try:
            version = int(fname.split("_", 1)[0])
        except (ValueError, IndexError):
            logger.warning(f"⚠️ Пропускаю миграцию с плохим именем: {fname}")
            continue

        if version <= current_version:
            continue

        fpath = os.path.join(migrations_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            sql = f.read()

        logger.info(f"🔄 Применяю миграцию {fname}")
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.executescript(sql)
                await db.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (version,),
                )
                await db.commit()
            logger.info(f"✅ Миграция {fname} применена")
            applied_any = True
        except Exception as e:
            logger.error(f"❌ Ошибка миграции {fname}: {e}")
            raise

    if not applied_any:
        logger.info("✅ Все миграции уже применены")
# =========================================================
#  LOW-LEVEL HELPERS
# =========================================================

async def _fetchone(query: str, params: tuple = ()) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row is not None else None


async def _fetchall(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def _execute(query: str, params: tuple = ()) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(query, params)
        await db.commit()
        rid = cur.lastrowid
        if rid is None:
            raise RuntimeError(f"lastrowid is None for: {query}")
        return rid


# =========================================================
#  USERS
# =========================================================

async def get_user(telegram_id: int) -> dict[str, Any] | None:
    return await _fetchone("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))


async def create_user(telegram_id: int, name: str | None = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, name) VALUES (?, ?)",
            (telegram_id, name),
        )
        await db.commit()


async def update_user(telegram_id: int, **fields: Any) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    values: list[Any] = list(fields.values()) + [telegram_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {keys} WHERE telegram_id=?", tuple(values))
        await db.commit()


# =========================================================
#  COUPLES
# =========================================================

async def create_couple(user_a_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO couples (user_a_id, status) VALUES (?, 'pending')",
            (user_a_id,),
        )
        couple_id = cur.lastrowid
        if couple_id is None:
            raise RuntimeError("Не удалось создать пару")
        await db.execute(
            "UPDATE users SET couple_id=? WHERE telegram_id=?",
            (couple_id, user_a_id),
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (couple_id) VALUES (?)",
            (couple_id,),
        )
        await db.commit()
        return couple_id


async def get_couple(couple_id: int) -> dict[str, Any] | None:
    return await _fetchone("SELECT * FROM couples WHERE id=?", (couple_id,))


async def join_couple(couple_id: int, user_b_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE couples SET user_b_id=?, status='active' WHERE id=?",
            (user_b_id, couple_id),
        )
        await db.execute(
            "UPDATE users SET couple_id=? WHERE telegram_id=?",
            (couple_id, user_b_id),
        )
        await db.commit()
    # Синхронизируем общий — вдруг у кого-то уже были сердечки
    await sync_common_balance(couple_id)


async def get_partner(couple_id: int, telegram_id: int) -> dict[str, Any] | None:
    return await _fetchone(
        "SELECT * FROM users WHERE couple_id=? AND telegram_id!=?",
        (couple_id, telegram_id),
    )


# =========================================================
#  BALANCE (с автосинхронизацией common)
# =========================================================

async def sync_common_balance(couple_id: int) -> None:
    """Пересчитывает common_balance = сумма личных балансов пары."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COALESCE(SUM(hearts_balance), 0) AS total "
            "FROM users WHERE couple_id=?",
            (couple_id,),
        ) as cur:
            row = await cur.fetchone()
        total = row["total"] if row else 0

        await db.execute(
            "UPDATE couples SET common_balance=? WHERE id=?",
            (total, couple_id),
        )
        await db.commit()


async def add_hearts(telegram_id: int, amount: int) -> None:
    """Начисляет личные сердечки, обновляет общий баланс и total_earned."""
    couple_id: int | None = None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT couple_id FROM users WHERE telegram_id=?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is not None:
            couple_id = row["couple_id"]

        # Начисляем и в hearts_balance, и в total_earned (если amount > 0)
        if amount > 0:
            await db.execute(
                "UPDATE users SET "
                "hearts_balance = hearts_balance + ?, "
                "total_earned = total_earned + ? "
                "WHERE telegram_id=?",
                (amount, amount, telegram_id),
            )
        else:
            # Отрицательный amount (сжигание) — только hearts_balance
            await db.execute(
                "UPDATE users SET hearts_balance = hearts_balance + ? "
                "WHERE telegram_id=?",
                (amount, telegram_id),
            )
        await db.commit()

    if couple_id is not None:
        await sync_common_balance(couple_id)

async def spend_hearts(telegram_id: int, amount: int) -> bool:
    """Списывает личные сердечки. Возвращает True при успехе."""
    couple_id: int | None = None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT hearts_balance, couple_id FROM users WHERE telegram_id=?",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()

        if row is None:
            return False
        if row["hearts_balance"] < amount:
            return False

        couple_id = row["couple_id"]

        await db.execute(
            "UPDATE users SET hearts_balance = hearts_balance - ? WHERE telegram_id=?",
            (amount, telegram_id),
        )
        await db.commit()

    if couple_id is not None:
        await sync_common_balance(couple_id)
    return True


async def add_common_hearts(couple_id: int, amount: int) -> None:
    """Начисляет amount на общий баланс — по половине каждому партнёру."""
    half = amount // 2
    rest = amount - half

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT telegram_id FROM users WHERE couple_id=? ORDER BY telegram_id",
            (couple_id,),
        ) as cur:
            raw = await cur.fetchall()
            users: list[dict[str, Any]] = [dict(r) for r in raw]

    if len(users) < 2:
        return

    await add_hearts(users[0]["telegram_id"], half)
    await add_hearts(users[1]["telegram_id"], rest)


async def spend_common_hearts(couple_id: int, amount: int) -> bool:
    """Сжигает amount с общего баланса — по половине с каждого партнёра."""
    half = amount // 2
    rest = amount - half

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT telegram_id, hearts_balance FROM users "
            "WHERE couple_id=? ORDER BY telegram_id",
            (couple_id,),
        ) as cur:
            raw = await cur.fetchall()
            users: list[dict[str, Any]] = [dict(r) for r in raw]

        if len(users) < 2:
            return False

        u1 = users[0]
        u2 = users[1]

        if u1["hearts_balance"] < half or u2["hearts_balance"] < rest:
            return False

        await db.execute(
            "UPDATE users SET hearts_balance = hearts_balance - ? WHERE telegram_id=?",
            (half, u1["telegram_id"]),
        )
        await db.execute(
            "UPDATE users SET hearts_balance = hearts_balance - ? WHERE telegram_id=?",
            (rest, u2["telegram_id"]),
        )
        await db.commit()

    await sync_common_balance(couple_id)
    return True


async def burn_hearts(telegram_id: int, amount: int) -> bool:
    """Псевдоним spend_hearts — сжигание сердечек."""
    return await spend_hearts(telegram_id, amount)


# =========================================================
#  MOVIES
# =========================================================

async def add_movie(couple_id: int, title: str, added_by: int) -> int:
    return await _execute(
        "INSERT INTO movies (couple_id, title, added_by, status) "
        "VALUES (?, ?, ?, 'pending')",
        (couple_id, title, added_by),
    )


async def confirm_movie(movie_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE movies SET status='in_list' WHERE id=?", (movie_id,))
        await db.commit()


async def delete_movie(movie_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM movies WHERE id=?", (movie_id,))
        await db.commit()


async def get_movies(couple_id: int) -> list[dict[str, Any]]:
    return await _fetchall(
        "SELECT * FROM movies WHERE couple_id=? AND status='in_list' ORDER BY id DESC",
        (couple_id,),
    )


async def get_movie(movie_id: int) -> dict[str, Any] | None:
    return await _fetchone("SELECT * FROM movies WHERE id=?", (movie_id,))


# =========================================================
#  TZ
# =========================================================

async def get_couple_tz_str(couple_id: int) -> str:
    row = await _fetchone(
        "SELECT tz FROM users WHERE couple_id=? AND tz IS NOT NULL LIMIT 1",
        (couple_id,),
    )
    if row is None or not row.get("tz"):
        return "Europe/Moscow"
    return row["tz"]

# =========================================================
#  TOTAL EARNED
# =========================================================

async def get_couple_total_earned(couple_id: int) -> int:
    """Сумма total_earned обоих партнёров."""
    row = await _fetchone(
        "SELECT COALESCE(SUM(total_earned), 0) AS total "
        "FROM users WHERE couple_id=?",
        (couple_id,),
    )
    return row["total"] if row else 0

# =========================================================
#  RATING
# =========================================================

async def get_rating_top(limit: int = 100) -> list[dict[str, Any]]:
    """
    Топ пар по накопленному за всё время (total_earned).
    Возвращает список: [{couple_id, name_a, name_b, total_earned, rank}]
    """
    query = """
        SELECT
            c.id AS couple_id,
            ua.name AS name_a,
            ub.name AS name_b,
            (COALESCE(ua.total_earned, 0) + COALESCE(ub.total_earned, 0)) AS total_earned
        FROM couples c
        LEFT JOIN users ua ON ua.telegram_id = c.user_a_id
        LEFT JOIN users ub ON ub.telegram_id = c.user_b_id
        WHERE c.status = 'active'
        ORDER BY total_earned DESC
        LIMIT ?
    """
    rows = await _fetchall(query, (limit,))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


async def get_couple_rank(couple_id: int) -> int | None:
    """Возвращает позицию пары в рейтинге (1-based) или None."""
    row = await _fetchone(
        """
        SELECT COUNT(*) + 1 AS rank
        FROM couples c1
        WHERE c1.status = 'active'
        AND (
            SELECT COALESCE(SUM(total_earned), 0)
            FROM users WHERE couple_id = c1.id
        ) > (
            SELECT COALESCE(SUM(total_earned), 0)
            FROM users WHERE couple_id = ?
        )
        """,
        (couple_id,),
    )
    return row["rank"] if row else None

# =========================================================
#  MOVIES BASE (случайный фильм)
# =========================================================

async def seed_movies_base() -> None:
    """Заполняет movies_base из utils.movies_data при первом запуске."""
    from utils.movies_data import MOVIES

    existing = await _fetchall("SELECT id FROM movies_base LIMIT 1")
    if existing:
        return

    for m in MOVIES:
        await _execute(
            "INSERT INTO movies_base "
            "(title, year, genre, duration, description, rating) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                m.get("title"),
                m.get("year"),
                m.get("genre"),
                m.get("duration"),
                m.get("description"),
                m.get("rating", 0),
            ),
        )
    logger.info(f"movies_base seeded: {len(MOVIES)} фильмов")


async def get_random_movie(exclude_titles: list[str] | None = None) -> dict | None:
    """Случайный фильм из базы. Исключает те, что уже в списке пары."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if exclude_titles:
            placeholders = ",".join("?" * len(exclude_titles))
            query = (
                f"SELECT * FROM movies_base "
                f"WHERE title NOT IN ({placeholders}) "
                f"ORDER BY RANDOM() LIMIT 1"
            )
            params = tuple(exclude_titles)
        else:
            query = "SELECT * FROM movies_base ORDER BY RANDOM() LIMIT 1"
            params = ()
        async with db.execute(query, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# =========================================================
#  MOVIE LIMITS (случайный фильм)
# =========================================================

async def get_movie_limit(user_id: int, date_str: str) -> int:
    """Сколько раз юзер сегодня нажимал «Случайный фильм»."""
    row = await _fetchone(
        "SELECT count FROM movie_limits WHERE user_id=? AND date=?",
        (user_id, date_str),
    )
    return row["count"] if row else 0


async def inc_movie_limit(user_id: int, date_str: str) -> None:
    """Увеличивает счётчик нажатий на 1."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO movie_limits (user_id, date, count) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, date) DO UPDATE SET count=count+1",
            (user_id, date_str),
        )
        await db.commit()


async def get_user_movie_limit(user_id: int) -> int:
    """
    Возвращает максимальный лимит для юзера.
    Free = 3, Premium = 10.
    """
    from config import MOVIE_RANDOM_LIMIT_FREE, MOVIE_RANDOM_LIMIT_PREMIUM
    user = await get_user(user_id)
    if user is None:
        return MOVIE_RANDOM_LIMIT_FREE

    is_premium = user.get("is_premium", 0)
    # Проверка premium_until (если есть)
    premium_until = user.get("premium_until")
    if is_premium and premium_until:
        # Можно проверить дату — если не истёк
        pass  # пока пропускаем

    if is_premium:
        return MOVIE_RANDOM_LIMIT_PREMIUM
    return MOVIE_RANDOM_LIMIT_FREE