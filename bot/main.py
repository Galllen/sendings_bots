import asyncio
import logging
from aiogram import Bot, Dispatcher,F

from config import config

bot = Bot(token=config.bot_token)
dp = Dispatcher()

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
