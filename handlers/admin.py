"""Админ-панель /admin."""
import logging
from html import escape
from aiogram.exceptions import TelegramForbiddenError
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID
from database import (
    get_user,
    get_couple,
    get_partner,
    add_hearts,
    _fetchone,
    _fetchall,
    _execute,
)
from keyboards import kb_back
from utils.helpers import safe_edit, send_to, cb_parts
from utils.admin_helpers import (
    is_admin,
    add_log,
    get_stats,
    ban_couple,
    ban_user,
    is_banned,
)

logger = logging.getLogger(__name__)

router = Router()


# =========================================================
#  FSM
# =========================================================

class AdminFSM(StatesGroup):
    broadcast_text = State()
    broadcast_button_text = State()
    broadcast_button_url = State()
    gift_target = State()
    gift_amount = State()
    gift_reason = State()
    ban_target = State()
    ban_reason = State()
    write_couple = State()


# =========================================================
#  ГЛАВНЫЙ ЭКРАН
# =========================================================
def _admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
        [InlineKeyboardButton(text="👥 Пары", callback_data="adm:couples:0")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:bc")],
        [InlineKeyboardButton(text="🎁 Подарить сердечки", callback_data="adm:gift")],
        [InlineKeyboardButton(text="🚫 Бан", callback_data="adm:ban")],
        [InlineKeyboardButton(text="📝 Логи", callback_data="adm:logs")],
        [InlineKeyboardButton(text="🧹 Очистить заблокировавших", callback_data="adm:cleanup")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
    ])


ADMIN_MAIN_TEXT = "🛠 <b>Админ-панель</b>\n\nВыбери раздел:"


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if message.from_user is None:
        return
    if not is_admin(message.from_user.id):
        await message.answer("🚫 Доступ запрещён")
        return
    await state.clear()
    await message.answer(ADMIN_MAIN_TEXT, reply_markup=_admin_main_kb())


@router.callback_query(F.data == "adm:main")
async def adm_main(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    await state.clear()
    await safe_edit(call, ADMIN_MAIN_TEXT, reply_markup=_admin_main_kb())
    await call.answer()


# =========================================================
#  📊 СТАТИСТИКА
# =========================================================

@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return

    s = await get_stats()

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего пар: <b>{s['total_couples']}</b>\n"
        f"✅ Активных: <b>{s['active_couples']}</b>\n"
        f"💤 Неактивных: <b>{s['total_couples'] - s['active_couples']}</b>\n\n"
        f"🆕 Новых сегодня: {s['new_today']}\n"
        f"🆕 За неделю: {s['new_week']}\n"
        f"🆕 За месяц: {s['new_month']}\n\n"
        f"❤️ Сердечек в системе: {s['hearts_total']}\n"
        f"💰 Куплено за месяц: {s['bought_month']} ₽\n\n"
        f"🎁 Подарков: {s['gifts']}\n"
        f"🎬 Фильмов: {s['movies']}\n"
        f"🖤 Пятниц: {s['fridays']}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:stats")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:main")],
    ])
    await safe_edit(call, text, reply_markup=kb)
    await call.answer()


# =========================================================
#  👥 СПИСОК ПАР
# =========================================================

