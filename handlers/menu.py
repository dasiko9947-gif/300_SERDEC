from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from config import ADMIN_ID
from utils.admin_helpers import is_admin
from keyboards import (
    kb_main_reply,
    kb_movies,
    kb_friday,
    kb_shop,
    kb_gifts_categories,
    kb_back,
)
from database import get_user, get_couple, get_partner, get_movies, _fetchone
from utils.helpers import safe_edit, send_to
router = Router()
from aiogram.fsm.context import FSMContext
# =========================================================
#  REPLY-КНОПКИ (главное меню снизу)
# =========================================================

@router.message(F.text == "🎬 Фильмы")
async def btn_movies(message: Message):
    if message.from_user is None:
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала /start")
        return

    couple = await get_couple(user["couple_id"])
    if couple is None:
        await message.answer("Пара не найдена")
        return

    movies = await get_movies(couple["id"])
    ratings = [m for m in movies if m.get("rating_a") and m.get("rating_b")]
    avg = 0.0
    if ratings:
        avg = round(
            sum((m["rating_a"] + m["rating_b"]) / 2 for m in ratings) / len(ratings),
            1,
        )

    text = (
        f"🎬 <b>Ваш список фильмов</b>\n\n"
        f"Фильмов: {len(movies)}\n"
        f"Средний балл пары: {avg}"
    )
    await message.answer(text, reply_markup=kb_movies())

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
    mode_on = bool(settings["friday_mode"]) if settings else True
    mode = "ВКЛ" if mode_on else "ВЫКЛ"

    # Считаем подряд
    events = await _fetchall(
        "SELECT status FROM friday_events WHERE couple_id=? "
        "ORDER BY created_at DESC LIMIT 500",
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
    await message.answer(text, reply_markup=kb_friday(mode_on=mode_on))

@router.message(F.text == "💰 Магазин")
async def btn_shop(message: Message):
    if message.from_user is None:
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала /start")
        return

    partner = await get_partner(user["couple_id"], message.from_user.id)
    couple = await get_couple(user["couple_id"])
    if couple is None:
        await message.answer("Пара не найдена")
        return

    partner_balance = partner["hearts_balance"] if partner else 0
    text = (
        f"💰 <b>Магазин</b>\n\n"
        f"❤️ Твой баланс: {user['hearts_balance']}\n"
        f"❤️ Баланс партнёра: {partner_balance}\n"
        f"❤️ Общий баланс пары: {couple['common_balance']}"
    )
    await message.answer(text, reply_markup=kb_shop())


@router.message(F.text == "👤 Мой профиль")
async def btn_profile(message: Message):
    from handlers.profile import render_profile_msg
    await render_profile_msg(message)


# =========================================================
#  КОМАНДЫ /help и /settings
# =========================================================

HELP_MAIN_TEXT = (
    "❓ <b>Как это работает</b>\n\n"
    "Выбери раздел:"
)

def _help_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Аватары", callback_data="help:avatars")],
        [InlineKeyboardButton(text="🏆 Рейтинг пар", callback_data="help:rating")],
        [InlineKeyboardButton(text="❤️ Сердечки", callback_data="help:hearts")],
        [InlineKeyboardButton(text="🏆 Достижения", callback_data="help:achievements")],
        [InlineKeyboardButton(text="📅 Даты", callback_data="help:dates")],
        [InlineKeyboardButton(text="🧠 Вопрос дня", callback_data="help:question")],
        [InlineKeyboardButton(text="🔗 Пригласи друга", callback_data="help:referral")],
    ])

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_MAIN_TEXT, reply_markup=_help_main_kb())

@router.callback_query(F.data == "help:main")
async def help_main(call: CallbackQuery):
    await safe_edit(call, HELP_MAIN_TEXT, reply_markup=_help_main_kb())
    await call.answer()

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    from handlers.settings import render_settings_msg
    await render_settings_msg(message)


# =========================================================
#  CALLBACK: ГЛАВНОЕ МЕНЮ (Reply-клавиатура)
# =========================================================

@router.callback_query(F.data == "menu:main")
async def cb_main(call: CallbackQuery):
    if call.from_user is None:
        return

    user = await get_user(call.from_user.id)
    balance = user["hearts_balance"] if user else 0
    text = f"🏠 <b>Главное меню</b>\n\n❤️ Твой баланс: {balance}"
    await safe_edit(call, text)
    await call.answer()


