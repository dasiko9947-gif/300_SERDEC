import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import BOT_TOKEN
from database import init_db
from handlers import (
    onboarding, menu, movies, friday, shop, gifts, avatars,
    hearts, rating, profile, question, admin, settings,
)
from scheduler import setup_scheduler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="hearts", description="❤️ Получить сердца"),
        BotCommand(command="rating", description="🏆 Рейтинг пар"),
        
        BotCommand(command="help", description="❓ Как это работает"),
        BotCommand(command="settings", description="⚙️ Настроить бота"),
    ]
    await bot.set_my_commands(commands)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env")

    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(onboarding.router)
    dp.include_router(menu.router)
    dp.include_router(movies.router)
    dp.include_router(friday.router)
    dp.include_router(avatars.router) 
    dp.include_router(shop.router)
    dp.include_router(rating.router)
    dp.include_router(gifts.router)
    dp.include_router(hearts.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)
    dp.include_router(question.router)
    dp.include_router(settings.router)

    setup_scheduler(bot)
    await set_commands(bot)

    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")