async def _render_couples(call: CallbackQuery, sort: str, page: int = 0) -> None:
    if sort == "new":
        order = "c.created_at DESC"
        title = "🆕 Новые"
    elif sort == "active":
        order = "c.created_at DESC"
        title = "🔥 Активные"
    else:
        order = "c.created_at ASC"
        title = "💤 Неактивные"

    rows = await _fetchall(
        f"SELECT c.*, "
        f"(SELECT name FROM users WHERE couple_id=c.id ORDER BY id LIMIT 1) AS name_a, "
        f"(SELECT name FROM users WHERE couple_id=c.id ORDER BY id DESC LIMIT 1) AS name_b, "
        f"c.common_balance AS balance "
        f"FROM couples c WHERE c.status='active' "
        f"ORDER BY {order} LIMIT 100"
    )

    total = len(rows)
    per_page = 10
    start = page * per_page
    end = start + per_page
    chunk = rows[start:end]

    if not chunk:
        await safe_edit(
            call,
            f"👥 <b>Пары ({total})</b>\n\nПусто.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:main")],
            ]),
        )
        await call.answer()
        return

    lines = [f"👥 <b>Пары ({total})</b> — {title}\n"]
    kb_rows: list[list[InlineKeyboardButton]] = []

    for i, r in enumerate(chunk, start + 1):
        name_a = r.get("name_a") or "—"
        name_b = r.get("name_b") or "—"
        lines.append(f"{i}. {name_a} & {name_b} — {r['balance']} ❤️")
        kb_rows.append([InlineKeyboardButton(
            text=f"👀 {name_a} & {name_b}",
            callback_data=f"adm:couple:{r['id']}",
        )])

    kb_rows.append([
        InlineKeyboardButton(text="🆕 Новые", callback_data="adm:couples:0:new"),
        InlineKeyboardButton(text="🔥 Активные", callback_data="adm:couples:0:active"),
        InlineKeyboardButton(text="💤 Неактивные", callback_data="adm:couples:0:inactive"),
    ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"adm:couples:{page-1}:{sort}",
        ))
    if end < total:
        nav.append(InlineKeyboardButton(
            text="➡️ Вперёд",
            callback_data=f"adm:couples:{page+1}:{sort}",
        ))
    if nav:
        kb_rows.append(nav)

    kb_rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="adm:main")])

    await safe_edit(
        call,
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:couples:"))
async def adm_couples(call: CallbackQuery):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return

    parts = cb_parts(call)
    try:
        page = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        page = 0
    sort = parts[3] if len(parts) > 3 else "new"

    await _render_couples(call, sort, page)


# =========================================================
#  🔍 КАРТОЧКА ПАРЫ
# =========================================================

@router.callback_query(F.data.startswith("adm:couple:"))
async def adm_couple_card(call: CallbackQuery):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return

    parts = cb_parts(call)
    try:
        couple_id = int(parts[2])
    except (ValueError, IndexError):
        await call.answer()
        return

    couple = await get_couple(couple_id)
    if couple is None:
        await call.answer("Пара не найдена", show_alert=True)
        return

    users = await _fetchall(
        "SELECT telegram_id, name, hearts_balance FROM users "
        "WHERE couple_id=? ORDER BY id",
        (couple_id,),
    )
    user_a = users[0] if len(users) > 0 else {}
    user_b = users[1] if len(users) > 1 else {}

    row = await _fetchone(
        "SELECT COUNT(*) AS c FROM movies "
        "WHERE couple_id=? AND status='in_list'",
        (couple_id,),
    )
    movies = row["c"] if row else 0

    row = await _fetchone(
        "SELECT COUNT(*) AS c FROM friday_events "
        "WHERE couple_id=? AND status='done'",
        (couple_id,),
    )
    fridays = row["c"] if row else 0

    row = await _fetchone(
        "SELECT COUNT(*) AS c FROM gifts WHERE couple_id=?",
        (couple_id,),
    )
    gifts = row["c"] if row else 0

    purchases = await _fetchall(
        "SELECT package, price, created_at FROM purchases "
        "WHERE user_id IN (?, ?) ORDER BY created_at DESC LIMIT 5",
        (user_a.get("telegram_id", 0), user_b.get("telegram_id", 0)),
    )
    purchases_lines = "\n".join(
        f"• {p['package']} ❤️ — {p['price']}₽ ({(p['created_at'] or '')[:10]})"
        for p in purchases
    ) or "—"

    text = (
        f"👤 <b>{user_a.get('name', '?')} & {user_b.get('name', '?')}</b>\n\n"
        f"🆔 Couple ID: <code>{couple_id}</code>\n"
        f"📅 Создана: {(couple.get('created_at') or '')[:10]}\n\n"
        f"❤️ {user_a.get('name', '?')}: {user_a.get('hearts_balance', 0)}\n"
        f"❤️ {user_b.get('name', '?')}: {user_b.get('hearts_balance', 0)}\n"
        f"❤️ Общий: {couple.get('common_balance', 0)}\n\n"
        f"📊 Прогресс:\n"
        f"• Фильмов: {movies}\n"
        f"• Пятниц: {fridays}\n"
        f"• Подарков: {gifts}\n\n"
        f"💰 Покупки:\n{purchases_lines}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎁 Подарить сердечки",
            callback_data=f"adm:gift_couple:{couple_id}",
        )],
        [InlineKeyboardButton(
            text="📢 Написать паре",
            callback_data=f"adm:write:{couple_id}",
        )],
        [InlineKeyboardButton(
            text="🚫 Забанить",
            callback_data=f"adm:ban_couple:{couple_id}",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:couples:0")],
    ])
    await safe_edit(call, text, reply_markup=kb)
    await call.answer()


