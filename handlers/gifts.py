import os
import logging

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from database import (
    get_user,
    get_couple,
    get_partner,
    spend_hearts,
    spend_common_hearts,
    _fetchall,
    _execute,
)
from keyboards import kb_gifts_categories, kb_back
from config import GIFTS_DIR
from states import GiftFSM
from utils.helpers import (
    safe_edit,
    safe_edit_photo,
    send_to,
    safe_send_photo,
    cb_parts,
    hug_text,
)
from utils.achievements import check_gift_collection

logger = logging.getLogger(__name__)

router = Router()


# =========================================================
#  КАТАЛОГ ПОДАРКОВ
#  key: (название, цена, описание, картинка, глагол_m, что_именно)
# =========================================================

GIFTS: dict[str, tuple[str, int, str, str, str, str]] = {
    # ❤️ Сердца
    "heart_wine": (
        "🍷 Винное сердце", 30,
        "Глубокий винный цвет — как старое вино.",
        os.path.join(GIFTS_DIR, "hearts", "heart_wine.png"),
        "нарисовал",
        "винное сердце",
    ),
    "heart_black": (
        "🖤 Чёрное сердце", 30,
        "Чёрный — стильно и с характером.",
        os.path.join(GIFTS_DIR, "hearts", "heart_black.png"),
        "вышил",
        "чёрное сердце",
    ),
    "heart_white": (
        "🤍 Белое сердце", 30,
        "Белое — чистота и нежность.",
        os.path.join(GIFTS_DIR, "hearts", "heart_white.png"),
        "вырезал",
        "белое сердце",
    ),
    # 🌹 Розы
    "rose_red": (
        "🌹 Красная роза", 30,
        "Классика — красная роза.",
        os.path.join(GIFTS_DIR, "roses", "rose_red.png"),
        "нарисовал",
        "красную розу",
    ),
    "rose_white": (
        "🤍 Белая роза", 30,
        "Белая — чистота и невинность.",
        os.path.join(GIFTS_DIR, "roses", "rose_white.png"),
        "вышил",
        "белую розу",
    ),
    "rose_pink": (
        "🌸 Розовая роза", 30,
        "Розовая — нежность и романтика.",
        os.path.join(GIFTS_DIR, "roses", "rose_pink.png"),
        "вырезал",
        "розовую розу",
    ),
    # 🧸 Мишки
    "bear_brown": (
        "🐻 Бурый мишка", 30,
        "Классический плюшевый друг.",
        os.path.join(GIFTS_DIR, "bears", "bear_brown.png"),
        "нарисовал",
        "бурого мишку",
    ),
    "bear_pink": (
        "🌸 Розовый мишка", 30,
        "Милый и нежный.",
        os.path.join(GIFTS_DIR, "bears", "bear_pink.png"),
        "вышил",
        "розового мишку",
    ),
    "bear_white": (
        "🤍 Белый мишка", 30,
        "Плюшевый и чистый.",
        os.path.join(GIFTS_DIR, "bears", "bear_white.png"),
        "вырезал",
        "белого мишку",
    ),
}


CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "hearts": [
        ("🍷 Винное — маркер — 30 ❤️", "gift:show:heart_wine"),
        ("🖤 Чёрное — вышивка — 30 ❤️", "gift:show:heart_black"),
        ("🤍 Белое — аппликация — 30 ❤️", "gift:show:heart_white"),
    ],
    "roses": [
        ("🌹 Красная — маркер — 30 ❤️", "gift:show:rose_red"),
        ("🤍 Белая — вышивка — 30 ❤️", "gift:show:rose_white"),
        ("🌸 Розовая — аппликация — 30 ❤️", "gift:show:rose_pink"),
    ],
    "bears": [
        ("🐻 Бурый — маркер — 30 ❤️", "gift:show:bear_brown"),
        ("🌸 Розовый — вышивка — 30 ❤️", "gift:show:bear_pink"),
        ("🤍 Белый — аппликация — 30 ❤️", "gift:show:bear_white"),
    ],
}


