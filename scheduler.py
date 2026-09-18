import logging
import random
from datetime import datetime, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import DB_PATH

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


# =========================================================
#  КЭШИ
# =========================================================

_settings_cache: dict[int, tuple[dict, float]] = {}
_SETTINGS_TTL = 3600   # 1 час (раньше 5 минут — реже проверяем)

_tz_cache: dict[int, tuple[ZoneInfo, float]] = {}
_TZ_TTL = 86400   # 24 часа (TZ не меняется почти никогда)


def _cache_valid(ts: float, ttl: int) -> bool:
    return (monotonic() - ts) < ttl


def _cleanup_caches() -> None:
    now = monotonic()
    for cid, (_, ts) in list(_settings_cache.items()):
        if (now - ts) > _SETTINGS_TTL:
            _settings_cache.pop(cid, None)
    for cid, (_, ts) in list(_tz_cache.items()):
        if (now - ts) > _TZ_TTL:
            _tz_cache.pop(cid, None)


# =========================================================
#  SETUP
# =========================================================

def setup_scheduler(bot) -> None:
    scheduler.add_job(
        tick_hourly,
        CronTrigger(minute="0"),         # каждый час в :00
        args=[bot],
        id="tick_hourly",
        replace_existing=True,
    )
    scheduler.add_job(
        remind_pending,
        CronTrigger(minute=0, hour="*/4"),   # раз в 4 часа
        args=[bot],
        id="remind_pending",
        replace_existing=True,
    )
    scheduler.add_job(
        remind_no_gift,
        CronTrigger(hour=19, minute=0),
        args=[bot],
        id="remind_no_gift",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Планировщик запущен (раз в час, TZ пары учитывается)")


# =========================================================
#  БД (с кэшами)
# =========================================================

async def _get_notifications(couple_id: int) -> bool:
    settings = await _get_settings(couple_id)
    return bool(settings.get("notifications", 1))


async def _get_active_couples() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM couples WHERE status='active'"
        ) as cur:
            raw = await cur.fetchall()
            return [dict(r) for r in raw]


async def _get_couple_users(couple_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT telegram_id, name, tz FROM users "
            "WHERE couple_id=? ORDER BY id",
            (couple_id,),
        ) as cur:
            raw = await cur.fetchall()
            return [dict(r) for r in raw]


async def _get_settings(couple_id: int) -> dict:
    now = monotonic()
    cached = _settings_cache.get(couple_id)
    if cached and _cache_valid(cached[1], _SETTINGS_TTL):
        return cached[0]

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT question_time, friday_time, friday_mode, notifications, "
            "tests_paused FROM settings WHERE couple_id=?",
            (couple_id,),
        ) as cur:
            row = await cur.fetchone()

    if row is None:
        settings = {
            "question_time": "10:00",
            "friday_time": "18:00",
            "friday_mode": 1,
            "notifications": 1,
            "tests_paused": 0,
        }
    else:
        settings = dict(row)

    _settings_cache[couple_id] = (settings, now)
    return settings


async def _get_couple_tz(couple_id: int) -> ZoneInfo:
    now = monotonic()
    cached = _tz_cache.get(couple_id)
    if cached and _cache_valid(cached[1], _TZ_TTL):
        return cached[0]

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tz FROM users WHERE couple_id=? AND tz IS NOT NULL "
            "ORDER BY id LIMIT 1",
            (couple_id,),
        ) as cur:
            row = await cur.fetchone()

    tz_str = row["tz"] if row and row["tz"] else "Europe/Moscow"
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")

    _tz_cache[couple_id] = (tz, now)
    return tz


async def _safe_send(bot, chat_id: int, text: str, reply_markup=None) -> None:
    if bot is None or chat_id is None:
        return
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"send_message failed to {chat_id}: {e}")


# =========================================================
#  TICK HOURLY (раз в час)
# =========================================================