# =========================================================
#  📢 РАССЫЛКА
# =========================================================

@router.callback_query(F.data == "adm:bc")
async def adm_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return

    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Всем", callback_data="adm:bc_aud:all")],
        [InlineKeyboardButton(text="✅ Активным", callback_data="adm:bc_aud:active")],
        [InlineKeyboardButton(text="👥 Конкретной паре", callback_data="adm:bc_aud:couple")],
        [InlineKeyboardButton(text="👤 Конкретному юзеру", callback_data="adm:bc_aud:user")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:main")],
    ])
    await safe_edit(
        call,
        "📢 <b>Рассылка</b>\n\nВыбери аудиторию:",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:bc_aud:"))
async def adm_bc_audience(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return

    parts = cb_parts(call)
    audience = parts[2] if len(parts) > 2 else "all"

    if audience in ("couple", "user"):
        await state.update_data(bc_audience=audience)
        await state.set_state(AdminFSM.broadcast_text)
        await safe_edit(
            call,
            f"📢 Введи ID {'пары' if audience == 'couple' else 'пользователя'}:",
        )
        await call.answer()
        return

    await state.update_data(bc_audience=audience, bc_target=None)
    await state.set_state(AdminFSM.broadcast_text)
    await safe_edit(call, "📢 Напиши текст рассылки:")
    await call.answer()


@router.message(AdminFSM.broadcast_text)
async def adm_bc_text(message: Message, state: FSMContext):
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    audience = data.get("bc_audience")
    target = data.get("bc_target")

    if audience in ("couple", "user") and target is None:
        try:
            target = int((message.text or "").strip())
        except ValueError:
            await message.answer("❌ Введи число")
            return
        await state.update_data(bc_target=target)
        await message.answer("📢 Теперь напиши текст рассылки:")
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустой текст")
        return

    await state.update_data(bc_text=text)
    await state.set_state(AdminFSM.broadcast_button_text)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Без кнопки", callback_data="adm:bc_send")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:bc")],
    ])
    await message.answer(
        "📎 Прикрепить кнопку?\n\n"
        "Если да — напиши <b>текст кнопки</b>.\n"
        "Если нет — нажми «Без кнопки».",
        reply_markup=kb,
    )


@router.message(AdminFSM.broadcast_button_text)
async def adm_bc_btn_text(message: Message, state: FSMContext):
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    btn_text = (message.text or "").strip()
    if not btn_text:
        await message.answer("Пусто")
        return
    await state.update_data(bc_btn_text=btn_text)
    await state.set_state(AdminFSM.broadcast_button_url)
    await message.answer("📎 Теперь напиши ссылку для кнопки (URL):")


@router.message(AdminFSM.broadcast_button_url)
async def adm_bc_btn_url(message: Message, state: FSMContext):
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    url = (message.text or "").strip()
    if not url.startswith("http"):
        await message.answer("URL должен начинаться с http")
        return
    await state.update_data(bc_btn_url=url)
    await _bc_preview(message, state)