# =========================================================
#  CALLBACK: ОТКРЫТИЕ РАЗДЕЛОВ (для кнопок Назад)
# =========================================================

@router.callback_query(F.data == "menu:movies")
async def open_movies(call: CallbackQuery):
    if call.from_user is None:
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    couple = await get_couple(user["couple_id"])
    if couple is None:
        await call.answer("Пара не найдена", show_alert=True)
        return

    movies = await get_movies(couple["id"])
    ratings = [m for m in movies if m.get("rating_a") and m.get("rating_b")]
    avg = 0.0
    if ratings:
        avg = round(
            sum((m["rating_a"] + m["rating_b"]) / 2 for m in ratings) / len(ratings),
            1,
        )

    text = (
        f"🎬 <b>Ваш список фильмов</b>\n\n"
        f"Фильмов: {len(movies)}\n"
        f"Средний балл пары: {avg}"
    )
    await safe_edit(call, text, reply_markup=kb_movies())
    await call.answer()

@router.callback_query(F.data == "menu:friday")
async def open_friday(call: CallbackQuery):
    if call.from_user is None:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
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
    mode_on = bool(settings["friday_mode"]) if settings else True
    mode = "ВКЛ" if mode_on else "ВЫКЛ"

    events = await _fetchall(
        "SELECT status FROM friday_events WHERE couple_id=? "
        "ORDER BY created_at DESC LIMIT 500",
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
    await safe_edit(call, text, reply_markup=kb_friday(mode_on=mode_on))
    await call.answer()
    
@router.callback_query(F.data == "menu:shop")
async def open_shop(call: CallbackQuery):
    if call.from_user is None:
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    partner = await get_partner(user["couple_id"], call.from_user.id)
    couple = await get_couple(user["couple_id"])
    if couple is None:
        await call.answer("Пара не найдена", show_alert=True)
        return

    partner_balance = partner["hearts_balance"] if partner else 0
    text = (
        f"💰 <b>Магазин</b>\n\n"
        f"❤️ Твой баланс: {user['hearts_balance']}\n"
        f"❤️ Баланс партнёра: {partner_balance}\n"
        f"❤️ Общий баланс пары: {couple['common_balance']}"
    )
    await safe_edit(call, text, reply_markup=kb_shop())
    await call.answer()


@router.callback_query(F.data == "menu:profile")
async def open_profile(call: CallbackQuery):
    from handlers.profile import render_profile
    await render_profile(call)
    await call.answer()


@router.callback_query(F.data == "menu:settings")
async def open_settings(call: CallbackQuery):
    from handlers.settings import render_settings
    await render_settings(call)
    await call.answer()


@router.callback_query(F.data == "menu:help")
async def open_help(call: CallbackQuery):
    from texts import HELP_MAIN
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Фильмы", callback_data="help:movies")],
        [InlineKeyboardButton(text="🖤 Пятница желаний", callback_data="help:friday")],
        [InlineKeyboardButton(text="💰 Магазин", callback_data="help:shop")],
        [InlineKeyboardButton(text="🎁 Подарки", callback_data="help:gifts")],
        [InlineKeyboardButton(text="❤️ Сердечки", callback_data="help:hearts")],
    ])
    await safe_edit(call, HELP_MAIN, reply_markup=kb)
    await call.answer()


# =========================================================
#  CALLBACK: возврат к подаркам (для shop:gifts)
# =========================================================

@router.callback_query(F.data == "menu:gifts_redirect")
async def cb_gifts_redirect(call: CallbackQuery):
    await safe_edit(call, "🎁 Подарки", reply_markup=kb_gifts_categories())
    await call.answer()


# =========================================================
#  КОМАНДЫ-ШОРТКАТЫ
# =========================================================

@router.message(Command("movies"))
async def cmd_movies(message: Message):
    await btn_movies(message)


@router.message(Command("shop"))
async def cmd_shop(message: Message):
    await btn_shop(message)


@router.message(Command("friday"))
async def cmd_friday(message: Message):
    await btn_friday(message)


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    from handlers.profile import render_profile_msg
    await render_profile_msg(message)

