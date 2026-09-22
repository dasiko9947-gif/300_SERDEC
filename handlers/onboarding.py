from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from states import Onboarding
from database import (
    get_user,
    create_user,
    update_user,
    create_couple,
    join_couple,
    get_couple,
    _fetchone,
    _execute,
    add_hearts,
)
from keyboards import kb_main_reply
from utils.helpers import safe_edit, send_to, cb_parts

router = Router()


# =========================================================
#  ГОРОДА И ЧАСОВЫЕ ПОЯСА (11 поясов РФ)
# =========================================================

CITIES: list[tuple[str, str]] = [
    ("🌍 Калининград (UTC+2)", "Europe/Kaliningrad"),
    ("🏛 Москва (UTC+3)", "Europe/Moscow"),
    ("🌆 Самара (UTC+4)", "Europe/Samara"),
    ("⛰ Екатеринбург (UTC+5)", "Asia/Yekaterinburg"),
    ("🌲 Омск (UTC+6)", "Asia/Omsk"),
    ("🌃 Красноярск (UTC+7)", "Asia/Krasnoyarsk"),
    ("🕌 Иркутск (UTC+8)", "Asia/Irkutsk"),
    ("🌊 Чита (UTC+9)", "Asia/Chita"),
    ("⚓ Владивосток (UTC+10)", "Asia/Vladivostok"),
    ("🌋 Магадан (UTC+11)", "Asia/Magadan"),
    ("❄ Анадырь (UTC+12)", "Asia/Anadyr"),
]


# =========================================================
#  ТЕКСТЫ
# =========================================================

START_A = (
    "Привет! 👋\n\n"
    "Я бот для пар — 300 СЕРДЕЦ ❤️ .\n"
    "Помогу вам с фильмами, желаниями и сюрпризами.\n\n"
    "Давай познакомимся."
)

Q_NAME = "Как тебя зовут?"
Q_GENDER = "Ты — парень или девушка?"
Q_START_DATE = (
    "Когда вы начали встречаться?\n\n"
    "Напиши дату в формате <b>ДД.ММ.ГГГГ</b>.\n"
    "Если не хочешь указывать — пропусти."
)
Q_TZ = "⏰ В каком городе ты живёшь?\nОт этого зависит время уведомлений."

FINAL_A = (
    "Готово, {name}! 🎉\n\n"
    "Отправь эту ссылку партнёру:\n\n{link}\n\n"
    "Как только подключится — я тебе скажу."
)

WELCOME_TEXT = (
    "🎉 <b>Добро пожаловать в 300 СЕРДЕЦ!</b>\n\n"
    "Я бот для пар. Помогаю укреплять отношения\n"
    "через игру, ритуалы и сюрпризы.\n\n"
    "<b>Что здесь есть:</b>\n\n"
    "🎬 <b>Фильмы</b> — выбирайте вместе, ставьте оценки.\n\n"
    "🖤 <b>Пятница желаний</b> — анонимные желания 18+.\n"
    "Раз в неделю — одно. Выполняете до воскресенья.\n\n"
    "💰 <b>Магазин</b> — подарки, аватары, товары партнёра.\n\n"
    "👤 <b>Профиль</b> — статус, достижения.\n\n"
    "❤️ <b>Сердечки</b> — зарабатывайте за действия.\n"
    "Покупайте за реальные деньги.\n\n"
    "❓ <b>Вопрос дня</b> — каждый день новый.\n"
    "Совпадёте — получите сердечки.\n\n"
    "Приятного пользования ❤️"
)


# =========================================================
#  КЛАВИАТУРЫ
# =========================================================

def skip_btn() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="onb_skip")]
    ])


def gender_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Парень", callback_data="gender:m")],
        [InlineKeyboardButton(text="👩 Девушка", callback_data="gender:f")],
    ])


