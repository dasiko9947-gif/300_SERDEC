import logging

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database import (
    get_user,
    get_partner,
    get_couple,
    add_hearts,
    _execute,
    _fetchall,
    _fetchone,
)
from config import HEARTS_QUESTION_MATCH, HEARTS_QUESTION_MISS
from utils.helpers import safe_edit, send_to, cb_parts
from utils.tests import (
    calculate_simple, calculate_weighted, calculate_scale,
    determine_attachment_type, calculate_attachment_compatibility,
    get_attachment_name, calculate_total_percent,
    TEST_WEIGHTS,
)
from utils.recommendations import get_recommendation

logger = logging.getLogger(__name__)

router = Router()


# =========================================================
#  ОТПРАВКА ВОПРОСА ДНЯ
# =========================================================

async def send_daily_question(bot, couple_id: int) -> None:
    """Отправляет вопрос дня обоим — но только тем, кто ещё не ответил."""
    users = await _get_couple_users(couple_id)
    if len(users) < 2:
        return

    test = await _get_current_test(couple_id)
    if test is None:
        return

    progress = await _fetchone(
        "SELECT current_q FROM test_progress WHERE couple_id=? AND test_id=?",
        (couple_id, test["id"]),
    )
    current_q = progress["current_q"] if progress else 0

    if current_q >= 30:
        return

    question = await _fetchone(
        "SELECT * FROM questions WHERE test_id=? AND order_num=? LIMIT 1",
        (test["id"], current_q + 1),
    )
    if question is None:
        return

    q_id = question["id"]

    text = (
        f"❓ <b>Вопрос дня</b>\n\n"
        f"Тест «{test['title']}»\n"
        f"Вопрос {current_q + 1} из 30\n\n"
        f"{question['text']}"
    )

    if question["q_type"] in ("scale5", "scale7"):
        text += "\n\n1 — совсем не согласен\n"
        if question["q_type"] == "scale5":
            text += "5 — полностью согласен"
        else:
            text += "7 — полностью согласен"

    kb = _question_kb(question)

    for u in users:
        tg_id = u["telegram_id"]
        # Проверяем: уже ответил?
        already = await _fetchone(
            "SELECT id FROM daily_answers "
            "WHERE couple_id=? AND question_id=? AND user_id=?",
            (couple_id, q_id, tg_id),
        )
        if already:
            continue   # ← уже ответил, не отправляем

        await send_to(bot, tg_id, text, reply_markup=kb)

async def _get_couple_users(couple_id: int) -> list[dict]:
    return await _fetchall(
        "SELECT telegram_id, name FROM users WHERE couple_id=? ORDER BY id",
        (couple_id,),
    )


async def _get_current_test(couple_id: int) -> dict | None:
    tests = await _fetchall("SELECT * FROM tests ORDER BY order_num")
    for t in tests:
        portrait = await _fetchone(
            "SELECT id FROM portraits WHERE couple_id=? AND test_id=?",
            (couple_id, t["id"]),
        )
        if portrait:
            continue
        progress = await _fetchone(
            "SELECT * FROM test_progress WHERE couple_id=? AND test_id=?",
            (couple_id, t["id"]),
        )
        if progress is None:
            await _execute(
                "INSERT INTO test_progress (couple_id, test_id, current_q) "
                "VALUES (?, ?, 0)",
                (couple_id, t["id"]),
            )
        return t
    return None


def _question_kb(question: dict) -> InlineKeyboardMarkup:
    q_type = question["q_type"]
    q_id = question["id"]

    if q_type == "choice":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🅰 {question['option_a']}",
                callback_data=f"tq:a:{q_id}",
            )],
            [InlineKeyboardButton(
                text=f"🅱 {question['option_b']}",
                callback_data=f"tq:b:{q_id}",
            )],
        ])

    if q_type == "scale5":
        row = [
            InlineKeyboardButton(text=str(i), callback_data=f"tq:{i}:{q_id}")
            for i in range(1, 6)
        ]
        return InlineKeyboardMarkup(inline_keyboard=[row])

    if q_type == "scale7":
        row1 = [
            InlineKeyboardButton(text=str(i), callback_data=f"tq:{i}:{q_id}")
            for i in range(1, 5)
        ]
        row2 = [
            InlineKeyboardButton(text=str(i), callback_data=f"tq:{i}:{q_id}")
            for i in range(5, 8)
        ]
        return InlineKeyboardMarkup(inline_keyboard=[row1, row2])

    return InlineKeyboardMarkup(inline_keyboard=[])


