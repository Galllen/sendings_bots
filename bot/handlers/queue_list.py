import asyncio
from aiogram import Router, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from bot import logger
from bot.navigate.keyboards import (
    main_menu_kb,
    queues_list_kb,
    queue_detail_kb,
    link_chats_kb
)
from db.base import (
    get_queues_paginated,
    get_queue_by_id,
    toggle_queue_status,
    delete_queue,
    create_queue,
    add_queue_messages,
    add_queue_chats,
    get_queue_messages,
    get_queue_chats,
    get_message_by_id,
    get_chat_by_id,
    get_all_chats,
    get_all_messages, get_db
)
from db.model import Message

router = Router()


class CreateQueue(StatesGroup):
    name = State()
    messages = State()
    chats = State()
    interval = State()


def get_all_messages():
    db = next(get_db())
    try:
        return db.query(Message).filter(Message.is_enabled == True).all()
    finally:
        db.close()


@router.callback_query(lambda c: c.data.startswith("queues:"))
async def show_queues(callback: types.CallbackQuery):
    _, _, offset_str = callback.data.split(":")
    offset = int(offset_str)
    limit = 5
    queues, total = get_queues_paginated(offset, limit)
    kb = queues_list_kb(queues, offset, total)
    await callback.message.edit_text("Очереди:", reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("queue:"))
async def show_queue_detail(callback: types.CallbackQuery):
    queue_id = int(callback.data.split(":")[1])
    queue = get_queue_by_id(queue_id)
    if not queue:
        await callback.answer("Очередь не найдена.", show_alert=True)
        return

    messages = get_queue_messages(queue_id)
    msg_list = "\n".join([f"• {m.name} (ID:{m.id})" for m in messages]) or "нет сообщений"

    chats = get_queue_chats(queue_id)
    chat_list = "\n".join([f"• {c.title or 'Без названия'} (ID:{c.id})" for c in chats]) or "нет чатов"

    status = "активна" if queue.is_active else "неактивна"
    text = f"""
📌 Очередь: {queue.name}
⏱ Интервал: {queue.interval_minutes} мин
🕒 Время: {queue.time_start} - {queue.time_end}
✅ Статус: {status}
📨 Сообщения ({len(messages)}):
{msg_list}
💬 Чаты ({len(chats)}):
{chat_list}
    """.strip()

    await callback.message.edit_text(text, reply_markup=queue_detail_kb(queue.id, queue.is_active))
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("toggle_queue:"))
async def toggle_queue_status_handler(callback: types.CallbackQuery):
    queue_id = int(callback.data.split(":")[1])
    new_status = toggle_queue_status(queue_id)
    status_text = "активирована" if new_status else "деактивирована"
    await callback.answer(f"Очередь {status_text}.", show_alert=True)

    queue = get_queue_by_id(queue_id)
    messages = get_queue_messages(queue_id)
    chats = get_queue_chats(queue_id)
    msg_list = "\n".join([f"• {m.name} (ID:{m.id})" for m in messages]) or "нет сообщений"
    chat_list = "\n".join([f"• {c.title or 'Без названия'} (ID:{c.id})" for c in chats]) or "нет чатов"
    status = "активна" if queue.is_active else "неактивна"
    text = f"""
📌 Очередь: {queue.name}
⏱ Интервал: {queue.interval_minutes} мин
🕒 Время: {queue.time_start} - {queue.time_end}
✅ Статус: {status}
📨 Сообщения ({len(messages)}):
{msg_list}
💬 Чаты ({len(chats)}):
{chat_list}
    """.strip()
    await callback.message.edit_text(text, reply_markup=queue_detail_kb(queue.id, queue.is_active))


@router.callback_query(lambda c: c.data.startswith("del_queue:"))
async def delete_queue_handler(callback: types.CallbackQuery):
    queue_id = int(callback.data.split(":")[1])
    success = delete_queue(queue_id)
    if success:
        await callback.answer("✅ Очередь удалена", show_alert=True)
        offset = 0
        queues, total = get_queues_paginated(offset, 5)
        kb = queues_list_kb(queues, offset, total)
        await callback.message.edit_text("Очереди:", reply_markup=kb)
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)


