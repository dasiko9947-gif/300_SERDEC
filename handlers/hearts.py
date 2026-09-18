import logging
from urllib.parse import quote

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database import get_user, _fetchall
from keyboards import kb_back
from utils.helpers import safe_edit, cb_parts

logger = logging.getLogger(__name__)

router = Router()


# =========================================================
#  ГЛАВНЫЙ ЭКРАН «ПОЛУЧИТЬ СЕРДЦА»
# =========================================================

def _hearts_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔗 Пригласи друга — +300 ❤️",
            callback_data="hearts:referral",
        )],
        [InlineKeyboardButton(
            text="📢 Подпишись на канал — скоро",
            callback_data="hearts:channel",
        )],
        [InlineKeyboardButton(
            text="🎁 Другие проекты — скоро",
            callback_data="hearts:projects",
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="menu:main",
        )],
    ])


HEARTS_TEXT = (
    "❤️ <b>Получить сердца</b>\n\n"
    "Сердечки — ваша валюта в «300 Сердцах».\n"
    "Их можно зарабатывать — без реальных денег.\n\n"
    "Выбери способ:"
)


@router.message(Command("hearts"))
async def cmd_hearts(message: Message):
    await message.answer(HEARTS_TEXT, reply_markup=_hearts_kb())


@router.callback_query(F.data == "hearts:main")
async def hearts_main(call: CallbackQuery):
    await safe_edit(call, HEARTS_TEXT, reply_markup=_hearts_kb())
    await call.answer()


# =========================================================
#  🔗 ПРИГЛАСИ ДРУГА
# =========================================================

@router.callback_query(F.data == "hearts:referral")
async def hearts_referral(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    bot = call.bot
    username = "bot"
    if bot is not None:
        me = await bot.get_me()
        username = me.username or "bot"

    link = f"https://t.me/{username}?start=ref_{call.from_user.id}"

    # Считаем, сколько уже приглашено
    invited = await _fetchall(
        "SELECT invited_id FROM referrals WHERE user_id=?",
        (call.from_user.id,),
    )
    total_earned = len(invited) * 300

    text = (
        "🔗 <b>Пригласи друга</b>\n\n"
        "За каждого друга — <b>+300 ❤️</b> тебе и ему.\n"
        "Он перейдёт по ссылке — оба получите сердечки.\n\n"
        f"Твоя ссылка:\n<code>{link}</code>\n\n"
        f"📊 Уже приглашено: <b>{len(invited)}</b>\n"
        f"💰 Заработано: <b>{total_earned} ❤️</b>"
    )

    # Кодируем текст для шаринга (иначе BUTTON_URL_INVALID)
    share_text = quote("Присоединяйся к «300 Сердцам»! ❤️")
    share_url = f"https://t.me/share/url?url={link}&text={share_text}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📤 Поделиться ссылкой",
            url=share_url,
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="hearts:main")],
    ])
    await safe_edit(call, text, reply_markup=kb)
    await call.answer()


# =========================================================
#  📢 КАНАЛ (заглушка)
# =========================================================

@router.callback_query(F.data == "hearts:channel")
async def hearts_channel(call: CallbackQuery):
    await safe_edit(
        call,
        "📢 <b>Подписка на канал</b>\n\n"
        "Скоро здесь можно будет подписаться на канал\n"
        "и получить <b>+100 ❤️</b>.\n\n"
        "Следи за обновлениями ❤️",
        reply_markup=kb_back("hearts:main"),
    )
    await call.answer()


# =========================================================
#  🎁 ДРУГИЕ ПРОЕКТЫ (заглушка)
# =========================================================

@router.callback_query(F.data == "hearts:projects")
async def hearts_projects(call: CallbackQuery):
    await safe_edit(
        call,
        "🎁 <b>Другие проекты</b>\n\n"
        "Скоро здесь появятся другие боты и проекты,\n"
        "за которые можно получить сердечки.\n\n"
        "Оставайся с нами ❤️",
        reply_markup=kb_back("hearts:main"),
    )
    await call.answer()