# =========================================================
#  ХЕЛПЕРЫ ПОЛА И ПОДПИСИ
# =========================================================

def _agree_verb(verb_m: str, gender: str | None) -> str:
    """Согласует глагол по полу: 'нарисовал' → 'нарисовала'."""
    if gender != "f":
        return verb_m

    special = {
        "вышил": "вышила",
        "создал": "создала",
        "создали": "создали",
    }
    if verb_m in special:
        return special[verb_m]
    return verb_m + "а"


def gift_caption(
    from_name: str,
    from_gender: str | None,
    key: str,
    letter: str | None = None,
) -> str:
    """
    🎁 Влад нарисовал тебе красную розу

    💌 «Люблю тебя»
    """
    _name, _price, _desc, _img, verb_m, what = GIFTS[key]
    verb = _agree_verb(verb_m, from_gender)

    main = f"🎁 <b>{from_name} {verb} тебе {what}</b>"

    if letter:
        return f"{main}\n\n💌 <i>«{letter}»</i>"
    return main


# =========================================================
#  МЕНЮ ПОДАРКОВ
# =========================================================

@router.callback_query(F.data == "shop:gifts")
async def open_gifts(call: CallbackQuery):
    await safe_edit(
        call,
        "🎁 <b>Подарки</b>\n\n"
        "Собери коллекцию из 9 подарков.\n"
        "Каждый — уникален: свой стиль и цвет.",
        reply_markup=kb_gifts_categories(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("gift:cat:"))
async def open_category(call: CallbackQuery):
    parts = cb_parts(call)
    cat = parts[2] if len(parts) > 2 else ""
    items = CATEGORIES.get(cat, [])
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=t, callback_data=d)] for t, d in items
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:gifts")])
    title = {
        "hearts": "❤️ Сердца",
        "roses": "🌹 Розы",
        "bears": "🧸 Мишки",
    }.get(cat, "Подарки")
    await safe_edit(
        call,
        title,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await call.answer()


# =========================================================
#  КАРТОЧКА ПОДАРКА
# =========================================================

@router.callback_query(F.data.startswith("gift:show:"))
async def gift_show(call: CallbackQuery):
    parts = cb_parts(call)
    key = parts[2] if len(parts) > 2 else ""

    if key not in GIFTS:
        await call.answer("Подарок не найден", show_alert=True)
        return

    name, price, desc, image_path, _verb, _what = GIFTS[key]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Подарить за {price} ❤️",
            callback_data=f"gift:buy:{key}",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:gifts")],
    ])

    caption = f"{name}\n\n{desc}\n\nЦена: {price} ❤️"

    if os.path.exists(image_path):
        await safe_edit_photo(call, image_path, caption, reply_markup=kb)
    else:
        await safe_edit(call, caption, reply_markup=kb)
    await call.answer()


# =========================================================
#  ПОКУПКА — ШАГ 1: выбор подарка + запрос письма
# =========================================================

@router.callback_query(F.data.startswith("gift:buy:"))
async def buy_gift(call: CallbackQuery, state: FSMContext):
    parts = cb_parts(call)
    key = parts[2] if len(parts) > 2 else ""

    if key not in GIFTS:
        await call.answer("Подарок не найден", show_alert=True)
        return

    name, price, _desc, _image, _verb, _what = GIFTS[key]

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    couple = await get_couple(user["couple_id"])
    if couple is None:
        await call.answer("Пара не найдена", show_alert=True)
        return

    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    if user["hearts_balance"] < price:
        await call.answer(
            f"Нужно {price} ❤️ — у тебя {user['hearts_balance']}",
            show_alert=True,
        )
        return

    await state.update_data(
        gift_key=key,
        gift_price=price,
        gift_partner_id=partner["telegram_id"],
        gift_partner_name=partner["name"],
    )
    await state.set_state(GiftFSM.letter)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Отправить без письма",
            callback_data="gift:letter:skip",
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="shop:gifts")],
    ])
    await safe_edit(
        call,
        f"🎁 Подарок: <b>{name}</b>\n"
        f"Цена: {price} ❤️\n\n"
        f"Хочешь приложить письмо?\n\n"
        f"Напиши текст в чат — или отправь без письма.",
        reply_markup=kb,
    )
    await call.answer()


