"""10 тестов + механики подсчёта + seed вопросов."""
import logging

from database import _execute, _fetchall, _fetchone

logger = logging.getLogger(__name__)


# =========================================================
#  СПИСОК ТЕСТОВ
# =========================================================

TESTS = [
    {
        "order_num": 1,
        "title": "Вкусы и мелочи",
        "level": "easy",
        "mechanics": "simple",
        "description": "Что вы любите — еда, фильмы, музыка.",
    },
    {
        "order_num": 2,
        "title": "Досуг и юмор",
        "level": "easy",
        "mechanics": "simple",
        "description": "Как вы развлекаетесь и смеётесь.",
    },
    {
        "order_num": 3,
        "title": "Быт и привычки",
        "level": "easy",
        "mechanics": "simple",
        "description": "Как устроен ваш день.",
    },
    {
        "order_num": 4,
        "title": "Общение и внимание",
        "level": "medium",
        "mechanics": "weighted",
        "description": "Как вы говорите и слушаете.",
    },
    {
        "order_num": 5,
        "title": "Ссоры и конфликты",
        "level": "medium",
        "mechanics": "weighted",
        "description": "Как вы ссоритесь и миритесь.",
    },
    {
        "order_num": 6,
        "title": "Ценности и принципы",
        "level": "medium",
        "mechanics": "weighted",
        "description": "Что для вас важно в жизни.",
    },
    {
        "order_num": 7,
        "title": "Языки любви",
        "level": "medium",
        "mechanics": "weighted",
        "description": "Как вы показываете и чувствуете любовь.",
    },
    {
        "order_num": 8,
        "title": "Личное пространство",
        "level": "deep",
        "mechanics": "scale5",
        "description": "Сколько близости и свободы вам нужно.",
    },
    {
        "order_num": 9,
        "title": "Близость и интимность",
        "level": "deep",
        "mechanics": "scale5",
        "description": "Темп и желания.",
    },
    {
        "order_num": 10,
        "title": "Привязанность",
        "level": "attachment",
        "mechanics": "attachment",
        "description": "Типы привязанности.",
    },
]


# =========================================================
#  SEED: тесты
# =========================================================

async def seed_tests() -> None:
    existing = await _fetchall("SELECT id FROM tests LIMIT 1")
    if existing:
        return
    for t in TESTS:
        await _execute(
            "INSERT INTO tests (order_num, title, level, mechanics, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (t["order_num"], t["title"], t["level"], t["mechanics"], t["description"]),
        )
    logger.info("tests seeded")


# =========================================================
#  МЕХАНИКИ ПОДСЧЁТА
# =========================================================

def calculate_simple(answers_a: list, answers_b: list) -> dict:
    """Тесты 1–3: простое совпадение."""
    if not answers_a:
        return {"percent": 0, "matches": 0, "total": 0}
    matches = sum(1 for a, b in zip(answers_a, answers_b) if a == b)
    percent = (matches / len(answers_a)) * 100
    return {
        "percent": round(percent),
        "matches": matches,
        "total": len(answers_a),
    }


def calculate_weighted(answers_a: list, answers_b: list, weights: list[int]) -> dict:
    """Тесты 4–7: совпадение с весами (1–10=1, 11–20=2, 21–30=3)."""
    if not answers_a:
        return {"percent": 0, "matches": 0, "total": 0}
    total_weight = sum(weights)
    matched_weight = sum(
        w for a, b, w in zip(answers_a, answers_b, weights) if a == b
    )
    matches = sum(1 for a, b in zip(answers_a, answers_b) if a == b)
    percent = (matched_weight / total_weight) * 100 if total_weight else 0
    return {
        "percent": round(percent),
        "matches": matches,
        "total": len(answers_a),
        "matched_weight": matched_weight,
        "total_weight": total_weight,
    }


def calculate_scale(answers_a: list[int], answers_b: list[int]) -> dict:
    """Тесты 8–9: близость по шкале (0 = +2 очка, 1 = +1, 2+ = 0)."""
    if not answers_a:
        return {"percent": 0, "close": 0, "mid": 0, "far": 0}

    total_points = 0
    close = mid = far = 0
    max_points = len(answers_a) * 2

    for a, b in zip(answers_a, answers_b):
        diff = abs(a - b)
        if diff == 0:
            total_points += 2
            close += 1
        elif diff == 1:
            total_points += 1
            mid += 1
        else:
            far += 1

    percent = (total_points / max_points) * 100 if max_points else 0
    return {
        "percent": round(percent),
        "close": close,
        "mid": mid,
        "far": far,
        "total": len(answers_a),
    }