async def tick_hourly(bot) -> None:
    # Кэш отправленного — по датам
    if not hasattr(tick_hourly, "_sent"):
        tick_hourly._sent = {}   # type: ignore[attr-defined]
    sent_by_date: dict[str, set] = tick_hourly._sent  # type: ignore[attr-defined]

    now_utc = datetime.utcnow()
    today_utc = now_utc.strftime("%Y-%m-%d")

    cutoff = (now_utc - timedelta(days=2)).strftime("%Y-%m-%d")
    for d in list(sent_by_date.keys()):
        if d < cutoff:
            del sent_by_date[d]

    sent: set = sent_by_date.setdefault(today_utc, set())

    _cleanup_caches()

    couples = await _get_active_couples()
    for c in couples:
        couple_id = c["id"]
        tz = await _get_couple_tz(couple_id)
        settings = await _get_settings(couple_id)

        now = datetime.now(tz)
        hour_str = now.strftime("%H:00")   # "10:00", "11:00", ...
        today = now.strftime("%Y-%m-%d")
        weekday = now.weekday()

        # --- Вопрос дня ---
        q_key = f"q:{couple_id}:{today}:{hour_str}"
        if q_key not in sent:
            if settings.get("question_time", "10:00") == hour_str:
                if not settings.get("tests_paused", 0):
                    from handlers.question import send_daily_question
                    await send_daily_question(bot, couple_id)
                sent.add(q_key)

        # --- Пятница ---
        if weekday == 4:
            fm_key = f"fm:{couple_id}:{today}"
            if fm_key not in sent and hour_str == "10:00":
                await friday_morning_reminder(bot, couple_id)
                sent.add(fm_key)

            f_key = f"f:{couple_id}:{today}"
            if f_key not in sent:
                if not settings.get("friday_mode", 1):
                    sent.add(f_key)
                elif settings.get("friday_time", "18:00") == hour_str:
                    await run_friday(bot, couple_id)
                    sent.add(f_key)

        # --- Даты + статус ---
        d_key = f"d:{couple_id}:{today}"
        if d_key not in sent and hour_str == "09:00":
            await remind_dates_for_couple(bot, couple_id, tz)
            sent.add(d_key)

            from utils.statuses import check_love_status
            from utils.helpers import days_together
            days = await days_together(couple_id)
            if days is not None:
                await check_love_status(bot, couple_id, days)

        # --- Оценка фильма (12:00) ---
        m_key = f"m:{couple_id}:{today}"
        if m_key not in sent and hour_str == "12:00":
            await remind_rate_movie(bot, couple_id, tz)
            sent.add(m_key)


# =========================================================
#  ПЯТНИЦА ЖЕЛАНИЙ
# =========================================================

BOT_WISHES = [
    "🌸 Массаж 15 минут",
    "🌸 Ужин при свечах",
    "🌸 Вечер без телефонов",
    "🌸 Комплименты весь день",
    "🌸 Совместная ванна",
    "🔥 Свидание вслепую",
    "🔥 Ролевая игра",
    "🔥 Массаж с маслом",
    "🔥 Танец для партнёра",
    "⚡ Связывание",
    "⚡ Секс с едой",
    "⚡ Игра с повязкой",
    "⚡ Новые позы",
]


async def friday_morning_reminder(bot, couple_id: int) -> None:
    if not await _get_notifications(couple_id):
        return
    settings = await _get_settings(couple_id)
    if not settings.get("friday_mode", 1):
        return

    users = await _get_couple_users(couple_id)
    if len(users) < 2:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) AS c FROM wishes "
            "WHERE couple_id=? AND status='active'",
            (couple_id,),
        ) as cur:
            row = await cur.fetchone()
            count = row["c"] if row else 0

    if count > 0:
        tail = (
            f"В кувшине {count} "
            f"{'желание' if count == 1 else 'желания' if count < 5 else 'желаний'}.\n"
            f"Сегодня вечером бот вытянет одно из них."
        )
    else:
        tail = (
            "Кувшин пуст — сегодня выпадет желание от бота.\n"
            "Добавь своё, чтобы в следующий раз вытянулось оно!"
        )

    text = f"🖤 <b>Сегодня Пятница желаний!</b>\n\n{tail}"
    for u in users:
        await _safe_send(bot, u["telegram_id"], text)


