from aiogram import Router, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from bot.navigate.keyboards import chats_list_kb, chat_detail_kb
from db.base import get_chats_paginated, get_chat_by_id, toggle_chat_status, save_chat

router = Router()

class AddingChat(StatesGroup):
    waiting_for_chat_id = State()
    waiting_for_title = State()

@router.callback_query(lambda c: c.data.startswith("chats:"))
async def show_chats(callback: types.CallbackQuery):
    _, _, offset_str = callback.data.split(":")
    offset = int(offset_str)
    limit = 5
    chats, total = get_chats_paginated(offset, limit)
    kb = chats_list_kb(chats, offset, total)
    await callback.message.edit_text("Чаты:", reply_markup=kb)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("chat:"))
async def show_chat_detail(callback: types.CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    chat = get_chat_by_id(chat_id)
    if not chat:
        await callback.answer("Чат не найден.", show_alert=True)
        return

    status = "активен" if chat.is_enabled else "деактивирован"
    text = f"""
ID: {chat.chat_id}
Название: {chat.title or 'не указано'}
Статус: {status}
    """.strip()

    await callback.message.edit_text(text, reply_markup=chat_detail_kb(chat.id, chat.is_enabled))
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("toggle_chat:"))
async def toggle_chat_status_handler(callback: types.CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    new_status = toggle_chat_status(chat_id)
    status_text = "активирован" if new_status else "деактивирован"
    await callback.answer(f"Чат {status_text}.", show_alert=True)
    # Обновим сообщение
    chat = get_chat_by_id(chat_id)
    text = f"""
ID: {chat.chat_id}
Название: {chat.title or 'не указано'}
Статус: {'активен' if chat.is_enabled else 'деактивирован'}
    """.strip()
    await callback.message.edit_text(text, reply_markup=chat_detail_kb(chat.id, chat.is_enabled))

@router.callback_query(lambda c: c.data == "back_to_chats")
async def back_to_chats(callback: types.CallbackQuery):
    offset = 0
    chats, total = get_chats_paginated(offset, 5)
    kb = chats_list_kb(chats, offset, total)
    await callback.message.edit_text("Чаты:", reply_markup=kb)
    await callback.answer()

# === Добавление ===
@router.callback_query(lambda c: c.data == "chat_add")
async def prompt_add_chat(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID или юзернейм чата (например, @mychat):")
    await state.set_state(AddingChat.waiting_for_chat_id)

@router.message(AddingChat.waiting_for_chat_id)
async def process_chat_id(message: types.Message, state: FSMContext):
    await state.update_data(chat_id=message.text)
    await message.answer("Введите название чата (опционально):")
    await state.set_state(AddingChat.waiting_for_title)

@router.message(AddingChat.waiting_for_title)
async def finish_add_chat(message: types.Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data.get("chat_id")
    title = message.text or None

    save_chat(chat_id, title)

    await message.answer(f"Чат {chat_id} добавлен!")
    await state.clear()

    offset = 0
    chats, total = get_chats_paginated(offset, 5)
    kb = chats_list_kb(chats, offset, total)
    await message.answer("Чаты:", reply_markup=kb)