@router.callback_query(lambda c: c.data == "back_to_queues")
async def back_to_queues(callback: types.CallbackQuery):
    offset = 0
    queues, total = get_queues_paginated(offset, 5)
    kb = queues_list_kb(queues, offset, total)
    await callback.message.edit_text("Очереди:", reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите действие:", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(lambda c: c.data == "queue_add")
async def prompt_add_queue(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название очереди:")
    await state.set_state(CreateQueue.name)


@router.message(CreateQueue.name)
async def process_queue_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    all_msgs = get_all_messages()
    if not all_msgs:
        await message.answer("Нет доступных сообщений. Сначала создайте сообщения.")
        await state.clear()
        return
    lines = [f"{msg.id}. {msg.name}" for msg in all_msgs]
    await message.answer(
        "Введите ID сообщений через запятую в порядке отправки.\nДоступные сообщения:\n" + "\n".join(lines)
    )
    await state.set_state(CreateQueue.messages)


@router.message(CreateQueue.messages)
async def process_queue_messages(message: types.Message, state: FSMContext):
    try:
        ids = [int(x.strip()) for x in message.text.split(',') if x.strip().isdigit()]
    except ValueError:
        await message.answer("Ошибка формата. Введите числа через запятую.")
        return

    existing_ids = []
    for msg_id in ids:
        msg = get_message_by_id(msg_id)
        if msg:
            existing_ids.append(msg_id)
        else:
            await message.answer(f"Сообщение с ID {msg_id} не найдено. Попробуйте снова.")
            return

    if not existing_ids:
        await message.answer("Не указано ни одного корректного ID сообщения.")
        return

    await state.update_data(message_ids=existing_ids)

    all_chats = get_all_chats(only_enabled=True)
    if not all_chats:
        await message.answer("Нет доступных чатов. Сначала добавьте чаты.")
        await state.clear()
        return
    lines = [f"{chat.id}. {chat.title or 'Без названия'} (ID чата: {chat.chat_id})" for chat in all_chats]
    await message.answer(
        "Введите ID чатов через запятую, в которые будет отправляться очередь:\n" + "\n".join(lines)
    )
    await state.set_state(CreateQueue.chats)


@router.message(CreateQueue.chats)
async def process_queue_chats(message: types.Message, state: FSMContext):
    try:
        ids = [int(x.strip()) for x in message.text.split(',') if x.strip().isdigit()]
    except ValueError:
        await message.answer("Ошибка формата. Введите числа через запятую.")
        return

    existing_ids = []
    for chat_id in ids:
        chat = get_chat_by_id(chat_id)
        if chat:
            existing_ids.append(chat_id)
        else:
            await message.answer(f"Чат с ID {chat_id} не найден. Попробуйте снова.")
            return

    if not existing_ids:
        await message.answer("Не указано ни одного корректного ID чата.")
        return

    await state.update_data(chat_ids=existing_ids)

    await message.answer(
        "Введите интервал между отправками сообщений в минутах (целое число).\n"
        "Например: 60 (1 час), 120 (2 часа)"
    )
    await state.set_state(CreateQueue.interval)


@router.message(CreateQueue.interval)
async def process_queue_interval(message: types.Message, state: FSMContext):
    try:
        interval = int(message.text.strip())
        if interval < 1:
            await message.answer("Интервал должен быть положительным числом (минимум 1 минута).")
            return
    except ValueError:
        await message.answer("Введите целое число минут.")
        return

    data = await state.get_data()
    name = data['name']
    message_ids = data['message_ids']
    chat_ids = data['chat_ids']

    queue_id = create_queue(name, interval, time_start="10:00", time_end="20:00")  # можно добавить возможность задавать время
    add_queue_messages(queue_id, message_ids)
    add_queue_chats(queue_id, chat_ids)

    await message.answer(f"✅ Очередь '{name}' создана с интервалом {interval} мин!")

    await state.clear()

    offset = 0
    queues, total = get_queues_paginated(offset, 5)
    kb = queues_list_kb(queues, offset, total)
    await message.answer("Очереди:", reply_markup=kb)