from aiogram import types, Router
from bot.navigate.keyboards import main_menu_kb, reply_menu_kb
from db.base import get_user_role, set_user_role
from bot.logger import get_logger

logger = get_logger(__name__)
router = Router()

@router.message(lambda msg: msg.text == "/start")
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    role = get_user_role(user_id)

    if role != "admin":
        await message.answer("❌ У вас нет доступа к этому боту.")
        logger.warning(f"Access denied for user {user_id} (role: {role}).")
        return

    logger.info(f"User {user_id} (admin) started the bot.")
    await message.answer("Выберите действие:", reply_markup=reply_menu_kb())
    await message.answer("Меню:", reply_markup=main_menu_kb())


@router.message(lambda msg: msg.text == "/get_access")
async def cmd_get_access(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"

    set_user_role(user_id, username, role="admin")

    await message.answer("🔓 Доступ получен!")
    logger.info(f"User {user_id} ({username}) got access and set to 'admin'.")