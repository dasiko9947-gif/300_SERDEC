from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from states import SettingsFSM
from database import (
    get_user,
    get_couple,
    get_partner,
    update_user,
    _fetchone,
    _fetchall,
    _execute,
)
from keyboards import kb_back
from utils.helpers import safe_edit, send_to, cb_parts

import aiosqlite
from config import DB_PATH

router = Router()

DATE_TYPES = [
    ("🎂 Мой день рождения", "birthday"),
    ("💞 Годовщина отношений", "anniversary"),
    ("📅 Другая дата", "other"),
]
# =========================================================
#  ГЛАВНЫЙ ЭКРАН НАСТРОЕК
# =========================================================

def _settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Даты", callback_data="set:dates")],
        [InlineKeyboardButton(text="✏️ Твоё имя", callback_data="set:nick")],
        [InlineKeyboardButton(text="🕐 Время уведомлений", callback_data="set:time")],
        [InlineKeyboardButton(text="🖤 Режим Пятницы", callback_data="set:friday")],
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="set:notify")],
        [InlineKeyboardButton(text="🗑 Удалить пару", callback_data="set:delete_pair")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
    ])


SETTINGS_TEXT = "⚙️ <b>Настроить бота</b>\n\nВыбери раздел:"


@router.callback_query(F.data == "menu:settings")
async def render_settings(call: CallbackQuery):
    await safe_edit(call, SETTINGS_TEXT, reply_markup=_settings_kb())
    await call.answer()


async def render_settings_msg(message: Message):
    await message.answer(SETTINGS_TEXT, reply_markup=_settings_kb())


# =========================================================
#  📅 ДАТЫ
# =========================================================
@router.callback_query(F.data == "set:dates")
async def set_dates(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    rows = await _fetchall(
        "SELECT id, title, date, remind, date_type FROM dates "
        "WHERE couple_id=? ORDER BY date",
        (user["couple_id"],),
    )

    lines = ["📅 <b>Ваши даты</b>\n"]
    if not rows:
        lines.append("Пока ничего нет.")
    else:
        for i, r in enumerate(rows, 1):
            bell = "🔔" if r.get("remind") else "🔕"
            dtype = r.get("date_type") or "other"
            icon = {"birthday": "🎂", "anniversary": "💞", "other": "📅"}.get(dtype, "📅")
            lines.append(f"{i}. {bell} {icon} {r['title']} — {r['date']}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить дату", callback_data="set:dates:add")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="set:dates:del")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:settings")],
    ])
    await safe_edit(call, "\n".join(lines), reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "set:dates:add")
