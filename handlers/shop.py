from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
import aiosqlite
from config import DB_PATH
from states import ShopFSM
from database import (
    get_user,
    get_partner,
    get_couple,
    spend_hearts,
    add_hearts,
    _fetchall,
    _execute,
)
from keyboards import kb_shop, kb_back
from config import MOVIE_CHOICE_COST, SURPRISE_COST, COMPLIMENT_COST
from config import (
    MOVIE_CHOICE_COST,
    SURPRISE_COST,
    COMPLIMENT_COST,
    PACKAGES,
    get_package,
    calc_bonus,
)
from utils.helpers import safe_edit, send_to, cb_parts, hug_text

router = Router()

SHOP_HELP = (
    "💰 <b>Магазин</b>\n\n"
    "🎁 <b>Подарки</b> — 9 подарков партнёру, комплимент.\n"
    "🛠 <b>Товары партнёра</b> — создай услугу, заработай сердечки.\n"
    "❤️ <b>Сердечки</b> — купи, подари, переведи.\n\n"
    "Сердечки сгорают на подарках.\n"
    "Сердечки идут партнёру на товарах партнёра."
)

# =========================================================
#  СПРАВКА
# =========================================================

@router.callback_query(F.data == "shop:help")
async def shop_help(call: CallbackQuery):
    await safe_edit(call, SHOP_HELP, reply_markup=kb_back("menu:shop"))
    await call.answer()


# =========================================================
#  ОФИЦИАЛЬНЫЕ ТОВАРЫ
# =========================================================

@router.callback_query(F.data == "shop:official")
async def shop_official(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🎬 Право выбора фильма — {MOVIE_CHOICE_COST} ❤️",
            callback_data="shop:buy_movie_choice",
        )],
        [InlineKeyboardButton(
            text=f"🎁 Сюрприз партнёру — {SURPRISE_COST} ❤️",
            callback_data="shop:buy_surprise",
        )],
        [InlineKeyboardButton(
            text=f"💌 Комплимент партнёру — {COMPLIMENT_COST} ❤️",
            callback_data="shop:buy_compliment",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:shop")],
    ])
    await safe_edit(
        call,
        "🏪 <b>Официальные товары</b>\n\nСердечки сгорают.",
        reply_markup=kb,
    )
    await call.answer()

# =========================================================
#  КОМПЛИМЕНТ (не анонимный, от партнёра)
# =========================================================

@router.callback_query(F.data == "shop:buy_compliment")
async def buy_compliment(call: CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return
    if user["hearts_balance"] < COMPLIMENT_COST:
        await call.answer("Недостаточно сердечек", show_alert=True)
        return

    partner_name = user.get("partner_name") or "партнёра"

    await state.set_state(ShopFSM.compliment_text)
    await safe_edit(
        call,
        f"💌 <b>Комплимент для {partner_name}</b>\n\n"
        f"Цена: {COMPLIMENT_COST} ❤️\n\n"
        f"Напиши комплимент — партнёр его получит.",
    )
    await call.answer()


@router.message(ShopFSM.compliment_text)
async def compliment_text(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer("Сначала /start")
        return

    ok = await spend_hearts(message.from_user.id, COMPLIMENT_COST)
    if not ok:
        await state.clear()
        await message.answer("Недостаточно сердечек")
        return

    partner = await get_partner(user["couple_id"], message.from_user.id)
    text = (message.text or "").strip()
    partner_name = user.get("partner_name") or "партнёр"
    await state.clear()

    if partner is not None:
        kb_reply = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤗 Обнять",
                    callback_data=f"compliment:hug:{message.from_user.id}",
                ),
                InlineKeyboardButton(
                    text="💌 Ответить комплиментом",
                    callback_data="shop:buy_compliment",
                ),
            ],
        ])
        await send_to(
            message.bot,
            partner["telegram_id"],
            f"💌 <b>{user['name']} пишет тебе:</b>\n\n«{text}»",
            reply_markup=kb_reply,
        )
    await message.answer(
        f"✅ Комплимент отправлен: {partner_name}.",
        reply_markup=kb_shop(),
    )