# =========================================================
#  ПОКУПКА — ШАГ 2: письмо
# =========================================================

@router.message(GiftFSM.letter)
async def gift_letter_received(message: Message, state: FSMContext):
    if message.from_user is None:
        return
    letter = (message.text or "").strip()
    if not letter:
        await message.answer("Пустое письмо. Напиши текст или нажми «Отправить без письма».")
        return
    if len(letter) > 300:
        letter = letter[:300] + "…"
    await _do_gift_purchase(message, state, letter)


@router.callback_query(F.data == "gift:letter:skip")
async def gift_letter_skip(call: CallbackQuery, state: FSMContext):
    await _do_gift_purchase(call, state, None)
    await call.answer()


# =========================================================
#  ПОКУПКА — ШАГ 3: списание + отправка + ачивки
# =========================================================

async def _do_gift_purchase(event, state: FSMContext, letter: str | None):
    data = await state.get_data()
    await state.clear()

    key = data.get("gift_key")
    price = data.get("gift_price")
    partner_id = data.get("gift_partner_id")

    if not key or price is None or partner_id is None:
        return

    if isinstance(event, CallbackQuery):
        user_id = event.from_user.id
        bot = event.bot
    else:
        if event.from_user is None:
            return
        user_id = event.from_user.id
        bot = event.bot

    user = await get_user(user_id)
    if user is None:
        return
    couple = await get_couple(user["couple_id"])
    if couple is None:
        return

    # Списываем
    ok = await spend_hearts(user_id, price)
    if not ok:
        await send_to(bot, user_id, "❌ Недостаточно сердечек.")
        return

    # Пишем в БД
    await _execute(
        "INSERT INTO gifts (couple_id, from_user, to_user, gift_key, is_shared) "
        "VALUES (?, ?, ?, ?, 0)",
        (user["couple_id"], user_id, partner_id, key),
    )

    # Подпись
    _name, _p, _d, image_path, _v, _w = GIFTS[key]
    caption = gift_caption(
        user["name"],
        user.get("gender"),
        key,
        letter,
    )

    kb_reply = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🤗 Обнять",
                callback_data=f"gift:hug:{user_id}",
            ),
            InlineKeyboardButton(
                text="🎁 Ответить подарком",
                callback_data="shop:gifts",
            ),
        ],
    ])

    if os.path.exists(image_path):
        await safe_send_photo(bot, partner_id, image_path, caption, reply_markup=kb_reply)
    else:
        await send_to(bot, partner_id, caption, reply_markup=kb_reply)

    # ---- ПРОВЕРКА АЧИВОК ПО КОЛЛЕКЦИИ ----
    new_ach = await check_gift_collection(
        couple["id"], couple["user_a_id"], couple["user_b_id"]
    )

    _gname = GIFTS[key][0]
    success_text = f"✅ Подарок отправлен: {_gname}"
    if letter:
        success_text += f"\n\n💌 С письмом: «{letter}»"
    if new_ach:
        success_text += "\n\n🏆 <b>Новые достижения:</b>\n\n" + "\n\n".join(new_ach)

    await send_to(bot, user_id, success_text, reply_markup=kb_back("shop:gifts"))

    # Партнёру тоже прилетит ачивка
    if new_ach:
        await send_to(
            bot,
            partner_id,
            "🏆 <b>Новые достижения:</b>\n\n" + "\n\n".join(new_ach),
        )


# =========================================================
#  КНОПКА «ОБНЯТЬ»
# =========================================================