async def dates_add(call: CallbackQuery, state: FSMContext):
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"date_type:{key}")]
        for label, key in DATE_TYPES
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="set:dates")])

    await safe_edit(
        call,
        "📅 <b>Какой это тип даты?</b>\n\n"
        "🎂 <b>День рождения</b> — +100 ❤️ партнёру в этот день.\n"
        "💞 <b>Годовщина</b> — +300 ❤️ вам обоим.\n"
        "📅 <b>Другая</b> — без бонуса, только напоминание.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await call.answer()

@router.callback_query(F.data.startswith("date_type:"))
async def dates_type_selected(call: CallbackQuery, state: FSMContext):
    parts = cb_parts(call)
    date_type = parts[1] if len(parts) > 1 else "other"

    await state.update_data(date_type=date_type)

    # Для других дат название задаёт пользователь, для дней рождения/годовщин — подставим
    if date_type == "birthday":
        await state.set_state(SettingsFSM.add_date_value)
        await safe_edit(
            call,
            "🎂 <b>День рождения партнёра</b>\n\n"
            "Напиши дату в формате <b>ДД.ММ</b>.\n"
            "Например: 14.03",
        )
    elif date_type == "anniversary":
        await state.set_state(SettingsFSM.add_date_value)
        await safe_edit(
            call,
            "💞 <b>Годовщина отношений</b>\n\n"
            "Напиши дату в формате <b>ДД.ММ</b> или <b>ДД.ММ.ГГГГ</b>.\n"
            "Например: 12.06.2023",
        )
    else:
        await state.set_state(SettingsFSM.add_date_title)
        await safe_edit(
            call,
            "📅 <b>Другая дата</b>\n\nНапиши название даты:",
        )
    await call.answer()

@router.message(SettingsFSM.add_date_title)
async def dates_add_title(message: Message, state: FSMContext):
    if message.from_user is None:
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(date_title=title)
    await state.set_state(SettingsFSM.add_date_value)
    await message.answer(
        "📅 Теперь напиши дату в формате <b>ДД.ММ</b> или <b>ДД.ММ.ГГГГ</b>."
    )

@router.message(SettingsFSM.add_date_value)
async def dates_add_value(message: Message, state: FSMContext):
    if message.from_user is None:
        return
    value = (message.text or "").strip()

    user = await get_user(message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer("Сначала /start")
        return

    data = await state.get_data()
    date_type = data.get("date_type", "other")
    title = data.get("date_title")

    # Автоназвания для birthday / anniversary
    my_name = user.get("name") or "меня"
    if date_type == "birthday":
        title = title or f"День рождения {my_name}"
    elif date_type == "anniversary":
        title = title or "Годовщина отношений"
    else:
        title = title or "Дата"

    await state.clear()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO dates (couple_id, title, date, remind, date_type, owner_id) "
            "VALUES (?, ?, ?, 1, ?, ?)",
            (user["couple_id"], title, value, date_type, message.from_user.id),
        )
        await db.commit()

    # Показываем подтверждение с указанием бонуса
    bonus_text = ""
    if date_type == "birthday":
        bonus_text = "\n\n🎂 +100 ❤️ партнёру в этот день."
    elif date_type == "anniversary":
        bonus_text = "\n\n💞 +300 ❤️ вам обоим в этот день."

    await message.answer(f"✅ Добавлено: <b>{title}</b> — {value}{bonus_text}")

@router.callback_query(F.data == "set:dates:del")
async def dates_del(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    rows = await _fetchall(
        "SELECT id, title, date FROM dates WHERE couple_id=?",
        (user["couple_id"],),
    )
    if not rows:
        await call.answer("Нет дат для удаления", show_alert=True)
        return

    buttons: list[list[InlineKeyboardButton]] = []
    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {r['title']} ({r['date']})",
                callback_data=f"set:dates:del:{r['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="set:dates")])
    await safe_edit(
        call,
        "🗑 <b>Выбери дату для удаления</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await call.answer()


@router.callback_query(F.data.startswith("set:dates:del:"))
async def dates_del_one(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 4:
        await call.answer()
        return
    try:
        date_id = int(parts[3])
    except ValueError:
        await call.answer()
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM dates WHERE id=?", (date_id,))
        await db.commit()

    await safe_edit(
        call,
        "✅ Дата удалена.",
        reply_markup=kb_back("set:dates"),
    )
    await call.answer()


# =========================================================
#  ✏️ ОБРАЩЕНИЕ К ПАРТНЁРУ
# =========================================================
@router.callback_query(F.data == "set:nick")
async def set_nick(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    current = user.get("name") or "—"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить", callback_data="set:nick:edit")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:settings")],
    ])
    await safe_edit(
        call,
        f"✏️ <b>Твоё имя</b>\n\nСейчас: <b>{current}</b>\n\n"
        f"Партнёр увидит новое имя везде.",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data == "set:nick:edit")
async def set_nick_edit(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsFSM.edit_nick)
    await safe_edit(call, "✏️ Напиши новое имя:")
    await call.answer()


@router.message(SettingsFSM.edit_nick)
async def set_nick_save(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    value = (message.text or "").strip()
    if not value or len(value) > 50:
        await message.answer("Имя должно быть от 1 до 50 символов.")
        return

    await update_user(message.from_user.id, name=value)
    await state.clear()

    await message.answer(f"✅ Твоё имя обновлено: <b>{value}</b>")
# =========================================================
#  🕐 ВРЕМЯ УВЕДОМЛЕНИЙ
# =========================================================

@router.callback_query(F.data == "set:time")
async def set_time(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    settings = await _fetchone(
        "SELECT question_time, friday_time FROM settings WHERE couple_id=?",
        (user["couple_id"],),
    )
    q_time = settings["question_time"] if settings else "10:00"
    f_time = settings["friday_time"] if settings else "18:00"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"❓ Вопрос дня — {q_time}",
            callback_data="set:time:q",
        )],
        [InlineKeyboardButton(
            text=f"🖤 Пятница — {f_time}",
            callback_data="set:time:f",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:settings")],
    ])
    await safe_edit(
        call,
        "🕐 <b>Время уведомлений</b>\n\n"
        "Выбери, во сколько присылать.\n"
        "Только целые часы: <b>10:00</b>, <b>11:00</b>, <b>18:00</b>.",
        reply_markup=kb,
    )
    await call.answer()

@router.callback_query(F.data == "set:time:q")
async def set_time_question(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsFSM.edit_time)
    await state.update_data(time_field="question_time")
    await safe_edit(
        call,
        "❓ <b>Во сколько присылать вопрос дня?</b>\n\n"
        "Напиши в формате <b>ЧЧ:00</b>.\n"
        "Например: <b>10:00</b> или <b>20:00</b>.",
    )
    await call.answer()

@router.callback_query(F.data == "set:time:f")
async def set_time_friday(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsFSM.edit_time)
    await state.update_data(time_field="friday_time")
    await safe_edit(
        call,
        "🖤 <b>Во сколько напоминать о Пятнице?</b>\n\n"
        "Напиши в формате <b>ЧЧ:00</b>.\n"
        "Например: <b>10:00</b> или <b>18:00</b>.",
    )
    await call.answer()


@router.message(SettingsFSM.edit_time)
async def set_time_save(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    raw = (message.text or "").strip()

    # Проверка формата ЧЧ:00
    valid = False
    value = ""

    if len(raw) == 5 and raw[2] == ":":
        hh = raw[:2]
        mm = raw[3:]
        if hh.isdigit() and mm == "00":
            h = int(hh)
            if 0 <= h <= 23:
                valid = True
                value = f"{h:02d}:00"

    if not valid:
        await message.answer(
            "❌ Неверный формат.\n\n"
            "Напиши так: <b>10:00</b> или <b>18:00</b>.\n"
            "Только целые часы."
        )
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer("Сначала /start")
        return

    data = await state.get_data()
    field = data.get("time_field", "question_time")
    await state.clear()

    await _execute(
        f"UPDATE settings SET {field}=? WHERE couple_id=?",
        (value, user["couple_id"]),
    )

    name = "Вопрос дня" if field == "question_time" else "Пятница"
    await message.answer(f"✅ {name}: <b>{value}</b>")


# =========================================================
#  🔔 УВЕДОМЛЕНИЯ
# =========================================================

@router.callback_query(F.data == "set:notify")
async def set_notify(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    settings = await _fetchone(
        "SELECT notifications FROM settings WHERE couple_id=?",
        (user["couple_id"],),
    )
    enabled = bool(settings["notifications"]) if settings else True

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{'✅ ВКЛ' if enabled else '❌ ВЫКЛ'} — переключить",
            callback_data="set:notify:toggle",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:settings")],
    ])
    await safe_edit(
        call,
        "🔔 <b>Уведомления</b>\n\n"
        "Сюда входят:\n"
        "• ❓ Вопрос дня\n"
        "• 📅 Напоминания о датах\n"
        "• 🖤 Напоминание о Пятнице\n"
        "• 🎁 Сюрпризы и подарки\n\n"
        f"Сейчас: <b>{'ВКЛ' if enabled else 'ВЫКЛ'}</b>",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data == "set:notify:toggle")
async def set_notify_toggle(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    settings = await _fetchone(
        "SELECT notifications FROM settings WHERE couple_id=?",
        (user["couple_id"],),
    )
    current = settings["notifications"] if settings else 1
    new_val = 0 if current else 1

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE settings SET notifications=? WHERE couple_id=?",
            (new_val, user["couple_id"]),
        )
        await db.commit()

    await safe_edit(
        call,
        f"🔔 Уведомления: {'ВКЛ' if new_val else 'ВЫКЛ'}",
        reply_markup=kb_back("set:notify"),
    )
    await call.answer()


# =========================================================
#  🖤 РЕЖИМ ПЯТНИЦЫ
# =========================================================

@router.callback_query(F.data == "set:friday")
async def set_friday(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    settings = await _fetchone(
        "SELECT friday_mode FROM settings WHERE couple_id=?",
        (user["couple_id"],),
    )
    enabled = bool(settings["friday_mode"]) if settings else True

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{'✅ ВКЛ' if enabled else '❌ ВЫКЛ'} — переключить",
            callback_data="set:friday:toggle",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:settings")],
    ])
    await safe_edit(
        call,
        "🖤 <b>Режим Пятницы желаний</b>\n\n"
        "Раз в неделю вы получаете одно желание.\n\n"
        "⚠️ <b>Включить</b> можно только по обоюдному согласию.\n"
        "<b>Выключить</b> может любой партнёр в одиночку.\n\n"
        f"Сейчас: <b>{'ВКЛ' if enabled else 'ВЫКЛ'}</b>",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data == "set:friday:toggle")