# =========================================================
#  ОБРАБОТКА ОТВЕТА
# =========================================================
@router.callback_query(F.data.startswith("tq:"))
async def test_answer(call: CallbackQuery):
    parts = cb_parts(call)
    if len(parts) < 3:
        await call.answer()
        return

    answer = parts[1]
    try:
        q_id = int(parts[2])
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

    question = await _fetchone(
        "SELECT test_id, q_type FROM questions WHERE id=?", (q_id,)
    )
    if question is None:
        await call.answer("Вопрос не найден", show_alert=True)
        return

    test_id = question["test_id"]
    if test_id is None:
        await call.answer("Ошибка вопроса", show_alert=True)
        return

    q_type = question["q_type"] or "choice"

    # ---- Проверка: уже отвечал на этот вопрос? ----
    existing = await _fetchone(
        "SELECT id, answer FROM daily_answers "
        "WHERE couple_id=? AND question_id=? AND user_id=?",
        (user["couple_id"], q_id, call.from_user.id),
    )
    if existing:
        await call.answer("Вы уже ответили на этот вопрос", show_alert=True)
        return

    # ---- Сохраняем ответ ----
    await _execute(
        "INSERT INTO daily_answers "
        "(couple_id, question_id, user_id, answer) "
        "VALUES (?, ?, ?, ?)",
        (user["couple_id"], q_id, call.from_user.id, answer),
    )

    partner = await get_partner(user["couple_id"], call.from_user.id)
    if partner is None:
        await call.answer("Партнёр не найден", show_alert=True)
        return

    partner_ans = await _fetchone(
        "SELECT answer FROM daily_answers "
        "WHERE couple_id=? AND question_id=? AND user_id=?",
        (user["couple_id"], q_id, partner["telegram_id"]),
    )

    if partner_ans is None:
        await safe_edit(
            call,
            f"✅ Твой ответ принят!\n\nЖдём ответ {partner['name']} ⏳",
        )
        await call.answer()
        return

    # ---- Оба ответили ----
    answer_a = answer
    answer_b = partner_ans["answer"]

    matched = answer_a == answer_b
    reward = HEARTS_QUESTION_MATCH if matched else HEARTS_QUESTION_MISS

    await add_hearts(call.from_user.id, reward)
    await add_hearts(partner["telegram_id"], reward)

    # Записываем в test_answers
    await _execute(
        "INSERT INTO test_answers "
        "(couple_id, test_id, question_id, user_a_answer, user_b_answer, matched) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user["couple_id"], test_id, q_id, answer_a, answer_b, 1 if matched else 0),
    )

    # Обновляем progress
    progress = await _fetchone(
        "SELECT * FROM test_progress WHERE couple_id=? AND test_id=?",
        (user["couple_id"], test_id),
    )
    new_q = 0
    if progress:
        new_q = (progress["current_q"] or 0) + 1
        await _execute(
            "UPDATE test_progress SET current_q=? "
            "WHERE couple_id=? AND test_id=?",
            (new_q, user["couple_id"], test_id),
        )

    # Формируем текст
    text = _result_text(
        q_type, answer_a, answer_b, matched, reward,
        user["name"], partner["name"],
    )

    await safe_edit(call, text)
    await send_to(call.bot, partner["telegram_id"], text)

    # Если тест завершён
    if new_q >= 30:
        await _finish_test(call.bot, user["couple_id"], test_id, user, partner)

    await call.answer()

