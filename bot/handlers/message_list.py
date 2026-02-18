from aiogram import Router, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from bot import logger
from bot.navigate.keyboards import main_menu_kb, messages_list_kb, message_detail_kb, link_chats_kb
from db.base import (
    get_messages_paginated,
    get_message_by_id,
    get_chats_by_message_id,
    save_message,
    toggle_message_status,
    get_unlinked_chats_for_message,
    link_message_to_chats,
    get_linked_chats_for_message,
    del_message_by_id
)

router = Router()


class AddingMessage(StatesGroup):
    waiting_for_name = State()
    waiting_for_content = State()
    waiting_for_interval = State()


class LinkingChats(StatesGroup):
    waiting_for_chat_ids = State()


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

    linked_chats = get_linked_chats_for_message(msg_id)
    chat_list = "\n".join(
        [f"• {c.title or 'Без названия'} (ID: {c.id})" for c in linked_chats]) or "нет привязанных чатов"

    status = "вкл." if msg.is_enabled else "выкл."
    text = f"""
📌 Сообщение: {msg.name}
📝 Текст: {msg.content[:100]}{'...' if len(msg.content) > 100 else ''}
⏱️ Интервал: {msg.interval_hours} ч
✅ Статус: {status}
💬 Привязанные чаты:
{chat_list}
""".strip()

    await callback.message.edit_text(text, reply_markup=message_detail_kb(msg.id, msg.is_enabled))
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("del_message:"))
async def del_message(callback: types.CallbackQuery):
    try:
        # Извлекаем ID из колбэка вида "del_message:123"
        msg_id = int(callback.data.split(":")[1].strip())  # ← .strip() защищает от пробелов

        # Вызываем функцию удаления
        success = del_message_by_id(msg_id)

        if success:
            await callback.answer(f"✅ Сообщение ID={msg_id} удалено", show_alert=True)

            # Возвращаемся к списку сообщений
            offset = 0
            messages, total = get_messages_paginated(offset, 5)
            kb = messages_list_kb(messages, offset, total)
            await callback.message.edit_text("Сообщения:", reply_markup=kb)
        else:
            await callback.answer(f"⚠️ Сообщение ID={msg_id} не найдено", show_alert=True)

    except (IndexError, ValueError) as e:
        # Логируем ошибку для отладки
        logger.error(f"Ошибка парсинга ID при удалении: callback_data='{callback.data}', error={e}")
        await callback.answer("❌ Ошибка формата данных. Обратитесь к администратору.", show_alert=True)
    except NameError as e:
        # Если функция del_message_by_id не импортирована
        logger.critical(f"Функция del_message_by_id не найдена! Ошибка: {e}")
        await callback.answer("❌ Критическая ошибка: функция удаления не загружена", show_alert=True)
    except Exception as e:
        logger.exception(f"Неожиданная ошибка при удалении сообщения: {e}")
        await callback.answer(f"❌ Ошибка удаления: {str(e)[:50]}", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("toggle_message_status:"))
