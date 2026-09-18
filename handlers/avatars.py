import os
import logging

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from database import update_user
from database import (
    get_user,
    get_couple,
    get_partner,
    spend_hearts,
    _execute,
)
from keyboards import kb_back
from config import AVATARS_DIR, DB_PATH
from utils.helpers import (
    safe_edit,
    safe_edit_photo,
    cb_parts,
    send_to,
)
from utils.achievements import add_hearts

import aiosqlite

logger = logging.getLogger(__name__)

router = Router()


# =========================================================
#  КАТАЛОГ АВАТАРОВ
#  key: (название, цена, описание, картинка, пол, звание)
# =========================================================

AVATARS = {
    "spartan": (
        "🛡 Спартанец", 1000,
        "Бронзовый шлем, красный плащ, копьё.\nСимвол силы и верности.",
        os.path.join(AVATARS_DIR, "spartan.png"),
        "m",
        "Спартанец",
    ),
    "amazon": (
        "🏹 Амазонка", 1000,
        "Кожаная броня, длинная коса, лук за спиной.\nСимвол красоты и силы.",
        os.path.join(AVATARS_DIR, "amazon.png"),
        "f",
        "Амазонка",
    ),
    # НОВОЕ: общий аватар «Пара»
    "couple": (
        "💞 Пара", 0,
        "Ваш общий аватар — символ вашей любви.",
        os.path.join(AVATARS_DIR, "couple.png"),
        "any",
        "Пара",
    ),
}

# =========================================================
#  HELPERS
# =========================================================

