"""Ю-Касcа SDK-клиент."""
import asyncio
import logging
import uuid

from yookassa import Payment, Configuration

from config import (
    YOOKASSA_SHOP_ID,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_RETURN_URL,
)

logger = logging.getLogger(__name__)

if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY
    logger.info("✅ ЮKassa настроена")
else:
    logger.error("❌ ЮKassa: нет ключей")

async def create_payment(
    amount_rub: int,
    description: str,
    user_id: int,
    recipient_id: int | None,
    hearts_amount: int,
    package: int,
    bonus_percent: int,
    is_first: bool,
) -> dict | None:
    """Создаёт платёж. Возвращает {yookassa_id, confirmation_url}."""
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        return None

    def _sync():
        return Payment.create(
            {
                "amount": {"value": f"{amount_rub}.00", "currency": "RUB"},
                "confirmation": {
                    "type": "redirect",
                    "return_url": YOOKASSA_RETURN_URL or "https://t.me",
                },
                "capture": True,
                "description": description[:128],
                "metadata": {
                    "user_id": str(user_id),
                    "recipient_id": str(recipient_id) if recipient_id else str(user_id),
                    "hearts": str(hearts_amount),
                    "package": str(package),
                    "bonus_percent": str(bonus_percent),
                    "is_first": "1" if is_first else "0",
                },
            },
            str(uuid.uuid4()),
        )

    try:
        loop = asyncio.get_event_loop()
        payment = await loop.run_in_executor(None, _sync)

        # Безопасно достаём confirmation_url
        confirmation = getattr(payment, "confirmation", None)
        confirmation_url: str | None = None
        if confirmation is not None:
            confirmation_url = getattr(confirmation, "confirmation_url", None)

        if not confirmation_url:
            logger.error("YooKassa: нет confirmation_url")
            return None

        return {
            "yookassa_id": payment.id,
            "confirmation_url": confirmation_url,
            "status": payment.status,
        }
    except Exception as e:
        logger.error(f"YooKassa create error: {e}")
        return None


async def check_payment(yookassa_id: str) -> str | None:
    """Возвращает 'succeeded' / 'pending' / 'canceled' или None."""
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        return None

    def _sync():
        return Payment.find_one(yookassa_id)

    try:
        loop = asyncio.get_event_loop()
        payment = await loop.run_in_executor(None, _sync)
        return payment.status
    except Exception as e:
        logger.error(f"YooKassa check error: {e}")
        return None