@router.callback_query(F.data.startswith("compliment:hug:"))
async def compliment_hug(call: CallbackQuery):
    """Ответ на комплимент — обнять отправителя."""
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        to_user_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    me = await get_user(call.from_user.id)
    if me is None:
        await call.answer()
        return

    partner = await get_partner(me["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    import random
    text = hug_text(me["name"], partner["name"], random.randint(0, 3))

    await send_to(call.bot, to_user_id, text)
    await call.answer("Обнимаю ❤️")


# =========================================================
#  СЮРПРИЗ ПАРТНЁРУ
# =========================================================

@router.callback_query(F.data == "shop:buy_surprise")
async def buy_surprise(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return
    if user["hearts_balance"] < SURPRISE_COST:
        await call.answer("Недостаточно сердечек", show_alert=True)
        return

    ok = await spend_hearts(call.from_user.id, SURPRISE_COST)
    if not ok:
        await call.answer("Ошибка списания", show_alert=True)
        return

    partner = await get_partner(user["couple_id"], call.from_user.id)

    if partner is not None:
        await send_to(
            call.bot,
            partner["telegram_id"],
            f"🎁 <b>{user['name']} купил(а) сюрприз!</b>\n\n"
            f"Ты должен(на):\n\n💆 Массаж 15 минут",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Выполнено", callback_data="surprise:done"),
                    InlineKeyboardButton(text="❌ Отказаться", callback_data="surprise:refuse"),
                ],
            ]),
        )
    await safe_edit(
        call,
        "✅ Сюрприз отправлен! Сердечки сгорели.",
        reply_markup=kb_back("menu:shop"),
    )
    await call.answer()


# =========================================================
#  ПОКУПКА СЕРДЕЧЕК
# =========================================================
@router.callback_query(F.data == "shop:buy_hearts")
async def buy_hearts_menu(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    from database import _fetchall
    purchases = await _fetchall(
        "SELECT id FROM purchases WHERE user_id=? LIMIT 1",
        (call.from_user.id,),
    )
    is_first = len(purchases) == 0

    extra = ""
    if is_first:
        extra = "\n\n🎁 <b>Первая покупка!</b>\n+30% к любому пакету."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❤️ Купить новые",
            callback_data="hearts:buy",
        )],
        [InlineKeyboardButton(
            text="💸 Перевести свои",
            callback_data="hearts:transfer",
        )],
        [InlineKeyboardButton(
            text="🎁 Подарить партнёру",
            callback_data="hearts:gift",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:shop")],
    ])

    await safe_edit(
        call,
        f"❤️ <b>Сердечки</b>\n\n"
        f"Твой баланс: {user['hearts_balance']} ❤️\n\n"
        f"Что хочешь сделать?{extra}",
        reply_markup=kb,
    )
    await call.answer()

@router.callback_query(F.data == "hearts:buy")
async def hearts_buy(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    from database import _fetchall
    purchases = await _fetchall(
        "SELECT id FROM purchases WHERE user_id=? LIMIT 1",
        (call.from_user.id,),
    )
    is_first = len(purchases) == 0

    rows: list[list[InlineKeyboardButton]] = []
    for pkg in PACKAGES:
        hearts = pkg["hearts"]
        price = pkg["price"]
        bonus_percent, total = calc_bonus(hearts, is_first)
        bonus_hearts = total - hearts
        text = f"{hearts} ❤️ — {price}₽ (+{bonus_hearts} бонус)"
        rows.append([InlineKeyboardButton(
            text=text,
            callback_data=f"pay:{hearts}",
        )])

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:buy_hearts")])

    extra = ""
    if is_first:
        extra = "\n\n🎁 <b>Первая покупка!</b> +30% к любому пакету."

    await safe_edit(
        call,
        f"❤️ <b>Купить сердечки</b>\n\nВыбери пакет:{extra}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await call.answer()

@router.callback_query(F.data == "hearts:transfer")
async def hearts_transfer(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    balance = user["hearts_balance"]
    if balance < 100:
        await safe_edit(
            call,
            f"💸 <b>Перевести свои</b>\n\n"
            f"У тебя: {balance} ❤️\n\n"
            f"Минимум для перевода — 100 ❤️.",
            reply_markup=kb_back("shop:buy_hearts"),
        )
        await call.answer()
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="100 ❤️", callback_data="tr:100")],
        [InlineKeyboardButton(text="300 ❤️", callback_data="tr:300")],
        [InlineKeyboardButton(text="500 ❤️", callback_data="tr:500")],
        [InlineKeyboardButton(text="✏️ Своё", callback_data="tr:custom")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:buy_hearts")],
    ])
    await safe_edit(
        call,
        f"💸 <b>Перевести свои</b>\n\n"
        f"У тебя: {balance} ❤️\n"
        f"Перевести для {partner['name']}:",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data.startswith("tr:"))