async def run_friday(bot, couple_id: int) -> None:
    if not await _get_notifications(couple_id):
        return
    users = await _get_couple_users(couple_id)
    if len(users) < 2:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, text FROM wishes WHERE couple_id=? AND status='active' "
            "ORDER BY RANDOM() LIMIT 1",
            (couple_id,),
        ) as cur:
            wish = await cur.fetchone()

    is_bot = False
    wish_id = None
    if wish is not None:
        wish_id = wish["id"]
        wish_text = wish["text"]
    else:
        is_bot = True
        wish_text = random.choice(BOT_WISHES)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO friday_events "
            "(couple_id, wish_id, wish_text, is_bot_wish, status) "
            "VALUES (?, ?, ?, ?, 'active')",
            (couple_id, wish_id, wish_text, 1 if is_bot else 0),
        )
        await db.commit()
        event_id = cur.lastrowid

        if wish_id is not None:
            await db.execute(
                "UPDATE wishes SET status='used' WHERE id=?", (wish_id,)
            )
            await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Принято",
            callback_data=f"friday:accept:{event_id}",
        )],
        [
            InlineKeyboardButton(
                text="⏭ Отмена — 300 ❤️",
                callback_data=f"friday:cancel:{event_id}",
            ),
            InlineKeyboardButton(
                text="🔄 Замена — 100 ❤️",
                callback_data=f"friday:replace:{event_id}",
            ),
        ],
    ])

    header = "🖤 <b>Пятница желаний</b>\n\nСегодня ваше желание:\n\n"
    if is_bot:
        header += (
            f"<b>{wish_text}</b>\n\n"
            "⚠️ Это желание от бота.\n"
            "Добавьте своё — и в следующий раз вытянется оно."
        )
    else:
        header += f"<b>{wish_text}</b>\n\nВыполните до конца воскресенья."

    for u in users:
        await _safe_send(bot, u["telegram_id"], header, reply_markup=kb)


# =========================================================
#  ДАТЫ
# =========================================================

async def remind_dates_for_couple(bot, couple_id: int, tz: ZoneInfo) -> None:
    if not await _get_notifications(couple_id):
        return
    users = await _get_couple_users(couple_id)
    if len(users) < 2:
        return

    now_local = datetime.now(tz)
    today_dm = now_local.strftime("%d.%m")
    tomorrow_dm = (now_local + timedelta(days=1)).strftime("%d.%m")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT title, date, date_type, owner_id FROM dates "
            "WHERE couple_id=? AND remind=1",
            (couple_id,),
        ) as cur:
            rows = await cur.fetchall()

    from utils.achievements import add_hearts

    for r in rows:
        date_str = r["date"] or ""
        if len(date_str) < 5:
            continue
        dd_mm = date_str[:5]
        date_type = r["date_type"] or "other"

        if dd_mm == tomorrow_dm:
            for u in users:
                await _safe_send(
                    bot, u["telegram_id"],
                    f"📅 <b>Напоминание</b>\n\n"
                    f"Завтра — <b>{r['title']}</b>!\n\n"
                    f"Не забудь поздравить ❤️",
                )

        if dd_mm != today_dm:
            continue

        if date_type == "birthday":
            owner_id = r["owner_id"]
            if owner_id is None:
                await add_hearts(users[0]["telegram_id"], 100)
                await add_hearts(users[1]["telegram_id"], 100)
                for u in users:
                    await _safe_send(
                        bot, u["telegram_id"],
                        f"🎂 <b>Сегодня день рождения!</b>\n\n"
                        f"<b>{r['title']}</b>\n\n+100 ❤️ каждому.",
                    )
            else:
                await add_hearts(owner_id, 100)
                partner_id = None
                for u in users:
                    if u["telegram_id"] != owner_id:
                        partner_id = u["telegram_id"]
                        break
                await _safe_send(
                    bot, owner_id,
                    f"🎂 <b>С днём рождения!</b>\n\n+100 ❤️ на баланс.",
                )
                if partner_id:
                    await _safe_send(
                        bot, partner_id,
                        f"🎂 <b>Сегодня ДР партнёра!</b>\n\n"
                        f"Не забудь поздравить ❤️\n"
                        f"Подари сердечки → /hearts",
                    )

        elif date_type == "anniversary":
            await add_hearts(users[0]["telegram_id"], 300)
            await add_hearts(users[1]["telegram_id"], 300)
            for u in users:
                await _safe_send(
                    bot, u["telegram_id"],
                    f"🎉 <b>Сегодня ваша годовщина!</b>\n\n"
                    f"{r['title']}\n\n+300 ❤️ каждому.",
                )


# =========================================================
#  ОЦЕНКА ФИЛЬМА
# =========================================================