def tz_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for label, code in CITIES:
        row.append(InlineKeyboardButton(text=label, callback_data=f"tz:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


# =========================================================
#  /start С deep-link (партнёр B + рефералка)
# =========================================================

@router.message(CommandStart(deep_link=True))
async def start_with_link(message: Message, command: CommandObject, state: FSMContext):
    if message.from_user is None:
        return

    payload = command.args or ""

    # ---- Реферальная ссылка ----
    if payload.startswith("ref_"):
        try:
            referrer_id = int(payload.split("_", 1)[1])
        except (IndexError, ValueError):
            return

        # Награда рефереру и новому
        await add_hearts(referrer_id, 300)
        await add_hearts(message.from_user.id, 300)

        await send_to(
            message.bot,
            referrer_id,
            "🎉 <b>Твой друг подключился!</b>\n\n+300 ❤️ на баланс.",
        )

        # Запишем в referrals
        await _execute(
            "INSERT INTO referrals (user_id, invited_id) VALUES (?, ?)",
            (referrer_id, message.from_user.id),
        )

        await message.answer(
            "🎉 Добро пожаловать!\n\n"
            "+300 ❤️ на баланс за то, что ты пришёл по ссылке друга.\n\n"
            "Давай начнём знакомство.\n\n" + Q_NAME
        )
        await state.set_state(Onboarding.name)
        return

    # ---- Пара (couple_<id>) ----
    if not payload.startswith("couple_"):
        return

    try:
        couple_id = int(payload.split("_", 1)[1])
    except (IndexError, ValueError):
        return

    await state.clear()

    user = await get_user(message.from_user.id)
    if user is not None and user["couple_id"] == couple_id:
        await message.answer("Ты уже в этой паре ❤️")
        return

    couple = await get_couple(couple_id)
    if couple is None or couple["status"] != "pending":
        await message.answer("Эта ссылка уже недействительна.")
        return

    await state.update_data(couple_id=couple_id)
    await state.set_state(Onboarding.name)

    a_user = await _fetchone(
        "SELECT * FROM users WHERE telegram_id=?",
        (couple["user_a_id"],),
    )
    a_name = "твой партнёр"
    if a_user is not None:
        a_name = a_user.get("name") or a_name

    await message.answer(
        f"Привет! 👋\n\n"
        f"Меня создал(а) {a_name}, чтобы ваши отношения стали ещё лучше.\n\n"
        f"Давай знакомиться.\n\n" + Q_NAME
    )


# =========================================================
#  /start ОБЫЧНЫЙ (партнёр A)
# =========================================================

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    user = await get_user(message.from_user.id)

    # Уже в паре — не перезаписываем!
    if user is not None and user["couple_id"]:
        couple = await get_couple(user["couple_id"])
        if couple is not None and couple["status"] == "active":
            await message.answer("Ты уже в паре ❤️", reply_markup=kb_main_reply(user_id=message.from_user.id))
            return
        if couple is not None and couple["status"] == "pending":
            bot = message.bot
            username = "bot"
            if bot is not None:
                me = await bot.get_me()
                username = me.username or "bot"
            link = f"https://t.me/{username}?start=couple_{couple['id']}"
            await message.answer(
                f"⏳ Ждём твою половинку.\n\n"
                f"Отправь ей ссылку:\n{link}",
                reply_markup=kb_main_reply(user_id=message.from_user.id),
            )
            return

    if user is None:
        await create_user(message.from_user.id)

    await state.set_state(Onboarding.name)
    await message.answer(START_A)
    await message.answer(Q_NAME)


# =========================================================
#  ШАГ 1: ИМЯ
# =========================================================

@router.message(Onboarding.name)
async def onb_name(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    name = (message.text or "").strip() or "Партнёр"
    await state.update_data(name=name)

    data = await state.get_data()
    couple_id = data.get("couple_id")

    # B — по ссылке
    if couple_id is not None:
        user = await get_user(message.from_user.id)
        if user is None:
            await create_user(message.from_user.id)
        await update_user(message.from_user.id, name=name)
        await state.set_state(Onboarding.gender)
        await message.answer(Q_GENDER, reply_markup=gender_kb())
        return

    # A — обычный онбординг
    await state.set_state(Onboarding.gender)
    await message.answer(Q_GENDER, reply_markup=gender_kb())


# =========================================================
#  ШАГ 2: ПОЛ
# =========================================================

@router.callback_query(F.data.startswith("gender:"))
async def onb_gender(call: CallbackQuery, state: FSMContext):
    if call.from_user is None:
        return

    parts = cb_parts(call)
    gender = parts[1] if len(parts) > 1 else "m"
    await state.update_data(gender=gender)

    data = await state.get_data()
    couple_id = data.get("couple_id")

    # =========================================================
    #  ЭТО B — пришёл по ссылке
    # =========================================================
    if couple_id is not None:
        await update_user(call.from_user.id, gender=gender)

        # Копируем TZ от A
        a_user = await _fetchone(
            "SELECT * FROM users WHERE telegram_id="
            "(SELECT user_a_id FROM couples WHERE id=?)",
            (couple_id,),
        )
        if a_user is not None and a_user.get("tz"):
            await update_user(call.from_user.id, tz=a_user["tz"])

        await join_couple(couple_id, call.from_user.id)

        a_name = a_user["name"] if a_user and a_user.get("name") else "партнёр"

        # ---- УВЕДОМЛЕНИЕ АДМИНУ ----
        from utils.admin_helpers import notify_admin
        a_id = a_user["telegram_id"] if a_user else "?"
        a_n = a_user["name"] if a_user and a_user.get("name") else "?"
        b_id = call.from_user.id
        b_n = call.from_user.full_name or "?"
        try:
            await notify_admin(
                call.bot,
                f"🎉 <b>Новая пара зарегистрирована!</b>\n\n"
                f"👤 A: {a_n} — <code>{a_id}</code>\n"
                f"👤 B: {b_n} — <code>{b_id}</code>\n"
                f"🆔 Couple ID: <code>{couple_id}</code>",
            )
        except Exception:
            pass

        await state.clear()

        await safe_edit(
            call,
            f"Отлично! Теперь вы с {a_name} вместе ❤️",
        )

        bot = call.bot
        if bot is not None:
            await bot.send_message(
                call.from_user.id,
                "Главное меню:",
                reply_markup=kb_main_reply(user_id=call.from_user.id),
            )
            await bot.send_message(call.from_user.id, WELCOME_TEXT)

        # Уведомить A (без повторного WELCOME_TEXT)
        if a_user is not None and a_user.get("telegram_id") is not None:
            await send_to(
                call.bot,
                a_user["telegram_id"],
                "🎉 <b>Твоя половинка подключилась!</b>\n\n"
                "Открой главное меню и начните пользоваться 👇",
            )

        await call.answer()
        return

    # =========================================================
    #  ЭТО A — обычный онбординг
    # =========================================================
    await state.set_state(Onboarding.start_date)
    await safe_edit(call, Q_START_DATE, reply_markup=skip_btn())
    await call.answer()

# =========================================================
#  ШАГ 3: ДАТА НАЧАЛА ОТНОШЕНИЙ (A, можно пропустить)
# =========================================================

@router.callback_query(F.data == "onb_skip")
async def onb_skip(call: CallbackQuery, state: FSMContext):
    cur = await state.get_state()
    if cur == Onboarding.start_date.state:
        await state.update_data(start_date=None)
        await state.set_state(Onboarding.tz)
        await safe_edit(call, Q_TZ, reply_markup=tz_kb())
    await call.answer()


@router.message(Onboarding.start_date)
async def onb_start_date(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    value = (message.text or "").strip()
    await state.update_data(start_date=value)
    await state.set_state(Onboarding.tz)
    await message.answer(Q_TZ, reply_markup=tz_kb())


# =========================================================
#  ШАГ 4: ЧАСОВОЙ ПОЯС + ФИНАЛ
# =========================================================

@router.callback_query(F.data.startswith("tz:"))
async def onb_tz(call: CallbackQuery, state: FSMContext):
    if call.from_user is None:
        return

    parts = cb_parts(call)
    tz = parts[1] if len(parts) > 1 else "Europe/Moscow"
    await state.update_data(tz=tz)

    # Только A
    bot = call.bot
    username = "bot"
    if bot is not None:
        me = await bot.get_me()
        username = me.username or "bot"

    data = await state.get_data()
    await update_user(
        call.from_user.id,
        name=data.get("name"),
        partner_name=data.get("name"),
        gender=data.get("gender", "m"),
        tz=tz,
    )
    new_couple_id = await create_couple(call.from_user.id)

    start_date = data.get("start_date")
    if start_date:
        await _execute(
            "INSERT INTO dates (couple_id, title, date, remind, date_type, owner_id) "
            "VALUES (?, 'Годовщина отношений', ?, 1, 'anniversary', ?)",
            (new_couple_id, start_date, call.from_user.id),
        )

    link = f"https://t.me/{username}?start=couple_{new_couple_id}"
    await state.clear()

    await safe_edit(
        call,
        FINAL_A.format(name=data.get("name"), link=link),
    )

    if bot is not None:
        await bot.send_message(
            call.from_user.id,
            "Как только партнёр подключится — я пришлю уведомление.",
            reply_markup=kb_main_reply(user_id=call.from_user.id),
        )
        await bot.send_message(call.from_user.id, WELCOME_TEXT)

    await call.answer()