async def transfer_amount(call: CallbackQuery, state: FSMContext):
    parts = cb_parts(call)
    action = parts[1] if len(parts) > 1 else ""

    if action == "custom":
        await state.set_state(ShopFSM.transfer_amount)
        await safe_edit(
            call,
            "✏️ Сколько перевести?\n\nНапиши число (от 100 до 10000).",
        )
        await call.answer()
        return

    try:
        amount = int(action)
    except ValueError:
        await call.answer()
        return

    await _show_transfer_confirm(call, amount)
    await call.answer()


@router.message(ShopFSM.transfer_amount)
async def transfer_amount_text(message: Message, state: FSMContext):
    if message.from_user is None:
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Напиши число.")
        return
    amount = int(text)
    if amount < 100 or amount > 10000:
        await message.answer("Сумма от 100 до 10000.")
        return
    await state.clear()

    user = await get_user(message.from_user.id)
    if user is None:
        return
    partner = await get_partner(user["couple_id"], message.from_user.id)
    if partner is None:
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Перевести {amount} ❤️",
            callback_data=f"tr_confirm:{amount}",
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="hearts:transfer")],
    ])
    await message.answer(
        f"💸 Перевести <b>{amount} ❤️</b> для {partner['name']}?\n\n"
        f"У тебя: {user['hearts_balance']} ❤️",
        reply_markup=kb,
    )


async def _show_transfer_confirm(call: CallbackQuery, amount: int):
    user = await get_user(call.from_user.id)
    if user is None:
        return
    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        return

    if user["hearts_balance"] < amount:
        await call.answer(
            f"Нужно {amount} ❤️ — у тебя {user['hearts_balance']}",
            show_alert=True,
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Перевести {amount} ❤️",
            callback_data=f"tr_confirm:{amount}",
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="hearts:transfer")],
    ])
    await safe_edit(
        call,
        f"💸 Перевести <b>{amount} ❤️</b> для {partner['name']}?\n\n"
        f"У тебя: {user['hearts_balance']} ❤️",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("tr_confirm:"))
async def transfer_confirm(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 2:
        await call.answer()
        return
    try:
        amount = int(parts[1])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer()
        return
    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer()
        return

    # Списываем с себя
    ok = await spend_hearts(call.from_user.id, amount)
    if not ok:
        await call.answer("Недостаточно сердечек", show_alert=True)
        return

    # Начисляем партнёру
    await add_hearts(partner["telegram_id"], amount)

    # Лог
    await _execute(
        "INSERT INTO transfers (couple_id, from_user, to_user, amount, reason) "
        "VALUES (?, ?, ?, ?, 'manual')",
        (user["couple_id"], call.from_user.id, partner["telegram_id"], amount),
    )

    user_after = await get_user(call.from_user.id)
    new_balance = user_after["hearts_balance"] if user_after else 0

    await safe_edit(
        call,
        f"✅ <b>Переведено!</b>\n\n"
        f"{partner['name']} получил(а) {amount} ❤️.\n"
        f"Твой баланс: {new_balance} ❤️",
        reply_markup=kb_back("menu:shop"),
    )

    await send_to(
        call.bot,
        partner["telegram_id"],
        f"💸 <b>{user['name']} перевёл(а) тебе {amount} ❤️!</b>",
    )
    await call.answer()

@router.callback_query(F.data == "hearts:gift")
async def hearts_gift(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return
    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    from database import _fetchall
    purchases = await _fetchall(
        "SELECT id FROM purchases WHERE user_id=? LIMIT 1",
        (call.from_user.id,),
    )
    is_first = len(purchases) == 0

    rows: list[list[InlineKeyboardButton]] = []
    for pkg in PACKAGES:
        hearts = pkg["hearts"]
        price = pkg["price"]
        bonus_percent, total = calc_bonus(hearts, is_first)
        bonus_hearts = total - hearts
        text = f"{hearts} ❤️ — {price}₽ (+{bonus_hearts} бонус)"
        rows.append([InlineKeyboardButton(
            text=text,
            callback_data=f"pay_gift:{hearts}",
        )])

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:buy_hearts")])

    extra = ""
    if is_first:
        extra = "\n\n🎁 <b>Первая покупка!</b> +30%."

    await safe_edit(
        call,
        f"🎁 <b>Подарить сердечки</b>\n\n"
        f"Пакет уйдёт {partner['name']}.{extra}\n\n"
        f"Выбери пакет:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await call.answer()

@router.callback_query(F.data.startswith("pay:"))
async def pay_pack(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 2:
        await call.answer()
        return
    try:
        hearts = int(parts[1])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    pkg = get_package(hearts)
    if pkg is None:
        await call.answer("Пакет не найден", show_alert=True)
        return

    from database import _fetchall
    purchases = await _fetchall(
        "SELECT id FROM purchases WHERE user_id=? LIMIT 1",
        (call.from_user.id,),
    )
    is_first = len(purchases) == 0

    bonus_percent, total = calc_bonus(hearts, is_first)
    price = pkg["price"]

    first_line = "🎁 <b>Первая покупка!</b>\n" if is_first else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплатить", callback_data=f"pay_confirm:{hearts}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="hearts:buy")],
    ])
    await safe_edit(
        call,
        f"❤️ Пакет: <b>{hearts} ❤️</b>\n"
        f"Цена: {price}₽\n\n"
        f"{first_line}"
        f"Бонус: +{bonus_percent}% = +{total - hearts} ❤️\n"
        f"Итого: <b>{total} ❤️</b>\n\n"
        f"Перейти к оплате?",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data.startswith("pay_gift:"))
