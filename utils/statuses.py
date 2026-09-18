"""Проверка и уведомления о смене статуса."""
import logging
from datetime import datetime, date

from database import (
    get_couple, _execute, _fetchone, _fetchall,
)
from config import get_status, get_love_status

logger = logging.getLogger(__name__)


# =========================================================
#  СТАТУС «ВМЕСТЕ N ДНЕЙ»
# =========================================================

async def check_love_status(bot, couple_id: int, days: int) -> None:
    """Проверяет, изменился ли статус «Вместе» — и уведомляет."""
    couple = await get_couple(couple_id)
    if couple is None:
        return

    new_status = get_love_status(days)
    old_status = couple.get("last_love_status")

    if old_status == new_status:
        return  # Ничего не изменилось

    # Обновляем в БД
    await _execute(
        "UPDATE couples SET last_love_status=? WHERE id=?",
        (new_status, couple_id),
    )

    # Если первый раз — не уведомляем (только сохраняем)
    if old_status is None:
        return

    # Уведомляем обоих
    users = await _fetchall(
        "SELECT telegram_id, name FROM users WHERE couple_id=? ORDER BY id",
        (couple_id,),
    )
    for u in users:
        try:
            await bot.send_message(
                u["telegram_id"],
                f"💕 <b>Новый статус!</b>\n\n"
                f"Вы вместе <b>{days} дней</b>.\n"
                f"Теперь ваш статус — <b>{new_status}</b>.\n\n"
                f"Поздравляем! ❤️",
            )
        except Exception as e:
            logger.warning(f"status notify failed: {e}")


# =========================================================
#  СТАТУС ПО СЕРДЕЧКАМ (total_earned)
# =========================================================

async def check_hearts_status(bot, couple_id: int) -> None:
    """
    Проверяет, изменился ли статус по сердечкам.
    Уведомляет только раз в день на пару.
    """
    couple = await get_couple(couple_id)
    if couple is None:
        return

    # Считаем total_earned пары
    row = await _fetchone(
        "SELECT COALESCE(SUM(total_earned), 0) AS total "
        "FROM users WHERE couple_id=?",
        (couple_id,),
    )
    total = row["total"] if row else 0

    new_status = get_status(total)
    old_status = couple.get("last_hearts_status")
    last_check = couple.get("last_status_check")

    if old_status == new_status:
        return

    # Обновляем
    today = date.today().isoformat()
    await _execute(
        "UPDATE couples SET last_hearts_status=?, last_status_check=? WHERE id=?",
        (new_status, today, couple_id),
    )

    # Первый раз — не уведомляем
    if old_status is None:
        return

    # Анти-спам: не чаще раза в день
    if last_check == today:
        return

    # Уведомляем
    users = await _fetchall(
        "SELECT telegram_id, name FROM users WHERE couple_id=? ORDER BY id",
        (couple_id,),
    )
    for u in users:
        try:
            await bot.send_message(
                u["telegram_id"],
                f"🏆 <b>Новый статус!</b>\n\n"
                f"Вы заработали <b>{total} ❤️</b> вместе.\n"
                f"Теперь ваш статус — <b>{new_status}</b>.\n\n"
                f"Так держать! ❤️",
            )
        except Exception as e:
            logger.warning(f"hearts status notify failed: {e}")