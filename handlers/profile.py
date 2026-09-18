from datetime import datetime

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)

from database import (
    get_user,
    get_couple,
    get_partner,
    get_movies,
    get_couple_total_earned,
    _fetchall,
    
    get_couple_rank, 
    _fetchone,
)
from config import get_status, get_love_status
from keyboards import kb_back
from utils.helpers import safe_edit
from handlers.avatars import get_my_avatar, display_name, AVATARS

router = Router()


# =========================================================
#  ХЕЛПЕРЫ
# =========================================================

async def _days_together(couple_id: int) -> int | None:
    """Считает дни с начала отношений (если дата задана)."""
    rows = await _fetchall(
        "SELECT date FROM dates WHERE couple_id=? AND date_type='anniversary' "
        "ORDER BY id LIMIT 1",
        (couple_id,),
    )
    if not rows:
        return None

    date_str = rows[0]["date"] or ""
    for fmt in ("%d.%m.%Y", "%d.%m"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if fmt == "%d.%m":
                dt = dt.replace(year=datetime.now().year)
            return (datetime.now() - dt).days
        except ValueError:
            continue
    return None


async def _build_profile(user, partner, couple, movies_count, achievements):
    """
    Возвращает (текст, путь_к_картинке_или_None).
    """
    # --- Аватары ---
    my_avatar_key = await get_my_avatar(user["telegram_id"])
    my_name = display_name(user["name"] or "Ты", my_avatar_key)

    partner_avatar_key = None
    partner_name_raw = partner["name"] if partner else "Партнёр"
    if partner:
        partner_avatar_key = await get_my_avatar(partner["telegram_id"])

    both_have = (
        my_avatar_key and partner_avatar_key
        and my_avatar_key != partner_avatar_key
    )

    pref = user.get("avatar_pref") or "auto"

    # --- Заголовок + картинка ---
    if both_have and pref == "couple":
        header_name = f"👑 {user['name']} 💞 {partner_name_raw} 👑"
        image_key = "couple"
    else:
        header_name = my_name
        image_key = my_avatar_key

    # --- Балансы ---
    partner_balance = partner["hearts_balance"] if partner else 0

    # --- Total earned ---
    total_earned = await get_couple_total_earned(couple["id"])

    # --- Позиция в рейтинге ---
    rank = await get_couple_rank(couple["id"])
    rank_line = f"• Позиция в рейтинге: <b>#{rank}</b>" if rank else ""

    # --- Дни вместе + статус ---
    days = await _days_together(couple["id"])
    if days is not None:
        love_status = get_love_status(days)
        days_line = f"📊 Вы вместе: <b>{days} дней</b> — {love_status}"
    else:
        days_line = ""

    # --- Пятницы ---
    fridays = await _fetchall(
        "SELECT status FROM friday_events WHERE couple_id=? "
        "ORDER BY created_at DESC LIMIT 500",
        (couple["id"],),
    )
    friday_streak = 0
    for e in fridays:
        if e["status"] == "done":
            friday_streak += 1
        else:
            break
    friday_total = sum(1 for e in fridays if e["status"] == "done")

    # --- Фильмов просмотрено ---
    watched = await _fetchone(
        "SELECT COUNT(*) AS c FROM movies "
        "WHERE couple_id=? AND watched_at IS NOT NULL",
        (couple["id"],),
    )
    watched_count = watched["c"] if watched else 0

    # --- Сборка ---
    lines = [
        f"👤 <b>{header_name}</b>",
        "",
    ]
    if days_line:
        lines.append(days_line)
        lines.append("")

    lines.extend([
        f"❤️ Твой баланс: {user['hearts_balance']}",
        f"❤️ Баланс партнёра: {partner_balance}",
        "",
        f"• Заработано за всё время: <b>{total_earned}</b>",
        f"• Статус: {get_status(total_earned)}",
    ])

    if rank_line:
        lines.append(rank_line)

    lines.append("")
    lines.extend([
        f"📊 Статистика:",
        f"• Фильмов просмотрено: <b>{watched_count}</b>",
        f"• Пятниц выполнено: <b>{friday_total}</b>",
        f"• Пятниц подряд: <b>{friday_streak}</b>",
    ])

    # --- Картинка ---
    image_path = None
    if image_key and image_key in AVATARS:
        image_path = AVATARS[image_key][3]

    return "\n".join(lines), image_path

async def _profile_kb(user) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    my_avatar_key = await get_my_avatar(user["telegram_id"])

    # Кнопка покупки аватара — только если его нет
    if my_avatar_key is None:
        rows.append([InlineKeyboardButton(
            text="🎨 Купить аватар",
            callback_data="avatar:buy",
        )])

    # Переключение между личным и общим аватаром
    partner = await get_partner(user["couple_id"], user["telegram_id"])
    if partner is not None and my_avatar_key:
        partner_avatar = await get_my_avatar(partner["telegram_id"])
        if partner_avatar and my_avatar_key != partner_avatar:
            pref = user.get("avatar_pref") or "auto"
            if pref == "couple":
                next_label = "🖼 Показать мой аватар"
                next_pref = "personal"
            else:
                next_label = "💞 Показать общую «Пару»"
                next_pref = "couple"
            rows.append([InlineKeyboardButton(
                text=next_label,
                callback_data=f"avatar:pref:{next_pref}",
            )])

    rows.append([InlineKeyboardButton(
        text="🧠 Портрет пары",
        callback_data="profile:portrait",
    )])

    rows.append([InlineKeyboardButton(
        text="🎁 Моя коллекция подарков",
        callback_data="gift:collection",
    )])

    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.callback_query(F.data == "profile:portrait")
async def profile_portrait(call: CallbackQuery):
    if call.from_user is None:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    couple_id = user["couple_id"]
    if couple_id is None:
        await call.answer("Пара не найдена", show_alert=True)
        return

    partner = await get_partner(couple_id, call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    from handlers.question import get_full_portrait_text
    text = await get_full_portrait_text(couple_id, user, partner)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:profile")],
    ])
    await safe_edit(call, text, reply_markup=kb)
    await call.answer()