async def pay_gift(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 2:
        await call.answer()
        return
    try:
        hearts = int(parts[1])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    pkg = get_package(hearts)
    if pkg is None:
        await call.answer("Пакет не найден", show_alert=True)
        return

    from database import _fetchall
    purchases = await _fetchall(
        "SELECT id FROM purchases WHERE user_id=? LIMIT 1",
        (call.from_user.id,),
    )
    is_first = len(purchases) == 0
    bonus_percent, total = calc_bonus(hearts, is_first)
    price = pkg["price"]

    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    first_line = "🎁 <b>Первая покупка!</b>\n" if is_first else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплатить", callback_data=f"pay_gift_confirm:{hearts}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="hearts:gift")],
    ])
    await safe_edit(
        call,
        f"🎁 Подарок: <b>{hearts} ❤️</b> → {partner['name']}\n"
        f"Цена: {price}₽\n\n"
        f"{first_line}"
        f"Бонус: +{bonus_percent}% = +{total - hearts} ❤️\n"
        f"Итого: <b>{total} ❤️</b>\n\n"
        f"Перейти к оплате?",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data.startswith("pay_confirm:"))
async def pay_confirm(call: CallbackQuery):
    """Обычная покупка — сердечки себе."""
    parts = cb_parts(call)
    if len(parts) < 2:
        await call.answer()
        return
    try:
        hearts = int(parts[1])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    pkg = get_package(hearts)
    if pkg is None:
        await call.answer("Пакет не найден", show_alert=True)
        return

    from database import _fetchall, _execute
    purchases = await _fetchall(
        "SELECT id FROM purchases WHERE user_id=? LIMIT 1",
        (call.from_user.id,),
    )
    is_first = len(purchases) == 0
    bonus_percent, total = calc_bonus(hearts, is_first)

    from utils.yookassa import create_payment
    result = await create_payment(
        amount_rub=pkg["price"],
        description=f"Пакет {hearts} ❤️ — 300 Сердец",
        user_id=call.from_user.id,
        recipient_id=None,
        hearts_amount=total,
        package=hearts,
        bonus_percent=bonus_percent,
        is_first=is_first,
    )

    if result is None:
        await call.answer("Ошибка оплаты", show_alert=True)
        return

    # Сохраняем платёж
    await _execute(
        "INSERT INTO payments_log "
        "(yookassa_id, user_id, recipient_id, hearts, package, bonus_percent, is_first, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
        (
            result["yookassa_id"], call.from_user.id, call.from_user.id,
            total, hearts, bonus_percent, 1 if is_first else 0,
        ),
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=result["confirmation_url"])],
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"pay_check:{result['yookassa_id']}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="shop:buy_hearts")],
    ])
    await safe_edit(
        call,
        f"❤️ <b>Пакет: {hearts} ❤️</b>\n"
        f"Цена: {pkg['price']}₽\n\n"
        f"Бонус: +{bonus_percent}% = +{total - hearts} ❤️\n"
        f"Итого: <b>{total} ❤️</b>\n\n"
        f"1. Нажми «Оплатить»\n"
        f"2. Оплати\n"
        f"3. Вернись в бота и нажми «✅ Я оплатил»",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data.startswith("pay_gift_confirm:"))