def _result_text(
    q_type: str,
    a: str,
    b: str,
    matched: bool,
    reward: int,
    name_a: str,
    name_b: str,
) -> str:
    """Короткий текст результата — без 'a' / 'b'."""
    if q_type in ("scale5", "scale7"):
        try:
            diff = abs(int(a) - int(b))
        except ValueError:
            diff = 0
        if diff == 0:
            return f"🎯 <b>Идеально!</b>\n\n+{reward} ❤️ каждому."
        elif diff == 1:
            return f"❤️ <b>Близко!</b>\n\n+{reward} ❤️ каждому."
        elif diff <= 2:
            return f"🙂 <b>Средне.</b>\n\n+{reward} ❤️ каждому."
        else:
            return f"🤔 <b>Далеко друг от друга.</b>\n\n+{reward} ❤️ каждому."

    if matched:
        return f"🎉 <b>Ваши ответы совпали!</b>\n\n+{reward} ❤️ каждому."
    return f"❌ <b>Ваши ответы разошлись.</b>\n\n+{reward} ❤️ каждому за участие."


# =========================================================
#  ЗАВЕРШЕНИЕ ТЕСТА
# =========================================================

async def _finish_test(bot, couple_id: int, test_id: int, user: dict, partner: dict) -> None:
    test = await _fetchone("SELECT * FROM tests WHERE id=?", (test_id,))
    if test is None:
        return

    rows = await _fetchall(
        "SELECT user_a_answer, user_b_answer FROM test_answers "
        "WHERE couple_id=? AND test_id=? ORDER BY id",
        (couple_id, test_id),
    )
    if not rows:
        return

    answers_a = [r["user_a_answer"] for r in rows]
    answers_b = [r["user_b_answer"] for r in rows]

    mechanics = test["mechanics"]

    if mechanics == "simple":
        result = calculate_simple(answers_a, answers_b)
    elif mechanics == "weighted":
        weights = [1] * 10 + [2] * 10 + [3] * 10
        result = calculate_weighted(answers_a, answers_b, weights)
    elif mechanics == "scale5":
        try:
            aa = [int(x) for x in answers_a]
            bb = [int(x) for x in answers_b]
        except ValueError:
            aa, bb = [], []
        result = calculate_scale(aa, bb)
    elif mechanics == "attachment":
        try:
            aa = [int(x) for x in answers_a]
            bb = [int(x) for x in answers_b]
        except ValueError:
            aa, bb = [1] * 30, [1] * 30
        type_a = determine_attachment_type(aa)
        type_b = determine_attachment_type(bb)
        percent = calculate_attachment_compatibility(type_a, type_b)
        result = {
            "percent": percent,
            "type_a": get_attachment_name(type_a),
            "type_b": get_attachment_name(type_b),
        }
    else:
        result = {"percent": 0}

    percent = result.get("percent", 0)

    # Сохраняем портрет
    await _execute(
        "INSERT OR REPLACE INTO portraits "
        "(couple_id, test_id, percent, matches, total) "
        "VALUES (?, ?, ?, ?, ?)",
        (couple_id, test_id, percent,
         result.get("matches", result.get("close", 0)), 30),
    )

    text = _finish_text(test, result, user, partner)

    await send_to(bot, user["telegram_id"], text)
    await send_to(bot, partner["telegram_id"], text)

    # Промежуточный портрет
    all_portraits = await _fetchall(
        "SELECT test_id, percent FROM portraits WHERE couple_id=?",
        (couple_id,),
    )
    if all_portraits:
        portrait_text = await _portrait_text(couple_id, all_portraits, user, partner)
        if portrait_text:
            await send_to(bot, user["telegram_id"], portrait_text)
            await send_to(bot, partner["telegram_id"], portrait_text)


def _finish_text(test: dict, result: dict, user: dict, partner: dict) -> str:
    percent = result.get("percent", 0)
    title = test["title"]

    text = f"🎉 <b>Тест «{title}» пройден!</b>\n\n"

    if test["mechanics"] == "attachment":
        text += (
            f"Твой тип: {result.get('type_a', '—')}\n"
            f"Тип {partner['name']}: {result.get('type_b', '—')}\n\n"
        )

    text += f"Совместимость: <b>{percent}%</b>\n\n"

    if "matches" in result and "total" in result:
        text += (
            f"🟢 Совпало: {result['matches']}\n"
            f"🔴 Не совпало: {result['total'] - result['matches']}\n"
        )
    elif "close" in result:
        text += (
            f"🟢 Близко: {result['close']}\n"
            f"🟡 Средне: {result['mid']}\n"
            f"🔴 Далеко: {result['far']}\n"
        )

    rec = get_recommendation(test["order_num"], percent)
    if rec:
        text += f"\n{rec}"

    return text


