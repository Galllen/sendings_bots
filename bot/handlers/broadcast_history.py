from aiogram import Router, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from bot.navigate.keyboards import chats_list_kb_for_history, back_to_history_menu_kb
from db.base import get_chats_paginated, get_chat_by_id, get_sent_history_by_chat
from bot import logger

router = Router()

@router.callback_query(lambda c: c.data.startswith("broadcast_history:"))
async def show_broadcast_chats(callback: types.CallbackQuery):
    _, _, offset_str = callback.data.split(":")
    offset = int(offset_str)
    limit = 5
    chats, total = get_chats_paginated(offset, limit)
    kb = chats_list_kb_for_history(chats, offset, total)
    await callback.message.edit_text(
        "Выберите чат для просмотра истории отправок:",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("chat_history:"))
async def show_chat_history(callback: types.CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    chat = get_chat_by_id(chat_id)
    if not chat:
        await callback.answer("Чат не найден", show_alert=True)
        return

    history = get_sent_history_by_chat(chat_id, limit=10)
    if not history:
        text = f"📭 История отправок для чата '{chat.title or chat.chat_id}' пуста."
    else:
        lines = []
        for h in history:
            account_phone = h.account.phone if h.account else "N/A"
            message_name = h.message.name if h.message else "N/A"
            status_icon = "✅" if h.status == 'success' else "❌"
            sent_time = h.sent_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"{status_icon} {account_phone} – {message_name} ({sent_time})")
        text = f"📋 Последние отправки в чат '{chat.title or chat.chat_id}':\n" + "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=back_to_history_menu_kb())
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_broadcast_history")
async def back_to_broadcast_history(callback: types.CallbackQuery):
    offset = 0
    chats, total = get_chats_paginated(offset, 5)
    kb = chats_list_kb_for_history(chats, offset, total)
    await callback.message.edit_text(
        "Выберите чат для просмотра истории отправок:",
        reply_markup=kb
    )
    await callback.answer()