async def pay_gift_confirm(call: CallbackQuery):
    """Подарок — сердечки партнёру."""
    parts = cb_parts(call)
    if len(parts) < 2:
        await call.answer()
        return
    try:
        hearts = int(parts[1])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    pkg = get_package(hearts)
    if pkg is None:
        await call.answer("Пакет не найден", show_alert=True)
        return

    from database import _fetchall, _execute
    purchases = await _fetchall(
        "SELECT id FROM purchases WHERE user_id=? LIMIT 1",
        (call.from_user.id,),
    )
    is_first = len(purchases) == 0
    bonus_percent, total = calc_bonus(hearts, is_first)

    from utils.yookassa import create_payment
    result = await create_payment(
        amount_rub=pkg["price"],
        description=f"Подарок {hearts} ❤️ — 300 Сердец",
        user_id=call.from_user.id,
        recipient_id=partner["telegram_id"],
        hearts_amount=total,
        package=hearts,
        bonus_percent=bonus_percent,
        is_first=is_first,
    )

    if result is None:
        await call.answer("Ошибка оплаты", show_alert=True)
        return

    await _execute(
        "INSERT INTO payments_log "
        "(yookassa_id, user_id, recipient_id, hearts, package, bonus_percent, is_first, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
        (
            result["yookassa_id"], call.from_user.id, partner["telegram_id"],
            total, hearts, bonus_percent, 1 if is_first else 0,
        ),
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=result["confirmation_url"])],
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"pay_check:{result['yookassa_id']}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="hearts:gift")],
    ])
    await safe_edit(
        call,
        f"🎁 <b>Подарок: {hearts} ❤️ → {partner['name']}</b>\n"
        f"Цена: {pkg['price']}₽\n\n"
        f"Бонус: +{bonus_percent}% = +{total - hearts} ❤️\n"
        f"Итого: <b>{total} ❤️</b>\n\n"
        f"1. Нажми «Оплатить»\n"
        f"2. Оплати\n"
        f"3. Вернись в бота и нажми «✅ Я оплатил»",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data.startswith("pay_check:"))
async def pay_check(call: CallbackQuery):
    """Проверяет статус платежа и начисляет сердечки."""
    parts = cb_parts(call)
    if len(parts) < 2:
        await call.answer()
        return
    yookassa_id = parts[1]

    from database import _fetchone, _execute
    p = await _fetchone(
        "SELECT * FROM payments_log WHERE yookassa_id=?", (yookassa_id,)
    )
    if p is None:
        await call.answer("Платёж не найден", show_alert=True)
        return

    # Уже обработан?
    if p["status"] == "succeeded":
        await call.answer("✅ Уже начислено", show_alert=False)
        return

    from utils.yookassa import check_payment
    status = await check_payment(yookassa_id)

    if status == "succeeded":
        # Начисляем
        from database import add_hearts
        recipient_id = p["recipient_id"] or p["user_id"]
        hearts = p["hearts"]

        await add_hearts(recipient_id, hearts)
        await _execute(
            "INSERT INTO purchases "
            "(user_id, package, price, bonus_percent, hearts_amount, is_first) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (p["user_id"], p["package"], p["package"], p["bonus_percent"],
             hearts, p["is_first"]),
        )
        await _execute(
            "UPDATE payments_log SET status='succeeded', processed_at=datetime('now') "
            "WHERE id=?",
            (p["id"],),
        )

        # Уведомления
        if recipient_id != p["user_id"]:
            partner = await get_user(recipient_id)
            name = partner["name"] if partner else "партнёр"
            await send_to(
                call.bot, recipient_id,
                f"🎁 <b>Тебе подарок — {hearts} ❤️!</b>\n\nПоздравляю! ❤️",
            )
            await safe_edit(
                call,
                f"✅ <b>Оплата прошла!</b>\n\n{name} получил(а) {hearts} ❤️.",
                reply_markup=kb_back("menu:shop"),
            )
        else:
            await safe_edit(
                call,
                f"✅ <b>Оплата прошла!</b>\n\n+{hearts} ❤️ на твой баланс.",
                reply_markup=kb_back("menu:shop"),
            )
        await call.answer()
        return

    if status == "canceled":
        await _execute(
            "UPDATE payments_log SET status='canceled' WHERE id=?", (p["id"],)
        )
        await safe_edit(
            call,
            "❌ Платёж отменён.\n\nПопробуй снова.",
            reply_markup=kb_back("menu:shop"),
        )
        await call.answer()
        return

    # Всё ещё pending
    await call.answer(
        "⏳ Платёж ещё не поступил.\n\nПодожди 10-20 секунд и попробуй снова.",
        show_alert=True,
    )

# =========================================================
#  🛠 ТОВАРЫ ПАРТНЁРА
#  Механика: A создаёт товар → B покупает → A выполняет →
#  B подтверждает → сердечки идут A. Двойное подтверждение.
# =========================================================

