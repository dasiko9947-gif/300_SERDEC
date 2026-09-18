from typing import Any

from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ParseMode

from datetime import datetime
from database import _fetchall
# =========================================================
#  UI
# =========================================================

async def safe_edit(call: CallbackQuery, text: str, reply_markup=None) -> None:
    """Пытается edit_text. Если нельзя (фото) — удаляет и отправляет новое."""
    bot = call.bot
    if bot is None:
        return

    msg = call.message if isinstance(call.message, Message) else None

    if msg is not None:
        try:
            await msg.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            return
        except TelegramBadRequest:
            try:
                await msg.delete()
            except Exception:
                pass
        except Exception:
            pass

    await bot.send_message(
        chat_id=call.from_user.id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


async def safe_edit_photo(call: CallbackQuery, photo_path: str, caption: str, reply_markup=None) -> None:
    """Удаляет старое сообщение и отправляет фото с подписью."""
    bot = call.bot
    if bot is None:
        return

    msg = call.message if isinstance(call.message, Message) else None
    if msg is not None:
        try:
            await msg.delete()
        except Exception:
            pass

    try:
        photo = FSInputFile(photo_path)
        await bot.send_photo(
            chat_id=call.from_user.id,
            photo=photo,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        # Если фото не отправилось — отправляем текстом
        await bot.send_message(
            chat_id=call.from_user.id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )


async def send_to(bot, chat_id: int | None, text: str, reply_markup=None) -> None:
    if bot is None or chat_id is None:
        return
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


# =========================================================
#  Callback data
# =========================================================

def cb_data(call: CallbackQuery) -> str:
    return call.data or ""


def cb_parts(call: CallbackQuery, sep: str = ":") -> list[str]:
    return cb_data(call).split(sep)


# =========================================================
#  DB
# =========================================================

def as_dict(row) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def as_dicts(rows) -> list[dict[str, Any]]:
    return [r if isinstance(r, dict) else dict(r) for r in rows]


# =========================================================
#  Keyboards
# =========================================================

def build_ikb(buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d)] for t, d in buttons]
    )


def build_grid(buttons: list[tuple[str, str]], cols: int = 2) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for b in buttons:
        row.append(InlineKeyboardButton(text=b[0], callback_data=b[1]))
        if len(row) == cols:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def safe_send_photo(
    bot,
    chat_id: int | None,
    photo_path: str,
    caption: str,
    reply_markup=None,
) -> None:
    """Отправляет фото с подписью через bot. Безопасно к None."""
    if bot is None or chat_id is None:
        return
    try:
        photo = FSInputFile(photo_path)
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        # Фоллбэк — текстом
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    
HUG_VARIANTS = [
    "🤗 {sender} крепко обнял(а) {receiver}!",
    "🫂 {sender} сжимает {receiver} в объятиях!",
    "💞 {sender} обнимает {receiver} — тепло и нежно!",
    "🤗 Крепкие объятия от {sender} для {receiver}!",
]


def hug_text(sender: str, receiver: str, idx: int) -> str:
    """Возвращает текст объятия по индексу."""
    template = HUG_VARIANTS[idx % len(HUG_VARIANTS)]
    return template.format(sender=sender, receiver=receiver)

# =========================================================
#  ДНИ ВМЕСТЕ
# =========================================================

async def days_together(couple_id: int) -> int | None:
    """
    Считает дни с начала отношений.
    Берёт дату из dates с date_type='anniversary'.
    Возвращает None, если дата не указана.
    """
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
                # Без года — берём текущий
                dt = dt.replace(year=datetime.now().year)
            return (datetime.now() - dt).days
        except ValueError:
            continue
    return None