@router.callback_query(F.data == "adm:bc_send")
async def adm_bc_send_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    await state.update_data(bc_btn_text=None, bc_btn_url=None)
    await _bc_preview(call.message, state, is_callback=True, call=call)
    await call.answer()


async def _bc_preview(target_msg, state: FSMContext, is_callback: bool = False, call=None):
    data = await state.get_data()
    audience = data.get("bc_audience")
    text = data.get("bc_text", "")
    btn_text = data.get("bc_btn_text")
    btn_url = data.get("bc_btn_url")

    count = await _bc_count_recipients(audience, data.get("bc_target"))

    preview = (
        f"⚠️ <b>Отправить {count}?</b>\n\n"
        f"<b>Текст:</b>\n{escape(text)}\n\n"
    )
    if btn_text and btn_url:
        preview += f"<b>Кнопка:</b> {btn_text} → {btn_url}\n\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, отправить", callback_data="adm:bc_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:bc")],
    ])

    if is_callback and call:
        await safe_edit(call, preview, reply_markup=kb)
    else:
        await target_msg.answer(preview, reply_markup=kb)


async def _bc_count_recipients(audience: str | None, target) -> int:
    if not audience:
        return 0
    if audience == "all":
        row = await _fetchone("SELECT COUNT(*) AS c FROM users WHERE couple_id IS NOT NULL")
    elif audience == "active":
        row = await _fetchone("SELECT COUNT(*) AS c FROM users WHERE couple_id IS NOT NULL")
    elif audience == "couple":
        row = await _fetchone("SELECT COUNT(*) AS c FROM users WHERE couple_id=?", (target,))
    elif audience == "user":
        row = await _fetchone("SELECT COUNT(*) AS c FROM users WHERE telegram_id=?", (target,))
    else:
        row = None
    return row["c"] if row else 0


@router.callback_query(F.data == "adm:bc_confirm")
async def adm_bc_confirm(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return

    data = await state.get_data()
    await state.clear()

    audience = data.get("bc_audience")
    target = data.get("bc_target")
    text = data.get("bc_text", "")
    btn_text = data.get("bc_btn_text")
    btn_url = data.get("bc_btn_url")

    if audience == "all":
        rows = await _fetchall("SELECT telegram_id FROM users WHERE couple_id IS NOT NULL")
    elif audience == "active":
        rows = await _fetchall("SELECT telegram_id FROM users WHERE couple_id IS NOT NULL")
    elif audience == "couple":
        rows = await _fetchall("SELECT telegram_id FROM users WHERE couple_id=?", (target,))
    elif audience == "user":
        rows = await _fetchall("SELECT telegram_id FROM users WHERE telegram_id=?", (target,))
    else:
        rows = []

    kb = None
    if btn_text and btn_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, url=btn_url)],
        ])

    sent = 0
    errors = 0
    bot = call.bot
    if bot is None:
        await call.answer("Ошибка: бот недоступен", show_alert=True)
        return

    for r in rows:
        try:
            await bot.send_message(r["telegram_id"], text, reply_markup=kb)
            sent += 1
        except Exception as e:
            errors += 1
            logger.warning(f"Broadcast error to {r['telegram_id']}: {e}")

    await _execute(
        "INSERT INTO broadcasts "
        "(admin_id, audience, target_id, text, button_text, button_url, sent_count, error_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (call.from_user.id, audience, target, text, btn_text, btn_url, sent, errors),
    )
    await add_log(
        "admin_action",
        f"Рассылка: {audience} → отправлено {sent}, ошибок {errors}",
        admin_id=call.from_user.id,
    )

    await safe_edit(
        call,
        f"✅ <b>Отправлено!</b>\n\n"
        f"📢 Доставлено: {sent}\n"
        f"❌ Ошибок: {errors}",
        reply_markup=kb_back("adm:main"),
    )
    await call.answer()


# =========================================================
#  🎁 ПОДАРИТЬ СЕРДЕЧКИ
# =========================================================

