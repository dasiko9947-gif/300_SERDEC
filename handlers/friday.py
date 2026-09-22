from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from states import WishFSM
from database import (
    get_user,
    get_couple,
    get_partner,
    spend_hearts,
    _fetchone,
    _fetchall,
    _execute,
)
from keyboards import kb_friday, kb_back
from config import CANCEL_WISH_COST, REPLACE_WISH_COST, DB_PATH
from texts import (
    WISH_ADD_PROMPT,
    WISH_ADDED,
    FRIDAY_HELP,
)
from utils.helpers import safe_edit, send_to, cb_parts
from utils.achievements import (
    reward_friday_done,
    check_friday_milestones,
)

import aiosqlite

router = Router()


@router.callback_query(F.data == "friday:add")
async def friday_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(WishFSM.add_text)
    await safe_edit(call, WISH_ADD_PROMPT)
    await call.answer()


@router.message(WishFSM.add_text)
async def friday_add_text(message: Message, state: FSMContext):
    if message.from_user is None:
        await state.clear()
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer("Сначала /start")
        return

    text = (message.text or "").strip()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO wishes (couple_id, text, author_id) VALUES (?, ?, ?)",
            (user["couple_id"], text, message.from_user.id),
        )
        await db.commit()
    await state.clear()
    await message.answer(WISH_ADDED, reply_markup=kb_friday())


@router.callback_query(F.data == "friday:help")
async def friday_help(call: CallbackQuery):
    await safe_edit(
        call,
        "🖤 <b>Пятница желаний</b>\n"
        "(пятница-развратница)\n\n"
        "Это желания 18+.\n"
        "То, что ты хочешь попробовать,\n"
        "но не знаешь, как предложить партнёру.\n\n"
        "Добавляй свои желания — анонимно.\n"
        "Партнёр их не видит.\n\n"
        "Включайте режим Пятницы —\n"
        "и добро пожаловать в пятницу-развратницу.\n\n"

        "Каждую пятницу бот вытянет одно желание.\n"
        "Выполните до конца воскресенья.\n\n"

        "<b>Кнопки:</b>\n"
        "• ✅ <b>Принято</b> — желание засчитано\n"
        "• ➕ <b>Добавить своё</b> — пополнить кувшин\n"
        "• ⏭ <b>Отмена</b> — 300 ❤️, желание сгорает\n"
        "• 🔄 <b>Замена</b> — 100 ❤️, выпадет другое\n\n"

        "Режим включается только по обоюдному согласию.\n"
        "За выполнение — +30 ❤️ обоим.",
        reply_markup=kb_back("menu:friday"),
    )
    await call.answer()