# =========================================================
#  ТЕСТ 10: ПРИВЯЗАННОСТЬ
# =========================================================

ATTACHMENT_ANXIETY_ITEMS = [1, 4, 6, 9, 11, 13, 18, 21, 24, 28]
ATTACHMENT_AVOIDANCE_ITEMS = [2, 5, 7, 10, 12, 14, 20, 22, 26, 30]

ATTACHMENT_NAMES = {
    "secure": "Надёжный",
    "anxious": "Тревожный",
    "avoidant": "Избегающий",
    "fearful": "Тревожно-избегающий",
}


def get_attachment_name(code: str) -> str:
    return ATTACHMENT_NAMES.get(code, code)


def determine_attachment_type(answers: list[int]) -> str:
    """По 30 ответам (1–7) определяет тип привязанности."""
    if len(answers) < 30:
        return "secure"

    anxiety = sum(answers[i-1] for i in ATTACHMENT_ANXIETY_ITEMS) / len(ATTACHMENT_ANXIETY_ITEMS)
    avoidance = sum(answers[i-1] for i in ATTACHMENT_AVOIDANCE_ITEMS) / len(ATTACHMENT_AVOIDANCE_ITEMS)

    if anxiety < 4 and avoidance < 4:
        return "secure"
    elif anxiety >= 4 and avoidance < 4:
        return "anxious"
    elif anxiety < 4 and avoidance >= 4:
        return "avoidant"
    else:
        return "fearful"


def calculate_attachment_compatibility(type_a: str, type_b: str) -> int:
    """Совместимость по типам привязанности."""
    matrix: dict[tuple[str, str], int] = {
        ("secure", "secure"): 100,
        ("secure", "anxious"): 75,
        ("secure", "avoidant"): 75,
        ("secure", "fearful"): 65,
        ("anxious", "anxious"): 60,
        ("anxious", "avoidant"): 30,
        ("anxious", "fearful"): 45,
        ("avoidant", "avoidant"): 60,
        ("avoidant", "fearful"): 45,
        ("fearful", "fearful"): 40,
    }
    if type_a <= type_b:
        key: tuple[str, str] = (type_a, type_b)
    else:
        key = (type_b, type_a)
    return matrix.get(key, 50)


# =========================================================
#  ВЕСА ТЕСТОВ ДЛЯ ИТОГОВОГО ПРОЦЕНТА
# =========================================================

TEST_WEIGHTS = {
    1: 1, 2: 1, 3: 1,
    4: 1.5, 5: 1.5, 6: 1.5,
    7: 2,
    8: 2, 9: 2,
    10: 2,
}


def calculate_total_percent(tests: list[dict]) -> int:
    """tests: [{test_id, percent}]"""
    total = 0.0
    total_weight = 0.0
    for t in tests:
        w = TEST_WEIGHTS.get(t["test_id"], 1)
        total += t["percent"] * w
        total_weight += w
    if total_weight == 0:
        return 0
    return round(total / total_weight)


async def seed_questions() -> None:
    """Заполняет 300 вопросов из QUESTIONS_DATA."""
    from utils.questions_data import QUESTIONS

    existing = await _fetchall("SELECT id FROM questions LIMIT 1")
    if existing:
        return

    tests = await _fetchall("SELECT * FROM tests ORDER BY order_num")
    if not tests:
        logger.warning("seed_questions: нет тестов")
        return

    # Сопоставляем order_num теста с test_id из БД
    test_by_order = {t["order_num"]: t["id"] for t in tests}

    for test_order, questions in QUESTIONS.items():
        test_id = test_by_order.get(test_order)
        if test_id is None:
            logger.warning(f"seed_questions: тест #{test_order} не найден")
            continue

        for idx, q in enumerate(questions, 1):
            await _execute(
                "INSERT INTO questions "
                "(test_id, order_num, text, q_type, option_a, option_b) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    test_id,
                    idx,
                    q["text"],
                    q["q_type"],
                    q.get("a"),
                    q.get("b"),
                ),
            )

    total = sum(len(q) for q in QUESTIONS.values())
    logger.info(f"questions seeded: {total} вопросов")