async def get_my_avatar(telegram_id: int) -> str | None:
    """Возвращает ключ аватара или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT avatar_key FROM avatars WHERE telegram_id=? "
            "ORDER BY id DESC LIMIT 1",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
            return row["avatar_key"] if row else None


def display_name(base_name: str, avatar_key: str | None) -> str:
    """
    Влад + spartan → «Влад-Спартанец»
    Тори + amazon  → «Тори-Амазонка»
    """
    if not avatar_key or avatar_key not in AVATARS:
        return base_name
    title = AVATARS[avatar_key][5]
    return f"{base_name}-{title}"


# =========================================================
#  КАРТОЧКА ПОКУПКИ (открывается из профиля)
#  Показывается ВСЕГДА — даже если не хватает сердечек
# =========================================================

@router.callback_query(F.data == "avatar:buy")
async def avatar_buy_menu(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    # Уже есть?
    existing = await get_my_avatar(call.from_user.id)
    if existing:
        await call.answer("У тебя уже есть аватар", show_alert=True)
        return

    gender = user.get("gender") or "m"
    key = "spartan" if gender == "m" else "amazon"
    name, price, desc, image_path, _g, _title = AVATARS[key]

    # Красивая карточка: картинка + что даёт + цена
    caption = (
        f"<b>{name}</b>\n\n"
        f"{desc}\n\n"
        f"<b>Что даёт:</b>\n"
        f"• Аватар в профиле\n"
        f"• Звание: <b>{user['name']}-{_title}</b>\n"
        f"• Если у обоих есть аватары — открывается «Парный аватар»\n"
        f"  и <b>+300 ❤️</b> каждому\n\n"
        f"💰 Цена: <b>{price} ❤️</b>\n"
        f"У тебя: {user['hearts_balance']} ❤️"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Купить за {price} ❤️",
            callback_data="avatar:confirm",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:profile")],
    ])

    if os.path.exists(image_path):
        await safe_edit_photo(call, image_path, caption, reply_markup=kb)
    else:
        await safe_edit(call, caption, reply_markup=kb)
    await call.answer()


# =========================================================
#  ПОДТВЕРЖДЕНИЕ ПОКУПКИ
#  Здесь и только здесь — проверка баланса
# =========================================================
@router.callback_query(F.data == "avatar:confirm")
async def avatar_confirm(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    existing = await get_my_avatar(call.from_user.id)
    if existing:
        await call.answer("У тебя уже есть аватар", show_alert=True)
        return

    gender = user.get("gender") or "m"
    key = "spartan" if gender == "m" else "amazon"
    name, price, _desc, _img, _g, _title = AVATARS[key]

    # ---- Проверка баланса ----
    if user["hearts_balance"] < price:
        shortage = price - user["hearts_balance"]
        await call.answer(
            f"❌ Недостаточно сердечек\n\n"
            f"Нужно: {price} ❤️\n"
            f"У тебя: {user['hearts_balance']} ❤️\n"
            f"Не хватает: {shortage} ❤️\n\n"
            f"Заработай: /hearts",
            show_alert=True,
        )
        return

    # ---- Списание ----
    ok = await spend_hearts(call.from_user.id, price)
    if not ok:
        await call.answer("Ошибка списания", show_alert=True)
        return

    couple = await get_couple(user["couple_id"])
    if couple is None:
        await call.answer()
        return

    await _execute(
        "INSERT INTO avatars (couple_id, telegram_id, avatar_key) "
        "VALUES (?, ?, ?)",
        (couple["id"], call.from_user.id, key),
    )

    # ---- Проверяем партнёра ----
    partner = await get_partner(user["couple_id"], call.from_user.id)
    partner_avatar = None
    if partner is not None:
        partner_avatar = await get_my_avatar(partner["telegram_id"])

    if partner is not None and partner_avatar and partner_avatar != key:
        # Оба купили — общий аватар +300 ❤️
        await add_hearts(call.from_user.id, 300)
        await add_hearts(partner["telegram_id"], 300)

        pair_text = (
            f"💞 <b>Поздравляем!</b>\n\n"
            f"У вас обоих есть аватары.\n"
            f"Открыт общий аватар — «Пара».\n\n"
            f"+300 ❤️ каждому!\n\n"
            f"В профиле можешь переключаться между своим аватаром\n"
            f"и общим — кнопкой «💞 Показать общую «Пару»»."
        )
        await safe_edit(call, pair_text)
        await send_to(call.bot, partner["telegram_id"], pair_text)

        # Достижение «Пара» — всплывашкой
        from utils.achievements import unlock_achievement
        if await unlock_achievement(couple["id"], "couple_avatar"):
            ach_text = "💞 <b>Достижение: Пара!</b>\n\nУ вас общий аватар 💞"
            await send_to(call.bot, call.from_user.id, ach_text)
            await send_to(call.bot, partner["telegram_id"], ach_text)

    await call.answer()


# =========================================================
#  МОИ АВАТАРЫ (личный + общий)
# =========================================================

@router.callback_query(F.data == "avatar:collection")
async def avatar_collection(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    my = await get_my_avatar(call.from_user.id)

    partner = await get_partner(user["couple_id"], call.from_user.id)
    partner_avatar = None
    partner_name = "партнёр"
    if partner is not None:
        partner_avatar = await get_my_avatar(partner["telegram_id"])
        partner_name = partner.get("name") or "партнёр"

    if not my:
        await safe_edit(
            call,
            "📖 У тебя пока нет аватаров.",
            reply_markup=kb_back("menu:profile"),
        )
        await call.answer()
        return

    name, _p, desc, image_path, _g, _title = AVATARS[my]

    header = (
        f"📖 <b>Твой аватар</b>\n\n"
        f"<b>{name}</b>\n\n{desc}"
    )

    # Если у обоих — показываем общий
    if partner_avatar and partner_avatar != my:
        my_name = user.get("name") or "Ты"
        header += (
            f"\n\n💞 <b>Общий аватар пары</b>\n\n"
            f"👑 {my_name} 💞 {partner_name} 👑\n"
        )

    bot = call.bot
    if bot is None:
        await call.answer()
        return

    # Удаляем старое сообщение
    from aiogram.types import FSInputFile, Message
    msg = call.message
    if isinstance(msg, Message):
        try:
            await msg.delete()
        except Exception:
            pass

    # Отправляем картинку + подпись
    if os.path.exists(image_path):
        try:
            photo = FSInputFile(image_path)
            await bot.send_photo(
                call.from_user.id,
                photo=photo,
                caption=header,
                reply_markup=kb_back("menu:profile"),
            )
        except Exception:
            await bot.send_message(
                call.from_user.id,
                header,
                reply_markup=kb_back("menu:profile"),
            )
    else:
        await bot.send_message(
            call.from_user.id,
            header,
            reply_markup=kb_back("menu:profile"),
        )
    await call.answer()

@router.callback_query(F.data.startswith("avatar:pref:"))
async def avatar_pref(call: CallbackQuery):
    parts = cb_parts(call)
    pref = parts[2] if len(parts) > 2 else "auto"
    if pref not in ("auto", "personal", "couple"):
        await call.answer()
        return

    await update_user(call.from_user.id, avatar_pref=pref)

    # Перерисовываем профиль
    from handlers.profile import render_profile
    await render_profile(call)
    await call.answer("Готово!")