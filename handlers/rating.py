import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database import (
    get_user,
    get_couple,
    get_rating_top,
    get_couple_rank,
    get_couple_total_earned,
)
from keyboards import kb_back
from config import get_status, get_love_status
from utils.helpers import safe_edit

logger = logging.getLogger(__name__)

router = Router()


# =========================================================
#  ХЕЛПЕР
# =========================================================

def _pair_name(a: str | None, b: str | None) -> str:
    """Формирует имя пары: 'Влад 💞 Тори'."""
    a = a or "Партнёр"
    b = b or "Партнёр"
    return f"{a} 💞 {b}"


def _format_top(rows: list[dict], my_couple_id: int | None = None) -> str:
    """Формирует текст рейтинга."""
    if not rows:
        return "🏆 <b>Рейтинг пар</b>\n\nПока пусто. Заработайте первые сердечки!"

    lines = ["🏆 <b>Рейтинг пар</b>", ""]
    lines.append("<i>Топ-100 по заработанному за всё время</i>")
    lines.append("")

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for r in rows[:100]:
        rank = r["rank"]
        medal = medals.get(rank, f"{rank}.")
        name = _pair_name(r["name_a"], r["name_b"])
        earned = r["total_earned"]

        prefix = "▶️ " if my_couple_id and r["couple_id"] == my_couple_id else ""
        lines.append(f"{prefix}{medal} {name} — <b>{earned}</b> ❤️")

    return "\n".join(lines)


# =========================================================
#  КОМАНДА /rating
# =========================================================

@router.message(Command("rating"))
async def cmd_rating(message: Message):
    if message.from_user is None:
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала /start")
        return

    top = await get_rating_top(100)
    text = _format_top(top, my_couple_id=user.get("couple_id"))

    # Своя позиция
    if user.get("couple_id"):
        rank = await get_couple_rank(user["couple_id"])
        total = await get_couple_total_earned(user["couple_id"])
        if rank is not None and rank > 100:
            text += f"\n\n📍 <b>Ваша позиция: #{rank}</b> ({total} ❤️)"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="rating:refresh")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
    ])
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "rating:refresh")
async def rating_refresh(call: CallbackQuery):
    if call.from_user is None:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    top = await get_rating_top(100)
    text = _format_top(top, my_couple_id=user.get("couple_id"))

    if user.get("couple_id"):
        rank = await get_couple_rank(user["couple_id"])
        total = await get_couple_total_earned(user["couple_id"])
        if rank is not None and rank > 100:
            text += f"\n\n📍 <b>Ваша позиция: #{rank}</b> ({total} ❤️)"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="rating:refresh")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
    ])
    await safe_edit(call, text, reply_markup=kb)
    await call.answer("Обновлено")