async def remind_rate_movie(bot, couple_id: int, tz: ZoneInfo) -> None:
    if not await _get_notifications(couple_id):
        return
    yesterday = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, title, rating_a, rating_b FROM movies "
            "WHERE couple_id=? AND watched_at IS NOT NULL "
            "AND DATE(watched_at)=?",
            (couple_id, yesterday),
        ) as cur:
            raw = await cur.fetchall()
            movies: list[dict] = [dict(r) for r in raw]

    if not movies:
        return
    users = await _get_couple_users(couple_id)
    if len(users) < 2:
        return

    for m in movies:
        if m["rating_a"] is None or m["rating_b"] is None:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⭐ Оценить фильм",
                    callback_data=f"movie:rate_menu:{m['id']}",
                )],
            ])
            for u in users:
                await _safe_send(
                    bot, u["telegram_id"],
                    f"🎬 Как вам фильм?\n\n<b>«{m['title']}»</b>\n\n"
                    f"Оцени от 1 до 10.",
                    reply_markup=kb,
                )


# =========================================================
#  ПОДАРОК БЕЗ ПОВОДА
# =========================================================

async def remind_no_gift(bot) -> None:
    couples = await _get_active_couples()
    for c in couples:
        couple_id = c["id"]
        if not await _get_notifications(couple_id):
            continue
        users = await _get_couple_users(couple_id)
        if len(users) < 2:
            continue

        for user in users:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT last_gift_reminder FROM users WHERE telegram_id=?",
                    (user["telegram_id"],),
                ) as cur:
                    row = await cur.fetchone()
                    last_reminder = row["last_gift_reminder"] if row else None

            now = datetime.utcnow()
            if last_reminder:
                try:
                    last_dt = datetime.fromisoformat(last_reminder.replace(" ", "T"))
                except Exception:
                    last_dt = None
                if last_dt and (now - last_dt).days < 30:
                    continue

            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT MAX(created_at) AS last_gift FROM gifts "
                    "WHERE couple_id=? AND from_user=?",
                    (couple_id, user["telegram_id"]),
                ) as cur:
                    row = await cur.fetchone()
                    last_gift = row["last_gift"] if row else None

            need_remind = False
            if last_gift is None:
                need_remind = True
            else:
                try:
                    gift_dt = datetime.fromisoformat(last_gift.replace(" ", "T"))
                    if (now - gift_dt).days >= 30:
                        need_remind = True
                except Exception:
                    pass

            if not need_remind:
                continue

            partner = None
            for u in users:
                if u["telegram_id"] != user["telegram_id"]:
                    partner = u
                    break
            if partner is None:
                continue

            await _safe_send(
                bot, user["telegram_id"],
                f"🎁 <b>Давно не дарил(а) подарок {partner['name']}!</b>\n\n"
                f"Может, пора? Загляни в магазин — там 9 подарков 💞",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🎁 Подарить",
                        callback_data="shop:gifts",
                    )],
                ]),
            )

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET last_gift_reminder=datetime('now') "
                    "WHERE telegram_id=?",
                    (user["telegram_id"],),
                )
                await db.commit()


# =========================================================
#  ПИНОК ПО НЕЗАВЕРШЁННЫМ (раз в 4 часа)
# =========================================================

async def remind_pending(bot) -> None:
    couples = await _get_active_couples()
    for c in couples:
        couple_id = c["id"]
        if not await _get_notifications(couple_id):
            continue
        users = await _get_couple_users(couple_id)
        if len(users) < 2:
            continue

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, title, rating_a, rating_b FROM movies "
                "WHERE couple_id=? AND watched_at IS NOT NULL "
                "AND (rating_a IS NULL OR rating_b IS NULL) "
                "AND DATE(watched_at) <= DATE('now', '-1 day') "
                "AND DATE(watched_at) >= DATE('now', '-7 days')",
                (couple_id,),
            ) as cur:
                raw = await cur.fetchall()
                movies: list[dict] = [dict(r) for r in raw]

        for m in movies:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⭐ Оценить фильм",
                    callback_data=f"movie:rate_menu:{m['id']}",
                )],
            ])
            if m["rating_a"] is None:
                await _safe_send(
                    bot, users[0]["telegram_id"],
                    f"🎬 Ты забыл(а) оценить «{m['title']}».\n\n"
                    f"Это займёт 5 секунд 😉",
                    reply_markup=kb,
                )
            if m["rating_b"] is None:
                await _safe_send(
                    bot, users[1]["telegram_id"],
                    f"🎬 Ты забыл(а) оценить «{m['title']}».\n\n"
                    f"Это займёт 5 секунд 😉",
                    reply_markup=kb,
                )