@router.callback_query(F.data == "friday:toggle")
async def friday_toggle(call: CallbackQuery):
    """
    Логика идентична настройкам:
    - ВКЛ → нужно согласие обоих
    - ВЫКЛ → можно одному
    """
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    settings = await _fetchone(
        "SELECT friday_mode FROM settings WHERE couple_id=?",
        (user["couple_id"],),
    )
    current = settings["friday_mode"] if settings else 1

    # ---- ВЫКЛ — один может без согласия ----
    if current == 1:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE settings SET friday_mode=0 WHERE couple_id=?",
                (user["couple_id"],),
            )
            await db.commit()

        await safe_edit(
            call,
            "🖤 Режим Пятницы <b>ВЫКЛЮЧЕН</b>.\n\n"
            "Партнёр получит уведомление.",
            reply_markup=kb_back("menu:friday"),
        )

        # Уведомляем партнёра
        partner = await get_partner(user["couple_id"], call.from_user.id)
        if partner is not None:
            await send_to(
                call.bot,
                partner["telegram_id"],
                f"🖤 {user['name']} выключил(а) режим Пятницы желаний.",
            )
        await call.answer()
        return

    # ---- ВКЛ — нужно согласие обоих ----
    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    await send_to(
        call.bot,
        partner["telegram_id"],
        f"🖤 {user['name']} хочет <b>включить</b> режим Пятницы желаний.\n\n"
        f"Раз в неделю бот будет вытягивать одно желание из кувшина.\n\n"
        f"Поддержишь?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да",
                    callback_data=f"set:friday:accept:{call.from_user.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Нет",
                    callback_data=f"set:friday:reject:{call.from_user.id}",
                ),
            ],
        ]),
    )
    await safe_edit(
        call,
        f"⏳ Запрос на включение отправлен {partner['name']}.",
        reply_markup=kb_back("menu:friday"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("friday:cancel:"))
async def friday_cancel(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        event_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    if user["hearts_balance"] < CANCEL_WISH_COST:
        await call.answer("Недостаточно сердечек", show_alert=True)
        return

    ok = await spend_hearts(call.from_user.id, CANCEL_WISH_COST)
    if not ok:
        await call.answer("Недостаточно сердечек", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE friday_events SET status='cancelled' WHERE id=?",
            (event_id,),
        )
        await db.commit()

    await safe_edit(call, f"⏭ Желание отменено. Сгорело {CANCEL_WISH_COST} ❤️")
    await call.answer()


@router.callback_query(F.data.startswith("friday:replace:"))
async def friday_replace(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        event_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    ok = await spend_hearts(call.from_user.id, REPLACE_WISH_COST)
    if not ok:
        await call.answer("Недостаточно сердечек", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE friday_events SET wish_text='💆 Массаж 15 минут', is_bot_wish=1 WHERE id=?",
            (event_id,),
        )
        await db.commit()

    await safe_edit(call, "🔄 Желание заменено. Выпало: 💆 Массаж 15 минут")
    await call.answer()


@router.callback_query(F.data == "friday:history")
async def friday_history(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    from database import _fetchall
    events = await _fetchall(
        "SELECT wish_text, status, created_at FROM friday_events "
        "WHERE couple_id=? ORDER BY created_at DESC LIMIT 20",
        (user["couple_id"],),
    )

    if not events:
        await safe_edit(
            call,
            "📜 История Пятниц\n\nПока пусто.",
            reply_markup=kb_back("menu:friday"),
        )
        await call.answer()
        return

    status_map = {
        "done": "✅ выполнено",
        "cancelled": "⏭ отменено",
        "replaced": "🔄 заменено",
        "active": "⏳ активно",
    }

    lines = ["📜 <b>История Пятниц</b>\n"]
    for e in events:
        dt = (e["created_at"] or "")[:10]
        status = status_map.get(e["status"], e["status"])
        text = (e["wish_text"] or "")[:40]
        lines.append(f"• {dt} — {status}")
        lines.append(f"  «{text}»")

    # Считаем «подряд»
    streak = 0
    for e in events:
        if e["status"] == "done":
            streak += 1
        else:
            break

    lines.append("")
    lines.append(f"Пятниц подряд: <b>{streak}</b>")

    await safe_edit(call, "\n".join(lines), reply_markup=kb_back("menu:friday"))
    await call.answer()

@router.message(F.text == "🖤 Пятница желаний")
async def btn_friday(message: Message):
    if message.from_user is None:
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала /start")
        return

    from database import _fetchone, _fetchall
    count_row = await _fetchone(
        "SELECT COUNT(*) AS c FROM wishes WHERE couple_id=? AND status='active'",
        (user["couple_id"],),
    )
    c = count_row["c"] if count_row else 0

    settings = await _fetchone(
        "SELECT friday_mode FROM settings WHERE couple_id=?",
        (user["couple_id"],),
    )
    mode = "ВКЛ" if (settings and settings["friday_mode"]) else "ВЫКЛ"

    # Считаем подряд
    events = await _fetchall(
        "SELECT status FROM friday_events WHERE couple_id=? "
        "ORDER BY created_at DESC LIMIT 50",
        (user["couple_id"],),
    )
    streak = 0
    for e in events:
        if e["status"] == "done":
            streak += 1
        else:
            break

    text = (
        f"🖤 <b>Пятница желаний</b>\n(пятница-развратница)\n\n"
        f"Режим: {mode}\n"
        f"Желаний в кувшине: {c}\n"
        f"Пятниц подряд: {streak}"
    )
    await message.answer(text, reply_markup=kb_friday())

@router.callback_query(F.data.startswith("friday:accept:"))
async def friday_accept(call: CallbackQuery):
    """Пользователь подтверждает участие в Пятнице (не выполнение)."""
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        event_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    couple = await get_couple(user["couple_id"])
    if couple is None:
        await call.answer("Пара не найдена", show_alert=True)
        return

    # Получаем событие
    event = await _fetchone(
        "SELECT * FROM friday_events WHERE id=?", (event_id,)
    )
    if event is None:
        await call.answer("Событие не найдено", show_alert=True)
        return

    if event["status"] != "active":
        await call.answer("Уже обработано", show_alert=True)
        return

    # Определяем, кто это
    is_a = call.from_user.id == couple["user_a_id"]
    field = "user_a_accepted" if is_a else "user_b_accepted"

    # Уже подтвердил?
    if event[field]:
        await call.answer("Ты уже подтвердил(а)", show_alert=True)
        return

    # Обновляем
    await _execute(
        f"UPDATE friday_events SET {field}=1 WHERE id=?",
        (event_id,),
    )

    partner = await get_partner(user["couple_id"], call.from_user.id)

    # Пересматриваем событие
    event2 = await _fetchone(
        "SELECT * FROM friday_events WHERE id=?", (event_id,)
    )
    if event2 is None:
        await call.answer("Ошибка: событие пропало", show_alert=True)
        return

    both_accepted = bool(event2["user_a_accepted"]) and bool(event2["user_b_accepted"])

    if both_accepted:
        # Оба приняли — ждём понедельника
        text = (
            "✅ <b>Принято!</b>\n\n"
            "У вас есть время до конца воскресенья.\n"
            "В понедельник я спрошу, выполнили или нет."
        )
        await safe_edit(call, text)
        if partner is not None:
            await send_to(call.bot, partner["telegram_id"], text)
    else:
        await safe_edit(
            call,
            "✅ Ты принял(а).\n\nЖдём партнёра ⏳",
        )
        if partner is not None:
            await send_to(
                call.bot,
                partner["telegram_id"],
                f"🖤 {user['name']} принял(а) Пятницу!\n\n"
                f"Подтверди тоже, чтобы продолжить.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✅ Принято",
                        callback_data=f"friday:accept:{event_id}",
                    )],
                ]),
            )
    await call.answer()

