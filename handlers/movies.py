from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from states import MovieFSM
from database import (
    get_user,
    get_partner,
    get_couple,
    add_movie,
    confirm_movie,
    delete_movie,
    get_movies,
    get_movie,
    spend_hearts,
    _execute,
)
from keyboards import kb_movies, kb_back, kb_confirm
from keyboards import kb_main_reply
from database import spend_hearts, add_hearts
from config import DB_PATH, MOVIE_CHOICE_COST, HEARTS_MOVIE_RATED
from texts import (
    MOVIE_ADD_PROMPT,
    MOVIE_WAIT_PARTNER,
    MOVIE_CONFIRM_REQUEST,
    MOVIE_CONFIRMED,
    MOVIE_REJECTED,
    MOVIE_HISTORY_EMPTY,
    MOVIE_HELP,
)
from utils.helpers import safe_edit, send_to, cb_parts
from utils.achievements import (
    reward_movie_rated,
    check_movie_milestones,
)
from database import spend_hearts

import aiosqlite

router = Router()


# =========================================================
#  ГЛАВНЫЙ ЭКРАН
# =========================================================

@router.callback_query(F.data == "menu:movies")
async def open_movies(call: CallbackQuery):
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


# =========================================================
#  ➕ ДОБАВИТЬ ФИЛЬМ
# =========================================================

@router.callback_query(F.data == "movie:add")
async def movie_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(MovieFSM.add_title)
    await safe_edit(call, MOVIE_ADD_PROMPT)
    await call.answer()


@router.message(MovieFSM.add_title)
async def movie_add_title(message: Message, state: FSMContext):
    if message.from_user is None:
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("Пустое название.")
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer("Сначала /start")
        return

    movie_id = await add_movie(user["couple_id"], title, message.from_user.id)
    partner = await get_partner(user["couple_id"], message.from_user.id)
    await state.clear()

    if partner is not None:
        await send_to(
            message.bot,
            partner["telegram_id"],
            MOVIE_CONFIRM_REQUEST.format(partner_name=user["name"], title=title),
            reply_markup=kb_confirm(f"movie:confirm:{movie_id}"),
        )
    await message.answer(MOVIE_WAIT_PARTNER, reply_markup=kb_movies())


