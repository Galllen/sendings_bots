from aiogram import Router, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from bot.navigate.keyboards import main_menu_kb, messages_list_kb, message_detail_kb
from db.base import get_messages_paginated, get_message_by_id, get_chats_by_message_id, save_message, toggle_message_status

router = Router()

@router.callback_query(lambda c: c.data.startswith("messages:"))
async def show_messages(callback: types.CallbackQuery):
    _, _, offset_str = callback.data.split(":")
    offset = int(offset_str)
    limit = 5
    messages, total = get_messages_paginated(offset, limit)
    kb = messages_list_kb(messages, offset, total)
    await callback.message.edit_text("Сообщения:", reply_markup=kb)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("message:"))
async def show_message_detail(callback: types.CallbackQuery):
    msg_id = int(callback.data.split(":")[1])
    msg = get_message_by_id(msg_id)
    if not msg:
        await callback.answer("Сообщение не найдено.", show_alert=True)
        return

    chats = get_chats_by_message_id(msg_id)
    chat_ids = ", ".join([c.chat_id for c in chats]) or "нет"

    status = "вкл." if msg.is_enabled else "выкл."
    text = f"""
Сообщение: {msg.content}
Частота отправки: {msg.interval_hours} часов
Включено: {status}
Список чатов: {chat_ids}
    """.strip()

    await callback.message.edit_text(text, reply_markup=message_detail_kb(msg.id, msg.is_enabled))
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("toggle_message_status:"))
async def toggle_message_status_handler(callback: types.CallbackQuery):
    msg_id = int(callback.data.split(":")[1])  # ✅
    new_status = toggle_message_status(msg_id)
    status_text = "активировано" if new_status else "деактивировано"
    await callback.answer(f"Сообщение {status_text}.", show_alert=True)

    msg = get_message_by_id(msg_id)
    chats = get_chats_by_message_id(msg_id)
    chat_ids = ", ".join([c.chat_id for c in chats]) or "нет"
    status = "вкл." if msg.is_enabled else "выкл."
    text = f"""
Сообщение: {msg.content}
Частота отправки: {msg.interval_hours} часов
Включено: {status}
Список чатов: {chat_ids}
    """.strip()

    await callback.message.edit_text(text, reply_markup=message_detail_kb(msg.id, msg.is_enabled))

@router.callback_query(lambda c: c.data.startswith("toggle_message_status:"))
async def toggle_message_status_handler(callback: types.CallbackQuery):
    msg_id = int(callback.data.split(":")[1])
    new_status = toggle_message_status(msg_id)
    status_text = "активировано" if new_status else "деактивировано"
    await callback.answer(f"Сообщение {status_text}.", show_alert=True)


    msg = get_message_by_id(msg_id)
    chats = get_chats_by_message_id(msg_id)
    chat_ids = ", ".join([c.chat_id for c in chats]) or "нет"
    status = "вкл." if msg.is_enabled else "выкл."
    text = f"""
Сообщение: {msg.content}
Частота отправки: {msg.interval_hours} часов
Включено: {status}
Список чатов: {chat_ids}
    """.strip()

    await callback.message.edit_text(text, reply_markup=message_detail_kb(msg.id, msg.is_enabled))

@router.callback_query(lambda c: c.data == "back_to_messages")
async def back_to_messages(callback: types.CallbackQuery):
    offset = 0
    messages, total = get_messages_paginated(offset, 5)
    kb = messages_list_kb(messages, offset, total)
    await callback.message.edit_text("Сообщения:", reply_markup=kb)
    await callback.answer()

@router.callback_query(lambda c: c.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите действие:", reply_markup=main_menu_kb())
    await callback.answer()


class AddingMessage(StatesGroup):
    waiting_for_name = State()
    waiting_for_content = State()
    waiting_for_interval = State()

@router.callback_query(lambda c: c.data == "message_add")
async def prompt_add_message(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название сообщения:")
    await state.set_state(AddingMessage.waiting_for_name)

@router.message(AddingMessage.waiting_for_name)
async def process_message_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите содержимое сообщения:")
    await state.set_state(AddingMessage.waiting_for_content)

@router.message(AddingMessage.waiting_for_content)
async def process_message_content(message: types.Message, state: FSMContext):
    await state.update_data(content=message.text)
    await message.answer("Введите интервал в часах (по умолчанию 24):")
    await state.set_state(AddingMessage.waiting_for_interval)

@router.message(AddingMessage.waiting_for_interval)
async def finish_add_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("name")
    content = data.get("content")
    interval = int(message.text) if message.text.isdigit() else 24

    save_message(name, content, interval)

    await message.answer(f"Сообщение '{name}' добавлено!")
    await state.clear()


    offset = 0
    messages, total = get_messages_paginated(offset, 5)
    kb = messages_list_kb(messages, offset, total)
    await message.answer("Сообщения:", reply_markup=kb)