async def set_friday_toggle(call: CallbackQuery):
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
            "Партнёр увидит это при следующем открытии.",
            reply_markup=kb_back("set:friday"),
        )
        # Уведомим партнёра
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
        f"Хочешь?",
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
        f"⏳ Запрос на включение отправлен {user['partner_name']}.",
        reply_markup=kb_back("set:friday"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("set:friday:accept:"))
async def set_friday_accept(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 4:
        await call.answer()
        return
    try:
        from_id = int(parts[3])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE settings SET friday_mode=1 WHERE couple_id=?",
            (user["couple_id"],),
        )
        await db.commit()

    await safe_edit(call, "✅ Режим Пятницы <b>ВКЛЮЧЁН</b>. Приятных пятниц!")
    await send_to(
        call.bot,
        from_id,
        f"✅ {user['name']} не против. Режим Пятницы <b>ВКЛЮЧЁН</b>.",
    )
    await call.answer()


@router.callback_query(F.data.startswith("set:friday:reject:"))
async def set_friday_reject(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 4:
        await call.answer()
        return
    try:
        from_id = int(parts[3])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return

    await safe_edit(call, "❌ Ты против. Режим остаётся ВЫКЛ.")
    await send_to(
        call.bot,
        from_id,
        f"❌ {user['name']} против. Режим остаётся ВЫКЛ.",
    )
    await call.answer()


# =========================================================
#  🗑 УДАЛЕНИЕ ПАРЫ
# =========================================================

@router.callback_query(F.data == "set:delete_pair")
async def set_delete_pair(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🗑 Да, удалить всё",
            callback_data="set:delete_pair:confirm",
        )],
        [InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="menu:settings",
        )],
    ])
    await safe_edit(
        call,
        "🗑 <b>Удалить пару</b>\n\n"
        "⚠️ Это действие <b>необратимо</b>:\n\n"
        "• Удалятся оба аккаунта\n"
        "• Удалятся все фильмы, желания, подарки\n"
        "• Удалятся даты и настройки\n"
        "• Сердечки сгорят\n\n"
        "Партнёр получит уведомление.\n\n"
        "Точно удалить?",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data == "set:delete_pair:confirm")