@router.callback_query(F.data.startswith("gift:hug:"))
async def gift_hug(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        to_user_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    me = await get_user(call.from_user.id)
    if me is None:
        await call.answer()
        return
    partner = await get_partner(me["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    import random
    text = hug_text(me["name"], partner["name"], random.randint(0, 3))

    await send_to(call.bot, to_user_id, text)
    await call.answer("Обнимаешь ❤️")


# =========================================================
#  МОЯ КОЛЛЕКЦИЯ (полученные / отправленные)
# =========================================================

@router.callback_query(F.data == "gift:collection")
async def gift_collection(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    received = await _fetchall(
        "SELECT gift_key, from_user, is_shared, created_at FROM gifts "
        "WHERE couple_id=? AND (to_user=? OR is_shared=1) "
        "ORDER BY created_at DESC",
        (user["couple_id"], call.from_user.id),
    )
    sent = await _fetchall(
        "SELECT gift_key, to_user, is_shared, created_at FROM gifts "
        "WHERE couple_id=? AND from_user=? "
        "ORDER BY created_at DESC",
        (user["couple_id"], call.from_user.id),
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"📥 Мне подарили ({len(received)})",
            callback_data="gift:received",
        )],
        [InlineKeyboardButton(
            text=f"📤 Я подарил ({len(sent)})",
            callback_data="gift:sent",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:profile")],
    ])
    await safe_edit(
        call,
        f"📖 <b>Моя коллекция</b>\n\n"
        f"📥 Получено: {len(received)}\n"
        f"📤 Подарено: {len(sent)}",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data == "gift:received")
async def gift_received(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    rows = await _fetchall(
        "SELECT gift_key, from_user, is_shared, created_at FROM gifts "
        "WHERE couple_id=? AND (to_user=? OR is_shared=1) "
        "ORDER BY created_at DESC",
        (user["couple_id"], call.from_user.id),
    )

    if not rows:
        await safe_edit(
            call,
            "📥 Тебе пока никто ничего не подарил.",
            reply_markup=kb_back("gift:collection"),
        )
        await call.answer()
        return

    bot = call.bot
    if bot is None:
        await call.answer()
        return

    msg = call.message
    if isinstance(msg, Message):
        try:
            await msg.delete()
        except Exception:
            pass

    await bot.send_message(
        call.from_user.id,
        f"📥 <b>Тебе подарили ({len(rows)})</b>",
    )

    for r in rows:
        key = r["gift_key"]
        if key not in GIFTS:
            continue
        name, _price, desc, image_path, _verb, _what = GIFTS[key]
        mark = " 💞 (общий)" if r["is_shared"] else ""
        caption = f"<b>{name}</b>{mark}\n\n{desc}"

        if os.path.exists(image_path):
            await safe_send_photo(bot, call.from_user.id, image_path, caption)
        else:
            await send_to(bot, call.from_user.id, caption)

    await bot.send_message(
        call.from_user.id,
        "👆 Твои подарки",
        reply_markup=kb_back("gift:collection"),
    )
    await call.answer()


@router.callback_query(F.data == "gift:sent")
async def gift_sent(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    rows = await _fetchall(
        "SELECT gift_key, to_user, is_shared, created_at FROM gifts "
        "WHERE couple_id=? AND from_user=? "
        "ORDER BY created_at DESC",
        (user["couple_id"], call.from_user.id),
    )

    if not rows:
        await safe_edit(
            call,
            "📤 Ты пока ничего не подарил.",
            reply_markup=kb_back("gift:collection"),
        )
        await call.answer()
        return

    bot = call.bot
    if bot is None:
        await call.answer()
        return

    msg = call.message
    if isinstance(msg, Message):
        try:
            await msg.delete()
        except Exception:
            pass

    await bot.send_message(
        call.from_user.id,
        f"📤 <b>Ты подарил ({len(rows)})</b>",
    )

    for r in rows:
        key = r["gift_key"]
        if key not in GIFTS:
            continue
        name, _price, desc, image_path, _verb, _what = GIFTS[key]
        mark = " 💞 (общий)" if r["is_shared"] else ""
        caption = f"<b>{name}</b>{mark}\n\n{desc}"

        if os.path.exists(image_path):
            await safe_send_photo(bot, call.from_user.id, image_path, caption)
        else:
            await send_to(bot, call.from_user.id, caption)

    await bot.send_message(
        call.from_user.id,
        "👆 Твои отправленные",
        reply_markup=kb_back("gift:collection"),
    )
    await call.answer()