import asyncio

from bot.handlers.broadcast import periodic_broadcast
from bot.handlers.chat_membership import periodic_membership_check
from bot.logger import get_logger
from aiogram import Bot, Dispatcher, F, Router
from aiogram.dispatcher import router
from bot.navigate.start import router as start_router
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers.message_list import router as message_router
from bot.handlers.account_list import router as accounts_router
from bot.handlers.chats_list import router as chats_router
from config import config


logger = get_logger(__name__)

router = Router()
bot = Bot(token=config.bot_token)
dp = Dispatcher()

async def main():
    logger.info("Starting bot...")
    dp.include_router(router)

    dp.include_router(message_router)
    dp.include_router(accounts_router)
    dp.include_router(chats_router)
    dp.include_router(start_router)

    broadcast_task = asyncio.create_task(periodic_broadcast())
    membership_task = asyncio.create_task(periodic_membership_check())

    try:
        await dp.start_polling(bot)
    finally:
        broadcast_task.cancel()
        membership_task.cancel()
        try:
            await broadcast_task
            await membership_task
        except asyncio.CancelledError:
            pass

    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        logger.info("Bot is running...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")