import asyncio
from datetime import datetime, timedelta

from bot.handlers.chat_membership import periodic_membership_check
from bot.logger import get_logger
from aiogram import Bot, Dispatcher, F, Router
from aiogram.dispatcher import router
from bot.navigate.start import router as start_router
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers.message_list import router as message_router
from bot.handlers.account_list import router as accounts_router
from bot.handlers.chats_list import router as chats_router
from bot.handlers.queue_list import router as queue_router
from bot.handlers.queue_broadcast import periodic_queue_broadcast

from config import config
from db.base import get_today_successful_sent_count, get_db
from db.model import User

logger = get_logger(__name__)

router = Router()
bot = Bot(token=config.bot_token)
dp = Dispatcher()


async def send_daily_report_to_admins(bot: Bot):
    db = next(get_db())
    try:
        admins = db.query(User).filter(User.role == 'admin').all()
        if not admins:
            return
        today_success = get_today_successful_sent_count()
        message_text = (
            f"📊 Отчёт за {datetime.now().strftime('%Y-%m-%d')}\n"
            f"✅ Успешных отправок: {today_success}"
        )
        for admin in admins:
            try:
                await bot.send_message(admin.telegram_id, message_text)
            except Exception as e:
                logger.error(f"Не удалось отправить отчёт админу {admin.telegram_id}: {e}")
    finally:
        db.close()

async def daily_report(bot: Bot):
    """Фоновая задача – ждёт 20:00 и отправляет отчёт"""
    while True:
        now = datetime.now()
        target = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if now > target:
            target += timedelta(days=1)
        sleep_seconds = (target - now).total_seconds()
        await asyncio.sleep(sleep_seconds)
        try:
            await send_daily_report_to_admins(bot)
        except Exception as e:
            logger.exception(f"Ошибка в daily_report: {e}")



async def main():
    logger.info("Starting bot...")
    dp.include_router(router)

    dp.include_router(message_router)
    dp.include_router(accounts_router)
    dp.include_router(chats_router)
    dp.include_router(start_router)
    dp.include_router(queue_router)

    membership_task = asyncio.create_task(periodic_membership_check())
    report_task = asyncio.create_task(daily_report(bot))
    queue_task = asyncio.create_task(periodic_queue_broadcast())

    try:
        await dp.start_polling(bot)
    finally:
        queue_task.cancel()
        try:
            await queue_task
        except asyncio.CancelledError:
            pass
        membership_task.cancel()
        report_task.cancel()
        try:
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