# Категории: (label, price, примеры)
PARTNER_CATEGORIES = [
    ("🟢 Мелкое — 100 ❤️", 100, [
        "🍫 Подарю тебе шоколадку",
        "💆 Сделаю массаж 10 минут",
        "🎵 Спою песню для тебя",
        "✏️ Своё",
    ]),
    ("🟡 Среднее — 300 ❤️", 300, [
        "💆 Сделаю массаж 30 минут",
        "🍕 Сделаю нам ужин на свой выбор",
        "🧹 Уберусь вместо тебя",
        "✏️ Своё",
    ]),
    ("🔴 Крупное — 1000 ❤️", 1000, [
        "✈️ Организую поездку на выходные",
        "🎭 Куплю билеты на концерт",
        "🏨 Устрою нам романтический вечер",
        "✏️ Своё",
    ]),
]


def _partner_items_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать товар", callback_data="pi:create")],
        [InlineKeyboardButton(text="📋 Мои товары", callback_data="pi:mine")],
        [InlineKeyboardButton(text="🛍 Купить у партнёра", callback_data="pi:buy")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:shop")],
    ])


@router.callback_query(F.data == "shop:partner_wishes")
async def shop_partner_items(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    text = (
        "🛠 <b>Товары партнёра</b>\n\n"
        "Создай услугу, которую окажешь партнёру.\n"
        "Назначь цену — и заработай сердечки.\n"
        "Партнёр купит — ты выполнишь.\n\n"
        "Примеры:\n"
        "• Сварю тебе кофе — 100 ❤️\n"
        "• Неделю мою посуду — 300 ❤️\n"
        "• Большой сюрприз для тебя — 1000 ❤️\n\n"
        "Сердечки идут тебе."
    )
    await safe_edit(call, text, reply_markup=_partner_items_kb())
    await call.answer()


# =========================================================
#  СОЗДАНИЕ ТОВАРА
# =========================================================

@router.callback_query(F.data == "pi:create")
async def pi_create(call: CallbackQuery):
    rows: list[list[InlineKeyboardButton]] = []
    for label, price, _examples in PARTNER_CATEGORIES:
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"pi:cat:{price}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:partner_wishes")])

    await safe_edit(
        call,
        "➕ <b>Создать товар</b>\n\nВыбери категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await call.answer()

@router.callback_query(F.data.startswith("pi:cat:"))
async def pi_category(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        price = int(parts[2])
    except ValueError:
        await call.answer()
        return

    cat = None
    for label, p, examples in PARTNER_CATEGORIES:
        if p == price:
            cat = (label, p, examples)
            break
    if cat is None:
        await call.answer("Категория не найдена", show_alert=True)
        return

    label, p, examples = cat

    rows: list[list[InlineKeyboardButton]] = []
    for idx, ex in enumerate(examples):
        if ex == "✏️ Своё":
            rows.append([InlineKeyboardButton(
                text=ex,
                callback_data=f"pi:custom:{price}",
            )])
        else:
            # ВАЖНО: только индекс, не текст!
            rows.append([InlineKeyboardButton(
                text=ex,
                callback_data=f"pi:save:{price}:{idx}",
            )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="pi:create",
    )])

    await safe_edit(
        call,
        f"<b>{label}</b>\n\nВыбери пример или напиши своё:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await call.answer()

@router.callback_query(F.data.startswith("pi:save:"))
async def pi_save(call: CallbackQuery):
    parts = cb_parts(call)
    # pi:save:<price>:<idx>
    if len(parts) < 4:
        await call.answer()
        return
    try:
        price = int(parts[2])
        idx = int(parts[3])
    except ValueError:
        await call.answer()
        return

    # Ищем категорию и берём текст по индексу
    cat_examples = None
    for _label, p, examples in PARTNER_CATEGORIES:
        if p == price:
            cat_examples = examples
            break

    if cat_examples is None or idx < 0 or idx >= len(cat_examples):
        await call.answer("Пример не найден", show_alert=True)
        return

    text = cat_examples[idx][:100]

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    await _execute(
        "INSERT INTO shop_items (couple_id, title, price, author_id, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        (user["couple_id"], text, price, call.from_user.id),
    )

    await safe_edit(
        call,
        f"✅ Товар создан!\n\n<b>{text}</b>\nЦена: {price} ❤️\n\n"
        f"Партнёр увидит его в магазине.",
        reply_markup=kb_back("shop:partner_wishes"),
    )
    await call.answer()

@router.callback_query(F.data.startswith("pi:custom:"))
async def pi_custom(call: CallbackQuery, state: FSMContext):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        price = int(parts[2])
    except ValueError:
        await call.answer()
        return

    await state.update_data(pi_price=price)
    await state.set_state(ShopFSM.custom_wish)
    await safe_edit(
        call,
        f"✏️ Напиши название товара (до 100 символов):\n\n"
        f"Цена будет: {price} ❤️",
    )
    await call.answer()


@router.message(ShopFSM.custom_wish)
async def pi_custom_text(message: Message, state: FSMContext):
    if message.from_user is None:
        return
    data = await state.get_data()
    price = data.get("pi_price", 0)
    title = (message.text or "").strip()[:100]
    await state.clear()

    if not title:
        await message.answer("Пустое название.")
        return

    user = await get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала /start")
        return

    await _execute(
        "INSERT INTO shop_items (couple_id, title, price, author_id, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        (user["couple_id"], title, price, message.from_user.id),
    )

    await message.answer(
        f"✅ Товар создан!\n\n<b>{title}</b>\nЦена: {price} ❤️\n\n"
        f"Партнёр увидит его в магазине.",
        reply_markup=kb_shop(),
    )


# =========================================================
#  МОИ ТОВАРЫ
# =========================================================

@router.callback_query(F.data == "pi:mine")
async def pi_mine(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    items = await _fetchall(
        "SELECT id, title, price FROM shop_items "
        "WHERE couple_id=? AND author_id=? AND status='active' "
        "ORDER BY id DESC",
        (user["couple_id"], call.from_user.id),
    )

    if not items:
        await safe_edit(
            call,
            "📋 У тебя пока нет товаров.\n\nСоздай первый — партнёр увидит.",
            reply_markup=kb_back("shop:partner_wishes"),
        )
        await call.answer()
        return

    lines = ["📋 <b>Мои товары</b>\n"]
    rows: list[list[InlineKeyboardButton]] = []
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it['title']} — {it['price']} ❤️")
        rows.append([InlineKeyboardButton(
            text=f"🗑 {i}. {it['title'][:30]}",
            callback_data=f"pi:del:{it['id']}",
        )])

    lines.append(f"\nВсего: {len(items)}")
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:partner_wishes")])

    await safe_edit(
        call,
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await call.answer()


@router.callback_query(F.data.startswith("pi:del:"))
async def pi_delete(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        item_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE shop_items SET status='deleted' WHERE id=?", (item_id,))
        await db.commit()

    await call.answer("✅ Товар удалён")
    await pi_mine(call)


# =========================================================
#  КУПИТЬ У ПАРТНЁРА
# =========================================================

@router.callback_query(F.data == "pi:buy")
async def pi_buy(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    items = await _fetchall(
        "SELECT id, title, price FROM shop_items "
        "WHERE couple_id=? AND author_id=? AND status='active' "
        "ORDER BY id DESC",
        (user["couple_id"], partner["telegram_id"]),
    )

    if not items:
        await safe_edit(
            call,
            f"🛍 У {partner['name']} пока нет товаров.",
            reply_markup=kb_back("shop:partner_wishes"),
        )
        await call.answer()
        return

    rows: list[list[InlineKeyboardButton]] = []
    for it in items:
        rows.append([InlineKeyboardButton(
            text=f"{it['title'][:40]} — {it['price']} ❤️",
            callback_data=f"pi:show:{it['id']}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:partner_wishes")])

    await safe_edit(
        call,
        f"🛍 <b>Товары {partner['name']}</b>\n\nВыбери товар:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await call.answer()


@router.callback_query(F.data.startswith("pi:show:"))
async def pi_show(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        item_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    item = await _fetchone_shop_item(item_id)
    if item is None:
        await call.answer("Товар не найден", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Купить за {item['price']} ❤️",
            callback_data=f"pi:confirm:{item_id}",
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="pi:buy")],
    ])

    await safe_edit(
        call,
        f"🛍 <b>{item['title']}</b>\n\n"
        f"Цена: {item['price']} ❤️\n\n"
        f"Сердечки спишутся после подтверждения партнёра.",
        reply_markup=kb,
    )
    await call.answer()


async def _fetchone_shop_item(item_id: int) -> dict | None:
    rows = await _fetchall(
        "SELECT id, title, price, author_id FROM shop_items WHERE id=?",
        (item_id,),
    )
    return rows[0] if rows else None


# =========================================================
#  ПОДТВЕРЖДЕНИЕ ПОКУПКИ
# =========================================================

@router.callback_query(F.data.startswith("pi:confirm:"))
async def pi_confirm(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return
    try:
        item_id = int(parts[2])
    except ValueError:
        await call.answer()
        return

    user = await get_user(call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    item = await _fetchone_shop_item(item_id)
    if item is None:
        await call.answer("Товар не найден", show_alert=True)
        return

    price = item["price"]
    if user["hearts_balance"] < price:
        await call.answer(
            f"Нужно {price} ❤️ — у тебя {user['hearts_balance']}",
            show_alert=True,
        )
        return

    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    # Уведомляем партнёра
    await send_to(
        call.bot,
        partner["telegram_id"],
        f"🎁 <b>{user['name']} хочет купить:</b>\n\n"
        f"{item['title']}\nЦена: {price} ❤️\n\n"
        f"Выполни и подтверди.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Выполнено",
                    callback_data=f"pi:done:{item_id}:{call.from_user.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отказаться",
                    callback_data=f"pi:refuse:{item_id}:{call.from_user.id}",
                ),
            ],
        ]),
    )

    await safe_edit(
        call,
        f"⏳ Запрос отправлен {partner['name']}.\n\n"
        f"Сердечки спишутся после подтверждения.",
        reply_markup=kb_back("shop:partner_wishes"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("pi:done:"))
async def pi_done(call: CallbackQuery):
    parts = cb_parts(call)
    # pi:done:<item_id>:<buyer_id>
    if len(parts) < 4:
        await call.answer()
        return
    try:
        item_id = int(parts[2])
        buyer_id = int(parts[3])
    except ValueError:
        await call.answer()
        return

    item = await _fetchone_shop_item(item_id)
    if item is None:
        await call.answer("Товар не найден", show_alert=True)
        return

    await send_to(
        call.bot,
        buyer_id,
        f"✅ <b>{item['title']}</b> — выполнено!\n\n"
        f"Подтверди получение.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"pi:buyer_ok:{item_id}:{call.from_user.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Не выполнено",
                    callback_data=f"pi:buyer_no:{item_id}:{call.from_user.id}",
                ),
            ],
        ]),
    )

    await safe_edit(call, "⏳ Ждём подтверждения от покупателя.")
    await call.answer()


