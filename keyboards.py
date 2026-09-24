from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from config import ADMIN_ID

# =========================================================
#  ГЛАВНОЕ МЕНЮ — Reply-клавиатура
# =========================================================

from config import ADMIN_ID


def kb_main_reply(user_id: int | None = None) -> ReplyKeyboardMarkup:
    rows = [
        [
            KeyboardButton(text="🎬 Фильмы"),
            KeyboardButton(text="🖤 Пятница желаний"),
        ],
        [
            KeyboardButton(text="💰 Магазин"),
            KeyboardButton(text="👤 Мой профиль"),
        ],
    ]

    # Скрытая админ-кнопка
    if user_id is not None and user_id == ADMIN_ID:
        rows.append([KeyboardButton(text="🛠 Админка")])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери раздел...",
    )


# =========================================================
#  ИНЛАЙН-КНОПКИ (внутри разделов)
# =========================================================

def kb_back(to: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=to)]
    ])


from config import MOVIE_ARTICLE_URL


def kb_movies() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить фильм", callback_data="movie:add")],
        [InlineKeyboardButton(text="🍿 Смотрим сегодня", callback_data="movie:list")],
        [InlineKeyboardButton(text="🎬 Право выбора — 300 ❤️", callback_data="movie:right")],
        [InlineKeyboardButton(text="📜 История просмотров", callback_data="movie:history")],
        [InlineKeyboardButton(text="❓ Что это?", callback_data="movie:help")],
    ])


def kb_movie_add() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Написать своё", callback_data="movie:add_manual")],
        [InlineKeyboardButton(text="🎲 Случайный фильм", callback_data="movie:random")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:movies")],
    ])


def kb_random_movie(partner_name: str = "партнёру") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё", callback_data="movie:random")],
        [InlineKeyboardButton(
            text=f"✅ Отправить {partner_name}",
            callback_data="movie:random_send",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="movie:add")],
    ])


def kb_movie_help() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎬 Что посмотреть?",
            url=MOVIE_ARTICLE_URL,
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:movies")],
    ])


def kb_friday(mode_on: bool = True) -> InlineKeyboardMarkup:
    mode_text = "⚙️ Режим: ВКЛ" if mode_on else "⚙️ Режим: ВЫКЛ"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить желание", callback_data="friday:add")],
        [InlineKeyboardButton(text="📜 История", callback_data="friday:history")],
        [InlineKeyboardButton(text=mode_text, callback_data="friday:toggle")],
        [InlineKeyboardButton(text="❓ Что это?", callback_data="friday:help")],
    ])

def kb_shop() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Подарки", callback_data="shop:gifts")],
        [InlineKeyboardButton(text="🛠 Товары партнёра", callback_data="shop:partner_wishes")],
        [InlineKeyboardButton(text="❤️ Сердечки", callback_data="shop:buy_hearts")],
        [InlineKeyboardButton(text="❓ Что это?", callback_data="shop:help")],
    ])

def kb_gifts_categories() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ Сердца", callback_data="gift:cat:hearts")],
        [InlineKeyboardButton(text="🌹 Розы", callback_data="gift:cat:roses")],
        [InlineKeyboardButton(text="🧸 Мишки", callback_data="gift:cat:bears")],
        [InlineKeyboardButton(text="💌 Комплимент", callback_data="shop:buy_compliment")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:shop")],
    ])


def kb_confirm(action_prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"{action_prefix}:yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"{action_prefix}:no"),
        ],
    ])