# =========================================================
#  RENDER: сообщением
# =========================================================

async def render_profile_msg(message: Message):
    if message.from_user is None:
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала /start")
        return

    couple_id = user["couple_id"]
    if couple_id is None:
        await message.answer("Пара не найдена")
        return

    couple = await get_couple(couple_id)
    if couple is None:
        await message.answer("Пара не найдена")
        return

    partner = await get_partner(couple_id, message.from_user.id)
    movies = await get_movies(couple_id)

    text, image_path = await _build_profile(
        user, partner, couple, len(movies), []
    )
    kb = await _profile_kb(user)

    if image_path:
        bot = message.bot
        if bot is None:
            return
        try:
            await bot.send_photo(
                message.chat.id,
                photo=FSInputFile(image_path),
                caption=text,
                reply_markup=kb,
            )
            return
        except Exception:
            pass

    await message.answer(text, reply_markup=kb)

# =========================================================
#  RENDER: callback
# =========================================================

async def render_profile(call: CallbackQuery):
    if call.from_user is None:
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    couple_id = user["couple_id"]
    if couple_id is None:
        await call.answer("Пара не найдена", show_alert=True)
        return

    couple = await get_couple(couple_id)
    if couple is None:
        await call.answer("Пара не найдена", show_alert=True)
        return

    partner = await get_partner(couple_id, call.from_user.id)
    movies = await get_movies(couple_id)

    text, image_path = await _build_profile(
        user, partner, couple, len(movies), []
    )
    kb = await _profile_kb(user)

    # Если аватар — отправляем фото, старое удаляем
    if image_path:
        bot = call.bot
        msg = call.message
        if isinstance(msg, Message) and bot is not None:
            try:
                await msg.delete()
            except Exception:
                pass
            try:
                await bot.send_photo(
                    call.from_user.id,
                    photo=FSInputFile(image_path),
                    caption=text,
                    reply_markup=kb,
                )
                await call.answer()
                return
            except Exception:
                pass

    await safe_edit(call, text, reply_markup=kb)


@router.callback_query(F.data == "menu:profile_render")
async def profile_render(call: CallbackQuery):
    await render_profile(call)
    await call.answer()