@router.callback_query(F.data.startswith("friday:done:"))
async def friday_done(call: CallbackQuery):
    """Один из партнёров подтвердил выполнение."""
    parts = cb_parts(call)
    try:
        event_id = int(parts[2])
    except (ValueError, IndexError):
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return
    couple = await get_couple(user["couple_id"])
    if couple is None:
        await call.answer()
        return

    event = await _fetchone(
        "SELECT * FROM friday_events WHERE id=?", (event_id,)
    )
    if event is None:
        await call.answer()
        return

    if event["status"] != "active":
        await call.answer("Уже обработано", show_alert=True)
        return

    is_a = call.from_user.id == couple["user_a_id"]
    field = "user_a_done" if is_a else "user_b_done"

    await _execute(
        f"UPDATE friday_events SET {field}=1 WHERE id=?",
        (event_id,),
    )

    event = await _fetchone(
        "SELECT * FROM friday_events WHERE id=?", (event_id,)
    )
    if event is None:
        await call.answer()
        return

    partner = await get_partner(user["couple_id"], call.from_user.id)

    both_done = bool(event["user_a_done"]) and bool(event["user_b_done"])

    if both_done:
        # Проверяем, что ещё не начисляли
        if event["status"] != "done":
            await _execute(
                "UPDATE friday_events SET status='done' WHERE id=?",
                (event_id,),
            )
            await reward_friday_done(couple["user_a_id"], couple["user_b_id"])

            text = (
                "🖤 <b>Пятница засчитана!</b>\n\n"
                "+30 ❤️ каждому. Так держать ❤️"
            )
            await safe_edit(call, text)
            if partner is not None:
                await send_to(call.bot, partner["telegram_id"], text)
        else:
            await safe_edit(call, "✅ Уже засчитано")
    else:
        await safe_edit(call, "✅ Ждём партнёра ⏳")
        if partner is not None:
            await send_to(
                call.bot,
                partner["telegram_id"],
                f"✅ {user['name']} подтвердил(а), что Пятница выполнена.\n\n"
                f"Подтверди тоже.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Да",
                            callback_data=f"friday:done:{event_id}",
                        ),
                        InlineKeyboardButton(
                            text="❌ Нет",
                            callback_data=f"friday:not_done:{event_id}",
                        ),
                    ],
                ]),
            )
    await call.answer()


@router.callback_query(F.data.startswith("friday:not_done:"))
async def friday_not_done(call: CallbackQuery):
    """Один из партнёров сказал, что не выполнено → Пятница не засчитана."""
    parts = cb_parts(call)
    try:
        event_id = int(parts[2])
    except (ValueError, IndexError):
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return

    await _execute(
        "UPDATE friday_events SET status='failed' WHERE id=?",
        (event_id,),
    )
    await safe_edit(
        call,
        "❌ Пятница не засчитана.\n\nВ следующий раз получится!",
    )
    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is not None:
        await send_to(
            call.bot,
            partner["telegram_id"],
            f"❌ {user['name']} отметил(а), что не выполнено.\n\n"
            "Пятница не засчитана.",
        )
    await call.answer()