@router.callback_query(F.data == "adm:gift")
async def adm_gift(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Паре", callback_data="adm:gift_type:couple")],
        [InlineKeyboardButton(text="👤 Пользователю", callback_data="adm:gift_type:user")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:main")],
    ])
    await safe_edit(call, "🎁 <b>Подарить сердечки</b>\n\nВыбери, кому:", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("adm:gift_type:"))
async def adm_gift_type(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    parts = cb_parts(call)
    gift_type = parts[2] if len(parts) > 2 else "couple"
    await state.update_data(gift_type=gift_type)
    await state.set_state(AdminFSM.gift_target)
    await safe_edit(
        call,
        f"Введи ID {'пары' if gift_type == 'couple' else 'пользователя'}:",
    )
    await call.answer()


@router.message(AdminFSM.gift_target)
async def adm_gift_target(message: Message, state: FSMContext):
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    try:
        target = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Введи число")
        return
    await state.update_data(gift_target=target)
    await state.set_state(AdminFSM.gift_amount)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="100 ❤️", callback_data="adm:gift_amt:100")],
        [InlineKeyboardButton(text="300 ❤️", callback_data="adm:gift_amt:300")],
        [InlineKeyboardButton(text="500 ❤️", callback_data="adm:gift_amt:500")],
        [InlineKeyboardButton(text="1000 ❤️", callback_data="adm:gift_amt:1000")],
        [InlineKeyboardButton(text="✏️ Своё", callback_data="adm:gift_amt:custom")],
    ])
    await message.answer("Сколько ❤️ подарить?", reply_markup=kb)


@router.callback_query(F.data.startswith("adm:gift_amt:"))
async def adm_gift_amt(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    parts = cb_parts(call)
    amt = parts[2] if len(parts) > 2 else ""

    if amt == "custom":
        await safe_edit(call, "✏️ Введи число:")
        await call.answer()
        return

    try:
        amount = int(amt)
    except ValueError:
        await call.answer()
        return

    await state.update_data(gift_amount=amount)
    await state.set_state(AdminFSM.gift_reason)
    await safe_edit(call, f"✅ Сумма: {amount} ❤️\n\nПричина (необязательно):")
    await call.answer()


@router.message(AdminFSM.gift_amount)
async def adm_gift_amount_text(message: Message, state: FSMContext):
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Число")
        return
    await state.update_data(gift_amount=amount)
    await state.set_state(AdminFSM.gift_reason)
    await message.answer(f"✅ {amount} ❤️\n\nПричина (необязательно):")


@router.message(AdminFSM.gift_reason)
async def adm_gift_reason(message: Message, state: FSMContext):
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    reason = (message.text or "").strip() or None

    data = await state.get_data()
    await state.clear()

    gift_type = data.get("gift_type")
    target = data.get("gift_target")
    amount = data.get("gift_amount")

    # ---- Валидация ----
    if not isinstance(amount, int) or amount <= 0:
        await message.answer("❌ Ошибка: сумма не задана")
        return
    if not isinstance(target, int):
        await message.answer("❌ Ошибка: цель не задана")
        return

    if gift_type == "couple":
        users = await _fetchall(
            "SELECT telegram_id FROM users WHERE couple_id=?", (target,)
        )
    else:
        users = await _fetchall(
            "SELECT telegram_id FROM users WHERE telegram_id=?", (target,)
        )

    for u in users:
        await add_hearts(u["telegram_id"], amount)

    await _execute(
        "INSERT INTO admin_gifts "
        "(admin_id, couple_id, user_id, amount, reason) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            message.from_user.id,
            target if gift_type == "couple" else None,
            target if gift_type == "user" else None,
            amount,
            reason,
        ),
    )
    await add_log(
        "admin_action",
        f"Подарок {amount} ❤️ ({gift_type} #{target})",
        admin_id=message.from_user.id,
    )

    # Уведомить получателей
    bot = message.bot
    if bot is not None:
        for u in users:
            try:
                text = f"🎁 Вам начислено <b>{amount} ❤️</b>.\n"
                if reason:
                    text += f"\nПричина: {escape(reason)}\n"
                text += "\nСпасибо, что вы с нами ❤️"
                await bot.send_message(u["telegram_id"], text)
            except Exception:
                pass

    await message.answer(
        f"✅ Подарено {amount} ❤️",
        reply_markup=kb_back("adm:main"),
    )


