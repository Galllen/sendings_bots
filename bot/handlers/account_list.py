from aiogram import Router, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    FloodWaitError,
    AuthKeyUnregisteredError
)
import os
import asyncio
from config import config
from db.base import (
    save_account,
    get_accounts_paginated,
    get_account_by_id,
    is_account_session_valid,
    toggle_account_status, del_account_by_id
)
from bot.navigate.keyboards import accounts_list_kb, account_detail_kb

router = Router()
SESSIONS_DIR = config.SESSIONS_DIR


class AddingAccount(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()


def get_session_path(phone: str) -> str:
    """Генерирует путь к файлу сессии по номеру телефона"""
    safe_phone = phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    return os.path.join(SESSIONS_DIR, f"account_{safe_phone}.session")


@router.callback_query(lambda c: c.data.startswith("accounts:start:"))
async def show_accounts_list(callback: types.CallbackQuery, state: FSMContext):
    try:
        offset = int(callback.data.split(":")[2])
        limit = 5

        accounts, total = await asyncio.to_thread(get_accounts_paginated, offset, limit)

        await callback.message.edit_text(
            f"👤 У вас {total} аккаунт(ов):",
            reply_markup=accounts_list_kb(accounts, offset, total)
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"Ошибка загрузки списка: {str(e)}", show_alert=True)


@router.callback_query(lambda c: c.data == "back_to_accounts")
async def back_to_accounts(callback: types.CallbackQuery, state: FSMContext):
    accounts, total = await asyncio.to_thread(get_accounts_paginated, 0, 5)
    await callback.message.edit_text(
        f"👤 У вас {total} аккаунт(ов):",
        reply_markup=accounts_list_kb(accounts, 0, total)
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("account:"))
async def show_account_detail(callback: types.CallbackQuery, state: FSMContext):
    try:
        acc_id = int(callback.data.split(":")[1])
        account = await asyncio.to_thread(get_account_by_id, acc_id)

        if not account:
            await callback.answer("Аккаунт не найден", show_alert=True)
            return

        session_valid = is_account_session_valid(account.session_file)

        status_text = "✅ Активен" if account.is_active else "🔴 Неактивен"
        session_status = "🟢 Сессия валидна" if session_valid else "⚠️ Сессия недоступна"

        text = (
            f"📱 Аккаунт: {account.phone}\n"
            f"Статус: {status_text}\n"
            f"Сессия: {session_status}\n"
            f"Добавлен: {account.added_at.strftime('%Y-%m-%d %H:%M') if account.added_at else '—'}"
        )

        await callback.message.edit_text(
            text,
            reply_markup=account_detail_kb(acc_id, account.is_active, session_valid)
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("toggle_account:"))
async def toggle_account(callback: types.CallbackQuery, state: FSMContext):
    try:
        acc_id = int(callback.data.split(":")[1])
        new_status = await asyncio.to_thread(toggle_account_status, acc_id)
        status_text = "активирован" if new_status else "деактивирован"
        await callback.answer(f"Аккаунт {status_text} ✅", show_alert=True)

        accounts, total = await asyncio.to_thread(get_accounts_paginated, 0, 5)
        await callback.message.edit_text(
            f"👤 У вас {total} аккаунт(ов):",
            reply_markup=accounts_list_kb(accounts, 0, total)
        )
    except Exception as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


@router.callback_query(lambda c: c.data == "account_add")
async def prompt_add_account(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📱 Введите номер телефона аккаунта (в формате +79991234567):\n"
        "ℹ️ Для авторизации используется официальное приложение — "
        "вам не нужно вводить API ID/API Hash."
    )
    await state.set_state(AddingAccount.waiting_for_phone)
    await callback.answer()


@router.message(AddingAccount.waiting_for_phone)
async def process_account_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if not phone.startswith('+'):
        await message.answer("❌ Номер должен начинаться с '+'. Пример: +79991234567")
        return

    session_path = get_session_path(phone)

    client = TelegramClient(
        session_path.replace('.session', ''),
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH
    )

    try:
        await client.connect()

        if await client.is_user_authorized():
            await client.disconnect()
            await asyncio.to_thread(
                save_account,
                phone=phone,
                session_file=session_path,
                api_id=config.TELEGRAM_API_ID,
                api_hash=config.TELEGRAM_API_HASH,
                is_active=True
            )
            await message.answer(f"✅ Аккаунт {phone} уже авторизован!")
            accounts, total = await asyncio.to_thread(get_accounts_paginated, 0, 5)
            await message.answer("👤 Аккаунты:", reply_markup=accounts_list_kb(accounts, 0, total))
            await state.clear()
            return

        sent = await client.send_code_request(phone)
        await client.disconnect()

        await state.update_data(
            phone=phone,
            session_path=session_path,
            phone_code_hash=sent.phone_code_hash
        )
        await message.answer(
            f"📨 Код подтверждения отправлен на {phone}\n"
            "Введите код (обычно 5 цифр, можно вводить слитно):"
        )
        await state.set_state(AddingAccount.waiting_for_code)

    except FloodWaitError as e:
        await client.disconnect()
        await message.answer(f"⚠️ Слишком много запросов. Попробуйте через {e.seconds} секунд.")
        await state.clear()
    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()


@router.message(AddingAccount.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.replace(' ', '').replace('-', '').strip()
    data = await state.get_data()
    phone = data.get('phone')
    session_path = data.get('session_path')
    phone_code_hash = data.get('phone_code_hash')

    if not all([phone, session_path, phone_code_hash]):
        await message.answer("❌ Данные авторизации утеряны. Начните заново.")
        await state.clear()
        return

    client = TelegramClient(
        session_path.replace('.session', ''),
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH
    )

    try:
        await client.connect()
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)

        if not await client.is_user_authorized():
            await client.disconnect()
            await state.update_data(phone=phone, session_path=session_path)
            await message.answer("🔐 Требуется пароль двухфакторной аутентификации. Введите его:")
            await state.set_state(AddingAccount.waiting_for_password)
            return

        await client.disconnect()

        await asyncio.to_thread(
            save_account,
            phone=phone,
            session_file=session_path,
            api_id=config.TELEGRAM_API_ID,
            api_hash=config.TELEGRAM_API_HASH,
            is_active=True
        )

        await message.answer(f"✅ Аккаунт {phone} успешно добавлен!")
        await state.clear()

        accounts, total = await asyncio.to_thread(get_accounts_paginated, 0, 5)
        await message.answer("👤 Аккаунты:", reply_markup=accounts_list_kb(accounts, 0, total))

    except SessionPasswordNeededError:
        await client.disconnect()
        await state.update_data(phone=phone, session_path=session_path)
        await message.answer("🔐 Требуется пароль двухфакторной аутентификации. Введите его:")
        await state.set_state(AddingAccount.waiting_for_password)

    except PhoneCodeInvalidError:
        await client.disconnect()
        await message.answer("❌ Неверный код. Попробуйте снова:")

    except FloodWaitError as e:
        await client.disconnect()
        await message.answer(f"⚠️ Слишком много попыток. Попробуйте через {e.seconds} секунд.")
        await state.clear()

    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()


@router.message(AddingAccount.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    phone = data.get('phone')
    session_path = data.get('session_path')

    if not all([phone, session_path]):
        await message.answer("❌ Данные авторизации утеряны. Начните заново.")
        await state.clear()
        return

    client = TelegramClient(
        session_path.replace('.session', ''),
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH
    )

    try:
        await client.connect()
        await client.sign_in(password=password)
        await client.disconnect()

        await asyncio.to_thread(
            save_account,
            phone=phone,
            session_file=session_path,
            api_id=config.TELEGRAM_API_ID,
            api_hash=config.TELEGRAM_API_HASH,
            is_active=True
        )

        await message.answer(f"✅ Аккаунт {phone} успешно добавлен с 2FA!")
        await state.clear()

        accounts, total = await asyncio.to_thread(get_accounts_paginated, 0, 5)
        await message.answer("👤 Аккаунты:", reply_markup=accounts_list_kb(accounts, 0, total))

    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка авторизации: {str(e)}\nПопробуйте снова:")


@router.callback_query(lambda c: c.data.startswith("del_account:"))
async def delete_account(callback: types.CallbackQuery):
    try:
        acc_id = int(callback.data.split(":")[1])
        success = del_account_by_id(acc_id)
        if success:
            await callback.answer("✅ Аккаунт удалён", show_alert=True)
            accounts, total = await asyncio.to_thread(get_accounts_paginated, 0, 5)
            await callback.message.edit_text(
                f"👤 У вас {total} аккаунт(ов):",
                reply_markup=accounts_list_kb(accounts, 0, total)
            )
        else:
            await callback.answer("❌ Аккаунт не найден", show_alert=True)
    except Exception as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)