@router.callback_query(F.data == "help:movies")
async def help_movies(call: CallbackQuery):
    await safe_edit(
        call,
        "🎬 <b>Фильмы</b>\n\n"
        "Добавляйте фильмы вместе.\n"
        "Хочешь добавить или удалить — партнёр подтверждает.\n\n"
        "После просмотра оба ставят оценку 1–10.\n"
        "Оценки видны в истории.\n\n"
        "🎬 <b>Право выбора</b> — 300 ❤️:\n"
        "• Ты выбираешь любой фильм (даже не из списка).\n"
        "• Партнёр обязан подтвердить.\n"
        "• Отказ = −100 ❤️ с его баланса.\n"
        "• Согласие = +30 ❤️ ему.\n\n"
        "За оценку — +10 ❤️.",
        reply_markup=kb_back("help:main"),
    )
    await call.answer()


@router.callback_query(F.data == "help:friday")
async def help_friday(call: CallbackQuery):
    await safe_edit(
        call,
        "🖤 <b>Пятница желаний</b>\n"
        "(пятница-развратница)\n\n"
        "Это желания 18+.\n"
        "То, что ты хочешь попробовать,\n"
        "но не знаешь, как предложить партнёру.\n\n"
        "Добавляй свои желания — анонимно.\n"
        "Партнёр их не видит.\n\n"
        "Раз в неделю бот вытянет одно желание.\n"
        "Выполните до конца воскресенья.\n\n"
        "Можно отменить (300 ❤️)\n"
        "или заменить (100 ❤️).\n\n"
        "Режим включается только по обоюдному согласию.\n"
        "За выполнение — +30 ❤️ обоим.",
        reply_markup=kb_back("help:main"),
    )
    await call.answer()


@router.callback_query(F.data == "help:shop")
async def help_shop(call: CallbackQuery):
    from handlers.shop import SHOP_HELP
    await safe_edit(call, SHOP_HELP, reply_markup=kb_back("help:main"))
    await call.answer()


@router.callback_query(F.data == "help:avatars")
async def help_avatars(call: CallbackQuery):
    await safe_edit(
        call,
        "🎨 <b>Аватары</b>\n\n"
        "Купи свой аватар:\n"
        "• Парень — 🛡 Спартанец (1000 ❤️)\n"
        "• Девушка — 🏹 Амазонка (1000 ❤️)\n\n"
        "Аватар виден в профиле.\n"
        "Ты можешь переключаться между личным и общим.\n\n"
        "Если у обоих есть аватары —\n"
        "открывается общий аватар «Пара».\n"
        "+300 сердечек каждому.",
        reply_markup=kb_back("help:main"),
    )
    await call.answer()


@router.callback_query(F.data == "help:hearts")
async def help_hearts(call: CallbackQuery):
    await safe_edit(
        call,
        "❤️ <b>Сердечки</b>\n\n"
        "Сердечки — ваша валюта.\n\n"
        "<b>Зарабатывайте:</b>\n"
        "• Вопрос дня — +5 ❤️ (совпало) / +2 ❤️ (нет)\n"
        "• Оценка фильма — +10 ❤️\n"
        "• Пятница желаний — +30 ❤️\n"
        "• Открытие «Пары» — +300 ❤️\n"
        "• Достижения — от +100 до +500 ❤️\n"
        "• Бонус на ДР — +100 ❤️\n"
        "• Бонус на годовщину — +300 ❤️\n\n"
        "<b>Покупайте:</b>\n"
        "• Комплимент — 10 ❤️\n"
        "• Подарки — 30 ❤️\n"
        "• Замена желания — 100 ❤️\n"
        "• Право выбора — 300 ❤️\n"
        "• Отмена желания — 300 ❤️\n"
        "• Аватары — 1000 ❤️\n\n"
        "<b>Пакеты:</b>\n"
        "• 300 ❤️ — 99₽ (+10%)\n"
        "• 1000 ❤️ — 249₽ (+20%)\n"
        "• 3000 ❤️ — 599₽ (+30%)\n\n"
        "🎁 Первая покупка — +30%.\n"
        "💸 Можно перевести свои сердечки\n"
        "или подарить пакет партнёру.",
        reply_markup=kb_back("help:main"),
    )
    await call.answer()