@router.callback_query(F.data.startswith("adm:gift_couple:"))
async def adm_gift_from_card(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    parts = cb_parts(call)
    try:
        couple_id = int(parts[2])
    except (ValueError, IndexError):
        await call.answer()
        return
    await state.update_data(gift_type="couple", gift_target=couple_id)
    await state.set_state(AdminFSM.gift_amount)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="100 ❤️", callback_data="adm:gift_amt:100")],
        [InlineKeyboardButton(text="300 ❤️", callback_data="adm:gift_amt:300")],
        [InlineKeyboardButton(text="500 ❤️", callback_data="adm:gift_amt:500")],
        [InlineKeyboardButton(text="1000 ❤️", callback_data="adm:gift_amt:1000")],
    ])
    await safe_edit(call, f"🎁 Подарить паре #{couple_id}\n\nСколько?", reply_markup=kb)
    await call.answer()


# =========================================================
#  🚫 БАН
# =========================================================

@router.callback_query(F.data == "adm:ban")
async def adm_ban(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    await state.clear()
    await state.set_state(AdminFSM.ban_target)
    await safe_edit(
        call,
        "🚫 <b>Бан</b>\n\nВведи ID пары или пользователя:",
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:ban_couple:"))
async def adm_ban_couple(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    parts = cb_parts(call)
    try:
        couple_id = int(parts[2])
    except (ValueError, IndexError):
        await call.answer()
        return
    await state.update_data(ban_couple_id=couple_id)
    await state.set_state(AdminFSM.ban_reason)
    await safe_edit(call, f"🚫 Причина бана пары #{couple_id}:")
    await call.answer()


@router.message(AdminFSM.ban_target)
async def adm_ban_target(message: Message, state: FSMContext):
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip()
    try:
        target_id = int(raw)
    except ValueError:
        await message.answer("❌ Число")
        return
    couple = await get_couple(target_id)
    if couple is not None:
        await state.update_data(ban_couple_id=target_id)
    else:
        await state.update_data(ban_user_id=target_id)
    await state.set_state(AdminFSM.ban_reason)
    await message.answer("🚫 Причина бана:")


@router.message(AdminFSM.ban_reason)
async def adm_ban_reason(message: Message, state: FSMContext):
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    reason = (message.text or "").strip() or "не указана"

    data = await state.get_data()
    await state.clear()

    couple_id = data.get("ban_couple_id")
    user_id = data.get("ban_user_id")

    bot = message.bot
    if bot is None:
        await message.answer("❌ Бот недоступен")
        return

    if couple_id:
        await ban_couple(couple_id, reason, message.from_user.id)
        users = await _fetchall(
            "SELECT telegram_id FROM users WHERE couple_id=?", (couple_id,)
        )
        for u in users:
            try:
                await bot.send_message(
                    u["telegram_id"],
                    f"🚫 <b>Вы забанены.</b>\n\n"
                    f"Причина: {escape(reason)}\n\n"
                    f"Для обжалования:\nvladgrigoryan1999@gmail.com",
                )
            except Exception:
                pass
        await message.answer(
            f"✅ Пара #{couple_id} забанена",
            reply_markup=kb_back("adm:main"),
        )
    elif user_id:
        await ban_user(user_id, reason, message.from_user.id)
        try:
            await bot.send_message(
                user_id,
                f"🚫 <b>Вы забанены.</b>\n\n"
                f"Причина: {escape(reason)}\n\n"
                f"Для обжалования:\nvladgrigoryan1999@gmail.com",
            )
        except Exception:
            pass
        await message.answer(
            f"✅ Пользователь #{user_id} забанен",
            reply_markup=kb_back("adm:main"),
        )
    else:
        await message.answer("❌ Что-то не так")


# =========================================================
#  📝 ЛОГИ
# =========================================================

@router.callback_query(F.data == "adm:logs")
async def adm_logs(call: CallbackQuery):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="adm:logs_today")],
        [InlineKeyboardButton(text="📅 За неделю", callback_data="adm:logs_week")],
        [InlineKeyboardButton(text="📅 За месяц", callback_data="adm:logs_month")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:main")],
    ])
    await safe_edit(call, "📝 <b>Логи</b>\n\nВыбери период:", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("adm:logs_"))
