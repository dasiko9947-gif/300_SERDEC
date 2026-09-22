"""Хелперы для админки: логи, баны, статистика, уведомления."""
import logging

from database import _execute, _fetchone, _fetchall
from config import ADMIN_ID

logger = logging.getLogger(__name__)


# =========================================================
#  ПРОВЕРКА АДМИНА
# =========================================================

def is_admin(user_id: int) -> bool:
    """Проверяет, что user_id — админ."""
    return user_id == ADMIN_ID


# =========================================================
#  ЛОГИ
# =========================================================

async def add_log(
    type: str,
    description: str,
    couple_id: int | None = None,
    user_id: int | None = None,
    admin_id: int | None = None,
) -> None:
    """Пишет лог."""
    try:
        await _execute(
            "INSERT INTO logs (type, couple_id, user_id, admin_id, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (type, couple_id, user_id, admin_id, description[:500]),
        )
    except Exception as e:
        logger.warning(f"Не записался лог: {e}")


# =========================================================
#  БАНЫ
# =========================================================

async def is_banned(couple_id: int | None = None, user_id: int | None = None) -> bool:
    """Проверяет активный бан."""
    if couple_id is not None:
        row = await _fetchone(
            "SELECT id FROM bans WHERE couple_id=? AND active=1 LIMIT 1",
            (couple_id,),
        )
        if row:
            return True
    if user_id is not None:
        row = await _fetchone(
            "SELECT id FROM bans WHERE user_id=? AND active=1 LIMIT 1",
            (user_id,),
        )
        if row:
            return True
    return False


async def ban_couple(couple_id: int, reason: str, admin_id: int) -> None:
    await _execute(
        "INSERT INTO bans (couple_id, reason, banned_by, active) "
        "VALUES (?, ?, ?, 1)",
        (couple_id, reason, admin_id),
    )
    await add_log(
        "ban",
        f"Забанена пара #{couple_id}: {reason}",
        couple_id=couple_id,
        admin_id=admin_id,
    )


async def ban_user(user_id: int, reason: str, admin_id: int) -> None:
    await _execute(
        "INSERT INTO bans (user_id, reason, banned_by, active) "
        "VALUES (?, ?, ?, 1)",
        (user_id, reason, admin_id),
    )
    await add_log(
        "ban",
        f"Забанен пользователь #{user_id}: {reason}",
        user_id=user_id,
        admin_id=admin_id,
    )


# =========================================================
#  СТАТИСТИКА
# =========================================================

async def get_stats() -> dict:
    """Собирает всю статистику для /admin → 📊."""
    stats: dict = {}

    row = await _fetchone("SELECT COUNT(*) AS c FROM couples")
    stats["total_couples"] = row["c"] if row else 0

    row = await _fetchone(
        "SELECT COUNT(*) AS c FROM couples WHERE status='active'"
    )
    stats["active_couples"] = row["c"] if row else 0

    row = await _fetchone(
        "SELECT COUNT(*) AS c FROM couples WHERE DATE(created_at) = DATE('now')"
    )
    stats["new_today"] = row["c"] if row else 0

    row = await _fetchone(
        "SELECT COUNT(*) AS c FROM couples "
        "WHERE created_at >= datetime('now', '-7 days')"
    )
    stats["new_week"] = row["c"] if row else 0

    row = await _fetchone(
        "SELECT COUNT(*) AS c FROM couples "
        "WHERE created_at >= datetime('now', '-30 days')"
    )
    stats["new_month"] = row["c"] if row else 0

    row = await _fetchone(
        "SELECT COALESCE(SUM(hearts_balance), 0) AS total FROM users"
    )
    stats["hearts_total"] = row["total"] if row else 0

    row = await _fetchone(
        "SELECT COALESCE(SUM(price), 0) AS total FROM purchases "
        "WHERE created_at >= datetime('now', '-30 days')"
    )
    stats["bought_month"] = row["total"] if row else 0

    row = await _fetchone("SELECT COUNT(*) AS c FROM gifts")
    stats["gifts"] = row["c"] if row else 0

    row = await _fetchone(
        "SELECT COUNT(*) AS c FROM movies WHERE status='in_list'"
    )
    stats["movies"] = row["c"] if row else 0

    row = await _fetchone(
        "SELECT COUNT(*) AS c FROM friday_events WHERE status='done'"
    )
    stats["fridays"] = row["c"] if row else 0

    return stats


# =========================================================
#  УВЕДОМЛЕНИЯ АДМИНУ
# =========================================================

async def notify_admin(bot, text: str) -> None:
    """Отправляет уведомление админу. Молча игнорирует ошибки."""
    if ADMIN_ID == 0 or bot is None:
        return
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        logger.warning(f"notify_admin failed: {e}")