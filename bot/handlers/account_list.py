from aiogram import Router, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError
import os
import asyncio
from bot.navigate.keyboards import accounts_list_kb, account_detail_kb, main_menu_kb
from db.base import get_accounts_paginated, get_account_by_id, toggle_account_status, save_account

router = Router()

# Папка для хранения сессий
SESSIONS_DIR = "sessions"

# Убедимся, что папка существует
os.makedirs(SESSIONS_DIR, exist_ok=True)


class AddingAccount(StatesGroup):
    waiting_for_phone = State()
    waiting_for_api_id = State()
    waiting_for_api_hash = State()
    waiting_for_code = State()
    waiting_for_password = State()
    waiting_for_client = State()  # Для хранения клиента между шагами


@router.callback_query(lambda c: c.data == "account_add")
async def prompt_add_account(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📱 Введите номер телефона аккаунта (в формате +79991234567):")
    await state.set_state(AddingAccount.waiting_for_phone)
    await callback.answer()


@router.message(AddingAccount.waiting_for_phone)
async def process_account_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()

    # Валидация номера
    if not phone.startswith('+'):
        await message.answer("❌ Номер должен начинаться с '+'. Попробуйте снова:")
        return

    await state.update_data(phone=phone)
    await message.answer("🔑 Введите API ID (получить на https://my.telegram.org):")
    await state.set_state(AddingAccount.waiting_for_api_id)


@router.message(AddingAccount.waiting_for_api_id)
async def process_api_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ API ID должен быть числом. Попробуйте снова:")
        return

    await state.update_data(api_id=int(message.text))
    await message.answer("🔑 Введите API Hash:")
    await state.set_state(AddingAccount.waiting_for_api_hash)


@router.message(AddingAccount.waiting_for_api_hash)
async def process_api_hash(message: types.Message, state: FSMContext):
    api_hash = message.text.strip()
    if len(api_hash) < 32:
        await message.answer("❌ Неверный формат API Hash. Попробуйте снова:")
        return

    data = await state.get_data()
    phone = data['phone']
    api_id = data['api_id']

    # Генерируем уникальное имя сессии
    session_name = f"{SESSIONS_DIR}/account_{phone.replace('+', '')}"

    # Создаем клиента
    client = TelegramClient(session_name, api_id, api_hash)

    try:
        await client.connect()

        # Отправляем код подтверждения
        await client.send_code_request(phone)

        # Сохраняем клиент и данные в состояние
        await state.update_data(
            client=client,
            api_hash=api_hash,
            session_file=session_name + '.session'
        )

        await message.answer(f"📨 Код подтверждения отправлен на {phone}\nВведите код (без пробелов):")
        await state.set_state(AddingAccount.waiting_for_code)

    except FloodWaitError as e:
        await client.disconnect()
        await message.answer(f"⚠️ Слишком много попыток. Попробуйте через {e.seconds} секунд.")
        await state.clear()
    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка при отправке кода: {str(e)}")
        await state.clear()


@router.message(AddingAccount.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.replace(' ', '').replace('-', '').strip()

    data = await state.get_data()
    client = data.get('client')
    phone = data['phone']
    api_id = data['api_id']
    api_hash = data['api_hash']
    session_file = data['session_file']

    if not client or not client.is_connected():
        await message.answer("❌ Сессия устарела. Начните добавление аккаунта заново.")
        await state.clear()
        return

    try:
        # Пытаемся авторизоваться
        await client.sign_in(phone, code)

        # Проверяем, авторизован ли клиент
        if not await client.is_user_authorized():
            raise SessionPasswordNeededError()

        # Успешная авторизация
        await client.disconnect()

        # Сохраняем аккаунт в БД
        save_account(
            phone=phone,
            session_file=session_file,
            api_id=api_id,
            api_hash=api_hash,
            is_active=True
        )

        await message.answer(
            f"✅ Аккаунт {phone} успешно добавлен!\n"
            f"📁 Сессия сохранена: {session_file}"
        )
        await state.clear()

        # Показываем список аккаунтов
        offset = 0
        accounts, total = get_accounts_paginated(offset, 5)
        kb = accounts_list_kb(accounts, offset, total)
        await message.answer("Аккаунты:", reply_markup=kb)

    except SessionPasswordNeededError:
        # Требуется двухфакторная аутентификация
        await message.answer("🔐 Требуется пароль двухфакторной аутентификации. Введите его:")
        await state.set_state(AddingAccount.waiting_for_password)

    except PhoneCodeInvalidError:
        await message.answer("❌ Неверный код. Попробуйте снова:")

    except FloodWaitError as e:
        await client.disconnect()
        await message.answer(f"⚠️ Слишком много попыток. Попробуйте через {e.seconds} секунд.")
        await state.clear()

    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка авторизации: {str(e)}")
        await state.clear()


@router.message(AddingAccount.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()

    data = await state.get_data()
    client = data.get('client')
    phone = data['phone']
    api_id = data['api_id']
    api_hash = data['api_hash']
    session_file = data['session_file']

    if not client or not client.is_connected():
        await message.answer("❌ Сессия устарела. Начните добавление аккаунта заново.")
        await state.clear()
        return

    try:
        # Авторизуемся с паролем 2FA
        await client.sign_in(password=password)

        # Успешная авторизация
        await client.disconnect()

        # Сохраняем аккаунт в БД
        save_account(
            phone=phone,
            session_file=session_file,
            api_id=api_id,
            api_hash=api_hash,
            is_active=True
        )

        await message.answer(
            f"✅ Аккаунт {phone} успешно добавлен с двухфакторной аутентификацией!\n"
            f"📁 Сессия сохранена: {session_file}"
        )
        await state.clear()

        # Показываем список аккаунтов
        offset = 0
        accounts, total = get_accounts_paginated(offset, 5)
        kb = accounts_list_kb(accounts, offset, total)
        await message.answer("Аккаунты:", reply_markup=kb)

    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка авторизации: {str(e)}\nПопробуйте снова:")
        # Не очищаем состояние — даем еще попытку


# === Обработчики списка и деталей (без изменений) ===
@router.callback_query(lambda c: c.data.startswith("accounts:"))
async def show_accounts(callback: types.CallbackQuery):
    _, _, offset_str = callback.data.split(":")
    offset = int(offset_str)
    limit = 5
    accounts, total = get_accounts_paginated(offset, limit)
    kb = accounts_list_kb(accounts, offset, total)
    await callback.message.edit_text("Аккаунты:", reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("account:"))
async def show_account_detail(callback: types.CallbackQuery):
    acc_id = int(callback.data.split(":")[1])
    acc = get_account_by_id(acc_id)
    if not acc:
        await callback.answer("Аккаунт не найден.", show_alert=True)
        return
    status = "активен" if acc.is_active else "деактивирован"
    text = f"""
Телефон: {acc.phone}
Сессия: {acc.session_file}
API ID: {acc.api_id}
Статус: {status}
""".strip()
    await callback.message.edit_text(text, reply_markup=account_detail_kb(acc.id, acc.is_active))
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("toggle_account:"))
async def toggle_account_status_handler(callback: types.CallbackQuery):
    acc_id = int(callback.data.split(":")[1])
    new_status = toggle_account_status(acc_id)
    status_text = "активирован" if new_status else "деактивирован"
    await callback.answer(f"Аккаунт {status_text}.", show_alert=True)
    acc = get_account_by_id(acc_id)
    text = f"""
Телефон: {acc.phone}
Сессия: {acc.session_file}
API ID: {acc.api_id}
Статус: {'активен' if acc.is_active else 'деактивирован'}
""".strip()
    await callback.message.edit_text(text, reply_markup=account_detail_kb(acc.id, acc.is_active))


@router.callback_query(lambda c: c.data == "back_to_accounts")
async def back_to_accounts(callback: types.CallbackQuery):
    offset = 0
    accounts, total = get_accounts_paginated(offset, 5)
    kb = accounts_list_kb(accounts, offset, total)
    await callback.message.edit_text("Аккаунты:", reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите действие:", reply_markup=main_menu_kb())
    await callback.answer()