@router.callback_query(F.data.startswith("pi:refuse:"))
async def pi_refuse(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 4:
        await call.answer()
        return
    try:
        buyer_id = int(parts[3])
    except ValueError:
        await call.answer()
        return

    await safe_edit(call, "❌ Отказано. Сердечки не списаны.")
    await send_to(
        call.bot,
        buyer_id,
        f"❌ {call.from_user.full_name} — не сейчас.\nЗаказ отменён."
    )
    await call.answer()


@router.callback_query(F.data.startswith("pi:buyer_ok:"))
async def pi_buyer_ok(call: CallbackQuery):
    parts = cb_parts(call)
    # pi:buyer_ok:<item_id>:<seller_id>
    if len(parts) < 4:
        await call.answer()
        return
    try:
        item_id = int(parts[2])
        seller_id = int(parts[3])
    except ValueError:
        await call.answer()
        return

    buyer = await get_user(call.from_user.id)
    if buyer is None:
        await call.answer()
        return

    item = await _fetchone_shop_item(item_id)
    if item is None:
        await call.answer("Товар не найден", show_alert=True)
        return

    price = item["price"]

    # Списываем с покупателя
    ok = await spend_hearts(call.from_user.id, price)
    if not ok:
        await safe_edit(call, "❌ Недостаточно сердечек.")
        await call.answer()
        return

    # Начисляем продавцу
    await add_hearts(seller_id, price)

    # Лог
    await _execute(
        "INSERT INTO transactions (couple_id, from_user, to_user, amount, reason) "
        "VALUES (?, ?, ?, ?, 'shop_item')",
        (buyer["couple_id"], call.from_user.id, seller_id, price),
    )

    await safe_edit(
        call,
        f"✅ <b>Сделка закрыта!</b>\n\n{price} ❤️ перешли партнёру.",
    )
    await send_to(
        call.bot,
        seller_id,
        f"✅ <b>Сделка закрыта!</b>\n\n"
        f"Ты получил(а) {price} ❤️ за «{item['title']}».",
    )
    await call.answer()


@router.callback_query(F.data.startswith("pi:buyer_no:"))
async def pi_buyer_no(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 4:
        await call.answer()
        return
    try:
        seller_id = int(parts[3])
    except ValueError:
        await call.answer()
        return

    await safe_edit(call, "❌ Не подтверждено. Сердечки не списаны.")
    await send_to(
        call.bot,
        seller_id,
        "❌ Покупатель не подтвердил выполнение.",
    )
    await call.answer()