async def adm_logs_period(call: CallbackQuery):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    period = call.data.replace("adm:logs_", "") if call.data else ""
    if period == "today":
        where = "DATE(created_at) = DATE('now')"
    elif period == "week":
        where = "created_at >= datetime('now', '-7 days')"
    else:
        where = "created_at >= datetime('now', '-30 days')"

    rows = await _fetchall(
        f"SELECT * FROM logs WHERE {where} ORDER BY id DESC LIMIT 30"
    )
    if not rows:
        await safe_edit(call, "📝 Логов нет.", reply_markup=kb_back("adm:logs"))
        await call.answer()
        return

    lines = ["📝 <b>Логи</b>\n"]
    for r in rows:
        dt = (r.get("created_at") or "")[11:16]
        desc = (r.get("description") or "")[:80]
        lines.append(f"• {dt} — {desc}")

    await safe_edit(call, "\n".join(lines), reply_markup=kb_back("adm:logs"))
    await call.answer()


# =========================================================
#  📢 НАПИСАТЬ ПАРЕ
# =========================================================

@router.callback_query(F.data.startswith("adm:write:"))
async def adm_write_couple(call: CallbackQuery, state: FSMContext):
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return
    parts = cb_parts(call)
    try:
        couple_id = int(parts[2])
    except (ValueError, IndexError):
        await call.answer()
        return
    await state.update_data(write_couple_id=couple_id)
    await state.set_state(AdminFSM.write_couple)
    await safe_edit(call, "📢 Напиши сообщение паре:")
    await call.answer()


@router.message(AdminFSM.write_couple)
async def adm_write_couple_send(message: Message, state: FSMContext):
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто")
        return
    data = await state.get_data()
    await state.clear()
    couple_id = data.get("write_couple_id")

    if not isinstance(couple_id, int):
        await message.answer("❌ Ошибка: пара не задана")
        return

    users = await _fetchall(
        "SELECT telegram_id FROM users WHERE couple_id=?", (couple_id,)
    )
    bot = message.bot
    if bot is None:
        await message.answer("❌ Бот недоступен")
        return

    sent = 0
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], text)
            sent += 1
        except Exception:
            pass
    await message.answer(
        f"✅ Отправлено: {sent}",
        reply_markup=kb_back("adm:main"),
    ) 

# =========================================================
#  🧹 ОЧИСТКА ЗАБЛОКИРОВАВШИХ
# =========================================================