async def toggle_message_status_handler(callback: types.CallbackQuery):
    msg_id = int(callback.data.split(":")[1])
    new_status = toggle_message_status(msg_id)
    status_text = "активировано" if new_status else "деактивировано"
    await callback.answer(f"Сообщение {status_text}.", show_alert=True)

    msg = get_message_by_id(msg_id)
    linked_chats = get_linked_chats_for_message(msg_id)
    chat_list = "\n".join(
        [f"• {c.title or 'Без названия'} (ID: {c.id})" for c in linked_chats]) or "нет привязанных чатов"

    status = "вкл." if msg.is_enabled else "выкл."
    text = f"""
📌 Сообщение: {msg.name}
📝 Текст: {msg.content[:100]}{'...' if len(msg.content) > 100 else ''}
⏱️ Интервал: {msg.interval_hours} ч
✅ Статус: {status}
💬 Привязанные чаты:
{chat_list}
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
    await message.answer(
        "Введите интервал отправки в часах (можно дробное значение):\n"
        "• 0.1 = 6 минут\n"
        "• 0.5 = 30 минут\n"
        "• 1 = 1 час\n"
        "• 24 = 1 день"
    )
    await state.set_state(AddingMessage.waiting_for_interval)


@router.message(AddingMessage.waiting_for_interval)
async def finish_add_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("name")
    content = data.get("content")

    try:
        interval = float(message.text.strip().replace(',', '.'))
        if interval < 0.1:
            await message.answer("❌ Минимальный интервал: 0.1 часа (6 минут). Попробуйте снова:")
            return
        if interval > 168:  # 7 дней
            await message.answer("❌ Максимальный интервал: 168 часов (7 дней). Попробуйте снова:")
            return
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число (например: 0.5, 1, 24):")
        return

    msg_id = save_message(name, content, interval)

    await message.answer(f"✅ Сообщение '{name}' добавлено с интервалом {interval}ч!")
    await state.clear()

    offset = 0
    messages, total = get_messages_paginated(offset, 5)
    kb = messages_list_kb(messages, offset, total)
    await message.answer("Сообщения:", reply_markup=kb)


@router.callback_query(lambda c: c.data.startswith("link_chats:"))
async def start_linking_chats(callback: types.CallbackQuery, state: FSMContext):
    msg_id = int(callback.data.split(":")[1])
    unlinked_chats = get_unlinked_chats_for_message(msg_id)

    if not unlinked_chats:
        await callback.answer("Нет доступных чатов для привязки", show_alert=True)
        return

    chat_list = "\n".join([
        f"{i + 1}. {c.title or 'Без названия'} (ID: {c.id})"
        for i, c in enumerate(unlinked_chats[:10])
    ])

    await state.update_data(
        message_id=msg_id,
        available_chat_ids=[c.id for c in unlinked_chats[:10]]
    )

    await callback.message.edit_text(
        f"📎 Привязка чатов к сообщению\n\n"
        f"Доступные чаты:\n{chat_list}\n\n"
        f"Отправьте ID чата (или несколько через запятую, например: 1,3,5):",
        reply_markup=link_chats_kb(msg_id)
    )
    await state.set_state(LinkingChats.waiting_for_chat_ids)
    await callback.answer()


@router.message(LinkingChats.waiting_for_chat_ids)
async def process_chat_ids(message: types.Message, state: FSMContext):
    data = await state.get_data()
    msg_id = data['message_id']
    available_chat_ids = data['available_chat_ids']

    try:
        input_ids = message.text.strip().replace(' ', ',').split(',')
        selected_ids = []

        for id_str in input_ids:
            id_str = id_str.strip()
            if not id_str:
                continue
            try:
                idx = int(id_str) - 1
                if 0 <= idx < len(available_chat_ids):
                    selected_ids.append(available_chat_ids[idx])
                else:
                    # Попробуем как реальный ID чата
                    chat_id = int(id_str)
                    if chat_id in available_chat_ids:
                        selected_ids.append(chat_id)
            except ValueError:
                continue

        if not selected_ids:
            await message.answer("❌ Не найдено подходящих чатов. Попробуйте снова:")
            return

        success = link_message_to_chats(msg_id, selected_ids)

        if success:
            linked_chats = get_linked_chats_for_message(msg_id)
            chat_names = ", ".join([c.title or f"ID:{c.id}" for c in linked_chats])
            await message.answer(f"✅ Чаты привязаны: {chat_names}")
        else:
            await message.answer("❌ Ошибка при привязке чатов")

        await state.clear()


        msg = get_message_by_id(msg_id)
        linked_chats = get_linked_chats_for_message(msg_id)
        chat_list = "\n".join(
            [f"• {c.title or 'Без названия'} (ID: {c.id})" for c in linked_chats]) or "нет привязанных чатов"

        status = "вкл." if msg.is_enabled else "выкл."
        text = f"""
📌 Сообщение: {msg.name}
📝 Текст: {msg.content[:100]}{'...' if len(msg.content) > 100 else ''}
⏱️ Интервал: {msg.interval_hours} ч
✅ Статус: {status}
💬 Привязанные чаты:
{chat_list}
""".strip()

        await message.answer(text, reply_markup=message_detail_kb(msg.id, msg.is_enabled))

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()