async def set_delete_pair_confirm(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return

    couple_id = user["couple_id"]
    partner = await get_partner(couple_id, call.from_user.id)

    # Собираем оба telegram_id
    tg_ids = [call.from_user.id]
    if partner is not None:
        tg_ids.append(partner["telegram_id"])

    # Уведомим партнёра
    if partner is not None:
        await send_to(
            call.bot,
            partner["telegram_id"],
            "💔 Пара удалена.\n\n"
            "Все данные стёрты.\n"
            "Если захотите начать заново — /start.",
        )

    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Удаляем всё, что по couple_id
        tables_by_couple = [
            "gifts",
            "wishes",
            "friday_events",
            "movies",
            "dates",
            "achievements",
            "avatars",
            "shop_items",
            "transactions",
            "transfers",
            "settings",
            "question_answers",
            "test_answers",
            "test_progress",
            "portraits",
            "daily_answers",
        ]
        for table in tables_by_couple:
            try:
                await db.execute(
                    f"DELETE FROM {table} WHERE couple_id=?", (couple_id,)
                )
            except Exception as e:
                import logging
                logging.warning(f"delete_pair: skip {table}: {e}")

        # 2. Purchases — по user_id обоих
        for tg_id in tg_ids:
            await db.execute("DELETE FROM purchases WHERE user_id=?", (tg_id,))

        # 3. Referrals — по user_id / invited_id
        for tg_id in tg_ids:
            await db.execute(
                "DELETE FROM referrals WHERE user_id=? OR invited_id=?",
                (tg_id, tg_id),
            )

        # 4. Обнуляем пользователей
        await db.execute(
            "UPDATE users SET couple_id=NULL, hearts_balance=0, total_earned=0, "
            "avatar_pref='auto' WHERE couple_id=?",
            (couple_id,),
        )

        # 5. Удаляем пару
        await db.execute("DELETE FROM couples WHERE id=?", (couple_id,))

        await db.commit()

    await safe_edit(
        call,
        "💔 Пара удалена.\n\n"
        "Все данные стёрты.\n"
        "Чтобы начать заново — /start.",
    )
    await call.answer()