@router.callback_query(F.data == "adm:cleanup")
async def adm_cleanup(call: CallbackQuery):
    """Проверяет всех юзеров через getChat. Показывает, сколько заблокировали."""
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return

    bot = call.bot
    if bot is None:
        await call.answer("Бот недоступен", show_alert=True)
        return

    # Меняем сообщение — идёт проверка
    await safe_edit(call, "⏳ <b>Проверяю пользователей...</b>\n\nЭто займёт время.")
    await call.answer()

    # Все юзеры
    users = await _fetchall("SELECT telegram_id FROM users")
    total = len(users)

    blocked: list[int] = []

    from aiogram.exceptions import TelegramForbiddenError

    for u in users:
        tg_id = u["telegram_id"]
        try:
            # Лёгкий запрос — просто проверка доступа
            await bot.get_chat(tg_id)
        except TelegramForbiddenError:
            blocked.append(tg_id)
        except Exception:
            # Другая ошибка — не считаем блокировкой
            pass

    if not blocked:
        await safe_edit(
            call,
            f"🧹 <b>Очистка</b>\n\n"
            f"Проверено: <b>{total}</b>\n"
            f"Заблокировавших: <b>0</b>\n\n"
            f"Все чисто ✅",
            reply_markup=kb_back("adm:main"),
        )
        return

    # Показываем результат — со списком ID
    lines = [
        f"🧹 <b>Очистка</b>\n",
        f"Проверено: {total}",
        f"Заблокировали: <b>{len(blocked)}</b>\n",
    ]
    # Первые 20 ID
    for tg_id in blocked[:20]:
        lines.append(f"• <code>{tg_id}</code>")
    if len(blocked) > 20:
        lines.append(f"… и ещё {len(blocked) - 20}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🗑 Удалить {len(blocked)}",
            callback_data=f"adm:cleanup_yes:{len(blocked)}",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:main")],
    ])
    # Сохраняем список в FSM (через тот же callback — сохраним во временный список)
    adm_cleanup._blocked = blocked   # type: ignore[attr-defined]

    await safe_edit(call, "\n".join(lines), reply_markup=kb)


@router.callback_query(F.data.startswith("adm:cleanup_yes:"))
async def adm_cleanup_yes(call: CallbackQuery):
    """Удаляет найденных заблокировавших."""
    if call.from_user is None or not is_admin(call.from_user.id):
        await call.answer()
        return

    blocked: list[int] = getattr(adm_cleanup, "_blocked", [])
    if not blocked:
        await call.answer("Список пуст, начни заново", show_alert=True)
        return

    deleted = 0
    for tg_id in blocked:
        try:
            # Достаём юзера
            u = await _fetchone(
                "SELECT couple_id FROM users WHERE telegram_id=?", (tg_id,)
            )
            if u is None:
                continue

            couple_id = u.get("couple_id")

            # Если есть пара — смотрим, что со вторым
            if couple_id:
                partner = await _fetchone(
                    "SELECT telegram_id FROM users "
                    "WHERE couple_id=? AND telegram_id!=?",
                    (couple_id, tg_id),
                )
                # Обнуляем второго
                if partner:
                    await _execute(
                        "UPDATE users SET couple_id=NULL WHERE telegram_id=?",
                        (partner["telegram_id"],),
                    )

                # Чистим данные пары
                for table in [
                    "gifts", "wishes", "friday_events", "movies", "dates",
                    "achievements", "avatars", "shop_items", "transactions",
                    "transfers", "settings", "question_answers", "test_answers",
                    "test_progress", "portraits", "daily_answers",
                ]:
                    try:
                        await _execute(f"DELETE FROM {table} WHERE couple_id=?", (couple_id,))
                    except Exception:
                        pass

                try:
                    await _execute("DELETE FROM couples WHERE id=?", (couple_id,))
                except Exception:
                    pass

            # Удаляем юзера и его данные
            await _execute("DELETE FROM users WHERE telegram_id=?", (tg_id,))
            await _execute("DELETE FROM purchases WHERE user_id=?", (tg_id,))
            await _execute(
                "DELETE FROM referrals WHERE user_id=? OR invited_id=?",
                (tg_id, tg_id),
            )
            deleted += 1
        except Exception as e:
            logger.warning(f"cleanup delete failed {tg_id}: {e}")

    # Очищаем временный список
    adm_cleanup._blocked = []   # type: ignore[attr-defined]

    await add_log(
        "admin_action",
        f"Очистка заблокировавших: удалено {deleted}",
        admin_id=call.from_user.id,
    )

    await safe_edit(
        call,
        f"✅ <b>Удалено: {deleted}</b>",
        reply_markup=kb_back("adm:main"),
    )
    await call.answer()