@router.callback_query(F.data == "help:achievements")
async def help_achievements(call: CallbackQuery):
    await safe_edit(
        call,
        "🏆 <b>Достижения и рейтинг</b>\n\n"
        "<b>Награды:</b>\n"
        "🎬 <b>Фильмы:</b>\n"
        "• 🎬 10 фильмов — +100 ❤️\n"
        "• 🎬 30 фильмов — +200 ❤️\n"
        "• 🎬 100 фильмов — +300 ❤️\n"
        "• 🎬 300 фильмов — +1000 ❤️\n\n"

        "🖤 <b>Пятницы:</b>\n"
        "• 🖤 4 подряд — +100 ❤️\n"
        "• 🖤 15 подряд — +200 ❤️\n"
        "• 🖤 30 подряд — +300 ❤️\n"
        "• 🖤 100 подряд — +1000 ❤️\n\n"

        "🎁 <b>Коллекция подарков:</b>\n"
        "• 🎨 Все 9 — +100 ❤️\n\n"

        "💞 <b>Общий аватар «Пара»:</b>\n"
        "• +300 ❤️ каждому\n\n"

        "<b>Статусы (от накопленных за всё время сердечек):</b>\n"
        "🌱 Первопроходцы (0–99)\n"
        "🌙 Мечтатели (100–499)\n"
        "🥈 Серебряные (500–999)\n"
        "🥇 Золотые (1000–2999)\n"
        "💠 Бриллиантовые (3000–9999)\n"
        "👑 Королевские (10000+)",
        reply_markup=kb_back("help:main"),
    )
    await call.answer()


@router.callback_query(F.data == "help:dates")
async def help_dates(call: CallbackQuery):
    await safe_edit(
        call,
        "📅 <b>Даты</b>\n\n"
        "Добавляйте важные даты.\n"
        "Бот напомнит за день до каждой.\n\n"
        "🎂 В день рождения — +100 ❤️.\n"
        "🎉 В годовщину — +300 ❤️ обоим.",
        reply_markup=kb_back("help:main"),
    )
    await call.answer()


@router.callback_query(F.data == "help:question")
async def help_question(call: CallbackQuery):
    await safe_edit(
        call,
        "🧠 <b>Вопрос дня</b>\n\n"
        "Каждый день бот задаёт вопрос.\n"
        "Вы отвечаете одновременно — и узнаёте, совпало или нет.\n\n"
        "300 вопросов — это 10 тестов по 30.\n"
        "Тесты идут от лёгких к глубоким:\n"
        "• Вкусы и мелочи\n"
        "• Досуг и юмор\n"
        "• Быт и привычки\n"
        "• Общение\n"
        "• Конфликты\n"
        "• Ценности\n"
        "• Языки любви\n"
        "• Личное пространство\n"
        "• Близость\n"
        "• Привязанность\n\n"
        "Пройдя тест, вы получаете «Портрет пары».\n\n"
        "Это не клинический тест.\n"
        "Но вопросы основаны на реальных методиках:\n"
        "5 языков любви, 7 принципов счастливого брака, типы привязанности.\n\n"
        "Так вы лучше узнаёте друг друга.",
        reply_markup=kb_back("help:main"),
    )
    await call.answer()

@router.callback_query(F.data == "help:rating")
async def help_rating(call: CallbackQuery):
    await safe_edit(
        call,
        "🏆 <b>Рейтинг пар</b>\n\n"
        "Топ-100 пар по <b>заработанному за всё время</b>.\n\n"
        "Что идёт в зачёт:\n"
        "• Вопросы дня\n"
        "• Оценки фильмов\n"
        "• Пятницы\n"
        "• Достижения\n"
        "• Покупки сердечек\n\n"
        "Открыть рейтинг: <b>/rating</b>",
        reply_markup=kb_back("help:main"),
    )
    await call.answer()

@router.callback_query(F.data == "help:referral")
async def help_referral(call: CallbackQuery):
    await safe_edit(
        call,
        "🔗 <b>Пригласи друга</b>\n\n"
        "Приведи друга → +300 ❤️ тебе и партнёру.\n\n"
        "Открой /hearts → «Пригласи друга»\n"
        "и получи свою ссылку.",
        reply_markup=kb_back("help:main"),
    )
    await call.answer()

@router.message(F.text == "🛠 Админка")
async def btn_admin(message: Message, state: FSMContext):
    if message.from_user is None:
        return
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    from handlers.admin import ADMIN_MAIN_TEXT, _admin_main_kb
    await message.answer(ADMIN_MAIN_TEXT, reply_markup=_admin_main_kb())