# =========================================================
#  ПРОМЕЖУТОЧНЫЙ ПОРТРЕТ (после каждого теста)
# =========================================================
async def _portrait_text(couple_id, portraits, user, partner) -> str | None:
    if not portraits:
        return None

    from utils.recommendations import get_short_recommendation

    done = len(portraits)
    total = 10
    total_percent = calculate_total_percent(portraits)

    lines = [
        f"📊 <b>Портрет пары</b>",
        "",
        f"Пройдено: {done} из {total} тестов",
        "",
        f"Текущая совместимость: <b>{total_percent}%</b>",
        "",
    ]

    # Сортируем по убыванию
    sorted_p = sorted(portraits, key=lambda x: x["percent"], reverse=True)

    # Собираем данные тестов
    tests_all = await _fetchall("SELECT id, order_num, title FROM tests")
    titles = {t["id"]: t["title"] for t in tests_all}
    orders = {t["id"]: t["order_num"] for t in tests_all}

    # Лучшее
    lines.append("🟢 <b>Лучшее:</b>")
    for p in sorted_p[:2]:
        lines.append(f"• {titles.get(p['test_id'], '?')} — {p['percent']}%")

    # Точки роста + рекомендации
    lines.append("")
    lines.append("🟡 <b>Точки роста:</b>")
    for p in sorted_p[-2:]:
        test_title = titles.get(p["test_id"], "?")
        lines.append(f"• {test_title} — {p['percent']}%")
        order = orders.get(p["test_id"], 0)
        short = get_short_recommendation(order)
        if short:
            lines.append(f"  💡 {short}")

    # Финальный портрет
    if done >= 10:
        lines.append("")
        lines.append("🎉 <b>Портрет пары готов!</b>")

    return "\n".join(lines)

# =========================================================
#  ПУБЛИЧНЫЙ ПОРТРЕТ (для кнопки в профиле)
# =========================================================

async def get_full_portrait_text(couple_id: int, user: dict, partner: dict) -> str:
    """
    Полный портрет пары для профиля.
    Если тестов ещё нет — возвращает заглушку.
    """
    portraits = await _fetchall(
        "SELECT test_id, percent FROM portraits WHERE couple_id=? "
        "ORDER BY test_id",
        (couple_id,),
    )

    if not portraits:
        return (
            "🧠 <b>Портрет пары</b>\n\n"
            "Пока нет пройденных тестов.\n\n"
            "Каждый день вы получаете вопрос дня.\n"
            "За 30 дней пройдёте первый тест — и увидите свой портрет.\n\n"
            "Всего 10 тестов: от вкусов до привязанности."
        )

    done = len(portraits)
    total_percent = calculate_total_percent(portraits)

    # Собираем данные тестов
    tests_all = await _fetchall("SELECT id, order_num, title FROM tests")
    titles = {t["id"]: t["title"] for t in tests_all}
    orders = {t["id"]: t["order_num"] for t in tests_all}

    sorted_p = sorted(portraits, key=lambda x: x["percent"], reverse=True)

    lines = [
        "🧠 <b>Портрет пары</b>",
        "",
        f"Пройдено: {done} из 10 тестов",
        "",
        f"Общая совместимость: <b>{total_percent}%</b>",
        "",
    ]

    # Сильные стороны
    lines.append("🟢 <b>Сильные стороны:</b>")
    for p in sorted_p[:3]:
        lines.append(f"• {titles.get(p['test_id'], '?')} — {p['percent']}%")

    # Точки роста
    lines.append("")
    lines.append("🟡 <b>Точки роста:</b>")
    from utils.recommendations import get_short_recommendation
    for p in sorted_p[-3:]:
        test_title = titles.get(p["test_id"], "?")
        lines.append(f"• {test_title} — {p['percent']}%")
        order = orders.get(p["test_id"], 0)
        short = get_short_recommendation(order)
        if short:
            lines.append(f"  💡 {short}")

    if done >= 10:
        lines.append("")
        lines.append("🎉 <b>Полный портрет готов!</b>")
        lines.append("Вы прошли все 10 тестов.")

    return "\n".join(lines)