@router.callback_query(F.data.startswith("movie:confirm:"))
async def movie_confirm(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 4:
        await call.answer()
        return
    try:
        movie_id = int(parts[2])
    except ValueError:
        await call.answer()
        return
    decision = parts[3]

    movie = await get_movie(movie_id)
    if movie is None:
        await call.answer("Фильм не найден", show_alert=True)
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return

    couple = await get_couple(user["couple_id"])
    if couple is None:
        await call.answer("Пара не найдена", show_alert=True)
        return

    partner = await get_partner(user["couple_id"], call.from_user.id)

    if decision == "yes":
        await confirm_movie(movie_id)
        await safe_edit(call, MOVIE_CONFIRMED.format(title=movie["title"]))
        if partner is not None:
            await send_to(
                call.bot,
                partner["telegram_id"],
                MOVIE_CONFIRMED.format(title=movie["title"]),
            )
    else:
        await delete_movie(movie_id)
        await safe_edit(call, MOVIE_REJECTED.format(title=movie["title"]))
        if partner is not None:
            await send_to(
                call.bot,
                partner["telegram_id"],
                MOVIE_REJECTED.format(title=movie["title"]),
            )
    await call.answer()


# =========================================================
#  📋 СПИСОК ФИЛЬМОВ (объединён с «Смотрим сегодня»)
# =========================================================

@router.callback_query(F.data == "movie:list")
async def movie_list(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    movies = await get_movies(user["couple_id"])
    if not movies:
        await safe_edit(
            call,
            "📋 Список пуст.\n\nДобавь первый фильм: ➕ Добавить фильм.",
            reply_markup=kb_back("menu:movies"),
        )
        await call.answer()
        return

    buttons: list[list[InlineKeyboardButton]] = []
    for m in movies[:30]:
        # Указываем средний балл, если есть
        if m.get("rating_a") and m.get("rating_b"):
            avg = (m["rating_a"] + m["rating_b"]) / 2
            label = f"🎬 {m['title']} — {avg:.1f} ⭐"
        else:
            label = f"🎬 {m['title']}"
        buttons.append([InlineKeyboardButton(
            text=label[:60],   # ограничиваем длину
            callback_data=f"movie:card:{m['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:movies")])

    await safe_edit(
        call,
        f"📋 <b>Ваши фильмы</b> ({len(movies)})\n\n"
        f"Выбери фильм — посмотреть карточку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await call.answer()


# =========================================================
#  КАРТОЧКА ФИЛЬМА
# =========================================================

@router.callback_query(F.data.startswith("movie:card:"))
async def movie_card(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        movie_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    movie = await get_movie(movie_id)
    if movie is None:
        await call.answer("Фильм не найден", show_alert=True)
        return

    # Имя того, кто добавил
    adder = await get_user(movie["added_by"])
    adder_name = adder["name"] if adder and adder.get("name") else "партнёр"

    status_map = {
        "in_list": "в списке",
        "pending": "ждёт подтверждения",
        "watched": "просмотрен",
    }
    status_text = status_map.get(movie["status"], movie["status"])

    # Средний балл, если оба поставили
    rating_text = ""
    if movie.get("rating_a") and movie.get("rating_b"):
        avg = (movie["rating_a"] + movie["rating_b"]) / 2
        rating_text = f"\n⭐ Средний балл: {avg:.1f}"

    text = (
        f"🎬 <b>«{movie['title']}»</b>\n\n"
        f"Добавил: {adder_name}\n"
        f"Статус: {status_text}"
        f"{rating_text}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🍿 Смотрим сегодня",
            callback_data=f"movie:today_pick:{movie_id}",
        )],
        [InlineKeyboardButton(
            text="🗑 Удалить",
            callback_data=f"movie:del:{movie_id}",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="movie:list")],
    ])
    await safe_edit(call, text, reply_markup=kb)
    await call.answer()


# =========================================================
#  🍿 СМОТРИМ СЕГОДНЯ (из карточки)
# =========================================================

@router.callback_query(F.data.startswith("movie:today_pick:"))
async def movie_today_pick(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        movie_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    movie = await get_movie(movie_id)
    if movie is None:
        await call.answer("Фильм не найден", show_alert=True)
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return
    partner = await get_partner(user["couple_id"], call.from_user.id)

    if partner is not None:
        await send_to(
            call.bot,
            partner["telegram_id"],
            f"{user['name']} выбрал(а) фильм на сегодня:\n\n"
            f"🎬 «{movie['title']}»\n\nПодтверди.",
            reply_markup=kb_confirm(f"movie:today_confirm:{movie_id}"),
        )

    await safe_edit(
        call,
        "Отправлено партнёру. Ждём ⏳",
        reply_markup=kb_back("movie:list"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("movie:today_confirm:"))
async def movie_today_confirm(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        movie_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    movie = await get_movie(movie_id)
    if movie is None:
        await call.answer("Фильм не найден", show_alert=True)
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return
    partner = await get_partner(user["couple_id"], call.from_user.id)

    # Фиксируем watched_at
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE movies SET watched_at=datetime('now') WHERE id=?",
            (movie_id,),
        )
        await db.commit()

    text = (
        f"✅ Отлично!\n\n"
        f"Сегодня смотрите:\n🎬 «{movie['title']}»\n\n"
        f"Приятного просмотра ❤️\n\n"
        f"Завтра в 12:00 я спрошу, как вам."
    )
    await safe_edit(call, text)
    if partner is not None:
        await send_to(
            call.bot,
            partner["telegram_id"],
            f"✅ Подтверждено!\n\nСегодня смотрите:\n🎬 «{movie['title']}»",
        )
    await call.answer()


# =========================================================
#  🗑 УДАЛЕНИЕ ФИЛЬМА
# =========================================================

@router.callback_query(F.data.startswith("movie:del:"))
async def movie_delete(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        movie_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    movie = await get_movie(movie_id)
    if movie is None:
        await call.answer("Фильм не найден", show_alert=True)
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return
    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    # Отправляем запрос партнёру
    await send_to(
        call.bot,
        partner["telegram_id"],
        f"🗑 {user['name']} хочет убрать фильм:\n\n"
        f"🎬 «{movie['title']}»\n\nУбираем(на)?",
        reply_markup=kb_confirm(f"movie:del_confirm:{movie_id}"),
    )
    await safe_edit(
        call,
        f"⏳ Запрос отправлен {partner['name']}.",
        reply_markup=kb_back("movie:list"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("movie:del_confirm:"))
async def movie_del_confirm(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 4:
        await call.answer()
        return
    try:
        movie_id = int(parts[2])
    except ValueError:
        await call.answer()
        return
    decision = parts[3]

    movie = await get_movie(movie_id)
    if movie is None:
        await call.answer("Фильм не найден", show_alert=True)
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return
    partner = await get_partner(user["couple_id"], call.from_user.id)

    if decision == "yes":
        await delete_movie(movie_id)
        await safe_edit(call, f"✅ «{movie['title']}» убрали из списка.")
        if partner is not None:
            await send_to(
                call.bot,
                partner["telegram_id"],
                f"✅ Убрали.\n«{movie['title']}» больше не в списке.",
            )
    else:
        await safe_edit(call, f"❌ Хорошо, оставляем.\n«{movie['title']}» в списке.")
        if partner is not None:
            await send_to(
                call.bot,
                partner["telegram_id"],
                f"❌ Пока оставим.\n«{movie['title']}» в списке.",
            )
    await call.answer()


# =========================================================
#  ⭐ ОЦЕНКА ФИЛЬМА
# =========================================================

@router.callback_query(F.data.startswith("movie:rate_menu:"))
async def movie_rate_menu(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        movie_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    movie = await get_movie(movie_id)
    if movie is None:
        await call.answer("Фильм не найден", show_alert=True)
        return

    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(
            text=str(i),
            callback_data=f"movie:rate:{movie_id}:{i}",
        ))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await safe_edit(
        call,
        f"Как вам фильм?\n\n🎬 <b>«{movie['title']}»</b>\n\nОцени от 1 до 10.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await call.answer()


@router.callback_query(F.data.startswith("movie:rate:"))
async def movie_rate(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 4:
        await call.answer()
        return
    try:
        movie_id = int(parts[2])
        rating = int(parts[3])
    except ValueError:
        await call.answer()
        return

    if not (1 <= rating <= 10):
        await call.answer("Оценка 1–10", show_alert=True)
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return
    couple = await get_couple(user["couple_id"])
    if couple is None:
        await call.answer()
        return

    # Определяем поле
    field = "rating_a" if call.from_user.id == couple["user_a_id"] else "rating_b"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE movies SET {field}=? WHERE id=?", (rating, movie_id))
        await db.commit()

    movie = await get_movie(movie_id)
    if movie is None:
        await call.answer()
        return

    partner = await get_partner(user["couple_id"], call.from_user.id)

    if movie.get("rating_a") is None or movie.get("rating_b") is None:
        await safe_edit(
            call,
            f"✅ Твоя оценка: {rating}/10\n\nЖдём партнёра...",
        )
        await call.answer()
        return

    # ---- Оба поставили ----
    avg = (movie["rating_a"] + movie["rating_b"]) / 2
    await reward_movie_rated(couple["user_a_id"], couple["user_b_id"])

    text = (
        f"🎬 <b>«{movie['title']}»</b>\n\n"
        f"{movie['rating_a']}/10 и {movie['rating_b']}/10\n"
        f"Средний балл пары: <b>{avg:.1f}</b>\n\n"
        f"+{HEARTS_MOVIE_RATED} ❤️ каждому!"
    )

    new_ach = await check_movie_milestones(
        couple["id"], couple["user_a_id"], couple["user_b_id"]
    )
    if new_ach:
        text += "\n\n🏆 <b>Новые достижения:</b>\n" + "\n".join(new_ach)

    await safe_edit(call, text)
    if partner is not None:
        await send_to(call.bot, partner["telegram_id"], text)
    await call.answer()


# =========================================================
#  📜 ИСТОРИЯ ПРОСМОТРОВ
# =========================================================

@router.callback_query(F.data == "movie:history")
async def movie_history(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    movies = await get_movies(user["couple_id"])
    rated = [m for m in movies if m.get("rating_a") and m.get("rating_b")]
    if not rated:
        await safe_edit(call, MOVIE_HISTORY_EMPTY, reply_markup=kb_back("menu:movies"))
        await call.answer()
        return

    lines = ["📜 <b>История просмотров</b>\n"]
    for i, m in enumerate(rated[:15], 1):
        avg = (m["rating_a"] + m["rating_b"]) / 2
        lines.append(f"{i}. «{m['title']}» — {avg:.1f} ⭐")
        lines.append(f"   {m['rating_a']}/10 · {m['rating_b']}/10")

    if rated:
        best = max(rated, key=lambda x: (x["rating_a"] + x["rating_b"]) / 2)
        worst = min(rated, key=lambda x: (x["rating_a"] + x["rating_b"]) / 2)
        best_avg = (best["rating_a"] + best["rating_b"]) / 2
        worst_avg = (worst["rating_a"] + worst["rating_b"]) / 2
        lines.append("")
        lines.append(f"🏆 Лучший: «{best['title']}» — {best_avg:.1f}")
        lines.append(f"💩 Худший: «{worst['title']}» — {worst_avg:.1f}")

    await safe_edit(call, "\n".join(lines), reply_markup=kb_back("menu:movies"))
    await call.answer()


# =========================================================
#  🎬 ПРАВО ВЫБОРА
# =========================================================
@router.callback_query(F.data == "movie:right")
async def movie_right(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    # Показываем карточку без проверки баланса — проверим на следующем шаге
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Купить за {MOVIE_CHOICE_COST} ❤️",
            callback_data="movie:right_buy",
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:movies")],
    ])

    text = (
        f"🎬 <b>Право выбора</b>\n\n"
        f"💰 Цена: <b>{MOVIE_CHOICE_COST} ❤️</b> (с твоего баланса)\n\n"
        f"<b>Что это даёт:</b>\n"
        f"• Ты выбираешь любой фильм на сегодня\n"
        f"  (даже если его нет в списке)\n"
        f"• Партнёр обязан подтвердить\n\n"
        f"<b>Если партнёр откажется:</b>\n"
        f"• С его баланса сгорит 100 ❤️\n\n"
        f"<b>Если партнёр согласится:</b>\n"
        f"• Получит +30 ❤️\n\n"
        f"У тебя сейчас: {user['hearts_balance']} ❤️"
    )

    await safe_edit(call, text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "movie:right_buy")
async def movie_right_buy(call: CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    # Проверяем баланс только сейчас
    if user["hearts_balance"] < MOVIE_CHOICE_COST:
        shortage = MOVIE_CHOICE_COST - user["hearts_balance"]
        await call.answer(
            f"❌ Недостаточно сердечек\n\n"
            f"Нужно: {MOVIE_CHOICE_COST} ❤️\n"
            f"У тебя: {user['hearts_balance']} ❤️\n"
            f"Не хватает: {shortage} ❤️\n\n"
            f"Заработай: /hearts",
            show_alert=True,
        )
        return

    await state.set_state(MovieFSM.right_title)
    await safe_edit(
        call,
        f"🎬 <b>Право выбора</b>\n\n"
        f"Напиши название фильма, который хочешь посмотреть сегодня.\n\n"
        f"Можно любой — даже если его нет в списке.",
        reply_markup=kb_back("menu:movies"),
    )
    await call.answer()
    
@router.message(MovieFSM.right_title)
async def movie_right_title(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    title = (message.text or "").strip()
    if not title:
        await message.answer("Напиши название фильма.")
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer("Сначала /start")
        return

    # Списываем с A
    ok = await spend_hearts(message.from_user.id, MOVIE_CHOICE_COST)
    if not ok:
        await state.clear()
        await message.answer("Недостаточно сердечек.")
        return

    partner = await get_partner(user["couple_id"], message.from_user.id)
    await state.clear()

    if partner is None:
        await message.answer("Партнёр не найден.")
        return

    # Отправляем B
    await send_to(
        message.bot,
        partner["telegram_id"],
        f"🎬 <b>{user['name']} использует «Право выбора»</b>\n\n"
        f"Сегодня смотрите:\n🎬 «{title}»\n\n"
        f"Подтверждаешь?\n\n"
        f"⚠️ Если откажешься — с <b>твоего</b> баланса сгорит 100 ❤️.\n"
        f"✅ Если согласишься — получишь +30 ❤️.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Смотрю",
                    callback_data=f"movie:right_yes:{message.from_user.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отказаться",
                    callback_data=f"movie:right_no:{message.from_user.id}",
                ),
            ],
        ]),
    )

    await message.answer(
        f"✅ Отправлено {partner['name']}.\n\nЖдём ⏳",
        reply_markup=kb_main_reply(),
    )


@router.callback_query(F.data.startswith("movie:right_yes:"))
async def movie_right_yes(call: CallbackQuery):
    parts = cb_parts(call)
    # movie:right_yes:<from_id>
    if len(parts) < 3:
        await call.answer()
        return
    try:
        from_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    me = await get_user(call.from_user.id)
    if me is None:
        await call.answer()
        return

    # +30 согласившемуся
    from database import add_hearts
    await add_hearts(call.from_user.id, 30)

    text = (
        f"✅ <b>Отлично!</b>\n\n"
        f"Сегодня смотрим вместе.\n\n"
        f"+30 ❤️ тебе за поддержку ❤️"
    )
    await safe_edit(call, text)
    await send_to(
        call.bot,
        from_id,
        f"✅ {me['name']} — за!\n\nПриятного просмотра!",
    )


@router.callback_query(F.data.startswith("movie:right_no:"))
async def movie_right_no(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        from_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    me = await get_user(call.from_user.id)
    if me is None:
        await call.answer()
        return

    # Списываем 100 ❤️ с B (или всё, что есть)
    PENALTY = 100
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT hearts_balance FROM users WHERE telegram_id=?",
            (call.from_user.id,),
        ) as cur:
            row = await cur.fetchone()
        current = row["hearts_balance"] if row else 0
        burn = min(PENALTY, current)

        if burn > 0:
            await db.execute(
                "UPDATE users SET hearts_balance = hearts_balance - ? "
                "WHERE telegram_id=?",
                (burn, call.from_user.id),
            )
            await db.commit()

    text = (
        f"❌ <b>Ты против.</b>\n\n"
        f"С твоего баланса сгорело <b>{burn} ❤️</b>."
    )
    await safe_edit(call, text)
    await send_to(
        call.bot,
        from_id,
        f"❌ {me['name']} против.\n\n",
    )
    await call.answer()

# =========================================================
#  ❓ ЧТО ЭТО?
# =========================================================

@router.callback_query(F.data == "movie:help")
async def movie_help(call: CallbackQuery):
    await safe_edit(call, MOVIE_HELP, reply_markup=kb_back("menu:movies"))
    await call.answer()